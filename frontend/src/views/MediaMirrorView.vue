<script setup lang="ts">
import { ref, computed, onMounted, watch, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore } from '@/stores/settings'
import { mediaServerLabel } from '@/services/mediaServerLabel'
import { compareTitles } from '@/services/sortTitle'

type MirrorMappingEntry = {
  tmdb_id: number | string | null
  source_rating_key: string | null
  title: string | null
  year: number | string | null
  targets: Record<string, string | null>
}

type MirrorGroup = {
  id: string
  name: string
  members: { serverId: string; libraryId: string; libraryName?: string }[]
  mirror?: {
    enabled?: boolean
    sourceServerId?: string | null
    targetServerIds?: string[]
    assetTypes?: string[]
    scheduleEnabled?: boolean
    scheduleCron?: string | null
    lastRunAt?: string | null
    lastRunStats?: {
      checked?: number
      updated?: number
      skipped?: number
      unchanged?: number
      unmapped?: number
      failed?: number
      unmappedSample?: string[]
    } | null
    // Movie-group-only (Quirk #123's follow-up, added right after the
    // cross-server collection-title-matching fix -- see
    // _dedupe_collections_by_title() in database.py) -- reuses this SAME
    // mirror config's sourceServerId/targetServerIds rather than needing its
    // own independent set, but gets its OWN asset-type selection
    // (collectionAssetTypes) -- a user wanting to mirror collections only,
    // with no movie asset types checked, previously had no way to do that.
    mirrorCollections?: boolean
    collectionAssetTypes?: string[]
    lastRunCollectionStats?: {
      checked?: number
      updated?: number
      skipped?: number
      unchanged?: number
      unmapped?: number
      failed?: number
      unmappedSample?: string[]
    } | null
  } | null
}

type RunStatus = {
  state?: 'idle' | 'running' | 'done' | 'error'
  total?: number
  processed?: number
  current?: string
  updated?: number
  skipped?: number
  unchanged?: number
  unmapped?: number
  failed?: number
  error?: string | null
}

const apiBase = getApiBase()
const route = useRoute()
const settings = useSettingsStore()

const isTV = computed(() => route.name === 'tv-media-mirror')
const mediaType = computed(() => (isTV.value ? 'tv' : 'movie'))
const libraryId = computed(() => (route.query.library as string) || '')
// Phase 8a -- see App.vue's resolveLibraryTarget(). Absent for a Plex tab
// (the backend already defaults to "plex-1"), explicitly set for a
// Jellyfin/Emby-only group tab.
const serverId = computed(() => (route.query.server as string) || 'plex-1')

const loading = ref(false)
const group = ref<MirrorGroup | null>(null)

const enabled = ref(false)
const sourceServerId = ref<string>('')
const targetServerIds = ref<Set<string>>(new Set())
const assetTypes = ref<Set<string>>(new Set(['poster']))
const saving = ref(false)
const saveMessage = ref('')

// Scheduled sync (Quirk #123's follow-up) -- runs a full sync on a cron,
// same shape as Settings -> Cleanup's own scheduled-cleanup UI (checkbox +
// cron text input + "Next Run"). Rides along on the SAME config save as
// everything else above (mirror.scheduleEnabled/scheduleCron are just two
// more fields on the one config object POST /config already saves as a
// unit) -- no separate save action needed, unlike Cleanup's page-wide Save
// Changes button, since Media Mirror's config has always auto-saved on its
// own "Save Configuration" click.
const scheduleEnabled = ref(false)
const scheduleCron = ref('0 3 * * 0')
const nextRun = ref<string | null>(null)

const mapping = ref<MirrorMappingEntry[]>([])
const mappingLoading = ref(false)

// Collections mirroring (Quirk #123's follow-up) -- movie-group-only, since
// Collections themselves are always resolved via the owning "movie" Library
// Group (api_collections() never gives them their own media_type). Reuses
// this same group's source/target/asset-type config above; its own mapping
// is a SEPARATE fetch (a different mapping FUNCTION server-side, matching
// by normalized title instead of tmdb_id) so it's tracked with its own
// ref/loading state rather than sharing `mapping`.
const mirrorCollections = ref(false)
const collectionAssetTypes = ref<Set<string>>(new Set(['poster']))
const collectionMapping = ref<MirrorMappingEntry[]>([])
const collectionMappingLoading = ref(false)

const runStatus = ref<RunStatus>({ state: 'idle' })
let pollHandle: ReturnType<typeof setInterval> | null = null
// Continuous polling (started on mount, only stopped on unmount) means
// `runStatus` is always live/trustworthy -- no need for a session-scoped
// gate to hide a stale completed-with-error status, since the very next
// poll after mount already reflects reality. `previousRunState` lets the
// poller detect a running->done transition (to refresh the group/mapping)
// without ever needing to stop and restart the interval around a run.
const starting = ref(false)
let previousRunState: RunStatus['state'] | undefined

