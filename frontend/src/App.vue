<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Sidebar, { type MenuItem } from './components/layout/Sidebar.vue'
import TopNav from './components/layout/TopNav.vue'
import EditorPane from './components/editor/EditorPane.vue'
import TvShowEditorPane from './components/editor/TvShowEditorPane.vue'
import NotificationContainer from './components/NotificationContainer.vue'
import UpdateAnnouncementModal from './components/UpdateAnnouncementModal.vue'
import ChangelogModal from './components/ChangelogModal.vue'
import { useUiStore, type TabKey } from './stores/ui'
import { useMovies } from './composables/useMovies'
import { useTvShows } from './composables/useTvShows'
import { useSettingsStore } from './stores/settings'
import { useScanStore } from './stores/scan'
import { useOperationStatus } from './stores/operationStatus'
import { getApiBase } from '@/services/apiBase'

const tabs = computed<MenuItem[]>(() => {
  // Check if Plex is configured
  const plexConfigured = !!(settings.plex.value.url && settings.plex.value.token)

  // If Plex not configured, only show Settings
  if (!plexConfigured) {
    return [
      { key: 'settings', label: 'Settings' }
    ]
  }

  const libs = settings.plex.value.libraryMappings && settings.plex.value.libraryMappings.length
    ? settings.plex.value.libraryMappings
    : [{ id: settings.plex.value.movieLibraryName || 'default', displayName: 'Movies', title: 'Movies' }]

  const movieTabs: MenuItem[] = libs.map((lib, idx) => ({
    key: `movies-${lib.id || idx}`,
    label: lib.displayName || lib.title || `Library ${idx + 1}`,
    submenu: [
      { key: `batch-${lib.id || idx}`, label: 'Batch Edit' },
      { key: `collections-${lib.id || idx}`, label: 'Collections' },
      { key: `assets-${lib.id || idx}`, label: 'Local Assets' },
      { key: `backup-${lib.id || idx}`, label: 'Backup / Restore' }
    ]
  }))

  const tvLibs = settings.plex.value.tvShowLibraryMappings && settings.plex.value.tvShowLibraryMappings.length
    ? settings.plex.value.tvShowLibraryMappings
    : []

  const tvShowTabs: MenuItem[] = tvLibs.length > 0 ? tvLibs.map((lib, idx) => ({
    key: `tv-shows-${lib.id || idx}`,
    label: lib.displayName || lib.title || `TV Library ${idx + 1}`,
    submenu: [
      { key: `tv-batch-${lib.id || idx}`, label: 'Batch Edit' },
      { key: `tv-assets-${lib.id || idx}`, label: 'Local Assets' },
      { key: `tv-backup-${lib.id || idx}`, label: 'Backup / Restore' }
    ]
  })) : []

  return [
    ...movieTabs,
    ...tvShowTabs,
    { key: 'template-manager', label: 'Template Manager' },
    { key: 'overlay-config-manager', label: 'Overlay Config' },
    { key: 'history', label: 'History' },
    { key: 'settings', label: 'Settings' },
    { key: 'logs', label: 'Logs' }
  ]
})

const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const searchQuery = ref('')
const sidebarOpen = ref(false)
const showChangelog = ref(false)

const toggleSidebar = () => {
  sidebarOpen.value = !sidebarOpen.value
}

const closeSidebar = () => {
  sidebarOpen.value = false
}
const { movies, hydratePostersFromSession } = useMovies()
const { tvShows } = useTvShows()
const settings = useSettingsStore()
const scan = useScanStore()
const operationStatus = useOperationStatus()
let scanPoller: number | null = null
let batchPoller: number | null = null
let backupPoller: number | null = null

// State for all-libraries search
const allLibrariesMovies = ref<{ libraryName: string; mediaType: string; movies: any[] }[]>([])
const allLibrariesTvShows = ref<{ libraryName: string; mediaType: string; shows: any[] }[]>([])
const allLibrariesLoaded = ref(false)

