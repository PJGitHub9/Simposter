<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PosterModeRule } from '@/stores/settings'
import { fetchRuleCounts, ruleMatchCounts } from '@/services/posterModes'
import { getApiBase } from '@/services/apiBase'

const props = defineProps<{
  groupId: string
  rules: PosterModeRule[]
  availableLabels: string[]
  // The group has a Plex library (Plex label rules can match).
  hasPlex: boolean
  // 'Radarr' / 'Sonarr': which app a tag rule reads for this group's media type.
  arrLabel: string
  // The linked Radarr/Sonarr instance, if any (tag rules can match).
  arrInstanceId?: string | null
}>()

const emit = defineEmits<{
  (e: 'update:rules', rules: PosterModeRule[]): void
}>()

const labelListId = computed(() => `pm-labels-${props.groupId}`)
const tagListId = computed(() => `pm-tags-${props.groupId}`)
const counts = computed(() => ruleMatchCounts.value[props.groupId] || [])
const knownTags = ref<string[]>([])

async function loadTags() {
  knownTags.value = []
  if (!props.arrInstanceId) return
  try {
    const res = await fetch(`${getApiBase()}/api/arr/${encodeURIComponent(props.arrInstanceId)}/tags`)
    if (res.ok) knownTags.value = (await res.json()).tags || []
  } catch {
    /* suggestions only */
  }
}
watch(() => props.arrInstanceId, loadTags, { immediate: true })

// Counts as of now (a scan may have matched titles since the last Save).
async function loadCounts() {
  const id = props.groupId
  if (!id) return
  const perRule = await fetchRuleCounts(id)
  if (perRule && props.groupId === id) ruleMatchCounts.value = { ...ruleMatchCounts.value, [id]: perRule }
}
watch(() => props.groupId, loadCounts, { immediate: true })

function update(i: number, patch: Partial<PosterModeRule>) {
  emit('update:rules', props.rules.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
}
function remove(i: number) {
  emit('update:rules', props.rules.filter((_, idx) => idx !== i))
}
function add() {
  const source: PosterModeRule['source'] = props.hasPlex || !props.arrInstanceId ? 'plex_label' : 'arr_tag'
  emit('update:rules', [...props.rules, { source, value: '', mode: 'overlay_only' }])
}
function sourceOf(rule: PosterModeRule): PosterModeRule['source'] {
  return rule.source || 'plex_label'
}
/** Why a rule can't match anything right now, or ''. */
function inactiveNote(rule: PosterModeRule): string {
  if (sourceOf(rule) === 'arr_tag' && !props.arrInstanceId) return `no ${props.arrLabel} linked`
  if (sourceOf(rule) === 'plex_label' && !props.hasPlex) return 'no Plex library in this group'
  return ''
}
</script>

<template>
  <div class="mode-rules">
    <span class="rules-title">Poster mode rules</span>
    <span class="rules-help">
      A title with the Plex label, or with the tag in the linked {{ arrLabel }}, gets that mode.
      "Leave alone" wins over "Overlay only"; a mode set by hand wins over both.
    </span>
    <div v-for="(rule, i) in rules" :key="i" class="rule-row">
      <select
        :value="sourceOf(rule)"
        class="rule-select"
        @change="update(i, { source: ($event.target as HTMLSelectElement).value as PosterModeRule['source'] })"
      >
        <option v-if="hasPlex || sourceOf(rule) === 'plex_label'" value="plex_label">Plex label</option>
        <option v-if="arrInstanceId || sourceOf(rule) === 'arr_tag'" value="arr_tag">{{ arrLabel }} tag</option>
      </select>
      <input
        :value="rule.value"
        type="text"
        class="rule-input"
        :placeholder="sourceOf(rule) === 'arr_tag' ? 'tag' : 'label text'"
        :list="sourceOf(rule) === 'arr_tag' ? tagListId : labelListId"
        @input="update(i, { value: ($event.target as HTMLInputElement).value })"
      />
      <select
        :value="rule.mode"
        class="rule-select"
        @change="update(i, { mode: ($event.target as HTMLSelectElement).value as PosterModeRule['mode'] })"
      >
        <option value="overlay_only">Overlay only</option>
        <option value="leave_alone">Leave alone</option>
      </select>
      <span v-if="inactiveNote(rule)" class="rule-inactive">{{ inactiveNote(rule) }}</span>
      <span v-else-if="counts[i] != null" class="rule-count">{{ counts[i] }} title{{ counts[i] === 1 ? '' : 's' }} matched</span>
      <button type="button" class="rule-remove" title="Remove rule" @click="remove(i)">✕</button>
    </div>
    <datalist :id="labelListId">
      <option v-for="l in availableLabels" :key="l" :value="l" />
    </datalist>
    <datalist :id="tagListId">
      <option v-for="t in knownTags" :key="t" :value="t" />
    </datalist>
    <button type="button" class="rule-add" @click="add">+ Add rule</button>
  </div>
</template>

<style scoped>
.mode-rules {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rules-title {
  font-weight: 500;
  font-size: 13px;
  color: var(--text-primary);
}

.rules-help {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.3;
}

.rule-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.rule-input,
.rule-select {
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  font-size: 13px;
}

.rule-input {
  flex: 1 1 140px;
  min-width: 0;
}

.rule-count {
  font-size: 12px;
  color: var(--accent);
}

.rule-inactive {
  font-size: 12px;
  color: #fbbf24;
}

.rule-remove {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.rule-remove:hover {
  color: #ff6b6b;
  border-color: rgba(255, 107, 107, 0.5);
}

.rule-add {
  align-self: flex-start;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(61, 214, 183, 0.1);
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
}
</style>
