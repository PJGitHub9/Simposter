import { ref } from 'vue'

type Movie = {
  key: string
  title: string
  year?: number
  poster?: string | null
}

const moviesCache = ref<Movie[]>([])

export function useMovies() {
  return {
    movies: moviesCache
  }
}
