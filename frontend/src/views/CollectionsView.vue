<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MovieGrid from '../components/movies/MovieGrid.vue'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore } from '@/stores/settings'
import { mediaServerLabel } from '@/services/mediaServerLabel'
import { compareTitles } from '@/services/sortTitle'

type Collection = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
  library_id?: string
  server_id?: string | null
  also_on?: string[] | null
  other_servers?: { server_id: string; rating_key: string }[] | null
}

type CreatorMode = 'simposter' | 'kometa'

const emit = defineEmits<{
  (e: 'select', collection: Collection & { mediaType?: 'movie' | 'tv-show' | 'collection'; creatorMode?: CreatorMode }): void
}>()

const apiBase = getApiBase()
const route = useRoute()
const router = useRouter()
const settings = useSettingsStore()

const collections = ref<Collection[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

// Search/filter/sort -- same shape as Logos/Backdrops/Square Art's own
// toolbars (search box + <select>s, compareTitles() for the title sort,
// Quirk #103), applied purely client-side to the already-fetched list.
// Deliberately separate from the existing "Show from" dropdown above, which
// controls the BACKEND merge-winner/filter behavior (Quirk #121) and needs a
// round trip to change -- this is a plain display filter over whatever the
// backend already returned, so it works regardless of the group's own
// mergeItems setting (filtering "only Jellyfin" while merge is ON just shows
// whichever merged cards happen to currently be displaying as Jellyfin).
const search = ref('')
const serverFilter = ref('')
const sortBy = ref<'title_asc' | 'title_desc'>('title_asc')

const serverFilterOptions = computed(() => {
  const seen = new Set<string>()
  const opts: { id: string; label: string }[] = []
  for (const c of collections.value) {
    const sid = c.server_id || 'plex-1'
    if (seen.has(sid)) continue
    seen.add(sid)
    opts.push({ id: sid, label: mediaServerLabel(sid, settings.mediaServers.value) })
  }
  return opts
})

const displayCollections = computed(() => {
  let list = collections.value

  if (serverFilter.value) {
    list = list.filter((c) => (c.server_id || 'plex-1') === serverFilter.value)
  }

  const q = search.value.trim().toLowerCase()
  if (q) list = list.filter((c) => c.title.toLowerCase().includes(q))

  list = [...list].sort((a, b) =>
    sortBy.value === 'title_asc' ? compareTitles(a.title, b.title) : compareTitles(b.title, a.title)
  )

  return list
})

const movieLibraries = computed(() => {
  const libs = settings.plex.value.libraryMappings
  return libs && libs.length
    ? libs
    : [{ id: settings.plex.value.movieLibraryName || 'default', displayName: 'Movies', title: 'Movies' }]
})

const defaultLibraryId = computed(() => movieLibraries.value[0]?.id || 'default')
const currentLibrary = computed(() => (route.query.library as string) || defaultLibraryId.value)
// Phase 8a's own established pattern (Quirk #116/#120) -- defaults to 'plex-1'
// so every existing URL/caller is byte-identical to before this existed; only
// a Jellyfin/Emby-only group's "Collections" submenu entry ever sets this.
const currentServer = computed(() => (route.query.server as string) || 'plex-1')

const libraryLabel = computed(() => {
  const lib = movieLibraries.value.find((l) => (l.id || '').toString() === currentLibrary.value)
  if (lib) return lib.displayName || lib.title || 'Collections'
  // Not a Plex library mapping -- check libraryGroups for a Jellyfin/Emby-only
  // group's own display name instead (mirrors notifications.py's identical
  // fallback, backend/api/notifications.py's _get_library_name()).
  const group = (settings.libraryGroups.value || []).find((g) =>
    (g.members || []).some((m) => m.libraryId === currentLibrary.value)
  )
  return group?.name || 'Collections'
})

// "Show posters from" (Quirk #85/#121's own dropdown, now wired up for
// Collections too) -- deliberately NOT useLibraryGroupPreference(), which
// hardcodes server_id=plex-1 in its own load() and would resolve the wrong
// group for a Jellyfin/Emby-only group tab (currentServer can be a real
// non-Plex server_id there, see currentServer's own comment above). Mirrors
// MediaMirrorView.vue's identical direct-fetch workaround for the same
// limitation.
type GroupMember = { serverId: string; libraryId: string; libraryName?: string }
type GroupInfo = { members: GroupMember[]; preferredServerId: string | null; mergeItems?: boolean }
const group = ref<GroupInfo | null>(null)
const serverChangeSaving = ref(false)

const mergeEnabled = computed(() => group.value?.mergeItems !== false)

const serverOptions = computed(() => {
  if (!group.value) return []
  const members = group.value.members
  const plexMember = members.find((m) => m.serverId === 'plex-1')
  const others = members.filter((m) => m.serverId !== 'plex-1')
  const servers = [
    ...(plexMember ? [{ id: 'plex-1', label: mediaServerLabel('plex-1', settings.mediaServers.value) }] : []),
    ...others.map((m) => ({ id: m.serverId, label: mediaServerLabel(m.serverId, settings.mediaServers.value) })),
  ]
  if (mergeEnabled.value) return servers
  return [{ id: '', label: 'All' }, ...servers]
})

const hasServerChoice = computed(() => serverOptions.value.length > 1)

const preferredServerId = computed(() => {
  if (!mergeEnabled.value) return group.value?.preferredServerId || ''
  return group.value?.preferredServerId || serverOptions.value[0]?.id || 'plex-1'
})

const fetchGroup = async () => {
  group.value = null
  const lib = currentLibrary.value
  if (!lib) return
  try {
    const res = await fetch(
      `${apiBase}/api/media-server/library-group?server_id=${encodeURIComponent(currentServer.value)}&library_id=${encodeURIComponent(lib)}&media_type=movie`
    )
    if (res.ok) {
      const data = await res.json()
      group.value = data.group || null
    }
  } catch {
    group.value = null
  }
}

const onPreferredServerChange = async (serverId: string) => {
  if (!group.value || !currentLibrary.value) return
  serverChangeSaving.value = true
  try {
    const res = await fetch(`${apiBase}/api/media-server/library-group/preferred-server`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        server_id: currentServer.value,
        library_id: currentLibrary.value,
        media_type: 'movie',
        preferred_server_id: serverId,
      }),
    })
    if (res.ok) {
      const data = await res.json()
      group.value = data.group || group.value
      await fetchCollections()
    }
  } finally {
    serverChangeSaving.value = false
  }
}

