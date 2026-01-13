<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { getApiBase } from '@/services/apiBase'

interface LibraryMapping {
  id: string
  title?: string
  displayName?: string
  autoGenerateEnabled?: boolean
  autoGeneratePresetId?: string | null
  autoGenerateTemplateId?: string | null
}

interface PlexLibrary {
  title: string
  key: string
  type: string
}

interface Preset {
  id: string
  name: string
}

const props = defineProps<{
  plexUrl: string
  plexToken: string
  libraries: LibraryMapping[]
  tvShowLibraries: LibraryMapping[]
  savedLibraryIds: Set<string>
  savedTvShowLibraryIds: Set<string>
  testConnection: string
  testConnectionLoading: boolean
  plexLibraries: PlexLibrary[]
  scanCooldown: boolean
  scanningLibraryId: string | null
  schedulerEnabled: boolean
  schedulerCronExpression: string
  schedulerLibraryIds: string[]
  schedulerNextRun: string | null
  unsavedChanges: boolean
}>()

const apiBase = getApiBase()
const availablePresets = ref<Record<string, Preset[]>>({})
const presetsLoading = ref(false)

const emit = defineEmits<{
  'update:plexUrl': [value: string]
  'update:plexToken': [value: string]
  'update:libraries': [value: LibraryMapping[]]
  'update:tvShowLibraries': [value: LibraryMapping[]]
  'update:schedulerEnabled': [value: boolean]
  'update:schedulerCronExpression': [value: string]
  'update:schedulerLibraryIds': [value: string[]]
  'test-connection': []
  'scan-library': [libraryId?: string]
  'save': []
}>()

const localPlexUrl = computed({
  get: () => props.plexUrl,
  set: (val) => emit('update:plexUrl', val)
})

const localPlexToken = computed({
  get: () => props.plexToken,
  set: (val) => emit('update:plexToken', val)
})

const localLibraries = computed({
  get: () => props.libraries,
  set: (val) => emit('update:libraries', val)
})

const localTvShowLibraries = computed({
  get: () => props.tvShowLibraries,
  set: (val) => emit('update:tvShowLibraries', val)
})

const localSchedulerEnabled = computed({
  get: () => props.schedulerEnabled,
  set: (val) => emit('update:schedulerEnabled', val)
})

const localSchedulerCronExpression = computed({
  get: () => props.schedulerCronExpression,
  set: (val) => emit('update:schedulerCronExpression', val)
})

const localSchedulerLibraryIds = computed({
  get: () => props.schedulerLibraryIds,
  set: (val) => emit('update:schedulerLibraryIds', val)
})

const toggleLibrarySelection = (libraryId: string) => {
  const current = [...localSchedulerLibraryIds.value]
  const index = current.indexOf(libraryId)
  if (index > -1) {
    current.splice(index, 1)
  } else {
    current.push(libraryId)
  }
  localSchedulerLibraryIds.value = current
}

const isLibrarySelected = (libraryId: string) => {
  return localSchedulerLibraryIds.value.includes(libraryId)
}

const addLibrary = () => {
  localLibraries.value = [...localLibraries.value, {
    id: '',
    title: '',
    displayName: '',
    autoGenerateEnabled: false,
    autoGeneratePresetId: null,
    autoGenerateTemplateId: null
  }]
}

const removeLibrary = (idx: number) => {
  localLibraries.value = localLibraries.value.filter((_, i) => i !== idx)
}

const addTvShowLibrary = () => {
  localTvShowLibraries.value = [...localTvShowLibraries.value, { id: '', title: '', displayName: '' }]
}

const removeTvShowLibrary = (idx: number) => {
  localTvShowLibraries.value = localTvShowLibraries.value.filter((_, i) => i !== idx)
}

const availableLibrariesForScheduler = computed(() => {
  const allLibs = [
    ...props.libraries.map(l => ({ id: l.id, name: l.displayName || l.title || l.id, type: 'Movie' })),
    ...props.tvShowLibraries.map(l => ({ id: l.id, name: l.displayName || l.title || l.id, type: 'TV' }))
  ].filter(l => l.id)
  return allLibs
})

const formatNextRunTime = (timestamp: string | null) => {
  if (!timestamp) return 'Not scheduled'
  try {
    const date = new Date(timestamp)
    return date.toLocaleString()
  } catch {
    return timestamp
  }
}

