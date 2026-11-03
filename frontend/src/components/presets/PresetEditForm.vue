<script setup lang="ts">
// Type-in editing of one preset (Template Manager). No live render: values are
// typed and saved. Series values save through /api/presets/save (a merge, so
// keys this form doesn't show are kept; season config untouched). Season
// values save through /api/presets/save-season-options with the full resolved
// season object, which the backend reduces to a diff. Seasons inherit any
// value they haven't overridden, overlays included.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useNotification } from '@/composables/useNotification'
import { FIELD_GROUPS, changedFieldPayload, fieldsFor, fromDisplay, isFieldVisible, toDisplay, type PresetField } from '@/services/presetFields'
import { presetOverlayLists, type OverlayLists, type PresetOverlayLists } from '@/services/presetOverlayLists'
import PresetOverlayList from './PresetOverlayList.vue'

type PresetLike = { id: string; name?: string; options: Record<string, any>; season_options?: Record<string, any> | null }

// allPresets: every template's presets; this template's are offered as fallback presets.
const props = defineProps<{
  templateId: string
  preset: PresetLike
  allPresets?: Record<string, { presets: { id: string; name?: string }[] }>
}>()
// `saved` carries the overlay lists before and after, so the page can offer a refresh.
const emit = defineEmits<{ saved: [lists: { before: PresetOverlayLists; after: PresetOverlayLists }]; 'dirty-change': [dirty: boolean] }>()

const apiBase = getApiBase()
const { success, error: notifyError } = useNotification()

const fields = computed(() => fieldsFor(props.templateId))
const hasSeason = computed(() => props.templateId !== 'kometa')
const hasOverlays = computed(() => props.templateId !== 'kometa')
const view = ref<'series' | 'season'>('series')
const group = ref<(typeof FIELD_GROUPS)[number]['id'] | 'overlays'>('image')
const saving = ref(false)

const seriesValues = ref<Record<string, unknown>>({})
const loadedSeries = ref<Record<string, unknown>>({}) // as loaded, to send only what changed
const seasonEdits = ref<Record<string, unknown>>({})
const seriesLists = ref<OverlayLists>({ ids: [], below: [] })
const seasonLists = ref<OverlayLists>({ ids: [], below: [] })
const seasonOverride = ref(false)
const baseline = ref('')

const seasonDiff = computed<Record<string, any>>(() => props.preset.season_options || {})

function load() {
  const o = props.preset.options || {}
  const values: Record<string, unknown> = {}
  for (const f of fields.value) values[f.key] = toDisplay(f, o[f.key])
  seriesValues.value = values
  loadedSeries.value = { ...values }
  seasonEdits.value = {}
  const lists = presetOverlayLists(o, seasonDiff.value)
  seriesLists.value = lists.series
  seasonLists.value = lists.season
  seasonOverride.value = Array.isArray(seasonDiff.value.overlay_config_ids)
  baseline.value = snapshot()
}

// A season value: an edit made here, else the stored season override, else the series value.
function seasonValue(f: PresetField): unknown {
  if (f.key in seasonEdits.value) return seasonEdits.value[f.key]
  if (f.key in seasonDiff.value) return toDisplay(f, seasonDiff.value[f.key])
  return seriesValues.value[f.key]
}

function valueOf(f: PresetField): unknown {
  return view.value === 'season' ? seasonValue(f) : seriesValues.value[f.key]
}

function setValue(f: PresetField, v: unknown) {
  if (view.value === 'season') seasonEdits.value = { ...seasonEdits.value, [f.key]: v }
  else seriesValues.value = { ...seriesValues.value, [f.key]: v }
}

function differsFromSeries(f: PresetField): boolean {
  return view.value === 'season' && String(seasonValue(f)) !== String(seriesValues.value[f.key])
}

function snapshot(): string {
  return JSON.stringify([seriesValues.value, seasonEdits.value, seriesLists.value, seasonOverride.value ? seasonLists.value : null])
}
const dirty = computed(() => baseline.value !== '' && snapshot() !== baseline.value)
watch(dirty, d => emit('dirty-change', d))

const fieldByKey = computed(() => new Map(fields.value.map(f => [f.key, f])))
const shownValueOf = (key: string): unknown => {
  const f = fieldByKey.value.get(key)
  return f ? valueOf(f) : undefined
}
const fieldInView = (f: PresetField) => !(f.seriesOnly && view.value === 'season')

