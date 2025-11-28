<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import MovieGrid from '../components/movies/MovieGrid.vue'
import BatchEditModal from '../components/BatchEditModal.vue'
import { useSettingsStore } from '../stores/settings'
import { useMovies } from '../composables/useMovies'

type Movie = {
  key: string
  title: string
  year?: number
  addedAt?: number
  poster?: string | null
}

type MovieWithLabels = Movie & {
  labels: string[]
}

// Simple module-level caches so navigating away/back does not refetch everything
const { movies: moviesCache } = useMovies()
const posterCacheStore = ref<Record<string, string | null>>({})
const labelCacheStore = ref<Record<string, string[]>>({})
const posterInFlight = new Set<string>()
const labelInFlight = new Set<string>()
const moviesLoaded = ref(false)
const POSTER_CACHE_KEY = 'simposter-poster-cache'
const LABELS_CACHE_KEY = 'simposter-labels-cache'

const loadPosterCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
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

loadPosterCache()
loadLabelCache()

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
const filterLabel = ref<string>('')
const posterCache = posterCacheStore
const labelCache = labelCacheStore
const batchEditOpen = ref(false)

const apiBase = import.meta.env.VITE_API_URL || window.location.origin
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
  if (sortBy.value === 'title') {
    list.sort((a, b) => a.title.localeCompare(b.title))
  } else if (sortBy.value === 'year') {
    list.sort((a, b) => (b.year || 0) - (a.year || 0))
  } else if (sortBy.value === 'addedAt') {
    list.sort((a, b) => (b.addedAt || 0) - (a.addedAt || 0))
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
      const data = (await res.json()) as Movie[]
      moviesCache.value = data
      moviesLoaded.value = true
    }
    movies.value = moviesCache.value
  } catch (err: any) {
    error.value = err?.message || 'Failed to load movies'
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
        const posterRes = await fetch(`${apiBase}/api/movie/${m.key}/poster`)
        const posterData = await posterRes.json()
        return { key: m.key, url: posterData.url || null }
      } catch {
        return { key: m.key, url: null }
      }
    })
  )
  results.forEach((r) => {
    posterCache.value[r.key] = r.url
    posterInFlight.delete(r.key)
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

const handleSelect = (movie: any) => {
  emit('select', movie)
}

const openBatchEdit = () => {
  batchEditOpen.value = true
}

const closeBatchEdit = () => {
  batchEditOpen.value = false
}

const nextPage = () => {
  if (page.value < totalPages.value) page.value += 1
}

const prevPage = () => {
  if (page.value > 1) page.value -= 1
}

onMounted(async () => {
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
            <option value="title">Title (A-Z)</option>
            <option value="year">Year (Newest)</option>
            <option value="addedAt">Date Added (Newest)</option>
          </select>
        </div>
        <div class="control-group">
          <label for="label-select">Filter by Label:</label>
          <select id="label-select" v-model="filterLabel" class="control-select">
            <option value="">All Labels</option>
            <option v-for="label in allLabels" :key="label" :value="label">{{ label }}</option>
          </select>
        </div>
        <button class="btn-batch-edit" @click="openBatchEdit">Batch Send</button>
      </div>
    </div>
    <div v-if="error" class="callout error">
      <p>{{ error }}</p>
      <button @click="fetchMovies">Retry</button>
    </div>
    <div v-else-if="loading" class="callout">Loading movies…</div>
    <MovieGrid v-else heading="Movies" :items="paged" @select="handleSelect" />
    <div class="toolbar glass pagination">
      <div class="pager">
        <button @click="prevPage" :disabled="page === 1">Prev</button>
        <span>{{ page }} / {{ totalPages }}</span>
        <button @click="nextPage" :disabled="page === totalPages">Next</button>
      </div>
    </div>

    <BatchEditModal
      :is-open="batchEditOpen"
      :movies="movies"
      @close="closeBatchEdit"
    />
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

.btn-batch-edit {
  border: 1px solid rgba(61, 214, 183, 0.4);
  border-radius: 8px;
  padding: 7px 12px;
  background: rgba(61, 214, 183, 0.1);
  color: #3dd6b7;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: 500;
}

.btn-batch-edit:hover {
  background: rgba(61, 214, 183, 0.2);
  border-color: rgba(61, 214, 183, 0.6);
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
