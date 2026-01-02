<script setup lang="ts">
import { computed, onMounted, ref, watch, nextTick } from 'vue'
import type { MovieInput } from '../../services/types'
import { useRenderService } from '../../services/render'
import { usePresetService } from '../../services/presets'
import { useNotification } from '../../composables/useNotification'
import { useSettingsStore } from '../../stores/settings'
import { useMovies } from '../../composables/useMovies'
import TextOverlayPanel from './TextOverlayPanel.vue'
import { getApiBase } from '../../services/apiBase'

const props = defineProps<{ movie: MovieInput }>()

const settings = useSettingsStore()
const { movies: globalMovies, setMoviePoster } = useMovies()

const apiBase = getApiBase()

const tmdbId = ref<number | null>(null)
const tvdbId = ref<number | null>(null)
const posters = ref<{ url: string; thumb?: string; has_text?: boolean; language?: string; source?: string }[]>([])
const logos = ref<{ url: string; thumb?: string; color?: string; language?: string; source?: string; type?: string }[]>([])
const labels = ref<string[]>([])
const selectedLabels = ref<Set<string>>(new Set())
const existingPoster = ref<string | null>(null)

const posterFilter = ref<'all' | 'textless' | 'text'>('all')
const posterLanguageFilter = ref<'all' | 'en' | 'with_lang'>('all')
const showTmdbPosters = ref(true)
const showFanartPosters = ref(true)
const showTvdbPosters = ref(true)
const logoPreference = ref<'first' | 'white' | 'color'>('first')
const logoLanguageFilter = ref<'all' | 'en' | 'with_lang'>('all')
const showTmdbLogos = ref(true)
const showFanartLogos = ref(true)
const showTvdbLogos = ref(true)
const showClearArt = ref(true)
const logoMode = ref<'original' | 'match' | 'hex' | 'none'>('original')
const logoHex = ref('#ffffff')
const isLogoNone = computed(() => logoMode.value === 'none')

const normalizeLogoMode = (mode: unknown): 'original' | 'match' | 'hex' | 'none' => {
  if (typeof mode !== 'string') return 'original'
  const m = mode.toLowerCase()
  if (['original', 'stock', 'keep'].includes(m)) return 'original'
  if (['match', 'color', 'colormatch', 'color-match'].includes(m)) return 'match'
  if (['hex', 'custom'].includes(m)) return 'hex'
  if (['none', 'off', 'no'].includes(m)) return 'none'
  return 'original'
}

const selectedPoster = ref<string | null>(null)
const selectedLogo = ref<string | null>(null)
// Cache poster selection per season/series so switching targets doesn't reset the choice
const selectedPosterCache = ref<Record<string, string>>({})
// Cache full settings per season/series to prevent cross-contamination
const settingsCache = ref<Record<string, any>>({})
const POSTER_CACHE_KEY = 'simposter-poster-cache'

const showBoundingBox = ref(false)
const previewImgRef = ref<HTMLImageElement | null>(null)
const posterRefreshKey = ref(0)

// TV Show Season Management
type Season = {
  key: string
  title: string
  index: number
  thumb?: string
  isSeries?: boolean
  poster?: string
}
type RenderedPreview = {
  seasonKey: string
  seasonTitle: string
  imageUrl: string
}
const seasons = ref<Season[]>([])
const selectedSeasons = ref<Set<string>>(new Set())
const currentSeasonIndex = ref(0)
const currentSeason = computed(() => {
  const selected = Array.from(selectedSeasons.value)
  if (selected.length === 0 || currentSeasonIndex.value >= selected.length) return null
  const seasonKey = selected[currentSeasonIndex.value]
  return seasons.value.find(s => s.key === seasonKey) || null
})

// Rendered preview carousel
const renderedPreviews = ref<RenderedPreview[]>([])
const activePreviewIndex = ref(0)

// Sorted rendered previews by season order (series first, then seasons 0, 1, 2, etc.)
const sortedRenderedPreviews = computed(() => {
  return [...renderedPreviews.value].sort((a, b) => {
    const seasonA = seasons.value.find(s => s.key === a.seasonKey)
    const seasonB = seasons.value.find(s => s.key === b.seasonKey)

    if (!seasonA || !seasonB) return 0

    // Series always first
    if (seasonA.isSeries) return -1
    if (seasonB.isSeries) return 1

    // Then by season index (0 = Specials, 1, 2, 3, etc.)
    return seasonA.index - seasonB.index
  })
})

// Cache rendered previews to avoid re-rendering when cycling back
// Key format: `${seasonKey}_${bgUrl}_${logoUrl}_${JSON.stringify(options)}`
const renderedPreviewCache = ref<Record<string, string>>({})

// Track which season preset fields have been manually modified by the user
// Key is seasonKey, value is Set of field names (e.g., 'fontSize', 'shadowEnabled')
const userModifiedFields = ref<Record<string, Set<string>>>({})

// Cache assets per season to avoid re-fetching when switching
const seasonAssetsCache = ref<Record<string, { posters: any[]; logos: any[]; backdrops?: any[] }>>({})
const showLevelAssets = ref<{ posters: any[]; logos: any[]; backdrops?: any[] }>({ posters: [], logos: [], backdrops: [] })

// Simple session cache for seasons per show to avoid refetching on each open
const SEASONS_CACHE_KEY = 'simposter-tv-seasons-cache'
const seasonsCache = ref<Record<string, Season[]>>({})

const loadSeasonsCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    const raw = sessionStorage.getItem(SEASONS_CACHE_KEY)
    if (raw) seasonsCache.value = JSON.parse(raw)
  } catch {
    /* ignore */
  }
}

const saveSeasonsCache = () => {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(SEASONS_CACHE_KEY, JSON.stringify(seasonsCache.value))
  } catch {
    /* ignore */
  }
}

const posterUrlForRatingKey = (ratingKey?: string | null) => {
  if (!ratingKey) return undefined
  return `${apiBase}/api/movie/${ratingKey}/poster?raw=1`
}
const toPlexPosterUrl = (path?: string | null) => {
  if (!path) return undefined
  const url = String(path)
  if (url.startsWith('http')) return url
  return `${apiBase}/api/plex-poster?path=${encodeURIComponent(url)}`
}

const seriesPosterUrl = computed(() => {
  // Only derive from the series-level sources; do not use the global existingPoster
  // to avoid bleeding season posters into the series thumbnail.
  if (props.movie.poster) {
    const maybeUrl = toPlexPosterUrl(props.movie.poster)
    if (maybeUrl) return maybeUrl
  }
  return posterUrlForRatingKey(props.movie.key) || null
})

const buildSeriesEntry = (): Season => ({
  key: props.movie.key,
  title: `${props.movie.title} (Series)`,
  index: -1,
  thumb: seriesPosterUrl.value || posterUrlForRatingKey(props.movie.key),
  isSeries: true
})

const options = ref({
  posterZoom: 100,
  posterShiftY: 0,
  matteHeight: 0,
  fadeHeight: 0,
  vignette: 0,
  grain: 0,
  logoScale: 50,
  logoOffset: 75,
  uniformLogoMaxW: 500,
  uniformLogoMaxH: 200,
  uniformLogoOffsetX: 50,
  uniformLogoOffsetY: 78,
  borderEnabled: false,
  borderThickness: 0,
  borderColor: '#ffffff',
  overlayFile: '',
  overlayOpacity: 40,
  overlayMode: 'screen'
})

// Text overlay settings
const textOverlayEnabled = ref(false)
const customText = ref('')
const fontFamily = ref('Arial')
const fontSize = ref(120)
const fontWeight = ref('700')
const textColor = ref('#ffffff')
const textAlign = ref('center')
const textTransform = ref('uppercase')
const letterSpacing = ref(2)
const lineHeight = ref(120)
const positionY = ref(75)
const shadowEnabled = ref(true)
const shadowBlur = ref(10)
const shadowOffsetX = ref(0)
const shadowOffsetY = ref(4)
const shadowColor = ref('#000000')
const shadowOpacity = ref(80)
const strokeEnabled = ref(false)
const strokeWidth = ref(4)
const strokeColor = ref('#000000')
const availableFonts = ref<string[]>([])

const render = useRenderService()
const loading = render.loading
const error = render.error
const lastPreview = render.lastPreview

// Helpers to isolate per-target settings
const getCurrentSettings = () => ({
  selectedPoster: selectedPoster.value,
  selectedLogo: selectedLogo.value,
  posterFilter: posterFilter.value,
  posterLanguageFilter: posterLanguageFilter.value,
  logoPreference: logoPreference.value,
  logoLanguageFilter: logoLanguageFilter.value,
  showTmdbPosters: showTmdbPosters.value,
  showFanartPosters: showFanartPosters.value,
  showTvdbPosters: showTvdbPosters.value,
  showTmdbLogos: showTmdbLogos.value,
  showFanartLogos: showFanartLogos.value,
  showTvdbLogos: showTvdbLogos.value,
  showClearArt: showClearArt.value,
  logoMode: logoMode.value,
  logoHex: logoHex.value,
  options: JSON.parse(JSON.stringify(options.value)),
  textOverlayEnabled: textOverlayEnabled.value,
  customText: customText.value,
  fontFamily: fontFamily.value,
  fontSize: fontSize.value,
  fontWeight: fontWeight.value,
  textColor: textColor.value,
  textAlign: textAlign.value,
  textTransform: textTransform.value,
  letterSpacing: letterSpacing.value,
  lineHeight: lineHeight.value,
  positionY: positionY.value,
  shadowEnabled: shadowEnabled.value,
  shadowBlur: shadowBlur.value,
  shadowOffsetX: shadowOffsetX.value,
  shadowOffsetY: shadowOffsetY.value,
  shadowColor: shadowColor.value,
  shadowOpacity: shadowOpacity.value,
  strokeEnabled: strokeEnabled.value,
  strokeWidth: strokeWidth.value,
  strokeColor: strokeColor.value,
})

const applySettings = (s: any) => {
  if (!s) return
  if (s.selectedPoster !== undefined) selectedPoster.value = s.selectedPoster
  if (s.selectedLogo !== undefined) selectedLogo.value = s.selectedLogo
  if (s.posterFilter !== undefined) posterFilter.value = s.posterFilter
  if (s.posterLanguageFilter !== undefined) posterLanguageFilter.value = s.posterLanguageFilter
  if (s.logoPreference !== undefined) logoPreference.value = s.logoPreference
  if (s.logoLanguageFilter !== undefined) logoLanguageFilter.value = s.logoLanguageFilter
  if (s.showTmdbPosters !== undefined) showTmdbPosters.value = s.showTmdbPosters
  if (s.showFanartPosters !== undefined) showFanartPosters.value = s.showFanartPosters
  if (s.showTvdbPosters !== undefined) showTvdbPosters.value = s.showTvdbPosters
  if (s.showTmdbLogos !== undefined) showTmdbLogos.value = s.showTmdbLogos
  if (s.showFanartLogos !== undefined) showFanartLogos.value = s.showFanartLogos
  if (s.showTvdbLogos !== undefined) showTvdbLogos.value = s.showTvdbLogos
  if (s.showClearArt !== undefined) showClearArt.value = s.showClearArt
  if (s.logoMode !== undefined) logoMode.value = s.logoMode
  if (s.logoHex !== undefined) logoHex.value = s.logoHex
  if (s.options) Object.assign(options.value, s.options)
  if (s.textOverlayEnabled !== undefined) textOverlayEnabled.value = s.textOverlayEnabled
  if (s.customText !== undefined) customText.value = s.customText
  if (s.fontFamily !== undefined) fontFamily.value = s.fontFamily
  if (s.fontSize !== undefined) fontSize.value = s.fontSize
  if (s.fontWeight !== undefined) fontWeight.value = s.fontWeight
  if (s.textColor !== undefined) textColor.value = s.textColor
  if (s.textAlign !== undefined) textAlign.value = s.textAlign
  if (s.textTransform !== undefined) textTransform.value = s.textTransform
  if (s.letterSpacing !== undefined) letterSpacing.value = s.letterSpacing
  if (s.lineHeight !== undefined) lineHeight.value = s.lineHeight
  if (s.positionY !== undefined) positionY.value = s.positionY
  if (s.shadowEnabled !== undefined) shadowEnabled.value = s.shadowEnabled
  if (s.shadowBlur !== undefined) shadowBlur.value = s.shadowBlur
  if (s.shadowOffsetX !== undefined) shadowOffsetX.value = s.shadowOffsetX
  if (s.shadowOffsetY !== undefined) shadowOffsetY.value = s.shadowOffsetY
  if (s.shadowColor !== undefined) shadowColor.value = s.shadowColor
  if (s.shadowOpacity !== undefined) shadowOpacity.value = s.shadowOpacity
  if (s.strokeEnabled !== undefined) strokeEnabled.value = s.strokeEnabled
  if (s.strokeWidth !== undefined) strokeWidth.value = s.strokeWidth
  if (s.strokeColor !== undefined) strokeColor.value = s.strokeColor
}

const currentTargetKey = computed(() => currentSeason.value?.key || props.movie.key)

const saveCurrentSettings = () => {
  const key = currentTargetKey.value
  const settings = getCurrentSettings()

  const isSeason = currentSeason.value && !currentSeason.value.isSeries

  if (isSeason) {
    // For seasons, only cache preset fields if user manually modified them
    const modified = userModifiedFields.value[key] || new Set()
    const presetFields = [
      'logoMode', 'textOverlayEnabled', 'customText', 'fontFamily', 'fontSize',
      'shadowEnabled', 'letterSpacing', 'positionY', 'posterZoom', 'posterShiftY',
      'matteHeight', 'fadeHeight', 'vignette', 'grain', 'logoScale', 'logoOffset'
    ]

    // Remove preset fields that user hasn't modified
    presetFields.forEach(field => {
      if (!modified.has(field)) {
        delete (settings as any)[field]
        // Also remove from options object if applicable
        if (settings.options && field in settings.options) {
          delete settings.options[field]
        }
      }
    })
  } else {
    // For series, ensure season_text is never saved
    if (settings.options && settings.options.season_text) {
      console.log('[SAVE] Removing season_text from series settings')
      delete settings.options.season_text
    }
  }

  settingsCache.value[key] = settings
  if (selectedPoster.value) selectedPosterCache.value[key] = selectedPoster.value
}

const restoreSettingsForCurrent = () => {
  const key = currentTargetKey.value
  const cached = settingsCache.value[key]
  const isSeason = currentSeason.value && !currentSeason.value.isSeries

  console.log('[RESTORE] Target:', key, 'isSeason:', isSeason, 'hasCached:', !!cached)

  if (isSeason) {
    console.log('[RESTORE] Season detected, applying preset season_options')
    applyPresetOptions(selectedPreset.value, { forceSeasonOverrides: true })
    if (cached) {
      console.log('[RESTORE] Applying cached season edits on top of preset')
      // Apply all cached season edits so manual tweaks persist when returning
      applySettings(cached)
    }
  } else {
    // This is a series poster - explicitly clear season_text
    if (options.value.season_text) {
      console.log('[RESTORE] Clearing season_text for series')
      delete options.value.season_text
    }

    if (cached) {
      console.log('[RESTORE] Applying cached settings for series')
      applySettings(cached)
      // Ensure season_text is not in cached settings for series
      if (options.value.season_text) {
        delete options.value.season_text
      }
    } else {
      console.log('[RESTORE] Series with no cache, applying preset')
      applyPresetOptions(selectedPreset.value, { forceSeasonOverrides: false })
    }
  }

  // Restore cached poster selection if available
  if (selectedPosterCache.value[key]) {
    selectedPoster.value = selectedPosterCache.value[key]
    console.log('[RESTORE] Restored cached poster for', key)
  }
}

