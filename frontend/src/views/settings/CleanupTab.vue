<script setup lang="ts">
import { ref, computed, reactive, watch, onBeforeUnmount } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore } from '@/stores/settings'
import { mediaServerLabel } from '@/services/mediaServerLabel'

type ScanCategory = {
  id: string
  label: string
  description: string
  kind: 'files' | 'rows'
  count: number
  bytes: number
}

type ScanResult = {
  scanned_at: number
  history_days: number
  categories: ScanCategory[]
  total_bytes: number
  total_bytes_human: string
  stale_cache_warning: string | null
}

type TrashBatch = {
  batch_id: string
  created_at: number
  categories: string[]
  bytes: number
  bytes_human: string
}

// Same 8 category ids backend/api/cleanup.py's scan reports -- kept as a small
// static catalog here since the schedule checklist needs to be selectable even
// before the user has ever run a manual scan (which is the only other place
// these labels/descriptions exist, sourced live from the backend).
const CATEGORY_CATALOG = [
  { id: 'poster_cache', label: 'Orphaned poster cache' },
  { id: 'logo_cache', label: 'Orphaned logo cache' },
  { id: 'backdrop_cache', label: 'Orphaned backdrop cache' },
  { id: 'square_art_cache', label: 'Orphaned square art cache' },
  { id: 'overlay_effect_cache', label: 'Orphaned overlay effect cache' },
  { id: 'uploaded_files', label: 'Unused uploaded images' },
  { id: 'overlay_assets', label: 'Unused overlay badge assets' },
  { id: 'poster_history', label: 'Old History entries' },
]

const props = defineProps<{
  scheduleEnabled: boolean
  scheduleCronExpression: string
  scheduleCategories: string[]
  scheduleHistoryDays: number
  unsavedChanges: boolean
}>()

const emit = defineEmits<{
  'update:scheduleEnabled': [value: boolean]
  'update:scheduleCronExpression': [value: string]
  'update:scheduleCategories': [value: string[]]
  'update:scheduleHistoryDays': [value: number]
  save: []
}>()

const localScheduleEnabled = computed({
  get: () => props.scheduleEnabled,
  set: (val) => emit('update:scheduleEnabled', val)
})
const localScheduleCronExpression = computed({
  get: () => props.scheduleCronExpression,
  set: (val) => emit('update:scheduleCronExpression', val)
})
const localScheduleHistoryDays = computed({
  get: () => props.scheduleHistoryDays,
  set: (val) => emit('update:scheduleHistoryDays', val)
})

function isScheduleCategorySelected(id: string): boolean {
  return props.scheduleCategories.includes(id)
}

function toggleScheduleCategory(id: string) {
  const next = new Set(props.scheduleCategories)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  emit('update:scheduleCategories', Array.from(next))
}

