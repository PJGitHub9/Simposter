<script setup lang="ts">
// "Show when" for an overlay element: conditions that must all match. Same rules
// as backend/overlay_engine.py (see services/overlayEngine.ts). Which element wins
// when several overlap lives in the config-level Badge sets panel.
import { normalizeListUrl, type OverlayCondition, type OverlayRuleFields } from '@/services/overlayEngine'
import { computed, onMounted, ref } from 'vue'
import { FIELDS, FIELD_GROUPS, fieldDef, opsFor, opDef, needsMdblist } from '@/services/overlayFields'
import { useSettingsStore } from '@/stores/settings'
import { listDisplayName, providerLabel, useListSources } from '@/composables/useListSources'

/** subject: what the conditions decide about, for the wording (a layer, or a whole overlay). */
const props = defineProps<{ element: OverlayRuleFields; subject?: 'layer' | 'overlay' }>()
const what = computed(() => (props.subject === 'overlay' ? 'this overlay' : 'this layer'))

// Ratings and MDBList lists are only offered once an MDBList API key is set
// (a condition that already uses one keeps showing its field).
const settings = useSettingsStore()
const hasMdblistKey = computed(() => !!settings.mdblist.value.apiKey)
// "On a list" works with any list service set up in Settings → General.
const hasListSource = computed(() => hasMdblistKey.value || !!settings.wetrakr.value.clientId
  || !!settings.simkl.value.clientId || !!(settings.floppy.value.url && settings.floppy.value.token))
const fieldsFor = (c: OverlayCondition) => {
  const current = fieldDef(String(c.field || ''))?.value
  const offered = (f: (typeof FIELDS)[number]) => f.value === current
    || (f.kind === 'list' ? hasListSource.value : (hasMdblistKey.value || !needsMdblist(f)))
  return FIELD_GROUPS
    .map(g => ({ group: g, fields: FIELDS.filter(f => f.group === g && offered(f)) }))
    .filter(g => g.fields.length)
}

// ---- List picker for "On a list" conditions
const listSources = useListSources()
onMounted(() => { if (props.element.conditions?.some(c => isListField(c))) listSources.load() })
const isListField = (c: OverlayCondition) => fieldDef(String(c.field || ''))?.kind === 'list'
const pasteText = ref<Record<number, string>>({})
const pasteMsg = ref<Record<number, { ok: boolean; text: string } | null>>({})
const pasteBusy = ref<Record<number, boolean>>({})
const showPaste = ref<Record<number, boolean>>({})

const listKeys = (c: OverlayCondition): string[] =>
  valueList(c).map(v => normalizeListUrl(v) || v)

/** Put a list key into the condition: replaces it for "is on", adds it for "is on any of". */
const useList = (c: OverlayCondition, key: string) => {
  if (!key) return
  if (isMulti(c)) {
    const cur = listKeys(c)
    if (!cur.includes(key)) c.value = [...cur, key]
  } else {
    c.value = key
  }
}
const removeList = (c: OverlayCondition, key: string) => {
  c.value = listKeys(c).filter(k => k !== key)
}
const pickList = (i: number, c: OverlayCondition, value: string) => {
  if (value === '__paste__') { showPaste.value = { ...showPaste.value, [i]: true }; return }
  useList(c, value)
}
const addPasted = async (i: number, c: OverlayCondition) => {
  const text = (pasteText.value[i] || '').trim()
  if (!text) return
  pasteBusy.value = { ...pasteBusy.value, [i]: true }
  const res = await listSources.resolve(text)
  pasteBusy.value = { ...pasteBusy.value, [i]: false }
  if (!res.key) {
    pasteMsg.value = { ...pasteMsg.value, [i]: { ok: false, text: res.error || 'Not a list link Simposter recognizes' } }
    return
  }
  useList(c, res.key)
  pasteText.value = { ...pasteText.value, [i]: '' }
  showPaste.value = { ...showPaste.value, [i]: false }
  pasteMsg.value = {
    ...pasteMsg.value,
    [i]: res.error ? { ok: false, text: `Added, but it can't be read yet: ${res.error}` } : { ok: true, text: `Added ${listDisplayName(res.key)}` },
  }
}

