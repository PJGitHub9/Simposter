<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MovieGrid from '../components/movies/MovieGrid.vue'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore } from '@/stores/settings'

type Collection = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
  library_id?: string
}

const emit = defineEmits<{
  (e: 'select', collection: Collection & { mediaType?: 'movie' | 'tv-show' }): void
}>()

const apiBase = getApiBase()
const route = useRoute()
const router = useRouter()
const settings = useSettingsStore()

const collections = ref<Collection[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const movieLibraries = computed(() => {
  const libs = settings.plex.value.libraryMappings
  return libs && libs.length
    ? libs
    : [{ id: settings.plex.value.movieLibraryName || 'default', displayName: 'Movies', title: 'Movies' }]
})

const defaultLibraryId = computed(() => movieLibraries.value[0]?.id || 'default')
const currentLibrary = computed(() => (route.query.library as string) || defaultLibraryId.value)

const libraryLabel = computed(() => {
  const lib = movieLibraries.value.find((l) => (l.id || '').toString() === currentLibrary.value)
  return lib?.displayName || lib?.title || 'Collections'
})

const normalizePoster = (url: string | null | undefined) => {
  if (!url) return null
  if (/^https?:\/\//i.test(url)) return url
  return `${apiBase}${url}`
}

const fetchCollections = async () => {
  loading.value = true
  error.value = null
  try {
    const lib = currentLibrary.value
    const url = new URL(`${apiBase}/api/collections`)
    if (lib) url.searchParams.set('library_id', lib)
    const res = await fetch(url.toString())
    if (!res.ok) throw new Error(`Failed to load collections (${res.status})`)
    const data = (await res.json()) as Collection[]
    collections.value = data.map((c) => ({ ...c, poster: normalizePoster(c.poster) }))
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'Failed to load collections'
    error.value = message
  } finally {
    loading.value = false
  }
}

const handleSelect = (collection: Collection) => {
  emit('select', { ...collection, mediaType: 'movie' })
}

onMounted(() => {
  if (!route.query.library && route.name === 'collections' && defaultLibraryId.value) {
    router.replace({ name: 'collections', query: { library: defaultLibraryId.value } })
  }
  fetchCollections()
})

watch(
  () => route.query.library,
  () => {
    fetchCollections()
  }
)

watch(defaultLibraryId, (val, oldVal) => {
  if (!route.query.library && val && val !== oldVal && route.name === 'collections') {
    router.replace({ name: 'collections', query: { library: val } })
  }
})
</script>

<template>
  <div class="view glass">
    <div class="header">
      <div>
        <p class="label">&#x1F4DA; Collections</p>
        <h2>{{ libraryLabel }}</h2>
      </div>
    </div>

    <div v-if="loading" class="state muted">Loading collections...</div>
    <div v-else-if="error" class="state error">{{ error }}</div>
    <div v-else-if="collections.length === 0" class="state muted">No collections found in this library.</div>
    <MovieGrid
      v-else
      heading="Collections"
      :items="collections"
      @select="handleSelect"
    />
  </div>
</template>

<style scoped>
.view {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.label {
  text-transform: uppercase;
  font-size: 12px;
  color: var(--muted);
  letter-spacing: 1px;
}

.state {
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
}

.muted {
  color: var(--muted);
}

.error {
  color: #f05d7b;
}
</style>