const restoreSettingsForKey = async (key: string) => {
  const cached = settingsCache.value[key]
  if (cached) {
    applySettings(cached)
  }
  if (selectedPosterCache.value[key]) {
    selectedPoster.value = selectedPosterCache.value[key]
  } else {
    ensurePosterSelected()
  }
  await nextTick()
}

const ensurePosterSelected = () => {
  if (selectedPoster.value) return
  const first = posters.value[0]
  if (first?.url) {
    selectedPoster.value = first.url
    return
  }
  if (seriesPosterUrl.value) {
    selectedPoster.value = seriesPosterUrl.value
  }
}

const { success, error: notifyError } = useNotification()

// Watch for preview changes and store them in carousel
watch(lastPreview, (newPreview) => {
  if (!newPreview) return
  
  const season = currentSeason.value
  if (!season) return

  // Check if we already have a preview for this season
  const existingIndex = renderedPreviews.value.findIndex(p => p.seasonKey === season.key)

  if (existingIndex >= 0) {
    // Update existing preview
    const existing = renderedPreviews.value[existingIndex]
    if (existing) existing.imageUrl = newPreview
    activePreviewIndex.value = existingIndex
  } else {
    // Add new preview
    renderedPreviews.value.push({
      seasonKey: season.key,
      seasonTitle: season.title,
      imageUrl: newPreview
    })
    activePreviewIndex.value = renderedPreviews.value.length - 1
  }
})

// Switch to a rendered preview
async function switchToRenderedPreview(index: number) {
  if (index < 0 || index >= renderedPreviews.value.length) return
  activePreviewIndex.value = index

  saveCurrentSettings()

  const preview = renderedPreviews.value[index]
  if (preview) {
    lastPreview.value = preview.imageUrl
    const seasonIndex = Array.from(selectedSeasons.value).findIndex(key => key === preview.seasonKey)
    if (seasonIndex >= 0) {
      // Suppress auto-preview watcher during preview switching
      console.log('[SWITCH PREVIEW] Setting suppressAutoPreview=true for', preview.seasonTitle)
      suppressAutoPreview = true

      try {
        currentSeasonIndex.value = seasonIndex

        // Restore cached poster BEFORE fetching images to prevent applyPosterFilter from changing it
        const cachedPoster = selectedPosterCache.value[preview.seasonKey]
        if (cachedPoster) {
          selectedPoster.value = cachedPoster
        }

        // Load season-specific assets when switching to this preview
        // Skip restore in fetchImagesForCurrentSeason since we call restoreSettingsForCurrent explicitly below
        await fetchImagesForCurrentSeason(true)
        restoreSettingsForCurrent()
      } finally {
        // Always re-enable auto-preview, even if there's an error
        await nextTick()
        console.log('[SWITCH PREVIEW] Setting suppressAutoPreview=false')
        suppressAutoPreview = false
      }
    }
  }
}

function syncRenderedPlaceholders() {
  const selectedKeys = new Set(selectedSeasons.value)
  // Drop previews for deselected seasons
  renderedPreviews.value = renderedPreviews.value.filter(p => selectedKeys.has(p.seasonKey))
  // Add placeholders for newly selected seasons
  selectedKeys.forEach((key) => {
    const exists = renderedPreviews.value.some(p => p.seasonKey === key)
    if (!exists) {
      const season = seasons.value.find(s => s.key === key)
      renderedPreviews.value.push({
        seasonKey: key,
        seasonTitle: season?.title || 'Season',
        imageUrl: ''
      })
    }
  })
  if (activePreviewIndex.value >= renderedPreviews.value.length) {
    activePreviewIndex.value = Math.max(0, renderedPreviews.value.length - 1)
  }
}

function cycleRenderedPreviews(direction: 1 | -1) {
  const total = renderedPreviews.value.length
  if (!total) return
  const nextIndex = (activePreviewIndex.value + direction + total) % total
  switchToRenderedPreview(nextIndex)
}

function onPreviewWheel(event: WheelEvent) {
  if (!renderedPreviews.value.length) return
  event.preventDefault()
  const direction: 1 | -1 = event.deltaY > 0 ? 1 : -1
  cycleRenderedPreviews(direction)
}

const presetService = usePresetService()
const templates = presetService.templates
const presets = presetService.presets
const selectedTemplate = presetService.selectedTemplate
const selectedPreset = presetService.selectedPreset
const presetLoading = presetService.loading
const newPresetId = ref('')

const isUniformLogo = computed(() => selectedTemplate.value === 'uniformlogo')

// State persistence
const EDITOR_STATE_KEY = 'simposter_editor_state'

const saveEditorState = () => {
  try {
    const state = {
      options: options.value,
      selectedTemplate: selectedTemplate.value,
      selectedPreset: selectedPreset.value,
      posterFilter: posterFilter.value,
      posterLanguageFilter: posterLanguageFilter.value,
      showTmdbPosters: showTmdbPosters.value,
      showFanartPosters: showFanartPosters.value,
      showTvdbPosters: showTvdbPosters.value,
      logoPreference: logoPreference.value,
      logoLanguageFilter: logoLanguageFilter.value,
      showTmdbLogos: showTmdbLogos.value,
      showFanartLogos: showFanartLogos.value,
      showTvdbLogos: showTvdbLogos.value,
      showClearArt: showClearArt.value,
      logoMode: logoMode.value,
      logoHex: logoHex.value,
      textOverlay: {
        enabled: textOverlayEnabled.value,
        customText: customText.value,
        fontFamily: fontFamily.value,
        fontSize: fontSize.value,
        fontWeight: fontWeight.value,
        textColor: textColor.value,
        textAlign: textAlign.value,
        textTransform: textTransform.value,
        letterSpacing: letterSpacing.value,
        lineHeight: lineHeight.value,
        positionY: positionY.value,
        shadowEnabled: shadowEnabled.value,
        shadowBlur: shadowBlur.value,
        shadowOffsetX: shadowOffsetX.value,
        shadowOffsetY: shadowOffsetY.value,
        shadowColor: shadowColor.value,
        shadowOpacity: shadowOpacity.value,
        strokeEnabled: strokeEnabled.value,
        strokeWidth: strokeWidth.value,
        strokeColor: strokeColor.value
      }
    }
    localStorage.setItem(EDITOR_STATE_KEY, JSON.stringify(state))
  } catch (e) {
    console.warn('Failed to save editor state:', e)
  }
}

const loadGlobalFallbackSettings = async () => {
  try {
    const res = await fetch(`${apiBase}/api/template-fallback`)
    if (!res.ok) return
    const data = await res.json()

    // Map API filter values to UI filter values
    const mapFilterValue = (apiValue: string): 'all' | 'en' | 'with_lang' => {
      if (apiValue === 'en') return 'en'
      if (apiValue === 'original') return 'with_lang'
      return 'all'
    }

    // Only set if not already saved in local state
    if (data.poster_filter) {
      posterLanguageFilter.value = mapFilterValue(data.poster_filter)
    }
    if (data.logo_filter) {
      logoLanguageFilter.value = mapFilterValue(data.logo_filter)
    }
  } catch (e) {
    console.warn('Failed to load global fallback settings:', e)
  }
}

const loadEditorState = () => {
  try {
    const saved = localStorage.getItem(EDITOR_STATE_KEY)
    if (!saved) return
    const state = JSON.parse(saved)
    if (state.options) Object.assign(options.value, state.options)
    if (state.selectedTemplate) selectedTemplate.value = state.selectedTemplate
    if (state.selectedPreset) selectedPreset.value = state.selectedPreset
    if (state.posterFilter) posterFilter.value = state.posterFilter
  // Only restore language filters if they're not set to default 'all' (prefer global settings)
  if (state.posterLanguageFilter && state.posterLanguageFilter !== 'all') posterLanguageFilter.value = state.posterLanguageFilter
  if (typeof state.showTmdbPosters === 'boolean') showTmdbPosters.value = state.showTmdbPosters
  if (typeof state.showFanartPosters === 'boolean') showFanartPosters.value = state.showFanartPosters
  if (typeof state.showTvdbPosters === 'boolean') showTvdbPosters.value = state.showTvdbPosters
  if (state.logoPreference) logoPreference.value = state.logoPreference
  // Only restore language filters if they're not set to default 'all' (prefer global settings)
  if (state.logoLanguageFilter && state.logoLanguageFilter !== 'all') logoLanguageFilter.value = state.logoLanguageFilter
  if (typeof state.showTmdbLogos === 'boolean') showTmdbLogos.value = state.showTmdbLogos
  if (typeof state.showFanartLogos === 'boolean') showFanartLogos.value = state.showFanartLogos
  if (typeof state.showTvdbLogos === 'boolean') showTvdbLogos.value = state.showTvdbLogos
  if (typeof state.showClearArt === 'boolean') showClearArt.value = state.showClearArt
  if (state.logoMode) logoMode.value = state.logoMode
  if (state.logoHex) logoHex.value = state.logoHex
    if (state.textOverlay) {
      textOverlayEnabled.value = state.textOverlay.enabled ?? false
      customText.value = state.textOverlay.customText ?? ''
      fontFamily.value = state.textOverlay.fontFamily ?? 'Arial'
      fontSize.value = state.textOverlay.fontSize ?? 120
      fontWeight.value = state.textOverlay.fontWeight ?? '700'
      textColor.value = state.textOverlay.textColor ?? '#ffffff'
      textAlign.value = state.textOverlay.textAlign ?? 'center'
      textTransform.value = state.textOverlay.textTransform ?? 'uppercase'
      letterSpacing.value = state.textOverlay.letterSpacing ?? 2
      lineHeight.value = state.textOverlay.lineHeight ?? 120
      positionY.value = state.textOverlay.positionY ?? 75
      shadowEnabled.value = state.textOverlay.shadowEnabled ?? true
      shadowBlur.value = state.textOverlay.shadowBlur ?? 10
      shadowOffsetX.value = state.textOverlay.shadowOffsetX ?? 0
      shadowOffsetY.value = state.textOverlay.shadowOffsetY ?? 4
      shadowColor.value = state.textOverlay.shadowColor ?? '#000000'
      shadowOpacity.value = state.textOverlay.shadowOpacity ?? 80
      strokeEnabled.value = state.textOverlay.strokeEnabled ?? false
      strokeWidth.value = state.textOverlay.strokeWidth ?? 4
      strokeColor.value = state.textOverlay.strokeColor ?? '#000000'
    }
  } catch (e) {
    console.warn('Failed to load editor state:', e)
  }
}

const boundingBoxStyle = computed(() => {
  if (!previewImgRef.value || !showBoundingBox.value || !isUniformLogo.value) return {}

  const img = previewImgRef.value
  const container = img.parentElement as HTMLElement | null
  if (!container) return {}

  const imgRect = img.getBoundingClientRect()
  const containerRect = container.getBoundingClientRect()

  const imgWidth = imgRect.width
  const imgHeight = imgRect.height

  if (!imgWidth || !imgHeight) return {}

  // Get the actual rendered poster dimensions (2000x3000 typical)
  // The preview is scaled down, so we need to calculate scale factor
  const naturalWidth = img.naturalWidth || 2000
  const naturalHeight = img.naturalHeight || 3000
  const scaleX = imgWidth / naturalWidth
  const scaleY = imgHeight / naturalHeight

  // Calculate bounding box dimensions in pixels (from backend perspective)
  const maxW = options.value.uniformLogoMaxW
  const maxH = options.value.uniformLogoMaxH

  // Scale the box dimensions to match the preview
  const boxWidth = maxW * scaleX
  const boxHeight = maxH * scaleY

  // Position offsets (percentages from backend)
  const offsetX = options.value.uniformLogoOffsetX / 100
  const offsetY = options.value.uniformLogoOffsetY / 100

  // Position (centered on offset point) relative to container
  const imageOffsetLeft = imgRect.left - containerRect.left
  const imageOffsetTop = imgRect.top - containerRect.top
  const left = imageOffsetLeft + (imgWidth * offsetX) - (boxWidth / 2)
  const top = imageOffsetTop + (imgHeight * offsetY) - (boxHeight / 2)

  return {
    width: `${boxWidth}px`,
    height: `${boxHeight}px`,
    left: `${left}px`,
    top: `${top}px`
  }
})

const posterCounts = computed(() => {
  const tmdb = posters.value.filter(p => (p.source || 'tmdb').toLowerCase() === 'tmdb').length
  const fanart = posters.value.filter(p => (p.source || 'tmdb').toLowerCase() === 'fanart').length
  const tvdb = posters.value.filter(p => (p.source || 'tmdb').toLowerCase() === 'tvdb').length
  return { tmdb, fanart, tvdb, total: posters.value.length }
})

const filteredPosters = computed(() => {
  let items = posters.value
  if (posterFilter.value === 'textless') {
    // Treat posters with no language or has_text=false as textless
    items = items.filter((p) => p.has_text === false || !p.language)
  } else if (posterFilter.value === 'text') {
    items = items.filter((p) => p.has_text === true)
  }

  // Only apply language filter when not filtering for textless (textless posters don't have language tags)
  if (posterFilter.value !== 'textless' && posterLanguageFilter.value === 'en') {
    items = items.filter((p) => {
      const lang = (p.language || '').toLowerCase()
      return lang === 'en' || lang === 'eng'
    })
  }

  items = items.filter((p) => {
    const src = (p.source || 'tmdb').toLowerCase()
    if (src === 'fanart') return showFanartPosters.value
    if (src === 'tvdb') return showTvdbPosters.value
    return showTmdbPosters.value
  })

  return items
})

const logoCounts = computed(() => {
  const tmdb = logos.value.filter(l => (l.source || 'tmdb').toLowerCase() === 'tmdb').length
  const fanart = logos.value.filter(l => (l.source || 'tmdb').toLowerCase() === 'fanart').length
  const tvdb = logos.value.filter(l => (l.source || 'tmdb').toLowerCase() === 'tvdb').length
  return { tmdb, fanart, tvdb, total: logos.value.length }
})

const filteredLogos = computed(() => {
  let items = logos.value
  // Only apply language filter if there's a language tag (logos without language tags are universal)
  if (logoLanguageFilter.value === 'en') {
    items = items.filter((l) => {
      const lang = (l.language || '').toLowerCase()
      // Include logos with no language (universal) or English language
        return !l.language || lang === 'en' || lang === 'eng'
      })
    }
  // Skip SVG logos for now to avoid missing render dependencies
  items = items.filter((l) => {
    const url = (l.url || '').toLowerCase()
    return !url.endsWith('.svg') && !url.includes('.svg?')
  })
    if (!showClearArt.value) {
      items = items.filter((l) => (l.type || 'logo') === 'logo')
    }
    items = items.filter((l) => {
      const src = (l.source || 'tmdb').toLowerCase()
    if (src === 'fanart') return showFanartLogos.value
    if (src === 'tvdb') return showTvdbLogos.value
    return showTmdbLogos.value
  })
  const scoreLogo = (l: any) => {
    const url = (l.url || '').toLowerCase()
    const likes = Number(l.likes || 0)
    const isWhite = url.includes('white') || url.includes('_w') || url.includes('-w') || url.includes('light')
    if (logoPreference.value === 'white') return (isWhite ? 1000 : 0) + likes
    if (logoPreference.value === 'color') return (isWhite ? -100 : 0) + likes
    return likes
  }
  return [...items].sort((a, b) => scoreLogo(b) - scoreLogo(a))
})