function formatNextRun(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

const apiBase = getApiBase()

function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`
  const units = ['KB', 'MB', 'GB']
  let size = n / 1024
  for (const unit of units) {
    if (size < 1024 || unit === 'GB') return `${size.toFixed(1)} ${unit}`
    size /= 1024
  }
  return `${size.toFixed(1)} GB`
}

// --- Scan / Clean ------------------------------------------------------------

const historyDays = ref(180)
const scanning = ref(false)
const scanResult = ref<ScanResult | null>(null)
const scanError = ref<string | null>(null)
const selectedCategories = ref<Set<string>>(new Set())
const cleaning = ref(false)
const cleanMessage = ref<string | null>(null)
const cleanError = ref<string | null>(null)

const selectedTotalBytes = computed(() => {
  if (!scanResult.value) return 0
  return scanResult.value.categories
    .filter((c) => selectedCategories.value.has(c.id))
    .reduce((sum, c) => sum + c.bytes, 0)
})

function toggleCategory(id: string) {
  const next = new Set(selectedCategories.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedCategories.value = next
}

function selectAll() {
  if (!scanResult.value) return
  selectedCategories.value = new Set(scanResult.value.categories.filter((c) => c.count > 0).map((c) => c.id))
}

function selectNone() {
  selectedCategories.value = new Set()
}

async function runScan() {
  scanning.value = true
  scanError.value = null
  cleanMessage.value = null
  try {
    const res = await fetch(`${apiBase}/api/cleanup/scan?history_days=${historyDays.value}`)
    if (!res.ok) throw new Error(await res.text())
    scanResult.value = await res.json()
    selectedCategories.value = new Set()
  } catch (e: any) {
    scanError.value = e.message || 'Failed to scan for cleanup candidates.'
  } finally {
    scanning.value = false
  }
}

async function runClean() {
  if (selectedCategories.value.size === 0) return
  if (!confirm(`Move ${selectedCategories.value.size} selected categories to the cleanup trash? Nothing is permanently deleted -- you can restore from the Trash section below.`)) return
  cleaning.value = true
  cleanError.value = null
  cleanMessage.value = null
  try {
    const res = await fetch(`${apiBase}/api/cleanup/clean`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ categories: Array.from(selectedCategories.value), history_days: historyDays.value }),
    })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    cleanMessage.value = `Moved ${data.moved_files} file(s) and removed ${data.deleted_rows} row(s) to the cleanup trash.`
    scanResult.value = null
    selectedCategories.value = new Set()
    await loadTrash()
  } catch (e: any) {
    cleanError.value = e.message || 'Failed to run cleanup.'
  } finally {
    cleaning.value = false
  }
}

// --- Trash ---------------------------------------------------------------

const trashBatches = ref<TrashBatch[]>([])
const loadingTrash = ref(false)
const trashActionBusy = ref<Set<string>>(new Set())

async function loadTrash() {
  loadingTrash.value = true
  try {
    const res = await fetch(`${apiBase}/api/cleanup/trash`)
    if (res.ok) {
      const data = await res.json()
      trashBatches.value = data.batches || []
    }
  } catch {
    /* non-critical */
  } finally {
    loadingTrash.value = false
  }
}

async function restoreBatch(batchId: string) {
  if (trashActionBusy.value.has(batchId)) return
  trashActionBusy.value = new Set(trashActionBusy.value).add(batchId)
  try {
    const res = await fetch(`${apiBase}/api/cleanup/trash/restore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ batch_id: batchId }),
    })
    if (res.ok) await loadTrash()
  } catch {
    /* ignore */
  } finally {
    const next = new Set(trashActionBusy.value)
    next.delete(batchId)
    trashActionBusy.value = next
  }
}

async function emptyBatch(batchId: string) {
  if (trashActionBusy.value.has(batchId)) return
  if (!confirm('Permanently delete this trash batch? This cannot be undone.')) return
  trashActionBusy.value = new Set(trashActionBusy.value).add(batchId)
  try {
    const res = await fetch(`${apiBase}/api/cleanup/trash/empty`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ batch_id: batchId }),
    })
    if (res.ok) await loadTrash()
  } catch {
    /* ignore */
  } finally {
    const next = new Set(trashActionBusy.value)
    next.delete(batchId)
    trashActionBusy.value = next
  }
}

async function emptyAllTrash() {
  if (!confirm('Permanently delete everything in the cleanup trash? This cannot be undone.')) return
  try {
    const res = await fetch(`${apiBase}/api/cleanup/trash/empty-all`, { method: 'POST' })
    if (res.ok) await loadTrash()
  } catch {
    /* ignore */
  }
}

loadTrash()

// --- Scheduled cleanup status ------------------------------------------------

const scheduleNextRun = ref<string | null>(null)

async function loadScheduleStatus() {
  try {
    const res = await fetch(`${apiBase}/api/cleanup/schedule`)
    if (res.ok) {
      const data = await res.json()
      scheduleNextRun.value = data.next_run_time || null
    }
  } catch {
    /* non-critical */
  }
}

loadScheduleStatus()