const normalizePoster = (url: string | null | undefined) => {
  if (!url) return null
  if (/^https?:\/\//i.test(url)) return url
  return `${apiBase}${url}`
}

const fetchCollections = async (forceRefresh = false) => {
  loading.value = true
  error.value = null
  try {
    const lib = currentLibrary.value
    const url = new URL(`${apiBase}/api/collections`)
    if (lib) url.searchParams.set('library_id', lib)
    url.searchParams.set('server_id', currentServer.value)
    if (forceRefresh) url.searchParams.set('force_refresh', 'true')
    const res = await fetch(url.toString())
    if (!res.ok) throw new Error(`Failed to load collections (${res.status})`)
    const data = (await res.json()) as Collection[]
    collections.value = data.map((c) => ({ ...c, poster: normalizePoster(c.poster) }))
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'Failed to load collections'
    error.value = message
  } finally {
    loading.value = false
  }
}

const refreshCollections = () => fetchCollections(true)

// Per-card refresh button (MovieCard.vue's small refresh icon) — MovieGrid
// already emits this for every item, but CollectionsView never wired up a
// listener for it at all, so clicking it silently did nothing. Reuses the
// same /api/movie/{key}/poster?force_refresh=1 proxy the collection poster
// itself is already served through (collections have no dedicated poster
// endpoint of their own).
const handleRefreshPoster = async (ratingKey: string) => {
  try {
    const res = await fetch(`${apiBase}/api/movie/${ratingKey}/poster?meta=1&force_refresh=1`)
    if (!res.ok) return
    const data = await res.json()
    const url = normalizePoster(data.url)
    const idx = collections.value.findIndex((c) => c.key === ratingKey)
    if (idx === -1) return
    collections.value[idx] = { ...collections.value[idx]!, poster: url }
  } catch {
    /* ignore */
  }
}

const pendingCollection = ref<Collection | null>(null)

const handleSelect = (collection: Collection) => {
  pendingCollection.value = collection
}

const chooseCreator = (mode: CreatorMode) => {
  if (!pendingCollection.value) return
  emit('select', { ...pendingCollection.value, mediaType: 'collection', creatorMode: mode })
  pendingCollection.value = null
}

const cancelCreatorChoice = () => {
  pendingCollection.value = null
}

onMounted(() => {
  if (!route.query.library && route.name === 'collections' && defaultLibraryId.value) {
    router.replace({ name: 'collections', query: { library: defaultLibraryId.value } })
  }
  fetchCollections()
  fetchGroup()
})

watch(
  () => route.query.library,
  () => {
    fetchCollections()
    fetchGroup()
  }
)

watch(defaultLibraryId, (val, oldVal) => {
  if (!route.query.library && val && val !== oldVal && route.name === 'collections') {
    router.replace({ name: 'collections', query: { library: val } })
  }
})
</script>

<template>
  <div class="view glass">
    <div class="header">
      <div>
        <p class="label">&#x1F4DA; Collections</p>
        <h2>{{ libraryLabel }}</h2>
        <p class="collections-plex-note">Kometa Creator can't send to Jellyfin/Emby yet</p>
      </div>
      <div class="header-actions">
        <input
          v-model="search"
          class="search-input"
          type="text"
          placeholder="Search..."
        />
        <!-- Plain client-side display filter, shown once more than one server
             is actually present in the fetched list -- independent of the
             "Show from" merge-winner dropdown below, which only filters when
             the group's own mergeItems setting is off (Quirk #121). -->
        <select v-if="serverFilterOptions.length > 1" v-model="serverFilter" class="toolbar-select">
          <option value="">All Servers</option>
          <option v-for="opt in serverFilterOptions" :key="opt.id" :value="opt.id">{{ opt.label }}</option>
        </select>
        <select v-model="sortBy" class="toolbar-select">
          <option value="title_asc">Title (A–Z)</option>
          <option value="title_desc">Title (Z–A)</option>
        </select>
        <!-- Only shown once this library is actually linked to another server via a
             Library Group (Quirk #62/#64) -- same live "prefer" control Movies/TV
             Shows already have (Quirk #85), now wired up for Collections too. -->
        <div v-if="hasServerChoice" class="prefer-group">
          <label class="toolbar-label">Show from:</label>
          <select
            :value="preferredServerId"
            class="toolbar-select"
            :disabled="serverChangeSaving"
            @change="onPreferredServerChange(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="opt in serverOptions" :key="opt.id" :value="opt.id">{{ opt.label }}</option>
          </select>
        </div>
        <button @click="refreshCollections" class="refresh-btn" :disabled="loading">
          {{ loading ? 'Refreshing...' : 'Refresh Cache' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="state muted">Loading collections...</div>
    <div v-else-if="error" class="state error">{{ error }}</div>
    <div v-else-if="collections.length === 0" class="state muted">No collections found in this library.</div>
    <div v-else-if="displayCollections.length === 0" class="state muted">No collections match your search/filter.</div>
    <MovieGrid
      v-else
      heading="Collections"
      :items="displayCollections"
      @select="handleSelect"
      @refresh="handleRefreshPoster"
      @resend-done="handleRefreshPoster"
    />

    <Teleport to="body">
      <div v-if="pendingCollection" class="modal-backdrop" @click.self="cancelCreatorChoice">
        <div class="modal glass">
          <p class="label">Choose your creator</p>
          <h3>{{ pendingCollection.title }}</h3>
          <div class="creator-list">
            <button class="creator-item" @click="chooseCreator('simposter')">
              <div>
                <p class="name">Simposter Creator</p>
                <p class="desc">The standard manual editor — upload your own poster and logo art.</p>
              </div>
              <span class="pill">Use</span>
            </button>
            <button class="creator-item" @click="chooseCreator('kometa')">
              <div>
                <p class="name">Kometa Creator</p>
                <p class="desc">Flat-color background, gradient fade, and a centered logo — Kometa-style collection posters.</p>
              </div>
              <span class="pill">Use</span>
            </button>
          </div>
          <button class="cancel" @click="cancelCreatorChoice">Cancel</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.view {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.prefer-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.toolbar-label {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.search-input {
  padding: 5px 10px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  outline: none;
  width: 160px;
  transition: border-color 0.15s;
}

.search-input::placeholder {
  color: rgba(255, 255, 255, 0.3);
}

.search-input:focus {
  border-color: rgba(61, 214, 183, 0.4);
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

.collections-plex-note {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.refresh-btn {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 14px;
  background: rgba(61, 214, 183, 0.15);
  color: #3dd6b7;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  margin: 0;
}

.refresh-btn:hover:not(:disabled) {
  background: rgba(61, 214, 183, 0.25);
  border-color: rgba(61, 214, 183, 0.5);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.label {
  text-transform: uppercase;
  font-size: 12px;
  color: var(--muted);
  letter-spacing: 1px;
}

.state {
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
}

.muted {
  color: var(--muted);
}

.error {
  color: #f05d7b;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  width: min(480px, 90vw);
  padding: 20px;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.creator-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.creator-item {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  cursor: pointer;
  color: inherit;
}

.creator-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.creator-item .name {
  font-weight: 600;
}

.creator-item .desc {
  color: var(--muted);
  font-size: 12px;
  margin-top: 2px;
}

.creator-item .pill {
  flex-shrink: 0;
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(61, 214, 183, 0.18);
  color: #d8fff4;
}

.cancel {
  align-self: flex-end;
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  font-size: 13px;
  padding: 4px 8px;
}

.cancel:hover {
  color: var(--fg, #fff);
}
</style>
