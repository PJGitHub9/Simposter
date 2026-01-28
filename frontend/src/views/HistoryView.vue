<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore } from '@/stores/settings'

interface HistoryRecord {
  id: number
  rating_key: string
  library_id: string | null
  title: string | null
  year: number | null
  template_id: string | null
  preset_id: string | null
  action: string
  save_path: string | null
  source: string | null
  poster_fallback_used: boolean
  poster_fallback_template: string | null
  poster_fallback_preset: string | null
  logo_fallback_used: boolean
  logo_fallback_template: string | null
  logo_fallback_preset: string | null
  created_at: string
}

const apiBase = getApiBase()
const settings = useSettingsStore()
const records = ref<HistoryRecord[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

// Filters
const selectedLibrary = ref<string>('all')
const selectedTemplate = ref<string>('all')
const selectedAction = ref<string>('all')
const selectedSource = ref<string>('all')

// Map library IDs to display names
const getLibraryName = (libraryId: string | null): string => {
  if (!libraryId) return '—'

  // Check movie libraries
  const movieLib = settings.plex.value.libraryMappings?.find(m => m.id === libraryId)
  if (movieLib) {
    return movieLib.displayName || movieLib.title || libraryId
  }

  // Check TV libraries
  const tvLib = settings.plex.value.tvShowLibraryMappings?.find(m => m.id === libraryId)
  if (tvLib) {
    return tvLib.displayName || tvLib.title || libraryId
  }

  return libraryId
}

const libraries = computed(() => {
  const libs = new Set<string>()
  records.value.forEach(r => {
    if (r.library_id) libs.add(r.library_id)
  })
  return Array.from(libs).sort()
})

const templates = computed(() => {
  const tmpls = new Set<string>()
  records.value.forEach(r => {
    if (r.template_id) tmpls.add(r.template_id)
  })
  return Array.from(tmpls).sort()
})

const filteredRecords = computed(() => {
  let filtered = records.value

  if (selectedLibrary.value !== 'all') {
    filtered = filtered.filter(r => r.library_id === selectedLibrary.value)
  }

  if (selectedTemplate.value !== 'all') {
    filtered = filtered.filter(r => r.template_id === selectedTemplate.value)
  }

  if (selectedAction.value !== 'all') {
    filtered = filtered.filter(r => r.action === selectedAction.value)
  }

  if (selectedSource.value !== 'all') {
    filtered = filtered.filter(r => r.source === selectedSource.value)
  }

  return filtered
})

const fetchHistory = async () => {
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams()
    if (selectedLibrary.value !== 'all') {
      params.append('library_id', selectedLibrary.value)
    }
    if (selectedTemplate.value !== 'all') {
      params.append('template_id', selectedTemplate.value)
    }
    if (selectedAction.value !== 'all') {
      params.append('action', selectedAction.value)
    }
    params.append('limit', '500')

    const url = `${apiBase}/api/poster-history?${params.toString()}`
    const res = await fetch(url)

    if (!res.ok) {
      throw new Error(`Failed to fetch history: ${res.status}`)
    }

    const data = await res.json()
    records.value = data.records || []
  } catch (e: any) {
    error.value = e.message || 'Failed to load history'
    console.error('[HISTORY] Error fetching history:', e)
  } finally {
    loading.value = false
  }
}

const formatDate = computed(() => (timestamp: string) => {
  try {
    // Backend stores timestamps in UTC without timezone suffix
    // Append 'Z' to treat as UTC, or convert "YYYY-MM-DD HH:MM:SS" to ISO format
    let isoTimestamp = timestamp
    if (!timestamp.includes('T') && !timestamp.endsWith('Z')) {
      // Convert "2026-01-12 14:13:20" to "2026-01-12T14:13:20Z"
      isoTimestamp = timestamp.replace(' ', 'T') + 'Z'
    }

    const date = new Date(isoTimestamp)
    const timezone = settings.timezone.value || 'UTC'
    return date.toLocaleString('en-US', {
      timeZone: timezone,
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    })
  } catch {
    return timestamp
  }
})

const getActionLabel = (action: string) => {
  switch (action) {
    case 'sent_to_plex':
      return 'Sent to Plex'
    case 'saved_local':
      return 'Saved Locally'
    default:
      return action
  }
}

