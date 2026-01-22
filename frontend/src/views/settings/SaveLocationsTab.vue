<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  movieSaveLocation: string
  tvShowSaveLocation: string
  tvShowSaveMode: string
  saveBatchInSubfolder: boolean
  unsavedChanges: boolean
}>()

const emit = defineEmits<{
  'update:movieSaveLocation': [value: string]
  'update:tvShowSaveLocation': [value: string]
  'update:tvShowSaveMode': [value: string]
  'update:saveBatchInSubfolder': [value: boolean]
  'save': []
}>()

const localMovieSaveLocation = computed({
  get: () => props.movieSaveLocation,
  set: (val) => emit('update:movieSaveLocation', val)
})

const localTvShowSaveLocation = computed({
  get: () => props.tvShowSaveLocation,
  set: (val) => emit('update:tvShowSaveLocation', val)
})

const localTvShowSaveMode = computed({
  get: () => props.tvShowSaveMode,
  set: (val) => emit('update:tvShowSaveMode', val)
})

const localSaveBatchInSubfolder = computed({
  get: () => props.saveBatchInSubfolder,
  set: (val) => emit('update:saveBatchInSubfolder', val)
})
</script>

<template>
  <div class="tab-content">
    <h2>Save Locations</h2>

    <div class="section">
      <h3>Local Asset Save Paths</h3>
      <p class="section-description">
        Configure where generated posters are saved when using "Save to Disk" feature.
        Use variables to organize files by library, title, year, etc.
      </p>

      <label>
        <span class="label-text">Movie Save Location</span>
        <input
          v-model="localMovieSaveLocation"
          type="text"
          placeholder="/config/output/{library}/{title}.jpg"
        />
        <span class="help-text">
          Available variables: <code>{library}</code>, <code>{title}</code>, <code>{year}</code>, <code>{key}</code>
        </span>
      </label>

      <label>
        <span class="label-text">TV Show Save Location</span>
        <input
          v-model="localTvShowSaveLocation"
          type="text"
          placeholder="/config/output/{library}/{title} ({year}).jpg"
        />
        <span class="help-text">
          Available variables: <code>{library}</code>, <code>{title}</code>, <code>{year}</code>
        </span>
        <span class="help-text extra-note">
          Note: Season and series naming is controlled by the "TV Show File Structure" setting below
        </span>
      </label>

      <label>
        <span class="label-text">TV Show File Structure</span>
        <select v-model="localTvShowSaveMode">
          <option value="flat">Flat - All in one folder (e.g., "Show - series.jpg", "Show - s01.jpg")</option>
          <option value="nested">Nested - Each show in its own folder (e.g., "Show/series.jpg", "Show/s01.jpg")</option>
        </select>
        <span class="help-text">
          Controls how TV show posters are organized within the save location
        </span>
      </label>

      <label class="checkbox-label">
        <input type="checkbox" v-model="localSaveBatchInSubfolder" />
        <span>Save batch operations in timestamped subfolder</span>
      </label>
      <span class="help-text checkbox-help">
        When enabled, batch saves will be organized in folders like "batch-2025-01-08-143022"
      </span>
    </div>

    <div class="section info-section">
      <h3>Path Variable Examples</h3>
      <div class="examples">
        <div class="example-item">
          <div class="example-label">Movies by library and title:</div>
          <code>/config/output/{library}/{title}.jpg</code>
          <div class="example-result">→ /config/output/4K Movies/The Matrix.jpg</div>
        </div>

        <div class="example-item">
          <div class="example-label">Movies with year:</div>
          <code>/config/output/{library}/{title} ({year}).jpg</code>
          <div class="example-result">→ /config/output/Movies/Inception (2010).jpg</div>
        </div>

        <div class="example-item">
          <div class="example-label">TV shows with year (flat structure):</div>
          <code>/config/output/{library}/{title} ({year}).jpg</code>
          <div class="example-result">→ /config/output/TV Shows/Breaking Bad (2008) - series.jpg</div>
          <div class="example-result">→ /config/output/TV Shows/Breaking Bad (2008) - s01.jpg</div>
        </div>

        <div class="example-item">
          <div class="example-label">TV shows with year (nested structure):</div>
          <code>/config/output/{library}/{title} ({year}).jpg</code>
          <div class="example-result">→ /config/output/TV Shows/Breaking Bad (2008)/series.jpg</div>
          <div class="example-result">→ /config/output/TV Shows/Breaking Bad (2008)/s01.jpg</div>
        </div>

        <div class="example-item">
          <div class="example-label">Organized by year folder:</div>
          <code>/config/output/{library}/{year}/{title}.jpg</code>
          <div class="example-result">→ /config/output/Movies/2024/Dune Part Two.jpg</div>
        </div>
      </div>
    </div>

    <div class="actions">
      <button @click="emit('save')" class="primary" :disabled="!unsavedChanges">
        {{ unsavedChanges ? 'Save Changes' : 'No Changes' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.tab-content {
  padding: 20px;
  max-width: 1600px;
}

h2 {
  margin-top: 0;
  margin-bottom: 24px;
  color: var(--text-primary);
  font-size: 24px;
}

h3 {
  margin-top: 0;
  margin-bottom: 16px;
  color: var(--text-secondary);
  font-size: 18px;
}

.section {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
}

.section-description {
  color: var(--text-muted);
  font-size: 14px;
  margin-bottom: 20px;
  line-height: 1.5;
}

.info-section {
  background: rgba(100, 200, 255, 0.03);
  border-color: rgba(100, 200, 255, 0.2);
}

label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.label-text {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 14px;
}

.help-text {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: -4px;
}

.help-text code {
  background: rgba(255, 255, 255, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 11px;
  color: var(--accent);
}

.extra-note {
  margin-top: 4px;
}

.checkbox-label {
  flex-direction: row;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  margin-bottom: 4px;
}

.checkbox-label input[type="checkbox"] {
  width: auto;
  cursor: pointer;
}

.checkbox-label span {
  font-weight: 500;
  color: var(--text-primary);
}

.checkbox-help {
  margin-left: 30px;
  margin-top: 0;
}

input[type="text"],
select {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
}

input[type="text"] {
  font-family: 'Courier New', monospace;
}

select {
  cursor: pointer;
}

select option {
  background: var(--bg-primary);
  color: var(--text-primary);
}

.examples {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.example-item {
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
}

.example-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.example-item code {
  display: block;
  background: rgba(255, 255, 255, 0.08);
  padding: 8px 12px;
  border-radius: 6px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: var(--accent);
  margin: 6px 0;
}

.example-result {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
  margin-top: 6px;
}

.actions {
  display: flex;
  gap: 12px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
}

button {
  padding: 10px 20px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

button:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.08);
  border-color: var(--accent);
}

button.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

button.primary:hover:not(:disabled) {
  opacity: 0.9;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
