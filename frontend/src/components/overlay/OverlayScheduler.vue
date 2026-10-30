<script setup lang="ts">
// Overlay Manager → Scheduler: how often the data overlays depend on is
// re-fetched (ratings, lists: these cost API calls), plus each library
// group's Overlay Refresh schedule, which re-checks posters against that
// stored data with no API calls of its own. See backend/list_sources.py
// (get_refresh_settings) and backend/overlay_refresh.py (prepare_data).
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

interface GroupSchedule {
  id: string
  name: string
  mediaType: string
  members: { serverId: string; libraryId: string }[]
  enabled: boolean
  scheduleCron: string
  lastRunAt?: string | null
  nextRun?: string | null
}

const ratingsDays = ref(45)
const listsHours = ref(24)
const saved = ref({ ratingsDays: 45, listsHours: 24 })
const groups = ref<GroupSchedule[]>([])
const loading = ref(false)
const saving = ref(false)
const message = ref<{ ok: boolean; text: string } | null>(null)
// "Refresh now" for lists/ratings, and per-group Overlay Refresh runs.
const dataRefresh = ref<{ state?: string; lists?: number; ratings?: number; error?: string | null }>({})
const runs = ref<Record<string, string | undefined>>({})
const dataMessage = ref<{ ok: boolean; text: string } | null>(null)
let pollTimer: ReturnType<typeof setTimeout> | null = null
const anyRunning = computed(() => dataRefresh.value.state === 'running' || Object.values(runs.value).includes('running'))

const dirty = computed(() => ratingsDays.value !== saved.value.ratingsDays || listsHours.value !== saved.value.listsHours)

async function load() {
  loading.value = true
  try {
    const res = await fetch(`${getApiBase()}/api/overlay-refresh/data-refresh`)
    if (res.ok) {
      const data = await res.json()
      ratingsDays.value = data.ratingsDays
      listsHours.value = data.listsHours
      saved.value = { ratingsDays: data.ratingsDays, listsHours: data.listsHours }
      groups.value = data.groups || []
      applyStatus(data)
    }
  } catch { /* leave defaults */ }
  loading.value = false
}

function applyStatus(data: { data_refresh?: typeof dataRefresh.value; runs?: Record<string, string | undefined> }) {
  const wasRefreshing = dataRefresh.value.state === 'running'
  dataRefresh.value = data.data_refresh || {}
  runs.value = data.runs || {}
  if (wasRefreshing && dataRefresh.value.state === 'done') {
    dataMessage.value = { ok: true, text: `Fetched ${dataRefresh.value.lists || 0} list(s) and ${dataRefresh.value.ratings || 0} rating(s)` }
  } else if (wasRefreshing && dataRefresh.value.state === 'error') {
    dataMessage.value = { ok: false, text: dataRefresh.value.error || 'Refresh failed' }
  }
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = anyRunning.value ? setTimeout(poll, 2000) : null
}

async function poll() {
  try {
    const res = await fetch(`${getApiBase()}/api/overlay-refresh/data-refresh`)
    if (res.ok) {
      const data = await res.json()
      groups.value = data.groups || groups.value
      applyStatus(data)
    }
  } catch { /* try again on the next tick */ }
}

