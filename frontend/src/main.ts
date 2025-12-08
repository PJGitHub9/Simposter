import './assets/main.css'

import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import { APP_VERSION } from './version'

document.title = `Simposter (${APP_VERSION})`

createApp(App).use(router).mount('#app')
