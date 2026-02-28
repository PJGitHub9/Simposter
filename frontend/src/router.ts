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

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/movies' },
    { path: '/movies', name: 'movies', component: MoviesView },
    { path: '/movies/batch-edit', name: 'batch-edit', component: BatchEditView },
    { path: '/movies/collections', name: 'collections', component: CollectionsView },
    { path: '/movies/local-assets', name: 'local-assets', component: LocalAssetsView },
    { path: '/tv-shows', name: 'tv-shows', component: TvShowsView },
    { path: '/tv-shows/batch-edit', name: 'tv-batch-edit', component: TvBatchEditView },
    { path: '/tv-shows/local-assets', name: 'tv-local-assets', component: LocalAssetsView },
    { path: '/backup', name: 'backup', component: BackupRestoreView },
    { path: '/templates', name: 'template-manager', component: TemplateManagerView },
    { path: '/overlays', name: 'overlay-config-manager', component: OverlayConfigManagerView },
    { path: '/history', name: 'history', component: HistoryView },
    { path: '/settings', name: 'settings', component: SettingsView },
    { path: '/logs', name: 'logs', component: LogsView }
  ]
})