// Every DISTINCT server this library's group links, labeled via the same
// shared helper the rest of the app already uses (Quirk #79) so a custom
// server name is honored here too. Deduped by serverId, not a plain map --
// a group's own picker UI enforces at most one member per server type
// (LibraryGroupCard.vue's Plex row only ever shows a single chip), but a
// group that already has a duplicate from before that guard existed would
// otherwise render two <option>s sharing the exact same value here, which
// is genuinely broken (v-model can't tell them apart) rather than just
// confusing to look at -- defensive regardless of whether the underlying
// data has been cleaned up yet.
const memberOptions = computed(() => {
  if (!group.value) return []
  const seen = new Set<string>()
  const options: { id: string; label: string }[] = []
  for (const m of group.value.members) {
    if (seen.has(m.serverId)) continue
    seen.add(m.serverId)
    options.push({ id: m.serverId, label: mediaServerLabel(m.serverId, settings.mediaServers.value) })
  }
  return options
})

const targetOptions = computed(() => memberOptions.value.filter(o => o.id !== sourceServerId.value))

// A group needs at least 2 linked members for mirroring to mean anything --
// matches the "only show a control once there's an actual choice" convention
// already established for the merge/prefer dropdowns (Quirk #85/#120).
const hasEnoughMembers = computed(() => (group.value?.members.length || 0) > 1)

const ASSET_TYPE_LABELS: Record<string, string> = {
  poster: 'Posters',
  logo: 'Logos',
  backdrop: 'Backdrops',
  square_art: 'Square Art',
}

// Square Art has no Jellyfin/Emby equivalent at all -- JellyfinClient can't
// download it from a non-Plex source (Quirk #59) and can't upload it to a
// non-Plex target (raises NotImplementedError, harmlessly skipped per item
// by the sync engine -- Quirk #123). It only ever does anything useful when
// BOTH the source and at least one selected target are Plex, matching the
// same "Square art only available in Plex" rule this app already applies
// to the Logos/Backdrops/Square Art library tabs (Quirk #92).
const isPlexId = (id: string) => id.startsWith('plex')
const squareArtAvailable = computed(() =>
  isPlexId(sourceServerId.value) && Array.from(targetServerIds.value).some(isPlexId)
)
watch(squareArtAvailable, (available) => {
  if (available) return
  if (assetTypes.value.has('square_art')) {
    const next = new Set(assetTypes.value)
    next.delete('square_art')
    assetTypes.value = next
  }
  if (collectionAssetTypes.value.has('square_art')) {
    const next = new Set(collectionAssetTypes.value)
    next.delete('square_art')
    collectionAssetTypes.value = next
  }
})