const fetchPresets = async () => {
  presetsLoading.value = true
  try {
    const res = await fetch(`${apiBase}/api/presets`)
    if (res.ok) {
      availablePresets.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to fetch presets:', e)
  } finally {
    presetsLoading.value = false
  }
}

// Get all presets flattened for dropdown
const allPresets = computed(() => {
  const presets: Preset[] = []
  Object.entries(availablePresets.value).forEach(([templateId, templateData]) => {
    const templatePresets = (templateData as any).presets
    if (Array.isArray(templatePresets)) {
      templatePresets.forEach(preset => {
        presets.push({
          id: `${templateId}:${preset.id}`,
          name: `${templateId} - ${preset.name}`
        })
      })
    }
  })
  return presets
})

onMounted(() => {
  fetchPresets()
})
</script>

<template>
  <div class="tab-content">
    <h2>Libraries</h2>

    <!-- Plex Connection -->
    <div class="section">
      <h3>Plex Connection</h3>

      <div class="plex-connection-grid">
        <label>
          <span class="label-text">Plex URL</span>
          <input
            v-model="localPlexUrl"
            type="text"
            placeholder="http://localhost:32400"
          />
          <span class="help-text">Your Plex server URL</span>
        </label>

        <label>
          <span class="label-text">Plex Token</span>
          <input
            v-model="localPlexToken"
            type="password"
            placeholder="X-Plex-Token"
          />
          <span class="help-text">Find your Plex token in Plex settings</span>
        </label>
      </div>

      <div class="plex-actions">
        <button
          @click="emit('test-connection')"
          :disabled="testConnectionLoading || !localPlexUrl || !localPlexToken"
          class="secondary"
        >
          {{ testConnectionLoading ? 'Testing...' : 'Test Connection' }}
        </button>

        <button
          @click="emit('scan-library')"
          :disabled="scanCooldown"
          class="secondary"
        >
          {{ scanCooldown ? 'Scanning...' : 'Scan All Libraries' }}
        </button>

        <div v-if="testConnection" class="status-message">
          {{ testConnection }}
        </div>
      </div>
    </div>

    <!-- Libraries Grid -->
    <div class="libraries-grid">
      <!-- Movie Libraries -->
      <div class="section">
        <div class="section-header-inline">
          <h3>Movie Libraries</h3>
          <button @click="addLibrary" class="secondary-small">
            + Add
          </button>
        </div>

        <div v-for="(lib, idx) in localLibraries" :key="idx" class="library-card">
        <div class="library-fields">
          <label>
            <span class="label-text">Library ID</span>
            <select
              v-model="lib.id"
              :disabled="savedLibraryIds.has(String(lib.id))"
            >
              <option value="">Select a library...</option>
              <option
                v-for="plexLib in plexLibraries.filter(l => l.type === 'movie')"
                :key="plexLib.key"
                :value="plexLib.key"
              >
                {{ plexLib.title }} ({{ plexLib.key }})
              </option>
            </select>
          </label>

          <label>
            <span class="label-text">Display Name</span>
            <input
              v-model="lib.displayName"
              type="text"
              placeholder="Custom display name"
            />
          </label>
        </div>

        <!-- Auto-Generation Settings -->
        <div v-if="lib.id" class="auto-gen-section">
          <label class="checkbox-label">
            <input type="checkbox" v-model="lib.autoGenerateEnabled" />
            <span>Enable automatic poster generation for new content</span>
          </label>

          <div v-if="lib.autoGenerateEnabled" class="preset-selection">
            <label>
              <span class="label-text">Template & Preset</span>
              <select v-model="lib.autoGeneratePresetId">
                <option value="">Select a preset...</option>
                <option
                  v-for="preset in allPresets"
                  :key="preset.id"
                  :value="preset.id"
                >
                  {{ preset.name }}
                </option>
              </select>
              <span class="help-text">Choose which template/preset to use for auto-generation</span>
            </label>
          </div>
        </div>

        <div class="library-actions">
          <button
            v-if="lib.id"
            @click="emit('scan-library', lib.id)"
            :disabled="scanCooldown || scanningLibraryId === lib.id"
            class="scan-btn"
            :title="`Scan ${lib.displayName || lib.title || lib.id}`"
          >
            {{ scanningLibraryId === lib.id ? 'Scanning...' : 'Scan' }}
          </button>

          <button
            v-if="localLibraries.length > 1"
            @click="removeLibrary(idx)"
            class="remove-btn"
            :disabled="savedLibraryIds.has(String(lib.id))"
          >
            Remove
          </button>
        </div>
      </div>
      </div>

      <!-- TV Show Libraries -->
      <div class="section">
        <div class="section-header-inline">
          <h3>TV Show Libraries</h3>
          <button @click="addTvShowLibrary" class="secondary-small">
            + Add
          </button>
        </div>

        <div v-for="(lib, idx) in localTvShowLibraries" :key="idx" class="library-card">
        <div class="library-fields">
          <label>
            <span class="label-text">Library ID</span>
            <select
              v-model="lib.id"
              :disabled="savedTvShowLibraryIds.has(String(lib.id))"
            >
              <option value="">Select a library...</option>
              <option
                v-for="plexLib in plexLibraries.filter(l => l.type === 'show')"
                :key="plexLib.key"
                :value="plexLib.key"
              >
                {{ plexLib.title }} ({{ plexLib.key }})
              </option>
            </select>
          </label>

          <label>
            <span class="label-text">Display Name</span>
            <input
              v-model="lib.displayName"
              type="text"
              placeholder="Custom display name"
            />
          </label>
        </div>

        <div v-if="lib.id" class="auto-gen-section">
          <label class="checkbox-label">
            <input type="checkbox" v-model="lib.autoGenerateEnabled" />
            <span>Enable automatic poster generation for new content</span>
          </label>

          <div v-if="lib.autoGenerateEnabled" class="preset-selection">
            <label>
              <span class="label-text">Template & Preset</span>
              <select v-model="lib.autoGeneratePresetId">
                <option value="">Select a preset...</option>
                <option
                  v-for="preset in allPresets"
                  :key="preset.id"
                  :value="preset.id"
                >
                  {{ preset.name }}
                </option>
              </select>
              <span class="help-text">Choose which template/preset to use for auto-generation</span>
            </label>
          </div>
        </div>

        <div class="library-actions">
          <button
            v-if="lib.id"
            @click="emit('scan-library', lib.id)"
            :disabled="scanCooldown || scanningLibraryId === lib.id"
            class="scan-btn"
            :title="`Scan ${lib.displayName || lib.title || lib.id}`"
          >
            {{ scanningLibraryId === lib.id ? 'Scanning...' : 'Scan' }}
          </button>

          <button
            v-if="localTvShowLibraries.length > 1"
            @click="removeTvShowLibrary(idx)"
            class="remove-btn"
            :disabled="savedTvShowLibraryIds.has(String(lib.id))"
          >
            Remove
          </button>
        </div>
      </div>
      </div>
    </div>

    <!-- Scheduled Scans -->
    <div class="section">
      <h3>Scheduled Scans</h3>

      <div class="scheduler-header">
        <label class="checkbox-label">
          <input type="checkbox" v-model="localSchedulerEnabled" />
          <span>Enable scheduled scanning</span>
        </label>

        <div v-if="localSchedulerEnabled" class="cron-input-inline">
          <label>
            <span class="label-text">Cron Expression</span>
            <input
              v-model="localSchedulerCronExpression"
              type="text"
              placeholder="0 2 * * *"
            />
            <span class="help-text">
              Example: "0 2 * * *" = Daily at 2 AM
            </span>
          </label>
        </div>
      </div>

      <div v-if="localSchedulerEnabled" class="scheduler-config">
        <div class="library-selection">
          <span class="label-text">Libraries to Scan</span>
          <span class="help-text">Select libraries to scan automatically (leave all unchecked for all libraries)</span>

          <div class="library-checkboxes-horizontal">
            <label
              v-for="lib in availableLibrariesForScheduler"
              :key="lib.id"
              class="checkbox-label"
            >
              <input
                type="checkbox"
                :checked="isLibrarySelected(lib.id)"
                @change="toggleLibrarySelection(lib.id)"
              />
              <span>{{ lib.name }} <span class="lib-type">({{ lib.type }})</span></span>
            </label>
          </div>
        </div>

        <div v-if="schedulerNextRun" class="next-run">
          <strong>Next Run:</strong> {{ formatNextRunTime(schedulerNextRun) }}
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
  margin-bottom: 24px;
}

