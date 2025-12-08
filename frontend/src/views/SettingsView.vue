<script setup lang="ts">
import { useSettingsStore, type Theme } from '../stores/settings'
import { APP_VERSION } from '@/version'
import { useMovies } from '../composables/useMovies'
import { ref, onMounted, watch, computed } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useScanStore } from '@/stores/scan'

const settings = useSettingsStore()
const saved = ref('')
const allLabels = ref<Record<string, string[]>>({})
const { movies: moviesCache, moviesLoaded } = useMovies()
const scan = useScanStore()

// Cooldown state to prevent rapid clicking
const scanCooldown = ref(false)

// Computed property to ensure button disable state is reactive
const isScanInProgress = computed(() => scan.running.value || scan.checking.value || scanCooldown.value)

// Local state that will only be applied when save is clicked
const localTheme = ref<Theme>('neon')
const localPosterDensity = ref(20)
const localSaveLocation = ref('')
const localSaveBatch = ref(false)
const localDefaultLabelsToRemove = ref<Record<string, string[]>>({})
const localPlexUrl = ref('')
const localPlexToken = ref('')
const localPlexLibrary = ref('')
const localLibraries = ref<Array<{ id: string; title?: string; displayName?: string }>>([])
const localTmdbApiKey = ref('')
const localTvdbApiKey = ref('')
// Image Quality
const localOutputFormat = ref('jpg')
const localJpgQuality = ref(95)
const localPngCompression = ref(6)
const localWebpQuality = ref(90)
// Performance
const localConcurrentRenders = ref(2)
const localTmdbRateLimit = ref(40)
const localTvdbRateLimit = ref(20)
const localMemoryLimit = ref(2048)
let scanPoller: number | null = null

const loadLocalSettings = () => {
  localTheme.value = settings.theme.value
  localPosterDensity.value = settings.posterDensity.value
  localSaveLocation.value = settings.saveLocation.value
  localSaveBatch.value = settings.saveBatchInSubfolder.value
  localDefaultLabelsToRemove.value = JSON.parse(JSON.stringify(settings.defaultLabelsToRemove.value))
  // Connection settings
  localPlexUrl.value = settings.plex.value.url
  localPlexToken.value = settings.plex.value.token
  localPlexLibrary.value = settings.plex.value.movieLibraryName
  // Deep clone library mappings to prevent real-time updates
  const libraryMappings = settings.plex.value.libraryMappings && settings.plex.value.libraryMappings.length > 0
    ? settings.plex.value.libraryMappings
    : (settings.plex.value.movieLibraryNames || settings.plex.value.movieLibraryName
        ? (settings.plex.value.movieLibraryNames || [settings.plex.value.movieLibraryName]).map((n: string, idx: number) => ({
            id: n,
            title: n,
            displayName: n || `Library ${idx + 1}`
          }))
        : [{ id: '', title: '', displayName: '' }]
      )
  localLibraries.value = JSON.parse(JSON.stringify(libraryMappings)) as Array<{ id: string; title?: string; displayName?: string }>
  localTmdbApiKey.value = settings.tmdb.value.apiKey
  localTvdbApiKey.value = settings.tvdb.value.apiKey
  // Image Quality
  localOutputFormat.value = settings.imageQuality.value.outputFormat
  localJpgQuality.value = settings.imageQuality.value.jpgQuality
  localPngCompression.value = settings.imageQuality.value.pngCompression
  localWebpQuality.value = settings.imageQuality.value.webpQuality
  // Performance
  localConcurrentRenders.value = settings.performance.value.concurrentRenders
  localTmdbRateLimit.value = settings.performance.value.tmdbRateLimit
  localTvdbRateLimit.value = settings.performance.value.tvdbRateLimit
  localMemoryLimit.value = settings.performance.value.memoryLimit
}

