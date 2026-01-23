<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  theme: string
  posterDensity: number
  deduplicateMovies: boolean
  timezone: string
  tmdbApiKey: string
  tvdbApiKey: string
  fanartApiKey: string
  unsavedChanges: boolean
  testingKeys?: Record<string, boolean>
  apiKeyTestResults?: Record<string, string>
}>()

const emit = defineEmits<{
  'update:theme': [value: string]
  'update:posterDensity': [value: number]
  'update:deduplicateMovies': [value: boolean]
  'update:timezone': [value: string]
  'update:tmdbApiKey': [value: string]
  'update:tvdbApiKey': [value: string]
  'update:fanartApiKey': [value: string]
  'test-api-key': [keyType: string, apiKey: string]
  'save': []
}>()

const localTheme = computed({
  get: () => props.theme,
  set: (val) => emit('update:theme', val)
})

const localPosterDensity = computed({
  get: () => props.posterDensity,
  set: (val) => emit('update:posterDensity', val)
})

const localDeduplicateMovies = computed({
  get: () => props.deduplicateMovies,
  set: (val) => emit('update:deduplicateMovies', val)
})

const localTimezone = computed({
  get: () => props.timezone,
  set: (val) => emit('update:timezone', val)
})

const localTmdbApiKey = computed({
  get: () => props.tmdbApiKey,
  set: (val) => emit('update:tmdbApiKey', val)
})

const localTvdbApiKey = computed({
  get: () => props.tvdbApiKey,
  set: (val) => emit('update:tvdbApiKey', val)
})

const localFanartApiKey = computed({
  get: () => props.fanartApiKey,
  set: (val) => emit('update:fanartApiKey', val)
})

