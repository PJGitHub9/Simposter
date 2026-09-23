<script setup lang="ts">
export type SearchEditChoice = 'poster' | 'logo' | 'backdrop' | 'square-art'

const props = defineProps<{
  item: { title: string; year?: number | string }
}>()

const emit = defineEmits<{
  close: []
  choose: [choice: SearchEditChoice]
}>()
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @click.self="emit('close')">
      <div class="modal glass">
        <p class="label">What do you want to edit?</p>
        <h3>{{ item.title }}<span v-if="item.year" class="year"> ({{ item.year }})</span></h3>
        <div class="choice-list">
          <button class="choice-item" @click="emit('choose', 'poster')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
            <div>
              <p class="name">Poster</p>
              <p class="desc">The main poster — background, logo, and text overlay.</p>
            </div>
          </button>
          <button class="choice-item" @click="emit('choose', 'logo')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9l4-4 4 4 4-4 4 4" /><circle cx="8.5" cy="14.5" r="1.5" />
            </svg>
            <div>
              <p class="name">Logo</p>
              <p class="desc">The clearlogo Plex shows for this item.</p>
            </div>
          </button>
          <button class="choice-item" @click="emit('choose', 'backdrop')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9l4-4 4 4 4-4 4 4" /><circle cx="8.5" cy="14.5" r="1.5" />
            </svg>
            <div>
              <p class="name">Backdrop</p>
              <p class="desc">The background art behind the item's details page.</p>
            </div>
          </button>
          <button class="choice-item" @click="emit('choose', 'square-art')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
            </svg>
            <div>
              <p class="name">Square Art</p>
              <p class="desc">Square (1:1) art — for clients that use it, e.g. Plexamp-style grids.</p>
            </div>
          </button>
        </div>
        <button class="cancel" @click="emit('close')">Cancel</button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2100;
  padding: 20px;
}

.modal {
  width: min(440px, 90vw);
  padding: 20px;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: rgba(17, 20, 30, 0.98);
  border: 1px solid var(--border);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6);
}

.label {
  text-transform: uppercase;
  font-size: 12px;
  color: var(--muted);
  letter-spacing: 1px;
  margin: 0;
}

.modal h3 {
  margin: 0;
  font-size: 16px;
  color: #eef2ff;
}

.year {
  color: var(--muted);
  font-weight: 400;
}

.choice-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.choice-item {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  color: inherit;
  transition: background 0.15s, border-color 0.15s;
}

.choice-item svg {
  flex-shrink: 0;
  color: var(--muted);
  opacity: 0.7;
}

.choice-item:hover {
  background: rgba(61, 214, 183, 0.1);
  border-color: rgba(61, 214, 183, 0.35);
}

.choice-item .name {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #eef2ff;
}

.choice-item .desc {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.cancel {
  align-self: flex-end;
  border: none;
  background: none;
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
  padding: 6px 10px;
}

.cancel:hover {
  color: #eef2ff;
}
</style>