const isMulti = (c: OverlayCondition) => !!opDef(String(c.op))?.multi
const isNoValue = (c: OverlayCondition) => !!opDef(String(c.op))?.noValue
const isUnsupported = (c: OverlayCondition) => String(c.field || '').startsWith('_')

const valueList = (c: OverlayCondition): string[] =>
  (Array.isArray(c.value) ? c.value : (c.value === undefined || c.value === null || c.value === '' ? [] : String(c.value).split(',')))
    .map(v => String(v).trim()).filter(Boolean)

const valueText = (c: OverlayCondition): string =>
  Array.isArray(c.value) ? c.value.join(', ') : (c.value ?? '').toString()

const setValueText = (c: OverlayCondition, text: string) => {
  const kind = fieldDef(String(c.field))?.kind
  if (isMulti(c)) {
    c.value = text.split(',').map(s => s.trim()).filter(Boolean)
  } else if ((kind === 'number' || ['gt', 'gte', 'lt', 'lte'].includes(String(c.op))) && text.trim() !== '' && Number.isFinite(Number(text))) {
    c.value = Number(text)
  } else {
    c.value = text
  }
}

const toggleChoice = (c: OverlayCondition, v: string) => {
  const cur = valueList(c)
  c.value = cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v]
}

const changeField = (c: OverlayCondition, field: string) => {
  c.field = field
  const def = fieldDef(field)
  if (def?.kind === 'list') listSources.load()
  const first = opsFor(field)[0]
  c.op = first ? first.value : 'eq'
  c.value = def?.kind === 'choice' && def.options?.[0] ? def.options[0].value : ''
}

const changeOp = (c: OverlayCondition, op: string) => {
  const wasMulti = isMulti(c)
  c.op = op
  if (opDef(op)?.noValue) { delete c.value; return }
  const nowMulti = isMulti(c)
  if (nowMulti && !wasMulti) c.value = valueList(c)
  else if (!nowMulti && wasMulti) c.value = valueList(c)[0] ?? ''
  else if (c.value === undefined) c.value = ''
}

const addCondition = () => {
  if (!props.element.conditions) props.element.conditions = []
  props.element.conditions.push({ field: 'resolution', op: 'eq', value: '4k' })
}

const removeCondition = (i: number) => {
  props.element.conditions?.splice(i, 1)
  if (props.element.conditions && props.element.conditions.length === 0) delete props.element.conditions
}

</script>

