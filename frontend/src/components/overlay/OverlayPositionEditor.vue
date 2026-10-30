<script setup lang="ts">
// One position control for every overlay layer: pin it to a corner, edge or
// the center, then set the distance from that edge in pixels of a 2000x3000 poster. Elements keep whichever
// stored format they already use, so nothing moves:
//   - imported (Kometa) elements: horizontal/vertical_align + offsets in 1000x1500 pixels
//   - everything else: a point (position_x/position_y, 0-1) plus the anchor of the
//     element that sits on that point (text uses text_align instead).
import { computed } from 'vue'

type H = 'left' | 'center' | 'right'
type V = 'top' | 'center' | 'bottom'

interface PosElement {
  type?: string
  placement?: string
  horizontal_align?: string
  vertical_align?: string
  horizontal_offset?: number | string
  vertical_offset?: number | string
  position_x?: number
  position_y?: number
  anchor?: string
  text_align?: string
  badge_anchors?: Record<string, string>
}

const props = defineProps<{ element: PosElement }>()

const isCover = computed(() => props.element.type === 'full_cover_image')
const isKometa = computed(() => props.element.placement === 'kometa')
const isPlainText = computed(() => !isKometa.value && props.element.type === 'text_label')

// Distances are shown in pixels of Simposter's 2000x3000 poster.
const POSTER_W = 2000
const POSTER_H = 3000
// Kometa offsets are in a 1000x1500 space, i.e. half of the poster's pixels.
const KOMETA_TO_POSTER = 2

// ---- read the current pin + distances ----

const parseAnchor = (a: string | undefined): [V, H] => {
  const t = (a || 'center').toLowerCase()
  if (t === 'center') return ['center', 'center']
  const [v, h] = t.split('-')
  return [(['top', 'center', 'bottom'].includes(v || '') ? v : 'center') as V, (['left', 'center', 'right'].includes(h || '') ? h : 'center') as H]
}

const pinH = computed<H>(() => {
  if (isKometa.value) return ((props.element.horizontal_align || 'left').toLowerCase() as H)
  if (isPlainText.value) {
    const a = (props.element.text_align || 'center').toLowerCase()
    return (a === 'left' || a === 'right' ? a : 'center') as H
  }
  return parseAnchor(props.element.anchor)[1]
})

const pinV = computed<V>(() => {
  if (isKometa.value) return ((props.element.vertical_align || 'top').toLowerCase() as V)
  return parseAnchor(props.element.anchor)[0]
})

/** Kometa offset (pixels in 1000x1500 space, or "N%" of the poster) in poster pixels. */
const kometaPx = (value: number | string | undefined, posterSpan: number): number => {
  if (value === undefined || value === null || value === '') return 0
  const t = String(value).trim()
  if (t.endsWith('%')) return (Number(t.slice(0, -1)) || 0) / 100 * posterSpan
  return (Number(t) || 0) * KOMETA_TO_POSTER
}

type Edge = 'left' | 'top' | 'right' | 'bottom' | 'center'
/** A 0-1 point as a distance (in poster pixels) from the given edge, or from the center. */
const pointToDistance = (p: number, edge: Edge, span: number) =>
  edge === 'left' || edge === 'top' ? p * span : edge === 'right' || edge === 'bottom' ? (1 - p) * span : (p - 0.5) * span

const distanceToPoint = (d: number, edge: Edge, span: number) =>
  edge === 'left' || edge === 'top' ? d / span : edge === 'right' || edge === 'bottom' ? 1 - d / span : 0.5 + d / span

const distX = computed(() => Math.round(isKometa.value
  ? kometaPx(props.element.horizontal_offset, POSTER_W)
  : pointToDistance(props.element.position_x ?? 0.5, pinH.value, POSTER_W)))

const distY = computed(() => Math.round(isKometa.value
  ? kometaPx(props.element.vertical_offset, POSTER_H)
  : pointToDistance(props.element.position_y ?? 0.5, pinV.value, POSTER_H)))

// ---- write ----

const write = (h: H, v: V, dx: number, dy: number) => {
  const el = props.element
  if (isKometa.value) {
    el.horizontal_align = h
    el.vertical_align = v
    el.horizontal_offset = Math.round(dx / KOMETA_TO_POSTER)
    el.vertical_offset = Math.round(dy / KOMETA_TO_POSTER)
    return
  }
  el.position_x = Math.round(distanceToPoint(dx, h, POSTER_W) * 10000) / 10000
  el.position_y = Math.round(distanceToPoint(dy, v, POSTER_H) * 10000) / 10000
  el.anchor = v === 'center' && h === 'center' ? 'center' : `${v}-${h}`
  if (isPlainText.value) el.text_align = h
}