const saveSettings = async () => {
  // Apply local settings to the store
  settings.theme.value = localTheme.value
  settings.posterDensity.value = localPosterDensity.value
  settings.saveLocation.value = localSaveLocation.value
  settings.saveBatchInSubfolder.value = localSaveBatch.value
  settings.defaultLabelsToRemove.value = JSON.parse(JSON.stringify(localDefaultLabelsToRemove.value))
  const libs = localLibraries.value.filter(l => l.id || l.title)
  settings.plex.value = {
    url: localPlexUrl.value,
    token: localPlexToken.value,
    movieLibraryName: libs[0]?.id || localPlexLibrary.value || '',
    movieLibraryNames: libs.length > 0 ? libs.map(l => l.id) : undefined,
    libraryMappings: libs.map(l => ({
      id: l.id || '',
      title: l.title || l.id || '',
      displayName: l.displayName || l.title || l.id || '',
    }))
  }
  settings.tmdb.value = { apiKey: localTmdbApiKey.value }
  settings.tvdb.value = { apiKey: localTvdbApiKey.value, comingSoon: settings.tvdb.value.comingSoon }
  settings.imageQuality.value = {
    outputFormat: localOutputFormat.value,
    jpgQuality: localJpgQuality.value,
    pngCompression: localPngCompression.value,
    webpQuality: localWebpQuality.value
  }
  settings.performance.value = {
    concurrentRenders: localConcurrentRenders.value,
    tmdbRateLimit: localTmdbRateLimit.value,
    tvdbRateLimit: localTvdbRateLimit.value,
    memoryLimit: localMemoryLimit.value
  }

  // Save to backend
  await settings.save()
  saved.value = settings.error.value ? `Error: ${settings.error.value}` : 'Saved!'
  setTimeout(() => (saved.value = ''), 1500)
}

const testConnection = ref('')
const testConnectionLoading = ref(false)
const plexLibraries = ref<Array<{ title: string; key: string; type: string }>>([])
const addLibrary = () => {
  localLibraries.value = [...localLibraries.value, { id: '', title: '', displayName: '' }]
}
const removeLibrary = (idx: number) => {
  localLibraries.value = localLibraries.value.filter((_, i) => i !== idx)
}

const testPlexConnection = async () => {
  testConnectionLoading.value = true
  testConnection.value = 'Testing connection...'
  plexLibraries.value = []

  try {
    const apiBase = getApiBase()
    // Send current input values as query parameters to test with them
    const params = new URLSearchParams({
      plex_url: localPlexUrl.value,
      plex_token: localPlexToken.value
    })
    const res = await fetch(`${apiBase}/api/test-plex-connection?${params}`)
    const data = await res.json()

    if (data.status === 'ok') {
      plexLibraries.value = data.sections || []
      const movieLibs = plexLibraries.value.filter(s => s.type === 'movie')
      const sectionsList = movieLibs.map((s: any) => s.title).join(', ')
      testConnection.value = `✓ Connected! Found ${movieLibs.length} movie libraries: ${sectionsList}`
      if (movieLibs.length > 0) {
        // Seed libraries if none configured yet
        if (!localLibraries.value.length || localLibraries.value.every(l => !l.id)) {
          localLibraries.value = movieLibs.map((s: any, idx: number) => ({
            id: s.key,
            title: s.title,
            displayName: s.title || `Library ${idx + 1}`,
          }))
        }
      }
    } else {
      testConnection.value = `✗ ${data.error}: ${data.message}`
    }
  } catch (e) {
    testConnection.value = `✗ Connection failed: ${e instanceof Error ? e.message : 'Unknown error'}`
  } finally {
    testConnectionLoading.value = false
    setTimeout(() => (testConnection.value = ''), 10000)
  }
}

const clearCache = () => {
  if (scan.running.value) {
    saved.value = 'Scan in progress - cannot clear session cache'
    setTimeout(() => (saved.value = ''), 2000)
    return
  }
  if (!window.confirm('This will clear cached movies/posters/labels from this browser session. Continue?')) {
    return
  }
  try {
    // Clear poster cache from sessionStorage
    sessionStorage.removeItem('simposter-poster-cache')
    // Clear label cache from localStorage
    sessionStorage.removeItem('simposter-labels-cache')
    sessionStorage.removeItem('simposter-movies-cache')
    saved.value = 'Session cache cleared!'
    setTimeout(() => (saved.value = ''), 1500)
  } catch (e) {
    console.error('Failed to clear cache', e)
  }
}