<template>
  <div class="rules">
    <div class="rules-body">
      <p v-if="!element.conditions?.length" class="hint">No conditions, so {{ what }} shows on every poster. Add one to show it only on some, e.g. only on 4K movies.</p>

      <div v-for="(c, i) in element.conditions || []" :key="i" class="cond" :class="{ bad: isUnsupported(c) }">
        <div class="cond-row">
          <span class="cond-lead">{{ i === 0 ? 'When' : 'and' }}</span>

          <select class="cond-field" :value="fieldDef(String(c.field))?.value ?? c.field" @change="changeField(c, ($event.target as HTMLSelectElement).value)">
            <option v-if="!fieldDef(String(c.field))" :value="c.field" :disabled="!c.field">{{ isUnsupported(c) ? 'Unsupported (imported)' : (c.field || 'Choose a field…') }}</option>
            <optgroup v-for="g in fieldsFor(c)" :key="g.group" :label="g.group">
              <option v-for="f in g.fields" :key="f.value" :value="f.value">{{ f.label }}</option>
            </optgroup>
          </select>

          <select v-if="!isUnsupported(c)" class="cond-op" :value="c.op" @change="changeOp(c, ($event.target as HTMLSelectElement).value)">
            <option v-for="o in opsFor(String(c.field), String(c.op))" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>

          <button type="button" class="btn-x" title="Remove condition" @click="removeCondition(i)">✕</button>
        </div>

        <!-- A list: pick one of your lists, or paste any list link -->
        <div v-if="!isUnsupported(c) && !isNoValue(c) && isListField(c)" class="cond-value-row list-pick">
          <div v-if="isMulti(c) && listKeys(c).length" class="chips">
            <span v-for="k in listKeys(c)" :key="k" class="chip on">
              {{ listDisplayName(k) }}
              <button type="button" class="chip-x" title="Remove" @click="removeList(c, k)">✕</button>
            </span>
          </div>
          <select class="cond-value" :value="isMulti(c) ? '' : (listKeys(c)[0] || '')" @change="pickList(i, c, ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = isMulti(c) ? '' : (listKeys(c)[0] || '')">
            <option value="" disabled>{{ isMulti(c) ? 'Add a list…' : 'Choose a list…' }}</option>
            <option v-if="!isMulti(c) && listKeys(c)[0] && !listSources.groups.value.some(g => g.items.some(o => o.key === listKeys(c)[0]))" :value="listKeys(c)[0]">
              {{ listDisplayName(listKeys(c)[0]) }}
            </option>
            <optgroup v-for="g in listSources.groups.value" :key="g.label" :label="g.label">
              <option v-for="o in g.items" :key="o.key" :value="o.key">{{ o.title || listDisplayName(o.key) }}{{ o.items != null ? ` (${o.items})` : '' }}</option>
            </optgroup>
            <option value="__paste__">Paste a list link…</option>
          </select>
          <div v-if="showPaste[i]" class="paste-row">
            <input
              v-model="pasteText[i]"
              class="cond-value"
              type="text"
              placeholder="https://wetrakr.com/lists/… , https://simkl.com/… , https://mdblist.com/lists/… or a Floppy list link"
              @keydown.enter.prevent="addPasted(i, c)"
            />
            <button type="button" class="btn-small" :disabled="pasteBusy[i]" @click="addPasted(i, c)">{{ pasteBusy[i] ? 'Checking…' : 'Add' }}</button>
          </div>
          <p v-if="pasteMsg[i]" class="cond-note inline" :class="{ warn: !pasteMsg[i]?.ok }">{{ pasteMsg[i]?.text }}</p>
          <p v-if="listSources.loaded.value && !listSources.groups.value.length" class="cond-note inline">
            No lists found yet. Connect WeTrakr, SIMKL or Floppy in Settings → General, or paste a list link.
          </p>
          <p v-for="(msg, svc) in listSources.errors.value" :key="svc" class="cond-note inline warn">{{ providerLabel(String(svc)) }}: {{ msg }}</p>
        </div>

        <div v-else-if="!isUnsupported(c) && !isNoValue(c)" class="cond-value-row">
          <!-- Known choices, several allowed -->
          <div v-if="fieldDef(String(c.field))?.kind === 'choice' && isMulti(c)" class="chips">
            <button
              v-for="o in fieldDef(String(c.field))?.options || []"
              :key="o.value"
              type="button"
              class="chip"
              :class="{ on: valueList(c).includes(o.value) }"
              @click="toggleChoice(c, o.value)"
            >{{ o.label }}</button>
          </div>
          <!-- Known choices, one -->
          <select
            v-else-if="fieldDef(String(c.field))?.kind === 'choice'"
            class="cond-value"
            :value="String(c.value ?? '')"
            @change="setValueText(c, ($event.target as HTMLSelectElement).value)"
          >
            <option v-if="c.value && !fieldDef(String(c.field))?.options?.some(o => o.value === String(c.value))" :value="String(c.value)">{{ c.value }}</option>
            <option v-for="o in fieldDef(String(c.field))?.options || []" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
          <!-- Free value -->
          <input
            v-else
            class="cond-value"
            :type="fieldDef(String(c.field))?.kind === 'number' && !isMulti(c) ? 'number' : 'text'"
            step="any"
            :value="valueText(c)"
            :placeholder="isMulti(c) ? 'several, separated by commas' : (fieldDef(String(c.field))?.placeholder || 'value')"
            @change="setValueText(c, ($event.target as HTMLInputElement).value)"
          />
        </div>

        <p v-if="isUnsupported(c)" class="cond-note warn">
          An imported Kometa rule Simposter can't check, so {{ what }} never shows. Remove this condition to show it.
        </p>
        <p v-else-if="String(c.op).includes('regex')" class="cond-note">
          A regular expression. Add <code>(?i)</code> at the start to ignore upper/lower case.
        </p>
        <p v-else-if="fieldDef(String(c.field))?.note || fieldDef(String(c.field))?.hint" class="cond-note">
          {{ fieldDef(String(c.field))?.note || fieldDef(String(c.field))?.hint }}
        </p>
      </div>

      <div class="rules-actions">
        <button type="button" class="btn-small" @click="addCondition">+ Add condition</button>
        <p v-if="!hasMdblistKey" class="hint">Ratings show up here once you add an MDBList API key in Settings → General{{ hasListSource ? '' : ', and lists once you set up MDBList, WeTrakr, SIMKL or Floppy there' }}.</p>
        <span v-if="(element.conditions?.length || 0) > 1" class="hint">All conditions must match.</span>
      </div>

    </div>
  </div>