// Tabs that have something to show for this template and view (Fallback is series-only).
const availableGroups = computed(() =>
  FIELD_GROUPS.filter(g => fields.value.some(f => f.group === g.id && fieldInView(f))),
)
watch(availableGroups, gs => {
  if (group.value !== 'overlays' && !gs.some(g => g.id === group.value)) group.value = 'image'
})

// The current tab's visible fields, under their sub-headings. Fields whose
// setting is off (e.g. shadow details while the shadow is off) are hidden but kept.
const sections = computed(() => {
  const out: { title: string; fields: PresetField[] }[] = []
  for (const f of fields.value) {
    if (f.group !== group.value || !fieldInView(f) || !isFieldVisible(f, shownValueOf)) continue
    const title = f.section || ''
    let sec = out.find(s => s.title === title)
    if (!sec) out.push((sec = { title, fields: [] }))
    sec.fields.push(f)
  }
  return out
})

// A fallback preset is always one of this template's own presets (other than this one).
const fallbackPresetChoices = computed(() =>
  (props.allPresets?.[props.templateId]?.presets || []).filter(p => p.id !== props.preset.id))

// Overlay configs and fonts for the dropdowns (fetched once per page load).
const overlayConfigs = ref<{ id: string; name: string }[]>([])
const fonts = ref<string[]>([])
onMounted(async () => {
  load()
  try {
    const [oc, fo] = await Promise.all([
      hasOverlays.value ? fetch(`${apiBase}/api/overlay-configs`).then(r => r.json()) : Promise.resolve({ configs: [] }),
      fetch(`${apiBase}/api/fonts`).then(r => r.json()),
    ])
    overlayConfigs.value = (oc.configs || []).map((c: any) => ({ id: c.id, name: c.name }))
    fonts.value = fo.fonts || []
  } catch {
    // dropdowns stay empty; typing still works
  }
})
// A reload (e.g. after another card saved) must not wipe edits made here.
watch(() => props.preset, () => { if (!dirty.value) load() })
onBeforeUnmount(() => { if (dirty.value) emit('dirty-change', false) })

const shownLists = computed<OverlayLists>(() =>
  view.value === 'season' && !seasonOverride.value ? seriesLists.value : view.value === 'season' ? seasonLists.value : seriesLists.value,
)
function setLists(v: OverlayLists) {
  if (view.value === 'season') seasonLists.value = v
  else seriesLists.value = v
}
function overrideSeason() {
  seasonOverride.value = true
  seasonLists.value = { ids: [...seriesLists.value.ids], below: [...seriesLists.value.below] }
}

function fieldPayload(values: Record<string, unknown>, keys: Iterable<string>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const key of keys) {
    const f = fields.value.find(x => x.key === key)
    if (!f) continue
    const v = fromDisplay(f, values[key])
    if (v !== null) out[key] = v
  }
  return out
}