const optionsPayload = computed(() => {
  // Generate season text (e.g., "Season 1" or "Specials") - only for actual seasons, not series
  let seasonText = ""
  if (currentSeason.value && !currentSeason.value.isSeries) {
    if (currentSeason.value.index === 0) {
      seasonText = "Specials"
    } else {
      seasonText = `Season ${currentSeason.value.index}`
    }
  }

  // Replace {season} placeholder in custom text
  const processedCustomText = customText.value.replace('{season}', seasonText)

  const payload: Record<string, any> = {
    poster_zoom: options.value.posterZoom / 100,
    poster_shift_y: options.value.posterShiftY / 100,
    matte_height_ratio: options.value.matteHeight / 100,
    fade_height_ratio: options.value.fadeHeight / 100,
    vignette_strength: options.value.vignette / 100,
    grain_amount: options.value.grain / 100,
    logo_scale: options.value.logoScale / 100,
    logo_offset: options.value.logoOffset / 100,
    uniform_logo_max_w: options.value.uniformLogoMaxW,
    uniform_logo_max_h: options.value.uniformLogoMaxH,
    uniform_logo_offset_x: options.value.uniformLogoOffsetX / 100,
    uniform_logo_offset_y: options.value.uniformLogoOffsetY / 100,
    border_enabled: options.value.borderEnabled,
    border_px: options.value.borderThickness,
    border_color: options.value.borderColor,
    overlay_file: options.value.overlayFile || null,
    overlay_opacity: options.value.overlayOpacity / 100,
    overlay_mode: options.value.overlayMode,
    logo_mode: logoMode.value,
    logo_hex: logoHex.value,
    poster_filter: posterFilter.value,
    logo_preference: logoPreference.value,
    text_overlay_enabled: textOverlayEnabled.value,
    custom_text: processedCustomText,
    font_family: fontFamily.value,
    font_size: fontSize.value,
    font_weight: fontWeight.value,
    text_color: textColor.value,
    text_align: textAlign.value,
    text_transform: textTransform.value,
    letter_spacing: letterSpacing.value,
    line_height: lineHeight.value / 100,
    position_y: positionY.value / 100,
    shadow_enabled: shadowEnabled.value,
    shadow_blur: shadowBlur.value,
    shadow_offset_x: shadowOffsetX.value,
    shadow_offset_y: shadowOffsetY.value,
    shadow_color: shadowColor.value,
    shadow_opacity: shadowOpacity.value / 100,
    stroke_enabled: strokeEnabled.value,
    stroke_width: strokeWidth.value,
    stroke_color: strokeColor.value
  }

  // Only include season_text if it's not empty (for seasons, not series)
  if (seasonText) {
    payload.season_text = seasonText
  }

  return payload
})

const bgUrl = computed(() => selectedPoster.value || '')
const logoUrl = computed(() => (logoMode.value === 'none' ? '' : selectedLogo.value || ''))

const reloadPreset = async () => {
  await presetService.load()
  const p = presets.value.find((x) => x.id === selectedPreset.value)
  if (p?.options) {
    const o = p.options
    // Reset text overlay defaults first
    textOverlayEnabled.value = false
    customText.value = ''
    fontFamily.value = 'Arial'
    fontSize.value = 120
    fontWeight.value = '700'
    textColor.value = '#ffffff'
    textAlign.value = 'center'
    textTransform.value = 'uppercase'
    letterSpacing.value = 2
    lineHeight.value = 120
    positionY.value = 75
    shadowEnabled.value = true
    shadowBlur.value = 10
    shadowOffsetX.value = 0
    shadowOffsetY.value = 4
    shadowColor.value = '#000000'
    shadowOpacity.value = 80
    strokeEnabled.value = false
    strokeWidth.value = 4
    strokeColor.value = '#000000'
    options.value.posterZoom = Math.round((Number(o.poster_zoom) || 1) * 100)
    options.value.posterShiftY = Math.round((Number(o.poster_shift_y) || 0) * 100)
    options.value.matteHeight = Math.round((Number(o.matte_height_ratio) || 0) * 100)
    options.value.fadeHeight = Math.round((Number(o.fade_height_ratio) || 0) * 100)
    options.value.vignette = Math.round((Number(o.vignette_strength) || 0) * 100)
    options.value.grain = Math.round((Number(o.grain_amount) || 0) * 100)
    options.value.logoScale = Math.round((Number(o.logo_scale) || 0.5) * 100)
    options.value.logoOffset = Math.round((Number(o.logo_offset) || 0.75) * 100)
    if (o.uniform_logo_max_w) options.value.uniformLogoMaxW = Number(o.uniform_logo_max_w)
    if (o.uniform_logo_max_h) options.value.uniformLogoMaxH = Number(o.uniform_logo_max_h)
    if (typeof o.uniform_logo_offset_x === 'number') options.value.uniformLogoOffsetX = Math.round(o.uniform_logo_offset_x * 100)
    if (typeof o.uniform_logo_offset_y === 'number') options.value.uniformLogoOffsetY = Math.round(o.uniform_logo_offset_y * 100)
    options.value.borderEnabled = !!o.border_enabled
    options.value.borderThickness = Number(o.border_px) || 0
    if (o.border_color) options.value.borderColor = String(o.border_color)
    if (o.overlay_file) options.value.overlayFile = String(o.overlay_file)
    if (typeof o.overlay_opacity === 'number') options.value.overlayOpacity = Math.round(o.overlay_opacity * 100)
    if (o.overlay_mode) options.value.overlayMode = String(o.overlay_mode)
    if (typeof o.poster_filter === 'string' && ['all', 'textless', 'text'].includes(o.poster_filter)) {
      posterFilter.value = o.poster_filter as 'all' | 'textless' | 'text'
    }
    if (typeof o.logo_preference === 'string' && ['first', 'white', 'color'].includes(o.logo_preference)) {
      logoPreference.value = o.logo_preference as 'first' | 'white' | 'color'
    }
    logoMode.value = normalizeLogoMode(o.logo_mode)
    if (typeof o.logo_hex === 'string') {
      logoHex.value = o.logo_hex
    }

    // Load text overlay settings
    textOverlayEnabled.value = !!o.text_overlay_enabled
    if (typeof o.custom_text === 'string') customText.value = o.custom_text
    if (typeof o.font_family === 'string') fontFamily.value = o.font_family
    if (typeof o.font_size === 'number') fontSize.value = o.font_size
    if (typeof o.font_weight === 'string') fontWeight.value = o.font_weight
    if (typeof o.text_color === 'string') textColor.value = o.text_color
    if (typeof o.text_align === 'string') textAlign.value = o.text_align
    if (typeof o.text_transform === 'string') textTransform.value = o.text_transform
    if (typeof o.letter_spacing === 'number') letterSpacing.value = o.letter_spacing
    if (typeof o.line_height === 'number') lineHeight.value = Math.round(o.line_height * 100)
    if (typeof o.position_y === 'number') positionY.value = Math.round(o.position_y * 100)
    if (typeof o.shadow_enabled === 'boolean') shadowEnabled.value = o.shadow_enabled
    if (typeof o.shadow_blur === 'number') shadowBlur.value = o.shadow_blur
    if (typeof o.shadow_offset_x === 'number') shadowOffsetX.value = o.shadow_offset_x
    if (typeof o.shadow_offset_y === 'number') shadowOffsetY.value = o.shadow_offset_y
    if (typeof o.shadow_color === 'string') shadowColor.value = o.shadow_color
    if (typeof o.shadow_opacity === 'number') shadowOpacity.value = Math.round(o.shadow_opacity * 100)
    if (typeof o.stroke_enabled === 'boolean') strokeEnabled.value = o.stroke_enabled
    if (typeof o.stroke_width === 'number') strokeWidth.value = o.stroke_width
    if (typeof o.stroke_color === 'string') strokeColor.value = o.stroke_color

    applyPosterFilter()
    applyLogoPreference()
    success('Preset reloaded!')
  }
}

const saveCurrentPreset = async () => {
  if (!selectedTemplate.value || !selectedPreset.value) {
    notifyError('Please select a template and preset')
    return
  }

  // Convert frontend options to backend format
  const backendOptions = {
    poster_zoom: options.value.posterZoom / 100,
    poster_shift_y: options.value.posterShiftY / 100,
    matte_height_ratio: options.value.matteHeight / 100,
    fade_height_ratio: options.value.fadeHeight / 100,
    vignette_strength: options.value.vignette / 100,
    grain_amount: options.value.grain / 100,
    logo_scale: options.value.logoScale / 100,
    logo_offset: options.value.logoOffset / 100,
    uniform_logo_max_w: options.value.uniformLogoMaxW,
    uniform_logo_max_h: options.value.uniformLogoMaxH,
    uniform_logo_offset_x: options.value.uniformLogoOffsetX / 100,
    uniform_logo_offset_y: options.value.uniformLogoOffsetY / 100,
    border_enabled: options.value.borderEnabled,
    border_px: options.value.borderThickness,
    border_color: options.value.borderColor,
    overlay_file: options.value.overlayFile,
    overlay_opacity: options.value.overlayOpacity / 100,
    overlay_mode: options.value.overlayMode,
    poster_filter: posterFilter.value,
    logo_preference: logoPreference.value,
    logo_mode: logoMode.value,
    logo_hex: logoHex.value,
    text_overlay_enabled: textOverlayEnabled.value,
    custom_text: customText.value,
    font_family: fontFamily.value,
    font_size: fontSize.value,
    font_weight: fontWeight.value,
    text_color: textColor.value,
    text_align: textAlign.value,
    text_transform: textTransform.value,
    letter_spacing: letterSpacing.value,
    line_height: lineHeight.value / 100,
    position_y: positionY.value / 100,
    shadow_enabled: shadowEnabled.value,
    shadow_blur: shadowBlur.value,
    shadow_offset_x: shadowOffsetX.value,
    shadow_offset_y: shadowOffsetY.value,
    shadow_color: shadowColor.value,
    shadow_opacity: shadowOpacity.value / 100,
    stroke_enabled: strokeEnabled.value,
    stroke_width: strokeWidth.value,
    stroke_color: strokeColor.value
  }

  await presetService.savePreset(backendOptions)
  if (!presetService.error.value) {
    success('Preset saved!')
  } else {
    notifyError(`Failed to save: ${presetService.error.value}`)
  }
}

const saveAsNewPreset = async () => {
  if (!newPresetId.value.trim()) {
    notifyError('Enter a preset id to save as')
    return
  }

  const backendOptions = {
    poster_zoom: options.value.posterZoom / 100,
    poster_shift_y: options.value.posterShiftY / 100,
    matte_height_ratio: options.value.matteHeight / 100,
    fade_height_ratio: options.value.fadeHeight / 100,
    vignette_strength: options.value.vignette / 100,
    grain_amount: options.value.grain / 100,
    logo_scale: options.value.logoScale / 100,
    logo_offset: options.value.logoOffset / 100,
    uniform_logo_max_w: options.value.uniformLogoMaxW,
    uniform_logo_max_h: options.value.uniformLogoMaxH,
    uniform_logo_offset_x: options.value.uniformLogoOffsetX / 100,
    uniform_logo_offset_y: options.value.uniformLogoOffsetY / 100,
    border_enabled: options.value.borderEnabled,
    border_px: options.value.borderThickness,
    border_color: options.value.borderColor,
    overlay_file: options.value.overlayFile,
    overlay_opacity: options.value.overlayOpacity / 100,
    overlay_mode: options.value.overlayMode,
    poster_filter: posterFilter.value,
    logo_preference: logoPreference.value,
    logo_mode: logoMode.value,
    logo_hex: logoHex.value,
    text_overlay_enabled: textOverlayEnabled.value,
    custom_text: customText.value,
    font_family: fontFamily.value,
    font_size: fontSize.value,
    font_weight: fontWeight.value,
    text_color: textColor.value,
    text_align: textAlign.value,
    text_transform: textTransform.value,
    letter_spacing: letterSpacing.value,
    line_height: lineHeight.value / 100,
    position_y: positionY.value / 100,
    shadow_enabled: shadowEnabled.value,
    shadow_blur: shadowBlur.value,
    shadow_offset_x: shadowOffsetX.value,
    shadow_offset_y: shadowOffsetY.value,
    shadow_color: shadowColor.value,
    shadow_opacity: shadowOpacity.value / 100,
    stroke_enabled: strokeEnabled.value,
    stroke_width: strokeWidth.value,
    stroke_color: strokeColor.value
  }

  const newId = newPresetId.value.trim()
  await presetService.savePresetAs(newId, backendOptions)
  if (!presetService.error.value) {
    selectedPreset.value = newId
    success('Preset saved as new!')
    newPresetId.value = ''
  } else {
    notifyError(`Failed to save: ${presetService.error.value}`)
  }
}

const applyLogoPreference = () => {
  if (!logos.value.length) return
  if (logoMode.value === 'none') return
  const ordered = filteredLogos.value
  if (!ordered.length) return
  selectedLogo.value = ordered[0]?.url || null
}

const applyPosterFilter = () => {
  const isSeason = !!(currentSeason.value && !currentSeason.value.isSeries)
  const seasonPosters = posters.value || []
  const seriesPosters = showLevelAssets.value.posters || []
  if (!seasonPosters.length && !(isSeason && seriesPosters.length)) return

  if (posterFilter.value === 'textless') {
    const seasonTextless = seasonPosters.find((p) => p.has_text === false)
    const seriesTextless = isSeason ? seriesPosters.find((p: any) => p.has_text === false) : null
    const choice = seasonTextless || seriesTextless

    // If no textless at all, keep existing selection or first season poster
    if (choice) {
      // Replace selection if it's empty or currently not textless
      if (!selectedPoster.value) selectedPoster.value = choice.url
      else {
        const currentIsTextless = [...seasonPosters, ...seriesPosters].some((p) => p.url === selectedPoster.value && p.has_text === false)
        if (!currentIsTextless) selectedPoster.value = choice.url
      }
    } else if (!selectedPoster.value) {
      selectedPoster.value = seasonPosters[0]?.url || null
    }
  } else if (posterFilter.value === 'text') {
    const withText = seasonPosters.find((p) => p.has_text === true)
    if (withText) selectedPoster.value = withText.url
    else if (!selectedPoster.value) selectedPoster.value = seasonPosters[0]?.url || null
  } else if (!selectedPoster.value && seasonPosters.length) {
    const firstPoster = seasonPosters[0]
    if (firstPoster) selectedPoster.value = firstPoster.url
  }
}

const fetchTmdbAssets = async () => {
  posters.value = []
  logos.value = []
  selectedPoster.value = null
  selectedLogo.value = null
  seasonAssetsCache.value = {}
  showLevelAssets.value = { posters: [], logos: [], backdrops: [] }
  try {
    // Detect media type (movie or TV show)
    const mediaType = props.movie.mediaType || 'movie'
    const isTvShow = mediaType === 'tv-show'

    // Use appropriate endpoint for TMDB ID lookup
    const tmdbEndpoint = isTvShow
      ? `${apiBase}/api/tv-show/${props.movie.key}/tmdb`
      : `${apiBase}/api/movie/${props.movie.key}/tmdb`

  const tmdbRes = await fetch(tmdbEndpoint)
  const tmdb = await tmdbRes.json()
  tmdbId.value = tmdb.tmdb_id || null
  tvdbId.value = tmdb.tvdb_id || null
  if (!tmdbId.value) return

    // Use appropriate endpoint for images
  const tvdbQuery = tvdbId.value ? `&tvdb_id=${tvdbId.value}` : ''
  const imagesEndpoint = isTvShow
    ? `${apiBase}/api/tmdb/tv/${tmdbId.value}/images?${tvdbQuery.replace(/^&/, '')}`
    : `${apiBase}/api/tmdb/${tmdbId.value}/images`

    const imgRes = await fetch(imagesEndpoint)
    const imgs = await imgRes.json()
    posters.value = imgs.posters || []
    logos.value = imgs.logos || []
    showLevelAssets.value = {
      posters: imgs.posters || [],
      logos: imgs.logos || [],
      backdrops: imgs.backdrops || []
    }
    applyPosterFilter()
    applyLogoPreference()
    ensurePosterSelected()
  } catch (e) {
    console.error(e)
  }
}

