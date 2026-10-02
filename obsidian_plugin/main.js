const { Plugin, PluginSettingTab, Setting, Notice, Modal } = require('obsidian');

const DEFAULT_SETTINGS = {
  serverUrl: 'http://localhost:8765',
  wsUrl: 'ws://localhost:8765/ws',
  defaultTaskFolder: 'Task-List',
  autoReconnect: true,
  enableStatusBar: true,
};

class IntellectWorkflowPlugin extends Plugin {
  async onload() {
    await this.loadSettings();

    this.ws = null;
    this.isConnected = false;
    this.currentFocus = { app_name: 'Idle', window_title: '' };
    this.reconnectTimer = null;

    // Status bar item
    if (this.settings.enableStatusBar) {
      this.statusBarItem = this.addStatusBarItem();
      this.updateStatusBar();
      this.statusBarItem.addEventListener('click', () => {
        new IntellectDashboardModal(this.app, this).open();
      });
    }

    // Ribbon icon
    this.addRibbonIcon('zap', 'Intellect & Workflow Control', () => {
      new IntellectDashboardModal(this.app, this).open();
    });

    // Commands
    this.addCommand({
      id: 'open-intellect-dashboard',
      name: 'Open Intellect Dashboard',
      callback: () => {
        new IntellectDashboardModal(this.app, this).open();
      },
    });

    this.addCommand({
      id: 'sync-active-note-tasks',
      name: 'Sync Active File Tasks with Server',
      callback: async () => {
        await this.syncActiveFileTasks();
      },
    });

    this.addCommand({
      id: 'prioritize-current-tasks',
      name: 'AI Prioritize Tasks in Current File',
      callback: async () => {
        await this.prioritizeCurrentFile();
      },
    });

    // Settings tab
    this.addSettingTab(new IntellectSettingTab(this.app, this));

    // Connect WebSocket
    this.initWebSocket();
  }

  onunload() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    if (this.ws) {
      this.ws.close();
    }
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
    if (this.ws) {
      this.ws.close();
    }
    this.initWebSocket();
  }

  initWebSocket() {
    if (!this.settings.wsUrl) return;

    try {
      this.ws = new WebSocket(this.settings.wsUrl);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.updateStatusBar();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleIncomingEvent(data);
        } catch (e) {
          // ignore parsing error
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.updateStatusBar();
        if (this.settings.autoReconnect) {
          this.reconnectTimer = setTimeout(() => this.initWebSocket(), 5000);
        }
      };

      this.ws.onerror = () => {
        this.isConnected = false;
        this.updateStatusBar();
      };
    } catch (e) {
      this.isConnected = false;
      this.updateStatusBar();
    }
  }

  handleIncomingEvent(payload) {
    if (payload.type === 'focus_changed' || payload.event === 'focus_changed') {
      const data = payload.data || payload;
      this.currentFocus = {
        app_name: data.app_name || 'Idle',
        window_title: data.window_title || '',
      };
      this.updateStatusBar();
    } else if (payload.type === 'task_verified' || payload.type === 'notification') {
      const msg = payload.message || payload.title || 'Intellect event received';
      new Notice(`⚡ [Intellect] ${msg}`);
    }
  }

  updateStatusBar() {
    if (!this.statusBarItem) return;
    this.statusBarItem.empty();

    const container = this.statusBarItem.createDiv({ cls: 'intellect-status-bar' });
    const dot = container.createSpan({
      cls: `intellect-status-dot ${this.isConnected ? 'intellect-status-online' : 'intellect-status-offline'}`,
    });

    const text = this.isConnected
      ? `Intellect: ${this.currentFocus.app_name}`
      : 'Intellect: Offline';

    container.createSpan({ text });
  }

  async fetchApi(endpoint, options = {}) {
    const url = `${this.settings.serverUrl.replace(/\/+$/, '')}${endpoint}`;
    try {
      const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      new Notice(`Intellect API Error: ${err.message}`);
      return null;
    }
  }

  async syncActiveFileTasks() {
    const activeFile = this.app.workspace.getActiveFile();
    if (!activeFile) {
      new Notice('No active markdown file to sync.');
      return;
    }
    new Notice(`Syncing ${activeFile.name}...`);
    const res = await this.fetchApi(`/tasks?file_path=${encodeURIComponent(activeFile.path)}`);
    if (res && res.tasks) {
      new Notice(`Synced ${res.tasks.length} tasks from ${activeFile.name}`);
    }
  }

  async prioritizeCurrentFile() {
    const activeFile = this.app.workspace.getActiveFile();
    if (!activeFile) {
      new Notice('Open a task note before running AI prioritization.');
      return;
    }
    new Notice('AI evaluating task graph and priorities...');
    const res = await this.fetchApi('/tasks/prioritize', {
      method: 'POST',
      body: JSON.stringify({ file_path: activeFile.path }),
    });
    if (res && res.status === 'ok') {
      new Notice(`Prioritized ${res.ranked_tasks ? res.ranked_tasks.length : 'all'} tasks.`);
    }
  }
}

