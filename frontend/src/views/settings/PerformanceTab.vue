<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  concurrentRenders: number
  useOverlayCache: boolean
  unsavedChanges: boolean
  scanRunning: boolean
  outputFormat: string
  jpgQuality: number
  pngCompression: number
  webpQuality: number
  tmdbRateLimit: number
  tvdbRateLimit: number
  memoryLimit: number
  webhookAutoSend: boolean
  webhookAutoLabels: string
  imageQualityChanged?: boolean
  performanceChanged?: boolean
  automationChanged?: boolean
}>()

const emit = defineEmits<{
  'update:concurrentRenders': [value: number]
  'update:useOverlayCache': [value: boolean]
  'update:outputFormat': [value: string]
  'update:jpgQuality': [value: number]
  'update:pngCompression': [value: number]
  'update:webpQuality': [value: number]
  'update:tmdbRateLimit': [value: number]
  'update:tvdbRateLimit': [value: number]
  'update:memoryLimit': [value: number]
  'update:webhookAutoSend': [value: boolean]
  'update:webhookAutoLabels': [value: string]
  'clear-frontend-cache': []
  'clear-backend-cache': []
  'save': []
}>()

const localConcurrentRenders = computed({
  get: () => props.concurrentRenders,
  set: (val) => emit('update:concurrentRenders', val)
})

const localUseOverlayCache = computed({
  get: () => props.useOverlayCache,
  set: (val) => emit('update:useOverlayCache', val)
})

const localOutputFormat = computed({
  get: () => props.outputFormat,
  set: (val) => emit('update:outputFormat', val)
})

const localJpgQuality = computed({
  get: () => props.jpgQuality,
  set: (val) => emit('update:jpgQuality', val)
})

const localPngCompression = computed({
  get: () => props.pngCompression,
  set: (val) => emit('update:pngCompression', val)
})

const localWebpQuality = computed({
  get: () => props.webpQuality,
  set: (val) => emit('update:webpQuality', val)
})

const localTmdbRateLimit = computed({
  get: () => props.tmdbRateLimit,
  set: (val) => emit('update:tmdbRateLimit', val)
})

const localTvdbRateLimit = computed({
  get: () => props.tvdbRateLimit,
  set: (val) => emit('update:tvdbRateLimit', val)
})

const localMemoryLimit = computed({
  get: () => props.memoryLimit,
  set: (val) => emit('update:memoryLimit', val)
})

const localWebhookAutoSend = computed({
  get: () => props.webhookAutoSend,
  set: (val) => emit('update:webhookAutoSend', val)
})

const localWebhookAutoLabels = computed({
  get: () => props.webhookAutoLabels,
  set: (val) => emit('update:webhookAutoLabels', val)
})

</script>

