<script setup lang="ts">
const emit = defineEmits<{ (e: 'done'): void }>()

const FEATURES = [
  {
    icon: '🎬',
    name: 'Movie & TV Libraries',
    desc: 'Your poster grid. Click any title to open the editor — pick artwork, adjust the logo, and send it to Plex.',
    nav: 'Movies / TV Shows',
  },
  {
    icon: '✏️',
    name: 'Batch Edit',
    desc: 'Generate posters for your entire library at once using a single preset. Great for a fresh start.',
    nav: 'Batch Edit',
  },
  {
    icon: '🎨',
    name: 'Template Manager',
    desc: 'Create and customize presets — logo position, poster effects, text overlays, and fallback behaviour.',
    nav: 'Template Manager',
  },
  {
    icon: '📐',
    name: 'Overlay Manager',
    desc: 'Add metadata badges on top of posters: resolution, codec, audio format, edition, and more.',
    nav: 'Overlay Manager',
  },
  {
    icon: '🗂️',
    name: 'Local Assets',
    desc: 'Browse every poster Simposter has saved to disk. Re-send any saved poster to Plex any time.',
    nav: 'Local Assets',
  },
  {
    icon: '💾',
    name: 'Backup & Restore',
    desc: 'Export your presets and settings to a JSON file so you can restore or share them easily.',
    nav: 'Settings → Backup',
  },
] as const
</script>

<template>
  <Teleport to="body">
    <div class="qs-backdrop">
      <div class="qs-modal">
        <div class="qs-header">
          <div class="qs-icon">🗺️</div>
          <div>
            <h2 class="qs-title">Quick start guide</h2>
            <p class="qs-sub">Here's a quick overview of what Simposter can do.</p>
          </div>
        </div>

        <div class="qs-grid">
          <div v-for="f in FEATURES" :key="f.name" class="qs-card">
            <div class="qs-card-icon">{{ f.icon }}</div>
            <div class="qs-card-name">{{ f.name }}</div>
            <div class="qs-card-desc">{{ f.desc }}</div>
            <div class="qs-card-nav">{{ f.nav }}</div>
          </div>
        </div>

        <div class="qs-actions">
          <button class="qs-btn-primary" @click="emit('done')">Let's go!</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.qs-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9000;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.qs-modal {
  background: #12141f;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  padding: 28px 28px 22px;
  width: 100%;
  max-width: 580px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.6);
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.qs-header {
  display: flex;
  align-items: center;
  gap: 14px;
}

.qs-icon { font-size: 32px; flex-shrink: 0; }
.qs-title { margin: 0 0 2px; font-size: 20px; font-weight: 700; color: #eef2ff; }
.qs-sub { margin: 0; font-size: 13px; color: #8892aa; }

.qs-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.qs-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  transition: border-color 0.15s, background 0.15s;
}
.qs-card:hover {
  border-color: rgba(61, 214, 183, 0.25);
  background: rgba(61, 214, 183, 0.04);
}

.qs-card-icon { font-size: 22px; line-height: 1; }
.qs-card-name { font-size: 13px; font-weight: 700; color: #eef2ff; }
.qs-card-desc { font-size: 12px; color: #8892aa; line-height: 1.45; flex: 1; }
.qs-card-nav {
  font-size: 11px; font-weight: 600;
  color: var(--accent, #3dd6b7);
  margin-top: 4px;
}

.qs-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 4px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.qs-btn-primary {
  padding: 9px 28px;
  background: var(--accent, #3dd6b7);
  color: #0b0d14;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.15s;
}
.qs-btn-primary:hover { opacity: 0.88; }

@media (max-width: 480px) {
  .qs-grid { grid-template-columns: 1fr; }
  .qs-modal { padding: 20px 16px 18px; }
}
</style>