const scanLibrary = async () => {
  if (scan.running.value || scan.checking.value) {
    saved.value = 'Scan already in progress'
    setTimeout(() => (saved.value = ''), 2000)
    return
  }

  if (scanCooldown.value) {
    saved.value = 'Please wait before starting another scan'
    setTimeout(() => (saved.value = ''), 2000)
    return
  }
  
  try {
    // Set scan state immediately to prevent double-clicks
    scan.running.value = true
    // Enable cooldown for 10 seconds
    scanCooldown.value = true
    setTimeout(() => {
      // Only disable cooldown if scan is not still running
      if (!scan.running.value && !scan.checking.value) {
        scanCooldown.value = false
      } else {
        // If scan is still running, check again in 5 seconds
        const checkScanStatus = () => {
          if (!scan.running.value && !scan.checking.value) {
            scanCooldown.value = false
          } else {
            setTimeout(checkScanStatus, 5000)
          }
        }
        setTimeout(checkScanStatus, 5000)
      }
    }, 10000)
    saved.value = 'Rescanning library...'
    scan.visible.value = true
    scan.log.value = ['Starting rescan...']
    scan.progress.value = { processed: 0, total: 0 }
    scan.current.value = ''
    startScanPolling()
    
    const apiBase = getApiBase()
    const res = await fetch(`${apiBase}/api/scan-library`, { method: 'POST' })
    if (!res.ok) {
      if (res.status === 409) {
        throw new Error('Scan already in progress on server')
      }
      throw new Error(`API error ${res.status}`)
    }
    const data = await res.json()

    // Cache movies
    if (Array.isArray(data.movies)) {
      moviesCache.value = data.movies
      moviesLoaded.value = true
      scan.progress.value = { processed: data.movies.length, total: data.movies.length }
      scan.log.value = data.movies.slice(0, 20).map((m: any) => `${m.title}${m.year ? ` (${m.year})` : ''}`)
      if (data.movies.length > 20) {
        scan.log.value.push(`...and ${data.movies.length - 20} more`)
      }
      try {
        sessionStorage.setItem('simposter-movies-cache', JSON.stringify(data.movies))
      } catch (err) {
        console.error('Failed to cache movies', err)
      }
    }

    // Cache posters
    if (data.posters && typeof sessionStorage !== 'undefined') {
      try {
        sessionStorage.setItem('simposter-poster-cache', JSON.stringify(data.posters))
      } catch (err) {
        console.error('Failed to cache posters', err)
      }
    }

    // Cache labels
    if (data.labels && typeof sessionStorage !== 'undefined') {
      try {
        sessionStorage.setItem('simposter-labels-cache', JSON.stringify(data.labels))
      } catch (err) {
        console.error('Failed to cache labels', err)
      }
    }

    saved.value = `Rescanned ${data.count || 0} items`
    setTimeout(() => (saved.value = ''), 2000)
    // Refresh label cache after scan
    await fetchAllLabels()
    // Mark scan done; overlay will auto-hide via scan store
    scan.log.value = [`Done: ${scan.progress.value.processed || data.count || 0} items`]
    scan.running.value = false
    // Clear cooldown when scan completes
    scanCooldown.value = false
    // Ensure overlay hides even if no further poll events arrive
    setTimeout(() => {
      scan.visible.value = false
      scan.log.value = []
      scan.current.value = ''
    }, 2000)
  } catch (e) {
    saved.value = `Scan failed: ${e instanceof Error ? e.message : 'Unknown error'}`
    scan.log.value = [`Scan failed: ${e instanceof Error ? e.message : 'Unknown error'}`]
    setTimeout(() => {
      saved.value = ''
      scan.visible.value = false
    }, 3000)
  }
  stopScanPolling()
  scan.running.value = false
  // Clear cooldown when function exits
  scanCooldown.value = false
}