const fetchImagesForSeason = async (season: Season) => {
  if (!tmdbId.value) return

  // Series entry uses show-level assets
  if (season.isSeries) {
    return {
      posters: showLevelAssets.value.posters || [],
      logos: showLevelAssets.value.logos || [],
      backdrops: showLevelAssets.value.backdrops || []
    }
  }

  // Use cached assets if available
  const cached = seasonAssetsCache.value[season.key]
  if (cached) {
    return cached
  }

  try {
    const tvdbQuery = tvdbId.value ? `&tvdb_id=${tvdbId.value}` : ''
    const imgRes = await fetch(`${apiBase}/api/tmdb/tv/${tmdbId.value}/images?season=${season.index}${tvdbQuery}`)
    if (!imgRes.ok) throw new Error('Failed to fetch season images')
    const imgs = await imgRes.json()
    const assets = {
      posters: imgs.posters || [],
      logos: imgs.logos || [],
      backdrops: imgs.backdrops || []
    }
    seasonAssetsCache.value[season.key] = assets
    return assets
  } catch (err) {
    console.error('Failed to fetch season images:', err)
    return { posters: [], logos: [], backdrops: [] }
  }
}

const fetchImagesForCurrentSeason = async (skipRestore = false) => {
  const season = currentSeason.value
  if (!season) return

  const assets = await fetchImagesForSeason(season)
  if (assets) {
    const seasonPosters = assets.posters || []
    posters.value = seasonPosters

    // For seasons with textless filter, also include series textless posters
    // Season posters are shown FIRST, then series posters are appended
    if (!season.isSeries && posterFilter.value === 'textless') {
      const seriesTextlessPosters = (showLevelAssets.value.posters || [])
        .filter((p: any) => p.has_text === false)

      if (seriesTextlessPosters.length > 0) {
        // Add series textless posters to the END of the list with a marker
        const markedSeriesPosters = seriesTextlessPosters.map((p: any) => ({
          ...p,
          _isSeriesPoster: true  // Mark so we can show in UI
        }))
        // Season posters first, then series posters
        posters.value = [...seasonPosters, ...markedSeriesPosters]
        console.log(`[FETCH IMAGES] Poster order: ${seasonPosters.length} season posters, then ${seriesTextlessPosters.length} series textless posters`)
      }
    }

    logos.value = assets.logos || []
    applyPosterFilter()
    applyLogoPreference()
    if (!season.isSeries && !skipRestore) {
      restoreSettingsForCurrent()
    }
  }
}

// Fetch assets for all selected seasons in parallel
const fetchAssetsForAllSeasons = async () => {
  console.log('[FETCH ASSETS] Called fetchAssetsForAllSeasons(), tmdbId:', tmdbId.value)

  if (!tmdbId.value) {
    console.log('[FETCH ASSETS] No tmdbId, returning early')
    return
  }

  const selectedKeys = Array.from(selectedSeasons.value)
  const seasonsToFetch = selectedKeys
    .map(key => seasons.value.find(s => s.key === key))
    .filter(Boolean) as Season[]

  console.log('[FETCH ASSETS] Fetching assets for', seasonsToFetch.length, 'seasons')

  await Promise.all(seasonsToFetch.map(season => fetchImagesForSeason(season)))

  console.log('[FETCH ASSETS] All assets fetched')
}

const fetchLabels = async () => {
  try {
    // Use appropriate endpoint based on media type
    const mediaType = props.movie.mediaType || 'movie'
    const isTvShow = mediaType === 'tv-show'
    const labelsEndpoint = isTvShow
      ? `${apiBase}/api/tv-show/${props.movie.key}/labels`
      : `${apiBase}/api/movie/${props.movie.key}/labels`

    const res = await fetch(labelsEndpoint)
    if (!res.ok) return
    const data = await res.json()
    labels.value = data.labels || []
    // Apply default labels to remove from settings
    const defaultLabelsConfig = settings.defaultLabelsToRemove.value || {}
    let defaultToRemove: string[] = []

    // Handle both legacy array format and new Record format
    if (Array.isArray(defaultLabelsConfig)) {
      defaultToRemove = defaultLabelsConfig
    } else {
      // Get labels from all libraries (since we don't have library context here)
      defaultToRemove = Object.values(defaultLabelsConfig).flat()
    }

    selectedLabels.value = new Set(defaultToRemove.filter((label: string) => labels.value.includes(label)))
  } catch (e) {
    console.error(e)
  }
}

const updateGlobalPosterCache = (key: string, url: string | null) => {
  if (typeof sessionStorage === 'undefined') return
  try {
    const raw = sessionStorage.getItem(POSTER_CACHE_KEY)
    const cache = raw ? JSON.parse(raw) : {}
    cache[key] = url
    sessionStorage.setItem(POSTER_CACHE_KEY, JSON.stringify(cache))
    // Update shared movies list so search/header reflect the new poster immediately
    setMoviePoster(key, url)
  } catch {
    /* ignore */
  }
}

const fetchExistingPoster = async (forceRefresh?: boolean | Event) => {
  try {
    // Handle both boolean and Event parameter
    const refreshFlag = typeof forceRefresh === 'boolean'
      ? forceRefresh
      : (forceRefresh instanceof Event ? true : false)
    
    // Use current season key if available, otherwise use series key
    const targetKey = currentSeason.value?.key || props.movie.key
    
    console.log('[EXISTING POSTER] Fetching for target:', targetKey, 'forceRefresh:', refreshFlag)
    
    const res = await fetch(`${apiBase}/api/movie/${targetKey}/poster?meta=1${refreshFlag ? '&force_refresh=1' : ''}`)
    if (!res.ok) {
      existingPoster.value = null
      updateGlobalPosterCache(targetKey, null)
      posterRefreshKey.value += 1
      return
    }
    const data = await res.json()
    if (data.url) {
      // Use absolute URL so it works when API is on another host/port
      existingPoster.value = data.url.startsWith('http')
        ? data.url
        : `${apiBase}${data.url}`
      updateGlobalPosterCache(targetKey, existingPoster.value)

      console.log('[EXISTING POSTER] Updated to:', existingPoster.value)

      // Update the thumbnail for the target season/series in the left list
      seasons.value = seasons.value.map(s => s.key === targetKey ? { ...s, thumb: existingPoster.value || s.thumb } : s)
    } else {
      existingPoster.value = null
      updateGlobalPosterCache(targetKey, null)
    }
    // Force re-render by toggling key
    posterRefreshKey.value += 1
  } catch (err) {
    console.error('Failed to fetch existing poster:', err)
    existingPoster.value = null
    updateGlobalPosterCache(props.movie.key, null)
    posterRefreshKey.value += 1
  }
}

const toggleLabel = (label: string) => {
  const set = new Set(selectedLabels.value)
  if (set.has(label)) set.delete(label)
  else set.add(label)
  selectedLabels.value = set
}

const doPreview = async (skipBackgroundRender = false) => {
  if (!bgUrl.value) return
  // Cache current settings before rendering
  saveCurrentSettings()

  // Capture reactive values at the start to prevent race conditions
  // If user clicks to switch seasons while render is in progress,
  // we want to use the season info from when render started, not when it completes
  const season = currentSeason.value
  const capturedBgUrl = bgUrl.value
  const capturedLogoUrl = logoUrl.value
  const capturedTemplate = selectedTemplate.value
  const capturedPreset = selectedPreset.value

  // Capture season text at the start to prevent wrong text appearing
  let capturedSeasonText = ""
  if (season && !season.isSeries) {
    if (season.index === 0) {
      capturedSeasonText = "Specials"
    } else {
      capturedSeasonText = `Season ${season.index}`
    }
  }

  // Build options payload with captured season text
  const processedCustomText = customText.value.replace('{season}', capturedSeasonText)

  const capturedOptionsPayload: Record<string, any> = {
    poster_zoom: options.value.posterZoom / 100,
    poster_shift_y: options.value.posterShiftY / 100,
    matte_height_ratio: options.value.matteHeight / 100,
    fade_height_ratio: options.value.fadeHeight / 100,
    vignette_strength: options.value.vignette / 100,
    grain_amount: options.value.grain / 100,
    logo_scale: options.value.logoScale / 100,
    logo_offset: options.value.logoOffset / 100,
    uniform_logo_max_w: options.value.uniformLogoMaxW,
    uniform_logo_max_h: options.value.uniformLogoMaxH,
    uniform_logo_offset_x: options.value.uniformLogoOffsetX / 100,
    uniform_logo_offset_y: options.value.uniformLogoOffsetY / 100,
    border_enabled: options.value.borderEnabled,
    border_px: options.value.borderThickness,
    border_color: options.value.borderColor,
    overlay_file: options.value.overlayFile || null,
    overlay_opacity: options.value.overlayOpacity / 100,
    overlay_mode: options.value.overlayMode,
    logo_mode: logoMode.value,
    logo_hex: logoHex.value,
    poster_filter: posterFilter.value,
    logo_preference: logoPreference.value,
    text_overlay_enabled: textOverlayEnabled.value,
    custom_text: processedCustomText,
    font_family: fontFamily.value,
    font_size: fontSize.value,
    font_weight: fontWeight.value,
    text_color: textColor.value,
    text_align: textAlign.value,
    text_transform: textTransform.value,
    letter_spacing: letterSpacing.value,
    line_height: lineHeight.value / 100,
    position_y: positionY.value / 100,
    shadow_enabled: shadowEnabled.value,
    shadow_blur: shadowBlur.value,
    shadow_offset_x: shadowOffsetX.value,
    shadow_offset_y: shadowOffsetY.value,
    shadow_color: shadowColor.value,
    shadow_opacity: shadowOpacity.value / 100,
    stroke_enabled: strokeEnabled.value,
    stroke_width: strokeWidth.value,
    stroke_color: strokeColor.value
  }

  // Only include season_text if it's not empty (for seasons, not series)
  if (capturedSeasonText) {
    capturedOptionsPayload.season_text = capturedSeasonText
  }

  console.log('[PREVIEW] Starting with:', {
    target: season?.key || props.movie.key,
    seasonTitle: season?.title,
    capturedSeasonText,
    logoMode: logoMode.value,
    textOverlayEnabled: textOverlayEnabled.value,
    customText: customText.value,
    fontSize: fontSize.value
  })
  console.log('[PREVIEW] Full capturedOptionsPayload:', capturedOptionsPayload)
  console.log('[PREVIEW] capturedOptionsPayload.text_overlay_enabled:', capturedOptionsPayload.text_overlay_enabled)
  console.log('[PREVIEW] capturedOptionsPayload.custom_text:', capturedOptionsPayload.custom_text)
  console.log('[PREVIEW] capturedOptionsPayload.season_text:', capturedOptionsPayload.season_text)

  // Generate cache key based on captured settings
  const cacheKey = season ? `${season.key}_${capturedBgUrl}_${capturedLogoUrl}_${JSON.stringify(capturedOptionsPayload)}` : ''

  // Check if we have a cached render for these exact settings
  if (cacheKey && renderedPreviewCache.value[cacheKey]) {
    console.log('[PREVIEW] Using cached render for', season?.title)
    lastPreview.value = renderedPreviewCache.value[cacheKey]
    return
  }

  // Render and cache the result using captured values
  await render.preview(props.movie, capturedBgUrl, capturedLogoUrl, capturedOptionsPayload, capturedTemplate, capturedPreset)

  // Store in cache if we have a season key
  if (cacheKey && lastPreview.value) {
    renderedPreviewCache.value[cacheKey] = lastPreview.value
  }

  // After rendering current season, render all other selected seasons in background
  // Skip if caller will handle background rendering (e.g., selectAllSeasons)
  if (!skipBackgroundRender) {
    renderAllSelectedSeasons()
  }
}

