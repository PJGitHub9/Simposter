<script setup lang="ts">
// Badge sets for one overlay config: groups of elements where only one is drawn
// (stored as element.group + element.weight; highest weight wins, see
// overlay_engine.select_elements). Also shows "hide" rules (element.suppress),
// which mostly come from Kometa imports.
import { computed, ref } from 'vue'
import { elementLabel, uniqueElementName } from '@/services/overlayLabels'

interface SetElement {
  name?: string
  type?: string
  text?: string
  metadata_field?: string
  group?: string
  weight?: number
  suppress?: string[]
}

/** embedded: shown as its own editor tab, always open, no header toggle. */
const props = defineProps<{ elements: SetElement[]; embedded?: boolean }>()

const open = ref(props.embedded || props.elements.some(e => e.group || e.suppress?.length))
const label = (el: SetElement) => elementLabel(el, props.elements.indexOf(el))

const setNames = computed(() => {
  const out: string[] = []
  for (const el of props.elements) if (el.group && !out.includes(el.group)) out.push(el.group)
  return out
})

/** Members of a set, first = wins (highest weight; ties keep list order). */
const members = (name: string): SetElement[] =>
  props.elements
    .map((el, i) => ({ el, i }))
    .filter(({ el }) => el.group === name)
    .sort((a, b) => (Number(b.el.weight) || 0) - (Number(a.el.weight) || 0) || a.i - b.i)
    .map(({ el }) => el)

const applyOrder = (order: SetElement[]) => order.forEach((el, i) => { el.weight = (order.length - i) * 10 })

const move = (name: string, el: SetElement, dir: -1 | 1) => {
  const order = members(name)
  const i = order.indexOf(el)
  const j = i + dir
  if (i < 0 || j < 0 || j >= order.length) return
  const a = order[i]!
  const b = order[j]!
  order[i] = b
  order[j] = a
  applyOrder(order)
}

const removeFrom = (name: string, el: SetElement) => {
  delete el.group
  delete el.weight
  applyOrder(members(name))
}

const available = computed(() => props.elements.filter(e => !e.group && e.type !== 'full_cover_image'))

const addTo = (name: string, indexText: string) => {
  const el = props.elements[Number(indexText)]
  if (!el) return
  el.group = name
  applyOrder([...members(name).filter(m => m !== el), el])
}

const deleteSet = (name: string) => {
  for (const el of props.elements) if (el.group === name) { delete el.group; delete el.weight }
}

const renaming = ref<string | null>(null)
const renameText = ref('')
const startRename = (name: string) => { renaming.value = name; renameText.value = name }
const commitRename = () => {
  const from = renaming.value
  const to = renameText.value.trim()
  renaming.value = null
  if (!from || !to || to === from) return
  for (const el of props.elements) if (el.group === from) el.group = to
}

const newName = ref('')
const adding = ref(false)
const createSet = () => {
  const base = newName.value.trim() || 'Badge set'
  let name = base
  let n = 2
  while (setNames.value.includes(name)) name = `${base} ${n++}`
  adding.value = false
  newName.value = ''
  // A set exists once it has a member; start it with the first free element.
  const first = available.value[0]
  if (first) { first.group = name; first.weight = 10 }
  else pendingEmpty.value = name
}
const pendingEmpty = ref<string | null>(null)

