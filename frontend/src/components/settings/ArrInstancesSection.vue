<script setup lang="ts">
// Radarr or Sonarr connections (Settings → Media Servers). Simposter only
// reads tags from them, for poster mode rules on a library group. Bound
// straight to the settings store like the media server list; the page-wide
// Save sends it.
import { computed, reactive, ref } from 'vue'
import { useSettingsStore, type ArrInstance } from '@/stores/settings'
import { getApiBase } from '@/services/apiBase'
import { mediaServerId } from '@/services/mediaServerId'

const props = defineProps<{
  type: 'radarr' | 'sonarr'
  changed?: boolean
}>()

const settings = useSettingsStore()
const apiBase = getApiBase()

const label = computed(() => (props.type === 'radarr' ? 'Radarr' : 'Sonarr'))
const instances = computed(() => settings.arrInstances.value.filter(i => i.type === props.type))

type TestResult = { ok: boolean; message: string }
const testResults = reactive<Record<string, TestResult>>({})
const testing = reactive<Record<string, boolean>>({})

const addOpen = ref(false)
const draft = reactive({ name: '', url: '', apiKey: '' })
const draftTesting = ref(false)
const draftResult = ref<TestResult | null>(null)

function patch(id: string, change: Partial<ArrInstance>) {
  settings.arrInstances.value = settings.arrInstances.value.map(i => (i.id === id ? { ...i, ...change } : i))
}

