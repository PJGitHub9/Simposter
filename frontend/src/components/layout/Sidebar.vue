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
  }>(),
  {
    tabs: () => [],
    active: 'movies',
    activeSubmenu: '',
    mobileOpen: false
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

// Icons are now emojis embedded in the label text — no separate SVG icons needed
</script>

<template>
  <aside :class="['sidebar', 'glass', { 'mobile-open': mobileOpen }]">
    <div class="sidebar__title">Simposter</div>
    <nav>
      <div v-for="tab in tabs" :key="tab.key" class="nav-item">
        <button
          :class="['nav-btn', { active: tab.key === activeKey }]"
          @click="handleTabClick(tab)"
        >
          {{ tab.label }}
        </button>

        <!-- Submenu -->
        <div v-if="tab.submenu && tab.submenu.length > 0 && tab.key === activeKey" class="submenu">
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

  .sidebar__title {
    padding: 0 16px 16px;
    font-size: 20px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 8px;
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
