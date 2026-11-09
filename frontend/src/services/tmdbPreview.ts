import { getApiBase } from '@/services/apiBase'

// Library-less preview source: TMDb trending/search, used by the Template Manager and
// Overlay Manager pickers when there is nothing in the library to preview with.

export type TmdbPreviewItem = {
  key: string // synthetic `tmdb-<type>-<id>` -- never a rating key, never sent to the backend
  title: string
  year?: string
  tmdbId: number
  tmdbType: 'movie' | 'tv'
  posterUrl?: string
}

const apiBase = getApiBase()

const toItem = (h: any, type: 'movie' | 'tv'): TmdbPreviewItem => ({
  key: `tmdb-${type}-${h.tmdb_id}`,
  title: h.title || '',
  year: h.year ? String(h.year) : undefined,
  tmdbId: Number(h.tmdb_id),
  tmdbType: type,
  posterUrl: h.poster_path ? `https://image.tmdb.org/t/p/w780${h.poster_path}` : undefined,
})

export const isTmdbKey = (key: string | undefined | null) => !!key && key.startsWith('tmdb-')

export async function fetchTmdbTrending(type: 'movie' | 'tv' = 'movie'): Promise<TmdbPreviewItem[]> {
  try {
    const res = await fetch(`${apiBase}/api/tmdb/trending?type=${type}`)
    if (!res.ok) return []
    const data = await res.json()
    return Array.isArray(data) ? data.map((h) => toItem(h, type)) : []
  } catch {
    return []
  }
}

export async function searchTmdb(q: string, type: 'movie' | 'tv' = 'movie'): Promise<TmdbPreviewItem[]> {
  if (!q.trim()) return []
  try {
    const res = await fetch(`${apiBase}/api/tmdb/search?type=${type}&q=${encodeURIComponent(q.trim())}`)
    if (!res.ok) return []
    const data = await res.json()
    return Array.isArray(data) ? data.map((h) => toItem(h, type)) : []
  } catch {
    return []
  }
}

/** Poster + logo for a preview render, picked like SquareArtModal does (textless poster first, first non-SVG logo). */
export async function fetchTmdbPreviewImages(item: TmdbPreviewItem): Promise<{ background: string; logo: string | null }> {
  const endpoint = item.tmdbType === 'tv'
    ? `${apiBase}/api/tmdb/tv/${item.tmdbId}/images`
    : `${apiBase}/api/tmdb/${item.tmdbId}/images`
  const res = await fetch(endpoint)
  if (!res.ok) throw new Error(`Failed to fetch TMDb images (HTTP ${res.status})`)
  const data = await res.json()
  const posters: Array<{ url: string; has_text?: boolean }> = data.posters || []
  const logos: Array<{ url: string }> = (data.logos || []).filter((l: { url?: string }) => {
    const u = (l.url || '').toLowerCase()
    return !u.endsWith('.svg') && !u.includes('.svg?')
  })
  const poster = posters.find((p) => p.has_text === false) || posters[0]
  const background = poster?.url || item.posterUrl || ''
  if (!background) throw new Error('No poster found on TMDb for this title')
  return { background, logo: logos[0]?.url || null }
}
