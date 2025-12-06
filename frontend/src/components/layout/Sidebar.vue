<script setup lang="ts">
import { computed } from 'vue'
import type { TabKey } from '../../stores/ui'

export type SubMenuItem = {
  key: string
  label: string
}

export type MenuItem = {
  key: TabKey
  label: string
  submenu?: SubMenuItem[]
}

const props = withDefaults(
  defineProps<{
    tabs: MenuItem[]
    active: TabKey
    activeSubmenu?: string
  }>(),
  {
    tabs: () => [],
    active: 'movies',
    activeSubmenu: ''
  }
)

const emit = defineEmits<{
  (e: 'select', tab: TabKey): void
  (e: 'submenuClick', parentKey: TabKey, submenuKey: string): void
}>()

const activeKey = computed(() => props.active)

const handleTabClick = (tab: MenuItem) => {
  // Always navigate to the tab
  emit('select', tab.key)
}

const getIcon = (key: TabKey | string) => {
  const icons: Record<string, string> = {
    movies: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="17" x2="22" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/></svg>`,
    settings: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2.69l1.82 3.69 4.07.59-2.95 2.87.7 4.05L12 11.69l-3.64 1.91.7-4.05L6.11 6.68l4.07-.59L12 2.69z" fill="none"/><path d="M19.4 15c.1-.3.1-.6.1-1s0-.7-.1-1l2.1-1.6c.2-.1.2-.4.1-.6l-2-3.5c-.1-.2-.4-.3-.6-.2l-2.5 1c-.5-.4-1.1-.7-1.7-1l-.4-2.6c0-.2-.2-.4-.5-.4h-4c-.2 0-.5.2-.5.4l-.4 2.6c-.6.2-1.2.6-1.7 1l-2.5-1c-.2-.1-.5 0-.6.2l-2 3.5c-.1.2 0 .5.1.6l2.1 1.6c0 .3-.1.6-.1 1s0 .7.1 1l-2.1 1.6c-.2.1-.2.4-.1.6l2 3.5c.1.2.4.3.6.2l2.5-1c.5.4 1.1.7 1.7 1l.4 2.6c0 .2.2.4.5.4h4c.2 0 .5-.2.5-.4l.4-2.6c.6-.2 1.2-.6 1.7-1l2.5 1c.2.1.5 0 .6-.2l2-3.5c.1-.2 0-.5-.1-.6L19.4 15z"/></svg>`,
    logs: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><line x1="10" y1="10" x2="16" y2="10"/><line x1="10" y1="14" x2="16" y2="14"/></svg>`,
    'batch-edit': `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><path d="M9 14l2 2 4-4"/></svg>`,
    'local-assets': `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>`
  }
  return icons[key] || ''
}
</script>

<template>
  <aside class="sidebar glass">
    <div class="sidebar__title">Simposter</div>
    <nav>
      <div v-for="tab in tabs" :key="tab.key" class="nav-item">
        <button
          :class="['nav-btn', { active: tab.key === activeKey }]"
          @click="handleTabClick(tab)"
        >
          <span class="icon" v-html="getIcon(tab.key)" />
          <span>{{ tab.label }}</span>
        </button>

        <!-- Submenu -->
        <div v-if="tab.submenu && tab.submenu.length > 0 && tab.key === activeKey" class="submenu">
          <button
            v-for="item in tab.submenu"
            :key="item.key"
            :class="['submenu-btn', { active: item.key === props.activeSubmenu }]"
            @click="emit('submenuClick', tab.key, item.key)"
          >
            <span class="submenu-icon" v-html="getIcon(item.key)" />
            <span>{{ item.label }}</span>
          </button>
        </div>
      </div>
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

.nav-item {
  display: flex;
  flex-direction: column;
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
  width: 100%;
  text-align: left;
}

.nav-btn .icon {
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.6;
  transition: all 0.2s;
  flex-shrink: 0;
}

.expand-icon {
  margin-left: auto;
  font-size: 10px;
  opacity: 0.5;
  transition: all 0.2s;
}

.nav-btn.active {
  background: linear-gradient(90deg, rgba(61, 214, 183, 0.15), rgba(91, 141, 238, 0.12));
  border-color: rgba(61, 214, 183, 0.3);
}

.nav-btn.active .icon {
  opacity: 1;
  color: var(--accent);
}

.nav-btn:hover:not(.active) {
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.06);
}

.submenu {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 4px;
  margin-left: 12px;
  padding-left: 12px;
  border-left: 2px solid rgba(61, 214, 183, 0.2);
}

.submenu-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: #c9d6ff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 400;
  transition: all 0.2s;
  width: 100%;
  text-align: left;
}

.submenu-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.5;
  transition: all 0.2s;
  flex-shrink: 0;
}

.submenu-btn.active {
  background: rgba(61, 214, 183, 0.15);
  border-color: rgba(61, 214, 183, 0.4);
  color: var(--accent);
}

.submenu-btn.active .submenu-icon {
  opacity: 1;
  color: var(--accent);
}

.submenu-btn:hover:not(.active) {
  background: rgba(61, 214, 183, 0.08);
  border-color: rgba(61, 214, 183, 0.2);
  color: var(--accent);
}

.submenu-btn:hover:not(.active) .submenu-icon {
  opacity: 1;
  color: var(--accent);
}
</style>
