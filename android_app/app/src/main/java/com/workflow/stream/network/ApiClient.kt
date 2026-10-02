package com.workflow.stream.network

import com.google.gson.Gson
import com.workflow.stream.data.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

class ApiClient(private var baseUrl: String = "http://10.0.2.2:8765") {

    private val gson = Gson()
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    fun updateBaseUrl(newUrl: String) {
        baseUrl = newUrl.trimEnd('/')
    }

    fun getBaseUrl(): String = baseUrl

    suspend fun getTasks(filePath: String = ""): Result<TasksResponse> = withContext(Dispatchers.IO) {
        try {
            val url = if (filePath.isNotEmpty()) "$baseUrl/api/tasks?file_path=$filePath" else "$baseUrl/api/tasks"
            val request = Request.Builder().url(url).get().build()
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    return@withContext Result.failure(IOException("HTTP error: ${response.code}"))
                }
                val body = response.body?.string() ?: "{}"
                val result = gson.fromJson(body, TasksResponse::class.java)
                Result.success(result)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getPriorities(filePath: String = ""): Result<PrioritizeResponse> = withContext(Dispatchers.IO) {
        try {
            val url = if (filePath.isNotEmpty()) "$baseUrl/api/tasks/prioritize?file_path=$filePath" else "$baseUrl/api/tasks/prioritize"
            val request = Request.Builder().url(url).get().build()
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    return@withContext Result.failure(IOException("HTTP error: ${response.code}"))
                }
                val body = response.body?.string() ?: "{}"
                val result = gson.fromJson(body, PrioritizeResponse::class.java)
                Result.success(result)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun updateTaskStatus(taskIdentifier: String, completed: Boolean, filePath: String = ""): Result<TaskItem> = withContext(Dispatchers.IO) {
        try {
            val payload = TaskUpdatePayload(completed = completed, file_path = filePath.ifEmpty { null })
            val json = gson.toJson(payload)
            val requestBody = json.toRequestBody("application/json".toMediaType())
            val request = Request.Builder()
                .url("$baseUrl/api/tasks/$taskIdentifier")
                .patch(requestBody)
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    return@withContext Result.failure(IOException("HTTP error: ${response.code}"))
                }
                val body = response.body?.string() ?: "{}"
                val result = gson.fromJson(body, TaskItem::class.java)
                Result.success(result)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun addTask(text: String, section: String = "", filePath: String = ""): Result<TaskItem> = withContext(Dispatchers.IO) {
        try {
            val payload = TaskCreatePayload(
                text = text,
                section = section.ifEmpty { null },
                file_path = filePath.ifEmpty { null }
            )
            val json = gson.toJson(payload)
            val requestBody = json.toRequestBody("application/json".toMediaType())
            val request = Request.Builder()
                .url("$baseUrl/api/tasks")
                .post(requestBody)
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    return@withContext Result.failure(IOException("HTTP error: ${response.code}"))
                }
                val body = response.body?.string() ?: "{}"
                val result = gson.fromJson(body, TaskItem::class.java)
                Result.success(result)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
