<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  dbExporting: boolean
  dbImporting: boolean
  showDbImportModal: boolean
  dbImportText: string
  unsavedChanges: boolean
}>()

const emit = defineEmits<{
  'update:showDbImportModal': [value: boolean]
  'update:dbImportText': [value: string]
  'export-db': []
  'import-db': []
  'save': []
}>()

const localShowDbImportModal = computed({
  get: () => props.showDbImportModal,
  set: (val) => emit('update:showDbImportModal', val)
})

const localDbImportText = computed({
  get: () => props.dbImportText,
  set: (val) => emit('update:dbImportText', val)
})
</script>

<template>
  <div class="tab-content">
    <h2>Advanced Settings</h2>

    <div class="section">
      <h3>Database Backup</h3>
      <p class="section-description">
        Export and import your complete Simposter database. Includes all settings, presets, templates, and configurations.
      </p>

      <div class="preset-actions">
        <div class="preset-action-item">
          <div class="preset-info">
            <strong>Export Database</strong>
            <p>Download complete database backup as a JSON file for backup or migration</p>
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
        <li><strong>All Settings:</strong> UI settings, Plex connection, API keys, save locations, performance settings</li>
        <li><strong>Template Presets:</strong> All custom presets with template options and season configurations</li>
        <li><strong>Scheduler Settings:</strong> Cron schedules and library scan configurations</li>
        <li><strong>Cache Data:</strong> Movie and TV show metadata cache (optional, can be excluded)</li>
      </ul>
      <div class="note">
        <strong>⚠️ Warning:</strong> Importing a database will completely replace your current configuration.
        Make sure to export your current database first as a backup before importing.
      </div>
    </div>

    <!-- Import Modal -->
    <div v-if="localShowDbImportModal" class="modal-overlay" @click.self="localShowDbImportModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>Import Database</h3>
          <button class="close-btn" @click="localShowDbImportModal = false">×</button>
        </div>

        <div class="modal-body">
          <p class="modal-description">
            ⚠️ <strong>Warning:</strong> This will completely replace your current database. Make sure you have a backup first!
          </p>
          <p class="modal-description">
            Paste the JSON content from your database export file below.
          </p>

          <textarea
            v-model="localDbImportText"
            placeholder="Paste database JSON here..."
            rows="15"
          ></textarea>
        </div>

        <div class="modal-actions">
          <button
            @click="localShowDbImportModal = false"
            class="secondary"
            :disabled="dbImporting"
          >
            Cancel
          </button>
          <button
            @click="emit('import-db')"
            class="primary"
            :disabled="dbImporting || !localDbImportText.trim()"
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

.modal-description {
  color: var(--text-muted);
  font-size: 14px;
  margin-bottom: 16px;
  line-height: 1.5;
}

textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 13px;
  font-family: 'Courier New', monospace;
  resize: vertical;
  min-height: 300px;
}

textarea:focus {
  outline: none;
  border-color: var(--accent);
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
</style>
