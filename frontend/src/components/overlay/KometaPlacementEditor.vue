<script setup lang="ts">
// Background box and outline for a text or image element (part of its Look).
// These only exist for elements using Kometa-style placement (align + offset in
// a 1000x1500 space). Adding a box to a plain element converts it, keeping its
// position and roughly its size; the Position tab works the same either way.
import { computed } from 'vue'
import type { OverlayRuleFields } from '@/services/overlayEngine'

const props = defineProps<{ element: OverlayRuleFields & { type: string } }>()

const isKometa = computed(() => props.element.placement === 'kometa')
const isBoxOnly = computed(() => !!props.element.box_only)
const isText = computed(() => props.element.type === 'text_label' && !isBoxOnly.value)

/** Convert a plain (point + anchor) element to Kometa placement in place. */
const convert = () => {
  const el = props.element as Record<string, any>
  const anchor = String(el.anchor || 'center').toLowerCase()
  const [v0, h0] = anchor === 'center' ? ['center', 'center'] : anchor.split('-')
  let h = (h0 || 'center') as string
  const v = (v0 || 'center') as string
  if (isText.value) {
    const a = String(el.text_align || 'center').toLowerCase()
    h = a === 'left' || a === 'right' ? a : 'center'
  }
  const px = Number(el.position_x ?? 0.5)
  const py = Number(el.position_y ?? 0.5)
  const dist = (p: number, edge: string) => (edge === 'left' || edge === 'top' ? p : edge === 'center' ? p - 0.5 : 1 - p) * 100
  el.placement = 'kometa'
  el.horizontal_align = h
  el.vertical_align = v
  el.horizontal_offset = Math.round(dist(px, h) * 10)
  el.vertical_offset = Math.round(dist(py, v) * 15)
  // Kometa sizes are in a 1000x1500 space and scale up with the poster (x2 on 2000x3000).
  if (isText.value) el.font_size = Math.max(1, Math.round(Number(el.font_size || 40) / 2))
  else el.scale = Math.round(Number(el.scale || 1) / 2 * 100) / 100
  if (!el.back_color) el.back_color = '#00000099'
  if (el.back_padding === undefined) el.back_padding = 10
  if (el.back_radius === undefined) el.back_radius = 10
}

const BOX_KEYS = ['back_color', 'back_width', 'back_height', 'back_padding', 'back_radius', 'back_align', 'back_line_width', 'back_line_color'] as const
/** A box is drawn when it has a color or a border. */
const hasBox = computed(() => {
  const el = props.element as unknown as Record<string, unknown>
  return !!el.back_color || (!!el.back_line_width && Number(el.back_line_width) > 0)
})
const removeBox = () => {
  const el = props.element as unknown as Record<string, unknown>
  for (const k of BOX_KEYS) delete el[k]
}
const addBox = () => {
  const el = props.element as unknown as Record<string, unknown>
  el.back_color = '#00000099'
  if (el.back_padding === undefined) el.back_padding = 10
  if (el.back_radius === undefined) el.back_radius = 10
}
const hasOutline = computed(() => Number((props.element as unknown as Record<string, unknown>).stroke_width || 0) > 0)
const removeOutline = () => {
  const el = props.element as unknown as Record<string, unknown>
  delete el.stroke_width
  delete el.stroke_color
}

type NumKey = 'back_width' | 'back_height' | 'back_radius' | 'back_padding' | 'back_line_width' | 'stroke_width'
type TextKey = 'back_color' | 'back_line_color' | 'stroke_color' | 'url' | 'back_align'

const setNum = (key: NumKey, text: string) => {
  if (text.trim() === '' || !Number.isFinite(Number(text))) delete props.element[key]
  else props.element[key] = Number(text)
}

const setText = (key: TextKey, text: string) => {
  const t = text.trim()
  if (t) props.element[key] = t
  else delete props.element[key]
}

