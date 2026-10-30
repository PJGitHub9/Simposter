<script setup lang="ts">
// A small collapsible group inside an editor tab (e.g. "Logo box", "Drop shadow").
// Open/closed is remembered per title in localStorage, shared by both editors.
import { ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  title: string
  summary?: string
  defaultOpen?: boolean
}>(), { summary: '', defaultOpen: false })

const STORAGE_KEY = 'simposter-editor-cards'

function readAll(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {}
  } catch {
    return {}
  }
}

const saved = readAll()[props.title]
const open = ref<boolean>(typeof saved === 'boolean' ? saved : props.defaultOpen)

watch(open, (val) => {
  try {
    const all = readAll()
    all[props.title] = val
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
  } catch {
    /* storage unavailable: keep the in-memory state */
  }
})
</script>

<template>
  <div class="editor-card" :class="{ open }">
    <button type="button" class="editor-card-header" @click="open = !open">
      <svg class="editor-card-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="9 6 15 12 9 18" />
      </svg>
      <span class="editor-card-title">{{ title }}</span>
      <span v-if="summary" class="editor-card-summary">{{ summary }}</span>
    </button>
    <div v-show="open" class="editor-card-body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.editor-card {
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  margin-top: 10px;
}

.editor-card.open {
  border-color: rgba(61, 214, 183, 0.22);
}

.editor-card-header {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: none;
  border: none;
  color: #dbe4ff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}

.editor-card-header:hover .editor-card-title {
  color: var(--accent, #3dd6b7);
}

.editor-card-chevron {
  flex-shrink: 0;
  color: var(--muted);
  transition: transform 0.15s ease;
}

.editor-card.open .editor-card-chevron {
  transform: rotate(90deg);
}

.editor-card-title {
  flex: 1;
  transition: color 0.15s;
}

.editor-card-summary {
  font-size: 11px;
  font-weight: 500;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 55%;
}

.editor-card-body {
  padding: 2px 12px 12px;
}
</style>
