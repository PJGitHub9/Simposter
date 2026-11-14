// Which Plex labels to remove when a poster is sent, for one library.
// Mirrors backend/api/webhooks.py _get_default_remove_labels(): a library id is
// looked up in both the movie and the TV list (Plex library ids are unique per
// server, and the setup wizard has stored TV libraries in the movie list), and
// "Overlay" is always included while Kometa compatibility is on.
import { useSettingsStore } from '@/stores/settings'

export const KOMETA_LABEL = 'Overlay'

type LabelMap = Record<string, string[]> | string[] | null | undefined

function listFor(map: LabelMap, libraryId: string): string[] {
  if (!map) return []
  if (Array.isArray(map)) return map
  return map[libraryId] || []
}

function allIn(map: LabelMap): string[] {
  if (!map) return []
  if (Array.isArray(map)) return map
  return Object.values(map).flat()
}

export function kometaCompatibilityOn(): boolean {
  const settings = useSettingsStore()
  return !!settings.automation.value?.kometaCompatibility
}

// libraryId omitted: every library of that media type (used where the page has
// no library context).
export function labelsToRemoveFor(libraryId: string | number | null | undefined, mediaType: 'movie' | 'tv'): string[] {
  const settings = useSettingsStore()
  const movie = settings.defaultLabelsToRemove.value as LabelMap
  const tv = settings.defaultTvLabelsToRemove.value as LabelMap
  const out = new Set<string>()
  if (libraryId != null && libraryId !== '') {
    const id = String(libraryId)
    listFor(movie, id).forEach(l => out.add(l))
    listFor(tv, id).forEach(l => out.add(l))
  } else {
    allIn(mediaType === 'tv' ? tv : movie).forEach(l => out.add(l))
  }
  if (kometaCompatibilityOn()) out.add(KOMETA_LABEL)
  return [...out].filter(Boolean)
}
