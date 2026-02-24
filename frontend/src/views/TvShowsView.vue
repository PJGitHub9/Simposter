<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MovieGrid from '../components/movies/MovieGrid.vue'
import { useSettingsStore } from '../stores/settings'
import { useTvShows } from '../composables/useTvShows'
import { getApiBase } from '@/services/apiBase'

type TvShow = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
  mediaType?: 'movie' | 'tv-show'
  tmdb_id?: number
  tvdb_id?: number
}

// Simple module-level caches so navigating away/back does not refetch everything
const { tvShows: tvShowsCache, tvShowsLoaded: tvShowsLoadedFlag, setTvShowPoster } = useTvShows()
const posterCacheStore = ref<Record<string, string | null>>({})
const labelCacheStore = ref<Record<string, string[]>>({})
const posterInFlight = new Set<string>()
const labelInFlight = new Set<string>()
const tvShowsLoaded = tvShowsLoadedFlag
const route = useRoute()
const currentLibrary = computed(() => (route.query.library as string) || 'default')
const POSTER_CACHE_KEY = computed(() => `simposter-tv-poster-cache-${currentLibrary.value}`)
const LABELS_CACHE_KEY = computed(() => `simposter-tv-labels-cache-${currentLibrary.value}`)
const TVSHOWS_CACHE_KEY = computed(() => `simposter-tv-shows-cache-${currentLibrary.value}`)
const CACHE_VERSION_KEY = 'simposter-tv-cache-version'
const CURRENT_CACHE_VERSION = '1' // Increment this to invalidate all caches

const loadPosterCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    // Check cache version - clear if outdated
    const cachedVersion = sessionStorage.getItem(CACHE_VERSION_KEY)
    if (cachedVersion !== CURRENT_CACHE_VERSION) {
      clearAllCaches()
      sessionStorage.setItem(CACHE_VERSION_KEY, CURRENT_CACHE_VERSION)
      return
    }

    const raw = sessionStorage.getItem(POSTER_CACHE_KEY.value)
    if (raw) {
      posterCacheStore.value = JSON.parse(raw)
    }
  } catch {
    /* ignore */
  }
}

const savePosterCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(POSTER_CACHE_KEY.value, JSON.stringify(posterCacheStore.value))
  } catch {
    /* ignore */
  }
}

const loadLabelCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    const raw = sessionStorage.getItem(LABELS_CACHE_KEY.value)
    if (raw) {
      labelCacheStore.value = JSON.parse(raw)
    }
  } catch {
    /* ignore */
  }
}

const saveLabelCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(LABELS_CACHE_KEY.value, JSON.stringify(labelCacheStore.value))
  } catch {
    /* ignore */
  }
}

const loadTvShowsCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    const raw = sessionStorage.getItem(TVSHOWS_CACHE_KEY.value)
    if (raw) {
      const cached = JSON.parse(raw)
      // Only use cache if it actually has TV shows
      if (cached && cached.length > 0) {
        // STRICT validation: only show TV shows from current library
        const currentLib = currentLibrary.value || 'default'
        const validCached = cached.filter((show: any) => {
          const cachedLib = String(show.library_id || 'default')
          // STRICT: library IDs must match exactly
          return cachedLib === currentLib
        })
        if (validCached.length > 0) {
          tvShowsCache.value = validCached
        } else {
          // No valid shows for this library, clear the cache
          tvShowsCache.value = []
        }
        // Don't set tvShowsLoaded here - let onMounted decide whether to fetch fresh
      }
    }
  } catch {
    /* ignore */
  }
}

const saveTvShowsCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(TVSHOWS_CACHE_KEY.value, JSON.stringify(tvShowsCache.value))
  } catch {
    /* ignore */
  }
}

const clearAllCaches = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.removeItem(POSTER_CACHE_KEY.value)
    sessionStorage.removeItem(LABELS_CACHE_KEY.value)
    sessionStorage.removeItem(TVSHOWS_CACHE_KEY.value)
    posterCacheStore.value = {}
    labelCacheStore.value = {}
    tvShowsCache.value = []
    tvShowsLoaded.value = false
  } catch {
    /* ignore */
  }
}

