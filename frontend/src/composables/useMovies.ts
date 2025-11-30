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

export function useMovies() {
  return {
    movies: moviesCache,
    moviesLoaded
  }
}