class IntellectDashboardModal extends Modal {
  constructor(app, plugin) {
    super(app);
    this.plugin = plugin;
  }

  async onOpen() {
    const { contentEl } = this;
    contentEl.empty();

    contentEl.createEl('h2', { text: '⚡ Autonomous Intellect & Workflow Control', cls: 'intellect-modal-header' });

    // Focus & State Card
    const focusCard = contentEl.createDiv({ cls: 'intellect-card' });
    focusCard.createDiv({ text: 'Active Focus & System State', cls: 'intellect-card-title' });

    const statusRow = focusCard.createDiv({ cls: 'intellect-meta-row' });
    statusRow.createSpan({ text: 'Server Connection:' });
    statusRow.createSpan({
      text: this.plugin.isConnected ? 'Connected (Live WebSocket)' : 'Disconnected (Offline)',
      cls: this.plugin.isConnected ? 'intellect-status-online' : 'intellect-status-offline',
    });

    const appRow = focusCard.createDiv({ cls: 'intellect-meta-row' });
    appRow.createSpan({ text: 'Current Frontmost App:' });
    appRow.createSpan({ text: this.plugin.currentFocus.app_name || 'N/A' });

    const winRow = focusCard.createDiv({ cls: 'intellect-meta-row' });
    winRow.createSpan({ text: 'Window Title:' });
    winRow.createSpan({ text: this.plugin.currentFocus.window_title || 'N/A' });

    // Quick Actions
    const actionCard = contentEl.createDiv({ cls: 'intellect-card' });
    actionCard.createDiv({ text: 'Workflow Operations', cls: 'intellect-card-title' });

    const btnRow = actionCard.createDiv({ cls: 'intellect-btn-row' });
    
    const syncBtn = btnRow.createEl('button', { text: 'Reconcile Active Tasks' });
    syncBtn.addEventListener('click', async () => {
      await this.plugin.syncActiveFileTasks();
      this.close();
    });

    const prioBtn = btnRow.createEl('button', { text: 'AI Prioritize Graph' });
    prioBtn.addEventListener('click', async () => {
      await this.plugin.prioritizeCurrentFile();
      this.close();
    });

    const refreshBtn = btnRow.createEl('button', { text: 'Refresh Focus' });
    refreshBtn.addEventListener('click', async () => {
      const data = await this.plugin.fetchApi('/focus');
      if (data) {
        this.plugin.currentFocus = data;
        this.plugin.updateStatusBar();
        this.onOpen();
      }
    });
  }

  onClose() {
    const { contentEl } = this;
    contentEl.empty();
  }
}

class IntellectSettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl('h2', { text: 'Autonomous Intellect Settings' });

    new Setting(containerEl)
      .setName('REST API Server URL')
      .setDesc('Base HTTP endpoint of your 24/7 daemon (e.g. http://localhost:8765 or tailscale IP)')
      .addText((text) =>
        text
          .setPlaceholder('http://localhost:8765')
          .setValue(this.plugin.settings.serverUrl)
          .onChange(async (val) => {
            this.plugin.settings.serverUrl = val;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName('WebSocket Stream URL')
      .setDesc('Real-time event stream URL for active focus and verdicts (e.g. ws://localhost:8765/ws)')
      .addText((text) =>
        text
          .setPlaceholder('ws://localhost:8765/ws')
          .setValue(this.plugin.settings.wsUrl)
          .onChange(async (val) => {
            this.plugin.settings.wsUrl = val;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName('Task Folder')
      .setDesc('Vault folder containing your daily markdown checklists')
      .addText((text) =>
        text
          .setPlaceholder('Task-List')
          .setValue(this.plugin.settings.defaultTaskFolder)
          .onChange(async (val) => {
            this.plugin.settings.defaultTaskFolder = val;
            await this.plugin.saveSettings();
          })
      );
  }
}

module.exports = IntellectWorkflowPlugin;