async function post(url: string, body: unknown) {
  const res = await fetch(`${apiBase}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

async function save() {
  if (!dirty.value || saving.value) return
  saving.value = true
  const before = presetOverlayLists(props.preset.options || {}, seasonDiff.value)
  try {
    // Series: only the fields that changed, plus both overlay lists (always sent, [] when empty).
    // Untouched fields are never sent (the endpoint merges, so they stay as stored).
    const seriesOptions: Record<string, any> = changedFieldPayload(fields.value, loadedSeries.value, seriesValues.value)
    // A fallback action other than "use a different preset" clears its target.
    for (const kind of ['Poster', 'Logo']) {
      const action = seriesOptions[`fallback${kind}Action`]
      if (action !== undefined && action !== 'template') {
        seriesOptions[`fallback${kind}Template`] = ''
        seriesOptions[`fallback${kind}Preset`] = ''
      } else if (action === 'template' || seriesOptions[`fallback${kind}Preset`] !== undefined) {
        // The fallback always uses this preset's own template; the renderer
        // needs it stored next to the fallback preset.
        seriesOptions[`fallback${kind}Template`] = props.templateId
      }
    }
    if (hasOverlays.value) {
      seriesOptions.overlay_config_ids = [...seriesLists.value.ids]
      seriesOptions.overlay_config_ids_below = [...seriesLists.value.below]
    }
    if (Object.keys(seriesOptions).length) {
      await post('/api/presets/save', {
        template_id: props.templateId,
        preset_id: props.preset.id,
        name: props.preset.name || props.preset.id,
        options: seriesOptions,
      })
    }
    const newBase = { ...(props.preset.options || {}), ...seriesOptions }

    let newSeasonDiff: Record<string, any> | null = props.preset.season_options || null
    const seasonChanged = Object.keys(seasonEdits.value).length > 0 || seasonOverride.value
    if (hasSeason.value && seasonChanged) {
      // Full resolved season object; the backend keeps only what differs from the series.
      const resolved: Record<string, any> = {
        ...newBase,
        ...seasonDiff.value,
        ...fieldPayload(seasonEdits.value, Object.keys(seasonEdits.value)),
      }
      const lists = seasonOverride.value ? seasonLists.value : seriesLists.value
      resolved.overlay_config_ids = [...lists.ids]
      resolved.overlay_config_ids_below = [...lists.below]
      await post('/api/presets/save-season-options', {
        template_id: props.templateId,
        preset_id: props.preset.id,
        season_options: resolved,
      })
      newSeasonDiff = resolved
    }
    success(`Saved "${props.preset.name || props.preset.id}"`)
    baseline.value = snapshot()
    emit('dirty-change', false)
    emit('saved', { before, after: presetOverlayLists(newBase, newSeasonDiff) })
  } catch (e) {
    notifyError(`Couldn't save: ${e instanceof Error ? e.message : e}`)
  } finally {
    saving.value = false
  }
}

function cancel() {
  load()
}

defineExpose({ dirty })
</script>

<template>
  <div class="pef">
    <div class="pef-top">
      <div v-if="hasSeason" class="pef-switch" role="tablist">
        <button type="button" :class="{ active: view === 'series' }" @click="view = 'series'">Series / Movie</button>
        <button type="button" :class="{ active: view === 'season' }" @click="view = 'season'">Season</button>
      </div>
      <div class="pef-groups" role="tablist">
        <button v-for="g in availableGroups" :key="g.id" type="button" :class="{ active: group === g.id }" @click="group = g.id">{{ g.label }}</button>
        <button v-if="hasOverlays" type="button" :class="{ active: group === 'overlays' }" @click="group = 'overlays'">Overlays</button>
      </div>
    </div>
    <p v-if="view === 'season'" class="pef-note">Season posters use the series value unless one is set here (marked "season").</p>

    <PresetOverlayList
      v-if="group === 'overlays'"
      :model-value="shownLists"
      :configs="overlayConfigs"
      :inherited="view === 'season' && !seasonOverride"
      @update:model-value="setLists"
      @override="overrideSeason"
    />

    <p v-else-if="group === 'fallback'" class="pef-note">
      What batch, webhook and scheduled renders do when this preset's preferred poster or logo can't be found. The manual editor never falls back.
    </p>
    <div v-if="group !== 'overlays'" class="pef-sections">
      <section v-for="sec in sections" :key="sec.title" class="pef-section">
        <h5 v-if="sec.title" class="pef-section-title">{{ sec.title }}</h5>
        <div class="pef-grid">
          <label v-for="f in sec.fields" :key="f.key" class="pef-field" :class="{ bool: f.type === 'bool' }">
            <span class="pef-label">
              {{ f.label }}
              <span v-if="differsFromSeries(f)" class="pef-season-tag">season</span>
            </span>
            <input v-if="f.type === 'bool'" type="checkbox" :checked="!!valueOf(f)" @change="setValue(f, ($event.target as HTMLInputElement).checked)" />
            <select v-else-if="f.type === 'select'" :value="valueOf(f)" @change="setValue(f, ($event.target as HTMLSelectElement).value)">
              <option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
            <select
              v-else-if="f.type === 'preset'"
              :value="valueOf(f)"
              @change="setValue(f, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">Use the first preset</option>
              <option v-for="p in fallbackPresetChoices" :key="p.id" :value="p.id">{{ p.name || p.id }}</option>
            </select>
            <span v-else-if="f.type === 'color'" class="pef-color">
              <input type="color" :value="String(valueOf(f) || '#ffffff').slice(0, 7)" @input="setValue(f, ($event.target as HTMLInputElement).value)" />
              <input type="text" :value="valueOf(f)" @change="setValue(f, ($event.target as HTMLInputElement).value)" />
            </span>
            <template v-else-if="f.type === 'font'">
              <input type="text" :list="`pef-fonts-${templateId}-${preset.id}`" :value="valueOf(f)" @change="setValue(f, ($event.target as HTMLInputElement).value)" />
            </template>
            <input
              v-else-if="f.type === 'number' || f.type === 'percent'"
              type="number"
              :min="f.min"
              :max="f.max"
              :step="f.step ?? (f.type === 'percent' ? 0.5 : 1)"
              :value="valueOf(f)"
              @input="setValue(f, ($event.target as HTMLInputElement).value)"
            />
            <input v-else type="text" :value="valueOf(f)" @change="setValue(f, ($event.target as HTMLInputElement).value)" />
            <span v-if="f.help" class="pef-help">{{ f.help }}</span>
          </label>
        </div>
      </section>
    </div>
    <datalist :id="`pef-fonts-${templateId}-${preset.id}`">
      <option v-for="name in fonts" :key="name" :value="name" />
    </datalist>

    <div class="pef-foot">
      <span v-if="dirty" class="pef-dirty">Unsaved changes</span>
      <button type="button" class="pef-btn" :disabled="!dirty || saving" @click="cancel">Cancel</button>
      <button type="button" class="pef-btn primary" :disabled="!dirty || saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
    </div>

  </div>