// The color picker only knows #RRGGBB; keep any alpha typed in the text box.
const pickColor = (key: 'back_color' | 'back_line_color' | 'stroke_color', hex: string) => {
  const current = (props.element[key] || '').replace(/^#/, '')
  const alpha = current.length === 8 ? current.slice(6) : ''
  props.element[key] = hex + alpha
}
const pickerValue = (v: string | undefined, fallback: string) => {
  const t = (v || '').replace(/^#/, '')
  return /^[0-9a-f]{6}/i.test(t) ? `#${t.slice(0, 6)}` : fallback
}
</script>

<template>
  <div class="kp">
    <template v-if="!isKometa">
      <button type="button" class="kp-add" @click="convert">+ Add a background box{{ isText ? ' or outline' : '' }}</button>
    </template>

    <template v-else>
      <div v-if="!isBoxOnly" class="kp-sec">
      <div class="kp-sec-head">
        <div class="kp-sec-title">{{ isText ? 'Outline' : 'Image link' }}</div>
        <button v-if="isText && hasOutline" type="button" class="kp-remove" @click="removeOutline">Remove outline</button>
      </div>
      <div class="kp-grid">
        <label v-if="!isText" class="full">
          <span>Image URL (used when no image is picked above)</span>
          <input type="text" :value="element.url || ''" placeholder="https://..." @change="setText('url', ($event.target as HTMLInputElement).value)" />
        </label>

        <template v-if="isText">
          <label>
            <span>Outline width</span>
            <input type="number" min="0" :value="element.stroke_width ?? ''" placeholder="0" @change="setNum('stroke_width', ($event.target as HTMLInputElement).value)" />
          </label>
          <label>
            <span>Outline color</span>
            <div class="color-wrap">
              <input type="color" :value="pickerValue(element.stroke_color, '#000000')" @input="pickColor('stroke_color', ($event.target as HTMLInputElement).value)" />
              <input type="text" :value="element.stroke_color || ''" placeholder="#000000" @change="setText('stroke_color', ($event.target as HTMLInputElement).value)" />
            </div>
          </label>
        </template>
      </div>
      </div>

      <div v-if="!hasBox" class="kp-sec">
      <p v-if="isBoxOnly" class="kp-note">This box has no color yet, so nothing is drawn.</p>
      <button type="button" class="kp-add" @click="addBox">+ Add a background box</button>
      </div>
      <div v-else class="kp-sec">
      <div class="kp-sec-head">
        <div class="kp-sec-title">Background box</div>
        <button v-if="!isBoxOnly" type="button" class="kp-remove" @click="removeBox">Remove background box</button>
      </div>
      <div class="kp-grid">
        <label>
          <span>Color (#RRGGBBAA for transparency)</span>
          <div class="color-wrap">
            <input type="color" :value="pickerValue(element.back_color, '#000000')" @input="pickColor('back_color', ($event.target as HTMLInputElement).value)" />
            <input type="text" :value="element.back_color || ''" placeholder="none" @change="setText('back_color', ($event.target as HTMLInputElement).value)" />
          </div>
        </label>
        <label>
          <span>Content align</span>
          <select :value="element.back_align || 'center'" @change="setText('back_align', ($event.target as HTMLSelectElement).value === 'center' ? '' : ($event.target as HTMLSelectElement).value)">
            <option value="center">Center</option>
            <option value="left">Left</option>
            <option value="right">Right</option>
            <option value="top">Top</option>
            <option value="bottom">Bottom</option>
          </select>
        </label>
        <label>
          <span>Width</span>
          <input type="number" min="0" :value="element.back_width ?? ''" placeholder="fit" @change="setNum('back_width', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Height</span>
          <input type="number" min="0" :value="element.back_height ?? ''" placeholder="fit" @change="setNum('back_height', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Padding</span>
          <input type="number" min="0" :value="element.back_padding ?? ''" placeholder="0" @change="setNum('back_padding', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Corner radius</span>
          <input type="number" min="0" :value="element.back_radius ?? ''" placeholder="0" @change="setNum('back_radius', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Border width</span>
          <input type="number" min="0" :value="element.back_line_width ?? ''" placeholder="0" @change="setNum('back_line_width', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Border color</span>
          <div class="color-wrap">
            <input type="color" :value="pickerValue(element.back_line_color, '#ffffff')" @input="pickColor('back_line_color', ($event.target as HTMLInputElement).value)" />
            <input type="text" :value="element.back_line_color || ''" placeholder="#FFFFFF" @change="setText('back_line_color', ($event.target as HTMLInputElement).value)" />
          </div>
        </label>
      </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.kp { grid-column: 1 / -1; display: flex; flex-direction: column; gap: 0.45rem; }
.kp-grid label span { color: var(--text-secondary, #888); font-size: 0.72rem; font-weight: 500; }
.kp-sec { display: flex; flex-direction: column; gap: 0.5rem; padding: 0.6rem 0.7rem 0.7rem; border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 8px; background: rgba(255, 255, 255, 0.015); }
.kp-sec-head { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.kp-remove { background: none; border: none; padding: 0; color: var(--text-secondary, #888); font-size: 0.72rem; cursor: pointer; }
.kp-remove:hover { color: #f87171; text-decoration: underline; }
.kp-sec-title { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--accent, #3dd6b7); }
.kp-add { align-self: flex-start; padding: 0.3rem 0.7rem; background: rgba(61, 214, 183, 0.08); border: 1px dashed rgba(61, 214, 183, 0.35); border-radius: 6px; color: var(--accent, #3dd6b7); cursor: pointer; font-size: 0.74rem; }
.kp-note { margin: 0 0 0.4rem; font-size: 0.72rem; color: var(--text-secondary, #888); }
.kp-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.45rem; }
.kp-grid label { display: flex; flex-direction: column; gap: 0.2rem; min-width: 0; }
.kp-grid label.full { grid-column: 1 / -1; }
.kp input, .kp select { padding: 0.32rem 0.4rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 5px; color: var(--text-primary, #fff); font-size: 0.78rem; min-width: 0; }
.kp input:focus, .kp select:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.color-wrap { display: flex; gap: 0.3rem; }
.color-wrap input[type='color'] { width: 30px; padding: 0; height: 28px; flex: none; cursor: pointer; }
.color-wrap input[type='text'] { flex: 1; }
</style>
