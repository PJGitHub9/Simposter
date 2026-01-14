<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getApiBase } from '@/services/apiBase'
import { useNotification } from '@/composables/useNotification'
import { useTvShows } from '../composables/useTvShows'
import { useSettingsStore } from '@/stores/settings'

// Define props and emits to avoid Vue warnings
defineProps<{
  search?: string
}>()

defineEmits<{
  select: [value: any]
}>()

type TvShow = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
  seasons?: Season[]
}

type Season = {
  key: string
  title: string
  index: number
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

type PosterStatusEntry = {
  template_id?: string | null
  preset_id?: string | null
  created_at?: string | null
}

type PosterStatus = {
  sent: PosterStatusEntry | null
  saved: PosterStatusEntry | null
}

const { success, error: showError } = useNotification()
const { tvShows: tvShowsCache, tvShowsLoaded: tvShowsLoadedFlag } = useTvShows()
const settings = useSettingsStore()

const tvShows = ref<TvShow[]>(tvShowsCache.value)
const includeSeasons = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const selectedShows = ref<Set<string>>(new Set())
const searchQuery = ref('')
const filterLabel = ref<string>('')
const sortBy = ref<'title' | 'year' | 'addedAt'>('title')
const sortOrder = ref<'asc' | 'desc'>('asc')
const posterLimit = ref<number>(50)
const currentPage = ref<number>(1)
const currentSeasonIndex = ref<number>(0)

// Get current library from route query params
const route = useRoute()
const currentLibrary = computed(() => (route.query.library as string) || '')

// Label cache (library-specific)
const getLabelsCacheKey = () => {
  return `simposter-labels-cache-${currentLibrary.value || 'default'}`
}
const labelCache = ref<Record<string, string[]>>({})
const labelInFlight = new Set<string>()
const allAvailableLabels = ref<string[]>([]) // All labels available in current library

const loadLabelCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    const raw = sessionStorage.getItem(getLabelsCacheKey())
    if (raw) {
      const cachedLabels = JSON.parse(raw)
      // Only load labels for movies that are actually in the current library
      const currentMovieKeys = new Set(tvShows.value.map(m => m.key))
      const filteredLabels: Record<string, string[]> = {}
      
      Object.entries(cachedLabels).forEach(([movieKey, labels]) => {
        if (currentMovieKeys.has(movieKey)) {
          filteredLabels[movieKey] = labels as string[]
        }
      })
      
      labelCache.value = filteredLabels
    }
  } catch {
    /* ignore */
  }
}

const saveLabelCache = () => {
  if (typeof sessionStorage === 'undefined') return
  // Only save if we have a valid library ID
  if (!currentLibrary.value) return
  try {
    sessionStorage.setItem(getLabelsCacheKey(), JSON.stringify(labelCache.value))
  } catch {
    /* ignore */
  }
}

// Reload label cache when library changes
watch(currentLibrary, async (newLib, oldLib) => {
  if (newLib === oldLib) return // Avoid unnecessary reloads
  
  // Clear all library-specific state completely
  labelCache.value = {}
  tvShows.value = []
  selectedShows.value.clear()
  currentPage.value = 1
  posterCache.value = {}
  posterStatus.value = {}
  tvShowsLoadedFlag.value = false
  labelsToRemove.value = new Set()
  
  // Clear any stale data from previous library to prevent contamination
  if (oldLib && typeof sessionStorage !== 'undefined') {
    const oldLabelKey = `simposter-labels-cache-${oldLib}`
    const oldPosterKey = `simposter-poster-cache-${oldLib}`
    // Don't remove from sessionStorage, but clear from memory
  }
  
  // Load caches for new library only if we have a valid library ID
  if (newLib) {
    await fetchMovies()
    // Use efficient bulk cache loading first
    await fetchAllAvailableLabels() // Fetch all labels for library first
    await fetchLabelsFromCache()
    loadLabelCache()
    loadPosterCache()
    await fetchPosterStatus()
    syncLabelsFromSettings()
  }
})

// Template/preset selection
const templates = ref<Template[]>([])
const presets = ref<Preset[]>([])
const presetsDataFull = ref<Record<string, any>>({}) // Store full presets data including options
const selectedTemplate = ref('')
const selectedPreset = ref('')
const sendToPlex = ref(true)
const saveLocally = ref(false)
const sentFilter = ref<'all' | 'sent' | 'unsent'>('all')
const savedFilter = ref<'all' | 'saved' | 'unsaved'>('all')
const labelsToRemove = ref<Set<string>>(new Set())
const processing = ref(false)
const currentIndex = ref(0)
const statusOverlay = ref<{ visible: boolean; message: string; detail?: string }>({ visible: false, message: '' })
const posterStatus = ref<Record<string, PosterStatus>>({})
const statusLoading = ref(false)

const syncLabelsFromSettings = () => {
  const libId = currentLibrary.value || 'default'
  const defaults = settings.defaultLabelsToRemove.value?.[libId]
  labelsToRemove.value = new Set(Array.isArray(defaults) ? defaults : [])
}

const apiBase = getApiBase()

// Poster cache - library-specific
const getPosterCacheKey = () => {
  return `simposter-poster-cache-${currentLibrary.value || 'default'}`
}
const posterCache = ref<Record<string, string | null>>({})
const posterInFlight = new Set<string>()

const loadPosterCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    const raw = sessionStorage.getItem(getPosterCacheKey())
    if (raw) {
      const cachedPosters = JSON.parse(raw)
      // Only load posters for movies that are actually in the current library
      const currentMovieKeys = new Set(tvShows.value.map(m => m.key))
      const filteredPosters: Record<string, string | null> = {}
      
      Object.entries(cachedPosters).forEach(([movieKey, posterUrl]) => {
        if (currentMovieKeys.has(movieKey)) {
          filteredPosters[movieKey] = posterUrl as string | null
        }
      })
      
      posterCache.value = filteredPosters
    }
  } catch {
    /* ignore */
  }
}

const savePosterCache = () => {
  if (typeof sessionStorage === 'undefined') return
  // Only save if we have a valid library ID
  if (!currentLibrary.value) return
  try {
    sessionStorage.setItem(getPosterCacheKey(), JSON.stringify(posterCache.value))
  } catch {
    /* ignore */
  }
}

