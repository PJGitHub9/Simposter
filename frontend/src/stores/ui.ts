import { ref } from 'vue'

export type TabKey = 'movies' | 'settings' | 'logs'
type SelectedMovie = { key: string; title: string; year?: number | string; poster?: string | null } | null

const selectedMovie = ref<SelectedMovie>(null)

export function useUiStore() {
  return {
    selectedMovie,
    setSelectedMovie: (movie: SelectedMovie) => (selectedMovie.value = movie)
  }
}
