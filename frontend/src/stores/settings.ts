import { ref } from 'vue'
import { getApiBase } from '../services/apiBase'

const apiBase = getApiBase()

export type Theme = 'neon' | 'slate' | 'dracula' | 'nord' | 'oled' | 'light'

export type PlexSettings = {
  url: string
  token: string
  movieLibraryName: string
  movieLibraryNames?: string[]
  libraryMappings?: Array<{ id: string; title?: string; displayName?: string }>
  tvShowLibraryName?: string
  tvShowLibraryNames?: string[]
  tvShowLibraryMappings?: Array<{ id: string; title?: string; displayName?: string }>
}

export type TMDBSettings = {
  apiKey: string
}

export type TVDBSettings = {
  apiKey: string
  comingSoon?: boolean
}

export type FanartSettings = {
  apiKey: string
}

export type ImageQualitySettings = {
  outputFormat: string
  jpgQuality: number
  pngCompression: number
  webpQuality: number
}

export type PerformanceSettings = {
  concurrentRenders: number
  tmdbRateLimit: number
  tvdbRateLimit: number
  memoryLimit: number
  useOverlayCache: boolean
}

export type UISettings = {
  theme: Theme
  posterDensity: number
  defaultLabelsToRemove?: string[] | Record<string, string[]>
  defaultTvLabelsToRemove?: string[] | Record<string, string[]>
  saveLocation?: string
  saveBatchInSubfolder?: boolean
  plex?: PlexSettings
  tmdb?: TMDBSettings
  tvdb?: TVDBSettings
  fanart?: FanartSettings
  imageQuality?: ImageQualitySettings
  performance?: PerformanceSettings
  apiOrder?: string[]
}

const theme = ref<Theme>('neon')
const posterDensity = ref(20)
const defaultLabelsToRemove = ref<Record<string, string[]>>({})
const defaultTvLabelsToRemove = ref<Record<string, string[]>>({})
const loading = ref(false)
const error = ref<string | null>(null)
const loaded = ref(false)
const saveLocation = ref<string>('/output')
const saveBatchInSubfolder = ref<boolean>(false)
const plex = ref<PlexSettings>({ url: '', token: '', movieLibraryName: '', movieLibraryNames: [], libraryMappings: [], tvShowLibraryName: '', tvShowLibraryNames: [], tvShowLibraryMappings: [] })
const tmdb = ref<TMDBSettings>({ apiKey: '' })
const tvdb = ref<TVDBSettings>({ apiKey: '', comingSoon: false })
const fanart = ref<FanartSettings>({ apiKey: '' })
const imageQuality = ref<ImageQualitySettings>({ outputFormat: 'jpg', jpgQuality: 95, pngCompression: 6, webpQuality: 90 })
const performance = ref<PerformanceSettings>({ concurrentRenders: 2, tmdbRateLimit: 40, tvdbRateLimit: 20, memoryLimit: 2048, useOverlayCache: true })
const apiOrder = ref<string[]>(['tmdb', 'fanart', 'tvdb'])

async function loadSettings() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch(`${apiBase}/api/ui-settings`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = (await res.json()) as UISettings
    theme.value = data.theme || 'neon'
    posterDensity.value = Number(data.posterDensity) || 20
    // Handle both legacy array format and new Record format
    if (Array.isArray(data.defaultLabelsToRemove)) {
      // Legacy format: convert to new format using first library as default
      defaultLabelsToRemove.value = { 'default': data.defaultLabelsToRemove }
    } else {
      defaultLabelsToRemove.value = data.defaultLabelsToRemove || {}
    }
    // Load TV labels (same logic as movie labels)
    if (Array.isArray(data.defaultTvLabelsToRemove)) {
      defaultTvLabelsToRemove.value = { 'default': data.defaultTvLabelsToRemove }
    } else {
      defaultTvLabelsToRemove.value = data.defaultTvLabelsToRemove || {}
    }
    loaded.value = true
    saveLocation.value = data.saveLocation ?? "/output"
    saveBatchInSubfolder.value = !!data.saveBatchInSubfolder
    plex.value = {
      url: data.plex?.url ?? '',
      token: data.plex?.token ?? '',
      movieLibraryName: data.plex?.movieLibraryName ?? '',
      movieLibraryNames: data.plex?.movieLibraryNames ?? (data.plex?.movieLibraryName ? [data.plex.movieLibraryName] : []),
      libraryMappings: data.plex?.libraryMappings ?? [],
      tvShowLibraryName: data.plex?.tvShowLibraryName ?? '',
      tvShowLibraryNames: data.plex?.tvShowLibraryNames ?? (data.plex?.tvShowLibraryName ? [data.plex.tvShowLibraryName] : []),
      tvShowLibraryMappings: data.plex?.tvShowLibraryMappings ?? []
    }
    tmdb.value = { apiKey: data.tmdb?.apiKey ?? '' }
    tvdb.value = { apiKey: data.tvdb?.apiKey ?? '', comingSoon: data.tvdb?.comingSoon ?? true }
    fanart.value = { apiKey: data.fanart?.apiKey ?? '' }
    imageQuality.value = {
      outputFormat: data.imageQuality?.outputFormat ?? 'jpg',
      jpgQuality: data.imageQuality?.jpgQuality ?? 95,
      pngCompression: data.imageQuality?.pngCompression ?? 6,
      webpQuality: data.imageQuality?.webpQuality ?? 90
    }
    performance.value = {
      concurrentRenders: data.performance?.concurrentRenders ?? 2,
      tmdbRateLimit: data.performance?.tmdbRateLimit ?? 40,
      tvdbRateLimit: data.performance?.tvdbRateLimit ?? 20,
      memoryLimit: data.performance?.memoryLimit ?? 2048,
      useOverlayCache: data.performance?.useOverlayCache ?? true
    }
    apiOrder.value = data.apiOrder ?? ['tmdb', 'fanart', 'tvdb']

  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'Failed to load settings'
    error.value = message
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  loading.value = true
  error.value = null
  try {
    const payload: UISettings = {
      theme: theme.value,
      posterDensity: posterDensity.value,
      defaultLabelsToRemove: defaultLabelsToRemove.value,
      defaultTvLabelsToRemove: defaultTvLabelsToRemove.value,
      saveLocation: saveLocation.value,
      saveBatchInSubfolder: saveBatchInSubfolder.value,
      plex: { ...plex.value },
      tmdb: { ...tmdb.value },
      tvdb: { ...tvdb.value },
      fanart: { ...fanart.value },
      imageQuality: { ...imageQuality.value },
      performance: { ...performance.value },
      apiOrder: apiOrder.value
    }
    const res = await fetch(`${apiBase}/api/ui-settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!res.ok) throw new Error(`API error ${res.status}`)
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'Failed to save settings'
    error.value = message
  } finally {
    loading.value = false
  }
}

export function useSettingsStore() {
  if (!loaded.value && !loading.value) {
    loadSettings()
  }

  return {
    theme,
    posterDensity,
    defaultLabelsToRemove,
    defaultTvLabelsToRemove,
    plex,
    tmdb,
    tvdb,
    fanart,
    imageQuality,
    performance,
    apiOrder,
    loading,
    error,
    loaded,
    saveLocation,
    saveBatchInSubfolder,
    load: loadSettings,
    save: saveSettings
  }
}
