<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
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
const posters = ref<{ url: string; thumb?: string; has_text?: boolean }[]>([])
const logos = ref<{ url: string; thumb?: string; color?: string }[]>([])
const labels = ref<string[]>([])
const selectedLabels = ref<Set<string>>(new Set())
const existingPoster = ref<string | null>(null)

const posterFilter = ref<'all' | 'textless' | 'text'>('all')
const logoPreference = ref<'first' | 'white' | 'color'>('first')
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
const POSTER_CACHE_KEY = 'simposter-poster-cache'

const showBoundingBox = ref(false)
const previewImgRef = ref<HTMLImageElement | null>(null)
const posterRefreshKey = ref(0)

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

const { success, error: notifyError } = useNotification()

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
      logoPreference: logoPreference.value,
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

const loadEditorState = () => {
  try {
    const saved = localStorage.getItem(EDITOR_STATE_KEY)
    if (!saved) return
    const state = JSON.parse(saved)
    if (state.options) Object.assign(options.value, state.options)
    if (state.selectedTemplate) selectedTemplate.value = state.selectedTemplate
    if (state.selectedPreset) selectedPreset.value = state.selectedPreset
    if (state.posterFilter) posterFilter.value = state.posterFilter
    if (state.logoPreference) logoPreference.value = state.logoPreference
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
  const imgWidth = img.clientWidth
  const imgHeight = img.clientHeight

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

  // Position (centered on offset point)
  const left = (imgWidth * offsetX) - (boxWidth / 2)
  const top = (imgHeight * offsetY) - (boxHeight / 2)

  return {
    width: `${boxWidth}px`,
    height: `${boxHeight}px`,
    left: `${left}px`,
    top: `${top}px`
  }
})

const filteredPosters = computed(() => {
  if (posterFilter.value === 'textless') return posters.value.filter((p) => p.has_text === false)
  if (posterFilter.value === 'text') return posters.value.filter((p) => p.has_text === true)
  return posters.value
})

const filteredLogos = computed(() => logos.value)

const optionsPayload = computed(() => ({
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
}))

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
  if (logoPreference.value === 'first') {
    const firstLogo = logos.value[0]
    if (firstLogo) selectedLogo.value = firstLogo.url
    return
  }
  const target = logoPreference.value === 'white' ? 'white' : 'color'
  const match = logos.value.find((l) => (l.thumb || l.url).toLowerCase().includes(target))
  const fallback = logos.value[0]
  if (match) selectedLogo.value = match.url
  else if (fallback) selectedLogo.value = fallback.url
}

const applyPosterFilter = () => {
  if (!posters.value.length) return
  if (posterFilter.value === 'textless') {
    const textless = posters.value.find((p) => p.has_text === false)
    if (textless) selectedPoster.value = textless.url
    else if (!selectedPoster.value) selectedPoster.value = posters.value[0]?.url || null
  } else if (posterFilter.value === 'text') {
    const withText = posters.value.find((p) => p.has_text === true)
    if (withText) selectedPoster.value = withText.url
    else if (!selectedPoster.value) selectedPoster.value = posters.value[0]?.url || null
  } else if (!selectedPoster.value && posters.value.length) {
    const firstPoster = posters.value[0]
    if (firstPoster) selectedPoster.value = firstPoster.url
  }
}

const fetchTmdbAssets = async () => {
  posters.value = []
  logos.value = []
  selectedPoster.value = null
  selectedLogo.value = null
  try {
    const tmdbRes = await fetch(`${apiBase}/api/movie/${props.movie.key}/tmdb`)
    const tmdb = await tmdbRes.json()
    tmdbId.value = tmdb.tmdb_id || null
    if (!tmdbId.value) return
    const imgRes = await fetch(`${apiBase}/api/tmdb/${tmdbId.value}/images`)
    const imgs = await imgRes.json()
    posters.value = imgs.posters || []
    logos.value = imgs.logos || []
    applyPosterFilter()
    applyLogoPreference()
  } catch (e) {
    console.error(e)
  }
}

