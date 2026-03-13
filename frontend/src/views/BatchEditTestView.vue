<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getApiBase } from '@/services/apiBase'
import { useNotification } from '@/composables/useNotification'
import { useMovies } from '@/composables/useMovies'

type Movie = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
}

type HistoryRecord = {
  id: number
  rating_key: string
  library_id?: string | null
  title?: string | null
  year?: number | null
  template_id?: string | null
  preset_id?: string | null
  action: 'saved_local' | 'sent_to_plex'
  save_path?: string | null
  created_at: string
}

const route = useRoute()
const apiBase = getApiBase()
const { error: showError } = useNotification()
const { movies: moviesCache, moviesLoaded } = useMovies()

const movies = ref<Movie[]>([])
const history = ref<HistoryRecord[]>([])
const loading = ref(false)
const historyLoading = ref(false)
const error = ref<string | null>(null)
const search = ref('')
const templateFilter = ref<string>('all')
const statusFilter = ref<'all' | 'saved_local' | 'sent_to_plex' | 'unsent'>('all')

const currentLibrary = computed(() => (route.query.library as string) || '')

const uniqueTemplates = computed(() => {
  const set = new Set<string>()
  history.value.forEach((r) => {
    if (r.template_id) set.add(r.template_id)
  })
  return Array.from(set).sort()
})

const historyByMovie = computed(() => {
  const map = new Map<
    string,
    { local?: HistoryRecord; plex?: HistoryRecord; last?: HistoryRecord }
  >()
  history.value.forEach((record) => {
    const existing = map.get(record.rating_key) || {}
    if (record.action === 'saved_local') {
      if (!existing.local || new Date(record.created_at) > new Date(existing.local.created_at)) {
        existing.local = record
      }
    } else if (record.action === 'sent_to_plex') {
      if (!existing.plex || new Date(record.created_at) > new Date(existing.plex.created_at)) {
        existing.plex = record
      }
    }
    if (!existing.last || new Date(record.created_at) > new Date(existing.last.created_at)) {
      existing.last = record
    }
    map.set(record.rating_key, existing)
  })
  return map
})

const fetchMovies = async () => {
  loading.value = true
  error.value = null
  try {
    if (!moviesLoaded.value) {
      const res = await fetch(
        `${apiBase}/api/movies${currentLibrary.value ? `?library_id=${encodeURIComponent(currentLibrary.value)}` : ''}`
      )
      if (!res.ok) throw new Error(`API error ${res.status}`)
      const data = (await res.json()) as Movie[]
      moviesCache.value = data
      moviesLoaded.value = true
    }
    movies.value = moviesCache.value
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Failed to load movies'
  } finally {
    loading.value = false
  }
}

// Reload when library changes
watch(currentLibrary, async (newLib, oldLib) => {
  if (newLib === oldLib) return
  moviesLoaded.value = false
  moviesCache.value = []
  movies.value = []
  await fetchMovies()
  await fetchHistory()
})

const fetchHistory = async () => {
  historyLoading.value = true
  try {
    const url = `${apiBase}/api/poster-history${
      currentLibrary.value ? `?library_id=${encodeURIComponent(currentLibrary.value)}` : ''
    }`
    const res = await fetch(url)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    history.value = data.records || []
  } catch (err: unknown) {
    showError(err instanceof Error ? err.message : 'Failed to load history')
  } finally {
    historyLoading.value = false
  }
}

const formatDate = (iso: string) => {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
}

const rows = computed(() => {
  return movies.value.map((m) => {
    const status = historyByMovie.value.get(m.key) || {}
    return {
      ...m,
      lastLocal: status.local,
      lastPlex: status.plex,
      lastAction: status.last,
    }
  })
})

const filteredRows = computed(() => {
  const q = search.value.toLowerCase().trim()
  return rows.value.filter((row) => {
    const matchQuery =
      !q ||
      row.title.toLowerCase().includes(q) ||
      (row.year && row.year.toString().includes(q))

    const matchTemplate =
      templateFilter.value === 'all' ||
      (row.lastLocal && row.lastLocal.template_id === templateFilter.value) ||
      (row.lastPlex && row.lastPlex.template_id === templateFilter.value)

    const hasHistory = row.lastLocal || row.lastPlex
    const matchStatus =
      statusFilter.value === 'all' ||
      (statusFilter.value === 'saved_local' && !!row.lastLocal) ||
      (statusFilter.value === 'sent_to_plex' && !!row.lastPlex) ||
      (statusFilter.value === 'unsent' && !hasHistory)

    return matchQuery && matchTemplate && matchStatus
  })
})

watch(
  () => currentLibrary.value,
  async () => {
    await fetchMovies()
    await fetchHistory()
  }
)

onMounted(async () => {
  await fetchMovies()
  await fetchHistory()
})
</script>

