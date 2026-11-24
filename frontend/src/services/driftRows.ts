// History -> Changed Outside Simposter, list view: one row per title (all its
// server copies), plus a small concurrency-limited runner for bulk actions.

export interface DriftCopy {
  server_id: string
  rating_key: string
  asset_type?: string
  title: string
  drift_detected_at: string
}

export interface DriftRow<T extends DriftCopy> {
  key: string
  title: string
  asset: string
  copies: T[]
  latest: string
}

const SERVER_ORDER = ['plex', 'jellyfin', 'emby', 'silo']
const serverRank = (id: string) => {
  if (id === 'plex-1') return -1
  const i = SERVER_ORDER.indexOf(id.split('-')[0] || '')
  return i < 0 ? SERVER_ORDER.length : i
}

/** Rows for one library group: copies with the same title and asset type share a row. */
export function buildDriftRows<T extends DriftCopy>(items: T[], groupKey: string): DriftRow<T>[] {
  const rows = new Map<string, DriftRow<T>>()
  for (const item of items) {
    const asset = item.asset_type || 'poster'
    const title = item.title || item.rating_key
    const key = `${groupKey}|${asset}|${title}`
    let row = rows.get(key)
    if (!row) {
      row = { key, title, asset, copies: [], latest: '' }
      rows.set(key, row)
    }
    row.copies.push(item)
    if ((item.drift_detected_at || '') > row.latest) row.latest = item.drift_detected_at || ''
  }
  for (const row of rows.values()) {
    row.copies.sort((a, b) => serverRank(a.server_id) - serverRank(b.server_id))
  }
  return [...rows.values()].sort((a, b) => (a.latest < b.latest ? 1 : a.latest > b.latest ? -1 : a.title.localeCompare(b.title)))
}

/** Run fn over items, at most `limit` at a time. One failure never stops the rest. */
export async function runLimited<T>(
  items: T[],
  limit: number,
  fn: (item: T) => Promise<void>,
  onProgress?: (done: number) => void,
): Promise<Array<{ item: T; error: string | null }>> {
  const results: Array<{ item: T; error: string | null }> = items.map(item => ({ item, error: null }))
  let next = 0
  let done = 0
  const worker = async () => {
    while (next < items.length) {
      const i = next++
      try {
        await fn(items[i] as T)
      } catch (e: any) {
        results[i]!.error = e?.message || String(e)
      }
      done += 1
      onProgress?.(done)
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker))
  return results
}