// --- Media server maintenance ----------------------------------------------
// One subsection per configured server, titled with its own name: Plex servers
// get Plex's three maintenance operations, Jellyfin/Emby servers get their
// built-in cleanup tasks (whichever of the supported ones that server reports).

type PlexActionState = 'idle' | 'running' | 'done' | 'error'
type MaintServer = { id: string; type: 'plex' | 'jellyfin' | 'emby'; label: string }
type MaintTask = {
  key: string
  name: string
  description: string
  state: string
  progress?: number | null
  last_run_end?: string | null
  last_run_status?: string | null
}

const settingsStore = useSettingsStore()

const maintenanceServers = computed((): MaintServer[] => {
  const servers = settingsStore.mediaServers.value
  const out: MaintServer[] = []
  const plex = settingsStore.plex.value
  if (plex.url && plex.token) out.push({ id: 'plex-1', type: 'plex', label: mediaServerLabel('plex-1', servers) })
  for (const type of ['plex', 'jellyfin', 'emby'] as const) {
    for (const s of servers) {
      if (s.type !== type || s.id === 'plex-1' || s.enabled === false || !s.url) continue
      out.push({ id: s.id, type, label: mediaServerLabel(s.id, servers) })
    }
  }
  return out
})

// Plex actions -- state keyed "serverId:action" (a string key, not a ref
// passed from the template, which Vue would hand over already unwrapped).
const plexActionState = reactive<Record<string, PlexActionState>>({})
const PLEX_ACTIONS = [
  { key: 'empty-trash', label: 'Empty Trash', doneLabel: 'Done', confirm: 'Empty trash for every library section on {name}?',
    title: 'Empty Trash', text: "Empties the trash for every library section (items you've removed from Plex itself)." },
  { key: 'clean-bundles', label: 'Clean Bundles', doneLabel: 'Started', confirm: "Start Clean Bundles on {name}?",
    title: 'Clean Bundles', text: 'Removes unused metadata bundles Plex has left behind for items no longer in any library.' },
  { key: 'optimize-db', label: 'Optimize Database', doneLabel: 'Started', confirm: "Start Optimize Database on {name}?",
    title: 'Optimize Database', text: "Cleans up Plex's own database from unused or fragmented data." },
]

function plexState(serverId: string, action: string): PlexActionState {
  return plexActionState[`${serverId}:${action}`] || 'idle'
}

async function runPlexAction(server: MaintServer, action: (typeof PLEX_ACTIONS)[number]) {
  if (!confirm(action.confirm.replace('{name}', server.label))) return
  const key = `${server.id}:${action.key}`
  plexActionState[key] = 'running'
  try {
    const res = await fetch(`${apiBase}/api/cleanup/plex/${action.key}?server_id=${encodeURIComponent(server.id)}`, { method: 'POST' })
    plexActionState[key] = res.ok ? 'done' : 'error'
  } catch {
    plexActionState[key] = 'error'
  } finally {
    setTimeout(() => { plexActionState[key] = 'idle' }, 3000)
  }
}

// Jellyfin/Emby tasks
const serverTasks = reactive<Record<string, { loading: boolean; error: string; tasks: MaintTask[] }>>({})
const taskStarting = reactive<Record<string, boolean>>({})
let taskPollTimer: ReturnType<typeof setTimeout> | null = null

async function loadServerTasks(serverId: string, quiet = false) {
  // Re-read through the reactive object after creating the entry -- the
  // assignment expression returns the plain object, and mutating that one
  // wouldn't trigger a re-render (the page got stuck on "Loading tasks...").
  if (!serverTasks[serverId]) serverTasks[serverId] = { loading: false, error: '', tasks: [] }
  const entry = serverTasks[serverId]!
  if (!quiet) entry.loading = true
  try {
    const res = await fetch(`${apiBase}/api/cleanup/media-server/${encodeURIComponent(serverId)}/tasks`)
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body?.detail || `Couldn't load tasks (${res.status})`)
    }
    entry.tasks = (await res.json()).tasks || []
    entry.error = ''
  } catch (e) {
    entry.error = e instanceof Error ? e.message : "Couldn't load tasks"
  } finally {
    entry.loading = false
  }
}

