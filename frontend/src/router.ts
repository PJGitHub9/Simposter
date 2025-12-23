import { createRouter, createWebHistory } from 'vue-router'
import MoviesView from './views/MoviesView.vue'
import TvShowsView from './views/TvShowsView.vue'
import SettingsView from './views/SettingsView.vue'
import LogsView from './views/LogsView.vue'
import BatchEditView from './views/BatchEditView.vue'
import LocalAssetsView from './views/LocalAssetsView.vue'
import CollectionsView from './views/CollectionsView.vue'
import TemplateManagerView from './views/TemplateManagerView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/movies' },
    { path: '/movies', name: 'movies', component: MoviesView },
    { path: '/movies/batch-edit', name: 'batch-edit', component: BatchEditView },
    { path: '/movies/collections', name: 'collections', component: CollectionsView },
    { path: '/movies/local-assets', name: 'local-assets', component: LocalAssetsView },
    { path: '/tv-shows', name: 'tv-shows', component: TvShowsView },
    { path: '/templates', name: 'template-manager', component: TemplateManagerView },
    { path: '/settings', name: 'settings', component: SettingsView },
    { path: '/logs', name: 'logs', component: LogsView }
  ]
})
