import { ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

// Logos/Backdrops/Square Art all call the identical /api/movies /api/tv-shows
// endpoints MoviesView/TvShowsView already cache -- this gives them the same
// sessionStorage cache-first instant paint (fetch fresh in the background,
// only blank the grid on a genuine first-ever visit with nothing cached yet).
const CACHE_VERSION = '1'

export function useArtLibraryCache<T extends { key: string }>(namespace: string) {
  const items = ref<T[]>([])
  const loading = ref(false)

  const cacheKey = (isTV: boolean, libraryId: string) =>
    `simposter-${namespace}-cache-${isTV ? 'tv' : 'movie'}-${libraryId || 'all'}-v${CACHE_VERSION}`

  function loadFromCache(isTV: boolean, libraryId: string): boolean {
    if (typeof sessionStorage === 'undefined') return false
    try {
      const raw = sessionStorage.getItem(cacheKey(isTV, libraryId))
      if (!raw) return false
      const cached = JSON.parse(raw)
      if (!Array.isArray(cached) || cached.length === 0) return false
      items.value = cached
      return true
    } catch {
      return false
    }
  }

  function saveToCache(isTV: boolean, libraryId: string) {
    if (typeof sessionStorage === 'undefined') return
    try {
      sessionStorage.setItem(cacheKey(isTV, libraryId), JSON.stringify(items.value))
    } catch {
      /* quota exceeded -- fine to skip, next visit just misses the cache */
    }
  }

  async function fetchItems(isTV: boolean, libraryId: string, mapFn?: (raw: any) => T) {
    const hadCache = loadFromCache(isTV, libraryId)
    if (!hadCache) {
      loading.value = true
      items.value = []
    }
    const apiBase = getApiBase()
    try {
      const endpoint = isTV ? 'tv-shows' : 'movies'
      const params = libraryId ? `?library_id=${libraryId}` : ''
      const res = await fetch(`${apiBase}/api/${endpoint}${params}`)
      if (res.ok) {
        const data = await res.json()
        items.value = mapFn ? (data as any[]).map(mapFn) : (data as T[])
        saveToCache(isTV, libraryId)
      }
    } catch {
      /* keep whatever we had (cache or empty) on a failed revalidation */
    } finally {
      loading.value = false
    }
  }

  return { items, loading, fetchItems }
}