const fetchLabels = async () => {
  try {
    const res = await fetch(`${apiBase}/api/movie/${props.movie.key}/labels`)
    if (!res.ok) return
    const data = await res.json()
    labels.value = data.labels || []
    // Apply default labels to remove from settings
    const defaultToRemove = settings.defaultLabelsToRemove.value || []
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

const fetchExistingPoster = async (forceRefresh = false) => {
  try {
    const res = await fetch(`${apiBase}/api/movie/${props.movie.key}/poster?meta=1${forceRefresh ? '&force_refresh=1' : ''}`)
    if (!res.ok) {
      existingPoster.value = null
      updateGlobalPosterCache(props.movie.key, null)
      return
    }
    const data = await res.json()
    if (data.url) {
      // Use absolute URL so it works when API is on another host/port
      existingPoster.value = data.url.startsWith('http')
        ? data.url
        : `${apiBase}${data.url}`
      updateGlobalPosterCache(props.movie.key, existingPoster.value)
    } else {
      existingPoster.value = null
      updateGlobalPosterCache(props.movie.key, null)
    }
    // Force re-render by toggling key
    posterRefreshKey.value += 1
  } catch (err) {
    console.error('Failed to fetch existing poster:', err)
    existingPoster.value = null
    updateGlobalPosterCache(props.movie.key, null)
  }
}

const toggleLabel = (label: string) => {
  const set = new Set(selectedLabels.value)
  if (set.has(label)) set.delete(label)
  else set.add(label)
  selectedLabels.value = set
}

const doPreview = async () => {
  if (!bgUrl.value) return
  await render.preview(props.movie, bgUrl.value, logoUrl.value, optionsPayload.value, selectedTemplate.value, selectedPreset.value)
}

const doSave = async () => {
  if (!bgUrl.value) return
  const res = await render.save(props.movie, bgUrl.value, logoUrl.value, optionsPayload.value, selectedTemplate.value, selectedPreset.value)
  if (res && typeof res.saved_path === 'string') {
    success(`Saved to ${res.saved_path}`)
  } else {
    success('Saved to disk')
  }
}

const doSend = async () => {
  if (!bgUrl.value) return
  try {
    await render.send(props.movie, bgUrl.value, logoUrl.value, optionsPayload.value, Array.from(selectedLabels.value), selectedTemplate.value, selectedPreset.value)
    success('Successfully sent poster to Plex!')
    // Wait 600ms for Plex to process, then refresh poster and labels
    await new Promise(resolve => setTimeout(resolve, 600))
    await fetchExistingPoster(true)
    await fetchLabels()
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to send poster to Plex'
    notifyError(message)
  }
}

// Load saved state on mount
onMounted(() => {
  loadEditorState()
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
    await fetchTmdbAssets()
    await fetchLabels()
    await fetchExistingPoster()
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

const applyPresetOptions = (id: string) => {
  const p = presets.value.find((x) => x.id === id)
  if (!p?.options) return

  const o = p.options

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
}

watch(selectedPreset, (id) => {
  applyPresetOptions(id)
})

let previewTimer: ReturnType<typeof setTimeout> | null = null
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
    strokeColor
  ],
  () => {
    if (previewTimer) clearTimeout(previewTimer)
    previewTimer = setTimeout(() => {
      doPreview()
    }, 400)
  },
  { deep: true }
)
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
          

          <div class="label-title">TMDb Posters</div>
          <div class="thumb-strip">
            <div
              v-for="p in filteredPosters"
              :key="p.url"
              class="thumb poster-thumb"
              :class="{ active: selectedPoster === p.url }"
              @click="selectedPoster = p.url"
            >
              <img :src="p.thumb || p.url" alt="" />
              <div class="source-badge">TMDb</div>
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

          <div v-if="!isLogoNone" class="label-title">TMDb Logos</div>
          <div v-if="!isLogoNone" class="thumb-strip logo-strip">
            <div
              v-for="l in filteredLogos"
              :key="l.url"
              class="thumb logo-thumb"
              :class="{ active: selectedLogo === l.url }"
              @click="selectedLogo = l.url"
            >
              <img :src="l.thumb || l.url" alt="" />
              <div class="source-badge">TMDb</div>
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

    <div class="preview-pane">
      <div class="preview-inner">
        <div class="preview-existing">
          <div class="preview-label">
            Current Plex Poster
            <button class="refresh-btn" title="Refresh poster" @click="fetchExistingPoster">
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

        <div class="preview-main">
          <div class="preview-label">
            Preview
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
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z" />
                  <circle cx="12" cy="13" r="3" />
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

            <!-- Bounding Box for Uniform Logo -->
            <div v-if="isUniformLogo && showBoundingBox && lastPreview" class="bounding-box" :style="boundingBoxStyle"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-shell {
  display: grid;
  grid-template-columns: 480px 1fr;
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

.poster-thumb {
  width: 70px;
  height: 105px;
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
  min-width: 80px;
  max-width: 140px;
  height: 50px;
  padding: 6px;
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
  min-width: 100px;
  height: 50px;
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

.preview-pane {
  background: rgba(10, 12, 18, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  overflow: auto;
  height: 100%;
}

.preview-inner {
  display: flex;
  gap: 20px;
  align-items: flex-start;
  max-width: 100%;
}

.preview-existing {
  text-align: center;
}

.preview-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
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
  flex: 1;
  max-width: 800px;
}

.preview-container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 500px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 12px;
  border: 1px solid var(--border);
}

.preview-img {
  max-height: 80vh;
  max-width: 100%;
  width: auto;
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
  max-height: 80vh;
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

.bounding-box {
  position: absolute;
  border: 2px dashed rgba(255, 255, 0, 0.8);
  pointer-events: none;
}
</style>
