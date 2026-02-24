<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore } from '@/stores/settings'

type LocalAsset = {
  filename: string
  path: string
  full_path: string
  size: number
  modified: string
  folder: string
  library_id?: string
  library_name?: string
  movie_title?: string
  movie_year?: string | number | null
}

const localAssets = ref<LocalAsset[]>([])
const localAssetsLoading = ref(false)
const localAssetsError = ref<string | null>(null)
const assetSearchQuery = ref('')
const assetFolderFilter = ref('')
const selectedAsset = ref<LocalAsset | null>(null)
const showModal = ref(false)
const deletingAsset = ref(false)
const showMovieTitles = ref(false)

const route = useRoute()
const apiBase = getApiBase()
const settings = useSettingsStore()

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

// Get all configured libraries (movie + TV show)
const allLibraries = computed(() => {
  const movieLibs = (settings.plex.value.libraryMappings || []).map(lib => ({
    id: lib.id,
    displayName: lib.displayName || lib.title || lib.id,
    type: 'movie'
  }))
  const tvShowLibs = (settings.plex.value.tvShowLibraryMappings || []).map(lib => ({
    id: lib.id,
    displayName: lib.displayName || lib.title || lib.id,
    type: 'tvshow'
  }))
  return [...movieLibs, ...tvShowLibs].filter(lib => lib.id)
})

// Get unique folders from assets
const assetFolders = computed(() => {
  const folders = new Set<string>()
  localAssets.value.forEach(asset => {
    if (asset.folder) folders.add(asset.folder)
  })
  return Array.from(folders).sort()
})

// Helper to check if an asset belongs to a library
// Checks embedded metadata first, falls back to folder path matching
const assetBelongsToLibrary = (asset: LocalAsset, libraryId: string | number, libraryDisplayName: string): boolean => {
  const libIdStr = String(libraryId)
  // Prefer embedded metadata (most reliable)
  if (asset.library_id) {
    return String(asset.library_id) === libIdStr
  }

  // Fall back to folder-based matching for older assets without metadata
  if (!asset.folder) return false
  const folderLower = asset.folder.toLowerCase()
  const libraryLower = (libraryDisplayName || '').toLowerCase()
  // Check if folder is the library name or contains it as a path component
  return folderLower === libraryLower || folderLower.includes(`/${libraryLower}`) || folderLower.includes(`\\${libraryLower}`)
}

const getDisplayName = (asset: LocalAsset): string => {
  const title = asset.movie_title || ''
  const year = asset.movie_year ? ` (${asset.movie_year})` : ''
  if (showMovieTitles.value && title) {
    return `${title}${year}`
  }
  return asset.filename
}

const activeLibraryId = computed(() => {
  const fromRoute = (route.query.library as string) || ''
  if (fromRoute) return String(fromRoute)
  const firstLib = settings.plex.value.libraryMappings && settings.plex.value.libraryMappings[0]
  if (firstLib?.id) return String(firstLib.id)
  return settings.plex.value.movieLibraryName ? String(settings.plex.value.movieLibraryName) : ''
})

