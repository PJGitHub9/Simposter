<script setup lang="ts">
import { computed, onMounted, ref, onUnmounted } from 'vue'
import { getApiBase } from '@/services/apiBase'

type LogLevel = 'all' | 'debug' | 'info' | 'warning' | 'error'

const apiBase = getApiBase()
const loading = ref(false)
const error = ref<string | null>(null)
const text = ref('')
const logLevel = ref<LogLevel>('all')
const searchQuery = ref('')
const autoRefresh = ref(false)
const logSettings = ref({
  level: 'INFO',
  maxSize: 20,
  maxBackups: 7
})
const isCurrentView = computed(() => !selectedDate.value)
let refreshInterval: ReturnType<typeof setInterval> | null = null

type LogFile = {
  name: string
  size: number
  mtime: number
  current: boolean
}

const logFiles = ref<LogFile[]>([])
const selectedDate = ref<string | null>(null) // YYYYMMDD or null for current

const fetchLogFiles = async () => {
  try {
    const res = await fetch(`${apiBase}/api/log-files`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    logFiles.value = data.files || []
    // Ensure selected date is valid
    const hasSelected = selectedDate.value
      ? logFiles.value.some(f => !f.current && f.name.includes(selectedDate.value as string))
      : logFiles.value.some(f => f.current)
    if (!hasSelected) {
      selectedDate.value = null
    }
  } catch (err) {
    console.error('Failed to load log files:', err)
  }
}

const fetchLogs = async (date?: string | null) => {
  loading.value = true
  error.value = null
  try {
    const params = date ? `?date=${date}` : ''
    const res = await fetch(`${apiBase}/api/logs${params}`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    text.value = data.text || ''
    // If current view is empty but API returned lines count, try refetching latest file list
    if (!text.value && (data.lines || 0) === 0) {
      await fetchLogFiles()
    }
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Failed to load logs'
  } finally {
    loading.value = false
  }
}

const parsedLogs = computed(() => {
  if (!text.value) return []

  const lines = text.value.split('\n').filter(line => line.trim())
  return lines.map((line, index) => {
    // Try to parse timestamp, level, and message
    let level: LogLevel = 'info'
    let timestamp = ''
    let message = line

    // Match pattern: YYYY-MM-DD HH:MM:SS [LEVEL] message
    const timestampMatch = line.match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})/)
    if (timestampMatch && timestampMatch[1]) {
      timestamp = timestampMatch[1]
      message = line.substring(timestampMatch[0].length).trim()
    }

    // Match [LEVEL] pattern
    const levelMatch = message.match(/^\[(\w+)\]/)
    if (levelMatch && levelMatch[1]) {
      const detectedLevel = levelMatch[1].toLowerCase()
      if (detectedLevel === 'error' || detectedLevel === 'err') level = 'error'
      else if (detectedLevel === 'warn' || detectedLevel === 'warning') level = 'warning'
      else if (detectedLevel === 'debug') level = 'debug'
      else if (detectedLevel === 'info') level = 'info'

      message = message.substring(levelMatch[0].length).trim()
    } else {
      // Fallback: detect by keywords
      const lowerLine = line.toLowerCase()
      if (lowerLine.includes('error') || lowerLine.includes('exception') || lowerLine.includes('failed')) {
        level = 'error'
      } else if (lowerLine.includes('warn')) {
        level = 'warning'
      } else if (lowerLine.includes('debug')) {
        level = 'debug'
      }
    }

    return { index, line, level, timestamp, message }
  })
})

const filteredLogs = computed(() => {
  let logs = logLevel.value === 'all' ? parsedLogs.value : parsedLogs.value.filter(log => log.level === logLevel.value)

  // Apply search filter
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    logs = logs.filter(log => log.message.toLowerCase().includes(query) || log.line.toLowerCase().includes(query))
  }

  return logs.slice().reverse()
})

