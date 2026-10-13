package pe.georescue.protection

import java.util.ArrayDeque
import kotlin.math.sqrt

class EarthquakeDetector(initialConfig: DetectionConfig = DetectionConfig()) {
    @Volatile
    var config: DetectionConfig = initialConfig
        set(value) {
            require(value.highPassAlpha in 0.0..1.0)
            require(value.samplePeriodNanos > 0L)
            require(value.shortWindowNanos > 0L)
            require(value.longWindowNanos > value.shortWindowNanos)
            require(value.staLtaRatioThreshold > 0.0)
            require(value.minimumMeanAcceleration > 0.0)
            require(value.sustainedDurationNanos > 0L)
            require(value.lowSeverityMaximum > 0.0)
            require(value.highSeverityMaximum > value.lowSeverityMaximum)
            require(value.ordinaryCountdownSeconds > 0)
            require(value.severeCountdownSeconds > 0)
            require(value.freeFallThreshold > 0.0)
            require(value.impactThreshold > value.freeFallThreshold)
            require(value.impactSuppressionNanos >= 0L)
            require(value.humanMotionMinimumPeriodSeconds > 0.0)
            require(value.humanMotionMaximumPeriodSeconds > value.humanMotionMinimumPeriodSeconds)
            require(value.humanMotionMaximumPeriodCv >= 0.0)
            field = value
        }

    private data class TimedMagnitude(val timestamp: Long, val magnitude: Double)

    private val samples = ArrayDeque<TimedMagnitude>()
    private val peakTimes = ArrayDeque<Long>()
    private var gravityX = 0.0
    private var gravityY = 0.0
    private var gravityZ = 0.0
    private var gravityInitialized = false
    private var previousMagnitude = 0.0
    private var previousWasPeak = false
    private var freeFallAtNanos: Long? = null
    private var freeFallImpactAtNanos: Long? = null
    private var conditionStartNanos: Long? = null

    init {
        config = initialConfig
    }

    @Synchronized
    fun process(timestampNanos: Long, x: Double, y: Double, z: Double): DetectorResult? {
        val currentConfig = config
        if (!x.isFinite() || !y.isFinite() || !z.isFinite() || timestampNanos < 0L) return null
        val rawMagnitude = magnitude(x, y, z)
        if (rawMagnitude < currentConfig.freeFallThreshold) freeFallAtNanos = timestampNanos
        val freeFall = freeFallAtNanos
        if (
            freeFall != null &&
            timestampNanos - freeFall in 0..1_000_000_000L &&
            rawMagnitude >= currentConfig.impactThreshold
        ) {
            freeFallImpactAtNanos = timestampNanos
        }
        if (freeFall != null && timestampNanos - freeFall > 1_000_000_000L) {
            freeFallAtNanos = null
        }

        if (!gravityInitialized) {
            gravityX = x
            gravityY = y
            gravityZ = z
            gravityInitialized = true
        } else {
            val alpha = currentConfig.highPassAlpha
            gravityX = alpha * gravityX + (1.0 - alpha) * x
            gravityY = alpha * gravityY + (1.0 - alpha) * y
            gravityZ = alpha * gravityZ + (1.0 - alpha) * z
        }
        val filteredMagnitude = magnitude(x - gravityX, y - gravityY, z - gravityZ)
        samples.addLast(TimedMagnitude(timestampNanos, filteredMagnitude))
        while (
            samples.isNotEmpty() &&
            timestampNanos - samples.first().timestamp > currentConfig.longWindowNanos
        ) {
            samples.removeFirst()
        }
        updatePeriodicity(timestampNanos, filteredMagnitude, currentConfig)

        val longWindowStart = timestampNanos - currentConfig.longWindowNanos
        if ((samples.firstOrNull()?.timestamp ?: timestampNanos) > longWindowStart) return null
        val shortStart = timestampNanos - currentConfig.shortWindowNanos
        val shortValues = samples.filter { it.timestamp >= shortStart }.map { it.magnitude }
        val longValues = samples.filter { it.timestamp < shortStart }.map { it.magnitude }
        if (shortValues.isEmpty() || longValues.isEmpty()) return null

        val sta = shortValues.average()
        val lta = longValues.average()
        val ratio = sta / maxOf(lta, 0.05)
        if (sta <= currentConfig.minimumMeanAcceleration) {
            conditionStartNanos = null
            return null
        }

        val startedAt = conditionStartNanos ?: if (ratio > currentConfig.staLtaRatioThreshold) {
            timestampNanos.also { conditionStartNanos = it }
        } else {
            return null
        }
        if (timestampNanos - startedAt < currentConfig.sustainedDurationNanos) return null

        val sustainedStart = timestampNanos - currentConfig.sustainedDurationNanos
        val sustainedMagnitudes = samples
            .filter { it.timestamp >= sustainedStart }
            .map { it.magnitude }
        val sustainedMean = sustainedMagnitudes.average()
        val severity = when {
            sustainedMean > currentConfig.highSeverityMaximum -> 5
            sustainedMean >= currentConfig.lowSeverityMaximum -> 4
            else -> 3
        }
        val discardReason = when {
            freeFallImpactAtNanos?.let {
                timestampNanos - it <= currentConfig.sustainedDurationNanos +
                    currentConfig.impactSuppressionNanos
            } == true -> "FREE_FALL_IMPACT"
            isRegularHumanMotion(currentConfig) -> "PERIODIC_MOVEMENT_1_3_HZ"
            else -> null
        }
        val metrics = DetectionMetrics(
            timestampNanos = timestampNanos,
            meanAcceleration = sustainedMean,
            peakAcceleration = sustainedMagnitudes.maxOrNull() ?: filteredMagnitude,
            staLtaRatio = ratio,
            severityHint = severity,
            countdownSeconds = if (severity >= 4) {
                currentConfig.severeCountdownSeconds
            } else {
                currentConfig.ordinaryCountdownSeconds
            },
            discardReason = discardReason,
        )
        conditionStartNanos = null
        return if (discardReason == null) DetectorResult.Candidate(metrics) else DetectorResult.Discarded(metrics)
    }

    @Synchronized
    fun reset() {
        samples.clear()
        peakTimes.clear()
        gravityInitialized = false
        previousMagnitude = 0.0
        previousWasPeak = false
        freeFallAtNanos = null
        freeFallImpactAtNanos = null
        conditionStartNanos = null
    }

    private fun updatePeriodicity(timestampNanos: Long, magnitude: Double, config: DetectionConfig) {
        val rising = magnitude >= config.minimumMeanAcceleration && magnitude > previousMagnitude
        if (previousWasPeak && magnitude < previousMagnitude) peakTimes.addLast(timestampNanos)
        previousWasPeak = rising
        previousMagnitude = magnitude
        while (peakTimes.isNotEmpty() && timestampNanos - peakTimes.first() > 4_000_000_000L) {
            peakTimes.removeFirst()
        }
    }

    private fun isRegularHumanMotion(config: DetectionConfig): Boolean {
        if (peakTimes.size < 4) return false
        val periods = peakTimes.toList()
            .zipWithNext { left, right -> (right - left) / 1_000_000_000.0 }
        val mean = periods.average()
        if (mean !in config.humanMotionMinimumPeriodSeconds..config.humanMotionMaximumPeriodSeconds) {
            return false
        }
        val variance = periods.sumOf { (it - mean) * (it - mean) } / periods.size
        return sqrt(variance) / mean <= config.humanMotionMaximumPeriodCv
    }

    private fun magnitude(x: Double, y: Double, z: Double): Double =
        sqrt(x * x + y * y + z * z)
}
