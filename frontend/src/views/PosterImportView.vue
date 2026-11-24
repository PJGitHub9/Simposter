<script setup lang="ts">
// Tools -> Poster Import: Kometa-style `url_poster` YAML (Kometa metadata files,
// TPDbCollectionMaker output) applied to this library group, once or from a
// live file on the server. Backend: backend/custom_posters.py.
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore } from '@/stores/settings'
import { mediaServerLabel } from '@/services/mediaServerLabel'
import ServerFilePicker from '@/components/overlay/ServerFilePicker.vue'

type Mode = 'template' | 'overlay' | 'as_is'
type Copy = { server_id: string; rating_key: string; library_id: string }
type Entry = {
  key: string
  id: number | null
  title: string | null
  year: number | null
  url: string | null
  seasons: Record<string, string>
  section: string
  notes: string[]
  status: 'matched' | 'collection' | 'not_found' | 'ambiguous'
  matched_title?: string
  matched_year?: number
  message?: string
  copies: Copy[]
}
type JobResult = { key: string; title: string; mode: string; status: string; message: string }
type JobStatus = {
  state?: 'idle' | 'running' | 'done' | 'error'
  label?: string
  total?: number
  processed?: number
  current?: string
  summary?: string
  error?: string | null
  results?: JobResult[]
}
type LiveFile = {
  id: string
  path: string
  name: string
  mode: Mode
  template_id: string
  preset_id: string | null
  interval_hours: number
  enabled: boolean
  last_checked_at: string | null
  last_changed_at: string | null
  last_status: string | null
  last_message: string | null
  next_run: string | null
}
type Stored = {
  item_key: string
  season_index: number | null
  title: string | null
  url: string
  updated_at: string
}

const apiBase = getApiBase()
const route = useRoute()
const settings = useSettingsStore()

const isTV = computed(() => route.name === 'tv-poster-import')
const mediaType = computed(() => (isTV.value ? 'tv' : 'movie'))
const libraryId = computed(() => (route.query.library as string) || '')
const serverId = computed(() => (route.query.server as string) || 'plex-1')
const libQuery = computed(() =>
  `server_id=${encodeURIComponent(serverId.value)}&library_id=${encodeURIComponent(libraryId.value)}&media_type=${mediaType.value}`)

const MODE_LABELS: Record<Mode, string> = {
  template: 'Render with a preset',
  overlay: 'Overlays only',
  as_is: 'Use as-is and leave alone',
}
const MODE_HELP: Record<Mode, string> = {
  template: 'The imported poster becomes the background of a normal render (logo, text, effects and overlays from the preset). Later renders keep using it.',
  overlay: 'Sets the title to Overlay only: the preset\'s overlays are drawn on the imported poster, and Overlay Refresh keeps them current.',
  as_is: 'Uploads the poster unchanged and sets the title to Leave alone, so webhooks, scans and refreshes never replace it.',
}

const tab = ref<'once' | 'live' | 'stored'>('once')

// ---- presets ----
const presets = ref<{ id: string; name: string }[]>([])
const loadPresets = async () => {
  try {
    const res = await fetch(`${apiBase}/api/presets`)
    const data = await res.json()
    presets.value = (data?.uniformlogo?.presets || []).map((p: any) => ({ id: p.id, name: p.name || p.id }))
  } catch {
    presets.value = []
  }
}
const defaultPreset = computed(() => {
  const group = (settings.libraryGroups.value || []).find(g =>
    (g.members || []).some(m => m.serverId === serverId.value && m.libraryId === libraryId.value))
  const mappings = isTV.value ? settings.plex.value.tvShowLibraryMappings : settings.plex.value.libraryMappings
  const plexMember = group?.members?.find(m => m.serverId === 'plex-1')
  const mapping = (mappings || []).find((m: any) => String(m.id) === String(plexMember?.libraryId ?? libraryId.value))
  return (mapping as any)?.autoGeneratePresetId || (group as any)?.autoGeneratePresetId || presets.value[0]?.id || ''
})

