<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick, toRaw, shallowRef, type Ref } from 'vue'
import { getApiBase } from '@/services/apiBase'
import OverlayRulesEditor from '@/components/overlay/OverlayRulesEditor.vue'
import KometaPlacementEditor from '@/components/overlay/KometaPlacementEditor.vue'
import KometaImportModal from '@/components/overlay/KometaImportModal.vue'
import OverlayPositionEditor from '@/components/overlay/OverlayPositionEditor.vue'
import OverlayBadgeSets from '@/components/overlay/OverlayBadgeSets.vue'
import LiveKometaFiles from '@/components/overlay/LiveKometaFiles.vue'
import OverlayScheduler from '@/components/overlay/OverlayScheduler.vue'
import OverlayWorkflowGuide from '@/components/overlay/OverlayWorkflowGuide.vue'
import OverlayRefreshPrompt from '@/components/overlay/OverlayRefreshPrompt.vue'
import { elementNoun, elementPlace, elementWhen } from '@/services/overlayLabels'
import { FIELDS, fieldDef, opDef, TEXT_VARIABLES, TEXT_VARIABLE_GROUPS, needsMdblist } from '@/services/overlayFields'
import { useSettingsStore } from '@/stores/settings'
import { listDisplayName, useListSources } from '@/composables/useListSources'
import { mediaServerLabel } from '@/services/mediaServerLabel'
import {
  buildContext, selectElementIndices, fillText, placeBox, offsetsFromBox, cssColor, blurAmount, queuePlacements,
  KOMETA_W, KOMETA_H, referencedLists, checkCondition, type OverlayRuleFields, type OverlayCondition,
} from '@/services/overlayEngine'

const apiBase = getApiBase()

// --- Types ---

interface OverlayElement extends OverlayRuleFields {
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
  font_weight?: string
  font_size?: number
  font_color?: string
  label_name?: string
  show_if_label?: string
  hide_if_label?: string
  metadata_field?: string
  badge_modes?: Record<string, string>
  badge_assets?: Record<string, string>
  badge_texts?: Record<string, string>
  badge_urls?: Record<string, string>
  badge_scales?: Record<string, number>
  badge_anchors?: Record<string, string>
  slug_aliases?: Record<string, string>
  text_align?: string
}