// Fetch all movies and TV shows from all libraries for search
const fetchAllLibrariesContent = async () => {
  const apiBase = getApiBase()
  
  // Get or initialize poster cache from sessionStorage
  let posterCache: Record<string, string | null> = {}
  if (typeof sessionStorage !== 'undefined') {
    try {
      const cached = sessionStorage.getItem('simposter-poster-cache')
      if (cached) {
        posterCache = JSON.parse(cached)
      }
    } catch {
      /* ignore */
    }
  }
  
  // Fetch movies
  try {
    const res = await fetch(`${apiBase}/api/movies`)
    if (res.ok) {
      const allMovies = await res.json()

      // Cache poster URLs
      for (const movie of allMovies) {
        if (movie.key && movie.poster) {
          posterCache[movie.key] = movie.poster
        }
      }

      const movieLibs = settings.plex.value.libraryMappings && settings.plex.value.libraryMappings.length
        ? settings.plex.value.libraryMappings
        : [{ id: settings.plex.value.movieLibraryName || 'default', displayName: 'Movies', title: 'Movies' }]

      // Group movies by library_id
      const grouped = new Map<string, any[]>()
      for (const movie of allMovies) {
        const libId = movie.library_id || 'default'
        if (!grouped.has(libId)) {
          grouped.set(libId, [])
        }
        grouped.get(libId)!.push(movie)
      }

      // Convert to sorted array
      const groups: { libraryName: string; mediaType: string; movies: any[] }[] = []
      for (const lib of movieLibs) {
        const libId = lib.id || 'default'
        const movies = grouped.get(libId) || []
        if (movies.length > 0) {
          groups.push({
            libraryName: lib.displayName || lib.title || 'Movies',
            mediaType: 'movie',
            movies
          })
        }
      }

      allLibrariesMovies.value = groups
    }
  } catch {
    /* ignore */
  }

  // Fetch TV shows
  try {
    const res = await fetch(`${apiBase}/api/tv-shows`)
    if (res.ok) {
      const allShows = await res.json()

      // Cache poster URLs
      for (const show of allShows) {
        if (show.key && show.poster) {
          posterCache[show.key] = show.poster
        }
      }

      const tvLibs = settings.plex.value.tvShowLibraryMappings && settings.plex.value.tvShowLibraryMappings.length
        ? settings.plex.value.tvShowLibraryMappings
        : []

      if (tvLibs.length > 0) {
        // Group shows by library_id
        const grouped = new Map<string, any[]>()
        for (const show of allShows) {
          const libId = show.library_id || 'default'
          if (!grouped.has(libId)) {
            grouped.set(libId, [])
          }
          grouped.get(libId)!.push(show)
        }

        // Convert to sorted array
        const groups: { libraryName: string; mediaType: string; shows: any[] }[] = []
        for (const lib of tvLibs) {
          const libId = lib.id || 'default'
          const shows = grouped.get(libId) || []
          if (shows.length > 0) {
            groups.push({
              libraryName: lib.displayName || lib.title || 'TV Shows',
              mediaType: 'tv-show',
              shows
            })
          }
        }

        allLibrariesTvShows.value = groups
      }
    }
  } catch {
    /* ignore */
  }

  // Save poster cache to sessionStorage
  if (typeof sessionStorage !== 'undefined') {
    try {
      sessionStorage.setItem('simposter-poster-cache', JSON.stringify(posterCache))
    } catch {
      /* ignore */
    }
  }

  allLibrariesLoaded.value = true
}