</template>

<style scoped>
.rules { grid-column: 1 / -1; }
.rules-body { display: flex; flex-direction: column; gap: 0.5rem; }

.cond { display: flex; flex-direction: column; gap: 0.3rem; padding: 0.45rem; border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 6px; background: rgba(255, 255, 255, 0.015); }
.cond.bad { border-color: rgba(248, 113, 113, 0.35); }
.cond-row { display: flex; align-items: center; gap: 0.35rem; }
.cond-lead { font-size: 0.72rem; color: var(--text-secondary, #888); width: 2.4rem; flex-shrink: 0; }
.cond-field { flex: 1.3; min-width: 0; }
.cond-op { flex: 1; min-width: 0; }
.cond-value-row { padding-left: 2.75rem; }
.cond-value { width: 100%; box-sizing: border-box; }
.cond select, .cond input { padding: 0.32rem 0.4rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.78rem; }
.cond select { background-color: var(--surface-soft, #141824); color-scheme: dark; }
:root[data-theme='light'] .cond select { color-scheme: light; }
.cond select option { background: var(--surface, #1b1f2a); color: var(--text-primary, #fff); font-weight: 400; }
.cond select optgroup { background: var(--surface, #1b1f2a); color: var(--text-secondary, #8b95a7); font-style: normal; font-weight: 700; }
.cond select:focus, .cond input:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.cond-note { margin: 0; padding-left: 2.75rem; font-size: 0.68rem; color: var(--text-secondary, #888); }
.cond-note.warn { color: #f87171; }
.cond-note code { font-size: 0.68rem; background: rgba(255, 255, 255, 0.06); padding: 0 0.25rem; border-radius: 3px; }

.chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
.chip { padding: 0.2rem 0.55rem; border-radius: 12px; border: 1px solid var(--border, #2a2f3e); background: transparent; color: var(--text-secondary, #aaa); font-size: 0.72rem; cursor: pointer; }
.chip.on { background: rgba(61, 214, 183, 0.15); border-color: rgba(61, 214, 183, 0.5); color: var(--accent, #3dd6b7); }

.rules-actions { display: flex; align-items: center; gap: 0.6rem; }
.btn-small { padding: 0.25rem 0.6rem; background: rgba(61, 214, 183, 0.08); border: 1px solid rgba(61, 214, 183, 0.25); border-radius: 5px; color: var(--accent, #3dd6b7); cursor: pointer; font-size: 0.72rem; }
.btn-x { flex-shrink: 0; width: 24px; height: 24px; padding: 0; background: transparent; border: 1px solid transparent; border-radius: 4px; color: var(--text-secondary, #888); cursor: pointer; }
.btn-x:hover { border-color: #f87171; color: #f87171; }
.hint { margin: 0; font-size: 0.7rem; color: var(--text-secondary, #888); }
.list-pick { display: flex; flex-direction: column; gap: 0.35rem; }
.paste-row { display: flex; gap: 0.35rem; }
.paste-row .cond-value { flex: 1; }
.cond-note.inline { padding-left: 0; }
.chip-x { margin-left: 0.25rem; padding: 0; background: none; border: none; color: inherit; cursor: pointer; font-size: 0.65rem; }

</style>
