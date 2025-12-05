<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
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
}

// Simple module-level caches so navigating away/back does not refetch everything
const { movies: moviesCache, moviesLoaded: moviesLoadedFlag, setMoviePoster, hydratePostersFromSession } = useMovies()
const posterCacheStore = ref<Record<string, string | null>>({})
const labelCacheStore = ref<Record<string, string[]>>({})
const posterInFlight = new Set<string>()
const labelInFlight = new Set<string>()
const moviesLoaded = moviesLoadedFlag
const POSTER_CACHE_KEY = 'simposter-poster-cache'
const LABELS_CACHE_KEY = 'simposter-labels-cache'
const MOVIES_CACHE_KEY = 'simposter-movies-cache'
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

    const raw = sessionStorage.getItem(POSTER_CACHE_KEY)
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
    sessionStorage.setItem(POSTER_CACHE_KEY, JSON.stringify(posterCacheStore.value))
  } catch {
    /* ignore */
  }
}

const loadLabelCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    const raw = sessionStorage.getItem(LABELS_CACHE_KEY)
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
    sessionStorage.setItem(LABELS_CACHE_KEY, JSON.stringify(labelCacheStore.value))
  } catch {
    /* ignore */
  }
}

const loadMoviesCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    const raw = sessionStorage.getItem(MOVIES_CACHE_KEY)
    if (raw) {
      const cached = JSON.parse(raw)
      // Only use cache if it actually has movies
      if (cached && cached.length > 0) {
        moviesCache.value = cached
        moviesLoaded.value = true
      }
    }
  } catch {
    /* ignore */
  }
}

const saveMoviesCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(MOVIES_CACHE_KEY, JSON.stringify(moviesCache.value))
  } catch {
    /* ignore */
  }
}

const clearAllCaches = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.removeItem(POSTER_CACHE_KEY)
    sessionStorage.removeItem(LABELS_CACHE_KEY)
    sessionStorage.removeItem(MOVIES_CACHE_KEY)
    posterCacheStore.value = {}
    labelCacheStore.value = {}
    moviesCache.value = []
    moviesLoaded.value = false
  } catch {
    /* ignore */
  }
}

const refreshData = async () => {
  clearAllCaches()
  sessionStorage.setItem(CACHE_VERSION_KEY, CURRENT_CACHE_VERSION)
  movies.value = []
  await fetchMovies()
  await fetchPosters(paged.value)
  await fetchLabels(paged.value)
}

loadPosterCache()
loadLabelCache()
loadMoviesCache()

const props = defineProps<{
  search?: string
}>()

const emit = defineEmits<{
  (e: 'select', movie: Movie): void
}>()

const movies = ref<Movie[]>(moviesCache.value)
const loading = ref(false)
const error = ref<string | null>(null)
const page = ref(1)
const sortBy = ref<'title' | 'year' | 'addedAt'>('title')
const sortOrder = ref<'asc' | 'desc'>('asc')
const filterLabel = ref<string>('')
const posterCache = posterCacheStore
const labelCache = labelCacheStore

const apiBase = getApiBase()
const settings = useSettingsStore()

const pageSize = computed(() => settings.posterDensity.value || 20)

// Get all unique labels from cache
const allLabels = computed(() => {
  const labels = new Set<string>()
  Object.values(labelCache.value).forEach(movieLabels => {
    movieLabels.forEach(label => labels.add(label))
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

const fetchMovies = async () => {
  loading.value = true
  error.value = null
  try {
    if (!moviesLoaded.value) {
      const res = await fetch(`${apiBase}/api/movies`)
      if (!res.ok) throw new Error(`API error ${res.status}`)
      const data = (await res.json()) as (Movie & { labels?: string[] })[]
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
      hydratePostersFromSession() // reapply cached poster URLs after replacing movie list
      moviesLoaded.value = true
      saveMoviesCache()
    }
    movies.value = moviesCache.value
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
        const posterMetaUrl = `${apiBase}/api/movie/${m.key}/poster?meta=1`
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
        const labelsRes = await fetch(`${apiBase}/api/movie/${m.key}/labels`)
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
  emit('select', movie)
}

const nextPage = () => {
  if (page.value < totalPages.value) page.value += 1
}

const prevPage = () => {
  if (page.value > 1) page.value -= 1
}

const handleRefreshPoster = async (ratingKey: string) => {
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

onMounted(async () => {
  // Reload caches from sessionStorage (in case they were updated by scan library)
  loadPosterCache()
  loadLabelCache()

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
      </div>
    </div>
    <div v-if="error" class="callout error">
      <p>{{ error }}</p>
      <button @click="fetchMovies">Retry</button>
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
