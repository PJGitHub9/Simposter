<script setup lang="ts">
// Thumb Art: Jellyfin/Emby's 16:9 "Thumb" image (usually a backdrop with the
// title/logo on it). Plex has no such slot -- the mirror of Square Art being
// Plex-only -- so this page only lists items that have a Jellyfin or Emby copy,
// and each tile shows that copy's Thumb Art.
//
// Unlike Logos/Backdrops/Square Art, Thumb Art isn't stored in the library
// cache or fetched by scans: each tile loads /api/thumb-art/{id}, which fetches
// it from the server the first time and caches it on disk after that.
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import ThumbArtModal from '@/components/ThumbArtModal.vue'
import { useArtLibraryCache } from '@/composables/useArtLibraryCache'
import { usePagedItems } from '@/composables/usePagedItems'
import { getApiBase } from '@/services/apiBase'
import { mediaServerLabel } from '@/services/mediaServerLabel'
import { useSettingsStore } from '@/stores/settings'
import { compareTitles } from '@/services/sortTitle'

type LinkedServer = { server_id: string; rating_key: string }

type ThumbArtItem = {
  key: string
  title: string
  year?: number | string
  tmdb_id?: number | null
  library_id?: string | number | null
  addedAt?: number | null
  labels?: string[]
  server_id?: string | null
  other_servers?: LinkedServer[] | null
}

const apiBase = getApiBase()
const settings = useSettingsStore()
const route = useRoute()
const { items, loading, fetchItems } = useArtLibraryCache<ThumbArtItem>('thumb-art')
const search = ref('')
const sortBy = ref<'title_asc' | 'title_desc' | 'year_desc' | 'year_asc' | 'added_desc' | 'added_asc'>('title_asc')
const filterLabel = ref('')
const failedImages = ref<Set<string>>(new Set())
// Bumped after a send so the tile re-requests its image.
const tileVersion = ref<Record<string, number>>({})
const selectedItem = ref<(ThumbArtItem & { mediaType: 'movie' | 'tv-show' }) | null>(null)

const isTV = computed(() => route.name === 'tv-thumb-art')
const libraryId = computed(() => (route.query.library as string) || '')
const serverId = computed(() => (route.query.server as string) || '')

// Thumb Art is Jellyfin/Emby-only: show the icon of each of those server types in
// the group next to the header.
const headerServerTypes = computed(() => {
  const sid = serverId.value || 'plex-1'
  const group = (settings.libraryGroups.value || []).find(g =>
    (g.members || []).some(m => m.serverId === sid && m.libraryId === libraryId.value)
  )
  const types = new Set<string>()
  for (const m of group?.members || []) {
    if (m.serverId === 'plex-1') continue
    const t = settings.mediaServers.value.find(s => s.id === m.serverId)?.type || m.serverId.split('-')[0]
    if (t === 'jellyfin' || t === 'emby') types.add(t)
  }
  return Array.from(types)
})

// Every Jellyfin/Emby copy of an item: the item itself if it's a Jellyfin/Emby
// row, plus any linked copies (other_servers) of a merged card.
function nonPlexCopies(item: ThumbArtItem): LinkedServer[] {
  const list: LinkedServer[] = []
  const own = item.server_id || 'plex-1'
  if (own !== 'plex-1') list.push({ server_id: own, rating_key: item.key })
  for (const o of item.other_servers || []) {
    if (o?.server_id && o.server_id !== 'plex-1' && o.rating_key && !list.some(l => l.server_id === o.server_id)) {
      list.push({ server_id: o.server_id, rating_key: o.rating_key })
    }
  }
  return list
}

// Only items that exist on a Jellyfin/Emby server can have Thumb Art.
const eligibleItems = computed(() => items.value.filter((m) => nonPlexCopies(m).length > 0))

const allLabels = computed(() => {
  const labels = new Set<string>()
  eligibleItems.value.forEach(m => (m.labels || []).forEach(l => labels.add(l)))
  return Array.from(labels).sort()
})

const displayItems = computed(() => {
  let list = eligibleItems.value
  if (filterLabel.value) list = list.filter((m) => (m.labels || []).includes(filterLabel.value))
  const q = search.value.trim().toLowerCase()
  if (q) list = list.filter((m) => m.title.toLowerCase().includes(q))
  return [...list].sort((a, b) => {
    if (sortBy.value === 'title_asc') return compareTitles(a.title, b.title)
    if (sortBy.value === 'title_desc') return compareTitles(b.title, a.title)
    if (sortBy.value === 'added_desc') return (b.addedAt || 0) - (a.addedAt || 0)
    if (sortBy.value === 'added_asc') return (a.addedAt || 0) - (b.addedAt || 0)
    const ay = Number(a.year) || 0
    const by_ = Number(b.year) || 0
    return sortBy.value === 'year_desc' ? by_ - ay : ay - by_
  })
})

const { page, totalPages, pagedItems, nextPage, prevPage, resetPage } = usePagedItems(displayItems)
watch([search, sortBy, filterLabel], resetPage)

function tileSrc(item: ThumbArtItem): string | null {
  const copy = nonPlexCopies(item)[0]
  if (!copy) return null
  const bump = tileVersion.value[item.key]
  return `${apiBase}/api/thumb-art/${encodeURIComponent(copy.rating_key)}?thumb=1${bump ? `&t=${bump}` : ''}`
}