function anyTaskRunning(): boolean {
  return Object.values(serverTasks).some(e => e.tasks.some(t => t.state !== 'Idle'))
}

// While anything is running, refresh every few seconds so progress and the
// final result show up without a manual reload.
function scheduleTaskPoll() {
  if (taskPollTimer) clearTimeout(taskPollTimer)
  taskPollTimer = setTimeout(async () => {
    taskPollTimer = null
    const ids = maintenanceServers.value.filter(s => s.type !== 'plex').map(s => s.id)
    await Promise.all(ids.map(id => loadServerTasks(id, true)))
    if (anyTaskRunning()) scheduleTaskPoll()
  }, 3000)
}

async function runServerTask(server: MaintServer, task: MaintTask) {
  if (!confirm(`Run "${task.name}" on ${server.label} now?`)) return
  const key = `${server.id}:${task.key}`
  taskStarting[key] = true
  try {
    const res = await fetch(`${apiBase}/api/cleanup/media-server/${encodeURIComponent(server.id)}/tasks/${encodeURIComponent(task.key)}/run`, { method: 'POST' })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      alert(body?.detail || `Couldn't start "${task.name}"`)
    }
  } catch {
    alert(`Couldn't start "${task.name}"`)
  } finally {
    taskStarting[key] = false
  }
  await loadServerTasks(server.id, true)
  scheduleTaskPoll()
}

function taskLastRun(task: MaintTask): string {
  if (!task.last_run_end) return 'Never run'
  const when = new Date(task.last_run_end)
  const label = isNaN(when.getTime()) ? task.last_run_end : when.toLocaleString()
  return `Last run ${label}${task.last_run_status ? ` — ${task.last_run_status}` : ''}`
}

function taskButtonLabel(serverId: string, task: MaintTask): string {
  if (taskStarting[`${serverId}:${task.key}`]) return 'Starting...'
  if (task.state === 'Running') return task.progress != null ? `Running ${Math.round(task.progress)}%` : 'Running...'
  if (task.state === 'Cancelling') return 'Cancelling...'
  return 'Run Now'
}

// Fetch each Jellyfin/Emby server's tasks as soon as it shows up in the list.
// Not just on mount: the settings (and so the server list) may still be
// loading when this tab first renders.
watch(
  () => maintenanceServers.value.filter(s => s.type !== 'plex').map(s => s.id),
  (ids) => {
    for (const id of ids) if (!serverTasks[id]) loadServerTasks(id)
  },
  { immediate: true }
)
onBeforeUnmount(() => {
  if (taskPollTimer) clearTimeout(taskPollTimer)
})

// --- Simposter's own SQLite database (distinct from Plex's Optimize Database
// above, which only ever touches Plex's own server-side DB) ------------------

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

const dbStats = ref<{ file_size_bytes: number; reclaimable_bytes: number } | null>(null)
const dbVacuumState = ref<PlexActionState>('idle')
const dbVacuumResult = ref<string | null>(null)

async function loadDbStats() {
  try {
    const res = await fetch(`${apiBase}/api/cleanup/database/stats`)
    if (res.ok) dbStats.value = await res.json()
  } catch {
    /* non-critical */
  }
}

loadDbStats()

