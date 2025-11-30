<script setup lang="ts">
import { useSettingsStore, type Theme } from '../stores/settings'
import { useMovies } from '../composables/useMovies'
import { ref, onMounted, watch } from 'vue'

const settings = useSettingsStore()
const saved = ref('')
const allLabels = ref<string[]>([])
const { movies: moviesCache, moviesLoaded } = useMovies()

// Local state that will only be applied when save is clicked
const localTheme = ref<Theme>('neon')
const localPosterDensity = ref(20)
const localAutoSave = ref(false)
const localShowBoundingBoxes = ref(true)
const localSaveLocation = ref('')
const localDefaultLabelsToRemove = ref<string[]>([])

const loadLocalSettings = () => {
  localTheme.value = settings.theme.value
  localPosterDensity.value = settings.posterDensity.value
  localAutoSave.value = settings.autoSave.value
  localShowBoundingBoxes.value = settings.showBoundingBoxes.value
  localSaveLocation.value = settings.saveLocation.value
  localDefaultLabelsToRemove.value = [...settings.defaultLabelsToRemove.value]
}

const saveSettings = async () => {
  // Apply local settings to the store
  settings.theme.value = localTheme.value
  settings.posterDensity.value = localPosterDensity.value
  settings.autoSave.value = localAutoSave.value
  settings.showBoundingBoxes.value = localShowBoundingBoxes.value
  settings.saveLocation.value = localSaveLocation.value
  settings.defaultLabelsToRemove.value = [...localDefaultLabelsToRemove.value]

  // Save to backend
  await settings.save()
  saved.value = settings.error.value ? `Error: ${settings.error.value}` : 'Saved!'
  setTimeout(() => (saved.value = ''), 1500)
}

const clearCache = () => {
  try {
    // Clear poster cache from sessionStorage
    sessionStorage.removeItem('simposter-poster-cache')
    // Clear label cache from localStorage
    sessionStorage.removeItem('simposter-labels-cache')
    saved.value = 'Cache cleared!'
    setTimeout(() => (saved.value = ''), 1500)
  } catch (e) {
    console.error('Failed to clear cache', e)
  }
}

const scanLibrary = async () => {
  try {
    saved.value = 'Scanning library...'
    const apiBase = import.meta.env.VITE_API_URL || window.location.origin
    const res = await fetch(`${apiBase}/api/scan-library`, { method: 'POST' })
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()

    // Cache movies
    if (Array.isArray(data.movies)) {
      moviesCache.value = data.movies
      moviesLoaded.value = true
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

    saved.value = `Scanned ${data.count || 0} items!`
    setTimeout(() => (saved.value = ''), 2000)
    // Refresh label cache after scan
    await fetchAllLabels()
  } catch (e) {
    saved.value = `Scan failed: ${e instanceof Error ? e.message : 'Unknown error'}`
    setTimeout(() => (saved.value = ''), 2000)
  }
}

// Fetch all available labels from movies
const fetchAllLabels = async () => {
  try {
    const labelCache = sessionStorage.getItem('simposter-labels-cache')
    if (labelCache) {
      const cache = JSON.parse(labelCache) as Record<string, string[]>
      const labels = new Set<string>()
      Object.values(cache).forEach((movieLabels) => {
        if (Array.isArray(movieLabels)) {
          movieLabels.forEach((label) => labels.add(label))
        }
      })
      allLabels.value = Array.from(labels).sort()
    }
  } catch (e) {
    console.error('Failed to fetch labels', e)
  }
}

onMounted(async () => {
  // Ensure settings are loaded from API before syncing local form state
  if (!settings.loaded.value && !settings.loading.value) {
    await settings.load()
  }
  loadLocalSettings()
  fetchAllLabels()
})

// If settings finish loading after initial render, sync the local form
watch(
  () => settings.loaded.value,
  (val) => {
    if (val) loadLocalSettings()
  }
)

const toggleLabel = (label: string) => {
  const set = new Set(localDefaultLabelsToRemove.value)
  if (set.has(label)) {
    set.delete(label)
  } else {
    set.add(label)
  }
  localDefaultLabelsToRemove.value = Array.from(set)
}

const isLabelSelected = (label: string) => {
  return localDefaultLabelsToRemove.value.includes(label)
}
</script>

<template>
  <div class="view glass" @click.stop @mouseup.stop @mousedown.stop @select.stop @selectstart.stop>
    <h2>Settings</h2>
    <div class="grid">
      <label>
        <span>Theme</span>
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
        <span>Movies per page</span>
        <input
          v-model.number="localPosterDensity"
          type="number"
          min="5"
          max="100"
          @select.stop
          @selectstart.stop
        />
      </label>
      <label class="inline">
        <input v-model="localAutoSave" type="checkbox" />
        <span>Autosave renders</span>
      </label>
      <label class="inline">
        <input v-model="localShowBoundingBoxes" type="checkbox" />
        <span>Show bounding boxes (debug)</span>
      </label>
      <label @mousedown.stop @click.stop>
        <span>Save Location</span>
        <input
          v-model="localSaveLocation"
          type="text"
          placeholder="/output/{title} {year}/poster"
          @mousedown.stop
          @click.stop
          @mouseup.stop
          @select.stop
          @selectstart.stop
        />
        <span class="help-text">Available variables: {title}, {year}, {key}</span>
      </label>
    </div>
    <div v-if="allLabels.length > 0" class="labels-section">
      <h3>Default Labels to Remove</h3>
      <p class="section-subtitle">When sending to Plex, these labels will be removed by default</p>
      <div class="labels-grid">
        <label v-for="label in allLabels" :key="label" class="label-checkbox">
          <input type="checkbox" :checked="isLabelSelected(label)" @change="toggleLabel(label)" />
          <span>{{ label }}</span>
        </label>
      </div>
    </div>

    <div class="actions">
      <button @click="saveSettings">Save</button>
      <button @click="clearCache" class="secondary">Clear Cache</button>
      <button @click="scanLibrary" class="secondary">Scan Library</button>
      <span class="status">{{ saved }}</span>
    </div>
  </div>
</template>

<style scoped>
.view {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  color: #dbe4ff;
}

label.label-checkbox {
  flex-direction: row;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  color: #dbe4ff;
  cursor: pointer;
  transition: all 0.2s;
}

label.label-checkbox:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(61, 214, 183, 0.3);
}

.inline {
  flex-direction: row;
  align-items: center;
}

input,
select {
  border-radius: 10px;
  border: 1px solid var(--border);
  padding: 10px;
  background: rgba(255, 255, 255, 0.03);
  color: #e6edff;
}

.labels-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
}

.labels-section h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #eef2ff;
}

.section-subtitle {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}

.labels-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}

.label-checkbox input {
  cursor: pointer;
  width: auto;
  padding: 0;
  margin: 0;
}

.label-checkbox span {
  font-size: 13px;
  flex: 1;
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

button {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.05);
  color: #dce6ff;
  cursor: pointer;
}

button.secondary {
  background: rgba(255, 255, 255, 0.02);
  color: #aab4cc;
}

button.secondary:hover {
  background: rgba(255, 255, 255, 0.04);
}

.status {
  color: #a9b4d6;
}

.help-text {
  font-size: 11px;
  color: var(--muted);
  opacity: 0.7;
  font-style: italic;
}

</style>
