<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, type Ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

const apiBase = getApiBase()

// --- Types ---

interface OverlayElement {
  type: string
  position_x: number
  position_y: number
  width?: number
  height?: number
  max_width?: number
  max_height?: number
  scale?: number
  anchor?: string
  asset_id?: string
  text?: string
  font_family?: string
  font_size?: number
  font_color?: string
  label_name?: string
  show_if_label?: string
  hide_if_label?: string
  metadata_field?: string
  badge_modes?: Record<string, string>
  badge_assets?: Record<string, string>
  badge_texts?: Record<string, string>
  badge_scales?: Record<string, number>
  badge_anchors?: Record<string, string>
  text_align?: string
}

interface OverlayConfig {
  id: string
  name: string
  elements: OverlayElement[]
  created_at?: string
  updated_at?: string
}

interface OverlayAsset {
  id: string
  name: string
  file_path: string
  file_type: string
  width: number
  height: number
  created_at?: string
}

interface SimpleMovie {
  key: string
  title: string
}

// --- Predefined badge values ---

const RESOLUTION_VALUES = ['4k', '1080', '720', '480', 'sd']
const VIDEO_CODEC_VALUES = ['h264', 'hevc', 'av1', 'mpeg4', 'vc1', 'vp9']
const CODEC_VALUES = ['atmos', 'dts-x', 'dts-hd ma', 'dts', 'truehd', 'aac', 'ac3', 'flac', 'eac3']
const AUDIO_CHANNELS_VALUES = ['2', '6', '8']
const AUDIO_LANGUAGE_VALUES = ['en', 'es', 'fr', 'de', 'ja', 'ko', 'zh', 'it', 'pt', 'ru']
const EDITION_VALUES = ['theatrical', 'extended', "director's cut", 'unrated', 'imax']

const METADATA_FIELD_VALUES: Record<string, string[]> = {
  video_resolution: RESOLUTION_VALUES,
  video_codec: VIDEO_CODEC_VALUES,
  audio_codec: CODEC_VALUES,
  audio_channels: AUDIO_CHANNELS_VALUES,
  audio_language: AUDIO_LANGUAGE_VALUES,
  edition: EDITION_VALUES,
}

const getValuesForField = (field: string): string[] => {
  return METADATA_FIELD_VALUES[field] || RESOLUTION_VALUES
}

// --- State ---

const configs = ref<OverlayConfig[]>([])
const assets = ref<OverlayAsset[]>([])
const fonts = ref<string[]>([])
const loading = ref(false)
const selectedConfig = ref<OverlayConfig | null>(null)
const showEditor = ref(false)
const showAssetUpload = ref(false)
const hoveredElementIdx = ref<number | null>(null)

// Preview canvas
const previewCanvas = ref<HTMLCanvasElement | null>(null)
const PREVIEW_W = 300
const PREVIEW_H = 450
const assetImageCache = ref<Record<string, HTMLImageElement>>({})

// Drag state
const dragEnabled = ref(false)
const draggingIdx = ref<number | null>(null)

// Poster search state
const movies = ref<SimpleMovie[]>([])
const moviesLoaded = ref(false)
const movieSearchTerm = ref('')
const showMovieSearch = ref(false)
const selectedMovie = ref<SimpleMovie | null>(null)
const posterBgImage = ref<HTMLImageElement | null>(null)
const posterLoading = ref(false)

const movieSearchResults = computed(() => {
  const q = movieSearchTerm.value.trim().toLowerCase()
  if (!q) return movies.value.slice(0, 30)
  return movies.value.filter(m => m.title.toLowerCase().includes(q)).slice(0, 30)
})

// Preview value switcher
const previewResolution = ref('4k')
const previewVideoCodec = ref('hevc')
const previewCodec = ref('atmos')
const previewAudioChannels = ref('6')
const previewAudioLanguage = ref('en')
const previewEdition = ref('theatrical')

const previewMetadataValues: Record<string, Ref<string>> = {
  video_resolution: previewResolution,
  video_codec: previewVideoCodec,
  audio_codec: previewCodec,
  audio_channels: previewAudioChannels,
  audio_language: previewAudioLanguage,
  edition: previewEdition,
}

// Asset upload state
const uploadFileName = ref('')
const uploadFile = ref<File | null>(null)
const uploading = ref(false)

// --- API functions ---

const loadConfigs = async () => {
  loading.value = true
  try {
    const res = await fetch(`${apiBase}/api/overlay-configs`)
    if (res.ok) {
      const data = await res.json()
      configs.value = data.configs || []
    }
  } catch (e) {
    console.error('Failed to load overlay configs:', e)
  } finally {
    loading.value = false
  }
}

const loadAssets = async () => {
  try {
    const res = await fetch(`${apiBase}/api/overlay-assets`)
    if (res.ok) {
      const data = await res.json()
      assets.value = data.assets || []
    }
  } catch (e) {
    console.error('Failed to load overlay assets:', e)
  }
}

const loadFonts = async () => {
  try {
    const res = await fetch(`${apiBase}/api/fonts`)
    if (res.ok) {
      const data = await res.json()
      fonts.value = data.fonts || []
    }
  } catch (e) {
    console.error('Failed to load fonts:', e)
  }
}

const loadMovies = async () => {
  if (moviesLoaded.value) return
  try {
    const res = await fetch(`${apiBase}/api/movies`)
    if (res.ok) {
      const data = await res.json()
      movies.value = (Array.isArray(data) ? data : []).map((m: any) => ({ key: m.key, title: m.title }))
      moviesLoaded.value = true
    }
  } catch (e) {
    console.error('Failed to load movies:', e)
  }
}

const createNewConfig = () => {
  selectedConfig.value = {
    id: `overlay-${Date.now()}`,
    name: 'New Overlay Config',
    elements: []
  }
  showEditor.value = true
}

const editConfig = (config: OverlayConfig) => {
  selectedConfig.value = JSON.parse(JSON.stringify(config))
  showEditor.value = true
}