function tileServerLabel(item: ThumbArtItem): string {
  return nonPlexCopies(item).map(c => mediaServerLabel(c.server_id, settings.mediaServers.value)).join(', ')
}

function refresh() {
  failedImages.value = new Set()
  fetchItems(isTV.value, libraryId.value, (m: any) => ({
    key: m.key,
    title: m.title,
    year: m.year,
    tmdb_id: m.tmdb_id,
    library_id: m.library_id,
    addedAt: m.addedAt,
    labels: m.labels || [],
    server_id: m.server_id,
    other_servers: m.other_servers || null,
  }), serverId.value)
}

function openModal(item: ThumbArtItem) {
  selectedItem.value = { ...item, mediaType: isTV.value ? 'tv-show' : 'movie' }
}

function onImgError(key: string) {
  failedImages.value = new Set([...failedImages.value, key])
}

function onThumbArtUpdated() {
  if (!selectedItem.value) return
  const key = selectedItem.value.key
  failedImages.value = new Set([...failedImages.value].filter(k => k !== key))
  tileVersion.value = { ...tileVersion.value, [key]: Date.now() }
}

watch(libraryId, () => refresh())
onMounted(() => refresh())
</script>

<template>
  <div class="square-art-view">
    <div class="page-header">
      <h2>🌄 Thumb Art<img v-for="t in headerServerTypes" :key="t" :src="`/icons/${t}.svg`" class="header-server-icon" :alt="t" :title="`Thumb Art is for ${t === 'emby' ? 'Emby' : 'Jellyfin'}`" /></h2>
      <div class="header-actions">
        <div class="stats">
          <span class="stat-total">{{ eligibleItems.length }} on Jellyfin/Emby</span>
        </div>
        <input v-model="search" class="search-input" type="text" placeholder="Search..." />
        <select v-model="filterLabel" class="toolbar-select">
          <option value="">All Labels</option>
          <option v-for="label in allLabels" :key="label" :value="label">{{ label }}</option>
        </select>
        <select v-model="sortBy" class="toolbar-select">
          <option value="title_asc">Title (A–Z)</option>
          <option value="title_desc">Title (Z–A)</option>
          <option value="year_desc">Year (Newest)</option>
          <option value="year_asc">Year (Oldest)</option>
          <option value="added_desc">Date Added (Newest)</option>
          <option value="added_asc">Date Added (Oldest)</option>
        </select>
        <button class="btn-refresh" @click="refresh" :disabled="loading">
          <svg v-if="loading" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <div class="section-note">
      Thumb Art is the 16:9 landscape image Jellyfin and Emby use for thumbnail views. Plex has no
      equivalent, so only titles on a Jellyfin or Emby server are listed. Click a title to make one
      from a backdrop with your template/preset and send it, or save a copy to disk.
    </div>

    <div v-if="loading" class="state-msg">Loading...</div>

    <div v-else-if="displayItems.length === 0" class="state-msg">
      <template v-if="search">No results for "{{ search }}".</template>
      <template v-else>No titles from a Jellyfin or Emby server here yet. Run a library scan.</template>
    </div>

    <div v-else class="art-grid">
      <div
        v-for="item in pagedItems"
        :key="item.key"
        class="art-card"
        :class="{ 'has-art': !failedImages.has(item.key) }"
        :title="`Click to create/replace Thumb Art (${tileServerLabel(item)})`"
        @click="openModal(item)"
      >
        <div class="art-area">
          <img
            v-if="tileSrc(item) && !failedImages.has(item.key)"
            :src="tileSrc(item) || ''"
            :alt="item.title"
            class="art-img"
            loading="lazy"
            @error="onImgError(item.key)"
          />
          <div v-else class="no-art-placeholder">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.35"><rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="8" cy="10" r="1.5"/><polyline points="22 16 16 11 6 19"/></svg>
            <span>No Thumb Art yet</span>
          </div>
        </div>
        <div class="art-meta">
          <span class="art-title">{{ item.title }}</span>
          <span v-if="item.year" class="art-year">{{ item.year }}</span>
        </div>
      </div>
    </div>

    <div v-if="!loading && displayItems.length > 0" class="pagination-bar">
      <button class="page-btn" @click="prevPage" :disabled="page === 1">Prev</button>
      <span class="page-indicator">{{ page }} / {{ totalPages }}</span>
      <button class="page-btn" @click="nextPage" :disabled="page === totalPages">Next</button>
    </div>
  </div>

  <ThumbArtModal
    v-if="selectedItem"
    :item="selectedItem"
    @close="selectedItem = null"
    @updated="onThumbArtUpdated"
  />
</template>

<style scoped>
.header-server-icon {
  width: 20px;
  height: 20px;
  margin-left: 8px;
  vertical-align: -3px;
}
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

.prefer-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.toolbar-label {
  font-size: 12px;
  color: #a8b3cf;
  white-space: nowrap;
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

.plex-only-note {
  padding: 60px 20px;
  font-size: 15px;
  font-weight: 500;
  color: #6b7a99;
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

/* Grid — square (1:1) thumbnails, mirroring what square art itself will look like */
.art-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
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
  aspect-ratio: 16 / 9;
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
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 10px;
  }
}
</style>