const clearBackendCache = async () => {
  if (scan.running.value || scan.checking.value) {
    saved.value = 'Scan in progress - cannot clear cache'
    setTimeout(() => (saved.value = ''), 2000)
    return
  }
  if (!window.confirm('⚠️ This will delete backend cache (posters + DB cache). Continue?')) {
    return
  }
  try {
    const apiBase = getApiBase()
    const res = await fetch(`${apiBase}/api/cache`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    saved.value = `Backend cache cleared (${data.removed_posters || 0} poster files removed)`
    // Also clear browser caches
    sessionStorage.removeItem('simposter-poster-cache')
    sessionStorage.removeItem('simposter-labels-cache')
    sessionStorage.removeItem('simposter-movies-cache')
  } catch (e) {
    saved.value = `Failed to clear backend cache: ${e instanceof Error ? e.message : 'Unknown error'}`
  } finally {
    setTimeout(() => (saved.value = ''), 2500)
  }
}

// Fetch all available labels from movies per library
const fetchAllLabels = async () => {
  try {
    const libs = settings.plex.value.libraryMappings || []
    const labelsByLibrary: Record<string, string[]> = {}

    // Get all valid library IDs
    const validLibIds = new Set(libs.map(l => l.id).filter(Boolean))

    // Clear stale caches that don't correspond to current libraries
    if (typeof sessionStorage !== 'undefined') {
      const keysToRemove: string[] = []
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i)
        if (key && key.startsWith('simposter-labels-cache-')) {
          const libId = key.replace('simposter-labels-cache-', '')
          if (libId !== 'default' && !validLibIds.has(libId)) {
            keysToRemove.push(key)
          }
        }
      }
      keysToRemove.forEach(key => sessionStorage.removeItem(key))
    }

    for (const lib of libs) {
      const libId = lib.id || 'default'
      const labelCacheKey = `simposter-labels-cache-${libId}`
      const labelCache = sessionStorage.getItem(labelCacheKey)

      if (labelCache) {
        const cache = JSON.parse(labelCache) as Record<string, string[]>
        const labels = new Set<string>()
        Object.values(cache).forEach((movieLabels) => {
          if (Array.isArray(movieLabels)) {
            movieLabels.forEach((label) => labels.add(label))
          }
        })
        labelsByLibrary[libId] = Array.from(labels).sort()
      }

      // Initialize empty labels if library not in settings yet
      if (!localDefaultLabelsToRemove.value[libId]) {
        localDefaultLabelsToRemove.value[libId] = []
      }
    }

    allLabels.value = labelsByLibrary
  } catch (e) {
    console.error('Failed to fetch labels', e)
  }
}

onMounted(async () => {
  // Ensure settings are loaded from API before syncing local form state
  if (!settings.loaded.value) {
    await settings.load()
  }

  // Only load local settings and labels after settings are confirmed loaded
  loadLocalSettings()
  fetchAllLabels()

  // Load Plex libraries if credentials exist to populate dropdowns
  if (settings.plex.value.url && settings.plex.value.token) {
    await testPlexConnection()
  }
})

// If settings finish loading after initial render, sync the local form
watch(
  () => settings.loaded.value,
  (val) => {
    if (val) {
      loadLocalSettings()
      fetchAllLabels()
    }
  }
)

// Refetch labels when library mappings change
watch(
  () => settings.plex.value.libraryMappings,
  () => {
    fetchAllLabels()
  },
  { deep: true }
)

const toggleLabel = (libraryId: string, label: string) => {
  if (!localDefaultLabelsToRemove.value[libraryId]) {
    localDefaultLabelsToRemove.value[libraryId] = []
  }
  const set = new Set(localDefaultLabelsToRemove.value[libraryId])
  if (set.has(label)) {
    set.delete(label)
  } else {
    set.add(label)
  }
  localDefaultLabelsToRemove.value[libraryId] = Array.from(set)
}

const isLabelSelected = (libraryId: string, label: string) => {
  return localDefaultLabelsToRemove.value[libraryId]?.includes(label) || false
}

const startScanPolling = () => {
  stopScanPolling()
  const apiBase = getApiBase()
  scanPoller = window.setInterval(async () => {
    try {
      const res = await fetch(`${apiBase}/api/scan-progress`)
      if (!res.ok) return
      const data = await res.json()
      if (data.total) {
        scan.progress.value = { processed: data.processed || 0, total: data.total || 0 }
      }
      if (data.current) {
        scan.current.value = data.current
      }
      if (scan.progress.value.total) {
        const pct = Math.min(100, Math.round((scan.progress.value.processed / scan.progress.value.total) * 100))
        const line = `${scan.progress.value.processed}/${scan.progress.value.total} (${pct}%) ${scan.current.value || ''}`
        scan.log.value = [line]
      }
      if (data.state && data.state !== 'running') {
        stopScanPolling()
        scan.running.value = false
        scan.visible.value = false
      }
    } catch {
      // ignore polling errors
    }
  }, 1000)
}

const stopScanPolling = () => {
  if (scanPoller !== null) {
    clearInterval(scanPoller)
    scanPoller = null
  }
}
</script>

