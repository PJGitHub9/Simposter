<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { copyToClipboard } from '@/services/clipboard'
import { usePagedItems } from '@/composables/usePagedItems'
import { useNotification } from '@/composables/useNotification'
import { openApiEditor } from '@/composables/useApiEditorLauncher'
import { useSettingsStore } from '@/stores/settings'

type Cfg = {
  enabled: boolean
  key: string
  defaultMoviePreset: string
  defaultTvPreset: string
  waitSeconds: number
  retentionDays: number
  movieGroup: string
  tvGroup: string
}
type Status = {
  enabled: boolean
  key_set: boolean
  default_movie_preset: string
  default_tv_preset: string
  default_preset_missing: boolean
  url_templates: { movie: string; tv: string }
  url_templates_with_key?: { movie: string; tv: string }
  counts: { pinned: number; rendered: number }
}
type Item = {
  id: number
  type: 'movie' | 'tv'
  tmdb_id: number
  season: number | null
  preset: string
  group?: string
  source: 'library' | 'rendered' | 'pinned'
  title: string
  hits: number
  created_at: string | null
  last_served_at: string | null
  thumb_url: string
}
type SearchResult = { tmdb_id: number; title: string; year?: string | number; poster_path?: string | null }

const apiBase = getApiBase()
const store = useSettingsStore()
const { success, error: showError, info } = useNotification()

const cfg = ref<Cfg>({ enabled: false, key: '', defaultMoviePreset: '', defaultTvPreset: '', waitSeconds: 10, retentionDays: 90, movieGroup: '', tvGroup: '' })

// Library groups per media type, for the default-group pickers and tile labels.
const movieGroups = computed(() => store.libraryGroups.value.filter(g => g.mediaType === 'movie'))
const tvGroups = computed(() => store.libraryGroups.value.filter(g => g.mediaType === 'tv'))
const groupName = (id?: string) => (id ? store.libraryGroups.value.find(g => g.id === id)?.name || id : '')
const saved = ref<Cfg | null>(null)
const status = ref<Status | null>(null)
const presets = ref<{ id: string; name?: string }[]>([])
const newKey = ref('') // shown once in full after Generate
const saving = ref(false)
const loadFailed = ref(false)

const dirty = computed(() => !!saved.value && JSON.stringify(saved.value) !== JSON.stringify(cfg.value))
const keyEmpty = computed(() => !cfg.value.key)

async function loadSettings() {
  try {
    const res = await fetch(`${apiBase}/api/poster-api/settings`)
    if (!res.ok) throw new Error(String(res.status))
    const data = await res.json()
    cfg.value = { ...cfg.value, ...data }
    saved.value = { ...cfg.value }
    loadFailed.value = false
  } catch {
    loadFailed.value = true
    showError('Failed to load Poster API settings')
  }
}

async function loadStatus() {
  try {
    const res = await fetch(`${apiBase}/api/poster-api/status`)
    if (res.ok) status.value = await res.json()
  } catch { /* status is informational */ }
}

async function loadPresets() {
  try {
    const res = await fetch(`${apiBase}/api/presets`)
    if (!res.ok) return
    const data = await res.json()
    presets.value = data?.uniformlogo?.presets || []
  } catch { /* leave empty */ }
}