async function runTest(url: string, apiKey: string, instanceId?: string): Promise<TestResult> {
  try {
    const res = await fetch(`${apiBase}/api/arr/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: props.type, url, apiKey, instance_id: instanceId }),
    })
    const data = await res.json()
    if (res.ok && data.ok) return { ok: true, message: `✓ Connected to ${data.app} ${data.version}`.trim() }
    return { ok: false, message: `✗ ${data.error || data.detail || 'Could not connect'}` }
  } catch {
    return { ok: false, message: '✗ Could not connect' }
  }
}

async function testInstance(inst: ArrInstance) {
  testing[inst.id] = true
  testResults[inst.id] = await runTest(inst.url, inst.apiKey || '', inst.id)
  testing[inst.id] = false
}

async function testDraft() {
  draftTesting.value = true
  draftResult.value = await runTest(draft.url, draft.apiKey)
  draftTesting.value = false
}

function cancelAdd() {
  addOpen.value = false
  draft.name = ''
  draft.url = ''
  draft.apiKey = ''
  draftResult.value = null
}

function addInstance() {
  const url = draft.url.trim()
  if (!url || !draft.apiKey) return
  const id = mediaServerId(props.type, url)
  const entry: ArrInstance = { id, type: props.type, name: draft.name.trim(), url, apiKey: draft.apiKey, enabled: true }
  const others = settings.arrInstances.value.filter(i => i.id !== id)
  settings.arrInstances.value = [...others, entry]
  cancelAdd()
}

function removeInstance(id: string) {
  settings.arrInstances.value = settings.arrInstances.value.filter(i => i.id !== id)
  // A library group linked to it loses the link.
  if (settings.libraryGroups.value.some(g => g.arrInstanceId === id)) {
    settings.libraryGroups.value = settings.libraryGroups.value.map(g =>
      g.arrInstanceId === id ? { ...g, arrInstanceId: null } : g,
    )
  }
  delete testResults[id]
}

function linkedGroups(id: string): string {
  return settings.libraryGroups.value.filter(g => g.arrInstanceId === id).map(g => g.name).join(', ')
}
</script>

<template>
  <div :class="['section', { 'section-unsaved': changed }]">
    <h3>{{ label }}</h3>
    <p class="scan-hint section-hint">
      Simposter only reads tags from {{ label }}, for poster mode rules. Link an instance to a
      {{ type === 'radarr' ? 'movie' : 'TV show' }} library group in Settings → Libraries.
    </p>

    <div class="server-list">
      <div v-for="inst in instances" :key="inst.id" class="server-card">
        <div class="server-card-row">
          <span class="server-type-badge" :class="type">{{ label }}</span>
          <input
            :value="inst.name"
            :placeholder="`Name (e.g. ${label} 4K)`"
            class="server-name-input"
            @input="patch(inst.id, { name: ($event.target as HTMLInputElement).value })"
          />
          <label class="enabled-toggle">
            <input type="checkbox" :checked="inst.enabled !== false" @change="patch(inst.id, { enabled: ($event.target as HTMLInputElement).checked })" />
            Enabled
          </label>
        </div>
        <div class="server-card-row">
          <input
            :value="inst.url"
            placeholder="Address (e.g. http://192.168.1.10:7878)"
            class="server-url-input"
            @input="patch(inst.id, { url: ($event.target as HTMLInputElement).value })"
          />
          <input
            :value="inst.apiKey"
            type="password"
            placeholder="API Key"
            class="server-credential-input"
            @input="patch(inst.id, { apiKey: ($event.target as HTMLInputElement).value })"
          />
        </div>
        <div class="server-card-row">
          <button class="secondary" :disabled="testing[inst.id] || !inst.url" @click="testInstance(inst)">
            {{ testing[inst.id] ? 'Testing…' : 'Test Connection' }}
          </button>
          <span v-if="testResults[inst.id]" class="test-result-inline" :class="{ ok: testResults[inst.id]?.ok }">{{ testResults[inst.id]?.message }}</span>
        </div>
        <p v-if="linkedGroups(inst.id)" class="scan-hint">Linked to: {{ linkedGroups(inst.id) }}</p>
        <p v-else class="scan-hint">Not linked to a library group yet.</p>
        <div class="server-card-footer">
          <button class="remove-btn-text" @click="removeInstance(inst.id)">Remove {{ label }}</button>
        </div>
      </div>
      <p v-if="!instances.length" class="empty-state">No {{ label }} connected yet.</p>
    </div>

    <button v-if="!addOpen" type="button" class="secondary-small add-server-toggle" @click="addOpen = true">
      + Add {{ label }}
    </button>
    <div v-else class="add-server-form">
      <div class="add-server-header">
        <strong class="add-server-title">Add {{ label }}</strong>
        <button type="button" class="icon-btn" title="Cancel" @click="cancelAdd">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
      <div class="add-server-row">
        <input v-model="draft.name" :placeholder="`Name (e.g. ${label} 4K)`" class="server-name-input" />
        <input v-model="draft.url" :placeholder="`Address (e.g. http://192.168.1.10:${type === 'radarr' ? 7878 : 8989})`" class="server-url-input" />
        <input v-model="draft.apiKey" type="password" placeholder="API Key" class="server-credential-input" />
      </div>
      <div class="add-server-row">
        <button class="secondary" :disabled="draftTesting || !draft.url || !draft.apiKey" @click="testDraft">
          {{ draftTesting ? 'Testing…' : 'Test Connection' }}
        </button>
        <span v-if="draftResult" class="test-result-inline" :class="{ ok: draftResult.ok }">{{ draftResult.message }}</span>
        <button class="primary" :disabled="!draft.url || !draft.apiKey" @click="addInstance">Add {{ label }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 0;
  transition: border-color 0.2s, background 0.2s;
}

.section-unsaved {
  border-color: rgba(255, 193, 7, 0.5);
  background: rgba(255, 193, 7, 0.05);
}

.section h3 {
  margin-top: 0;
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 18px;
}

.section-hint {
  margin: 0 0 16px 0;
}

.server-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.server-card {
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.02);
  transition: all 0.2s;
}

.server-card:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(61, 214, 183, 0.3);
}

.server-card-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}

.server-type-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.server-type-badge.radarr { background: rgba(255, 194, 48, 0.15); color: #ffc230; }
.server-type-badge.sonarr { background: rgba(53, 197, 244, 0.15); color: #35c5f4; }

.server-name-input,
.server-url-input,
.server-credential-input {
  flex: 1;
  min-width: 140px;
  width: auto;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 13px;
}

.enabled-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  font-size: 13px;
  color: var(--text-secondary);
}

.test-result-inline {
  font-size: 13px;
  color: var(--text-secondary);
}

.test-result-inline.ok {
  color: #3dd6b7;
}

.scan-hint {
  color: var(--text-secondary);
  font-size: 12px;
  margin: 4px 0 0 0;
}

.empty-state {
  color: var(--text-muted);
  font-size: 13px;
  margin: 0;
}

.server-card-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.remove-btn-text {
  background: none;
  border: none;
  padding: 2px 4px;
  font-size: 12px;
  font-weight: 600;
  color: #f05d7b;
  cursor: pointer;
}

.remove-btn-text:hover {
  text-decoration: underline;
}

.add-server-toggle {
  width: 100%;
}

.add-server-form {
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.015);
}

.add-server-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.add-server-title {
  color: var(--text-primary);
  font-size: 14px;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.icon-btn:hover {
  color: #f05d7b;
  background: rgba(255, 255, 255, 0.06);
}

.add-server-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}

.add-server-row:last-child {
  margin-bottom: 0;
}

button.secondary,
button.primary {
  padding: 10px 20px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

button.secondary:hover:not(:disabled) {
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

button.secondary-small {
  padding: 6px 12px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

button.secondary-small:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  border-color: var(--accent);
}
</style>
