<script setup lang="ts">
import { ref, computed, onMounted, watch, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore } from '@/stores/settings'
import { mediaServerLabel } from '@/services/mediaServerLabel'

type MirrorMappingEntry = {
  tmdb_id: number | string | null
  source_rating_key: string | null
  title: string | null
  year: number | string | null
  targets: Record<string, string | null>
}

type MirrorGroup = {
  id: string
  name: string
  members: { serverId: string; libraryId: string; libraryName?: string }[]
  mirror?: {
    enabled?: boolean
    sourceServerId?: string | null
    targetServerIds?: string[]
    assetTypes?: string[]
    lastRunAt?: string | null
    lastRunStats?: {
      checked?: number
      updated?: number
      skipped?: number
      unmapped?: number
      failed?: number
      unmappedSample?: string[]
    } | null
  } | null
}

type RunStatus = {
  state?: 'idle' | 'running' | 'done' | 'error'
  total?: number
  processed?: number
  current?: string
  updated?: number
  skipped?: number
  unmapped?: number
  failed?: number
  error?: string | null
}

const apiBase = getApiBase()
const route = useRoute()
const settings = useSettingsStore()

const isTV = computed(() => route.name === 'tv-media-mirror')
const mediaType = computed(() => (isTV.value ? 'tv' : 'movie'))
const libraryId = computed(() => (route.query.library as string) || '')
// Phase 8a -- see App.vue's resolveLibraryTarget(). Absent for a Plex tab
// (the backend already defaults to "plex-1"), explicitly set for a
// Jellyfin/Emby-only group tab.
const serverId = computed(() => (route.query.server as string) || 'plex-1')

const loading = ref(false)
const group = ref<MirrorGroup | null>(null)

const enabled = ref(false)
const sourceServerId = ref<string>('')
const targetServerIds = ref<Set<string>>(new Set())
const assetTypes = ref<Set<string>>(new Set(['poster']))
const saving = ref(false)
const saveMessage = ref('')

const mapping = ref<MirrorMappingEntry[]>([])
const mappingLoading = ref(false)

const runStatus = ref<RunStatus>({ state: 'idle' })
let pollHandle: ReturnType<typeof setInterval> | null = null

// Every server this library's group actually links, labeled via the same
// shared helper the rest of the app already uses (Quirk #79) so a custom
// server name is honored here too.
const memberOptions = computed(() => {
  if (!group.value) return []
  return group.value.members.map(m => ({
    id: m.serverId,
    label: mediaServerLabel(m.serverId, settings.mediaServers.value),
  }))
})

const targetOptions = computed(() => memberOptions.value.filter(o => o.id !== sourceServerId.value))

// A group needs at least 2 linked members for mirroring to mean anything --
// matches the "only show a control once there's an actual choice" convention
// already established for the merge/prefer dropdowns (Quirk #85/#120).
const hasEnoughMembers = computed(() => (group.value?.members.length || 0) > 1)

const ASSET_TYPE_LABELS: Record<string, string> = {
  poster: 'Posters',
  logo: 'Logos',
  backdrop: 'Backdrops',
  square_art: 'Square Art',
}