async function putSettings(next: Cfg, keyOnly = false): Promise<boolean> {
  saving.value = true
  try {
    const res = await fetch(`${apiBase}/api/poster-api/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(next)
    })
    if (!res.ok) {
      let msg = `Save failed (${res.status})`
      try { const j = await res.json(); if (j?.detail) msg = String(j.detail) } catch { /* ignore */ }
      showError(msg)
      return false
    }
    const data = await res.json()
    saved.value = { ...saved.value, ...data } as Cfg
    // keyOnly: leave the user's other unsaved edits in cfg (and thus their dirty state) intact.
    cfg.value = keyOnly ? { ...cfg.value, key: data.key } : { ...saved.value }
    // Keep the shared store in step so a later full Settings save doesn't send a stale copy.
    store.posterApi.value = { ...saved.value }
    await loadStatus()
    return true
  } catch {
    showError('Save failed')
    return false
  } finally {
    saving.value = false
  }
}

async function save() {
  if (await putSettings(cfg.value)) success('Poster API settings saved')
}

async function generateKey() {
  if (loadFailed.value || !saved.value) return
  try {
    const res = await fetch(`${apiBase}/api/poster-api/generate-key`, { method: 'POST' })
    if (!res.ok) throw new Error(String(res.status))
    const { key } = await res.json()
    if (await putSettings({ ...saved.value, key }, true)) {
      newKey.value = key
      success('New key saved. Copy it now - it is masked after you leave this page.')
    }
  } catch {
    showError('Failed to generate key')
  }
}

async function copyNewKey() {
  if (await copyToClipboard(newKey.value)) success('Key copied')
  else showError('Copy failed')
}

async function clearKey() {
  if (loadFailed.value || !saved.value) return
  if (!window.confirm('Remove the API key? Anyone who can reach Simposter will be able to use this API without one.')) return
  if (await putSettings({ ...saved.value, key: '' }, true)) {
    newKey.value = ''
    success('Key cleared')
  }
}

async function copyTemplate(text: string) {
  if (await copyToClipboard(text)) success('Copied')
  else showError('Copy failed')
}

// Displayed with the key hidden (YOUR_KEY); Copy copies the same URL with the
// real key filled in, so it works as pasted into another app.
const templates = computed(() => {
  const t = status.value?.url_templates
  const k = status.value?.url_templates_with_key || t
  if (!t || !k) return []
  return [
    { label: 'Movies', value: t.movie, copy: k.movie },
    { label: 'TV shows', value: t.tv, copy: k.tv }
  ]
})

// ---- posters grid ----
const items = ref<Item[]>([])
const total = ref(0)
const search = ref('')
const typeFilter = ref<'' | 'movie' | 'tv'>('')
const sourceFilter = ref<'' | 'pinned' | 'rendered'>('')
const listLoading = ref(false)
const failedThumbs = ref<Set<number>>(new Set())
const { page, totalPages, pagedItems, nextPage, prevPage, resetPage } = usePagedItems(items, 24)

async function loadItems() {
  listLoading.value = true
  try {
    const q = new URLSearchParams({ limit: '200', offset: '0' })
    if (search.value.trim()) q.set('search', search.value.trim())
    if (typeFilter.value) q.set('type', typeFilter.value)
    if (sourceFilter.value) q.set('source', sourceFilter.value)
    const res = await fetch(`${apiBase}/api/poster-api/items?${q}`)
    if (!res.ok) throw new Error(String(res.status))
    const data = await res.json()
    items.value = data.items || []
    total.value = data.total ?? items.value.length
    failedThumbs.value = new Set()
  } catch {
    showError('Failed to load posters')
  } finally {
    listLoading.value = false
  }
}

// ---- Recent requests (every call to the public poster URLs) ----
type RequestRow = {
  id: number
  requested_at: string | null
  type: 'movie' | 'tv' | null
  tmdb_id: number | null
  season: number | null
  preset: string
  group: string
  result: string
  title: string
  duration_ms: number | null
}
const REQUEST_RESULTS: { value: string; label: string; hint: string }[] = [
  { value: 'library', label: 'Library', hint: 'Served the poster already in your library' },
  { value: 'pinned', label: 'Pinned', hint: 'Served a poster you pinned' },
  { value: 'rendered', label: 'Cached render', hint: 'Served a poster the API rendered earlier' },
  { value: 'generated', label: 'Generated', hint: 'Rendered for this request' },
  { value: 'redirect', label: 'Sent to TMDb', hint: 'The render took too long; sent to the stock TMDb poster while it finishes' },
  { value: 'not_found', label: 'Not found', hint: 'No such title, no poster art, or an unknown preset/group' },
  { value: 'bad_key', label: 'Bad key', hint: 'Missing or wrong API key' },
]
const resultLabel = (r: string) => REQUEST_RESULTS.find(x => x.value === r)?.label || r
const resultHint = (r: string) => REQUEST_RESULTS.find(x => x.value === r)?.hint || ''
const REQ_PAGE = 50
const requests = ref<RequestRow[]>([])
const reqTotal = ref(0)
const reqCounts = ref<Record<string, number>>({})
const reqResult = ref('')
const reqSearch = ref('')
const reqOffset = ref(0)
const reqLoading = ref(false)

async function loadRequests() {
  reqLoading.value = true
  try {
    const q = new URLSearchParams({ limit: String(REQ_PAGE), offset: String(reqOffset.value) })
    if (reqResult.value) q.set('result', reqResult.value)
    if (reqSearch.value.trim()) q.set('search', reqSearch.value.trim())
    const res = await fetch(`${apiBase}/api/poster-api/requests?${q}`)
    if (!res.ok) throw new Error(String(res.status))
    const data = await res.json()
    requests.value = data.items || []
    reqTotal.value = data.total ?? 0
    reqCounts.value = data.counts || {}
  } catch {
    showError('Failed to load the request history')
  } finally {
    reqLoading.value = false
  }
}

async function clearRequests() {
  if (!window.confirm('Clear the whole request history?')) return
  try {
    const res = await fetch(`${apiBase}/api/poster-api/requests`, { method: 'DELETE' })
    if (!res.ok) throw new Error(String(res.status))
    reqOffset.value = 0
    await loadRequests()
  } catch {
    showError('Failed to clear the request history')
  }
}

let reqSearchTimer: ReturnType<typeof setTimeout> | null = null
watch(reqResult, () => { reqOffset.value = 0; loadRequests() })
watch(reqSearch, () => {
  if (reqSearchTimer) clearTimeout(reqSearchTimer)
  reqSearchTimer = setTimeout(() => { reqOffset.value = 0; loadRequests() }, 300)
})
function reqPage(delta: number) {
  reqOffset.value = Math.max(0, reqOffset.value + delta * REQ_PAGE)
  loadRequests()
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch([typeFilter, sourceFilter], () => { resetPage(); loadItems() })
watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { resetPage(); loadItems() }, 300)
})

function thumbSrc(it: Item) {
  const u = it.thumb_url || ''
  const base = u.startsWith('http') || u.startsWith('data:') ? u : `${apiBase}${u}`
  return `${base}${base.includes('?') ? '&' : '?'}t=${encodeURIComponent(it.last_served_at || it.created_at || '')}`
}

function fmtTime(s: string | null) {
  if (!s) return 'never'
  const iso = /Z|[+-]\d\d:?\d\d$/.test(s) ? s : s.replace(' ', 'T') + 'Z'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? s : d.toLocaleString()
}

const sourceLabel = (s: string) => (s === 'library' ? 'Library' : s === 'pinned' ? 'Pinned' : 'Rendered')

function target(it: Item) {
  return { type: it.type, tmdb_id: it.tmdb_id, season: it.season, preset: it.preset, group: it.group || '' }
}

async function regenerate(it: Item) {
  try {
    const res = await fetch(`${apiBase}/api/poster-api/regenerate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(target(it))
    })
    if (!res.ok) throw new Error(String(res.status))
    info('Regenerating…')
    setTimeout(loadItems, 3000)
  } catch {
    showError('Regenerate failed')
  }
}

