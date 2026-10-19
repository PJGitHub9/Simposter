<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getApiBase } from '@/services/apiBase'

// Overlay Refresh (Quirk #166): per library group, re-check the posters
// Simposter sent with overlays and re-render the ones whose overlay would now
// come out differently (new resolution, rating, list membership, an edited
// overlay config).

type RefreshConfig = {
  enabled?: boolean
  scheduleCron?: string | null
  plexLabel?: string
  lastRunAt?: string | null
  lastRunStats?: Record<string, number> | null
}

type Group = {
  id: string
  name: string
  members: { serverId: string; libraryId: string; libraryName?: string }[]
  overlayRefresh?: RefreshConfig | null
}

type RunItem = {
  key: string
  server_id: string
  rating_key: string
  season_index: number | null
  title: string
  reason?: string
  overlay?: string[]
  status?: string
}

type RunStatus = {
  state?: 'idle' | 'running' | 'done' | 'error'
  mode?: 'check' | 'apply'
  total?: number
  processed?: number
  current?: string
  changed?: number
  updated?: number
  unchanged?: number
  failed?: number
  error?: string | null
  items?: RunItem[]
  finished_at?: string
}

type TrackedItem = {
  key: string
  server: string
  title: string | null
  year: number | null
  season_index: number | null
  preset_id: string | null
  overlay: string[]
  updated_at: string | null
}

type LogEntry = {
  id: number
  title: string | null
  status: string
  detail: string | null
  created_at: string
}

const apiBase = getApiBase()
const route = useRoute()

const isTV = computed(() => route.name === 'tv-overlay-refresh')
const mediaType = computed(() => (isTV.value ? 'tv' : 'movie'))
const libraryId = computed(() => (route.query.library as string) || '')
const serverId = computed(() => (route.query.server as string) || 'plex-1')

const loading = ref(false)
const group = ref<Group | null>(null)
const tracked = ref(0)
const nextRun = ref<string | null>(null)

const enabled = ref(false)
const scheduleCron = ref('0 4 * * *')
const plexLabel = ref('Simposter-Overlay')
const saving = ref(false)
const saveMessage = ref('')

const SCHEDULE_PRESETS: [string, string][] = [
  ['0 4 * * *', 'Daily at 4 AM'],
  ['0 */6 * * *', 'Every 6 hours'],
  ['0 4 * * 0', 'Weekly, Sunday 4 AM'],
]

const hasPlexMember = computed(() => !!group.value?.members.some(m => m.serverId === 'plex-1'))

const status = ref<RunStatus>({ state: 'idle' })
const starting = ref(false)
let pollHandle: ReturnType<typeof setInterval> | null = null
let previousState: RunStatus['state'] | undefined

const showTracked = ref(false)
const trackedItems = ref<TrackedItem[]>([])
const trackedSearch = ref('')
const trackedLimit = ref(100)

const showLog = ref(false)
const logEntries = ref<LogEntry[]>([])

const running = computed(() => status.value.state === 'running')
const progressPct = computed(() => {
  const t = status.value.total || 0
  return t ? Math.round(((status.value.processed || 0) / t) * 100) : 0
})
const resultItems = computed(() => status.value.items || [])
const pendingKeys = computed(() => resultItems.value.filter(i => i.status === 'changed').map(i => i.key))

const filteredTracked = computed(() => {
  const q = trackedSearch.value.trim().toLowerCase()
  const list = q
    ? trackedItems.value.filter(i => (i.title || '').toLowerCase().includes(q) || i.overlay.some(o => o.toLowerCase().includes(q)))
    : trackedItems.value
  return list
})

const formatDate = (iso?: string | null) => {
  if (!iso) return ''
  const d = new Date(iso.includes('T') || iso.includes('Z') ? iso : iso.replace(' ', 'T') + 'Z')
  return isNaN(d.getTime()) ? iso : d.toLocaleString()
}