function toggleTarget(id: string) {
  const next = new Set(targetServerIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  targetServerIds.value = next
}

function toggleAssetType(id: string) {
  const next = new Set(assetTypes.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  assetTypes.value = next
}

async function fetchGroup() {
  group.value = null
  if (!libraryId.value) return
  loading.value = true
  try {
    const res = await fetch(
      `${apiBase}/api/media-server/library-group?server_id=${encodeURIComponent(serverId.value)}&library_id=${encodeURIComponent(libraryId.value)}&media_type=${mediaType.value}`
    )
    if (res.ok) {
      const data = await res.json()
      group.value = data.group || null
      applyConfigFromGroup()
    }
  } catch {
    group.value = null
  } finally {
    loading.value = false
  }
}

function applyConfigFromGroup() {
  const mirror = group.value?.mirror
  enabled.value = !!mirror?.enabled
  sourceServerId.value = mirror?.sourceServerId || group.value?.members?.[0]?.serverId || ''
  targetServerIds.value = new Set((mirror?.targetServerIds || []).filter(Boolean))
  assetTypes.value = new Set((mirror?.assetTypes && mirror.assetTypes.length) ? mirror.assetTypes : ['poster'])
}

// Switching the source server should drop it from the target list if it was
// somehow also checked there -- a server can't mirror to itself.
watch(sourceServerId, (val) => {
  if (targetServerIds.value.has(val)) {
    const next = new Set(targetServerIds.value)
    next.delete(val)
    targetServerIds.value = next
  }
})

async function saveConfig() {
  saving.value = true
  saveMessage.value = ''
  try {
    const res = await fetch(`${apiBase}/api/media-mirror/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        server_id: serverId.value,
        library_id: libraryId.value,
        media_type: mediaType.value,
        mirror: {
          enabled: enabled.value,
          sourceServerId: sourceServerId.value || null,
          targetServerIds: Array.from(targetServerIds.value),
          assetTypes: Array.from(assetTypes.value),
        },
      }),
    })
    if (res.ok) {
      const data = await res.json()
      group.value = data.group || group.value
      saveMessage.value = 'Saved.'
      await fetchMapping()
    } else {
      saveMessage.value = 'Failed to save.'
    }
  } catch {
    saveMessage.value = 'Failed to save.'
  } finally {
    saving.value = false
    setTimeout(() => { saveMessage.value = '' }, 3000)
  }
}

async function fetchMapping() {
  if (!libraryId.value || !sourceServerId.value || targetServerIds.value.size === 0) {
    mapping.value = []
    return
  }
  mappingLoading.value = true
  try {
    const params = new URLSearchParams({
      server_id: serverId.value,
      library_id: libraryId.value,
      media_type: mediaType.value,
      source_server_id: sourceServerId.value,
      target_server_ids: Array.from(targetServerIds.value).join(','),
    })
    const res = await fetch(`${apiBase}/api/media-mirror/mapping?${params.toString()}`)
    if (res.ok) {
      const data = await res.json()
      mapping.value = data.mapping || []
    }
  } catch {
    mapping.value = []
  } finally {
    mappingLoading.value = false
  }
}

const unmappedCount = computed(() => mapping.value.filter(m => !Object.values(m.targets || {}).some(v => v)).length)

async function pollRunStatus() {
  try {
    const params = new URLSearchParams({
      server_id: serverId.value, library_id: libraryId.value, media_type: mediaType.value,
    })
    const res = await fetch(`${apiBase}/api/media-mirror/run-status?${params.toString()}`)
    if (res.ok) {
      const data: RunStatus = await res.json()
      runStatus.value = data
      if (data.state !== 'running' && pollHandle) {
        clearInterval(pollHandle)
        pollHandle = null
        if (data.state === 'done') {
          await fetchGroup()
          await fetchMapping()
        }
      }
    }
  } catch {
    // transient -- keep polling
  }
}

async function runNow() {
  try {
    const res = await fetch(`${apiBase}/api/media-mirror/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ server_id: serverId.value, library_id: libraryId.value, media_type: mediaType.value }),
    })
    if (res.ok) {
      runStatus.value = { state: 'running', total: 0, processed: 0 }
      if (pollHandle) clearInterval(pollHandle)
      pollHandle = setInterval(pollRunStatus, 1000)
    } else {
      const data = await res.json().catch(() => ({}))
      saveMessage.value = data.detail || 'Could not start run.'
      setTimeout(() => { saveMessage.value = '' }, 4000)
    }
  } catch {
    saveMessage.value = 'Could not start run.'
    setTimeout(() => { saveMessage.value = '' }, 4000)
  }
}