function toggleTarget(id: string) {
  const next = new Set(targetServerIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  targetServerIds.value = next
}

function toggleAssetType(id: string) {
  if (id === 'square_art' && !squareArtAvailable.value) return
  const next = new Set(assetTypes.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  assetTypes.value = next
}

function toggleCollectionAssetType(id: string) {
  if (id === 'square_art' && !squareArtAvailable.value) return
  const next = new Set(collectionAssetTypes.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collectionAssetTypes.value = next
}

async function fetchGroup() {
  group.value = null
  if (!libraryId.value) return
  loading.value = true
  try {
    const res = await fetch(
      `${apiBase}/api/media-server/library-group?server_id=${encodeURIComponent(serverId.value)}&library_id=${encodeURIComponent(libraryId.value)}&media_type=${mediaType.value}`
    )
    if (res.ok) {
      const data = await res.json()
      group.value = data.group || null
      applyConfigFromGroup()
    }
  } catch {
    group.value = null
  } finally {
    loading.value = false
  }
  await fetchSchedule()
}

function applyConfigFromGroup() {
  const mirror = group.value?.mirror
  enabled.value = !!mirror?.enabled
  sourceServerId.value = mirror?.sourceServerId || group.value?.members?.[0]?.serverId || ''
  targetServerIds.value = new Set((mirror?.targetServerIds || []).filter(Boolean))
  // A saved EMPTY list is a real choice (collections-only mirroring) -- only
  // fall back to the 'poster' default when the field was never saved at all.
  // (Treating [] as "unset" re-ticked Posters after every save.)
  assetTypes.value = new Set(Array.isArray(mirror?.assetTypes) ? mirror.assetTypes : ['poster'])
  scheduleEnabled.value = !!mirror?.scheduleEnabled
  scheduleCron.value = mirror?.scheduleCron || '0 3 * * 0'
  mirrorCollections.value = !isTV.value && !!mirror?.mirrorCollections
  collectionAssetTypes.value = new Set(Array.isArray(mirror?.collectionAssetTypes) ? mirror.collectionAssetTypes : ['poster'])
}

async function fetchSchedule() {
  if (!libraryId.value) {
    nextRun.value = null
    return
  }
  try {
    const params = new URLSearchParams({
      server_id: serverId.value, library_id: libraryId.value, media_type: mediaType.value,
    })
    const res = await fetch(`${apiBase}/api/media-mirror/schedule?${params.toString()}`)
    if (res.ok) {
      const data = await res.json()
      nextRun.value = data.schedule?.next_run_time || null
    }
  } catch {
    nextRun.value = null
  }
}

// Switching the source server should drop it from the target list if it was
// somehow also checked there -- a server can't mirror to itself.
watch(sourceServerId, (val) => {
  if (targetServerIds.value.has(val)) {
    const next = new Set(targetServerIds.value)
    next.delete(val)
    targetServerIds.value = next
  }
})

async function saveConfig() {
  saving.value = true
  saveMessage.value = ''
  // A saved config invalidates whatever an earlier run's error was about --
  // don't leave a stale failure banner from before this save sitting there.
  if (runStatus.value.state !== 'running') {
    runStatus.value = { state: 'idle' }
    previousRunState = 'idle'
  }
  try {
    const res = await fetch(`${apiBase}/api/media-mirror/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        server_id: serverId.value,
        library_id: libraryId.value,
        media_type: mediaType.value,
        mirror: {
          enabled: enabled.value,
          sourceServerId: sourceServerId.value || null,
          targetServerIds: Array.from(targetServerIds.value),
          assetTypes: Array.from(assetTypes.value),
          scheduleEnabled: scheduleEnabled.value,
          scheduleCron: scheduleCron.value || null,
          mirrorCollections: !isTV.value && mirrorCollections.value,
          collectionAssetTypes: Array.from(collectionAssetTypes.value),
        },
      }),
    })
    if (res.ok) {
      const data = await res.json()
      group.value = data.group || group.value
      saveMessage.value = 'Saved.'
      await fetchMapping()
      await fetchCollectionMapping()
      await fetchSchedule()
    } else {
      saveMessage.value = 'Failed to save.'
    }
  } catch {
    saveMessage.value = 'Failed to save.'
  } finally {
    saving.value = false
    setTimeout(() => { saveMessage.value = '' }, 3000)
  }
}

async function fetchMapping() {
  if (!libraryId.value || !sourceServerId.value || targetServerIds.value.size === 0) {
    mapping.value = []
    return
  }
  mappingLoading.value = true
  try {
    const params = new URLSearchParams({
      server_id: serverId.value,
      library_id: libraryId.value,
      media_type: mediaType.value,
      source_server_id: sourceServerId.value,
      target_server_ids: Array.from(targetServerIds.value).join(','),
    })
    const res = await fetch(`${apiBase}/api/media-mirror/mapping?${params.toString()}`)
    if (res.ok) {
      const data = await res.json()
      mapping.value = data.mapping || []
    }
  } catch {
    mapping.value = []
  } finally {
    mappingLoading.value = false
  }
}

async function fetchCollectionMapping() {
  if (isTV.value || !mirrorCollections.value || !libraryId.value || !sourceServerId.value || targetServerIds.value.size === 0) {
    collectionMapping.value = []
    return
  }
  collectionMappingLoading.value = true
  try {
    const params = new URLSearchParams({
      server_id: serverId.value,
      library_id: libraryId.value,
      media_type: 'collection',
      source_server_id: sourceServerId.value,
      target_server_ids: Array.from(targetServerIds.value).join(','),
    })
    const res = await fetch(`${apiBase}/api/media-mirror/mapping?${params.toString()}`)
    if (res.ok) {
      const data = await res.json()
      collectionMapping.value = data.mapping || []
    }
  } catch {
    collectionMapping.value = []
  } finally {
    collectionMappingLoading.value = false
  }
}

const unmappedCount = computed(() => mapping.value.filter(m => !Object.values(m.targets || {}).some(v => v)).length)
const unmappedCollectionCount = computed(() => collectionMapping.value.filter(m => !Object.values(m.targets || {}).some(v => v)).length)

function rowHasAnyMatch(entry: MirrorMappingEntry): boolean {
  return Array.from(targetServerIds.value).some(id => !!(entry.targets && entry.targets[id]))
}

// The mapping tables live behind tabs (Movies/TV Shows | Collections) with
// one shared search/filter/sort toolbar and paging -- a whole library in one
// endless table was hard to work with.
type MappingTab = 'items' | 'collections'
type MappingFilter = 'all' | 'mapped' | 'unmapped'
const activeTab = ref<MappingTab>('items')
const mappingSearch = ref('')
const mappingFilter = ref<MappingFilter>('all')
const mappingSort = ref<'title_asc' | 'title_desc'>('title_asc')
const PAGE_SIZES = [25, 50, 100] as const
const pageSize = ref<number>(50)
const page = ref(1)

const showCollectionsTab = computed(() => !isTV.value && mirrorCollections.value)
// Falls back to the main tab if Collections gets switched off while open.
const currentTab = computed<MappingTab>(() =>
  activeTab.value === 'collections' && showCollectionsTab.value ? 'collections' : 'items'
)
const isCollectionsTab = computed(() => currentTab.value === 'collections')
const activeMapping = computed(() => (isCollectionsTab.value ? collectionMapping.value : mapping.value))
const activeMappingLoading = computed(() =>
  isCollectionsTab.value ? collectionMappingLoading.value : mappingLoading.value
)
const activeUnmappedCount = computed(() =>
  isCollectionsTab.value ? unmappedCollectionCount.value : unmappedCount.value
)

const filteredMapping = computed(() => {
  const q = mappingSearch.value.trim().toLowerCase()
  const out = activeMapping.value.filter(e => {
    if (q && !(e.title || '').toLowerCase().includes(q)) return false
    if (mappingFilter.value === 'mapped') return rowHasAnyMatch(e)
    if (mappingFilter.value === 'unmapped') return !rowHasAnyMatch(e)
    return true
  })
  out.sort((a, b) => compareTitles(a.title || '', b.title || ''))
  if (mappingSort.value === 'title_desc') out.reverse()
  return out
})
const totalPages = computed(() => Math.max(1, Math.ceil(filteredMapping.value.length / pageSize.value)))
const pagedMapping = computed(() => {
  const start = (Math.min(page.value, totalPages.value) - 1) * pageSize.value
  return filteredMapping.value.slice(start, start + pageSize.value)
})
watch([currentTab, mappingSearch, mappingFilter, mappingSort, pageSize], () => { page.value = 1 })

function refreshActiveMapping() {
  return isCollectionsTab.value ? fetchCollectionMapping() : fetchMapping()
}

// Per-row manual "Send" (Quirk #123's follow-up) -- keyed by source_rating_key
// so multiple rows can be in flight independently, matching the Set-ref
// pattern this app already uses elsewhere for per-item async state.
const sendingKeys = ref<Set<string>>(new Set())
const sendResults = ref<Record<string, string>>({})

function sendResultLabel(status: string): string {
  if (status === 'updated') return '✓ Sent'
  if (status === 'skipped') return '— Nothing to send'
  if (status === 'unchanged') return '— Already up to date'
  if (status === 'unmapped') return '— No match'
  if (status === 'failed') return '✗ Failed'
  return '✗ Error'
}

async function sendItem(entry: MirrorMappingEntry, mediaTypeOverride?: string) {
  const key = entry.source_rating_key
  if (!key) return
  sendingKeys.value = new Set(sendingKeys.value).add(key)
  const clearedResults = { ...sendResults.value }
  delete clearedResults[key]
  sendResults.value = clearedResults
  try {
    const res = await fetch(`${apiBase}/api/media-mirror/send-item`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        server_id: serverId.value,
        library_id: libraryId.value,
        media_type: mediaTypeOverride || mediaType.value,
        source_rating_key: key,
      }),
    })
    if (res.ok) {
      const data = await res.json()
      sendResults.value = { ...sendResults.value, [key]: data.status || 'updated' }
    } else {
      const data = await res.json().catch(() => ({}))
      sendResults.value = { ...sendResults.value, [key]: 'error' }
      saveMessage.value = data.detail || 'Could not send this item.'
      setTimeout(() => { saveMessage.value = '' }, 4000)
    }
  } catch {
    sendResults.value = { ...sendResults.value, [key]: 'error' }
  } finally {
    const next = new Set(sendingKeys.value)
    next.delete(key)
    sendingKeys.value = next
    setTimeout(() => {
      const cleared = { ...sendResults.value }
      delete cleared[key]
      sendResults.value = cleared
    }, 5000)
  }
}

async function pollRunStatus() {
  try {
    const params = new URLSearchParams({
      server_id: serverId.value, library_id: libraryId.value, media_type: mediaType.value,
    })
    const res = await fetch(`${apiBase}/api/media-mirror/run-status?${params.toString()}`)
    if (res.ok) {
      const data: RunStatus = await res.json()
      runStatus.value = data
      if (previousRunState === 'running' && data.state === 'done') {
        await fetchGroup()
        await fetchMapping()
      }
      previousRunState = data.state
    }
  } catch {
    // transient -- keep polling regardless
  }
}

// Run Now normally only copies items whose source art changed since the last
// run; this bypasses that and re-copies everything.
const forceRecopy = ref(false)

async function runNow() {
  starting.value = true
  try {
    const res = await fetch(`${apiBase}/api/media-mirror/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        server_id: serverId.value, library_id: libraryId.value, media_type: mediaType.value,
        force: forceRecopy.value,
      }),
    })
    if (res.ok) {
      runStatus.value = { state: 'running', total: 0, processed: 0 }
      previousRunState = 'running'
    } else {
      const data = await res.json().catch(() => ({}))
      saveMessage.value = data.detail || 'Could not start run.'
      setTimeout(() => { saveMessage.value = '' }, 4000)
    }
  } catch {
    saveMessage.value = 'Could not start run.'
    setTimeout(() => { saveMessage.value = '' }, 4000)
  } finally {
    starting.value = false
  }
}

