import { createRouter, createWebHistory } from 'vue-router'
import MoviesView from './views/MoviesView.vue'
import SettingsView from './views/SettingsView.vue'
import LogsView from './views/LogsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/movies' },
    { path: '/movies', name: 'movies', component: MoviesView },
    { path: '/settings', name: 'settings', component: SettingsView },
    { path: '/logs', name: 'logs', component: LogsView }
  ]
})