<template>
  <div class="view" @click.stop @mouseup.stop @mousedown.stop @select.stop @selectstart.stop>
    <div class="settings-header">
      <div class="settings-title-row">
        <div>
          <h2>Settings</h2>
          <p class="header-subtitle">Customize your Simposter experience</p>
        </div>
        <span class="version-chip">{{ APP_VERSION }}</span>
      </div>
    </div>

    <div class="settings-section">
      <h3 class="section-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/>
          <path d="M2 17l10 5 10-5"/>
          <path d="M2 12l10 5 10-5"/>
        </svg>
        Appearance
      </h3>
      <div class="grid">
        <label>
          <span class="label-text">Theme</span>
          <select v-model="localTheme">
            <option value="neon">Neon</option>
            <option value="slate">Slate</option>
            <option value="dracula">Dracula</option>
            <option value="nord">Nord</option>
            <option value="oled">OLED</option>
            <option value="light">Light</option>
          </select>
        </label>
        <label>
          <span class="label-text">Movies per page</span>
          <input
            v-model.number="localPosterDensity"
            type="number"
            min="5"
            max="100"
            @select.stop
            @selectstart.stop
          />
        </label>
      </div>
    </div>

    <div class="settings-section">
      <h3 class="section-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
          <line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>
        Output
      </h3>
      <div class="grid">
        <label class="full-width" @mousedown.stop @click.stop>
          <span class="label-text">Save Location</span>
          <input
            v-model="localSaveLocation"
            type="text"
            placeholder="config/output/{library}/{title}.jpg"
            @mousedown.stop
            @click.stop
            @mouseup.stop
            @select.stop
            @selectstart.stop
          />
          <span class="help-text">Available variables: {library}, {title}, {year}, {key}</span>
        </label>
        <label class="inline">
          <input type="checkbox" v-model="localSaveBatch" />
          <span class="label-text">Save batch runs into subfolder (add /batch/ after output root)</span>
        </label>
      </div>
    </div>

    <div class="settings-section">
      <h3 class="section-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
        </svg>
        Connections
      </h3>
      <div class="grid connections">
        <label>
          <span class="label-text">Plex URL</span>
          <input
            v-model="localPlexUrl"
            type="text"
            placeholder="http://localhost:32400"
            @mousedown.stop
            @click.stop
            @mouseup.stop
            @select.stop
            @selectstart.stop
          />
        </label>
        <label>
          <span class="label-text">Plex Token</span>
          <input
            v-model="localPlexToken"
            type="password"
            placeholder="Plex token"
            @mousedown.stop
            @click.stop
            @mouseup.stop
            @select.stop
            @selectstart.stop
          />
          <span class="help-text">Use the Plex token or future auto-discovery once available.</span>
        </label>
        <div class="test-connection-wrapper">
          <button
            class="btn-test-connection"
            @click="testPlexConnection"
            :disabled="testConnectionLoading"
          >
            {{ testConnectionLoading ? 'Testing...' : 'Test Plex Connection' }}
          </button>
          <p v-if="testConnection" :class="['test-result', testConnection.startsWith('✓') ? 'success' : 'error']">
            {{ testConnection }}
          </p>
        </div>
      </div>
      
      <div class="movie-libraries-subsection">
        <h4 class="subsection-title">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
            <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
          </svg>
          Movie Libraries
        </h4>
        <div class="library-list">
          <div
            v-for="(lib, idx) in localLibraries"
            :key="idx"
            class="library-row"
          >
            <div class="library-header">
              <span class="label-text">{{ lib.displayName || lib.title || `Library ${idx + 1}` }}</span>
              <span v-if="lib.id" class="library-id-badge">ID: {{ lib.id }}</span>
            </div>
            <select
              v-model="lib.id"
              class="form-control"
              :class="{ 'locked': !!lib.id }"
              :disabled="!!lib.id"
              @change="(e) => {
                const selected = plexLibraries.find(p => p.key === (e.target as HTMLSelectElement).value)
                if (selected && !lib.displayName) {
                  lib.title = selected.title
                  lib.displayName = selected.title
                }
              }"
            >
              <option value="">Select a library...</option>
              <option
                v-for="p in plexLibraries.filter(s => s.type === 'movie')"
                :key="p.key"
                :value="p.key"
              >
                {{ p.title }} (ID: {{ p.key }})
              </option>
            </select>
            <input
              v-model="lib.displayName"
              type="text"
              placeholder="Display name (e.g., 4K Movies)"
              @mousedown.stop
              @click.stop
              @mouseup.stop
              @select.stop
              @selectstart.stop
            />
            <button class="secondary small" type="button" @click="removeLibrary(idx)" :disabled="localLibraries.length <= 1">Remove</button>
          </div>
          <button class="secondary small" type="button" @click="addLibrary">+ Add Library</button>
          <span class="help-text">First entry is treated as the default. Use Plex dropdowns or IDs; display names show in Simposter.</span>
        </div>
      </div>

      <div class="api-keys-section">
        <label>
          <span class="label-text">TMDb API Key</span>
          <input
            v-model="localTmdbApiKey"
            type="password"
            placeholder="TMDb API key"
            @mousedown.stop
            @click.stop
            @mouseup.stop
            @select.stop
            @selectstart.stop
          />
        </label>
        <label>
          <span class="label-text">TVDB API Key</span>
          <input
            v-model="localTvdbApiKey"
            type="password"
            placeholder="TVDB API key (coming soon)"
            @mousedown.stop
            @click.stop
            @mouseup.stop
            @select.stop
            @selectstart.stop
          />
          <span class="help-text">Coming soon—value is saved for future use.</span>
        </label>
      </div>
    </div>

    <div class="settings-section">
      <h3 class="section-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
          <circle cx="8.5" cy="8.5" r="1.5"/>
          <polyline points="21 15 16 10 5 21"/>
        </svg>
        Image Quality
      </h3>
      <div class="grid">
        <label>
          <span class="label-text">Output Format</span>
          <select v-model="localOutputFormat">
            <option value="jpg">JPEG</option>
            <option value="png">PNG</option>
            <option value="webp">WebP</option>
          </select>
        </label>
        <label v-if="localOutputFormat === 'jpg'">
          <span class="label-text">JPEG Quality</span>
          <input
            v-model.number="localJpgQuality"
            type="range"
            min="60"
            max="100"
            class="quality-slider"
          />
          <div class="slider-value">{{ localJpgQuality }}%</div>
        </label>
        <label v-if="localOutputFormat === 'png'">
          <span class="label-text">PNG Compression</span>
          <input
            v-model.number="localPngCompression"
            type="range"
            min="0"
            max="9"
            class="quality-slider"
          />
          <div class="slider-value">Level {{ localPngCompression }}</div>
        </label>
        <label v-if="localOutputFormat === 'webp'">
          <span class="label-text">WebP Quality</span>
          <input
            v-model.number="localWebpQuality"
            type="range"
            min="60"
            max="100"
            class="quality-slider"
          />
          <div class="slider-value">{{ localWebpQuality }}%</div>
        </label>
      </div>
    </div>

    <div class="settings-section">
      <h3 class="section-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
        </svg>
        Performance
      </h3>
      <div class="grid">
        <label>
          <span class="label-text">Concurrent Renders</span>
          <input
            v-model.number="localConcurrentRenders"
            type="number"
            min="1"
            max="8"
            @select.stop
            @selectstart.stop
          />
          <span class="help-text">How many posters to render at the same time</span>
        </label>
        <label>
          <span class="label-text">TMDb Rate Limit</span>
          <input
            v-model.number="localTmdbRateLimit"
            type="number"
            min="10"
            max="100"
            @select.stop
            @selectstart.stop
          />
          <span class="help-text">Requests per 10 seconds</span>
        </label>
        <label>
          <span class="label-text">TVDB Rate Limit</span>
          <input
            v-model.number="localTvdbRateLimit"
            type="number"
            min="5"
            max="50"
            @select.stop
            @selectstart.stop
          />
          <span class="help-text">Requests per 10 seconds</span>
        </label>
        <label>
          <span class="label-text">Memory Limit (MB)</span>
          <input
            v-model.number="localMemoryLimit"
            type="number"
            min="512"
            max="8192"
            step="256"
            @select.stop
            @selectstart.stop
          />
          <span class="help-text">Maximum memory for image processing</span>
        </label>
      </div>
    </div>

    <div v-if="Object.keys(allLabels).length > 0" class="settings-section labels-section">
      <h3 class="section-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/>
          <line x1="7" y1="7" x2="7.01" y2="7"/>
        </svg>
        Default Labels to Remove
      </h3>
      <p class="section-subtitle">When sending to Plex, these labels will be removed by default for each library</p>

      <!-- Library-specific label sections -->
      <div v-for="(labels, libId) in allLabels" :key="libId" class="library-labels-section">
        <h4 class="library-labels-title">
          {{ localLibraries.find(l => l.id === libId)?.displayName || localLibraries.find(l => l.id === libId)?.title || libId }}
        </h4>
        <div v-if="labels.length > 0" class="labels-grid">
          <label v-for="label in labels" :key="`${libId}-${label}`" class="label-checkbox">
            <input type="checkbox" :checked="isLabelSelected(libId, label)" @change="toggleLabel(libId, label)" />
            <span>{{ label }}</span>
          </label>
        </div>
        <p v-else class="no-labels-message">No labels found for this library yet. Scan the library to discover labels.</p>
      </div>
    </div>

    <div class="actions">
      <button @click="saveSettings" class="primary">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
          <polyline points="17 21 17 13 7 13 7 21"/>
          <polyline points="7 3 7 8 15 8"/>
        </svg>
        Save Settings
      </button>
      <button @click="clearCache" class="secondary" :disabled="isScanInProgress">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="1 4 1 10 7 10"/>
          <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
        </svg>
        Clear Session Cache
      </button>
      <button @click="clearBackendCache" class="secondary" :disabled="isScanInProgress">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 4H8l-7 8 7 8h13a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2z"/>
          <polyline points="18 9 12 15"/>
          <polyline points="12 9 18 15"/>
        </svg>
        Clear Backend Cache
      </button>
      <button @click="scanLibrary" class="secondary" :disabled="isScanInProgress">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
          <polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
        {{ scanCooldown ? 'Please Wait...' : scan.running.value ? 'Scanning...' : 'Rescan Library' }}
      </button>
      <span v-if="saved" class="status">{{ saved }}</span>
    </div>

    <!-- Overlay now global in App.vue -->
  </div>
