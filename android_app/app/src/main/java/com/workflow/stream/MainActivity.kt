package com.workflow.stream

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.gson.JsonObject
import com.workflow.stream.data.TaskItem
import com.workflow.stream.network.ApiClient
import com.workflow.stream.network.WebSocketClient
import com.workflow.stream.notifications.NotificationHelper
import com.workflow.stream.sync.TaskSyncWorker
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity(), WebSocketClient.EventListener {

    private lateinit var apiClient: ApiClient
    private var webSocketClient: WebSocketClient? = null
    private lateinit var notificationHelper: NotificationHelper

    private lateinit var adapter: TaskAdapter
    private lateinit var recyclerView: RecyclerView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var focusTitle: TextView
    private lateinit var focusDesc: TextView
    private lateinit var dateHeader: TextView
    private lateinit var statusPill: TextView
    private lateinit var taskInput: EditText
    private lateinit var addBtn: Button
    private lateinit var settingsBtn: ImageButton

    private var currentFilter: String = "ALL" // ALL, OPEN, DONE
    private var rawTaskList: List<TaskItem> = emptyList()

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            Toast.makeText(this, "Alerts enabled for priority tasks", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        notificationHelper = NotificationHelper(this)
        val sharedPrefs = getSharedPreferences("workflow_prefs", Context.MODE_PRIVATE)
        val savedHost = sharedPrefs.getString("server_host", "http://10.0.2.2:8765") ?: "http://10.0.2.2:8765"
        apiClient = ApiClient(savedHost)

        initViews()
        setupRecyclerView()
        checkNotificationPermission()

        TaskSyncWorker.schedulePeriodicSync(this)

        initWebSocket(savedHost)
        loadData()
    }

    private fun initViews() {
        recyclerView = findViewById(R.id.taskRecyclerView)
        swipeRefresh = findViewById(R.id.swipeRefresh)
        focusTitle = findViewById(R.id.focusTitle)
        focusDesc = findViewById(R.id.focusDesc)
        dateHeader = findViewById(R.id.dateHeader)
        statusPill = findViewById(R.id.statusPill)
        taskInput = findViewById(R.id.taskInput)
        addBtn = findViewById(R.id.addBtn)
        settingsBtn = findViewById(R.id.settingsBtn)

        swipeRefresh.setOnRefreshListener { loadData() }

        addBtn.setOnClickListener { handleAddTask() }
        taskInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                handleAddTask()
                true
            } else false
        }

        settingsBtn.setOnClickListener { showServerConfigDialog() }

        findViewById<Button>(R.id.filterAll).setOnClickListener { setFilter("ALL") }
        findViewById<Button>(R.id.filterOpen).setOnClickListener { setFilter("OPEN") }
        findViewById<Button>(R.id.filterDone).setOnClickListener { setFilter("DONE") }
    }

    private fun setupRecyclerView() {
        adapter = TaskAdapter { task, newStatus ->
            // Optimistic toggle
            task.completed = newStatus
            adapter.notifyDataSetChanged()

            // Push to server over WebSocket
            webSocketClient?.toggleTask(task.lineNumber, newStatus)

            // Or REST fallback
            lifecycleScope.launch {
                apiClient.updateTaskStatus(task.lineNumber.toString(), newStatus)
            }
        }
        recyclerView.layoutManager = LinearLayoutManager(this)
        recyclerView.adapter = adapter
    }

    private fun initWebSocket(httpBaseUrl: String) {
        val wsUrl = httpBaseUrl.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        webSocketClient?.stop()
        webSocketClient = WebSocketClient(wsUrl, this)
        webSocketClient?.start()
    }

    private fun loadData() {
        swipeRefresh.isRefreshing = true
        lifecycleScope.launch {
            val tasksResult = apiClient.getTasks()
            val priorityResult = apiClient.getPriorities()
            swipeRefresh.isRefreshing = false

            if (tasksResult.isSuccess) {
                val data = tasksResult.getOrNull()
                rawTaskList = data?.tasks ?: emptyList()
                val summary = data?.summary
                val file = summary?.get("file") as? String ?: "17-Sep.md"
                dateHeader.text = "Obsidian Vault • $file"
                applyFilter()
            }

            if (priorityResult.isSuccess) {
                val pData = priorityResult.getOrNull()
                focusTitle.text = pData?.immediateFocus ?: "No immediate blockers"
                focusDesc.text = pData?.rezoningSuggestion ?: "All topological priorities clear"
            }
        }
    }

    private fun handleAddTask() {
        val text = taskInput.text.toString().trim()
        if (text.isEmpty()) return

        webSocketClient?.addTask(text)
        taskInput.text.clear()

        lifecycleScope.launch {
            apiClient.addTask(text)
            loadData()
        }
    }

    private fun setFilter(filter: String) {
        currentFilter = filter
        applyFilter()
    }

    private fun applyFilter() {
        val filtered = when (currentFilter) {
            "OPEN" -> rawTaskList.filter { !it.completed }
            "DONE" -> rawTaskList.filter { it.completed }
            else -> rawTaskList
        }
        adapter.submitList(filtered)
    }

    private fun checkNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(
                    this,
                    Manifest.permission.POST_NOTIFICATIONS
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                requestPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    private fun showServerConfigDialog() {
        val sharedPrefs = getSharedPreferences("workflow_prefs", Context.MODE_PRIVATE)
        val currentHost = sharedPrefs.getString("server_host", "http://10.0.2.2:8765") ?: "http://10.0.2.2:8765"

        val input = EditText(this).apply {
            setText(currentHost)
            hint = "e.g. http://192.168.1.50:8765"
        }

        AlertDialog.Builder(this)
            .setTitle("Server Connection")
            .setMessage("Set local IP or Tailscale domain of your Mac:")
            .setView(input)
            .setPositiveButton("Save & Reconnect") { _, _ ->
                val newHost = input.text.toString().trim()
                if (newHost.isNotEmpty()) {
                    sharedPrefs.edit().putString("server_host", newHost).apply()
                    apiClient.updateBaseUrl(newHost)
                    initWebSocket(newHost)
                    loadData()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // --- WebSocket Callbacks ---
    override fun onConnected() {
        statusPill.text = "● Live Sync"
        statusPill.setTextColor(ContextCompat.getColor(this, R.color.green_accent))
    }

    override fun onDisconnected() {
        statusPill.text = "○ Offline"
        statusPill.setTextColor(ContextCompat.getColor(this, R.color.red_accent))
    }

    override fun onTaskUpdated(taskJson: JsonObject) {
        loadData()
    }

    override fun onTaskAdded(taskJson: JsonObject) {
        loadData()
    }

    override fun onTaskDeleted(taskJson: JsonObject) {
        loadData()
    }

    override fun onTaskReminder(title: String, message: String) {
        notificationHelper.showTaskReminder(title, message)
    }

    override fun onFocusChanged(focusJson: JsonObject) {
        val title = focusJson.get("title")?.asString ?: ""
        if (title.isNotEmpty()) {
            Toast.makeText(this, "Mac Focus: $title", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        webSocketClient?.stop()
    }
}
