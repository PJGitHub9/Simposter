import { ref } from 'vue'

type Movie = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
}

const moviesCache = ref<Movie[]>([])
const moviesLoaded = ref(false)
const POSTER_CACHE_KEY = 'simposter-poster-cache'

export function useMovies() {
  const setMoviePoster = (key: string, url: string | null) => {
    const idx = moviesCache.value.findIndex((m) => m.key === key)
    if (idx !== -1) {
      moviesCache.value[idx] = { ...moviesCache.value[idx], poster: url }
    }
  }

  const hydratePostersFromSession = () => {
    if (typeof sessionStorage === 'undefined') return
    try {
      const raw = sessionStorage.getItem(POSTER_CACHE_KEY)
      if (!raw) return
      const cache = JSON.parse(raw)
      Object.entries(cache).forEach(([key, url]) => {
        setMoviePoster(key, url as string | null)
      })
    } catch {
      /* ignore */
    }
  }

  return {
    movies: moviesCache,
    moviesLoaded,
    setMoviePoster,
    hydratePostersFromSession
  }
}