</template>

<style scoped>
.view {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.settings-header {
  margin-bottom: 8px;
}

.settings-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.settings-header h2 {
  margin: 0 0 8px 0;
  font-size: 28px;
  font-weight: 700;
  background: linear-gradient(120deg, #3dd6b7, #5b8dee);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--muted);
  font-weight: 400;
}

.settings-section {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
  transition: all 0.2s;
}

.settings-section:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(61, 214, 183, 0.15);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
  color: #eef2ff;
}

.section-title svg {
  color: var(--accent);
  flex-shrink: 0;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}

.connections {
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  max-width: 600px;
}

.movie-libraries-subsection {
  margin-top: 24px;
}

.subsection-title {
  font-size: 16px;
  font-weight: 600;
  color: #3dd6b7;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.subsection-title svg {
  width: 16px;
  height: 16px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
  color: #dbe4ff;
  transition: all 0.2s;
}

label:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(61, 214, 183, 0.2);
}

.label-text {
  font-size: 13px;
  font-weight: 500;
  color: #c9d6ff;
}

label.inline {
  flex-direction: row;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

label.inline input[type="checkbox"] {
  width: auto;
  margin: 0;
  cursor: pointer;
}

label.full-width {
  grid-column: 1 / -1;
}

input,
select,
textarea {
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 10px 12px;
  background: rgba(0, 0, 0, 0.2);
  color: #e6edff;
  font-size: 14px;
  transition: all 0.2s;
}

input:focus,
select:focus {
  outline: none;
  border-color: rgba(61, 214, 183, 0.5);
  background: rgba(0, 0, 0, 0.3);
  box-shadow: 0 0 0 3px rgba(61, 214, 183, 0.1);
}

input[type="number"] {
  appearance: textfield;
}

input[type="checkbox"] {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  cursor: pointer;
  accent-color: var(--accent);
}

.quality-slider {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.1);
  outline: none;
  cursor: pointer;
}