function formatLastRun(iso?: string | null): string {
  if (!iso) return 'Never'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

async function refresh() {
  await fetchGroup()
  await pollRunStatus()
  if (sourceServerId.value && targetServerIds.value.size > 0) {
    await fetchMapping()
  }
}

watch([libraryId, serverId], refresh)
onMounted(refresh)
onUnmounted(() => {
  if (pollHandle) clearInterval(pollHandle)
})
</script>

<template>
  <div class="media-mirror-view">
    <div class="page-header">
      <h2>🪞 Media Mirror</h2>
      <div class="header-actions">
        <span v-if="saveMessage" class="save-msg">{{ saveMessage }}</span>
      </div>
    </div>

    <div class="section-note">
      Designate one linked server's library as "the truth" and copy its posters/logos/backdrops/square art
      to one or more other linked servers in this group. Run manually below, or on a schedule (coming soon).
    </div>

    <div v-if="loading" class="state-msg">Loading...</div>

    <div v-else-if="!group" class="state-msg">
      This library isn't linked to another server yet. Link one in Settings → Libraries to use Media Mirror.
    </div>

    <div v-else-if="!hasEnoughMembers" class="state-msg">
      This group only has one linked server so far — link a second one in Settings → Libraries before
      configuring Media Mirror.
    </div>

    <template v-else>
      <div class="section">
        <div class="section-header-inline">
          <h3>Configuration</h3>
          <label class="enable-toggle">
            <input type="checkbox" v-model="enabled" />
            Enabled
          </label>
        </div>

        <div class="config-grid">
          <div class="config-field">
            <label class="field-label">Source (the truth)</label>
            <select v-model="sourceServerId" class="toolbar-select">
              <option v-for="opt in memberOptions" :key="opt.id" :value="opt.id">{{ opt.label }}</option>
            </select>
          </div>

          <div class="config-field">
            <label class="field-label">Mirror to</label>
            <div class="checkbox-list">
              <label v-for="opt in targetOptions" :key="opt.id" class="checkbox-item">
                <input
                  type="checkbox"
                  :checked="targetServerIds.has(opt.id)"
                  @change="toggleTarget(opt.id)"
                />
                {{ opt.label }}
              </label>
              <div v-if="targetOptions.length === 0" class="no-labels-hint">
                No other server to mirror to — link one in Settings → Libraries.
              </div>
            </div>
          </div>

          <div class="config-field">
            <label class="field-label">Asset types</label>
            <div class="checkbox-list">
              <label v-for="(label, id) in ASSET_TYPE_LABELS" :key="id" class="checkbox-item">
                <input
                  type="checkbox"
                  :checked="assetTypes.has(id)"
                  @change="toggleAssetType(id)"
                />
                {{ label }}
              </label>
            </div>
          </div>
        </div>

        <div class="config-actions">
          <button class="primary" :disabled="saving" @click="saveConfig">
            {{ saving ? 'Saving...' : 'Save Configuration' }}
          </button>
          <button
            class="secondary"
            :disabled="!enabled || runStatus.state === 'running' || sourceServerId === '' || targetServerIds.size === 0"
            @click="runNow"
          >
            {{ runStatus.state === 'running' ? 'Running...' : 'Run Now' }}
          </button>
        </div>

        <div v-if="group.mirror?.lastRunAt" class="last-run-note">
          Last run: {{ formatLastRun(group.mirror.lastRunAt) }} —
          {{ group.mirror.lastRunStats?.updated ?? 0 }} updated,
          {{ group.mirror.lastRunStats?.skipped ?? 0 }} unchanged,
          {{ group.mirror.lastRunStats?.unmapped ?? 0 }} unmapped,
          {{ group.mirror.lastRunStats?.failed ?? 0 }} failed
        </div>

        <div v-if="runStatus.state === 'running'" class="run-progress">
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: (runStatus.total ? (100 * (runStatus.processed || 0) / runStatus.total) : 0) + '%' }"
            ></div>
          </div>
          <span class="progress-text">
            {{ runStatus.processed || 0 }} / {{ runStatus.total || 0 }}
            <template v-if="runStatus.current">— {{ runStatus.current }}</template>
          </span>
        </div>

        <div v-else-if="runStatus.state === 'error'" class="state-msg error-msg">
          {{ runStatus.error || 'The last run failed.' }}
        </div>
      </div>

      <div class="section">
        <div class="section-header-inline">
          <h3>Confirm Mappings</h3>
          <button class="secondary-small" :disabled="mappingLoading" @click="fetchMapping">
            {{ mappingLoading ? 'Checking...' : 'Refresh Mapping' }}
          </button>
        </div>
        <div class="section-description">
          Confirms which items on the source server were matched to an item on each target server (by TMDb ID)
          before anything is copied. An item with no match on a target is skipped during a run.
        </div>

        <div v-if="sourceServerId === '' || targetServerIds.size === 0" class="state-msg small">
          Pick a source and at least one target above to preview the mapping.
        </div>
        <div v-else-if="mappingLoading" class="state-msg small">Checking mapping...</div>
        <div v-else-if="mapping.length === 0" class="state-msg small">No items found on the source server.</div>
        <template v-else>
          <div v-if="unmappedCount > 0" class="unmapped-warning">
            ⚠ {{ unmappedCount }} item(s) have no match on any selected target server and will be skipped.
          </div>
          <div class="mapping-table-wrap">
            <table class="mapping-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th v-for="id in Array.from(targetServerIds)" :key="id">
                    {{ memberOptions.find(o => o.id === id)?.label || id }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="entry in mapping" :key="entry.source_rating_key || entry.title || ''">
                  <td>{{ entry.title }}<span v-if="entry.year" class="mapping-year"> ({{ entry.year }})</span></td>
                  <td v-for="id in Array.from(targetServerIds)" :key="id">
                    <span v-if="entry.targets && entry.targets[id]" class="mapped-ok">✓ Mapped</span>
                    <span v-else class="mapped-missing">— No match</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.media-mirror-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #eef2ff;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.save-msg {
  font-size: 13px;
  color: var(--accent, #3dd6b7);
}

.section-note {
  font-size: 12px;
  color: #6b7a99;
  line-height: 1.5;
}

.state-msg {
  padding: 40px 20px;
  text-align: center;
  color: #a8b3cf;
}

.state-msg.small {
  padding: 16px 20px;
  font-size: 13px;
}

.state-msg.error-msg {
  color: #ff8a8a;
  padding: 12px 20px;
}

.section {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-header-inline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.section h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #eef2ff;
}

.section-description {
  font-size: 12px;
  color: #6b7a99;
  line-height: 1.5;
}

.enable-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #c9d1e0;
  cursor: pointer;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
}