const getActionClass = (action: string) => {
  switch (action) {
    case 'sent_to_plex':
      return 'action-plex'
    case 'saved_local':
      return 'action-local'
    default:
      return ''
  }
}

const getSourceLabel = (source: string | null) => {
  switch (source) {
    case 'auto':
      return 'Auto'
    case 'batch':
      return 'Batch'
    case 'webhook':
      return 'Webhook'
    case 'manual':
      return 'Manual'
    default:
      return 'Manual'
  }
}

const getSourceClass = (source: string | null) => {
  switch (source) {
    case 'auto':
      return 'source-auto'
    case 'batch':
      return 'source-batch'
    case 'webhook':
      return 'source-webhook'
    case 'manual':
      return 'source-manual'
    default:
      return 'source-manual'
  }
}

const getFallbackInfo = (record: HistoryRecord): string | null => {
  const parts: string[] = []

  if (record.poster_fallback_used && record.poster_fallback_template) {
    const preset = record.poster_fallback_preset ? `/${record.poster_fallback_preset}` : ''
    parts.push(`Poster: ${record.poster_fallback_template}${preset}`)
  }

  if (record.logo_fallback_used && record.logo_fallback_template) {
    const preset = record.logo_fallback_preset ? `/${record.logo_fallback_preset}` : ''
    parts.push(`Logo: ${record.logo_fallback_template}${preset}`)
  }

  return parts.length > 0 ? parts.join(', ') : null
}

const hasFallback = (record: HistoryRecord): boolean => {
  return record.poster_fallback_used || record.logo_fallback_used
}

const clearFilters = () => {
  selectedLibrary.value = 'all'
  selectedTemplate.value = 'all'
  selectedAction.value = 'all'
  selectedSource.value = 'all'
}

onMounted(async () => {
  // Ensure settings are loaded before fetching history (for timezone)
  if (!settings.loaded.value) {
    await settings.load()
  }
  fetchHistory()
})
</script>

<template>
  <div class="history-view">
    <div class="header">
      <h1>Poster Generation History</h1>
      <p class="subtitle">View all poster generations (manual and automatic)</p>
    </div>

    <div class="filters">
      <div class="filter-group">
        <label>
          <span>Library</span>
          <select v-model="selectedLibrary" @change="fetchHistory">
            <option value="all">All Libraries</option>
            <option v-for="lib in libraries" :key="lib" :value="lib">
              {{ getLibraryName(lib) }}
            </option>
          </select>
        </label>

        <label>
          <span>Template</span>
          <select v-model="selectedTemplate" @change="fetchHistory">
            <option value="all">All Templates</option>
            <option v-for="tmpl in templates" :key="tmpl" :value="tmpl">
              {{ tmpl }}
            </option>
          </select>
        </label>

        <label>
          <span>Action</span>
          <select v-model="selectedAction" @change="fetchHistory">
            <option value="all">All Actions</option>
            <option value="sent_to_plex">Sent to Plex</option>
            <option value="saved_local">Saved Locally</option>
          </select>
        </label>

        <label>
          <span>Source</span>
          <select v-model="selectedSource" @change="fetchHistory">
            <option value="all">All Sources</option>
            <option value="manual">Manual</option>
            <option value="batch">Batch</option>
            <option value="webhook">Webhook</option>
            <option value="auto">Auto</option>
          </select>
        </label>

        <button @click="clearFilters" class="btn-clear">
          Clear Filters
        </button>

        <button @click="fetchHistory" class="btn-refresh" :disabled="loading">
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="error-message">
      {{ error }}
    </div>

    <div v-if="loading && records.length === 0" class="loading">
      Loading history...
    </div>

    <div v-else-if="filteredRecords.length === 0" class="empty-state">
      <p>No poster generation history found.</p>
      <p class="hint">Start generating posters to see them here!</p>
    </div>

    <div v-else class="history-table-container">
      <div class="results-count">
        Showing {{ filteredRecords.length }} record{{ filteredRecords.length !== 1 ? 's' : '' }}
      </div>

      <table class="history-table">
        <thead>
          <tr>
            <th>Date & Time</th>
            <th>Title</th>
            <th>Year</th>
            <th>Library</th>
            <th>Template</th>
            <th>Preset</th>
            <th>Source</th>
            <th>Action</th>
            <th>Fallback</th>
            <th>Path</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in filteredRecords" :key="record.id">
            <td class="date-cell">
              {{ formatDate(record.created_at) }}
            </td>
            <td class="title-cell">
              {{ record.title || 'Unknown' }}
            </td>
            <td class="year-cell">
              {{ record.year || '—' }}
            </td>
            <td class="library-cell">
              {{ getLibraryName(record.library_id) }}
            </td>
            <td class="template-cell">
              {{ record.template_id || '—' }}
            </td>
            <td class="preset-cell">
              {{ record.preset_id || '—' }}
            </td>
            <td class="source-cell">
              <span :class="['source-badge', getSourceClass(record.source)]">
                {{ getSourceLabel(record.source) }}
              </span>
            </td>
            <td class="action-cell">
              <span :class="['action-badge', getActionClass(record.action)]">
                {{ getActionLabel(record.action) }}
              </span>
            </td>
            <td class="fallback-cell">
              <span v-if="hasFallback(record)" class="fallback-badge" :title="getFallbackInfo(record) || ''">
                {{ getFallbackInfo(record) }}
              </span>
              <span v-else class="no-fallback">—</span>
            </td>
            <td class="path-cell">
              <span v-if="record.save_path" :title="record.save_path" class="path-text">
                {{ record.save_path }}
              </span>
              <span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.history-view {
  padding: 24px;
  max-width: 1600px;
  margin: 0 auto;
}