// Grouped content for search - use fetched data when available, fallback to sessionStorage
const groupedContentForSearch = computed(() => {
  const groups: (
    | { libraryName: string; mediaType: string; movies: any[] }
    | { libraryName: string; mediaType: string; shows: any[] }
  )[] = []

  // Add movies if loaded
  if (allLibrariesLoaded.value && (allLibrariesMovies.value.length > 0 || allLibrariesTvShows.value.length > 0)) {
    groups.push(...allLibrariesMovies.value)
    groups.push(...allLibrariesTvShows.value)
    return groups
  }

  // Fallback to sessionStorage
  const movieLibs = settings.plex.value.libraryMappings && settings.plex.value.libraryMappings.length
    ? settings.plex.value.libraryMappings
    : [{ id: settings.plex.value.movieLibraryName || 'default', displayName: 'Movies', title: 'Movies' }]

  const tvLibs = settings.plex.value.tvShowLibraryMappings && settings.plex.value.tvShowLibraryMappings.length
    ? settings.plex.value.tvShowLibraryMappings
    : []

  if (typeof sessionStorage !== 'undefined') {
    // Movies from sessionStorage
    for (const lib of movieLibs) {
      const libId = lib.id || 'default'
      const libName = lib.displayName || lib.title || 'Movies'
      const cacheKey = `simposter-movies-cache-${libId}`
      try {
        const raw = sessionStorage.getItem(cacheKey)
        if (raw) {
          const libMovies = JSON.parse(raw)
          if (Array.isArray(libMovies) && libMovies.length > 0) {
            groups.push({
              libraryName: libName,
              mediaType: 'movie',
              movies: libMovies
            })
          }
        }
      } catch {
        /* ignore */
      }
    }

    // TV shows from sessionStorage
    for (const lib of tvLibs) {
      const libId = lib.id || 'default'
      const libName = lib.displayName || lib.title || 'TV Shows'
      const cacheKey = `simposter-tv-shows-cache-${libId}`
      try {
        const raw = sessionStorage.getItem(cacheKey)
        if (raw) {
          const libShows = JSON.parse(raw)
          if (Array.isArray(libShows) && libShows.length > 0) {
            groups.push({
              libraryName: libName,
              mediaType: 'tv-show',
              shows: libShows
            })
          }
        }
      } catch {
        /* ignore */
      }
    }
  }

  return groups
})

const activeTab = computed<TabKey>(() => {
  const libQuery = (route.query.library as string) || ''
  if (route.name === 'backup' && (route.query.type as string) === 'tv-show') {
    if (libQuery) return `tv-shows-${libQuery}`
    const firstTvLib = settings.plex.value.tvShowLibraryMappings && settings.plex.value.tvShowLibraryMappings[0]
    return `tv-shows-${firstTvLib?.id || 'default'}`
  }
  if (route.name === 'batch-edit' || route.name === 'local-assets' || route.name === 'movies' || route.name === 'collections' || route.name === 'backup') {
    if (libQuery) return `movies-${libQuery}`
    // fallback to first lib key
    const firstLib = settings.plex.value.libraryMappings && settings.plex.value.libraryMappings[0]
    return `movies-${firstLib?.id || 'default'}`
  }
  if (route.name === 'tv-shows' || route.name === 'tv-batch-edit' || route.name === 'tv-local-assets') {
    if (libQuery) return `tv-shows-${libQuery}`
    // fallback to first TV lib key
    const firstTvLib = settings.plex.value.tvShowLibraryMappings && settings.plex.value.tvShowLibraryMappings[0]
    return `tv-shows-${firstTvLib?.id || 'default'}`
  }
  return (route.name as TabKey) || 'movies'
})

const activeSubmenu = computed<string>(() => {
  const libQuery = (route.query.library as string) || ''
  if (route.name === 'batch-edit') return `batch-${libQuery || 'default'}`
  if (route.name === 'tv-batch-edit') return `tv-batch-${libQuery || 'default'}`
  if (route.name === 'collections') return `collections-${libQuery || 'default'}`
  if (route.name === 'local-assets') return `assets-${libQuery || 'default'}`
  if (route.name === 'tv-local-assets') return `tv-assets-${libQuery || 'default'}`
  if (route.name === 'backup') {
    const type = route.query.type as string
    return type === 'tv-show' ? `tv-backup-${libQuery || 'default'}` : `backup-${libQuery || 'default'}`
  }
  return ''
})
const showBackButton = computed(() => !!ui.selectedMovie.value)

const handleSelect = (movie: { key: string; title: string; year?: number | string; poster?: string | null; tmdb_id?: string | number; tvdb_id?: string | number }) => {
  // Guard against native DOM events being passed instead of movie objects
  if (!movie || typeof movie !== 'object' || !movie.key || !movie.title) {
    return
  }
  // Detect media type based on current route
  const mediaType = route.name === 'tv-shows' ? 'tv-show' : 'movie'
  ui.setSelectedMovie({ ...movie, mediaType })

  // Update URL with edit mode and library info
  const currentLibrary = route.query.library as string | undefined
  const itemId = mediaType === 'tv-show' ? (movie.tvdb_id || movie.key) : (movie.tmdb_id || movie.key)
  const newQuery: Record<string, string> = {
    edit: String(itemId)
  }
  if (currentLibrary) {
    newQuery.library = currentLibrary
  }

  router.replace({ query: newQuery })
}

