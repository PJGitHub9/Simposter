import { createRouter, createWebHistory } from 'vue-router'
import MoviesView from './views/MoviesView.vue'
import SettingsView from './views/SettingsView.vue'
import LogsView from './views/LogsView.vue'
import BatchEditView from './views/BatchEditView.vue'
import LocalAssetsView from './views/LocalAssetsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/movies' },
    { path: '/movies', name: 'movies', component: MoviesView },
    { path: '/movies/batch-edit', name: 'batch-edit', component: BatchEditView },
    { path: '/movies/local-assets', name: 'local-assets', component: LocalAssetsView },
    { path: '/settings', name: 'settings', component: SettingsView },
    { path: '/logs', name: 'logs', component: LogsView }
  ]
})
