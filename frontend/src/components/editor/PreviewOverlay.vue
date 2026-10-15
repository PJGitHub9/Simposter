<script setup lang="ts">
// Overlay drawn on top of the editor's preview image: a small toolbar
// (boxes / guides toggles), the logo and text boxes (drag to move, drag the
// corner handle to resize), and optional center/safe-area guides.
// Used by both EditorPane.vue and TvShowEditorPane.vue. Must be rendered
// directly inside the positioned .preview-container that also holds the
// preview <img>, since everything is placed using the image's offsetLeft/Top.
import { ref, computed, watch, onBeforeUnmount } from 'vue'

export interface PreviewBox {
  maxW: number
  maxH: number
  offsetX: number // percent of image width (box center)
  offsetY: number // percent of image height (box center)
}

const props = defineProps<{
  img: HTMLImageElement | null
  canShowBoxes: boolean
  showBoxes: boolean
  logoBox: PreviewBox | null
  textBox: PreviewBox | null
}>()

const emit = defineEmits<{
  'update:showBoxes': [value: boolean]
  'update:logoBox': [box: PreviewBox]
  'update:textBox': [box: PreviewBox]
}>()

const GUIDES_KEY = 'simposter-editor-guides'
const readGuides = () => {
  try {
    return localStorage.getItem(GUIDES_KEY) === '1'
  } catch {
    return false
  }
}
const showGuides = ref(readGuides())
watch(showGuides, (v) => {
  try {
    localStorage.setItem(GUIDES_KEY, v ? '1' : '0')
  } catch {
    /* storage unavailable */
  }
})

// Where the image sits inside the container, and its natural (render) size.
const rect = ref({ left: 0, top: 0, width: 0, height: 0, natW: 2000, natH: 3000 })
const measure = () => {
  const img = props.img
  if (!img) {
    rect.value = { left: 0, top: 0, width: 0, height: 0, natW: 2000, natH: 3000 }
    return
  }
  rect.value = {
    left: img.offsetLeft,
    top: img.offsetTop,
    width: img.clientWidth,
    height: img.clientHeight,
    natW: img.naturalWidth || 2000,
    natH: img.naturalHeight || 3000
  }
}

let observer: ResizeObserver | null = null
watch(
  () => props.img,
  (img, old) => {
    observer?.disconnect()
    old?.removeEventListener('load', measure)
    if (img) {
      observer = new ResizeObserver(measure)
      observer.observe(img)
      img.addEventListener('load', measure)
    }
    measure()
  },
  { immediate: true }
)
window.addEventListener('resize', measure)
onBeforeUnmount(() => {
  observer?.disconnect()
  props.img?.removeEventListener('load', measure)
  window.removeEventListener('resize', measure)
  stopDrag()
})

const imageRectStyle = computed(() => ({
  left: `${rect.value.left}px`,
  top: `${rect.value.top}px`,
  width: `${rect.value.width}px`,
  height: `${rect.value.height}px`
}))

const boxStyle = (b: PreviewBox) => {
  const r = rect.value
  if (!r.width || !r.height) return { display: 'none' }
  const w = b.maxW * (r.width / r.natW)
  const h = b.maxH * (r.height / r.natH)
  return {
    width: `${w}px`,
    height: `${h}px`,
    left: `${r.left + (r.width * b.offsetX) / 100 - w / 2}px`,
    top: `${r.top + (r.height * b.offsetY) / 100 - h / 2}px`
  }
}

const boxes = computed(() => {
  if (!props.canShowBoxes || !props.showBoxes) return []
  const list: { kind: 'logo' | 'text'; label: string; box: PreviewBox }[] = []
  if (props.logoBox) list.push({ kind: 'logo', label: 'Logo', box: props.logoBox })
  if (props.textBox) list.push({ kind: 'text', label: 'Text', box: props.textBox })
  return list
})

// Dragging
const dragging = ref<'logo' | 'text' | null>(null)
let moveHandler: ((e: PointerEvent) => void) | null = null
const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v))

function stopDrag() {
  if (moveHandler) window.removeEventListener('pointermove', moveHandler)
  window.removeEventListener('pointerup', stopDrag)
  moveHandler = null
  dragging.value = null
}

