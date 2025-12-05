<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useNotification } from '@/composables/useNotification'
import { useMovies } from '../composables/useMovies'

type Movie = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
}

type Template = {
  id: string
  name: string
}

type Preset = {
  id: string
  name: string
  template_id: string
}

const { success, error: showError } = useNotification()
const { movies: moviesCache, moviesLoaded: moviesLoadedFlag } = useMovies()

const movies = ref<Movie[]>(moviesCache.value)
const loading = ref(false)
const error = ref<string | null>(null)
const selectedMovies = ref<Set<string>>(new Set())
const searchQuery = ref('')
const filterLabel = ref<string>('')
const posterLimit = ref<number>(50)
const currentPage = ref<number>(1)

// Label cache
const LABELS_CACHE_KEY = 'simposter-labels-cache'
const labelCache = ref<Record<string, string[]>>({})
const labelInFlight = new Set<string>()

const loadLabelCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    const raw = sessionStorage.getItem(LABELS_CACHE_KEY)
    if (raw) {
      labelCache.value = JSON.parse(raw)
    }
  } catch {
    /* ignore */
  }
}

const saveLabelCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(LABELS_CACHE_KEY, JSON.stringify(labelCache.value))
  } catch {
    /* ignore */
  }
}

loadLabelCache()

// Template/preset selection
const templates = ref<Template[]>([])
const presets = ref<Preset[]>([])
const selectedTemplate = ref('')
const selectedPreset = ref('')
const sendToPlex = ref(true)
const saveLocally = ref(false)
const labelsToRemove = ref<Set<string>>(new Set())
const processing = ref(false)
const currentIndex = ref(0)
const statusOverlay = ref<{ visible: boolean; message: string; detail?: string }>({ visible: false, message: '' })

const apiBase = getApiBase()

// Poster cache - shared with MoviesView via sessionStorage
const POSTER_CACHE_KEY = 'simposter-poster-cache'
const posterCache = ref<Record<string, string | null>>({})
const posterInFlight = new Set<string>()

const loadPosterCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    const raw = sessionStorage.getItem(POSTER_CACHE_KEY)
    if (raw) {
      posterCache.value = JSON.parse(raw)
    }
  } catch {
    /* ignore */
  }
}

const savePosterCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(POSTER_CACHE_KEY, JSON.stringify(posterCache.value))
  } catch {
    /* ignore */
  }
}

loadPosterCache()

// Get all unique labels from cache
const allLabels = computed(() => {
  const labels = new Set<string>()
  Object.values(labelCache.value).forEach(movieLabels => {
    movieLabels.forEach(label => labels.add(label))
  })
  return Array.from(labels).sort()
})

