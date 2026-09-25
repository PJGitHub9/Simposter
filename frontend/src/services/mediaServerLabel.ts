// Shared "what should we call this server in the UI" helper -- used
// anywhere a server_id needs to become a human-readable label: the manual
// editor's preview toggle/send picker, the grid's resend modal, the top nav
// status badge, and Settings' own linked-library chips. Consolidated here
// (rather than each call site deriving its own label) specifically so a
// custom `name` (added so a user with two Jellyfin servers can tell them
// apart -- e.g. "pj-jellyfin") is honored everywhere consistently, instead
// of some places showing the name and others silently falling back to a
// generic "Jellyfin" because they never got updated.
import type { MediaServerEntry } from '@/stores/settings'

export function mediaServerTypeLabel(type: string): string {
  return type === 'jellyfin' ? 'Jellyfin' : type === 'emby' ? 'Emby' : type === 'plex' ? 'Plex' : type
}

export function mediaServerLabel(serverId: string, mediaServers: MediaServerEntry[]): string {
  const entry = mediaServers.find(s => s.id === serverId)
  if (serverId === 'plex-1') {
    // Primary Plex can be named too (Settings -> Media Servers), same as any
    // other server -- falls back to the plain generic 'Plex' label when unset.
    return entry?.name && entry.name.trim() ? entry.name.trim() : 'Plex'
  }
  if (!entry) return serverId
  if (entry.name && entry.name.trim()) return entry.name.trim()
  return mediaServerTypeLabel(entry.type)
}
