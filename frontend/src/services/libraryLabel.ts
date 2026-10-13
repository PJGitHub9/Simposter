// Shared "what should we call this library_id in the UI" helper. A library_id
// is either a Plex section id (short digits, listed in plex.libraryMappings /
// tvShowLibraryMappings) or a Jellyfin/Emby library GUID that only appears as
// a LibraryGroup member. Looking only at the Plex mappings (what several views
// used to do) shows a raw GUID for every Jellyfin/Emby library -- so every
// place that turns a library_id into a name should go through here.
import { useSettingsStore } from '@/stores/settings'

export type LibraryInfo = {
  label: string
  mediaType: 'movie' | 'tv' | null
  // Which server the library belongs to -- what the sidebar/routes pass as
  // ?server= (Phase 8a). 'plex-1' for a Plex mapping.
  serverId: string | null
}

export function libraryInfo(libraryId: string | null | undefined): LibraryInfo | null {
  if (!libraryId) return null
  const settings = useSettingsStore()
  const id = String(libraryId)

  const movieLib = settings.plex.value.libraryMappings?.find(m => String(m.id) === id)
  if (movieLib) return { label: movieLib.displayName || movieLib.title || id, mediaType: 'movie', serverId: 'plex-1' }
  const tvLib = settings.plex.value.tvShowLibraryMappings?.find(m => String(m.id) === id)
  if (tvLib) return { label: tvLib.displayName || tvLib.title || id, mediaType: 'tv', serverId: 'plex-1' }

  for (const g of settings.libraryGroups.value || []) {
    const member = (g.members || []).find(m => String(m.libraryId) === id)
    if (member) {
      return {
        label: g.name || member.libraryName || id,
        mediaType: g.mediaType === 'tv' ? 'tv' : 'movie',
        serverId: member.serverId || null,
      }
    }
  }
  return null
}

export function libraryLabel(libraryId: string | null | undefined, fallback = '—'): string {
  if (!libraryId) return fallback
  return libraryInfo(libraryId)?.label || String(libraryId)
}
