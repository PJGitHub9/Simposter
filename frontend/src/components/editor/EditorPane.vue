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

// Simple debounce helper
function debounce<T extends (...args: any[]) => any>(fn: T, delay: number): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (timeoutId) clearTimeout(timeoutId)
    timeoutId = setTimeout(() => fn(...args), delay)
  }
}

const props = defineProps<{ movie: MovieInput }>()

const settings = useSettingsStore()
const { movies: globalMovies, setMoviePoster } = useMovies()

const apiBase = getApiBase()

const tmdbId = ref<number | null>(null)
const posters = ref<{ url: string; thumb?: string; has_text?: boolean; language?: string; source?: string }[]>([])
const logos = ref<{ url: string; thumb?: string; color?: string; language?: string; source?: string; type?: string }[]>([])
const labels = ref<string[]>([])
const selectedLabels = ref<Set<string>>(new Set())
const existingPoster = ref<string | null>(null)
const existingLogo = ref<string | null>(null)
const logoRefreshKey = ref(0)

const posterFilter = ref<'all' | 'textless' | 'text'>('all')
const posterLanguageFilter = ref<'all' | 'en' | 'with_lang'>('all')
const showTmdbPosters = ref(true)
const showFanartPosters = ref(true)
const logoPreference = ref<'first' | 'white' | 'color'>('first')
const logoLanguageFilter = ref<'all' | 'en' | 'with_lang'>('all')
const showTmdbLogos = ref(true)
const showFanartLogos = ref(true)
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
const POSTER_CACHE_KEY = 'simposter-poster-cache'

// Collections have no logo source of their own (TMDb collections carry
// posters/backdrops only) — this lets the user borrow a logo from one of the
// collection's member movies instead (works for a franchise's shared logo,
// not for studio/curated collections with no single representative movie).
const collectionMovies = ref<{ key: string; title: string; year?: number | null }[]>([])
const selectedCollectionMovieKey = ref<string | null>(null)
const loadingCollectionLogo = ref(false)

// Custom uploaded poster
const uploadedPosterUrl = ref<string | null>(null)
const posterUploading = ref(false)
const posterDropActive = ref(false)

const uploadPosterFile = async (file: File) => {
  if (!file.type.startsWith('image/')) return
  posterUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`${apiBase}/api/upload/background`, { method: 'POST', body: fd })
    if (!res.ok) throw new Error('Upload failed')
    const data = await res.json()
    uploadedPosterUrl.value = `${apiBase}${data.url}`
    selectedPoster.value = uploadedPosterUrl.value
  } catch (e) {
    console.error('[EditorPane] Poster upload failed:', e)
  } finally {
    posterUploading.value = false
  }
}

const onPosterFileInput = (e: Event) => {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) uploadPosterFile(file)
  ;(e.target as HTMLInputElement).value = ''
}

const onPosterDrop = (e: DragEvent) => {
  posterDropActive.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) uploadPosterFile(file)
}

const clearUploadedPoster = () => {
  uploadedPosterUrl.value = null
  if (selectedPoster.value && selectedPoster.value === uploadedPosterUrl.value) {
    selectedPoster.value = posters.value[0]?.url || null
  }
}

// Custom uploaded logo
const uploadedLogoUrl = ref<string | null>(null)
const logoUploading = ref(false)
const logoDropActive = ref(false)

const uploadLogoFile = async (file: File) => {
  if (!file.type.startsWith('image/')) return
  logoUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('kind', 'logo')
    const res = await fetch(`${apiBase}/api/upload/background`, { method: 'POST', body: fd })
    if (!res.ok) throw new Error('Upload failed')
    const data = await res.json()
    uploadedLogoUrl.value = `${apiBase}${data.url}`
    selectedLogo.value = uploadedLogoUrl.value
  } catch (e) {
    console.error('[EditorPane] Logo upload failed:', e)
  } finally {
    logoUploading.value = false
  }
}

const onLogoFileInput = (e: Event) => {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) uploadLogoFile(file)
  ;(e.target as HTMLInputElement).value = ''
}

const onLogoDrop = (e: DragEvent) => {
  logoDropActive.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) uploadLogoFile(file)
}

const clearUploadedLogo = () => {
  uploadedLogoUrl.value = null
  if (selectedLogo.value && selectedLogo.value === uploadedLogoUrl.value) {
    selectedLogo.value = filteredLogos.value[0]?.url || null
  }
}

const showBoundingBox = ref(false)
const previewImgRef = ref<HTMLImageElement | null>(null)
const posterRefreshKey = ref(0)