async function refreshDataNow() {
  dataMessage.value = null
  try {
    const res = await fetch(`${getApiBase()}/api/overlay-refresh/data-refresh/now`, { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || 'Could not start')
    dataRefresh.value = { state: 'running' }
    if (pollTimer) clearTimeout(pollTimer)
    pollTimer = setTimeout(poll, 1500)
  } catch (e) {
    dataMessage.value = { ok: false, text: e instanceof Error ? e.message : 'Could not start' }
  }
}

async function runGroupNow(g: GroupSchedule) {
  try {
    const res = await fetch(`${getApiBase()}/api/overlay-refresh/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_id: g.id, apply: true }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || 'Could not start')
    runs.value = { ...runs.value, [g.id]: 'running' }
    if (pollTimer) clearTimeout(pollTimer)
    pollTimer = setTimeout(poll, 1500)
  } catch (e) {
    dataMessage.value = { ok: false, text: `${g.name || g.id}: ${e instanceof Error ? e.message : 'Could not start'}` }
  }
}

onBeforeUnmount(() => { if (pollTimer) clearTimeout(pollTimer) })

async function save() {
  saving.value = true
  message.value = null
  try {
    const res = await fetch(`${getApiBase()}/api/overlay-refresh/data-refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ratingsDays: Number(ratingsDays.value), listsHours: Number(listsHours.value) }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Could not save')
    ratingsDays.value = data.ratingsDays
    listsHours.value = data.listsHours
    saved.value = { ratingsDays: data.ratingsDays, listsHours: data.listsHours }
    message.value = { ok: true, text: 'Saved' }
  } catch (e) {
    message.value = { ok: false, text: e instanceof Error ? e.message : 'Could not save' }
  }
  saving.value = false
}

/** The library page of a group, for its Overlay Refresh link. */
const refreshLink = (g: GroupSchedule) => {
  const plex = g.members.find(m => m.serverId === 'plex-1')
  const member = plex || g.members[0]
  const query: Record<string, string> = member ? { library: member.libraryId } : {}
  if (member && !plex) query.server = member.serverId
  return { name: g.mediaType === 'tv' ? 'tv-overlay-refresh' : 'overlay-refresh', query }
}

const fmt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : '')

/** "0 * * * *" -> "Every hour", for the common presets the Overlay Refresh page offers. */
const describeCron = (cron: string): string => {
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) return cron
  const [min, hour, dom, mon, dow] = parts
  if (dom === '*' && mon === '*' && dow === '*') {
    if (hour === '*' && /^\d+$/.test(min!)) return 'Every hour'
    const step = /^\*\/(\d+)$/.exec(hour!)
    if (step && /^\d+$/.test(min!)) return `Every ${step[1]} hours`
    if (/^\d+$/.test(hour!) && /^\d+$/.test(min!)) return `Daily at ${hour!.padStart(2, '0')}:${min!.padStart(2, '0')}`
  }
  return cron
}

onMounted(load)
</script>

<template>
  <div class="scheduler">
    <p class="intro">
      Ratings and lists come from outside services (MDBList, WeTrakr, SIMKL, Floppy), so fetching them costs API calls.
      Simposter stores them and only fetches again when they're older than the times below. A movie's file name,
      quality and edition don't need this: a scan or webhook picks up those changes.
    </p>

    <div class="fields">
      <label class="field">
        <span class="label">Re-check ratings every</span>
        <span class="input-row"><input v-model.number="ratingsDays" type="number" min="1" max="90" step="1" /> days</span>
        <span class="help">One request per 100 items, only for items whose overlay uses a rating.</span>
      </label>
      <label class="field">
        <span class="label">Re-check lists every</span>
        <span class="input-row"><input v-model.number="listsHours" type="number" min="1" max="720" step="1" /> hours</span>
        <span class="help">A few requests per list (lists come a page at a time), only for lists an overlay uses.</span>
      </label>
    </div>
    <div class="actions">
      <button type="button" class="btn-primary" :disabled="!dirty || saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
      <span v-if="message" class="msg" :class="{ bad: !message.ok }">{{ message.text }}</span>
      <button
        type="button"
        class="btn-secondary"
        :disabled="dataRefresh.state === 'running'"
        title="Fetch every list your overlays use, and the ratings of every tracked poster, now (ignoring the times above). Doesn't change any poster: run Overlay Refresh for that."
        @click="refreshDataNow"
      >{{ dataRefresh.state === 'running' ? 'Refreshing ratings & lists…' : 'Refresh ratings & lists now' }}</button>
      <span v-if="dataMessage" class="msg" :class="{ bad: !dataMessage.ok }">{{ dataMessage.text }}</span>
    </div>

    <h3 class="sub">Overlay Refresh schedules</h3>
    <p class="intro">
      Overlay Refresh re-checks the posters Simposter sent and re-renders any whose overlay would now look different
      (a new rating, joining or leaving a list, a label change after a scan). It uses the stored ratings and lists, and
      first fetches any that are due, so it makes no other API calls. Each library group has its own schedule.
    </p>
    <p v-if="loading" class="intro">Loading…</p>
    <table v-else-if="groups.length" class="groups">
      <thead>
        <tr><th>Library group</th><th>Schedule</th><th>Next run</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="g in groups" :key="g.id">
          <td>{{ g.name || g.id }} <span class="kind">{{ g.mediaType === 'tv' ? 'TV' : 'Movies' }}</span></td>
          <td>{{ g.enabled && g.scheduleCron ? describeCron(g.scheduleCron) : 'Off' }}</td>
          <td>{{ g.enabled ? fmt(g.nextRun) : '' }}</td>
          <td class="row-actions">
            <button
              type="button"
              class="btn-small"
              :disabled="runs[g.id] === 'running'"
              title="Re-check this group's posters now and re-send the ones whose overlay would look different"
              @click="runGroupNow(g)"
            >{{ runs[g.id] === 'running' ? 'Running…' : 'Run now' }}</button>
            <router-link :to="refreshLink(g)" class="link">Open Overlay Refresh</router-link>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="intro">No library groups yet (Settings → Libraries).</p>
  </div>
