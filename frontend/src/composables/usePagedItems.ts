import { computed, ref, watch, type Ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'

// Client-side pagination matching Movies/TV Shows: page size tracks the
// user's "Poster Density" setting rather than a hardcoded number, so Logos/
// Backdrops/Square Art behave the same way instead of rendering (and
// fetching art for) every item in the library at once.
export function usePagedItems<T>(sourceItems: Ref<T[]>, fixedPageSize?: number) {
  const settings = useSettingsStore()
  // `fixedPageSize` is for non-library grids (Poster API) that shouldn't follow Poster Density.
  const pageSize = computed(() => fixedPageSize ?? (settings.posterDensity.value || 20))
  const page = ref(1)

  const totalPages = computed(() => Math.max(1, Math.ceil(sourceItems.value.length / pageSize.value)))

  const pagedItems = computed(() => {
    const start = (page.value - 1) * pageSize.value
    return sourceItems.value.slice(start, start + pageSize.value)
  })

  watch(pageSize, () => {
    page.value = 1
  })

  watch(sourceItems, () => {
    if (page.value > totalPages.value) page.value = totalPages.value
  })

  function nextPage() {
    if (page.value < totalPages.value) page.value += 1
  }

  function prevPage() {
    if (page.value > 1) page.value -= 1
  }

  function resetPage() {
    page.value = 1
  }

  return { page, pageSize, totalPages, pagedItems, nextPage, prevPage, resetPage }
}
