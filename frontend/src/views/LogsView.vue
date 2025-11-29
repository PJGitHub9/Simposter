<script setup lang="ts">
import { computed, onMounted, ref, onUnmounted } from 'vue'

type LogLevel = 'all' | 'debug' | 'info' | 'warning' | 'error'

const apiBase = import.meta.env.VITE_API_URL || window.location.origin
const loading = ref(false)
const error = ref<string | null>(null)
const text = ref('')
const logLevel = ref<LogLevel>('all')
const autoRefresh = ref(false)
let refreshInterval: ReturnType<typeof setInterval> | null = null

const fetchLogs = async () => {
  loading.value = true
  error.value = null
  try {
    const res = await fetch(`${apiBase}/api/logs`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    text.value = data.text || ''
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
    // Try to parse log level from common patterns
    let level: LogLevel = 'info'
    const lowerLine = line.toLowerCase()

    if (lowerLine.includes('error') || lowerLine.includes('exception') || lowerLine.includes('failed')) {
      level = 'error'
    } else if (lowerLine.includes('warn') || lowerLine.includes('warning')) {
      level = 'warning'
    } else if (lowerLine.includes('debug')) {
      level = 'debug'
    }

    return { index, line, level }
  })
})

const filteredLogs = computed(() => {
  const logs = logLevel.value === 'all' ? parsedLogs.value : parsedLogs.value.filter(log => log.level === logLevel.value)
  return logs.slice().reverse()
})

const toggleAutoRefresh = () => {
  autoRefresh.value = !autoRefresh.value

  if (autoRefresh.value) {
    refreshInterval = setInterval(() => {
      fetchLogs()
    }, 5000)
  } else if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

onMounted(fetchLogs)
onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<template>
  <div class="view glass">
    <div class="header">
      <div>
        <p class="label">Activity</p>
        <h2>Render Logs</h2>
      </div>
      <div class="header-controls">
        <div class="filter-group">
          <label class="filter-label">Filter:</label>
          <select v-model="logLevel" class="log-filter">
            <option value="all">All Logs</option>
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
        <button class="ghost" @click="fetchLogs">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
          Refresh
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
          <span class="log-text">{{ log.line }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.view {
  padding: 16px;
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
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0;
  max-height: 65vh;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.log-line {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  transition: background 0.15s;
}

.log-line:last-child {
  border-bottom: none;
}

.log-line:hover {
  background: rgba(255, 255, 255, 0.03);
}

.log-level-badge {
  flex-shrink: 0;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
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
  font-size: 13px;
  color: #e6edff;
  line-height: 1.6;
  word-break: break-all;
}

.log-line.error .log-text {
  color: #ffb3b3;
}

.log-line.warning .log-text {
  color: #ffe4a3;
}
</style>
