package com.workflow.stream.network

import android.os.Handler
import android.os.Looper
import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonObject
import okhttp3.*
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class WebSocketClient(
    private val serverWsUrl: String,
    private val listener: EventListener
) {

    interface EventListener {
        fun onConnected()
        fun onDisconnected()
        fun onTaskUpdated(taskJson: JsonObject)
        fun onTaskAdded(taskJson: JsonObject)
        fun onTaskDeleted(taskJson: JsonObject)
        fun onTaskReminder(title: String, message: String)
        fun onFocusChanged(focusJson: JsonObject)
    }

    private val TAG = "WebSocketClient"
    private val gson = Gson()
    private val client = OkHttpClient.Builder()
        .pingInterval(15, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private val isRunning = AtomicBoolean(false)
    private val handler = Handler(Looper.getMainLooper())
    private var reconnectDelayMs = 1000L

    fun start() {
        isRunning.set(true)
        connect()
    }

    fun stop() {
        isRunning.set(false)
        handler.removeCallbacksAndMessages(null)
        webSocket?.close(1000, "App closed")
        webSocket = null
    }

    private fun connect() {
        if (!isRunning.get()) return

        Log.d(TAG, "Connecting to WebSocket: $serverWsUrl")
        val request = Request.Builder().url(serverWsUrl).build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                Log.d(TAG, "WebSocket Connected successfully")
                reconnectDelayMs = 1000L
                handler.post { listener.onConnected() }
            }

            override fun onMessage(ws: WebSocket, text: String) {
                try {
                    val json = gson.fromJson(text, JsonObject::class.java)
                    val event = json.get("event")?.asString ?: return

                    handler.post {
                        when (event) {
                            "task_updated" -> json.getAsJsonObject("task")?.let { listener.onTaskUpdated(it) }
                            "task_added" -> json.getAsJsonObject("task")?.let { listener.onTaskAdded(it) }
                            "task_deleted" -> json.getAsJsonObject("task")?.let { listener.onTaskDeleted(it) }
                            "task_reminder" -> {
                                val title = json.get("title")?.asString ?: "Task Reminder"
                                val msg = json.get("message")?.asString ?: ""
                                listener.onTaskReminder(title, msg)
                            }
                            "focus_changed" -> json.getAsJsonObject("browser_tab")?.let { listener.onFocusChanged(it) }
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error parsing WebSocket message: ${e.message}")
                }
            }

            override fun onClosing(ws: WebSocket, code: Int, reason: String) {
                ws.close(1000, null)
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket Closed: $reason")
                handler.post { listener.onDisconnected() }
                scheduleReconnect()
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "WebSocket failure: ${t.message}")
                handler.post { listener.onDisconnected() }
                scheduleReconnect()
            }
        })
    }

    private fun scheduleReconnect() {
        if (!isRunning.get()) return
        handler.postDelayed({
            if (isRunning.get()) {
                connect()
                reconnectDelayMs = (reconnectDelayMs * 2).coerceAtMost(30000L)
            }
        }, reconnectDelayMs)
    }

    fun toggleTask(lineNumber: Int, completed: Boolean, filePath: String = "") {
        val payload = JsonObject().apply {
            addProperty("action", "toggle_task")
            addProperty("task_identifier", lineNumber)
            addProperty("completed", completed)
            if (filePath.isNotEmpty()) addProperty("file_path", filePath)
        }
        webSocket?.send(payload.toString())
    }

    fun addTask(text: String, section: String = "", filePath: String = "") {
        val payload = JsonObject().apply {
            addProperty("action", "add_task")
            addProperty("text", text)
            if (section.isNotEmpty()) addProperty("section", section)
            if (filePath.isNotEmpty()) addProperty("file_path", filePath)
        }
        webSocket?.send(payload.toString())
    }
}