// ---- import once ----
const text = ref('')
const mode = ref<Mode>('template')
const presetId = ref('')
const entries = ref<Entry[]>([])
const messages = ref<string[]>([])
const checking = ref(false)
const checkError = ref('')
const overrides = ref<Record<string, Mode | 'skip' | ''>>({})
const showOnly = ref<'all' | 'matched' | 'unmatched'>('all')
const fileInput = ref<HTMLInputElement | null>(null)

const needsPreset = (m: Mode) => m === 'template' || m === 'overlay'
const importable = computed(() => entries.value.filter(e => e.status === 'matched' || e.status === 'collection'))
const willImport = computed(() => importable.value.filter(e => overrides.value[e.key] !== 'skip'))
const shownEntries = computed(() => {
  if (showOnly.value === 'matched') return importable.value
  if (showOnly.value === 'unmatched') return entries.value.filter(e => e.status === 'not_found' || e.status === 'ambiguous')
  return entries.value
})
const counts = computed(() => ({
  matched: entries.value.filter(e => e.status === 'matched').length,
  collection: entries.value.filter(e => e.status === 'collection').length,
  unmatched: entries.value.filter(e => e.status === 'not_found' || e.status === 'ambiguous').length,
}))

const loadFile = (ev: Event) => {
  const f = (ev.target as HTMLInputElement).files?.[0]
  if (!f) return
  const reader = new FileReader()
  reader.onload = () => {
    text.value = String(reader.result || '')
    entries.value = []
  }
  reader.readAsText(f)
  ;(ev.target as HTMLInputElement).value = ''
}

