/**
 * Workflow Stream - Background Service Worker (Manifest V3)
 * Real-time WebSocket connection to local macOS Workflow agent (port 8765),
 * active browser focus reporting, and real-time badge updates.
 */

const WS_URL = "ws://localhost:8765/ws";
const HTTP_URL = "http://localhost:8765";

let socket = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_DELAY = 30000;
let reconnectTimer = null;
let lastSentTab = { url: "", title: "" };

/**
 * Initialize connection and alarms
 */
function init() {
  connectWebSocket();
  setupTabListeners();
  setupAlarms();
}

/**
 * Establish WebSocket connection with exponential backoff
 */
function connectWebSocket() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      reconnectAttempts = 0;
      updateConnectionState(true);
      // Immediately send current active tab
      reportCurrentActiveTab();
      // Request initial task state
      sendSocketMessage({ type: "get_tasks" });
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleServerMessage(data);
      } catch (err) {
        console.error("[Workflow Stream] Error parsing WS message:", err);
      }
    };

    socket.onerror = (err) => {
      console.warn("[Workflow Stream] WebSocket error:", err);
    };

    socket.onclose = () => {
      updateConnectionState(false);
      scheduleReconnect();
    };
  } catch (err) {
    console.warn("[Workflow Stream] Connection setup error:", err);
    updateConnectionState(false);
    scheduleReconnect();
  }
}

/**
 * Schedule reconnect with exponential backoff (1s, 2s, 4s, 8s ... up to 30s)
 */
function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts), MAX_RECONNECT_DELAY);
  reconnectAttempts++;
  reconnectTimer = setTimeout(() => {
    connectWebSocket();
  }, delay);
}

/**
 * Send JSON message via WebSocket or fallback to HTTP POST
 */
function sendSocketMessage(payload) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(payload));
  } else {
    // Fallback: send via REST API if WebSocket is offline/connecting
    fetch(`${HTTP_URL}/api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(() => {
      // Server might be starting up; ignore network errors gracefully
    });
  }
}

/**
 * Handle incoming server push messages
 */
function handleServerMessage(data) {
  switch (data.type) {
    case "task_update":
    case "tasks_state": {
      const tasks = data.tasks || [];
      const openCount = tasks.filter((t) => !t.completed).length;
      updateBadge(openCount);

      // Save to local storage for instant popup access
      chrome.storage.local.set({
        workflow_tasks: tasks,
        workflow_date: data.date || "Today",
        workflow_immediate_focus: data.immediate_focus || null,
        workflow_rezoning_nudge: data.rezoning_nudge || null,
        workflow_last_sync: Date.now(),
      });

      // Broadcast to any open popup
      chrome.runtime.sendMessage({ type: "TASKS_UPDATED", data }).catch(() => {});
      break;
    }
    case "badge_update": {
      if (typeof data.count === "number") {
        updateBadge(data.count);
      }
      break;
    }
    case "focus_rezoning": {
      chrome.storage.local.set({
        workflow_immediate_focus: data.immediate_focus,
        workflow_rezoning_nudge: data.rezoning_nudge,
      });
      chrome.runtime.sendMessage({ type: "FOCUS_UPDATED", data }).catch(() => {});
      break;
    }
  }
}

/**
 * Update Chrome Extension action badge
 */
function updateBadge(count) {
  const text = count > 0 ? String(count) : "";
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color: count > 0 ? "#1f6feb" : "#238636" });
  chrome.action.setBadgeTextColor({ color: "#ffffff" }).catch(() => {});
}

/**
 * Save connection status to storage and notify popup
 */
function updateConnectionState(isConnected) {
  chrome.storage.local.set({ workflow_connected: isConnected });
  if (!isConnected) {
    chrome.action.setBadgeBackgroundColor({ color: "#6e7681" });
  }
  chrome.runtime.sendMessage({ type: "CONNECTION_STATE", isConnected }).catch(() => {});
}

/**
 * Report active browser tab title and URL to macOS workflow daemon
 */
function reportCurrentActiveTab() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || tabs.length === 0) return;
    const tab = tabs[0];
    if (!tab.url || tab.url.startsWith("chrome://") || tab.url.startsWith("chrome-extension://")) {
      return;
    }

    if (tab.url === lastSentTab.url && tab.title === lastSentTab.title) {
      return;
    }

    lastSentTab = { url: tab.url, title: tab.title || "" };

    const payload = {
      type: "browser_focus",
      title: tab.title || "",
      url: tab.url,
      timestamp: new Date().toISOString(),
    };

    sendSocketMessage(payload);
  });
}

/**
 * Monitor tab changes in real time
 */
function setupTabListeners() {
  // When active tab switches
  chrome.tabs.onActivated.addListener(() => {
    reportCurrentActiveTab();
  });

  // When tab finishes loading or updates title/URL
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (tab.active && (changeInfo.status === "complete" || changeInfo.title)) {
      reportCurrentActiveTab();
    }
  });

  // Handle messages from popup
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "TOGGLE_TASK") {
      sendSocketMessage({
        type: "toggle_task",
        task_identifier: message.task_identifier,
        completed: message.completed,
        file_path: message.file_path || "",
      });
      sendResponse({ status: "queued" });
    } else if (message.type === "ADD_TASK") {
      sendSocketMessage({
        type: "add_task",
        task_text: message.task_text,
        file_path: message.file_path || "",
        section: message.section || "",
      });
      sendResponse({ status: "queued" });
    } else if (message.type === "FORCE_SYNC") {
      connectWebSocket();
      sendSocketMessage({ type: "get_tasks" });
      sendResponse({ status: "refreshing" });
    }
    return true;
  });
}

/**
 * Periodic healthcheck alarm to maintain Manifest V3 service worker lifecycle
 */
function setupAlarms() {
  chrome.alarms.create("workflow_keepalive", { periodInMinutes: 1 });
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === "workflow_keepalive") {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        connectWebSocket();
      }
      reportCurrentActiveTab();
    }
  });
}

// Start
init();
