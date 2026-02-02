<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { getApiBase } from '@/services/apiBase'

interface LibraryMapping {
  id: string
  title?: string
  displayName?: string
}

const props = defineProps<{
  discordWebhookUrl: string
  discordEnabled: boolean
  discordNotifyLibraries: string[]
  discordNotifyBatch: boolean
  discordNotifyManual: boolean
  discordNotifyWebhook: boolean
  discordNotifyAutoGenerate: boolean
  libraries: LibraryMapping[]
  tvShowLibraries: LibraryMapping[]
  unsavedChanges: boolean
}>()

const emit = defineEmits<{
  'update:discordWebhookUrl': [value: string]
  'update:discordEnabled': [value: boolean]
  'update:discordNotifyLibraries': [value: string[]]
  'update:discordNotifyBatch': [value: boolean]
  'update:discordNotifyManual': [value: boolean]
  'update:discordNotifyWebhook': [value: boolean]
  'update:discordNotifyAutoGenerate': [value: boolean]
  'save': []
}>()

const apiBase = getApiBase()
const testingWebhook = ref(false)
const testResult = ref<string | null>(null)

const localDiscordWebhookUrl = computed({
  get: () => props.discordWebhookUrl,
  set: (val) => emit('update:discordWebhookUrl', val)
})

const localDiscordEnabled = computed({
  get: () => props.discordEnabled,
  set: (val) => emit('update:discordEnabled', val)
})

const localDiscordNotifyBatch = computed({
  get: () => props.discordNotifyBatch,
  set: (val) => emit('update:discordNotifyBatch', val)
})

const localDiscordNotifyManual = computed({
  get: () => props.discordNotifyManual,
  set: (val) => emit('update:discordNotifyManual', val)
})

const localDiscordNotifyWebhook = computed({
  get: () => props.discordNotifyWebhook,
  set: (val) => emit('update:discordNotifyWebhook', val)
})

const localDiscordNotifyAutoGenerate = computed({
  get: () => props.discordNotifyAutoGenerate,
  set: (val) => emit('update:discordNotifyAutoGenerate', val)
})

// Combine all libraries for display
const allLibraries = computed(() => {
  const movieLibs = props.libraries.map(lib => ({
    ...lib,
    type: 'movie' as const,
    label: lib.displayName || lib.title || lib.id
  }))
  const tvLibs = props.tvShowLibraries.map(lib => ({
    ...lib,
    type: 'tv' as const,
    label: `${lib.displayName || lib.title || lib.id} (TV)`
  }))
  return [...movieLibs, ...tvLibs]
})

const isLibrarySelected = (libraryId: string) => {
  return props.discordNotifyLibraries.includes(libraryId)
}

const toggleLibrary = (libraryId: string) => {
  const current = [...props.discordNotifyLibraries]
  const index = current.indexOf(libraryId)
  if (index > -1) {
    current.splice(index, 1)
  } else {
    current.push(libraryId)
  }
  emit('update:discordNotifyLibraries', current)
}

const selectAllLibraries = () => {
  const allIds = allLibraries.value.map(lib => lib.id)
  emit('update:discordNotifyLibraries', allIds)
}

const deselectAllLibraries = () => {
  emit('update:discordNotifyLibraries', [])
}

const testWebhook = async () => {
  if (!localDiscordWebhookUrl.value) {
    testResult.value = 'Please enter a webhook URL'
    return
  }

  testingWebhook.value = true
  testResult.value = null

  try {
    const response = await fetch(`${apiBase}/api/notifications/test-discord`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ webhook_url: localDiscordWebhookUrl.value })
    })

    const data = await response.json()
    if (response.ok && data.success) {
      testResult.value = 'Test message sent successfully!'
    } else {
      testResult.value = data.error || 'Failed to send test message'
    }
  } catch (error) {
    testResult.value = 'Failed to connect to server'
  } finally {
    testingWebhook.value = false
  }
}
</script>