const handleTabSelect = (tab: TabKey) => {
  // Always close editor if open
  if (ui.selectedMovie.value) {
    ui.setSelectedMovie(null)
  }
  if (tab.startsWith('movies-')) {
    const libId = tab.replace('movies-', '')
    router.push({ name: 'movies', query: { library: libId } })
  } else if (tab.startsWith('tv-shows-')) {
    const libId = tab.replace('tv-shows-', '')
    router.push({ name: 'tv-shows', query: { library: libId } })
  } else {
    router.push({ name: tab })
  }
}

const handleBack = () => {
  ui.setSelectedMovie(null)

  // Remove edit parameter from URL, keep other query params
  const { edit, ...remainingQuery } = route.query
  router.replace({ query: remainingQuery })
}

onMounted(async () => {
  const applyTheme = (theme: string) => {
    document.documentElement.dataset.theme = theme
  }
  applyTheme(settings.theme.value)
  watch(
    () => settings.theme.value,
    (t) => applyTheme(t)
  )

  // Wait for settings to load before checking Plex configuration
  if (!settings.loaded.value) {
    await settings.load()
  }

  // Check if Plex is configured
  const plexConfigured = !!(settings.plex.value.url && settings.plex.value.token)
  if (!plexConfigured && route.path !== '/settings') {
    // Redirect to settings if Plex not configured
    router.push('/settings')
  }

  hydratePostersFromSession()
  fetchAllLibrariesContent()
  scan.checking.value = true
  fetchScanStatus().then((running) => {
    if (running) startScanPolling()
    else scan.checking.value = false
  })
  // Check if batch operation is running
  fetchBatchStatus().then((running) => {
    if (running) startBatchPolling()
  })
  // Check if backup operation is running
  fetchBackupStatus().then((running) => {
    if (running) startBackupPolling()
  })

  // Restore edit state from URL if present
  if (route.query.edit) {
    // We need to wait for content to load before we can find the item
    // This will be handled by a watcher below
  }
})

// Watch for URL edit parameter changes (browser back/forward)
watch(() => route.query.edit, (editId) => {
  if (editId && !ui.selectedMovie.value) {
    // User navigated to an edit URL, find the item and open editor
    const mediaType = route.name === 'tv-shows' ? 'tv-show' : 'movie'
    const allItems = mediaType === 'tv-show' ? tvShows.value : movies.value

    // Try to find by tmdb_id/tvdb_id first, fall back to key
    const item = allItems.find((m: any) => {
      const itemId = mediaType === 'tv-show' ? (m.tvdb_id || m.key) : (m.tmdb_id || m.key)
      return String(itemId) === String(editId)
    })

    if (item) {
      ui.setSelectedMovie({ ...item, mediaType })
    }
  } else if (!editId && ui.selectedMovie.value) {
    // Edit parameter removed, close editor
    ui.setSelectedMovie(null)
  }
})

onUnmounted(() => {
  stopScanPolling()
  stopBatchPolling()
  stopBackupPolling()
})

const fetchScanStatus = async () => {
  const apiBase = getApiBase()
  try {
    const res = await fetch(`${apiBase}/api/scan-progress`)
    if (!res.ok) return false
    const data = await res.json()
    if (scan.applyStatus) scan.applyStatus(data)
    else scan.checking.value = false
    return data.state === 'running'
  } catch {
    scan.checking.value = false
    return false
  }
}

const startScanPolling = () => {
  stopScanPolling()
  const apiBase = getApiBase()
  scanPoller = window.setInterval(async () => {
    try {
      const res = await fetch(`${apiBase}/api/scan-progress`)
      if (!res.ok) return
      const data = await res.json()
      if (scan.applyStatus) scan.applyStatus(data)
      if (data.state && data.state !== 'running') {
        stopScanPolling()
      }
    } catch {
      /* ignore */
    }
  }, 3000)
}

