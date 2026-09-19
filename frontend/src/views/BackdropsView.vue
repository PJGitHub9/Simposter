<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import BackdropEditorModal from '@/components/BackdropEditorModal.vue'
import { useArtLibraryCache } from '@/composables/useArtLibraryCache'
import { usePagedItems } from '@/composables/usePagedItems'

type BackdropItem = {
  key: string
  title: string
  year?: number | string
  art_url?: string | null
  tmdb_id?: number | null
  is_tv?: boolean
}

const route = useRoute()
const { items, loading, fetchItems } = useArtLibraryCache<BackdropItem>('backdrops')
const filter = ref<'all' | 'has_backdrop' | 'missing'>('all')
const sortBy = ref<'title_asc' | 'title_desc' | 'year_desc' | 'year_asc'>('title_asc')
const search = ref('')
const failedImages = ref<Set<string>>(new Set())
const selectedItem = ref<BackdropItem | null>(null)

const isTV = computed(() => route.name === 'tv-backdrops')
const libraryId = computed(() => (route.query.library as string) || '')

const withBackdrop = computed(() => items.value.filter(m => m.art_url))
const withoutBackdrop = computed(() => items.value.filter(m => !m.art_url))

const displayItems = computed(() => {
  let list = items.value

  // Filter
  if (filter.value === 'has_backdrop') list = list.filter(m => m.art_url && !failedImages.value.has(m.key))
  else if (filter.value === 'missing') list = list.filter(m => !m.art_url || failedImages.value.has(m.key))

  // Search
  const q = search.value.trim().toLowerCase()
  if (q) list = list.filter(m => m.title.toLowerCase().includes(q))

  // Sort
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

const { page, totalPages, pagedItems, nextPage, prevPage, resetPage } = usePagedItems(displayItems)
watch([filter, search, sortBy], resetPage)

function refresh() {
  failedImages.value = new Set()
  fetchItems(isTV.value, libraryId.value)
}

function openEditor(item: BackdropItem) {
  selectedItem.value = { ...item, is_tv: isTV.value }
}

function onImgError(key: string) {
  failedImages.value = new Set([...failedImages.value, key])
}

function onBackdropUpdated(newArtUrl: string | null) {
  if (selectedItem.value && newArtUrl) {
    const target = items.value.find(i => i.key === selectedItem.value!.key)
    if (target) {
      target.art_url = newArtUrl
      failedImages.value = new Set([...failedImages.value].filter(k => k !== target.key))
    }
  }
}

watch(libraryId, refresh)
onMounted(refresh)
</script>

<template>
  <div class="backdrops-view">
    <div class="page-header">
      <h2>🎞️ Backdrops</h2>
      <div class="header-actions">
        <div class="stats">
          <span class="stat-cached">{{ withBackdrop.length }} cached</span>
          <span class="stat-sep">/</span>
          <span class="stat-total">{{ items.length }} total</span>
          <span v-if="withoutBackdrop.length > 0" class="stat-missing">
            ({{ withoutBackdrop.length }} missing)
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
          <option value="has_backdrop">Has backdrop</option>
          <option value="missing">Missing backdrop</option>
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

    <div v-if="loading" class="state-msg">Loading backdrops...</div>

    <div v-else-if="displayItems.length === 0" class="state-msg">
      <template v-if="search">No results for "{{ search }}".</template>
      <template v-else-if="filter === 'missing'">No items are missing a backdrop.</template>
      <template v-else-if="filter === 'has_backdrop'">No backdrops cached yet. Run a library scan.</template>
      <template v-else-if="withBackdrop.length === 0">
        No backdrops found in Plex for this library. Run a library scan to check for backdrops.
      </template>
    </div>

    <div v-else class="backdrop-grid">
      <div
        v-for="item in pagedItems"
        :key="item.key"
        class="backdrop-card"
        :class="{
          'has-backdrop': !!item.art_url && !failedImages.has(item.key),
          'no-backdrop': !item.art_url || failedImages.has(item.key),
        }"
        title="Click to edit backdrop"
        @click="openEditor(item)"
      >
        <div class="backdrop-area">
          <img
            v-if="item.art_url && !failedImages.has(item.key)"
            :src="item.art_url"
            :alt="item.title"
            class="backdrop-img"
            @error="onImgError(item.key)"
          />
          <div v-else class="no-backdrop-placeholder">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.35"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9l4-4 4 4 4-4 4 4"/><circle cx="8.5" cy="14.5" r="1.5"/></svg>
            <span>No backdrop cached</span>
          </div>
        </div>
        <div class="backdrop-meta">
          <span class="backdrop-title">{{ item.title }}</span>
          <span v-if="item.year" class="backdrop-year">{{ item.year }}</span>
        </div>
      </div>
    </div>

    <div v-if="!loading && displayItems.length > 0" class="pagination-bar">
      <button class="page-btn" @click="prevPage" :disabled="page === 1">Prev</button>
      <span class="page-indicator">{{ page }} / {{ totalPages }}</span>
      <button class="page-btn" @click="nextPage" :disabled="page === totalPages">Next</button>
    </div>
  </div>

  <BackdropEditorModal
    v-if="selectedItem"
    :item="selectedItem"
    @close="selectedItem = null"
    @updated="onBackdropUpdated"
  />
</template>

<style scoped>
.backdrops-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
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

.state-msg {
  padding: 40px 20px;
  text-align: center;
  color: #a8b3cf;
  font-size: 14px;
}

.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 10px 12px;
}

.page-btn {
  padding: 5px 14px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  cursor: pointer;
  transition: all 0.15s;
}

.page-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.09);
  border-color: rgba(61, 214, 183, 0.35);
  color: #eef2ff;
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.page-indicator {
  font-size: 13px;
  color: #a8b3cf;
  min-width: 60px;
  text-align: center;
}

/* Grid — wide cards for backdrop (16:9) thumbnails */
.backdrop-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}

.backdrop-card {
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(14, 16, 24, 0.6);
  transition: border-color 0.15s, transform 0.15s;
  cursor: pointer;
}

.backdrop-card:hover {
  border-color: rgba(61, 214, 183, 0.4);
  transform: translateY(-2px);
}

.backdrop-card.no-backdrop {
  opacity: 0.7;
}

/* Backdrop display area — 16:9 aspect, dark background */
.backdrop-area {
  aspect-ratio: 16 / 9;
  background: #0a0b12;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.backdrop-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.no-backdrop-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: rgba(255, 255, 255, 0.3);
  font-size: 11px;
  text-align: center;
}

/* Title/year row below the backdrop */
.backdrop-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.backdrop-title {
  font-size: 12px;
  font-weight: 500;
  color: #c9d1e0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.backdrop-year {
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

  .backdrop-grid {
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 10px;
  }
}
</style>