async function runDbVacuum() {
  if (!dbStats.value) return
  const reclaimable = formatBytes(dbStats.value.reclaimable_bytes)
  if (!confirm(`Compact Simposter's database? This reclaims roughly ${reclaimable} of unused space by rewriting the file -- safe and reversible only in the sense that no data is lost, just the file is rewritten.`)) return
  dbVacuumState.value = 'running'
  dbVacuumResult.value = null
  try {
    const res = await fetch(`${apiBase}/api/cleanup/database/vacuum`, { method: 'POST' })
    if (res.ok) {
      const data = await res.json()
      dbVacuumResult.value = `Reclaimed ${formatBytes(data.bytes_reclaimed)} (${formatBytes(data.bytes_before)} → ${formatBytes(data.bytes_after)})`
      dbVacuumState.value = 'done'
      await loadDbStats()
    } else {
      dbVacuumState.value = 'error'
    }
  } catch {
    dbVacuumState.value = 'error'
  } finally {
    setTimeout(() => { dbVacuumState.value = 'idle' }, 5000)
  }
}
</script>

<template>
  <div class="tab-content">
    <h2>Cleanup</h2>

    <div class="section">
      <h3>Simposter Cache Cleanup</h3>
      <p class="section-description">
        Finds cached poster/logo/backdrop/square art files, overlay effect renders, uploaded images, and overlay
        assets that no longer correspond to anything in your library or presets, plus old History entries. Nothing
        is deleted directly -- everything moves to a reversible trash first (see below).
      </p>

      <div class="scan-controls">
        <label class="days-input">
          History older than
          <input type="number" v-model.number="historyDays" min="1" max="3650" />
          days
        </label>
        <button @click="runScan" :disabled="scanning" class="secondary">
          {{ scanning ? 'Scanning...' : 'Scan for Cleanup Candidates' }}
        </button>
      </div>

      <p v-if="scanError" class="error-text">{{ scanError }}</p>
      <p v-if="cleanMessage" class="success-text">{{ cleanMessage }}</p>
      <p v-if="cleanError" class="error-text">{{ cleanError }}</p>

      <div v-if="scanResult" class="scan-report">
        <p v-if="scanResult.stale_cache_warning" class="note">⚠️ {{ scanResult.stale_cache_warning }}</p>

        <div class="category-header">
          <span>{{ scanResult.total_bytes_human }} reclaimable across all categories</span>
          <div class="select-links">
            <button class="link-btn" @click="selectAll">Select All</button>
            <button class="link-btn" @click="selectNone">Select None</button>
          </div>
        </div>

        <div class="category-list">
          <label
            v-for="cat in scanResult.categories"
            :key="cat.id"
            class="category-item"
            :class="{ disabled: cat.count === 0 }"
          >
            <input
              type="checkbox"
              :checked="selectedCategories.has(cat.id)"
              :disabled="cat.count === 0"
              @change="toggleCategory(cat.id)"
            />
            <div class="category-info">
              <strong>{{ cat.label }}</strong>
              <p>{{ cat.description }}</p>
            </div>
            <div class="category-stats">
              <span class="count">{{ cat.count }}</span>
              <span class="size" v-if="cat.kind === 'files'">{{ humanBytes(cat.bytes) }}</span>
            </div>
          </label>
        </div>

        <div class="clean-actions">
          <span v-if="selectedCategories.size > 0" class="selected-summary">
            {{ selectedCategories.size }} categories selected ({{ humanBytes(selectedTotalBytes) }})
          </span>
          <button
            @click="runClean"
            :disabled="cleaning || selectedCategories.size === 0"
            class="primary"
          >
            {{ cleaning ? 'Cleaning...' : 'Clean Selected' }}
          </button>
        </div>
      </div>
    </div>

    <div class="section">
      <h3>Cleanup Trash</h3>
      <p class="section-description">
        Files/rows moved here by "Clean Selected" above. Nothing is permanently removed until you empty a batch (or
        all of them) explicitly.
      </p>

      <div v-if="loadingTrash" class="state-msg">Loading...</div>
      <div v-else-if="trashBatches.length === 0" class="state-msg">Trash is empty.</div>
      <template v-else>
        <div class="trash-list">
          <div v-for="batch in trashBatches" :key="batch.batch_id" class="trash-item">
            <div class="trash-info">
              <strong>{{ new Date(batch.created_at * 1000).toLocaleString() }}</strong>
              <p>{{ batch.categories.join(', ') }} &mdash; {{ batch.bytes_human }}</p>
            </div>
            <div class="trash-actions">
              <button
                @click="restoreBatch(batch.batch_id)"
                :disabled="trashActionBusy.has(batch.batch_id)"
                class="secondary"
              >
                Restore
              </button>
              <button
                @click="emptyBatch(batch.batch_id)"
                :disabled="trashActionBusy.has(batch.batch_id)"
                class="danger"
              >
                Empty
              </button>
            </div>
          </div>
        </div>
        <div class="actions">
          <button @click="emptyAllTrash" class="danger">Empty All Trash</button>
        </div>
      </template>
    </div>

    <div class="section">
      <h3>Scheduled Cleanup</h3>
      <p class="section-description">
        Automatically scan and move matched categories to the cleanup trash on a schedule -- never permanently
        deletes anything on its own, the trash still only gets emptied when you do it above. Off by default.
      </p>

      <label class="checkbox-label">
        <input type="checkbox" v-model="localScheduleEnabled" />
        <span>Enable scheduled cleanup</span>
      </label>

      <div v-if="localScheduleEnabled" class="schedule-config">
        <div class="cron-input-inline">
          <label>
            <span class="label-text">Cron Expression</span>
            <input v-model="localScheduleCronExpression" type="text" placeholder="0 3 * * 0" />
            <span class="help-text">Example: "0 3 * * 0" = Weekly, Sundays at 3 AM</span>
          </label>
          <label class="days-input">
            History older than
            <input type="number" v-model.number="localScheduleHistoryDays" min="1" max="3650" />
            days
          </label>
        </div>

        <div class="schedule-categories">
          <span class="label-text">Categories to include</span>
          <div class="category-checkboxes">
            <label v-for="cat in CATEGORY_CATALOG" :key="cat.id" class="checkbox-label">
              <input
                type="checkbox"
                :checked="isScheduleCategorySelected(cat.id)"
                @change="toggleScheduleCategory(cat.id)"
              />
              <span>{{ cat.label }}</span>
            </label>
          </div>
        </div>

        <div v-if="scheduleNextRun" class="next-run">
          <strong>Next Run:</strong> {{ formatNextRun(scheduleNextRun) }}
        </div>
      </div>

      <div class="actions">
        <button @click="emit('save')" class="primary" :disabled="!unsavedChanges">
          {{ unsavedChanges ? 'Save Changes' : 'No Changes' }}
        </button>
      </div>
    </div>

    <div class="section">
      <h3>Simposter Database Maintenance</h3>
      <p class="section-description">
        Simposter's own <code>simposter.db</code> -- distinct from the Plex maintenance below, which only touches
        Plex's server-side database. Years of settings/cache/history changes leave behind unused free pages in the
        file that SQLite doesn't reclaim on its own; compacting rewrites the file to reclaim that space.
      </p>

      <div class="preset-actions">
        <div class="preset-action-item">
          <div class="preset-info">
            <strong>Compact Database</strong>
            <p v-if="dbStats">
              Current size: {{ formatBytes(dbStats.file_size_bytes) }}
              <span v-if="dbStats.reclaimable_bytes > 0"> ({{ formatBytes(dbStats.reclaimable_bytes) }} reclaimable)</span>
            </p>
            <p v-if="dbVacuumResult" class="note">{{ dbVacuumResult }}</p>
          </div>
          <button
            @click="runDbVacuum"
            :disabled="dbVacuumState === 'running' || !dbStats"
            class="secondary"
          >
            {{ dbVacuumState === 'running' ? 'Compacting...' : dbVacuumState === 'done' ? 'Done' : dbVacuumState === 'error' ? 'Failed' : 'Compact Database' }}
          </button>
        </div>
      </div>
    </div>

    <div class="section">
      <h3>Media Server Maintenance</h3>
      <p class="section-description">
        Runs each media server's own built-in maintenance -- unrelated to Simposter's own cache above. These also run
        on the server's own schedule; use these buttons if you don't want to wait.
      </p>

      <p v-if="maintenanceServers.length === 0" class="note">
        No media servers configured yet -- add one in Settings &rarr; Media Servers.
      </p>

      <div v-for="server in maintenanceServers" :key="server.id" class="server-maint">
        <h4 class="server-maint-title">
          <span class="server-type-pill" :class="server.type">{{ server.type }}</span>
          {{ server.label }}
        </h4>

        <!-- Plex -->
        <div v-if="server.type === 'plex'" class="preset-actions">
          <div v-for="action in PLEX_ACTIONS" :key="action.key" class="preset-action-item">
            <div class="preset-info">
              <strong>{{ action.title }}</strong>
              <p>{{ action.text }}</p>
            </div>
            <button
              @click="runPlexAction(server, action)"
              :disabled="plexState(server.id, action.key) === 'running'"
              class="secondary"
            >
              {{ plexState(server.id, action.key) === 'running' ? 'Running...'
                : plexState(server.id, action.key) === 'done' ? action.doneLabel
                : plexState(server.id, action.key) === 'error' ? 'Failed' : action.label }}
            </button>
          </div>
        </div>

        <!-- Jellyfin / Emby -->
        <template v-else>
          <p v-if="!serverTasks[server.id] || serverTasks[server.id]?.loading" class="note">Loading tasks...</p>
          <p v-else-if="serverTasks[server.id]?.error" class="note error-note">{{ serverTasks[server.id]?.error }}</p>
          <p v-else-if="!serverTasks[server.id]?.tasks.length" class="note">
            This server doesn't report any of the supported maintenance tasks.
          </p>
          <div v-else class="preset-actions">
            <div v-for="task in serverTasks[server.id]?.tasks || []" :key="task.key" class="preset-action-item">
              <div class="preset-info">
                <strong>{{ task.name }}</strong>
                <p>{{ task.description }}</p>
                <p class="task-last-run">{{ taskLastRun(task) }}</p>
              </div>
              <button
                @click="runServerTask(server, task)"
                :disabled="task.state !== 'Idle' || !!taskStarting[`${server.id}:${task.key}`]"
                class="secondary"
              >
                {{ taskButtonLabel(server.id, task) }}
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <div class="section coming-soon">
      <h3>ImageMaid Integration <span class="badge">Coming Soon</span></h3>
      <p class="section-description">
        Everything above cleans Simposter's own cache, plus Plex's own coarse, built-in maintenance operations. Neither
        touches something ImageMaid specifically targets: old, no-longer-selected poster/art versions that pile up
        inside the metadata "bundle" of an item still active in your library (e.g. 15 leftover images from past
        Kometa runs or manual poster swaps on a movie you still have). "Clean Bundles" above only removes a bundle
        entirely, and only for items no longer in any library -- it won't touch that.
      </p>
      <p class="section-description">
        Closing that gap the way ImageMaid does requires direct filesystem access to Plex's own server data directory
        (to read Plex's database and the bundle files themselves) -- a new required volume mount, not just an API
        call. Planned for a future release.
      </p>
    </div>
  </div>
</template>

<style scoped>
.tab-content {
  padding: 20px;
  max-width: 1600px;
}

h2 {
  margin-top: 0;
  margin-bottom: 24px;
  color: var(--text-primary);
  font-size: 24px;
}

h3 {
  margin-top: 0;
  margin-bottom: 16px;
  color: var(--text-secondary);
  font-size: 18px;
}

.section {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
}

.section-description {
  color: var(--text-muted);
  font-size: 14px;
  margin-bottom: 20px;
  line-height: 1.5;
}

.section-description:last-child {
  margin-bottom: 0;
}

.coming-soon {
  opacity: 0.85;
}

.coming-soon h3 {
  display: flex;
  align-items: center;
  gap: 10px;
}

.badge {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 3px 9px;
  border-radius: 999px;
  background: rgba(255, 193, 7, 0.12);
  color: #ffc107;
  border: 1px solid rgba(255, 193, 7, 0.35);
}

.scan-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.days-input {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-muted);
}

