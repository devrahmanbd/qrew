/**
 * Workflow Stream - Popup Controller
 * Instant optimistic UI, real-time WebSocket state, and Obsidian task synchronization.
 */

// Fallback initial task set matching Obsidian Vault / Task-List / 17-Sep.md
const DEFAULT_FALLBACK_TASKS = [
  { line_number: 3, text: "Facebook Account Create", completed: false, section: "## 17-Sep", tags: [] },
  { line_number: 4, text: "Microsoft Video Create", completed: false, section: "## 17-Sep", tags: [] },
  { line_number: 5, text: "Ghost Sender Video Share", completed: false, section: "## 17-Sep", tags: [] },
  { line_number: 6, text: "Account Recovery of Flynn, Shaheen(first)", completed: false, section: "## 17-Sep", tags: [] },
  { line_number: 7, text: "DB to text old geezer", completed: false, section: "## 17-Sep", tags: [] },
  { line_number: 8, text: "Framique", completed: false, section: "## 17-Sep", tags: [] },
];

let state = {
  tasks: [],
  activeFilter: "all",
  currentDate: "17-Sep",
  isConnected: false,
  immediateFocus: "Account Recovery of Flynn, Shaheen(first)",
  rezoningNudge: "Explicit prerequisite '(first)' • Critical blocker",
};

// DOM Elements
const taskListEl = document.getElementById("task-list");
const emptyStateEl = document.getElementById("empty-state");
const statusPillEl = document.getElementById("status-pill");
const statusTextEl = document.getElementById("status-text");
const dateBadgeEl = document.getElementById("date-badge");
const sectionIndicatorEl = document.getElementById("section-indicator");
const quickAddForm = document.getElementById("quick-add-form");
const taskInputEl = document.getElementById("task-input");
const refreshBtnEl = document.getElementById("refresh-btn");
const focusSectionEl = document.getElementById("focus-section");
const focusTitleEl = document.getElementById("focus-task-title");
const focusReasonEl = document.getElementById("focus-task-reason");
const focusCompleteBtn = document.getElementById("focus-complete-btn");

const countAllEl = document.getElementById("count-all");
const countOpenEl = document.getElementById("count-open");
const countCompletedEl = document.getElementById("count-completed");

/**
 * Initialize popup
 */
document.addEventListener("DOMContentLoaded", async () => {
  setupFilterListeners();
  setupFormListener();
  setupRefreshListener();
  setupFocusActionListener();
  listenToBackgroundMessages();

  // Load cached state from storage immediately for 0ms latency
  await loadCachedState();

  // Trigger background sync
  chrome.runtime.sendMessage({ type: "FORCE_SYNC" });
});

/**
 * Load cached state from chrome.storage.local
 */
async function loadCachedState() {
  chrome.storage.local.get(
    [
      "workflow_tasks",
      "workflow_date",
      "workflow_connected",
      "workflow_immediate_focus",
      "workflow_rezoning_nudge",
    ],
    (result) => {
      state.isConnected = Boolean(result.workflow_connected);
      updateConnectionPill(state.isConnected);

      if (result.workflow_date) {
        state.currentDate = result.workflow_date;
        dateBadgeEl.textContent = state.currentDate;
        sectionIndicatorEl.textContent = `## ${state.currentDate}`;
      }

      if (result.workflow_immediate_focus) {
        state.immediateFocus = result.workflow_immediate_focus;
      }
      if (result.workflow_rezoning_nudge) {
        state.rezoningNudge = result.workflow_rezoning_nudge;
      }

      if (Array.isArray(result.workflow_tasks) && result.workflow_tasks.length > 0) {
        state.tasks = result.workflow_tasks;
      } else {
        state.tasks = DEFAULT_FALLBACK_TASKS;
      }

      renderUI();
    }
  );
}

/**
 * Listen for live background worker broadcasts
 */
function listenToBackgroundMessages() {
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "CONNECTION_STATE") {
      state.isConnected = message.isConnected;
      updateConnectionPill(state.isConnected);
    } else if (message.type === "TASKS_UPDATED" && message.data) {
      if (Array.isArray(message.data.tasks)) {
        state.tasks = message.data.tasks;
      }
      if (message.data.date) {
        state.currentDate = message.data.date;
        dateBadgeEl.textContent = state.currentDate;
        sectionIndicatorEl.textContent = `## ${state.currentDate}`;
      }
      if (message.data.immediate_focus) {
        state.immediateFocus = message.data.immediate_focus;
      }
      if (message.data.rezoning_nudge) {
        state.rezoningNudge = message.data.rezoning_nudge;
      }
      renderUI();
    } else if (message.type === "FOCUS_UPDATED" && message.data) {
      if (message.data.immediate_focus) {
        state.immediateFocus = message.data.immediate_focus;
      }
      if (message.data.rezoning_nudge) {
        state.rezoningNudge = message.data.rezoning_nudge;
      }
      renderFocusCard();
    }
  });
}

/**
 * Render complete UI
 */
function renderUI() {
  updateCounts();
  renderFocusCard();
  renderTaskList();
}

/**
 * Update filter counts
 */
function updateCounts() {
  const total = state.tasks.length;
  const completed = state.tasks.filter((t) => t.completed).length;
  const open = total - completed;

  countAllEl.textContent = total;
  countOpenEl.textContent = open;
  countCompletedEl.textContent = completed;
}

/**
 * Render the Top Focus AI recommendation card
 */
