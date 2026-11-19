<script setup lang="ts">
// A preset's overlays in draw order. Shown top-first (top of the list is drawn
// on top, like the Overlay Manager's layers); stored bottom-to-top in
// overlay_config_ids, with overlay_config_ids_below the subset drawn under the
// logo and text.
import { computed, ref } from 'vue'
import type { OverlayLists } from '@/services/presetOverlayLists'

const props = defineProps<{
  modelValue: OverlayLists
  configs: { id: string; name: string }[]
  inherited?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: OverlayLists]; override: [] }>()

const nameById = computed(() => new Map(props.configs.map(c => [c.id, c.name])))
const rows = computed(() => [...props.modelValue.ids].reverse())
const addable = computed(() => props.configs.filter(c => !props.modelValue.ids.includes(c.id)))
const addChoice = ref('')

function emitLists(ids: string[], below: string[]) {
  // keep `below` a subset of `ids`, in the same relative order
  emit('update:modelValue', { ids, below: ids.filter(id => below.includes(id)) })
}

// `step` +1 moves toward the top (later in the stored list), -1 toward the bottom.
function move(id: string, step: 1 | -1) {
  const ids = [...props.modelValue.ids]
  const i = ids.indexOf(id)
  const j = i + step
  if (i < 0 || j < 0 || j >= ids.length) return
  ;[ids[i], ids[j]] = [ids[j]!, ids[i]!]
  emitLists(ids, props.modelValue.below)
}

function setBelow(id: string, below: boolean) {
  const set = new Set(props.modelValue.below)
  if (below) set.add(id)
  else set.delete(id)
  emitLists([...props.modelValue.ids], [...set])
}

function remove(id: string) {
  emitLists(props.modelValue.ids.filter(x => x !== id), props.modelValue.below.filter(x => x !== id))
}

function add() {
  if (!addChoice.value) return
  emitLists([...props.modelValue.ids, addChoice.value], props.modelValue.below)
  addChoice.value = ''
}
</script>

<template>
  <div class="pol">
    <div v-if="inherited" class="pol-inherited">
      <span>Same as series</span>
      <button type="button" class="pol-btn" @click="emit('override')">Use different overlays for seasons</button>
    </div>
    <p v-if="!rows.length" class="pol-empty">No overlays on this preset.</p>
    <ol v-else class="pol-list">
      <li v-for="(id, i) in rows" :key="id" class="pol-row" :class="{ missing: !nameById.has(id) }">
        <span class="pol-pos">{{ i + 1 }}</span>
        <span class="pol-name">{{ nameById.get(id) || 'Missing overlay' }}</span>
        <template v-if="!inherited">
          <template v-if="nameById.has(id)">
            <select class="pol-where" :value="modelValue.below.includes(id) ? 'below' : 'above'"
              @change="setBelow(id, ($event.target as HTMLSelectElement).value === 'below')">
              <option value="above">Above logo &amp; text</option>
              <option value="below">Below logo &amp; text</option>
            </select>
            <button type="button" class="pol-icon" title="Move up (drawn later, on top)" :disabled="i === 0" @click="move(id, 1)">↑</button>
            <button type="button" class="pol-icon" title="Move down" :disabled="i === rows.length - 1" @click="move(id, -1)">↓</button>
          </template>
          <button type="button" class="pol-icon danger" title="Remove from this preset" @click="remove(id)">×</button>
        </template>
        <span v-else class="pol-where-static">{{ modelValue.below.includes(id) ? 'Below logo & text' : 'Above logo & text' }}</span>
      </li>
    </ol>
    <div v-if="!inherited && addable.length" class="pol-add">
      <select v-model="addChoice" class="pol-where">
        <option value="">Add overlay…</option>
        <option v-for="c in addable" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
      <button type="button" class="pol-btn" :disabled="!addChoice" @click="add">Add on top</button>
    </div>
    <p class="pol-hint">Top of the list is drawn on top. Badge sets and Kometa queues pick by weight, whatever the order.</p>
  </div>
</template>

<style scoped>
.pol { display: flex; flex-direction: column; gap: 8px; }
.pol-inherited { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-size: 0.8rem; color: var(--text-secondary, #9aa); }
.pol-empty, .pol-hint { margin: 0; font-size: 0.78rem; color: var(--text-secondary, #9aa); }
.pol-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.pol-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 6px 8px; border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 8px; background: rgba(255, 255, 255, 0.02); }
.pol-row.missing .pol-name { color: #ffa502; font-style: italic; }
.pol-pos { min-width: 18px; font-size: 0.72rem; color: var(--text-secondary, #9aa); }
.pol-name { flex: 1 1 140px; min-width: 0; font-size: 0.85rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pol-where { padding: 4px 6px; font-size: 0.78rem; border-radius: 6px; border: 1px solid var(--border, #2a2f3e); background: var(--input-bg, #1b2030); color: var(--text-primary, #fff); }
.pol-where-static { font-size: 0.75rem; color: var(--text-secondary, #9aa); }
.pol-icon { width: 28px; height: 28px; border-radius: 6px; border: 1px solid var(--border, #2a2f3e); background: rgba(255, 255, 255, 0.04); color: var(--text-primary, #fff); cursor: pointer; }
.pol-icon:disabled { opacity: 0.35; cursor: not-allowed; }
.pol-icon.danger:hover { border-color: #ff6b6b; color: #ff6b6b; }
.pol-add { display: flex; gap: 6px; flex-wrap: wrap; }
.pol-btn { padding: 5px 10px; font-size: 0.78rem; border-radius: 6px; border: 1px solid var(--border, #2a2f3e); background: rgba(255, 255, 255, 0.04); color: var(--text-primary, #fff); cursor: pointer; }
.pol-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.pol-btn:hover:not(:disabled), .pol-icon:hover:not(:disabled) { border-color: var(--accent, #3dd6b7); }
</style>