/** Pin to a new spot, keeping the same distances (centered axes start at 0). */
const pin = (v: V, h: H) => {
  // Moving off center starts 60px in from the edge.
  const dx = h === pinH.value ? distX.value : (h === 'center' ? 0 : (pinH.value === 'center' ? 60 : distX.value))
  const dy = v === pinV.value ? distY.value : (v === 'center' ? 0 : (pinV.value === 'center' ? 60 : distY.value))
  write(h, v, dx, dy)
}

const setDist = (axis: 'x' | 'y', text: string) => {
  const n = Math.round(Number(text))
  if (!Number.isFinite(n)) return
  write(pinH.value, pinV.value, axis === 'x' ? n : distX.value, axis === 'y' ? n : distY.value)
}

const xLabel = computed(() => pinH.value === 'left' ? 'From left edge' : pinH.value === 'right' ? 'From right edge' : 'Shift right (negative = left)')
const yLabel = computed(() => pinV.value === 'top' ? 'From top edge' : pinV.value === 'bottom' ? 'From bottom edge' : 'Shift down (negative = up)')

const ROWS: V[] = ['top', 'center', 'bottom']
const COLS: H[] = ['left', 'center', 'right']
const cellTitle = (v: V, h: H) => (v === 'center' && h === 'center' ? 'Center' : `${v === 'center' ? 'Middle' : v[0]!.toUpperCase() + v.slice(1)} ${h === 'center' ? 'center' : h}`)

const hasPerValueAnchors = computed(() =>
  Object.values(props.element.badge_anchors || {}).some(v => !!v))
</script>

<template>
  <div class="pos">
    <p v-if="isCover" class="hint">This layer always fills the whole poster, so it has no position.</p>
    <template v-else>
      <div class="pos-main">
        <div class="pin-wrap">
          <span class="lbl">Pin to</span>
          <div class="pin-grid" role="radiogroup" aria-label="Pin to">
            <template v-for="v in ROWS" :key="v">
              <button
                v-for="h in COLS"
                :key="v + h"
                type="button"
                class="pin-cell"
                :class="{ on: pinV === v && pinH === h }"
                :title="cellTitle(v, h)"
                @click="pin(v, h)"
              ><span class="dot"></span></button>
            </template>
          </div>
        </div>
        <div class="dist">
          <label>
            <span class="lbl">{{ xLabel }}</span>
            <div class="num"><input type="number" step="10" :value="distX" @change="setDist('x', ($event.target as HTMLInputElement).value)" /><em>px</em></div>
          </label>
          <label>
            <span class="lbl">{{ yLabel }}</span>
            <div class="num"><input type="number" step="10" :value="distY" @change="setDist('y', ($event.target as HTMLInputElement).value)" /><em>px</em></div>
          </label>
        </div>
      </div>
      <p class="hint">
        Distances are in pixels of the finished 2000×3000 poster. You can also drag the layer on the preview.
        <template v-if="isPlainText"> Text is measured to its middle line.</template>
      </p>
      <p v-if="hasPerValueAnchors" class="hint">Some badge values have their own anchor under Look, which overrides the pin for those values.</p>
    </template>
  </div>
</template>

<style scoped>
.pos { grid-column: 1 / -1; display: flex; flex-direction: column; gap: 0.5rem; }
.pos-main { display: flex; gap: 1rem; align-items: flex-start; flex-wrap: wrap; }
.pin-wrap { display: flex; flex-direction: column; gap: 0.3rem; }
.lbl { font-size: 0.72rem; color: var(--text-secondary, #888); font-weight: 500; }
.pin-grid { display: grid; grid-template-columns: repeat(3, 26px); grid-template-rows: repeat(3, 26px); gap: 3px; padding: 4px; border: 1px solid var(--border, #2a2f3e); border-radius: 6px; background: rgba(255, 255, 255, 0.02); width: max-content; }
.pin-cell { display: flex; align-items: center; justify-content: center; padding: 0; border: 1px solid transparent; border-radius: 4px; background: rgba(255, 255, 255, 0.03); cursor: pointer; }
.pin-cell .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-secondary, #666); }
.pin-cell:hover { border-color: var(--border, #3a4050); }
.pin-cell.on { background: rgba(61, 214, 183, 0.18); border-color: rgba(61, 214, 183, 0.6); }
.pin-cell.on .dot { background: var(--accent, #3dd6b7); width: 9px; height: 9px; }
.dist { flex: 1; min-width: 180px; display: flex; flex-direction: column; gap: 0.45rem; }
.dist label { display: flex; flex-direction: column; gap: 0.2rem; }
.num { display: flex; align-items: center; gap: 0.3rem; }
.num input { width: 100%; max-width: 120px; padding: 0.32rem 0.4rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.8rem; }
.num input:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.num em { font-style: normal; font-size: 0.75rem; color: var(--text-secondary, #888); }
.hint { margin: 0; font-size: 0.68rem; color: var(--text-secondary, #888); line-height: 1.4; }
</style>