function formatLastRun(iso?: string | null): string {
  if (!iso) return 'Never'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

async function refresh() {
  await fetchGroup()
  await pollRunStatus()
  if (sourceServerId.value && targetServerIds.value.size > 0) {
    await fetchMapping()
    await fetchCollectionMapping()
  }
}

watch([libraryId, serverId], refresh)
onMounted(() => {
  refresh()
  pollHandle = setInterval(pollRunStatus, 2000)
})
onUnmounted(() => {
  if (pollHandle) clearInterval(pollHandle)
})
</script>

<template>
  <div class="media-mirror-view">
    <div class="page-header">
      <h2>🪞 Media Mirror</h2>
      <div class="header-actions">
        <span v-if="saveMessage" class="save-msg">{{ saveMessage }}</span>
      </div>
    </div>

    <div class="section-note">
      Designate one linked server's library as "the truth" and copy its posters/logos/backdrops/square art
      to one or more other linked servers in this group. Run manually below, or on a schedule. Only art that changed
      since the last run is copied again.
    </div>

    <div v-if="loading" class="state-msg">Loading...</div>

    <div v-else-if="!group" class="state-msg">
      This library isn't linked to another server yet. Link one in Settings → Libraries to use Media Mirror.
    </div>

    <div v-else-if="!hasEnoughMembers" class="state-msg">
      This group only has one linked server so far — link a second one in Settings → Libraries before
      configuring Media Mirror.
    </div>

    <template v-else>
      <div class="section">
        <div class="section-header-inline">
          <h3>Configuration</h3>
          <label class="enable-toggle">
            <input type="checkbox" v-model="enabled" />
            Enabled
          </label>
        </div>

        <div class="config-grid">
          <div class="config-field">
            <label class="field-label">Source (the truth)</label>
            <select v-model="sourceServerId" class="toolbar-select">
              <option v-for="opt in memberOptions" :key="opt.id" :value="opt.id">{{ opt.label }}</option>
            </select>
          </div>

          <div class="config-field">
            <label class="field-label">Mirror to</label>
            <div class="checkbox-list">
              <label v-for="opt in targetOptions" :key="opt.id" class="checkbox-item">
                <input
                  type="checkbox"
                  :checked="targetServerIds.has(opt.id)"
                  @change="toggleTarget(opt.id)"
                />
                {{ opt.label }}
              </label>
              <div v-if="targetOptions.length === 0" class="no-labels-hint">
                No other server to mirror to — link one in Settings → Libraries.
              </div>
            </div>
          </div>

          <div class="config-field">
            <label class="field-label">Asset types</label>
            <div class="checkbox-list">
              <label
                v-for="(label, id) in ASSET_TYPE_LABELS"
                :key="id"
                class="checkbox-item"
                :class="{ 'checkbox-item-disabled': id === 'square_art' && !squareArtAvailable }"
                :title="id === 'square_art' && !squareArtAvailable
                  ? 'Square Art only works when both the source and at least one target are Plex — Jellyfin/Emby have no square art equivalent.'
                  : undefined"
              >
                <input
                  type="checkbox"
                  :checked="assetTypes.has(id)"
                  :disabled="id === 'square_art' && !squareArtAvailable"
                  @change="toggleAssetType(id)"
                />
                {{ label }}
              </label>
            </div>
          </div>

          <div v-if="!isTV" class="config-field">
            <label class="field-label checkbox-field-label">
              <input type="checkbox" v-model="mirrorCollections" @change="fetchCollectionMapping" />
              Also mirror Collections
            </label>
            <span class="help-text">Uses the same source/targets above, matched by collection name. Has its own asset-type selection below.</span>
            <div v-if="mirrorCollections" class="checkbox-list collection-asset-types">
              <label
                v-for="(label, id) in ASSET_TYPE_LABELS"
                :key="id"
                class="checkbox-item"
                :class="{ 'checkbox-item-disabled': id === 'square_art' && !squareArtAvailable }"
                :title="id === 'square_art' && !squareArtAvailable
                  ? 'Square Art only works when both the source and at least one target are Plex — Jellyfin/Emby have no square art equivalent.'
                  : undefined"
              >
                <input
                  type="checkbox"
                  :checked="collectionAssetTypes.has(id)"
                  :disabled="id === 'square_art' && !squareArtAvailable"
                  @change="toggleCollectionAssetType(id)"
                />
                {{ label }}
              </label>
            </div>
          </div>

          <div class="config-field">
            <label class="field-label checkbox-field-label">
              <input type="checkbox" v-model="scheduleEnabled" />
              Run on a schedule
            </label>
            <div v-if="scheduleEnabled" class="schedule-config">
              <input v-model="scheduleCron" type="text" class="toolbar-select cron-input" placeholder="0 3 * * 0" />
              <span class="help-text">Example: "0 3 * * 0" = Weekly, Sundays at 3 AM. Each run only copies items whose source art changed since the last run.</span>
              <div v-if="nextRun" class="next-run-note">Next run: {{ formatLastRun(nextRun) }}</div>
            </div>
          </div>
        </div>

        <div class="config-actions">
          <button class="primary" :disabled="saving || runStatus.state === 'running'" @click="saveConfig">
            {{ saving ? 'Saving...' : 'Save Configuration' }}
          </button>
          <button
            class="secondary"
            :disabled="starting || !enabled || runStatus.state === 'running' || sourceServerId === '' || targetServerIds.size === 0 || (assetTypes.size === 0 && !(mirrorCollections && collectionAssetTypes.size > 0))"
            @click="runNow"
          >
            {{ starting ? 'Starting...' : (runStatus.state === 'running' ? 'Running...' : 'Run Now') }}
          </button>
          <label class="checkbox-item force-toggle" title="Normally only items whose source art changed since the last run are copied.">
            <input type="checkbox" v-model="forceRecopy" />
            Re-copy everything
          </label>
        </div>

        <div v-if="group.mirror?.lastRunAt" class="last-run-note">
          Last run: {{ formatLastRun(group.mirror.lastRunAt) }} —
          {{ group.mirror.lastRunStats?.updated ?? 0 }} updated,
          {{ (group.mirror.lastRunStats?.unchanged ?? 0) + (group.mirror.lastRunStats?.skipped ?? 0) }} unchanged,
          {{ group.mirror.lastRunStats?.unmapped ?? 0 }} unmapped,
          {{ group.mirror.lastRunStats?.failed ?? 0 }} failed
          <template v-if="mirrorCollections && group.mirror?.lastRunCollectionStats">
            — collections: {{ group.mirror.lastRunCollectionStats.updated ?? 0 }} updated,
            {{ (group.mirror.lastRunCollectionStats.unchanged ?? 0) + (group.mirror.lastRunCollectionStats.skipped ?? 0) }} unchanged,
            {{ group.mirror.lastRunCollectionStats.unmapped ?? 0 }} unmapped,
            {{ group.mirror.lastRunCollectionStats.failed ?? 0 }} failed
          </template>
        </div>

        <div v-if="runStatus.state === 'running'" class="run-progress">
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: (runStatus.total ? (100 * (runStatus.processed || 0) / runStatus.total) : 0) + '%' }"
            ></div>
          </div>
          <span class="progress-text">
            {{ runStatus.processed || 0 }} / {{ runStatus.total || 0 }}
            <template v-if="runStatus.current">— {{ runStatus.current }}</template>
          </span>
        </div>

        <div v-else-if="runStatus.state === 'error'" class="state-msg error-msg">
          {{ runStatus.error || 'The last run failed.' }}
        </div>
      </div>

      <div class="section">
        <div class="section-header-inline">
          <h3>Confirm Mappings</h3>
          <button class="secondary-small" :disabled="activeMappingLoading" @click="refreshActiveMapping">
            {{ activeMappingLoading ? 'Checking...' : 'Refresh Mapping' }}
          </button>
        </div>

        <div class="mapping-tabs">
          <button
            class="mapping-tab"
            :class="{ active: currentTab === 'items' }"
            @click="activeTab = 'items'"
          >
            {{ isTV ? 'TV Shows' : 'Movies' }} <span class="tab-count">{{ mapping.length }}</span>
          </button>
          <button
            v-if="showCollectionsTab"
            class="mapping-tab"
            :class="{ active: currentTab === 'collections' }"
            @click="activeTab = 'collections'"
          >
            Collections <span class="tab-count">{{ collectionMapping.length }}</span>
          </button>
        </div>

        <div class="section-description">
          <template v-if="isCollectionsTab">
            Collections are matched by NAME (not TMDb ID) across servers, since Jellyfin/Emby append "Collection" to
            the end of a collection's name — e.g. Plex's "Marvel Cinematic Universe" matches Jellyfin's
            "Marvel Cinematic Universe Collection" automatically.
          </template>
          <template v-else>
            Which items on the source server were matched to an item on each target server (by TMDb ID). An item
            with no match on a target is skipped during a run. Use Send on a row to copy just that one item now.
          </template>
        </div>

        <div v-if="sourceServerId === '' || targetServerIds.size === 0" class="state-msg small">
          Pick a source and at least one target above to preview the mapping.
        </div>
        <div v-else-if="activeMappingLoading" class="state-msg small">Checking mapping...</div>
        <div v-else-if="activeMapping.length === 0" class="state-msg small">
          {{ isCollectionsTab ? 'No collections found on the source server.' : 'No items found on the source server.' }}
        </div>
        <template v-else>
          <div v-if="activeUnmappedCount > 0" class="unmapped-warning">
            ⚠ {{ activeUnmappedCount }} {{ isCollectionsTab ? 'collection(s)' : 'item(s)' }} have no match on any
            selected target server and will be skipped.
          </div>
          <div class="mapping-toolbar">
            <input
              v-model="mappingSearch"
              type="text"
              class="search-input"
              :placeholder="isCollectionsTab ? 'Search collections...' : 'Search titles...'"
            />
            <select v-model="mappingFilter" class="toolbar-select">
              <option value="all">All</option>
              <option value="mapped">Mapped</option>
              <option value="unmapped">No match</option>
            </select>
            <select v-model="mappingSort" class="toolbar-select">
              <option value="title_asc">Title A–Z</option>
              <option value="title_desc">Title Z–A</option>
            </select>
            <span class="mapping-count">{{ filteredMapping.length }} of {{ activeMapping.length }}</span>
          </div>
          <div v-if="filteredMapping.length === 0" class="state-msg small">Nothing matches this search/filter.</div>
          <template v-else>
            <div class="mapping-table-wrap">
              <table class="mapping-table">
                <thead>
                  <tr>
                    <th>{{ isCollectionsTab ? 'Collection' : 'Title' }}</th>
                    <th v-for="id in Array.from(targetServerIds)" :key="id">
                      {{ memberOptions.find(o => o.id === id)?.label || id }}
                    </th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="entry in pagedMapping" :key="entry.source_rating_key || entry.title || ''">
                    <td>{{ entry.title }}<span v-if="entry.year" class="mapping-year"> ({{ entry.year }})</span></td>
                    <td v-for="id in Array.from(targetServerIds)" :key="id">
                      <span v-if="entry.targets && entry.targets[id]" class="mapped-ok">✓ Mapped</span>
                      <span v-else class="mapped-missing">— No match</span>
                    </td>
                    <td class="mapping-send-cell">
                      <button
                        class="secondary-small"
                        :disabled="!entry.source_rating_key || sendingKeys.has(entry.source_rating_key) || !rowHasAnyMatch(entry)"
                        @click="sendItem(entry, isCollectionsTab ? 'collection' : undefined)"
                      >
                        {{ entry.source_rating_key && sendingKeys.has(entry.source_rating_key) ? 'Sending...' : 'Send' }}
                      </button>
                      <span
                        v-if="entry.source_rating_key && sendResults[entry.source_rating_key]"
                        class="send-result-inline"
                        :class="{ 'send-result-ok': sendResults[entry.source_rating_key] === 'updated' }"
                      >
                        {{ sendResultLabel(sendResults[entry.source_rating_key] || '') }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="pagination-bar">
              <button class="page-btn" :disabled="page <= 1" @click="page = 1">«</button>
              <button class="page-btn" :disabled="page <= 1" @click="page--">‹ Prev</button>
              <span class="page-indicator">Page {{ Math.min(page, totalPages) }} of {{ totalPages }}</span>
              <button class="page-btn" :disabled="page >= totalPages" @click="page++">Next ›</button>
              <button class="page-btn" :disabled="page >= totalPages" @click="page = totalPages">»</button>
              <select v-model.number="pageSize" class="toolbar-select page-size-select">
                <option v-for="n in PAGE_SIZES" :key="n" :value="n">{{ n }} / page</option>
              </select>
            </div>
          </template>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.media-mirror-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #eef2ff;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.save-msg {
  font-size: 13px;
  color: var(--accent, #3dd6b7);
}

.section-note {
  font-size: 12px;
  color: #6b7a99;
  line-height: 1.5;
}

.state-msg {
  padding: 40px 20px;
  text-align: center;
  color: #a8b3cf;
}

.state-msg.small {
  padding: 16px 20px;
  font-size: 13px;
}

.state-msg.error-msg {
  color: #ff8a8a;
  padding: 12px 20px;
}

.section {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
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
}

.section h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #eef2ff;
}