const options = ref({
  posterZoom: 100,
  posterShiftY: 0,
  matteHeight: 0,
  fadeHeight: 0,
  topMatteHeight: 0,
  topFadeHeight: 0,
  vignette: 0,
  grain: 0,
  logoScale: 50,
  logoOffset: 75,
  uniformLogoMaxW: 500,
  uniformLogoMaxH: 200,
  uniformLogoOffsetX: 50,
  uniformLogoOffsetY: 78,
  uniformLogoHAlign: 'center' as 'left' | 'center' | 'right',
  uniformLogoVAlign: 'center' as 'top' | 'center' | 'bottom',
  uniformLogoShadowEnabled: false,
  uniformLogoShadowOpacity: 60,
  uniformLogoShadowAngle: -45,
  uniformLogoShadowDistance: 8,
  uniformLogoShadowSize: 15,
  uniformLogoShadowColor: '#000000',
  borderEnabled: false,
  borderThickness: 0,
  borderColor: '#ffffff',
  overlayFile: '',
  overlayOpacity: 40,
  overlayMode: 'screen',
  overlayConfigIds: [] as string[],
  overlayConfigIdsBelow: [] as string[]
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
const shadowEnabled = ref(false)
const shadowBlur = ref(10)
const shadowOffsetX = ref(0)
const shadowOffsetY = ref(4)
const shadowColor = ref('#000000')
const shadowOpacity = ref(80)
const strokeEnabled = ref(false)
const strokeWidth = ref(4)
const strokeColor = ref('#000000')
const textBboxEnabled = ref(false)
const availableFonts = ref<string[]>([])

// Overlay configs
const overlayConfigs = ref<{ id: string; name: string }[]>([])

const render = useRenderService()
const loading = render.loading
const error = render.error
const lastPreview = render.lastPreview

const { success, error: notifyError, info: notifyInfo } = useNotification()

const presetService = usePresetService()
const templates = presetService.templates
const presets = presetService.presets
const selectedTemplate = presetService.selectedTemplate
const selectedPreset = presetService.selectedPreset
const presetLoading = presetService.loading
const newPresetId = ref('')

const isUniformLogo = computed(() => selectedTemplate.value === 'uniformlogo')

// Accordion section open/close state
const sectionOpen = ref({
  template: false,
  poster: true,
  logo: true,
  text: false,
  boundingBox: false,
  overlay: false,
})
const toggleSection = (key: keyof typeof sectionOpen.value) => {
  sectionOpen.value[key] = !sectionOpen.value[key]
}

// State persistence
const EDITOR_STATE_KEY = 'simposter_editor_state'

const saveEditorStateImmediate = () => {
  try {
    const state = {
      options: options.value,
      selectedTemplate: selectedTemplate.value,
      selectedPreset: selectedPreset.value,
      posterFilter: posterFilter.value,
      posterLanguageFilter: posterLanguageFilter.value,
      showTmdbPosters: showTmdbPosters.value,
      showFanartPosters: showFanartPosters.value,
      logoPreference: logoPreference.value,
      logoLanguageFilter: logoLanguageFilter.value,
      showTmdbLogos: showTmdbLogos.value,
      showFanartLogos: showFanartLogos.value,
      showClearArt: showClearArt.value,
      logoMode: logoMode.value,
      logoHex: logoHex.value,
      sectionOpen: sectionOpen.value,
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
        strokeColor: strokeColor.value,
        bboxEnabled: textBboxEnabled.value
      }
    }
    localStorage.setItem(EDITOR_STATE_KEY, JSON.stringify(state))
  } catch (e) {
    console.warn('Failed to save editor state:', e)
  }
}

// Debounced version to reduce localStorage writes
const saveEditorState = debounce(saveEditorStateImmediate, 300)

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
    if (state.logoPreference) logoPreference.value = state.logoPreference
    // Only restore language filters if they're not set to default 'all' (prefer global settings)
    if (state.logoLanguageFilter && state.logoLanguageFilter !== 'all') logoLanguageFilter.value = state.logoLanguageFilter
    if (typeof state.showTmdbLogos === 'boolean') showTmdbLogos.value = state.showTmdbLogos
    if (typeof state.showFanartLogos === 'boolean') showFanartLogos.value = state.showFanartLogos
    if (typeof state.showClearArt === 'boolean') showClearArt.value = state.showClearArt
    if (state.logoMode) logoMode.value = state.logoMode
    if (state.logoHex) logoHex.value = state.logoHex
    if (state.sectionOpen) Object.assign(sectionOpen.value, state.sectionOpen)
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
      shadowEnabled.value = state.textOverlay.shadowEnabled ?? false
      shadowBlur.value = state.textOverlay.shadowBlur ?? 10
      shadowOffsetX.value = state.textOverlay.shadowOffsetX ?? 0
      shadowOffsetY.value = state.textOverlay.shadowOffsetY ?? 4
      shadowColor.value = state.textOverlay.shadowColor ?? '#000000'
      shadowOpacity.value = state.textOverlay.shadowOpacity ?? 80
      strokeEnabled.value = state.textOverlay.strokeEnabled ?? false
      strokeWidth.value = state.textOverlay.strokeWidth ?? 4
      strokeColor.value = state.textOverlay.strokeColor ?? '#000000'
      textBboxEnabled.value = state.textOverlay.bboxEnabled ?? false
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

  // Position (centered on offset point, adjusted for image offset within container)
  const left = img.offsetLeft + (imgWidth * offsetX) - (boxWidth / 2)
  const top = img.offsetTop + (imgHeight * offsetY) - (boxHeight / 2)

  return {
    width: `${boxWidth}px`,
    height: `${boxHeight}px`,
    left: `${left}px`,
    top: `${top}px`
  }
})

const filteredPosters = computed(() => {
  let items = posters.value
  if (posterFilter.value === 'textless') {
    items = items.filter((p) => p.has_text === false || !p.language)
  } else if (posterFilter.value === 'text') {
    items = items.filter((p) => p.has_text === true)
  }

  // Skip language filter when showing textless posters
  if (posterFilter.value !== 'textless') {
    if (posterLanguageFilter.value === 'en') {
      items = items.filter((p) => (p.language || '').toLowerCase() === 'en' || (p.language || '').toLowerCase() === 'eng')
    } else if (posterLanguageFilter.value === 'with_lang') {
      items = items.filter((p) => !!p.language)
    }
  }

  items = items.filter((p) => {
    const src = (p.source || 'tmdb').toLowerCase()
    if (src === 'fanart') return showFanartPosters.value
    return showTmdbPosters.value
  })

  return items
})