.days-input input {
  width: 70px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  margin-bottom: 12px;
}

.checkbox-label input[type="checkbox"] {
  width: auto;
  cursor: pointer;
}

.checkbox-label span {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 14px;
}

.schedule-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 4px;
}

.cron-input-inline {
  display: flex;
  align-items: flex-end;
  gap: 20px;
  flex-wrap: wrap;
}

.cron-input-inline label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cron-input-inline input[type="text"] {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  min-width: 160px;
}

.label-text {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 13px;
}

.help-text {
  font-size: 11px;
  color: var(--text-muted);
}

.schedule-categories {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.category-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
}

.category-checkboxes .checkbox-label {
  margin-bottom: 0;
}

.next-run {
  padding: 14px;
  background: rgba(61, 214, 183, 0.05);
  border: 1px solid rgba(61, 214, 183, 0.2);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.next-run strong {
  color: var(--accent);
}

.error-text {
  color: #f05d7b;
  font-size: 13px;
  margin-top: 12px;
}

.success-text {
  color: #3dd6b7;
  font-size: 13px;
  margin-top: 12px;
}

.note {
  margin-top: 16px;
  padding: 12px;
  background: rgba(255, 200, 0, 0.1);
  border: 1px solid rgba(255, 200, 0, 0.3);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.6;
}

.scan-report {
  margin-top: 20px;
}

.category-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 10px;
}

