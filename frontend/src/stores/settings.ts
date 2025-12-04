import { ref } from 'vue'

const apiBase = import.meta.env.VITE_API_URL || window.location.origin

export type Theme = 'neon' | 'slate' | 'dracula' | 'nord' | 'oled' | 'light'

export type PlexSettings = {
  url: string
  token: string
  movieLibraryName: string
}

export type TMDBSettings = {
  apiKey: string
}

export type TVDBSettings = {
  apiKey: string
  comingSoon?: boolean
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
}

export type UISettings = {
  theme: Theme
  posterDensity: number
  defaultLabelsToRemove?: string[]
  saveLocation?: string
  saveBatchInSubfolder?: boolean
  plex?: PlexSettings
  tmdb?: TMDBSettings
  tvdb?: TVDBSettings
  imageQuality?: ImageQualitySettings
  performance?: PerformanceSettings
}

const theme = ref<Theme>('neon')
const posterDensity = ref(20)
const defaultLabelsToRemove = ref<string[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const loaded = ref(false)
const saveLocation = ref<string>('/output')
const saveBatchInSubfolder = ref<boolean>(false)
const plex = ref<PlexSettings>({ url: '', token: '', movieLibraryName: '' })
const tmdb = ref<TMDBSettings>({ apiKey: '' })
const tvdb = ref<TVDBSettings>({ apiKey: '', comingSoon: true })
const imageQuality = ref<ImageQualitySettings>({ outputFormat: 'jpg', jpgQuality: 95, pngCompression: 6, webpQuality: 90 })
const performance = ref<PerformanceSettings>({ concurrentRenders: 2, tmdbRateLimit: 40, tvdbRateLimit: 20, memoryLimit: 2048 })

async function loadSettings() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch(`${apiBase}/api/ui-settings`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = (await res.json()) as UISettings
    theme.value = data.theme || 'neon'
    posterDensity.value = Number(data.posterDensity) || 20
    defaultLabelsToRemove.value = data.defaultLabelsToRemove || []
    loaded.value = true
    saveLocation.value = data.saveLocation ?? "/output"
    saveBatchInSubfolder.value = !!data.saveBatchInSubfolder
    plex.value = {
      url: data.plex?.url ?? '',
      token: data.plex?.token ?? '',
      movieLibraryName: data.plex?.movieLibraryName ?? ''
    }
    tmdb.value = { apiKey: data.tmdb?.apiKey ?? '' }
    tvdb.value = { apiKey: data.tvdb?.apiKey ?? '', comingSoon: data.tvdb?.comingSoon ?? true }
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
      memoryLimit: data.performance?.memoryLimit ?? 2048
    }

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
      saveLocation: saveLocation.value,
      saveBatchInSubfolder: saveBatchInSubfolder.value,
      plex: { ...plex.value },
      tmdb: { ...tmdb.value },
      tvdb: { ...tvdb.value },
      imageQuality: { ...imageQuality.value },
      performance: { ...performance.value }
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
    plex,
    tmdb,
    tvdb,
    imageQuality,
    performance,
    loading,
    error,
    loaded,
    saveLocation,
    saveBatchInSubfolder,
    load: loadSettings,
    save: saveSettings
  }
}