const stopScanPolling = () => {
  if (scanPoller !== null) {
    clearInterval(scanPoller)
    scanPoller = null
  }
}

// Batch progress polling
const fetchBatchStatus = async () => {
  const apiBase = getApiBase()
  try {
    const res = await fetch(`${apiBase}/api/batch-progress`)
    if (!res.ok) return false
    const data = await res.json()
    operationStatus.applyStatus(data, 'batch')
    return data.state === 'running'
  } catch {
    return false
  }
}

const startBatchPolling = () => {
  stopBatchPolling()
  const apiBase = getApiBase()
  const startedAt = Date.now()
  const GRACE_PERIOD = 3000 // 3s grace period for backend to receive request and set state to "running"

  const pollOnce = async () => {
    try {
      const res = await fetch(`${apiBase}/api/batch-progress`)
      if (!res.ok) return
      const data = await res.json()
      const inGracePeriod = Date.now() - startedAt < GRACE_PERIOD

      if (data.state === 'running') {
        // Batch is running — show progress immediately
        operationStatus.applyStatus(data, 'batch')
      } else if (!inGracePeriod) {
        // Grace period elapsed — batch is truly done (or never started), apply final state and stop
        operationStatus.applyStatus(data, 'batch')
        stopBatchPolling()
      }
      // During grace period with non-running state: skip — old "done" from previous batch
    } catch {
      /* ignore */
    }
  }

  // Delay first poll slightly so the batch request reaches the backend first
  setTimeout(pollOnce, 300)

  batchPoller = window.setInterval(pollOnce, 200)
}

const stopBatchPolling = () => {
  if (batchPoller !== null) {
    clearInterval(batchPoller)
    batchPoller = null
  }
}

// Export for use by BatchEditModal
;(window as any).startBatchPolling = startBatchPolling

// --- Backup progress polling (same pattern as batch) ---
const fetchBackupStatus = async () => {
  const apiBase = getApiBase()
  try {
    const res = await fetch(`${apiBase}/api/backup/progress`)
    if (!res.ok) return false
    const data = await res.json()
    operationStatus.applyStatus(data, 'backup')
    return data.state === 'running'
  } catch {
    return false
  }
}

const startBackupPolling = () => {
  stopBackupPolling()
  const apiBase = getApiBase()
  const startedAt = Date.now()
  const GRACE_PERIOD = 3000

  const pollOnce = async () => {
    try {
      const res = await fetch(`${apiBase}/api/backup/progress`)
      if (!res.ok) return
      const data = await res.json()
      const inGracePeriod = Date.now() - startedAt < GRACE_PERIOD

      if (data.state === 'running') {
        operationStatus.applyStatus(data, 'backup')
      } else if (!inGracePeriod) {
        operationStatus.applyStatus(data, 'backup')
        stopBackupPolling()
      }
    } catch {
      /* ignore */
    }
  }

  setTimeout(pollOnce, 300)
  backupPoller = window.setInterval(pollOnce, 500)
}

const stopBackupPolling = () => {
  if (backupPoller !== null) {
    clearInterval(backupPoller)
    backupPoller = null
  }
}

;(window as any).startBackupPolling = startBackupPolling

const handleSearchSelect = (item: { key: string; title: string; year?: number | string; poster?: string | null; mediaType?: 'movie' | 'tv-show' }) => {
  const mediaType = item.mediaType || 'movie'
  if (mediaType === 'tv-show') {
    router.push({ name: 'tv-shows' })
  } else {
    router.push({ name: 'movies' })
  }
  ui.setSelectedMovie({ ...item, mediaType })
}

