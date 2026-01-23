<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MovieGrid from '../components/movies/MovieGrid.vue'
import { useSettingsStore } from '../stores/settings'
import { useMovies } from '../composables/useMovies'
import { getApiBase } from '@/services/apiBase'

type Movie = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
  mediaType?: 'movie' | 'tv-show'
  library_id?: string | number
}

// Simple module-level caches so navigating away/back does not refetch everything
const { movies: moviesCache, moviesLoaded: moviesLoadedFlag, setMoviePoster } = useMovies()
const posterCacheStore = ref<Record<string, string | null>>({})
const labelCacheStore = ref<Record<string, string[]>>({})
const posterInFlight = new Set<string>()
const labelInFlight = new Set<string>()
const moviesLoaded = moviesLoadedFlag
const route = useRoute()
const currentLibrary = computed(() => (route.query.library as string) || '')
const POSTER_CACHE_KEY = computed(() => `simposter-poster-cache-${currentLibrary.value || 'all'}`)
const LABELS_CACHE_KEY = computed(() => `simposter-labels-cache-${currentLibrary.value || 'all'}`)
const MOVIES_CACHE_KEY = computed(() => `simposter-movies-cache-${currentLibrary.value || 'all'}`)
const CACHE_VERSION_KEY = 'simposter-cache-version'
const CURRENT_CACHE_VERSION = '2' // Increment this to invalidate all caches

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
  } catch (e) {
    console.warn('[MoviesView] Failed to load poster cache:', e)
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

const loadMoviesCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    const raw = sessionStorage.getItem(MOVIES_CACHE_KEY.value)
    console.log('[MoviesView] loadMoviesCache - Cache key:', MOVIES_CACHE_KEY.value)
    console.log('[MoviesView] loadMoviesCache - Current library:', currentLibrary.value)
    if (raw) {
      const cached = JSON.parse(raw)
      console.log('[MoviesView] loadMoviesCache - Total cached items:', cached.length)
      // Only use cache if it actually has movies
      if (cached && cached.length > 0) {
        // STRICT validation: only show movies from current library
        const currentLib = currentLibrary.value || ''
        const validCached = cached.filter((m: any) => {
          const cachedLib = String(m.library_id || '')
          // STRICT: library IDs must match exactly
          return cachedLib === currentLib
        })
        console.log('[MoviesView] loadMoviesCache - Filtered items for library', currentLib + ':', validCached.length)
        if (validCached.length > 0) {
          moviesCache.value = validCached
          console.log('[MoviesView] loadMoviesCache - Set moviesCache to', validCached.length, 'items')
        } else {
          // No valid movies for this library, clear the cache
          moviesCache.value = []
          console.log('[MoviesView] loadMoviesCache - No valid items, cleared cache')
        }
        // Don't set moviesLoaded here - let onMounted decide whether to fetch fresh
      }
    } else {
      console.log('[MoviesView] loadMoviesCache - No cached data found')
    }
  } catch (e) {
    console.warn('[MoviesView] loadMoviesCache - Error:', e)
  }
}

const saveMoviesCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(MOVIES_CACHE_KEY.value, JSON.stringify(moviesCache.value))
  } catch {
    /* ignore */
  }
}

const clearAllCaches = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.removeItem(POSTER_CACHE_KEY.value)
    sessionStorage.removeItem(LABELS_CACHE_KEY.value)
    sessionStorage.removeItem(MOVIES_CACHE_KEY.value)
    posterCacheStore.value = {}
    labelCacheStore.value = {}
    moviesCache.value = []
    movies.value = []
    moviesLoaded.value = false
  } catch {
    /* ignore */
  }
}

const refreshData = async () => {
  clearAllCaches()
  sessionStorage.setItem(CACHE_VERSION_KEY, CURRENT_CACHE_VERSION)
  movies.value = []
  moviesLoaded.value = false
  await fetchMovies()
  await fetchPosters(paged.value)
  await fetchLabels(paged.value)
}

