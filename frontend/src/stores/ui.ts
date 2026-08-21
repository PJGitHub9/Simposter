import { ref } from 'vue'

// Allow dynamic tab keys (per library)
export type TabKey = string
export type MediaType = 'movie' | 'tv-show' | 'collection'
export type CreatorMode = 'simposter' | 'kometa'
type SelectedMovie = { key: string; title: string; year?: number | string; poster?: string | null; mediaType?: MediaType; creatorMode?: CreatorMode } | null

const selectedMovie = ref<SelectedMovie>(null)

export function useUiStore() {
  return {
    selectedMovie,
    setSelectedMovie: (movie: SelectedMovie) => (selectedMovie.value = movie)
  }
}