const handleSubmenuClick = (parentKey: TabKey, submenuKey: string) => {
  // Always close editor if open
  if (ui.selectedMovie.value) {
    ui.setSelectedMovie(null)
  }

  if (parentKey.startsWith('movies-')) {
    const libId = parentKey.replace('movies-', '')
    if (submenuKey.startsWith('batch-')) {
      router.push({ name: 'batch-edit', query: { library: libId } })
    } else if (submenuKey.startsWith('collections-')) {
      router.push({ name: 'collections', query: { library: libId } })
    } else if (submenuKey.startsWith('assets-')) {
      router.push({ name: 'local-assets', query: { library: libId } })
    } else if (submenuKey.startsWith('backup-')) {
      router.push({ name: 'backup', query: { library: libId, type: 'movie' } })
    }
  } else if (parentKey.startsWith('tv-shows-')) {
    const libId = parentKey.replace('tv-shows-', '')
    if (submenuKey.startsWith('tv-batch-')) {
      router.push({ name: 'tv-batch-edit', query: { library: libId } })
    } else if (submenuKey.startsWith('tv-assets-')) {
      router.push({ name: 'tv-local-assets', query: { library: libId } })
    } else if (submenuKey.startsWith('tv-backup-')) {
      router.push({ name: 'backup', query: { library: libId, type: 'tv-show' } })
    }
  }
}
</script>

<template>
  <div class="shell">
    <NotificationContainer />
    <UpdateAnnouncementModal />

    <!-- Mobile sidebar overlay -->
    <div v-if="sidebarOpen" class="sidebar-overlay" @click="closeSidebar"></div>

    <ChangelogModal :visible="showChangelog" @close="showChangelog = false" />

    <TopNav
      :search="searchQuery"
      :show-back="showBackButton"
      :movies="groupedContentForSearch.length > 0 ? groupedContentForSearch : movies"
      @update:search="searchQuery = $event"
      @back="handleBack"
      @select-movie="handleSearchSelect"
      @show-changelog="showChangelog = true"
    >
      <template #menu-toggle>
        <button class="hamburger-btn" @click="toggleSidebar" aria-label="Toggle menu">
          <svg v-if="!sidebarOpen" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
          <svg v-else width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </template>
    </TopNav>
    <!-- Legacy scan overlay (for backwards compatibility) -->
    <div v-if="scan.visible.value" class="global-scan-overlay glass">
      <div v-if="scan.running.value" class="spinner"></div>
      <div v-else class="checkmark">✓</div>
      <div class="scan-body">
        <p class="title">{{ scan.running.value ? 'Rescanning library...' : 'Completed library scan!' }}</p>
        <p v-if="scan.current.value" class="current">Now: {{ scan.current.value }}</p>
        <div v-if="scan.progress.value.total" class="progress-row">
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: Math.min(100, Math.round((scan.progress.value.processed / scan.progress.value.total) * 100)) + '%' }"
            ></div>
          </div>
          <span class="progress-text">{{ scan.progress.value.processed }} / {{ scan.progress.value.total }}</span>
        </div>
        <ul class="scan-list">
          <li v-for="line in scan.log.value" :key="line">{{ line }}</li>
        </ul>
      </div>
    </div>

    <!-- New unified operation status overlay -->
    <div v-if="operationStatus.visible.value" class="global-operation-overlay glass">
      <div v-if="operationStatus.state.value === 'running'" class="spinner"></div>
      <div v-else-if="operationStatus.state.value === 'done'" class="checkmark">✓</div>
      <div v-else-if="operationStatus.state.value === 'error'" class="error-icon">✕</div>

      <div class="operation-body">
        <p class="title">
          <span v-if="operationStatus.type.value === 'scan'">
            {{ operationStatus.state.value === 'running' ? 'Rescanning library...' : 'Completed library scan!' }}
          </span>
          <span v-else-if="operationStatus.type.value === 'batch'">
            {{ operationStatus.state.value === 'running' ? 'Processing batch...' :
               operationStatus.state.value === 'error' ? 'Batch failed!' : 'Batch complete!' }}
          </span>
          <span v-else-if="operationStatus.type.value === 'backup'">
            {{ operationStatus.state.value === 'running' ? 'Backup / Restore in progress...' :
               operationStatus.state.value === 'error' ? 'Backup / Restore failed!' : 'Backup / Restore complete!' }}
          </span>
        </p>

        <!-- Combined status line for batch/backup operations -->
        <p v-if="(operationStatus.type.value === 'batch' || operationStatus.type.value === 'backup') && operationStatus.state.value === 'running'" class="batch-status">
          <span class="batch-count">{{ operationStatus.progress.value.processed + 1 }}/{{ operationStatus.progress.value.total }}</span>
          <span v-if="operationStatus.currentStep.value" class="batch-step">{{ operationStatus.currentStep.value }}</span>
          <span v-if="operationStatus.currentMovie.value" class="batch-movie">{{ operationStatus.currentMovie.value }}</span>
        </p>

        <!-- For scan, show simpler format -->
        <template v-else>
          <p v-if="operationStatus.currentMovie.value" class="current">
            {{ operationStatus.currentMovie.value }}
          </p>
          <p v-if="operationStatus.currentStep.value" class="step">
            {{ operationStatus.currentStep.value }}
          </p>
        </template>

        <div v-if="operationStatus.progress.value.total" class="progress-row">
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: Math.min(100, Math.round((operationStatus.progress.value.processed / operationStatus.progress.value.total) * 100)) + '%' }"
            ></div>
          </div>
          <span class="progress-text">{{ operationStatus.progress.value.processed }} / {{ operationStatus.progress.value.total }}</span>
        </div>

        <p v-if="operationStatus.error.value" class="error-text">{{ operationStatus.error.value }}</p>
      </div>
    </div>

    <!-- Normal workspace (movies/settings/logs) -->
    <div v-if="!ui.selectedMovie.value" class="workspace">
      <Sidebar :tabs="tabs" :active="activeTab" :active-submenu="activeSubmenu" :mobile-open="sidebarOpen" @select="(tab) => { handleTabSelect(tab); closeSidebar() }" @submenu-click="(parentKey, submenuKey) => { handleSubmenuClick(parentKey, submenuKey); closeSidebar() }" />
      <section class="main-pane glass">
        <router-view :key="activeTab" :search="searchQuery" @select="handleSelect" />
      </section>
    </div>

    <!-- Inline editor when a movie is selected -->
    <div v-else class="workspace">
      <Sidebar :tabs="tabs" :active="activeTab" :active-submenu="activeSubmenu" :mobile-open="sidebarOpen" @select="(tab) => { handleTabSelect(tab); closeSidebar() }" @submenu-click="(parentKey, submenuKey) => { handleSubmenuClick(parentKey, submenuKey); closeSidebar() }" />
      <section class="main-pane glass">
        <TvShowEditorPane
          v-if="ui.selectedMovie.value.mediaType === 'tv-show'"
          :movie="ui.selectedMovie.value"
          @close="ui.setSelectedMovie(null)"
        />
        <EditorPane
          v-else
          :movie="ui.selectedMovie.value"
          @close="ui.setSelectedMovie(null)"
        />
      </section>
    </div>
  </div>
