// Library group proposals for the setup wizard's "Library groups" step.
// Libraries picked on different servers with the same name (ignoring case,
// spaces, dashes and underscores) become one group. Ids follow the scheme Settings uses, so a
// later edit there finds the same group: a Plex member anchors it
// (group-{type}-{plexLibraryId}), else group-{type}-{serverId}-{libraryId}.
// A group never holds two libraries from the same server.
import type { LibraryGroup, LibraryGroupMember } from '@/stores/settings'

export type LibCandidate = { serverId: string; libraryId: string; libraryName: string; mediaType: 'movie' | 'tv' }

// "4k Movies", "4K-Movies" and "4k_movies" match; "Movies" and "4K Movies" don't.
export const nameKey = (name: string) => name.toLowerCase().replace(/[-_\s]+/g, ' ').trim()

export const memberKey = (m: { serverId: string; libraryId: string }) => `${m.serverId}:${m.libraryId}`

export const finalGroupId = (g: Pick<LibraryGroup, 'mediaType' | 'members'>): string => {
  const plex = g.members.find(m => m.serverId === 'plex-1')
  if (plex) return `group-${g.mediaType}-${plex.libraryId}`
  const first = g.members[0]
  return first ? `group-${g.mediaType}-${first.serverId}-${first.libraryId}` : `group-${g.mediaType}-empty`
}

const newGroup = (mediaType: 'movie' | 'tv', members: LibraryGroupMember[], name: string, id?: string): LibraryGroup => {
  const g: LibraryGroup = {
    id: '',
    name,
    mediaType,
    members,
    autoGenerateEnabled: false,
    autoGeneratePresetId: null,
    autoGenerateTemplateId: null,
    labelsToRemove: [],
  }
  g.id = id || finalGroupId(g)
  return g
}

let newCounter = 0

/** New groups for the candidates that aren't in an existing group yet. */
export const proposeGroups = (candidates: LibCandidate[], existing: LibraryGroup[]): LibraryGroup[] => {
  const taken = new Set(existing.flatMap(g => g.members.map(memberKey)))
  const buckets = new Map<string, LibCandidate[][]>()
  for (const c of candidates) {
    if (taken.has(memberKey(c))) continue
    taken.add(memberKey(c))
    const key = `${c.mediaType}:${nameKey(c.libraryName || c.libraryId)}`
    const groups = buckets.get(key) || []
    // Same name but this server already in the group: start another group.
    const slot = groups.find(g => !g.some(x => x.serverId === c.serverId))
    if (slot) slot.push(c)
    else groups.push([c])
    buckets.set(key, groups)
  }
  const result: LibraryGroup[] = []
  const ids = new Set(existing.map(g => g.id))
  for (const groups of buckets.values()) {
    for (const members of groups) {
      const anchor = members.find(m => m.serverId === 'plex-1') || members[0]!
      const g = newGroup(
        anchor.mediaType,
        members.map(m => ({ serverId: m.serverId, libraryId: m.libraryId, libraryName: m.libraryName })),
        anchor.libraryName || anchor.libraryId,
      )
      // Ids are only keys while editing; finalizeGroups() picks the saved id.
      if (ids.has(g.id)) g.id = `new-${Date.now()}-${newCounter++}`
      ids.add(g.id)
      result.push(g)
    }
  }
  return result
}

/** Groups a member can move into: same media type, not its own, no library from its server. */
export const moveTargets = (draft: LibraryGroup[], fromId: string, member: { serverId: string; libraryId: string }, mediaType: 'movie' | 'tv') =>
  draft.filter(g => g.id !== fromId && g.mediaType === mediaType && !g.members.some(m => m.serverId === member.serverId))

/** Move a member to another group ('new' = a group of its own). Groups left
 *  empty are removed unless they're existing (saved) groups. */
export const moveMember = (draft: LibraryGroup[], fromId: string, key: string, toId: string, existingIds: Set<string>): LibraryGroup[] => {
  const groups = draft.map(g => ({ ...g, members: [...g.members] }))
  const from = groups.find(g => g.id === fromId)
  if (!from) return draft
  const idx = from.members.findIndex(m => memberKey(m) === key)
  if (idx < 0) return draft
  const [member] = from.members.splice(idx, 1)
  if (toId === 'new') {
    groups.push(newGroup(from.mediaType, [member!], member!.libraryName || member!.libraryId, `new-${Date.now()}-${newCounter++}`))
  } else {
    const to = groups.find(g => g.id === toId)
    if (!to || to.members.some(m => m.serverId === member!.serverId)) return draft
    to.members.push(member!)
  }
  return groups.filter(g => g.members.length > 0 || existingIds.has(g.id))
}

/** The groups to save: existing groups keep their id (name/new members applied),
 *  new groups get their id from their members. */
export const finalizeGroups = (draft: LibraryGroup[], existing: LibraryGroup[]): LibraryGroup[] => {
  const existingIds = new Set(existing.map(g => g.id))
  const used = new Set<string>()
  const out: LibraryGroup[] = []
  for (const g of existing) {
    const d = draft.find(x => x.id === g.id)
    out.push(d ? { ...g, name: d.name.trim() || g.name, members: d.members } : g)
    used.add(g.id)
  }
  for (const d of draft) {
    if (existingIds.has(d.id) || !d.members.length) continue
    let id = finalGroupId(d)
    for (let n = 2; used.has(id); n++) id = `${finalGroupId(d)}-${n}`
    used.add(id)
    out.push({ ...d, id, name: d.name.trim() || d.members[0]!.libraryName || id })
  }
  return out
}

const shape = (gs: LibraryGroup[]) => JSON.stringify(gs.map(g => [g.id, g.name, g.members.map(memberKey)]))

export const groupsChanged = (next: LibraryGroup[], current: LibraryGroup[]) => shape(next) !== shape(current)