const forceRefreshingPosters = ref(false)
const forcePosterRefresh = async () => {
  if (forceRefreshingPosters.value || loading.value) return
  forceRefreshingPosters.value = true
  try {
    // Force refresh posters from Plex and get updated URLs
    const currentMovies = paged.value
    const results = await Promise.all(
      currentMovies.map(async (m) => {
        try {
          // Force refresh the poster file from Plex and get the new URL with timestamp
          const posterMetaUrl = `${apiBase}/api/movie/${m.key}/poster?meta=1&force_refresh=1${currentLibrary.value ? `&library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`
          const posterRes = await fetch(posterMetaUrl)
          if (posterRes.ok) {
            const data = await posterRes.json()
            const url = data.url ? (data.url.startsWith('http') ? data.url : `${apiBase}${data.url}`) : null
            return { key: m.key, url }
          }
          return { key: m.key, url: null }
        } catch (e) {
          console.warn(`Failed to refresh poster for ${m.title}:`, e)
          return { key: m.key, url: null }
        }
      })
    )

    // Update poster cache with new URLs (with updated timestamps)
    results.forEach((r) => {
      posterCache.value[r.key] = r.url
      setMoviePoster(r.key, r.url)
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
watch(currentLibrary, (newLib, oldLib) => {
  console.log('[MoviesView] Library changed from', oldLib, 'to', newLib)
  console.log('[MoviesView] Current moviesCache length before clear:', moviesCache.value.length)
  console.log('[MoviesView] Current movies display length before clear:', movies.value.length)

  // Clear display AND cache immediately to prevent showing wrong library's movies
  loading.value = true
  movies.value = []
  moviesCache.value = []
  moviesLoaded.value = false
  console.log('[MoviesView] Cleared all arrays')

  clearAllCaches()
  loadPosterCache()
  loadLabelCache()
  // Don't load movies cache - force fresh fetch from API
  fetchMovies().then(() => {
    console.log('[MoviesView] Fetch complete, moviesCache length:', moviesCache.value.length)
    console.log('[MoviesView] Fetch complete, movies display length:', movies.value.length)
    fetchPosters(paged.value)
    fetchLabels(paged.value)
  })
})

const props = defineProps<{
  search?: string
}>()

const emit = defineEmits<{
  (e: 'select', movie: Movie): void
}>()

const movies = ref<Movie[]>(moviesCache.value)
const loading = ref(false)
const error = ref<string | null>(null)

// Initialize from URL query parameters (route already declared on line 25)
const router = useRouter()
const page = ref(Number(route.query.page) || 1)
const sortBy = ref<'title' | 'year' | 'addedAt'>((route.query.sortBy as any) || 'title')
const sortOrder = ref<'asc' | 'desc'>((route.query.sortOrder as any) || 'asc')
const filterLabel = ref<string>((route.query.label as string) || '')

const posterCache = posterCacheStore
const labelCache = labelCacheStore

const apiBase = getApiBase()
const settings = useSettingsStore()

const pageSize = computed(() => settings.posterDensity.value || 20)

// Get all unique labels from cache
const allLabels = computed(() => {
  const labels = new Set<string>()
  Object.values(labelCache.value).forEach(movieLabels => {
    if (Array.isArray(movieLabels)) {
      movieLabels.forEach(label => labels.add(label))
    }
  })
  return Array.from(labels).sort()
})

const filtered = computed(() => {
  const term = (props.search || '').trim().toLowerCase()
  let result = movies.value
  
  // Filter by search term
  if (term) {
    result = result.filter((m) => m.title.toLowerCase().includes(term))
  }
  
  // Filter by label
  if (filterLabel.value) {
    result = result.filter(m => {
      const labels = labelCache.value[m.key] || []
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
  return slice.map((m) => ({ ...m, poster: posterCache.value[m.key] ?? m.poster ?? null }))
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

const fetchMovies = async (forceRefresh = false) => {
  loading.value = true
  error.value = null
  try {
    // Always fetch to ensure we have the correct library's data
    const params = new URLSearchParams()
    if (currentLibrary.value) params.set('library_id', currentLibrary.value)
    if (forceRefresh) params.set('force_refresh', 'true')
    if (settings.deduplicateMovies.value) params.set('deduplicate', 'true')
    const url = `${apiBase}/api/movies${params.toString() ? '?' + params.toString() : ''}`
    console.log('[MoviesView] fetchMovies - Current library:', currentLibrary.value)
    console.log('[MoviesView] fetchMovies - URL:', url)
    const res = await fetch(url)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = (await res.json()) as (Movie & { labels?: string[] })[]
    console.log('[MoviesView] fetchMovies - Received', data.length, 'items from API')
    console.log('[MoviesView] fetchMovies - Sample library_ids:', data.slice(0, 5).map(m => m.library_id))
    // Seed caches from server data when available
    data.forEach((m) => {
      if (m.poster && !(m.key in posterCacheStore.value)) {
        posterCacheStore.value[m.key] = m.poster
      }
      if (m.labels && !(m.key in labelCacheStore.value)) {
        labelCacheStore.value[m.key] = m.labels
      }
    })
    savePosterCache()
    saveLabelCache()

    moviesCache.value = data
    console.log('[MoviesView] fetchMovies - Set moviesCache to', data.length, 'items')

    // IMPORTANT: Don't use hydratePostersFromSession() - it uses wrong cache key!
    // Instead, manually apply poster cache from our library-specific cache
    moviesCache.value.forEach((m: Movie) => {
      if (m.key in posterCacheStore.value && posterCacheStore.value[m.key]) {
        m.poster = posterCacheStore.value[m.key]
      }
    })

    moviesLoaded.value = true
    saveMoviesCache()
    movies.value = moviesCache.value
    console.log('[MoviesView] fetchMovies - Set movies display to', movies.value.length, 'items')
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Failed to load movies'
  } finally {
    loading.value = false
  }
}

const fetchPosters = async (list: Movie[]) => {
  const missing = list.filter((m) => !(m.key in posterCache.value) && !posterInFlight.has(m.key))
  if (!missing.length) return
  missing.forEach((m) => posterInFlight.add(m.key))
  const results = await Promise.all(
    missing.map(async (m) => {
      try {
        const posterMetaUrl = `${apiBase}/api/movie/${m.key}/poster?meta=1${currentLibrary.value ? `&library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`
        const posterRes = await fetch(posterMetaUrl)
        if (posterRes.ok) {
          const data = await posterRes.json()
          const url = data.url ? (data.url.startsWith('http') ? data.url : `${apiBase}${data.url}`) : null
          return { key: m.key, url }
        }
        return { key: m.key, url: null }
      } catch {
        return { key: m.key, url: null }
      }
    })
  )
  results.forEach((r) => {
    posterCache.value[r.key] = r.url
    posterInFlight.delete(r.key)
    // Update global movies cache so search bar sees latest poster
    setMoviePoster(r.key, r.url)
  })
  savePosterCache()
}

const fetchLabels = async (list: Movie[]) => {
  const missing = list.filter((m) => !(m.key in labelCache.value) && !labelInFlight.has(m.key))
  if (!missing.length) return
  missing.forEach((m) => labelInFlight.add(m.key))
  const results = await Promise.all(
    missing.map(async (m) => {
      try {
        const labelsRes = await fetch(`${apiBase}/api/movie/${m.key}/labels${currentLibrary.value ? `?library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`)
        const labelsData = await labelsRes.json()
        return { key: m.key, labels: labelsData.labels || [] }
      } catch {
        return { key: m.key, labels: [] }
      }
    })
  )
  results.forEach((r) => {
    labelCache.value[r.key] = r.labels
    labelInFlight.delete(r.key)
  })
  saveLabelCache()
}

const handleSelect = (movie: Movie) => {
  emit('select', { ...movie, mediaType: 'movie' as const })
}

const nextPage = () => {
  if (page.value < totalPages.value) page.value += 1
}

const prevPage = () => {
  if (page.value > 1) page.value -= 1
}

const handleRefreshPoster = async (ratingKey: string, forceRefresh?: boolean) => {
  try {
    const res = await fetch(`${apiBase}/api/movie/${ratingKey}/poster?meta=1&force_refresh=1`)
    if (!res.ok) return
    const data = await res.json()
    const url = data.url ? (data.url.startsWith('http') ? data.url : `${apiBase}${data.url}`) : null
    posterCache.value[ratingKey] = url
    setMoviePoster(ratingKey, url)
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
  if (sortBy.value !== 'title') query.sortBy = sortBy.value
  if (sortOrder.value !== 'asc') query.sortOrder = sortOrder.value
  if (filterLabel.value) query.label = filterLabel.value

  // Update URL without triggering navigation
  router.replace({ query })
}, { deep: true })

// Watch for route query changes (browser back/forward buttons)
watch(() => route.query, (newQuery) => {
  page.value = Number(newQuery.page) || 1
  sortBy.value = (newQuery.sortBy as any) || 'title'
  sortOrder.value = (newQuery.sortOrder as any) || 'asc'
  filterLabel.value = (newQuery.label as string) || ''
}, { deep: true })

onMounted(async () => {
  // Load caches AFTER route is fully ready (prevents loading wrong library)
  loadPosterCache()
  loadLabelCache()
  loadMoviesCache()

  if (!settings.loaded.value && !settings.loading.value) {
    await settings.load()
  }
  await fetchMovies()
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
      <button @click="() => fetchMovies()">Retry</button>
    </div>
    <div v-else-if="loading" class="callout">Loading movies…</div>
    <MovieGrid v-else heading="Movies" :items="paged" @select="handleSelect" @refresh="handleRefreshPoster" />
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
  border-color: rgba(255, 107, 107, 0.5);
  background: rgba(255, 107, 107, 0.12);
  color: #ffb3b3;
}

.refresh-btn.danger:hover:not(:disabled) {
  background: rgba(255, 107, 107, 0.2);
  border-color: rgba(255, 107, 107, 0.65);
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
</style>