</template>

<style scoped>
.scheduler { display: flex; flex-direction: column; gap: 0.75rem; }
.intro { margin: 0; font-size: 0.8rem; color: var(--text-secondary, #888); line-height: 1.45; }
.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.9rem; }
.field { display: flex; flex-direction: column; gap: 0.3rem; }
.label { font-size: 0.82rem; font-weight: 600; color: var(--text-primary, #fff); }
.input-row { display: flex; align-items: center; gap: 0.45rem; font-size: 0.8rem; color: var(--text-secondary, #888); }
.input-row input {
  width: 6rem; padding: 0.4rem 0.5rem; background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border, #2a2f3e); border-radius: 6px; color: var(--text-primary, #fff);
}
.input-row input:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.help { font-size: 0.72rem; color: var(--text-secondary, #888); }
.actions { display: flex; align-items: center; gap: 0.75rem; }
.btn-primary {
  padding: 0.45rem 1rem; background: var(--accent, #3dd6b7); color: #0b0f17; border: none;
  border-radius: 6px; font-weight: 600; cursor: pointer;
}
.btn-primary:disabled { opacity: 0.5; cursor: default; }
.actions { flex-wrap: wrap; }
.btn-secondary, .btn-small {
  background: rgba(255, 255, 255, 0.04); color: var(--text-primary, #fff); border: 1px solid var(--border, #2a2f3e);
  border-radius: 6px; cursor: pointer;
}
.btn-secondary { padding: 0.45rem 1rem; margin-left: auto; }
.btn-small { padding: 0.2rem 0.6rem; font-size: 0.75rem; }
.btn-secondary:hover:not(:disabled), .btn-small:hover:not(:disabled) { border-color: var(--accent, #3dd6b7); }
.btn-secondary:disabled, .btn-small:disabled { opacity: 0.5; cursor: default; }
.row-actions { display: flex; align-items: center; justify-content: flex-end; gap: 0.75rem; }
.msg { font-size: 0.78rem; color: var(--accent, #3dd6b7); }
.msg.bad { color: #f87171; }
.sub { margin: 0.6rem 0 0; font-size: 0.95rem; color: var(--text-primary, #fff); }
.groups { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.groups th { text-align: left; font-weight: 600; color: var(--text-secondary, #888); padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border, #2a2f3e); }
.groups td { padding: 0.45rem 0.5rem; border-bottom: 1px solid rgba(255, 255, 255, 0.04); color: var(--text-primary, #fff); }
.kind { margin-left: 0.4rem; font-size: 0.68rem; color: var(--text-secondary, #888); }
.link { color: var(--accent, #3dd6b7); }
</style>