// ---- hide rules ----
const hiders = computed(() => props.elements.filter(e => e.suppress?.length))
const nameExists = (n: string) => props.elements.some(e => e.name === n)
const unhide = (el: SetElement, n: string) => {
  const next = (el.suppress || []).filter(x => x !== n)
  if (next.length) el.suppress = next
  else delete el.suppress
}
const addHide = (el: SetElement, indexText: string) => {
  const target = props.elements[Number(indexText)]
  if (!target || target === el) return
  if (!target.name) target.name = uniqueElementName(props.elements, label(target).replace(/"/g, ''))
  const cur = el.suppress || []
  if (!cur.includes(target.name)) el.suppress = [...cur, target.name]
}
</script>

<template>
  <div class="sets" :class="{ embedded }">
    <button v-if="!embedded" type="button" class="sets-head" @click="open = !open">
      <span class="chev" :class="{ open }">›</span>
      <span class="sets-title">Badge sets</span>
      <span class="sets-sub">{{ setNames.length ? `${setNames.length} set${setNames.length === 1 ? '' : 's'}` : 'Only show one badge from a group' }}</span>
    </button>

    <div v-if="open" class="sets-body">
      <p v-if="embedded && elements.length < 2" class="empty">
        Add at least two layers first. A badge set is for layers that shouldn't appear together, like 4K, 1080p and 720p badges.
      </p>
      <p class="hint">
        Put badges that shouldn't appear together in one set, e.g. 4K, 1080p and 720p. On each poster, the first one in the set
        whose "Show when" matches is drawn and the rest are skipped.
      </p>

      <div v-for="name in setNames" :key="name" class="set">
        <div class="set-head">
          <input v-if="renaming === name" v-model="renameText" class="rename" @keyup.enter="commitRename" @blur="commitRename" />
          <button v-else type="button" class="set-name" title="Rename" @click="startRename(name)">{{ name }}</button>
          <button type="button" class="link danger" @click="deleteSet(name)">Remove set</button>
        </div>
        <ol class="rank">
          <li v-for="(m, i) in members(name)" :key="i">
            <span class="rank-n">{{ i + 1 }}</span>
            <span class="rank-label">{{ label(m) }}</span>
            <button type="button" class="ibtn" :disabled="i === 0" title="Move up (wins over the ones below)" @click="move(name, m, -1)">↑</button>
            <button type="button" class="ibtn" :disabled="i === members(name).length - 1" title="Move down" @click="move(name, m, 1)">↓</button>
            <button type="button" class="ibtn" title="Take out of this set" @click="removeFrom(name, m)">✕</button>
          </li>
        </ol>
        <select v-if="available.length" class="add-sel" value="" @change="addTo(name, ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''">
          <option value="" disabled>+ Add a layer to this set…</option>
          <option v-for="el in available" :key="elements.indexOf(el)" :value="elements.indexOf(el)">{{ label(el) }}</option>
        </select>
      </div>

      <div v-if="adding" class="new-set">
        <input v-model="newName" placeholder="Set name, e.g. Resolution" @keyup.enter="createSet" />
        <button type="button" class="btn-small" @click="createSet">Create</button>
        <button type="button" class="link" @click="adding = false">Cancel</button>
      </div>
      <button v-else type="button" class="btn-small" :disabled="!available.length" @click="adding = true">+ New badge set</button>
      <p v-if="pendingEmpty" class="hint">Add a layer to the overlay first, then put it in a set.</p>

      <template v-if="hiders.length">
        <div class="sub">Hide rules <span class="hint">(from imported Kometa files)</span></div>
        <div v-for="(el, i) in hiders" :key="i" class="hide-row">
          <span class="hide-lead">When <strong>{{ label(el) }}</strong> shows, hide:</span>
          <div class="chips">
            <button
              v-for="n in el.suppress"
              :key="n"
              type="button"
              class="chip"
              :class="{ stale: !nameExists(n) }"
              :title="nameExists(n) ? 'Click to stop hiding it' : 'No layer has this name. Click to remove.'"
              @click="unhide(el, n)"
            >{{ n }} ✕</button>
            <select class="add-sel small" value="" @change="addHide(el, ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''">
              <option value="" disabled>+ hide another…</option>
              <option v-for="o in elements.filter(x => x !== el)" :key="elements.indexOf(o)" :value="elements.indexOf(o)">{{ label(o) }}</option>
            </select>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.sets { border: 1px solid var(--border, #2a2f3e); border-radius: 8px; background: rgba(255, 255, 255, 0.02); margin-bottom: 0.6rem; }
.sets-head { display: flex; align-items: center; gap: 0.45rem; width: 100%; padding: 0.5rem 0.65rem; background: none; border: none; color: var(--text-primary, #fff); cursor: pointer; text-align: left; }
.chev { display: inline-block; transition: transform 0.15s; color: var(--text-secondary, #888); }
.chev.open { transform: rotate(90deg); }
.sets-title { font-weight: 600; font-size: 0.82rem; }
.sets-sub { margin-left: auto; font-size: 0.72rem; color: var(--text-secondary, #888); }
.sets.embedded { border: none; background: none; margin: 0; }
.sets.embedded .sets-body { padding: 0; }
.sets.embedded .hint { font-size: 0.78rem; }
.empty { margin: 0; padding: 1rem; text-align: center; font-size: 0.85rem; color: var(--text-secondary, #aaa); }
.sets-body { padding: 0 0.65rem 0.65rem; display: flex; flex-direction: column; gap: 0.55rem; }
.hint { margin: 0; font-size: 0.7rem; color: var(--text-secondary, #888); line-height: 1.4; }
.set { border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 6px; padding: 0.45rem; display: flex; flex-direction: column; gap: 0.35rem; }
.set-head { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.set-name { background: none; border: none; padding: 0; color: var(--text-primary, #fff); font-weight: 600; font-size: 0.8rem; cursor: text; }
.rename, .new-set input { flex: 1; min-width: 0; padding: 0.3rem 0.4rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.78rem; }
.rank { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.15rem; }
.rank li { display: flex; align-items: center; gap: 0.35rem; padding: 0.2rem 0.3rem; border-radius: 5px; font-size: 0.76rem; color: var(--text-primary, #ddd); background: rgba(255, 255, 255, 0.02); }
.rank-n { width: 1.2rem; text-align: center; font-weight: 700; color: var(--accent, #3dd6b7); }
.rank-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ibtn { width: 22px; height: 22px; padding: 0; background: transparent; border: 1px solid transparent; border-radius: 4px; color: var(--text-secondary, #888); cursor: pointer; }
.ibtn:hover:not(:disabled) { border-color: var(--border, #3a4050); color: var(--text-primary, #fff); }
.ibtn:disabled { opacity: 0.3; cursor: default; }
.add-sel { align-self: flex-start; padding: 0.28rem 0.4rem; background: var(--surface-soft, #141824); color-scheme: dark; border: 1px dashed var(--border, #2a2f3e); border-radius: 5px; color: var(--text-secondary, #aaa); font-size: 0.74rem; }
:root[data-theme='light'] .add-sel { color-scheme: light; }
.add-sel option { background: var(--surface, #1b1f2a); color: var(--text-primary, #fff); }
.add-sel.small { font-size: 0.7rem; }
.new-set { display: flex; gap: 0.35rem; align-items: center; }
.btn-small { align-self: flex-start; padding: 0.28rem 0.65rem; background: rgba(61, 214, 183, 0.08); border: 1px solid rgba(61, 214, 183, 0.25); border-radius: 5px; color: var(--accent, #3dd6b7); cursor: pointer; font-size: 0.74rem; }
.btn-small:disabled { opacity: 0.4; cursor: default; }
.link { background: none; border: none; color: var(--text-secondary, #888); cursor: pointer; font-size: 0.72rem; }
.link.danger:hover { color: #f87171; }
.sub { font-size: 0.78rem; font-weight: 600; color: var(--text-primary, #fff); margin-top: 0.2rem; }
.sub .hint { font-weight: 400; }
.hide-row { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.74rem; color: var(--text-secondary, #aaa); }
.chips { display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
.chip { padding: 0.18rem 0.5rem; border-radius: 12px; border: 1px solid rgba(61, 214, 183, 0.4); background: rgba(61, 214, 183, 0.1); color: var(--accent, #3dd6b7); font-size: 0.72rem; cursor: pointer; }
.chip.stale { border-style: dashed; border-color: #f87171; background: transparent; color: #f87171; }
</style>