.section-description {
  font-size: 12px;
  color: #6b7a99;
  line-height: 1.5;
}

.enable-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #c9d1e0;
  cursor: pointer;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
}

.config-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 12px;
  color: #a8b3cf;
  font-weight: 600;
}

.toolbar-select {
  padding: 5px 10px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}

.toolbar-select:hover {
  border-color: rgba(61, 214, 183, 0.35);
}

.toolbar-select option {
  background: #1a1d2e;
  color: #c9d1e0;
}

.mapping-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.search-input {
  flex: 1 1 200px;
  min-width: 0;
  padding: 5px 10px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  outline: none;
  transition: border-color 0.15s;
}

.search-input:focus {
  border-color: rgba(61, 214, 183, 0.5);
}

.mapping-count {
  font-size: 12px;
  color: var(--muted, #8b93a7);
  white-space: nowrap;
}

.checkbox-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #c9d1e0;
  cursor: pointer;
}

.checkbox-item-disabled {
  color: #6b7a99;
  cursor: not-allowed;
}

.checkbox-item-disabled input[type="checkbox"] {
  cursor: not-allowed;
}

.no-labels-hint {
  font-size: 12px;
  color: #6b7a99;
  font-style: italic;
}

.checkbox-field-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.collection-asset-types {
  margin-top: 6px;
  margin-left: 20px;
  padding-left: 10px;
  border-left: 2px solid rgba(255, 255, 255, 0.08);
}

