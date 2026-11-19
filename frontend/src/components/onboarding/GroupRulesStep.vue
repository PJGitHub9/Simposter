<script setup lang="ts">
// Setup wizard step: per library group, which Radarr (movies) / Sonarr (TV)
// it uses and its poster mode rules (Plex label / Radarr-Sonarr tag →
// Overlay only or Leave alone). Same rules editor as Settings → Libraries.
// Only groups whose link or rules were changed here are written.
import { computed, onMounted, reactive } from 'vue'
import { useSettingsStore, type PosterModeRule } from '@/stores/settings'
import { getApiBase } from '@/services/apiBase'
import PosterModeRules from '@/components/settings/PosterModeRules.vue'

const props = defineProps<{ defaults: { radarr: string | null; sonarr: string | null } }>()

const settings = useSettingsStore()
const apiBase = getApiBase()

type Local = { link: string; rules: PosterModeRule[]; labels: string[] }
const local = reactive<Record<string, Local>>({})

const groups = computed(() => settings.libraryGroups.value.filter(g => g.members.length > 0))
const instancesFor = (type: 'movie' | 'tv') =>
  settings.arrInstances.value.filter(i => i.enabled !== false && i.type === (type === 'tv' ? 'sonarr' : 'radarr'))
const plexMember = (id: string) => groups.value.find(g => g.id === id)?.members.find(m => m.serverId === 'plex-1')

const startLink = (g: { mediaType: 'movie' | 'tv'; arrInstanceId?: string | null }) => {
  if (g.arrInstanceId) return g.arrInstanceId
  const list = instancesFor(g.mediaType)
  const d = g.mediaType === 'tv' ? props.defaults.sonarr : props.defaults.radarr
  if (d && list.some(i => i.id === d)) return d
  return list[0]?.id || ''
}

const loadLabels = async (groupId: string, libraryId: string, type: 'movie' | 'tv') => {
  try {
    const path = type === 'tv' ? 'tv-shows' : 'movies'
    const res = await fetch(`${apiBase}/api/${path}/labels/all?library_id=${encodeURIComponent(libraryId)}`)
    if (res.ok) local[groupId]!.labels = (await res.json())?.labels || []
  } catch { /* suggestions only */ }
}

onMounted(() => {
  for (const g of groups.value) {
    local[g.id] = { link: startLink(g), rules: JSON.parse(JSON.stringify(g.posterModeRules || [])), labels: [] }
    const plex = plexMember(g.id)
    if (plex) void loadLabels(g.id, plex.libraryId, g.mediaType)
  }
})

const linkChanged = (g: { id: string; arrInstanceId?: string | null }) =>
  (local[g.id]?.link || null) !== (g.arrInstanceId || null)
const rulesChanged = (g: { id: string; posterModeRules?: PosterModeRule[] }) =>
  JSON.stringify(local[g.id]?.rules || []) !== JSON.stringify(g.posterModeRules || [])

const changed = () => groups.value.some(g => local[g.id] && (linkChanged(g) || rulesChanged(g)))

/** Write changed links/rules into the settings store. Returns the ids of groups
 *  whose rules changed (to re-check which titles they match). */
const apply = (): string[] => {
  const ruleIds: string[] = []
  settings.libraryGroups.value = settings.libraryGroups.value.map(g => {
    const l = local[g.id]
    if (!l) return g
    const next = { ...g }
    if (linkChanged(g)) next.arrInstanceId = l.link || null
    if (rulesChanged(g)) {
      next.posterModeRules = l.rules
      ruleIds.push(g.id)
    }
    return next
  })
  return ruleIds
}

defineExpose({ apply, changed })
</script>

<template>
  <div class="ob-form">
    <p class="ob-hint-text" style="margin-top: 0;">
      Rules let another app keep control of some posters: <strong>Overlay only</strong> keeps that
      app's poster and adds Simposter's overlays, <strong>Leave alone</strong> means Simposter never
      changes it. Match by a Plex label or a Radarr/Sonarr tag. Skip this if you don't need it.
    </p>
    <div v-for="g in groups" :key="g.id" class="ob-server-form">
      <div class="ob-server-heading" style="cursor: default;">
        {{ g.name }} <span class="ob-optional">{{ g.mediaType === 'tv' ? 'TV' : 'Movies' }}</span>
      </div>
      <template v-if="local[g.id]">
        <div v-if="instancesFor(g.mediaType).length" class="ob-key-row">
          <label class="ob-label">{{ g.mediaType === 'tv' ? 'Sonarr' : 'Radarr' }}</label>
          <select v-model="local[g.id]!.link" class="ob-input">
            <option value="">None</option>
            <option v-for="i in instancesFor(g.mediaType)" :key="i.id" :value="i.id">{{ i.name || i.url }}</option>
          </select>
        </div>
        <PosterModeRules
          :group-id="g.id"
          :rules="local[g.id]!.rules"
          :available-labels="local[g.id]!.labels"
          :has-plex="!!plexMember(g.id)"
          :arr-label="g.mediaType === 'tv' ? 'Sonarr' : 'Radarr'"
          :arr-instance-id="local[g.id]!.link || null"
          @update:rules="local[g.id]!.rules = $event"
        />
      </template>
    </div>
  </div>
</template>

<style scoped src="./onboardingForm.css"></style>
<style scoped>
select.ob-input { appearance: auto; }
</style>