async function clearItem(it: Item) {
  if (!window.confirm(`Clear "${it.title || it.tmdb_id}"? The next request will fetch and render it again.`)) return
  try {
    const res = await fetch(`${apiBase}/api/poster-api/clear`, {
      // only this tile's source -- clearing a Rendered tile must not delete a pinned poster
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...target(it), source: it.source })
    })
    if (!res.ok) throw new Error(String(res.status))
    success('Cleared')
    await loadItems()
    loadStatus()
  } catch {
    showError('Clear failed')
  }
}

function editItem(it: Item) {
  openApiEditor({ tmdb_id: it.tmdb_id, mediaType: it.type, title: it.title || `TMDb ${it.tmdb_id}` })
}

// ---- multi-select (bulk regenerate / clear) ----
// Row ids are unique per tile (one id per media/tmdb/season/preset/source row).
const selected = ref<Set<number>>(new Set())
const bulkBusy = ref(false)
const selectedItems = computed(() => items.value.filter(it => selected.value.has(it.id)))
const selectedRendered = computed(() => selectedItems.value.filter(it => it.source === 'rendered'))
const allOnPageSelected = computed(() =>
  pagedItems.value.length > 0 && pagedItems.value.every(it => selected.value.has(it.id)))

function toggleSelect(it: Item) {
  const next = new Set(selected.value)
  if (next.has(it.id)) next.delete(it.id)
  else next.add(it.id)
  selected.value = next
}
function toggleSelectPage() {
  const next = new Set(selected.value)
  if (allOnPageSelected.value) pagedItems.value.forEach(it => next.delete(it.id))
  else pagedItems.value.forEach(it => next.add(it.id))
  selected.value = next
}
function selectAllLoaded() { selected.value = new Set(items.value.map(it => it.id)) }
function clearSelection() { selected.value = new Set() }
// Drop selections that disappeared after a reload or filter change.
watch(items, (list) => {
  const ids = new Set(list.map(it => it.id))
  const kept = [...selected.value].filter(id => ids.has(id))
  if (kept.length !== selected.value.size) selected.value = new Set(kept)
})

