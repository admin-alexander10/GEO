package pe.georescue.protection

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import kotlin.math.PI
import kotlin.math.sin

class EarthquakeDetectorTest {
    @Test
    fun sustainedNonPeriodicShakingProducesCandidateAndSeverityHint() {
        val detector = EarthquakeDetector()
        var result: DetectorResult? = null
        var timestamp = 0L
        repeat(500) {
            timestamp += 20_000_000L
            detector.process(timestamp, 0.0, 0.0, 9.81)
        }
        repeat(300) { index ->
            timestamp += 20_000_000L
            val t = index / 50.0
            val irregularShaking = 3.5 * sin(2.0 * PI * 5.0 * t) +
                2.4 * sin(2.0 * PI * 7.3 * t)
            result = detector.process(timestamp, irregularShaking, 0.0, 9.81) ?: result
        }

        val candidate = result as? DetectorResult.Candidate
            ?: error("Expected a sustained shaking candidate.")
        assertEquals(4, candidate.metrics.severityHint)
        assertEquals(7, candidate.metrics.countdownSeconds)
    }

    @Test
    fun sustainedRegularWalkingFrequencyIsRecordedAsDiscardableMotion() {
        val detector = EarthquakeDetector()
        var result: DetectorResult? = null
        var timestamp = 0L
        repeat(500) {
            timestamp += 20_000_000L
            detector.process(timestamp, 0.0, 0.0, 9.81)
        }
        repeat(400) { index ->
            timestamp += 20_000_000L
            val t = index / 50.0
            val walk = 4.0 * sin(2.0 * PI * 1.0 * t)
            result = detector.process(timestamp, walk, 0.0, 9.81) ?: result
        }

        val discarded = result as? DetectorResult.Discarded
            ?: error("Expected periodic movement to be discarded.")
        assertEquals("PERIODIC_MOVEMENT_1_3_HZ", discarded.metrics.discardReason)
    }

    @Test
    fun isolatedAccelerationPeakDoesNotTrigger() {
        val detector = EarthquakeDetector()
        var timestamp = 0L
        repeat(500) {
            timestamp += 20_000_000L
            assertNull(detector.process(timestamp, 0.0, 0.0, 9.81))
        }
        repeat(100) { index ->
            timestamp += 20_000_000L
            val x = if (index == 40) 30.0 else 0.0
            assertNull(detector.process(timestamp, x, 0.0, 9.81))
        }
    }

    @Test
    fun freeFallFollowedByImpactIsDiscarded() {
        val detector = EarthquakeDetector()
        var result: DetectorResult? = null
        var timestamp = 0L
        repeat(500) {
            timestamp += 20_000_000L
            detector.process(timestamp, 0.0, 0.0, 9.81)
        }
        timestamp += 20_000_000L
        detector.process(timestamp, 0.0, 0.0, 0.0)
        timestamp += 20_000_000L
        detector.process(timestamp, 25.0, 0.0, 9.81)
        repeat(300) { index ->
            timestamp += 20_000_000L
            val t = index / 50.0
            val shaking = 3.5 * sin(2.0 * PI * 5.0 * t) +
                2.4 * sin(2.0 * PI * 7.3 * t)
            result = detector.process(timestamp, shaking, 0.0, 9.81) ?: result
        }

        val discarded = result as? DetectorResult.Discarded
            ?: error("Expected free-fall impact to be discarded.")
        assertEquals("FREE_FALL_IMPACT", discarded.metrics.discardReason)
    }
}
