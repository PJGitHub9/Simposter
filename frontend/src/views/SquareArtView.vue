<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import SquareArtModal from '@/components/SquareArtModal.vue'
import { useArtLibraryCache } from '@/composables/useArtLibraryCache'

type SquareArtItem = {
  key: string
  title: string
  year?: number | string
  poster?: string | null
  logo_url?: string | null
  square_art_url?: string | null
  tmdb_id?: number | null
  library_id?: string | number | null
}

const route = useRoute()
const { items, loading, fetchItems } = useArtLibraryCache<SquareArtItem>('square-art')
const filter = ref<'all' | 'has_square_art' | 'missing'>('all')
const search = ref('')
const sortBy = ref<'title_asc' | 'title_desc' | 'year_desc' | 'year_asc'>('title_asc')
const failedImages = ref<Set<string>>(new Set())
const selectedItem = ref<SquareArtItem | null>(null)

const isTV = computed(() => route.name === 'tv-square-art')
const libraryId = computed(() => (route.query.library as string) || '')

const withSquareArt = computed(() => items.value.filter((m) => m.square_art_url))
const withoutSquareArt = computed(() => items.value.filter((m) => !m.square_art_url))

const displayItems = computed(() => {
  let list = items.value

  if (filter.value === 'has_square_art') list = list.filter((m) => m.square_art_url && !failedImages.value.has(m.key))
  else if (filter.value === 'missing') list = list.filter((m) => !m.square_art_url || failedImages.value.has(m.key))

  const q = search.value.trim().toLowerCase()
  if (q) list = list.filter((m) => m.title.toLowerCase().includes(q))
  list = [...list].sort((a, b) => {
    if (sortBy.value === 'title_asc') return a.title.localeCompare(b.title)
    if (sortBy.value === 'title_desc') return b.title.localeCompare(a.title)
    const ay = Number(a.year) || 0
    const by_ = Number(b.year) || 0
    if (sortBy.value === 'year_desc') return by_ - ay
    return ay - by_
  })
  return list
})

function refresh() {
  failedImages.value = new Set()
  fetchItems(isTV.value, libraryId.value, (m: any) => ({
    key: m.key,
    title: m.title,
    year: m.year,
    poster: m.poster,
    logo_url: m.logo_url,
    square_art_url: m.square_art_url,
    tmdb_id: m.tmdb_id,
    library_id: m.library_id,
  }))
}

function openModal(item: SquareArtItem) {
  selectedItem.value = { ...item, ...(isTV.value ? { mediaType: 'tv-show' } : { mediaType: 'movie' }) } as any
}

function onImgError(key: string) {
  failedImages.value = new Set([...failedImages.value, key])
}

watch(libraryId, refresh)
onMounted(refresh)
</script>

