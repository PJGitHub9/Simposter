<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getApiBase } from '@/services/apiBase'
import LogoEditorModal from '@/components/LogoEditorModal.vue'

type LogoItem = {
  key: string
  title: string
  year?: number | string
  logo_url?: string | null
  tmdb_id?: number | null
  is_tv?: boolean
}

const route = useRoute()
const loading = ref(false)
const items = ref<LogoItem[]>([])
const filter = ref<'all' | 'has_logo' | 'missing'>('all')
const sortBy = ref<'title_asc' | 'title_desc' | 'year_desc' | 'year_asc'>('title_asc')
const search = ref('')
const failedImages = ref<Set<string>>(new Set())
const selectedItem = ref<LogoItem | null>(null)

const isTV = computed(() => route.name === 'tv-logos')
const libraryId = computed(() => (route.query.library as string) || '')

const withLogo = computed(() => items.value.filter(m => m.logo_url))
const withoutLogo = computed(() => items.value.filter(m => !m.logo_url))

const displayItems = computed(() => {
  let list = items.value

  // Filter
  if (filter.value === 'has_logo') list = list.filter(m => m.logo_url && !failedImages.value.has(m.key))
  else if (filter.value === 'missing') list = list.filter(m => !m.logo_url || failedImages.value.has(m.key))

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

async function fetchItems() {
  loading.value = true
  items.value = []
  failedImages.value = new Set()
  const apiBase = getApiBase()
  try {
    const endpoint = isTV.value ? 'tv-shows' : 'movies'
    const params = libraryId.value ? `?library_id=${libraryId.value}` : ''
    const res = await fetch(`${apiBase}/api/${endpoint}${params}`)
    if (res.ok) {
      items.value = await res.json()
    }
  } catch { /* ignore */ }
  loading.value = false
}

function openEditor(item: LogoItem) {
  selectedItem.value = { ...item, is_tv: isTV.value }
}

function onImgError(key: string) {
  failedImages.value = new Set([...failedImages.value, key])
}

function onLogoUpdated(newLogoUrl: string | null) {
  if (selectedItem.value && newLogoUrl) {
    const target = items.value.find(i => i.key === selectedItem.value!.key)
    if (target) {
      target.logo_url = newLogoUrl
      failedImages.value = new Set([...failedImages.value].filter(k => k !== target.key))
    }
  }
}

watch(libraryId, fetchItems)
onMounted(fetchItems)
</script>

<template>
  <div class="logos-view">
    <div class="page-header">
      <h2>🖼️ Logos</h2>
      <div class="header-actions">
        <div class="stats">
          <span class="stat-cached">{{ withLogo.length }} cached</span>
          <span class="stat-sep">/</span>
          <span class="stat-total">{{ items.length }} total</span>
          <span v-if="withoutLogo.length > 0" class="stat-missing">
            ({{ withoutLogo.length }} missing)
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
          <option value="has_logo">Has logo</option>
          <option value="missing">Missing logo</option>
        </select>
        <select v-model="sortBy" class="toolbar-select">
          <option value="title_asc">Title (A–Z)</option>
          <option value="title_desc">Title (Z–A)</option>
          <option value="year_desc">Year (Newest)</option>
          <option value="year_asc">Year (Oldest)</option>
        </select>
        <button class="btn-refresh" @click="fetchItems" :disabled="loading">
          <svg v-if="loading" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="state-msg">Loading logos...</div>

    <div v-else-if="displayItems.length === 0" class="state-msg">
      <template v-if="search">No results for "{{ search }}".</template>
      <template v-else-if="filter === 'missing'">No items are missing a logo.</template>
      <template v-else-if="filter === 'has_logo'">No logos cached yet. Run a library scan.</template>
      <template v-else-if="withLogo.length === 0">
        No clearlogos found in Plex for this library. Run a library scan to check for clearlogos.
      </template>
    </div>

    <div v-else class="logo-grid">
      <div
        v-for="item in displayItems"
        :key="item.key"
        class="logo-card"
        :class="{
          'has-logo': !!item.logo_url && !failedImages.has(item.key),
          'no-logo': !item.logo_url || failedImages.has(item.key),
        }"
        title="Click to edit logo"
        @click="openEditor(item)"
      >
        <div class="logo-area">
          <img
            v-if="item.logo_url && !failedImages.has(item.key)"
            :src="item.logo_url"
            :alt="item.title"
            class="logo-img"
            @error="onImgError(item.key)"
          />
          <div v-else class="no-logo-placeholder">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.35"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9l4-4 4 4 4-4 4 4"/><circle cx="8.5" cy="14.5" r="1.5"/></svg>
            <span>No logo cached</span>
          </div>
        </div>
        <div class="logo-meta">
          <span class="logo-title">{{ item.title }}</span>
          <span v-if="item.year" class="logo-year">{{ item.year }}</span>
        </div>
      </div>
    </div>
  </div>

  <LogoEditorModal
    v-if="selectedItem"
    :item="selectedItem"
    @close="selectedItem = null"
    @updated="onLogoUpdated"
  />
</template>

<style scoped>
.logos-view {
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

/* Grid — wider cards for landscape logos */
.logo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
}

.logo-card {
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(14, 16, 24, 0.6);
  transition: border-color 0.15s, transform 0.15s;
  cursor: pointer;
}

.logo-card:hover {
  border-color: rgba(61, 214, 183, 0.4);
  transform: translateY(-2px);
}

.logo-card.no-logo {
  opacity: 0.7;
}

/* Logo display area — 3:1 aspect, dark background */
.logo-area {
  aspect-ratio: 3 / 1;
  background: #0a0b12;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 14px;
  position: relative;
}

.logo-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.no-logo-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: rgba(255, 255, 255, 0.3);
  font-size: 11px;
  text-align: center;
}

/* Title/year row below the logo */
.logo-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.logo-title {
  font-size: 12px;
  font-weight: 500;
  color: #c9d1e0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.logo-year {
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

  .logo-grid {
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 10px;
  }
}
</style>
