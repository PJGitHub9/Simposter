<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Sidebar, { type MenuItem } from './components/layout/Sidebar.vue'
import TopNav from './components/layout/TopNav.vue'
import EditorPane from './components/editor/EditorPane.vue'
import NotificationContainer from './components/NotificationContainer.vue'
import { useUiStore, type TabKey } from './stores/ui'
import { useMovies } from './composables/useMovies'
import { useSettingsStore } from './stores/settings'
import { useScanStore } from './stores/scan'
import { getApiBase } from '@/services/apiBase'

const tabs: MenuItem[] = [
  {
    key: 'movies',
    label: 'Movies',
    submenu: [
      { key: 'batch-edit', label: 'Batch Edit' },
      { key: 'local-assets', label: 'Local Assets' }
    ]
  },
  { key: 'settings', label: 'Settings' },
  { key: 'logs', label: 'Logs' }
]

const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const searchQuery = ref('')
const { movies, hydratePostersFromSession } = useMovies()
const settings = useSettingsStore()
const scan = useScanStore()
let scanPoller: number | null = null

const activeTab = computed<TabKey>(() => {
  // Treat batch-edit and local-assets as part of movies for sidebar highlighting
  if (route.name === 'batch-edit' || route.name === 'local-assets') return 'movies'
  return (route.name as TabKey) || 'movies'
})

const activeSubmenu = computed<string>(() => {
  // Return the current route name if it's a submenu route
  if (route.name === 'batch-edit') return 'batch-edit'
  if (route.name === 'local-assets') return 'local-assets'
  return ''
})
const showBackButton = computed(() => !!ui.selectedMovie.value)

const handleSelect = (movie: { key: string; title: string; year?: number | string; poster?: string | null }) => {
  // Guard against native DOM events being passed instead of movie objects
  if (!movie || typeof movie !== 'object' || !movie.key || !movie.title) {
    return
  }
  ui.setSelectedMovie(movie)
}

const handleTabSelect = (tab: TabKey) => {
  // Always close editor if open
  if (ui.selectedMovie.value) {
    ui.setSelectedMovie(null)
  }
  router.push({ name: tab })
}

const handleBack = () => {
  ui.setSelectedMovie(null)
}

onMounted(() => {
  const applyTheme = (theme: string) => {
    document.documentElement.dataset.theme = theme
  }
  applyTheme(settings.theme.value)
  watch(
    () => settings.theme.value,
    (t) => applyTheme(t)
  )
  hydratePostersFromSession()
  scan.checking.value = true
  fetchScanStatus().then((running) => {
    if (running) startScanPolling()
    else scan.checking.value = false
  })
})

onUnmounted(() => {
  stopScanPolling()
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

const handleSearchSelect = (movie: { key: string; title: string; year?: number | string; poster?: string | null }) => {
  router.push({ name: 'movies' })
  ui.setSelectedMovie(movie)
}

const handleSubmenuClick = (parentKey: TabKey, submenuKey: string) => {
  // Always close editor if open
  if (ui.selectedMovie.value) {
    ui.setSelectedMovie(null)
  }

  if (parentKey === 'movies') {
    if (submenuKey === 'batch-edit') {
      router.push({ name: 'batch-edit' })
    } else if (submenuKey === 'local-assets') {
      router.push({ name: 'local-assets' })
    }
  }
}
</script>

<template>
  <div class="shell">
    <NotificationContainer />
    <TopNav
      :search="searchQuery"
      :show-back="showBackButton"
      :movies="movies"
      @update:search="searchQuery = $event"
      @back="handleBack"
      @select-movie="handleSearchSelect"
    />
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

    <!-- Normal workspace (movies/settings/logs) -->
    <div v-if="!ui.selectedMovie.value" class="workspace">
      <Sidebar :tabs="tabs" :active="activeTab" :active-submenu="activeSubmenu" @select="handleTabSelect" @submenu-click="handleSubmenuClick" />
      <section class="main-pane glass">
        <router-view :key="activeTab" :search="searchQuery" @select="handleSelect" />
      </section>
    </div>

    <!-- Inline editor when a movie is selected -->
    <div v-else class="workspace">
      <Sidebar :tabs="tabs" :active="activeTab" :active-submenu="activeSubmenu" @select="handleTabSelect" @submenu-click="handleSubmenuClick" />
      <section class="main-pane glass">
        <EditorPane :movie="ui.selectedMovie.value" @close="ui.setSelectedMovie(null)" />
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

@media (max-width: 900px) {
  .workspace {
    grid-template-columns: 1fr;
  }
}
</style>