<template>
  <div class="square-art-view">
    <div class="page-header">
      <h2>🔳 Square Art</h2>
      <div class="header-actions">
        <div class="stats">
          <span class="stat-cached">{{ withSquareArt.length }} in Plex</span>
          <span class="stat-sep">/</span>
          <span class="stat-total">{{ items.length }} total</span>
          <span v-if="withoutSquareArt.length > 0" class="stat-missing">
            ({{ withoutSquareArt.length }} missing)
          </span>
        </div>
        <input
          v-model="search"
          class="search-input"
          type="text"
          placeholder="Search..."
        />
        <select v-model="filter" class="toolbar-select">
          <option value="all">All</option>
          <option value="has_square_art">In Plex</option>
          <option value="missing">Missing</option>
        </select>
        <select v-model="sortBy" class="toolbar-select">
          <option value="title_asc">Title (A–Z)</option>
          <option value="title_desc">Title (Z–A)</option>
          <option value="year_desc">Year (Newest)</option>
          <option value="year_asc">Year (Oldest)</option>
        </select>
        <button class="btn-refresh" @click="refresh" :disabled="loading">
          <svg v-if="loading" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <div class="section-note">
      Titles with square art already in Plex show it below (populated by library scans, same as
      Logos/Backdrops). Click a title to generate/replace it from your existing template/preset —
      send to Plex's dedicated square art slot, or save a copy to disk.
    </div>

    <div v-if="loading" class="state-msg">Loading...</div>

    <div v-else-if="displayItems.length === 0" class="state-msg">
      <template v-if="search">No results for "{{ search }}".</template>
      <template v-else-if="filter === 'missing'">Every item already has square art in Plex.</template>
      <template v-else-if="filter === 'has_square_art'">No square art found yet. Run a library scan, or generate one below.</template>
      <template v-else>No items found. Run a library scan.</template>
    </div>

    <div v-else class="art-grid">
      <div
        v-for="item in displayItems"
        :key="item.key"
        class="art-card"
        :class="{ 'has-art': !!item.square_art_url && !failedImages.has(item.key) }"
        title="Click to create/replace square art"
        @click="openModal(item)"
      >
        <div class="art-area">
          <img
            v-if="item.square_art_url && !failedImages.has(item.key)"
            :src="item.square_art_url"
            :alt="item.title"
            class="art-img"
            @error="onImgError(item.key)"
          />
          <div v-else class="no-art-placeholder">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.35"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
            <span>No square art in Plex</span>
          </div>
        </div>
        <div class="art-meta">
          <span class="art-title">{{ item.title }}</span>
          <span v-if="item.year" class="art-year">{{ item.year }}</span>
        </div>
      </div>
    </div>
  </div>

  <SquareArtModal
    v-if="selectedItem"
    :item="selectedItem"
    @close="selectedItem = null"
  />
</template>

<style scoped>
.square-art-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #eef2ff;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.stats {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
}

.stat-cached {
  color: var(--accent, #3dd6b7);
  font-weight: 600;
}

.stat-sep {
  color: rgba(255, 255, 255, 0.25);
}

.stat-total {
  color: #a8b3cf;
}

.stat-missing {
  color: rgba(255, 180, 100, 0.7);
  font-size: 12px;
}

.search-input {
  padding: 5px 10px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  outline: none;
  width: 160px;
  transition: border-color 0.15s;
}

.search-input::placeholder {
  color: rgba(255, 255, 255, 0.3);
}

.search-input:focus {
  border-color: rgba(61, 214, 183, 0.4);
}

.toolbar-select {
  padding: 5px 10px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}

.toolbar-select:hover {
  border-color: rgba(61, 214, 183, 0.35);
}

.toolbar-select option {
  background: #1a1d2e;
  color: #c9d1e0;
}

.btn-refresh {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-refresh:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.09);
  border-color: rgba(61, 214, 183, 0.35);
  color: #eef2ff;
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: default;
}

.spin {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.section-note {
  font-size: 12px;
  color: #6b7a99;
  line-height: 1.5;
}

.state-msg {
  padding: 40px 20px;
  text-align: center;
  color: #a8b3cf;
  font-size: 14px;
}

/* Grid — square (1:1) thumbnails, mirroring what square art itself will look like */
.art-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 14px;
}

.art-card {
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(14, 16, 24, 0.6);
  transition: border-color 0.15s, transform 0.15s;
  cursor: pointer;
}

.art-card:hover {
  border-color: rgba(61, 214, 183, 0.4);
  transform: translateY(-2px);
}

.art-card:not(.has-art) {
  opacity: 0.7;
}

.art-area {
  aspect-ratio: 1 / 1;
  background: #0a0b12;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.art-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.no-art-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: rgba(255, 255, 255, 0.3);
  font-size: 11px;
  text-align: center;
}

.art-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.art-title {
  font-size: 12px;
  font-weight: 500;
  color: #c9d1e0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.art-year {
  font-size: 11px;
  color: #6b7a99;
  flex-shrink: 0;
}

@media (max-width: 700px) {
  .header-actions {
    gap: 8px;
  }

  .search-input {
    width: 120px;
  }

  .art-grid {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 10px;
  }
}
</style>
