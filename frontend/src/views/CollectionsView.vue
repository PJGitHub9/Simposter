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

type CreatorMode = 'simposter' | 'kometa'

const emit = defineEmits<{
  (e: 'select', collection: Collection & { mediaType?: 'movie' | 'tv-show' | 'collection'; creatorMode?: CreatorMode }): void
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

const fetchCollections = async (forceRefresh = false) => {
  loading.value = true
  error.value = null
  try {
    const lib = currentLibrary.value
    const url = new URL(`${apiBase}/api/collections`)
    if (lib) url.searchParams.set('library_id', lib)
    if (forceRefresh) url.searchParams.set('force_refresh', 'true')
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

const refreshCollections = () => fetchCollections(true)

// Per-card refresh button (MovieCard.vue's small refresh icon) — MovieGrid
// already emits this for every item, but CollectionsView never wired up a
// listener for it at all, so clicking it silently did nothing. Reuses the
// same /api/movie/{key}/poster?force_refresh=1 proxy the collection poster
// itself is already served through (collections have no dedicated poster
// endpoint of their own).
const handleRefreshPoster = async (ratingKey: string) => {
  try {
    const res = await fetch(`${apiBase}/api/movie/${ratingKey}/poster?meta=1&force_refresh=1`)
    if (!res.ok) return
    const data = await res.json()
    const url = normalizePoster(data.url)
    const idx = collections.value.findIndex((c) => c.key === ratingKey)
    if (idx === -1) return
    collections.value[idx] = { ...collections.value[idx]!, poster: url }
  } catch {
    /* ignore */
  }
}

const pendingCollection = ref<Collection | null>(null)

const handleSelect = (collection: Collection) => {
  pendingCollection.value = collection
}

const chooseCreator = (mode: CreatorMode) => {
  if (!pendingCollection.value) return
  emit('select', { ...pendingCollection.value, mediaType: 'collection', creatorMode: mode })
  pendingCollection.value = null
}

const cancelCreatorChoice = () => {
  pendingCollection.value = null
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
      <button @click="refreshCollections" class="refresh-btn" :disabled="loading">
        {{ loading ? 'Refreshing...' : 'Refresh Cache' }}
      </button>
    </div>

    <div v-if="loading" class="state muted">Loading collections...</div>
    <div v-else-if="error" class="state error">{{ error }}</div>
    <div v-else-if="collections.length === 0" class="state muted">No collections found in this library.</div>
    <MovieGrid
      v-else
      heading="Collections"
      :items="collections"
      @select="handleSelect"
      @refresh="handleRefreshPoster"
      @resend-done="handleRefreshPoster"
    />

    <div v-if="pendingCollection" class="modal-backdrop" @click.self="cancelCreatorChoice">
      <div class="modal glass">
        <p class="label">Choose your creator</p>
        <h3>{{ pendingCollection.title }}</h3>
        <div class="creator-list">
          <button class="creator-item" @click="chooseCreator('simposter')">
            <div>
              <p class="name">Simposter Creator</p>
              <p class="desc">The standard manual editor — upload your own poster and logo art.</p>
            </div>
            <span class="pill">Use</span>
          </button>
          <button class="creator-item" @click="chooseCreator('kometa')">
            <div>
              <p class="name">Kometa Creator</p>
              <p class="desc">Flat-color background, gradient fade, and a centered logo — Kometa-style collection posters.</p>
            </div>
            <span class="pill">Use</span>
          </button>
        </div>
        <button class="cancel" @click="cancelCreatorChoice">Cancel</button>
      </div>
    </div>
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

.refresh-btn {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 14px;
  background: rgba(61, 214, 183, 0.15);
  color: #3dd6b7;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  margin: 0;
}

.refresh-btn:hover:not(:disabled) {
  background: rgba(61, 214, 183, 0.25);
  border-color: rgba(61, 214, 183, 0.5);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  width: min(480px, 90vw);
  padding: 20px;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.creator-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.creator-item {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  cursor: pointer;
  color: inherit;
}

.creator-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.creator-item .name {
  font-weight: 600;
}

.creator-item .desc {
  color: var(--muted);
  font-size: 12px;
  margin-top: 2px;
}

.creator-item .pill {
  flex-shrink: 0;
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(61, 214, 183, 0.18);
  color: #d8fff4;
}

.cancel {
  align-self: flex-end;
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  font-size: 13px;
  padding: 4px 8px;
}

.cancel:hover {
  color: var(--fg, #fff);
}
</style>