function startDrag(e: PointerEvent, kind: 'logo' | 'text', mode: 'move' | 'resize') {
  const box = kind === 'logo' ? props.logoBox : props.textBox
  const r = { ...rect.value }
  if (!box || !r.width || !r.height) return
  e.preventDefault()
  e.stopPropagation()
  stopDrag()
  const start = { ...box }
  const startX = e.clientX
  const startY = e.clientY
  const scaleX = r.width / r.natW
  const scaleY = r.height / r.natH
  dragging.value = kind
  moveHandler = (ev: PointerEvent) => {
    const dx = ev.clientX - startX
    const dy = ev.clientY - startY
    const next: PreviewBox =
      mode === 'move'
        ? {
            ...start,
            offsetX: clamp(Math.round(start.offsetX + (dx / r.width) * 100), 0, 100),
            offsetY: clamp(Math.round(start.offsetY + (dy / r.height) * 100), 0, 100)
          }
        : {
            // The box is centered on its offset, so a corner drag grows both sides.
            ...start,
            maxW: clamp(Math.round(start.maxW + (2 * dx) / scaleX), 50, 1800),
            maxH: clamp(Math.round(start.maxH + (2 * dy) / scaleY), 50, 2800)
          }
    if (kind === 'logo') emit('update:logoBox', next)
    else emit('update:textBox', next)
  }
  window.addEventListener('pointermove', moveHandler)
  window.addEventListener('pointerup', stopDrag)
}
</script>

<template>
  <div class="overlay-toolbar">
    <button
      v-if="canShowBoxes"
      type="button"
      class="overlay-btn"
      :class="{ active: showBoxes }"
      title="Show the logo and text boxes. Drag a box to move it, drag its corner to resize."
      @click="emit('update:showBoxes', !showBoxes)"
    >▭ Boxes</button>
    <button
      type="button"
      class="overlay-btn"
      :class="{ active: showGuides }"
      title="Show center lines and a 5% safe-area margin"
      @click="showGuides = !showGuides"
    ># Guides</button>
  </div>

  <div v-if="showGuides && rect.width" class="guides" :style="imageRectStyle">
    <div class="guide-line vertical"></div>
    <div class="guide-line horizontal"></div>
    <div class="guide-safe"></div>
  </div>

  <div
    v-for="b in boxes"
    :key="b.kind"
    class="edit-box"
    :class="[b.kind, { dragging: dragging === b.kind }]"
    :style="boxStyle(b.box)"
    @pointerdown="startDrag($event, b.kind, 'move')"
  >
    <span class="edit-box-label">{{ b.label }}</span>
    <span
      class="edit-box-handle"
      title="Drag to resize"
      @pointerdown="startDrag($event, b.kind, 'resize')"
    ></span>
  </div>
</template>

<style scoped>
.overlay-toolbar {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  gap: 6px;
  z-index: 12;
}

.overlay-btn {
  padding: 4px 9px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(10, 12, 18, 0.75);
  color: #c9d1e0;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.overlay-btn:hover {
  background: rgba(30, 34, 46, 0.9);
}

.overlay-btn.active {
  border-color: rgba(61, 214, 183, 0.6);
  color: #3dd6b7;
}

.guides {
  position: absolute;
  pointer-events: none;
  z-index: 9;
}

.guide-line {
  position: absolute;
  background: rgba(255, 255, 255, 0.45);
}

.guide-line.vertical {
  left: 50%;
  top: 0;
  bottom: 0;
  width: 1px;
}

.guide-line.horizontal {
  top: 50%;
  left: 0;
  right: 0;
  height: 1px;
}

.guide-safe {
  position: absolute;
  inset: 5%;
  border: 1px dashed rgba(255, 255, 255, 0.4);
}

.edit-box {
  position: absolute;
  border: 2px dashed rgba(255, 255, 0, 0.85);
  cursor: move;
  touch-action: none;
  z-index: 11;
}

.edit-box.text {
  border-color: rgba(0, 220, 255, 0.9);
}

.edit-box.dragging,
.edit-box:hover {
  background: rgba(255, 255, 255, 0.06);
}

.edit-box-label {
  position: absolute;
  top: -1px;
  left: -1px;
  padding: 1px 5px;
  font-size: 10px;
  font-weight: 700;
  color: #0a0c12;
  background: rgba(255, 255, 0, 0.85);
  pointer-events: none;
}

.edit-box.text .edit-box-label {
  background: rgba(0, 220, 255, 0.9);
}

.edit-box-handle {
  position: absolute;
  right: -6px;
  bottom: -6px;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  background: rgba(255, 255, 0, 0.95);
  border: 1px solid rgba(0, 0, 0, 0.5);
  cursor: nwse-resize;
}

.edit-box.text .edit-box-handle {
  background: rgba(0, 220, 255, 0.95);
}
</style>