<template>
  <div class="tab-content">
    <h2>Image Quality & Performance</h2>

    <!-- Image Quality Settings -->
    <div class="section" :class="{ 'unsaved-changes': imageQualityChanged }">
      <h3>Image Quality</h3>
      <p class="section-description">
        Configure output format and compression settings
      </p>

      <label>
        <span class="label-text">Output Format</span>
        <select v-model="localOutputFormat">
          <option value="jpg">JPEG</option>
          <option value="png">PNG</option>
          <option value="webp">WebP</option>
        </select>
      </label>

      <div v-if="localOutputFormat === 'jpg'" class="quality-control">
        <label>
          <span class="label-text">JPEG Quality: {{ localJpgQuality }}%</span>
          <input
            type="range"
            v-model.number="localJpgQuality"
            min="1"
            max="100"
            step="1"
          />
          <span class="help-text">Higher = better quality, larger file size</span>
        </label>
      </div>

      <div v-if="localOutputFormat === 'png'" class="quality-control">
        <label>
          <span class="label-text">PNG Compression: {{ localPngCompression }}</span>
          <input
            type="range"
            v-model.number="localPngCompression"
            min="0"
            max="9"
            step="1"
          />
          <span class="help-text">0 = no compression (fast), 9 = max compression (slow)</span>
        </label>
      </div>

      <div v-if="localOutputFormat === 'webp'" class="quality-control">
        <label>
          <span class="label-text">WebP Quality: {{ localWebpQuality }}</span>
          <input
            type="range"
            v-model.number="localWebpQuality"
            min="1"
            max="100"
            step="1"
          />
          <span class="help-text">Higher = better quality, larger file size</span>
        </label>
      </div>
    </div>

    <!-- Rendering Performance -->
    <div class="section" :class="{ 'unsaved-changes': performanceChanged }">
      <h3>Rendering Performance</h3>
      <p class="section-description">
        Configure rendering options to optimize speed and quality balance.
      </p>

      <label class="checkbox-label">
        <input type="checkbox" v-model="localUseOverlayCache" />
        <span>Use Overlay Cache</span>
      </label>
      <span class="help-text checkbox-help">
        Pre-generate template effect overlays for 3-5x faster batch rendering. Recommended for most users.
      </span>

      <label>
        <span class="label-text">Concurrent Rendering: {{ localConcurrentRenders }}</span>
        <input
          type="range"
          v-model.number="localConcurrentRenders"
          min="1"
          max="10"
          step="1"
        />
        <span class="help-text">
          Number of posters to render simultaneously during batch operations. Higher = faster but more CPU usage.
        </span>
      </label>

      <label>
        <span class="label-text">Memory Limit: {{ localMemoryLimit }} MB</span>
        <input
          type="range"
          v-model.number="localMemoryLimit"
          min="512"
          max="8192"
          step="256"
        />
        <span class="help-text">Maximum memory to use during batch operations</span>
      </label>
    </div>

    <!-- API Rate Limits -->
    <div class="section">
      <h3>API Rate Limits</h3>
      <p class="section-description">
        Control request rates to external APIs (per 10 seconds)
      </p>

      <label>
        <span class="label-text">TMDb Rate Limit: {{ localTmdbRateLimit }} req/10s</span>
        <input
          type="range"
          v-model.number="localTmdbRateLimit"
          min="5"
          max="100"
          step="5"
        />
        <span class="help-text">Default: 40 (TMDb free tier: 40 req/10s)</span>
      </label>

      <label>
        <span class="label-text">TVDB Rate Limit: {{ localTvdbRateLimit }} req/10s</span>
        <input
          type="range"
          v-model.number="localTvdbRateLimit"
          min="5"
          max="100"
          step="5"
        />
        <span class="help-text">Default: 20 (TVDB free tier: 20 req/10s)</span>
      </label>
    </div>

    <!-- Automatic Poster Generation -->
    <div class="section" :class="{ 'unsaved-changes': automationChanged }">
      <h3>Automatic Poster Generation</h3>
      <p class="section-description">
        Configure automatic poster generation and delivery via webhooks (Radarr, Sonarr, Tautulli).
        Webhooks automatically trigger poster generation when new media is added.
      </p>

      <label class="checkbox-label">
        <input type="checkbox" v-model="localWebhookAutoSend" />
        <span>Automatically Send to Plex</span>
      </label>
      <p class="help-text" style="margin: -8px 0 16px 0;">
        When enabled, webhook-generated posters are automatically sent to Plex and replace the existing poster
      </p>

      <label>
        <span class="label-text">Default Labels for Webhook Posters</span>
        <input
          type="text"
          v-model="localWebhookAutoLabels"
          placeholder="Simposter, Auto"
        />
        <span class="help-text">Comma-separated list of labels to apply to webhook-generated posters (e.g., "Simposter, Auto")</span>
      </label>
    </div>

    <!-- Cache Management -->
    <div class="section">
      <h3>Cache Management</h3>
      <p class="section-description">
        Clear cached data to free up space or troubleshoot issues. All caches will rebuild automatically when needed.
      </p>

      <div class="cache-actions">
        <div class="cache-action-item">
          <div class="cache-info">
            <strong>Frontend Cache</strong>
            <p>Clears browser session storage (movies, posters, labels)</p>
          </div>
          <button
            @click="emit('clear-frontend-cache')"
            :disabled="scanRunning"
            class="secondary"
          >
            Clear Frontend Cache
          </button>
        </div>

        <div class="cache-action-item">
          <div class="cache-info">
            <strong>Backend Cache</strong>
            <p>Clears server cache and database (poster files, metadata cache)</p>
          </div>
          <button
            @click="emit('clear-backend-cache')"
            :disabled="scanRunning"
            class="danger"
          >
            Clear Backend Cache
          </button>
        </div>
      </div>

      <div v-if="scanRunning" class="warning-message">
        ⚠️ Cache operations are disabled while a library scan is in progress
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

h4 {
  margin-top: 0;
  margin-bottom: 12px;
  color: var(--text-secondary);
  font-size: 16px;
}

.section {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.section.unsaved-changes {
  background: rgba(255, 200, 0, 0.08);
  border-color: rgba(255, 200, 0, 0.4);
}

.section-description {
  color: var(--text-muted);
  font-size: 13px;
  margin: -8px 0 16px 0;
  line-height: 1.5;
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

.checkbox-label {
  flex-direction: row;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  cursor: pointer;
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
  margin-left: 24px;
  margin-top: -12px;
}

select,
input[type="text"],
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

select:focus {
  outline: none;
  border-color: var(--accent);
  background: rgba(255, 255, 255, 0.06);
}

input[type="text"] {
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
}

input[type="text"]:focus {
  outline: none;
  border-color: var(--accent);
  background: rgba(255, 255, 255, 0.06);
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

input[type="range"]::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  border: none;
}

.quality-control {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.cache-actions {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cache-action-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.cache-info {
  flex: 1;
}

.cache-info strong {
  display: block;
  color: var(--text-primary);
  font-size: 14px;
  margin-bottom: 4px;
}

.cache-info p {
  color: var(--text-muted);
  font-size: 13px;
  margin: 0;
}

.warning-message {
  padding: 12px;
  background: rgba(255, 200, 0, 0.1);
  border: 1px solid rgba(255, 200, 0, 0.3);
  border-radius: 8px;
  color: #ffb000;
  font-size: 14px;
  margin-top: 16px;
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
  white-space: nowrap;
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

button.secondary {
  background: rgba(255, 255, 255, 0.06);
}

button.danger {
  background: rgba(255, 0, 0, 0.1);
  border-color: rgba(255, 0, 0, 0.3);
  color: #ff6b6b;
}

button.danger:hover:not(:disabled) {
  background: rgba(255, 0, 0, 0.2);
  border-color: #ff6b6b;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
