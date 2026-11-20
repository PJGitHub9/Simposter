<script setup lang="ts">
// "Settings on other pages": a short list of settings that are saved on their
// own pages (not by this page's Save button), with their current values and a
// link to each. Read-only; every value is fetched fresh when the tab opens.
import { computed, onMounted, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore } from '@/stores/settings'
import { useServerless } from '@/composables/useServerless'

const apiBase = getApiBase()
const settings = useSettingsStore()
const { serverless } = useServerless()

const DRIFT_LABELS: Record<string, string> = {
  off: "Don't check",
  list: 'Only list them',
  notify: 'List and notify',
  resend: "Put Simposter's version back",
}

const loading = ref(true)
const driftAction = ref<string | null>(null)
const driftTracked = ref<number | null>(null)
const ratingsDays = ref<number | null>(null)
const listsHours = ref<number | null>(null)
const liveFiles = ref<Array<{ enabled?: boolean }> | null>(null)
const groupStatus = ref<Record<string, { mirror: { enabled: boolean }; overlayRefresh: { enabled: boolean } }> | null>(null)

const getJson = async (path: string) => {
  try {
    const res = await fetch(`${apiBase}${path}`)
    return res.ok ? await res.json() : null
  } catch {
    return null
  }
}

onMounted(async () => {
  const [drift, refresh, live, groups] = await Promise.all([
    serverless.value ? null : getJson('/api/poster-drift'),
    getJson('/api/overlay-refresh/data-refresh'),
    getJson('/api/live-kometa-files'),
    serverless.value ? null : getJson('/api/media-server/library-groups/status'),
  ])
  if (drift) {
    driftAction.value = drift.action ?? null
    driftTracked.value = typeof drift.tracked === 'number' ? drift.tracked : null
  }
  if (refresh) {
    ratingsDays.value = refresh.ratingsDays ?? null
    listsHours.value = refresh.listsHours ?? null
  }
  if (live) liveFiles.value = live.files || []
  if (groups) groupStatus.value = groups.groups || {}
  loading.value = false
})

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

const groupCounts = computed(() => {
  const all = Object.values(groupStatus.value || {})
  return {
    total: all.length,
    mirror: all.filter(g => g.mirror?.enabled).length,
    refresh: all.filter(g => g.overlayRefresh?.enabled).length,
  }
})

interface Row {
  name: string
  what: string
  value: string
  to: string | { name: string; query?: Record<string, string> }
  linkText: string
}

const rows = computed<Row[]>(() => {
  const out: Row[] = []
  const dash = loading.value ? '…' : 'Unknown'
  if (!serverless.value) {
    out.push({
      name: 'Changed outside Simposter',
      what: 'What a scan does when a poster, logo or backdrop Simposter sent was changed on the server.',
      value: driftAction.value
        ? `${DRIFT_LABELS[driftAction.value] || driftAction.value}${driftTracked.value != null ? ` · ${plural(driftTracked.value, 'tracked image')}` : ''}`
        : dash,
      to: { name: 'history', query: { tab: 'drift' } },
      linkText: 'History',
    })
    const c = groupCounts.value
    out.push({
      name: 'Media Mirror',
      what: 'Copies artwork from one server to the others in a library group. Set per group.',
      value: groupStatus.value ? (c.total ? `On for ${c.mirror} of ${plural(c.total, 'group')}` : 'No library groups') : dash,
      to: { name: 'settings', query: { tab: 'libraries' } },
      linkText: 'Libraries',
    })
    out.push({
      name: 'Overlay Refresh',
      what: 'Re-sends posters whose overlay now looks different, on a schedule. Set per group.',
      value: groupStatus.value ? (c.total ? `Scheduled for ${c.refresh} of ${plural(c.total, 'group')}` : 'No library groups') : dash,
      to: { name: 'settings', query: { tab: 'libraries' } },
      linkText: 'Libraries',
    })
  }
  out.push({
    name: 'Ratings & lists refresh',
    what: 'How long overlay ratings and lists are kept before they are fetched again.',
    value: ratingsDays.value != null && listsHours.value != null
      ? `Ratings every ${plural(ratingsDays.value, 'day')}, lists every ${plural(listsHours.value, 'hour')}`
      : dash,
    to: { name: 'overlay-config-manager', query: { section: 'scheduler' } },
    linkText: 'Overlays → Scheduler',
  })
  const files = liveFiles.value
  out.push({
    name: 'Live Kometa files',
    what: 'Kometa overlay files Simposter re-reads on a schedule.',
    value: files
      ? (files.length ? `${plural(files.length, 'file')}, ${files.filter(f => f.enabled !== false).length} active` : 'None')
      : dash,
    to: { name: 'overlay-config-manager', query: { section: 'advanced' } },
    linkText: 'Overlays → Advanced',
  })
  if (serverless.value || settings.posterApiEnabledSaved.value) {
    out.push({
      name: 'Poster API',
      what: 'Default presets, wait time and pinned posters for other apps requesting posters.',
      value: 'On',
      to: { name: 'poster-api' },
      linkText: 'Poster API',
    })
  }
  return out
})
</script>

<template>
  <div class="section">
    <h3>Settings on other pages</h3>
    <p class="section-description">
      These are set and saved on their own pages, not with this page's Save button.
    </p>
    <div class="other-list">
      <div v-for="row in rows" :key="row.name" class="other-row">
        <div class="other-main">
          <div class="other-name">{{ row.name }}</div>
          <div class="other-what">{{ row.what }}</div>
        </div>
        <div class="other-value">{{ row.value }}</div>
        <router-link :to="row.to" class="other-link">{{ row.linkText }} →</router-link>
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
  margin-bottom: 20px;
}
.section h3 {
  margin: 0 0 6px 0;
  font-size: 18px;
}
.section-description {
  margin: 0 0 14px 0;
  font-size: 14px;
  color: var(--text-muted);
  line-height: 1.5;
}
.other-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.other-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 220px) auto;
  gap: 14px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
}
.other-name {
  font-weight: 600;
  font-size: 14px;
}
.other-what {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}
.other-value {
  font-size: 13px;
}
.other-link {
  font-size: 13px;
  color: var(--accent, #3dd6b7);
  text-decoration: none;
  white-space: nowrap;
}
.other-link:hover {
  text-decoration: underline;
}
@media (max-width: 600px) {
  .other-row {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
  }
}
</style>
