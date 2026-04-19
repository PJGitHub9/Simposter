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
    mobileOpen?: boolean
    collapsed?: boolean
  }>(),
  {
    tabs: () => [],
    active: 'movies',
    activeSubmenu: '',
    mobileOpen: false,
    collapsed: false,
  }
)

const emit = defineEmits<{
  (e: 'select', tab: TabKey): void
  (e: 'submenuClick', parentKey: TabKey, submenuKey: string): void
  (e: 'toggleCollapse'): void
}>()

const activeKey = computed(() => props.active)

const handleTabClick = (tab: MenuItem) => {
  emit('select', tab.key)
}

// Extract the leading emoji character from a label like "🎬 Movies"
const getIcon = (label: string) => {
  // Match emoji at start of string (including multi-codepoint sequences)
  const match = label.match(/^(\p{Emoji_Presentation}|\p{Emoji}\uFE0F|\p{Emoji_Modifier_Base})+/u)
  return match ? match[0] : label.charAt(0)
}

const getTextLabel = (label: string) => label.replace(/^[\p{Emoji_Presentation}\p{Emoji}\uFE0F\s]+/u, '').trim()
</script>

<template>
  <aside :class="['sidebar', 'glass', { 'mobile-open': mobileOpen, 'collapsed': collapsed }]">
    <div class="sidebar__header">
      <span v-if="!collapsed" class="sidebar__title">Simposter</span>
      <button class="collapse-btn" :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'" @click="emit('toggleCollapse')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline v-if="collapsed" points="9 18 15 12 9 6" />
          <polyline v-else points="15 18 9 12 15 6" />
        </svg>
      </button>
    </div>

    <nav>
      <div v-for="tab in tabs" :key="tab.key" class="nav-item">
        <!-- Collapsed: icon button with tooltip -->
        <button
          v-if="collapsed"
          :class="['nav-btn', 'icon-btn', { active: tab.key === activeKey }]"
          :title="getTextLabel(tab.label)"
          @click="handleTabClick(tab)"
        >
          <span class="nav-icon">{{ getIcon(tab.label) }}</span>
        </button>

        <!-- Expanded: full label button -->
        <button
          v-else
          :class="['nav-btn', { active: tab.key === activeKey }]"
          @click="handleTabClick(tab)"
        >
          {{ tab.label }}
        </button>

        <!-- Submenu — only shown when expanded -->
        <div v-if="!collapsed && tab.submenu && tab.submenu.length > 0 && tab.key === activeKey" class="submenu">
          <button
            v-for="item in tab.submenu"
            :key="item.key"
            :class="['submenu-btn', { active: item.key === props.activeSubmenu }]"
            @click="emit('submenuClick', tab.key, item.key)"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
    </nav>

  </aside>
</template>

<style scoped>
.sidebar {
  width: 100%;
  padding: 20px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: rgba(17, 20, 30, 0.9);
  border-right: 1px solid var(--border);
  height: 100%;
  overflow: hidden;
  transition: padding 0.2s ease;
}

.sidebar.collapsed {
  padding: 20px 6px 12px;
  align-items: center;
}

.sidebar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  min-height: 32px;
}

.sidebar.collapsed .sidebar__header {
  justify-content: center;
}

.sidebar__title {
  font-weight: 700;
  letter-spacing: 0.4px;
  color: var(--accent);
  padding: 0 4px;
  white-space: nowrap;
  overflow: hidden;
}

nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  flex: 1;
  min-height: 0;
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
  white-space: nowrap;
}

.nav-btn.icon-btn {
  justify-content: center;
  padding: 10px;
  width: 40px;
  height: 40px;
}

.nav-icon {
  font-size: 18px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.nav-btn.active {
  background: linear-gradient(90deg, rgba(61, 214, 183, 0.15), rgba(91, 141, 238, 0.12));
  border-color: rgba(61, 214, 183, 0.3);
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

.submenu-btn.active {
  background: rgba(61, 214, 183, 0.15);
  border-color: rgba(61, 214, 183, 0.4);
  color: var(--accent);
}

.submenu-btn:hover:not(.active) {
  background: rgba(61, 214, 183, 0.08);
  border-color: rgba(61, 214, 183, 0.2);
  color: var(--accent);
}

/* Collapse toggle button */
.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: transparent;
  color: rgba(255, 255, 255, 0.35);
  cursor: pointer;
  transition: color 0.2s, background 0.2s, border-color 0.2s;
}

.collapse-btn:hover {
  color: var(--accent);
  background: rgba(61, 214, 183, 0.08);
  border-color: rgba(61, 214, 183, 0.2);
}

/* Mobile responsive styles */
@media (max-width: 900px) {
  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    width: 280px;
    max-width: 85vw;
    z-index: 100;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    padding-top: 16px;
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.4);
    overflow-y: auto;
  }

  .sidebar.mobile-open {
    transform: translateX(0);
  }

  /* Hide collapse toggle on mobile — sidebar is already overlay */
  .collapse-btn {
    display: none;
  }

  .sidebar__header {
    padding: 0 16px 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 8px;
  }

  .sidebar__title {
    font-size: 20px;
  }

  nav {
    padding: 0 8px;
  }

  .nav-btn {
    padding: 14px 16px;
    font-size: 15px;
  }

  .submenu {
    margin-left: 16px;
    padding-left: 16px;
  }

  .submenu-btn {
    padding: 12px 14px;
    font-size: 14px;
  }
}

@media (max-width: 600px) {
  .sidebar {
    width: 260px;
    padding: 12px 8px;
  }

  .sidebar__title {
    font-size: 18px;
    padding: 0 12px 12px;
  }

  .nav-btn {
    padding: 12px 14px;
    font-size: 14px;
    border-radius: 8px;
  }

  .submenu-btn {
    padding: 10px 12px;
    font-size: 13px;
  }
}
</style>