.header {
  margin-bottom: 24px;
}

.header h1 {
  margin: 0 0 8px 0;
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
}

.subtitle {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.filters {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 24px;
}

.filter-group {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.filter-group label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 180px;
}

.filter-group label span {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.filter-group select {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
}

.filter-group select:hover {
  background: rgba(255, 255, 255, 0.08);
}

.btn-clear,
.btn-refresh {
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  height: 36px;
  margin-top: auto;
}

.btn-clear:hover,
.btn-refresh:hover {
  background: rgba(255, 255, 255, 0.1);
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-message {
  padding: 16px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: #ef4444;
  margin-bottom: 24px;
}

.loading {
  text-align: center;
  padding: 48px;
  color: var(--text-secondary);
  font-size: 16px;
}

.empty-state {
  text-align: center;
  padding: 64px 24px;
  color: var(--text-secondary);
}

.empty-state p {
  margin: 0 0 8px 0;
  font-size: 16px;
}

.empty-state .hint {
  font-size: 14px;
  color: var(--text-tertiary);
}

.results-count {
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--text-secondary);
}

.history-table-container {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.history-table {
  width: 100%;
  border-collapse: collapse;
}

.history-table thead {
  background: rgba(255, 255, 255, 0.05);
}

.history-table th {
  text-align: left;
  padding: 12px 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border);
}

.history-table td {
  padding: 12px 16px;
  font-size: 14px;
  color: var(--text-primary);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.history-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.03);
}

.history-table tbody tr:last-child td {
  border-bottom: none;
}

.date-cell {
  white-space: nowrap;
  font-size: 13px;
  color: var(--text-secondary);
}

.title-cell {
  font-weight: 500;
  max-width: 300px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.year-cell,
.library-cell,
.template-cell,
.preset-cell {
  font-size: 13px;
  color: var(--text-secondary);
}

.source-cell,
.action-cell {
  white-space: nowrap;
}

.source-badge,
.action-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.source-auto {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.source-batch {
  background: rgba(168, 85, 247, 0.15);
  color: #a855f7;
}

.source-webhook {
  background: rgba(14, 165, 233, 0.15);
  color: #0ea5e9;
}

.source-manual {
  background: rgba(148, 163, 184, 0.15);
  color: #94a3b8;
}

.action-plex {
  background: rgba(229, 160, 13, 0.15);
  color: #e5a00d;
}

.action-local {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.fallback-cell {
  max-width: 200px;
  font-size: 12px;
}

.fallback-badge {
  display: inline-block;
  padding: 4px 8px;
  background: rgba(251, 146, 60, 0.15);
  color: #fb923c;
  border-radius: 6px;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
  cursor: help;
}

.no-fallback {
  color: var(--text-tertiary);
}

.path-cell {
  max-width: 250px;
}

.path-text {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: monospace;
}
</style>
