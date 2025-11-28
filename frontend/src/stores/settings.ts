import { ref } from 'vue'

const apiBase = import.meta.env.VITE_API_URL || window.location.origin

export type Theme = 'neon' | 'slate' | 'dracula' | 'nord' | 'oled' | 'light'

export type UISettings = {
  theme: Theme
  showBoundingBoxes: boolean
  autoSave: boolean
  posterDensity: number
  defaultLabelsToRemove?: string[]
}

const theme = ref<Theme>('neon')
const showBoundingBoxes = ref(true)
const autoSave = ref(false)
const posterDensity = ref(20)
const defaultLabelsToRemove = ref<string[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const loaded = ref(false)

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
  } catch (e: any) {
    error.value = e?.message || 'Failed to load settings'
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
      defaultLabelsToRemove: defaultLabelsToRemove.value
    }
    const res = await fetch(`${apiBase}/api/ui-settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!res.ok) throw new Error(`API error ${res.status}`)
  } catch (e: any) {
    error.value = e?.message || 'Failed to save settings'
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
    load: loadSettings,
    save: saveSettings
  }
}
