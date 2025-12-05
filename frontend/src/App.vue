<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Sidebar, { type MenuItem } from './components/layout/Sidebar.vue'
import TopNav from './components/layout/TopNav.vue'
import EditorPane from './components/editor/EditorPane.vue'
import NotificationContainer from './components/NotificationContainer.vue'
import { useUiStore, type TabKey } from './stores/ui'
import { useMovies } from './composables/useMovies'
import { useSettingsStore } from './stores/settings'

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
})

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

@media (max-width: 900px) {
  .workspace {
    grid-template-columns: 1fr;
  }
}
</style>