</template>

<style scoped>
.pef { display: flex; flex-direction: column; gap: 12px; }
.pef-top { display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between; }
.pef-switch, .pef-groups { display: flex; flex-wrap: wrap; gap: 4px; }
.pef-switch button, .pef-groups button { padding: 5px 10px; font-size: 0.8rem; border-radius: 6px; border: 1px solid var(--border, #2a2f3e); background: rgba(255, 255, 255, 0.03); color: var(--text-secondary, #9aa); cursor: pointer; }
.pef-switch button.active, .pef-groups button.active { border-color: var(--accent, #3dd6b7); color: var(--accent, #3dd6b7); background: rgba(61, 214, 183, 0.08); }
.pef-note { margin: 0; font-size: 0.78rem; color: var(--text-secondary, #9aa); }
.pef-sections { display: flex; flex-direction: column; gap: 14px; }
.pef-section { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 10px; background: rgba(255, 255, 255, 0.015); }
.pef-section-title { margin: 0; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; color: var(--text-secondary, #9aa); }
.pef-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px 14px; }
.pef-field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.pef-field.bool { flex-direction: row-reverse; justify-content: flex-end; align-items: center; gap: 8px; }
.pef-label { font-size: 0.78rem; color: var(--text-secondary, #9aa); display: flex; align-items: center; gap: 6px; }
.pef-season-tag { padding: 0 6px; border-radius: 999px; font-size: 0.65rem; background: rgba(91, 141, 238, 0.18); color: #8fb0ff; }
.pef-field input[type='text'], .pef-field input[type='number'], .pef-field select { width: 100%; min-width: 0; padding: 6px 8px; font-size: 0.85rem; border-radius: 6px; border: 1px solid var(--border, #2a2f3e); background: var(--input-bg, #1b2030); color: var(--text-primary, #fff); box-sizing: border-box; }
.pef-color { display: flex; gap: 6px; align-items: center; }
.pef-color input[type='color'] { width: 34px; height: 30px; padding: 0; border: none; background: none; flex: none; }
.pef-help { font-size: 0.7rem; color: var(--text-secondary, #9aa); }
.pef-foot { display: flex; justify-content: flex-end; align-items: center; gap: 8px; flex-wrap: wrap; }
.pef-dirty { margin-right: auto; font-size: 0.78rem; color: #ffa502; }
.pef-btn { padding: 6px 14px; font-size: 0.82rem; border-radius: 7px; border: 1px solid var(--border, #2a2f3e); background: rgba(255, 255, 255, 0.04); color: var(--text-primary, #fff); cursor: pointer; }
.pef-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.pef-btn.primary { background: var(--accent, #3dd6b7); border-color: var(--accent, #3dd6b7); color: #04130f; font-weight: 600; }
</style>