.config-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 12px;
  color: #a8b3cf;
  font-weight: 600;
}

.toolbar-select {
  padding: 5px 10px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}

.toolbar-select:hover {
  border-color: rgba(61, 214, 183, 0.35);
}

.toolbar-select option {
  background: #1a1d2e;
  color: #c9d1e0;
}

.checkbox-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #c9d1e0;
  cursor: pointer;
}

.no-labels-hint {
  font-size: 12px;
  color: #6b7a99;
  font-style: italic;
}

.config-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

button.primary {
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 7px;
  border: none;
  background: var(--accent, #3dd6b7);
  color: #0b1220;
  cursor: pointer;
  transition: opacity 0.15s;
}

button.primary:hover:not(:disabled) {
  opacity: 0.9;
}

button.primary:disabled {
  opacity: 0.5;
  cursor: default;
}

button.secondary {
  padding: 7px 16px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  cursor: pointer;
  transition: all 0.15s;
}

button.secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.09);
  border-color: rgba(61, 214, 183, 0.35);
  color: #eef2ff;
}

button.secondary:disabled {
  opacity: 0.5;
  cursor: default;
}

button.secondary-small {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  cursor: pointer;
  transition: all 0.15s;
}

button.secondary-small:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.09);
  border-color: rgba(61, 214, 183, 0.35);
  color: #eef2ff;
}

button.secondary-small:disabled {
  opacity: 0.5;
  cursor: default;
}

.last-run-note {
  font-size: 12px;
  color: #a8b3cf;
}

.run-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent, #3dd6b7);
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 12px;
  color: #a8b3cf;
  white-space: nowrap;
}

.unmapped-warning {
  font-size: 12px;
  color: rgba(255, 180, 100, 0.9);
  background: rgba(255, 180, 100, 0.08);
  border: 1px solid rgba(255, 180, 100, 0.25);
  border-radius: 7px;
  padding: 8px 12px;
}

.mapping-table-wrap {
  overflow-x: auto;
}

.mapping-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.mapping-table th,
.mapping-table td {
  text-align: left;
  padding: 6px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  color: #c9d1e0;
  white-space: nowrap;
}

.mapping-table th {
  color: #a8b3cf;
  font-weight: 600;
  font-size: 12px;
}

.mapping-year {
  color: #6b7a99;
  font-size: 12px;
}

.mapped-ok {
  color: var(--accent, #3dd6b7);
}

.mapped-missing {
  color: #6b7a99;
}
</style>