const check = async () => {
  checking.value = true
  checkError.value = ''
  try {
    const res = await fetch(`${apiBase}/api/poster-import/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.value, server_id: serverId.value, library_id: libraryId.value, media_type: mediaType.value }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
    entries.value = data.entries || []
    messages.value = data.messages || []
    overrides.value = {}
    showOnly.value = 'all'
  } catch (e: any) {
    checkError.value = e?.message || 'Check failed'
    entries.value = []
  } finally {
    checking.value = false
  }
}

const entryTitle = (e: Entry) => e.matched_title || e.title || e.key
const entryYear = (e: Entry) => e.matched_year || e.year
const seasonCount = (e: Entry) => Object.keys(e.seasons || {}).length
const serversOf = (e: Entry) =>
  [...new Set((e.copies || []).map(c => mediaServerLabel(c.server_id, settings.mediaServers.value)))].join(', ')
const statusLabel = (e: Entry) =>
  ({ matched: 'Matched', collection: 'Collection', not_found: 'Not found', ambiguous: 'Unclear' } as Record<string, string>)[e.status] || e.status

// ---- job status ----
const job = ref<JobStatus>({ state: 'idle' })
const jobError = ref('')
let poll: ReturnType<typeof setInterval> | null = null
const pollStatus = async () => {
  try {
    const res = await fetch(`${apiBase}/api/poster-import/status`)
    job.value = await res.json()
    if (job.value.state !== 'running') {
      stopPoll()
      if (tab.value === 'stored') loadStored()
      if (tab.value === 'live') loadFiles()
    }
  } catch {
    /* keep polling */
  }
}
const startPoll = () => {
  stopPoll()
  poll = setInterval(pollStatus, 1500)
  pollStatus()
}
const stopPoll = () => {
  if (poll) clearInterval(poll)
  poll = null
}
const running = computed(() => job.value.state === 'running')
const percent = computed(() => {
  const t = job.value.total || 0
  return t ? Math.round(((job.value.processed || 0) / t) * 100) : 0
})

const starting = ref(false)
const apply = async () => {
  jobError.value = ''
  starting.value = true
  const cleanOverrides: Record<string, string> = {}
  for (const [k, v] of Object.entries(overrides.value)) if (v) cleanOverrides[k] = v
  try {
    const res = await fetch(`${apiBase}/api/poster-import/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text.value, server_id: serverId.value, library_id: libraryId.value, media_type: mediaType.value,
        mode: mode.value, template_id: 'uniformlogo', preset_id: presetId.value || null, overrides: cleanOverrides,
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
    job.value = { state: 'running', label: 'Import', total: willImport.value.length, processed: 0, current: 'Starting…' }
    startPoll()
  } catch (e: any) {
    jobError.value = e?.message || 'Import failed to start'
  } finally {
    starting.value = false
  }
}

// ---- live files ----
const files = ref<LiveFile[]>([])
const filesError = ref('')
const showPicker = ref(false)
const form = ref({ id: '' as string, path: '', name: '', mode: 'template' as Mode, preset_id: '', interval_hours: 6, enabled: true })
const savingFile = ref(false)
const INTERVALS = [
  { v: 1, l: 'Every hour' }, { v: 3, l: 'Every 3 hours' }, { v: 6, l: 'Every 6 hours' },
  { v: 12, l: 'Every 12 hours' }, { v: 24, l: 'Once a day' },
]

const loadFiles = async () => {
  try {
    const res = await fetch(`${apiBase}/api/poster-import/files?${libQuery.value}`)
    files.value = (await res.json()).files || []
  } catch {
    files.value = []
  }
}
const resetForm = () => {
  form.value = { id: '', path: '', name: '', mode: 'template', preset_id: defaultPreset.value, interval_hours: 6, enabled: true }
}
const editFile = (f: LiveFile) => {
  form.value = { id: f.id, path: f.path, name: f.name, mode: f.mode, preset_id: f.preset_id || '', interval_hours: f.interval_hours, enabled: f.enabled }
}
const saveFile = async (patch?: Partial<LiveFile>, base?: LiveFile) => {
  filesError.value = ''
  savingFile.value = true
  const body = base
    ? { ...base, ...patch, server_id: serverId.value, library_id: libraryId.value, media_type: mediaType.value }
    : { ...form.value, id: form.value.id || null, template_id: 'uniformlogo', preset_id: form.value.preset_id || null,
        server_id: serverId.value, library_id: libraryId.value, media_type: mediaType.value }
  try {
    const res = await fetch(`${apiBase}/api/poster-import/files`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
    if (!base) {
      const isNew = !form.value.id
      resetForm()
      if (isNew) setTimeout(startPoll, 300)
    }
    await loadFiles()
  } catch (e: any) {
    filesError.value = e?.message || 'Save failed'
  } finally {
    savingFile.value = false
  }
}
const syncFile = async (f: LiveFile, force = false) => {
  filesError.value = ''
  const res = await fetch(`${apiBase}/api/poster-import/files/${f.id}/sync?force=${force}`, { method: 'POST' })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    filesError.value = data?.detail || `HTTP ${res.status}`
    return
  }
  startPoll()
}
const removeFile = async (f: LiveFile) => {
  if (!window.confirm(`Stop watching ${f.name || f.path}? Posters it already imported stay as they are.`)) return
  await fetch(`${apiBase}/api/poster-import/files/${f.id}`, { method: 'DELETE' })
  if (form.value.id === f.id) resetForm()
  loadFiles()
}
const fileName = (f: LiveFile) => f.name || f.path.replace(/\\/g, '/').split('/').pop() || ''
const checkingFile = (f: LiveFile) => running.value && job.value.label === `Live file ${fileName(f)}`
const fmtTime = (s: string | null) => (s ? new Date(s).toLocaleString() : '—')

// ---- stored posters ----
const stored = ref<Stored[]>([])
const storedFilter = ref('')
const loadStored = async () => {
  try {
    const res = await fetch(`${apiBase}/api/poster-import/posters?${libQuery.value}`)
    stored.value = (await res.json()).posters || []
  } catch {
    stored.value = []
  }
}
const shownStored = computed(() => {
  const q = storedFilter.value.trim().toLowerCase()
  return q ? stored.value.filter(s => (s.title || '').toLowerCase().includes(q)) : stored.value
})
const removeStored = async (s: Stored) => {
  const what = s.season_index === null ? (s.title || 'this title') : `${s.title} season ${s.season_index}`
  if (!window.confirm(`Stop using the imported poster for ${what}? The next render uses TMDb's posters again; the poster on your server doesn't change until then.`)) return
  await fetch(`${apiBase}/api/poster-import/posters/remove`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ media_type: mediaType.value, item_key: s.item_key, season_index: s.season_index }),
  })
  loadStored()
}

