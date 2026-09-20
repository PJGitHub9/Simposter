<script setup lang="ts">
import { ref, computed } from 'vue'
import { getApiBase } from '@/services/apiBase'

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

// --- Plex server maintenance -----------------------------------------------

type PlexActionState = 'idle' | 'running' | 'done' | 'error'
const plexEmptyTrashState = ref<PlexActionState>('idle')
const plexCleanBundlesState = ref<PlexActionState>('idle')
const plexOptimizeState = ref<PlexActionState>('idle')

// Three separate functions rather than one taking a ref parameter -- a ref
// passed as a template-call argument arrives already unwrapped (Vue's
// <script setup> auto-unwraps top-level refs in template expressions), so a
// generic version can't actually write back to the right state ref.
async function runPlexActionFor(endpoint: string, state: typeof plexEmptyTrashState) {
  state.value = 'running'
  try {
    const res = await fetch(`${apiBase}/api/cleanup/plex/${endpoint}`, { method: 'POST' })
    state.value = res.ok ? 'done' : 'error'
  } catch {
    state.value = 'error'
  } finally {
    setTimeout(() => { state.value = 'idle' }, 3000)
  }
}

function runPlexEmptyTrash() {
  if (!confirm('Empty trash for every Plex library section?')) return
  runPlexActionFor('empty-trash', plexEmptyTrashState)
}

function runPlexCleanBundles() {
  if (!confirm("Start Plex's Clean Bundles operation?")) return
  runPlexActionFor('clean-bundles', plexCleanBundlesState)
}

function runPlexOptimizeDb() {
  if (!confirm("Start Plex's Optimize Database operation?")) return
  runPlexActionFor('optimize-db', plexOptimizeState)
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
      <h3>Plex Server Maintenance</h3>
      <p class="section-description">
        These call Plex's own maintenance operations directly (the same ones Plex's Scheduled Tasks and tools like
        ImageMaid use) -- unrelated to Simposter's own cache above.
      </p>

      <div class="preset-actions">
        <div class="preset-action-item">
          <div class="preset-info">
            <strong>Empty Trash</strong>
            <p>Empties the trash for every Plex library section (items you've removed from Plex itself).</p>
          </div>
          <button
            @click="runPlexEmptyTrash"
            :disabled="plexEmptyTrashState === 'running'"
            class="secondary"
          >
            {{ plexEmptyTrashState === 'running' ? 'Running...' : plexEmptyTrashState === 'done' ? 'Done' : plexEmptyTrashState === 'error' ? 'Failed' : 'Empty Trash' }}
          </button>
        </div>
        <div class="preset-action-item">
          <div class="preset-info">
            <strong>Clean Bundles</strong>
            <p>Removes unused metadata bundles Plex has left behind for items no longer in any library.</p>
          </div>
          <button
            @click="runPlexCleanBundles"
            :disabled="plexCleanBundlesState === 'running'"
            class="secondary"
          >
            {{ plexCleanBundlesState === 'running' ? 'Running...' : plexCleanBundlesState === 'done' ? 'Started' : plexCleanBundlesState === 'error' ? 'Failed' : 'Clean Bundles' }}
          </button>
        </div>
        <div class="preset-action-item">
          <div class="preset-info">
            <strong>Optimize Database</strong>
            <p>Cleans up Plex's own database from unused or fragmented data.</p>
          </div>
          <button
            @click="runPlexOptimizeDb"
            :disabled="plexOptimizeState === 'running'"
            class="secondary"
          >
            {{ plexOptimizeState === 'running' ? 'Running...' : plexOptimizeState === 'done' ? 'Started' : plexOptimizeState === 'error' ? 'Failed' : 'Optimize Database' }}
          </button>
        </div>
      </div>
      <p class="note">
        These run on Plex's own schedule too (usually weekly) -- use these buttons if you don't want to wait for that.
      </p>
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
</style>