</template>


<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: calc(100vh - 24px);
}

.workspace {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 14px;
  flex: 1;
  align-items: stretch;
}

.main-pane {
  padding: 16px;
  background: rgba(14, 16, 24, 0.75);
  height: 100%;
  overflow-y: auto;
}

.global-scan-overlay {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 3000;
  display: flex;
  gap: 10px;
  padding: 12px 14px;
  background: rgba(0, 0, 0, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #eef2ff;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  max-width: 360px;
}

.global-scan-overlay .spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: var(--accent, #3dd6b7);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
  flex-shrink: 0;
}

.global-scan-overlay .checkmark {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent, #3dd6b7);
  color: #0b0d14;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12px;
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.global-scan-overlay .scan-body {
  flex: 1;
}

.global-scan-overlay .title {
  margin: 0 0 4px 0;
  font-weight: 600;
}

.global-scan-overlay .current {
  margin: 0 0 6px 0;
  font-size: 13px;
  color: #dbe4ff;
}

.global-scan-overlay .progress-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0 8px;
}

.global-scan-overlay .progress-bar {
  flex: 1;
  height: 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.global-scan-overlay .progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3dd6b7, #5b8dee);
  border-radius: 4px;
  transition: width 0.2s ease;
}

.global-scan-overlay .progress-text {
  font-size: 12px;
  color: #dbe4ff;
  min-width: 80px;
  text-align: right;
}

.global-scan-overlay .scan-list {
  margin: 0;
  padding-left: 18px;
  max-height: 140px;
  overflow-y: auto;
  font-size: 13px;
}

/* New unified operation overlay styles */
.global-operation-overlay {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 3000;
  display: flex;
  gap: 10px;
  padding: 12px 14px;
  background: rgba(0, 0, 0, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #eef2ff;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  max-width: 400px;
}

.global-operation-overlay .spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: var(--accent, #3dd6b7);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
  flex-shrink: 0;
}

.global-operation-overlay .checkmark {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent, #3dd6b7);
  color: #0b0d14;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12px;
  flex-shrink: 0;
}

.global-operation-overlay .error-icon {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #ff6b6b;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12px;
  flex-shrink: 0;
}

.global-operation-overlay .operation-body {
  flex: 1;
  min-width: 0;
}

.global-operation-overlay .title {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
}

.global-operation-overlay .current {
  margin: 0 0 2px 0;
  font-size: 13px;
  color: #dbe4ff;
  font-weight: 500;
}

.global-operation-overlay .step {
  margin: 0 0 6px 0;
  font-size: 12px;
  color: var(--accent, #3dd6b7);
  font-style: italic;
}

.global-operation-overlay .batch-status {
  margin: 0 0 6px 0;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.global-operation-overlay .batch-count {
  font-weight: 600;
  color: var(--accent, #3dd6b7);
}

.global-operation-overlay .batch-step {
  font-style: italic;
  color: #a8b3cf;
}

.global-operation-overlay .batch-movie {
  font-weight: 500;
  color: #dbe4ff;
}

.global-operation-overlay .progress-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0 8px;
}

.global-operation-overlay .progress-bar {
  flex: 1;
  height: 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.global-operation-overlay .progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3dd6b7, #5b8dee);
  border-radius: 4px;
  transition: width 0.2s ease;
}

.global-operation-overlay .progress-text {
  font-size: 12px;
  color: #dbe4ff;
  min-width: 80px;
  text-align: right;
}

.global-operation-overlay .error-text {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: #ff6b6b;
  font-weight: 500;
}

/* Mobile hamburger button */
.hamburger-btn {
  display: none;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.hamburger-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(61, 214, 183, 0.4);
}

/* Mobile sidebar overlay */
.sidebar-overlay {
  display: none;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 99;
  backdrop-filter: blur(2px);
}

/* Tablet breakpoint - sidebar collapses to hamburger */
@media (max-width: 900px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .hamburger-btn {
    display: flex;
  }

  .sidebar-overlay {
    display: block;
  }

  .main-pane {
    padding: 12px;
  }

  .global-scan-overlay,
  .global-operation-overlay {
    left: 16px;
    right: 16px;
    max-width: none;
    width: auto;
  }
}

/* Mobile breakpoint - smaller adjustments */
@media (max-width: 600px) {
  .shell {
    gap: 8px;
    min-height: calc(100vh - 16px);
  }

  .workspace {
    gap: 8px;
  }

  .main-pane {
    padding: 10px;
    border-radius: 10px;
  }

  .global-scan-overlay,
  .global-operation-overlay {
    top: auto;
    bottom: 16px;
    left: 12px;
    right: 12px;
    padding: 8px 10px;
    font-size: 12px;
    gap: 8px;
    border-radius: 8px;
  }

  .global-scan-overlay .spinner,
  .global-scan-overlay .checkmark,
  .global-operation-overlay .spinner,
  .global-operation-overlay .checkmark,
  .global-operation-overlay .error-icon {
    width: 16px;
    height: 16px;
    font-size: 10px;
  }

  .global-scan-overlay .title,
  .global-operation-overlay .title {
    font-size: 12px;
    margin-bottom: 2px;
  }

  .global-scan-overlay .current,
  .global-operation-overlay .current,
  .global-operation-overlay .step {
    font-size: 11px;
    margin-bottom: 4px;
  }

  .global-scan-overlay .progress-row,
  .global-operation-overlay .progress-row {
    margin: 4px 0;
  }

  .global-scan-overlay .progress-bar,
  .global-operation-overlay .progress-bar {
    height: 4px;
  }

  .global-scan-overlay .progress-text,
  .global-operation-overlay .progress-text {
    min-width: 50px;
    font-size: 10px;
  }

  .global-operation-overlay .batch-status {
    font-size: 11px;
    gap: 4px;
  }

  .global-scan-overlay .scan-list {
    display: none;
  }
}
</style>
