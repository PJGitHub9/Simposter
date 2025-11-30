import { ref } from 'vue'

const apiBase = import.meta.env.VITE_API_URL || window.location.origin

export type Theme = 'neon' | 'slate' | 'dracula' | 'nord' | 'oled' | 'light'

export type UISettings = {
  theme: Theme
  showBoundingBoxes: boolean
  autoSave: boolean
  posterDensity: number
  defaultLabelsToRemove?: string[]
  saveLocation?: string
}

const theme = ref<Theme>('neon')
const showBoundingBoxes = ref(true)
const autoSave = ref(false)
const posterDensity = ref(20)
const defaultLabelsToRemove = ref<string[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const loaded = ref(false)
const saveLocation = ref<string>('/output')

async function loadSettings() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch(`${apiBase}/api/ui-settings`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = (await res.json()) as UISettings
    theme.value = data.theme || 'neon'
    showBoundingBoxes.value = !!data.showBoundingBoxes
    autoSave.value = !!data.autoSave
    posterDensity.value = Number(data.posterDensity) || 20
    defaultLabelsToRemove.value = data.defaultLabelsToRemove || []
    loaded.value = true
    saveLocation.value = data.saveLocation ?? "/output"

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
      showBoundingBoxes: showBoundingBoxes.value,
      autoSave: autoSave.value,
      posterDensity: posterDensity.value,
      defaultLabelsToRemove: defaultLabelsToRemove.value,
      saveLocation: saveLocation.value
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
    showBoundingBoxes,
    autoSave,
    posterDensity,
    defaultLabelsToRemove,
    loading,
    error,
    loaded,
    saveLocation,
    load: loadSettings,
    save: saveSettings
  }
}
