<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getApiBase } from '@/services/apiBase'

const route = useRoute()
const apiBase = getApiBase()

const libraryId = ref('')
const mediaType = ref('movie')
const loading = ref(false)
const backupCount = ref(0)
const backupDate = ref<string | null>(null)
const backupSize = ref(0)
const backupPath = ref('')
const includeSeasons = ref(true)
const actionInProgress = ref(false)
const showConfirmDelete = ref(false)

// Restore preview state
const showRestorePreview = ref(false)
const previewLoading = ref(false)
const previewItems = ref<any[]>([])
const previewStats = ref({ total: 0, matched: 0, unmatched: 0 })

// Manual assign state
const libraryItems = ref<any[]>([])
const libraryItemsLoaded = ref(false)
const libraryItemsLoading = ref(false)
const assigningItem = ref<any>(null)
const assignSearch = ref('')

const selectedCount = computed(() => previewItems.value.filter(i => i.selected).length)
const matchedCount = computed(() => previewItems.value.filter(i => i.match_type !== 'unmatched').length)

const allMatchedSelected = computed(() => {
  const matched = previewItems.value.filter(i => i.rating_key)
  return matched.length > 0 && matched.every(i => i.selected)
})

const filteredAssignItems = computed(() => {
  const q = assignSearch.value.toLowerCase().trim()
  if (!q) return libraryItems.value
  return libraryItems.value.filter(i => i.title.toLowerCase().includes(q))
})

const isTv = computed(() => mediaType.value === 'tv-show')

const toggleSelectAll = () => {
  const newVal = !allMatchedSelected.value
  previewItems.value.forEach(i => {
    if (i.rating_key) i.selected = newVal
  })
}

const formatSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const formatDate = (iso: string | null) => {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const thumbUrl = (filename: string) => {
  return `${apiBase}/api/backup/file/${libraryId.value}/${encodeURIComponent(filename)}?media_type=${mediaType.value}`
}

const fetchStatus = async () => {
  loading.value = true
  try {
    const res = await fetch(`${apiBase}/api/backup/status/${libraryId.value}?media_type=${mediaType.value}`)
    if (res.ok) {
      const data = await res.json()
      backupCount.value = data.count || 0
      backupDate.value = data.last_date || null
      backupSize.value = data.total_size || 0
      backupPath.value = data.path || ''
    }
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

const fetchLibraryItems = async () => {
  if (libraryItemsLoaded.value) return
  libraryItemsLoading.value = true
  try {
    const res = await fetch(`${apiBase}/api/backup/library-items/${libraryId.value}?media_type=${mediaType.value}`)
    if (res.ok) {
      const data = await res.json()
      libraryItems.value = data.items || []
      libraryItemsLoaded.value = true
    }
  } catch { /* ignore */ } finally {
    libraryItemsLoading.value = false
  }
}

const openAssign = (item: any) => {
  assigningItem.value = item
  assignSearch.value = ''
  fetchLibraryItems()
}

const assignMatch = (plexItem: any) => {
  if (assigningItem.value) {
    assigningItem.value.rating_key = plexItem.rating_key
    assigningItem.value.plex_title = plexItem.title
    assigningItem.value.match_type = 'manual'
    assigningItem.value.selected = true
  }
  assigningItem.value = null
}

const startBackup = async () => {
  actionInProgress.value = true
  try {
    const res = await fetch(`${apiBase}/api/backup/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ library_id: libraryId.value, media_type: mediaType.value, include_seasons: includeSeasons.value })
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
      alert(err.detail || 'Failed to start backup')
      actionInProgress.value = false
      return
    }
    if (typeof (window as any).startBackupPolling === 'function') {
      ;(window as any).startBackupPolling()
    }
    pollUntilDone()
  } catch {
    alert('Failed to start backup')
    actionInProgress.value = false
  }
}

const loadRestorePreview = async () => {
  previewLoading.value = true
  showRestorePreview.value = true
  previewItems.value = []
  previewStats.value = { total: 0, matched: 0, unmatched: 0 }

  try {
    const res = await fetch(`${apiBase}/api/backup/restore/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ library_id: libraryId.value, media_type: mediaType.value })
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
      alert(err.detail || 'Failed to load restore preview')
      showRestorePreview.value = false
      return
    }
    const data = await res.json()
    previewStats.value = { total: data.total, matched: data.matched, unmatched: data.unmatched }
    previewItems.value = (data.items || []).map((item: any) => ({
      ...item,
      selected: item.rating_key ? true : false,
    }))
  } catch {
    alert('Failed to load restore preview')
    showRestorePreview.value = false
  } finally {
    previewLoading.value = false
  }
}

const executeRestore = async () => {
  const selected = previewItems.value.filter(i => i.selected && i.rating_key)
  if (selected.length === 0) return

  showRestorePreview.value = false
  actionInProgress.value = true

  try {
    const res = await fetch(`${apiBase}/api/backup/restore/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        library_id: libraryId.value,
        items: selected.map(i => ({ filename: i.filename, rating_key: i.rating_key }))
      })
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
      alert(err.detail || 'Failed to start restore')
      actionInProgress.value = false
      return
    }
    if (typeof (window as any).startBackupPolling === 'function') {
      ;(window as any).startBackupPolling()
    }
    pollUntilDone()
  } catch {
    alert('Failed to start restore')
    actionInProgress.value = false
  }
}

const deleteBackup = async () => {
  showConfirmDelete.value = false
  actionInProgress.value = true
  try {
    const res = await fetch(`${apiBase}/api/backup/delete/${libraryId.value}?media_type=${mediaType.value}`, { method: 'DELETE' })
    if (!res.ok) {
      alert('Failed to delete backup')
    }
    await fetchStatus()
  } catch {
    alert('Failed to delete backup')
  } finally {
    actionInProgress.value = false
  }
}

let pollInterval: ReturnType<typeof setInterval> | null = null

const pollUntilDone = () => {
  if (pollInterval) clearInterval(pollInterval)
  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`${apiBase}/api/backup/progress`)
      if (res.ok) {
        const data = await res.json()
        if (data.state !== 'running') {
          if (pollInterval) clearInterval(pollInterval)
          pollInterval = null
          actionInProgress.value = false
          await fetchStatus()
        }
      }
    } catch {
      /* ignore */
    }
  }, 1000)
}

onMounted(() => {
  libraryId.value = (route.query.library as string) || ''
  mediaType.value = (route.query.type as string) || 'movie'
  fetchStatus()
})
</script>

<template>
  <div class="backup-view">
    <div class="page-header">
      <div>
        <h1>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Backup / Restore
        </h1>
        <p class="page-subtitle">Back up original Plex posters and restore them later</p>
      </div>
      <button class="btn-refresh" @click="fetchStatus" :disabled="loading || actionInProgress">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="1 4 1 10 7 10"/>
          <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
        </svg>
        Refresh
      </button>
    </div>

    <!-- Two-column layout -->
    <div class="sections-grid">

      <!-- ═══ BACKUP SECTION ═══ -->
      <div class="section-card">
        <div class="section-header">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          <h2>Backup</h2>
        </div>

        <!-- Status -->
        <div v-if="loading" class="status-row muted">Loading...</div>
        <div v-else-if="backupCount > 0" class="status-block">
          <div class="status-row">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="icon-ok">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            <span><strong>{{ backupCount }}</strong> {{ backupCount === 1 ? 'poster' : 'posters' }} backed up</span>
          </div>
          <div v-if="backupDate" class="status-row muted small">Last: {{ formatDate(backupDate) }}</div>
          <div class="status-row muted small">Size: {{ formatSize(backupSize) }}</div>
        </div>
        <div v-else class="status-row muted">No backup yet</div>

        <!-- Folder path -->
        <div v-if="backupPath" class="folder-path">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          <span>{{ backupPath }}</span>
        </div>

        <!-- TV: include seasons toggle -->
        <label v-if="isTv" class="toggle-option">
          <input type="checkbox" v-model="includeSeasons" />
          <span class="toggle-slider"></span>
          <span class="toggle-text">Include season posters</span>
        </label>

        <!-- Buttons -->
        <div class="section-actions">
          <button class="btn-primary" @click="startBackup" :disabled="actionInProgress">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            {{ backupCount > 0 ? 'Re-backup' : 'Backup Posters' }}
          </button>
          <button v-if="backupCount > 0" class="btn-danger-outline" @click="showConfirmDelete = true" :disabled="actionInProgress">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
            Delete
          </button>
        </div>
      </div>

      <!-- ═══ RESTORE SECTION ═══ -->
      <div class="section-card">
        <div class="section-header">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          <h2>Restore</h2>
        </div>

        <p class="section-desc">
          Place poster files in the backup folder below. Restore will auto-match filenames to your Plex library, or you can manually assign them.
        </p>

        <!-- Folder path -->
        <div v-if="backupPath" class="folder-path">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          <span>{{ backupPath }}</span>
        </div>

        <!-- Filename format guide -->
        <div class="format-guide">
          <div class="format-label">Expected filename format</div>
          <div class="format-examples">
            <code v-if="!isTv">Title (Year).jpg</code>
            <code v-if="!isTv" class="example">The Matrix (1999).jpg</code>
            <template v-if="isTv">
              <code>Show Name (Year).jpg</code>
              <code>Show Name (Year) - Season 01.jpg</code>
              <code class="example">Breaking Bad (2008).jpg</code>
              <code class="example">Breaking Bad (2008) - Season 01.jpg</code>
            </template>
          </div>
          <div class="format-note">Files that don't match this pattern can still be manually assigned</div>
        </div>

        <!-- Restore button -->
        <div class="section-actions">
          <button class="btn-primary" @click="loadRestorePreview" :disabled="actionInProgress || backupCount === 0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            Restore Posters
          </button>
        </div>
      </div>

    </div>

    <!-- ═══ RESTORE PREVIEW MODAL ═══ -->
    <div v-if="showRestorePreview" class="modal-overlay" @click.self="showRestorePreview = false">
      <div class="preview-modal">
        <div class="preview-header">
          <div>
            <h2>Review Restore Matches</h2>
            <p class="preview-subtitle" v-if="!previewLoading">
              <span class="stat-matched">{{ previewStats.matched }} matched</span>
              <span class="stat-sep">&middot;</span>
              <span class="stat-unmatched" v-if="previewStats.unmatched > 0">{{ previewStats.unmatched }} unmatched</span>
              <span class="stat-sep" v-if="previewStats.unmatched > 0">&middot;</span>
              <span>{{ previewStats.total }} total</span>
            </p>
          </div>
          <button class="btn-close" @click="showRestorePreview = false">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div v-if="previewLoading" class="preview-loading">
          <div class="spinner"></div>
          <p>Matching backup files to Plex library...</p>
        </div>

        <template v-else>
          <div class="preview-controls">
            <label class="select-all-control" @click.prevent="toggleSelectAll">
              <input type="checkbox" :checked="allMatchedSelected" @click.stop="toggleSelectAll" />
              <span>Select all matched ({{ matchedCount }})</span>
            </label>
            <span class="selected-count">{{ selectedCount }} selected</span>
          </div>

          <div class="preview-list">
            <div
              v-for="item in previewItems"
              :key="item.filename"
              class="preview-item"
              :class="{ unmatched: item.match_type === 'unmatched', selected: item.selected }"
            >
              <input
                type="checkbox"
                v-model="item.selected"
                :disabled="!item.rating_key"
                class="item-checkbox"
              />
              <img
                :src="thumbUrl(item.filename)"
                class="preview-thumb"
                loading="lazy"
                @error="($event.target as HTMLImageElement).style.display = 'none'"
              />
              <div class="preview-info">
                <div class="preview-filename">{{ item.filename }}</div>
                <div v-if="item.plex_title" class="preview-match-target">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="9 18 15 12 9 6"/>
                  </svg>
                  {{ item.plex_title }}
                </div>
                <div v-else class="preview-no-match">No match found</div>
              </div>
              <span class="match-badge" :class="item.match_type">
                {{ item.match_type === 'manifest' ? 'Exact' :
                   item.match_type === 'name_match' ? 'Name' :
                   item.match_type === 'manual' ? 'Manual' : 'No Match' }}
              </span>
              <button class="btn-assign" @click="openAssign(item)" :title="item.rating_key ? 'Change match' : 'Assign to Plex item'">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
            </div>
          </div>

          <div class="preview-footer">
            <button class="btn-cancel" @click="showRestorePreview = false">Cancel</button>
            <button class="btn-confirm" @click="executeRestore" :disabled="selectedCount === 0">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              Restore {{ selectedCount }} {{ selectedCount === 1 ? 'poster' : 'posters' }}
            </button>
          </div>
        </template>
      </div>
    </div>

    <!-- ═══ MANUAL ASSIGN MODAL ═══ -->
    <div v-if="assigningItem" class="modal-overlay assign-overlay" @click.self="assigningItem = null">
      <div class="assign-modal">
        <div class="assign-header">
          <h3>Assign to Plex Item</h3>
          <p class="assign-file">{{ assigningItem.filename }}</p>
          <button class="btn-close" @click="assigningItem = null">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="assign-search-wrap">
          <svg class="assign-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            v-model="assignSearch"
            class="assign-search"
            type="text"
            placeholder="Search library..."
            autofocus
          />
        </div>
        <div class="assign-list">
          <div v-if="libraryItemsLoading" class="assign-loading">
            <div class="spinner-sm"></div>
            Loading library items...
          </div>
          <div v-else-if="!libraryItemsLoaded" class="assign-loading">Loading...</div>
          <div v-else-if="filteredAssignItems.length === 0" class="assign-empty">No items match your search</div>
          <button
            v-for="li in filteredAssignItems"
            :key="li.rating_key"
            class="assign-item"
            :class="{ season: li.is_season }"
            @click="assignMatch(li)"
          >
            <span class="assign-item-title">{{ li.title }}</span>
            <span v-if="li.is_season" class="assign-item-badge">Season</span>
          </button>
        </div>
      </div>
    </div>

    <!-- ═══ CONFIRM DELETE DIALOG ═══ -->
    <div v-if="showConfirmDelete" class="modal-overlay" @click.self="showConfirmDelete = false">
      <div class="confirm-dialog">
        <h3>Delete Backup?</h3>
        <p>This will permanently delete all {{ backupCount }} backed-up poster files. This cannot be undone.</p>
        <div class="confirm-actions">
          <button class="btn-cancel" @click="showConfirmDelete = false">Cancel</button>
          <button class="btn-confirm danger" @click="deleteBackup">Delete</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backup-view {
  padding: 1.5rem;
  max-width: 960px;
}

/* ── Page header ── */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
}

.page-header h1 {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0 0 0.4rem 0;
  color: var(--text-primary, #fff);
  font-size: 2rem;
  font-weight: 700;
}

.page-header h1 svg { color: var(--accent, #3dd6b7); }

.page-subtitle {
  margin: 0;
  color: var(--text-secondary, #aaa);
  font-size: 0.95rem;
}

.btn-refresh {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.9rem;
  background: var(--surface, #1a1f2e);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  transition: border-color 0.2s;
}
.btn-refresh:hover:not(:disabled) { border-color: var(--accent, #3dd6b7); }
.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Two-column grid ── */
.sections-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
}

/* ── Section cards ── */
.section-card {
  background: var(--surface, #1a1f2e);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 12px;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.section-header svg { color: var(--accent, #3dd6b7); }

.section-header h2 {
  margin: 0;
  color: var(--text-primary, #fff);
  font-size: 1.15rem;
  font-weight: 600;
}

.section-desc {
  margin: 0;
  color: var(--text-secondary, #aaa);
  font-size: 0.88rem;
  line-height: 1.5;
}

/* ── Status block ── */
.status-block {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-primary, #fff);
  font-size: 0.92rem;
}

.status-row.muted { color: var(--text-secondary, #aaa); }
.status-row.small { font-size: 0.82rem; }

.icon-ok { color: var(--accent, #3dd6b7); flex-shrink: 0; }

/* ── Folder path ── */
.folder-path {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.6rem 0.8rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 6px;
}

.folder-path svg {
  flex-shrink: 0;
  color: var(--text-secondary, #666);
  margin-top: 1px;
}

.folder-path span {
  font-family: monospace;
  font-size: 0.78rem;
  color: var(--text-secondary, #aaa);
  word-break: break-all;
  line-height: 1.4;
}

/* ── Filename format guide ── */
.format-guide {
  padding: 0.75rem 0.9rem;
  background: rgba(61, 214, 183, 0.04);
  border: 1px solid rgba(61, 214, 183, 0.12);
  border-radius: 8px;
}

.format-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--accent, #3dd6b7);
  margin-bottom: 0.5rem;
}

.format-examples {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.format-examples code {
  display: block;
  font-size: 0.82rem;
  color: var(--text-primary, #fff);
  font-family: monospace;
}

.format-examples code.example {
  color: var(--text-secondary, #777);
  font-style: italic;
}

.format-note {
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: var(--text-secondary, #777);
}

/* ── Toggle ── */
.toggle-option {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  cursor: pointer;
  user-select: none;
}

.toggle-option input[type="checkbox"] { display: none; }

.toggle-slider {
  position: relative;
  width: 36px;
  height: 20px;
  background: var(--border, #2a2f3e);
  border-radius: 10px;
  transition: background 0.2s;
  flex-shrink: 0;
}

.toggle-slider::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  width: 14px;
  height: 14px;
  background: var(--text-secondary, #aaa);
  border-radius: 50%;
  transition: transform 0.2s, background 0.2s;
}

.toggle-option input:checked + .toggle-slider {
  background: var(--accent, #3dd6b7);
}

.toggle-option input:checked + .toggle-slider::after {
  transform: translateX(16px);
  background: #fff;
}

.toggle-text {
  color: var(--text-primary, #fff);
  font-size: 0.88rem;
}

/* ── Section action buttons ── */
.section-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: auto;
}

.btn-primary {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.6rem 1.1rem;
  background: linear-gradient(135deg, var(--accent, #3dd6b7), #2bc4a6);
  color: #000;
  border: none;
  border-radius: 7px;
  cursor: pointer;
  font-size: 0.88rem;
  font-weight: 500;
  transition: opacity 0.2s, transform 0.1s;
}

.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn-primary:active:not(:disabled) { transform: scale(0.97); }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-danger-outline {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.6rem 0.9rem;
  background: transparent;
  color: #f87171;
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: 7px;
  cursor: pointer;
  font-size: 0.85rem;
  transition: background 0.15s;
}

.btn-danger-outline:hover:not(:disabled) { background: rgba(248, 113, 113, 0.08); }
.btn-danger-outline:disabled { opacity: 0.4; cursor: not-allowed; }

/* ═══ MODALS ═══ */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(2px);
}

.assign-overlay { z-index: 1100; }

/* ── Preview modal ── */
.preview-modal {
  background: var(--surface, #1a1f2e);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 14px;
  width: 90%;
  max-width: 720px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 1.5rem 1.5rem 1rem;
  border-bottom: 1px solid var(--border, #2a2f3e);
}

.preview-header h2 {
  margin: 0 0 0.35rem 0;
  color: var(--text-primary, #fff);
  font-size: 1.2rem;
  font-weight: 600;
}

.preview-subtitle {
  margin: 0;
  font-size: 0.82rem;
  color: var(--text-secondary, #aaa);
  display: flex;
  align-items: center;
  gap: 0.45rem;
}

.stat-matched { color: var(--accent, #3dd6b7); font-weight: 500; }
.stat-unmatched { color: #f87171; font-weight: 500; }
.stat-sep { color: var(--text-secondary, #555); }

.btn-close {
  background: none;
  border: none;
  color: var(--text-secondary, #aaa);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: color 0.2s;
}
.btn-close:hover { color: var(--text-primary, #fff); }

.preview-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 3rem;
  color: var(--text-secondary, #aaa);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border, #2a2f3e);
  border-top-color: var(--accent, #3dd6b7);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.spinner-sm {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border, #2a2f3e);
  border-top-color: var(--accent, #3dd6b7);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.preview-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.65rem 1.5rem;
  border-bottom: 1px solid var(--border, #2a2f3e);
  background: rgba(255, 255, 255, 0.02);
}

.select-all-control {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  color: var(--text-primary, #fff);
  font-size: 0.82rem;
  user-select: none;
}

.select-all-control input {
  accent-color: var(--accent, #3dd6b7);
  width: 15px;
  height: 15px;
  cursor: pointer;
}

.selected-count {
  font-size: 0.82rem;
  color: var(--text-secondary, #aaa);
}

/* ── Preview list ── */
.preview-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.4rem 0;
}

.preview-item {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.5rem 1.5rem;
  transition: background 0.15s;
}

.preview-item:hover { background: rgba(255, 255, 255, 0.03); }
.preview-item.unmatched { opacity: 0.5; }
.preview-item.unmatched:hover { opacity: 0.8; }
.preview-item.selected:not(.unmatched) { background: rgba(61, 214, 183, 0.04); }

.item-checkbox {
  accent-color: var(--accent, #3dd6b7);
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  cursor: pointer;
}
.item-checkbox:disabled { cursor: not-allowed; opacity: 0.3; }

.preview-thumb {
  width: 34px;
  height: 50px;
  object-fit: cover;
  border-radius: 3px;
  background: var(--border, #2a2f3e);
  flex-shrink: 0;
}

.preview-info {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.preview-filename {
  font-size: 0.85rem;
  color: var(--text-primary, #fff);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

.preview-match-target {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.78rem;
  color: var(--accent, #3dd6b7);
  margin-top: 2px;
}
.preview-match-target svg { flex-shrink: 0; opacity: 0.6; }

.preview-no-match {
  font-size: 0.78rem;
  color: #f87171;
  margin-top: 2px;
}

.match-badge {
  flex-shrink: 0;
  padding: 2px 7px;
  border-radius: 10px;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.match-badge.manifest { background: rgba(61, 214, 183, 0.15); color: var(--accent, #3dd6b7); }
.match-badge.name_match { background: rgba(96, 165, 250, 0.15); color: #60a5fa; }
.match-badge.manual { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
.match-badge.unmatched { background: rgba(248, 113, 113, 0.15); color: #f87171; }

/* ── Assign button ── */
.btn-assign {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 5px;
  color: var(--text-secondary, #aaa);
  cursor: pointer;
  transition: all 0.15s;
  opacity: 0;
}

.preview-item:hover .btn-assign { opacity: 1; }
.preview-item.unmatched .btn-assign { opacity: 1; border-color: #f87171; color: #f87171; }
.btn-assign:hover { border-color: var(--accent, #3dd6b7); color: var(--accent, #3dd6b7); background: rgba(61, 214, 183, 0.08); }

/* ── Preview footer ── */
.preview-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border, #2a2f3e);
}

/* ── Assign modal ── */
.assign-modal {
  background: var(--surface, #1a1f2e);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 14px;
  width: 90%;
  max-width: 440px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.assign-header {
  position: relative;
  padding: 1.15rem 1.15rem 0.65rem;
  border-bottom: 1px solid var(--border, #2a2f3e);
}

.assign-header h3 {
  margin: 0 0 0.25rem 0;
  color: var(--text-primary, #fff);
  font-size: 1rem;
  font-weight: 600;
  padding-right: 2rem;
}

.assign-file {
  margin: 0;
  font-size: 0.78rem;
  color: var(--text-secondary, #aaa);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.assign-header .btn-close {
  position: absolute;
  top: 0.9rem;
  right: 0.9rem;
}

.assign-search-wrap {
  position: relative;
  padding: 0.65rem 1.15rem;
  border-bottom: 1px solid var(--border, #2a2f3e);
}

.assign-search-icon {
  position: absolute;
  left: 1.75rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-secondary, #555);
  pointer-events: none;
}

.assign-search {
  width: 100%;
  padding: 0.5rem 0.7rem 0.5rem 1.9rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 6px;
  color: var(--text-primary, #fff);
  font-size: 0.88rem;
  outline: none;
  transition: border-color 0.2s;
}
.assign-search:focus { border-color: var(--accent, #3dd6b7); }
.assign-search::placeholder { color: var(--text-secondary, #555); }

.assign-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.2rem 0;
}

.assign-loading,
.assign-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  padding: 2rem;
  text-align: center;
  color: var(--text-secondary, #aaa);
  font-size: 0.88rem;
}

.assign-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.5rem 1.15rem;
  background: transparent;
  border: none;
  color: var(--text-primary, #fff);
  font-size: 0.85rem;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}

.assign-item:hover { background: rgba(61, 214, 183, 0.08); }
.assign-item.season { padding-left: 1.9rem; }

.assign-item-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.assign-item-badge {
  flex-shrink: 0;
  font-size: 0.6rem;
  text-transform: uppercase;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(96, 165, 250, 0.15);
  color: #60a5fa;
  letter-spacing: 0.03em;
}

/* ── Confirm dialog ── */
.confirm-dialog {
  background: var(--surface, #1a1f2e);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 12px;
  padding: 1.75rem;
  max-width: 400px;
  width: 90%;
}

.confirm-dialog h3 {
  margin: 0 0 0.8rem 0;
  color: var(--text-primary, #fff);
  font-size: 1.1rem;
}

.confirm-dialog p {
  margin: 0 0 1.25rem 0;
  color: var(--text-secondary, #aaa);
  line-height: 1.5;
  font-size: 0.9rem;
}

.confirm-actions {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
}

.btn-cancel {
  padding: 0.55rem 1.1rem;
  background: transparent;
  color: var(--text-secondary, #aaa);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.88rem;
}
.btn-cancel:hover { border-color: var(--text-secondary, #aaa); }

.btn-confirm {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.55rem 1.1rem;
  background: linear-gradient(135deg, var(--accent, #3dd6b7), #2bc4a6);
  color: #000;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.88rem;
  font-weight: 500;
}
.btn-confirm:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-confirm.danger {
  background: linear-gradient(135deg, #f87171, #ef4444);
  color: #fff;
}

/* ── Mobile ── */
@media (max-width: 768px) {
  .backup-view { padding: 1rem; }

  .page-header { flex-direction: column; gap: 0.75rem; }
  .page-header h1 { font-size: 1.5rem; }

  .sections-grid {
    grid-template-columns: 1fr;
  }

  .preview-modal { width: 96%; max-height: 90vh; }
  .preview-item { padding: 0.5rem 1rem; }
  .preview-thumb { width: 28px; height: 42px; }
  .btn-assign { opacity: 1; }

  .assign-modal { width: 96%; max-height: 80vh; }
}
</style>