// Filter assets by search, folder, and library
const filteredAssets = computed(() => {
  let result = localAssets.value

  // Filter by search query
  if (assetSearchQuery.value.trim()) {
    const query = assetSearchQuery.value.toLowerCase()
    result = result.filter(asset =>
      getDisplayName(asset).toLowerCase().includes(query) ||
      asset.filename.toLowerCase().includes(query) ||
      asset.folder.toLowerCase().includes(query)
    )
  }

  // Filter by library (using embedded metadata when available)
  if (activeLibraryId.value) {
    const selectedLibrary = allLibraries.value.find(lib => String(lib.id) === String(activeLibraryId.value))
    if (selectedLibrary) {
      result = result.filter(asset => assetBelongsToLibrary(asset, selectedLibrary.id, selectedLibrary.displayName))
    }
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

// Modal functions
const openModal = (asset: LocalAsset) => {
  selectedAsset.value = asset
  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
  selectedAsset.value = null
}

// Delete asset
const deleteAsset = async (asset: LocalAsset) => {
  if (!window.confirm(`Are you sure you want to delete "${asset.filename}"? This cannot be undone.`)) {
    return
  }

  deletingAsset.value = true
  try {
    const res = await fetch(`${apiBase}/api/local-assets/${asset.path}`, {
      method: 'DELETE'
    })
    if (!res.ok) throw new Error(`Failed to delete: ${res.status}`)

    // Remove from local list
    localAssets.value = localAssets.value.filter(a => a.path !== asset.path)

    // Close modal if this was the selected asset
    if (selectedAsset.value?.path === asset.path) {
      closeModal()
    }
  } catch (err: unknown) {
    alert(`Failed to delete file: ${err instanceof Error ? err.message : 'Unknown error'}`)
  } finally {
    deletingAsset.value = false
  }
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
      <label class="toggle show-titles-toggle">
        <input type="checkbox" v-model="showMovieTitles" />
        <span class="toggle-slider"></span>
        <span class="toggle-label">
          {{ showMovieTitles ? 'Show movie titles' : 'Show filenames' }}
        </span>
      </label>
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
        <div class="asset-image" @click="openModal(asset)">
          <img
            :src="`${apiBase}/api/local-assets/${asset.path}`"
            :alt="asset.filename"
            loading="lazy"
          />
          <div class="image-overlay">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"/>
              <path d="M21 21l-4.35-4.35"/>
              <path d="M11 8v6"/>
              <path d="M8 11h6"/>
            </svg>
          </div>
          <button class="btn-delete" @click.stop="deleteAsset(asset)" :disabled="deletingAsset">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
        <div class="asset-info">
          <p class="asset-filename" :title="getDisplayName(asset)">{{ getDisplayName(asset) }}</p>
          <p v-if="showMovieTitles && asset.filename" class="asset-subtitle" :title="asset.filename">
            📄 {{ asset.filename }}
          </p>
          <div class="asset-meta">
            <span class="asset-size">{{ formatFileSize(asset.size) }}</span>
            <span class="asset-date">{{ formatDate(asset.modified) }}</span>
          </div>
          <p v-if="asset.library_name" class="asset-library" :title="`Library: ${asset.library_name}`">
            📚 {{ asset.library_name }}
          </p>
          <p v-else-if="asset.folder" class="asset-folder">📁 {{ asset.folder }}</p>
        </div>
      </div>
    </div>

    <!-- Modal -->
    <div v-if="showModal && selectedAsset" class="modal-overlay" @click="closeModal">
      <div class="modal-content" @click.stop>
        <button class="modal-close" @click="closeModal">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18"/>
            <path d="M6 6l12 12"/>
          </svg>
        </button>
        <img
          :src="`${apiBase}/api/local-assets/${selectedAsset.path}`"
          :alt="selectedAsset.filename"
          class="modal-image"
        />
        <div class="modal-info">
          <h3>{{ getDisplayName(selectedAsset) }}</h3>
          <p v-if="showMovieTitles && selectedAsset.filename" class="modal-subtitle" :title="selectedAsset.filename">
            📄 {{ selectedAsset.filename }}
          </p>
          <p class="modal-path">{{ selectedAsset.full_path }}</p>
          <div class="modal-details">
            <span>{{ formatFileSize(selectedAsset.size) }}</span>
            <span>•</span>
            <span>{{ formatDate(selectedAsset.modified) }}</span>
            <span v-if="selectedAsset.library_name">•</span>
            <span v-if="selectedAsset.library_name">📚 {{ selectedAsset.library_name }}</span>
            <span v-else-if="selectedAsset.folder">•</span>
            <span v-else-if="selectedAsset.folder">📁 {{ selectedAsset.folder }}</span>
          </div>
          <button class="btn-delete-modal" @click="deleteAsset(selectedAsset)" :disabled="deletingAsset">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
            Delete
          </button>
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

.toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.45rem 0.75rem;
  background: var(--input-bg, #242933);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 6px;
  cursor: pointer;
}

.toggle input {
  display: none;
}

.toggle-slider {
  width: 42px;
  height: 22px;
  background: var(--border, #2a2f3e);
  border-radius: 999px;
  position: relative;
  transition: background 0.2s;
}

.toggle-slider::after {
  content: "";
  position: absolute;
  top: 3px;
  left: 3px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s ease;
}

.toggle input:checked + .toggle-slider {
  background: var(--accent, #3dd6b7);
}

.toggle input:checked + .toggle-slider::after {
  transform: translateX(20px);
}

.toggle-label {
  color: var(--text-secondary, #aaa);
  font-size: 0.9rem;
  white-space: nowrap;
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
  position: relative;
  aspect-ratio: 2/3;
  overflow: hidden;
  background: var(--surface-alt, #242933);
  cursor: pointer;
}

.asset-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.asset-image:hover img {
  transform: scale(1.05);
}

.image-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  opacity: 0;
  transition: opacity 0.2s;
  pointer-events: none;
}

.image-overlay svg {
  color: #fff;
}

.asset-image:hover .image-overlay {
  opacity: 1;
}

.btn-delete {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 8px;
  background: rgba(255, 107, 107, 0.9);
  border: none;
  border-radius: 6px;
  color: #fff;
  cursor: pointer;
  opacity: 0;
  transition: all 0.2s;
  z-index: 10;
}

.btn-delete:hover:not(:disabled) {
  background: rgba(255, 0, 0, 1);
  transform: scale(1.1);
}

.btn-delete:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.asset-image:hover .btn-delete {
  opacity: 1;
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

.asset-subtitle {
  margin: -0.25rem 0 0.5rem 0;
  color: var(--text-secondary, #9aa4b5);
  font-size: 0.8rem;
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

.asset-library {
  margin: 0;
  padding: 0.4rem 0.6rem;
  background: rgba(138, 102, 255, 0.15);
  border-radius: 4px;
  color: #a78bfa;
  font-size: 0.8rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 2rem;
  animation: fadeIn 0.2s ease-in;
}

.modal-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  background: var(--surface, #1a1f2e);
  border-radius: 12px;
  padding: 1.5rem;
  animation: scaleIn 0.2s ease-out;
}

.modal-close {
  position: absolute;
  top: 1rem;
  right: 1rem;
  padding: 0.5rem;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  border-radius: 6px;
  color: #fff;
  cursor: pointer;
  transition: all 0.2s;
  z-index: 10;
}

.modal-close:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: rotate(90deg);
}

.modal-image {
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
  border-radius: 8px;
}

.modal-info {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.modal-info h3 {
  margin: 0;
  color: var(--text-primary, #fff);
  font-size: 1.2rem;
  font-weight: 600;
}

.modal-subtitle {
  margin: 0;
  color: var(--text-secondary, #9aa4b5);
  font-size: 0.9rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-path {
  margin: 0.5rem 0 0 0;
  color: var(--text-secondary, #aaa);
  font-size: 0.85rem;
  font-family: monospace;
  word-break: break-all;
}

.modal-details {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  color: var(--text-secondary, #aaa);
  font-size: 0.9rem;
}

.btn-delete-modal {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.25rem;
  background: rgba(255, 107, 107, 0.2);
  border: 1px solid rgba(255, 107, 107, 0.4);
  border-radius: 6px;
  color: #ff6b6b;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  align-self: flex-start;
}

.btn-delete-modal:hover:not(:disabled) {
  background: rgba(255, 107, 107, 0.3);
  border-color: rgba(255, 107, 107, 0.6);
  transform: translateY(-2px);
}

.btn-delete-modal:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes scaleIn {
  from {
    transform: scale(0.9);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
