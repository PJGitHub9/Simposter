<script setup lang="ts">
import { computed, ref } from 'vue'
import { launchOnboarding } from '@/composables/useOnboardingLauncher'

interface APISource {
  id: string
  name: string
}

const props = defineProps<{
  dbExporting: boolean
  dbImporting: boolean
  showDbImportModal: boolean
  dbImportText: string
  apiOrder: string[]
  unsavedChanges: boolean
  dbExportIncludeSecrets: boolean
}>()

const emit = defineEmits<{
  'update:showDbImportModal': [value: boolean]
  'update:dbImportText': [value: string]
  'update:apiOrder': [value: string[]]
  'update:dbExportIncludeSecrets': [value: boolean]
  'export-db': []
  'import-db': []
  'save': []
}>()

const localDbExportIncludeSecrets = computed({
  get: () => props.dbExportIncludeSecrets,
  set: (val) => emit('update:dbExportIncludeSecrets', val)
})

const localShowDbImportModal = computed({
  get: () => props.showDbImportModal,
  set: (val) => emit('update:showDbImportModal', val)
})

const localDbImportText = computed({
  get: () => props.dbImportText,
  set: (val) => emit('update:dbImportText', val)
})

// Backup file picked in the import modal
const dbImportFileName = ref('')
const dbImportFileError = ref('')
const dbImportSummary = computed(() => {
  if (!localDbImportText.value.trim()) return ''
  try {
    const d = JSON.parse(localDbImportText.value)
    if (!d || typeof d !== 'object' || !d.settings || !Array.isArray(d.presets)) return ''
    const parts = [
      `${Object.keys(d.settings).length} settings`,
      `${d.presets.length} presets`
    ]
    if (d.overlays) {
      parts.push(`${(d.overlays.configs || []).length} overlays`)
      parts.push(`${(d.overlays.assets || []).length} overlay images`)
    }
    const when = d.exported_at ? ` from ${new Date(d.exported_at).toLocaleString()}` : ''
    const version = d.app_version ? ` (${d.app_version})` : ''
    const keys = d.secrets_included ? '' : '. No API keys in this file; your current ones are kept.'
    return `Backup${when}${version}: ${parts.join(', ')}${keys}`
  } catch {
    return ''
  }
})

const onDbImportFile = async (e: Event) => {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  dbImportFileError.value = ''
  if (!file) return
  dbImportFileName.value = file.name
  try {
    const text = await file.text()
    let d: unknown
    try {
      d = JSON.parse(text)
    } catch {
      throw new Error('Could not read this file as JSON')
    }
    const obj = d as { settings?: unknown; presets?: unknown }
    if (!obj || typeof obj !== 'object' || !obj.settings || !Array.isArray(obj.presets)) {
      throw new Error('This file is not a Simposter database backup')
    }
    localDbImportText.value = text
  } catch (err) {
    localDbImportText.value = ''
    dbImportFileError.value = err instanceof Error ? err.message : 'Could not read this file'
  } finally {
    input.value = ''
  }
}

const closeDbImport = () => {
  localShowDbImportModal.value = false
  localDbImportText.value = ''
  dbImportFileName.value = ''
  dbImportFileError.value = ''
}

const localApiOrder = computed({
  get: () => props.apiOrder,
  set: (val) => emit('update:apiOrder', val)
})

const apiOrderLocked = ref(true)
const draggedApi = ref<string | null>(null)

const availableAPIs: APISource[] = [
  { id: 'tmdb', name: 'TMDb' },
  { id: 'tvdb', name: 'TVDB' },
  { id: 'fanart', name: 'Fanart.tv' }
]

const startDrag = (api: string) => {
  draggedApi.value = api
}

const onDrop = (targetApi: string) => {
  if (!draggedApi.value || draggedApi.value === targetApi || apiOrderLocked.value) return

  const draggedIndex = localApiOrder.value.indexOf(draggedApi.value)
  const targetIndex = localApiOrder.value.indexOf(targetApi)

  if (draggedIndex > -1 && targetIndex > -1) {
    const newOrder = [...localApiOrder.value]
    const temp = newOrder[draggedIndex]
    newOrder[draggedIndex] = newOrder[targetIndex]!
    newOrder[targetIndex] = temp!
    localApiOrder.value = newOrder
  }

  draggedApi.value = null
}

const moveApiUp = (api: string) => {
  if (apiOrderLocked.value) return
  const index = localApiOrder.value.indexOf(api)
  if (index > 0) {
    const newOrder = [...localApiOrder.value]
    const temp = newOrder[index]
    newOrder[index] = newOrder[index - 1]!
    newOrder[index - 1] = temp!
    localApiOrder.value = newOrder
  }
}

