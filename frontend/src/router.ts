import { createRouter, createWebHistory } from 'vue-router'
import MoviesView from './views/MoviesView.vue'
import TvShowsView from './views/TvShowsView.vue'
import SettingsView from './views/SettingsView.vue'
import LogsView from './views/LogsView.vue'
import BatchEditView from './views/BatchEditView.vue'
import TvBatchEditView from './views/TvBatchEditView.vue'
import LocalAssetsView from './views/LocalAssetsView.vue'
import CollectionsView from './views/CollectionsView.vue'
import TemplateManagerView from './views/TemplateManagerView.vue'
import HistoryView from './views/HistoryView.vue'
import BackupRestoreView from './views/BackupRestoreView.vue'
import OverlayConfigManagerView from './views/OverlayConfigManagerView.vue'
import LogosView from './views/LogosView.vue'
import BackdropsView from './views/BackdropsView.vue'
import SquareArtView from './views/SquareArtView.vue'
import ThumbArtView from './views/ThumbArtView.vue'
import MediaMirrorView from './views/MediaMirrorView.vue'
import OverlayRefreshView from './views/OverlayRefreshView.vue'
import PosterApiView from './views/PosterApiView.vue'
import { useSettingsStore } from './stores/settings'
import { useServerless } from './composables/useServerless'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/movies' },
    { path: '/movies', name: 'movies', component: MoviesView },
    { path: '/movies/batch-edit', name: 'batch-edit', component: BatchEditView },
    { path: '/movies/collections', name: 'collections', component: CollectionsView },
    { path: '/movies/local-assets', name: 'local-assets', component: LocalAssetsView },
    { path: '/movies/logos', name: 'logos', component: LogosView },
    { path: '/movies/backdrops', name: 'backdrops', component: BackdropsView },
    { path: '/movies/square-art', name: 'square-art', component: SquareArtView },
    { path: '/movies/thumb-art', name: 'thumb-art', component: ThumbArtView },
    { path: '/movies/media-mirror', name: 'media-mirror', component: MediaMirrorView },
    { path: '/movies/overlay-refresh', name: 'overlay-refresh', component: OverlayRefreshView },
    { path: '/tv-shows', name: 'tv-shows', component: TvShowsView },
    { path: '/tv-shows/batch-edit', name: 'tv-batch-edit', component: TvBatchEditView },
    { path: '/tv-shows/local-assets', name: 'tv-local-assets', component: LocalAssetsView },
    { path: '/tv-shows/logos', name: 'tv-logos', component: LogosView },
    { path: '/tv-shows/backdrops', name: 'tv-backdrops', component: BackdropsView },
    { path: '/tv-shows/square-art', name: 'tv-square-art', component: SquareArtView },
    { path: '/tv-shows/thumb-art', name: 'tv-thumb-art', component: ThumbArtView },
    { path: '/tv-shows/media-mirror', name: 'tv-media-mirror', component: MediaMirrorView },
    { path: '/tv-shows/overlay-refresh', name: 'tv-overlay-refresh', component: OverlayRefreshView },
    { path: '/backup', name: 'backup', component: BackupRestoreView },
    { path: '/templates', name: 'template-manager', component: TemplateManagerView },
    { path: '/overlays', name: 'overlay-config-manager', component: OverlayConfigManagerView },
    { path: '/history', name: 'history', component: HistoryView },
    { path: '/settings', name: 'settings', component: SettingsView },
    { path: '/poster-api', name: 'poster-api', component: PosterApiView },
    { path: '/logs', name: 'logs', component: LogsView }
  ]
})

// Routes that need a media server's library. In server-less mode (onboarding done, no
// server configured) they all redirect to /poster-api.
export const LIBRARY_ROUTE_NAMES = new Set([
  'movies', 'batch-edit', 'collections', 'local-assets', 'logos', 'backdrops', 'square-art',
  'thumb-art', 'media-mirror', 'overlay-refresh',
  'tv-shows', 'tv-batch-edit', 'tv-local-assets', 'tv-logos', 'tv-backdrops', 'tv-square-art',
  'tv-thumb-art', 'tv-media-mirror', 'tv-overlay-refresh',
  'history', 'backup'  // backup = per-library server artwork, nothing to do without a server
])

router.beforeEach(async (to) => {
  if (!LIBRARY_ROUTE_NAMES.has(String(to.name || ''))) return true
  const settings = useSettingsStore()
  if (!settings.loaded.value) {
    try { await settings.load() } catch { /* leave unredirected if settings can't load */ }
  }
  if (!settings.loaded.value) return true
  const { serverless } = useServerless()
  // onboardingCompleted is part of `serverless`, so a fresh install still reaches the wizard.
  return serverless.value ? { path: '/poster-api', replace: true } : true
})