.schedule-config {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
}

.cron-input {
  max-width: 180px;
}

.help-text {
  font-size: 12px;
  color: #6b7a99;
}

.next-run-note {
  font-size: 12px;
  color: var(--accent, #3dd6b7);
}

.config-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

button.primary {
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 7px;
  border: none;
  background: var(--accent, #3dd6b7);
  color: #0b1220;
  cursor: pointer;
  transition: opacity 0.15s;
}

button.primary:hover:not(:disabled) {
  opacity: 0.9;
}

button.primary:disabled {
  opacity: 0.5;
  cursor: default;
}

button.secondary {
  padding: 7px 16px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  cursor: pointer;
  transition: all 0.15s;
}

button.secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.09);
  border-color: rgba(61, 214, 183, 0.35);
  color: #eef2ff;
}

button.secondary:disabled {
  opacity: 0.5;
  cursor: default;
}

button.secondary-small {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  cursor: pointer;
  transition: all 0.15s;
}

button.secondary-small:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.09);
  border-color: rgba(61, 214, 183, 0.35);
  color: #eef2ff;
}

button.secondary-small:disabled {
  opacity: 0.5;
  cursor: default;
}

.last-run-note {
  font-size: 12px;
  color: #a8b3cf;
}

.run-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent, #3dd6b7);
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 12px;
  color: #a8b3cf;
  white-space: nowrap;
}