const moveApiDown = (api: string) => {
  if (apiOrderLocked.value) return
  const index = localApiOrder.value.indexOf(api)
  if (index < localApiOrder.value.length - 1) {
    const newOrder = [...localApiOrder.value]
    const temp = newOrder[index]
    newOrder[index] = newOrder[index + 1]!
    newOrder[index + 1] = temp!
    localApiOrder.value = newOrder
  }
}
</script>

<template>
  <div class="tab-content">
    <h2>Advanced Settings</h2>

    <!-- Setup Wizard -->
    <div class="section">
      <h3>Setup Wizard</h3>
      <p class="section-description">
        Re-run the first-time setup wizard — useful if you skipped it, or want to redo Plex/library setup or re-import the starter presets.
      </p>

      <div class="preset-actions">
        <div class="preset-action-item">
          <div class="preset-info">
            <strong>Run Startup Wizard</strong>
            <p>Walks through media server connections, library selection, API keys, and starter presets again. Your existing settings aren't cleared — you'll just be stepping through the same screens.</p>
          </div>
          <button @click="launchOnboarding" class="secondary">
            Run Startup Wizard
          </button>
        </div>
      </div>
    </div>

    <!-- API Source Priority -->
    <div class="section">
      <h3>API Source Priority</h3>
      <p class="section-description">
        Reorder which API to use first when fetching artwork (drag to reorder)
      </p>

      <div class="api-order-header">
        <span>Priority Order</span>
        <button
          @click="apiOrderLocked = !apiOrderLocked"
          class="lock-btn"
          :class="{ locked: apiOrderLocked }"
          type="button"
        >
          {{ apiOrderLocked ? '🔒 Locked' : '🔓 Unlock' }}
        </button>
      </div>

      <div class="api-order-list">
        <div
          v-for="(apiId, index) in localApiOrder"
          :key="apiId"
          class="api-order-item"
          :class="{ disabled: apiOrderLocked, dragging: draggedApi === apiId }"
          draggable="true"
          @dragstart="startDrag(apiId)"
          @dragover.prevent
          @drop="onDrop(apiId)"
        >
          <span class="api-index">{{ index + 1 }}</span>
          <span class="api-name">{{ availableAPIs.find(a => a.id === apiId)?.name || apiId }}</span>
          <div class="api-controls" v-if="!apiOrderLocked">
            <button
              @click="moveApiUp(apiId)"
              :disabled="index === 0"
              class="arrow-btn"
              type="button"
            >
              ↑
            </button>
            <button
              @click="moveApiDown(apiId)"
              :disabled="index === localApiOrder.length - 1"
              class="arrow-btn"
              type="button"
            >
              ↓
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="section">
      <h3>Database Backup</h3>
      <p class="section-description">
        Export and import your Simposter settings, presets and overlays (with their badge images) as one JSON file.
      </p>

      <div class="preset-actions">
        <div class="preset-action-item">
          <div class="preset-info">
            <strong>Export Database</strong>
            <p>Download complete database backup as a JSON file for backup or migration</p>
            <label class="checkbox-label" style="margin-top: 8px;">
              <input type="checkbox" v-model="localDbExportIncludeSecrets" />
              <span>Include API keys and tokens (Plex token, Jellyfin/Emby keys, TMDb/TVDB/Fanart keys, webhook secret)</span>
            </label>
            <p class="help-text" v-if="localDbExportIncludeSecrets">
              The exported file will contain your credentials in plain text — store it securely.
            </p>
            <p class="help-text" v-else>
              Credentials will be left out of the export. Restoring it on this install keeps your current keys; on a new install you'll need to re-enter them.
            </p>
          </div>
          <button
            @click="emit('export-db')"
            :disabled="dbExporting"
            class="secondary"
          >
            {{ dbExporting ? 'Exporting...' : 'Export Database' }}
          </button>
        </div>

        <div class="preset-action-item">
          <div class="preset-info">
            <strong>Import Database</strong>
            <p>Restore database from a backup file (will replace current database)</p>
          </div>
          <button
            @click="localShowDbImportModal = true"
            class="secondary"
          >
            Import Database
          </button>
        </div>
      </div>
    </div>

    <div class="section info-section">
      <h3>What's Included in Database Export</h3>
      <ul class="included-list">
        <li><strong>All Settings:</strong> media server connections, library groups, save locations, automation, notifications and schedules (API keys only if you tick the box)</li>
        <li><strong>Template Presets:</strong> every preset, including season settings</li>
        <li><strong>Overlays:</strong> every overlay and the badge images it uses</li>
        <li><strong>Not included:</strong> poster/logo caches, history and the retry queue. Run a library scan after restoring to rebuild the caches.</li>
      </ul>
      <div class="note">
        <strong>⚠️ Warning:</strong> Importing a database will completely replace your current configuration.
        Make sure to export your current database first as a backup before importing.
      </div>
    </div>

    <!-- Import Modal -->
    <div v-if="localShowDbImportModal" class="modal-overlay" @click.self="!dbImporting && closeDbImport()">
      <div class="modal">
        <div class="modal-header">
          <h3>Import Database</h3>
          <button class="close-btn" :disabled="dbImporting" @click="closeDbImport">×</button>
        </div>

        <div class="modal-body">
          <p class="modal-description">
            ⚠️ <strong>Warning:</strong> This replaces your current settings, presets and overlays. Export a backup first if you might want them back.
          </p>

          <label class="file-pick">
            <input type="file" accept=".json,application/json" @change="onDbImportFile" />
            <span class="file-pick-btn">Choose backup file…</span>
            <span class="file-pick-name">{{ dbImportFileName || 'No file selected' }}</span>
          </label>
          <p v-if="dbImportFileError" class="file-error">{{ dbImportFileError }}</p>
          <p v-else-if="dbImportSummary" class="file-summary">{{ dbImportSummary }}</p>
        </div>

        <div class="modal-actions">
          <button
            @click="closeDbImport"
            class="secondary"
            :disabled="dbImporting"
          >
            Cancel
          </button>
          <button
            @click="emit('import-db')"
            class="primary"
            :disabled="dbImporting || !dbImportSummary"
          >
            {{ dbImporting ? 'Importing...' : 'Import Database' }}
          </button>
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

