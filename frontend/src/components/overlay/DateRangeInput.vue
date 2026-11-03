<script setup lang="ts">
// A date (or date range) for an overlay rule. "Every year" stores MM-DD values,
// which the engines treat as a yearly window that may wrap past New Year
// (12-20 to 01-05). Otherwise full YYYY-MM-DD dates.
import { computed } from 'vue'
import { rangeParts } from '@/services/overlayFields'

const props = defineProps<{ modelValue: unknown; range: boolean; allowYearly: boolean; yearlyDefault?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DAYS = Array.from({ length: 31 }, (_, i) => i + 1)
const pad = (n: number | string) => String(n).padStart(2, '0')

// Windows people commonly want; picking one fills both ends.
const SEASONS: Array<{ label: string; start: string; end: string }> = [
  { label: 'Christmas', start: '12-01', end: '12-26' },
  { label: 'New Year', start: '12-27', end: '01-02' },
  { label: "Valentine's Day", start: '02-07', end: '02-14' },
  { label: "St Patrick's Day", start: '03-10', end: '03-17' },
  { label: 'Halloween', start: '10-01', end: '10-31' },
  { label: 'Summer', start: '06-21', end: '09-22' },
]

const parts = computed<[string, string]>(() =>
  props.range ? rangeParts(props.modelValue) : [String(props.modelValue ?? '').trim(), ''])

const isMonthDay = (v: string) => /^\d{1,2}-\d{1,2}$/.test(v)
const isFullDate = (v: string) => /^\d{4}-\d{2}-\d{2}$/.test(v)

// Yearly when the stored values say so; for an empty value, the field's default.
const yearly = computed(() => {
  if (!props.allowYearly) return false
  const filled = parts.value.filter(Boolean)
  if (!filled.length) return !!props.yearlyDefault
  return filled.every(isMonthDay)
})

const emitParts = (a: string, b: string) => emit('update:modelValue', props.range ? [a, b] : a)

const setPart = (i: 0 | 1, v: string) => {
  const next: [string, string] = [...parts.value]
  next[i] = v
  emitParts(next[0], next[1])
}

const md = (v: string): [number, number] => {
  const m = v.match(/^(\d{1,2})-(\d{1,2})$/)
  return m ? [Number(m[1]), Number(m[2])] : [1, 1]
}
const setMonth = (i: 0 | 1, month: number) => setPart(i, `${pad(month)}-${pad(md(parts.value[i] || '01-01')[1])}`)
const setDay = (i: 0 | 1, day: number) => setPart(i, `${pad(md(parts.value[i] || '01-01')[0])}-${pad(day)}`)

// Switching between yearly and fixed dates converts what's there.
const toggleYearly = (on: boolean) => {
  const year = new Date().getFullYear()
  const conv = (v: string) => {
    if (!v) return ''
    if (on && isFullDate(v)) return v.slice(5)
    if (!on && isMonthDay(v)) { const [m, d] = md(v); return `${year}-${pad(m)}-${pad(d)}` }
    return v
  }
  const [a, b] = parts.value
  const ca = conv(a) || (on ? '12-01' : '')
  const cb = conv(b) || (on ? '12-26' : '')
  emitParts(ca, props.range ? cb : '')
}

const pickSeason = (label: string) => {
  const s = SEASONS.find(x => x.label === label)
  if (s) emitParts(s.start, s.end)
}
</script>

<template>
  <div class="dri">
    <div class="dri-row">
      <template v-for="i in (range ? [0, 1] : [0]) as (0 | 1)[]" :key="i">
        <span v-if="i === 1" class="dri-and">and</span>
        <span v-if="yearly" class="dri-md">
          <select :value="md(parts[i] || '01-01')[0]" @change="setMonth(i, Number(($event.target as HTMLSelectElement).value))">
            <option v-for="(m, mi) in MONTHS" :key="m" :value="mi + 1">{{ m }}</option>
          </select>
          <select :value="md(parts[i] || '01-01')[1]" @change="setDay(i, Number(($event.target as HTMLSelectElement).value))">
            <option v-for="d in DAYS" :key="d" :value="d">{{ d }}</option>
          </select>
        </span>
        <input v-else type="date" :value="isFullDate(parts[i]) ? parts[i] : ''" @change="setPart(i, ($event.target as HTMLInputElement).value)" />
      </template>
    </div>
    <div v-if="allowYearly" class="dri-row dri-opts">
      <label class="dri-check"><input type="checkbox" :checked="yearly" @change="toggleYearly(($event.target as HTMLInputElement).checked)" /> Every year</label>
      <select v-if="yearly && range" class="dri-season" value="" @change="pickSeason(($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''">
        <option value="" disabled>Quick pick…</option>
        <option v-for="s in SEASONS" :key="s.label" :value="s.label">{{ s.label }}</option>
      </select>
    </div>
  </div>
</template>

<style scoped>
.dri { display: flex; flex-direction: column; gap: 0.3rem; }
.dri-row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem; }
.dri-md { display: inline-flex; gap: 0.2rem; }
.dri-and { font-size: 0.72rem; color: var(--text-secondary, #888); }
.dri-check { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.72rem; color: var(--text-secondary, #aaa); cursor: pointer; }
.dri-check input { margin: 0; }
.dri select, .dri input[type='date'] { padding: 0.32rem 0.4rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.78rem; color-scheme: dark; }
:root[data-theme='light'] .dri select, :root[data-theme='light'] .dri input[type='date'] { color-scheme: light; }
.dri select option { background: var(--surface, #1b1f2a); color: var(--text-primary, #fff); }
.dri select:focus, .dri input:focus { outline: none; border-color: var(--accent, #3dd6b7); }
</style>
