package pe.georescue.protection

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase

@Entity(tableName = "protection_config")
data class ProtectionConfigEntity(
    @PrimaryKey val id: Int = 1,
    val apiBaseUrl: String = "",
    val platformPhone: String = "",
    val username: String = "",
    val phonePendingOtp: String = "",
    val verifiedPhone: String = "",
    val deviceId: String = "",
    val encryptedToken: String = "",
    val encryptedSigningSecret: String = "",
)

@Entity(tableName = "trusted_contacts")
data class TrustedContactEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val name: String,
    val phone: String,
    val consentedAt: Long,
)

@Entity(tableName = "automatic_alerts")
data class AutomaticAlertEntity(
    @PrimaryKey val clientAlertId: String,
    val detectionEventId: Long,
    val severity: Int,
    val latitude: Double?,
    val longitude: Double?,
    val precisionMeters: Int?,
    val ageSeconds: Long?,
    val locationAgeRecordedAt: Long?,
    val timestampSeconds: Long,
    val status: String = "OPEN",
    val apiState: String = "PENDING",
    val serverAlertId: Int? = null,
    val signedSmsState: String = "PENDING",
    val createdAt: Long = System.currentTimeMillis(),
)

@Entity(tableName = "delivery_attempts")
data class DeliveryAttemptEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val clientAlertId: String,
    val channel: String,
    val target: String,
    val type: String,
    val attemptedAt: Long,
    val result: String,
    val detail: String = "",
)

@Dao
interface ProtectionDao {
    @Query("SELECT * FROM protection_config WHERE id = 1")
    fun getConfig(): ProtectionConfigEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun saveConfig(config: ProtectionConfigEntity)

    @Insert
    fun addContact(contact: TrustedContactEntity)

    @Query("SELECT * FROM trusted_contacts ORDER BY id")
    fun getContacts(): List<TrustedContactEntity>

    @Query("SELECT COUNT(*) FROM trusted_contacts WHERE consentedAt > 0")
    fun consentedContactCount(): Int

    @Query("SELECT * FROM automatic_alerts WHERE clientAlertId = :id")
    fun getAlert(id: String): AutomaticAlertEntity?

    @Query("SELECT * FROM automatic_alerts WHERE status = 'OPEN' ORDER BY createdAt")
    fun getOpenAlerts(): List<AutomaticAlertEntity>

    @Query("SELECT * FROM automatic_alerts ORDER BY createdAt DESC LIMIT 1")
    fun getLatestAlert(): AutomaticAlertEntity?

    @Query("SELECT * FROM automatic_alerts WHERE status = 'OPEN' ORDER BY createdAt DESC LIMIT 1")
    fun getLatestOpenAlert(): AutomaticAlertEntity?

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    fun insertAlert(alert: AutomaticAlertEntity): Long

    @Query("UPDATE automatic_alerts SET latitude = :latitude, longitude = :longitude, precisionMeters = :precision, ageSeconds = :age, locationAgeRecordedAt = :observedAt WHERE clientAlertId = :id AND status = 'OPEN'")
    fun updateLocation(id: String, latitude: Double, longitude: Double, precision: Int, age: Long, observedAt: Long): Int

    @Query("UPDATE automatic_alerts SET apiState = :state WHERE clientAlertId = :id")
    fun updateApiState(id: String, state: String)

    @Query("UPDATE automatic_alerts SET serverAlertId = :serverId WHERE clientAlertId = :id")
    fun updateServerAlertId(id: String, serverId: Int)

    @Query("UPDATE automatic_alerts SET signedSmsState = :state WHERE clientAlertId = :id")
    fun updateSmsState(id: String, state: String)

    @Query("UPDATE automatic_alerts SET status = :state WHERE clientAlertId = :id AND status = 'OPEN'")
    fun closeAlert(id: String, state: String): Int

    @Insert
    fun addAttempt(attempt: DeliveryAttemptEntity): Long

    @Query("UPDATE delivery_attempts SET result = :result, detail = :detail WHERE id = :attemptId")
    fun updateAttempt(attemptId: Long, result: String, detail: String)

    @Query("SELECT * FROM delivery_attempts WHERE id = :attemptId")
    fun getAttempt(attemptId: Long): DeliveryAttemptEntity?

    @Query("SELECT COUNT(*) FROM delivery_attempts WHERE clientAlertId = :alertId AND channel = :channel AND result IN ('SMS_SENT_TO_NETWORK', 'SMS_DELIVERED')")
    fun successfulAttemptCount(alertId: String, channel: String): Int

    @Query("SELECT COUNT(*) FROM delivery_attempts WHERE clientAlertId = :alertId AND channel = :channel AND type = :type AND result IN ('SMS_SENT_TO_NETWORK', 'SMS_DELIVERED')")
    fun successfulAttemptCountForType(alertId: String, channel: String, type: String): Int

    @Query("SELECT COUNT(*) FROM delivery_attempts WHERE clientAlertId = :alertId AND channel = :channel AND type = :type")
    fun attemptCountForType(alertId: String, channel: String, type: String): Int

    @Query("SELECT COUNT(*) FROM delivery_attempts WHERE clientAlertId = :alertId AND channel = :channel AND target = :target AND type = :type AND result IN ('SMS_SENT_TO_NETWORK', 'SMS_DELIVERED')")
    fun successfulTargetAttemptCount(alertId: String, channel: String, target: String, type: String): Int

    @Query("SELECT * FROM delivery_attempts WHERE clientAlertId = :alertId ORDER BY attemptedAt DESC")
    fun getAttempts(alertId: String): List<DeliveryAttemptEntity>
}

fun AutomaticAlertEntity.currentLocationAgeSeconds(nowMillis: Long = System.currentTimeMillis()): Long? =
    ageSeconds?.let { age ->
        val recordedAt = locationAgeRecordedAt ?: createdAt
        (age + ((nowMillis - recordedAt).coerceAtLeast(0L) / 1000L)).coerceAtMost(31536000L)
    }

@Database(
    entities = [
        ProtectionConfigEntity::class,
        TrustedContactEntity::class,
        AutomaticAlertEntity::class,
        DeliveryAttemptEntity::class,
    ],
    version = 1,
    exportSchema = false,
)
abstract class ProtectionDatabase : RoomDatabase() {
    abstract fun protectionDao(): ProtectionDao

    companion object {
        @Volatile
        private var instance: ProtectionDatabase? = null

        fun get(context: Context): ProtectionDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    ProtectionDatabase::class.java,
                    "protection_outbox.db",
                ).build().also { instance = it }
            }
    }
}
