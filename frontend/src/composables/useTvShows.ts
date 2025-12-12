import { ref } from 'vue'

type TvShow = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
}

const tvShowsCache = ref<TvShow[]>([])
const tvShowsLoaded = ref(false)
const POSTER_CACHE_KEY = 'simposter-tv-poster-cache'

export function useTvShows() {
  const setTvShowPoster = (key: string, url: string | null) => {
    if (!key) return
    const idx = tvShowsCache.value.findIndex((s) => s.key === key)
    if (idx === -1) return
    const current = tvShowsCache.value[idx]
    if (!current) return
    // Preserve required fields; fallback to empty title if missing to satisfy type
    tvShowsCache.value[idx] = {
      key: current.key || key,
      title: current.title || '',
      year: current.year,
      addedAt: current.addedAt,
      poster: url
    }
  }

  const hydratePostersFromSession = () => {
    if (typeof sessionStorage === 'undefined') return
    try {
      const raw = sessionStorage.getItem(POSTER_CACHE_KEY)
      if (!raw) return
      const cache = JSON.parse(raw)
      Object.entries(cache).forEach(([key, url]) => {
        setTvShowPoster(key, url as string | null)
      })
    } catch {
      /* ignore */
    }
  }

  return {
    tvShows: tvShowsCache,
    tvShowsLoaded,
    setTvShowPoster,
    hydratePostersFromSession
  }
}
