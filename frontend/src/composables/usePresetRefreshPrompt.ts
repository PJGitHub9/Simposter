// After a preset save that changed its overlays, ask whether to refresh the
// posters Overlay Refresh tracks for that preset. Used by Template Manager and
// both poster editors; render <PresetRefreshPrompt> when `prompt` is set.
import { ref } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { overlayListsChanged, type PresetOverlayLists } from '@/services/presetOverlayLists'

export interface PresetPromptGroup {
  group_id: string
  group_name: string
  matching: { keys: string[]; items: Array<{ title: string; servers: string[] }> }
  different: { keys: string[]; items: Array<{ title: string; servers: string[] }> }
  running: boolean
}

export interface PresetPromptState {
  templateId: string
  presetId: string
  presetName: string
  old: PresetOverlayLists
  groups: PresetPromptGroup[]
  total_matching: number
  total_different: number
}

export function usePresetRefreshPrompt() {
  const prompt = ref<PresetPromptState | null>(null)

  async function offer(
    templateId: string,
    presetId: string,
    presetName: string,
    before: PresetOverlayLists,
    after: PresetOverlayLists,
  ): Promise<void> {
    if (!overlayListsChanged(before, after)) return
    try {
      const res = await fetch(`${getApiBase()}/api/overlay-refresh/by-preset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_id: templateId, preset_id: presetId, old: before }),
      })
      if (!res.ok) return
      const data = await res.json()
      if ((data.total_matching || 0) + (data.total_different || 0) === 0) return
      prompt.value = { templateId, presetId, presetName, old: before, ...data }
    } catch {
      // The save itself already succeeded; the prompt is optional.
    }
  }

  function close() {
    prompt.value = null
  }

  return { prompt, offer, close }
}