// Render all selected seasons in the background so they're ready when user clicks them
const renderAllSelectedSeasons = async () => {
  console.log('[RENDER ALL] Called renderAllSelectedSeasons()')

  const selectedKeys = Array.from(selectedSeasons.value)
  const currentKey = currentSeason.value?.key

  console.log('[RENDER ALL] selectedKeys:', selectedKeys)
  console.log('[RENDER ALL] currentKey:', currentKey)

  // Capture reactive values at the start to prevent race conditions
  const currentTemplate = selectedTemplate.value
  const currentPreset = selectedPreset.value
  const currentLogoUrl = logoUrl.value

  // Get base options but remove season-specific processed values
  const baseOptions = { ...optionsPayload.value }
  // Only remove custom_text and season_text which are already processed for current season
  // Keep text_overlay_enabled and logo_mode - they'll be handled per-season below
  delete (baseOptions as any).custom_text
  delete (baseOptions as any).season_text

  // Build array of seasons to render (excluding current which is already rendered)
  const seasonsToRender = selectedKeys
    .filter(key => key !== currentKey)
    .map(key => seasons.value.find(s => s.key === key))
    .filter(Boolean) as Season[]

  console.log('[BACKGROUND RENDER] Starting parallel render for', seasonsToRender.length, 'seasons')

  // Render all seasons in parallel for better performance
  const renderPromises = seasonsToRender.map(async (season) => {
    // Capture season details early to avoid race conditions
    const seasonKey = season.key
    const seasonTitle = season.title
    const seasonIsSeries = season.isSeries
    const seasonIndex = season.index

    // Get the poster URL for this specific season
    const seasonPosterUrl = season.thumb || season.poster || posterUrlForRatingKey(seasonKey)
    if (!seasonPosterUrl) {
      console.warn('[BACKGROUND RENDER] No poster URL for', seasonTitle)
      return
    }

    // Check if user manually selected a different poster for this season
    const cachedPoster = selectedPosterCache.value[seasonKey]
    let seasonBgUrl = cachedPoster || seasonPosterUrl

    console.log(`[BACKGROUND RENDER] ${seasonTitle} - Poster selection:`, {
      hasCachedPoster: !!cachedPoster,
      defaultPosterUrl: seasonPosterUrl,
      posterFilter: posterFilter.value
    })

    // Only apply poster filter if we don't have a manually selected poster
    // and we have assets cached for this season
    if (!cachedPoster) {
      const seasonAssets = seasonAssetsCache.value[seasonKey]
      const seasonPosters = seasonAssets?.posters || []
      const seriesPosters = showLevelAssets.value.posters || []
      const isSeason = !seasonIsSeries

      console.log(`[BACKGROUND RENDER] ${seasonTitle} - Available posters:`, {
        seasonPostersCount: seasonPosters.length,
        seriesPostersCount: seriesPosters.length,
        isSeason
      })

      // Apply poster filter based on available assets
      // For textless filter: check season posters first, then fall back to series textless
      if (posterFilter.value === 'textless') {
        // Find textless poster for this season
        const seasonTextless = seasonPosters.find((p) => p.has_text === false)
        // For seasons (not series), also consider series textless posters as fallback
        const seriesTextless = isSeason ? seriesPosters.find((p: any) => p.has_text === false) : null
        const choice = seasonTextless || seriesTextless

        if (choice) {
          seasonBgUrl = choice.url
          const source = seasonTextless ? 'season' : 'series'
          console.log(`[BACKGROUND RENDER] ${seasonTitle} - Using ${source} textless poster:`, choice.url.substring(0, 80))
        } else {
          console.log(`[BACKGROUND RENDER] ${seasonTitle} - No textless poster found (season or series), using Plex default`)
        }
      } else if (seasonPosters.length > 0) {
        // For text/all filters, only use season-specific posters if available
        if (posterFilter.value === 'text') {
          // Find poster with text for this season
          const withText = seasonPosters.find((p) => p.has_text === true)
          if (withText) {
            seasonBgUrl = withText.url
            console.log(`[BACKGROUND RENDER] ${seasonTitle} - Using text poster:`, withText.url.substring(0, 80))
          } else {
            console.log(`[BACKGROUND RENDER] ${seasonTitle} - No text poster found, using Plex default`)
          }
        } else {
          // Filter is 'all' - use first available TMDB/Fanart poster
          seasonBgUrl = seasonPosters[0]?.url || seasonPosterUrl
          console.log(`[BACKGROUND RENDER] ${seasonTitle} - Using first available poster (all):`, seasonBgUrl.substring(0, 80))
        }
      } else {
        console.log(`[BACKGROUND RENDER] ${seasonTitle} - No TMDB/Fanart season assets, using Plex default`)
      }
      // If no cached assets, just use the season's default Plex poster
    } else {
      console.log(`[BACKGROUND RENDER] ${seasonTitle} - Using cached manual selection:`, cachedPoster.substring(0, 80))
    }

    // Get cached settings for this season
    const cachedSettings = settingsCache.value[seasonKey]

    // Build options using preset defaults + any cached customizations
    let seasonOptions = { ...baseOptions }

    // Add season_text for season-specific rendering
    let thisSeasonText = ''
    console.log(`[BACKGROUND RENDER] ${seasonTitle} - isSeries=${seasonIsSeries}, index=${seasonIndex}`)
    if (!seasonIsSeries) {
      thisSeasonText = seasonTitle.includes('Special') ? 'Specials' : `Season ${seasonIndex}`
      seasonOptions.season_text = thisSeasonText
      console.log(`[BACKGROUND RENDER] ${seasonTitle} - Set season_text to "${thisSeasonText}"`)
    } else {
      // Explicitly ensure no season_text for series poster
      console.log('[BACKGROUND RENDER] Rendering series poster - no season_text')
    }

    // For background renders, don't send text overlay, logo mode, or custom text
    // Let the backend preset's season_options define these per-season
    // Only send season_text so backend can use it for {season} placeholder replacement
    const hasUserModifications = cachedSettings && userModifiedFields.value[seasonKey]?.size > 0

    if (!hasUserModifications) {
      // No user modifications - let backend preset season_options handle everything
      // Remove fields that should come from preset season_options
      const fieldsToRemove = [
        'text_overlay_enabled', 'custom_text', 'logo_mode', 'font_size', 'font_family',
        'font_weight', 'text_color', 'text_align', 'text_transform', 'letter_spacing', 'line_height',
        'position_y', 'shadow_enabled', 'shadow_blur', 'shadow_offset_x', 'shadow_offset_y',
        'shadow_color', 'shadow_opacity', 'stroke_enabled', 'stroke_width', 'stroke_color'
      ]
      seasonOptions = Object.keys(seasonOptions).reduce((acc, key) => {
        if (!fieldsToRemove.includes(key)) {
          (acc as any)[key] = (seasonOptions as any)[key]
        }
        return acc
      }, {} as any)
      // Keep season_text for backend placeholder replacement (only if not empty)
      if (thisSeasonText) {
        seasonOptions.season_text = thisSeasonText
      }
    } else {
      // User has modified this season - apply their customizations
      if (cachedSettings.logoMode) seasonOptions.logo_mode = cachedSettings.logoMode
      if (cachedSettings.textOverlayEnabled !== undefined) {
        seasonOptions.text_overlay_enabled = cachedSettings.textOverlayEnabled
        // Send custom_text as-is (with {season} template) - let backend replace it
        if (cachedSettings.customText !== undefined) {
          seasonOptions.custom_text = cachedSettings.customText
        }
      }
      if (cachedSettings.fontSize) seasonOptions.font_size = cachedSettings.fontSize
      if (cachedSettings.fontFamily) seasonOptions.font_family = cachedSettings.fontFamily
    }

    const seasonLogoUrl = cachedSettings?.selectedLogo || currentLogoUrl

    // Generate cache key
    const cacheKey = `${seasonKey}_${seasonBgUrl}_${seasonLogoUrl}_${JSON.stringify(seasonOptions)}`

    // Check if already in preview cache
    const existingPreview = renderedPreviews.value.find(p => p.seasonKey === seasonKey)
    if (existingPreview?.imageUrl) {
      console.log('[BACKGROUND RENDER] Already have preview for', season.title)
      return
    }

    // Render in background
    console.log(`[BACKGROUND RENDER] ${seasonTitle} - Starting render (user modified: ${hasUserModifications})`)
    console.log(`[BACKGROUND RENDER] ${seasonTitle} - Options:`, {
      text_overlay_enabled: seasonOptions.text_overlay_enabled,
      custom_text: seasonOptions.custom_text,
      season_text: seasonOptions.season_text,
      logo_mode: seasonOptions.logo_mode,
      poster_filter: seasonOptions.poster_filter
    })
    try {
      const result = await render.preview(
        props.movie,
        seasonBgUrl,
        seasonLogoUrl,
        seasonOptions,
        currentTemplate,
        currentPreset,
        false, // Enable caching for performance
        true   // Skip lastPreview update for background renders
      )

      // Get the image data directly from the result instead of the shared lastPreview
      if (result?.image_base64) {
        const imageUrl = `data:image/jpeg;base64,${result.image_base64}`

        // Cache the result
        renderedPreviewCache.value[cacheKey] = imageUrl

        // Update or add to renderedPreviews using captured seasonKey and seasonTitle
        const existingIndex = renderedPreviews.value.findIndex(p => p.seasonKey === seasonKey)
        if (existingIndex >= 0) {
          renderedPreviews.value[existingIndex]!.imageUrl = imageUrl
        } else {
          renderedPreviews.value.push({
            seasonKey,
            seasonTitle,
            imageUrl: imageUrl
          })
        }
        console.log(`[BACKGROUND RENDER] ${seasonTitle} - Completed successfully`)
      } else {
        console.warn(`[BACKGROUND RENDER] ${seasonTitle} - No image data returned`)
      }
    } catch (err) {
      console.error(`[BACKGROUND RENDER] ${seasonTitle} - Failed:`, err)
    }
  })

  // Wait for all renders to complete
  await Promise.all(renderPromises)

  const successCount = renderedPreviews.value.filter(p => p.imageUrl).length
  const totalCount = seasonsToRender.length
  console.log(`[BACKGROUND RENDER] Completed ${successCount}/${totalCount} renders`)
}

const doSave = async () => {
  if (!bgUrl.value) return

  // Get selected seasons or use the movie itself if no seasons
  const selectedSeasonKeys = Array.from(selectedSeasons.value)

  if (selectedSeasonKeys.length === 0) {
    notifyError('No seasons selected')
    return
  }

  // Save for each selected season
  for (const seasonKey of selectedSeasonKeys) {
    const season = seasons.value.find(s => s.key === seasonKey)
    if (!season) continue

    // Create a temporary movie object for this season
    const seasonMovie = { ...props.movie, key: seasonKey, title: season.title }
    const res = await render.save(seasonMovie, bgUrl.value, logoUrl.value, optionsPayload.value, selectedTemplate.value, selectedPreset.value)

    if (res && typeof res.saved_path === 'string') {
      success(`Saved ${season.title} to ${res.saved_path}`)
    } else {
      success(`Saved ${season.title} to disk`)
    }
  }
}

const doSend = async () => {
  if (!bgUrl.value) return

  // Get selected seasons or use the movie itself if no seasons
  const selectedSeasonKeys = Array.from(selectedSeasons.value)

  if (selectedSeasonKeys.length === 0) {
    notifyError('No seasons selected')
    return
  }

  const succeeded: string[] = []
  const failed: string[] = []

  try {
    // Save the current target settings before iterating
    saveCurrentSettings()

    // Preserve current target settings to restore after send
    const originalKey = currentTargetKey.value
    const originalSettings = getCurrentSettings()
    const originalPoster = selectedPoster.value

    console.log(`[SEND TO PLEX] Sending ${selectedSeasonKeys.length} season(s)`)

    // Send for each selected season
    for (const seasonKey of selectedSeasonKeys) {
      const season = seasons.value.find(s => s.key === seasonKey)
      if (!season) continue

      try {
        // Switch context to the target season/series and load its cached settings
        const idxInSelected = Array.from(selectedSeasons.value).findIndex(k => k === seasonKey)
        if (idxInSelected >= 0) currentSeasonIndex.value = idxInSelected
        await fetchImagesForCurrentSeason()
        await restoreSettingsForKey(seasonKey)

        // Create a temporary movie object for this season
        const seasonMovie = { ...props.movie, key: seasonKey, title: season.title }
        await render.send(seasonMovie, bgUrl.value, logoUrl.value, optionsPayload.value, Array.from(selectedLabels.value), selectedTemplate.value, selectedPreset.value)

        succeeded.push(season.title)
        console.log(`[SEND TO PLEX] ${season.title} - Success`)
      } catch (err) {
        failed.push(season.title)
        console.error(`[SEND TO PLEX] ${season.title} - Failed:`, err)
      }
    }

    // Restore original editing context/settings/poster
    if (originalKey) {
      settingsCache.value[originalKey] = originalSettings
      if (originalPoster) selectedPosterCache.value[originalKey] = originalPoster
      await restoreSettingsForKey(originalKey)
      // Restore current season index to the original selection if possible
      const origIdx = Array.from(selectedSeasons.value).findIndex(k => k === originalKey)
      if (origIdx >= 0) currentSeasonIndex.value = origIdx
    }

    // Show results
    if (succeeded.length > 0) {
      const seasonList = succeeded.join(', ')
      success(`Successfully sent ${succeeded.length} poster(s): ${seasonList}`)
    }
    if (failed.length > 0) {
      const seasonList = failed.join(', ')
      notifyError(`Failed to send ${failed.length} poster(s): ${seasonList}`)
    }

    console.log(`[SEND TO PLEX] Completed - ${succeeded.length} succeeded, ${failed.length} failed`)

    // Wait 600ms for Plex to process, then refresh poster and labels
    await new Promise(resolve => setTimeout(resolve, 600))
    await fetchExistingPoster(true)
    await fetchLabels()
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to send posters to Plex'
    notifyError(message)
    console.error('[SEND TO PLEX] Fatal error:', err)
  }
}

// Fetch TV show seasons
async function fetchSeasons() {
  if (!props.movie?.key) return

  const cached = seasonsCache.value[props.movie.key]
  if (cached && cached.length) {
    const seriesEntry = buildSeriesEntry()
    seasons.value = [seriesEntry, ...cached]
    // Only select the series poster by default
    selectedSeasons.value = new Set([seriesEntry.key])
    currentSeasonIndex.value = 0
    syncRenderedPlaceholders()
    return
  }

  try {
    const response = await fetch(`${apiBase}/api/tv-show/${props.movie.key}/seasons`)
    if (!response.ok) throw new Error('Failed to fetch seasons')
    const data = await response.json()

    // Convert Plex thumb URLs to full URLs and prepend a series-level entry
    const mappedSeasons = (data.seasons || []).map((s: Season) => ({
      ...s,
      thumb: posterUrlForRatingKey(s.key) || toPlexPosterUrl(s.poster || s.thumb)
    }))

    const seriesEntry = buildSeriesEntry()
    seasons.value = [seriesEntry, ...mappedSeasons]

    // Cache for subsequent opens
    seasonsCache.value[props.movie.key] = mappedSeasons
    saveSeasonsCache()

    // Only select the series poster by default
    selectedSeasons.value = new Set([seriesEntry.key])
    currentSeasonIndex.value = 0
    syncRenderedPlaceholders()
  } catch (err) {
    console.error('Failed to fetch seasons:', err)
    notifyError('Failed to load TV show seasons')
  }
}

// Toggle season selection
// Toggle selection only (for checkboxes) - doesn't change focus/preview
function toggleSelectionOnly(seasonKey: string) {
  const wasSelected = selectedSeasons.value.has(seasonKey)
  const newSelection = new Set(selectedSeasons.value)

  if (wasSelected) {
    newSelection.delete(seasonKey)
    // Ensure at least one item is always selected
    if (newSelection.size === 0) {
      const seriesKey = seasons.value.find(s => s.isSeries)?.key || props.movie.key
      newSelection.add(seriesKey)
    }
  } else {
    newSelection.add(seasonKey)
  }

  selectedSeasons.value = newSelection
  // Trigger background render for newly selected/deselected items
  renderAllSelectedSeasons()
}

async function toggleSeasonSelection(seasonKey: string) {
  // Persist current target settings before switching to avoid bleed-over
  saveCurrentSettings()

  const season = seasons.value.find(s => s.key === seasonKey)
  if (!season) return

  const wasSelected = selectedSeasons.value.has(seasonKey)
  const isCurrentlyFocused = currentSeason.value?.key === seasonKey

  // If clicking an already-selected season that's currently focused, deselect it
  // Otherwise, if it's selected but not focused, just switch to it
  // If it's not selected, add it and switch to it
  const newSelection = new Set(selectedSeasons.value)

  if (wasSelected && isCurrentlyFocused) {
    // Deselect the focused season
    newSelection.delete(seasonKey)
    selectedSeasons.value = newSelection

    // If no seasons left, force select the series
    if (newSelection.size === 0) {
      const seriesKey = seasons.value.find(s => s.isSeries)?.key || props.movie.key
      selectedSeasons.value = new Set([seriesKey])
      currentSeasonIndex.value = 0
      await nextTick()
      await fetchImagesForCurrentSeason()
      restoreSettingsForCurrent()
      await fetchExistingPoster()
      syncRenderedPlaceholders()
      await doPreview()
    } else {
      // Just removed a season, sync the rendered previews
      syncRenderedPlaceholders()
    }
  } else if (wasSelected && !isCurrentlyFocused) {
    // Season already selected, just switch focus to it (use cached render if available)
    const selected = Array.from(newSelection)
    const idx = selected.findIndex(k => k === seasonKey)
    currentSeasonIndex.value = idx >= 0 ? idx : 0
    await nextTick()
    await fetchImagesForCurrentSeason()
    restoreSettingsForCurrent()
    await fetchExistingPoster()

    // Check if we already have a rendered preview for this season
    const existingPreview = renderedPreviews.value.find(p => p.seasonKey === seasonKey)
    if (existingPreview && existingPreview.imageUrl) {
      // Use the cached preview
      lastPreview.value = existingPreview.imageUrl
    }
  } else {
    // Add new season and switch to it
    newSelection.add(seasonKey)
    selectedSeasons.value = newSelection
    
    const selected = Array.from(newSelection)
    const idx = selected.findIndex(k => k === seasonKey)
    currentSeasonIndex.value = idx >= 0 ? idx : 0
    await nextTick()
    await fetchImagesForCurrentSeason()
    restoreSettingsForCurrent()
    await fetchExistingPoster()
    syncRenderedPlaceholders()
    await doPreview()
  }
}

// Select all seasons
async function selectAllSeasons() {
  console.log('[SELECT ALL] Starting selectAllSeasons()')

  // Select all seasons
  const allKeys = seasons.value.map(s => s.key)
  selectedSeasons.value = new Set(allKeys)
  currentSeasonIndex.value = 0
  syncRenderedPlaceholders()

  console.log('[SELECT ALL] Selected', allKeys.length, 'seasons')

  // Fetch images and restore settings for the first season
  await nextTick()
  await fetchImagesForCurrentSeason()
  restoreSettingsForCurrent()
  await fetchExistingPoster()

  // Trigger preview (skip background render since we'll do it after fetching assets)
  console.log('[SELECT ALL] Calling doPreview()')
  try {
    await doPreview(true)
    console.log('[SELECT ALL] doPreview() completed')
  } catch (err) {
    console.error('[SELECT ALL] doPreview() error:', err)
  }

  // Fetch assets for all seasons first, then trigger background rendering
  console.log('[SELECT ALL] About to fetch assets for all seasons')
  await fetchAssetsForAllSeasons()

  console.log('[SELECT ALL] About to render all selected seasons')
  await renderAllSelectedSeasons()

  console.log('[SELECT ALL] Completed selectAllSeasons()')
}