// Get all unique labels from cache
const allLabels = computed(() => {
  // Prefer all available labels from library if we have them
  if (allAvailableLabels.value.length > 0) {
    return allAvailableLabels.value
  }
  // Fallback to labels from loaded shows
  const labels = new Set<string>()
  Object.values(labelCache.value).forEach(movieLabels => {
    movieLabels.forEach(label => labels.add(label))
  })
  return Array.from(labels).sort()
})

const filteredMovies = computed(() => {
  const query = searchQuery.value.toLowerCase().trim()
  let result = tvShows.value

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

  // Filter by sent status
  if (sentFilter.value !== 'all') {
    result = result.filter(m => {
      const hasSent = !!posterStatus.value[m.key]?.sent
      return sentFilter.value === 'sent' ? hasSent : !hasSent
    })
  }

  // Filter by saved status
  if (savedFilter.value !== 'all') {
    result = result.filter(m => {
      const hasSaved = !!posterStatus.value[m.key]?.saved
      return savedFilter.value === 'saved' ? hasSaved : !hasSaved
    })
  }

  return result
})

const sortedMovies = computed(() => {
  const list = [...filteredMovies.value]
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

const totalPages = computed(() => {
  return Math.ceil(sortedMovies.value.length / posterLimit.value)
})

const limitedMovies = computed(() => {
  const start = (currentPage.value - 1) * posterLimit.value
  const end = start + posterLimit.value
  return sortedMovies.value.slice(start, end)
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
  if (selectedShows.value.size === 0) return 0
  return (currentIndex.value / selectedShows.value.size) * 100
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

const templateNameMap = computed(() => {
  const map: Record<string, string> = {}
  templates.value.forEach(t => {
    map[t.id] = t.name || t.id
  })
  return map
})

const presetNameMap = computed(() => {
  const map: Record<string, string> = {}
  presets.value.forEach(p => {
    map[p.id] = p.name || p.id
  })
  return map
})

const getTemplateName = (id?: string | null) => {
  if (!id) return '—'
  return templateNameMap.value[id] || id
}

const getPresetName = (id?: string | null) => {
  if (!id) return '—'
  return presetNameMap.value[id] || id
}

const formatDate = (value?: string | null) => {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const getTemplatePresetText = (movieKey: string) => {
  const status = posterStatus.value[movieKey]
  const source = status?.sent || status?.saved
  const tpl = getTemplateName(source?.template_id)
  const pre = getPresetName(source?.preset_id)
  return `${tpl}/${pre}`
}

const getSentText = (movieKey: string) => {
  const sent = posterStatus.value[movieKey]?.sent
  return formatDate(sent?.created_at)
}

const getSavedText = (movieKey: string) => {
  const saved = posterStatus.value[movieKey]?.saved
  return formatDate(saved?.created_at)
}

const formatDateTime = (value?: string | null) => {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  })
}

const getSentTooltip = (movieKey: string) => {
  const sent = posterStatus.value[movieKey]?.sent
  return sent?.created_at ? `Sent on ${formatDateTime(sent.created_at)}` : 'Not sent'
}

const getSavedTooltip = (movieKey: string) => {
  const saved = posterStatus.value[movieKey]?.saved
  return saved?.created_at ? `Saved on ${formatDateTime(saved.created_at)}` : 'Not saved'
}

const fetchMovies = async () => {
  loading.value = true
  error.value = null
  try {
    if (!tvShowsLoadedFlag.value) {
      const res = await fetch(`${apiBase}/api/tv-shows${currentLibrary.value ? `?library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`)
      if (!res.ok) throw new Error(`API error ${res.status}`)
      const data = (await res.json()) as TvShow[]
      tvShowsCache.value = data
      tvShowsLoadedFlag.value = true
    }
    tvShows.value = tvShowsCache.value
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Failed to load TV shows'
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
        const posterUrl = `${apiBase}/api/tv-show/${m.key}/poster${currentLibrary.value ? `?library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`
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

const fetchAllAvailableLabels = async () => {
  try {
    if (!currentLibrary.value) {
      allAvailableLabels.value = []
      return
    }
    
    const res = await fetch(`${apiBase}/api/tv-shows/labels/all?library_id=${encodeURIComponent(currentLibrary.value)}`)
    if (res.ok) {
      const data = await res.json()
      allAvailableLabels.value = data.labels || []
      console.log(`[TvBatchEdit] Loaded ${allAvailableLabels.value.length} unique labels for library ${currentLibrary.value}`)
    }
  } catch (e) {
    console.warn('[TvBatchEdit] Failed to fetch all labels:', e)
  }
}

const fetchLabelsFromCache = async () => {
  try {
    // First, try to get labels from backend cache for the current library
    const cacheUrl = `${apiBase}/api/cache/movies${currentLibrary.value ? `?library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`
    const cacheRes = await fetch(cacheUrl)
    if (cacheRes.ok) {
      const cacheData = await cacheRes.json()
      const cachedMovies = cacheData.movies || []
      
      let labelsFound = 0
      cachedMovies.forEach((movie: any) => {
        if (movie.labels && movie.labels.length > 0) {
          labelCache.value[movie.rating_key] = movie.labels
          labelsFound++
        }
      })
      
      console.log(`[BatchEdit] Loaded ${labelsFound} label sets from backend cache for library ${currentLibrary.value}`)
      saveLabelCache()
    }
  } catch (e) {
    console.warn('[BatchEdit] Failed to load labels from cache:', e)
  }
}

const fetchLabels = async (list: TvShow[]) => {
  const missing = list.filter(m => !(m.key in labelCache.value) && !labelInFlight.has(m.key))
  if (!missing.length) return

  // Mark all missing movies as in flight
  missing.forEach(m => labelInFlight.add(m.key))

  try {
    // Use bulk endpoint for efficiency if we have many movies
    if (missing.length > 5) {
      const bulkRes = await fetch(`${apiBase}/api/movies/labels/bulk`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(missing.map(m => m.key))
      })
      
      if (bulkRes.ok) {
        const bulkData = await bulkRes.json()
        Object.entries(bulkData.labels || {}).forEach(([movieKey, labels]) => {
          labelCache.value[movieKey] = labels as string[]
          labelInFlight.delete(movieKey)
        })
        saveLabelCache()
        console.log(`[BatchEdit] Loaded ${Object.keys(bulkData.labels || {}).length} label sets via bulk endpoint`)
        return
      }
    }

    // Fall back to individual requests for smaller sets or if bulk fails
    const results = await Promise.all(
      missing.map(async m => {
        try {
          const labelsRes = await fetch(`${apiBase}/api/movie/${m.key}/labels${currentLibrary.value ? `?library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`)
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
  } catch (error) {
    // Clean up in flight status on any error
    missing.forEach(m => labelInFlight.delete(m.key))
    console.error('Failed to fetch labels:', error)
  }
}

const fetchPosterStatus = async () => {
  if (!currentLibrary.value) return
  statusLoading.value = true
  try {
    const ratingKeys = tvShowsCache.value.map(m => m.key)
    if (ratingKeys.length === 0) {
      posterStatus.value = {}
      return
    }

    const res = await fetch(`${apiBase}/api/poster-status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        library_id: currentLibrary.value,
        rating_keys: ratingKeys,
      }),
    })

    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    const statusMap: Record<string, PosterStatus> = {}
    Object.entries(data.status || {}).forEach(([key, val]) => {
      const entry = val as { sent?: PosterStatusEntry | null; saved?: PosterStatusEntry | null }
      statusMap[key] = {
        sent: entry.sent || null,
        saved: entry.saved || null,
      }
    })
    posterStatus.value = statusMap
  } catch (err) {
    console.error('Failed to fetch poster status', err)
  } finally {
    statusLoading.value = false
  }
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
      presetsDataFull.value = presetsData // Store full data for later use
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
  if (selectedShows.value.has(key)) {
    selectedShows.value.delete(key)
  } else {
    selectedShows.value.add(key)
  }
}

const selectAll = () => {
  const merged = new Set(selectedShows.value)
  moviesWithPosters.value.forEach(m => merged.add(m.key))
  selectedShows.value = merged
}

const deselectAll = () => {
  selectedShows.value.clear()
}

const toggleLabelToRemove = (label: string) => {
  if (labelsToRemove.value.has(label)) {
    labelsToRemove.value.delete(label)
  } else {
    labelsToRemove.value.add(label)
  }
}

const processBatch = async () => {
  if (selectedShows.value.size === 0 || !selectedTemplate.value) {
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
    const ratingKeys = Array.from(selectedShows.value)
    const selectedForStatus = selectedShowsList.value

    const payload = {
      rating_keys: ratingKeys,
      template_id: selectedTemplate.value,
      preset_id: selectedPreset.value || undefined,
      options: {},
      send_to_plex: sendToPlex.value,
      save_locally: saveLocally.value,
      labels: sendToPlex.value ? Array.from(labelsToRemove.value) : [],
      library_id: currentLibrary.value || undefined,
      include_seasons: includeSeasons.value
    }

    // Simulate progress
    const progressInterval = setInterval(() => {
      const idx = Math.min(currentIndex.value, selectedShows.value.size - 1)
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
      currentIndex.value = Math.min(currentIndex.value + 1, selectedShows.value.size)
      if (currentIndex.value >= selectedShows.value.size) {
        clearInterval(progressInterval)
      }
    }, 300)

    const response = await fetch(`${apiBase}/api/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    clearInterval(progressInterval)
    currentIndex.value = selectedShows.value.size

    if (!response.ok) {
      throw new Error('Failed to process batch')
    }

    await response.json()

    let message = `Successfully processed ${selectedShows.value.size} movies`
    if (sendToPlex.value && saveLocally.value) {
      message += ' (sent to Plex and saved locally)'
    } else if (sendToPlex.value) {
      message += ' (sent to Plex)'
    } else if (saveLocally.value) {
      message += ' (saved locally)'
    }
    success(message)
    statusOverlay.value = { visible: true, message }

    // Refresh status for sent/saved indicators
    await fetchPosterStatus()

    // Clear poster cache to force reload of updated posters from Plex
    posterCache.value = {}
    posterInFlight.clear()

    // Refetch posters to show the new Simposter posters
    await fetchPosters()

    // Reset
    setTimeout(() => {
      processing.value = false
      selectedShows.value.clear()
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

// Get all selected movies (across pages) in selection order, merging cached posters
const selectedShowsList = computed(() => {
  const keys = Array.from(selectedShows.value)
  const byKey = new Map(tvShows.value.map(m => [m.key, m]))
  return keys
    .map((key) => {
      const base = byKey.get(key)
      if (!base) return null
      const poster = posterCache.value[key] ?? base.poster ?? null
      return { ...base, poster }
    })
    .filter(Boolean) as TvShow[]
})

// Current movie being previewed
const currentPreviewMovie = computed(() => {
  if (selectedShowsList.value.length === 0) return null
  return selectedShowsList.value[previewIndex.value] || selectedShowsList.value[0]
})

const nextPreview = () => {
  if (previewIndex.value < selectedShowsList.value.length - 1) {
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
watch(selectedShows, () => {
  previewIndex.value = 0
})

watch(selectedShowsList, (list) => {
  if (previewIndex.value >= list.length) {
    previewIndex.value = Math.max(0, list.length - 1)
  }

  // Preload all selected shows in background for instant navigation
  if (list.length > 0 && selectedTemplate.value) {
    console.log('[TV BATCH PREVIEW] Preloading', list.length, 'shows in background')
    // Preload in batches to avoid overwhelming the server
    list.forEach((show, idx) => {
      setTimeout(() => {
        preloadShowPreview(show)
      }, idx * 300) // Stagger requests by 300ms each
    })
  }
})

// Season cycling for TV shows
const currentSeasons = ref<Season[]>([])
const loadingSeasons = ref(false)
const hasNavigatedToSeason = ref(false) // Track if user has navigated to a season

const fetchSeasons = async (showKey: string) => {
  if (!includeSeasons.value) {
    currentSeasons.value = []
    return
  }

  loadingSeasons.value = true
  try {
    const res = await fetch(`${apiBase}/api/tv-show/${showKey}/seasons${currentLibrary.value ? `?library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`)
    if (!res.ok) throw new Error(`Failed to fetch seasons`)
    const data = await res.json()

    // Add synthetic "Series" entry at the beginning
    const seriesEntry = {
      index: -1,
      key: showKey,
      title: 'Series',
      poster: currentPreviewMovie.value?.poster || null,
      isSeries: true
    }

    currentSeasons.value = [seriesEntry, ...(data.seasons || [])]
    currentSeasonIndex.value = 0
  } catch (err) {
    console.error('Failed to fetch seasons:', err)
    currentSeasons.value = []
  } finally {
    loadingSeasons.value = false
  }
}

const nextSeason = () => {
  if (currentSeasonIndex.value < currentSeasons.value.length - 1) {
    currentSeasonIndex.value++
    hasNavigatedToSeason.value = true
    // Schedule preload for next season after navigating
    if (selectedTemplate.value) {
      schedulePreload()
    }
  }
}

const prevSeason = () => {
  if (currentSeasonIndex.value > 0) {
    currentSeasonIndex.value--
    hasNavigatedToSeason.value = true
    // Schedule preload for next season after navigating
    if (selectedTemplate.value) {
      schedulePreload()
    }
  }
}

const currentSeason = computed(() => {
  if (!includeSeasons.value || currentSeasons.value.length === 0) return null
  const season = currentSeasons.value[currentSeasonIndex.value]
  // Return series entry (index -1) without requiring navigation
  // For actual seasons, require navigation to prevent auto-displaying first season
  if (season?.index === -1 || hasNavigatedToSeason.value) {
    return season
  }
  return null
})

// Watch for preview movie changes to fetch seasons
watch(currentPreviewMovie, async (newMovie, oldMovie) => {
  hasNavigatedToSeason.value = false // Reset navigation flag when changing shows
  if (newMovie && includeSeasons.value) {
    await fetchSeasons(newMovie.key)
  } else {
    currentSeasons.value = []
    currentSeasonIndex.value = 0
  }

  // Schedule background preload when a new movie is selected
  // Only if we actually changed movies and have a template selected
  if (newMovie && newMovie.key !== oldMovie?.key && selectedTemplate.value) {
    schedulePreload()
  }
})

// Watch for includeSeasons toggle
watch(includeSeasons, async (enabled) => {
  hasNavigatedToSeason.value = false // Reset navigation flag when toggling
  if (enabled && currentPreviewMovie.value) {
    await fetchSeasons(currentPreviewMovie.value.key)
    // Don't auto-select first season - let user navigate to it
    // This ensures series poster shows by default
    // Don't call fetchPreview() here - currentSeason will change when seasons load,
    // which will trigger watch(currentSeasonIndex) and call fetchPreview()
  } else {
    currentSeasons.value = []
    currentSeasonIndex.value = 0
    // When disabling seasons, we need to fetch the show-level preview
    previewCache.value = {}
    fetchPreview()
  }
})

// Preview rendering
const previewImage = ref<string | null>(null)
const previewLoading = ref(false)
const previewCache = ref<Record<string, string>>({})
let preloadTimeout: ReturnType<typeof setTimeout> | null = null
let currentPreviewAbortController: AbortController | null = null
let previewRequestId = 0

const cancelPreload = () => {
  if (preloadTimeout !== null) {
    clearTimeout(preloadTimeout)
    preloadTimeout = null
  }
}

const schedulePreload = () => {
  // Cancel any existing preload
  cancelPreload()

  // Start preload immediately (no delay) to prepare for navigation
  preloadTimeout = setTimeout(() => {
    console.log('[TV BATCH PREVIEW] Starting background preload for adjacent item')

    // Preload the next item in the list if available
    if (selectedShowsList.value.length > 1 && previewIndex.value < selectedShowsList.value.length - 1) {
      const nextShow = selectedShowsList.value[previewIndex.value + 1]
      preloadShowPreview(nextShow)
    }
  }, 500)
}

// Preload preview for a specific show in the background
const preloadShowPreview = async (show: any) => {
  if (!selectedTemplate.value) return

  console.log('[TV BATCH PREVIEW] Preloading show in background:', show.title)

  // Build the cache key for this show
  const libraryPart = currentLibrary.value ? `lib:${currentLibrary.value}` : 'no-lib'
  const seasonIdx = includeSeasons.value ? -1 : undefined // Always preload series entry first
  const cacheKey = includeSeasons.value
    ? `${libraryPart}|${show.key}|${selectedTemplate.value}|${selectedPreset.value || 'none'}|season:${seasonIdx}`
    : `${libraryPart}|${show.key}|${selectedTemplate.value}|${selectedPreset.value || 'none'}|show`

  // Skip if already cached
  if (previewCache.value[cacheKey]) {
    console.log('[TV BATCH PREVIEW] Preload skipped - already cached:', cacheKey)
    return
  }

  // Get poster_filter from preset if available
  let posterFilter = 'all'
  if (selectedPreset.value && selectedTemplate.value) {
    const templateData = presetsDataFull.value[selectedTemplate.value]
    if (templateData && templateData.presets) {
      const preset = templateData.presets.find((p: any) => p.id === selectedPreset.value)
      if (preset && preset.options) {
        posterFilter = preset.options.poster_filter || 'all'
      }
    }
  }

  // Fetch the correct poster using the select-poster endpoint
  let posterUrl = show.poster || ''

  // If we have a textless/text filter, use the select-poster endpoint
  if (posterFilter === 'textless' || posterFilter === 'text') {
    console.log('[TV BATCH PREVIEW] Preload fetching filtered poster with filter:', posterFilter)
    const selectParams = new URLSearchParams({
      poster_filter: posterFilter,
      ...(currentLibrary.value && { library_id: currentLibrary.value })
    })

    try {
      const selectRes = await fetch(`${apiBase}/api/tv-show/${show.key}/select-poster?${selectParams}`)
      if (selectRes.ok) {
        const selectData = await selectRes.json()
        if (selectData.url) {
          posterUrl = selectData.url
          console.log('[TV BATCH PREVIEW] Preload selected filtered poster:', posterUrl?.substring(0, 100))
        } else {
          console.warn('[TV BATCH PREVIEW] Preload poster selection returned no URL, using fallback')
        }
      } else {
        console.warn('[TV BATCH PREVIEW] Preload poster selection failed, using fallback')
      }
    } catch (err) {
      console.error('[TV BATCH PREVIEW] Preload error selecting poster:', err)
    }
  }

  // Build the payload with correct options and selected poster
  const payload = {
    template_id: selectedTemplate.value,
    background_url: posterUrl,
    logo_url: null,
    options: { poster_filter: posterFilter },
    preset_id: selectedPreset.value || undefined,
    movie_title: show.title,
    movie_year: show.year ? Number(show.year) : undefined,
    tv_show_rating_key: show.key
  }

  console.log('[TV BATCH PREVIEW] Preload payload with poster_filter:', posterFilter)

  try {
    const response = await fetch(`${apiBase}/api/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (response.ok) {
      const data = await response.json()
      const img = `data:image/jpeg;base64,${data.image_base64}`
      previewCache.value[cacheKey] = img
      console.log('[TV BATCH PREVIEW] Preload completed for:', show.title)
    }
  } catch (err) {
    console.log('[TV BATCH PREVIEW] Preload failed for:', show.title, err)
  }
}

const fetchPreview = async (isPreload = false) => {
  console.log('[TV BATCH PREVIEW] fetchPreview called:', {
    isPreload,
    hasMovie: !!currentPreviewMovie.value,
    hasTemplate: !!selectedTemplate.value,
    includeSeasons: includeSeasons.value,
    currentSeason: currentSeason.value?.title || 'null'
  })

  // If this is a manual fetch (not preload), cancel any scheduled preload
  if (!isPreload) {
    cancelPreload()

    // Cancel any in-flight preview request
    if (currentPreviewAbortController) {
      currentPreviewAbortController.abort()
      currentPreviewAbortController = null
    }
  }

  if (!currentPreviewMovie.value || !selectedTemplate.value) {
    console.log('[TV BATCH PREVIEW] Early return - missing movie or template')
    previewImage.value = null
    return
  }

  // Assign a unique ID to this request to track ordering
  const requestId = ++previewRequestId

  // Determine if we're viewing a show or a specific season
  const movie = currentPreviewMovie.value
  const isShowLevel = movie.seasons !== undefined // Has seasons = show level

  // Build cache key - include library, show key, template, preset, and season index
  let cacheKey: string
  const libraryPart = currentLibrary.value ? `lib:${currentLibrary.value}` : 'no-lib'

  console.log('[TV BATCH PREVIEW] Cache key decision:', {
    includeSeasons: includeSeasons.value,
    isShowLevel,
    hasCurrentSeason: !!currentSeason.value,
    currentSeasonIndex: currentSeason.value?.index,
    seasonsLength: currentSeasons.value.length
  })

  if (includeSeasons.value && !isShowLevel) {
    // Viewing a specific season - include season info in cache key
    cacheKey = `${libraryPart}|${movie.key}|${selectedTemplate.value}|${selectedPreset.value || 'none'}|season:${movie.title}`
    console.log('[TV BATCH PREVIEW] Using season item cache key (branch 1)')
  } else if (includeSeasons.value && currentSeason.value && currentSeasons.value.length > 0) {
    // Viewing show with seasons enabled AND seasons have been loaded AND a season is selected
    // Use season index for more reliable cache key (title can have special chars)
    const seasonIdx = currentSeason.value.index
    cacheKey = `${libraryPart}|${movie.key}|${selectedTemplate.value}|${selectedPreset.value || 'none'}|season:${seasonIdx}`
    console.log('[TV BATCH PREVIEW] Using season index cache key (branch 2):', seasonIdx)
  } else {
    // Viewing show without seasons OR seasons not loaded yet
    cacheKey = `${libraryPart}|${movie.key}|${selectedTemplate.value}|${selectedPreset.value || 'none'}|show`
    console.log('[TV BATCH PREVIEW] Using show cache key (branch 3)')
  }

  console.log('[TV BATCH PREVIEW] Final cache key:', cacheKey)

  if (previewCache.value[cacheKey]) {
    console.log('[TV BATCH PREVIEW] Using cached preview')
    // If this is a manual fetch (not preload), update the preview image
    if (!isPreload) {
      previewImage.value = previewCache.value[cacheKey] || null
    }
    return
  }

  // Only show loading indicator for manual fetches, not preloads
  if (!isPreload) {
    previewLoading.value = true
    // Clear the preview image while loading to prevent showing stale cached poster
    previewImage.value = null
  }

  // Create abort controller for this request
  const abortController = new AbortController()
  if (!isPreload) {
    currentPreviewAbortController = abortController
  }

  try {
    // Determine which poster to use
    let posterUrl = movie.poster
    let targetKey = movie.key
    let seasonIndex: number | undefined = undefined

    // Important: Only use season-specific rendering if we have seasons loaded AND includeSeasons is checked
    // This ensures the series poster shows by default when includeSeasons is first checked
    const shouldRenderSeason = includeSeasons.value && currentSeason.value && isShowLevel && currentSeasons.value.length > 0

    // If viewing seasons and we have a current season
    if (shouldRenderSeason) {
      // Check if this is the series entry (index -1) or an actual season
      if (currentSeason.value.index === -1) {
        // Series poster - don't set seasonIndex (will render as series)
        targetKey = currentSeason.value.key
        posterUrl = currentSeason.value.poster || null
        seasonIndex = undefined
      } else {
        // Actual season - set seasonIndex for season-specific rendering
        targetKey = currentSeason.value.key
        posterUrl = currentSeason.value.poster || null
        seasonIndex = currentSeason.value.index
      }
    }

    // Check if we should use poster selection based on preset's poster_filter
    let posterFilter = 'all'
    if (selectedPreset.value && selectedTemplate.value) {
      const templateData = presetsDataFull.value[selectedTemplate.value]
      if (templateData && templateData.presets) {
        const preset = templateData.presets.find((p: any) => p.id === selectedPreset.value)
        if (preset) {
          // Use season_options poster_filter if we're actually viewing a season (seasonIndex is defined)
          // Otherwise use regular options poster_filter (for series-level rendering)
          if (seasonIndex !== undefined && preset.season_options && preset.season_options.poster_filter) {
            posterFilter = preset.season_options.poster_filter
            console.log('[TV BATCH PREVIEW] Using season_options poster_filter:', posterFilter)
          } else if (preset.options && preset.options.poster_filter) {
            posterFilter = preset.options.poster_filter
            console.log('[TV BATCH PREVIEW] Using options poster_filter:', posterFilter)
          }
        }
      }
    }

    // If we have a textless/text filter, use the new select-poster endpoint
    if (posterFilter === 'textless' || posterFilter === 'text') {
      console.log('[TV BATCH PREVIEW] Fetching filtered poster with filter:', posterFilter)
      const selectParams = new URLSearchParams({
        poster_filter: posterFilter,
        ...(seasonIndex !== undefined && { season_index: seasonIndex.toString() }),
        ...(currentLibrary.value && { library_id: currentLibrary.value })
      })
      
      try {
        // Use movie.key (the show's rating key) not targetKey (which could be a season)
        // The endpoint needs the show's key to look up TMDB ID
        const selectRes = await fetch(`${apiBase}/api/tv-show/${movie.key}/select-poster?${selectParams}`)
        if (selectRes.ok) {
          const selectData = await selectRes.json()
          posterUrl = selectData.url
          console.log('[TV BATCH PREVIEW] Selected filtered poster: has_text=%s url=%s', selectData.has_text, posterUrl?.substring(0, 100))
        } else {
          const errorText = await selectRes.text()
          console.warn('[TV BATCH PREVIEW] Poster selection failed:', selectRes.status, errorText)
        }
      } catch (err) {
        console.error('[TV BATCH PREVIEW] Error selecting poster:', err)
      }
    }

    // Fetch poster if still not available
    if (!posterUrl) {
      const posterRes = await fetch(`${apiBase}/api/tv-show/${targetKey}/poster?meta=1${currentLibrary.value ? `&library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`)
      const posterData = await posterRes.json()
      if (posterData.url) {
        posterUrl = posterData.url.startsWith('http') ? posterData.url : `${apiBase}${posterData.url}`
      }
    }

    // Build options object with season_text and poster_filter
    const options: Record<string, any> = {}

    // Add poster_filter to options so preview endpoint respects it
    options.poster_filter = posterFilter
    console.log('[TV BATCH PREVIEW] Adding poster_filter to options:', posterFilter)

    // IMPORTANT: Only add season_text when we're actually rendering a season poster
    // This ensures the preview API doesn't mistakenly use season_options for series posters
    if (shouldRenderSeason) {
      if (!isShowLevel && movie.title) {
        // Viewing a specific season item - use its title
        options.season_text = movie.title
        console.log('[TV BATCH PREVIEW] Season item, text:', movie.title)
      } else if (currentSeason.value && currentSeason.value.index !== -1) {
        // Viewing show with current season selected (but not the series entry)
        options.season_text = currentSeason.value.title
        console.log('[TV BATCH PREVIEW] Show with season, text:', currentSeason.value.title)
      } else {
        // Series entry (index -1) - don't add season_text
        console.log('[TV BATCH PREVIEW] Series entry detected, NOT adding season_text')
      }
    } else {
      console.log('[TV BATCH PREVIEW] Rendering series poster, NOT adding season_text')
    }

    const payload = {
      template_id: selectedTemplate.value,
      background_url: posterUrl || '',
      logo_url: null,
      options,
      preset_id: selectedPreset.value || undefined,
      movie_title: movie.title,
      movie_year: movie.year ? Number(movie.year) : undefined,
      // Add TV show rating key so preview endpoint can fetch logos
      tv_show_rating_key: movie.key
    }

    console.log('[TV BATCH PREVIEW] Fetching preview with payload:', payload)

    const response = await fetch(`${apiBase}/api/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: abortController.signal
    })

    if (response.ok) {
      const data = await response.json()
      const img = `data:image/jpeg;base64,${data.image_base64}`

      // Always cache the result
      previewCache.value[cacheKey] = img

      // Only update preview image if this request is still the most recent one
      // This prevents race conditions where an older request completes after a newer one
      if (!isPreload && requestId === previewRequestId) {
        previewImage.value = img
        console.log('[TV BATCH PREVIEW] Preview rendered successfully (request #' + requestId + ')')
      } else if (isPreload) {
        console.log('[TV BATCH PREVIEW] Background preload completed and cached')
      } else {
        console.log('[TV BATCH PREVIEW] Ignoring stale preview response (request #' + requestId + ', current #' + previewRequestId + ')')
      }
    } else {
      console.error('[TV BATCH PREVIEW] Preview response not OK:', response.status)
      const errorText = await response.text()
      console.error('[TV BATCH PREVIEW] Error details:', errorText)
      if (!isPreload && requestId === previewRequestId) {
        previewImage.value = null
      }
    }
  } catch (err) {
    // Ignore abort errors - these are expected when canceling
    if (err instanceof Error && err.name === 'AbortError') {
      console.log('[TV BATCH PREVIEW] Request aborted (request #' + requestId + ')')
      return
    }
    console.error('[TV BATCH PREVIEW] Preview failed:', err)
    if (!isPreload && requestId === previewRequestId) {
      previewImage.value = null
    }
  } finally {
    // Only update loading state for manual fetches
    if (!isPreload) {
      previewLoading.value = false
    }
  }
}

// Watch for changes to fetch posters and labels
watch(moviesWithPosters, async (list) => {
  fetchPosters()
  // Only fetch individual labels for movies not already cached
  fetchLabels(list)
})

// Reset to page 1 when filters change
watch([searchQuery, filterLabel, sortBy, sortOrder, posterLimit], () => {
  currentPage.value = 1
})

// Ensure current page doesn't exceed total pages
watch(totalPages, () => {
  if (currentPage.value > totalPages.value) {
    currentPage.value = Math.max(1, totalPages.value)
  }
})

// Clear preset when template changes
watch(selectedTemplate, (newTemplate) => {
  selectedPreset.value = ''
  previewCache.value = {}
  fetchPreview()

  // Schedule a preload if we have a movie selected and now have a template
  if (newTemplate && currentPreviewMovie.value) {
    schedulePreload()
  }
})

// Update preview when preset or selected movie changes
watch(selectedPreset, () => {
  previewCache.value = {}
  fetchPreview()

  // Schedule a preload for the new preset/template combination
  if (selectedPreset.value && currentPreviewMovie.value) {
    schedulePreload()
  }
})

watch(currentPreviewMovie, () => {
  // When seasons are enabled, the currentSeason watch will handle preview fetching
  // When seasons are disabled, we need to fetch the show-level preview
  if (!includeSeasons.value) {
    fetchPreview()
  }
  // If includeSeasons is true, the watch(currentSeason) will trigger when seasons load
})

// Update preview when season changes
// Watch currentSeason instead of currentSeasonIndex because currentSeason is a computed
// property that changes when seasons are loaded, even if the index stays at 0
watch(currentSeason, (newSeason, oldSeason) => {
  console.log('[TV BATCH PREVIEW] currentSeason changed:', {
    oldSeason: oldSeason?.title || 'null',
    newSeason: newSeason?.title || 'null',
    includeSeasons: includeSeasons.value
  })

  // Fetch preview when we have a valid season (not null)
  // This handles both initial load and navigation between seasons
  if (newSeason && includeSeasons.value) {
    console.log('[TV BATCH PREVIEW] Fetching preview for season:', newSeason.title)
    fetchPreview()
  }
})

onMounted(async () => {
  // Wait for route to be ready 
  await new Promise(resolve => setTimeout(resolve, 0))

  // Ensure settings are loaded so defaults are available
  if (!settings.loaded.value) {
    await settings.load()
  }

  // Clear any stale cache data first to prevent cross-library contamination on page load
  labelCache.value = {}
  posterCache.value = {}
  tvShows.value = []
  selectedShows.value.clear()
  
  // Only proceed if we have a valid library context
  if (currentLibrary.value) {
    // Load templates/presets first
    await loadTemplatesAndPresets()
    
    // Then fetch fresh data
    await fetchMovies()
    
    // Try to load labels from backend cache first (much faster for bulk)
    await fetchLabelsFromCache()
    
    // Load any additional cached data from sessionStorage for this specific library
    loadLabelCache()
    loadPosterCache()

    // Load latest sent/saved status for this library
    await fetchPosterStatus()

    // Seed labels to remove from settings defaults
    syncLabelsFromSettings()
    
    // Fetch fresh posters and any missing labels for the loaded movies
    fetchPosters()
    fetchLabels(tvShows.value) // This will only fetch labels for movies not already in cache
  }
})
</script>

<template>
  <div class="batch-edit-view">
    <!-- Top Controls -->
    <div class="controls-panel">
      <h2>TV Show Batch Edit</h2>

      <!-- Template & Preset Selection -->
      <div class="selection-row template-row">
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
          <label class="checkbox-label">
            <input type="checkbox" v-model="includeSeasons" />
            Include Seasons
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
          :disabled="selectedShows.size === 0 || !selectedTemplate || !selectedPreset || (!sendToPlex && !saveLocally) || processing"
        >
          <span v-if="!processing">Process {{ selectedShows.size }} TV Shows</span>
          <span v-else>Processing {{ currentIndex }} / {{ selectedShows.size }}...</span>
        </button>
      </div>

      <!-- Progress Bar -->
      <div v-if="processing" class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
    </div>

    <!-- Movie Selection Controls -->
    <div class="movie-controls">
      <div class="filter-row">
        <div class="filter-groups">
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
          <div class="sort-control">
            <label for="sort-by">Sort by:</label>
            <select id="sort-by" v-model="sortBy" class="filter-select">
              <option value="title">Title</option>
              <option value="year">Year</option>
              <option value="addedAt">Date Added</option>
            </select>
          </div>
          <div class="sort-control">
            <label for="sort-order">Order:</label>
            <select id="sort-order" v-model="sortOrder" class="filter-select">
              <option value="asc">{{ sortBy === 'title' ? 'A-Z' : 'Oldest First' }}</option>
              <option value="desc">{{ sortBy === 'title' ? 'Z-A' : 'Newest First' }}</option>
            </select>
          </div>
          <select v-model="filterLabel" class="filter-select">
            <option value="">All Labels</option>
            <option v-for="label in allLabels" :key="label" :value="label">
              {{ label }}
            </option>
          </select>
          <select v-model="sentFilter" class="filter-select">
            <option value="all">All Sent States</option>
            <option value="sent">Sent</option>
            <option value="unsent">Not Sent</option>
          </select>
          <select v-model="savedFilter" class="filter-select">
            <option value="all">All Save States</option>
            <option value="saved">Saved</option>
            <option value="unsaved">Not Saved</option>
          </select>
        </div>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Filter movies..."
          class="filter-input"
        />
      </div>

      <div class="selection-row">
        <div class="selection-summary">
          <h3>{{ selectedShows.size }} of {{ moviesWithPosters.length }} selected</h3>
          <span v-if="filteredMovies.length > posterLimit" class="limit-notice">
            Showing {{ posterLimit }} of {{ filteredMovies.length }} movies
          </span>
        </div>
        <div class="selection-actions">
          <button class="btn-small" @click="selectAll">Select All</button>
          <button class="btn-small" @click="deselectAll">Deselect All</button>
        </div>
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
            :class="{ selected: selectedShows.has(movie.key) }"
            @click="toggleMovie(movie.key)"
          >
            <div class="checkbox-overlay">
              <input
                type="checkbox"
                :checked="selectedShows.has(movie.key)"
                @click.stop="toggleMovie(movie.key)"
                class="movie-checkbox"
              />
            </div>
            <div class="poster">
              <img
                :src="movie.poster || `/api/tv-show/${movie.key}/poster?w=200${currentLibrary ? `&library_id=${encodeURIComponent(currentLibrary)}` : ''}`"
                :alt="movie.title"
                loading="lazy"
              />
            </div>
            <div class="movie-info">
              <p class="title">{{ movie.title }}</p>
              <p class="year">{{ movie.year }}</p>
              <div class="status-row">
                <span class="pill pill-template" :title="`Template/Preset: ${getTemplatePresetText(movie.key)}`">
                  {{ getTemplatePresetText(movie.key) }}
                </span>
                <span
                  class="pill"
                  :class="getSentText(movie.key) ? 'pill-sent' : 'pill-unsent'"
                  :title="getSentTooltip(movie.key)"
                >
                  {{ getSentText(movie.key) ? 'Sent' : 'Not sent' }}
                </span>
                <span
                  class="pill"
                  :class="getSavedText(movie.key) ? 'pill-saved' : 'pill-unsaved'"
                  :title="getSavedTooltip(movie.key)"
                >
                  {{ getSavedText(movie.key) ? 'Saved' : 'Not saved' }}
                </span>
              </div>
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

        <!-- Title and Year Header -->
        <div class="preview-header">
          <p class="preview-title">{{ currentPreviewMovie.title }}</p>
          <p class="preview-year">{{ currentPreviewMovie.year }}</p>
        </div>

        <!-- Preview Poster -->
        <div class="preview-poster">
          <div v-if="previewLoading" class="preview-loading">Rendering...</div>
          <img
            v-else-if="previewImage"
            :src="previewImage"
            :alt="currentPreviewMovie.title"
          />
          <div v-else-if="!selectedTemplate" class="preview-loading">Select a template to preview</div>
          <div v-else class="preview-loading">Waiting for preview...</div>
        </div>

        <!-- Season Navigation - Below Poster -->
        <div v-if="includeSeasons && currentSeasons.length > 0" class="season-nav-inline">
          <button
            class="season-arrow-btn"
            @click="prevSeason"
            :disabled="currentSeasonIndex === 0"
          >
            ←
          </button>
          <span class="season-label">
            {{ currentSeason?.title || `Season ${currentSeasonIndex + 1}` }}
          </span>
          <button
            class="season-arrow-btn"
            @click="nextSeason"
            :disabled="currentSeasonIndex === currentSeasons.length - 1"
          >
            →
          </button>
        </div>

        <!-- Hints -->
        <div v-if="!selectedTemplate || !selectedPreset" class="preview-hints">
          <p v-if="!selectedTemplate" class="preview-hint">Select a template to preview</p>
          <p v-else-if="!selectedPreset" class="preview-hint">Preset optional - preview will use template defaults</p>
        </div>

        <!-- Show Navigation -->
        <div v-if="selectedShowsList.length > 1" class="preview-nav-section">
          <div class="preview-nav">
            <button
              class="nav-btn"
              @click="prevPreview"
              :disabled="previewIndex === 0"
            >
              ← Prev
            </button>
            <span class="nav-counter">{{ previewIndex + 1 }} / {{ selectedShowsList.length }}</span>
            <button
              class="nav-btn"
              @click="nextPreview"
              :disabled="previewIndex === selectedShowsList.length - 1"
            >
              Next →
            </button>
          </div>
        </div>

        <!-- Movie List -->
        <div v-if="selectedShowsList.length > 1" class="preview-list">
          <h4>Selected TV Shows ({{ selectedShowsList.length }})</h4>
          <div class="movie-list-scroll">
            <button
              v-for="(movie, index) in selectedShowsList"
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
  gap: 0.5rem;
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
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: var(--surface, #1a1f2e);
  border-radius: 8px;
  border: 1px solid var(--border, #2a2f3e);
}

.filter-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
}

.filter-groups {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
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

.limit-control {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.sort-control {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.sort-control label {
  color: var(--text-secondary, #aaa);
  font-size: 0.9rem;
  font-weight: 500;
  white-space: nowrap;
}

.selection-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.selection-row.template-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.75rem;
  align-items: end;
}

.selection-summary {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.selection-summary h3 {
  margin: 0;
  color: var(--text-primary, #fff);
  font-size: 1rem;
}

.selection-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
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
  min-width: 260px;
  flex: 1;
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

/* Preview header with title and year */
.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.preview-title {
  margin: 0;
  color: var(--text-primary, #fff);
  font-size: 1rem;
  font-weight: 600;
  flex: 1;
}

.preview-year {
  margin: 0;
  color: var(--text-secondary, #aaa);
  font-size: 0.9rem;
  white-space: nowrap;
}

.preview-poster {
  aspect-ratio: 2/3;
  overflow: hidden;
  background: var(--surface-alt, #242933);
  border-radius: 6px;
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

/* Season navigation inline below poster */
.season-nav-inline {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-top: 0.75rem;
  padding: 0.5rem;
}

.season-arrow-btn {
  background: transparent;
  border: none;
  color: var(--accent, #3dd6b7);
  font-size: 1.5rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  transition: all 0.2s;
  line-height: 1;
}

.season-arrow-btn:hover:not(:disabled) {
  color: #2bc4a3;
  transform: scale(1.2);
}

.season-arrow-btn:disabled {
  color: rgba(170, 170, 170, 0.3);
  cursor: not-allowed;
  transform: none;
}

.season-label {
  color: var(--text-primary, #fff);
  font-size: 0.9rem;
  font-weight: 500;
  text-align: center;
  min-width: 120px;
}

/* Hints section */
.preview-hints {
  margin-top: 0.75rem;
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

.meta {
  margin: 0;
  color: var(--text-secondary, #999);
  font-size: 0.8rem;
  line-height: 1.3;
}

.status-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  color: #dce6ff;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pill-template {
  background: rgba(91, 141, 238, 0.14);
  border-color: rgba(91, 141, 238, 0.3);
  color: #a8c3ff;
}

.pill-sent {
  background: rgba(61, 214, 183, 0.16);
  border-color: rgba(61, 214, 183, 0.35);
  color: #9bf2df;
}

.pill-unsent {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #c8d0e0;
}

.pill-saved {
  background: rgba(255, 193, 7, 0.14);
  border-color: rgba(255, 193, 7, 0.35);
  color: #ffe28a;
}

.pill-unsaved {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #c8d0e0;
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

/* Preview navigation section wrapper */
.preview-nav-section {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border, #2a2f3e);
}

/* Preview navigation */
.preview-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: transparent;
  border-radius: 6px;
  border: 1px solid rgba(61, 214, 183, 0.25);
}

.nav-btn {
  padding: 0.4rem 0.9rem;
  background: rgba(61, 214, 183, 0.1);
  color: var(--accent, #3dd6b7);
  border: 1px solid rgba(61, 214, 183, 0.3);
  border-radius: 4px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-btn:hover:not(:disabled) {
  background: rgba(61, 214, 183, 0.2);
  border-color: rgba(61, 214, 183, 0.5);
  transform: translateY(-1px);
}

.nav-btn:disabled {
  opacity: 0.25;
  cursor: not-allowed;
  transform: none;
}

.nav-counter {
  color: var(--text-primary, #fff);
  font-size: 0.85rem;
  font-weight: 500;
  min-width: 80px;
  text-align: center;
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