const filteredLogos = computed(() => {
  let items = logos.value
  if (logoLanguageFilter.value === 'en') {
    items = items.filter((l) => (l.language || '').toLowerCase() === 'en' || (l.language || '').toLowerCase() === 'eng' || !l.language)
  } else if (logoLanguageFilter.value === 'with_lang') {
    items = items.filter((l) => !!l.language)
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

const optionsPayload = computed(() => ({
  poster_zoom: options.value.posterZoom / 100,
  poster_shift_y: options.value.posterShiftY / 100,
  matte_height_ratio: options.value.matteHeight / 100,
  fade_height_ratio: options.value.fadeHeight / 100,
  top_matte_height_ratio: options.value.topMatteHeight / 100,
  top_fade_height_ratio: options.value.topFadeHeight / 100,
  vignette_strength: options.value.vignette / 100,
  grain_amount: options.value.grain / 100,
  logo_scale: options.value.logoScale / 100,
  logo_offset: options.value.logoOffset / 100,
  uniform_logo_max_w: options.value.uniformLogoMaxW,
  uniform_logo_max_h: options.value.uniformLogoMaxH,
  uniform_logo_offset_x: options.value.uniformLogoOffsetX / 100,
  uniform_logo_offset_y: options.value.uniformLogoOffsetY / 100,
  uniform_logo_h_align: options.value.uniformLogoHAlign,
  uniform_logo_v_align: options.value.uniformLogoVAlign,
  uniform_logo_shadow_enabled: options.value.uniformLogoShadowEnabled,
  uniform_logo_shadow_opacity: options.value.uniformLogoShadowOpacity,
  uniform_logo_shadow_angle: options.value.uniformLogoShadowAngle,
  uniform_logo_shadow_distance: options.value.uniformLogoShadowDistance,
  uniform_logo_shadow_size: options.value.uniformLogoShadowSize,
  uniform_logo_shadow_color: options.value.uniformLogoShadowColor,
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
  stroke_color: strokeColor.value,
  text_bbox_enabled: textBboxEnabled.value,
  overlay_config_ids: options.value.overlayConfigIds.length > 0 ? options.value.overlayConfigIds : undefined,
  overlay_config_ids_below: options.value.overlayConfigIdsBelow.length > 0 ? options.value.overlayConfigIdsBelow : undefined
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
    shadowEnabled.value = false
    shadowBlur.value = 10
    shadowOffsetX.value = 0
    shadowOffsetY.value = 4
    shadowColor.value = '#000000'
    shadowOpacity.value = 80
    strokeEnabled.value = false
    strokeWidth.value = 4
    strokeColor.value = '#000000'
    textBboxEnabled.value = false
    options.value.posterZoom = Math.round((Number(o.poster_zoom) || 1) * 100)
    options.value.posterShiftY = Math.round((Number(o.poster_shift_y) || 0) * 100)
    options.value.matteHeight = Math.round((Number(o.matte_height_ratio) || 0) * 100)
    options.value.fadeHeight = Math.round((Number(o.fade_height_ratio) || 0) * 100)
    options.value.topMatteHeight = Math.round((Number(o.top_matte_height_ratio) || 0) * 100)
    options.value.topFadeHeight = Math.round((Number(o.top_fade_height_ratio) || 0) * 100)
    options.value.vignette = Math.round((Number(o.vignette_strength) || 0) * 100)
    options.value.grain = Math.round((Number(o.grain_amount) || 0) * 100)
    options.value.logoScale = Math.round((Number(o.logo_scale) || 0.5) * 100)
    options.value.logoOffset = Math.round((Number(o.logo_offset) || 0.75) * 100)
    if (o.uniform_logo_max_w) options.value.uniformLogoMaxW = Number(o.uniform_logo_max_w)
    if (o.uniform_logo_max_h) options.value.uniformLogoMaxH = Number(o.uniform_logo_max_h)
    if (typeof o.uniform_logo_offset_x === 'number') options.value.uniformLogoOffsetX = Math.round(o.uniform_logo_offset_x * 100)
    if (typeof o.uniform_logo_offset_y === 'number') options.value.uniformLogoOffsetY = Math.round(o.uniform_logo_offset_y * 100)
    if (typeof o.uniform_logo_h_align === 'string') options.value.uniformLogoHAlign = o.uniform_logo_h_align as 'left' | 'center' | 'right'
    if (typeof o.uniform_logo_v_align === 'string') options.value.uniformLogoVAlign = o.uniform_logo_v_align as 'top' | 'center' | 'bottom'
    options.value.uniformLogoShadowEnabled = !!o.uniform_logo_shadow_enabled
    if (typeof o.uniform_logo_shadow_opacity === 'number') options.value.uniformLogoShadowOpacity = o.uniform_logo_shadow_opacity
    if (typeof o.uniform_logo_shadow_angle === 'number') options.value.uniformLogoShadowAngle = o.uniform_logo_shadow_angle
    if (typeof o.uniform_logo_shadow_distance === 'number') options.value.uniformLogoShadowDistance = o.uniform_logo_shadow_distance
    if (typeof o.uniform_logo_shadow_size === 'number') options.value.uniformLogoShadowSize = o.uniform_logo_shadow_size
    if (o.uniform_logo_shadow_color) options.value.uniformLogoShadowColor = String(o.uniform_logo_shadow_color)
    options.value.borderEnabled = !!o.border_enabled
    options.value.borderThickness = Number(o.border_px) || 0
    if (o.border_color) options.value.borderColor = String(o.border_color)
    if (o.overlay_file) options.value.overlayFile = String(o.overlay_file)
    if (typeof o.overlay_opacity === 'number') options.value.overlayOpacity = Math.round(o.overlay_opacity * 100)
    if (o.overlay_mode) options.value.overlayMode = String(o.overlay_mode)
    if (Array.isArray(o.overlay_config_ids)) options.value.overlayConfigIds = o.overlay_config_ids
    if (Array.isArray(o.overlay_config_ids_below)) options.value.overlayConfigIdsBelow = o.overlay_config_ids_below
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
    textBboxEnabled.value = !!o.text_bbox_enabled

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
    top_matte_height_ratio: options.value.topMatteHeight / 100,
    top_fade_height_ratio: options.value.topFadeHeight / 100,
    vignette_strength: options.value.vignette / 100,
    grain_amount: options.value.grain / 100,
    logo_scale: options.value.logoScale / 100,
    logo_offset: options.value.logoOffset / 100,
    uniform_logo_max_w: options.value.uniformLogoMaxW,
    uniform_logo_max_h: options.value.uniformLogoMaxH,
    uniform_logo_offset_x: options.value.uniformLogoOffsetX / 100,
    uniform_logo_offset_y: options.value.uniformLogoOffsetY / 100,
    uniform_logo_h_align: options.value.uniformLogoHAlign,
    uniform_logo_v_align: options.value.uniformLogoVAlign,
    uniform_logo_shadow_enabled: options.value.uniformLogoShadowEnabled,
    uniform_logo_shadow_opacity: options.value.uniformLogoShadowOpacity,
    uniform_logo_shadow_angle: options.value.uniformLogoShadowAngle,
    uniform_logo_shadow_distance: options.value.uniformLogoShadowDistance,
    uniform_logo_shadow_size: options.value.uniformLogoShadowSize,
    uniform_logo_shadow_color: options.value.uniformLogoShadowColor,
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
    stroke_color: strokeColor.value,
    text_bbox_enabled: textBboxEnabled.value,
    overlay_config_ids: options.value.overlayConfigIds.length > 0 ? options.value.overlayConfigIds : undefined,
    overlay_config_ids_below: options.value.overlayConfigIdsBelow.length > 0 ? options.value.overlayConfigIdsBelow : undefined
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

  // Preset IDs are used as filenames/DB keys and only allow letters, numbers, hyphens,
  // and underscores server-side — slugify here so a natural-language name like "top overlay"
  // doesn't silently succeed on save but then fail every subsequent preview/render.
  const slugified = newPresetId.value.trim().replace(/\s+/g, '-').replace(/[^a-zA-Z0-9_-]/g, '')
  if (!slugified) {
    notifyError('Preset id must contain letters, numbers, hyphens, or underscores')
    return
  }
  if (slugified !== newPresetId.value.trim()) {
    notifyInfo(`Preset id can't contain spaces or special characters — saving as "${slugified}"`)
  }

  const backendOptions = {
    poster_zoom: options.value.posterZoom / 100,
    poster_shift_y: options.value.posterShiftY / 100,
    matte_height_ratio: options.value.matteHeight / 100,
    fade_height_ratio: options.value.fadeHeight / 100,
    top_matte_height_ratio: options.value.topMatteHeight / 100,
    top_fade_height_ratio: options.value.topFadeHeight / 100,
    vignette_strength: options.value.vignette / 100,
    grain_amount: options.value.grain / 100,
    logo_scale: options.value.logoScale / 100,
    logo_offset: options.value.logoOffset / 100,
    uniform_logo_max_w: options.value.uniformLogoMaxW,
    uniform_logo_max_h: options.value.uniformLogoMaxH,
    uniform_logo_offset_x: options.value.uniformLogoOffsetX / 100,
    uniform_logo_offset_y: options.value.uniformLogoOffsetY / 100,
    uniform_logo_h_align: options.value.uniformLogoHAlign,
    uniform_logo_v_align: options.value.uniformLogoVAlign,
    uniform_logo_shadow_enabled: options.value.uniformLogoShadowEnabled,
    uniform_logo_shadow_opacity: options.value.uniformLogoShadowOpacity,
    uniform_logo_shadow_angle: options.value.uniformLogoShadowAngle,
    uniform_logo_shadow_distance: options.value.uniformLogoShadowDistance,
    uniform_logo_shadow_size: options.value.uniformLogoShadowSize,
    uniform_logo_shadow_color: options.value.uniformLogoShadowColor,
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
    stroke_color: strokeColor.value,
    text_bbox_enabled: textBboxEnabled.value,
    overlay_config_ids: options.value.overlayConfigIds.length > 0 ? options.value.overlayConfigIds : undefined,
    overlay_config_ids_below: options.value.overlayConfigIdsBelow.length > 0 ? options.value.overlayConfigIdsBelow : undefined
  }

  await presetService.savePresetAs(slugified, backendOptions)
  if (!presetService.error.value) {
    selectedPreset.value = slugified
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
    const mediaType = props.movie.mediaType || 'movie'

    if (mediaType === 'collection') {
      // Plex collections carry no TMDb ID of their own — resolved via a
      // one-time title search, cached server-side (collection_cache.tmdb_collection_id).
      // TMDb collections have posters/backdrops but no logos (unlike movies/shows) —
      // Fanart.tv does have franchise-wide logos, tagged under the same TMDb
      // collection ID in its /v3/movies/{id} namespace (verified live against
      // the LOTR collection). Falls back to an empty list if Fanart has none
      // for this collection; the "Import Logo From Movie" picker still covers that case.
      fetchCollectionMovies()

      const tmdbRes = await fetch(`${apiBase}/api/collection/${props.movie.key}/tmdb`)
      const tmdb = await tmdbRes.json()
      tmdbId.value = tmdb.tmdb_id || null
      if (!tmdbId.value) return

      const [imgRes, fanartRes] = await Promise.all([
        fetch(`${apiBase}/api/tmdb/collection/${tmdbId.value}/images`),
        fetch(`${apiBase}/api/tmdb/collection/${tmdbId.value}/fanart-logos`)
      ])
      const imgs = await imgRes.json()
      const fanart = await fanartRes.json()
      posters.value = imgs.posters || []
      logos.value = fanart.logos || []
      applyPosterFilter()
      applyLogoPreference()
      return
    }

    const isTvShow = mediaType === 'tv-show'

    // Use appropriate endpoint for TMDB ID lookup
    const tmdbEndpoint = isTvShow
      ? `${apiBase}/api/tv-show/${props.movie.key}/tmdb`
      : `${apiBase}/api/movie/${props.movie.key}/tmdb`

    const tmdbRes = await fetch(tmdbEndpoint)
    const tmdb = await tmdbRes.json()
    tmdbId.value = tmdb.tmdb_id || null
    if (!tmdbId.value) return

    // Use appropriate endpoint for images
    const imagesEndpoint = isTvShow
      ? `${apiBase}/api/tmdb/tv/${tmdbId.value}/images`
      : `${apiBase}/api/tmdb/${tmdbId.value}/images`

    const imgRes = await fetch(imagesEndpoint)
    const imgs = await imgRes.json()
    posters.value = imgs.posters || []
    logos.value = imgs.logos || []
    applyPosterFilter()
    applyLogoPreference()
  } catch (e) {
    console.error(e)
  }
}

const fetchCollectionMovies = async () => {
  collectionMovies.value = []
  selectedCollectionMovieKey.value = null
  try {
    const res = await fetch(`${apiBase}/api/collection/${props.movie.key}/movies`)
    if (!res.ok) return
    const data = await res.json()
    collectionMovies.value = data.movies || []
  } catch (e) {
    console.error(e)
  }
}

const importLogoFromMovie = async (movieKey: string | null) => {
  if (!movieKey) return
  loadingCollectionLogo.value = true
  try {
    const tmdbRes = await fetch(`${apiBase}/api/movie/${movieKey}/tmdb`)
    const tmdb = await tmdbRes.json()
    const movieTmdbId = tmdb.tmdb_id || null
    if (!movieTmdbId) {
      logos.value = []
      return
    }
    const imgRes = await fetch(`${apiBase}/api/tmdb/${movieTmdbId}/images`)
    const imgs = await imgRes.json()
    logos.value = imgs.logos || []
    applyLogoPreference()
  } catch (e) {
    console.error(e)
  } finally {
    loadingCollectionLogo.value = false
  }
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
    const refreshFlag = typeof forceRefresh === 'boolean'
      ? forceRefresh
      : false
    const mediaType = props.movie.mediaType || 'movie'
    const isTvShow = mediaType === 'tv-show'
    const endpoint = isTvShow
      ? `${apiBase}/api/tv-show/${props.movie.key}/poster?meta=1${refreshFlag ? '&force_refresh=1' : ''}`
      : `${apiBase}/api/movie/${props.movie.key}/poster?meta=1${refreshFlag ? '&force_refresh=1' : ''}`

    const res = await fetch(endpoint)
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

const fetchExistingLogo = async (forceRefresh = false) => {
  try {
    const params = `${forceRefresh ? 'force_refresh=1&' : ''}v=${Date.now()}`
    const url = `${apiBase}/api/logo/${props.movie.key}?${params}`
    const res = await fetch(url)
    existingLogo.value = res.ok ? url : null
    logoRefreshKey.value += 1
  } catch {
    existingLogo.value = null
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

const sendLogo = ref((settings.plex.value as any).sendLogosToPlex ?? false)
const logoSending = ref(false)

const doSendLogoOnly = async () => {
  if (!logoUrl.value) {
    notifyError('No logo selected to send.')
    return
  }
  logoSending.value = true
  try {
    const res = await fetch(`${apiBase}/api/plex/send-logo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rating_key: props.movie.key,
        logo_url: logoUrl.value,
        is_tv: false,
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    success('Logo sent to Plex!')
    await fetchExistingLogo()
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to send logo to Plex'
    notifyError(message)
  } finally {
    logoSending.value = false
  }
}

const doSend = async () => {
  if (!bgUrl.value) return
  try {
    await render.send(props.movie, bgUrl.value, logoUrl.value, optionsPayload.value, Array.from(selectedLabels.value), selectedTemplate.value, selectedPreset.value, sendLogo.value)
    success('Successfully sent poster to Plex!')
    // Wait 600ms for Plex to process, then refresh poster and labels
    await new Promise(resolve => setTimeout(resolve, 600))
    await fetchExistingPoster(true)
    await fetchExistingLogo()
    await fetchLabels()
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to send poster to Plex'
    notifyError(message)
  }
}

// Load overlay configs for the selector
const loadOverlayConfigs = async () => {
  try {
    const res = await fetch(`${apiBase}/api/overlay-configs`)
    if (res.ok) {
      const data = await res.json()
      overlayConfigs.value = (data.configs || []).map((c: any) => ({ id: c.id, name: c.name }))
    }
  } catch (e) {
    console.warn('Failed to load overlay configs:', e)
  }
}

const toggleOverlayConfig = (configId: string) => {
  const idx = options.value.overlayConfigIds.indexOf(configId)
  if (idx >= 0) {
    options.value.overlayConfigIds.splice(idx, 1)
    const belowIdx = options.value.overlayConfigIdsBelow.indexOf(configId)
    if (belowIdx >= 0) options.value.overlayConfigIdsBelow.splice(belowIdx, 1)
  } else {
    options.value.overlayConfigIds.push(configId)
  }
}

const toggleOverlayConfigBelow = (configId: string) => {
  const idx = options.value.overlayConfigIdsBelow.indexOf(configId)
  if (idx >= 0) {
    options.value.overlayConfigIdsBelow.splice(idx, 1)
  } else {
    options.value.overlayConfigIdsBelow.push(configId)
  }
}

// Load saved state on mount
onMounted(async () => {
  await loadGlobalFallbackSettings()
  loadEditorState()
  loadOverlayConfigs()
  fetch(`${apiBase}/api/fonts`)
    .then(r => r.ok ? r.json() : null)
    .then(d => { if (d?.fonts) availableFonts.value = d.fonts })
    .catch(() => {})
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
  strokeColor,
  textBboxEnabled
], () => {
  saveEditorState()
}, { deep: true })

watch(
  () => props.movie.key,
  async () => {
    await fetchTmdbAssets()
    await fetchLabels()
    await fetchExistingPoster()
    await fetchExistingLogo()
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
  shadowEnabled.value = false
  shadowBlur.value = 10
  shadowOffsetX.value = 0
  shadowOffsetY.value = 4
  shadowColor.value = '#000000'
  shadowOpacity.value = 80
  strokeEnabled.value = false
  strokeWidth.value = 4
  strokeColor.value = '#000000'
  textBboxEnabled.value = false

  options.value.posterZoom = Math.round((Number(o.poster_zoom) || 1) * 100)
  options.value.posterShiftY = Math.round((Number(o.poster_shift_y) || 0) * 100)
  options.value.matteHeight = Math.round((Number(o.matte_height_ratio) || 0) * 100)
  options.value.fadeHeight = Math.round((Number(o.fade_height_ratio) || 0) * 100)
  options.value.topMatteHeight = Math.round((Number(o.top_matte_height_ratio) || 0) * 100)
  options.value.topFadeHeight = Math.round((Number(o.top_fade_height_ratio) || 0) * 100)
  options.value.vignette = Math.round((Number(o.vignette_strength) || 0) * 100)
  options.value.grain = Math.round((Number(o.grain_amount) || 0) * 100)
  options.value.logoScale = Math.round((Number(o.logo_scale) || 0.5) * 100)
  options.value.logoOffset = Math.round((Number(o.logo_offset) || 0.75) * 100)
  if (o.uniform_logo_max_w) options.value.uniformLogoMaxW = Number(o.uniform_logo_max_w)
  if (o.uniform_logo_max_h) options.value.uniformLogoMaxH = Number(o.uniform_logo_max_h)
  if (typeof o.uniform_logo_offset_x === 'number') options.value.uniformLogoOffsetX = Math.round(o.uniform_logo_offset_x * 100)
  if (typeof o.uniform_logo_offset_y === 'number') options.value.uniformLogoOffsetY = Math.round(o.uniform_logo_offset_y * 100)
  if (typeof o.uniform_logo_h_align === 'string') options.value.uniformLogoHAlign = o.uniform_logo_h_align as 'left' | 'center' | 'right'
  if (typeof o.uniform_logo_v_align === 'string') options.value.uniformLogoVAlign = o.uniform_logo_v_align as 'top' | 'center' | 'bottom'
  options.value.uniformLogoShadowEnabled = !!o.uniform_logo_shadow_enabled
  if (typeof o.uniform_logo_shadow_opacity === 'number') options.value.uniformLogoShadowOpacity = o.uniform_logo_shadow_opacity
  if (typeof o.uniform_logo_shadow_angle === 'number') options.value.uniformLogoShadowAngle = o.uniform_logo_shadow_angle
  if (typeof o.uniform_logo_shadow_distance === 'number') options.value.uniformLogoShadowDistance = o.uniform_logo_shadow_distance
  if (typeof o.uniform_logo_shadow_size === 'number') options.value.uniformLogoShadowSize = o.uniform_logo_shadow_size
  if (o.uniform_logo_shadow_color) options.value.uniformLogoShadowColor = String(o.uniform_logo_shadow_color)
  options.value.borderEnabled = !!o.border_enabled
  options.value.borderThickness = Number(o.border_px) || 0
  if (o.border_color) options.value.borderColor = String(o.border_color)
  if (o.overlay_file) options.value.overlayFile = String(o.overlay_file)
  if (typeof o.overlay_opacity === 'number') options.value.overlayOpacity = Math.round(o.overlay_opacity * 100)
  if (o.overlay_mode) options.value.overlayMode = String(o.overlay_mode)
  if (Array.isArray(o.overlay_config_ids)) options.value.overlayConfigIds = o.overlay_config_ids
  if (Array.isArray(o.overlay_config_ids_below)) options.value.overlayConfigIdsBelow = o.overlay_config_ids_below
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
  textBboxEnabled.value = !!o.text_bbox_enabled

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
    strokeColor,
    textBboxEnabled
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

        <!-- 1. Preset -->
        <div class="acc-section">
          <button class="acc-header" @click="toggleSection('template')">
            <span>Preset</span>
            <svg class="acc-chevron" :class="{ open: sectionOpen.template }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <div v-show="sectionOpen.template" class="acc-body">
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
        </div>

        <!-- 2. Poster -->
        <div class="acc-section">
          <button class="acc-header" @click="toggleSection('poster')">
            <span>Poster</span>
            <svg class="acc-chevron" :class="{ open: sectionOpen.poster }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <div v-show="sectionOpen.poster" class="acc-body">
            <!-- Poster source -->
            <div class="sub-section-title" style="margin-top: 0">Source</div>
            <label class="field-label">
              Filter
              <select v-model="posterFilter">
                <option value="all">All Posters</option>
                <option value="textless">Textless Only</option>
                <option value="text">With Text</option>
              </select>
            </label>
            <div class="inline-controls">
              <label class="inline-field" v-if="posterFilter !== 'textless'">
                <span>Language</span>
                <select v-model="posterLanguageFilter">
                  <option value="all">All</option>
                  <option value="en">English</option>
                  <option value="with_lang">With language tag</option>
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
            </div>
            <div class="sub-section-title">Upload &amp; Selection</div>
            <!-- Custom upload -->
            <div
              class="poster-upload-zone"
              :class="{ 'drag-over': posterDropActive, 'has-upload': !!uploadedPosterUrl }"
              @dragover.prevent="posterDropActive = true"
              @dragleave="posterDropActive = false"
              @drop.prevent="onPosterDrop"
              @click="!uploadedPosterUrl && ($refs.posterFileInput as HTMLInputElement)?.click()"
            >
              <template v-if="uploadedPosterUrl">
                <img :src="uploadedPosterUrl" class="upload-preview" alt="Uploaded poster" />
                <div class="upload-overlay">
                  <button class="upload-reselect" @click.stop="selectedPoster = uploadedPosterUrl" :class="{ active: selectedPoster === uploadedPosterUrl }">Use this</button>
                  <button class="upload-replace" @click.stop="($refs.posterFileInput as HTMLInputElement)?.click()">Replace</button>
                  <button class="upload-remove" @click.stop="clearUploadedPoster">✕</button>
                </div>
              </template>
              <template v-else>
                <div class="upload-prompt">
                  <span v-if="posterUploading">Uploading…</span>
                  <span v-else>&#8679; Drop image or click to upload</span>
                </div>
              </template>
            </div>
            <input ref="posterFileInput" type="file" accept="image/*" style="display:none" @change="onPosterFileInput" />

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

            <!-- Poster adjustments -->
            <div class="sub-section-title">Position</div>
            <div class="slider">
              <label>Poster Shift Y %</label>
              <div class="slider-row">
                <input v-model.number="options.posterShiftY" type="range" min="-50" max="50" />
                <input v-model.number="options.posterShiftY" type="number" min="-50" max="50" class="slider-num" />
              </div>
            </div>

            <div class="sub-section-title">Top Fade</div>
            <div class="slider">
              <label>Top Matte Height %</label>
              <div class="slider-row">
                <input v-model.number="options.topMatteHeight" type="range" min="0" max="50" />
                <input v-model.number="options.topMatteHeight" type="number" min="0" max="50" class="slider-num" />
              </div>
            </div>
            <div class="slider">
              <label>Top Fade Height %</label>
              <div class="slider-row">
                <input v-model.number="options.topFadeHeight" type="range" min="0" max="100" />
                <input v-model.number="options.topFadeHeight" type="number" min="0" max="100" class="slider-num" />
              </div>
            </div>

            <div class="sub-section-title">Bottom Fade</div>
            <div class="slider">
              <label>Bottom Matte Height %</label>
              <div class="slider-row">
                <input v-model.number="options.matteHeight" type="range" min="0" max="50" />
                <input v-model.number="options.matteHeight" type="number" min="0" max="50" class="slider-num" />
              </div>
            </div>
            <div class="slider">
              <label>Bottom Fade Height %</label>
              <div class="slider-row">
                <input v-model.number="options.fadeHeight" type="range" min="0" max="100" />
                <input v-model.number="options.fadeHeight" type="number" min="0" max="100" class="slider-num" />
              </div>
            </div>

            <div class="sub-section-title">Effects</div>
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
        </div>

        <!-- 3. Logo -->
        <div class="acc-section">
          <button class="acc-header" @click="toggleSection('logo')">
            <span>Logo</span>
            <svg class="acc-chevron" :class="{ open: sectionOpen.logo }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <div v-show="sectionOpen.logo" class="acc-body">
            <!-- Logo mode + color (preset-level — used by batch & webhook) -->
            <div class="sub-section-title" style="margin-top: 0">Preset / Batch / Webhook</div>
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

            <div class="sub-section-title">Preview Logo (Manual Selection)</div>

            <!-- Logo source + thumbnails -->
            <template v-if="!isLogoNone">
              <template v-if="props.movie.mediaType === 'collection'">
                <p class="muted-text" v-if="logos.length">
                  Showing {{ logos.length }} franchise logo{{ logos.length === 1 ? '' : 's' }} from Fanart.tv, or import one from a specific movie below.
                </p>
                <label class="field-label">
                  Import Logo From Movie {{ logos.length ? '(overrides the list above)' : '' }}
                  <select
                    v-model="selectedCollectionMovieKey"
                    @change="importLogoFromMovie(selectedCollectionMovieKey)"
                  >
                    <option :value="null">Select a movie in this collection…</option>
                    <option v-for="m in collectionMovies" :key="m.key" :value="m.key">
                      {{ m.title }}{{ m.year ? ` (${m.year})` : '' }}
                    </option>
                  </select>
                </label>
                <p class="muted-text" v-if="loadingCollectionLogo">Loading logo options…</p>
                <p class="muted-text" v-else-if="!logos.length && collectionMovies.length === 0">No movies found in this collection.</p>
                <p class="muted-text" v-else-if="!logos.length">No franchise logo found on Fanart.tv for this collection — try importing one from a movie instead.</p>
              </template>
              <label class="field-label">
                Logo Style
                <select v-model="logoPreference">
                  <option value="first">First Available</option>
                  <option value="white">White Logos</option>
                  <option value="color">Colored Logos</option>
                </select>
              </label>
              <div class="inline-controls">
                <label class="inline-field">
                  <span>Language</span>
                  <select v-model="logoLanguageFilter">
                    <option value="all">All</option>
                    <option value="en">English</option>
                    <option value="with_lang">With language tag</option>
                  </select>
                </label>
                <label class="inline-field">
                  <span>Clearart</span>
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
              </div>

              <!-- Custom upload -->
              <div
                class="logo-upload-zone"
                :class="{ 'drag-over': logoDropActive, 'has-upload': !!uploadedLogoUrl }"
                @dragover.prevent="logoDropActive = true"
                @dragleave="logoDropActive = false"
                @drop.prevent="onLogoDrop"
                @click="!uploadedLogoUrl && ($refs.logoFileInput as HTMLInputElement)?.click()"
              >
                <template v-if="uploadedLogoUrl">
                  <img :src="uploadedLogoUrl" class="upload-preview" alt="Uploaded logo" />
                  <div class="upload-overlay">
                    <button class="upload-reselect" @click.stop="selectedLogo = uploadedLogoUrl" :class="{ active: selectedLogo === uploadedLogoUrl }">Use this</button>
                    <button class="upload-replace" @click.stop="($refs.logoFileInput as HTMLInputElement)?.click()">Replace</button>
                    <button class="upload-remove" @click.stop="clearUploadedLogo">✕</button>
                  </div>
                </template>
                <template v-else>
                  <div class="upload-prompt">
                    <span v-if="logoUploading">Uploading…</span>
                    <span v-else>&#8679; Drop image or click to upload</span>
                  </div>
                </template>
              </div>
              <input ref="logoFileInput" type="file" accept="image/*" style="display:none" @change="onLogoFileInput" />

              <div class="thumb-strip logo-strip">
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
            </template>

            <!-- Drop Shadow: Uniform Logo templates only — box geometry for the logo itself
                 lives in the separate "Bounding Box" section (shared with Custom Text), but the
                 shadow effect only ever applies to the logo, so it lives here instead. -->
            <template v-if="isUniformLogo">
              <div class="sub-section-title">Drop Shadow</div>
              <label class="checkbox-label">
                <input type="checkbox" v-model="options.uniformLogoShadowEnabled" />
                <span>Drop shadow</span>
              </label>
              <template v-if="options.uniformLogoShadowEnabled">
                <div class="slider">
                  <label>Shadow Color</label>
                  <input v-model="options.uniformLogoShadowColor" type="color" />
                </div>
                <div class="slider">
                  <label>Opacity (%)</label>
                  <div class="slider-row">
                    <input v-model.number="options.uniformLogoShadowOpacity" type="range" min="0" max="100" />
                    <input v-model.number="options.uniformLogoShadowOpacity" type="number" min="0" max="100" class="slider-num" />
                  </div>
                </div>
                <div class="slider">
                  <label>Angle (°)</label>
                  <div class="slider-row">
                    <input v-model.number="options.uniformLogoShadowAngle" type="range" min="-180" max="180" />
                    <input v-model.number="options.uniformLogoShadowAngle" type="number" min="-180" max="180" class="slider-num" />
                  </div>
                </div>
                <div class="slider">
                  <label>Distance (px)</label>
                  <div class="slider-row">
                    <input v-model.number="options.uniformLogoShadowDistance" type="range" min="0" max="100" />
                    <input v-model.number="options.uniformLogoShadowDistance" type="number" min="0" max="100" class="slider-num" />
                  </div>
                </div>
                <div class="slider">
                  <label>Size / Blur (px)</label>
                  <div class="slider-row">
                    <input v-model.number="options.uniformLogoShadowSize" type="range" min="0" max="250" />
                    <input v-model.number="options.uniformLogoShadowSize" type="number" min="0" max="250" class="slider-num" />
                  </div>
                </div>
              </template>
            </template>

            <!-- Position & Size only applies to non-Uniform-Logo templates now — Uniform Logo
                 geometry moved to its own "Bounding Box" section, since that box is shared
                 between Logo and Custom Text, not a Logo-only concept. -->
              <template v-if="!isUniformLogo">
                <div class="sub-section-title">Position &amp; Size</div>
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
              </template>
          </div>
        </div>

        <!-- 4. Custom Text -->
        <div class="acc-section">
          <button class="acc-header" @click="toggleSection('text')">
            <span>Custom Text</span>
            <svg class="acc-chevron" :class="{ open: sectionOpen.text }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <div v-show="sectionOpen.text" class="acc-body">
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
          </div>
        </div>

        <!-- 5. Bounding Box (Uniform Logo templates only) -->
        <div v-if="isUniformLogo" class="acc-section">
          <button class="acc-header" @click="toggleSection('boundingBox')">
            <span>Bounding Box</span>
            <svg class="acc-chevron" :class="{ open: sectionOpen.boundingBox }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <div v-show="sectionOpen.boundingBox" class="acc-body">
            <div class="field-hint" style="margin-bottom: 12px;">
              This box defines where the logo sits. Custom Text can optionally fit itself inside
              the same box instead of overflowing — handy when Logo Mode is "No Logo" and text
              takes its place.
            </div>
            <label class="checkbox-label">
              <input type="checkbox" v-model="showBoundingBox" />
              <span>Show bounding box on preview</span>
            </label>
            <label class="checkbox-label">
              <input type="checkbox" v-model="textBboxEnabled" />
              <span>Restrict Custom Text to this box</span>
            </label>
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
                <input v-model.number="options.uniformLogoMaxH" type="range" min="50" max="2800" />
                <input v-model.number="options.uniformLogoMaxH" type="number" min="50" max="2800" class="slider-num" />
              </div>
            </div>
            <div class="slider">
              <label>Box X %</label>
              <div class="slider-row">
                <input v-model.number="options.uniformLogoOffsetX" type="range" min="0" max="100" />
                <input v-model.number="options.uniformLogoOffsetX" type="number" min="0" max="100" class="slider-num" />
              </div>
            </div>
            <div class="slider">
              <label>Box Y %</label>
              <div class="slider-row">
                <input v-model.number="options.uniformLogoOffsetY" type="range" min="0" max="100" />
                <input v-model.number="options.uniformLogoOffsetY" type="number" min="0" max="100" class="slider-num" />
              </div>
            </div>
            <div class="slider">
              <label>Horizontal Align</label>
              <div class="align-btn-group">
                <button
                  v-for="opt in (['left', 'center', 'right'] as const)"
                  :key="opt"
                  :class="['align-btn', { active: options.uniformLogoHAlign === opt }]"
                  @click="options.uniformLogoHAlign = opt"
                >{{ opt }}</button>
              </div>
            </div>
            <div class="slider">
              <label>Vertical Align</label>
              <div class="align-btn-group">
                <button
                  v-for="opt in (['top', 'center', 'bottom'] as const)"
                  :key="opt"
                  :class="['align-btn', { active: options.uniformLogoVAlign === opt }]"
                  @click="options.uniformLogoVAlign = opt"
                >{{ opt }}</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 6. Overlay & Border -->
        <div class="acc-section">
          <button class="acc-header" @click="toggleSection('overlay')">
            <span>Overlay &amp; Border</span>
            <svg class="acc-chevron" :class="{ open: sectionOpen.overlay }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <div v-show="sectionOpen.overlay" class="acc-body">
            <div class="slider">
              <label class="checkbox-label">
                <input v-model="options.borderEnabled" type="checkbox" />
                Border Enabled
              </label>
            </div>
            <div v-if="options.borderEnabled" class="slider">
              <label>Border Thickness (px)</label>
              <div class="slider-row">
                <input v-model.number="options.borderThickness" type="range" min="0" max="60" />
                <input v-model.number="options.borderThickness" type="number" min="0" max="60" class="slider-num" />
              </div>
            </div>
            <div v-if="options.borderEnabled" class="slider">
              <label>Border Color</label>
              <input v-model="options.borderColor" type="color" />
            </div>

            <div v-if="overlayConfigs.length > 0" class="slider">
              <label>Overlay Configs</label>
              <div class="overlay-config-checkboxes">
                <div v-for="cfg in overlayConfigs" :key="cfg.id" class="overlay-config-item">
                  <label class="checkbox-label">
                    <input
                      type="checkbox"
                      :checked="options.overlayConfigIds.includes(cfg.id)"
                      @change="toggleOverlayConfig(cfg.id)"
                    />
                    {{ cfg.name }}
                  </label>
                  <label v-if="options.overlayConfigIds.includes(cfg.id)" class="checkbox-label overlay-config-below-row">
                    <input
                      type="checkbox"
                      :checked="options.overlayConfigIdsBelow.includes(cfg.id)"
                      @change="toggleOverlayConfigBelow(cfg.id)"
                    />
                    Place below logo &amp; text
                  </label>
                </div>
              </div>
            </div>

            <div class="sub-section-title" style="margin-top: 12px">Labels to Remove</div>
            <div class="label-chips">
              <label v-for="l in labels" :key="l" class="chip">
                <input type="checkbox" :checked="selectedLabels.has(l)" @change="toggleLabel(l)" />
                <span>{{ l }}</span>
              </label>
              <p v-if="!labels.length" class="muted-text">No labels found</p>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="acc-actions">
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

          <div class="preview-label" style="margin-top: 14px;">
            Current Plex Logo
            <button class="refresh-btn" title="Fetch logo from Plex" @click="fetchExistingLogo(true)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
          </div>
          <div class="existing-logo-area">
            <img v-if="existingLogo" :key="logoRefreshKey" :src="existingLogo" alt="Existing logo" class="existing-logo-img" />
            <div v-else class="empty-preview small">No logo</div>
          </div>
        </div>

        <div class="preview-main">
          <div class="preview-label">
            Preview
            <span v-if="loading" class="status-badge">Rendering...</span>
            <span v-else-if="lastPreview" class="status-badge success">Rendered</span>
            <div class="preview-actions float-right">
              <label class="send-logo-toggle" title="Also send the selected logo to Plex">
                <input type="checkbox" v-model="sendLogo" />
                <span>Send logo</span>
              </label>
              <button title="Send Logo to Plex" class="btn-send-logo btn-inline" :disabled="logoSending || !logoUrl" @click="doSendLogoOnly">
                <svg v-if="logoSending" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                <span class="btn-label">{{ logoSending ? 'Sending...' : 'Send Logo' }}</span>
              </button>
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

            <!-- Bounding Box (Uniform Logo template) — same box for logo placement and text-bbox mode -->
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

/* Custom poster/logo upload zone */
.poster-upload-zone, .logo-upload-zone {
  position: relative;
  border: 1.5px dashed var(--border, #2a2f3e);
  border-radius: 8px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  overflow: hidden;
  margin-bottom: 6px;
}
.poster-upload-zone:hover, .poster-upload-zone.drag-over,
.logo-upload-zone:hover, .logo-upload-zone.drag-over {
  border-color: rgba(61, 214, 183, 0.6);
  background: rgba(61, 214, 183, 0.05);
}
.poster-upload-zone.has-upload, .logo-upload-zone.has-upload {
  height: 130px;
  cursor: default;
}
.upload-preview {
  height: 100%;
  width: auto;
  object-fit: contain;
  display: block;
}
.upload-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.15s;
}
.poster-upload-zone.has-upload:hover .upload-overlay,
.logo-upload-zone.has-upload:hover .upload-overlay { opacity: 1; }
.upload-reselect, .upload-replace, .upload-remove {
  border: 1px solid rgba(255,255,255,0.3);
  background: rgba(255,255,255,0.15);
  color: #fff;
  border-radius: 5px;
  padding: 4px 8px;
  font-size: 0.75rem;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;
}
.upload-reselect:hover, .upload-replace:hover { background: rgba(61,214,183,0.35); }
.upload-reselect.active { border-color: #3dd6b7; color: #3dd6b7; }
.upload-remove { border-color: rgba(255,100,100,0.4); }
.upload-remove:hover { background: rgba(255,100,100,0.3); }
.upload-prompt {
  color: var(--text-secondary, #9aa4b5);
  font-size: 0.82rem;
  text-align: center;
  pointer-events: none;
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

.slider {
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

.align-btn-group {
  display: flex;
  gap: 6px;
}

.align-btn {
  flex: 1;
  padding: 5px 0;
  font-size: 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-secondary);
  cursor: pointer;
  text-transform: capitalize;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.align-btn.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
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

.overlay-config-below-row {
  margin-left: 22px;
  opacity: 0.85;
  font-size: 0.9em;
}

.field-hint {
  font-size: 11px;
  color: rgba(61, 214, 183, 0.7);
  font-style: italic;
  line-height: 1.4;
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

.send-logo-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: #a8b3cf;
  cursor: pointer;
  user-select: none;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
  transition: all 0.15s;
}
.send-logo-toggle:has(input:checked) {
  color: #eef2ff;
  border-color: rgba(61, 214, 183, 0.35);
}
.send-logo-toggle input {
  margin: 0;
  accent-color: var(--accent, #3dd6b7);
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
  justify-content: flex-end;
}
.btn-inline {
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  white-space: nowrap;
}

.btn-send-logo {
  background: rgba(61, 214, 183, 0.12);
  color: #3dd6b7;
  border: 1px solid rgba(61, 214, 183, 0.3);
  cursor: pointer;
  transition: all 0.15s;
}
.btn-send-logo:hover:not(:disabled) {
  background: rgba(61, 214, 183, 0.22);
  border-color: rgba(61, 214, 183, 0.55);
}
.btn-send-logo:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn-send-logo .spin {
  animation: spin-inline 0.9s linear infinite;
}
@keyframes spin-inline {
  to { transform: rotate(360deg); }
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

.existing-logo-area {
  width: 160px;
  background: #0a0b12;
  border-radius: 6px;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  box-sizing: border-box;
}

.existing-logo-img {
  width: 100%;
  max-height: 72px;
  object-fit: contain;
  display: block;
}

.empty-preview.small {
  font-size: 11px;
  padding: 8px;
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

/* Accordion */
.acc-section {
  border-bottom: 1px solid var(--border);
}

.acc-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 0;
  background: none;
  border: none;
  color: #a8b8e0;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.4px;
  text-transform: uppercase;
  cursor: pointer;
  text-align: left;
  transition: color 0.15s;
}

.acc-header:hover {
  color: var(--accent);
}

.acc-header:hover .acc-chevron {
  color: var(--accent);
}

.acc-chevron {
  flex-shrink: 0;
  color: var(--muted);
  transition: transform 0.2s ease, color 0.15s;
}

.acc-chevron.open {
  transform: rotate(180deg);
}

.acc-body {
  padding-bottom: 18px;
}

.acc-actions {
  padding: 16px 0 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sub-section-title {
  font-size: 10px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 10px;
  margin-top: 14px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

/* Mobile responsive styles */
@media (max-width: 1200px) {
  .editor-shell {
    grid-template-columns: 380px 1fr;
  }

  .btn-inline {
    min-width: 80px;
    padding: 7px 10px;
    font-size: 12px;
  }
}

@media (max-width: 900px) {
  .editor-shell {
    grid-template-columns: 1fr;
    height: auto;
    min-height: calc(100vh - 60px);
  }

  .controls-sidebar {
    border-right: none;
    border-bottom: 1px solid var(--border);
    max-height: none;
  }

  .controls-scroll {
    max-height: none;
    padding-bottom: 80px;
  }

  .preview-pane {
    padding: 16px;
    min-height: 400px;
  }

  .preview-inner {
    flex-direction: column;
    align-items: center;
  }

  .preview-existing {
    display: none;
  }

  .preview-main {
    max-width: 100%;
    width: 100%;
  }

  .preview-label {
    flex-wrap: wrap;
    gap: 8px;
  }

  .preview-actions {
    width: 100%;
    justify-content: center;
    margin-top: 8px;
  }

  .btn-inline {
    flex: 1;
    max-width: 160px;
  }

  .preview-container {
    min-height: 350px;
  }

  .preview-img {
    max-height: 60vh;
  }

  .thumb-strip {
    -webkit-overflow-scrolling: touch;
  }

  .pane-header h2 {
    font-size: 16px;
  }

  .section-title {
    font-size: 13px;
  }
}

@media (max-width: 600px) {
  .editor-shell {
    min-height: auto;
  }

  .pane-header {
    padding: 12px 14px;
  }

  .kicker {
    font-size: 10px;
  }

  .pane-header h2 {
    font-size: 14px;
  }

  .controls-scroll {
    padding: 0 14px 60px;
  }

  .section {
    margin-top: 12px;
  }

  .field-label {
    font-size: 12px;
    margin-bottom: 10px;
  }

  .field-label select,
  .field-label input {
    padding: 6px;
    font-size: 12px;
  }

  .divider {
    margin: 14px 0;
  }

  .thumb-strip {
    gap: 4px;
    padding: 4px 0;
  }

  .poster-thumb {
    width: 60px;
    height: 90px;
  }

  .logo-thumb {
    min-width: 80px;
    max-width: 120px;
    height: 55px;
    padding: 6px;
  }

  .source-badge {
    font-size: 8px;
    padding: 1px 4px;
  }

  .inline-controls {
    flex-wrap: wrap;
    gap: 8px;
  }

  .inline-field {
    font-size: 11px;
  }

  .inline-field select {
    padding: 4px 6px;
    font-size: 11px;
  }

  .slider label {
    font-size: 11px;
  }

  .slider-row {
    grid-template-columns: 1fr 55px;
    gap: 6px;
  }

  .slider-num {
    padding: 4px;
    font-size: 11px;
  }

  .uniform-section {
    padding: 10px;
  }

  .uniform-title {
    font-size: 12px;
    margin-bottom: 10px;
  }

  .label-chips {
    gap: 4px;
  }

  .chip {
    padding: 4px 8px;
    font-size: 11px;
  }

  .btn-primary {
    padding: 8px;
    font-size: 13px;
  }

  .preset-row {
    flex-wrap: wrap;
    gap: 6px;
  }

  .save-preset-btn {
    min-width: 38px;
    height: 34px;
    padding: 8px 10px;
  }

  .reload-preset-btn {
    width: 34px;
    height: 34px;
  }

  .new-preset-input {
    padding: 8px;
    font-size: 12px;
  }

  .preview-pane {
    padding: 12px;
    min-height: 320px;
  }

  .preview-container {
    min-height: 280px;
    border-radius: 10px;
  }

  .preview-img {
    max-height: 50vh;
    border-radius: 8px;
  }

  .preview-label {
    font-size: 11px;
  }

  .preview-actions {
    gap: 6px;
    margin-top: 6px;
  }

  .btn-inline {
    padding: 8px;
    font-size: 12px;
    border-radius: 8px;
  }

  .btn-label {
    display: none;
  }

  .empty-preview {
    padding: 24px;
  }

  .empty-preview.large {
    min-height: 250px;
  }

  .empty-preview svg {
    width: 48px;
    height: 48px;
  }

  .empty-preview p {
    font-size: 13px;
  }

  .loading-overlay p {
    font-size: 14px;
  }

  .spinner {
    width: 36px;
    height: 36px;
    border-width: 3px;
  }
}
</style>