function renderFocusCard() {
  const openTasks = state.tasks.filter((t) => !t.completed);

  // If no open tasks, hide focus card
  if (openTasks.length === 0) {
    focusSectionEl.style.display = "none";
    return;
  }

  focusSectionEl.style.display = "block";

  // Match target task
  let targetTask = openTasks.find((t) => t.text === state.immediateFocus);
  if (!targetTask) {
    // Look for (first) prerequisite or pick top open item
    targetTask = openTasks.find((t) => t.text.toLowerCase().includes("(first)")) || openTasks[0];
    state.immediateFocus = targetTask.text;
  }

  focusTitleEl.textContent = targetTask.text;
  if (targetTask.text.toLowerCase().includes("(first)")) {
    focusReasonEl.textContent = "Explicit prerequisite '(first)' • Blocks dependent tasks";
  } else {
    focusReasonEl.textContent = state.rezoningNudge || "Highest topological priority for today";
  }
}

/**
 * Render task list with filter
 */
function renderTaskList() {
  taskListEl.innerHTML = "";

  const filteredTasks = state.tasks.filter((t) => {
    if (state.activeFilter === "open") return !t.completed;
    if (state.activeFilter === "completed") return t.completed;
    return true;
  });

  if (filteredTasks.length === 0) {
    emptyStateEl.style.display = "flex";
    return;
  }

  emptyStateEl.style.display = "none";

  filteredTasks.forEach((task) => {
    const li = document.createElement("li");
    li.className = `task-item ${task.completed ? "completed" : ""}`;
    if (!task.completed && task.text === state.immediateFocus) {
      li.classList.add("is-top-focus");
    }

    const isPrereq = task.text.toLowerCase().includes("(first)");

    li.innerHTML = `
      <label class="custom-checkbox">
        <input type="checkbox" ${task.completed ? "checked" : ""} />
        <span class="checkbox-visual">
          <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
            <path d="M1 4L3.8 6.8L9 1.2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </span>
      </label>
      <div class="task-body">
        <div class="task-label">${escapeHtml(task.text)}</div>
        <div class="task-badges">
          ${isPrereq ? '<span class="badge-prereq">FIRST</span>' : ""}
          ${(task.tags || []).map((tag) => `<span class="badge-tag">${escapeHtml(tag)}</span>`).join("")}
        </div>
      </div>
    `;

    // Click anywhere on the item to toggle
    const checkbox = li.querySelector("input");
    checkbox.addEventListener("change", (e) => {
      e.stopPropagation();
      toggleTask(task);
    });

    li.addEventListener("click", (e) => {
      if (e.target.tagName !== "INPUT") {
        checkbox.checked = !checkbox.checked;
        toggleTask(task);
      }
    });

    taskListEl.appendChild(li);
  });
}

/**
 * Optimistic task toggle
 */
function toggleTask(task) {
  const newCompleted = !task.completed;
  task.completed = newCompleted;

  // Optimistically re-render UI immediately
  renderUI();

  // Save to local cache
  chrome.storage.local.set({ workflow_tasks: state.tasks });

  // Dispatch to background worker / WebSocket
  chrome.runtime.sendMessage({
    type: "TOGGLE_TASK",
    task_identifier: task.text,
    completed: newCompleted,
    file_path: state.currentDate,
  });
}

/**
 * Setup filter pills
 */
function setupFilterListeners() {
  const pills = document.querySelectorAll(".filter-bar .pill");
  pills.forEach((pill) => {
    pill.addEventListener("click", () => {
      pills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.activeFilter = pill.getAttribute("data-filter");
      renderTaskList();
    });
  });
}

/**
 * Setup Quick Add form
 */
function setupFormListener() {
  quickAddForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = taskInputEl.value.trim();
    if (!text) return;

    const newTask = {
      line_number: state.tasks.length + 1,
      text: text,
      completed: false,
      section: `## ${state.currentDate}`,
      tags: [],
    };

    // Optimistically insert
    state.tasks.push(newTask);
    taskInputEl.value = "";
    renderUI();

    // Cache
    chrome.storage.local.set({ workflow_tasks: state.tasks });

    // Send to background / Obsidian
    chrome.runtime.sendMessage({
      type: "ADD_TASK",
      task_text: text,
      file_path: state.currentDate,
      section: `## ${state.currentDate}`,
    });
  });
}

/**
 * Setup Refresh button
 */
function setupRefreshListener() {
  refreshBtnEl.addEventListener("click", () => {
    refreshBtnEl.style.transform = "rotate(360deg)";
    setTimeout(() => {
      refreshBtnEl.style.transform = "none";
    }, 300);

    chrome.runtime.sendMessage({ type: "FORCE_SYNC" });
  });
}

/**
 * Complete Top Focus action button
 */
function setupFocusActionListener() {
  focusCompleteBtn.addEventListener("click", () => {
    const target = state.tasks.find((t) => t.text === state.immediateFocus && !t.completed);
    if (target) {
      toggleTask(target);
    }
  });
}

/**
 * Update connection pill style
 */
function updateConnectionPill(isConnected) {
  if (isConnected) {
    statusPillEl.className = "status-pill status-live";
    statusTextEl.textContent = "Live";
  } else {
    statusPillEl.className = "status-pill status-offline";
    statusTextEl.textContent = "Offline";
  }
}

/**
 * Escape HTML to prevent injection
 */
function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