<template>
  <div class="tab-content">
    <h2>Notifications</h2>

    <!-- Discord Webhook -->
    <div class="section">
      <h3>Discord Webhook</h3>
      <p class="section-description">
        Receive notifications in Discord when posters are generated.
      </p>

      <label class="checkbox-option enable-checkbox">
        <input type="checkbox" v-model="localDiscordEnabled" />
        <div class="checkbox-content">
          <span class="checkbox-label-text">Enable Discord notifications</span>
          <span class="checkbox-description">
            Send poster generation notifications to a Discord channel
          </span>
        </div>
      </label>

      <div v-if="localDiscordEnabled" class="discord-settings">
        <label>
          <span class="label-text">Webhook URL</span>
          <div class="input-with-button">
            <input
              v-model="localDiscordWebhookUrl"
              type="password"
              placeholder="https://discord.com/api/webhooks/..."
            />
            <button
              @click="testWebhook"
              class="secondary"
              :disabled="!localDiscordWebhookUrl || testingWebhook"
              type="button"
            >
              {{ testingWebhook ? 'Testing...' : 'Test' }}
            </button>
          </div>
          <span v-if="testResult" :class="['test-result', testResult.includes('success') ? 'success' : 'error']">
            {{ testResult }}
          </span>
          <span class="help-text">
            Create a webhook in Discord: Server Settings &rarr; Integrations &rarr; Webhooks &rarr; New Webhook
          </span>
        </label>

        <!-- Library Selection -->
        <div class="subsection">
          <div class="subsection-header">
            <span class="label-text">Libraries to notify for</span>
            <div class="quick-actions">
              <button type="button" class="link-btn" @click="selectAllLibraries">Select All</button>
              <span class="separator">|</span>
              <button type="button" class="link-btn" @click="deselectAllLibraries">Deselect All</button>
            </div>
          </div>
          <span class="help-text">Choose which libraries should trigger Discord notifications</span>

          <div v-if="allLibraries.length > 0" class="libraries-grid">
            <label
              v-for="lib in allLibraries"
              :key="lib.id"
              class="library-checkbox"
            >
              <input
                type="checkbox"
                :checked="isLibrarySelected(lib.id)"
                @change="toggleLibrary(lib.id)"
              />
              <span>{{ lib.label }}</span>
            </label>
          </div>
          <p v-else class="no-libraries">
            No libraries configured. Add libraries in the Libraries tab first.
          </p>
        </div>

        <!-- Notification Types -->
        <div class="subsection">
          <span class="label-text">Notification types</span>
          <span class="help-text">Choose which events should send Discord notifications</span>

          <div class="notification-types">
            <label class="type-checkbox">
              <input type="checkbox" v-model="localDiscordNotifyBatch" />
              <div class="type-content">
                <span class="type-label">Batch Edit</span>
                <span class="type-description">When batch processing completes</span>
              </div>
            </label>

            <label class="type-checkbox">
              <input type="checkbox" v-model="localDiscordNotifyManual" />
              <div class="type-content">
                <span class="type-label">Manual Send</span>
                <span class="type-description">When manually sending a poster to Plex</span>
              </div>
            </label>

            <label class="type-checkbox">
              <input type="checkbox" v-model="localDiscordNotifyWebhook" />
              <div class="type-content">
                <span class="type-label">Webhook (Radarr/Sonarr/Tautulli)</span>
                <span class="type-description">When webhooks trigger poster generation</span>
              </div>
            </label>

            <label class="type-checkbox">
              <input type="checkbox" v-model="localDiscordNotifyAutoGenerate" />
              <div class="type-content">
                <span class="type-label">Auto-Generate (Library Scan)</span>
                <span class="type-description">When library scans generate posters</span>
              </div>
            </label>
          </div>
        </div>
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

.section-description {
  margin: -8px 0 16px 0;
  color: var(--text-muted);
  font-size: 13px;
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

.enable-checkbox {
  display: flex;
  flex-direction: row;
  gap: 12px;
  align-items: flex-start;
  padding: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 20px;
}

.enable-checkbox:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--accent);
}

.enable-checkbox input[type="checkbox"] {
  margin-top: 2px;
  width: 18px;
  height: 18px;
  cursor: pointer;
  flex-shrink: 0;
}

.checkbox-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.checkbox-label-text {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 14px;
}

.checkbox-description {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}

.discord-settings {
  padding-left: 8px;
  border-left: 3px solid var(--accent);
  margin-left: 8px;
}

input[type="text"],
input[type="password"] {
  width: 100%;
  max-width: 500px;
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

.test-result {
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  font-weight: 500;
}

.test-result.success {
  background: rgba(76, 175, 80, 0.15);
  color: #4caf50;
  border: 1px solid rgba(76, 175, 80, 0.3);
}

.test-result.error {
  background: rgba(255, 71, 87, 0.15);
  color: #ff4757;
  border: 1px solid rgba(255, 71, 87, 0.3);
}

.subsection {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.subsection-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.quick-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.link-btn {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}

.link-btn:hover {
  text-decoration: underline;
}

.separator {
  color: var(--text-muted);
  font-size: 12px;
}

.libraries-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.library-checkbox {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: rgba(88, 101, 242, 0.08);
  border: 1px solid rgba(88, 101, 242, 0.2);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 0;
}

.library-checkbox:hover {
  border-color: rgba(88, 101, 242, 0.4);
}

.library-checkbox:has(input:checked) {
  background: rgba(88, 101, 242, 0.2);
  border-color: rgba(88, 101, 242, 0.5);
}

.library-checkbox input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.library-checkbox span {
  font-size: 13px;
  color: var(--text-primary);
}

.no-libraries {
  color: var(--text-muted);
  font-style: italic;
  font-size: 13px;
  margin: 12px 0 0 0;
}

.notification-types {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.type-checkbox {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 0;
}

.type-checkbox:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--accent);
}

.type-checkbox:has(input:checked) {
  background: rgba(88, 101, 242, 0.1);
  border-color: rgba(88, 101, 242, 0.4);
}

.type-checkbox input {
  margin-top: 2px;
  width: 16px;
  height: 16px;
  cursor: pointer;
  flex-shrink: 0;
}

.type-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.type-label {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 14px;
}

.type-description {
  font-size: 12px;
  color: var(--text-muted);
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
