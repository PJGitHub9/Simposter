import { ref } from 'vue'

// Cross-component trigger so the Poster API page (a routed view) can ask App.vue -- which owns
// the poster editors, mounted outside <router-view> -- to open one for a TMDb-identified item
// that has no media-server rating key. Same idea as useOnboardingLauncher.ts.
export type ApiEditorItem = {
  apiMode: true
  tmdb_id: number
  mediaType: 'movie' | 'tv'
  title: string
  year?: string | number
}

export const apiEditorRequest = ref<ApiEditorItem | null>(null)

export function openApiEditor(item: Omit<ApiEditorItem, 'apiMode'> & { apiMode?: true }) {
  apiEditorRequest.value = { ...item, apiMode: true }
}