<template>
  <div class="batch-test-view">
    <div class="header">
      <div>
        <p class="eyebrow">Experimental</p>
        <h1>&#x270F;&#xFE0F; Batch Edit Tracker</h1>
        <p class="subtitle">Track which templates were used, when posters were saved or sent to Plex.</p>
      </div>
      <div class="pill">{{ filteredRows.length }} items</div>
    </div>

    <div class="filters">
      <input v-model="search" class="input" placeholder="Search title or year..." />
      <select v-model="templateFilter" class="input select">
        <option value="all">All templates</option>
        <option v-for="tmpl in uniqueTemplates" :key="tmpl" :value="tmpl">
          Template: {{ tmpl }}
        </option>
      </select>
      <select v-model="statusFilter" class="input select">
        <option value="all">All statuses</option>
        <option value="sent_to_plex">Sent to Plex</option>
        <option value="saved_local">Saved locally</option>
        <option value="unsent">No history</option>
      </select>
      <button class="btn ghost" :disabled="historyLoading || loading" @click="fetchHistory">
        Refresh history
      </button>
    </div>

    <div v-if="loading || historyLoading" class="loading">
      <div class="spinner"></div>
      <p>Loading…</p>
    </div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <div class="grid">
      <div v-for="row in filteredRows" :key="row.key" class="card">
        <div class="thumb">
          <img
            :src="`${apiBase}/api/movie/${row.key}/poster${currentLibrary ? `?library_id=${encodeURIComponent(currentLibrary)}` : ''}`"
            :alt="row.title"
            loading="lazy"
          />
        </div>
        <div class="body">
          <div class="title">
            <h3>{{ row.title }}</h3>
            <span v-if="row.year" class="year">{{ row.year }}</span>
          </div>

          <div class="status">
            <div class="badge muted" v-if="!row.lastLocal && !row.lastPlex">No history yet</div>
            <div v-if="row.lastLocal" class="badge success">
              Saved {{ formatDate(row.lastLocal.created_at) }}
              <span v-if="row.lastLocal.template_id" class="pill tiny">Template {{ row.lastLocal.template_id }}</span>
            </div>
            <div v-if="row.lastPlex" class="badge info">
              Sent to Plex {{ formatDate(row.lastPlex.created_at) }}
              <span v-if="row.lastPlex.template_id" class="pill tiny">Template {{ row.lastPlex.template_id }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.batch-test-view {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.eyebrow {
  margin: 0 0 0.35rem 0;
  font-size: 0.9rem;
  letter-spacing: 0.04em;
  color: var(--accent, #3dd6b7);
  text-transform: uppercase;
}

.subtitle {
  margin: 0.25rem 0 0;
  color: var(--text-secondary, #98a1b3);
}

.pill {
  align-self: center;
  padding: 0.5rem 0.85rem;
  border-radius: 999px;
  background: rgba(61, 214, 183, 0.14);
  color: var(--accent, #3dd6b7);
  font-weight: 600;
  font-size: 0.95rem;
}

.filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.75rem;
  align-items: center;
}

.input {
  width: 100%;
  padding: 0.75rem 0.85rem;
  border-radius: 8px;
  border: 1px solid var(--border, #2a2f3e);
  background: var(--surface, #1c2130);
  color: var(--text-primary, #fff);
}

.select {
  cursor: pointer;
}

.btn {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  border: 1px solid var(--border, #2a2f3e);
  background: var(--surface, #1c2130);
  color: var(--text-primary, #fff);
  cursor: pointer;
  transition: all 0.2s;
}

.btn.ghost:hover:not(:disabled) {
  border-color: var(--accent, #3dd6b7);
  color: var(--accent, #3dd6b7);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading,
.error {
  padding: 1rem;
  color: var(--text-secondary, #98a1b3);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1rem;
}

.card {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 0.75rem;
  padding: 0.9rem;
  border-radius: 12px;
  background: var(--surface, #1a1f2e);
  border: 1px solid var(--border, #2a2f3e);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
}

.thumb img {
  width: 100%;
  border-radius: 8px;
  object-fit: cover;
  aspect-ratio: 2/3;
  background: #0f111a;
}

.body {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.title h3 {
  margin: 0;
  color: var(--text-primary, #fff);
}

.year {
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-secondary, #98a1b3);
  font-size: 0.8rem;
}

.status {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 10px;
  font-size: 0.9rem;
  width: fit-content;
}

.badge.success {
  background: rgba(61, 214, 183, 0.14);
  color: var(--accent, #3dd6b7);
  border: 1px solid rgba(61, 214, 183, 0.3);
}

.badge.info {
  background: rgba(91, 141, 238, 0.14);
  color: #8eb4ff;
  border: 1px solid rgba(91, 141, 238, 0.4);
}

.badge.muted {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary, #98a1b3);
  border: 1px dashed rgba(255, 255, 255, 0.1);
}

.pill.tiny {
  padding: 0.2rem 0.5rem;
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-secondary, #c5cede);
  border-radius: 999px;
  font-size: 0.75rem;
}
</style>
