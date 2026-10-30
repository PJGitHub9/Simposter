<script setup lang="ts">
// Live Kometa files: overlay YAMLs on the Simposter server that another tool
// (e.g. UMTK) rewrites. Each is re-read every N hours and re-imported when it
// changes; see backend/live_kometa.py. Lives in Overlay Manager → Advanced.
import { onMounted, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'
import ServerFilePicker from './ServerFilePicker.vue'

interface LiveFile {
  id: string
  path: string
  name: string | null
  library_type: string
  config_id: string | null
  interval_hours: number
  enabled: boolean
  refresh_posters: boolean
  last_checked_at: string | null
  last_changed_at: string | null
  last_status: string | null
  last_message: string | null
  next_run: string | null
}

const emit = defineEmits<{ changed: []; openOverlay: [configId: string] }>()
const apiBase = getApiBase()

const files = ref<LiveFile[]>([])
const loading = ref(false)
const busy = ref<string | null>(null)
const error = ref('')

const INTERVALS = [
  { hours: 1, label: 'Every hour' },
  { hours: 3, label: 'Every 3 hours' },
  { hours: 6, label: 'Every 6 hours' },
  { hours: 12, label: 'Every 12 hours' },
  { hours: 24, label: 'Once a day' },
]

const showPicker = ref(false)
const onPicked = (path: string) => {
  form.value.path = path
  showPicker.value = false
}

const blank = () => ({ id: '' as string, path: '', name: '', library_type: 'movie', interval_hours: 6, enabled: true, refresh_posters: true })
const form = ref(blank())
const showForm = ref(false)

const load = async () => {
  loading.value = true
  try {
    const res = await fetch(`${apiBase}/api/live-kometa-files`)
    if (res.ok) files.value = (await res.json()).files || []
  } finally {
    loading.value = false
  }
}

const startAdd = () => { form.value = blank(); error.value = ''; showForm.value = true }
const startEdit = (f: LiveFile) => {
  form.value = { id: f.id, path: f.path, name: f.name || '', library_type: f.library_type, interval_hours: f.interval_hours, enabled: f.enabled, refresh_posters: f.refresh_posters }
  error.value = ''
  showForm.value = true
}

const save = async () => {
  error.value = ''
  busy.value = 'save'
  try {
    const res = await fetch(`${apiBase}/api/live-kometa-files`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form.value, id: form.value.id || undefined }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) { error.value = data.detail || 'Could not save'; return }
    showForm.value = false
    await load()
    emit('changed')
  } finally {
    busy.value = null
  }
}

const syncNow = async (f: LiveFile) => {
  busy.value = f.id
  try {
    await fetch(`${apiBase}/api/live-kometa-files/${f.id}/sync?force=true`, { method: 'POST' })
    await load()
    emit('changed')
  } finally {
    busy.value = null
  }
}

const setEnabled = async (f: LiveFile, enabled: boolean) => {
  busy.value = f.id
  try {
    await fetch(`${apiBase}/api/live-kometa-files`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...f, enabled }),
    })
    await load()
  } finally {
    busy.value = null
  }
}

const remove = async (f: LiveFile) => {
  if (!confirm(`Stop watching ${f.name || f.path}? The overlay it created stays; delete it from the list above if you don't need it.`)) return
  await fetch(`${apiBase}/api/live-kometa-files/${f.id}`, { method: 'DELETE' })
  await load()
}

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—')
const fileName = (p: string) => p.split(/[\\/]/).pop() || p

onMounted(load)
</script>