.quality-slider::-webkit-slider-thumb {
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(61, 214, 183, 0.3);
}

.quality-slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  border: none;
  box-shadow: 0 2px 6px rgba(61, 214, 183, 0.3);
}

.slider-value {
  margin-top: 6px;
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
}

.labels-section {
  background: rgba(61, 214, 183, 0.03);
  border-color: rgba(61, 214, 183, 0.15);
}

.section-subtitle {
  margin: 0 0 16px 0;
  font-size: 13px;
  color: var(--muted);
  font-weight: 400;
}

.library-labels-section {
  margin-bottom: 24px;
  padding-bottom: 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.library-labels-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.library-labels-title {
  margin: 0 0 12px 0;
  font-size: 15px;
  font-weight: 600;
  color: #eef2ff;
  display: flex;
  align-items: center;
  gap: 8px;
}

.no-labels-message {
  margin: 0;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  color: var(--muted);
  font-size: 13px;
  font-style: italic;
}

.labels-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}

.label-checkbox {
  flex-direction: row;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
  cursor: pointer;
  transition: all 0.2s;
}

.label-checkbox:hover {
  background: rgba(61, 214, 183, 0.08);
  border-color: rgba(61, 214, 183, 0.3);
}

.label-checkbox input {
  cursor: pointer;
  width: auto;
  padding: 0;
  margin: 0;
  flex-shrink: 0;
}

