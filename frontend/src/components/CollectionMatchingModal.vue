<script setup lang="ts">
// "Collection matching" window (Collections page). Collections match across a
// library group's servers by name; this lets the user override that per
// collection -- pick which collection on each other server is the same one,
// choose "none" to split a wrong automatic match, or reset to automatic.
// Each change saves immediately (POST /api/media-server/collection-matching).
import { computed, onMounted, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

const props = defineProps<{
  serverId: string
  libraryId: string
}>()

const emit = defineEmits<{
  close: []
  // Fired on close when anything was saved, so the grid can re-fetch.
  changed: []
}>()

type CollectionRef = { rating_key: string; title: string }
type Row = { rating_key: string; title: string; partners: Record<string, string | null>; manual: boolean }
type MatchingState = {
  group: { id: string; name?: string } | null
  anchor_server_id?: string
  servers?: { server_id: string; label: string }[]
  collections?: Record<string, CollectionRef[]>
  rows?: Row[]
}

const apiBase = getApiBase()
const state = ref<MatchingState | null>(null)
const loading = ref(true)
const error = ref('')
const savingRow = ref<string | null>(null)
const search = ref('')
const showManualOnly = ref(false)
const didChange = ref(false)

const anchorLabel = computed(() =>
  state.value?.servers?.find(s => s.server_id === state.value?.anchor_server_id)?.label || 'Main server'
)
const otherServers = computed(() =>
  (state.value?.servers || []).filter(s => s.server_id !== state.value?.anchor_server_id)
)

const filteredRows = computed(() => {
  const q = search.value.trim().toLowerCase()
  return (state.value?.rows || []).filter(r => {
    if (showManualOnly.value && !r.manual) return false
    if (!q) return true
    if (r.title.toLowerCase().includes(q)) return true
    // Also match on the partner collections' titles.
    return otherServers.value.some(s => {
      const rk = r.partners[s.server_id]
      const t = rk ? titleFor(s.server_id, rk) : ''
      return t.toLowerCase().includes(q)
    })
  })
})

// Collections on another server that no row currently matches -- shown as a
// hint, since those are the ones most likely to need linking by hand.
const unmatchedCounts = computed(() => {
  const out: Record<string, number> = {}
  for (const s of otherServers.value) {
    const used = new Set((state.value?.rows || []).map(r => r.partners[s.server_id]).filter(Boolean))
    out[s.server_id] = (state.value?.collections?.[s.server_id] || []).filter(c => !used.has(c.rating_key)).length
  }
  return out
})

function titleFor(serverId: string, ratingKey: string): string {
  return state.value?.collections?.[serverId]?.find(c => c.rating_key === ratingKey)?.title || ''
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch(
      `${apiBase}/api/media-server/collection-matching?server_id=${encodeURIComponent(props.serverId)}&library_id=${encodeURIComponent(props.libraryId)}`
    )
    if (!res.ok) throw new Error(`Failed to load (${res.status})`)
    state.value = await res.json()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load'
  } finally {
    loading.value = false
  }
}

async function save(row: Row, partners: Record<string, string | null>, reset = false) {
  if (!state.value?.group) return
  savingRow.value = row.rating_key
  error.value = ''
  try {
    const res = await fetch(`${apiBase}/api/media-server/collection-matching`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        group_id: state.value.group.id,
        anchor_rating_key: row.rating_key,
        partners,
        reset,
      }),
    })
    if (!res.ok) throw new Error(`Failed to save (${res.status})`)
    state.value = await res.json()
    didChange.value = true
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save'
  } finally {
    savingRow.value = null
  }
}

function onPartnerChange(row: Row, serverId: string, value: string) {
  // Save the whole row: every server's current choice, with this one changed.
  save(row, { ...row.partners, [serverId]: value || null })
}

function close() {
  if (didChange.value) emit('changed')
  emit('close')
}

