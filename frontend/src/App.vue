<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Sidebar from './components/layout/Sidebar.vue'
import TopNav from './components/layout/TopNav.vue'
import EditorPane from './components/editor/EditorPane.vue'
import NotificationContainer from './components/NotificationContainer.vue'
import { useUiStore, type TabKey } from './stores/ui'
import { useMovies } from './composables/useMovies'
import { useSettingsStore } from './stores/settings'

const tabs: { key: TabKey; label: string }[] = [
  { key: 'movies', label: 'Movies' },
  { key: 'settings', label: 'Settings' },
  { key: 'logs', label: 'Logs' }
]

const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const searchQuery = ref('')
const { movies } = useMovies()
const settings = useSettingsStore()

const activeTab = computed<TabKey>(() => (route.name as TabKey) || 'movies')
const showBackButton = computed(() => !!ui.selectedMovie.value)

const handleSelect = (movie: { key: string; title: string; year?: number | string; poster?: string | null }) => {
  ui.setSelectedMovie(movie)
}

const handleTabSelect = (tab: TabKey) => {
  // Close editor if open
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
})

const handleSearchSelect = (movie: { key: string; title: string; year?: number | string; poster?: string | null }) => {
  router.push({ name: 'movies' })
  ui.setSelectedMovie(movie)
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
      <Sidebar :tabs="tabs" :active="activeTab" @select="handleTabSelect" />
      <section class="main-pane glass">
        <router-view :key="activeTab" :search="searchQuery" @select="handleSelect" />
      </section>
    </div>

    <!-- Inline editor when a movie is selected -->
    <div v-else class="workspace">
      <Sidebar :tabs="tabs" :active="activeTab" @select="handleTabSelect" />
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
}

.workspace {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 14px;
}

.main-pane {
  padding: 16px;
  background: rgba(14, 16, 24, 0.75);
  min-height: 60vh;
}

@media (max-width: 900px) {
  .workspace {
    grid-template-columns: 1fr;
  }
}
</style>