const filteredMovies = computed(() => {
  const query = searchQuery.value.toLowerCase().trim()
  let result = movies.value

  // Filter by search term
  if (query) {
    result = result.filter(
      m => m.title.toLowerCase().includes(query) || (m.year && m.year.toString().includes(query))
    )
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

const totalPages = computed(() => {
  return Math.ceil(filteredMovies.value.length / posterLimit.value)
})

const limitedMovies = computed(() => {
  const start = (currentPage.value - 1) * posterLimit.value
  const end = start + posterLimit.value
  return filteredMovies.value.slice(start, end)
})

const nextPage = () => {
  if (currentPage.value < totalPages.value) {
    currentPage.value++
  }
}

const prevPage = () => {
  if (currentPage.value > 1) {
    currentPage.value--
  }
}

const progressPercent = computed(() => {
  if (selectedMovies.value.size === 0) return 0
  return (currentIndex.value / selectedMovies.value.size) * 100
})

// Computed property to merge cached posters with movie data
const moviesWithPosters = computed(() => {
  return limitedMovies.value.map(m => ({
    ...m,
    poster: posterCache.value[m.key] ?? m.poster ?? null
  }))
})

// Filter presets by selected template
const filteredPresets = computed(() => {
  if (!selectedTemplate.value) return presets.value
  return presets.value.filter(p => p.template_id === selectedTemplate.value)
})

const fetchMovies = async () => {
  loading.value = true
  error.value = null
  try {
    if (!moviesLoadedFlag.value) {
      const res = await fetch(`${apiBase}/api/movies`)
      if (!res.ok) throw new Error(`API error ${res.status}`)
      const data = (await res.json()) as Movie[]
      moviesCache.value = data
      moviesLoadedFlag.value = true
    }
    movies.value = moviesCache.value
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Failed to load movies'
  } finally {
    loading.value = false
  }
}

const fetchPosters = async () => {
  const missing = limitedMovies.value.filter(
    m => (!posterCache.value[m.key]) && !posterInFlight.has(m.key)
  )
  if (!missing.length) return

  missing.forEach(m => posterInFlight.add(m.key))
  const results = await Promise.all(
    missing.map(async m => {
      try {
        const posterUrl = `${apiBase}/api/movie/${m.key}/poster`
        const res = await fetch(posterUrl)
        if (res.ok) {
          return { key: m.key, url: posterUrl }
        }
        return { key: m.key, url: null }
      } catch {
        return { key: m.key, url: null }
      }
    })
  )
  results.forEach(r => {
    posterCache.value[r.key] = r.url
    posterInFlight.delete(r.key)
  })
  savePosterCache()
}

const fetchLabels = async (list: Movie[]) => {
  const missing = list.filter(m => !(m.key in labelCache.value) && !labelInFlight.has(m.key))
  if (!missing.length) return

  missing.forEach(m => labelInFlight.add(m.key))
  const results = await Promise.all(
    missing.map(async m => {
      try {
        const labelsRes = await fetch(`${apiBase}/api/movie/${m.key}/labels`)
        const labelsData = await labelsRes.json()
        return { key: m.key, labels: labelsData.labels || [] }
      } catch {
        return { key: m.key, labels: [] }
      }
    })
  )
  results.forEach(r => {
    labelCache.value[r.key] = r.labels
    labelInFlight.delete(r.key)
  })
  saveLabelCache()
}

const loadTemplatesAndPresets = async () => {
  try {
    // Load available templates from backend
    const templatesRes = await fetch(`${apiBase}/api/templates/list`)
    if (templatesRes.ok) {
      const templatesData = await templatesRes.json()
      templates.value = templatesData.templates || []
      console.log('Loaded templates:', templates.value)
    } else {
      console.error('Failed to load templates:', templatesRes.status)
      // Fallback to hardcoded templates if API fails
      templates.value = [
        { id: 'default', name: 'Default Poster' },
        { id: 'uniformlogo', name: 'Uniform Logo' }
      ]
    }

    // Load presets
    const presetsRes = await fetch(`${apiBase}/api/presets`)
    if (presetsRes.ok) {
      const presetsData = await presetsRes.json()
      console.log('Raw presets data:', presetsData)
      // Convert presets structure to flat array
      const allPresets: Preset[] = []
      Object.entries(presetsData).forEach(([templateId, data]: [string, any]) => {
        if (data.presets && Array.isArray(data.presets)) {
          data.presets.forEach((preset: any) => {
            allPresets.push({
              id: preset.id,
              name: preset.name,
              template_id: templateId
            })
          })
        }
      })
      presets.value = allPresets
      console.log('Loaded presets:', presets.value)
    } else {
      console.error('Failed to load presets:', presetsRes.status)
    }
  } catch (err) {
    console.error('Error loading templates/presets:', err)
    // Fallback to hardcoded templates
    templates.value = [
      { id: 'default', name: 'Default Poster' },
      { id: 'uniformlogo', name: 'Uniform Logo' }
    ]
  }
}

const toggleMovie = (key: string) => {
  if (selectedMovies.value.has(key)) {
    selectedMovies.value.delete(key)
  } else {
    selectedMovies.value.add(key)
  }
}

const selectAll = () => {
  selectedMovies.value = new Set(moviesWithPosters.value.map(m => m.key))
}

const deselectAll = () => {
  selectedMovies.value.clear()
}

const toggleLabelToRemove = (label: string) => {
  if (labelsToRemove.value.has(label)) {
    labelsToRemove.value.delete(label)
  } else {
    labelsToRemove.value.add(label)
  }
}

const processBatch = async () => {
  if (selectedMovies.value.size === 0 || !selectedTemplate.value) {
    showError('Please select movies and a template')
    return
  }

  if (!sendToPlex.value && !saveLocally.value) {
    showError('Please select at least one action (Send to Plex or Save locally)')
    return
  }

  processing.value = true
  currentIndex.value = 0
  statusOverlay.value = { visible: true, message: 'Starting batch…' }

  try {
    const ratingKeys = Array.from(selectedMovies.value)
    const selectedForStatus = selectedMoviesList.value

    const payload = {
      rating_keys: ratingKeys,
      template_id: selectedTemplate.value,
      preset_id: selectedPreset.value || undefined,
      options: {},
      send_to_plex: sendToPlex.value,
      save_locally: saveLocally.value,
      labels: sendToPlex.value ? Array.from(labelsToRemove.value) : []
    }

    // Simulate progress
    const progressInterval = setInterval(() => {
      const idx = Math.min(currentIndex.value, selectedMovies.value.size - 1)
      const movie = selectedForStatus[idx]
      if (movie) {
        statusOverlay.value = {
          visible: true,
          message: `Rendering ${movie.title}`,
          detail: sendToPlex.value && saveLocally.value
            ? 'Sending to Plex and saving locally'
            : sendToPlex.value
              ? 'Sending to Plex'
              : 'Saving locally'
        }
      }
      currentIndex.value = Math.min(currentIndex.value + 1, selectedMovies.value.size)
      if (currentIndex.value >= selectedMovies.value.size) {
        clearInterval(progressInterval)
      }
    }, 300)

    const response = await fetch(`${apiBase}/api/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    clearInterval(progressInterval)
    currentIndex.value = selectedMovies.value.size

    if (!response.ok) {
      throw new Error('Failed to process batch')
    }

    await response.json()

    let message = `Successfully processed ${selectedMovies.value.size} movies`
    if (sendToPlex.value && saveLocally.value) {
      message += ' (sent to Plex and saved locally)'
    } else if (sendToPlex.value) {
      message += ' (sent to Plex)'
    } else if (saveLocally.value) {
      message += ' (saved locally)'
    }
    success(message)
    statusOverlay.value = { visible: true, message }

    // Reset
    setTimeout(() => {
      processing.value = false
      selectedMovies.value.clear()
      selectedTemplate.value = ''
      selectedPreset.value = ''
      statusOverlay.value = { visible: false, message: '' }
    }, 1500)
  } catch (err) {
    showError(`Batch processing failed: ${err}`)
    console.error(err)
    processing.value = false
    statusOverlay.value = { visible: false, message: '' }
  }
}

// Preview navigation
const previewIndex = ref(0)

// Get all selected movies in order
const selectedMoviesList = computed(() => {
  const keys = Array.from(selectedMovies.value)
  return keys.map(key => moviesWithPosters.value.find(m => m.key === key)).filter(Boolean) as Movie[]
})

// Current movie being previewed
const currentPreviewMovie = computed(() => {
  if (selectedMoviesList.value.length === 0) return null
  return selectedMoviesList.value[previewIndex.value] || selectedMoviesList.value[0]
})

const nextPreview = () => {
  if (previewIndex.value < selectedMoviesList.value.length - 1) {
    previewIndex.value++
  }
}

const prevPreview = () => {
  if (previewIndex.value > 0) {
    previewIndex.value--
  }
}

const goToPreview = (index: number) => {
  previewIndex.value = index
}

// Reset preview index when selection changes
watch(selectedMovies, () => {
  previewIndex.value = 0
})

// Preview rendering
const previewImage = ref<string | null>(null)
const previewLoading = ref(false)
const previewCache = ref<Record<string, string>>({})

const fetchPreview = async () => {
  if (!currentPreviewMovie.value || !selectedTemplate.value) {
    previewImage.value = null
    return
  }

  const cacheKey = `${currentPreviewMovie.value.key}|${selectedTemplate.value}|${selectedPreset.value || 'none'}`
  if (previewCache.value[cacheKey]) {
    previewImage.value = previewCache.value[cacheKey]
    return
  }

  previewLoading.value = true
  try {
    const movie = currentPreviewMovie.value

    // Ensure we have a valid poster URL
    let posterUrl = movie.poster
    if (!posterUrl) {
      // Fetch the poster if not cached
      const posterRes = await fetch(`${apiBase}/api/movie/${movie.key}/poster?meta=1`)
      const posterData = await posterRes.json()
      if (posterData.url) {
        posterUrl = posterData.url.startsWith('http') ? posterData.url : `${apiBase}${posterData.url}`
      }
    }

    const payload = {
      template_id: selectedTemplate.value,
      background_url: posterUrl || '',
      logo_url: null,
      options: {},
      preset_id: selectedPreset.value || undefined,
      movie_title: movie.title,
      movie_year: movie.year ? Number(movie.year) : undefined
    }

    const response = await fetch(`${apiBase}/api/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (response.ok) {
      const data = await response.json()
      const img = `data:image/jpeg;base64,${data.image_base64}`
      previewImage.value = img
      previewCache.value[cacheKey] = img
    } else {
      console.error('Preview response not OK:', response.status)
      previewImage.value = null
    }
  } catch (err) {
    console.error('Preview failed:', err)
    previewImage.value = null
  } finally {
    previewLoading.value = false
  }
}

// Watch for changes to fetch posters and labels
watch(moviesWithPosters, (list) => {
  fetchPosters()
  fetchLabels(list)
})

// Reset to page 1 when filters change
watch([searchQuery, filterLabel, posterLimit], () => {
  currentPage.value = 1
})

// Ensure current page doesn't exceed total pages
watch(totalPages, () => {
  if (currentPage.value > totalPages.value) {
    currentPage.value = Math.max(1, totalPages.value)
  }
})

// Clear preset when template changes
watch(selectedTemplate, () => {
  selectedPreset.value = ''
  previewCache.value = {}
  fetchPreview()
})

// Update preview when preset or selected movie changes
watch(selectedPreset, () => {
  previewCache.value = {}
  fetchPreview()
})

watch(currentPreviewMovie, () => {
  fetchPreview()
})

onMounted(async () => {
  await Promise.all([fetchMovies(), loadTemplatesAndPresets()])
  fetchPosters()
  fetchLabels(movies.value)
})
</script>

<template>
  <div class="batch-edit-view">
    <!-- Top Controls -->
    <div class="controls-panel">
      <h2>Batch Edit</h2>

      <!-- Template & Preset Selection -->
      <div class="selection-row">
        <div class="form-group">
          <label>Template</label>
          <select v-model="selectedTemplate" class="form-control">
            <option value="">Select a template...</option>
            <option v-for="tpl in templates" :key="tpl.id" :value="tpl.id">
              {{ tpl.name }}
            </option>
          </select>
        </div>

        <div class="form-group">
          <label>Preset</label>
          <select v-model="selectedPreset" class="form-control" :class="{ 'disabled-select': !selectedTemplate }" :disabled="!selectedTemplate">
            <option value="">{{ selectedTemplate ? 'Select a preset...' : 'Select a template first' }}</option>
            <option
              v-for="preset in filteredPresets"
              :key="preset.id"
              :value="preset.id"
            >
              {{ preset.name }}
            </option>
          </select>
        </div>
      </div>

      <!-- Actions -->
      <div class="actions-row">
        <div class="checkboxes">
          <label class="checkbox-label">
            <input type="checkbox" v-model="sendToPlex" />
            Send to Plex
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="saveLocally" />
            Save locally
          </label>
        </div>

        <!-- Label Removal Selector -->
        <div v-if="sendToPlex && allLabels.length > 0" class="label-selector">
          <label class="label-selector-title">Select labels to remove:</label>
          <div class="label-options">
            <label
              v-for="label in allLabels"
              :key="label"
              class="checkbox-label small"
            >
              <input
                type="checkbox"
                :checked="labelsToRemove.has(label)"
                @change="toggleLabelToRemove(label)"
              />
              {{ label }}
            </label>
          </div>
        </div>

        <button
          class="btn-process"
          @click="processBatch"
          :disabled="selectedMovies.size === 0 || !selectedTemplate || !selectedPreset || (!sendToPlex && !saveLocally) || processing"
        >
          <span v-if="!processing">Process {{ selectedMovies.size }} Movies</span>
          <span v-else>Processing {{ currentIndex }} / {{ selectedMovies.size }}...</span>
        </button>
      </div>

      <!-- Progress Bar -->
      <div v-if="processing" class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
    </div>

    <!-- Movie Selection Controls -->
    <div class="movie-controls">
      <div class="controls-left">
        <h3>{{ selectedMovies.size }} of {{ moviesWithPosters.length }} selected</h3>
        <button class="btn-small" @click="selectAll">Select All</button>
        <button class="btn-small" @click="deselectAll">Deselect All</button>
        <span v-if="filteredMovies.length > posterLimit" class="limit-notice">
          Showing {{ posterLimit }} of {{ filteredMovies.length }} movies
        </span>
      </div>

      <div class="controls-right">
        <div class="limit-control">
          <label for="poster-limit">Show:</label>
          <select id="poster-limit" v-model.number="posterLimit" class="filter-select">
            <option :value="25">25 posters</option>
            <option :value="50">50 posters</option>
            <option :value="100">100 posters</option>
            <option :value="200">200 posters</option>
            <option :value="500">500 posters</option>
          </select>
        </div>
        <select v-model="filterLabel" class="filter-select">
          <option value="">All Labels</option>
          <option v-for="label in allLabels" :key="label" :value="label">
            {{ label }}
          </option>
        </select>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Filter movies..."
          class="filter-input"
        />
      </div>
    </div>

    <!-- Content Area with Grid and Preview -->
    <div class="content-area">
      <!-- Movie Grid Container -->
      <div class="grid-container">
        <div v-if="loading" class="loading">Loading movies...</div>
        <div v-else-if="error" class="error">{{ error }}</div>
        <div v-else class="movie-grid">
          <div
            v-for="movie in moviesWithPosters"
            :key="movie.key"
            class="movie-card"
            :class="{ selected: selectedMovies.has(movie.key) }"
            @click="toggleMovie(movie.key)"
          >
            <div class="checkbox-overlay">
              <input
                type="checkbox"
                :checked="selectedMovies.has(movie.key)"
                @click.stop="toggleMovie(movie.key)"
                class="movie-checkbox"
              />
            </div>
            <div class="poster">
              <img
                :src="movie.poster || `/api/movie/${movie.key}/poster?w=200`"
                :alt="movie.title"
                loading="lazy"
              />
            </div>
            <div class="movie-info">
              <p class="title">{{ movie.title }}</p>
              <p class="year">{{ movie.year }}</p>
            </div>
          </div>
        </div>

        <!-- Pagination Controls -->
        <div v-if="!loading && !error && totalPages > 1" class="pagination-controls">
          <button class="page-btn" @click="prevPage" :disabled="currentPage === 1">
            ← Previous
          </button>
          <span class="page-info">
            Page {{ currentPage }} of {{ totalPages }}
          </span>
          <button class="page-btn" @click="nextPage" :disabled="currentPage === totalPages">
            Next →
          </button>
        </div>
      </div>

      <!-- Preview Sidebar -->
      <div v-if="currentPreviewMovie" class="preview-sidebar">
        <h3>Preview</h3>
        <div class="preview-poster">
          <div v-if="previewLoading" class="preview-loading">Rendering...</div>
          <img
            v-else-if="previewImage"
            :src="previewImage"
            :alt="currentPreviewMovie.title"
          />
          <img
            v-else
            :src="currentPreviewMovie.poster || `/api/movie/${currentPreviewMovie.key}/poster`"
            :alt="currentPreviewMovie.title"
          />
        </div>

        <!-- Navigation Controls -->
        <div v-if="selectedMoviesList.length > 1" class="preview-nav">
          <button
            class="nav-btn"
            @click="prevPreview"
            :disabled="previewIndex === 0"
          >
            ← Prev
          </button>
          <span class="nav-counter">{{ previewIndex + 1 }} / {{ selectedMoviesList.length }}</span>
          <button
            class="nav-btn"
            @click="nextPreview"
            :disabled="previewIndex === selectedMoviesList.length - 1"
          >
            Next →
          </button>
        </div>

        <div class="preview-info">
          <p class="preview-title">{{ currentPreviewMovie.title }}</p>
          <p class="preview-year">{{ currentPreviewMovie.year }}</p>
          <p v-if="!selectedTemplate" class="preview-hint">Select a template to preview</p>
          <p v-else-if="!selectedPreset" class="preview-hint">Preset optional - preview will use template defaults</p>
        </div>

        <!-- Movie List -->
        <div v-if="selectedMoviesList.length > 1" class="preview-list">
          <h4>Selected Movies</h4>
          <div class="movie-list-scroll">
            <button
              v-for="(movie, index) in selectedMoviesList"
              :key="movie.key"
              :class="['movie-list-item', { active: index === previewIndex }]"
              @click="goToPreview(index)"
            >
              <span class="list-item-number">{{ index + 1 }}</span>
              <span class="list-item-title">{{ movie.title }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div v-if="statusOverlay.visible" class="status-overlay">
    <div class="status-card">
      <div class="spinner"></div>
      <div>
        <p class="status-title">{{ statusOverlay.message }}</p>
        <p v-if="statusOverlay.detail" class="status-detail">{{ statusOverlay.detail }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.batch-edit-view {
  padding: 1.5rem;
  max-width: 100%;
}

.controls-panel {
  background: var(--surface, #1a1f2e);
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  border: 1px solid var(--border, #2a2f3e);
}

.controls-panel h2 {
  margin: 0 0 1rem 0;
  color: var(--text-primary, #fff);
}

.selection-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
}

.form-group label {
  color: var(--text-primary, #fff);
  margin-bottom: 0.5rem;
  font-weight: 500;
  font-size: 0.9rem;
}

.form-control {
  padding: 0.75rem;
  background: var(--input-bg, #242933);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  font-size: 1rem;
}

.form-control:focus {
  outline: none;
  border-color: var(--accent, #3dd6b7);
}

.actions-row {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.actions-row > :last-child {
  align-self: flex-end;
}

.checkboxes {
  display: flex;
  gap: 1.5rem;
  align-items: center;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-primary, #fff);
  cursor: pointer;
  font-size: 0.95rem;
}

.checkbox-label.sub-option {
  margin-left: 1rem;
  color: var(--text-secondary, #aaa);
  font-size: 0.9rem;
}

.checkbox-label input[type='checkbox'] {
  cursor: pointer;
  width: 16px;
  height: 16px;
  accent-color: var(--accent, #3dd6b7);
}

.btn-process {
  padding: 0.75rem 2rem;
  background: var(--accent, #3dd6b7);
  color: #000;
  border: none;
  border-radius: 4px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn-process:hover:not(:disabled) {
  background: #2bc4a3;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(61, 214, 183, 0.3);
}

.btn-process:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.progress-bar {
  width: 100%;
  height: 6px;
  background: var(--border, #2a2f3e);
  border-radius: 3px;
  overflow: hidden;
  margin-top: 1rem;
}

.progress-fill {
  height: 100%;
  background: var(--accent, #3dd6b7);
  transition: width 0.3s ease;
}

.movie-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: var(--surface, #1a1f2e);
  border-radius: 8px;
  border: 1px solid var(--border, #2a2f3e);
}

.controls-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.controls-left h3 {
  margin: 0;
  color: var(--text-primary, #fff);
  font-size: 1rem;
}

.btn-small {
  padding: 0.5rem 1rem;
  background: var(--surface-alt, #242933);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-small:hover {
  background: var(--accent, #3dd6b7);
  color: #000;
  border-color: var(--accent, #3dd6b7);
}

.controls-right {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
}

.limit-control {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.limit-control label {
  color: var(--text-secondary, #aaa);
  font-size: 0.9rem;
  font-weight: 500;
  white-space: nowrap;
}

.limit-notice {
  color: var(--accent, #3dd6b7);
  font-size: 0.85rem;
  font-weight: 500;
  margin-left: 0.5rem;
}

.filter-select {
  padding: 0.6rem 1rem;
  background: var(--input-bg, #242933);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  font-size: 0.9rem;
  min-width: 150px;
}

.filter-select:focus {
  outline: none;
  border-color: var(--accent, #3dd6b7);
}

.filter-input {
  padding: 0.6rem 1rem;
  background: var(--input-bg, #242933);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  font-size: 0.9rem;
  min-width: 300px;
}

.filter-input:focus {
  outline: none;
  border-color: var(--accent, #3dd6b7);
}

.loading,
.error {
  padding: 2rem;
  text-align: center;
  color: var(--text-secondary, #aaa);
  font-size: 1.1rem;
}

.error {
  color: #ff6b6b;
}

.content-area {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 1.5rem;
}

.grid-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.movie-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 1rem;
}

.pagination-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 1rem;
  background: var(--surface, #1a1f2e);
  border-radius: 8px;
  border: 1px solid var(--border, #2a2f3e);
}

.page-btn {
  padding: 0.6rem 1.2rem;
  background: var(--accent, #3dd6b7);
  color: #000;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 100px;
}

.page-btn:hover:not(:disabled) {
  background: #2bc4a3;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(61, 214, 183, 0.3);
}

.page-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
  transform: none;
}

.page-info {
  color: var(--text-primary, #fff);
  font-size: 0.95rem;
  font-weight: 500;
  min-width: 120px;
  text-align: center;
}

.preview-sidebar {
  background: var(--surface, #1a1f2e);
  border-radius: 8px;
  padding: 1.5rem;
  border: 1px solid var(--border, #2a2f3e);
  position: sticky;
  top: 1.5rem;
  height: fit-content;
}

.preview-sidebar h3 {
  margin: 0 0 1rem 0;
  color: var(--text-primary, #fff);
  font-size: 1.1rem;
}

.preview-poster {
  aspect-ratio: 2/3;
  overflow: hidden;
  background: var(--surface-alt, #242933);
  border-radius: 6px;
  margin-bottom: 1rem;
  position: relative;
}

.preview-poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--text-secondary, #aaa);
  font-size: 0.9rem;
}

.preview-info {
  padding: 0.5rem 0;
}

.preview-title {
  margin: 0 0 0.25rem 0;
  color: var(--text-primary, #fff);
  font-size: 1rem;
  font-weight: 600;
}

.preview-year {
  margin: 0;
  color: var(--text-secondary, #aaa);
  font-size: 0.9rem;
}

.preview-hint {
  margin: 0.5rem 0 0 0;
  color: var(--accent, #3dd6b7);
  font-size: 0.85rem;
  font-style: italic;
}

.movie-card {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: var(--surface, #1a1f2e);
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.movie-card:hover {
  border-color: rgba(61, 214, 183, 0.3);
  transform: translateY(-4px);
}

.movie-card.selected {
  border-color: var(--accent, #3dd6b7);
  box-shadow: 0 0 20px rgba(61, 214, 183, 0.3);
}

.checkbox-overlay {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 10;
}

.movie-checkbox {
  cursor: pointer;
  width: 20px;
  height: 20px;
  accent-color: var(--accent, #3dd6b7);
}

.poster {
  aspect-ratio: 2/3;
  overflow: hidden;
  background: var(--surface-alt, #242933);
}

.poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.movie-info {
  padding: 0.75rem;
}

.title {
  margin: 0 0 0.25rem 0;
  color: var(--text-primary, #fff);
  font-size: 0.9rem;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.year {
  margin: 0;
  color: var(--text-secondary, #aaa);
  font-size: 0.85rem;
}

/* Disabled select styling */
.disabled-select {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Label selector */
.label-selector {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  background: var(--surface-alt, #242933);
  border-radius: 6px;
  border: 1px solid var(--border, #2a2f3e);
  flex: 1;
}

.label-selector-title {
  color: var(--text-primary, #fff);
  font-weight: 500;
  font-size: 0.9rem;
  margin: 0;
}

.label-options {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.checkbox-label.small {
  font-size: 0.85rem;
  color: var(--text-secondary, #ccc);
}

/* Preview navigation */
.preview-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 0.75rem;
  padding: 0.5rem;
  background: var(--surface-alt, #242933);
  border-radius: 6px;
}

.nav-btn {
  padding: 0.5rem 1rem;
  background: var(--accent, #3dd6b7);
  color: #000;
  border: none;
  border-radius: 4px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-btn:hover:not(:disabled) {
  background: #2bc4a3;
  transform: translateY(-1px);
}

.nav-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
  transform: none;
}

.nav-counter {
  color: var(--text-secondary, #aaa);
  font-size: 0.85rem;
  font-weight: 500;
}

/* Preview movie list */
.preview-list {
  margin-top: 1rem;
  border-top: 1px solid var(--border, #2a2f3e);
  padding-top: 1rem;
}

.preview-list h4 {
  margin: 0 0 0.75rem 0;
  color: var(--text-primary, #fff);
  font-size: 0.9rem;
  font-weight: 600;
}

.movie-list-scroll {
  max-height: 300px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.movie-list-scroll::-webkit-scrollbar {
  width: 6px;
}

.movie-list-scroll::-webkit-scrollbar-track {
  background: var(--surface-alt, #242933);
  border-radius: 3px;
}

.movie-list-scroll::-webkit-scrollbar-thumb {
  background: var(--border, #2a2f3e);
  border-radius: 3px;
}

.movie-list-scroll::-webkit-scrollbar-thumb:hover {
  background: var(--accent, #3dd6b7);
}

.movie-list-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s;
  color: var(--text-secondary, #aaa);
  font-size: 0.85rem;
}

.movie-list-item:hover {
  background: rgba(61, 214, 183, 0.08);
  border-color: rgba(61, 214, 183, 0.2);
  color: var(--text-primary, #fff);
}

.movie-list-item.active {
  background: rgba(61, 214, 183, 0.15);
  border-color: rgba(61, 214, 183, 0.4);
  color: var(--accent, #3dd6b7);
  font-weight: 600;
}

.list-item-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  background: var(--surface-alt, #242933);
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
  flex-shrink: 0;
}

.movie-list-item.active .list-item-number {
  background: var(--accent, #3dd6b7);
  color: #000;
}

.list-item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-overlay {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 2000;
}

.status-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: rgba(0, 0, 0, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #eef2ff;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: var(--accent, #3dd6b7);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

.status-title {
  margin: 0;
  font-weight: 600;
  font-size: 0.95rem;
}

.status-detail {
  margin: 2px 0 0 0;
  font-size: 0.8rem;
  color: #cdd4e0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
