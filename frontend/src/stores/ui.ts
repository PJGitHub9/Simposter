import { ref } from 'vue'

// Allow dynamic tab keys (per library)
export type TabKey = string
type SelectedMovie = { key: string; title: string; year?: number | string; poster?: string | null } | null

const selectedMovie = ref<SelectedMovie>(null)

export function useUiStore() {
  return {
    selectedMovie,
    setSelectedMovie: (movie: SelectedMovie) => (selectedMovie.value = movie)
  }
}
