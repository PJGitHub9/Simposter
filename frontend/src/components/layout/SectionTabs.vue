<script setup lang="ts">
// Tab strip shown above a library's Artwork pages (Logos, Backdrops, Square Art,
// Thumb Art) and Tools pages (Overlay Refresh, Media Mirror, Local Assets,
// Backup / Restore). The sidebar has one entry for each group; these tabs switch
// between the pages inside it. Each page keeps its own route, so old links work.
import type { RouteLocationRaw } from 'vue-router'

export interface SectionTab {
  key: string
  label: string
  to: RouteLocationRaw
  active: boolean
}

defineProps<{ title: string; tabs: SectionTab[] }>()
</script>

<template>
  <nav class="section-tabs" :aria-label="title">
    <span class="section-title">{{ title }}</span>
    <div class="tab-row">
      <router-link
        v-for="t in tabs"
        :key="t.key"
        :to="t.to"
        :class="['section-tab', { active: t.active }]"
        :aria-current="t.active ? 'page' : undefined"
      >
        {{ t.label }}
      </router-link>
    </div>
  </nav>
</template>

<style scoped>
.section-tabs {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 14px 20px 0;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.08));
}
.section-title {
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--text-secondary, #9aa4b2);
  padding-bottom: 10px;
}
.tab-row {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  min-width: 0;
}
.section-tab {
  padding: 8px 14px 10px;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary, #9aa4b2);
  text-decoration: none;
  font-size: 0.9rem;
  white-space: nowrap;
}
.section-tab:hover {
  color: var(--text-primary, #e6e9ef);
}
.section-tab.active {
  color: var(--accent, #3dd6b7);
  border-bottom-color: var(--accent, #3dd6b7);
  font-weight: 600;
}
@media (max-width: 600px) {
  .section-tabs { padding: 10px 12px 0; gap: 6px; }
  .section-title { display: none; }
  .tab-row { flex-wrap: nowrap; overflow-x: auto; width: 100%; }
}
</style>
