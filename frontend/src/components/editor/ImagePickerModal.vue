<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'

// "View all" grid for the manual editors' Poster section: shows the same
// (already filtered) poster or backdrop candidates as the thumbnail strip,
// but large and all at once instead of scrolling a single row.
type ImageCandidate = {
  url: string
  thumb?: string
  has_text?: boolean
  language?: string
  source?: string
  width?: number
  height?: number
}

const props = defineProps<{
  title: string
  images: ImageCandidate[]
  selected: string | null
  wide?: boolean
}>()

const emit = defineEmits<{
  close: []
  select: [url: string]
}>()

// TMDb's resized thumbnail can 404 while the original loads fine (Quirk #29).
const failedThumbs = ref(new Set<string>())
const thumbSrc = (img: ImageCandidate) => (failedThumbs.value.has(img.url) ? img.url : img.thumb || img.url)
const onThumbError = (img: ImageCandidate) => {
  if (img.thumb && img.thumb !== img.url && !failedThumbs.value.has(img.url)) {
    failedThumbs.value = new Set(failedThumbs.value).add(img.url)
  }
}

const textLabel = (img: ImageCandidate) => (img.has_text === false || !img.language ? 'Textless' : (img.language || '').toUpperCase())

function choose(url: string) {
  emit('select', url)
  emit('close')
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div class="picker-backdrop" @click.self="emit('close')">
      <div class="picker-modal">
        <div class="picker-header">
          <h3>{{ title }} <span class="picker-count">{{ props.images.length }}</span></h3>
          <button type="button" class="picker-close" aria-label="Close" @click="emit('close')">✕</button>
        </div>
        <p v-if="!props.images.length" class="picker-empty">Nothing matches the current filter.</p>
        <div v-else class="picker-grid" :class="{ wide }">
          <button
            v-for="img in props.images"
            :key="img.url"
            type="button"
            class="picker-tile"
            :class="{ active: img.url === props.selected }"
            @click="choose(img.url)"
          >
            <img :src="thumbSrc(img)" alt="" loading="lazy" referrerpolicy="no-referrer" @error="onThumbError(img)" />
            <div class="picker-meta">
              <span class="picker-badge">{{ (img.source || 'tmdb').toUpperCase() }}</span>
              <span class="picker-badge">{{ textLabel(img) }}</span>
              <span v-if="img.width && img.height" class="picker-size">{{ img.width }}×{{ img.height }}</span>
            </div>
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.picker-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1100;
  padding: 20px;
}

.picker-modal {
  background: #14161f;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  padding: 20px;
  width: 100%;
  max-width: 1100px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.picker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.picker-header h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary, #eef2ff);
}

.picker-count {
  font-size: 12px;
  color: var(--muted, #a8b3cf);
  margin-left: 6px;
}

.picker-close {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: var(--text-primary, #eef2ff);
  border-radius: 8px;
  padding: 4px 10px;
  cursor: pointer;
}

.picker-empty {
  color: var(--muted, #a8b3cf);
  font-size: 13px;
}

.picker-grid {
  /* The modal is a fixed-height flex column: let the grid take the remaining space and
     scroll, and keep rows at their natural height instead of squashing to fit. */
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  grid-auto-rows: max-content;
  align-content: start;
  gap: 12px;
  padding-right: 4px;
}

.picker-grid.wide {
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
}

.picker-tile {
  position: relative;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 10px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.04);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  transition: border-color 0.15s, transform 0.15s;
}

.picker-tile:hover {
  border-color: rgba(61, 214, 183, 0.5);
  transform: translateY(-2px);
}

.picker-tile.active {
  border-color: var(--accent, #3dd6b7);
}

.picker-tile img {
  width: 100%;
  aspect-ratio: 2 / 3;
  object-fit: cover;
  display: block;
  flex-shrink: 0;
}

.picker-grid.wide .picker-tile img {
  aspect-ratio: 16 / 9;
}

.picker-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 6px;
}

.picker-badge {
  font-size: 10px;
  letter-spacing: 0.5px;
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-primary, #eef2ff);
}

.picker-size {
  font-size: 10px;
  color: var(--muted, #a8b3cf);
  margin-left: auto;
}
</style>