onMounted(load)
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @click.self="close">
      <div class="modal glass">
        <div class="modal-header">
          <div>
            <p class="label">Collection matching</p>
            <h3>{{ state?.group?.name || 'Library group' }}</h3>
          </div>
          <button class="icon-btn" title="Close" @click="close">✕</button>
        </div>

        <p class="intro">
          Collections are matched across servers by name. Pick the matching collection on each
          server to link ones with different names, or choose "— none —" to split a wrong match.
          Changes save immediately.
        </p>

        <div v-if="loading" class="state muted">Loading…</div>
        <div v-else-if="error && !state" class="state error">{{ error }}</div>
        <div v-else-if="!state?.group" class="state muted">This library isn't in a library group.</div>
        <div v-else-if="otherServers.length === 0" class="state muted">
          This group only has one server, so there's nothing to match.
        </div>
        <template v-else>
          <div class="toolbar">
            <input v-model="search" class="search-input" type="text" placeholder="Search collections..." />
            <label class="manual-toggle">
              <input type="checkbox" v-model="showManualOnly" /> Manual matches only
            </label>
            <span class="hint">
              <template v-for="s in otherServers" :key="s.server_id">
                {{ unmatchedCounts[s.server_id] }} unmatched on {{ s.label }}.
              </template>
            </span>
          </div>
          <p v-if="error" class="state error inline">{{ error }}</p>

          <div class="table-wrap">
            <table class="match-table">
              <thead>
                <tr>
                  <th>{{ anchorLabel }}</th>
                  <th v-for="s in otherServers" :key="s.server_id">{{ s.label }}</th>
                  <th class="actions-col"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in filteredRows" :key="row.rating_key" :class="{ busy: savingRow === row.rating_key }">
                  <td class="title-cell">
                    {{ row.title }}
                    <span v-if="row.manual" class="manual-badge">Manual</span>
                  </td>
                  <td v-for="s in otherServers" :key="s.server_id">
                    <select
                      :value="row.partners[s.server_id] || ''"
                      :disabled="savingRow !== null"
                      @change="onPartnerChange(row, s.server_id, ($event.target as HTMLSelectElement).value)"
                    >
                      <option value="">— none —</option>
                      <option v-for="c in state?.collections?.[s.server_id] || []" :key="c.rating_key" :value="c.rating_key">
                        {{ c.title }}
                      </option>
                    </select>
                  </td>
                  <td class="actions-col">
                    <button
                      v-if="row.manual"
                      class="reset-btn"
                      :disabled="savingRow !== null"
                      title="Go back to matching by name"
                      @click="save(row, {}, true)"
                    >
                      Reset
                    </button>
                  </td>
                </tr>
                <tr v-if="filteredRows.length === 0">
                  <td :colspan="otherServers.length + 2" class="state muted">No collections match.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 16px;
}
.modal {
  width: min(960px, 100%);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px;
  border-radius: 14px;
  background: var(--surface, #12141a);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.label {
  margin: 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted, #8b93a7);
}
h3 {
  margin: 4px 0 0;
}
.icon-btn {
  background: transparent;
  border: none;
  color: var(--text-muted, #8b93a7);
  font-size: 16px;
  cursor: pointer;
  padding: 4px 8px;
}
.icon-btn:hover {
  color: var(--text-primary, #fff);
}
.intro {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted, #8b93a7);
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.search-input {
  flex: 1 1 220px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.1));
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary, #fff);
}
.manual-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  white-space: nowrap;
}
.hint {
  font-size: 12px;
  color: var(--text-muted, #8b93a7);
}
.table-wrap {
  overflow: auto;
  min-height: 0;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  border-radius: 10px;
}
.match-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.match-table th {
  position: sticky;
  top: 0;
  background: var(--surface, #12141a);
  text-align: left;
  padding: 10px 12px;
  font-weight: 600;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.08));
}
.match-table td {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  vertical-align: middle;
}
.match-table tr.busy {
  opacity: 0.6;
}
.match-table select {
  width: 100%;
  min-width: 180px;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.1));
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary, #fff);
}
.title-cell {
  font-weight: 500;
}
.manual-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 8px;
  border-radius: 6px;
  font-size: 11px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  background: rgba(61, 214, 183, 0.15);
  color: var(--accent, #3dd6b7);
}
.actions-col {
  width: 1%;
  white-space: nowrap;
}
.reset-btn {
  padding: 5px 10px;
  font-size: 12px;
  border-radius: 6px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.1));
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary, #fff);
  cursor: pointer;
}
.reset-btn:hover:not(:disabled) {
  border-color: var(--accent, #3dd6b7);
}
.reset-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.state {
  padding: 16px;
  text-align: center;
}
.state.inline {
  padding: 0;
  text-align: left;
}
.muted {
  color: var(--text-muted, #8b93a7);
}
.error {
  color: #f05d7b;
}
</style>
