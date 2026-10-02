package com.workflow.stream.sync

import android.content.Context
import android.util.Log
import androidx.work.*
import com.workflow.stream.network.ApiClient
import com.workflow.stream.notifications.NotificationHelper
import java.util.concurrent.TimeUnit

class TaskSyncWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    private val TAG = "TaskSyncWorker"

    override suspend fun doWork(): Result {
        Log.d(TAG, "Executing background task synchronization...")
        val sharedPrefs = applicationContext.getSharedPreferences("workflow_prefs", Context.MODE_PRIVATE)
        val serverHost = sharedPrefs.getString("server_host", "http://10.0.2.2:8765") ?: "http://10.0.2.2:8765"

        val apiClient = ApiClient(serverHost)
        val notifHelper = NotificationHelper(applicationContext)

        val priorityResult = apiClient.getPriorities()
        if (priorityResult.isSuccess) {
            val data = priorityResult.getOrNull()
            data?.immediateFocus?.let { focus ->
                Log.d(TAG, "Background sync discovered active priority: $focus")
                // Only alert if there is a critical first task
                if (focus.contains("(first)", ignoreCase = true)) {
                    notifHelper.showTaskReminder(
                        title = "Critical Action Item",
                        message = "$focus
${data.rezoningSuggestion ?: ""}"
                    )
                }
            }
            return Result.success()
        } else {
            Log.w(TAG, "Background sync failed to contact server: ${priorityResult.exceptionOrNull()?.message}")
            return Result.retry()
        }
    }

    companion object {
        private const val SYNC_WORK_NAME = "workflow_stream_sync_work"

        fun schedulePeriodicSync(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .setRequiresBatteryNotLow(true)
                .build()

            val syncRequest = PeriodicWorkRequestBuilder<TaskSyncWorker>(
                repeatInterval = 30,
                repeatIntervalTimeUnit = TimeUnit.MINUTES
            )
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.MINUTES)
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                SYNC_WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                syncRequest
            )
        }
    }
}
