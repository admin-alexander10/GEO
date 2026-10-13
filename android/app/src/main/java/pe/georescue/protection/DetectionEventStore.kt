package pe.georescue.protection

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class DetectionEventStore(context: Context) :
    SQLiteOpenHelper(context.applicationContext, "protection_events.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE detection_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at_ms INTEGER NOT NULL,
                mean_m_s2 REAL NOT NULL,
                peak_m_s2 REAL NOT NULL,
                sta_lta REAL NOT NULL,
                severity_hint INTEGER NOT NULL,
                result TEXT NOT NULL,
                discard_reason TEXT
            )
            """.trimIndent(),
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        throw IllegalStateException("No destructive database upgrade is defined.")
    }

    @Synchronized
    fun record(metrics: DetectionMetrics, result: String): Long {
        val values = ContentValues().apply {
            put("occurred_at_ms", System.currentTimeMillis())
            put("mean_m_s2", metrics.meanAcceleration)
            put("peak_m_s2", metrics.peakAcceleration)
            put("sta_lta", metrics.staLtaRatio)
            put("severity_hint", metrics.severityHint)
            put("result", result)
            put("discard_reason", metrics.discardReason)
        }
        val id = writableDatabase.insertOrThrow("detection_events", null, values)
        return id
    }

    @Synchronized
    fun updateResult(id: Long, result: String) {
        val values = ContentValues().apply { put("result", result) }
        val updated = writableDatabase.update(
            "detection_events",
            values,
            "id = ?",
            arrayOf(id.toString()),
        )
        check(updated == 1) { "Detection event $id no longer exists." }
    }
}
