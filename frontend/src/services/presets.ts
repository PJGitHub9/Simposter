import { ref } from 'vue'
import type { PresetOptions } from './types'

const apiBase = import.meta.env.VITE_API_URL || window.location.origin

export function usePresetService() {
  const templates = ref<string[]>(['default'])
  const presets = ref<{ id: string; name?: string; options?: PresetOptions }[]>([])
  const selectedTemplate = ref('default')
  const selectedPreset = ref('')
  const loading = ref(false)
  const error = ref<string | null>(null)

  const load = async () => {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(`${apiBase}/api/presets`)
      if (!res.ok) throw new Error(`API error ${res.status}`)
      const data = await res.json()
      const tplKeys = Object.keys(data)
      templates.value = tplKeys.length ? tplKeys : ['default']
      if (!tplKeys.includes(selectedTemplate.value)) {
        selectedTemplate.value = templates.value[0] || 'default'
      }
      presets.value = data[selectedTemplate.value]?.presets || []
      if (!presets.value.find((p) => p.id === selectedPreset.value)) {
        selectedPreset.value = presets.value[0]?.id || ''
      }
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to load presets'
      error.value = message
    } finally {
      loading.value = false
    }
  }

  const savePreset = async (options?: PresetOptions) => {
    if (!selectedTemplate.value || !selectedPreset.value) return
    loading.value = true
    error.value = null
    try {
      const payload = {
        template_id: selectedTemplate.value,
        preset_id: selectedPreset.value,
        options: options ?? presets.value.find((p) => p.id === selectedPreset.value)?.options ?? {}
      }
      const res = await fetch(`${apiBase}/api/presets/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!res.ok) throw new Error(`API error ${res.status}`)
      await load()
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to save preset'
      error.value = message
    } finally {
      loading.value = false
    }
  }

  return { templates, presets, selectedTemplate, selectedPreset, loading, error, load, savePreset }
}