.select-links {
  display: flex;
  gap: 10px;
}

.link-btn {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}

.category-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.category-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
}

.category-item.disabled {
  opacity: 0.5;
  cursor: default;
}

.category-info {
  flex: 1;
  min-width: 0;
}

.category-info strong {
  display: block;
  color: var(--text-primary);
  font-size: 14px;
}

.category-info p {
  margin: 2px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.category-stats {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
}

.category-stats .count {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 14px;
}

.category-stats .size {
  font-size: 12px;
  color: var(--text-muted);
}

.clean-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.selected-summary {
  font-size: 13px;
  color: var(--text-muted);
}

.state-msg {
  padding: 14px;
  color: var(--text-muted);
  font-size: 14px;
}

.trash-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trash-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.trash-info strong {
  display: block;
  color: var(--text-primary);
  font-size: 14px;
}

.trash-info p {
  margin: 2px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.trash-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.preset-actions {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.preset-action-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.preset-info {
  flex: 1;
}

.preset-info strong {
  display: block;
  color: var(--text-primary);
  font-size: 14px;
  margin-bottom: 4px;
}

.preset-info p {
  color: var(--text-muted);
  font-size: 13px;
  margin: 0;
}

.actions {
  display: flex;
  gap: 12px;
  padding-top: 16px;
}

button {
  padding: 10px 20px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

button:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.08);
  border-color: var(--accent);
}

button.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

button.primary:hover:not(:disabled) {
  opacity: 0.9;
}

button.secondary {
  background: rgba(255, 255, 255, 0.06);
}

button.danger {
  background: rgba(240, 93, 123, 0.12);
  border-color: rgba(240, 93, 123, 0.4);
  color: #f05d7b;
}

button.danger:hover:not(:disabled) {
  background: rgba(240, 93, 123, 0.22);
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.server-maint {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}
.server-maint:first-of-type {
  border-top: none;
  padding-top: 0;
}
.server-maint-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 15px;
}
.server-type-pill {
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
.server-type-pill.plex { background: rgba(229, 160, 13, 0.15); color: #e5a00d; }
.server-type-pill.jellyfin { background: rgba(170, 92, 195, 0.15); color: #aa5cc3; }
.server-type-pill.emby { background: rgba(82, 181, 75, 0.15); color: #52b54b; }
.task-last-run {
  font-size: 12px;
  opacity: 0.75;
}
.error-note {
  color: #f05d7b;
}
</style>
