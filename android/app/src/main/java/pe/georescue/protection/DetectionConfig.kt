package pe.georescue.protection

data class DetectionConfig(
    val highPassAlpha: Double = 0.8,
    val samplePeriodNanos: Long = 20_000_000L,
    val shortWindowNanos: Long = 500_000_000L,
    val longWindowNanos: Long = 10_000_000_000L,
    val staLtaRatioThreshold: Double = 3.0,
    val minimumMeanAcceleration: Double = 0.8,
    val sustainedDurationNanos: Long = 3_000_000_000L,
    val lowSeverityMaximum: Double = 2.0,
    val highSeverityMaximum: Double = 4.0,
    val ordinaryCountdownSeconds: Int = 10,
    val severeCountdownSeconds: Int = 7,
    val freeFallThreshold: Double = 2.0,
    val impactThreshold: Double = 20.0,
    val impactSuppressionNanos: Long = 2_000_000_000L,
    val humanMotionMinimumPeriodSeconds: Double = 1.0 / 3.0,
    val humanMotionMaximumPeriodSeconds: Double = 1.0,
    val humanMotionMaximumPeriodCv: Double = 0.25,
)

data class DetectionMetrics(
    val timestampNanos: Long,
    val meanAcceleration: Double,
    val peakAcceleration: Double,
    val staLtaRatio: Double,
    val severityHint: Int,
    val countdownSeconds: Int,
    val discardReason: String? = null,
)

sealed class DetectorResult {
    data class Candidate(val metrics: DetectionMetrics) : DetectorResult()
    data class Discarded(val metrics: DetectionMetrics) : DetectorResult()
}