const load = async () => {
  entries.value = []
  await loadPresets()
  presetId.value = defaultPreset.value
  resetForm()
  loadFiles()
  loadStored()
  pollStatus()
  const res = await fetch(`${apiBase}/api/poster-import/status`).then(r => r.json()).catch(() => null)
  if (res?.state === 'running') startPoll()
}

watch(tab, t => {
  if (t === 'stored') loadStored()
  if (t === 'live') loadFiles()
})
watch([libraryId, serverId, mediaType], load)
onMounted(load)
onUnmounted(stopPoll)
</script>

<template>
  <div class="poster-import-view">
    <div class="page-header">
      <h2>📥 Poster Import</h2>
    </div>

    <div class="section-note">
      Paste or load a Kometa-style file with <code>url_poster</code> links: a Kometa metadata file (titles keyed by
      TMDb id) or TPDbCollectionMaker's output (keyed by title, with seasons and collections). Simposter downloads
      each linked image once and keeps it as that title's poster in this library group.
    </div>

    <div class="tabs">
      <button type="button" :class="{ active: tab === 'once' }" @click="tab = 'once'">Import once</button>
      <button type="button" :class="{ active: tab === 'live' }" @click="tab = 'live'">Live files</button>
      <button type="button" :class="{ active: tab === 'stored' }" @click="tab = 'stored'">
        Imported posters<span v-if="stored.length" class="count">{{ stored.length }}</span>
      </button>
    </div>

    <div v-if="running || job.state === 'done' || job.state === 'error'" class="section job">
      <div class="job-head">
        <strong>{{ job.label || 'Import' }}</strong>
        <span v-if="running">{{ job.processed || 0 }} / {{ job.total || 0 }} · {{ job.current }}</span>
        <span v-else-if="job.state === 'done'" class="ok">Finished: {{ job.summary }}</span>
        <span v-else class="bad">{{ job.error }}</span>
      </div>
      <div v-if="running" class="bar"><div class="fill" :style="{ width: percent + '%' }" /></div>
      <details v-if="job.results && job.results.length">
        <summary>Results ({{ job.results.length }})</summary>
        <ul class="results">
          <li v-for="r in job.results" :key="r.key" :class="r.status">
            <strong>{{ r.title }}</strong> — {{ r.message }}
          </li>
        </ul>
      </details>
    </div>

    <!-- Import once -->
    <div v-if="tab === 'once'" class="section">
      <div class="row">
        <button type="button" class="secondary" @click="fileInput?.click()">Load a .yml file</button>
        <input ref="fileInput" type="file" accept=".yml,.yaml,text/yaml" hidden @change="loadFile" />
        <span class="hint">or paste below</span>
      </div>
      <textarea v-model="text" rows="10" spellcheck="false" placeholder="metadata:
  603692:
    url_poster: https://theposterdb.com/api/assets/571277" />

      <div class="settings-grid">
        <label>
          <span>What to do with the posters</span>
          <select v-model="mode">
            <option v-for="(l, m) in MODE_LABELS" :key="m" :value="m">{{ l }}</option>
          </select>
        </label>
        <label v-if="needsPreset(mode)">
          <span>Preset</span>
          <select v-model="presetId">
            <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>
      </div>
      <p class="hint">{{ MODE_HELP[mode] }} Collections are always uploaded as-is.</p>

      <div class="row">
        <button type="button" class="primary" :disabled="!text.trim() || checking" @click="check">
          {{ checking ? 'Checking…' : 'Check' }}
        </button>
        <span v-if="checkError" class="bad">{{ checkError }}</span>
      </div>

      <template v-if="entries.length">
        <div class="row summary">
          <span>{{ counts.matched }} matched</span>
          <span v-if="counts.collection">{{ counts.collection }} collection{{ counts.collection === 1 ? '' : 's' }}</span>
          <span v-if="counts.unmatched" class="warn">{{ counts.unmatched }} not in this library group</span>
          <select v-model="showOnly" class="small">
            <option value="all">Show all</option>
            <option value="matched">Matched only</option>
            <option value="unmatched">Not matched only</option>
          </select>
        </div>
        <p v-for="m in messages" :key="m" class="warn">{{ m }}</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Title</th><th>Found</th><th>Servers</th><th>Seasons</th><th>Do</th></tr>
            </thead>
            <tbody>
              <tr v-for="e in shownEntries" :key="e.key" :class="e.status">
                <td>
                  <a v-if="e.url" :href="e.url" target="_blank" rel="noopener noreferrer">{{ entryTitle(e) }}</a>
                  <span v-else>{{ entryTitle(e) }}</span>
                  <span v-if="entryYear(e)" class="muted"> ({{ entryYear(e) }})</span>
                  <div v-if="e.message || e.notes.length" class="muted small-text">{{ [e.message, ...e.notes].filter(Boolean).join('; ') }}</div>
                </td>
                <td><span class="pill" :class="e.status">{{ statusLabel(e) }}</span></td>
                <td>{{ serversOf(e) || '—' }}</td>
                <td>{{ seasonCount(e) || '—' }}</td>
                <td>
                  <select v-if="e.status === 'matched'" v-model="overrides[e.key]" class="small">
                    <option value="">Default</option>
                    <option v-for="(l, m) in MODE_LABELS" :key="m" :value="m">{{ l }}</option>
                    <option value="skip">Skip</option>
                  </select>
                  <select v-else-if="e.status === 'collection'" v-model="overrides[e.key]" class="small">
                    <option value="">Upload as-is</option>
                    <option value="skip">Skip</option>
                  </select>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="row">
          <button type="button" class="primary" :disabled="!willImport.length || running || starting || (needsPreset(mode) && !presetId)" @click="apply">
            <template v-if="running || starting">Importing {{ job.processed || 0 }} / {{ job.total || willImport.length }}…</template>
            <template v-else>Import {{ willImport.length }} title{{ willImport.length === 1 ? '' : 's' }}</template>
          </button>
          <span v-if="jobError" class="bad">{{ jobError }}</span>
          <span v-else-if="running && job.current" class="muted small-text">{{ job.current }}</span>
          <span v-else-if="job.state === 'done' && job.label === 'Import'" class="ok small-text">Finished: {{ job.summary }}</span>
          <span v-else class="hint">One download per linked image; sends go to every server in this group that has the title.</span>
        </div>
        <div v-if="running" class="bar"><div class="fill" :style="{ width: percent + '%' }" /></div>
      </template>
    </div>

    <!-- Live files -->
    <div v-if="tab === 'live'" class="section">
      <p class="hint">
        A file on the Simposter server (for example one of your Kometa metadata files) that's read again on a schedule.
        Titles that are new or whose link changed are imported; a title removed from the file keeps its poster.
      </p>
      <div v-if="files.length" class="files">
        <div v-for="f in files" :key="f.id" class="file-card">
          <div class="file-head">
            <strong>{{ f.name || f.path.split(/[\\/]/).pop() }}</strong>
            <span class="muted">{{ MODE_LABELS[f.mode] }}<template v-if="f.preset_id"> · {{ f.preset_id }}</template></span>
            <span v-if="!f.enabled" class="pill paused">Paused</span>
          </div>
          <div class="muted small-text">{{ f.path }}</div>
          <div class="small-text">
            Last checked {{ fmtTime(f.last_checked_at) }}<template v-if="f.last_message">: {{ f.last_message }}</template>
          </div>
          <div v-if="f.next_run" class="muted small-text">Next check {{ fmtTime(f.next_run) }}</div>
          <div class="row">
            <button type="button" class="secondary-small" :disabled="running" @click="syncFile(f)">{{ checkingFile(f) ? 'Checking…' : 'Check now' }}</button>
            <button type="button" class="secondary-small" :disabled="running" title="Import every title again, changed or not" @click="syncFile(f, true)">Re-import all</button>
            <button type="button" class="secondary-small" @click="editFile(f)">Edit</button>
            <button type="button" class="secondary-small" @click="saveFile({ enabled: !f.enabled }, f)">{{ f.enabled ? 'Pause' : 'Resume' }}</button>
            <button type="button" class="link-danger" @click="removeFile(f)">Remove</button>
          </div>
        </div>
      </div>
      <p v-else class="muted">No live files for this library yet.</p>

      <div class="file-form">
        <h3>{{ form.id ? 'Edit live file' : 'Add a live file' }}</h3>
        <div class="row">
          <input v-model="form.path" type="text" placeholder="/config/metadata/movies_johnWick.yml" class="grow" />
          <button type="button" class="secondary" @click="showPicker = true">Browse…</button>
        </div>
        <div class="settings-grid">
          <label><span>Name (optional)</span><input v-model="form.name" type="text" /></label>
          <label>
            <span>What to do with the posters</span>
            <select v-model="form.mode">
              <option v-for="(l, m) in MODE_LABELS" :key="m" :value="m">{{ l }}</option>
            </select>
          </label>
          <label v-if="needsPreset(form.mode)">
            <span>Preset</span>
            <select v-model="form.preset_id">
              <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </label>
          <label>
            <span>Check</span>
            <select v-model.number="form.interval_hours">
              <option v-for="i in INTERVALS" :key="i.v" :value="i.v">{{ i.l }}</option>
            </select>
          </label>
        </div>
        <p class="hint">{{ MODE_HELP[form.mode] }}</p>
        <div class="row">
          <button type="button" class="primary" :disabled="!form.path.trim() || savingFile || (needsPreset(form.mode) && !form.preset_id)" @click="saveFile()">
            {{ form.id ? 'Save' : 'Add and import' }}
          </button>
          <button v-if="form.id" type="button" class="secondary" @click="resetForm">Cancel</button>
          <span v-if="filesError" class="bad">{{ filesError }}</span>
        </div>
      </div>
      <ServerFilePicker v-if="showPicker" :start="form.path" @pick="p => { form.path = p; showPicker = false }" @close="showPicker = false" />
    </div>

    <!-- Imported posters -->
    <div v-if="tab === 'stored'" class="section">
      <p class="hint">
        Titles in this library group with an imported poster. Renders use it instead of TMDb's posters, and Overlay only
        draws on it. Remove one to go back to TMDb's posters on the next render.
      </p>
      <input v-if="stored.length > 10" v-model="storedFilter" type="search" placeholder="Filter by title" class="filter" />
      <div v-if="shownStored.length" class="stored-grid">
        <div v-for="s in shownStored" :key="s.item_key + ':' + s.season_index" class="stored-card">
          <img :src="`${apiBase}/api/poster-import/image?url=${encodeURIComponent(s.url)}`" loading="lazy" alt="" />
          <div class="stored-meta">
            <strong>{{ s.title }}</strong>
            <span v-if="s.season_index !== null" class="muted">{{ s.season_index === 0 ? 'Specials' : `Season ${s.season_index}` }}</span>
            <button type="button" class="link-danger" @click="removeStored(s)">Remove</button>
          </div>
        </div>
      </div>
      <p v-else class="muted">No imported posters for this library group yet.</p>
    </div>
  </div>
