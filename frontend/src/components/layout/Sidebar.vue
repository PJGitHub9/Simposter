<script setup lang="ts">
 

import { computed } from 'vue'
import type { TabKey } from '../../stores/ui'

const props = withDefaults(
  defineProps<{
    tabs: { key: TabKey; label: string }[]
    active: TabKey
  }>(),
  {
    tabs: () => [],
    active: 'movies'
  }
)

const emit = defineEmits<{
  (e: 'select', tab: TabKey): void
}>()

const activeKey = computed(() => props.active)
</script>

<template>
  <aside class="sidebar glass">
    <div class="sidebar__title">Simposter</div>
    <nav>
      <button
        v-for="tab in tabs"
        :key="tab.key"
        :class="['nav-btn', { active: tab.key === activeKey }]"
        @click="emit('select', tab.key)"
      >
        <span class="dot" />
        <span>{{ tab.label }}</span>
      </button>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 100%;
  padding: 20px 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: rgba(17, 20, 30, 0.9);
  border-right: 1px solid var(--border);
  height: 100%;
}

.sidebar__title {
  font-weight: 700;
  letter-spacing: 0.4px;
  color: var(--accent);
  padding: 0 8px;
}

nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: transparent;
  color: #dbe6ff;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition:
    background 0.2s,
    border-color 0.2s,
    transform 0.15s;
}

.nav-btn .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  transition: all 0.2s;
}

.nav-btn.active {
  background: linear-gradient(90deg, rgba(61, 214, 183, 0.15), rgba(91, 141, 238, 0.12));
  border-color: rgba(61, 214, 183, 0.3);
}

.nav-btn.active .dot {
  background: var(--accent);
  box-shadow: 0 0 0 4px rgba(61, 214, 183, 0.2);
  transform: scale(1.2);
}

.nav-btn:hover:not(.active) {
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.06);
}
</style>