interface OverlayConfig {
  id: string
  name: string
  elements: OverlayElement[]
  /** Conditions for the whole overlay: when any fails, none of its layers draw. */
  conditions?: OverlayCondition[]
  streaming_region?: string
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

const STREAMING_PLATFORM_VALUES = [
  'netflix', 'prime-video', 'disney-plus', 'max', 'hulu',
  'apple-tv-plus', 'paramount-plus', 'peacock', 'tubi',
  'crunchyroll', 'shudder', 'mubi',
]
const STREAMING_PLATFORM_LABELS: Record<string, string> = {
  'netflix': 'Netflix', 'prime-video': 'Prime Video', 'disney-plus': 'Disney+',
  'max': 'Max', 'hulu': 'Hulu', 'apple-tv-plus': 'Apple TV+',
  'paramount-plus': 'Paramount+', 'peacock': 'Peacock', 'tubi': 'Tubi',
  'crunchyroll': 'Crunchyroll', 'shudder': 'Shudder', 'mubi': 'MUBI',
}
const STREAMING_REGIONS = [
  { code: 'US', label: 'United States' }, { code: 'GB', label: 'United Kingdom' },
  { code: 'CA', label: 'Canada' }, { code: 'AU', label: 'Australia' },
  { code: 'DE', label: 'Germany' }, { code: 'FR', label: 'France' },
  { code: 'ES', label: 'Spain' }, { code: 'IT', label: 'Italy' },
  { code: 'JP', label: 'Japan' }, { code: 'KR', label: 'South Korea' },
  { code: 'BR', label: 'Brazil' }, { code: 'MX', label: 'Mexico' },
]

const STUDIO_VALUES = [
  // Film studios
  'a24', 'netflix', 'amazon-mgm', 'apple-original',
  'disney', 'marvel-studios', 'pixar',
  'warner-bros', 'universal', 'paramount',
  'sony-pictures', '20th-century', 'lionsgate',
  'blumhouse', 'focus-features', 'dreamworks',
  'amblin', 'legendary', 'bad-robot',
  // TV networks
  'hbo', 'fx', 'amc', 'showtime', 'starz',
  'cbs', 'nbc', 'abc', 'fox',
]
const STUDIO_LABELS: Record<string, string> = {
  'a24': 'A24', 'netflix': 'Netflix', 'amazon-mgm': 'Amazon MGM',
  'apple-original': 'Apple Original Films', 'disney': 'Disney',
  'marvel-studios': 'Marvel Studios', 'pixar': 'Pixar',
  'warner-bros': 'Warner Bros.', 'universal': 'Universal', 'paramount': 'Paramount',
  'sony-pictures': 'Sony Pictures', '20th-century': '20th Century', 'lionsgate': 'Lionsgate',
  'blumhouse': 'Blumhouse', 'focus-features': 'Focus Features', 'dreamworks': 'DreamWorks',
  'amblin': 'Amblin', 'legendary': 'Legendary', 'bad-robot': 'Bad Robot',
  'hbo': 'HBO', 'fx': 'FX', 'amc': 'AMC', 'showtime': 'Showtime', 'starz': 'Starz',
  'cbs': 'CBS', 'nbc': 'NBC', 'abc': 'ABC', 'fox': 'FOX',
}

const METADATA_FIELD_VALUES: Record<string, string[]> = {
  video_resolution: RESOLUTION_VALUES,
  video_codec: VIDEO_CODEC_VALUES,
  audio_codec: CODEC_VALUES,
  audio_channels: AUDIO_CHANNELS_VALUES,
  audio_language: AUDIO_LANGUAGE_VALUES,
  edition: EDITION_VALUES,
  streaming_platform: STREAMING_PLATFORM_VALUES,
  studio: STUDIO_VALUES,
}

const getValuesForField = (field: string): string[] => {
  return METADATA_FIELD_VALUES[field] || RESOLUTION_VALUES
}

// --- State ---

const configs = ref<OverlayConfig[]>([])
const assets = ref<OverlayAsset[]>([])
const fonts = ref<string[]>([])
const simposterAssetMap = ref<Record<string, string>>({})
const loading = ref(false)
const selectedConfig = ref<OverlayConfig | null>(null)
const showEditor = ref(false)
const showAssetUpload = ref(false)
const hoveredElementIdx = ref<number | null>(null)

// Preview canvas
const previewCanvas = ref<HTMLCanvasElement | null>(null)
const PREVIEW_W = 380
const PREVIEW_H = 570
const assetImageCache = ref<Record<string, HTMLImageElement>>({})
const urlImageCache = ref<Record<string, HTMLImageElement>>({})

// Drag state
const dragEnabled = ref(true)
const draggingIdx = ref<number | null>(null)

// Poster search state
const movies = ref<SimpleMovie[]>([])
const moviesLoaded = ref(false)
const movieSearchTerm = ref('')
const showMovieSearch = ref(false)
const selectedMovie = ref<SimpleMovie | null>(null)
const posterBgImage = ref<HTMLImageElement | null>(null)
const posterLoading = ref(false)

// Library selection for preview
const previewLibraries = ref<Array<{key: string, title: string, type: string, server?: string}>>([])
const previewLibrariesLoading = ref(false)
const previewSelectedLibrary = ref<{key: string, title: string, type: string, server?: string} | null>(null)

// Preview mode: 'item' uses real Plex metadata, 'testing' uses manual dropdowns
const previewMode = ref<'item' | 'testing'>('testing')
const previewItemMetadata = ref<Record<string, string>>({})

const movieSearchResults = computed(() => {
  const q = movieSearchTerm.value.trim().toLowerCase()
  if (!q) return movies.value.slice(0, 50)
  return movies.value.filter(m => m.title.toLowerCase().includes(q)).slice(0, 50)
})

// Preview value switcher
const previewResolution = ref('4k')
const previewVideoCodec = ref('hevc')
const previewCodec = ref('atmos')
const previewAudioChannels = ref('6')
const previewAudioLanguage = ref('en')
const previewEdition = ref('theatrical')
const previewStreamingPlatform = ref('netflix')
const previewStudio = ref('a24')
// Condition test values (overlay engine v2)
const previewLabels = ref('')
const previewFilePath = ref('')
const previewRating = ref('8.0')
const previewItemLabels = ref<string[]>([])
const previewItemFilePaths = ref<string[]>([])
const previewItemLists = ref<string[]>([])
const previewCriticRating = ref('7.5')
const previewDaysAdded = ref('3')
const previewShowStatus = ref('continuing')
// Test mode: lists (by URL) the pretend item is on.
const previewOnLists = ref<Set<string>>(new Set())

const previewMetadataValues: Record<string, Ref<string>> = {
  video_resolution: previewResolution,
  video_codec: previewVideoCodec,
  audio_codec: previewCodec,
  audio_channels: previewAudioChannels,
  audio_language: previewAudioLanguage,
  edition: previewEdition,
  streaming_platform: previewStreamingPlatform,
  studio: previewStudio,
}

// Kometa import
const showKometaImport = ref(false)
const onKometaImported = async (ids: string[]) => {
  await Promise.all([loadConfigs(), loadAssets(), loadFonts()])
  const first = configs.value.find(c => c.id === ids[0])
  if (first) editConfig(first)
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

const loadSimposterAssets = async () => {
  try {
    const res = await fetch(`${apiBase}/api/simposter-assets-map`)
    if (res.ok) {
      const data = await res.json()
      simposterAssetMap.value = data.assets || {}
    }
  } catch (e) {
    console.warn('Failed to load simposter assets map:', e)
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

const loadPreviewLibraries = async () => {
  if (previewLibraries.value.length > 0) return
  previewLibrariesLoading.value = true
  try {
    // Every connected server's libraries (Plex, Jellyfin, Emby), so a Plex-less
    // install can preview overlays on its own items too.
    const res = await fetch(`${apiBase}/api/media-server/libraries`)
    if (res.ok) {
      const data = await res.json()
      const libs = (data.libraries || []) as Array<{ serverId: string; libraryId: string; libraryName: string; mediaType: string }>
      const multiServer = new Set(libs.map(l => l.serverId)).size > 1
      previewLibraries.value = libs
        .filter(l => l.mediaType === 'movie' || l.mediaType === 'tv')
        .map(l => ({
          key: String(l.libraryId),
          title: multiServer ? `${l.libraryName} (${mediaServerLabel(l.serverId, settingsStore.mediaServers.value)})` : l.libraryName,
          type: l.mediaType === 'tv' ? 'show' : 'movie',
          server: l.serverId,
        }))
    }
    if (!previewLibraries.value.length) {
      // Older setups without a media server list: Plex's own sections.
      const plexRes = await fetch(`${apiBase}/api/test-plex-connection`)
      if (plexRes.ok) {
        const data = await plexRes.json()
        previewLibraries.value = (data.sections || []).filter((s: any) => s.type === 'movie' || s.type === 'show')
      }
    }
  } catch (e) {
    console.error('Failed to load libraries:', e)
  } finally {
    previewLibrariesLoading.value = false
  }
}

const loadMoviesForLibrary = async (lib: {key: string, title: string, type: string, server?: string}) => {
  moviesLoaded.value = false
  movies.value = []
  try {
    const endpoint = lib.type === 'show' ? `/api/tv-shows` : `/api/movies`
    const serverParam = lib.server && lib.server !== 'plex-1' ? `&server_id=${encodeURIComponent(lib.server)}` : ''
    const res = await fetch(`${apiBase}${endpoint}?library_id=${encodeURIComponent(lib.key)}${serverParam}`)
    if (res.ok) {
      const data = await res.json()
      movies.value = (Array.isArray(data) ? data : []).map((m: any) => ({ key: m.key, title: m.title }))
    }
  } catch (e) {
    console.error('Failed to load items:', e)
  } finally {
    moviesLoaded.value = true
  }
}

// What the open overlay looked like when opened/saved, to warn before throwing edits away.
let savedSnapshot = ''
const snapshotOf = (c: OverlayConfig | null) => (c ? JSON.stringify(c) : '')
const hasUnsavedChanges = () => !!selectedConfig.value && snapshotOf(selectedConfig.value) !== savedSnapshot
const closeEditor = () => {
  if (hasUnsavedChanges() && !confirm('You have unsaved changes to this overlay. Close without saving?')) return
  showEditor.value = false
}
const onEditorKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && showEditor.value && !showMovieSearch.value && !showAssetUpload.value) closeEditor()
}

const createNewConfig = () => {
  elementFilter.value = ''
  expandedEls.value = new Set()
  selectedConfig.value = {
    id: `overlay-${Date.now()}`,
    name: 'New overlay',
    elements: [],
    streaming_region: 'US',
  }
  savedSnapshot = snapshotOf(selectedConfig.value)
  showEditor.value = true
}

/** Old "Show/Hide if Label" fields become ordinary label conditions (same behaviour). */
const migrateLegacyLabels = (els: OverlayElement[]) => {
  for (const el of els) {
    const conds = [...(el.conditions || [])]
    if (el.show_if_label) conds.push({ field: 'label', op: 'eq', value: el.show_if_label })
    if (el.hide_if_label) conds.push({ field: 'label', op: 'ne', value: el.hide_if_label })
    if (conds.length !== (el.conditions?.length || 0)) el.conditions = conds
    delete el.show_if_label
    delete el.hide_if_label
  }
}

const editConfig = (config: OverlayConfig) => {
  leftTab.value = 'layers'
  selectedConfig.value = JSON.parse(JSON.stringify(config))
  migrateLegacyLabels(selectedConfig.value?.elements || [])
  elementFilter.value = ''
  // Small configs open fully expanded; big (e.g. imported) ones start collapsed.
  const els = selectedConfig.value?.elements || []
  expandedEls.value = new Set(els.length <= 3 ? els.map(e => toRaw(e)) : [])
  // Taken after the label migration: converting old fields alone isn't an edit worth a warning.
  savedSnapshot = snapshotOf(selectedConfig.value)
  showEditor.value = true
}

// After saving an overlay that tracked posters were sent with, offer to refresh them.
const refreshPrompt = ref<{ configId: string; configName: string; groups: any[] } | null>(null)

const offerRefresh = async (configId: string, configName: string) => {
  try {
    const res = await fetch(`${apiBase}/api/overlay-refresh/by-overlay?config_id=${encodeURIComponent(configId)}`)
    if (!res.ok) return
    const data = await res.json()
    if (data.total > 0) refreshPrompt.value = { configId, configName, groups: data.groups }
  } catch (e) {
    console.error('Failed to look up posters using this overlay:', e)
  }
}

const saveConfig = async () => {
  if (!selectedConfig.value) return
  const changed = hasUnsavedChanges()
  const savedId = selectedConfig.value.id
  const savedName = selectedConfig.value.name || 'this overlay'
  try {
    const res = await fetch(`${apiBase}/api/overlay-configs/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // Always send conditions, so removing the last one clears them (null keeps the stored ones).
      body: JSON.stringify({ ...selectedConfig.value, conditions: selectedConfig.value.conditions || [] })
    })
    if (res.ok) {
      await loadConfigs()
      savedSnapshot = snapshotOf(selectedConfig.value)
      showEditor.value = false
      selectedConfig.value = null
      if (changed && savedId) offerRefresh(savedId, savedName)
    } else {
      alert('Failed to save overlay')
    }
  } catch (e) {
    console.error('Failed to save overlay config:', e)
    alert('Failed to save overlay')
  }
}

const deleteConfig = async (configId: string) => {
  let message = 'Delete this overlay?'
  try {
    const usageRes = await fetch(`${apiBase}/api/overlay-configs/${configId}/usage`)
    if (usageRes.ok) {
      const usage = await usageRes.json()
      if (usage.count > 0) {
        const names = usage.presets.map((p: { name: string }) => p.name).join(', ')
        message = `This overlay is tied to these presets: ${names}. Still want to delete? It will be removed from those presets.`
      }
    }
  } catch {
    // Usage check failed — fall back to the generic message rather than blocking delete
  }
  if (!confirm(message)) return
  try {
    const res = await fetch(`${apiBase}/api/overlay-configs/${configId}`, { method: 'DELETE' })
    if (res.ok) {
      await loadConfigs()
    } else {
      alert('Failed to delete overlay')
    }
  } catch (e) {
    console.error('Failed to delete overlay config:', e)
    alert('Failed to delete overlay')
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
  if (!confirm('Delete this image?')) return
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
    defaults.badge_urls = {}
    defaults.font_size = 40
    defaults.font_color = '#FFFFFF'
    defaults.font_family = 'Arial'
  } else if (type === 'audio_badge') {
    defaults.metadata_field = 'audio_codec'
    defaults.badge_modes = {}
    defaults.badge_assets = {}
    defaults.badge_texts = {}
    defaults.badge_urls = {}
    defaults.font_size = 30
    defaults.font_color = '#FFFFFF'
    defaults.font_family = 'Arial'
  } else if (type === 'edition_badge') {
    defaults.metadata_field = 'edition'
    defaults.badge_modes = {}
    defaults.badge_assets = {}
    defaults.badge_texts = {}
    defaults.badge_urls = {}
    defaults.font_size = 30
    defaults.font_color = '#FFFFFF'
    defaults.font_family = 'Arial'
  } else if (type === 'streaming_platform_badge') {
    defaults.metadata_field = 'streaming_platform'
    defaults.badge_modes = {}
    defaults.badge_assets = {}
    defaults.badge_texts = Object.fromEntries(STREAMING_PLATFORM_VALUES.map(v => [v, STREAMING_PLATFORM_LABELS[v] || v]))
    defaults.badge_urls = {}
    defaults.font_size = 30
    defaults.font_color = '#FFFFFF'
    defaults.font_family = 'Arial'
  } else if (type === 'studio_badge') {
    defaults.metadata_field = 'studio'
    defaults.badge_modes = {}
    defaults.badge_assets = {}
    defaults.badge_texts = Object.fromEntries(STUDIO_VALUES.map(v => [v, STUDIO_LABELS[v] || v]))
    defaults.badge_urls = {}
    defaults.font_size = 30
    defaults.font_color = '#FFFFFF'
    defaults.font_family = 'Arial'
  } else if (type === 'text_label') {
    defaults.font_size = 40
    defaults.font_color = '#FFFFFF'
    defaults.font_family = 'Arial'
    defaults.text = ''
  } else if (type === 'blur') {
    defaults.blur_amount = 20
  }

  selectedConfig.value.elements.push({
    type,
    position_x: 0.5,
    position_y: 0.5,
    ...defaults
  })
  showAddMenu.value = false
  elementFilter.value = ''
  const added = selectedConfig.value.elements[selectedConfig.value.elements.length - 1]
  if (added) revealElement(added)
}

// --------------------------------------------------------------------------
// Element list: collapsible cards, search, add menu, reorder
// --------------------------------------------------------------------------

const ADD_MENU = [
  { title: 'Badges that change with each movie', items: [
    { type: 'video_badge', label: 'Video', hint: 'Resolution or video codec' },
    { type: 'audio_badge', label: 'Audio', hint: 'Codec, channels or language' },
    { type: 'edition_badge', label: 'Edition', hint: "Director's Cut, IMAX..." },
    { type: 'streaming_platform_badge', label: 'Streaming', hint: 'Where it streams (TMDb)' },
    { type: 'studio_badge', label: 'Studio', hint: 'Studio or network logo' },
  ] },
  { title: 'Your own images and text', items: [
    { type: 'custom_image', label: 'Image', hint: 'One of your images, or a link' },
    { type: 'text_label', label: 'Text', hint: 'Any text, e.g. {audience_rating}' },
    { type: 'full_cover_image', label: 'Full-poster image', hint: 'A frame or border over the whole poster' },
    { type: 'blur', label: 'Blur', hint: 'Blurs the poster under the other layers' },
  ] },
]

const showAddMenu = ref(false)
const elementFilter = ref('')
const expandedEls = shallowRef(new Set<object>())
const elementIds = new WeakMap<object, number>()
let nextElementId = 1
const elementKey = (el: OverlayElement): number => {
  const raw = toRaw(el)
  let id = elementIds.get(raw)
  if (!id) { id = nextElementId++; elementIds.set(raw, id) }
  return id
}
const isExpanded = (el: OverlayElement) => expandedEls.value.has(toRaw(el))
const toggleExpanded = (el: OverlayElement) => {
  const next = new Set(expandedEls.value)
  const raw = toRaw(el)
  if (next.has(raw)) next.delete(raw)
  else next.add(raw)
  expandedEls.value = next
}
const setAllExpanded = (open: boolean) => {
  const els = filteredElements.value.map(f => toRaw(f.element))
  const next = new Set(expandedEls.value)
  for (const raw of els) {
    if (open) next.add(raw)
    else next.delete(raw)
  }
  expandedEls.value = next
}
const revealElement = (el: OverlayElement) => {
  const raw = toRaw(el)
  if (!expandedEls.value.has(raw)) expandedEls.value = new Set([...expandedEls.value, raw])
  nextTick(() => {
    document.querySelector(`[data-el-key="${elementKey(el)}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
}

type ElementTab = 'look' | 'position' | 'when'
const elementTabs = ref<Record<number, ElementTab>>({})
const tabOf = (el: OverlayElement): ElementTab => elementTabs.value[elementKey(el)] || 'look'
const setTab = (el: OverlayElement, tab: ElementTab) => { elementTabs.value = { ...elementTabs.value, [elementKey(el)]: tab } }

const filteredElements = computed(() => {
  const els = selectedConfig.value?.elements || []
  const q = elementFilter.value.trim().toLowerCase()
  return els
    .map((element, idx) => ({ element, idx }))
    .filter(({ element }) => {
      if (!q) return true
      const hay = [element.name, elementTypeLabel(element.type), element.group, element.text, element.metadata_field]
        .filter(Boolean).join(' ').toLowerCase()
      return hay.includes(q)
    })
})

// Shown top-down in layer order: the first card is drawn last, i.e. on top.
const displayElements = computed(() => [...filteredElements.value].reverse())

// Badge types and the media field each one shows by default.
const BADGE_DEFAULT_FIELD: Record<string, string> = {
  video_badge: 'video_resolution', resolution_badge: 'video_resolution',
  audio_badge: 'audio_codec', codec_badge: 'audio_codec',
  edition_badge: 'edition', streaming_platform_badge: 'streaming_platform', studio_badge: 'studio',
}

/** Problems that make a layer show nothing (or not what was meant). Shown as a warning on its card. */
const layerWarnings = (el: OverlayElement): string[] => {
  const out: string[] = []
  if (BADGE_DEFAULT_FIELD[el.type]) {
    const keys = [...new Set([...Object.keys(el.badge_modes || {}), '__other__'])]
    const mode = (v: string) => getBadgeMode(el, v)
    if (keys.every(v => mode(v) === 'none')) out.push('Set to show nothing for every value, so it never appears.')
    const label = (v: string) => (v === '__other__' ? 'other values' : v.toUpperCase())
    const noImage = keys.filter(v => mode(v) === 'image' && !(el.badge_assets?.[v] || (v !== '__other__' && el.badge_assets?.['__other__'])))
    if (noImage.length) out.push(`No image picked for ${noImage.map(label).join(', ')}.`)
    const noUrl = keys.filter(v => mode(v) === 'url' && !(el.badge_urls?.[v] || (v !== '__other__' && el.badge_urls?.['__other__'])))
    if (noUrl.length) out.push(`No link entered for ${noUrl.map(label).join(', ')}.`)
  }
  if ((el.type === 'custom_image' || el.type === 'full_cover_image') && !el.asset_id && !el.url) out.push('No image picked yet.')
  if (el.type === 'text_label' && !String(el.text || '').trim() && !el.box_only) out.push('No text entered yet.')
  if (el.box_only && !el.back_color && !(Number(el.back_line_width) > 0)) out.push('This box has no color or border, so it draws nothing.')
  for (const c of el.conditions || []) {
    const field = String(c.field || '')
    if (!field) out.push('A "Show when" condition has no field picked.')
    else if (field.startsWith('_')) out.push('A "Show when" condition came from Kometa and can never match, so this layer never shows.')
    else if (!fieldDef(field)) out.push(`"Show when" uses "${field}", which Simposter doesn't know.`)
    else if (!opDef(String(c.op || 'eq'))?.noValue) {
      const vals = Array.isArray(c.value) ? c.value : [c.value]
      if (!vals.some(v => v !== undefined && v !== null && String(v).trim() !== '')) out.push(`The "${fieldDef(field)?.label}" condition has no value.`)
    }
  }
  const names = new Set((selectedConfig.value?.elements || []).map(e => e.name).filter(Boolean))
  const missing = (el.suppress || []).filter(n => !names.has(n))
  if (missing.length) out.push(`Hides ${missing.map(n => `"${n}"`).join(', ')}, which no layer is called anymore.`)
  return out
}

/** What a layer's Look tab is for, shown at its top. */
const TYPE_HELP: Record<string, string> = {
  video_badge: 'Changes with each movie. Pick a field, then choose what to show for each value (an image, text, or nothing).',
  resolution_badge: 'Changes with each movie. Choose what to show for each resolution.',
  audio_badge: 'Changes with each movie. Pick a field, then choose what to show for each value (an image, text, or nothing).',
  codec_badge: 'Changes with each movie. Choose what to show for each audio codec.',
  edition_badge: "Shows the movie's edition (Plex only), e.g. Director's Cut or IMAX.",
  streaming_platform_badge: 'Shows where the movie streams, looked up on TMDb for the region at the top.',
  studio_badge: 'Shows the studio or TV network logo.',
  custom_image: 'Always the same image. Use "Show when" to put it only on some posters.',
  text_label: 'Any text. Words in {curly braces} are filled in per movie, e.g. {audience_rating}.',
  full_cover_image: 'Stretched over the whole poster, e.g. a frame or border. Use a PNG with a see-through middle.',
  blur: 'Blurs the poster under the other layers of this overlay (Kometa blur). With several blur layers, the strongest one is used.',
}

const moveElement = (idx: number, dir: -1 | 1) => {
  const els = selectedConfig.value?.elements
  const to = idx + dir
  if (!els || to < 0 || to >= els.length) return
  const [el] = els.splice(idx, 1)
  if (el) els.splice(to, 0, el)
}

const duplicateElement = (idx: number) => {
  const els = selectedConfig.value?.elements
  const el = els?.[idx]
  if (!els || !el) return
  const copy: OverlayElement = JSON.parse(JSON.stringify(el))
  if (copy.name) copy.name = `${copy.name} copy`
  els.splice(idx + 1, 0, copy)
  const added = els[idx + 1]
  if (added) revealElement(added)
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
    streaming_platform_badge: 'Streaming Badge',
    studio_badge: 'Studio Badge',
    custom_image: 'Image',
    full_cover_image: 'Full-poster image',
    text_label: 'Text',
    blur: 'Blur',
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
    streaming_platform_badge: '#10b981',
    studio_badge: '#f97316',
    custom_image: '#34d399',
    full_cover_image: '#22d3ee',
    text_label: '#fbbf24',
    blur: '#94a3b8',
    // Legacy types
    resolution_badge: '#60a5fa',
    codec_badge: '#a78bfa',
    label_badge: '#f472b6',
  }
  return colors[type] || '#60a5fa'
}

// Badge mode/asset helpers
// Appends the '__other__' catch-all row to any badge value list
const withOther = (vals: string[]): string[] => [...vals, '__other__']

// Display label for badge value rows; '__other__' shows as "Other (unrecognized)"
const badgeValueLabel = (val: string, labels?: Record<string, string>): string => {
  if (val === '__other__') return 'Other (unrecognized)'
  return labels?.[val] || val.toUpperCase()
}

const getBadgeMode = (element: OverlayElement, value: string): string => {
  // Match canvas resolution: specific value → __other__ fallback → default 'text'
  if (value === '__other__') return element.badge_modes?.['__other__'] ?? 'text'
  return element.badge_modes?.[value] ?? element.badge_modes?.['__other__'] ?? 'text'
}

// Returns true if the value has ANY explicit setting (not just inheriting from __other__)
const hasExplicitOverride = (element: OverlayElement, val: string): boolean =>
  element.badge_modes?.[val] !== undefined ||
  element.badge_scales?.[val] != null ||
  element.badge_anchors?.[val] != null

const getExplicitOverrides = (element: OverlayElement, values: string[]): string[] =>
  values.filter(v => hasExplicitOverride(element, v))

const getAvailableForOverride = (element: OverlayElement, values: string[]): string[] =>
  values.filter(v => !hasExplicitOverride(element, v))

const addBadgeOverride = (element: OverlayElement, val: string) => {
  if (!val || val === '__other__') return
  if (!element.badge_modes) element.badge_modes = {}
  // Start from the current __other__ setting so the override looks right immediately
  element.badge_modes[val] = element.badge_modes?.['__other__'] || 'asset'
  const defScale = element.badge_scales?.['__other__']
  const defAnchor = element.badge_anchors?.['__other__']
  if (defScale != null) { if (!element.badge_scales) element.badge_scales = {}; element.badge_scales[val] = defScale }
  if (defAnchor) { if (!element.badge_anchors) element.badge_anchors = {}; element.badge_anchors[val] = defAnchor }
}

const removeBadgeOverride = (element: OverlayElement, val: string) => {
  if (element.badge_modes) delete element.badge_modes[val]
  if (element.badge_scales) delete element.badge_scales[val]
  if (element.badge_anchors) delete element.badge_anchors[val]
  if (element.badge_texts) delete element.badge_texts[val]
  if (element.badge_assets) delete element.badge_assets[val]
  if (element.badge_urls) delete element.badge_urls[val]
}

// Slug alias helpers — map TMDb slugs to canonical asset slugs
const pendingAliasFrom = ref('')
const pendingAliasTo = ref('')

const addSlugAlias = (element: OverlayElement, from: string, to: string) => {
  const f = from.trim().toLowerCase()
  const t = to.trim().toLowerCase()
  if (!f || !t) return
  if (!element.slug_aliases) element.slug_aliases = {}
  element.slug_aliases[f] = t
  pendingAliasFrom.value = ''
  pendingAliasTo.value = ''
}

const removeSlugAlias = (element: OverlayElement, from: string) => {
  if (element.slug_aliases) delete element.slug_aliases[from]
}

const setBadgeMode = (element: OverlayElement, value: string, mode: string) => {
  if (!element.badge_modes) element.badge_modes = {}
  element.badge_modes[value] = mode
  // Clear image-specific overrides when switching away from image/asset
  if (mode !== 'image') {
    if (element.badge_assets?.[value]) delete element.badge_assets[value]
    if (mode !== 'url' && mode !== 'asset') {
      if (element.badge_scales?.[value] != null) delete element.badge_scales[value]
      if (element.badge_anchors?.[value]) delete element.badge_anchors[value]
    }
  }
}

const getBadgeUrl = (element: OverlayElement, value: string): string => {
  return element.badge_urls?.[value] ?? ''
}

const setBadgeUrl = (element: OverlayElement, value: string, url: string) => {
  if (!element.badge_urls) element.badge_urls = {}
  if (url) {
    element.badge_urls[value] = url
  } else {
    delete element.badge_urls[value]
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
    : element.type === 'streaming_platform_badge'
    ? 'streaming_platform'
    : element.type === 'studio_badge'
    ? 'studio'
    : (element.metadata_field || 'video_resolution')
  const allValues = withOther(getValuesForField(field))
  // Return true if any value's effective mode is "text" (unset defaults to "text")
  return allValues.some(v => (element.badge_modes?.[v] ?? 'text') === 'text')
}

// --- Poster search ---

const backToLibraries = () => {
  previewSelectedLibrary.value = null
  movies.value = []
  moviesLoaded.value = false
  movieSearchTerm.value = ''
}

const openMovieSearch = async () => {
  backToLibraries()
  showMovieSearch.value = true
  await loadPreviewLibraries()
}

const selectLibrary = async (lib: {key: string, title: string, type: string, server?: string}) => {
  previewSelectedLibrary.value = lib
  movieSearchTerm.value = ''
  await loadMoviesForLibrary(lib)
}

interface ItemData { metadata: Record<string, string>; labels: string[]; file_paths: string[]; lists: string[] }

// Rating fields (MDBList), for conditions and {text} values.
const RATING_KEYS = new Set([
  ...FIELDS.filter(f => f.group === 'Ratings').map(f => f.value),
  ...TEXT_VARIABLES.filter(v => v.group === 'Ratings').map(v => v.key),
])
const TEXT_VAR_RE = /\{([A-Za-z0-9_.]+)\}/g
const textKeys = (el: OverlayElement): string[] => [...String(el.text || '').matchAll(TEXT_VAR_RE)].map(m => m[1] as string)

/** What the current layers (saved or not) need from a real item, sent with the metadata request. */
const itemNeeds = computed(() => {
  const els = selectedConfig.value?.elements || []
  const ratings = els.some(el =>
    textKeys(el).some(k => RATING_KEYS.has(k)) || (el.conditions || []).some(c => RATING_KEYS.has(String(c.field || '').toLowerCase())))
    || (selectedConfig.value?.conditions || []).some(c => RATING_KEYS.has(String(c.field || '').toLowerCase()))
  const types = [...new Set(els.map(e => e.type).filter(t => t === 'streaming_platform_badge' || t === 'studio_badge'))].sort()
  // Item data fields filled on request (date added, show status).
  const used = new Set<string>()
  for (const c of [...els.flatMap(el => el.conditions || []), ...(selectedConfig.value?.conditions || [])]) {
    const f = String(c.field || '').toLowerCase()
    if (f === 'days_since_added' || f === 'show_status') used.add(f)
  }
  for (const el of els) for (const k of textKeys(el)) if (k === 'days_since_added' || k === 'show_status') used.add(k)
  return { ratings, lists: configLists.value, types, fields: [...used].sort() }
})
const itemNeedsKey = computed(() => JSON.stringify(itemNeeds.value))

const loadItemData = async (ratingKey: string, mediaType: string): Promise<ItemData | null> => {
  try {
    const params = new URLSearchParams({ rating_key: ratingKey })
    if (selectedConfig.value?.id) params.set('config_id', selectedConfig.value.id)
    params.set('media_type', mediaType)
    const needs = itemNeeds.value
    if (needs.ratings) params.set('ratings', 'true')
    if (needs.lists.length) params.set('lists', needs.lists.join(','))
    if (needs.types.length) params.set('badge_types', needs.types.join(','))
    if (needs.fields.length) params.set('fields', needs.fields.join(','))
    const res = await fetch(`${apiBase}/api/overlay-preview-metadata?${params}`)
    if (!res.ok) return null
    const data = await res.json()
    return { metadata: data.metadata || {}, labels: data.labels || [], file_paths: data.file_paths || [], lists: data.lists || [] }
  } catch (e) {
    console.error('Failed to fetch item metadata:', e)
    return null
  }
}

const loadPosterImage = (key: string) => new Promise<HTMLImageElement | null>(resolve => {
  const img = new Image()
  img.crossOrigin = 'anonymous'
  img.onload = () => resolve(img)
  img.onerror = () => resolve(null)
  img.src = `${apiBase}/api/movie/${key}/poster?raw=1`
})

const fetchItemMetadata = async (ratingKey: string) => {
  const d = await loadItemData(ratingKey, previewSelectedLibrary.value?.type === 'show' ? 'tv' : 'movie')
  if (!d) return
  previewItemMetadata.value = d.metadata
  previewItemLabels.value = d.labels
  previewItemFilePaths.value = d.file_paths
  previewItemLists.value = d.lists
}

const selectMovie = async (movie: SimpleMovie) => {
  showMovieSearch.value = false
  if (pickForCompare) {
    pickForCompare = false
    await addCompareItem(movie)
    return
  }
  selectedMovie.value = movie
  previewItemMetadata.value = {}
  previewItemLabels.value = []
  previewItemFilePaths.value = []
  previewItemLists.value = []
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
  } catch (e) {
    console.error('Failed to load poster:', e)
    posterBgImage.value = null
  } finally {
    posterLoading.value = false
  }
  if (switchToItemAfterPick) {
    switchToItemAfterPick = false
    previewMode.value = 'item'
  } else if (previewMode.value === 'item') {
    await fetchItemMetadata(movie.key)
  }
  renderPreview()
}

const clearPoster = () => {
  selectedMovie.value = null
  previewMode.value = 'testing'
  posterBgImage.value = null
  previewItemMetadata.value = {}
  previewItemLabels.value = []
  previewItemFilePaths.value = []
  previewItemLists.value = []
  nextTick(renderPreview)
}

// Item mode uses only the picked item's real values (an empty value stays empty,
// it must not fall back to the Test-mode inputs).
const isItemMode = computed(() => previewMode.value === 'item' && !!selectedMovie.value)

// One preview canvas: what to draw on, and the values its layers are checked against.
type PreviewCtx = ReturnType<typeof buildContext>
interface Scene {
  key: string
  canvas: HTMLCanvasElement
  bg: HTMLImageElement | null
  value: (field: string) => string
  ctx: PreviewCtx
  meta: Record<string, string>
  visible: Set<number>
  /** Only the main preview shows hover outlines and can be dragged on. */
  interactive: boolean
}
const sceneVers: Record<string, number> = {}
const isStale = (scene: Scene, ver: number) => sceneVers[scene.key] !== ver

const getPreviewValue = (field: string): string => {
  if (isItemMode.value) return previewItemMetadata.value[field] || ''
  return previewMetadataValues[field]?.value || ''
}

// Elements whose rules hide them for the current values are left out of the
// preview, unless this is on (then they're drawn faintly so they can be edited).
const showHiddenInPreview = ref(false)
try { showHiddenInPreview.value = localStorage.getItem('simposter-overlay-show-hidden') === '1' } catch { /* ignore */ }
watch(showHiddenInPreview, v => {
  try { localStorage.setItem('simposter-overlay-show-hidden', v ? '1' : '0') } catch { /* ignore */ }
  nextTick(renderPreview)
})

/** Context from a real item's data. */
const itemContext = (d: ItemData, mediaType: string, title?: string) => buildContext({
  ...d.metadata, media_type: mediaType, labels: d.labels, file_paths: d.file_paths, lists: d.lists,
  ...(title ? { movie_title: title } : {}),
})

/** Context from the example values, with some fields swapped (used by compare tiles). */
const exampleContext = (overrides: Record<string, string> = {}, title?: string) => {
  const meta: Record<string, unknown> = {}
  for (const field of Object.keys(previewMetadataValues)) meta[field] = overrides[field] ?? previewMetadataValues[field]?.value ?? ''
  meta.labels = previewLabels.value.split(',').map(s => s.trim()).filter(Boolean)
  meta.file_paths = previewFilePath.value.trim() ? [previewFilePath.value.trim()] : []
  if (String(previewRating.value).trim() !== '') meta.audience_rating = Number(previewRating.value)
  if (String(previewCriticRating.value).trim() !== '') meta.critic_rating = Number(previewCriticRating.value)
  if (String(previewDaysAdded.value).trim() !== '') meta.days_since_added = Number(previewDaysAdded.value)
  if (previewShowStatus.value) meta.show_status = previewShowStatus.value
  meta.lists = [...previewOnLists.value]
  if (title) meta.movie_title = title
  // Ratings without a test box (IMDb, Rotten Tomatoes, ...) use the list's example values.
  for (const v of TEXT_VARIABLES) {
    if (v.group === 'Ratings' && meta[v.key] === undefined) meta[v.key] = Number(v.example)
  }
  return buildContext(meta)
}

// Data the preview evaluates element conditions against (same rules as the backend).
const previewContext = computed(() => {
  if (isItemMode.value) {
    const meta: Record<string, string> = {}
    for (const field of Object.keys(previewMetadataValues)) meta[field] = getPreviewValue(field)
    return itemContext(
      { metadata: { ...meta, ...previewItemMetadata.value }, labels: previewItemLabels.value, file_paths: previewItemFilePaths.value, lists: previewItemLists.value },
      previewSelectedLibrary.value?.type === 'show' ? 'tv' : 'movie',
      selectedMovie.value?.title,
    )
  }
  return exampleContext({}, selectedMovie.value?.title)
})

const configLists = computed(() => selectedConfig.value
  ? referencedLists([...selectedConfig.value.elements, { conditions: selectedConfig.value.conditions || [] }])
  : [])
const togglePreviewList = (url: string) => {
  const next = new Set(previewOnLists.value)
  if (next.has(url)) next.delete(url)
  else next.add(url)
  previewOnLists.value = next
}
const listShortName = (url: string) => listDisplayName(url)
// List names for rule summaries and the test-mode list checkboxes.
useListSources().load()

/** Do the overlay's own conditions match this preview? */
const overlayPasses = (ctx: PreviewCtx) => (selectedConfig.value?.conditions || []).every(c => checkCondition(c, ctx))
/** Layers drawn for a preview: none when the overlay's own conditions fail. */
const selectVisible = (ctx: PreviewCtx) =>
  selectedConfig.value && overlayPasses(ctx) ? selectElementIndices(selectedConfig.value.elements, ctx) : new Set<number>()
const visibleElements = computed(() => selectVisible(previewContext.value))
const overlayMatchesPreview = computed(() => overlayPasses(previewContext.value))

const hasAnyRules = computed(() =>
  (selectedConfig.value?.elements || []).some(e => e.conditions?.length || e.group || e.suppress?.length || e.placement === 'kometa')
)

// Preview-space boxes of Kometa-placed elements (for hit testing and dragging).
const kometaBoxes = new Map<number, { x: number; y: number; w: number; h: number }>()
// Fonts on the Simposter server (uploaded, bundled or Kometa's) are loaded into
// the page so the preview draws text with the same font as the render.
const BROWSER_FONTS = new Set(['arial', 'helvetica', 'times new roman', 'georgia', 'verdana', 'courier new', 'impact'])
const serverFonts = new Map<string, 'loading' | 'ok' | 'none'>()
const fontFaceName = (family: string) => `sp-font-${family.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
/** CSS font string for a text layer; starts loading a server font the first time. */
const previewFont = (family: string | undefined, size: number, weight: string | number) => {
  const fam = (family || 'Arial').trim()
  const key = fam.toLowerCase()
  if (!BROWSER_FONTS.has(key)) {
    const state = serverFonts.get(key)
    // A server font file is one weight; asking for bold would make the browser fake it.
    if (state === 'ok') return `${size}px "${fontFaceName(fam)}", sans-serif`
    if (!state) {
      serverFonts.set(key, 'loading')
      const face = new FontFace(fontFaceName(fam), `url(${apiBase}/api/fonts/file?name=${encodeURIComponent(fam)})`)
      face.load()
        .then(f => { document.fonts.add(f); serverFonts.set(key, 'ok'); renderPreview() })
        .catch(() => serverFonts.set(key, 'none'))
    }
  }
  const bold = ['bold', '700', '800', '900'].includes(String(weight).toLowerCase())
  return `${bold ? 'bold ' : ''}${size}px "${fam}", sans-serif`
}

const isKometaPlaced = (el: OverlayElement) =>
  el.placement === 'kometa' && (el.type === 'text_label' || el.type === 'custom_image')
let dragGrab = { dx: 0, dy: 0 }

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
  const px = normX * PREVIEW_W, py = normY * PREVIEW_H
  for (let i = selectedConfig.value.elements.length - 1; i >= 0; i--) {
    const b = kometaBoxes.get(i)
    if (b && px >= b.x && px <= b.x + b.w && py >= b.y && py <= b.y + b.h) return i
  }
  const hitRadius = 25 / PREVIEW_W // ~25px radius in canvas space
  // Iterate in reverse so topmost element (last drawn) is hit first
  for (let i = selectedConfig.value.elements.length - 1; i >= 0; i--) {
    const el = selectedConfig.value.elements[i]
    if (!el || isKometaPlaced(el)) continue
    const dx = normX - el.position_x
    const dy = normY - el.position_y
    if (Math.sqrt(dx * dx + dy * dy) < hitRadius) return i
  }
  return null
}

const startDrag = (idx: number, pos: { x: number; y: number }) => {
  draggingIdx.value = idx
  hoveredElementIdx.value = idx
  const grabbed = selectedConfig.value?.elements[idx]
  if (grabbed) { setTab(grabbed, 'position'); revealElement(grabbed) }
  const b = kometaBoxes.get(idx)
  dragGrab = b ? { dx: pos.x * PREVIEW_W - b.x, dy: pos.y * PREVIEW_H - b.y } : { dx: 0, dy: 0 }
}

const moveDragged = (pos: { x: number; y: number }) => {
  if (draggingIdx.value === null || !selectedConfig.value) return
  const el = selectedConfig.value.elements[draggingIdx.value]
  if (!el) return
  const b = kometaBoxes.get(draggingIdx.value)
  if (isKometaPlaced(el) && b) {
    const nx = pos.x * PREVIEW_W - dragGrab.dx
    const ny = pos.y * PREVIEW_H - dragGrab.dy
    const o = offsetsFromBox(el, PREVIEW_W, PREVIEW_H, b.w, b.h, nx, ny)
    el.horizontal_offset = o.horizontal_offset
    el.vertical_offset = o.vertical_offset
    return
  }
  el.position_x = Math.round(Math.max(0, Math.min(1, pos.x)) * 1000) / 1000
  el.position_y = Math.round(Math.max(0, Math.min(1, pos.y)) * 1000) / 1000
}

const onCanvasMouseDown = (e: MouseEvent) => {
  if (!dragEnabled.value || !selectedConfig.value) return
  const pos = getCanvasMousePos(e)
  if (!pos) return
  const idx = hitTestElement(pos.x, pos.y)
  if (idx !== null) {
    startDrag(idx, pos)
    e.preventDefault()
  }
}

const onCanvasMouseMove = (e: MouseEvent) => {
  if (!dragEnabled.value || !selectedConfig.value) return

  const pos = getCanvasMousePos(e)
  if (!pos) return

  if (draggingIdx.value !== null) {
    moveDragged(pos)
    e.preventDefault()
  } else {
    // Hover feedback
    const idx = hitTestElement(pos.x, pos.y)
    hoveredElementIdx.value = idx
  }
}

const endDrag = () => {
  if (draggingIdx.value === null) return
  draggingIdx.value = null
  nextTick(renderPreview)
}
const onCanvasMouseUp = () => endDrag()

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
    startDrag(idx, pos)
    e.preventDefault()
  }
}

const onCanvasTouchMove = (e: TouchEvent) => {
  if (!dragEnabled.value || draggingIdx.value === null || !selectedConfig.value) return
  const pos = getTouchPos(e)
  if (!pos) return
  moveDragged(pos)
  e.preventDefault()
}

const onCanvasTouchEnd = () => endDrag()

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

const loadUrlImage = (url: string): Promise<HTMLImageElement> => {
  const proxyUrl = `${apiBase}/api/proxy-image?url=${encodeURIComponent(url)}`
  return new Promise((resolve, reject) => {
    if (urlImageCache.value[proxyUrl]) {
      resolve(urlImageCache.value[proxyUrl])
      return
    }
    const img = new Image()
    img.onload = () => {
      urlImageCache.value[proxyUrl] = img
      resolve(img)
    }
    img.onerror = reject
    img.src = proxyUrl
  })
}

// For URLs already served by this app's own backend (e.g. /api/asset-image) — load directly,
// no CORS-relay proxy needed. Routing a same-origin URL through /api/proxy-image makes it fetch
// itself over the LAN, which the proxy's SSRF guard correctly refuses.
const loadDirectImage = (url: string): Promise<HTMLImageElement> => {
  return new Promise((resolve, reject) => {
    if (urlImageCache.value[url]) {
      resolve(urlImageCache.value[url])
      return
    }
    const img = new Image()
    img.onload = () => {
      urlImageCache.value[url] = img
      resolve(img)
    }
    img.onerror = reject
    img.src = url
  })
}

// Normalize known URL patterns: GitHub blob viewer → raw CDN, strip ?raw suffix
const normalizeBadgeUrl = (url: string): string => {
  if (!url) return url
  const ghBlob = url.match(/^https?:\/\/github\.com\/([^/]+\/[^/]+)\/blob\/([^?#]+)/)
  if (ghBlob) return `https://raw.githubusercontent.com/${ghBlob[1]}/${ghBlob[2]}`
  return url.replace(/\?raw(=true)?$/i, '')
}

const prefetchBadgeUrl = (url: string) => {
  if (!url || !url.startsWith('http')) return
  loadUrlImage(url)
    .then(() => nextTick(renderPreview))
    .catch(() => {})
}

// Each canvas has its own render version (sceneVers): async renders check it after
// every image-load await, and a stale render aborts instead of overwriting a newer one.
const renderPreview = () => {
  if (!selectedConfig.value) return
  const canvas = previewCanvas.value
  if (canvas) {
    renderScene({
      key: 'main', canvas, bg: posterBgImage.value, value: getPreviewValue, ctx: previewContext.value,
      meta: previewItemMetadata.value, visible: visibleElements.value, interactive: true,
    })
  }
  // Compare posters aren't redrawn on every drag move, only when the drag ends.
  if (showCompare.value && draggingIdx.value === null) {
    for (const tile of compareTiles.value) {
      const c = compareCanvases.get(tile.id)
      if (c) renderScene(tileScene(tile, c))
    }
  }
}

const renderScene = async (scene: Scene) => {
  const ver = (sceneVers[scene.key] = (sceneVers[scene.key] || 0) + 1)
  const canvas = scene.canvas
  if (!selectedConfig.value) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  canvas.width = PREVIEW_W * dpr
  canvas.height = PREVIEW_H * dpr
  ctx.scale(dpr, dpr)

  // Background: poster image or gradient
  if (scene.bg) {
    const img = scene.bg
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

  // Kometa blur: blur what's drawn so far, like the backend does before the layers.
  const blurPx = blurAmount(selectedConfig.value.elements, scene.visible) * Math.min(PREVIEW_W / KOMETA_W, PREVIEW_H / KOMETA_H)
  if (blurPx > 0) {
    const copy = document.createElement('canvas')
    copy.width = ctx.canvas.width
    copy.height = ctx.canvas.height
    copy.getContext('2d')?.drawImage(ctx.canvas, 0, 0)
    ctx.save()
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.filter = `blur(${blurPx * (ctx.canvas.width / PREVIEW_W)}px)`
    ctx.drawImage(copy, 0, 0)
    ctx.restore()
  }

  // Poster border
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)'
  ctx.lineWidth = 1
  ctx.strokeRect(0.5, 0.5, PREVIEW_W - 1, PREVIEW_H - 1)

  // Grid guides (only without poster bg)
  if (!scene.bg) {
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

  // Render each element. Elements whose rules hide them for this item are drawn
  // faint so they can still be found and edited.
  if (scene.interactive) kometaBoxes.clear()
  const visible = scene.visible
  const queued = queuePlacements(selectedConfig.value.elements, visible)
  for (let idx = 0; idx < selectedConfig.value.elements.length; idx++) {
    if (isStale(scene, ver)) return  // A newer render has started; abort this stale one
    const raw = selectedConfig.value.elements[idx]
    if (!raw || raw.type === 'blur') continue
    // A queued layer takes its queue's position; past the last position it isn't drawn.
    const slot = queued.get(idx)
    if (queued.has(idx) && slot === null) continue
    const el: OverlayElement = slot ? { ...raw, ...slot, placement: 'kometa' } : raw
    const x = el.position_x * PREVIEW_W
    const y = el.position_y * PREVIEW_H
    const isHovered = scene.interactive && (hoveredElementIdx.value === idx || draggingIdx.value === idx)

    ctx.save()
    if (!visible.has(idx)) {
      // Compare tiles always leave skipped layers out: they show the real result.
      if (!scene.interactive || (!showHiddenInPreview.value && !isHovered)) { ctx.restore(); continue }
      ctx.globalAlpha = isHovered ? 0.5 : 0.2
    }
    // Layer numbers are only drawn on the main preview (-1 = don't draw).
    const drawIdx = scene.interactive ? idx : -1
    if (isKometaPlaced(el)) await renderKometaPreview(ctx, el, drawIdx, isHovered, ver, scene)
    else await renderPreviewElement(ctx, el, x, y, drawIdx, isHovered, ver, scene)
    if (slot && scene.interactive) kometaBoxes.delete(idx)  // its position comes from the queue: not draggable
    ctx.restore()
  }
}

// Kometa-placed element: same layout math as backend/overlay_engine.py, scaled
// from Kometa's 1000x1500 space to the preview canvas.
const renderKometaPreview = async (
  ctx: CanvasRenderingContext2D, el: OverlayElement, idx: number, isHovered: boolean, ver: number, scene: Scene
) => {
  const s = Math.min(PREVIEW_W / KOMETA_W, PREVIEW_H / KOMETA_H)
  let cw = 0, ch = 0
  let drawContent: ((cx: number, cy: number) => void) | null = null

  if (el.box_only) {
    // Kometa "backdrop": only the box; a missing size fills the canvas.
    cw = 0
    ch = 0
  } else if (el.type === 'text_label') {
    const filled = fillText(el.text || '', scene.ctx)
    const text = filled ?? (el.text || 'Text')
    const size = Math.max(4, (el.font_size || 40) * s)
    const stroke = (el.stroke_width || 0) * s
    const font = previewFont(el.font_family, size, el.font_weight || '700')
    ctx.font = font
    const m = ctx.measureText(text)
    const asc = m.actualBoundingBoxAscent || size * 0.8
    const desc = m.actualBoundingBoxDescent || size * 0.2
    const tw = m.width + stroke * 2
    const th = asc + desc + stroke * 2
    cw = tw
    ch = th
    const missing = filled === null
    // Image next to the text (Kometa text addon), laid out like the backend.
    let addon: HTMLImageElement | null = null
    if (el.asset_id || el.url) {
      try {
        addon = el.asset_id ? await loadAssetImage(el.asset_id) : await loadUrlImage(el.url as string)
      } catch { addon = null }
      if (isStale(scene, ver)) return
    }
    let textX = 0, textY = 0, addX = 0, addY = 0, iw = 0, ih = 0
    if (addon) {
      const am = (el.addon_scale || 1) * s
      iw = addon.width * am
      ih = addon.height * am
      const off = (el.addon_offset || 0) * s
      const pos = (el.addon_position || 'left').toLowerCase()
      if (pos === 'left' || pos === 'right') {
        cw = tw + iw + off
        ch = Math.max(th, ih)
        if (pos === 'left') textX = iw + off
        else addX = tw + off
      } else {
        cw = Math.max(tw, iw)
        ch = th + ih + off
        textX = (cw - tw) / 2
        addX = (cw - iw) / 2
        if (pos === 'top') textY = ih + off
        else addY = th + off
      }
    }
    const addonImg = addon
    drawContent = (cx, cy) => {
      if (addonImg) ctx.drawImage(addonImg, cx + addX, cy + addY, iw, ih)
      ctx.font = font
      ctx.textAlign = 'left'
      ctx.textBaseline = 'alphabetic'
      const tx = cx + textX + stroke, ty = cy + textY + stroke + asc
      if (missing) ctx.globalAlpha *= 0.5
      if (stroke > 0) {
        ctx.lineJoin = 'round'
        ctx.lineWidth = stroke * 2
        ctx.strokeStyle = cssColor(el.stroke_color, '#000000')
        ctx.strokeText(text, tx, ty)
      }
      ctx.fillStyle = cssColor(el.font_color, '#FFFFFF')
      ctx.fillText(text, tx, ty)
    }
  } else {
    let img: HTMLImageElement | null = null
    try {
      if (el.asset_id) img = await loadAssetImage(el.asset_id)
      else if (el.url) img = await loadUrlImage(el.url)
    } catch { img = null }
    if (isStale(scene, ver)) return
    const mult = (el.scale || 1) * s
    if (img) {
      const im = img
      cw = im.width * mult
      ch = im.height * mult
      drawContent = (cx, cy) => ctx.drawImage(im, cx, cy, cw, ch)
    } else {
      cw = 120 * s
      ch = 60 * s
      drawContent = (cx, cy) => {
        ctx.strokeStyle = '#34d399'
        ctx.setLineDash([3, 3])
        ctx.strokeRect(cx, cy, cw, ch)
        ctx.setLineDash([])
      }
    }
  }

  const pad = (el.back_padding || 0) * s
  const bw = el.back_width ? el.back_width * s : el.box_only ? PREVIEW_W : cw + pad * 2
  const bh = el.back_height ? el.back_height * s : el.box_only ? PREVIEW_H : ch + pad * 2
  const { x, y } = placeBox(el, PREVIEW_W, PREVIEW_H, bw, bh)
  if (scene.interactive) kometaBoxes.set(idx, { x, y, w: bw, h: bh })

  const lineW = (el.back_line_width || 0) * s
  if (el.back_color || (lineW && el.back_line_color)) {
    const r = (el.back_radius || 0) * s
    ctx.beginPath()
    ctx.roundRect(x, y, bw, bh, r)
    if (el.back_color) {
      ctx.fillStyle = cssColor(el.back_color, 'transparent')
      ctx.fill()
    }
    if (lineW) {
      ctx.lineWidth = lineW
      ctx.strokeStyle = cssColor(el.back_line_color, '#FFFFFF')
      ctx.stroke()
    }
  }

  const align = (el.back_align || 'center').toLowerCase()
  let cx = x + (bw - cw) / 2
  let cy = y + (bh - ch) / 2
  if (align.includes('left')) cx = x + pad
  else if (align.includes('right')) cx = x + bw - pad - cw
  if (align.includes('top')) cy = y + pad
  else if (align.includes('bottom')) cy = y + bh - pad - ch
  drawContent?.(cx, cy)

  if (isHovered) {
    ctx.strokeStyle = '#fbbf24'
    ctx.lineWidth = 1.5
    ctx.strokeRect(x - 1, y - 1, bw + 2, bh + 2)
  }
  drawElementIndex(ctx, x, y, idx)
}

const renderPreviewElement = async (
  ctx: CanvasRenderingContext2D,
  el: OverlayElement,
  x: number,
  y: number,
  idx: number,
  isHovered: boolean,
  ver: number,
  scene: Scene,
) => {
  const scale = PREVIEW_W / 2000

  // Badge type rendering config
  const badgeConfig: Record<string, { defaultField: string; defaultFontSize: number; accent: string; accentRgba: string }> = {
    video_badge:               { defaultField: 'video_resolution',  defaultFontSize: 40, accent: '#60a5fa', accentRgba: 'rgba(96, 165, 250, 0.2)' },
    resolution_badge:          { defaultField: 'video_resolution',  defaultFontSize: 40, accent: '#60a5fa', accentRgba: 'rgba(96, 165, 250, 0.2)' },
    audio_badge:               { defaultField: 'audio_codec',       defaultFontSize: 30, accent: '#a78bfa', accentRgba: 'rgba(167, 139, 250, 0.2)' },
    codec_badge:               { defaultField: 'audio_codec',       defaultFontSize: 30, accent: '#a78bfa', accentRgba: 'rgba(167, 139, 250, 0.2)' },
    edition_badge:             { defaultField: 'edition',            defaultFontSize: 30, accent: '#f59e0b', accentRgba: 'rgba(245, 158, 11, 0.2)' },
    streaming_platform_badge:  { defaultField: 'streaming_platform', defaultFontSize: 30, accent: '#10b981', accentRgba: 'rgba(16, 185, 129, 0.2)' },
    studio_badge:              { defaultField: 'studio',             defaultFontSize: 30, accent: '#f97316', accentRgba: 'rgba(249, 115, 22, 0.2)' },
  }

  const cfg = badgeConfig[el.type]
  if (cfg) {
    const metaField = el.metadata_field || cfg.defaultField
    const value = scene.value(metaField)
    const mode = el.badge_modes?.[value] ?? el.badge_modes?.['__other__'] ?? 'text'

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
          if (isStale(scene, ver)) return  // stale render — a newer one has started
          // Apply per-value scale/anchor overrides for badge types
          const effectiveEl = {
            ...el,
            scale: el.badge_scales?.[value] ?? el.badge_scales?.['__other__'] ?? el.scale,
            anchor: el.badge_anchors?.[value] ?? el.badge_anchors?.['__other__'] ?? el.anchor,
          }
          drawAssetOnCanvas(ctx, img, effectiveEl, x, y, scale, idx, isHovered, cfg.accent)
          return
        } catch { /* fall through to text */ }
      }
    }
    if (mode === 'url') {
      const url = el.badge_urls?.[value]
      if (url) {
        try {
          const img = await loadUrlImage(url)
          if (isStale(scene, ver)) return  // stale render
          const effectiveEl = {
            ...el,
            scale: el.badge_scales?.[value] ?? el.badge_scales?.['__other__'] ?? el.scale,
            anchor: el.badge_anchors?.[value] ?? el.badge_anchors?.['__other__'] ?? el.anchor,
          }
          drawAssetOnCanvas(ctx, img, effectiveEl, x, y, scale, idx, isHovered, cfg.accent)
          return
        } catch { /* fall through */ }
      }
      // No URL set — show a dim placeholder so the element is still visible
      const fontSize = Math.max(4, Math.round((el.font_size || cfg.defaultFontSize) * scale))
      drawBadge(ctx, x, y, url ? 'URL?' : 'URL', fontSize, cfg.accent, cfg.accentRgba, idx, isHovered, el.text_align || 'center')
      return
    }
    if (mode === 'asset') {
      if (value) {
        try {
          // Resolve alias first (same logic as backend renderer)
          const resolvedSlug = el.slug_aliases?.[value] ?? value
          // Backend does full resolution: company_id → logos.json → overrides → heuristic
          let assetUrl = `${apiBase}/api/asset-image?slug=${encodeURIComponent(resolvedSlug)}`
          // Pass TMDb company_id for studio_badge so ID-based lookup takes priority
          if (el.type === 'studio_badge') {
            const cid = scene.meta['studio_company_id']
            if (cid) assetUrl += `&company_id=${encodeURIComponent(cid)}`
          }
          const img = await loadDirectImage(assetUrl)
          if (isStale(scene, ver)) return  // stale render
          const effectiveEl = {
            ...el,
            scale: el.badge_scales?.[value] ?? el.badge_scales?.['__other__'] ?? el.scale,
            anchor: el.badge_anchors?.[value] ?? el.badge_anchors?.['__other__'] ?? el.anchor,
          }
          drawAssetOnCanvas(ctx, img, effectiveEl, x, y, scale, idx, isHovered, cfg.accent)
          return
        } catch { /* fall through to placeholder */ }
      }
      // No slug or asset not found — show placeholder
      const fontSize = Math.max(4, Math.round((el.font_size || cfg.defaultFontSize) * scale))
      drawBadge(ctx, x, y, value ? value.toUpperCase() : 'ASSET', fontSize, cfg.accent, cfg.accentRgba, idx, isHovered, el.text_align || 'center')
      return
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
        if (isStale(scene, ver)) return  // stale render
        drawAssetOnCanvas(ctx, img, el, x, y, scale, idx, isHovered, '#34d399')
        return
      } catch { /* fallback */ }
      drawBadge(ctx, x, y, 'IMG?', 9, '#34d399', 'rgba(52, 211, 153, 0.2)', idx, isHovered)
    } else {
      drawBadge(ctx, x, y, 'IMG', 9, '#34d399', 'rgba(52, 211, 153, 0.15)', idx, isHovered)
    }
  } else if (el.type === 'full_cover_image') {
    if (el.asset_id || el.url) {
      try {
        const img = el.asset_id ? await loadAssetImage(el.asset_id) : await loadUrlImage(el.url as string)
        if (isStale(scene, ver)) return  // stale render
        ctx.drawImage(img, 0, 0, PREVIEW_W, PREVIEW_H)
        if (isHovered) {
          ctx.strokeStyle = '#22d3ee'
          ctx.lineWidth = 2
          ctx.strokeRect(1, 1, PREVIEW_W - 2, PREVIEW_H - 2)
        }
        drawElementIndex(ctx, 14, 14, idx)
        return
      } catch { /* fallback */ }
      drawBadge(ctx, PREVIEW_W / 2, PREVIEW_H / 2, 'IMG?', 9, '#22d3ee', 'rgba(34, 211, 238, 0.2)', idx, isHovered)
    } else {
      drawBadge(ctx, PREVIEW_W / 2, PREVIEW_H / 2, 'FULL COVER', 9, '#22d3ee', 'rgba(34, 211, 238, 0.15)', idx, isHovered)
    }
  } else if (el.type === 'text_label') {
    // Same as the real render: {variables} filled in; a missing value skips the layer
    // (drawn faint with the raw text so it can still be found and moved).
    const filled = fillText(el.text || '', scene.ctx)
    if (filled === null) {
      if (!scene.interactive) return
      ctx.globalAlpha *= 0.4
    }
    const text = filled || el.text || 'Text'
    const fontSize = Math.max(4, Math.round((el.font_size || 40) * scale))
    const color = el.font_color || '#FFFFFF'
    const align = (el.text_align || 'center') as CanvasTextAlign

    ctx.font = previewFont(el.font_family, fontSize, '700')
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

  // Width/height and max-size limits only apply to image layers, as in the real render
  // (backend/templates/universal.py: badges are drawn at their own size x scale, uncapped).
  if (el.type === 'custom_image') {
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
    if (el.max_width) {
      const maxW = el.max_width * scale
      if (drawW > maxW) { drawH *= maxW / drawW; drawW = maxW }
    }
    if (el.max_height) {
      const maxH = el.max_height * scale
      if (drawH > maxH) { drawW *= maxH / drawH; drawH = maxH }
    }
  }

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
  if (idx < 0) return
  ctx.font = 'bold 7px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  const lx = x - 2, ly = y - 2
  ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'
  ctx.beginPath()
  ctx.arc(lx, ly, 6, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = '#fff'
  // Same number as the layer list (1 = top).
  ctx.fillText(`${(selectedConfig.value?.elements.length || 0) - idx}`, lx, ly)
}

// --- Watchers ---

watch(
  () => selectedConfig.value ? JSON.stringify(selectedConfig.value.elements) : '',
  () => { nextTick(renderPreview) }
)

watch(hoveredElementIdx, () => { nextTick(renderPreview) })
// When metadata arrives from the server, re-render immediately.
// This is the primary trigger for item-mode canvas updates.
watch(previewItemMetadata, () => { renderPreview() })
watch(previewMode, async () => {
  if (previewMode.value === 'item' && selectedMovie.value) {
    await fetchItemMetadata(selectedMovie.value.key)
  }
  // Call directly (not nextTick) — reactive data is already up-to-date at this point.
  renderPreview()
})
watch(previewResolution, () => { nextTick(renderPreview) })
watch(previewVideoCodec, () => { nextTick(renderPreview) })
watch(previewCodec, () => { nextTick(renderPreview) })
watch(previewAudioChannels, () => { nextTick(renderPreview) })
watch(previewAudioLanguage, () => { nextTick(renderPreview) })
watch(previewEdition, () => { nextTick(renderPreview) })
watch(previewStreamingPlatform, () => { nextTick(renderPreview) })
watch(previewStudio, () => { nextTick(renderPreview) })
watch([previewLabels, previewFilePath, previewRating, previewCriticRating, previewDaysAdded, previewShowStatus, previewOnLists, previewItemLabels, previewItemFilePaths, previewItemLists], () => { nextTick(renderPreview) })
// Re-render when the simposter asset map loads (it arrives async after mount)
watch(simposterAssetMap, () => { renderPreview() })
// A new rating/list/badge type in the layers: fetch it for the real items being previewed.
let needsTimer: ReturnType<typeof setTimeout> | undefined
watch(itemNeedsKey, () => {
  clearTimeout(needsTimer)
  needsTimer = setTimeout(async () => {
    if (previewMode.value === 'item' && selectedMovie.value) await fetchItemMetadata(selectedMovie.value.key)
    const tiles = compareTiles.value.filter(t => t.movie)
    if (!tiles.length) return
    const fresh = await Promise.all(tiles.map(t => loadItemData(t.movie!.key, t.mediaType || 'movie')))
    compareTiles.value = compareTiles.value.map(t => {
      const i = tiles.findIndex(x => x.id === t.id)
      return i >= 0 ? { ...t, data: fresh[i] || t.data } : t
    })
    nextTick(renderPreview)
  }, 400)
})

// Test values that this overlay actually uses; the rest sit behind "More values".
const BADGE_TEST_FIELD: Record<string, string> = {
  video_resolution: 'resolution', video_codec: 'video_codec', audio_codec: 'audio_codec',
  audio_channels: 'audio_channels', audio_language: 'audio_language',
}
const CONDITION_TEST_FIELD: Record<string, string> = {
  resolution: 'resolution', video_resolution: 'resolution', video_codec: 'video_codec', audio_codec: 'audio_codec',
  audio_channels: 'audio_channels', audio_language: 'audio_language', edition: 'edition', label: 'labels', labels: 'labels',
  filepath: 'filepath', file_path: 'filepath', filename: 'filepath', audience_rating: 'audience_rating',
  critic_rating: 'critic_rating', list: 'list', mdblist_list: 'list', streaming_platform: 'platform', studio: 'studio',
  days_since_added: 'days_since_added', show_status: 'show_status',
}
const usedTestFields = computed(() => {
  const out = new Set<string>()
  for (const el of selectedConfig.value?.elements || []) {
    if (el.type === 'video_badge' || el.type === 'resolution_badge') out.add(BADGE_TEST_FIELD[el.metadata_field || 'video_resolution'] || 'resolution')
    if (el.type === 'audio_badge' || el.type === 'codec_badge') out.add(BADGE_TEST_FIELD[el.metadata_field || 'audio_codec'] || 'audio_codec')
    if (el.type === 'edition_badge') out.add('edition')
    if (el.type === 'streaming_platform_badge') out.add('platform')
    if (el.type === 'studio_badge') out.add('studio')
    for (const c of el.conditions || []) {
      const f = CONDITION_TEST_FIELD[String(c.field || '').toLowerCase()]
      if (f) out.add(f)
    }
    for (const k of textKeys(el)) {
      const f = CONDITION_TEST_FIELD[k.toLowerCase()]
      if (f) out.add(f)
    }
  }
  for (const c of selectedConfig.value?.conditions || []) {
    const f = CONDITION_TEST_FIELD[String(c.field || '').toLowerCase()]
    if (f) out.add(f)
  }
  if (!out.size) { out.add('resolution'); out.add('audio_codec') }
  return out
})
const showAllTestValues = ref(false)
const showTest = (field: string) => showAllTestValues.value || usedTestFields.value.has(field)

// "A real movie" with nothing picked yet opens the picker, then switches over.
let switchToItemAfterPick = false
const useRealItem = () => {
  if (selectedMovie.value) { previewMode.value = 'item'; return }
  switchToItemAfterPick = true
  openMovieSearch()
}

const showAssets = ref(false)

/** Image layers can use a link instead of (or as a fallback for) an uploaded image. */
const setOptionalText = (el: OverlayElement, key: 'font_style' | 'asset_id', value: string) => {
  const v = value.trim()
  if (v) el[key] = v
  else delete el[key]
}

const setElementUrl = (el: OverlayElement, value: string) => {
  const v = value.trim()
  if (v) (el as OverlayElement & { url?: string }).url = v
  else delete (el as OverlayElement & { url?: string }).url
}

// Advanced section (live Kometa files), closed by default.
const showAdvanced = ref(false)
// Scheduler section (how often ratings/lists are re-fetched), closed by default.
const showScheduler = ref(false)
const schedulerCard = ref<HTMLElement | null>(null)
const advancedCard = ref<HTMLElement | null>(null)
// Links in the "How overlays work" guide open a section and scroll to it.
const openSection = async (which: 'scheduler' | 'advanced') => {
  if (which === 'scheduler') showScheduler.value = true
  else showAdvanced.value = true
  await nextTick()
  ;(which === 'scheduler' ? schedulerCard.value : advancedCard.value)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
const openOverlayById = (id: string) => {
  const cfg = configs.value.find(c => c.id === id)
  if (cfg) editConfig(cfg)
}

// Renaming a layer (its name is also how hide rules point at it).
const renamingKey = ref<number | null>(null)
const renameDraft = ref('')
const startRename = (el: OverlayElement) => {
  renameDraft.value = el.name || ''
  renamingKey.value = elementKey(el)
  nextTick(() => (document.querySelector('.element-rename') as HTMLInputElement | null)?.select())
}
const commitRename = (el: OverlayElement) => {
  if (renamingKey.value !== elementKey(el)) return
  renamingKey.value = null
  const next = renameDraft.value.trim()
  const old = el.name
  if (next === (old || '')) return
  if (next) el.name = next
  else delete el.name
  // Keep hide rules pointing at it.
  if (old) {
    for (const other of selectedConfig.value?.elements || []) {
      if (other.suppress?.includes(old)) {
        const kept = other.suppress.filter(n => n !== old)
        other.suppress = next ? other.suppress.map(n => (n === old ? next : n)) : kept
        if (!other.suppress.length) delete other.suppress
      }
    }
  }
}

// {text} values that need MDBList are only offered once its API key is set.
const settingsStore = useSettingsStore()
const hasMdblistKey = computed(() => !!settingsStore.mdblist.value.apiKey)
const textVariableGroups = computed(() => TEXT_VARIABLE_GROUPS
  .map(g => ({ group: g, vars: TEXT_VARIABLES.filter(v => v.group === g && (hasMdblistKey.value || !needsMdblist(v))) }))
  .filter(g => g.vars.length))

/** Put {key} into a text layer at the cursor (or at the end), from the "Insert value" list. */
const insertTextVariable = (el: OverlayElement, e: Event) => {
  const select = e.target as HTMLSelectElement
  const key = select.value
  select.value = ''
  if (!key) return
  const input = select.parentElement?.querySelector('input') as HTMLInputElement | null
  const token = `{${key}}`
  const text = el.text || ''
  const start = input && document.activeElement === input ? (input.selectionStart ?? text.length) : (lastTextCursor.get(el) ?? text.length)
  const end = input && document.activeElement === input ? (input.selectionEnd ?? start) : start
  el.text = text.slice(0, start) + token + text.slice(end)
  const pos = start + token.length
  lastTextCursor.set(el, pos)
  nextTick(() => {
    if (!input) return
    input.focus()
    input.setSelectionRange(pos, pos)
  })
}
// The select takes focus before its change event, so remember where the cursor was.
const lastTextCursor = new WeakMap<object, number>()
const rememberTextCursor = (el: OverlayElement, e: Event) => {
  const input = e.target as HTMLInputElement
  lastTextCursor.set(el, input.selectionStart ?? (el.text || '').length)
}

// Left side of the editor: build layers first, then group them into badge sets.
const leftTab = ref<'layers' | 'sets' | 'when'>('layers')
const badgeSetCount = computed(() => new Set((selectedConfig.value?.elements || []).map(e => e.group).filter(Boolean)).size)

// ---- Compare: the same overlay on a few posters at once ----
interface CompareTile {
  id: number
  label: string
  /** Example tile: fields that differ from the example values. */
  values?: Record<string, string>
  /** Real item tile. */
  movie?: SimpleMovie
  mediaType?: string
  data?: ItemData
  bg: HTMLImageElement | null
}
let nextTileId = 1
const exampleTile = (label: string, values: Record<string, string>): CompareTile => ({ id: nextTileId++, label, values, bg: null })
const compareTiles = ref<CompareTile[]>([
  exampleTile('4K · HEVC · Atmos', { video_resolution: '4k', video_codec: 'hevc', audio_codec: 'atmos', audio_channels: '8' }),
  exampleTile('1080p · H.264 · DTS', { video_resolution: '1080', video_codec: 'h264', audio_codec: 'dts', audio_channels: '6' }),
  exampleTile('720p · AAC stereo', { video_resolution: '720', video_codec: 'h264', audio_codec: 'aac', audio_channels: '2' }),
])
const showCompare = ref(false)
try { showCompare.value = localStorage.getItem('simposter-overlay-compare') === '1' } catch { /* ignore */ }
watch(showCompare, v => {
  try { localStorage.setItem('simposter-overlay-compare', v ? '1' : '0') } catch { /* ignore */ }
  nextTick(renderPreview)
})
const compareCanvases = new Map<number, HTMLCanvasElement>()
const setCompareCanvas = (id: number, el: unknown) => {
  if (el instanceof HTMLCanvasElement) compareCanvases.set(id, el)
  else compareCanvases.delete(id)
}
let pickForCompare = false
const pickCompareItem = () => {
  pickForCompare = true
  openMovieSearch()
}
const addCompareItem = async (movie: SimpleMovie) => {
  const mediaType = previewSelectedLibrary.value?.type === 'show' ? 'tv' : 'movie'
  const tile: CompareTile = { id: nextTileId++, label: movie.title, movie, mediaType, bg: null }
  compareTiles.value = [...compareTiles.value, tile]
  const [data, bg] = await Promise.all([loadItemData(movie.key, mediaType), loadPosterImage(movie.key)])
  compareTiles.value = compareTiles.value.map(t => (t.id === tile.id ? { ...t, data: data || undefined, bg } : t))
  nextTick(renderPreview)
}
const removeCompareTile = (id: number) => {
  compareTiles.value = compareTiles.value.filter(t => t.id !== id)
  nextTick(renderPreview)
}
const tileScene = (tile: CompareTile, canvas: HTMLCanvasElement): Scene => {
  if (tile.movie) {
    const meta = tile.data?.metadata || {}
    const ctx = itemContext(tile.data || { metadata: {}, labels: [], file_paths: [], lists: [] }, tile.mediaType || 'movie', tile.movie.title)
    return { key: `tile-${tile.id}`, canvas, bg: tile.bg, value: f => meta[f] || '', ctx, meta, visible: selectVisible(ctx), interactive: false }
  }
  const values = tile.values || {}
  const ctx = exampleContext(values, selectedMovie.value?.title)
  return {
    key: `tile-${tile.id}`, canvas, bg: posterBgImage.value,
    value: f => values[f] ?? previewMetadataValues[f]?.value ?? '',
    ctx, meta: {}, visible: selectVisible(ctx), interactive: false,
  }
}

const hasStreamingBadge = computed(() =>
  selectedConfig.value?.elements.some(e => e.type === 'streaming_platform_badge') ?? false
)
const hasStudioBadge = computed(() =>
  selectedConfig.value?.elements.some(e => e.type === 'studio_badge') ?? false
)

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

onUnmounted(() => window.removeEventListener('keydown', onEditorKeydown))
onMounted(() => {
  window.addEventListener('keydown', onEditorKeydown)
  loadConfigs()
  loadAssets()
  loadFonts()
  loadSimposterAssets()
})
</script>

<template>
  <div class="overlay-manager">
    <div class="page-header">
      <div>
        <h1>&#x1F9EA; Overlays <span style="font-size: 0.55em; opacity: 0.6; vertical-align: middle; font-weight: 400;">(experimental)</span></h1>
        <p class="page-subtitle">Badges, images and text drawn on top of a poster, kept up to date when ratings, lists or labels change.</p>
      </div>
    </div>

    <OverlayWorkflowGuide @open-scheduler="openSection('scheduler')" @open-advanced="openSection('advanced')" />

    <div class="content-grid">
      <!-- Left: Configs List -->
      <div class="section-card">
        <div class="section-header">
          <h2>Your overlays</h2>
          <div style="display:flex;gap:0.5rem;">
          <button class="btn-secondary-sm" title="Import Kometa overlay files" @click="showKometaImport = true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Import Kometa <span class="beta-badge" title="Beta: works, but may still have small issues. Please report anything odd.">Beta</span>
          </button>
          <button class="btn-primary-sm" @click="createNewConfig">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New overlay
          </button>
          </div>
        </div>

        <div v-if="loading" class="loading">Loading...</div>
        <div v-else-if="configs.length === 0" class="empty-state">
          No overlays yet. Click <strong>New overlay</strong> to build one, or <strong>Import Kometa</strong> if you already have Kometa overlay files.
        </div>
        <div v-else class="configs-list">
          <div v-for="config in configs" :key="config.id" class="config-item">
            <div class="config-info">
              <div class="config-name">{{ config.name }}</div>
              <div class="config-meta">{{ config.elements.length }} layer{{ config.elements.length !== 1 ? 's' : '' }}</div>
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

      <!-- Right: your images (collapsed by default; only needed when building image badges) -->
      <div class="section-card">
        <div class="section-header">
          <button type="button" class="section-toggle" @click="showAssets = !showAssets">
            <span class="section-chev" :class="{ open: showAssets }">›</span>
            <h2>Your images <span class="elements-count">{{ assets.length }}</span></h2>
          </button>
          <button class="btn-primary-sm" @click="showAssetUpload = true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            Upload image
          </button>
        </div>

        <p v-if="!showAssets" class="section-note">
          Images you can use in badges and image layers.<template v-if="assets.length"> Click the title to see them.</template>
        </p>
        <template v-else>
          <div v-if="assets.length === 0" class="empty-state">
            No images yet. Upload one, or copy files into <code>config/assets/</code> and
            <button type="button" class="btn-link" @click="rescanAssets">check the folder</button>.
          </div>
          <template v-else>
            <div class="assets-grid">
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
            <p class="section-note">Added files to <code>config/assets/</code> yourself? <button type="button" class="btn-link" @click="rescanAssets">Check the folder again</button></p>
          </template>
        </template>
      </div>
    </div>

    <!-- Config Editor Modal -->
    <!-- Scheduler: how often ratings and lists are re-fetched (hidden until opened) -->
    <div ref="schedulerCard" class="section-card advanced-card">
      <div class="section-header">
        <button type="button" class="section-toggle" @click="showScheduler = !showScheduler">
          <span class="section-chev" :class="{ open: showScheduler }">›</span>
          <h2>Scheduler</h2>
        </button>
      </div>
      <p v-if="!showScheduler" class="section-note">Step 4 of the guide above: how often ratings and lists are fetched again (API calls), and each library's Overlay Refresh schedule.</p>
      <OverlayScheduler v-else />
    </div>

    <!-- Advanced: live Kometa files (hidden until opened) -->
    <div ref="advancedCard" class="section-card advanced-card">
      <div class="section-header">
        <button type="button" class="section-toggle" @click="showAdvanced = !showAdvanced">
          <span class="section-chev" :class="{ open: showAdvanced }">›</span>
          <h2>Advanced</h2>
        </button>
      </div>
      <p v-if="!showAdvanced" class="section-note">Live Kometa files <span class="beta-badge" title="Beta: works, but may still have small issues. Please report anything odd.">Beta</span>: overlay files another tool keeps rewriting (like UMTK), re-imported automatically.</p>
      <template v-else>
        <h3 class="advanced-sub">Live Kometa files <span class="beta-badge" title="Beta: works, but may still have small issues. Please report anything odd.">Beta</span></h3>
        <LiveKometaFiles @changed="loadConfigs" @open-overlay="openOverlayById" />
      </template>
    </div>

    <Teleport to="body">
    <!-- Teleported so it centers on the window, not the page area (Quirk #23). -->
    <div v-if="showEditor && selectedConfig" class="modal-overlay">
      <div class="editor-modal">
        <div class="editor-header">
          <div>
            <h2>Edit overlay</h2>
            <div class="editor-name-row">
              <input v-model="selectedConfig.name" class="config-name-input" placeholder="Overlay name..." />
              <div v-if="hasStreamingBadge" class="region-selector">
                <span class="region-label">Streaming region</span>
                <select v-model="selectedConfig.streaming_region" class="region-select">
                  <option v-for="r in STREAMING_REGIONS" :key="r.code" :value="r.code">{{ r.label }}</option>
                </select>
              </div>
            </div>
          </div>
          <button class="btn-close" title="Close" @click="closeEditor">
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
                <div class="elements-title-row">
                  <div class="left-tabs" role="tablist">
                    <button type="button" role="tab" :class="{ on: leftTab === 'layers' }" @click="leftTab = 'layers'">
                      <span class="step">1</span> Layers <span class="elements-count">{{ selectedConfig.elements.length }}</span>
                    </button>
                    <button type="button" role="tab" :class="{ on: leftTab === 'sets' }" @click="leftTab = 'sets'">
                      <span class="step">2</span> Badge sets <span class="elements-count">{{ badgeSetCount }}</span>
                    </button>
                    <button type="button" role="tab" :class="{ on: leftTab === 'when' }" @click="leftTab = 'when'">
                      <span class="step">3</span> Show overlay when <span class="elements-count">{{ selectedConfig.conditions?.length || 0 }}</span>
                    </button>
                  </div>
                  <div v-if="leftTab === 'layers'" class="add-menu-wrap">
                    <button class="btn-add-main" @click="showAddMenu = !showAddMenu">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                      Add layer
                    </button>
                    <div v-if="showAddMenu" class="menu-backdrop" @click="showAddMenu = false"></div>
                    <div v-if="showAddMenu" class="add-menu">
                      <div v-for="section in ADD_MENU" :key="section.title" class="add-menu-section">
                        <div class="add-menu-title">{{ section.title }}</div>
                        <button v-for="item in section.items" :key="item.type" class="add-menu-item" @click="addElement(item.type)">
                          <span class="add-menu-dot" :style="{ background: elementTypeColor(item.type) }"></span>
                          <span class="add-menu-label">{{ item.label }}</span>
                          <span class="add-menu-hint">{{ item.hint }}</span>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                <div v-if="leftTab === 'layers' && selectedConfig.elements.length > 3" class="elements-toolbar">
                  <input v-model="elementFilter" class="elements-search" type="search" placeholder="Find a layer..." />
                  <button class="btn-link" @click="setAllExpanded(true)">Expand all</button>
                  <button class="btn-link" @click="setAllExpanded(false)">Collapse all</button>
                </div>
              </div>

              <template v-if="leftTab === 'layers'">
              <p v-if="selectedConfig.elements.length > 1" class="layer-hint">Top of the list is drawn on top.</p>

              <div v-if="selectedConfig.elements.length === 0" class="empty-elements">
                <strong>This overlay is empty.</strong><br />
                Click <strong>Add layer</strong> and pick a badge that changes with each movie (like 4K or Atmos),
                or your own image or text. Each layer you add shows up on the preview on the right.
              </div>
              <div v-else-if="filteredElements.length === 0" class="empty-elements">
                No layers match "{{ elementFilter }}".
              </div>

              <div v-else class="elements-list">
                <div
                  v-for="{ element, idx } in displayElements"
                  :key="elementKey(element)"
                  :data-el-key="elementKey(element)"
                  class="element-card"
                  :class="{ 'element-hovered': hoveredElementIdx === idx, 'element-collapsed': !isExpanded(element), 'element-dimmed': !visibleElements.has(idx) }"
                  @mouseenter="hoveredElementIdx = idx"
                  @mouseleave="hoveredElementIdx = null"
                >
                  <div class="element-header" @click="toggleExpanded(element)">
                    <div class="element-header-left">
                      <svg class="element-chevron" :class="{ open: isExpanded(element) }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 6 15 12 9 18"/></svg>
                      <span class="element-index" title="Layer (1 = top)">{{ selectedConfig.elements.length - idx }}</span>
                      <span class="element-dot" :style="{ background: elementTypeColor(element.type) }"></span>
                      <div class="element-title">
                        <input
                          v-if="renamingKey === elementKey(element)"
                          v-model="renameDraft"
                          class="element-rename"
                          :placeholder="elementNoun(element)"
                          @click.stop
                          @keyup.enter="commitRename(element)"
                          @keyup.esc.stop="renamingKey = null"
                          @blur="commitRename(element)"
                        />
                        <span v-else class="element-name" title="Double-click to rename" @dblclick.stop="startRename(element)">
                          {{ element.name || elementNoun(element) }}
                          <button type="button" class="rename-btn" title="Rename" @click.stop="startRename(element)">✎</button>
                        </span>
                        <span class="element-summary">
                          {{ elementPlace(element) }} · {{ elementWhen(element) }}<template v-if="element.group"> · in set "{{ element.group }}"</template>
                        </span>
                      </div>
                      <span v-if="layerWarnings(element).length" class="element-warn" :title="layerWarnings(element).join('\n')">⚠</span>
                      <span v-if="!visibleElements.has(idx)" class="element-hidden" title="Not drawn for the movie or values used in the preview">not on this preview</span>
                    </div>
                    <div class="element-actions" @click.stop>
                      <button class="btn-mini" :disabled="idx === selectedConfig.elements.length - 1" @click="moveElement(idx, 1)" title="Move up (drawn above the ones below it)">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 15 12 9 18 15"/></svg>
                      </button>
                      <button class="btn-mini" :disabled="idx === 0" @click="moveElement(idx, -1)" title="Move down (drawn under the ones above it)">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
                      </button>
                      <button class="btn-mini" @click="duplicateElement(idx)" title="Duplicate">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                      </button>
                      <button class="btn-mini danger" @click="removeElement(idx)" title="Remove element">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                      </button>
                    </div>
                  </div>

                  <div v-if="isExpanded(element)" class="element-fields">
                    <ul v-if="layerWarnings(element).length" class="warn-list">
                      <li v-for="w in layerWarnings(element)" :key="w">⚠ {{ w }}</li>
                    </ul>
                    <div class="el-tabs">
                      <button type="button" :class="{ on: tabOf(element) === 'look' }" @click="setTab(element, 'look')">Look</button>
                      <button type="button" :class="{ on: tabOf(element) === 'position' }" @click="setTab(element, 'position')">Position</button>
                      <button type="button" :class="{ on: tabOf(element) === 'when' }" @click="setTab(element, 'when')">
                        Show when<span v-if="element.conditions?.length" class="el-tab-count">{{ element.conditions.length }}</span>
                      </button>
                    </div>

                    <p v-if="tabOf(element) === 'position' && element.queue" class="look-help">
                      This layer is in the queue "{{ element.queue }}": it takes the queue's next free position (highest weight first),
                      so the position below isn't used. Re-import the Kometa file to change the queue.
                    </p>
                    <p v-else-if="tabOf(element) === 'position' && element.type === 'blur'" class="look-help">A blur covers the whole poster; it has no position.</p>
                    <OverlayPositionEditor v-else-if="tabOf(element) === 'position'" :element="element" />
                    <OverlayRulesEditor v-else-if="tabOf(element) === 'when'" :element="element" />

                    <template v-else>
                    <p v-if="element.box_only" class="look-help">A plain box with no text or image (a Kometa "backdrop"). Set its color and size below; without a color or border it draws nothing.</p>
                    <p v-else-if="TYPE_HELP[element.type]" class="look-help">{{ TYPE_HELP[element.type] }}</p>
                    <!-- Video Badge (+ legacy resolution_badge) -->
                    <template v-if="element.type === 'video_badge' || element.type === 'resolution_badge'">
                      <div class="look-sec"><div class="look-sec-title">What it shows</div><div class="look-sec-grid">
                      <label class="field-full">
                        <span>Show the movie's</span>
                        <select v-model="element.metadata_field">
                          <option value="video_resolution">Video Resolution</option>
                          <option value="video_codec">Video Codec</option>
                        </select>
                      </label>
                      </div></div>
                      <div class="field-full badge-assets-section look-sec">
                        <div class="look-sec-title">For each value</div>
                        <p class="look-sec-help">Choose what to draw for each value: an image, your own text, or nothing.</p>
                        <div class="badge-asset-rows">
                          <div v-for="val in withOther(getValuesForField(element.metadata_field || 'video_resolution'))" :key="val" class="badge-asset-item">
                            <div class="badge-asset-row">
                              <span class="badge-value-label">{{ badgeValueLabel(val) }}</span>
                              <select
                                :value="getBadgeMode(element, val)"
                                @change="setBadgeMode(element, val, ($event.target as HTMLSelectElement).value)"
                                class="badge-mode-select"
                              >
                                <option value="none">None</option>
                                <option value="text">Text</option>
                                <option value="image">Image</option>
                                <option value="url">URL</option>
                                <option value="asset">Simposter Asset</option>
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
                              <input
                                v-if="getBadgeMode(element, val) === 'url'"
                                type="url"
                                :value="getBadgeUrl(element, val)"
                                @input="setBadgeUrl(element, val, ($event.target as HTMLInputElement).value)"
                                @change="setBadgeUrl(element, val, normalizeBadgeUrl(($event.target as HTMLInputElement).value)); prefetchBadgeUrl(normalizeBadgeUrl(($event.target as HTMLInputElement).value))"
                                @keyup.enter="($event.target as HTMLInputElement).blur()"
                                placeholder="https://..."
                                class="badge-url-input"
                              />
                            </div>
                            <div v-if="['image', 'url', 'asset'].includes(getBadgeMode(element, val))" class="badge-image-overrides">
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
                        <div class="look-sec"><div class="look-sec-title">Text style</div><div class="look-sec-grid">
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
                        </div></div>
                      </template>
                    </template>

                    <!-- Audio Badge (+ legacy codec_badge) -->
                    <template v-if="element.type === 'audio_badge' || element.type === 'codec_badge'">
                      <div class="look-sec"><div class="look-sec-title">What it shows</div><div class="look-sec-grid">
                      <label class="field-full">
                        <span>Show the movie's</span>
                        <select v-model="element.metadata_field">
                          <option value="audio_codec">Audio Codec</option>
                          <option value="audio_channels">Audio Channels</option>
                          <option value="audio_language">Audio Language</option>
                        </select>
                      </label>
                      </div></div>
                      <div class="field-full badge-assets-section look-sec">
                        <div class="look-sec-title">For each value</div>
                        <p class="look-sec-help">Choose what to draw for each value: an image, your own text, or nothing.</p>
                        <div class="badge-asset-rows">
                          <div v-for="val in withOther(getValuesForField(element.metadata_field || 'audio_codec'))" :key="val" class="badge-asset-item">
                            <div class="badge-asset-row">
                              <span class="badge-value-label">{{ badgeValueLabel(val) }}</span>
                              <select
                                :value="getBadgeMode(element, val)"
                                @change="setBadgeMode(element, val, ($event.target as HTMLSelectElement).value)"
                                class="badge-mode-select"
                              >
                                <option value="none">None</option>
                                <option value="text">Text</option>
                                <option value="image">Image</option>
                                <option value="url">URL</option>
                                <option value="asset">Simposter Asset</option>
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
                              <input
                                v-if="getBadgeMode(element, val) === 'url'"
                                type="url"
                                :value="getBadgeUrl(element, val)"
                                @input="setBadgeUrl(element, val, ($event.target as HTMLInputElement).value)"
                                @change="setBadgeUrl(element, val, normalizeBadgeUrl(($event.target as HTMLInputElement).value)); prefetchBadgeUrl(normalizeBadgeUrl(($event.target as HTMLInputElement).value))"
                                @keyup.enter="($event.target as HTMLInputElement).blur()"
                                placeholder="https://..."
                                class="badge-url-input"
                              />
                            </div>
                            <div v-if="['image', 'url', 'asset'].includes(getBadgeMode(element, val))" class="badge-image-overrides">
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
                        <div class="look-sec"><div class="look-sec-title">Text style</div><div class="look-sec-grid">
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
                        </div></div>
                      </template>
                    </template>

                    <!-- Edition Badge -->
                    <template v-if="element.type === 'edition_badge'">
                      <div class="field-full badge-assets-section look-sec">
                        <div class="look-sec-title">For each value</div>
                        <p class="look-sec-help">Choose what to draw for each value: an image, your own text, or nothing.</p>
                        <div class="badge-asset-rows">
                          <div v-for="val in withOther(EDITION_VALUES)" :key="val" class="badge-asset-item">
                            <div class="badge-asset-row">
                              <span class="badge-value-label">{{ badgeValueLabel(val) }}</span>
                              <select
                                :value="getBadgeMode(element, val)"
                                @change="setBadgeMode(element, val, ($event.target as HTMLSelectElement).value)"
                                class="badge-mode-select"
                              >
                                <option value="none">None</option>
                                <option value="text">Text</option>
                                <option value="image">Image</option>
                                <option value="url">URL</option>
                                <option value="asset">Simposter Asset</option>
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
                              <input
                                v-if="getBadgeMode(element, val) === 'url'"
                                type="url"
                                :value="getBadgeUrl(element, val)"
                                @input="setBadgeUrl(element, val, ($event.target as HTMLInputElement).value)"
                                @change="setBadgeUrl(element, val, normalizeBadgeUrl(($event.target as HTMLInputElement).value)); prefetchBadgeUrl(normalizeBadgeUrl(($event.target as HTMLInputElement).value))"
                                @keyup.enter="($event.target as HTMLInputElement).blur()"
                                placeholder="https://..."
                                class="badge-url-input"
                              />
                            </div>
                            <div v-if="['image', 'url', 'asset'].includes(getBadgeMode(element, val))" class="badge-image-overrides">
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
                        <div class="look-sec"><div class="look-sec-title">Text style</div><div class="look-sec-grid">
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
                        </div></div>
                      </template>
                    </template>

                    <!-- Streaming Platform Badge -->
                    <template v-if="element.type === 'streaming_platform_badge'">
                      <div class="field-full badge-assets-section look-sec">
                        <div class="look-sec-title">For each value</div>
                        <p class="look-sec-help">Choose what to draw for each value: an image, your own text, or nothing.</p>
                        <!-- Default row (applies to all platforms unless overridden) -->
                        <div class="badge-override-section">
                          <span class="badge-override-section-label">Default</span>
                          <div class="badge-compact-row">
                            <span class="badge-compact-label badge-default-label">All platforms</span>
                            <select :value="getBadgeMode(element, '__other__')" @change="setBadgeMode(element, '__other__', ($event.target as HTMLSelectElement).value)" class="badge-compact-mode">
                              <option value="none">None</option><option value="text">Text</option><option value="image">Image</option><option value="url">URL</option><option value="asset">Simposter Asset</option>
                            </select>
                            <template v-if="['image','url','asset'].includes(getBadgeMode(element,'__other__'))">
                              <select v-if="getBadgeMode(element,'__other__')==='image'" :value="getBadgeAsset(element,'__other__')||''" @change="setBadgeAsset(element,'__other__',($event.target as HTMLSelectElement).value||undefined)" class="badge-compact-flex"><option value="">Select asset...</option><option v-for="a in assets" :key="a.id" :value="a.id">{{a.name}}</option></select>
                              <input v-if="getBadgeMode(element,'__other__')==='url'" type="url" :value="getBadgeUrl(element,'__other__')" @input="setBadgeUrl(element,'__other__',($event.target as HTMLInputElement).value)" @change="setBadgeUrl(element,'__other__',normalizeBadgeUrl(($event.target as HTMLInputElement).value))" placeholder="https://..." class="badge-compact-flex badge-compact-url-input" />
                              <input type="number" :value="getBadgeScale(element,'__other__')" @input="setBadgeScale(element,'__other__',($event.target as HTMLInputElement).value)" min="0.05" max="3.0" step="0.05" placeholder="1.0" class="badge-cr-scale" />
                              <select :value="getBadgeAnchor(element,'__other__')" @change="setBadgeAnchor(element,'__other__',($event.target as HTMLSelectElement).value)" class="badge-cr-anchor">
                                <option value="top-left">Top Left</option><option value="top-center">Top Center</option><option value="top-right">Top Right</option>
                                <option value="center-left">Center Left</option><option value="center">Center</option><option value="center-right">Center Right</option>
                                <option value="bottom-left">Bottom Left</option><option value="bottom-center">Bottom Center</option><option value="bottom-right">Bottom Right</option>
                              </select>
                            </template>
                            <input v-if="getBadgeMode(element,'__other__')==='text'" type="text" :value="getBadgeText(element,'__other__')" @input="setBadgeText(element,'__other__',($event.target as HTMLInputElement).value)" placeholder="Text override..." class="badge-compact-flex badge-text-input" />
                          </div>
                        </div>
                        <!-- Per-platform overrides -->
                        <div v-if="getExplicitOverrides(element, STREAMING_PLATFORM_VALUES).length > 0" class="badge-override-section">
                          <span class="badge-override-section-label">Overrides</span>
                          <div class="badge-compact-rows">
                            <div v-for="val in getExplicitOverrides(element, STREAMING_PLATFORM_VALUES)" :key="val" class="badge-compact-row">
                              <span class="badge-compact-label">{{ badgeValueLabel(val, STREAMING_PLATFORM_LABELS) }}</span>
                              <select :value="getBadgeMode(element, val)" @change="setBadgeMode(element, val, ($event.target as HTMLSelectElement).value)" class="badge-compact-mode">
                                <option value="none">None</option><option value="text">Text</option><option value="image">Image</option><option value="url">URL</option><option value="asset">Simposter Asset</option>
                              </select>
                              <template v-if="['image','url','asset'].includes(getBadgeMode(element,val))">
                                <select v-if="getBadgeMode(element,val)==='image'" :value="getBadgeAsset(element,val)||''" @change="setBadgeAsset(element,val,($event.target as HTMLSelectElement).value||undefined)" class="badge-compact-flex"><option value="">Select asset...</option><option v-for="a in assets" :key="a.id" :value="a.id">{{a.name}}</option></select>
                                <input v-if="getBadgeMode(element,val)==='url'" type="url" :value="getBadgeUrl(element,val)" @input="setBadgeUrl(element,val,($event.target as HTMLInputElement).value)" @change="setBadgeUrl(element,val,normalizeBadgeUrl(($event.target as HTMLInputElement).value));prefetchBadgeUrl(normalizeBadgeUrl(($event.target as HTMLInputElement).value))" placeholder="https://..." class="badge-compact-flex badge-compact-url-input" />
                                <input type="number" :value="getBadgeScale(element,val)" @input="setBadgeScale(element,val,($event.target as HTMLInputElement).value)" min="0.05" max="3.0" step="0.05" placeholder="1.0" class="badge-cr-scale" />
                                <select :value="getBadgeAnchor(element,val)" @change="setBadgeAnchor(element,val,($event.target as HTMLSelectElement).value)" class="badge-cr-anchor">
                                  <option value="top-left">Top Left</option><option value="top-center">Top Center</option><option value="top-right">Top Right</option>
                                  <option value="center-left">Center Left</option><option value="center">Center</option><option value="center-right">Center Right</option>
                                  <option value="bottom-left">Bottom Left</option><option value="bottom-center">Bottom Center</option><option value="bottom-right">Bottom Right</option>
                                </select>
                              </template>
                              <input v-if="getBadgeMode(element,val)==='text'" type="text" :value="getBadgeText(element,val)" @input="setBadgeText(element,val,($event.target as HTMLInputElement).value)" :placeholder="badgeValueLabel(val,STREAMING_PLATFORM_LABELS)" class="badge-compact-flex badge-text-input" />
                              <button type="button" class="badge-remove-override" @click="removeBadgeOverride(element, val)" title="Remove override">×</button>
                            </div>
                          </div>
                        </div>
                        <!-- Add override -->
                        <select class="badge-add-override-select" @change="addBadgeOverride(element, ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''">
                          <option value="">+ Override a platform...</option>
                          <option v-for="val in getAvailableForOverride(element, STREAMING_PLATFORM_VALUES)" :key="val" :value="val">{{ badgeValueLabel(val, STREAMING_PLATFORM_LABELS) }}</option>
                        </select>
                        <!-- Slug aliases -->
                        <div class="badge-alias-section">
                          <div class="badge-override-section-label">Slug Aliases <span class="badge-alias-hint">— remap TMDb slugs to asset names</span></div>
                          <div v-for="(toSlug, fromSlug) in (element.slug_aliases || {})" :key="fromSlug" class="badge-alias-row">
                            <span class="badge-alias-from">{{ fromSlug }}</span>
                            <span class="badge-alias-arrow">→</span>
                            <span class="badge-alias-to">{{ toSlug }}</span>
                            <button type="button" class="badge-remove-override" @click="removeSlugAlias(element, fromSlug)" title="Remove alias">×</button>
                          </div>
                          <div class="badge-alias-add-row">
                            <input v-model="pendingAliasFrom" placeholder="cj-enm-studios" class="badge-alias-input" @keyup.enter="addSlugAlias(element, pendingAliasFrom, pendingAliasTo)" />
                            <span class="badge-alias-arrow">→</span>
                            <input v-model="pendingAliasTo" placeholder="cj-entertainment-studios" class="badge-alias-input" @keyup.enter="addSlugAlias(element, pendingAliasFrom, pendingAliasTo)" />
                            <button type="button" class="badge-alias-add-btn" :disabled="!pendingAliasFrom || !pendingAliasTo" @click="addSlugAlias(element, pendingAliasFrom, pendingAliasTo)">Add</button>
                          </div>
                        </div>
                      </div>
                      <template v-if="hasBadgeTextMode(element)">
                        <div class="look-sec"><div class="look-sec-title">Text style</div><div class="look-sec-grid">
                        <label><span>Font Size (px)</span><input type="number" v-model.number="element.font_size" min="8" max="200" step="1" /></label>
                        <label><span>Font Color</span><div class="color-input-wrap"><input type="color" v-model="element.font_color" class="color-picker" /><input type="text" v-model="element.font_color" class="color-text" placeholder="#FFFFFF" /></div></label>
                        <label class="field-full"><span>Font Family</span><select v-model="element.font_family"><optgroup label="System Fonts"><option value="Arial">Arial</option><option value="Helvetica">Helvetica</option><option value="Times New Roman">Times New Roman</option><option value="Georgia">Georgia</option><option value="Verdana">Verdana</option><option value="Courier New">Courier New</option><option value="Impact">Impact</option></optgroup><optgroup v-if="fonts.length > 0" label="Custom Fonts"><option v-for="f in fonts" :key="f" :value="f">{{ f }}</option></optgroup></select></label>
                        <label class="field-full"><span>Text Align</span><div class="align-btn-group"><button type="button" :class="{ active: (element.text_align||'center')==='left' }" @click="element.text_align='left'">Left</button><button type="button" :class="{ active: (element.text_align||'center')==='center' }" @click="element.text_align='center'">Center</button><button type="button" :class="{ active: (element.text_align||'center')==='right' }" @click="element.text_align='right'">Right</button></div></label>
                        </div></div>
                      </template>
                    </template>

                    <!-- Studio Badge -->
                    <template v-if="element.type === 'studio_badge'">
                      <div class="field-full badge-assets-section look-sec">
                        <div class="look-sec-title">For each value</div>
                        <p class="look-sec-help">Choose what to draw for each value: an image, your own text, or nothing.</p>
                        <!-- Default row -->
                        <div class="badge-override-section">
                          <span class="badge-override-section-label">Default</span>
                          <div class="badge-compact-row">
                            <span class="badge-compact-label badge-default-label">All studios</span>
                            <select :value="getBadgeMode(element, '__other__')" @change="setBadgeMode(element, '__other__', ($event.target as HTMLSelectElement).value)" class="badge-compact-mode">
                              <option value="none">None</option><option value="text">Text</option><option value="image">Image</option><option value="url">URL</option><option value="asset">Simposter Asset</option>
                            </select>
                            <template v-if="['image','url','asset'].includes(getBadgeMode(element,'__other__'))">
                              <select v-if="getBadgeMode(element,'__other__')==='image'" :value="getBadgeAsset(element,'__other__')||''" @change="setBadgeAsset(element,'__other__',($event.target as HTMLSelectElement).value||undefined)" class="badge-compact-flex"><option value="">Select asset...</option><option v-for="a in assets" :key="a.id" :value="a.id">{{a.name}}</option></select>
                              <input v-if="getBadgeMode(element,'__other__')==='url'" type="url" :value="getBadgeUrl(element,'__other__')" @input="setBadgeUrl(element,'__other__',($event.target as HTMLInputElement).value)" @change="setBadgeUrl(element,'__other__',normalizeBadgeUrl(($event.target as HTMLInputElement).value))" placeholder="https://..." class="badge-compact-flex badge-compact-url-input" />
                              <input type="number" :value="getBadgeScale(element,'__other__')" @input="setBadgeScale(element,'__other__',($event.target as HTMLInputElement).value)" min="0.05" max="3.0" step="0.05" placeholder="1.0" class="badge-cr-scale" />
                              <select :value="getBadgeAnchor(element,'__other__')" @change="setBadgeAnchor(element,'__other__',($event.target as HTMLSelectElement).value)" class="badge-cr-anchor">
                                <option value="top-left">Top Left</option><option value="top-center">Top Center</option><option value="top-right">Top Right</option>
                                <option value="center-left">Center Left</option><option value="center">Center</option><option value="center-right">Center Right</option>
                                <option value="bottom-left">Bottom Left</option><option value="bottom-center">Bottom Center</option><option value="bottom-right">Bottom Right</option>
                              </select>
                            </template>
                            <input v-if="getBadgeMode(element,'__other__')==='text'" type="text" :value="getBadgeText(element,'__other__')" @input="setBadgeText(element,'__other__',($event.target as HTMLInputElement).value)" placeholder="Text override..." class="badge-compact-flex badge-text-input" />
                          </div>
                        </div>
                        <!-- Per-studio overrides -->
                        <div v-if="getExplicitOverrides(element, STUDIO_VALUES).length > 0" class="badge-override-section">
                          <span class="badge-override-section-label">Overrides</span>
                          <div class="badge-compact-rows">
                            <div v-for="val in getExplicitOverrides(element, STUDIO_VALUES)" :key="val" class="badge-compact-row">
                              <span class="badge-compact-label">{{ badgeValueLabel(val, STUDIO_LABELS) }}</span>
                              <select :value="getBadgeMode(element, val)" @change="setBadgeMode(element, val, ($event.target as HTMLSelectElement).value)" class="badge-compact-mode">
                                <option value="none">None</option><option value="text">Text</option><option value="image">Image</option><option value="url">URL</option><option value="asset">Simposter Asset</option>
                              </select>
                              <template v-if="['image','url','asset'].includes(getBadgeMode(element,val))">
                                <select v-if="getBadgeMode(element,val)==='image'" :value="getBadgeAsset(element,val)||''" @change="setBadgeAsset(element,val,($event.target as HTMLSelectElement).value||undefined)" class="badge-compact-flex"><option value="">Select asset...</option><option v-for="a in assets" :key="a.id" :value="a.id">{{a.name}}</option></select>
                                <input v-if="getBadgeMode(element,val)==='url'" type="url" :value="getBadgeUrl(element,val)" @input="setBadgeUrl(element,val,($event.target as HTMLInputElement).value)" @change="setBadgeUrl(element,val,normalizeBadgeUrl(($event.target as HTMLInputElement).value));prefetchBadgeUrl(normalizeBadgeUrl(($event.target as HTMLInputElement).value))" placeholder="https://..." class="badge-compact-flex badge-compact-url-input" />
                                <input type="number" :value="getBadgeScale(element,val)" @input="setBadgeScale(element,val,($event.target as HTMLInputElement).value)" min="0.05" max="3.0" step="0.05" placeholder="1.0" class="badge-cr-scale" />
                                <select :value="getBadgeAnchor(element,val)" @change="setBadgeAnchor(element,val,($event.target as HTMLSelectElement).value)" class="badge-cr-anchor">
                                  <option value="top-left">Top Left</option><option value="top-center">Top Center</option><option value="top-right">Top Right</option>
                                  <option value="center-left">Center Left</option><option value="center">Center</option><option value="center-right">Center Right</option>
                                  <option value="bottom-left">Bottom Left</option><option value="bottom-center">Bottom Center</option><option value="bottom-right">Bottom Right</option>
                                </select>
                              </template>
                              <input v-if="getBadgeMode(element,val)==='text'" type="text" :value="getBadgeText(element,val)" @input="setBadgeText(element,val,($event.target as HTMLInputElement).value)" :placeholder="badgeValueLabel(val,STUDIO_LABELS)" class="badge-compact-flex badge-text-input" />
                              <button type="button" class="badge-remove-override" @click="removeBadgeOverride(element, val)" title="Remove override">×</button>
                            </div>
                          </div>
                        </div>
                        <!-- Add override -->
                        <select class="badge-add-override-select" @change="addBadgeOverride(element, ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''">
                          <option value="">+ Override a studio...</option>
                          <option v-for="val in getAvailableForOverride(element, STUDIO_VALUES)" :key="val" :value="val">{{ badgeValueLabel(val, STUDIO_LABELS) }}</option>
                        </select>
                        <!-- Slug aliases -->
                        <div class="badge-alias-section">
                          <div class="badge-override-section-label">Slug Aliases <span class="badge-alias-hint">— remap TMDb slugs to asset names</span></div>
                          <div v-for="(toSlug, fromSlug) in (element.slug_aliases || {})" :key="fromSlug" class="badge-alias-row">
                            <span class="badge-alias-from">{{ fromSlug }}</span>
                            <span class="badge-alias-arrow">→</span>
                            <span class="badge-alias-to">{{ toSlug }}</span>
                            <button type="button" class="badge-remove-override" @click="removeSlugAlias(element, fromSlug)" title="Remove alias">×</button>
                          </div>
                          <div class="badge-alias-add-row">
                            <input v-model="pendingAliasFrom" placeholder="cj-enm-studios" class="badge-alias-input" @keyup.enter="addSlugAlias(element, pendingAliasFrom, pendingAliasTo)" />
                            <span class="badge-alias-arrow">→</span>
                            <input v-model="pendingAliasTo" placeholder="cj-entertainment-studios" class="badge-alias-input" @keyup.enter="addSlugAlias(element, pendingAliasFrom, pendingAliasTo)" />
                            <button type="button" class="badge-alias-add-btn" :disabled="!pendingAliasFrom || !pendingAliasTo" @click="addSlugAlias(element, pendingAliasFrom, pendingAliasTo)">Add</button>
                          </div>
                        </div>
                      </div>
                      <template v-if="hasBadgeTextMode(element)">
                        <div class="look-sec"><div class="look-sec-title">Text style</div><div class="look-sec-grid">
                        <label><span>Font Size (px)</span><input type="number" v-model.number="element.font_size" min="8" max="200" step="1" /></label>
                        <label><span>Font Color</span><div class="color-input-wrap"><input type="color" v-model="element.font_color" class="color-picker" /><input type="text" v-model="element.font_color" class="color-text" placeholder="#FFFFFF" /></div></label>
                        <label class="field-full"><span>Font Family</span><select v-model="element.font_family"><optgroup label="System Fonts"><option value="Arial">Arial</option><option value="Helvetica">Helvetica</option><option value="Times New Roman">Times New Roman</option><option value="Georgia">Georgia</option><option value="Verdana">Verdana</option><option value="Courier New">Courier New</option><option value="Impact">Impact</option></optgroup><optgroup v-if="fonts.length > 0" label="Custom Fonts"><option v-for="f in fonts" :key="f" :value="f">{{ f }}</option></optgroup></select></label>
                        <label class="field-full"><span>Text Align</span><div class="align-btn-group"><button type="button" :class="{ active: (element.text_align||'center')==='left' }" @click="element.text_align='left'">Left</button><button type="button" :class="{ active: (element.text_align||'center')==='center' }" @click="element.text_align='center'">Center</button><button type="button" :class="{ active: (element.text_align||'center')==='right' }" @click="element.text_align='right'">Right</button></div></label>
                        </div></div>
                      </template>
                    </template>

                    <!-- Custom Image -->
                    <template v-if="element.type === 'custom_image'">
                      <div class="look-sec"><div class="look-sec-title">Image</div><div class="look-sec-grid">
                      <label class="field-full">
                        <span>Image</span>
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
                      <label>
                        <span>Scale{{ element.placement === 'kometa' ? ' (Kometa size)' : '' }}</span>
                        <input type="number" v-model.number="element.scale" min="0.05" max="4" step="0.05" placeholder="1.0" />
                      </label>
                      <label v-if="element.placement !== 'kometa'" class="field-full">
                        <span>Image link (used when no image is picked above)</span>
                        <input type="text" :value="element.url || ''" placeholder="https://..." @change="setElementUrl(element, ($event.target as HTMLInputElement).value)" />
                      </label>
                      </div></div>
                    </template>

                    <!-- Full Cover Image -->
                    <template v-if="element.type === 'full_cover_image'">
                      <div class="look-sec"><div class="look-sec-title">Image</div><div class="look-sec-grid">
                      <label class="field-full">
                        <span>Image</span>
                        <select v-model="element.asset_id">
                          <option :value="undefined">Select asset...</option>
                          <option v-for="asset in assets" :key="asset.id" :value="asset.id">{{ asset.name }} ({{ asset.width }}x{{ asset.height }})</option>
                        </select>
                      </label>
                      <label class="field-full">
                        <span>Image link (used when no image is picked above)</span>
                        <input type="text" :value="element.url || ''" placeholder="https://..." @change="setElementUrl(element, ($event.target as HTMLInputElement).value)" />
                      </label>
                      </div></div>
                    </template>

                    <!-- Text Label -->
                    <template v-if="element.type === 'text_label' && !element.box_only">
                      <div class="look-sec"><div class="look-sec-title">Text</div><div class="look-sec-grid">
                      <label class="field-full">
                        <span>What it says</span>
                        <div class="text-var-row">
                          <input type="text" v-model="element.text" placeholder="Enter text, e.g. {audience_rating}" @blur="rememberTextCursor(element, $event)" />
                          <select class="text-var-select" value="" title="Insert a value that's filled in for each movie" @change="insertTextVariable(element, $event)">
                            <option value="" disabled>+ Insert value…</option>
                            <optgroup v-for="g in textVariableGroups" :key="g.group" :label="g.group">
                              <option v-for="v in g.vars" :key="v.key" :value="v.key">
                                {{ v.label }} (e.g. {{ v.example }}){{ v.note && !needsMdblist(v) ? ` · ${v.note}` : '' }}
                              </option>
                            </optgroup>
                          </select>
                        </div>
                        <small class="text-var-hint">Values in {curly braces} are filled in per movie. If a value is missing for a movie, this layer is skipped on that poster.<template v-if="!hasMdblistKey"> Ratings appear in the list once you add an MDBList API key in Settings → General.</template></small>
                      </label>
                      </div></div>
                      <div class="look-sec"><div class="look-sec-title">Font</div><div class="look-sec-grid">
                      <label>
                        <span>Font Size{{ element.placement === 'kometa' ? ' (Kometa size)' : ' (px)' }}</span>
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
                        <span>Font style (variable fonts only, e.g. Bold)</span>
                        <input type="text" :value="element.font_style || ''" placeholder="Leave empty for the font's default"
                          @change="setOptionalText(element, 'font_style', ($event.target as HTMLInputElement).value)" />
                        <small class="text-var-hint">Only fonts with several built-in styles use this. The preview shows the default style.</small>
                      </label>
                      </div></div>
                      <div v-if="element.placement === 'kometa'" class="look-sec"><div class="look-sec-title">Image next to the text</div><div class="look-sec-grid">
                      <label class="field-full">
                        <span>Image</span>
                        <select :value="element.asset_id" @change="setOptionalText(element, 'asset_id', ($event.target as HTMLSelectElement).value)">
                          <option value="">None</option>
                          <option v-for="asset in assets" :key="asset.id" :value="asset.id">{{ asset.name }} ({{ asset.width }}x{{ asset.height }})</option>
                        </select>
                      </label>
                      <label class="field-full">
                        <span>Image link (used when no image is picked above)</span>
                        <input type="text" :value="element.url || ''" placeholder="https://..." @change="setElementUrl(element, ($event.target as HTMLInputElement).value)" />
                      </label>
                      <template v-if="element.asset_id || element.url">
                        <label>
                          <span>Side</span>
                          <select v-model="element.addon_position">
                            <option :value="undefined">Left</option>
                            <option value="right">Right</option>
                            <option value="top">Above</option>
                            <option value="bottom">Below</option>
                          </select>
                        </label>
                        <label>
                          <span>Gap (Kometa px)</span>
                          <input type="number" v-model.number="element.addon_offset" min="0" max="500" step="1" />
                        </label>
                        <label>
                          <span>Image scale</span>
                          <input type="number" v-model.number="element.addon_scale" min="0.05" max="10" step="0.05" placeholder="1" />
                        </label>
                      </template>
                      </div></div>
                    </template>

                    <!-- Blur -->
                    <template v-if="element.type === 'blur'">
                      <div class="look-sec"><div class="look-sec-title">Blur</div><div class="look-sec-grid">
                      <label class="field-full">
                        <span>Strength (1-100, Kometa scale): {{ element.blur_amount || 0 }}</span>
                        <input type="range" v-model.number="element.blur_amount" min="1" max="100" step="1" />
                      </label>
                      </div></div>
                    </template>

                    <KometaPlacementEditor
                      v-if="element.type === 'text_label' || element.type === 'custom_image'"
                      :element="element"
                    />
                    </template>
                  </div>
                </div>
              </div>
              </template>

              <OverlayBadgeSets v-else-if="leftTab === 'sets'" embedded :elements="selectedConfig.elements" />
              <div v-else class="overlay-when">
                <p class="overlay-when-help">
                  Conditions for the whole overlay. When any of them doesn't match a movie, none of this overlay's layers are drawn on
                  its poster. Each layer's own "Show when" still applies on top.
                </p>
                <OverlayRulesEditor :element="selectedConfig" subject="overlay" />
              </div>
            </div>

            <!-- Right: Preview -->
            <div class="preview-column">
              <div class="preview-panel">
                <div class="preview-top-row">
                  <div class="preview-label">Preview</div>
                  <div class="preview-toggles">
                    <label class="drag-toggle" title="Draw elements that are hidden for this item faintly, so you can still see and move them">
                      <input type="checkbox" v-model="showHiddenInPreview" />
                      <span>Show skipped layers</span>
                    </label>
                    <label class="drag-toggle">
                      <input type="checkbox" v-model="dragEnabled" />
                      <span>Drag to move</span>
                    </label>
                  </div>
                </div>

                <!-- What the preview pretends the movie is -->
                <div class="preview-as">
                  <span class="preview-as-label">Preview with</span>
                  <div class="preview-mode-toggle">
                    <button :class="['mode-btn', previewMode === 'testing' && 'active']" @click="previewMode = 'testing'">Example values</button>
                    <button :class="['mode-btn', previewMode === 'item' && 'active']" @click="useRealItem">A real movie or show</button>
                  </div>
                </div>
                <div class="poster-search-row">
                  <button class="btn-search" @click="openMovieSearch" :disabled="posterLoading">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                    </svg>
                    {{ selectedMovie ? selectedMovie.title : (previewMode === 'item' ? 'Pick a movie or show...' : 'Use a real poster as the background...') }}
                  </button>
                  <button v-if="selectedMovie" class="btn-clear-poster" @click="clearPoster" title="Clear">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                  </button>
                </div>

                <p v-if="!overlayMatchesPreview" class="overlay-off-note">
                  This overlay's own conditions don't match this preview, so nothing is drawn.
                  <button type="button" class="btn-link" @click="leftTab = 'when'">See conditions</button>
                </p>
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
                <div v-if="previewMode === 'item' && selectedMovie" class="preview-values item-values">
                  <div v-for="[field, label] in [['video_resolution','Res'],['video_codec','VCodec'],['audio_codec','ACodec'],['audio_channels','Ch'],['audio_language','Lang'],['edition','Edition']]" :key="field" class="preview-value-field">
                    <span>{{ label }}</span>
                    <span class="item-val">{{ previewItemMetadata[(field as string)] || '—' }}</span>
                  </div>
                  <div v-if="hasStreamingBadge" class="preview-value-field">
                    <span>Platform</span>
                    <span class="item-val">{{ previewItemMetadata['streaming_platform'] || '—' }}</span>
                  </div>
                  <div v-if="hasStudioBadge" class="preview-value-field">
                    <span>Studio</span>
                    <span class="item-val">{{ previewItemMetadata['studio'] || '—' }}</span>
                  </div>
                  <template v-if="hasAnyRules">
                    <div class="preview-value-field">
                      <span>Labels</span>
                      <span class="item-val">{{ previewItemLabels.join(', ') || '—' }}</span>
                    </div>
                    <div class="preview-value-field preview-value-wide">
                      <span>File</span>
                      <span class="item-val item-path" :title="previewItemFilePaths.join(', ')">{{ previewItemFilePaths[0] || 'not scanned yet' }}</span>
                    </div>
                  </template>
                </div>
                <div v-else class="preview-values">
                  <label v-if="showTest('resolution')" class="preview-value-field">
                    <span>Resolution</span>
                    <select v-model="previewResolution">
                      <option v-for="v in RESOLUTION_VALUES" :key="v" :value="v">{{ v.toUpperCase() }}</option>
                    </select>
                  </label>
                  <label v-if="showTest('video_codec')" class="preview-value-field">
                    <span>Video Codec</span>
                    <select v-model="previewVideoCodec">
                      <option v-for="v in VIDEO_CODEC_VALUES" :key="v" :value="v">{{ v.toUpperCase() }}</option>
                    </select>
                  </label>
                  <label v-if="showTest('audio_codec')" class="preview-value-field">
                    <span>Audio Codec</span>
                    <select v-model="previewCodec">
                      <option v-for="v in CODEC_VALUES" :key="v" :value="v">{{ v.toUpperCase() }}</option>
                    </select>
                  </label>
                  <label v-if="showTest('audio_channels')" class="preview-value-field">
                    <span>Channels</span>
                    <select v-model="previewAudioChannels">
                      <option v-for="v in AUDIO_CHANNELS_VALUES" :key="v" :value="v">{{ v }}</option>
                    </select>
                  </label>
                  <label v-if="showTest('audio_language')" class="preview-value-field">
                    <span>Language</span>
                    <select v-model="previewAudioLanguage">
                      <option v-for="v in AUDIO_LANGUAGE_VALUES" :key="v" :value="v">{{ v.toUpperCase() }}</option>
                    </select>
                  </label>
                  <label v-if="showTest('edition')" class="preview-value-field">
                    <span>Edition</span>
                    <select v-model="previewEdition">
                      <option v-for="v in EDITION_VALUES" :key="v" :value="v">{{ v.charAt(0).toUpperCase() + v.slice(1) }}</option>
                    </select>
                  </label>
                  <label v-if="hasStreamingBadge && showTest('platform')" class="preview-value-field">
                    <span>Platform</span>
                    <select v-model="previewStreamingPlatform">
                      <option v-for="v in STREAMING_PLATFORM_VALUES" :key="v" :value="v">{{ STREAMING_PLATFORM_LABELS[v] || v }}</option>
                    </select>
                  </label>
                  <label v-if="hasStudioBadge && showTest('studio')" class="preview-value-field">
                    <span>Studio</span>
                    <select v-model="previewStudio">
                      <option v-for="v in STUDIO_VALUES" :key="v" :value="v">{{ STUDIO_LABELS[v] || v }}</option>
                    </select>
                  </label>
                  <template v-if="hasAnyRules || showAllTestValues">
                    <label v-if="showTest('labels')" class="preview-value-field">
                      <span>Labels</span>
                      <input type="text" v-model.lazy="previewLabels" placeholder="comma separated" />
                    </label>
                    <label v-if="showTest('audience_rating')" class="preview-value-field">
                      <span>Audience rating</span>
                      <input type="number" step="0.1" v-model.lazy="previewRating" />
                    </label>
                    <label v-if="showTest('critic_rating')" class="preview-value-field">
                      <span>Critic rating</span>
                      <input type="number" step="0.1" v-model.lazy="previewCriticRating" />
                    </label>
                    <label v-if="showTest('days_since_added')" class="preview-value-field">
                      <span>Days since added</span>
                      <input type="number" min="0" step="1" v-model.lazy="previewDaysAdded" />
                    </label>
                    <label v-if="showTest('show_status')" class="preview-value-field">
                      <span>Show status</span>
                      <select v-model="previewShowStatus">
                        <option value="continuing">Continuing</option>
                        <option value="ended">Ended</option>
                        <option value="canceled">Canceled</option>
                        <option value="upcoming">Upcoming</option>
                      </select>
                    </label>
                    <label v-if="showTest('filepath')" class="preview-value-field preview-value-wide">
                      <span>File path</span>
                      <input type="text" v-model.lazy="previewFilePath" placeholder="/movies/Title (2024)/Title (2024) [Bluray-2160p].mkv" />
                    </label>
                    <div v-if="configLists.length && showTest('list')" class="preview-value-field preview-value-wide">
                      <span>On lists</span>
                      <div class="preview-list-toggles">
                        <label v-for="url in configLists" :key="url" class="preview-list-toggle" :title="url">
                          <input type="checkbox" :checked="previewOnLists.has(url)" @change="togglePreviewList(url)" />
                          {{ listShortName(url) }}
                        </label>
                      </div>
                    </div>
                  </template>
                  <button type="button" class="btn-link more-values" @click="showAllTestValues = !showAllTestValues">
                    {{ showAllTestValues ? 'Only the values this overlay uses' : 'More values' }}
                  </button>
                </div>

                <div class="compare">
                  <label class="drag-toggle">
                    <input type="checkbox" v-model="showCompare" />
                    <span>Compare on several posters</span>
                  </label>
                  <div v-if="showCompare" class="compare-grid">
                    <div v-for="tile in compareTiles" :key="tile.id" class="compare-tile">
                      <canvas :ref="el => setCompareCanvas(tile.id, el)" class="compare-canvas" :width="PREVIEW_W" :height="PREVIEW_H"></canvas>
                      <div class="compare-label" :title="tile.label">
                        <span>{{ tile.label }}</span>
                        <button type="button" class="compare-x" title="Remove" @click="removeCompareTile(tile.id)">✕</button>
                      </div>
                    </div>
                    <button type="button" class="compare-add" @click="pickCompareItem">+ Add a real movie or show</button>
                  </div>
                  <p v-if="showCompare" class="compare-hint">Example posters use the example values above, with only resolution and audio changed.</p>
                </div>

                <div class="preview-info">
                  <span>{{ selectedConfig.elements.length }} layer{{ selectedConfig.elements.length !== 1 ? 's' : '' }}<template v-if="visibleElements.size !== selectedConfig.elements.length"> · {{ visibleElements.size }} drawn on this preview</template></span>
                  <span>2000 x 3000</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="editor-footer">
          <button class="btn-secondary" @click="closeEditor">Cancel</button>
          <button class="btn-primary" @click="saveConfig">Save overlay</button>
        </div>
      </div>
    </div>
    </Teleport>

    <!-- Item Picker Modal (2-step: library → item) -->
    <Teleport to="body">
    <div v-if="showMovieSearch" class="modal-overlay" @click.self="showMovieSearch = false" style="z-index: 1100;">
      <div class="search-modal">
        <div class="search-modal-header">
          <div class="search-modal-title">
            <button v-if="previewSelectedLibrary" class="btn-back" @click="backToLibraries" title="Back to libraries">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="15 18 9 12 15 6"/>
              </svg>
            </button>
            <h3>{{ previewSelectedLibrary ? previewSelectedLibrary.title : 'Select library' }}</h3>
          </div>
          <button class="btn-close" @click="showMovieSearch = false">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="search-modal-body">
          <!-- Step 1: library list -->
          <template v-if="!previewSelectedLibrary">
            <div v-if="previewLibrariesLoading" class="search-empty">Loading libraries...</div>
            <div v-else-if="previewLibraries.length === 0" class="search-empty">No libraries found. Check your media servers in Settings.</div>
            <div v-else class="library-list">
              <button
                v-for="lib in previewLibraries"
                :key="lib.key"
                class="library-btn"
                @click="selectLibrary(lib)"
              >
                <span class="library-icon">{{ lib.type === 'show' ? '📺' : '🎬' }}</span>
                <span class="library-name">{{ lib.title }}</span>
                <span class="library-type">{{ lib.type === 'show' ? 'TV' : 'Movies' }}</span>
              </button>
            </div>
          </template>
          <!-- Step 2: item search -->
          <template v-else>
            <input
              type="text"
              v-model="movieSearchTerm"
              placeholder="Search by title..."
              class="search-input"
              autofocus
            />
            <div class="search-results">
              <div v-if="!moviesLoaded" class="search-empty">Loading...</div>
              <template v-else>
                <button
                  v-for="movie in movieSearchResults"
                  :key="movie.key"
                  class="search-result"
                  @click="selectMovie(movie)"
                >
                  {{ movie.title }}
                </button>
                <div v-if="moviesLoaded && movieSearchResults.length === 0" class="search-empty">No items match that search.</div>
              </template>
            </div>
          </template>
        </div>
      </div>
    </div>
    </Teleport>

    <!-- Asset Upload Modal -->
    <Teleport to="body">
    <div v-if="showAssetUpload" class="modal-overlay" style="z-index: 1100;" @click.self="showAssetUpload = false">
      <div class="upload-modal">
        <div class="upload-header">
          <h3>Upload image</h3>
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
    </Teleport>
    <OverlayRefreshPrompt
      v-if="refreshPrompt"
      :config-id="refreshPrompt.configId"
      :config-name="refreshPrompt.configName"
      :groups="refreshPrompt.groups"
      @close="refreshPrompt = null"
    />
    <KometaImportModal v-if="showKometaImport" @close="showKometaImport = false" @imported="onKometaImported" />
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

.editor-modal { background: var(--surface, #1a1f2e); border: 1px solid var(--border, #2a2f3e); border-radius: 14px; width: 96vw; max-width: 1760px; height: 94vh; max-height: 94vh; display: flex; flex-direction: column; overflow: hidden; }
.editor-header { display: flex; justify-content: space-between; align-items: flex-start; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border, #2a2f3e); }
.editor-header h2 { margin: 0 0 0.4rem 0; color: var(--text-primary, #fff); font-size: 1.15rem; }
.editor-name-row { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
.config-name-input { flex: 1; min-width: 160px; padding: 0.45rem 0.6rem; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border, #2a2f3e); border-radius: 6px; color: var(--text-primary, #fff); font-size: 0.95rem; }
.config-name-input:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.region-selector { display: flex; align-items: center; gap: 0.4rem; white-space: nowrap; }
.region-label { color: var(--text-secondary, #888); font-size: 0.78rem; font-weight: 500; }
.region-select { padding: 0.4rem 0.5rem; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border, #2a2f3e); border-radius: 6px; color: var(--text-primary, #fff); font-size: 0.8rem; cursor: pointer; }
.region-select:focus { outline: none; border-color: var(--accent, #3dd6b7); }

.btn-close { background: none; border: none; color: var(--text-secondary, #aaa); cursor: pointer; padding: 4px; border-radius: 4px; transition: color 0.2s; }
.btn-close:hover { color: var(--text-primary, #fff); }

.editor-body { flex: 1; overflow-y: auto; padding: 1.25rem; }
.editor-columns { display: grid; grid-template-columns: minmax(0, 1fr) 440px; gap: 1.25rem; align-items: start; }

/* Elements column */
.elements-column { display: flex; flex-direction: column; gap: 0.75rem; min-width: 0; }
.elements-header { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 0.25rem; }
.elements-title-row { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.elements-count { font-size: 0.7rem; font-weight: 600; color: var(--text-secondary, #aaa); background: rgba(255, 255, 255, 0.07); border-radius: 10px; padding: 0.05rem 0.45rem; }

.add-menu-wrap { position: relative; }
.btn-add-main { display: flex; align-items: center; gap: 0.35rem; padding: 0.35rem 0.75rem; background: rgba(61, 214, 183, 0.1); border: 1px solid rgba(61, 214, 183, 0.3); border-radius: 6px; color: var(--accent, #3dd6b7); cursor: pointer; font-size: 0.78rem; font-weight: 600; transition: all 0.15s; }
.btn-add-main:hover { background: rgba(61, 214, 183, 0.2); }
.menu-backdrop { position: fixed; inset: 0; z-index: 40; }
.add-menu { position: absolute; right: 0; top: calc(100% + 6px); z-index: 41; width: 300px; background: var(--surface, #1b1f2a); border: 1px solid var(--border, #2a2f3e); border-radius: 8px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45); padding: 0.35rem; }
.add-menu-section + .add-menu-section { border-top: 1px solid var(--border, #2a2f3e); margin-top: 0.3rem; padding-top: 0.3rem; }
.add-menu-title { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary, #888); padding: 0.25rem 0.5rem; }
.add-menu-item { display: grid; grid-template-columns: 10px auto 1fr; align-items: center; gap: 0.5rem; width: 100%; padding: 0.4rem 0.5rem; background: transparent; border: none; border-radius: 5px; color: var(--text-primary, #fff); cursor: pointer; text-align: left; font-size: 0.8rem; }
.add-menu-item:hover { background: rgba(61, 214, 183, 0.1); }
.add-menu-dot { width: 8px; height: 8px; border-radius: 50%; }
.add-menu-label { font-weight: 600; white-space: nowrap; }
.add-menu-hint { color: var(--text-secondary, #888); font-size: 0.7rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.elements-toolbar { display: flex; align-items: center; gap: 0.5rem; }
.elements-search { flex: 1; min-width: 0; padding: 0.35rem 0.55rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 6px; color: var(--text-primary, #fff); font-size: 0.8rem; }
.elements-search:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.btn-link { background: none; border: none; padding: 0.2rem 0.3rem; color: var(--accent, #3dd6b7); cursor: pointer; font-size: 0.74rem; white-space: nowrap; }
.btn-link:hover { text-decoration: underline; }

.empty-elements { padding: 2rem; text-align: center; color: var(--text-secondary, #aaa); font-size: 0.9rem; }

.elements-list { display: flex; flex-direction: column; gap: 0.6rem; }
.element-card { background: rgba(255, 255, 255, 0.015); border: 1px solid var(--border, #2a2f3e); border-radius: 8px; padding: 0.55rem 0.7rem; transition: border-color 0.15s; }
.element-card.element-hovered { border-color: rgba(61, 214, 183, 0.4); }
.element-card.element-dimmed .element-header-left { opacity: 0.6; }

.element-header { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; cursor: pointer; user-select: none; }
.element-card:not(.element-collapsed) .element-header { margin-bottom: 0.6rem; }
.element-header-left { display: flex; align-items: center; gap: 0.5rem; min-width: 0; flex: 1; }
.element-chevron { flex-shrink: 0; color: var(--text-secondary, #888); transition: transform 0.15s; }
.element-chevron.open { transform: rotate(90deg); }
.element-title { display: flex; flex-direction: column; min-width: 0; }
.element-summary { font-size: 0.68rem; color: var(--text-secondary, #888); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.element-actions { display: flex; gap: 0.15rem; flex-shrink: 0; opacity: 0.55; transition: opacity 0.15s; }
.element-card:hover .element-actions { opacity: 1; }
.btn-mini { display: flex; align-items: center; justify-content: center; width: 22px; height: 22px; padding: 0; background: transparent; border: 1px solid transparent; border-radius: 4px; color: var(--text-secondary, #888); cursor: pointer; transition: all 0.15s; }
.btn-mini:hover:not(:disabled) { border-color: var(--border, #2a2f3e); color: var(--text-primary, #fff); background: rgba(255, 255, 255, 0.05); }
.btn-mini.danger:hover:not(:disabled) { border-color: #f87171; color: #f87171; background: rgba(248, 113, 113, 0.1); }
.btn-mini:disabled { opacity: 0.3; cursor: default; }
.element-index { display: flex; align-items: center; justify-content: center; width: 20px; height: 20px; background: rgba(255, 255, 255, 0.08); border-radius: 50%; color: var(--text-secondary, #aaa); font-size: 0.7rem; font-weight: 600; }


.advanced-card { margin-top: 1.25rem; }
.advanced-sub { margin: 0.6rem 0 0.4rem; font-size: 0.95rem; color: var(--text-primary, #fff); }
.look-help { grid-column: 1 / -1; margin: 0; font-size: 0.72rem; color: var(--text-secondary, #888); line-height: 1.4; }
.element-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.section-toggle { display: flex; align-items: center; gap: 0.45rem; background: none; border: none; padding: 0; cursor: pointer; color: inherit; }
.section-chev { display: inline-block; transition: transform 0.15s; color: var(--text-secondary, #888); font-size: 1.1rem; }
.section-chev.open { transform: rotate(90deg); }
.section-note { margin: 0.25rem 0 0; font-size: 0.78rem; color: var(--text-secondary, #888); }
.preview-as { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.4rem; }
.preview-as-label { font-size: 0.75rem; color: var(--text-secondary, #888); }
.more-values { grid-column: 1 / -1; justify-self: start; font-size: 0.72rem; }
.el-tabs { grid-column: 1 / -1; display: flex; gap: 0.25rem; border-bottom: 1px solid var(--border, #2a2f3e); margin-bottom: 0.2rem; }
.el-tabs button { padding: 0.35rem 0.7rem; background: none; border: none; border-bottom: 2px solid transparent; margin-bottom: -1px; color: var(--text-secondary, #888); font-size: 0.76rem; cursor: pointer; }
.el-tabs button:hover { color: var(--text-primary, #fff); }
.el-tabs button.on { color: var(--accent, #3dd6b7); border-bottom-color: var(--accent, #3dd6b7); font-weight: 600; }
.el-tab-count { display: inline-block; margin-left: 0.3rem; padding: 0 0.35rem; border-radius: 8px; background: rgba(61, 214, 183, 0.15); font-size: 0.65rem; }
.text-var-row { display: flex; gap: 0.4rem; align-items: stretch; }
.text-var-row input { flex: 1; min-width: 0; }
.text-var-select { flex: 0 0 auto; max-width: 13rem; background-color: var(--surface-soft, #141824); color-scheme: dark; }
:root[data-theme='light'] .text-var-select { color-scheme: light; }
.text-var-select option, .text-var-select optgroup { background: var(--surface, #1b1f2a); color: var(--text-primary, #fff); }
.text-var-hint { font-size: 0.68rem; color: var(--text-secondary, #888); }
.element-rename { width: 100%; max-width: 22rem; padding: 0.2rem 0.4rem; background: rgba(255, 255, 255, 0.06); border: 1px solid var(--accent, #3dd6b7); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.82rem; font-weight: 600; }
.rename-btn { margin-left: 0.3rem; padding: 0 0.2rem; background: none; border: none; color: var(--text-secondary, #888); font-size: 0.78rem; cursor: pointer; opacity: 0; }
.element-header:hover .rename-btn, .rename-btn:focus { opacity: 1; }
.rename-btn:hover { color: var(--accent, #3dd6b7); }
.overlay-when { display: flex; flex-direction: column; gap: 0.6rem; }
.overlay-when-help { margin: 0; font-size: 0.8rem; color: var(--text-secondary, #aaa); line-height: 1.45; }
.overlay-off-note { margin: 0; padding: 0.45rem 0.6rem; border: 1px solid rgba(251, 191, 36, 0.35); background: rgba(251, 191, 36, 0.07); border-radius: 6px; color: #fbbf24; font-size: 0.72rem; }
.left-tabs { display: flex; gap: 0.25rem; }
.left-tabs button { display: flex; align-items: center; gap: 0.4rem; padding: 0.4rem 0.75rem; background: none; border: none; border-bottom: 2px solid transparent; color: var(--text-secondary, #888); font-size: 0.92rem; font-weight: 600; cursor: pointer; }
.left-tabs button:hover { color: var(--text-primary, #fff); }
.left-tabs button.on { color: var(--text-primary, #fff); border-bottom-color: var(--accent, #3dd6b7); }
.left-tabs .step { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: rgba(255, 255, 255, 0.08); font-size: 0.68rem; }
.left-tabs button.on .step { background: var(--accent, #3dd6b7); color: #0b0f17; }
.layer-hint { margin: 0 0 0.4rem; font-size: 0.7rem; color: var(--text-secondary, #888); }
.element-fields { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.55rem; }
.element-fields label { display: flex; flex-direction: column; gap: 0.2rem; }
.element-fields label.field-full { grid-column: 1 / -1; }
.element-fields label span { color: var(--text-secondary, #888); font-size: 0.72rem; font-weight: 500; }
.element-fields input, .element-fields select { padding: 0.35rem 0.45rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.8rem; }
.element-fields input:focus, .element-fields select:focus { outline: none; border-color: var(--accent, #3dd6b7); }

.element-name { font-size: 0.74rem; color: var(--text-primary, #fff); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.element-hidden { flex-shrink: 0; font-size: 0.66rem; color: var(--text-secondary, #888); border: 1px dashed var(--border, #2a2f3e); border-radius: 4px; padding: 0.05rem 0.35rem; }
.preview-value-wide { grid-column: 1 / -1; }
.preview-list-toggles { display: flex; flex-wrap: wrap; gap: 0.3rem 0.8rem; }
.preview-list-toggle { display: flex; align-items: center; gap: 0.3rem; font-size: 0.75rem; color: var(--text-primary, #fff); cursor: pointer; }
.preview-value-field input { min-width: 0; }
.item-path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left; }
.field-full { grid-column: 1 / -1; }

.color-input-wrap { display: flex; gap: 0.35rem; align-items: stretch; }
.color-picker { width: 32px; height: 28px; padding: 1px; border: 1px solid var(--border, #2a2f3e); border-radius: 4px; background: transparent; cursor: pointer; flex-shrink: 0; }
.color-picker::-webkit-color-swatch-wrapper { padding: 1px; }
.color-picker::-webkit-color-swatch { border: none; border-radius: 2px; }
.color-text { flex: 1; min-width: 0; padding: 0.35rem 0.45rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.78rem; font-family: monospace; }

/* Badge assets mapping */
.badge-assets-section { display: flex; flex-direction: column; gap: 0.4rem; }
/* Look tab: each group of settings in its own titled box */
.look-sec { grid-column: 1 / -1; display: flex; flex-direction: column; gap: 0.5rem; padding: 0.6rem 0.7rem 0.7rem; border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 8px; background: rgba(255, 255, 255, 0.015); }
.look-sec-title { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--accent, #3dd6b7); }
.look-sec-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.55rem; }
.look-sec-help { margin: -0.2rem 0 0; font-size: 0.7rem; color: var(--text-secondary, #888); }

/* Compact badge rows for streaming/studio (override-based layout) */
.badge-override-section { display: flex; flex-direction: column; gap: 4px; margin-bottom: 6px; }
.badge-override-section-label { font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary, #666); }
.badge-default-label { color: var(--text-primary, #ccc) !important; font-style: normal !important; }
.badge-compact-rows { display: flex; flex-direction: column; gap: 3px; }
.badge-compact-row { display: flex; align-items: center; gap: 6px; min-height: 26px; }
.badge-compact-label {
  min-width: 90px;
  max-width: 90px;
  text-align: right;
  font-size: 0.72rem;
  color: var(--text-secondary, #aaa);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 0;
}
.badge-compact-mode {
  width: 90px;
  flex-shrink: 0;
  padding: 0.2rem 0.3rem;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  font-size: 0.72rem;
}
.badge-compact-mode:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.badge-cr-scale {
  width: 50px;
  flex-shrink: 0;
  padding: 0.2rem 0.25rem;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  font-size: 0.72rem;
  text-align: center;
}
.badge-cr-scale:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.badge-cr-anchor {
  width: 110px;
  flex-shrink: 0;
  padding: 0.2rem 0.3rem;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  font-size: 0.72rem;
}
.badge-cr-anchor:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.badge-compact-flex {
  flex: 1;
  min-width: 0;
  padding: 0.2rem 0.3rem;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  font-size: 0.72rem;
}
.badge-compact-flex:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.badge-compact-url-input { font-family: monospace; }
.badge-compact-url-input:focus { border-color: #10b981; }
.badge-remove-override {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  padding: 0;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 3px;
  color: var(--text-secondary, #888);
  font-size: 0.85rem;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.badge-remove-override:hover { background: rgba(239,68,68,0.15); border-color: #ef4444; color: #ef4444; }
.badge-add-override-select {
  width: 100%;
  margin-top: 4px;
  padding: 0.3rem 0.4rem;
  background: rgba(255,255,255,0.03);
  border: 1px dashed rgba(255,255,255,0.15);
  border-radius: 4px;
  color: var(--text-secondary, #888);
  font-size: 0.72rem;
  cursor: pointer;
  transition: border-color 0.15s;
}
.badge-add-override-select:hover { border-color: var(--accent, #3dd6b7); color: var(--text-primary, #fff); }
.badge-add-override-select:focus { outline: none; border-color: var(--accent, #3dd6b7); }

/* Slug alias editor */
.badge-alias-section { margin-top: 6px; display: flex; flex-direction: column; gap: 3px; }
.badge-alias-hint { font-weight: 400; text-transform: none; letter-spacing: 0; color: var(--text-secondary, #666); font-style: italic; }
.badge-alias-row { display: flex; align-items: center; gap: 6px; }
.badge-alias-from { font-size: 0.72rem; color: var(--text-secondary, #aaa); font-family: monospace; min-width: 0; }
.badge-alias-to { font-size: 0.72rem; color: var(--accent, #3dd6b7); font-family: monospace; min-width: 0; }
.badge-alias-arrow { color: var(--text-secondary, #555); font-size: 0.72rem; flex-shrink: 0; }
.badge-alias-add-row { display: flex; align-items: center; gap: 6px; margin-top: 2px; }
.badge-alias-input { flex: 1; min-width: 0; padding: 0.2rem 0.3rem; background: rgba(255,255,255,0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; font-family: monospace; }
.badge-alias-input:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.badge-alias-add-btn { flex-shrink: 0; padding: 0.2rem 0.5rem; background: rgba(61,214,183,0.1); border: 1px solid rgba(61,214,183,0.3); border-radius: 4px; color: var(--accent, #3dd6b7); font-size: 0.72rem; cursor: pointer; transition: all 0.15s; }
.badge-alias-add-btn:hover:not(:disabled) { background: rgba(61,214,183,0.2); border-color: var(--accent, #3dd6b7); }
.badge-alias-add-btn:disabled { opacity: 0.35; cursor: not-allowed; }

.badge-asset-rows { display: flex; flex-direction: column; gap: 0.4rem; }
.badge-asset-item { display: flex; flex-direction: column; gap: 0.25rem; }
.badge-asset-row { display: flex; align-items: center; gap: 0.4rem; }
.badge-image-overrides { display: flex; align-items: center; gap: 0.6rem; padding-left: 76px; }
.badge-image-overrides label { display: flex; align-items: center; gap: 0.3rem; color: var(--text-secondary, #888); font-size: 0.7rem; }
.badge-image-overrides input[type="number"] { width: 4.5rem; padding: 0.25rem 0.35rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.badge-image-overrides select { padding: 0.25rem 0.35rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.badge-image-overrides input:focus, .badge-image-overrides select:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.badge-value-label { color: var(--text-secondary, #aaa); font-size: 0.72rem; font-weight: 600; min-width: 80px; text-align: right; }
.badge-mode-select { width: 68px; flex-shrink: 0; padding: 0.3rem 0.3rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.badge-asset-select { flex: 1; padding: 0.3rem 0.4rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.badge-text-input { flex: 1; padding: 0.3rem 0.4rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.badge-text-input:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.badge-url-input { flex: 1; padding: 0.3rem 0.4rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; font-family: monospace; }
.badge-url-input:focus { outline: none; border-color: #10b981; }
.badge-asset-row select:focus { outline: none; border-color: var(--accent, #3dd6b7); }

/* Text align button group */
.align-btn-group { display: flex; gap: 0; border-radius: 5px; overflow: hidden; border: 1px solid var(--border, #2a2f3e); }
.align-btn-group button { flex: 1; padding: 0.3rem 0.5rem; background: rgba(255, 255, 255, 0.04); border: none; border-right: 1px solid var(--border, #2a2f3e); color: var(--text-secondary, #888); cursor: pointer; font-size: 0.72rem; font-weight: 500; transition: all 0.15s; }
.align-btn-group button:last-child { border-right: none; }
.align-btn-group button:hover { background: rgba(255, 255, 255, 0.08); color: var(--text-primary, #fff); }
.align-btn-group button.active { background: rgba(61, 214, 183, 0.15); color: var(--accent, #3dd6b7); font-weight: 600; }

/* Preview column */
.preview-column { position: sticky; top: 0; }
.preview-panel { background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border, #2a2f3e); border-radius: 10px; padding: 0.75rem; display: flex; flex-direction: column; gap: 0.5rem; overflow-y: auto; max-height: calc(94vh - 170px); }

.preview-top-row { display: flex; justify-content: space-between; align-items: center; }
.preview-label { color: var(--text-secondary, #888); font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }

.preview-toggles { display: flex; align-items: center; gap: 0.75rem; }
.drag-toggle { display: flex; align-items: center; gap: 0.35rem; cursor: pointer; user-select: none; }
.drag-toggle input[type="checkbox"] { width: 14px; height: 14px; accent-color: var(--accent, #3dd6b7); cursor: pointer; }
.drag-toggle span { color: var(--text-secondary, #888); font-size: 0.7rem; }

/* Poster search */
.poster-search-row { display: flex; gap: 0.3rem; }
.btn-search { flex: 1; display: flex; align-items: center; gap: 0.35rem; padding: 0.3rem 0.5rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-secondary, #888); cursor: pointer; font-size: 0.72rem; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: border-color 0.15s; }
.btn-search:hover { border-color: var(--accent, #3dd6b7); color: var(--text-primary, #fff); }
.btn-search:disabled { opacity: 0.5; cursor: wait; }
.btn-search svg { flex-shrink: 0; }

.btn-clear-poster { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; padding: 0; background: transparent; border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-secondary, #888); cursor: pointer; transition: all 0.15s; flex-shrink: 0; }
.btn-clear-poster:hover { border-color: #f87171; color: #f87171; }

.preview-mode-toggle { display: flex; flex-shrink: 0; border: 1px solid var(--border, #2a2f3e); border-radius: 4px; overflow: hidden; }
.mode-btn { padding: 0 0.45rem; height: 24px; background: transparent; border: none; color: var(--text-secondary, #888); cursor: pointer; font-size: 0.68rem; font-weight: 500; transition: all 0.15s; }
.mode-btn.active { background: var(--accent, #3dd6b7); color: #000; }
.mode-btn:not(.active):hover { background: rgba(255,255,255,0.06); color: var(--text-primary,#fff); }

.preview-frame { display: flex; justify-content: center; background: rgba(0, 0, 0, 0.3); border-radius: 6px; padding: 0.5rem; }
.preview-canvas { border-radius: 4px; display: block; }

/* Preview value switchers */
.preview-values { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; }
.preview-value-field { display: flex; flex-direction: column; gap: 0.15rem; }
.preview-value-field span { color: var(--text-secondary, #666); font-size: 0.65rem; font-weight: 500; }
.preview-value-field select { padding: 0.25rem 0.35rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 4px; color: var(--text-primary, #fff); font-size: 0.72rem; }
.preview-value-field select:focus { outline: none; border-color: var(--accent, #3dd6b7); }

.element-warn { color: #fbbf24; font-size: 0.85rem; cursor: help; flex-shrink: 0; }
.warn-list { grid-column: 1 / -1; margin: 0; padding: 0.4rem 0.6rem; list-style: none; border: 1px solid rgba(251, 191, 36, 0.35); background: rgba(251, 191, 36, 0.07); border-radius: 6px; color: #fbbf24; font-size: 0.74rem; line-height: 1.45; }
.compare { display: flex; flex-direction: column; gap: 0.4rem; }
.compare-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.4rem; }
.compare-tile { display: flex; flex-direction: column; gap: 0.2rem; min-width: 0; }
.compare-canvas { width: 100%; height: auto; aspect-ratio: 2 / 3; border-radius: 4px; background: rgba(0, 0, 0, 0.3); display: block; }
.compare-label { display: flex; align-items: center; gap: 0.2rem; font-size: 0.66rem; color: var(--text-secondary, #aaa); min-width: 0; }
.compare-label span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.compare-x { background: none; border: none; color: var(--text-secondary, #888); cursor: pointer; font-size: 0.7rem; padding: 0 0.15rem; }
.compare-x:hover { color: #f87171; }
.compare-add { aspect-ratio: 2 / 3; border: 1px dashed var(--border, #3a4050); border-radius: 4px; background: transparent; color: var(--accent, #3dd6b7); font-size: 0.72rem; cursor: pointer; padding: 0.4rem; }
.compare-hint { margin: 0; font-size: 0.66rem; color: var(--text-secondary, #888); }
.preview-info { display: flex; justify-content: space-between; color: var(--text-secondary, #666); font-size: 0.7rem; }

.editor-footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--border, #2a2f3e); }

.btn-secondary { padding: 0.55rem 1.1rem; background: transparent; color: var(--text-secondary, #aaa); border: 1px solid var(--border, #2a2f3e); border-radius: 6px; cursor: pointer; font-size: 0.88rem; }
.btn-secondary:hover { border-color: var(--text-secondary, #aaa); }

.btn-primary { padding: 0.55rem 1.1rem; background: linear-gradient(135deg, var(--accent, #3dd6b7), #2bc4a6); color: #000; border: none; border-radius: 6px; cursor: pointer; font-size: 0.88rem; font-weight: 500; }
.btn-primary:hover { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

/* Item values read-only display */
.item-values .preview-value-field { flex-direction: row; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.03); border: 1px solid var(--border,#2a2f3e); border-radius: 4px; padding: 0.2rem 0.4rem; }
.item-val { color: var(--accent, #3dd6b7); font-size: 0.72rem; font-weight: 600; }

/* Item picker modal */
.search-modal { background: var(--surface, #1a1f2e); border: 1px solid var(--border, #2a2f3e); border-radius: 12px; width: 90%; max-width: 440px; max-height: 70vh; display: flex; flex-direction: column; overflow: hidden; }
.search-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.25rem; border-bottom: 1px solid var(--border, #2a2f3e); }
.search-modal-title { display: flex; align-items: center; gap: 0.5rem; }
.search-modal-header h3 { margin: 0; color: var(--text-primary, #fff); font-size: 1rem; }
.btn-back { display: flex; align-items: center; justify-content: center; width: 26px; height: 26px; padding: 0; background: rgba(255,255,255,0.05); border: 1px solid var(--border,#2a2f3e); border-radius: 5px; color: var(--text-secondary,#888); cursor: pointer; transition: all 0.15s; }
.btn-back:hover { border-color: var(--accent,#3dd6b7); color: var(--accent,#3dd6b7); }
.library-list { display: flex; flex-direction: column; gap: 0.4rem; }
.library-btn { display: flex; align-items: center; gap: 0.6rem; padding: 0.6rem 0.8rem; background: rgba(255,255,255,0.03); border: 1px solid var(--border,#2a2f3e); border-radius: 7px; color: var(--text-primary,#fff); cursor: pointer; font-size: 0.88rem; text-align: left; transition: all 0.15s; }
.library-btn:hover { border-color: var(--accent,#3dd6b7); background: rgba(61,214,183,0.07); }
.library-icon { font-size: 1rem; }
.library-name { flex: 1; font-weight: 500; }
.library-type { font-size: 0.72rem; color: var(--text-secondary,#888); background: rgba(255,255,255,0.06); border-radius: 3px; padding: 0.1rem 0.35rem; }
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
  .editor-modal { width: 96%; height: 94vh; }
  .editor-columns { grid-template-columns: 1fr; }
  .preview-column { position: static; order: -1; }
  .upload-modal { width: 96%; }
}

.beta-badge {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  vertical-align: middle;
  background: rgba(139, 92, 246, 0.18);
  color: #a78bfa;
}
</style>