const toggleAutoRefresh = () => {
  if (!isCurrentView.value) {
    autoRefresh.value = false
    return
  }
  autoRefresh.value = !autoRefresh.value

  if (autoRefresh.value) {
    refreshInterval = setInterval(() => {
      fetchLogs(selectedDate.value)
    }, 5000)
  } else if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

const fetchLogConfig = async () => {
  try {
    const res = await fetch(`${apiBase}/api/log-config`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    logSettings.value = {
      level: data.level || 'INFO',
      maxSize: data.maxSize || 20,
      maxBackups: data.maxBackups || 7
    }
  } catch (err) {
    console.error('Failed to load log config:', err)
  }
}

const saveLogSettings = async () => {
  try {
    const res = await fetch(`${apiBase}/api/log-config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(logSettings.value)
    })
    if (!res.ok) throw new Error(`API error ${res.status}`)
  } catch (err) {
    console.error('Failed to save log config:', err)
  }
}

onMounted(() => {
  fetchLogFiles().then(() => fetchLogs(selectedDate.value))
  fetchLogConfig()
})
onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})

const selectLog = (file: LogFile) => {
  selectedDate.value = file.current ? null : file.name.match(/(\d{8})/)?.[1] || null
  if (!file.current && refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
    autoRefresh.value = false
  }
  fetchLogs(selectedDate.value)
}

const clearLogs = async () => {
  if (!window.confirm('⚠️ Clear all backend log files?')) return
  try {
    const res = await fetch(`${apiBase}/api/logs/clear`, { method: 'POST' })
    if (!res.ok) throw new Error(`API error ${res.status}`)
    await fetchLogFiles()
    await fetchLogs(selectedDate.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to clear logs'
    setTimeout(() => (error.value = null), 3000)
  }
}
</script>

<template>
  <div class="view">
    <div class="config-panel glass">
      <h3>Log Configuration</h3>
      <p class="config-subtitle">Settings for log file management (does not affect logs displayed below)</p>
      <div class="settings-grid">
        <div class="setting-item">
          <label for="log-level">Log Level</label>
          <select id="log-level" v-model="logSettings.level" class="setting-input">
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </div>
        <div class="setting-item">
          <label for="max-size">Max Size (MB)</label>
          <input id="max-size" v-model.number="logSettings.maxSize" type="number" min="1" max="1000" class="setting-input" />
        </div>
        <div class="setting-item">
          <label for="max-backups">Max Backups</label>
          <input id="max-backups" v-model.number="logSettings.maxBackups" type="number" min="1" max="30" class="setting-input" />
        </div>
      </div>
      <div class="settings-actions">
        <button class="btn-save" @click="saveLogSettings">Save Settings</button>
      </div>
    </div>

    <div class="logs-panel glass">
      <div class="header">
        <div>
          <p class="label">Activity</p>
          <h2>Logs</h2>
        </div>
        <div class="header-controls">
          <div class="filter-group">
            <div class="log-tabs">
              <button
                v-for="file in logFiles"
                :key="file.name"
                :class="['log-tab', { active: file.current ? !selectedDate : selectedDate && file.name.includes(selectedDate) }]"
                @click="selectLog(file)"
              >
                {{ file.current ? 'Today' : file.name.replace(/\\D/g, '') }}
              </button>
            </div>
          </div>
          <div class="filter-group">
            <input
              v-model="searchQuery"
              type="text"
              placeholder="Search logs..."
              class="log-search"
            />
          </div>
          <div class="filter-group">
            <label class="filter-label">Level:</label>
            <select v-model="logLevel" class="log-filter">
              <option value="all">All</option>
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
            </select>
          </div>
          <button :class="['auto-refresh-btn', { active: autoRefresh }]" @click="toggleAutoRefresh">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
            Auto
          </button>
          <button class="ghost" @click="fetchLogs(selectedDate)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
            Refresh
          </button>
          <button class="ghost danger" @click="clearLogs">
            Clear Logs
          </button>
        </div>
      </div>

      <div v-if="error" class="callout error">
        {{ error }}
      </div>
      <div v-else-if="loading" class="callout">Loading logs…</div>
      <div v-else class="log-container">
        <div v-if="!filteredLogs.length" class="empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10 9 9 9 8 9" />
          </svg>
          <p>No log entries yet.</p>
        </div>
        <div v-else class="log-output">
          <div v-for="log in filteredLogs" :key="log.index" :class="['log-line', log.level]">
            <span class="log-level-badge">{{ log.level.toUpperCase() }}</span>
            <span v-if="log.timestamp" class="log-timestamp">{{ log.timestamp }}</span>
            <span class="log-text">{{ log.message }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.view {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-panel {
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
}

.config-panel h3 {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
  color: #eef2ff;
}

.config-subtitle {
  margin: 0 0 16px 0;
  font-size: 12px;
  color: var(--muted);
  opacity: 0.8;
}

.logs-panel {
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 16px;
}

.label {
  text-transform: uppercase;
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 1px;
  margin-bottom: 4px;
}

.header h2 {
  font-size: 20px;
  font-weight: 700;
  color: #eef2ff;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-label {
  font-size: 13px;
  color: var(--muted);
  font-weight: 500;
}

.log-search {
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 13px;
  min-width: 200px;
  transition: all 0.2s;
}

.log-search:focus {
  outline: none;
  border-color: rgba(61, 214, 183, 0.5);
  background: rgba(255, 255, 255, 0.06);
}

.log-search::placeholder {
  color: var(--muted);
  opacity: 0.5;
}

.log-filter {
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.log-filter:focus {
  outline: none;
  border-color: rgba(61, 214, 183, 0.5);
}

.auto-refresh-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  background: rgba(255, 255, 255, 0.03);
  color: #dce6ff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}

.auto-refresh-btn:hover {
  background: rgba(255, 255, 255, 0.06);
}

.auto-refresh-btn.active {
  background: rgba(61, 214, 183, 0.15);
  border-color: rgba(61, 214, 183, 0.4);
  color: #3dd6b7;
}

.ghost {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  background: rgba(255, 255, 255, 0.03);
  color: #dce6ff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}

.ghost:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.1);
}

.callout {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  color: #d8e3ff;
}

.callout.error {
  border-color: rgba(255, 126, 126, 0.4);
  background: rgba(255, 107, 107, 0.05);
}

.log-container {
  margin-top: 8px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: var(--muted);
}

.empty-state svg {
  opacity: 0.3;
}

.empty-state p {
  font-size: 14px;
}

.log-output {
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0;
  max-height: 65vh;
  overflow-y: auto;
  overflow-x: hidden;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.log-output::-webkit-scrollbar {
  width: 8px;
}

.log-output::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
}

.log-output::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}

.log-output::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.15);
}

.log-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.log-tab {
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #dce6ff;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.log-tab:hover {
  background: rgba(255, 255, 255, 0.08);
}

.log-tab.active {
  border-color: rgba(61, 214, 183, 0.5);
  background: rgba(61, 214, 183, 0.12);
  color: #3dd6b7;
}

.ghost.danger {
  color: #ff6b6b;
  border-color: rgba(255, 107, 107, 0.4);
}

.ghost.danger:hover {
  background: rgba(255, 107, 107, 0.1);
}

.log-line {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  transition: background 0.15s;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.02);
}

.log-line:nth-child(even) {
  background: rgba(255, 255, 255, 0.04);
}

.log-line:last-child {
  border-bottom: none;
}

.log-line:hover {
  background: rgba(255, 255, 255, 0.06);
}

.log-level-badge {
  flex-shrink: 0;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  min-width: 50px;
  text-align: center;
}

.log-timestamp {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  opacity: 0.7;
  min-width: 130px;
}

.log-line.debug .log-level-badge {
  background: rgba(139, 92, 246, 0.15);
  color: #a78bfa;
  border: 1px solid rgba(139, 92, 246, 0.3);
}

.log-line.info .log-level-badge {
  background: rgba(91, 141, 238, 0.15);
  color: #5b8dee;
  border: 1px solid rgba(91, 141, 238, 0.3);
}

.log-line.warning .log-level-badge {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
  border: 1px solid rgba(251, 191, 36, 0.3);
}

.log-line.error .log-level-badge {
  background: rgba(255, 107, 107, 0.15);
  color: #ff6b6b;
  border: 1px solid rgba(255, 107, 107, 0.3);
}

.log-text {
  flex: 1;
  font-size: 12px;
  color: #d4dde8;
  line-height: 1.5;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.log-line.error .log-text {
  color: #ffb3b3;
}

.log-line.warning .log-text {
  color: #ffe4a3;
}

.log-line.debug .log-text {
  color: #c4c8d8;
  opacity: 0.9;
}

.settings-panel {
  padding: 16px;
  margin-bottom: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
}

.settings-panel h3 {
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
  color: #eef2ff;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.setting-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.setting-item label {
  font-size: 13px;
  color: var(--muted);
  font-weight: 500;
}

.setting-input {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 13px;
  transition: all 0.2s;
}

.setting-input:focus {
  outline: none;
  border-color: rgba(61, 214, 183, 0.5);
  background: rgba(255, 255, 255, 0.06);
}

.settings-actions {
  display: flex;
  gap: 10px;
}

.btn-save {
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid rgba(61, 214, 183, 0.4);
  background: rgba(61, 214, 183, 0.1);
  color: #3dd6b7;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-save:hover {
  background: rgba(61, 214, 183, 0.2);
  border-color: rgba(61, 214, 183, 0.6);
}

.btn-cancel {
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
  color: #dce6ff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-cancel:hover {
  background: rgba(255, 255, 255, 0.06);
}
</style>