// Deselect all seasons
async function deselectAllSeasons() {
  const seriesKey = seasons.value.find(s => s.isSeries)?.key || props.movie.key
  selectedSeasons.value = new Set([seriesKey])
  currentSeasonIndex.value = 0
  syncRenderedPlaceholders()

  // Fetch images and restore settings for the series
  await nextTick()
  await fetchImagesForCurrentSeason()
  restoreSettingsForCurrent()
  await fetchExistingPoster()

  // Trigger preview
  await doPreview()
}

// Keep the series entry poster updated when the Plex poster refreshes
watch(seriesPosterUrl, (url) => {
  const idx = seasons.value.findIndex(s => s.isSeries)
  if (idx === -1) return
  seasons.value = seasons.value.map((s, i) =>
    i === idx ? { ...s, thumb: url || s.thumb } : s
  )
})

// Cycle to next season in preview
function nextSeason() {
  const selectedCount = selectedSeasons.value.size
  if (selectedCount === 0) return
  currentSeasonIndex.value = (currentSeasonIndex.value + 1) % selectedCount
}

// Cycle to previous season in preview
function prevSeason() {
  const selectedCount = selectedSeasons.value.size
  if (selectedCount === 0) return
  currentSeasonIndex.value = currentSeasonIndex.value === 0 ? selectedCount - 1 : currentSeasonIndex.value - 1
}

// Load saved state on mount
onMounted(async () => {
  await loadGlobalFallbackSettings()
  loadEditorState()
  loadSeasonsCache()
  fetchSeasons()
})

// Watch for state changes and save
watch([
  options,
  selectedTemplate,
  selectedPreset,
  posterFilter,
  logoPreference,
  logoMode,
  logoHex,
  showTmdbPosters,
  showFanartPosters,
  showTmdbLogos,
  showFanartLogos,
  showTvdbLogos,
  showClearArt,
  textOverlayEnabled,
  customText,
  fontFamily,
  fontSize,
  fontWeight,
  textColor,
  textAlign,
  textTransform,
  letterSpacing,
  lineHeight,
  positionY,
  shadowEnabled,
  shadowBlur,
  shadowOffsetX,
  shadowOffsetY,
  shadowColor,
  shadowOpacity,
  strokeEnabled,
  strokeWidth,
  strokeColor
], () => {
  saveEditorState()
}, { deep: true })

watch(
  () => props.movie.key,
  async () => {
    await fetchSeasons()
    await fetchTmdbAssets()
    await fetchImagesForCurrentSeason()
    await fetchLabels()
    await fetchExistingPoster()
    ensurePosterSelected() // Ensure series poster is selected after existing poster loads
    await presetService.load()
    applyPresetOptions(selectedPreset.value)
  },
  { immediate: true }
)

watch(posterFilter, () => {
  applyPosterFilter()
})

watch(logoPreference, () => {
  applyLogoPreference()
})

type PresetApplyOptions = {
  // Force applying season overrides even if we already have cached season edits
  forceSeasonOverrides?: boolean
}

const applyPresetOptions = (id: string, opts: PresetApplyOptions = {}) => {
  const p = presets.value.find((x) => x.id === id)
  if (!p) return

    console.log('[PRESET APPLY] Found preset:', p.id, 'name:', (p as any).name)
    console.log('[PRESET APPLY] has season_options:', !!(p as any).season_options)
    if ((p as any).season_options) {
      console.log('[PRESET APPLY] season_options:', (p as any).season_options)
    }

  const isSeason = !!(currentSeason.value && !currentSeason.value.isSeries)
  const baseOptions = isSeason && (p as any).season_options ? (p as any).season_options : p.options
  if (!baseOptions) return

    console.log('[PRESET APPLY] isSeason:', isSeason, 'using:', baseOptions === (p as any).season_options ? 'season_options' : 'regular options')
    console.log('[PRESET APPLY] baseOptions.text_overlay_enabled:', baseOptions.text_overlay_enabled, 'custom_text:', baseOptions.custom_text)

  const o = baseOptions
  const currentKey = currentTargetKey.value
  const cached = settingsCache.value[currentKey]

  // Reset text overlay defaults before applying preset values
  textOverlayEnabled.value = false
  customText.value = ''
  fontFamily.value = 'Arial'
  fontSize.value = 120
  fontWeight.value = '700'
  textColor.value = '#ffffff'
  textAlign.value = 'center'
  textTransform.value = 'uppercase'
  letterSpacing.value = 2
  lineHeight.value = 120
  positionY.value = 75
  shadowEnabled.value = true
  shadowBlur.value = 10
  shadowOffsetX.value = 0
  shadowOffsetY.value = 4
  shadowColor.value = '#000000'
  shadowOpacity.value = 80
  strokeEnabled.value = false
  strokeWidth.value = 4
  strokeColor.value = '#000000'

  // Reset text overlay defaults before applying preset values
  textOverlayEnabled.value = false
  customText.value = ''
  fontFamily.value = 'Arial'
  fontSize.value = 120
  fontWeight.value = '700'
  textColor.value = '#ffffff'
  textAlign.value = 'center'
  textTransform.value = 'uppercase'
  letterSpacing.value = 2
  lineHeight.value = 120
  positionY.value = 75
  shadowEnabled.value = true
  shadowBlur.value = 10
  shadowOffsetX.value = 0
  shadowOffsetY.value = 4
  shadowColor.value = '#000000'
  shadowOpacity.value = 80
  strokeEnabled.value = false
  strokeWidth.value = 4
  strokeColor.value = '#000000'

  options.value.posterZoom = Math.round((Number(o.poster_zoom) || 1) * 100)
  options.value.posterShiftY = Math.round((Number(o.poster_shift_y) || 0) * 100)
  options.value.matteHeight = Math.round((Number(o.matte_height_ratio) || 0) * 100)
  options.value.fadeHeight = Math.round((Number(o.fade_height_ratio) || 0) * 100)
  options.value.vignette = Math.round((Number(o.vignette_strength) || 0) * 100)
  options.value.grain = Math.round((Number(o.grain_amount) || 0) * 100)
  options.value.logoScale = Math.round((Number(o.logo_scale) || 0.5) * 100)
  options.value.logoOffset = Math.round((Number(o.logo_offset) || 0.75) * 100)
  if (o.uniform_logo_max_w) options.value.uniformLogoMaxW = Number(o.uniform_logo_max_w)
  if (o.uniform_logo_max_h) options.value.uniformLogoMaxH = Number(o.uniform_logo_max_h)
  if (typeof o.uniform_logo_offset_x === 'number') options.value.uniformLogoOffsetX = Math.round(o.uniform_logo_offset_x * 100)
  if (typeof o.uniform_logo_offset_y === 'number') options.value.uniformLogoOffsetY = Math.round(o.uniform_logo_offset_y * 100)
  options.value.borderEnabled = !!o.border_enabled
  options.value.borderThickness = Number(o.border_px) || 0
  if (o.border_color) options.value.borderColor = String(o.border_color)
  if (o.overlay_file) options.value.overlayFile = String(o.overlay_file)
  if (typeof o.overlay_opacity === 'number') options.value.overlayOpacity = Math.round(o.overlay_opacity * 100)
  if (o.overlay_mode) options.value.overlayMode = String(o.overlay_mode)
  if (typeof o.poster_filter === 'string' && ['all', 'textless', 'text'].includes(o.poster_filter)) {
    posterFilter.value = o.poster_filter as 'all' | 'textless' | 'text'
  }
  if (typeof o.logo_preference === 'string' && ['first', 'white', 'color'].includes(o.logo_preference)) {
    logoPreference.value = o.logo_preference as 'first' | 'white' | 'color'
  }
  logoMode.value = normalizeLogoMode(o.logo_mode)
  if (typeof o.logo_hex === 'string') {
    logoHex.value = o.logo_hex
  }

  // Load text overlay settings (enable/disable + attributes)
  console.log('[PRESET APPLY] Loading text overlay from baseOptions - text_overlay_enabled:', o.text_overlay_enabled, 'custom_text:', o.custom_text)
  textOverlayEnabled.value = !!o.text_overlay_enabled
  if (typeof o.custom_text === 'string') customText.value = o.custom_text
  if (typeof o.font_family === 'string') fontFamily.value = o.font_family
  if (typeof o.font_size === 'number') fontSize.value = o.font_size
  if (typeof o.font_weight === 'string') fontWeight.value = o.font_weight
  if (typeof o.text_color === 'string') textColor.value = o.text_color
  if (typeof o.text_align === 'string') textAlign.value = o.text_align
  if (typeof o.text_transform === 'string') textTransform.value = o.text_transform
  if (typeof o.letter_spacing === 'number') letterSpacing.value = o.letter_spacing
  if (typeof o.line_height === 'number') lineHeight.value = Math.round(o.line_height * 100)
  if (typeof o.position_y === 'number') positionY.value = Math.round(o.position_y * 100)
  if (typeof o.shadow_enabled === 'boolean') shadowEnabled.value = o.shadow_enabled
  if (typeof o.shadow_blur === 'number') shadowBlur.value = o.shadow_blur
  if (typeof o.shadow_offset_x === 'number') shadowOffsetX.value = o.shadow_offset_x
  if (typeof o.shadow_offset_y === 'number') shadowOffsetY.value = o.shadow_offset_y
  if (typeof o.shadow_color === 'string') shadowColor.value = o.shadow_color
  if (typeof o.shadow_opacity === 'number') shadowOpacity.value = Math.round(o.shadow_opacity * 100)
  if (typeof o.stroke_enabled === 'boolean') strokeEnabled.value = o.stroke_enabled
  if (typeof o.stroke_width === 'number') strokeWidth.value = o.stroke_width
  if (typeof o.stroke_color === 'string') strokeColor.value = o.stroke_color

  // Season-specific overrides: apply AFTER loading from baseOptions
  // Only needed if season_options don't exist in the preset (legacy presets)
  // or if forceSeasonOverrides is explicitly requested
  if (isSeason && !((p as any).season_options) && (opts.forceSeasonOverrides || !cached)) {
    console.log('[PRESET APPLY] Applying hardcoded season overrides (no season_options in preset)')
    logoMode.value = 'none'
    textOverlayEnabled.value = true
    customText.value = '{season}'
    fontFamily.value = 'Arial'
    fontSize.value = 150
    shadowEnabled.value = false
    shadowBlur.value = 0
    letterSpacing.value = 1
    positionY.value = 85
  }
  
  console.log('[PRESET APPLY] Final values - textOverlayEnabled:', textOverlayEnabled.value, 'customText:', customText.value, 'logoMode:', logoMode.value)

  applyPosterFilter()
  applyLogoPreference()
}

watch(selectedPreset, (id) => {
  // When preset changes, check if we're on a season and force season overrides
  const isSeason = !!(currentSeason.value && !currentSeason.value.isSeries)
  applyPresetOptions(id, { forceSeasonOverrides: isSeason })
  // Clear modification tracking when preset changes
  if (isSeason && currentSeason.value) {
    delete userModifiedFields.value[currentSeason.value.key]
  }
})

// Track manual modifications to season preset fields
const markFieldModified = (fieldName: string) => {
  const isSeason = currentSeason.value && !currentSeason.value.isSeries
  if (isSeason && currentSeason.value) {
    const key = currentSeason.value.key
    if (!userModifiedFields.value[key]) {
      userModifiedFields.value[key] = new Set()
    }
    userModifiedFields.value[key].add(fieldName)
  }
}

watch(logoMode, () => markFieldModified('logoMode'))
watch(textOverlayEnabled, () => markFieldModified('textOverlayEnabled'))
watch(customText, () => markFieldModified('customText'))
watch(fontFamily, () => markFieldModified('fontFamily'))
watch(fontSize, () => markFieldModified('fontSize'))
watch(shadowEnabled, () => markFieldModified('shadowEnabled'))
watch(letterSpacing, () => markFieldModified('letterSpacing'))
watch(positionY, () => markFieldModified('positionY'))

// Track modifications to options fields
watch(() => options.value.posterZoom, () => markFieldModified('posterZoom'))
watch(() => options.value.posterShiftY, () => markFieldModified('posterShiftY'))
watch(() => options.value.matteHeight, () => markFieldModified('matteHeight'))
watch(() => options.value.fadeHeight, () => markFieldModified('fadeHeight'))
watch(() => options.value.vignette, () => markFieldModified('vignette'))
watch(() => options.value.grain, () => markFieldModified('grain'))
watch(() => options.value.logoScale, () => markFieldModified('logoScale'))
watch(() => options.value.logoOffset, () => markFieldModified('logoOffset'))

let previewTimer: ReturnType<typeof setTimeout> | null = null
let suppressAutoPreview = false // Flag to prevent auto-preview when switching to rendered preview
watch(
  [
    bgUrl,
    logoUrl,
    options,
    posterFilter,
    logoPreference,
    logoMode,
    logoHex,
    selectedTemplate,
    selectedPreset,
    textOverlayEnabled,
    customText,
    fontFamily,
    fontSize,
    fontWeight,
    textColor,
    textAlign,
    textTransform,
    letterSpacing,
    lineHeight,
    positionY,
    shadowEnabled,
    shadowBlur,
    shadowOffsetX,
    shadowOffsetY,
    shadowColor,
    shadowOpacity,
    strokeEnabled,
    strokeWidth,
    strokeColor,
    currentSeason
  ],
  () => {
    if (suppressAutoPreview) {
      console.log('[AUTO-PREVIEW] Suppressed (suppressAutoPreview=true)')
      return // Don't auto-preview when switching to rendered preview
    }
    console.log('[AUTO-PREVIEW] Debouncing preview (800ms)...')
    if (previewTimer) clearTimeout(previewTimer)
    previewTimer = setTimeout(() => {
      console.log('[AUTO-PREVIEW] Calling doPreview()')
      doPreview()
    }, 800)
  },
  { deep: true }
)

watch(currentSeason, () => {
  fetchImagesForCurrentSeason()
  syncRenderedPlaceholders()
})

watch(tmdbId, () => {
  fetchImagesForCurrentSeason()
})
</script>

