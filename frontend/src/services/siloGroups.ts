// Silo keeps one poster, logo and backdrop per title for all its libraries
// (CLAUDE.md Quirk #240). When Silo libraries sit in more than one library
// group, a title in two of them shares one image: Settings shows a note.
import type { LibraryGroup, MediaServerEntry } from '@/stores/settings'

export function isSiloServer(serverId: string, servers: MediaServerEntry[]): boolean {
  const s = servers.find(x => x.id === serverId)
  return (s?.type || serverId.split('-')[0]) === 'silo'
}

/** Names of the library groups that include a Silo library. */
export function siloGroupNames(groups: LibraryGroup[], servers: MediaServerEntry[]): string[] {
  return (groups || [])
    .filter(g => (g.members || []).some(m => isSiloServer(m.serverId, servers)))
    .map(g => g.name || g.id)
}

export function siloSharedImageNote(names: string[]): string {
  return 'Silo keeps one poster, logo and backdrop per title for all its libraries. A title in more than one '
    + `of these groups (${names.join(', ')}) shares one image there; the last send wins.`
}