.preset-actions {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.preset-action-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.preset-info {
  flex: 1;
}

.preset-info strong {
  display: block;
  color: var(--text-primary);
  font-size: 14px;
  margin-bottom: 4px;
}

.preset-info p {
  color: var(--text-muted);
  font-size: 13px;
  margin: 0;
}

.included-list {
  margin: 0;
  padding-left: 20px;
  color: var(--text-muted);
  font-size: 14px;
  line-height: 1.8;
}

.included-list li {
  margin-bottom: 8px;
}

.included-list strong {
  color: var(--text-primary);
}

.note {
  margin-top: 16px;
  padding: 12px;
  background: rgba(255, 200, 0, 0.1);
  border: 1px solid rgba(255, 200, 0, 0.3);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-muted);
  line-height: 1.6;
}

.note strong {
  color: #ffb000;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal {
  background: var(--bg-secondary, #1a1a1a);
  border: 1px solid var(--border);
  border-radius: 12px;
  width: 100%;
  max-width: 700px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid var(--border);
}

.modal-header h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 18px;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 32px;
  line-height: 1;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary);
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.file-pick {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 0 6px;
  cursor: pointer;
}

.file-pick input[type='file'] {
  display: none;
}

.file-pick-btn {
  flex-shrink: 0;
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-primary, #eef2ff);
  font-size: 13px;
  font-weight: 600;
}

.file-pick:hover .file-pick-btn {
  border-color: rgba(61, 214, 183, 0.5);
}

.file-pick-name {
  min-width: 0;
  color: var(--muted);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-summary {
  margin: 6px 0 0;
  font-size: 13px;
  color: #3dd6b7;
}

.file-error {
  margin: 6px 0 0;
  font-size: 13px;
  color: #ff6b6b;
}

.modal-description {
  color: var(--text-muted);
  font-size: 14px;
  margin-bottom: 16px;
  line-height: 1.5;
}



.modal-actions {
  display: flex;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid var(--border);
  justify-content: flex-end;
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

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* API Order Styles */
.api-order-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.lock-btn {
  padding: 6px 12px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  cursor: pointer;
}

.lock-btn.locked {
  background: rgba(255, 193, 7, 0.1);
  border-color: rgba(255, 193, 7, 0.3);
}

.api-order-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.api-order-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: grab;
  transition: all 0.2s;
}

.api-order-item:hover:not(.disabled) {
  background: rgba(255, 255, 255, 0.04);
  border-color: var(--accent);
}

.api-order-item.dragging {
  opacity: 0.5;
}

.api-order-item.disabled {
  cursor: default;
  opacity: 0.7;
}

.api-index {
  font-weight: bold;
  color: var(--accent);
  min-width: 24px;
  text-align: center;
}

.api-name {
  flex: 1;
  color: var(--text-primary);
  font-weight: 500;
}

.api-controls {
  display: flex;
  gap: 4px;
}

.arrow-btn {
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-primary);
  cursor: pointer;
  font-size: 12px;
  max-width: 32px;
}

.arrow-btn:hover:not(:disabled) {
  background: var(--accent);
  border-color: var(--accent);
}

.arrow-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
</style>