<template>
  <div class="editor-shell">
    <div class="controls-sidebar">
      <div class="pane-header">
        <div>
          <p class="kicker">Editing</p>
          <h2>{{ movie.title }} <span v-if="movie.year">({{ movie.year }})</span></h2>
        </div>
      </div>

      <div class="controls-scroll">
        <!-- Template & Preset -->
        <div class="section">
          <label class="field-label">
            Template
            <select v-model="selectedTemplate" @change="presetService.load">
              <option v-if="presetLoading">Loading…</option>
              <option v-for="t in templates" :key="t" :value="t">{{ t }}</option>
            </select>
          </label>

          <div class="preset-row">
            <label class="field-label preset-select">
              Preset
              <select v-model="selectedPreset">
                <option v-if="presetLoading">Loading…</option>
                <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name || p.id }}</option>
              </select>
            </label>
            <button class="reload-preset-btn" @click="reloadPreset" title="Reload preset values">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
            <button class="save-preset-btn" @click="saveCurrentPreset" title="Save current settings to preset">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                <polyline points="17 21 17 13 7 13 7 21"/>
                <polyline points="7 3 7 8 15 8"/>
              </svg>
            </button>
          </div>
          <div class="preset-row new-preset-row">
            <input v-model="newPresetId" type="text" placeholder="New preset id" class="new-preset-input" />
            <button class="save-preset-btn wide" @click="saveAsNewPreset" title="Save as a new preset">Save As</button>
          </div>
        </div>
        
        <hr class="divider" />
        
        <!-- Poster & Logo Selection -->
        <div class="section">
          <label class="field-label">
            Poster Filter
            <select v-model="posterFilter">
              <option value="all">All Posters</option>
              <option value="textless">Textless Only</option>
              <option value="text">With Text</option>
            </select>
          </label>
          

          <div class="label-title">Posters (TMDb: {{ posterCounts.tmdb }} | Fanart: {{ posterCounts.fanart }} | TVDB: {{ posterCounts.tvdb }})</div>
          <div class="inline-controls">
            <label class="inline-field" v-if="posterFilter !== 'textless'">
              <span>Language</span>
              <select v-model="posterLanguageFilter">
                <option value="all">All</option>
                <option value="en">English</option>
              </select>
            </label>
            <label class="inline-field checkbox">
              <input type="checkbox" v-model="showTmdbPosters" />
              <span>TMDb</span>
            </label>
            <label class="inline-field checkbox">
              <input type="checkbox" v-model="showFanartPosters" />
              <span>Fanart</span>
            </label>
            <label class="inline-field checkbox">
              <input type="checkbox" v-model="showTvdbPosters" />
              <span>TVDB</span>
            </label>
          </div>
          <div class="thumb-strip">
            <div
              v-for="p in filteredPosters"
              :key="p.url"
              class="thumb poster-thumb"
              :class="{ active: selectedPoster === p.url }"
              @click="selectedPoster = p.url"
            >
              <img :src="p.thumb || p.url" alt="" />
              <div class="source-badge">{{ (p.source || 'tmdb').toUpperCase() }}</div>
            </div>
          </div>

          <label v-if="!isLogoNone" class="field-label">
            Logo Preference
            <select v-model="logoPreference">
              <option value="first">First Available</option>
              <option value="white">White Logos</option>
              <option value="color">Colored Logos</option>
            </select>
          </label>

          <div v-if="!isLogoNone" class="label-title">Logos (TMDb: {{ logoCounts.tmdb }} | Fanart: {{ logoCounts.fanart }} | TVDB: {{ logoCounts.tvdb }})</div>
          <div v-if="!isLogoNone" class="inline-controls">
            <label class="inline-field">
              <span>Language</span>
              <select v-model="logoLanguageFilter">
                <option value="all">All</option>
                <option value="en">English</option>
              </select>
            </label>
            <label class="inline-field">
              <span>Include clearart</span>
              <input type="checkbox" v-model="showClearArt" />
            </label>
            <label class="inline-field checkbox">
              <input type="checkbox" v-model="showTmdbLogos" />
              <span>TMDb</span>
            </label>
            <label class="inline-field checkbox">
              <input type="checkbox" v-model="showFanartLogos" />
              <span>Fanart</span>
            </label>
            <label class="inline-field checkbox">
              <input type="checkbox" v-model="showTvdbLogos" />
              <span>TVDB</span>
            </label>
          </div>
          <div v-if="!isLogoNone" class="thumb-strip logo-strip">
            <div
              v-for="l in filteredLogos"
              :key="l.url"
              class="thumb logo-thumb"
              :class="{ active: selectedLogo === l.url }"
              @click="selectedLogo = l.url"
            >
              <img :src="l.thumb || l.url" alt="" />
              <div class="source-badge">{{ (l.source || 'tmdb').toUpperCase() }}</div>
              <div v-if="l.type && l.type !== 'logo'" class="type-badge">{{ l.type }}</div>
            </div>
            <button class="no-logo-btn" :class="{ active: isLogoNone }" @click="logoMode = 'none'">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
              </svg>
              <span>No Logo</span>
            </button>
          </div>

          <label class="field-label">
            Logo Mode
            <select v-model="logoMode">
              <option value="original">Keep Original</option>
              <option value="match">Color Match Poster</option>
              <option value="hex">Use Custom Hex</option>
              <option value="none">No Logo</option>
            </select>
          </label>

          <label v-if="logoMode === 'hex'" class="field-label">
            Logo Color
            <input v-model="logoHex" type="color" />
          </label>
        </div>

        <hr class="divider" />

        <!-- Poster Settings -->
        <div class="section sliders">
          <div class="section-title">Poster Settings</div>

          <div class="slider">
            <label>Poster Zoom %</label>
            <div class="slider-row">
              <input v-model.number="options.posterZoom" type="range" min="80" max="140" />
              <input v-model.number="options.posterZoom" type="number" min="80" max="140" class="slider-num" />
            </div>
          </div>

          <div class="slider">
            <label>Poster Shift Y %</label>
            <div class="slider-row">
              <input v-model.number="options.posterShiftY" type="range" min="-50" max="50" />
              <input v-model.number="options.posterShiftY" type="number" min="-50" max="50" class="slider-num" />
            </div>
          </div>
        </div>

        <hr class="divider" />

        <!-- Effects -->
        <div class="section sliders">
          <div class="section-title">Effects</div>

          <div class="slider">
            <label>Matte Height %</label>
            <div class="slider-row">
              <input v-model.number="options.matteHeight" type="range" min="0" max="50" />
              <input v-model.number="options.matteHeight" type="number" min="0" max="50" class="slider-num" />
            </div>
          </div>

          <div class="slider">
            <label>Fade Height %</label>
            <div class="slider-row">
              <input v-model.number="options.fadeHeight" type="range" min="0" max="40" />
              <input v-model.number="options.fadeHeight" type="number" min="0" max="40" class="slider-num" />
            </div>
          </div>

          <div class="slider">
            <label>Vignette</label>
            <div class="slider-row">
              <input v-model.number="options.vignette" type="range" min="0" max="100" />
              <input v-model.number="options.vignette" type="number" min="0" max="100" class="slider-num" />
            </div>
          </div>

          <div class="slider">
            <label>Grain</label>
            <div class="slider-row">
              <input v-model.number="options.grain" type="range" min="0" max="60" />
              <input v-model.number="options.grain" type="number" min="0" max="60" class="slider-num" />
            </div>
          </div>
        </div>

        <hr class="divider" />

        <!-- Logo Settings -->
        <div v-if="!isUniformLogo" class="section sliders">
          <div class="section-title">Logo Settings</div>

          <div class="slider">
            <label>Logo Scale %</label>
            <div class="slider-row">
              <input v-model.number="options.logoScale" type="range" min="20" max="120" />
              <input v-model.number="options.logoScale" type="number" min="20" max="120" class="slider-num" />
            </div>
          </div>

          <div class="slider">
            <label>Logo Position %</label>
            <div class="slider-row">
              <input v-model.number="options.logoOffset" type="range" min="0" max="100" />
              <input v-model.number="options.logoOffset" type="number" min="0" max="100" class="slider-num" />
            </div>
          </div>
        </div>

        <!-- Uniform Logo Controls -->
        <div v-if="isUniformLogo" class="section">
          <div v-if="isUniformLogo" class="uniform-section">
            <div class="uniform-title">Uniform Logo Settings</div>

            <div class="slider">
              <label>Max Width (px)</label>
              <div class="slider-row">
                <input v-model.number="options.uniformLogoMaxW" type="range" min="50" max="1800" />
                <input v-model.number="options.uniformLogoMaxW" type="number" min="50" max="1800" class="slider-num" />
              </div>
            </div>

            <div class="slider">
              <label>Max Height (px)</label>
              <div class="slider-row">
                <input v-model.number="options.uniformLogoMaxH" type="range" min="50" max="600" />
                <input v-model.number="options.uniformLogoMaxH" type="number" min="50" max="600" class="slider-num" />
              </div>
            </div>

            <div class="slider">
              <label>Logo Box X %</label>
              <div class="slider-row">
                <input v-model.number="options.uniformLogoOffsetX" type="range" min="0" max="100" />
                <input v-model.number="options.uniformLogoOffsetX" type="number" min="0" max="100" class="slider-num" />
              </div>
            </div>

            <div class="slider">
              <label>Logo Box Y %</label>
              <div class="slider-row">
                <input v-model.number="options.uniformLogoOffsetY" type="range" min="0" max="100" />
                <input v-model.number="options.uniformLogoOffsetY" type="number" min="0" max="100" class="slider-num" />
              </div>
            </div>

            <label class="checkbox-label">
              <input v-model="showBoundingBox" type="checkbox" />
              Show Logo Bounding Box (debug)
            </label>
          </div>
        </div>

        <hr class="divider" />

        <!-- Text Overlay -->
        <TextOverlayPanel
          v-model:enabled="textOverlayEnabled"
          v-model:customText="customText"
          v-model:fontFamily="fontFamily"
          v-model:fontSize="fontSize"
          v-model:fontWeight="fontWeight"
          v-model:textColor="textColor"
          v-model:textAlign="textAlign"
          v-model:textTransform="textTransform"
          v-model:letterSpacing="letterSpacing"
          v-model:lineHeight="lineHeight"
          v-model:positionY="positionY"
          v-model:shadowEnabled="shadowEnabled"
          v-model:shadowBlur="shadowBlur"
          v-model:shadowOffsetX="shadowOffsetX"
          v-model:shadowOffsetY="shadowOffsetY"
          v-model:shadowColor="shadowColor"
          v-model:shadowOpacity="shadowOpacity"
          v-model:strokeEnabled="strokeEnabled"
          v-model:strokeWidth="strokeWidth"
          v-model:strokeColor="strokeColor"
          :availableFonts="availableFonts"
        />

        <hr class="divider" />

        <!-- Border & Overlay -->
        <div class="section sliders">
          <div class="section-title">Border & Overlay</div>

          <div class="slider">
            <label class="checkbox-label">
              <input v-model="options.borderEnabled" type="checkbox" />
              Border Enabled
            </label>
          </div>

          <div v-if="options.borderEnabled" class="slider">
            <label>Border Thickness (px)</label>
            <div class="slider-row">
              <input v-model.number="options.borderThickness" type="range" min="0" max="30" />
              <input v-model.number="options.borderThickness" type="number" min="0" max="30" class="slider-num" />
            </div>
          </div>

          <div v-if="options.borderEnabled" class="slider">
            <label>Border Color</label>
            <input v-model="options.borderColor" type="color" />
          </div>

          <div class="slider">
            <label>Overlay File</label>
            <input v-model="options.overlayFile" type="text" placeholder="e.g. grain_overlay.png" />
          </div>

          <div class="slider">
            <label>Overlay Opacity %</label>
            <div class="slider-row">
              <input v-model.number="options.overlayOpacity" type="range" min="0" max="100" />
              <input v-model.number="options.overlayOpacity" type="number" min="0" max="100" class="slider-num" />
            </div>
          </div>

          <div class="slider">
            <label>Overlay Mode</label>
            <select v-model="options.overlayMode">
              <option value="screen">Screen</option>
              <option value="multiply">Multiply</option>
              <option value="alpha">Alpha Composite</option>
            </select>
          </div>
        </div>

        <hr class="divider" />

        <!-- Labels -->
        <div class="section">
          <div class="label-title">Labels to Remove</div>
          <div class="label-chips">
            <label v-for="l in labels" :key="l" class="chip">
              <input type="checkbox" :checked="selectedLabels.has(l)" @change="toggleLabel(l)" />
              <span>{{ l }}</span>
            </label>
            <p v-if="!labels.length" class="muted-text">No labels found</p>
          </div>
        </div>

        <hr class="divider" />

        <!-- Actions -->
        <div class="section actions">
          <button class="btn-primary" :disabled="loading" @click="doPreview">Preview</button>
          <span v-if="error" class="error-text">{{ error }}</span>
        </div>
      </div>
    </div>

    <!-- Season Selection Panel for TV Shows -->
    <div class="season-panel">
      <div class="season-header">
        <div class="season-title">Seasons</div>
        <div class="season-controls">
          <button @click="selectAllSeasons" class="season-ctrl-btn" title="Select All">All</button>
          <button @click="deselectAllSeasons" class="season-ctrl-btn" title="Deselect All">None</button>
        </div>
      </div>

      <!-- Current Season Indicator -->
      <div v-if="currentSeason" class="current-season-banner">
        <div class="banner-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z" />
            <circle cx="12" cy="13" r="3" />
          </svg>
        </div>
        <div class="banner-text">
          <div class="banner-label">Editing Posters For</div>
          <div class="banner-title">{{ currentSeason.title }}</div>
        </div>
        <div class="banner-nav">
          <button @click="prevSeason" class="nav-btn" title="Previous Season">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <button @click="nextSeason" class="nav-btn" title="Next Season">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>
      </div>

      <div class="season-list">
        <div
          v-for="season in seasons"
          :key="season.key"
          class="season-item"
          :class="{
            selected: selectedSeasons.has(season.key),
            active: currentSeason && currentSeason.key === season.key
          }"
          @click="toggleSeasonSelection(season.key)"
        >
          <div class="season-thumb-wrap">
            <img
              v-if="season.thumb"
              :src="season.thumb"
              :alt="season.title"
              class="season-thumb"
            />
            <div v-else class="season-thumb-placeholder">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
          </div>
          <div class="season-info">
            <div class="season-name-row">
              <div class="season-title-text">
                <span v-if="season.isSeries" class="season-badge">Series</span>
                <span v-else class="season-number">Season {{ season.index }}</span>
              </div>
              <div class="season-checkbox">
                <input
                  type="checkbox"
                  :checked="selectedSeasons.has(season.key)"
                  @click.stop="toggleSelectionOnly(season.key)"
                />
              </div>
            </div>
          </div>
        </div>
        <div v-if="seasons.length === 0" class="empty-seasons">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          </svg>
          <p>No seasons found</p>
        </div>
      </div>
    </div>

    <div class="preview-pane">
      <div class="preview-inner">
        <div class="preview-existing">
          <div class="preview-label">
            Current Plex Poster
            <button class="refresh-btn" title="Refresh poster" @click="fetchExistingPoster(true)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
          </div>
          <img v-if="existingPoster" :key="posterRefreshKey" :src="existingPoster" alt="Existing poster" class="existing-img" />
          <div v-else class="empty-preview">No poster</div>
        </div>

        <div class="preview-content-wrapper">
          <div class="preview-main">
          <div class="preview-label">
            <div class="preview-title-row">
              <span>Preview</span>
            </div>
            <div v-if="currentSeason" class="current-season-label">{{ currentSeason.title }}</div>
            <span v-if="loading" class="status-badge">Rendering...</span>
            <span v-else-if="lastPreview" class="status-badge success">Rendered</span>
            <div class="preview-actions float-right">
              <button title="Save to Disk" class="btn-save btn-inline" :disabled="loading" @click="doSave">💾 <span class="btn-label">Save to Disk</span></button>
              <button title="Send to Plex" class="btn-plex btn-inline" :disabled="loading" @click="doSend">📺 <span class="btn-label">Send to Plex</span></button>
            </div>
          </div>
          <div class="preview-container">
            <img v-if="lastPreview" ref="previewImgRef" :src="lastPreview" alt="Preview" class="preview-img" />
            <div v-else-if="selectedPoster" class="placeholder-state">
              <img :src="selectedPoster" alt="Selected poster" class="placeholder-img" />
              <div class="placeholder-overlay">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                  <circle cx="12" cy="13" r="4" />
                </svg>
                <p>Adjust settings to render</p>
              </div>
            </div>
            <div v-else class="empty-preview large">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
              <p>Select a poster to begin</p>
            </div>

            <!-- Loading Overlay -->
            <div v-if="loading" class="loading-overlay">
              <div class="spinner"></div>
              <p>Rendering...</p>
            </div>

            <!-- Bounding Box for Uniform Logo -->
            <div v-if="isUniformLogo && showBoundingBox && lastPreview" class="bounding-box" :style="boundingBoxStyle"></div>
          </div>

          </div>

          <!-- Rendered previews below main preview -->
          <div v-if="renderedPreviews.length" class="rendered-previews-section">
          <div class="carousel-label">
            Rendered Posters ({{ renderedPreviews.filter(p => p.imageUrl).length }})
            <span class="carousel-hint">Click to load • Scroll to cycle</span>
          </div>
          <div class="carousel-scroll">
            <div
              v-for="(preview, index) in sortedRenderedPreviews"
              :key="preview.seasonKey"
              class="carousel-item"
              :class="{ active: index === activePreviewIndex }"
              @click="switchToRenderedPreview(index)"
              :title="preview.seasonTitle"
            >
              <template v-if="preview.imageUrl">
                <img :src="preview.imageUrl" :alt="preview.seasonTitle" class="carousel-thumb" />
              </template>
              <template v-else>
                <div class="carousel-thumb placeholder">
                  <span>No render yet</span>
                </div>
              </template>
              <div class="carousel-item-label">{{ preview.seasonTitle }}</div>
            </div>
          </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-shell {
  display: grid;
  grid-template-columns: 480px 220px 1fr;
  gap: 0;
  height: calc(100vh - 60px);
  background: var(--surface);
  overflow: hidden;
}