<template>
  <div class="live">
    <p class="intro">
      For overlay files another tool keeps rewriting, like the ones UMTK updates daily for Kometa. Simposter re-reads the file on a
      schedule, re-imports it into the same overlay when it changed, and can re-render the posters whose overlay now looks different
      (Overlay Refresh). The path is on the Simposter server: in Docker, mount the folder with the file into the container.
    </p>

    <div v-if="loading && !files.length" class="muted">Loading…</div>
    <div v-else-if="!files.length && !showForm" class="muted">No live files yet.</div>

    <div v-for="f in files" :key="f.id" class="file" :class="{ paused: !f.enabled }">
      <div class="file-head">
        <div class="file-title">
          <strong>{{ f.name || fileName(f.path) }}</strong>
          <span class="tag">{{ f.library_type === 'show' ? 'TV' : f.library_type === 'both' ? 'Movies + TV' : 'Movies' }}</span>
          <span v-if="!f.enabled" class="tag paused-tag">Paused</span>
        </div>
        <div class="file-actions">
          <button type="button" class="link" :disabled="busy === f.id" @click="syncNow(f)">{{ busy === f.id ? 'Checking…' : 'Check now' }}</button>
          <button v-if="f.config_id" type="button" class="link" @click="emit('openOverlay', f.config_id)">Open overlay</button>
          <button type="button" class="link" @click="startEdit(f)">Edit</button>
          <button type="button" class="link" :disabled="busy === f.id" @click="setEnabled(f, !f.enabled)">{{ f.enabled ? 'Pause' : 'Resume' }}</button>
          <button type="button" class="link danger" @click="remove(f)">Remove</button>
        </div>
      </div>
      <div class="file-path" :title="f.path">{{ f.path }}</div>
      <div class="file-meta">
        <span>{{ INTERVALS.find(i => i.hours === f.interval_hours)?.label || `Every ${f.interval_hours} hours` }}</span>
        <span>Last checked: {{ when(f.last_checked_at) }}</span>
        <span>Last change: {{ when(f.last_changed_at) }}</span>
        <span v-if="f.enabled && f.next_run">Next check: {{ when(f.next_run) }}</span>
      </div>
      <div v-if="f.last_message" class="file-status" :class="f.last_status || ''">{{ f.last_message }}</div>
    </div>

    <div v-if="showForm" class="form">
      <label class="full">
        <span>File path on the Simposter server</span>
        <div class="path-row">
          <input v-model="form.path" type="text" placeholder="/kometa/config/overlays/UMTK_MOVIES_UPCOMING_OVERLAYS.yml" />
          <button type="button" class="btn browse" @click="showPicker = true">Browse…</button>
        </div>
      </label>
      <ServerFilePicker v-if="showPicker" :start="form.path" @pick="onPicked" @close="showPicker = false" />
      <label>
        <span>Overlay name (optional)</span>
        <input v-model="form.name" type="text" placeholder="Same as the file name" />
      </label>
      <label>
        <span>Library type</span>
        <select v-model="form.library_type">
          <option value="movie">Movies</option>
          <option value="show">TV shows</option>
          <option value="both">Movies and TV shows</option>
        </select>
      </label>
      <label>
        <span>Check the file</span>
        <select v-model.number="form.interval_hours">
          <option v-for="i in INTERVALS" :key="i.hours" :value="i.hours">{{ i.label }}</option>
        </select>
      </label>
      <label class="check full">
        <input v-model="form.refresh_posters" type="checkbox" />
        <span>When it changes, re-render posters whose overlay now looks different (Overlay Refresh, in every {{ form.library_type === 'show' ? 'TV' : form.library_type === 'both' ? 'movie and TV' : 'movie' }} library)</span>
      </label>
      <p v-if="error" class="err full">{{ error }}</p>
      <div class="form-actions full">
        <button type="button" class="btn" :disabled="!form.path.trim() || busy === 'save'" @click="save">{{ busy === 'save' ? 'Saving…' : (form.id ? 'Save' : 'Add and import now') }}</button>
        <button type="button" class="link" @click="showForm = false">Cancel</button>
      </div>
    </div>
    <button v-else type="button" class="btn add" @click="startAdd">+ Add a live file</button>
    <p class="muted small">
      The overlay it creates works like any other: turn it on in a preset, or in the editor's Extras tab. Overlay Refresh only
      re-renders posters Simposter has sent since Overlay Refresh was added.
    </p>
  </div>
</template>

<style scoped>
.live { display: flex; flex-direction: column; gap: 0.6rem; }
.intro { margin: 0; font-size: 0.8rem; color: var(--text-secondary, #aaa); line-height: 1.45; }
.muted { color: var(--text-secondary, #888); font-size: 0.82rem; }
.small { font-size: 0.72rem; margin: 0; }
.file { border: 1px solid var(--border, #2a2f3e); border-radius: 8px; padding: 0.6rem 0.75rem; display: flex; flex-direction: column; gap: 0.3rem; background: rgba(255, 255, 255, 0.02); }
.file.paused { opacity: 0.7; }
.file-head { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.file-title { display: flex; align-items: center; gap: 0.4rem; color: var(--text-primary, #fff); font-size: 0.88rem; }
.tag { font-size: 0.66rem; padding: 0.05rem 0.4rem; border-radius: 8px; background: rgba(255, 255, 255, 0.08); color: var(--text-secondary, #aaa); }
.paused-tag { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
.file-actions { display: flex; gap: 0.2rem; flex-wrap: wrap; }
.file-path { font-family: ui-monospace, monospace; font-size: 0.72rem; color: var(--text-secondary, #888); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-meta { display: flex; flex-wrap: wrap; gap: 0.2rem 1rem; font-size: 0.72rem; color: var(--text-secondary, #888); }
.file-status { font-size: 0.75rem; color: var(--text-primary, #ddd); }
.file-status.error { color: #f87171; }
.file-status.updated { color: var(--accent, #3dd6b7); }
.form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.55rem; padding: 0.7rem; border: 1px solid var(--border, #2a2f3e); border-radius: 8px; }
.form label { display: flex; flex-direction: column; gap: 0.2rem; font-size: 0.72rem; color: var(--text-secondary, #888); }
.form .full { grid-column: 1 / -1; }
.path-row { display: flex; gap: 0.4rem; }
.path-row input { flex: 1; min-width: 0; }
.btn.browse { align-self: stretch; white-space: nowrap; }
.form input[type='text'], .form select { padding: 0.35rem 0.45rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.8rem; }
.form select { background-color: var(--surface-soft, #141824); color-scheme: dark; }
:root[data-theme='light'] .form select { color-scheme: light; }
.form label.check { flex-direction: row; align-items: center; gap: 0.45rem; color: var(--text-primary, #ddd); font-size: 0.78rem; }
.form-actions { display: flex; gap: 0.6rem; align-items: center; }
.err { color: #f87171; font-size: 0.78rem; margin: 0; }
.btn { align-self: flex-start; padding: 0.35rem 0.8rem; background: rgba(61, 214, 183, 0.1); border: 1px solid rgba(61, 214, 183, 0.35); border-radius: 6px; color: var(--accent, #3dd6b7); cursor: pointer; font-size: 0.8rem; }
.btn:disabled { opacity: 0.5; cursor: default; }
.link { background: none; border: none; color: var(--accent, #3dd6b7); cursor: pointer; font-size: 0.75rem; padding: 0.15rem 0.3rem; }
.link:disabled { opacity: 0.5; cursor: default; }
.link.danger { color: var(--text-secondary, #888); }
.link.danger:hover { color: #f87171; }
@media (max-width: 700px) { .form { grid-template-columns: 1fr; } }
</style>