const refreshData = async () => {
  clearAllCaches()
  sessionStorage.setItem(CACHE_VERSION_KEY, CURRENT_CACHE_VERSION)
  tvShows.value = []
  await fetchTvShows()
  await fetchPosters(paged.value)
  await fetchLabels(paged.value)
}

const forcePosterRefresh = async () => {
  if (forceRefreshingPosters.value || loading.value) return
  forceRefreshingPosters.value = true
  try {
    // Force refresh posters from Plex and get updated URLs
    const currentShows = paged.value
    const results = await Promise.all(
      currentShows.map(async (s) => {
        try {
          // Force refresh the poster file from Plex and get the new URL with timestamp
          const posterMetaUrl = `${apiBase}/api/tv-show/${s.key}/poster?meta=1&force_refresh=1${currentLibrary.value ? `&library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`
          const posterRes = await fetch(posterMetaUrl)
          if (posterRes.ok) {
            const data = await posterRes.json()
            const url = data.url ? (data.url.startsWith('http') ? data.url : `${apiBase}${data.url}`) : null
            return { key: s.key, url }
          }
          return { key: s.key, url: null }
        } catch (e) {
          console.warn(`Failed to refresh poster for ${s.title}:`, e)
          return { key: s.key, url: null }
        }
      })
    )

    // Update poster cache with new URLs (with updated timestamps)
    results.forEach((r) => {
      posterCache.value[r.key] = r.url
      setTvShowPoster(r.key, r.url)
    })
    savePosterCache()
  } catch (e) {
    console.error('Force poster refresh failed:', e)
  } finally {
    forceRefreshingPosters.value = false
  }
}

// NOTE: Initial cache load moved to onMounted to ensure route is ready
// Reload caches when library changes
watch(currentLibrary, () => {
  // Clear display AND cache immediately to prevent showing wrong library's shows
  loading.value = true
  tvShows.value = []
  tvShowsCache.value = []
  tvShowsLoaded.value = false
  clearAllCaches()
  loadPosterCache()
  loadLabelCache()
  // Don't load TV shows cache - force fresh fetch from API
  fetchTvShows().then(() => {
    fetchPosters(paged.value)
    fetchLabels(paged.value)
  })
})

const props = defineProps<{
  search?: string
}>()

const emit = defineEmits<{
  (e: 'select', tvShow: TvShow): void
}>()

const tvShows = ref<TvShow[]>(tvShowsCache.value)
const loading = ref(false)
const error = ref<string | null>(null)

const apiBase = getApiBase()
const settings = useSettingsStore()

const pageSize = computed(() => settings.posterDensity.value || 20)

// Parse defaultSort from settings (format: "field-order" like "title-asc" or "added-desc")
const getDefaultSort = () => {
  const defaultSort = settings.defaultSort?.value || 'title-asc'
  const [field, order] = defaultSort.split('-')

  // Map "added" to "addedAt" for internal use
  const sortField = field === 'added' ? 'addedAt' : field

  return {
    sortBy: sortField as 'title' | 'year' | 'addedAt',
    sortOrder: order as 'asc' | 'desc'
  }
}

// Initialize from URL query parameters (route already declared on line 27)
const router = useRouter()
const page = ref(Number(route.query.page) || 1)

// Use URL query parameters if present, otherwise use settings default
const defaultSortSettings = getDefaultSort()
const sortBy = ref<'title' | 'year' | 'addedAt'>((route.query.sortBy as any) || defaultSortSettings.sortBy)
const sortOrder = ref<'asc' | 'desc'>((route.query.sortOrder as any) || defaultSortSettings.sortOrder)
const filterLabel = ref<string>((route.query.label as string) || '')

const posterCache = posterCacheStore
const labelCache = labelCacheStore
const forceRefreshingPosters = ref(false)

// Get all unique labels from cache
const allLabels = computed(() => {
  const labels = new Set<string>()
  Object.values(labelCache.value).forEach(showLabels => {
    if (Array.isArray(showLabels)) {
      showLabels.forEach(label => labels.add(label))
    }
  })
  return Array.from(labels).sort()
})

const filtered = computed(() => {
  const term = (props.search || '').trim().toLowerCase()
  let result = tvShows.value

  // Filter by search term
  if (term) {
    result = result.filter((s) => s.title.toLowerCase().includes(term))
  }

  // Filter by label
  if (filterLabel.value) {
    result = result.filter(s => {
      const labels = labelCache.value[s.key] || []
      return labels.includes(filterLabel.value)
    })
  }

  return result
})

const sorted = computed(() => {
  const list = [...filtered.value]
  const multiplier = sortOrder.value === 'asc' ? 1 : -1

  if (sortBy.value === 'title') {
    list.sort((a, b) => multiplier * a.title.localeCompare(b.title))
  } else if (sortBy.value === 'year') {
    list.sort((a, b) => multiplier * ((Number(a.year) || 0) - (Number(b.year) || 0)))
  } else if (sortBy.value === 'addedAt') {
    list.sort((a, b) => multiplier * ((a.addedAt || 0) - (b.addedAt || 0)))
  }
  return list
})

const totalPages = computed(() => Math.max(1, Math.ceil(sorted.value.length / pageSize.value)))

const paged = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const slice = sorted.value.slice(start, start + pageSize.value)
  return slice.map((s) => ({ ...s, poster: posterCache.value[s.key] ?? s.poster ?? null }))
})

watch(pageSize, () => {
  page.value = 1
})

watch(() => props.search, () => {
  page.value = 1
})

watch(() => filterLabel.value, () => {
  page.value = 1
})

watch(filtered, () => {
  if (page.value > totalPages.value) page.value = totalPages.value
})

watch(paged, (list) => {
  fetchPosters(list)
  fetchLabels(list)
})

const fetchTvShows = async () => {
  loading.value = true
  error.value = null
  try {
    // Always fetch to ensure we have the correct library's data
    const res = await fetch(`${apiBase}/api/tv-shows${currentLibrary.value ? `?library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = (await res.json()) as (TvShow & { labels?: string[] })[]
    // Seed caches from server data when available
    data.forEach((s) => {
      if (s.poster && !(s.key in posterCacheStore.value)) {
        posterCacheStore.value[s.key] = s.poster
      }
      if (s.labels && !(s.key in labelCacheStore.value)) {
        labelCacheStore.value[s.key] = s.labels
      }
    })
    savePosterCache()
    saveLabelCache()

    tvShowsCache.value = data

    // IMPORTANT: Don't use hydratePostersFromSession() - it uses wrong cache key!
    // Instead, manually apply poster cache from our library-specific cache
    tvShowsCache.value.forEach((s: TvShow) => {
      if (s.key in posterCacheStore.value && posterCacheStore.value[s.key]) {
        s.poster = posterCacheStore.value[s.key]
      }
    })

    tvShowsLoaded.value = true
    saveTvShowsCache()
    tvShows.value = tvShowsCache.value
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Failed to load TV shows'
  } finally {
    loading.value = false
  }
}

const fetchPosters = async (list: TvShow[]) => {
  const missing = list.filter((s) => !(s.key in posterCache.value) && !posterInFlight.has(s.key))
  if (!missing.length) return
  missing.forEach((s) => posterInFlight.add(s.key))
  const results = await Promise.all(
    missing.map(async (s) => {
      try {
        const posterMetaUrl = `${apiBase}/api/tv-show/${s.key}/poster?meta=1${currentLibrary.value ? `&library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`
        const posterRes = await fetch(posterMetaUrl)
        if (posterRes.ok) {
          const data = await posterRes.json()
          const url = data.url ? (data.url.startsWith('http') ? data.url : `${apiBase}${data.url}`) : null
          return { key: s.key, url }
        }
        return { key: s.key, url: null }
      } catch {
        return { key: s.key, url: null }
      }
    })
  )
  results.forEach((r) => {
    posterCache.value[r.key] = r.url
    posterInFlight.delete(r.key)
    // Update global TV shows cache so search bar sees latest poster
    setTvShowPoster(r.key, r.url)
  })
  savePosterCache()
}

const fetchLabels = async (list: TvShow[]) => {
  const missing = list.filter((s) => !(s.key in labelCache.value) && !labelInFlight.has(s.key))
  if (!missing.length) return
  missing.forEach((s) => labelInFlight.add(s.key))
  const results = await Promise.all(
    missing.map(async (s) => {
      try {
        const labelsRes = await fetch(`${apiBase}/api/tv-show/${s.key}/labels${currentLibrary.value ? `?library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`)
        const labelsData = await labelsRes.json()
        return { key: s.key, labels: labelsData.labels || [] }
      } catch {
        return { key: s.key, labels: [] }
      }
    })
  )
  results.forEach((r) => {
    labelCache.value[r.key] = r.labels
    labelInFlight.delete(r.key)
  })
  saveLabelCache()
}

const handleSelect = (tvShow: TvShow) => {
  emit('select', { ...tvShow, mediaType: 'tv-show' as const })
}

const nextPage = () => {
  if (page.value < totalPages.value) page.value += 1
}

const prevPage = () => {
  if (page.value > 1) page.value -= 1
}

const handleRefreshPoster = async (ratingKey: string) => {
  try {
    const res = await fetch(`${apiBase}/api/tv-show/${ratingKey}/poster?meta=1&force_refresh=1`)
    if (!res.ok) return
    const data = await res.json()
    const url = data.url ? (data.url.startsWith('http') ? data.url : `${apiBase}${data.url}`) : null
    posterCache.value[ratingKey] = url
    setTvShowPoster(ratingKey, url)
    savePosterCache()
  } catch {
    /* ignore */
  }
}

// Sync URL query parameters with state
watch([page, sortBy, sortOrder, filterLabel], () => {
  const query: Record<string, string> = {}

  // CRITICAL: Preserve library parameter!
  if (currentLibrary.value) {
    query.library = currentLibrary.value
  }

  if (page.value > 1) query.page = String(page.value)

  // Only add sort parameters if they differ from settings default
  const defaults = getDefaultSort()
  if (sortBy.value !== defaults.sortBy) query.sortBy = sortBy.value
  if (sortOrder.value !== defaults.sortOrder) query.sortOrder = sortOrder.value
  if (filterLabel.value) query.label = filterLabel.value

  // Update URL without triggering navigation
  router.replace({ query })
}, { deep: true })

// Watch for route query changes (browser back/forward buttons)
watch(() => route.query, (newQuery) => {
  const defaults = getDefaultSort()
  page.value = Number(newQuery.page) || 1
  sortBy.value = (newQuery.sortBy as any) || defaults.sortBy
  sortOrder.value = (newQuery.sortOrder as any) || defaults.sortOrder
  filterLabel.value = (newQuery.label as string) || ''
}, { deep: true })

onMounted(async () => {
  // Load caches AFTER route is fully ready (prevents loading wrong library)
  loadPosterCache()
  loadLabelCache()
  loadTvShowsCache()

  if (!settings.loaded.value && !settings.loading.value) {
    await settings.load()
  }
  await fetchTvShows()
  await fetchPosters(paged.value)
  await fetchLabels(paged.value)
})
</script>

<template>
  <div class="view">
    <div class="toolbar glass">
      <div class="controls">
        <div class="control-group">
          <label for="sort-select">Sort by:</label>
          <select id="sort-select" v-model="sortBy" class="control-select">
            <option value="title">Title</option>
            <option value="year">Year</option>
            <option value="addedAt">Date Added</option>
          </select>
        </div>
        <div class="control-group">
          <label for="sort-order">Order:</label>
          <select id="sort-order" v-model="sortOrder" class="control-select">
            <option value="asc">{{ sortBy === 'title' ? 'A-Z' : 'Oldest First' }}</option>
            <option value="desc">{{ sortBy === 'title' ? 'Z-A' : 'Newest First' }}</option>
          </select>
        </div>
        <div class="control-group">
          <label for="label-select">Filter by Label:</label>
          <select id="label-select" v-model="filterLabel" class="control-select">
            <option value="">All Labels</option>
            <option v-for="label in allLabels" :key="label" :value="label">{{ label }}</option>
          </select>
        </div>
        <button @click="refreshData" class="refresh-btn" :disabled="loading">
          {{ loading ? 'Refreshing...' : 'Refresh Cache' }}
        </button>
        <button @click="forcePosterRefresh" class="refresh-btn danger" :disabled="loading || forceRefreshingPosters">
          {{ forceRefreshingPosters ? 'Forcing...' : 'Force Poster Refresh' }}
        </button>
      </div>
    </div>
    <div v-if="error" class="callout error">
      <p>{{ error }}</p>
      <button @click="fetchTvShows">Retry</button>
    </div>
    <div v-else-if="loading" class="callout">Loading TV shows…</div>
    <MovieGrid v-else heading="TV Shows" :items="paged" @select="handleSelect" @refresh="handleRefreshPoster" />
    <div class="toolbar glass pagination">
      <div class="pager">
        <button @click="prevPage" :disabled="page === 1">Prev</button>
        <span>{{ page }} / {{ totalPages }}</span>
        <button @click="nextPage" :disabled="page === totalPages">Next</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  padding: 12px;
  flex-wrap: wrap;
}

.toolbar.pagination {
  justify-content: center;
}

.controls {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.control-group label {
  font-size: 13px;
  color: #dce6ff;
  font-weight: 500;
}

.control-select {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.control-select:focus {
  outline: none;
  border-color: rgba(61, 214, 183, 0.5);
}

.control-select:hover {
  background: rgba(255, 255, 255, 0.06);
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

.refresh-btn.danger {
  background: rgba(255, 126, 126, 0.15);
  color: #ff7e7e;
  border-color: rgba(255, 126, 126, 0.3);
}

.refresh-btn.danger:hover:not(:disabled) {
  background: rgba(255, 126, 126, 0.25);
  border-color: rgba(255, 126, 126, 0.5);
}

.pager {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #dce6ff;
}

.pager button {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.05);
  color: #dce6ff;
  cursor: pointer;
}

.pager button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.callout {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  color: #e1e8ff;
}

.callout.error {
  border-color: rgba(255, 126, 126, 0.4);
}

button {
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.05);
  color: #dce6ff;
  cursor: pointer;
}

/* Mobile responsive styles */
@media (max-width: 900px) {
  .view {
    gap: 12px;
  }

  .toolbar {
    padding: 10px;
  }

  .controls {
    gap: 10px;
    width: 100%;
  }

  .control-group {
    flex: 1;
    min-width: 120px;
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .control-group label {
    font-size: 11px;
  }

  .control-select {
    width: 100%;
    padding: 8px 10px;
    font-size: 13px;
  }

  .refresh-btn {
    flex: 1;
    min-width: 100px;
    padding: 10px 12px;
    font-size: 12px;
  }

  .pager {
    gap: 6px;
    font-size: 12px;
  }

  .pager button {
    padding: 8px 12px;
    font-size: 12px;
  }
}

@media (max-width: 600px) {
  .view {
    gap: 10px;
  }

  .toolbar {
    padding: 8px;
    gap: 8px;
  }

  .controls {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }

  .control-group {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .control-group label {
    font-size: 12px;
    white-space: nowrap;
  }

  .control-select {
    flex: 1;
    max-width: 160px;
  }

  .refresh-btn {
    width: 100%;
    padding: 10px;
  }

  .toolbar.pagination {
    padding: 10px;
  }

  .pager {
    width: 100%;
    justify-content: center;
  }

  .pager button {
    flex: 1;
    max-width: 100px;
  }

  .callout {
    padding: 10px;
    font-size: 13px;
  }
}
</style>
