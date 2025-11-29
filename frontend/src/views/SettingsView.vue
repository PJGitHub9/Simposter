<script setup lang="ts">
import { useSettingsStore } from '../stores/settings'
import { ref, onMounted } from 'vue'

const settings = useSettingsStore()
const saved = ref('')
const allLabels = ref<string[]>([])

const saveSettings = () => {
  settings.save()
  saved.value = 'Saved'
  setTimeout(() => (saved.value = ''), 1500)
}

const clearCache = () => {
  try {
    // Clear poster cache from sessionStorage
    sessionStorage.removeItem('simposter-poster-cache')
    // Clear label cache from localStorage
    sessionStorage.removeItem('simposter-labels-cache')
    saved.value = 'Cache cleared'
    setTimeout(() => (saved.value = ''), 1500)
  } catch (e) {
    console.error('Failed to clear cache', e)
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

onMounted(() => {
  fetchAllLabels()
})

const toggleLabel = (label: string) => {
  const set = new Set(settings.defaultLabelsToRemove.value)
  if (set.has(label)) {
    set.delete(label)
  } else {
    set.add(label)
  }
  settings.defaultLabelsToRemove.value = Array.from(set)
}

const isLabelSelected = (label: string) => {
  return settings.defaultLabelsToRemove.value.includes(label)
}
</script>

<template>
  <div class="view glass">
    <h2>Settings</h2>
    <div class="grid">
      <label>
        <span>Theme</span>
        <select v-model="settings.theme.value">
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
        <input v-model.number="settings.posterDensity.value" type="number" min="5" max="100" />
      </label>
      <label class="inline">
        <input v-model="settings.autoSave.value" type="checkbox" />
        <span>Autosave renders</span>
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
</style>
