// Poster modes (backend/poster_mode.py): per library group and title, who makes
// the poster. full = Simposter; overlay_only = overlays on a clean copy;
// leave_alone = Simposter doesn't touch it.
import { ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

export type PosterMode = 'full' | 'overlay_only' | 'leave_alone'

export const MODE_LABELS: Record<PosterMode, string> = {
  full: 'Full',
  overlay_only: 'Overlay only',
  leave_alone: 'Leave alone',
}

export function modeLabel(mode?: string | null): string {
  return MODE_LABELS[(mode || 'full') as PosterMode] || 'Full'
}

/** Which small icon a card shows: none for Full. */
export function modeIcon(mode?: string | null): 'overlay' | 'lock' | null {
  if (mode === 'overlay_only') return 'overlay'
  if (mode === 'leave_alone') return 'lock'
  return null
}

export function modeReasonText(reason?: string | null): string {
  if (!reason) return ''
  return reason === 'manual' ? 'set by hand' : reason
}

export function modeTooltip(mode?: string | null, reason?: string | null): string {
  const r = modeReasonText(reason)
  return r ? `${modeLabel(mode)}: ${r}` : modeLabel(mode)
}

/** Same id the backend's group_id_for() builds: the group's own id, else a pseudo id. */
export function groupIdFor(
  group: { id?: string } | null | undefined,
  serverId: string,
  libraryId: string,
  mediaType: 'movie' | 'tv',
): string {
  if (group?.id) return String(group.id)
  const server = serverId || 'plex-1'
  if (server === 'plex-1') return `group-${mediaType}-${libraryId}`
  return `lib:${server}:${libraryId}`
}

export type ModeItem = { tmdb_id?: number | string | null; tvdb_id?: number | string | null }

/** mode null = clear the manual setting (follow the rules). Returns titles updated. */
export async function setPosterModes(
  groupId: string,
  mediaType: 'movie' | 'tv',
  items: ModeItem[],
  mode: PosterMode | null,
): Promise<number> {
  const res = await fetch(`${getApiBase()}/api/poster-modes/set`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      group_id: groupId,
      media_type: mediaType,
      items: items.map(i => ({ tmdb_id: i.tmdb_id ?? undefined, tvdb_id: i.tvdb_id ?? undefined })),
      mode,
    }),
  })
  if (!res.ok) throw new Error(await res.text())
  const data = await res.json()
  return Number(data.updated || 0)
}

export async function reevaluatePosterModes(
  groupId: string,
): Promise<{ matched: number; changed: number; per_rule: number[] } | null> {
  try {
    const res = await fetch(`${getApiBase()}/api/poster-modes/reevaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_id: groupId }),
    })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

// Match counts from the last re-evaluation, per group id (shown next to each
// rule in Settings after Save).
export const ruleMatchCounts = ref<Record<string, number[]>>({})

export const MODE_FILTER_OPTIONS: { value: '' | PosterMode; label: string }[] = [
  { value: '', label: 'All modes' },
  { value: 'full', label: 'Full' },
  { value: 'overlay_only', label: 'Overlay only' },
  { value: 'leave_alone', label: 'Leave alone' },
]
