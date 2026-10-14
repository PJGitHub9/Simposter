import { ref } from 'vue'
import type { PresetOptions } from './types'
import { getApiBase } from './apiBase'

const apiBase = getApiBase()

type PresetRecord = { id: string; name?: string; options?: PresetOptions; season_options?: PresetOptions }

export function usePresetService() {
  const templates = ref<string[]>(['uniformlogo'])
  const presets = ref<PresetRecord[]>([])
  const selectedTemplate = ref('uniformlogo')
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
      templates.value = tplKeys.length ? tplKeys : ['uniformlogo']
      if (!tplKeys.includes(selectedTemplate.value)) {
        selectedTemplate.value = templates.value[0] || 'uniformlogo'
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

  const deriveSeasonOptions = (opts: PresetOptions): PresetOptions => {
    const base = { ...(opts || {}) } as Record<string, any>
    return {
      ...base,
      logo_mode: 'none',
      text_overlay_enabled: true,
      custom_text: '{season}',
      font_family: 'Arial',
      font_size: 150,
      shadow_enabled: false,
      shadow_blur: 0,
      letter_spacing: 1,
      position_y: 0.85,
      // Custom Text sits in its own box: a full-width band near the bottom.
      text_bbox_enabled: true,
      text_box_max_w: 1800,
      text_box_max_h: 600,
      text_box_offset_x: 0.5,
      text_box_offset_y: 0.85,
      text_box_h_align: 'center',
      text_box_v_align: 'center',
    }
  }

  const savePreset = async (options?: PresetOptions) => {
    if (!selectedTemplate.value || !selectedPreset.value) return
    loading.value = true
    error.value = null
    try {
      const baseOptions = options ?? presets.value.find((p) => p.id === selectedPreset.value)?.options ?? {}
      // No season_options: the backend keeps the preset's saved season config. Sending the
      // derived defaults here used to reset the season poster on every series/movie save.
      const payload = {
        template_id: selectedTemplate.value,
        preset_id: selectedPreset.value,
        options: baseOptions
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

  // seasonOptions: the new preset's season config (a full option set). When omitted, the
  // source preset's saved season differences are carried over on top of the new base, or the
  // standard season defaults are used if the source has none.
  const savePresetAs = async (presetId: string, options?: PresetOptions, seasonOptions?: PresetOptions) => {
    const targetId = presetId.trim()
    if (!targetId) return

    loading.value = true
    error.value = null
    try {
      const source = presets.value.find((p) => p.id === selectedPreset.value)
      const baseOptions = options ?? source?.options ?? {}
      const sourceSeason = (source?.season_options || {}) as Record<string, any>
      const season = seasonOptions
        ?? (Object.keys(sourceSeason).length
          ? ({ ...(baseOptions as Record<string, any>), ...sourceSeason } as PresetOptions)
          : deriveSeasonOptions(baseOptions))
      const payload = {
        template_id: selectedTemplate.value || 'uniformlogo',
        preset_id: targetId,
        options: baseOptions,
        season_options: season
      }
      const res = await fetch(`${apiBase}/api/presets/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!res.ok) throw new Error(`API error ${res.status}`)
      await load()
      // Select the newly created preset if it now exists
      if (presets.value.find((p) => p.id === targetId)) {
        selectedPreset.value = targetId
      }
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to save preset'
      error.value = message
    } finally {
      loading.value = false
    }
  }

  return { templates, presets, selectedTemplate, selectedPreset, loading, error, load, savePreset, savePresetAs }
}