.label-checkbox span {
  font-size: 13px;
  flex: 1;
  user-select: none;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 8px;
  flex-wrap: wrap;
}

button {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 18px;
  background: rgba(255, 255, 255, 0.05);
  color: #dce6ff;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

button svg {
  flex-shrink: 0;
}

.scan-overlay {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 2000;
}

.scan-card {
  display: flex;
  gap: 10px;
  padding: 12px 14px;
  background: rgba(0, 0, 0, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #eef2ff;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  max-width: 320px;
}

.scan-title {
  margin: 0 0 4px 0;
  font-weight: 600;
}

.scan-current {
  margin: 2px 0 6px;
  font-size: 13px;
  color: #dbe4ff;
  opacity: 0.9;
}

.scan-list {
  margin: 0;
  padding-left: 18px;
  max-height: 200px;
  overflow-y: auto;
  font-size: 13px;
}

.progress-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0 8px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3dd6b7, #5b8dee);
  border-radius: 4px;
  transition: width 0.2s ease;
}

.progress-text {
  font-size: 12px;
  color: #dbe4ff;
  min-width: 80px;
  text-align: right;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: var(--accent, #3dd6b7);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

button.primary {
  background: linear-gradient(135deg, rgba(61, 214, 183, 0.2), rgba(91, 141, 238, 0.15));
  border-color: rgba(61, 214, 183, 0.4);
  color: #eef2ff;
}

button.primary:hover {
  background: linear-gradient(135deg, rgba(61, 214, 183, 0.3), rgba(91, 141, 238, 0.25));
  border-color: rgba(61, 214, 183, 0.6);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(61, 214, 183, 0.15);
}

button.secondary {
  background: rgba(255, 255, 255, 0.02);
  color: #b8c5e0;
  border-color: rgba(255, 255, 255, 0.1);
}

button.secondary:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

.status {
  color: var(--accent);
  font-size: 14px;
  font-weight: 500;
  padding: 0 8px;
  animation: fadeIn 0.3s ease-in;
}

.version-chip {
  align-self: flex-start;
  padding: 6px 10px;
  border-radius: 12px;
  background: rgba(61, 214, 183, 0.12);
  color: #a9f0dd;
  border: 1px solid rgba(61, 214, 183, 0.35);
  font-weight: 600;
  font-size: 13px;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.help-text {
  font-size: 12px;
  color: var(--muted);
  opacity: 0.8;
  font-style: italic;
  margin-top: -2px;
}

@media (max-width: 768px) {
  .view {
    padding: 16px;
  }

  .grid,
  .connections {
    grid-template-columns: 1fr;
  }

  .actions {
    flex-direction: column;
    align-items: stretch;
  }

  button {
    width: 100%;
    justify-content: center;
  }
}

/* Test Connection */
.test-connection-wrapper {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--surface-alt, #1e2330);
  border-radius: 8px;
  border: 1px solid var(--border, #2a2f3e);
}

.btn-test-connection {
  padding: 0.75rem 1.5rem;
  background: var(--accent, #3dd6b7);
  color: #000;
  border: none;
  border-radius: 6px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  align-self: flex-start;
}

.btn-test-connection:hover:not(:disabled) {
  background: #2bc4a3;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(61, 214, 183, 0.3);
}

.btn-test-connection:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.test-result {
  margin: 0;
  padding: 0.75rem;
  border-radius: 6px;
  font-size: 0.9rem;
  line-height: 1.5;
}

.test-result.success {
  background: rgba(61, 214, 183, 0.1);
  color: var(--accent, #3dd6b7);
  border: 1px solid rgba(61, 214, 183, 0.3);
}

.test-result.error {
  background: rgba(255, 107, 107, 0.1);
  color: #ff6b6b;
  border: 1px solid rgba(255, 107, 107, 0.3);
}

.library-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.library-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
}

.library-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.library-id-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(61, 214, 183, 0.15);
  color: #a9f0dd;
  border: 1px solid rgba(61, 214, 183, 0.3);
  font-weight: 500;
}

/* Locked library dropdown */
.library-row select.locked {
  opacity: 0.6;
  cursor: not-allowed;
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.05);
}

.library-row select.locked:hover {
  border-color: rgba(255, 255, 255, 0.05);
}

.secondary.small {
  padding: 8px 10px;
  font-size: 12px;
  align-self: flex-start;
}

.api-keys-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 20px;
}
</style>