const itemTitle = (title: string | null, year: number | null, season: number | null) => {
  let t = title || '?'
  if (season !== null && season !== undefined) t += season === 0 ? ' - Specials' : ` - Season ${season}`
  if (year) t += ` (${year})`
  return t
}

const applyConfig = (cfg?: RefreshConfig | null) => {
  enabled.value = !!cfg?.enabled
  scheduleCron.value = cfg?.scheduleCron || '0 4 * * *'
  plexLabel.value = cfg?.plexLabel ?? 'Simposter-Overlay'
}

const fetchGroup = async () => {
  if (!libraryId.value) {
    group.value = null
    return
  }
  loading.value = true
  try {
    const qs = new URLSearchParams({ server_id: serverId.value, library_id: libraryId.value, media_type: mediaType.value })
    const res = await fetch(`${apiBase}/api/overlay-refresh/group?${qs}`)
    const data = res.ok ? await res.json() : {}
    group.value = data.group || null
    tracked.value = data.tracked || 0
    nextRun.value = data.schedule?.next_run_time || null
    if (data.status) status.value = data.status
    applyConfig(group.value?.overlayRefresh)
  } catch {
    group.value = null
  } finally {
    loading.value = false
  }
}

const saveConfig = async () => {
  if (!group.value) return
  saving.value = true
  saveMessage.value = ''
  try {
    const res = await fetch(`${apiBase}/api/overlay-refresh/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        group_id: group.value.id,
        config: { enabled: enabled.value, scheduleCron: scheduleCron.value.trim(), plexLabel: plexLabel.value.trim() },
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      saveMessage.value = `✗ ${data.detail || 'Could not save'}`
      return
    }
    group.value = data.group
    nextRun.value = data.schedule?.next_run_time || null
    saveMessage.value = '✓ Saved'
    setTimeout(() => { saveMessage.value = '' }, 2500)
  } catch {
    saveMessage.value = '✗ Could not save'
  } finally {
    saving.value = false
  }
}

const startRun = async (apply: boolean, keys?: string[], force = false) => {
  if (!group.value || running.value) return
  if (force && !confirm(`Re-render and re-send all ${tracked.value} tracked poster(s), even unchanged ones?`)) return
  starting.value = true
  try {
    const res = await fetch(`${apiBase}/api/overlay-refresh/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_id: group.value.id, apply, keys: keys ?? null, force }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      status.value = { state: 'error', error: data.detail || 'Could not start' }
      return
    }
    status.value = { state: 'running', mode: apply ? 'apply' : 'check', processed: 0, total: 0, items: [] }
    await pollStatus()
  } finally {
    starting.value = false
  }
}

const pollStatus = async () => {
  if (!group.value) return
  try {
    const res = await fetch(`${apiBase}/api/overlay-refresh/status?group_id=${encodeURIComponent(group.value.id)}`)
    if (!res.ok) return
    const data: RunStatus = await res.json()
    const prev = previousState
    status.value = data
    previousState = data.state
    if (prev === 'running' && data.state !== 'running') {
      if (data.mode === 'apply') {
        await fetchGroup()
        if (showTracked.value) await fetchTracked()
        if (showLog.value) await fetchLog()
      }
    }
  } catch {
    // keep last status
  }
}

const fetchTracked = async () => {
  if (!group.value) return
  const res = await fetch(`${apiBase}/api/overlay-refresh/items?group_id=${encodeURIComponent(group.value.id)}`)
  trackedItems.value = res.ok ? (await res.json()).items || [] : []
}

const fetchLog = async () => {
  if (!group.value) return
  const res = await fetch(`${apiBase}/api/overlay-refresh/log?group_id=${encodeURIComponent(group.value.id)}&limit=300`)
  logEntries.value = res.ok ? (await res.json()).entries || [] : []
}

const toggleTracked = async () => {
  showTracked.value = !showTracked.value
  if (showTracked.value) await fetchTracked()
}

