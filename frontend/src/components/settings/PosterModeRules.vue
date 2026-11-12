<script setup lang="ts">
import { computed } from 'vue'
import type { PosterModeRule } from '@/stores/settings'
import { ruleMatchCounts } from '@/services/posterModes'

const props = defineProps<{
  groupId: string
  rules: PosterModeRule[]
  availableLabels: string[]
}>()

const emit = defineEmits<{
  (e: 'update:rules', rules: PosterModeRule[]): void
}>()

const listId = computed(() => `pm-labels-${props.groupId}`)
const counts = computed(() => ruleMatchCounts.value[props.groupId] || [])

function update(i: number, patch: Partial<PosterModeRule>) {
  emit('update:rules', props.rules.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
}
function remove(i: number) {
  emit('update:rules', props.rules.filter((_, idx) => idx !== i))
}
function add() {
  emit('update:rules', [...props.rules, { source: 'plex_label', value: '', mode: 'overlay_only' }])
}
</script>

<template>
  <div class="mode-rules">
    <span class="rules-title">Poster mode rules <span class="rules-tag">Plex labels</span></span>
    <span class="rules-help">
      A title whose Plex copy has the label gets that mode. "Leave alone" wins over "Overlay only"; a mode set by hand wins over both.
    </span>
    <div v-for="(rule, i) in rules" :key="i" class="rule-row">
      <span class="rule-if">Label</span>
      <input
        :value="rule.value"
        type="text"
        class="rule-input"
        placeholder="label text"
        :list="listId"
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
      <span v-if="counts[i] !== undefined" class="rule-count">{{ counts[i] }} title{{ counts[i] === 1 ? '' : 's' }} matched</span>
      <button type="button" class="rule-remove" title="Remove rule" @click="remove(i)">✕</button>
    </div>
    <datalist :id="listId">
      <option v-for="l in availableLabels" :key="l" :value="l" />
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

.rules-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 5px;
  background: rgba(229, 160, 13, 0.12);
  color: #e5a00d;
  margin-left: 4px;
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

.rule-if {
  font-size: 12px;
  color: var(--text-muted);
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