const saveConfig = async () => {
  if (!selectedConfig.value) return
  try {
    const res = await fetch(`${apiBase}/api/overlay-configs/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(selectedConfig.value)
    })
    if (res.ok) {
      await loadConfigs()
      showEditor.value = false
      selectedConfig.value = null
    } else {
      alert('Failed to save overlay config')
    }
  } catch (e) {
    console.error('Failed to save overlay config:', e)
    alert('Failed to save overlay config')
  }
}

const deleteConfig = async (configId: string) => {
  if (!confirm('Delete this overlay configuration? This will unlink it from any presets using it.')) return
  try {
    const res = await fetch(`${apiBase}/api/overlay-configs/${configId}`, { method: 'DELETE' })
    if (res.ok) {
      await loadConfigs()
    } else {
      alert('Failed to delete overlay config')
    }
  } catch (e) {
    console.error('Failed to delete overlay config:', e)
    alert('Failed to delete overlay config')
  }
}

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files[0]) {
    uploadFile.value = target.files[0]
  }
}

const uploadAsset = async () => {
  if (!uploadFile.value || !uploadFileName.value.trim()) {
    alert('Please provide a name and select a file')
    return
  }
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('name', uploadFileName.value.trim())
    formData.append('file', uploadFile.value)
    const res = await fetch(`${apiBase}/api/overlay-assets/upload`, {
      method: 'POST',
      body: formData
    })
    if (res.ok) {
      await loadAssets()
      showAssetUpload.value = false
      uploadFileName.value = ''
      uploadFile.value = null
    } else {
      const error = await res.json().catch(() => ({ detail: 'Unknown error' }))
      const msg = typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail)
      alert(msg || 'Failed to upload asset')
    }
  } catch (e) {
    console.error('Failed to upload asset:', e)
    alert('Failed to upload asset')
  } finally {
    uploading.value = false
  }
}

const rescanAssets = async () => {
  try {
    const res = await fetch(`${apiBase}/api/overlay-assets/rescan`, { method: 'POST' })
    if (res.ok) {
      const data = await res.json()
      await loadAssets()
      if (data.added > 0) {
        alert(`Found ${data.added} new asset${data.added > 1 ? 's' : ''}: ${data.names.join(', ')}`)
      } else {
        alert('No new assets found — all files in the assets folder are already registered.')
      }
    } else {
      alert('Failed to rescan assets folder')
    }
  } catch (e) {
    console.error('Failed to rescan assets:', e)
    alert('Failed to rescan assets folder')
  }
}

const deleteAsset = async (assetId: string) => {
  if (!confirm('Delete this overlay asset?')) return
  try {
    const res = await fetch(`${apiBase}/api/overlay-assets/${assetId}`, { method: 'DELETE' })
    if (res.ok) {
      await loadAssets()
    } else {
      alert('Failed to delete asset')
    }
  } catch (e) {
    console.error('Failed to delete asset:', e)
    alert('Failed to delete asset')
  }
}

const getAssetUrl = (asset: OverlayAsset) => `${apiBase}/api/overlay-assets/${asset.id}/file`
const getAssetUrlById = (assetId: string) => `${apiBase}/api/overlay-assets/${assetId}/file`

// --- Element management ---

const addElement = (type: string) => {
  if (!selectedConfig.value) return
  const defaults: Partial<OverlayElement> = {}

  if (type === 'video_badge') {
    defaults.metadata_field = 'video_resolution'
    defaults.badge_modes = {}
    defaults.badge_assets = {}
    defaults.badge_texts = {}
    defaults.font_size = 40
    defaults.font_color = '#FFFFFF'
    defaults.font_family = 'Arial'
  } else if (type === 'audio_badge') {
    defaults.metadata_field = 'audio_codec'
    defaults.badge_modes = {}
    defaults.badge_assets = {}
    defaults.badge_texts = {}
    defaults.font_size = 30
    defaults.font_color = '#FFFFFF'
    defaults.font_family = 'Arial'
  } else if (type === 'edition_badge') {
    defaults.metadata_field = 'edition'
    defaults.badge_modes = {}
    defaults.badge_assets = {}
    defaults.badge_texts = {}
    defaults.font_size = 30
    defaults.font_color = '#FFFFFF'
    defaults.font_family = 'Arial'
  } else if (type === 'text_label') {
    defaults.font_size = 40
    defaults.font_color = '#FFFFFF'
    defaults.font_family = 'Arial'
    defaults.text = ''
  }

  selectedConfig.value.elements.push({
    type,
    position_x: 0.5,
    position_y: 0.5,
    ...defaults
  })
}

const removeElement = (index: number) => {
  if (!selectedConfig.value) return
  selectedConfig.value.elements.splice(index, 1)
}

const elementTypeLabel = (type: string): string => {
  const labels: Record<string, string> = {
    video_badge: 'Video Badge',
    audio_badge: 'Audio Badge',
    edition_badge: 'Edition Badge',
    custom_image: 'Custom Image',
    text_label: 'Text Label',
    // Legacy types
    resolution_badge: 'Resolution Badge',
    codec_badge: 'Codec Badge',
    label_badge: 'Label Badge',
  }
  return labels[type] || type
}

const elementTypeColor = (type: string): string => {
  const colors: Record<string, string> = {
    video_badge: '#60a5fa',
    audio_badge: '#a78bfa',
    edition_badge: '#f59e0b',
    custom_image: '#34d399',
    text_label: '#fbbf24',
    // Legacy types
    resolution_badge: '#60a5fa',
    codec_badge: '#a78bfa',
    label_badge: '#f472b6',
  }
  return colors[type] || '#60a5fa'
}

// Badge mode/asset helpers
const getBadgeMode = (element: OverlayElement, value: string): string => {
  return element.badge_modes?.[value] ?? 'text'
}

const setBadgeMode = (element: OverlayElement, value: string, mode: string) => {
  if (!element.badge_modes) element.badge_modes = {}
  element.badge_modes[value] = mode
  // Clear image-specific overrides when switching away from image
  if (mode !== 'image') {
    if (element.badge_assets?.[value]) delete element.badge_assets[value]
    if (element.badge_scales?.[value] != null) delete element.badge_scales[value]
    if (element.badge_anchors?.[value]) delete element.badge_anchors[value]
  }
}

const setBadgeAsset = (element: OverlayElement, value: string, assetId: string | undefined) => {
  if (!element.badge_assets) element.badge_assets = {}
  if (assetId) {
    element.badge_assets[value] = assetId
  } else {
    delete element.badge_assets[value]
  }
}

const getBadgeAsset = (element: OverlayElement, value: string): string | undefined => {
  return element.badge_assets?.[value]
}

const getBadgeText = (element: OverlayElement, value: string): string => {
  return element.badge_texts?.[value] ?? ''
}

const setBadgeText = (element: OverlayElement, value: string, text: string) => {
  if (!element.badge_texts) element.badge_texts = {}
  if (text) {
    element.badge_texts[value] = text
  } else {
    delete element.badge_texts[value]
  }
}

const getBadgeScale = (element: OverlayElement, value: string): number | undefined => {
  return element.badge_scales?.[value]
}
const setBadgeScale = (element: OverlayElement, value: string, v: string) => {
  if (!element.badge_scales) element.badge_scales = {}
  const n = parseFloat(v)
  if (!isNaN(n) && n > 0) {
    element.badge_scales[value] = n
  } else {
    delete element.badge_scales[value]
  }
}

const getBadgeAnchor = (element: OverlayElement, value: string): string => {
  return element.badge_anchors?.[value] ?? 'center'
}
const setBadgeAnchor = (element: OverlayElement, value: string, anchor: string) => {
  if (!element.badge_anchors) element.badge_anchors = {}
  element.badge_anchors[value] = anchor
}

const hasBadgeTextMode = (element: OverlayElement): boolean => {
  // Determine all possible values for this element's field
  const field = element.type === 'edition_badge'
    ? 'edition'
    : (element.metadata_field || 'video_resolution')
  const allValues = getValuesForField(field)
  // Return true if any value's effective mode is "text" (unset defaults to "text")
  return allValues.some(v => (element.badge_modes?.[v] ?? 'text') === 'text')
}

// --- Poster search ---

const openMovieSearch = async () => {
  await loadMovies()
  movieSearchTerm.value = ''
  showMovieSearch.value = true
}

const selectMovie = async (movie: SimpleMovie) => {
  showMovieSearch.value = false
  selectedMovie.value = movie
  posterLoading.value = true
  try {
    const url = `${apiBase}/api/movie/${movie.key}/poster?raw=1`
    const img = new Image()
    img.crossOrigin = 'anonymous'
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('Failed to load poster'))
      img.src = url
    })
    posterBgImage.value = img
    nextTick(renderPreview)
  } catch (e) {
    console.error('Failed to load poster:', e)
    posterBgImage.value = null
  } finally {
    posterLoading.value = false
  }
}

const clearPoster = () => {
  selectedMovie.value = null
  posterBgImage.value = null
  nextTick(renderPreview)
}

// --- Canvas drag ---

const getCanvasMousePos = (e: MouseEvent): { x: number; y: number } | null => {
  const canvas = previewCanvas.value
  if (!canvas) return null
  const rect = canvas.getBoundingClientRect()
  return {
    x: (e.clientX - rect.left) / rect.width,
    y: (e.clientY - rect.top) / rect.height
  }
}

const hitTestElement = (normX: number, normY: number): number | null => {
  if (!selectedConfig.value) return null
  const hitRadius = 25 / PREVIEW_W // ~25px radius in canvas space
  // Iterate in reverse so topmost element (last drawn) is hit first
  for (let i = selectedConfig.value.elements.length - 1; i >= 0; i--) {
    const el = selectedConfig.value.elements[i]
    if (!el) continue
    const dx = normX - el.position_x
    const dy = normY - el.position_y
    if (Math.sqrt(dx * dx + dy * dy) < hitRadius) return i
  }
  return null
}

const onCanvasMouseDown = (e: MouseEvent) => {
  if (!dragEnabled.value || !selectedConfig.value) return
  const pos = getCanvasMousePos(e)
  if (!pos) return
  const idx = hitTestElement(pos.x, pos.y)
  if (idx !== null) {
    draggingIdx.value = idx
    hoveredElementIdx.value = idx
    e.preventDefault()
  }
}

const onCanvasMouseMove = (e: MouseEvent) => {
  if (!dragEnabled.value || !selectedConfig.value) return

  const pos = getCanvasMousePos(e)
  if (!pos) return

  if (draggingIdx.value !== null) {
    const el = selectedConfig.value.elements[draggingIdx.value]
    if (el) {
      el.position_x = Math.round(Math.max(0, Math.min(1, pos.x)) * 1000) / 1000
      el.position_y = Math.round(Math.max(0, Math.min(1, pos.y)) * 1000) / 1000
    }
    e.preventDefault()
  } else {
    // Hover feedback
    const idx = hitTestElement(pos.x, pos.y)
    hoveredElementIdx.value = idx
  }
}

const onCanvasMouseUp = () => {
  draggingIdx.value = null
}

// Touch support
const getTouchPos = (e: TouchEvent): { x: number; y: number } | null => {
  const canvas = previewCanvas.value
  if (!canvas || !e.touches.length) return null
  const rect = canvas.getBoundingClientRect()
  const touch = e.touches[0]
  if (!touch) return null
  return {
    x: (touch.clientX - rect.left) / rect.width,
    y: (touch.clientY - rect.top) / rect.height
  }
}

const onCanvasTouchStart = (e: TouchEvent) => {
  if (!dragEnabled.value || !selectedConfig.value) return
  const pos = getTouchPos(e)
  if (!pos) return
  const idx = hitTestElement(pos.x, pos.y)
  if (idx !== null) {
    draggingIdx.value = idx
    hoveredElementIdx.value = idx
    e.preventDefault()
  }
}

const onCanvasTouchMove = (e: TouchEvent) => {
  if (!dragEnabled.value || draggingIdx.value === null || !selectedConfig.value) return
  const pos = getTouchPos(e)
  if (!pos) return
  const el = selectedConfig.value.elements[draggingIdx.value]
  if (el) {
    el.position_x = Math.round(Math.max(0, Math.min(1, pos.x)) * 1000) / 1000
    el.position_y = Math.round(Math.max(0, Math.min(1, pos.y)) * 1000) / 1000
  }
  e.preventDefault()
}

const onCanvasTouchEnd = () => {
  draggingIdx.value = null
}

// --- Preview canvas rendering ---

const loadAssetImage = (assetId: string): Promise<HTMLImageElement> => {
  return new Promise((resolve, reject) => {
    if (assetImageCache.value[assetId]) {
      resolve(assetImageCache.value[assetId])
      return
    }
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      assetImageCache.value[assetId] = img
      resolve(img)
    }
    img.onerror = reject
    img.src = getAssetUrlById(assetId)
  })
}

const renderPreview = async () => {
  const canvas = previewCanvas.value
  if (!canvas || !selectedConfig.value) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  canvas.width = PREVIEW_W * dpr
  canvas.height = PREVIEW_H * dpr
  ctx.scale(dpr, dpr)

  // Background: poster image or gradient
  if (posterBgImage.value) {
    const img = posterBgImage.value
    // Cover-fill the canvas maintaining aspect ratio
    const imgAspect = img.width / img.height
    const canvasAspect = PREVIEW_W / PREVIEW_H
    let sx = 0, sy = 0, sw = img.width, sh = img.height
    if (imgAspect > canvasAspect) {
      sw = img.height * canvasAspect
      sx = (img.width - sw) / 2
    } else {
      sh = img.width / canvasAspect
      sy = (img.height - sh) / 2
    }
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, PREVIEW_W, PREVIEW_H)
  } else {
    const bgGrad = ctx.createLinearGradient(0, 0, 0, PREVIEW_H)
    bgGrad.addColorStop(0, '#1a1a2e')
    bgGrad.addColorStop(0.5, '#16162a')
    bgGrad.addColorStop(1, '#0f0f1a')
    ctx.fillStyle = bgGrad
    ctx.fillRect(0, 0, PREVIEW_W, PREVIEW_H)
  }

  // Poster border
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)'
  ctx.lineWidth = 1
  ctx.strokeRect(0.5, 0.5, PREVIEW_W - 1, PREVIEW_H - 1)

  // Grid guides (only without poster bg)
  if (!posterBgImage.value) {
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)'
    ctx.setLineDash([4, 4])
    ctx.beginPath()
    ctx.moveTo(PREVIEW_W / 2, 0)
    ctx.lineTo(PREVIEW_W / 2, PREVIEW_H)
    ctx.moveTo(0, PREVIEW_H / 2)
    ctx.lineTo(PREVIEW_W, PREVIEW_H / 2)
    ctx.stroke()
    ctx.setLineDash([])

    ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)'
    for (let i = 1; i < 4; i++) {
      ctx.beginPath()
      ctx.moveTo(PREVIEW_W * (i / 4), 0)
      ctx.lineTo(PREVIEW_W * (i / 4), PREVIEW_H)
      ctx.moveTo(0, PREVIEW_H * (i / 4))
      ctx.lineTo(PREVIEW_W, PREVIEW_H * (i / 4))
      ctx.stroke()
    }
  }

  // Render each element
  for (let idx = 0; idx < selectedConfig.value.elements.length; idx++) {
    const el = selectedConfig.value.elements[idx]
    if (!el) continue
    const x = el.position_x * PREVIEW_W
    const y = el.position_y * PREVIEW_H
    const isHovered = hoveredElementIdx.value === idx || draggingIdx.value === idx

    await renderPreviewElement(ctx, el, x, y, idx, isHovered)
  }
}

const renderPreviewElement = async (
  ctx: CanvasRenderingContext2D,
  el: OverlayElement,
  x: number,
  y: number,
  idx: number,
  isHovered: boolean
) => {
  const scale = PREVIEW_W / 2000

  // Badge type rendering config
  const badgeConfig: Record<string, { defaultField: string; defaultFontSize: number; accent: string; accentRgba: string }> = {
    video_badge:      { defaultField: 'video_resolution', defaultFontSize: 40, accent: '#60a5fa', accentRgba: 'rgba(96, 165, 250, 0.2)' },
    resolution_badge: { defaultField: 'video_resolution', defaultFontSize: 40, accent: '#60a5fa', accentRgba: 'rgba(96, 165, 250, 0.2)' },
    audio_badge:      { defaultField: 'audio_codec',      defaultFontSize: 30, accent: '#a78bfa', accentRgba: 'rgba(167, 139, 250, 0.2)' },
    codec_badge:      { defaultField: 'audio_codec',      defaultFontSize: 30, accent: '#a78bfa', accentRgba: 'rgba(167, 139, 250, 0.2)' },
    edition_badge:    { defaultField: 'edition',           defaultFontSize: 30, accent: '#f59e0b', accentRgba: 'rgba(245, 158, 11, 0.2)' },
  }

  const cfg = badgeConfig[el.type]
  if (cfg) {
    const metaField = el.metadata_field || cfg.defaultField
    const fallbackRef = previewMetadataValues[metaField] || previewResolution
    const value = fallbackRef.value
    const mode = el.badge_modes?.[value] ?? 'text'

    if (mode === 'none') {
      ctx.font = 'bold 9px sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = cfg.accentRgba.replace('0.2)', '0.3)')
      ctx.fillText('—', x, y)
      drawElementIndex(ctx, x - 8, y - 6, idx)
      return
    }
    if (mode === 'image') {
      const assetId = el.badge_assets?.[value]
      if (assetId) {
        try {
          const img = await loadAssetImage(assetId)
          // Apply per-value scale/anchor overrides for badge types
          const effectiveEl = {
            ...el,
            scale: el.badge_scales?.[value] ?? el.scale,
            anchor: el.badge_anchors?.[value] ?? el.anchor,
          }
          drawAssetOnCanvas(ctx, img, effectiveEl, x, y, scale, idx, isHovered, cfg.accent)
          return
        } catch { /* fall through to text */ }
      }
    }
    // Text mode (or image fallback)
    const fontSize = Math.max(4, Math.round((el.font_size || cfg.defaultFontSize) * scale))
    const color = el.font_color || cfg.accent
    const displayText = el.badge_texts?.[value] || value.toUpperCase()
    drawBadge(ctx, x, y, displayText, fontSize, color, cfg.accentRgba, idx, isHovered, el.text_align || 'center')
  } else if (el.type === 'custom_image') {
    if (el.asset_id) {
      try {
        const img = await loadAssetImage(el.asset_id)
        drawAssetOnCanvas(ctx, img, el, x, y, scale, idx, isHovered, '#34d399')
        return
      } catch { /* fallback */ }
      drawBadge(ctx, x, y, 'IMG?', 9, '#34d399', 'rgba(52, 211, 153, 0.2)', idx, isHovered)
    } else {
      drawBadge(ctx, x, y, 'IMG', 9, '#34d399', 'rgba(52, 211, 153, 0.15)', idx, isHovered)
    }
  } else if (el.type === 'text_label') {
    const text = el.text || 'Text'
    const fontSize = Math.max(4, Math.round((el.font_size || 40) * scale))
    const color = el.font_color || '#FFFFFF'
    const align = (el.text_align || 'center') as CanvasTextAlign

    ctx.font = `bold ${fontSize}px sans-serif`
    ctx.textAlign = align
    ctx.textBaseline = 'middle'

    if (isHovered) {
      const metrics = ctx.measureText(text)
      const tw = metrics.width + 8
      const th = fontSize + 6
      const hx = align === 'left' ? x - 4 : align === 'right' ? x - tw + 4 : x - tw / 2
      ctx.strokeStyle = '#fbbf24'
      ctx.lineWidth = 1.5
      ctx.strokeRect(hx, y - th / 2, tw, th)
    }

    ctx.fillStyle = 'rgba(0, 0, 0, 0.5)'
    ctx.fillText(text, x + 1, y + 1)
    ctx.fillStyle = color
    ctx.fillText(text, x, y)
    drawElementIndex(ctx, x - 10, y - fontSize / 2 - 4, idx)
  } else if (el.type === 'label_badge') {
    const text = el.label_name || 'LABEL'
    const fontSize = Math.max(4, Math.round((el.font_size || 30) * scale))
    drawBadge(ctx, x, y, text, fontSize, '#f472b6', 'rgba(244, 114, 182, 0.2)', idx, isHovered, el.text_align || 'center')
  }
}

const drawAssetOnCanvas = (
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  el: OverlayElement,
  x: number, y: number,
  scale: number,
  idx: number,
  isHovered: boolean,
  highlightColor: string
) => {
  let drawW = img.width * scale
  let drawH = img.height * scale

  // Apply scale multiplier first (if provided)
  if (el.scale && el.scale > 0) {
    drawW *= el.scale
    drawH *= el.scale
  }

  // Apply percentage-based width/height (relative to canvas)
  if (el.width && el.width > 0) {
    const targetW = PREVIEW_W * el.width
    const r = targetW / drawW
    drawW = targetW
    drawH *= r
  }
  if (el.height && el.height > 0) {
    const targetH = PREVIEW_H * el.height
    const r = targetH / drawH
    drawH = targetH
    drawW *= r
  }

  // Apply max pixel constraints (scaled to preview)
  if (el.max_width) {
    const maxW = el.max_width * scale
    if (drawW > maxW) { drawH *= maxW / drawW; drawW = maxW }
  }
  if (el.max_height) {
    const maxH = el.max_height * scale
    if (drawH > maxH) { drawW *= maxH / drawH; drawH = maxH }
  }

  const maxDim = PREVIEW_W * 0.5
  if (drawW > maxDim || drawH > maxDim) {
    const r = maxDim / Math.max(drawW, drawH)
    drawW *= r; drawH *= r
  }
  drawW = Math.max(drawW, 16)
  drawH = Math.max(drawH, 16)

  // Apply anchor point
  const anchor = el.anchor || 'center'
  const [vPart, hPart] = anchor.includes('-') ? anchor.split('-') : ['center', 'center']
  const hOffset = hPart === 'left' ? 0 : hPart === 'right' ? drawW : drawW / 2
  const vOffset = vPart === 'top' ? 0 : vPart === 'bottom' ? drawH : drawH / 2
  const dx = x - hOffset
  const dy = y - vOffset

  if (isHovered) {
    ctx.strokeStyle = highlightColor
    ctx.lineWidth = 2
    ctx.strokeRect(dx - 2, dy - 2, drawW + 4, drawH + 4)
  }

  ctx.drawImage(img, dx, dy, drawW, drawH)
  drawElementIndex(ctx, dx, dy, idx)
}

const drawBadge = (
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  text: string, fontSize: number,
  borderColor: string, bgColor: string,
  idx: number, isHovered: boolean,
  align: string = 'center'
) => {
  ctx.font = `bold ${fontSize}px sans-serif`
  ctx.textAlign = align as CanvasTextAlign
  ctx.textBaseline = 'middle'
  const metrics = ctx.measureText(text)
  // Scale padding proportionally to font size so preview matches actual render proportions
  const pw = Math.max(2, Math.round(fontSize * 0.15))
  const ph = Math.max(1, Math.round(fontSize * 0.1))
  const bw = metrics.width + pw * 2
  const bh = fontSize + ph * 2
  // Position badge background based on alignment
  const bx = align === 'left' ? x - pw : align === 'right' ? x - bw + pw : x - bw / 2
  const by = y - bh / 2

  ctx.fillStyle = bgColor
  ctx.beginPath()
  ctx.roundRect(bx, by, bw, bh, Math.max(1, Math.round(fontSize * 0.1)))
  ctx.fill()

  ctx.strokeStyle = isHovered ? '#fff' : borderColor
  ctx.lineWidth = isHovered ? 1.5 : 1
  ctx.beginPath()
  ctx.roundRect(bx, by, bw, bh, Math.max(1, Math.round(fontSize * 0.1)))
  ctx.stroke()

  ctx.fillStyle = borderColor
  ctx.fillText(text, x, y)
  drawElementIndex(ctx, bx, by, idx)
}

const drawElementIndex = (ctx: CanvasRenderingContext2D, x: number, y: number, idx: number) => {
  ctx.font = 'bold 7px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  const lx = x - 2, ly = y - 2
  ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'
  ctx.beginPath()
  ctx.arc(lx, ly, 6, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = '#fff'
  ctx.fillText(`${idx + 1}`, lx, ly)
}

// --- Watchers ---

watch(
  () => selectedConfig.value ? JSON.stringify(selectedConfig.value.elements) : '',
  () => { nextTick(renderPreview) }
)

watch(hoveredElementIdx, () => { nextTick(renderPreview) })
watch(previewResolution, () => { nextTick(renderPreview) })
watch(previewVideoCodec, () => { nextTick(renderPreview) })
watch(previewCodec, () => { nextTick(renderPreview) })
watch(previewAudioChannels, () => { nextTick(renderPreview) })
watch(previewAudioLanguage, () => { nextTick(renderPreview) })
watch(previewEdition, () => { nextTick(renderPreview) })

watch(showEditor, (val) => {
  if (val) {
    nextTick(renderPreview)
  } else {
    // Reset preview state when closing
    dragEnabled.value = false
    draggingIdx.value = null
    selectedMovie.value = null
    posterBgImage.value = null
    showMovieSearch.value = false
  }
})

onMounted(() => {
  loadConfigs()
  loadAssets()
  loadFonts()
})
</script>

<template>
  <div class="overlay-manager">
    <div class="page-header">
      <div>
        <h1>&#x1F9EA; Overlay Configuration <span style="font-size: 0.55em; opacity: 0.6; vertical-align: middle; font-weight: 400;">(experimental)</span></h1>
        <p class="page-subtitle">Create reusable overlay templates with badges, images, and text elements</p>
      </div>
    </div>

    <div class="content-grid">
      <!-- Left: Configs List -->
      <div class="section-card">
        <div class="section-header">
          <h2>Overlay Configurations</h2>
          <button class="btn-primary-sm" @click="createNewConfig">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New Config
          </button>
        </div>

        <div v-if="loading" class="loading">Loading...</div>
        <div v-else-if="configs.length === 0" class="empty-state">
          No overlay configurations yet. Create one to get started!
        </div>
        <div v-else class="configs-list">
          <div v-for="config in configs" :key="config.id" class="config-item">
            <div class="config-info">
              <div class="config-name">{{ config.name }}</div>
              <div class="config-meta">{{ config.elements.length }} element{{ config.elements.length !== 1 ? 's' : '' }}</div>
            </div>
            <div class="config-actions">
              <button class="btn-icon" @click="editConfig(config)" title="Edit">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="btn-icon danger" @click="deleteConfig(config.id)" title="Delete">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: Assets Library -->
      <div class="section-card">
        <div class="section-header">
          <h2>Assets Library</h2>
          <div style="display:flex;gap:0.5rem;">
            <button class="btn-secondary-sm" @click="rescanAssets" title="Scan config/assets/ folder for new files">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
              </svg>
              Rescan
            </button>
            <button class="btn-primary-sm" @click="showAssetUpload = true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              Upload Asset
            </button>
          </div>
        </div>

        <div v-if="assets.length === 0" class="empty-state">
          No assets yet. Upload images or drop files into <code>config/assets/</code> and click Rescan.
        </div>
        <div v-else class="assets-grid">
          <div v-for="asset in assets" :key="asset.id" class="asset-item">
            <img :src="getAssetUrl(asset)" :alt="asset.name" class="asset-thumbnail" />
            <div class="asset-info">
              <div class="asset-name">{{ asset.name }}</div>
              <div class="asset-meta">{{ asset.width }}x{{ asset.height }}</div>
            </div>
            <button class="btn-icon-sm danger" @click="deleteAsset(asset.id)" title="Delete">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Config Editor Modal -->
    <div v-if="showEditor && selectedConfig" class="modal-overlay" @click.self="showEditor = false">
      <div class="editor-modal">
        <div class="editor-header">
          <div>
            <h2>Edit Overlay Configuration</h2>
            <input v-model="selectedConfig.name" class="config-name-input" placeholder="Config name..." />
          </div>
          <button class="btn-close" @click="showEditor = false">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div class="editor-body">
          <div class="editor-columns">
            <!-- Left: Elements -->
            <div class="elements-column">
              <div class="elements-header">
                <h3>Elements</h3>
                <div class="add-element-buttons">
                  <button class="btn-add" @click="addElement('video_badge')">+ Video</button>
                  <button class="btn-add" @click="addElement('audio_badge')">+ Audio</button>
                  <button class="btn-add" @click="addElement('edition_badge')">+ Edition</button>
                  <button class="btn-add" @click="addElement('custom_image')">+ Image</button>
                  <button class="btn-add" @click="addElement('text_label')">+ Text</button>
                </div>
              </div>

              <div v-if="selectedConfig.elements.length === 0" class="empty-elements">
                No elements yet. Add elements using the buttons above.
              </div>

              <div v-else class="elements-list">
                <div
                  v-for="(element, idx) in selectedConfig.elements"
                  :key="idx"
                  class="element-card"
                  :class="{ 'element-hovered': hoveredElementIdx === idx }"
                  @mouseenter="hoveredElementIdx = idx"
                  @mouseleave="hoveredElementIdx = null"
                >
                  <div class="element-header">
                    <div class="element-header-left">
                      <span class="element-index">{{ idx + 1 }}</span>
                      <span class="element-type-badge" :style="{ background: elementTypeColor(element.type) + '22', color: elementTypeColor(element.type), borderColor: elementTypeColor(element.type) + '44' }">
                        {{ elementTypeLabel(element.type) }}
                      </span>
                    </div>
                    <button class="btn-remove" @click="removeElement(idx)" title="Remove element">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                      </svg>
                    </button>
                  </div>

                  <div class="element-fields">
                    <!-- Position (all types) -->
                    <label>
                      <span>X Position</span>
                      <input type="number" v-model.number="element.position_x" min="0" max="1" step="0.01" />
                    </label>
                    <label>
                      <span>Y Position</span>
                      <input type="number" v-model.number="element.position_y" min="0" max="1" step="0.01" />
                    </label>

                    <!-- Scale + Anchor (custom_image only — badge types use per-value overrides) -->
                    <template v-if="element.type === 'custom_image'">
                      <label>
                        <span>Scale (0.1-2.0)</span>
                        <input type="number" v-model.number="element.scale" min="0.1" max="2.0" step="0.1" placeholder="1.0" />
                      </label>
                      <label>
                        <span>Anchor</span>
                        <select v-model="element.anchor">
                          <option value="top-left">Top Left</option>
                          <option value="top-center">Top Center</option>
                          <option value="top-right">Top Right</option>
                          <option value="center-left">Center Left</option>
                          <option value="center">Center (default)</option>
                          <option value="center-right">Center Right</option>
                          <option value="bottom-left">Bottom Left</option>
                          <option value="bottom-center">Bottom Center</option>
                          <option value="bottom-right">Bottom Right</option>
                        </select>
                      </label>
                    </template>

                    <!-- Video Badge (+ legacy resolution_badge) -->
                    <template v-if="element.type === 'video_badge' || element.type === 'resolution_badge'">
                      <label class="field-full">
                        <span>Metadata Field</span>
                        <select v-model="element.metadata_field">
                          <option value="video_resolution">Video Resolution</option>
                          <option value="video_codec">Video Codec</option>
                        </select>
                      </label>
                      <div class="field-divider"></div>
                      <div class="field-full badge-assets-section">
                        <div class="badge-assets-label">Badge Rendering (per value)</div>
                        <div class="badge-asset-rows">
                          <div v-for="val in getValuesForField(element.metadata_field || 'video_resolution')" :key="val" class="badge-asset-item">
                            <div class="badge-asset-row">
                              <span class="badge-value-label">{{ val.toUpperCase() }}</span>
                              <select
                                :value="getBadgeMode(element, val)"
                                @change="setBadgeMode(element, val, ($event.target as HTMLSelectElement).value)"
                                class="badge-mode-select"
                              >
                                <option value="none">None</option>
                                <option value="text">Text</option>
                                <option value="image">Image</option>
                              </select>
                              <input
                                v-if="getBadgeMode(element, val) === 'text'"
                                type="text"
                                :value="getBadgeText(element, val)"
                                @input="setBadgeText(element, val, ($event.target as HTMLInputElement).value)"
                                :placeholder="val.toUpperCase()"
                                class="badge-text-input"
                              />
                              <select
                                v-if="getBadgeMode(element, val) === 'image'"
                                :value="getBadgeAsset(element, val) || ''"
                                @change="setBadgeAsset(element, val, ($event.target as HTMLSelectElement).value || undefined)"
                                class="badge-asset-select"
                              >
                                <option value="">Select asset...</option>
                                <option v-for="asset in assets" :key="asset.id" :value="asset.id">{{ asset.name }}</option>
                              </select>
                            </div>
                            <div v-if="getBadgeMode(element, val) === 'image'" class="badge-image-overrides">
                              <label>Scale
                                <input type="number" :value="getBadgeScale(element, val)" @input="setBadgeScale(element, val, ($event.target as HTMLInputElement).value)" min="0.05" max="3.0" step="0.05" placeholder="1.0" />
                              </label>
                              <label>Anchor
                                <select :value="getBadgeAnchor(element, val)" @change="setBadgeAnchor(element, val, ($event.target as HTMLSelectElement).value)">
                                  <option value="top-left">Top Left</option>
                                  <option value="top-center">Top Center</option>
                                  <option value="top-right">Top Right</option>
                                  <option value="center-left">Center Left</option>
                                  <option value="center">Center</option>
                                  <option value="center-right">Center Right</option>
                                  <option value="bottom-left">Bottom Left</option>
                                  <option value="bottom-center">Bottom Center</option>
                                  <option value="bottom-right">Bottom Right</option>
                                </select>
                              </label>
                            </div>
                          </div>
                        </div>
                      </div>
                      <template v-if="hasBadgeTextMode(element)">
                        <div class="field-divider"></div>
                        <label>
                          <span>Font Size (px)</span>
                          <input type="number" v-model.number="element.font_size" min="8" max="200" step="1" />
                        </label>
                        <label>
                          <span>Font Color</span>
                          <div class="color-input-wrap">
                            <input type="color" v-model="element.font_color" class="color-picker" />
                            <input type="text" v-model="element.font_color" class="color-text" placeholder="#FFFFFF" />
                          </div>
                        </label>
                        <label class="field-full">
                          <span>Font Family</span>
                          <select v-model="element.font_family">
                            <optgroup label="System Fonts">
                              <option value="Arial">Arial</option>
                              <option value="Helvetica">Helvetica</option>
                              <option value="Times New Roman">Times New Roman</option>
                              <option value="Georgia">Georgia</option>
                              <option value="Verdana">Verdana</option>
                              <option value="Courier New">Courier New</option>
                              <option value="Impact">Impact</option>
                            </optgroup>
                            <optgroup v-if="fonts.length > 0" label="Custom Fonts">
                              <option v-for="f in fonts" :key="f" :value="f">{{ f }}</option>
                            </optgroup>
                          </select>
                        </label>
                        <label class="field-full">
                          <span>Text Align</span>
                          <div class="align-btn-group">
                            <button type="button" :class="{ active: (element.text_align || 'center') === 'left' }" @click="element.text_align = 'left'">Left</button>
                            <button type="button" :class="{ active: (element.text_align || 'center') === 'center' }" @click="element.text_align = 'center'">Center</button>
                            <button type="button" :class="{ active: (element.text_align || 'center') === 'right' }" @click="element.text_align = 'right'">Right</button>
                          </div>
                        </label>
                      </template>
                    </template>

                    <!-- Audio Badge (+ legacy codec_badge) -->
                    <template v-if="element.type === 'audio_badge' || element.type === 'codec_badge'">
                      <label class="field-full">
                        <span>Metadata Field</span>
                        <select v-model="element.metadata_field">
                          <option value="audio_codec">Audio Codec</option>
                          <option value="audio_channels">Audio Channels</option>
                          <option value="audio_language">Audio Language</option>
                        </select>
                      </label>
                      <div class="field-divider"></div>
                      <div class="field-full badge-assets-section">
                        <div class="badge-assets-label">Badge Rendering (per value)</div>
                        <div class="badge-asset-rows">
                          <div v-for="val in getValuesForField(element.metadata_field || 'audio_codec')" :key="val" class="badge-asset-item">
                            <div class="badge-asset-row">
                              <span class="badge-value-label">{{ val.toUpperCase() }}</span>
                              <select
                                :value="getBadgeMode(element, val)"
                                @change="setBadgeMode(element, val, ($event.target as HTMLSelectElement).value)"
                                class="badge-mode-select"
                              >
                                <option value="none">None</option>
                                <option value="text">Text</option>
                                <option value="image">Image</option>
                              </select>
                              <input
                                v-if="getBadgeMode(element, val) === 'text'"
                                type="text"
                                :value="getBadgeText(element, val)"
                                @input="setBadgeText(element, val, ($event.target as HTMLInputElement).value)"
                                :placeholder="val.toUpperCase()"
                                class="badge-text-input"
                              />
                              <select
                                v-if="getBadgeMode(element, val) === 'image'"
                                :value="getBadgeAsset(element, val) || ''"
                                @change="setBadgeAsset(element, val, ($event.target as HTMLSelectElement).value || undefined)"
                                class="badge-asset-select"
                              >
                                <option value="">Select asset...</option>
                                <option v-for="asset in assets" :key="asset.id" :value="asset.id">{{ asset.name }}</option>
                              </select>
                            </div>
                            <div v-if="getBadgeMode(element, val) === 'image'" class="badge-image-overrides">
                              <label>Scale
                                <input type="number" :value="getBadgeScale(element, val)" @input="setBadgeScale(element, val, ($event.target as HTMLInputElement).value)" min="0.05" max="3.0" step="0.05" placeholder="1.0" />
                              </label>
                              <label>Anchor
                                <select :value="getBadgeAnchor(element, val)" @change="setBadgeAnchor(element, val, ($event.target as HTMLSelectElement).value)">
                                  <option value="top-left">Top Left</option>
                                  <option value="top-center">Top Center</option>
                                  <option value="top-right">Top Right</option>
                                  <option value="center-left">Center Left</option>
                                  <option value="center">Center</option>
                                  <option value="center-right">Center Right</option>
                                  <option value="bottom-left">Bottom Left</option>
                                  <option value="bottom-center">Bottom Center</option>
                                  <option value="bottom-right">Bottom Right</option>
                                </select>
                              </label>
                            </div>
                          </div>
                        </div>
                      </div>
                      <template v-if="hasBadgeTextMode(element)">
                        <div class="field-divider"></div>
                        <label>
                          <span>Font Size (px)</span>
                          <input type="number" v-model.number="element.font_size" min="8" max="200" step="1" />
                        </label>
                        <label>
                          <span>Font Color</span>
                          <div class="color-input-wrap">
                            <input type="color" v-model="element.font_color" class="color-picker" />
                            <input type="text" v-model="element.font_color" class="color-text" placeholder="#FFFFFF" />
                          </div>
                        </label>
                        <label class="field-full">
                          <span>Font Family</span>
                          <select v-model="element.font_family">
                            <optgroup label="System Fonts">
                              <option value="Arial">Arial</option>
                              <option value="Helvetica">Helvetica</option>
                              <option value="Times New Roman">Times New Roman</option>
                              <option value="Georgia">Georgia</option>
                              <option value="Verdana">Verdana</option>
                              <option value="Courier New">Courier New</option>
                              <option value="Impact">Impact</option>
                            </optgroup>
                            <optgroup v-if="fonts.length > 0" label="Custom Fonts">
                              <option v-for="f in fonts" :key="f" :value="f">{{ f }}</option>
                            </optgroup>
                          </select>
                        </label>
                        <label class="field-full">
                          <span>Text Align</span>
                          <div class="align-btn-group">
                            <button type="button" :class="{ active: (element.text_align || 'center') === 'left' }" @click="element.text_align = 'left'">Left</button>
                            <button type="button" :class="{ active: (element.text_align || 'center') === 'center' }" @click="element.text_align = 'center'">Center</button>
                            <button type="button" :class="{ active: (element.text_align || 'center') === 'right' }" @click="element.text_align = 'right'">Right</button>
                          </div>
                        </label>
                      </template>
                    </template>

                    <!-- Edition Badge -->
                    <template v-if="element.type === 'edition_badge'">
                      <div class="field-divider"></div>
                      <div class="field-full badge-assets-section">
                        <div class="badge-assets-label">Badge Rendering (per value)</div>
                        <div class="badge-asset-rows">
                          <div v-for="val in EDITION_VALUES" :key="val" class="badge-asset-item">
                            <div class="badge-asset-row">
                              <span class="badge-value-label">{{ val.toUpperCase() }}</span>
                              <select
                                :value="getBadgeMode(element, val)"
                                @change="setBadgeMode(element, val, ($event.target as HTMLSelectElement).value)"
                                class="badge-mode-select"
                              >
                                <option value="none">None</option>
                                <option value="text">Text</option>
                                <option value="image">Image</option>
                              </select>
                              <input
                                v-if="getBadgeMode(element, val) === 'text'"
                                type="text"
                                :value="getBadgeText(element, val)"
                                @input="setBadgeText(element, val, ($event.target as HTMLInputElement).value)"
                                :placeholder="val.toUpperCase()"
                                class="badge-text-input"
                              />
                              <select
                                v-if="getBadgeMode(element, val) === 'image'"
                                :value="getBadgeAsset(element, val) || ''"
                                @change="setBadgeAsset(element, val, ($event.target as HTMLSelectElement).value || undefined)"
                                class="badge-asset-select"
                              >
                                <option value="">Select asset...</option>
                                <option v-for="asset in assets" :key="asset.id" :value="asset.id">{{ asset.name }}</option>
                              </select>
                            </div>
                            <div v-if="getBadgeMode(element, val) === 'image'" class="badge-image-overrides">
                              <label>Scale
                                <input type="number" :value="getBadgeScale(element, val)" @input="setBadgeScale(element, val, ($event.target as HTMLInputElement).value)" min="0.05" max="3.0" step="0.05" placeholder="1.0" />
                              </label>
                              <label>Anchor
                                <select :value="getBadgeAnchor(element, val)" @change="setBadgeAnchor(element, val, ($event.target as HTMLSelectElement).value)">
                                  <option value="top-left">Top Left</option>
                                  <option value="top-center">Top Center</option>
                                  <option value="top-right">Top Right</option>
                                  <option value="center-left">Center Left</option>
                                  <option value="center">Center</option>
                                  <option value="center-right">Center Right</option>
                                  <option value="bottom-left">Bottom Left</option>
                                  <option value="bottom-center">Bottom Center</option>
                                  <option value="bottom-right">Bottom Right</option>
                                </select>
                              </label>
                            </div>
                          </div>
                        </div>
                      </div>
                      <template v-if="hasBadgeTextMode(element)">
                        <div class="field-divider"></div>
                        <label>
                          <span>Font Size (px)</span>
                          <input type="number" v-model.number="element.font_size" min="8" max="200" step="1" />
                        </label>
                        <label>
                          <span>Font Color</span>
                          <div class="color-input-wrap">
                            <input type="color" v-model="element.font_color" class="color-picker" />
                            <input type="text" v-model="element.font_color" class="color-text" placeholder="#FFFFFF" />
                          </div>
                        </label>
                        <label class="field-full">
                          <span>Font Family</span>
                          <select v-model="element.font_family">
                            <optgroup label="System Fonts">
                              <option value="Arial">Arial</option>
                              <option value="Helvetica">Helvetica</option>
                              <option value="Times New Roman">Times New Roman</option>
                              <option value="Georgia">Georgia</option>
                              <option value="Verdana">Verdana</option>
                              <option value="Courier New">Courier New</option>
                              <option value="Impact">Impact</option>
                            </optgroup>
                            <optgroup v-if="fonts.length > 0" label="Custom Fonts">
                              <option v-for="f in fonts" :key="f" :value="f">{{ f }}</option>
                            </optgroup>
                          </select>
                        </label>
                        <label class="field-full">
                          <span>Text Align</span>
                          <div class="align-btn-group">
                            <button type="button" :class="{ active: (element.text_align || 'center') === 'left' }" @click="element.text_align = 'left'">Left</button>
                            <button type="button" :class="{ active: (element.text_align || 'center') === 'center' }" @click="element.text_align = 'center'">Center</button>
                            <button type="button" :class="{ active: (element.text_align || 'center') === 'right' }" @click="element.text_align = 'right'">Right</button>
                          </div>
                        </label>
                      </template>
                    </template>

                    <!-- Custom Image -->
                    <template v-if="element.type === 'custom_image'">
                      <label class="field-full">
                        <span>Asset</span>
                        <select v-model="element.asset_id">
                          <option :value="undefined">Select asset...</option>
                          <option v-for="asset in assets" :key="asset.id" :value="asset.id">{{ asset.name }} ({{ asset.width }}x{{ asset.height }})</option>
                        </select>
                      </label>
                      <label>
                        <span>Max Width (px)</span>
                        <input type="number" v-model.number="element.max_width" min="0" step="10" placeholder="none" />
                      </label>
                      <label>
                        <span>Max Height (px)</span>
                        <input type="number" v-model.number="element.max_height" min="0" step="10" placeholder="none" />
                      </label>
                    </template>

                    <!-- Text Label -->
                    <template v-if="element.type === 'text_label'">
                      <label class="field-full">
                        <span>Text</span>
                        <input type="text" v-model="element.text" placeholder="Enter text..." />
                      </label>
                      <label>
                        <span>Font Size (px)</span>
                        <input type="number" v-model.number="element.font_size" min="8" max="200" step="1" />
                      </label>
                      <label>
                        <span>Font Color</span>
                        <div class="color-input-wrap">
                          <input type="color" v-model="element.font_color" class="color-picker" />
                          <input type="text" v-model="element.font_color" class="color-text" placeholder="#FFFFFF" />
                        </div>
                      </label>
                      <label class="field-full">
                        <span>Font Family</span>
                        <select v-model="element.font_family">
                            <optgroup label="System Fonts">
                              <option value="Arial">Arial</option>
                              <option value="Helvetica">Helvetica</option>
                              <option value="Times New Roman">Times New Roman</option>
                              <option value="Georgia">Georgia</option>
                              <option value="Verdana">Verdana</option>
                              <option value="Courier New">Courier New</option>
                              <option value="Impact">Impact</option>
                            </optgroup>
                            <optgroup v-if="fonts.length > 0" label="Custom Fonts">
                              <option v-for="f in fonts" :key="f" :value="f">{{ f }}</option>
                            </optgroup>
                          </select>
                      </label>
                      <label class="field-full">
                        <span>Text Align</span>
                        <div class="align-btn-group">
                          <button type="button" :class="{ active: (element.text_align || 'center') === 'left' }" @click="element.text_align = 'left'">Left</button>
                          <button type="button" :class="{ active: (element.text_align || 'center') === 'center' }" @click="element.text_align = 'center'">Center</button>
                          <button type="button" :class="{ active: (element.text_align || 'center') === 'right' }" @click="element.text_align = 'right'">Right</button>
                        </div>
                      </label>
                    </template>

                    <!-- Conditional rendering (all types) -->
                    <div class="field-divider"></div>
                    <label>
                      <span>Show if Label</span>
                      <input type="text" v-model="element.show_if_label" placeholder="optional" />
                    </label>
                    <label>
                      <span>Hide if Label</span>
                      <input type="text" v-model="element.hide_if_label" placeholder="optional" />
                    </label>
                  </div>
                </div>
              </div>
            </div>

            <!-- Right: Preview -->
            <div class="preview-column">
              <div class="preview-panel">
                <div class="preview-top-row">
                  <div class="preview-label">Live Preview</div>
                  <label class="drag-toggle">
                    <input type="checkbox" v-model="dragEnabled" />
                    <span>Drag to position</span>
                  </label>
                </div>

                <!-- Poster search -->
                <div class="poster-search-row">
                  <button class="btn-search" @click="openMovieSearch" :disabled="posterLoading">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                    </svg>
                    {{ selectedMovie ? selectedMovie.title : 'Search poster...' }}
                  </button>
                  <button v-if="selectedMovie" class="btn-clear-poster" @click="clearPoster" title="Clear poster">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                  </button>
                </div>

                <div class="preview-frame">
                  <canvas
                    ref="previewCanvas"
                    :style="{ width: PREVIEW_W + 'px', height: PREVIEW_H + 'px', cursor: dragEnabled ? (draggingIdx !== null ? 'grabbing' : 'grab') : 'default' }"
                    class="preview-canvas"
                    @mousedown="onCanvasMouseDown"
                    @mousemove="onCanvasMouseMove"
                    @mouseup="onCanvasMouseUp"
                    @mouseleave="onCanvasMouseUp"
                    @touchstart="onCanvasTouchStart"
                    @touchmove="onCanvasTouchMove"
                    @touchend="onCanvasTouchEnd"
                  ></canvas>
                </div>

                <!-- Preview value switchers -->
                <div class="preview-values">
                  <label class="preview-value-field">
                    <span>Resolution</span>
                    <select v-model="previewResolution">
                      <option v-for="v in RESOLUTION_VALUES" :key="v" :value="v">{{ v.toUpperCase() }}</option>
                    </select>
                  </label>
                  <label class="preview-value-field">
                    <span>Video Codec</span>
                    <select v-model="previewVideoCodec">
                      <option v-for="v in VIDEO_CODEC_VALUES" :key="v" :value="v">{{ v.toUpperCase() }}</option>
                    </select>
                  </label>
                  <label class="preview-value-field">
                    <span>Audio Codec</span>
                    <select v-model="previewCodec">
                      <option v-for="v in CODEC_VALUES" :key="v" :value="v">{{ v.toUpperCase() }}</option>
                    </select>
                  </label>
                  <label class="preview-value-field">
                    <span>Channels</span>
                    <select v-model="previewAudioChannels">
                      <option v-for="v in AUDIO_CHANNELS_VALUES" :key="v" :value="v">{{ v }}</option>
                    </select>
                  </label>
                  <label class="preview-value-field">
                    <span>Language</span>
                    <select v-model="previewAudioLanguage">
                      <option v-for="v in AUDIO_LANGUAGE_VALUES" :key="v" :value="v">{{ v.toUpperCase() }}</option>
                    </select>
                  </label>
                  <label class="preview-value-field">
                    <span>Edition</span>
                    <select v-model="previewEdition">
                      <option v-for="v in EDITION_VALUES" :key="v" :value="v">{{ v.charAt(0).toUpperCase() + v.slice(1) }}</option>
                    </select>
                  </label>
                </div>

                <div class="preview-info">
                  <span>{{ selectedConfig.elements.length }} element{{ selectedConfig.elements.length !== 1 ? 's' : '' }}</span>
                  <span>2000 x 3000</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="editor-footer">
          <button class="btn-secondary" @click="showEditor = false">Cancel</button>
          <button class="btn-primary" @click="saveConfig">Save Configuration</button>
        </div>
      </div>
    </div>

    <!-- Movie Search Modal -->
    <div v-if="showMovieSearch" class="modal-overlay" @click.self="showMovieSearch = false" style="z-index: 1100;">
      <div class="search-modal">
        <div class="search-modal-header">
          <h3>Select a poster</h3>
          <button class="btn-close" @click="showMovieSearch = false">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="search-modal-body">
          <input
            type="text"
            v-model="movieSearchTerm"
            placeholder="Search by title..."
            class="search-input"
            autofocus
          />
          <div class="search-results">
            <button
              v-for="movie in movieSearchResults"
              :key="movie.key"
              class="search-result"
              @click="selectMovie(movie)"
            >
              {{ movie.title }}
            </button>
            <div v-if="movieSearchResults.length === 0" class="search-empty">No movies match that search.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Asset Upload Modal -->
    <div v-if="showAssetUpload" class="modal-overlay" @click.self="showAssetUpload = false">
      <div class="upload-modal">
        <div class="upload-header">
          <h3>Upload Overlay Asset</h3>
          <button class="btn-close" @click="showAssetUpload = false">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="upload-body">
          <label>
            <span>Asset Name</span>
            <input type="text" v-model="uploadFileName" placeholder="e.g., 4K Badge" />
          </label>
          <label>
            <span>Image File (PNG, JPG, WebP)</span>
            <input type="file" accept="image/png,image/jpeg,image/webp" @change="handleFileSelect" />
          </label>
        </div>
        <div class="upload-footer">
          <button class="btn-secondary" @click="showAssetUpload = false">Cancel</button>
          <button class="btn-primary" @click="uploadAsset" :disabled="uploading">
            {{ uploading ? 'Uploading...' : 'Upload' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay-manager { padding: 1.5rem; max-width: 1400px; }
.page-header { margin-bottom: 1.5rem; }
.page-header h1 { display: flex; align-items: center; gap: 0.75rem; margin: 0 0 0.4rem 0; color: var(--text-primary, #fff); font-size: 2rem; font-weight: 700; }
.page-header h1 svg { color: var(--accent, #3dd6b7); }
.page-subtitle { margin: 0; color: var(--text-secondary, #aaa); font-size: 0.95rem; }

.content-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
.section-card { background: var(--surface, #1a1f2e); border: 1px solid var(--border, #2a2f3e); border-radius: 12px; padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.section-header h2 { margin: 0; color: var(--text-primary, #fff); font-size: 1.15rem; font-weight: 600; }

.btn-primary-sm { display: flex; align-items: center; gap: 0.35rem; padding: 0.4rem 0.8rem; background: linear-gradient(135deg, var(--accent, #3dd6b7), #2bc4a6); color: #000; border: none; border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: 500; }
.btn-primary-sm:hover { opacity: 0.9; }
.btn-secondary-sm { display: flex; align-items: center; gap: 0.35rem; padding: 0.4rem 0.8rem; background: transparent; color: var(--text-secondary, #aaa); border: 1px solid var(--border, #2a2f3e); border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: 500; }
.btn-secondary-sm:hover { border-color: var(--accent, #3dd6b7); color: var(--accent, #3dd6b7); }

.loading, .empty-state { padding: 2rem; text-align: center; color: var(--text-secondary, #aaa); font-size: 0.9rem; }

.configs-list { display: flex; flex-direction: column; gap: 0.5rem; }
.config-item { display: flex; align-items: center; justify-content: space-between; padding: 0.75rem; background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border, #2a2f3e); border-radius: 8px; transition: background 0.15s; }
.config-item:hover { background: rgba(255, 255, 255, 0.04); }
.config-info { flex: 1; }
.config-name { color: var(--text-primary, #fff); font-weight: 500; font-size: 0.95rem; }
.config-meta { color: var(--text-secondary, #777); font-size: 0.8rem; margin-top: 2px; }
.config-actions { display: flex; gap: 0.5rem; }

.btn-icon { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; padding: 0; background: transparent; border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-secondary, #aaa); cursor: pointer; transition: all 0.15s; }
.btn-icon:hover { border-color: var(--accent, #3dd6b7); color: var(--accent, #3dd6b7); }
.btn-icon.danger:hover { border-color: #f87171; color: #f87171; }

.assets-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 0.75rem; }
.asset-item { position: relative; background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border, #2a2f3e); border-radius: 8px; padding: 0.5rem; display: flex; flex-direction: column; gap: 0.4rem; }
.asset-thumbnail { width: 100%; height: 80px; object-fit: contain; background: rgba(0, 0, 0, 0.2); border-radius: 4px; }
.asset-info { display: flex; flex-direction: column; }
.asset-name { color: var(--text-primary, #fff); font-size: 0.8rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.asset-meta { color: var(--text-secondary, #777); font-size: 0.7rem; }

.btn-icon-sm { position: absolute; top: 0.5rem; right: 0.5rem; display: flex; align-items: center; justify-content: center; width: 20px; height: 20px; padding: 0; background: rgba(0, 0, 0, 0.6); border: 1px solid rgba(248, 113, 113, 0.5); border-radius: 4px; color: #f87171; cursor: pointer; opacity: 0; transition: opacity 0.15s; }
.asset-item:hover .btn-icon-sm { opacity: 1; }
.btn-icon-sm:hover { background: rgba(248, 113, 113, 0.2); }

/* Modals */
.modal-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.7); display: flex; align-items: center; justify-content: center; z-index: 1000; backdrop-filter: blur(2px); }

.editor-modal { background: var(--surface, #1a1f2e); border: 1px solid var(--border, #2a2f3e); border-radius: 14px; width: 94%; max-width: 1100px; max-height: 88vh; display: flex; flex-direction: column; overflow: hidden; }
.editor-header { display: flex; justify-content: space-between; align-items: flex-start; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border, #2a2f3e); }
.editor-header h2 { margin: 0 0 0.4rem 0; color: var(--text-primary, #fff); font-size: 1.15rem; }
.config-name-input { width: 100%; padding: 0.45rem 0.6rem; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border, #2a2f3e); border-radius: 6px; color: var(--text-primary, #fff); font-size: 0.95rem; }
.config-name-input:focus { outline: none; border-color: var(--accent, #3dd6b7); }

.btn-close { background: none; border: none; color: var(--text-secondary, #aaa); cursor: pointer; padding: 4px; border-radius: 4px; transition: color 0.2s; }
.btn-close:hover { color: var(--text-primary, #fff); }

.editor-body { flex: 1; overflow-y: auto; padding: 1.25rem; }
.editor-columns { display: grid; grid-template-columns: 1fr 330px; gap: 1.25rem; align-items: start; }

/* Elements column */
.elements-column { display: flex; flex-direction: column; gap: 0.75rem; min-width: 0; }
.elements-header { margin-bottom: 0.25rem; }
.elements-header h3 { margin: 0 0 0.6rem 0; color: var(--text-primary, #fff); font-size: 0.95rem; }
.add-element-buttons { display: flex; gap: 0.4rem; flex-wrap: wrap; }

.btn-add { padding: 0.3rem 0.6rem; background: rgba(61, 214, 183, 0.08); border: 1px solid rgba(61, 214, 183, 0.25); border-radius: 5px; color: var(--accent, #3dd6b7); cursor: pointer; font-size: 0.75rem; transition: all 0.15s; }
.btn-add:hover { background: rgba(61, 214, 183, 0.18); }

.empty-elements { padding: 2rem; text-align: center; color: var(--text-secondary, #aaa); font-size: 0.9rem; }

.elements-list { display: flex; flex-direction: column; gap: 0.6rem; }
.element-card { background: rgba(255, 255, 255, 0.015); border: 1px solid var(--border, #2a2f3e); border-radius: 8px; padding: 0.7rem; transition: border-color 0.15s; }
.element-card.element-hovered { border-color: rgba(61, 214, 183, 0.4); }

.element-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; }
.element-header-left { display: flex; align-items: center; gap: 0.5rem; }
.element-index { display: flex; align-items: center; justify-content: center; width: 20px; height: 20px; background: rgba(255, 255, 255, 0.08); border-radius: 50%; color: var(--text-secondary, #aaa); font-size: 0.7rem; font-weight: 600; }
.element-type-badge { padding: 2px 8px; border: 1px solid; border-radius: 10px; font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.02em; }

.btn-remove { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; padding: 0; background: transparent; border: 1px solid transparent; border-radius: 4px; color: var(--text-secondary, #666); cursor: pointer; transition: all 0.15s; }
.btn-remove:hover { border-color: #f87171; color: #f87171; background: rgba(248, 113, 113, 0.1); }

.element-fields { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.55rem; }
.element-fields label { display: flex; flex-direction: column; gap: 0.2rem; }
.element-fields label.field-full { grid-column: 1 / -1; }
.element-fields label span { color: var(--text-secondary, #888); font-size: 0.72rem; font-weight: 500; }
.element-fields input, .element-fields select { padding: 0.35rem 0.45rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.8rem; }
.element-fields input:focus, .element-fields select:focus { outline: none; border-color: var(--accent, #3dd6b7); }

.field-divider { grid-column: 1 / -1; height: 1px; background: var(--border, #2a2f3e); margin: 0.15rem 0; }
.field-full { grid-column: 1 / -1; }

.color-input-wrap { display: flex; gap: 0.35rem; align-items: stretch; }
.color-picker { width: 32px; height: 28px; padding: 1px; border: 1px solid var(--border, #2a2f3e); border-radius: 4px; background: transparent; cursor: pointer; flex-shrink: 0; }
.color-picker::-webkit-color-swatch-wrapper { padding: 1px; }
.color-picker::-webkit-color-swatch { border: none; border-radius: 2px; }
.color-text { flex: 1; min-width: 0; padding: 0.35rem 0.45rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.78rem; font-family: monospace; }

/* Badge assets mapping */
.badge-assets-section { display: flex; flex-direction: column; gap: 0.4rem; }
.badge-assets-label { color: var(--text-secondary, #888); font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
.badge-asset-rows { display: flex; flex-direction: column; gap: 0.4rem; }
.badge-asset-item { display: flex; flex-direction: column; gap: 0.25rem; }
.badge-asset-row { display: flex; align-items: center; gap: 0.4rem; }
.badge-image-overrides { display: flex; align-items: center; gap: 0.6rem; padding-left: 76px; }
.badge-image-overrides label { display: flex; align-items: center; gap: 0.3rem; color: var(--text-secondary, #888); font-size: 0.7rem; }
.badge-image-overrides input[type="number"] { width: 4.5rem; padding: 0.25rem 0.35rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.badge-image-overrides select { padding: 0.25rem 0.35rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.badge-image-overrides input:focus, .badge-image-overrides select:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.badge-value-label { color: var(--text-secondary, #aaa); font-size: 0.72rem; font-weight: 600; min-width: 70px; text-align: right; }
.badge-mode-select { width: 68px; flex-shrink: 0; padding: 0.3rem 0.3rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.badge-asset-select { flex: 1; padding: 0.3rem 0.4rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.badge-text-input { flex: 1; padding: 0.3rem 0.4rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.badge-text-input:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.badge-asset-row select:focus { outline: none; border-color: var(--accent, #3dd6b7); }

/* Text align button group */
.align-btn-group { display: flex; gap: 0; border-radius: 5px; overflow: hidden; border: 1px solid var(--border, #2a2f3e); }
.align-btn-group button { flex: 1; padding: 0.3rem 0.5rem; background: rgba(255, 255, 255, 0.04); border: none; border-right: 1px solid var(--border, #2a2f3e); color: var(--text-secondary, #888); cursor: pointer; font-size: 0.72rem; font-weight: 500; transition: all 0.15s; }
.align-btn-group button:last-child { border-right: none; }
.align-btn-group button:hover { background: rgba(255, 255, 255, 0.08); color: var(--text-primary, #fff); }
.align-btn-group button.active { background: rgba(61, 214, 183, 0.15); color: var(--accent, #3dd6b7); font-weight: 600; }

/* Preview column */
.preview-column { position: sticky; top: 0; }
.preview-panel { background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border, #2a2f3e); border-radius: 10px; padding: 0.75rem; display: flex; flex-direction: column; gap: 0.5rem; }

.preview-top-row { display: flex; justify-content: space-between; align-items: center; }
.preview-label { color: var(--text-secondary, #888); font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }

.drag-toggle { display: flex; align-items: center; gap: 0.35rem; cursor: pointer; user-select: none; }
.drag-toggle input[type="checkbox"] { width: 14px; height: 14px; accent-color: var(--accent, #3dd6b7); cursor: pointer; }
.drag-toggle span { color: var(--text-secondary, #888); font-size: 0.7rem; }

/* Poster search */
.poster-search-row { display: flex; gap: 0.3rem; }
.btn-search { flex: 1; display: flex; align-items: center; gap: 0.35rem; padding: 0.3rem 0.5rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-secondary, #888); cursor: pointer; font-size: 0.72rem; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: border-color 0.15s; }
.btn-search:hover { border-color: var(--accent, #3dd6b7); color: var(--text-primary, #fff); }
.btn-search:disabled { opacity: 0.5; cursor: wait; }
.btn-search svg { flex-shrink: 0; }

.btn-clear-poster { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; padding: 0; background: transparent; border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-secondary, #888); cursor: pointer; transition: all 0.15s; }
.btn-clear-poster:hover { border-color: #f87171; color: #f87171; }

.preview-frame { display: flex; justify-content: center; background: rgba(0, 0, 0, 0.3); border-radius: 6px; padding: 0.5rem; }
.preview-canvas { border-radius: 4px; display: block; }

/* Preview value switchers */
.preview-values { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; }
.preview-value-field { display: flex; flex-direction: column; gap: 0.15rem; }
.preview-value-field span { color: var(--text-secondary, #666); font-size: 0.65rem; font-weight: 500; }
.preview-value-field select { padding: 0.25rem 0.35rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.preview-value-field select:focus { outline: none; border-color: var(--accent, #3dd6b7); }

.preview-info { display: flex; justify-content: space-between; color: var(--text-secondary, #666); font-size: 0.7rem; }

.editor-footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--border, #2a2f3e); }

.btn-secondary { padding: 0.55rem 1.1rem; background: transparent; color: var(--text-secondary, #aaa); border: 1px solid var(--border, #2a2f3e); border-radius: 6px; cursor: pointer; font-size: 0.88rem; }
.btn-secondary:hover { border-color: var(--text-secondary, #aaa); }

.btn-primary { padding: 0.55rem 1.1rem; background: linear-gradient(135deg, var(--accent, #3dd6b7), #2bc4a6); color: #000; border: none; border-radius: 6px; cursor: pointer; font-size: 0.88rem; font-weight: 500; }
.btn-primary:hover { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

/* Movie search modal */
.search-modal { background: var(--surface, #1a1f2e); border: 1px solid var(--border, #2a2f3e); border-radius: 12px; width: 90%; max-width: 440px; max-height: 70vh; display: flex; flex-direction: column; overflow: hidden; }
.search-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.25rem; border-bottom: 1px solid var(--border, #2a2f3e); }
.search-modal-header h3 { margin: 0; color: var(--text-primary, #fff); font-size: 1rem; }
.search-modal-body { padding: 1rem 1.25rem; display: flex; flex-direction: column; gap: 0.75rem; overflow: hidden; }
.search-input { padding: 0.5rem 0.6rem; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border, #2a2f3e); border-radius: 6px; color: var(--text-primary, #fff); font-size: 0.9rem; }
.search-input:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.search-results { overflow-y: auto; max-height: 45vh; display: flex; flex-direction: column; gap: 2px; }
.search-result { display: block; width: 100%; text-align: left; padding: 0.5rem 0.6rem; background: transparent; border: none; border-radius: 5px; color: var(--text-primary, #fff); cursor: pointer; font-size: 0.85rem; transition: background 0.1s; }
.search-result:hover { background: rgba(61, 214, 183, 0.1); }
.search-empty { padding: 1rem; text-align: center; color: var(--text-secondary, #777); font-size: 0.85rem; }

/* Upload Modal */
.upload-modal { background: var(--surface, #1a1f2e); border: 1px solid var(--border, #2a2f3e); border-radius: 12px; width: 90%; max-width: 480px; display: flex; flex-direction: column; }
.upload-header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border, #2a2f3e); }
.upload-header h3 { margin: 0; color: var(--text-primary, #fff); font-size: 1.05rem; }
.upload-body { padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; }
.upload-body label { display: flex; flex-direction: column; gap: 0.4rem; }
.upload-body label span { color: var(--text-secondary, #aaa); font-size: 0.85rem; font-weight: 500; }
.upload-body input[type="text"] { padding: 0.6rem; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border, #2a2f3e); border-radius: 6px; color: var(--text-primary, #fff); font-size: 0.9rem; }
.upload-body input[type="text"]:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.upload-body input[type="file"] { padding: 0.5rem; background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border, #2a2f3e); border-radius: 6px; color: var(--text-secondary, #aaa); font-size: 0.85rem; cursor: pointer; }
.upload-footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--border, #2a2f3e); }

@media (max-width: 900px) {
  .overlay-manager { padding: 1rem; }
  .content-grid { grid-template-columns: 1fr; }
  .editor-modal { width: 96%; max-height: 92vh; }
  .editor-columns { grid-template-columns: 1fr; }
  .preview-column { position: static; order: -1; }
  .upload-modal { width: 96%; }
}
</style>