.controls-sidebar {
  background: rgba(17, 20, 30, 0.95);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.pane-header {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border);
}

.kicker {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--muted);
  margin-bottom: 4px;
}

.pane-header h2 {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.2px;
  color: #eef2ff;
}

.pane-header h2 span {
  color: var(--muted);
  font-weight: 500;
}

.controls-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 0 18px 20px;
}

.section {
  margin-top: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #e0e9ff;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.divider {
  border: 0;
  border-top: 1px solid var(--border);
  margin: 18px 0;
}

.field-label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  font-weight: 500;
  color: #dce6ff;
}

.field-label select,
.field-label input[type='text'],
.field-label input[type='color'] {
  width: 100%;
  padding: 8px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 13px;
}

.field-label input[type='color'] {
  height: 38px;
  cursor: pointer;
}

.preset-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.new-preset-row {
  margin-top: 8px;
}
.new-preset-input {
  flex: 1;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
}
.save-preset-btn.wide {
  width: 120px;
}

.save-preset-btn {
  flex: 0 0 auto;
  min-width: 42px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(120deg, #3dd6b7, #5b8dee);
  color: #fff;
  font-weight: 600;
  padding: 10px 14px;
  box-shadow: 0 6px 18px rgba(61, 214, 183, 0.18);
  cursor: pointer;
  transition: all 0.2s ease;
}

.save-preset-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 22px rgba(61, 214, 183, 0.24);
}

.save-preset-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.preset-select {
  flex: 1;
}

.reload-preset-btn {
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: #dce6ff;
  cursor: pointer;
  transition: all 0.2s;
}

.reload-preset-btn:hover {
  background: rgba(61, 214, 183, 0.1);
  border-color: rgba(61, 214, 183, 0.3);
  color: var(--accent);
}

.label-title {
  font-size: 13px;
  font-weight: 600;
  color: #dce6ff;
  margin-bottom: 8px;
}

.thumb-strip {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding: 6px 0;
  margin-bottom: 12px;
}

.thumb {
  flex: 0 0 auto;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
  background: rgba(255, 255, 255, 0.02);
  position: relative;
}

.thumb:hover {
  border-color: rgba(61, 214, 183, 0.3);
}

.thumb.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}

.source-badge {
  position: absolute;
  bottom: 4px;
  left: 4px;
  padding: 2px 5px;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(4px);
  color: #3dd6b7;
  font-size: 9px;
  font-weight: 600;
  border-radius: 4px;
  border: 1px solid rgba(61, 214, 183, 0.3);
  letter-spacing: 0.3px;
}

.type-badge {
  position: absolute;
  top: 4px;
  left: 4px;
  padding: 2px 6px;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  font-size: 9px;
  font-weight: 600;
  border-radius: 4px;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}

.poster-thumb {
  width: 80px;
  height: 120px;
}

.poster-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.logo-strip {
  align-items: center;
}

.logo-thumb {
  min-width: 110px;
  max-width: 160px;
  height: 70px;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-thumb img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.no-logo-btn {
  flex: 0 0 auto;
  min-width: 110px;
  height: 70px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  border: 2px solid var(--border);
  border-radius: 8px;
  padding: 6px;
  background: rgba(255, 255, 255, 0.02);
  color: #dce6ff;
  cursor: pointer;
  transition: all 0.2s;
}

.no-logo-btn svg {
  opacity: 0.6;
}

.no-logo-btn span {
  font-size: 11px;
  font-weight: 500;
}

.no-logo-btn:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(61, 214, 183, 0.3);
}

.no-logo-btn.active {
  border-color: var(--accent);
  background: rgba(61, 214, 183, 0.08);
}

.inline-controls {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 6px 0 10px;
}
.inline-field {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
  color: #dce6ff;
}
.inline-field select {
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #dce6ff;
}
.inline-field.checkbox {
  gap: 4px;
}
.inline-field.checkbox input[type='checkbox'] {
  accent-color: var(--accent, #3dd6b7);
}

.sliders .slider {
  margin-bottom: 14px;
}

.slider label {
  font-size: 12px;
  font-weight: 500;
  color: #c4cceb;
  margin-bottom: 6px;
  display: block;
}

.slider-row {
  display: grid;
  grid-template-columns: 1fr 70px;
  gap: 8px;
  align-items: center;
}

.slider-row input[type='range'] {
  width: 100%;
}

.slider-num {
  width: 100%;
  padding: 6px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 12px;
  text-align: center;
}

.slider input[type='text'],
.slider select {
  width: 100%;
  padding: 8px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 13px;
}

.uniform-section {
  background: rgba(61, 214, 183, 0.05);
  border: 1px solid rgba(61, 214, 183, 0.2);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 14px;
}

.uniform-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 12px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #dce6ff;
  cursor: pointer;
}

.checkbox-label input[type='checkbox'] {
  cursor: pointer;
}

.label-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
  font-size: 12px;
  cursor: pointer;
}

.muted-text {
  font-size: 12px;
  color: var(--muted);
}

.batch-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.batch-form textarea {
  width: 100%;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  padding: 10px;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.float-right {
  margin-left: auto;
}

.btn-primary,
.btn-secondary {
  width: 100%;
  padding: 10px;
  border-radius: 8px;
  border: none;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: linear-gradient(120deg, #3dd6b7, #5b8dee);
  color: #fff;
  box-shadow: 0 4px 12px rgba(61, 214, 183, 0.3);
}

.btn-primary:hover:not(:disabled) {
  box-shadow: 0 6px 16px rgba(61, 214, 183, 0.4);
  transform: translateY(-1px);
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.06);
  color: #dce6ff;
  border: 1px solid var(--border);
}

.btn-secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.15);
}

/* Override to ensure .btn-plex color wins when combined with btn-secondary */
.btn-secondary.btn-plex {
  background: linear-gradient(120deg, #ff8a65, #ff7043);
  color: #fff;
  border: none;
  box-shadow: 0 6px 18px rgba(255, 112, 67, 0.12);
}
.btn-secondary.btn-plex:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 22px rgba(255, 112, 67, 0.18);
}

/* Inline buttons for preview area */
.preview-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 320px; /* slightly narrower so buttons are a bit smaller */
  justify-content: flex-end;
}
.btn-inline {
  width: calc(50% - 6px); /* two buttons share the preview-actions width */
  min-width: 130px;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.btn-label {
  display: inline-block;
  font-weight: 600;
  color: inherit;
}

/* Ensure btn-save is visible if any local rules apply */
.btn-save {
  background: linear-gradient(120deg, #7a6bff, #9b8bff);
  color: #fff;
  border: none;
  box-shadow: 0 6px 18px rgba(122, 107, 255, 0.12);
}
.btn-save:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 22px rgba(122, 107, 255, 0.18);
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-text {
  font-size: 12px;
  color: #ff6b6b;
}

/* Season Selection Panel */
.season-panel {
  background: rgba(15, 17, 25, 0.9);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.season-header {
  padding: 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.season-title {
  font-size: 13px;
  font-weight: 600;
  color: #dce6ff;
}

.season-controls {
  display: flex;
  gap: 4px;
}

.season-ctrl-btn {
  padding: 4px 8px;
  font-size: 11px;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 4px;
  color: #a5b4fc;
  cursor: pointer;
  transition: all 0.15s ease;
}

.season-ctrl-btn:hover {
  background: rgba(99, 102, 241, 0.2);
  border-color: rgba(99, 102, 241, 0.5);
}

/* Current Season Banner */
.current-season-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: linear-gradient(135deg, rgba(61, 214, 183, 0.12), rgba(91, 141, 238, 0.12));
  border-bottom: 1px solid rgba(61, 214, 183, 0.25);
  border-top: 1px solid rgba(61, 214, 183, 0.15);
}

.banner-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(61, 214, 183, 0.15);
  border: 1px solid rgba(61, 214, 183, 0.3);
  border-radius: 6px;
  color: var(--accent);
}

.banner-text {
  flex: 1;
  min-width: 0;
}

.banner-label {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #a4d9cf;
  margin-bottom: 2px;
}

.banner-title {
  font-size: 12px;
  font-weight: 600;
  color: #e6edff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.banner-nav {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.nav-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(61, 214, 183, 0.1);
  border: 1px solid rgba(61, 214, 183, 0.3);
  border-radius: 4px;
  color: var(--accent);
  cursor: pointer;
  transition: all 0.15s ease;
}

.nav-btn:hover {
  background: rgba(61, 214, 183, 0.2);
  border-color: rgba(61, 214, 183, 0.5);
  transform: scale(1.05);
}

.season-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}

.season-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  margin-bottom: 4px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.season-item:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(99, 102, 241, 0.3);
}

.season-item.selected {
  background: rgba(99, 102, 241, 0.15);
  border-color: rgba(99, 102, 241, 0.5);
}

.season-item.active {
  background: rgba(61, 214, 183, 0.2);
  border-color: rgba(61, 214, 183, 0.6);
  box-shadow: 0 0 0 1px rgba(61, 214, 183, 0.3);
}

.season-item.active:hover {
  background: rgba(61, 214, 183, 0.25);
}

.season-item.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.06);
}

.season-thumb-wrap {
  width: 40px;
  height: 60px;
  flex-shrink: 0;
  border-radius: 4px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  position: relative;
}

.season-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.season-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.05);
  color: var(--muted);
}

.season-label {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  font-weight: 600;
  color: #e6edff;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.series-tag {
  margin-left: 6px;
  font-size: 10px;
  color: #9ad8ff;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.season-badge {
  padding: 2px 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.3px;
  border-radius: 6px;
  background: rgba(61, 214, 183, 0.18);
  color: #a4f5de;
  border: 1px solid rgba(61, 214, 183, 0.35);
}

.season-checkbox {
  flex-shrink: 0;
}

.season-checkbox input[type='checkbox'] {
  cursor: pointer;
  width: 16px;
  height: 16px;
}

.season-info {
  flex: 1;
  min-width: 0;
}

.season-name-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.season-title-text {
  flex: 1;
  min-width: 0;
}

.season-number {
  font-size: 12px;
  font-weight: 600;
  color: #e6edff;
}

.season-note {
  margin: 6px 8px 8px;
  font-size: 12px;
  color: var(--muted);
}

.empty-seasons {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--muted);
  text-align: center;
}

.empty-seasons svg {
  margin-bottom: 12px;
  opacity: 0.5;
}

.empty-seasons p {
  font-size: 12px;
}

/* Season Navigation in Preview */
.preview-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.season-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 6px;
  padding: 4px 8px;
}

.season-nav-btn {
  background: transparent;
  border: none;
  color: #a5b4fc;
  cursor: pointer;
  padding: 2px 6px;
  font-size: 12px;
  transition: color 0.15s ease;
}

.season-nav-btn:hover {
  color: #c7d2fe;
}

.season-counter {
  font-size: 11px;
  color: #dce6ff;
  font-weight: 500;
  min-width: 40px;
  text-align: center;
}

.current-season-label {
  font-size: 11px;
  color: #a5b4fc;
  margin-top: 4px;
  font-weight: 500;
}

.preview-pane {
  background: rgba(10, 12, 18, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  overflow: auto;
  height: 100%;
}

.preview-inner {
  display: flex;
  flex-direction: row;
  gap: 12px;
  align-items: flex-start;
  max-width: 100%;
  width: 100%;
}

.preview-existing {
  text-align: center;
  flex-shrink: 0;
}

.preview-content-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  min-width: 0;
}

.preview-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.refresh-btn {
  padding: 4px;
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.refresh-btn:hover {
  color: #3dd6b7;
  background: rgba(61, 214, 183, 0.1);
}

.status-badge {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--muted);
  font-weight: 500;
}

.status-badge.success {
  background: rgba(61, 214, 183, 0.15);
  color: #3dd6b7;
}

.existing-img {
  width: 160px;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
}

.preview-main {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.preview-container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 12px;
  border: 1px solid var(--border);
  width: min(100%, 500px);
  max-height: 70vh;
  aspect-ratio: 2 / 3;
}

.preview-img {
  width: 100%;
  height: 100%;
  max-height: 70vh;
  max-width: 100%;
  object-fit: contain;
  border-radius: 10px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
}

.placeholder-state {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.placeholder-img {
  opacity: 0.2;
  filter: blur(3px);
  max-height: 85vh;
  max-width: 100%;
  border-radius: 10px;
}

.placeholder-overlay {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #dce6ff;
}

.placeholder-overlay svg {
  opacity: 0.7;
}

.placeholder-overlay p {
  font-size: 15px;
  font-weight: 500;
}

.empty-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  color: var(--muted);
}

.empty-preview.large {
  min-height: 400px;
}

.empty-preview svg {
  opacity: 0.3;
}

.empty-preview p {
  font-size: 14px;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(4px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  border-radius: 10px;
  z-index: 10;
}

.loading-overlay p {
  font-size: 16px;
  font-weight: 500;
  color: #dce6ff;
}

.spinner {
  width: 48px;
  height: 48px;
  border: 4px solid rgba(255, 255, 255, 0.1);
  border-top-color: #4a9eff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.bounding-box {
  position: absolute;
  border: 2px dashed rgba(255, 255, 0, 0.8);
  pointer-events: none;
}

.rendered-previews-section {
  width: 100%;
  max-width: 800px;
}

/* Rendered Preview Carousel */
.preview-carousel {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.carousel-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.carousel-hint {
  font-size: 10px;
  font-weight: 500;
  color: #8ea0c8;
  text-transform: none;
}

.carousel-scroll {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(99, 102, 241, 0.3) rgba(255, 255, 255, 0.05);
}

.carousel-scroll::-webkit-scrollbar {
  height: 6px;
}

.carousel-scroll::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 3px;
}

.carousel-scroll::-webkit-scrollbar-thumb {
  background: rgba(99, 102, 241, 0.3);
  border-radius: 3px;
}

.carousel-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(99, 102, 241, 0.5);
}

.carousel-item {
  flex-shrink: 0;
  width: 100px;
  cursor: pointer;
  border-radius: 6px;
  overflow: hidden;
  border: 2px solid transparent;
  transition: all 0.2s ease;
  background: rgba(255, 255, 255, 0.02);
}

.carousel-item:hover {
  border-color: rgba(99, 102, 241, 0.4);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.carousel-item.active {
  border-color: rgba(99, 102, 241, 0.8);
  background: rgba(99, 102, 241, 0.1);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
}

.carousel-thumb {
  width: 100%;
  height: 150px;
  object-fit: contain;
  display: block;
  background: rgba(0, 0, 0, 0.3);
}
.carousel-thumb.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--muted);
  background: rgba(255, 255, 255, 0.05);
  border: 1px dashed rgba(255, 255, 255, 0.1);
}

.carousel-item-label {
  padding: 6px 8px;
  font-size: 10px;
  color: #dce6ff;
  background: rgba(0, 0, 0, 0.5);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.carousel-item.active .carousel-item-label {
  background: rgba(99, 102, 241, 0.3);
  color: #c7d2fe;
  font-weight: 600;
}
</style>
