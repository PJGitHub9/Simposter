<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getApiBase } from '@/services/apiBase'

type LocalAsset = {
  filename: string
  path: string
  full_path: string
  size: number
  modified: string
  folder: string
}

const localAssets = ref<LocalAsset[]>([])
const localAssetsLoading = ref(false)
const localAssetsError = ref<string | null>(null)
const assetSearchQuery = ref('')
const assetFolderFilter = ref('')

const apiBase = getApiBase()

// Local assets functions
const fetchLocalAssets = async () => {
  localAssetsLoading.value = true
  localAssetsError.value = null
  try {
    const res = await fetch(`${apiBase}/api/local-assets`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    localAssets.value = data.assets || []
  } catch (err: unknown) {
    localAssetsError.value = err instanceof Error ? err.message : 'Failed to load local assets'
  } finally {
    localAssetsLoading.value = false
  }
}

// Get unique folders from assets
const assetFolders = computed(() => {
  const folders = new Set<string>()
  localAssets.value.forEach(asset => {
    if (asset.folder) folders.add(asset.folder)
  })
  return Array.from(folders).sort()
})

// Filter assets by search and folder
const filteredAssets = computed(() => {
  let result = localAssets.value

  // Filter by search query
  if (assetSearchQuery.value.trim()) {
    const query = assetSearchQuery.value.toLowerCase()
    result = result.filter(asset =>
      asset.filename.toLowerCase().includes(query) ||
      asset.folder.toLowerCase().includes(query)
    )
  }

  // Filter by folder
  if (assetFolderFilter.value) {
    result = result.filter(asset => asset.folder === assetFolderFilter.value)
  }

  return result
})

// Format file size
const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Format date
const formatDate = (isoDate: string): string => {
  const date = new Date(isoDate)
  return date.toLocaleString()
}

onMounted(() => {
  fetchLocalAssets()
})
</script>

<template>
  <div class="local-assets-view">
    <div class="header">
      <div>
        <h1>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
            <polyline points="13 2 13 9 20 9"/>
          </svg>
          Local Assets
        </h1>
        <p class="subtitle">Browse and manage saved posters from the output folder</p>
      </div>
      <button class="btn-refresh" @click="fetchLocalAssets" :disabled="localAssetsLoading">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="1 4 1 10 7 10"/>
          <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
        </svg>
        Refresh
      </button>
    </div>

    <!-- Filters -->
    <div class="assets-filters">
      <input
        v-model="assetSearchQuery"
        type="text"
        placeholder="Search assets..."
        class="filter-input"
      />
      <select v-model="assetFolderFilter" class="filter-select">
        <option value="">All Folders</option>
        <option v-for="folder in assetFolders" :key="folder" :value="folder">
          {{ folder }}
        </option>
      </select>
      <div class="asset-count">
        {{ filteredAssets.length }} {{ filteredAssets.length === 1 ? 'asset' : 'assets' }}
      </div>
    </div>

    <!-- Assets Grid -->
    <div v-if="localAssetsLoading" class="loading">
      <div class="spinner"></div>
      <p>Loading assets...</p>
    </div>
    <div v-else-if="localAssetsError" class="error">
      <p>{{ localAssetsError }}</p>
      <button class="btn-retry" @click="fetchLocalAssets">Retry</button>
    </div>
    <div v-else-if="filteredAssets.length === 0" class="empty-state">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
        <polyline points="13 2 13 9 20 9"/>
      </svg>
      <p class="empty-title">No local assets found</p>
      <p class="empty-hint">Saved posters will appear here</p>
    </div>
    <div v-else class="assets-grid">
      <div v-for="asset in filteredAssets" :key="asset.path" class="asset-card">
        <div class="asset-image">
          <img
            :src="`${apiBase}/api/local-assets/${asset.path}`"
            :alt="asset.filename"
            loading="lazy"
          />
        </div>
        <div class="asset-info">
          <p class="asset-filename" :title="asset.filename">{{ asset.filename }}</p>
          <div class="asset-meta">
            <span class="asset-size">{{ formatFileSize(asset.size) }}</span>
            <span class="asset-date">{{ formatDate(asset.modified) }}</span>
          </div>
          <p v-if="asset.folder" class="asset-folder">📁 {{ asset.folder }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.local-assets-view {
  padding: 1.5rem;
  max-width: 100%;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 2rem;
}

.header h1 {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0 0 0.5rem 0;
  color: var(--text-primary, #fff);
  font-size: 2rem;
  font-weight: 700;
}

.header h1 svg {
  color: var(--accent, #3dd6b7);
}

.subtitle {
  margin: 0;
  color: var(--text-secondary, #aaa);
  font-size: 0.95rem;
}

.assets-filters {
  display: flex;
  gap: 1rem;
  margin-bottom: 1.5rem;
  align-items: center;
  padding: 1rem;
  background: var(--surface, #1a1f2e);
  border-radius: 8px;
  border: 1px solid var(--border, #2a2f3e);
}

.filter-input {
  flex: 1;
  padding: 0.75rem;
  background: var(--input-bg, #242933);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  font-size: 0.95rem;
}

.filter-input:focus {
  outline: none;
  border-color: var(--accent, #3dd6b7);
}

.filter-select {
  padding: 0.75rem;
  background: var(--input-bg, #242933);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  font-size: 0.95rem;
  min-width: 200px;
}

.filter-select:focus {
  outline: none;
  border-color: var(--accent, #3dd6b7);
}

.asset-count {
  color: var(--text-secondary, #aaa);
  font-size: 0.9rem;
  font-weight: 500;
  padding: 0.75rem 1rem;
  background: rgba(61, 214, 183, 0.1);
  border-radius: 4px;
  white-space: nowrap;
}

.btn-refresh {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.25rem;
  background: var(--accent, #3dd6b7);
  color: #000;
  border: none;
  border-radius: 4px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-refresh:hover:not(:disabled) {
  background: #2bc4a3;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(61, 214, 183, 0.3);
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  color: var(--text-secondary, #aaa);
}

.loading p {
  margin: 1rem 0 0 0;
  font-size: 1.1rem;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(255, 255, 255, 0.2);
  border-top-color: var(--accent, #3dd6b7);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error {
  text-align: center;
  padding: 4rem 2rem;
  color: #ff6b6b;
}

.error p {
  margin: 0 0 1rem 0;
  font-size: 1.1rem;
}

.btn-retry {
  padding: 0.75rem 1.5rem;
  background: var(--accent, #3dd6b7);
  color: #000;
  border: none;
  border-radius: 4px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-retry:hover {
  background: #2bc4a3;
  transform: translateY(-2px);
}

.assets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1.5rem;
}

.asset-card {
  background: var(--surface, #1a1f2e);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border, #2a2f3e);
  transition: all 0.2s;
}

.asset-card:hover {
  border-color: var(--accent, #3dd6b7);
  transform: translateY(-4px);
  box-shadow: 0 8px 20px rgba(61, 214, 183, 0.2);
}

.asset-image {
  aspect-ratio: 2/3;
  overflow: hidden;
  background: var(--surface-alt, #242933);
}

.asset-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.asset-info {
  padding: 1rem;
}

.asset-filename {
  margin: 0 0 0.75rem 0;
  color: var(--text-primary, #fff);
  font-size: 0.9rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-meta {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.asset-size,
.asset-date {
  color: var(--text-secondary, #aaa);
  font-size: 0.8rem;
}

.asset-folder {
  margin: 0;
  padding: 0.4rem 0.6rem;
  background: rgba(61, 214, 183, 0.15);
  border-radius: 4px;
  color: var(--accent, #3dd6b7);
  font-size: 0.8rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  color: var(--text-secondary, #aaa);
}

.empty-state svg {
  opacity: 0.3;
  margin-bottom: 1.5rem;
}

.empty-title {
  margin: 0 0 0.5rem 0;
  font-size: 1.3rem;
  font-weight: 600;
  color: var(--text-primary, #fff);
}

.empty-hint {
  margin: 0;
  font-size: 0.95rem;
  opacity: 0.7;
}
</style>