.plex-connection-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.plex-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.scheduler-header {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.cron-input-inline {
  flex: 1;
  max-width: 400px;
}

.cron-input-inline label {
  margin-bottom: 0;
}

.cron-input-inline input {
  width: 100%;
}

.libraries-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 24px;
}

.libraries-grid .section {
  margin-bottom: 0;
}

.section-header-inline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-header-inline h3 {
  margin: 0;
}

.subsection {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.subsection h4 {
  margin-bottom: 16px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 0;
}

.label-text {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 13px;
}

.help-text {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: -2px;
  line-height: 1.3;
}

input[type="text"],
input[type="password"],
select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 13px;
}

input[type="text"]:disabled,
input[type="password"]:disabled,
select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.checkbox-label {
  flex-direction: row;
  align-items: center;
  gap: 10px;
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

.library-card {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 12px;
  transition: all 0.2s;
}

.library-card:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(61, 214, 183, 0.3);
}

.library-card:last-of-type {
  margin-bottom: 0;
}

.auto-gen-section {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.preset-selection {
  margin-top: 10px;
  margin-left: 24px;
}

.library-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 0;
}

.library-fields label {
  margin-bottom: 0;
}

.library-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.scan-btn {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(61, 214, 183, 0.1);
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.scan-btn:hover:not(:disabled) {
  background: rgba(61, 214, 183, 0.2);
  border-color: var(--accent);
}

.scan-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.remove-btn {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 0, 0, 0.1);
  color: #ff6b6b;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.remove-btn:hover:not(:disabled) {
  background: rgba(255, 0, 0, 0.2);
  border-color: #ff6b6b;
}

.remove-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

button.secondary-small {
  padding: 6px 12px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

button.secondary-small:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  border-color: var(--accent);
}

button.secondary-small:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.scan-buttons {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.scheduler-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.next-run {
  padding: 14px;
  background: rgba(61, 214, 183, 0.05);
  border: 1px solid rgba(61, 214, 183, 0.2);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.next-run strong {
  color: var(--accent);
}

.library-selection {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.library-checkboxes {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
}

.library-checkboxes .checkbox-label {
  margin-bottom: 0;
}

.library-checkboxes-horizontal {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
}

.library-checkboxes-horizontal .checkbox-label {
  margin-bottom: 0;
}

.lib-type {
  color: var(--text-muted);
  font-size: 12px;
}

.status-message {
  padding: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: 12px;
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

button.secondary {
  background: rgba(255, 255, 255, 0.06);
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