async function runBulk(action: 'regenerate' | 'clear') {
  const list = action === 'regenerate' ? selectedRendered.value : selectedItems.value
  if (!list.length) return
  if (action === 'clear' && !window.confirm(
    `Clear ${list.length} poster${list.length === 1 ? '' : 's'}? Pinned posters can't be regenerated; rendered ones are made again on the next request.`
  )) return
  bulkBusy.value = true
  try {
    const res = await fetch(`${apiBase}/api/poster-api/bulk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // each tile's own source, same rule as the single Clear button
      body: JSON.stringify({ action, items: list.map(it => ({ ...target(it), source: it.source })) })
    })
    if (!res.ok) throw new Error(String(res.status))
    const data = await res.json()
    if (action === 'regenerate') {
      info(`Regenerating ${data.done} poster${data.done === 1 ? '' : 's'}…`)
      setTimeout(loadItems, 3000)
    } else {
      success(`Cleared ${data.done} poster${data.done === 1 ? '' : 's'}`)
      clearSelection()
      await loadItems()
      loadStatus()
    }
  } catch {
    showError(action === 'regenerate' ? 'Bulk regenerate failed' : 'Bulk clear failed')
  } finally {
    bulkBusy.value = false
  }
}

// ---- add poster (TMDb search) ----
const addType = ref<'movie' | 'tv'>('movie')
const addQuery = ref('')
const addResults = ref<SearchResult[]>([])
const addLoading = ref(false)

async function runAddSearch() {
  const q = addQuery.value.trim()
  if (!q) { addResults.value = []; return }
  addLoading.value = true
  try {
    const res = await fetch(`${apiBase}/api/tmdb/search?q=${encodeURIComponent(q)}&type=${addType.value}`)
    if (!res.ok) throw new Error(String(res.status))
    addResults.value = await res.json()
  } catch {
    showError('TMDb search failed')
  } finally {
    addLoading.value = false
  }
}

function openResult(r: SearchResult) {
  openApiEditor({ tmdb_id: r.tmdb_id, mediaType: addType.value, title: r.title, year: r.year })
}

onMounted(async () => {
  await Promise.all([loadSettings(), loadStatus(), loadPresets(), loadItems(), loadRequests()])
})
</script>

<template>
  <div class="poster-api-view">
    <div class="view glass">
      <h2>🔌 Poster API</h2>
      <p class="muted">Serve posters rendered with your presets to any app by TMDb id.</p>

      <div v-if="loadFailed" class="warn">Could not load settings. Is the backend running?</div>

      <h3>Setup</h3>
      <div class="field row">
        <span v-if="cfg.enabled" class="hint">The Poster API is on. Turn it off in <router-link to="/settings?tab=media-servers">Settings → Media Servers</router-link>.</span>
        <span v-else class="warn">The Poster API is off. Turn it on in <router-link to="/settings?tab=media-servers">Settings → Media Servers</router-link>.</span>
      </div>

      <div class="field">
        <label>API key</label>
        <div class="row">
          <input class="text-input key-input" type="text" :value="newKey || cfg.key" readonly placeholder="No key set" />
          <button v-if="newKey" class="secondary" @click="copyNewKey">Copy</button>
          <button class="secondary" @click="generateKey" :disabled="saving || loadFailed || !saved">Generate</button>
          <button class="secondary" @click="clearKey" :disabled="saving || loadFailed || !saved || keyEmpty">Clear</button>
        </div>
        <div v-if="newKey" class="hint">Shown in full once. It is already stored and will be masked on reload.</div>
        <div v-if="keyEmpty" class="warn">Anyone who can reach Simposter can use your TMDb quota through this API — set a key.</div>
      </div>

      <div class="grid2">
        <div class="field">
          <label>Default movie preset</label>
          <select class="text-input" v-model="cfg.defaultMoviePreset">
            <option value="">simposter-main (default)</option>
            <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name || p.id }}</option>
          </select>
        </div>
        <div class="field">
          <label>Default TV preset</label>
          <select class="text-input" v-model="cfg.defaultTvPreset">
            <option value="">simposter-main (default)</option>
            <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name || p.id }}</option>
          </select>
        </div>
      </div>
      <div v-if="status?.default_preset_missing" class="warn">A default preset no longer exists. Requests without an explicit preset fall back to simposter-main (or the first preset if it's gone) until you pick another.</div>

      <div v-if="movieGroups.length > 1 || tvGroups.length > 1" class="grid2">
        <div class="field">
          <label>Movie library group</label>
          <select class="text-input" v-model="cfg.movieGroup">
            <option value="">Any library</option>
            <option v-for="g in movieGroups" :key="g.id" :value="g.id">{{ g.name || g.id }}</option>
          </select>
        </div>
        <div class="field">
          <label>TV library group</label>
          <select class="text-input" v-model="cfg.tvGroup">
            <option value="">Any library</option>
            <option v-for="g in tvGroups" :key="g.id" :value="g.id">{{ g.name || g.id }}</option>
          </select>
        </div>
      </div>
      <div v-if="movieGroups.length > 1 || tvGroups.length > 1" class="hint">
        Which library a request uses when it names none: the poster already in that library is served,
        and its file details (4K, HDR, audio) feed the overlay badges. Add <code>&amp;group=Name</code>
        to a URL to pick a group per request, for example one URL for 4K and one for regular.
      </div>

      <div class="field">
        <label>Wait seconds (2–30)</label>
        <input class="text-input num" type="number" min="2" max="30" v-model.number="cfg.waitSeconds" />
        <div class="hint">How long a request waits for a fresh render before redirecting to the TMDb poster.</div>
      </div>

      <div class="field">
        <label>URL templates</label>
        <div v-if="!templates.length" class="hint">Unavailable.</div>
        <div v-for="t in templates" :key="t.label" class="row tpl">
          <span class="tpl-label">{{ t.label }}</span>
          <code class="tpl-url">{{ t.value }}</code>
          <button class="secondary-small" @click="copyTemplate(t.copy)">Copy</button>
        </div>
        <div class="hint">
          {tmdb_id} is the TMDb id. For a season poster add <code>&amp;season=2</code>.
          <template v-if="status?.key_set"> Copy includes your API key, ready to paste into the other app.</template>
        </div>
      </div>

      <div class="row">
        <button class="primary" @click="save" :disabled="saving || !dirty">Save</button>
        <span v-if="dirty" class="hint">Unsaved changes</span>
      </div>
    </div>

    <div class="view glass">
      <div class="row between">
        <h3>Posters</h3>
        <span v-if="status" class="muted">{{ status.counts.rendered }} rendered · {{ status.counts.pinned }} pinned</span>
      </div>

      <div class="row wrap">
        <input class="text-input" v-model="search" placeholder="Search title or TMDb id" />
        <select class="text-input" v-model="typeFilter">
          <option value="">All types</option>
          <option value="movie">Movies</option>
          <option value="tv">TV</option>
        </select>
        <select class="text-input" v-model="sourceFilter">
          <option value="">All sources</option>
          <option value="pinned">Pinned</option>
          <option value="rendered">Rendered</option>
        </select>
      </div>

      <div v-if="items.length" class="row wrap bulk-bar">
        <label class="check">
          <input type="checkbox" :checked="allOnPageSelected" @change="toggleSelectPage" />
          Select page
        </label>
        <button v-if="items.length > pagedItems.length" class="secondary-small" @click="selectAllLoaded">Select all {{ items.length }}</button>
        <template v-if="selected.size">
          <span class="muted">{{ selected.size }} selected</span>
          <button class="secondary-small" :disabled="bulkBusy || !selectedRendered.length" :title="selectedRendered.length ? '' : 'Only rendered posters can be regenerated'" @click="runBulk('regenerate')">
            Regenerate{{ selectedRendered.length !== selected.size ? ` (${selectedRendered.length} rendered)` : '' }}
          </button>
          <button class="secondary-small danger" :disabled="bulkBusy" @click="runBulk('clear')">Clear</button>
          <button class="secondary-small" :disabled="bulkBusy" @click="clearSelection">Deselect</button>
        </template>
      </div>

      <div v-if="listLoading && !items.length" class="muted pad">Loading…</div>
      <div v-else-if="!items.length" class="muted pad">No posters yet. Request one through the API or add one below.</div>
      <div v-else class="poster-grid">
        <div v-for="it in pagedItems" :key="it.id" class="card" :class="{ selected: selected.has(it.id) }">
          <div class="thumb" @click="toggleSelect(it)">
            <input type="checkbox" class="pick" :checked="selected.has(it.id)" @click.stop @change="toggleSelect(it)" :aria-label="`Select ${it.title || it.tmdb_id}`" />
            <img v-if="!failedThumbs.has(it.id)" :src="thumbSrc(it)" :alt="it.title" loading="lazy"
                 @error="failedThumbs = new Set(failedThumbs).add(it.id)" />
            <div v-else class="thumb-missing">No preview</div>
            <span class="badge" :class="'b-' + it.source">{{ sourceLabel(it.source) }}</span>
          </div>
          <div class="meta">
            <div class="title" :title="it.title">{{ it.title || 'TMDb ' + it.tmdb_id }}</div>
            <div class="sub">
              {{ it.type === 'tv' ? 'TV' : 'Movie' }}<template v-if="it.season !== null && it.season !== undefined"> · Season {{ it.season }}</template>
              · {{ it.preset || 'default' }}<template v-if="it.group"> · {{ groupName(it.group) }}</template>
            </div>
            <div class="sub">{{ it.hits }} hits · {{ fmtTime(it.last_served_at) }}</div>
          </div>
          <div class="actions">
            <button class="secondary-small" @click="regenerate(it)" :disabled="it.source !== 'rendered'" :title="it.source !== 'rendered' ? 'Only rendered posters can be regenerated' : ''">Regenerate</button>
            <button class="secondary-small" @click="clearItem(it)">Clear</button>
            <button class="secondary-small" @click="editItem(it)">Open in editor</button>
          </div>
        </div>
      </div>

      <div v-if="items.length > 24" class="pager row">
        <button class="secondary-small" @click="prevPage" :disabled="page <= 1">Prev</button>
        <span>Page {{ page }} / {{ totalPages }}</span>
        <button class="secondary-small" @click="nextPage" :disabled="page >= totalPages">Next</button>
      </div>
      <div v-if="total > items.length" class="hint">Showing the first {{ items.length }} of {{ total }}. Narrow the search to see others.</div>
    </div>

    <div class="view glass">
      <div class="row between">
        <h3>Recent requests</h3>
        <div class="row">
          <button class="secondary-small" @click="loadRequests" :disabled="reqLoading">{{ reqLoading ? 'Loading…' : 'Refresh' }}</button>
          <button class="secondary-small" @click="clearRequests" :disabled="!reqTotal && !Object.keys(reqCounts).length">Clear</button>
        </div>
      </div>
      <p class="muted">Every call to the poster URLs and what Simposter answered with. The newest 2000 are kept.</p>
      <div class="row wrap req-counts">
        <span v-for="r in REQUEST_RESULTS" :key="r.value" class="req-count" :title="r.hint">
          <span class="req-badge" :class="'r-' + r.value">{{ r.label }}</span> {{ reqCounts[r.value] || 0 }}
        </span>
      </div>
      <div class="row wrap">
        <input class="text-input" v-model="reqSearch" placeholder="Search title or TMDb id" />
        <select class="text-input" v-model="reqResult">
          <option value="">All results</option>
          <option v-for="r in REQUEST_RESULTS" :key="r.value" :value="r.value">{{ r.label }}</option>
        </select>
      </div>
      <div v-if="!requests.length" class="hint">{{ reqLoading ? 'Loading…' : 'No requests yet.' }}</div>
      <div v-else class="req-table-wrap">
        <table class="req-table">
          <thead>
            <tr><th>Time</th><th>Title</th><th>Request</th><th>Result</th><th class="num-col">Took</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in requests" :key="r.id">
              <td class="nowrap">{{ fmtTime(r.requested_at) }}</td>
              <td>
                {{ r.title || (r.tmdb_id ? 'TMDb ' + r.tmdb_id : '—') }}
                <span v-if="r.title && r.tmdb_id" class="muted"> · TMDb {{ r.tmdb_id }}</span>
              </td>
              <td class="muted">
                {{ r.type === 'tv' ? 'TV' : r.type === 'movie' ? 'Movie' : '?' }}<template v-if="r.season !== null && r.season !== undefined"> · Season {{ r.season }}</template>
                <template v-if="r.preset"> · {{ r.preset }}</template>
                <template v-if="r.group"> · {{ groupName(r.group) }}</template>
              </td>
              <td><span class="req-badge" :class="'r-' + r.result" :title="resultHint(r.result)">{{ resultLabel(r.result) }}</span></td>
              <td class="num-col muted">{{ r.duration_ms != null ? (r.duration_ms >= 1000 ? (r.duration_ms / 1000).toFixed(1) + ' s' : r.duration_ms + ' ms') : '' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="reqTotal > REQ_PAGE" class="row">
        <button class="secondary-small" @click="reqPage(-1)" :disabled="reqOffset === 0">Newer</button>
        <span class="muted">{{ reqOffset + 1 }}–{{ Math.min(reqOffset + REQ_PAGE, reqTotal) }} of {{ reqTotal }}</span>
        <button class="secondary-small" @click="reqPage(1)" :disabled="reqOffset + REQ_PAGE >= reqTotal">Older</button>
      </div>
    </div>

    <div class="view glass">
      <h3>Add poster</h3>
      <div class="row wrap">
        <select class="text-input" v-model="addType" @change="runAddSearch">
          <option value="movie">Movie</option>
          <option value="tv">TV</option>
        </select>
        <input class="text-input grow" v-model="addQuery" placeholder="Search TMDb" @keyup.enter="runAddSearch" />
        <button class="primary" @click="runAddSearch" :disabled="addLoading">{{ addLoading ? 'Searching…' : 'Search' }}</button>
      </div>
      <ul v-if="addResults.length" class="results">
        <li v-for="r in addResults" :key="r.tmdb_id" class="row between">
          <span>{{ r.title }} <span class="muted">{{ r.year }} · TMDb {{ r.tmdb_id }}</span></span>
          <button class="secondary-small" @click="openResult(r)">Open in editor</button>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.poster-api-view { display: flex; flex-direction: column; gap: 16px; }
.view { padding: 24px; display: flex; flex-direction: column; gap: 14px; }
h2, h3 { margin: 0; }
.muted, .hint { color: #a8b3cf; font-size: 13px; }
.warn { background: rgba(255, 180, 100, 0.12); border: 1px solid rgba(255, 180, 100, 0.4); color: #ffcf99; padding: 8px 12px; border-radius: 8px; font-size: 13px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field > label { font-size: 13px; font-weight: 600; }
.row { display: flex; align-items: center; gap: 8px; }
.row.wrap { flex-wrap: wrap; }
.row.between { justify-content: space-between; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.check { display: flex; align-items: center; gap: 8px; }
.text-input { padding: 6px 10px; font-size: 13px; border-radius: 7px; border: 1px solid rgba(255, 255, 255, 0.12); background: rgba(255, 255, 255, 0.05); color: inherit; }
.key-input { flex: 1; font-family: monospace; }
.num { width: 100px; }
.grow { flex: 1; min-width: 160px; }
.tpl-label { width: 90px; font-size: 12px; color: #a8b3cf; flex-shrink: 0; }
.tpl-url { flex: 1; overflow-x: auto; white-space: nowrap; font-size: 12px; padding: 4px 8px; background: rgba(0, 0, 0, 0.25); border-radius: 6px; }
.pad { padding: 16px 0; }
.poster-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 14px; }
.card { display: flex; flex-direction: column; gap: 8px; padding: 8px; border-radius: 10px; background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); }
.thumb { position: relative; aspect-ratio: 2 / 3; background: rgba(0, 0, 0, 0.3); border-radius: 8px; overflow: hidden; }
.thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.thumb-missing { display: flex; align-items: center; justify-content: center; height: 100%; color: #a8b3cf; font-size: 12px; }
.thumb { cursor: pointer; }
.pick { position: absolute; top: 6px; right: 6px; z-index: 1; width: 16px; height: 16px; cursor: pointer; accent-color: var(--accent, #3dd6b7); }
.card.selected { border-color: var(--accent, #3dd6b7); box-shadow: 0 0 0 1px var(--accent, #3dd6b7) inset; }
.bulk-bar { gap: 10px; padding: 6px 0; }
button.secondary-small.danger:hover:not(:disabled) { border-color: rgba(255, 120, 120, 0.6); color: #ffb3b3; }
.badge { position: absolute; top: 6px; left: 6px; font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 999px; background: rgba(0, 0, 0, 0.65); }
.b-pinned { color: #ffd479; }
.b-rendered { color: #3dd6b7; }
.b-library { color: #8fb4ff; }
.req-counts { margin: 4px 0 10px; gap: 14px; }
.req-count { font-size: 13px; }
.req-badge { display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px; background: rgba(255, 255, 255, 0.07); }
.r-library { color: #8fb4ff; }
.r-pinned { color: #ffd479; }
.r-rendered { color: #3dd6b7; }
.r-generated { color: #b48cff; }
.r-redirect { color: #ffb36b; }
.r-not_found, .r-bad_key { color: #ff7b7b; }
.req-table-wrap { overflow-x: auto; margin-top: 10px; }
.req-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.req-table th { text-align: left; font-weight: 600; color: var(--text-muted); padding: 6px 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); }
.req-table td { padding: 6px 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); vertical-align: top; }
.req-table .num-col { text-align: right; white-space: nowrap; }
.req-table .nowrap { white-space: nowrap; }
.meta .title { font-weight: 600; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.meta .sub { font-size: 12px; color: #a8b3cf; }
.actions { display: flex; flex-wrap: wrap; gap: 6px; }
/* Same button styles as Media Mirror / Settings (primary, secondary, secondary-small). */
button.primary { padding: 7px 16px; font-size: 13px; font-weight: 600; border-radius: 7px; border: none; background: var(--accent, #3dd6b7); color: #0b1220; cursor: pointer; transition: opacity 0.15s; }
button.primary:hover:not(:disabled) { opacity: 0.9; }
button.primary:disabled { opacity: 0.5; cursor: default; }
button.secondary { padding: 7px 16px; font-size: 13px; border-radius: 7px; border: 1px solid rgba(255, 255, 255, 0.15); background: rgba(255, 255, 255, 0.05); color: #c9d1e0; cursor: pointer; transition: all 0.15s; }
button.secondary:hover:not(:disabled) { background: rgba(255, 255, 255, 0.09); border-color: rgba(61, 214, 183, 0.35); color: #eef2ff; }
button.secondary:disabled { opacity: 0.5; cursor: default; }
button.secondary-small { padding: 4px 10px; font-size: 12px; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.15); background: rgba(255, 255, 255, 0.05); color: #c9d1e0; cursor: pointer; transition: all 0.15s; white-space: nowrap; }
button.secondary-small:hover:not(:disabled) { background: rgba(255, 255, 255, 0.09); border-color: rgba(61, 214, 183, 0.35); color: #eef2ff; }
button.secondary-small:disabled { opacity: 0.5; cursor: default; }
:root[data-theme='light'] button.secondary, :root[data-theme='light'] button.secondary-small { border-color: var(--border); background: rgba(0, 0, 0, 0.03); color: #1e293b; }
.pager { justify-content: center; }
.results { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.results li { padding: 6px 8px; border-radius: 8px; background: rgba(255, 255, 255, 0.04); }
@media (max-width: 700px) { .grid2 { grid-template-columns: 1fr; } }
</style>
