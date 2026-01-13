<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  concurrentRenders: number
  useOverlayCache: boolean
  unsavedChanges: boolean
  scanRunning: boolean
}>()

const emit = defineEmits<{
  'update:concurrentRenders': [value: number]
  'update:useOverlayCache': [value: boolean]
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
</script>

<template>
  <div class="tab-content">
    <h2>Performance Settings</h2>

    <div class="section">
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
    </div>

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

    <div class="section info-section">
      <h3>Performance Tips</h3>
      <ul class="tips-list">
        <li>
          <strong>Overlay Cache:</strong> Keep enabled for best performance with uniformlogo and similar templates
        </li>
        <li>
          <strong>Concurrent Renders:</strong> Set to 3-5 for balanced performance. Higher values use more memory.
        </li>
        <li>
          <strong>Clear Frontend Cache:</strong> If posters aren't updating, clear frontend cache first (quick fix)
        </li>
        <li>
          <strong>Clear Backend Cache:</strong> Only needed when troubleshooting metadata issues or freeing disk space
        </li>
        <li>
          <strong>Database Indexing:</strong> Simposter uses optimized database indexes for 5-10x faster queries
        </li>
      </ul>
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
  margin-bottom: 16px;
}

input[type="range"] {
  width: 100%;
  max-width: 400px;
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

.tips-list {
  margin: 0;
  padding-left: 20px;
  color: var(--text-muted);
  font-size: 14px;
  line-height: 1.8;
}

.tips-list li {
  margin-bottom: 12px;
}

.tips-list strong {
  color: var(--text-primary);
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
