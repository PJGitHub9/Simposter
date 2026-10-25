<script setup lang="ts">
// Browse folders on the Simposter server and pick a .yml/.yaml file. A browser
// file picker can't be used: it only reads files from your own computer and
// never tells the page their path, while live files are read by the server.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

const props = defineProps<{ start?: string }>()
const emit = defineEmits<{ pick: [path: string]; close: [] }>()

type FileEntry = { name: string; size: number; modified: number }

const current = ref<string | null>(null)
const parent = ref<string | null>(null)
const dirs = ref<string[]>([])
const files = ref<FileEntry[]>([])
const roots = ref<string[]>([])
const loading = ref(false)
const error = ref('')
const typed = ref('')
const filter = ref('')

const sep = computed(() => (current.value && /^[A-Za-z]:\\/.test(current.value) ? '\\' : '/'))
const join = (dir: string, name: string) => (dir.endsWith('/') || dir.endsWith('\\') ? dir + name : dir + sep.value + name)

const shownDirs = computed(() => {
  const q = filter.value.trim().toLowerCase()
  return q ? dirs.value.filter(d => d.toLowerCase().includes(q)) : dirs.value
})
const shownFiles = computed(() => {
  const q = filter.value.trim().toLowerCase()
  return q ? files.value.filter(f => f.name.toLowerCase().includes(q)) : files.value
})

const open = async (path?: string | null) => {
  loading.value = true
  error.value = ''
  try {
    const qs = path ? `?path=${encodeURIComponent(path)}` : ''
    const res = await fetch(`${getApiBase()}/api/live-kometa-files/browse${qs}`)
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || `Couldn't open the folder (${res.status})`)
    current.value = data.path
    parent.value = data.parent
    dirs.value = data.dirs || []
    files.value = data.files || []
    roots.value = data.roots || []
    typed.value = data.path || ''
    filter.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    // Still show the starting points so there's somewhere to go.
    if (!roots.value.length) {
      const res = await fetch(`${getApiBase()}/api/live-kometa-files/browse`).catch(() => null)
      if (res?.ok) roots.value = (await res.json()).roots || []
    }
  } finally {
    loading.value = false
  }
}

const go = () => {
  const p = typed.value.trim()
  if (/\.ya?ml$/i.test(p)) emit('pick', p)
  else open(p)
}

const fmtSize = (n: number) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`)
const fmtDate = (s: number) => new Date(s * 1000).toLocaleString()

const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') emit('close') }
onMounted(() => {
  window.addEventListener('keydown', onKey)
  open(props.start?.trim() || null)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div class="fp-backdrop" @click.self="emit('close')">
      <div class="fp" role="dialog" aria-label="Pick a file on the Simposter server">
        <div class="fp-head">
          <strong>Pick a file on the Simposter server</strong>
          <button type="button" class="fp-x" aria-label="Close" @click="emit('close')">✕</button>
        </div>
        <p class="fp-help">These are the server's folders, not your computer's. In Docker, only folders mounted into the container show here.</p>

        <div class="fp-roots">
          <button v-for="r in roots" :key="r" type="button" class="fp-root" :class="{ active: current === r }" @click="open(r)">{{ r }}</button>
        </div>

        <form class="fp-path" @submit.prevent="go">
          <button type="button" class="fp-up" :disabled="!parent || loading" title="Up one folder" @click="open(parent)">↑</button>
          <input v-model="typed" type="text" placeholder="Type or paste a folder, then press Enter" />
          <button type="submit" class="fp-go" :disabled="!typed.trim() || loading">Go</button>
        </form>

        <input v-if="dirs.length + files.length > 8" v-model="filter" class="fp-filter" type="text" placeholder="Filter this folder" />

        <p v-if="error" class="fp-err">{{ error }}</p>

        <div class="fp-list">
          <p v-if="loading" class="fp-empty">Loading…</p>
          <p v-else-if="!current" class="fp-empty">Pick a starting folder above.</p>
          <template v-else>
            <button v-for="d in shownDirs" :key="'d' + d" type="button" class="fp-row" @click="open(join(current, d))">
              <span class="fp-icon">📁</span><span class="fp-name">{{ d }}</span>
            </button>
            <button v-for="f in shownFiles" :key="'f' + f.name" type="button" class="fp-row file" @click="emit('pick', join(current, f.name))">
              <span class="fp-icon">📄</span><span class="fp-name">{{ f.name }}</span>
              <span class="fp-meta">{{ fmtSize(f.size) }} · {{ fmtDate(f.modified) }}</span>
            </button>
            <p v-if="!shownDirs.length && !shownFiles.length" class="fp-empty">No folders or .yml files here.</p>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.fp-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: 1100; padding: 16px; }
.fp { width: min(640px, 100%); max-height: min(80vh, 720px); display: flex; flex-direction: column; gap: 0.55rem; padding: 1rem; background: var(--surface, #161b26); border: 1px solid var(--border, #2a2f3e); border-radius: 12px; color: var(--text-primary, #fff); }
.fp-head { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
.fp-x { background: none; border: none; color: var(--text-secondary, #888); cursor: pointer; font-size: 1rem; }
.fp-help { margin: 0; font-size: 0.75rem; color: var(--text-secondary, #888); }
.fp-roots { display: flex; flex-wrap: wrap; gap: 0.3rem; }
.fp-root { padding: 0.2rem 0.55rem; font-size: 0.72rem; font-family: ui-monospace, monospace; border-radius: 6px; border: 1px solid var(--border, #2a2f3e); background: rgba(255, 255, 255, 0.03); color: var(--text-primary, #ddd); cursor: pointer; }
.fp-root.active { border-color: var(--accent, #3dd6b7); color: var(--accent, #3dd6b7); }
.fp-path { display: flex; gap: 0.35rem; }
.fp-path input, .fp-filter { flex: 1; min-width: 0; padding: 0.35rem 0.45rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.78rem; font-family: ui-monospace, monospace; }
.fp-filter { font-family: inherit; }
.fp-up, .fp-go { padding: 0.3rem 0.65rem; background: rgba(61, 214, 183, 0.1); border: 1px solid rgba(61, 214, 183, 0.35); border-radius: 6px; color: var(--accent, #3dd6b7); cursor: pointer; font-size: 0.8rem; }
.fp-up:disabled, .fp-go:disabled { opacity: 0.5; cursor: default; }
.fp-err { margin: 0; color: #f87171; font-size: 0.78rem; }
.fp-list { flex: 1; min-height: 160px; overflow-y: auto; border: 1px solid var(--border, #2a2f3e); border-radius: 8px; padding: 0.25rem; }
.fp-row { display: flex; align-items: center; gap: 0.5rem; width: 100%; padding: 0.35rem 0.5rem; background: none; border: none; border-radius: 5px; color: var(--text-primary, #ddd); cursor: pointer; text-align: left; font-size: 0.8rem; }
.fp-row:hover { background: rgba(255, 255, 255, 0.05); }
.fp-row.file .fp-name { color: var(--accent, #3dd6b7); }
.fp-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fp-meta { font-size: 0.7rem; color: var(--text-secondary, #888); white-space: nowrap; }
.fp-empty { margin: 0.5rem; font-size: 0.78rem; color: var(--text-secondary, #888); }
@media (max-width: 520px) { .fp-meta { display: none; } }
</style>