.unmapped-warning {
  font-size: 12px;
  color: rgba(255, 180, 100, 0.9);
  background: rgba(255, 180, 100, 0.08);
  border: 1px solid rgba(255, 180, 100, 0.25);
  border-radius: 7px;
  padding: 8px 12px;
}

.mapping-table-wrap {
  overflow-x: auto;
}

.mapping-tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 12px;
}

.mapping-tab {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: #a8b3cf;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: -1px;
  transition: color 0.15s, border-color 0.15s;
}

.mapping-tab:hover {
  color: #e6ecf5;
}

.mapping-tab.active {
  color: #3dd6b7;
  border-bottom-color: #3dd6b7;
}

.tab-count {
  margin-left: 6px;
  font-size: 11px;
  font-weight: 500;
  padding: 1px 7px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.07);
  color: #a8b3cf;
}

.pagination-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 12px;
}

.page-btn {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  cursor: pointer;
}

.page-btn:hover:not(:disabled) {
  border-color: rgba(61, 214, 183, 0.35);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-indicator {
  font-size: 12px;
  color: #a8b3cf;
  padding: 0 6px;
}

.page-size-select {
  margin-left: 8px;
}

.force-toggle {
  font-size: 12px;
  color: #a8b3cf;
}

.mapping-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.mapping-table th,
.mapping-table td {
  text-align: left;
  padding: 6px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  color: #c9d1e0;
  white-space: nowrap;
}

.mapping-table th {
  color: #a8b3cf;
  font-weight: 600;
  font-size: 12px;
}

.mapping-year {
  color: #6b7a99;
  font-size: 12px;
}

.mapped-ok {
  color: var(--accent, #3dd6b7);
}

.mapped-missing {
  color: #6b7a99;
}

.mapping-send-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.send-result-inline {
  font-size: 12px;
  color: #6b7a99;
}

.send-result-ok {
  color: var(--accent, #3dd6b7);
}
</style>