</template>

<style scoped>
.poster-import-view { display: flex; flex-direction: column; gap: 12px; }
.page-header h2 { margin: 0; font-size: 20px; font-weight: 700; color: #eef2ff; }
.section-note, .hint { font-size: 12px; color: #6b7a99; line-height: 1.5; margin: 0; }
.section-note code { font-size: 11px; }
.section {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.section h3 { margin: 0; font-size: 15px; font-weight: 600; color: #eef2ff; }
.tabs { display: flex; gap: 6px; flex-wrap: wrap; }
.tabs button {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #a8b3cf;
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 13px;
  cursor: pointer;
}
.tabs button.active { border-color: var(--accent, #3dd6b7); color: #eef2ff; }
.count { margin-left: 6px; font-size: 11px; color: var(--accent, #3dd6b7); }
.row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.grow { flex: 1; min-width: 200px; }
textarea, input[type='text'], input[type='search'], select {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  color: #eef2ff;
  padding: 8px 10px;
  font-size: 13px;
}
textarea { font-family: ui-monospace, Consolas, monospace; font-size: 12px; resize: vertical; width: 100%; box-sizing: border-box; }
select.small { padding: 4px 8px; font-size: 12px; }
.settings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.settings-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #a8b3cf; }
button.primary, button.secondary, button.secondary-small {
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  padding: 8px 14px;
  border: 1px solid rgba(255, 255, 255, 0.12);
}
button.primary { background: var(--accent, #3dd6b7); color: #0b1020; border-color: transparent; font-weight: 600; }
button.secondary, button.secondary-small { background: rgba(255, 255, 255, 0.06); color: #eef2ff; }
button.secondary-small { padding: 5px 10px; font-size: 12px; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.link-danger { background: none; border: none; color: #ff8a8a; cursor: pointer; font-size: 12px; padding: 4px; }
.summary { font-size: 13px; color: #a8b3cf; }
.ok { color: var(--accent, #3dd6b7); }
.bad { color: #ff8a8a; font-size: 13px; }
.warn { color: #f5c26b; font-size: 13px; }
.muted { color: #6b7a99; }
.small-text { font-size: 12px; }
.table-wrap { overflow-x: auto; max-height: 480px; overflow-y: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; color: #6b7a99; font-weight: 500; padding: 6px 8px; position: sticky; top: 0; background: #141a2e; }
td { padding: 6px 8px; border-top: 1px solid rgba(255, 255, 255, 0.05); color: #d6ddf0; vertical-align: top; }
td a { color: #d6ddf0; }
tr.not_found td, tr.ambiguous td { opacity: 0.6; }
.pill { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: rgba(255, 255, 255, 0.08); white-space: nowrap; }
.pill.matched { background: rgba(61, 214, 183, 0.15); color: var(--accent, #3dd6b7); }
.pill.collection { background: rgba(120, 160, 255, 0.15); color: #9fb8ff; }
.pill.not_found, .pill.ambiguous, .pill.paused { background: rgba(245, 194, 107, 0.15); color: #f5c26b; }
.job-head { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; font-size: 13px; color: #a8b3cf; }
.bar { height: 6px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; overflow: hidden; }
.fill { height: 100%; background: var(--accent, #3dd6b7); transition: width 0.3s; }
.results { margin: 8px 0 0; padding-left: 18px; font-size: 12px; color: #a8b3cf; max-height: 240px; overflow-y: auto; }
.results li.error { color: #ff8a8a; }
.results li.partial { color: #f5c26b; }
details summary { cursor: pointer; font-size: 12px; color: #a8b3cf; }
.files { display: flex; flex-direction: column; gap: 10px; }
.file-card {
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  word-break: break-all;
}
.file-head { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; font-size: 13px; }
.file-form { display: flex; flex-direction: column; gap: 10px; border-top: 1px solid rgba(255, 255, 255, 0.06); padding-top: 12px; }
.filter { max-width: 280px; }
.stored-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 12px; }
.stored-card { display: flex; flex-direction: column; gap: 6px; font-size: 12px; }
.stored-card img { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 6px; background: rgba(255, 255, 255, 0.04); }
.stored-meta { display: flex; flex-direction: column; gap: 2px; color: #d6ddf0; }
.stored-meta .link-danger { align-self: flex-start; padding: 0; }
</style>