// Common timezones list
const timezones = [
  { value: 'UTC', label: 'UTC (Coordinated Universal Time)' },
  { value: 'America/New_York', label: 'Eastern Time (US & Canada)' },
  { value: 'America/Chicago', label: 'Central Time (US & Canada)' },
  { value: 'America/Denver', label: 'Mountain Time (US & Canada)' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (US & Canada)' },
  { value: 'America/Anchorage', label: 'Alaska' },
  { value: 'Pacific/Honolulu', label: 'Hawaii' },
  { value: 'Europe/London', label: 'London' },
  { value: 'Europe/Paris', label: 'Paris, Berlin, Madrid' },
  { value: 'Europe/Athens', label: 'Athens, Istanbul' },
  { value: 'Europe/Moscow', label: 'Moscow' },
  { value: 'Asia/Dubai', label: 'Dubai' },
  { value: 'Asia/Kolkata', label: 'India' },
  { value: 'Asia/Shanghai', label: 'Beijing, Shanghai' },
  { value: 'Asia/Tokyo', label: 'Tokyo' },
  { value: 'Asia/Seoul', label: 'Seoul' },
  { value: 'Australia/Sydney', label: 'Sydney' },
  { value: 'Pacific/Auckland', label: 'Auckland' },
]
</script>

<template>
  <div class="tab-content">
    <h2>General Settings</h2>

    <div class="section">
      <h3>Appearance</h3>

      <label>
        <span class="label-text">Theme</span>
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
        <span class="label-text">Poster Grid Density: {{ localPosterDensity }}</span>
        <input
          type="range"
          v-model.number="localPosterDensity"
          min="10"
          max="40"
          step="1"
        />
        <span class="help-text">Adjust spacing between posters in grid view</span>
      </label>

      <label>
        <span class="label-text">Timezone</span>
        <select v-model="localTimezone">
          <option v-for="tz in timezones" :key="tz.value" :value="tz.value">
            {{ tz.label }}
          </option>
        </select>
        <span class="help-text">Used for scheduling and timestamps in history</span>
      </label>
    </div>

    <div class="section">
      <h3>Library Display</h3>
      <p class="section-description">
        Configure how movies are displayed in the library view.
      </p>

      <label class="checkbox-label">
        <input type="checkbox" v-model="localDeduplicateMovies" />
        <span>Hide duplicate movies (multiple editions)</span>
      </label>
      <span class="help-text checkbox-help">
        When enabled, only shows the most recently added version when you have multiple editions of the same movie (e.g., Extended Edition, Director's Cut). Useful for cleaner library views when you have duplicate movies with the same TMDb ID.
      </span>
    </div>

    <div class="section">
      <h3>API Keys</h3>
      <p class="section-description">
        Configure API keys for accessing metadata from external services.
      </p>

      <div class="api-keys-grid">
        <label>
          <span class="label-text">TMDb API Key <span class="required">*</span></span>
          <div class="input-with-button">
            <input
              v-model="localTmdbApiKey"
              type="password"
              placeholder="Enter your TMDb API key"
            />
            <button
              @click="emit('test-api-key', 'tmdb', localTmdbApiKey)"
              class="secondary"
              :disabled="!localTmdbApiKey || testingKeys?.tmdb"
              type="button"
            >
              {{ testingKeys?.tmdb ? 'Testing...' : 'Test' }}
            </button>
          </div>
          <span v-if="apiKeyTestResults?.tmdb" :class="['api-test-result', apiKeyTestResults.tmdb.includes('error') || apiKeyTestResults.tmdb.includes('Error') ? 'error' : 'success']">
            {{ apiKeyTestResults.tmdb }}
          </span>
          <span class="help-text">Required for movie and TV show posters and metadata. Get one at <a href="https://www.themoviedb.org/settings/api" target="_blank">tmdb.org</a></span>
        </label>

        <label>
          <span class="label-text">TVDB API Key</span>
          <div class="input-with-button">
            <input
              v-model="localTvdbApiKey"
              type="password"
              placeholder="Enter your TVDB API key"
            />
            <button
              @click="emit('test-api-key', 'tvdb', localTvdbApiKey)"
              class="secondary"
              :disabled="!localTvdbApiKey || testingKeys?.tvdb"
              type="button"
            >
              {{ testingKeys?.tvdb ? 'Testing...' : 'Test' }}
            </button>
          </div>
          <span v-if="apiKeyTestResults?.tvdb" :class="['api-test-result', apiKeyTestResults.tvdb.includes('error') || apiKeyTestResults.tvdb.includes('Error') ? 'error' : 'success']">
            {{ apiKeyTestResults.tvdb }}
          </span>
          <span class="help-text">Required for TV. Provides TV show artwork. Get one at <a href="https://www.thetvdb.com/api" target="_blank">thetvdb.com</a></span>
        </label>

        <label>
          <span class="label-text">Fanart.tv API Key</span>
          <div class="input-with-button">
            <input
              v-model="localFanartApiKey"
              type="password"
              placeholder="Enter your Fanart.tv API key"
            />
            <button
              @click="emit('test-api-key', 'fanart', localFanartApiKey)"
              class="secondary"
              :disabled="!localFanartApiKey || testingKeys?.fanart"
              type="button"
            >
              {{ testingKeys?.fanart ? 'Testing...' : 'Test' }}
            </button>
          </div>
          <span v-if="apiKeyTestResults?.fanart" :class="['api-test-result', apiKeyTestResults.fanart.includes('error') || apiKeyTestResults.fanart.includes('Error') ? 'error' : 'success']">
            {{ apiKeyTestResults.fanart }}
          </span>
          <span class="help-text">Optional. Provides high-quality clearlogos and artwork. Get one at <a href="https://fanart.tv/api/" target="_blank">fanart.tv</a></span>
        </label>
      </div>

      <div class="api-test-section">
      </div>
    </div>

    <div class="section">
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

.help-text a {
  color: var(--accent);
  text-decoration: none;
}

.help-text a:hover {
  text-decoration: underline;
}

.api-keys-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

@media (max-width: 1200px) {
  .api-keys-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .api-keys-grid {
    grid-template-columns: 1fr;
  }
}

.api-test-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.api-test-result {
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  font-weight: 500;
}

.api-test-result.success {
  background: rgba(76, 175, 80, 0.15);
  color: #4caf50;
  border: 1px solid rgba(76, 175, 80, 0.3);
}

.api-test-result.error {
  background: rgba(255, 71, 87, 0.15);
  color: #ff4757;
  border: 1px solid rgba(255, 71, 87, 0.3);
}

select,
input[type="range"] {
  width: 100%;
  max-width: 400px;
}

input[type="text"],
input[type="password"] {
  width: 100%;
  max-width: 400px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
}

input[type="text"]:focus,
input[type="password"]:focus {
  outline: none;
  border-color: var(--accent);
  background: rgba(255, 255, 255, 0.06);
}

.input-with-button {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.input-with-button input {
  flex: 1;
  margin: 0;
}

.input-with-button button {
  padding: 10px 16px;
  white-space: nowrap;
  margin-top: 0;
  height: 40px;
}

.required {
  color: #ff6b6b;
}

.section-description {
  margin: -8px 0 16px 0;
  color: var(--text-muted);
  font-size: 13px;
}

select,
input[type="range"] {
  width: 100%;
  max-width: 400px;
}

select {
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
}

input[type="range"] {
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  outline: none;
}

input[type="range"]::-webkit-slider-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
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
