<script setup lang="ts">
defineProps<{
  open: { value: boolean }
}>()

const emit = defineEmits<{
  (e: 'toggle'): void
}>()
</script>

<template>
  <section class="drawer" :class="{ open: open.value }">
    <div class="drawer__handle" @click="emit('toggle')">
      <span>{{ open.value ? 'Collapse Editor' : 'Expand Editor' }}</span>
    </div>
    <div class="drawer__body glass">
      <div class="preview">
        <slot name="preview" />
      </div>
      <div class="tools">
        <slot />
      </div>
    </div>
  </section>
</template>

<style scoped>
.drawer {
  position: sticky;
  bottom: 0;
  margin-top: 16px;
}

.drawer__handle {
  width: fit-content;
  margin: 0 auto;
  padding: 8px 14px;
  border-radius: 10px 10px 0 0;
  background: rgba(255, 255, 255, 0.06);
  color: #e8efff;
  cursor: pointer;
  border: 1px solid var(--border);
  border-bottom: none;
  font-size: 12px;
  letter-spacing: 0.5px;
}

.drawer__body {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 16px;
  max-height: 0;
  overflow: hidden;
  padding: 0 18px;
  transition: max-height 0.3s ease, padding 0.2s ease;
  background: rgba(14, 16, 24, 0.9);
}

.drawer.open .drawer__body {
  max-height: 540px;
  padding: 18px;
}

.preview {
  min-height: 320px;
}

.tools {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

@media (max-width: 900px) {
  .drawer__body {
    grid-template-columns: 1fr;
  }
}
</style>