const toggleLog = async () => {
  showLog.value = !showLog.value
  if (showLog.value) await fetchLog()
}

watch([libraryId, serverId, mediaType], async () => {
  status.value = { state: 'idle' }
  previousState = undefined
  showTracked.value = false
  showLog.value = false
  await fetchGroup()
})

onMounted(async () => {
  await fetchGroup()
  previousState = status.value.state
  pollHandle = setInterval(() => {
    if (running.value) pollStatus()
  }, 1000)
})

onUnmounted(() => {
  if (pollHandle) clearInterval(pollHandle)
})
</script>

<template>
  <div class="overlay-refresh-view">
    <div class="page-header">
      <h2>🔁 Overlay Refresh</h2>
    </div>

    <div class="section-note">
      Every poster Simposter sends with overlays is remembered here, with the art it was made from. A check rebuilds
      each poster's overlay from the item's current data (resolution, codecs, file name, ratings, lists, and your
      current overlays) and lists the ones that would now look different. Refreshing re-renders those from the
      same art and sends them again. New data comes from library scans and MDBList.
    </div>

    <div v-if="loading && !group" class="state-msg">Loading...</div>

    <div v-else-if="!group" class="state-msg">
      This library isn't in a library group yet. Open Settings → Libraries and save once to create it.
    </div>

    <template v-else>
      <div class="section">
        <div class="section-header-inline">
          <h3>Schedule</h3>
          <label class="enable-toggle">
            <input type="checkbox" v-model="enabled" />
            Refresh on a schedule
          </label>
        </div>

        <div class="config-grid">
          <div class="config-field">
            <label class="field-label">When</label>
            <div class="schedule-row">
              <select class="toolbar-select" :disabled="!enabled" @change="scheduleCron = ($event.target as HTMLSelectElement).value">
                <option value="" disabled :selected="!SCHEDULE_PRESETS.some(p => p[0] === scheduleCron)">Custom</option>
                <option v-for="p in SCHEDULE_PRESETS" :key="p[0]" :value="p[0]" :selected="p[0] === scheduleCron">{{ p[1] }}</option>
              </select>
              <input v-model="scheduleCron" type="text" class="text-input cron-input" :disabled="!enabled" placeholder="0 4 * * *" />
            </div>
            <span class="help-text">Cron format: minute hour day month weekday. Each run only re-sends posters whose overlay changed.</span>
            <span v-if="enabled && nextRun" class="next-run-note">Next run: {{ formatDate(nextRun) }}</span>
          </div>

          <div v-if="hasPlexMember" class="config-field">
            <label class="field-label">Plex label</label>
            <input v-model="plexLabel" type="text" class="text-input" placeholder="Simposter-Overlay" />
            <span class="help-text">
              Added in Plex to items whose poster has an overlay (removed if a refresh leaves none). Leave empty for no
              label. Jellyfin and Emby have no labels; their changes are in the log below.
            </span>
          </div>
        </div>

        <div class="config-actions">
          <button class="btn-primary" :disabled="saving" @click="saveConfig">{{ saving ? 'Saving...' : 'Save' }}</button>
          <span v-if="saveMessage" class="save-msg">{{ saveMessage }}</span>
          <span v-if="group.overlayRefresh?.lastRunAt" class="last-run">
            Last refresh {{ formatDate(group.overlayRefresh.lastRunAt) }}<template v-if="group.overlayRefresh.lastRunStats">
              — {{ group.overlayRefresh.lastRunStats.updated || 0 }} updated, {{ group.overlayRefresh.lastRunStats.failed || 0 }} failed,
              {{ group.overlayRefresh.lastRunStats.checked || 0 }} checked</template>
          </span>
        </div>
      </div>

      <div class="section">
        <div class="section-header-inline">
          <h3>Run now</h3>
          <span class="tracked-count">{{ tracked }} tracked poster{{ tracked === 1 ? '' : 's' }}</span>
        </div>

        <div v-if="tracked === 0" class="state-msg small">
          Nothing tracked yet. Posters are tracked when you send them with an overlay (editor, Batch Edit, webhooks or
          auto-generate), from now on.
        </div>

        <div class="run-actions">
          <button class="btn-secondary" :disabled="running || starting || tracked === 0" @click="startRun(false)">Check for changes</button>
          <button class="btn-primary" :disabled="running || starting || tracked === 0" @click="startRun(true)">Refresh changed posters</button>
          <button class="btn-link" :disabled="running || starting || tracked === 0" @click="startRun(true, undefined, true)">Re-send all</button>
        </div>

        <div v-if="running" class="progress">
          <div class="progress-text">
            {{ status.mode === 'apply' ? 'Refreshing' : 'Checking' }} {{ status.processed || 0 }} / {{ status.total || 0 }}
            <span v-if="status.current" class="progress-current">— {{ status.current }}</span>
          </div>
          <div class="progress-bar"><div class="progress-fill" :style="{ width: progressPct + '%' }"></div></div>
        </div>

        <div v-if="status.state === 'error'" class="error-msg">{{ status.error }}</div>

        <div v-if="!running && (status.state === 'done') && status.mode" class="result-summary">
          <template v-if="status.mode === 'check'">
            {{ status.changed || 0 }} poster(s) would change, {{ status.unchanged || 0 }} unchanged.
            <button v-if="pendingKeys.length" class="btn-primary btn-small" @click="startRun(true, pendingKeys)">
              Refresh these {{ pendingKeys.length }}
            </button>
          </template>
          <template v-else>
            {{ status.updated || 0 }} updated, {{ status.failed || 0 }} failed, {{ status.unchanged || 0 }} unchanged.
          </template>
        </div>

        <table v-if="resultItems.length" class="result-table">
          <thead>
            <tr><th>Item</th><th>What changed</th><th>Overlay now</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="item in resultItems" :key="item.key">
              <td>{{ item.title }}</td>
              <td>{{ item.reason }}</td>
              <td class="overlay-cell">{{ (item.overlay || []).join(', ') || 'none' }}</td>
              <td>
                <span class="status-pill" :class="item.status">{{ item.status === 'changed' ? 'would change' : item.status }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="section">
        <button class="collapse-header" @click="toggleTracked">
          <span>{{ showTracked ? '▾' : '▸' }}</span> Tracked posters
        </button>
        <template v-if="showTracked">
          <input v-model="trackedSearch" type="text" class="text-input search-input" placeholder="Search title or overlay..." />
          <table class="result-table">
            <thead>
              <tr><th>Item</th><th>Server</th><th>Overlay</th><th>Sent</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredTracked.slice(0, trackedLimit)" :key="item.key">
                <td>{{ itemTitle(item.title, item.year, item.season_index) }}</td>
                <td>{{ item.server }}</td>
                <td class="overlay-cell">{{ item.overlay.join(', ') || 'none' }}</td>
                <td class="date-cell">{{ formatDate(item.updated_at) }}</td>
              </tr>
            </tbody>
          </table>
          <button v-if="filteredTracked.length > trackedLimit" class="btn-link" @click="trackedLimit += 100">
            Show more ({{ filteredTracked.length - trackedLimit }} left)
          </button>
          <div v-if="!filteredTracked.length" class="state-msg small">No tracked posters.</div>
        </template>
      </div>

      <div class="section">
        <button class="collapse-header" @click="toggleLog">
          <span>{{ showLog ? '▾' : '▸' }}</span> Refresh log
        </button>
        <template v-if="showLog">
          <table v-if="logEntries.length" class="result-table">
            <thead>
              <tr><th>When</th><th>Item</th><th>Result</th><th>Details</th></tr>
            </thead>
            <tbody>
              <tr v-for="e in logEntries" :key="e.id">
                <td class="date-cell">{{ formatDate(e.created_at) }}</td>
                <td>{{ e.title }}</td>
                <td><span class="status-pill" :class="e.status">{{ e.status }}</span></td>
                <td>{{ e.detail }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="state-msg small">No refreshes yet.</div>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.overlay-refresh-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary, #eef2ff);
}

.section-note {
  font-size: 12px;
  color: var(--muted, #6b7a99);
  line-height: 1.5;
  max-width: 900px;
}

.state-msg {
  padding: 40px 20px;
  text-align: center;
  color: var(--muted, #a8b3cf);
}

.state-msg.small {
  padding: 12px 0;
  font-size: 13px;
  text-align: left;
}

.section {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  border-radius: 10px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-header-inline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.section h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #eef2ff);
}

.enable-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-primary, #c9d1e0);
  cursor: pointer;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}

.config-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 12px;
  color: var(--muted, #a8b3cf);
  font-weight: 600;
}

.schedule-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-select,
.text-input {
  padding: 6px 10px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.12));
  background: var(--surface-soft, rgba(255, 255, 255, 0.05));
  color: var(--text-primary, #c9d1e0);
  outline: none;
}

.toolbar-select option {
  background: var(--surface, #1a1d2e);
  color: var(--text-primary, #c9d1e0);
}

.toolbar-select:disabled,
.text-input:disabled {
  opacity: 0.5;
}

.text-input:focus,
.toolbar-select:focus {
  border-color: rgba(61, 214, 183, 0.5);
}

.cron-input {
  width: 140px;
}

.search-input {
  max-width: 360px;
}

.help-text {
  font-size: 12px;
  color: var(--muted, #6b7a99);
  line-height: 1.4;
}

.next-run-note {
  font-size: 12px;
  color: var(--accent, #3dd6b7);
}

.config-actions,
.run-actions,
.result-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--text-primary, #c9d1e0);
}

.save-msg {
  font-size: 13px;
  color: var(--accent, #3dd6b7);
}

.last-run,
.tracked-count {
  font-size: 12px;
  color: var(--muted, #8b93a7);
}

button {
  font-size: 13px;
  border-radius: 7px;
  padding: 7px 14px;
  cursor: pointer;
  border: 1px solid transparent;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--accent, #3dd6b7);
  color: #0b1020;
  font-weight: 600;
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--border, rgba(255, 255, 255, 0.15));
  color: var(--text-primary, #c9d1e0);
}

.btn-link {
  background: none;
  color: var(--muted, #8b93a7);
  text-decoration: underline;
  padding: 7px 4px;
}

.btn-small {
  padding: 4px 10px;
  font-size: 12px;
}

.progress {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-text {
  font-size: 13px;
  color: var(--text-primary, #c9d1e0);
}

.progress-current {
  color: var(--muted, #8b93a7);
}

.progress-bar {
  height: 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent, #3dd6b7);
  transition: width 0.3s;
}

.error-msg {
  color: #ff8a8a;
  font-size: 13px;
}

.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  color: var(--text-primary, #c9d1e0);
}

.result-table th {
  text-align: left;
  font-weight: 600;
  color: var(--muted, #8b93a7);
  padding: 6px 8px;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.1));
}

.result-table td {
  padding: 6px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  vertical-align: top;
}

.overlay-cell {
  color: var(--muted, #a8b3cf);
}

.date-cell {
  white-space: nowrap;
  color: var(--muted, #8b93a7);
}

.status-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  white-space: nowrap;
  background: rgba(255, 255, 255, 0.08);
}

.status-pill.updated {
  background: rgba(61, 214, 183, 0.18);
  color: #3dd6b7;
}

.status-pill.failed {
  background: rgba(255, 71, 87, 0.18);
  color: #ff8a8a;
}

.status-pill.changed {
  background: rgba(255, 165, 2, 0.18);
  color: #ffb347;
}

.collapse-header {
  background: none;
  border: none;
  padding: 0;
  text-align: left;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #eef2ff);
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
