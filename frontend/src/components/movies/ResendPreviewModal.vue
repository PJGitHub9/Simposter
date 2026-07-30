<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getApiBase } from '@/services/apiBase'

const props = defineProps<{
  isOpen: boolean
  ratingKey: string
  title: string
  isTv: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'confirm', includeSeasons: boolean): void
}>()

const apiBase = getApiBase()

const savedImageUrl = computed(() => {
  if (!props.ratingKey) return ''
  return `${apiBase}/api/render-cache/${props.ratingKey}/preview?is_tv=${props.isTv}&v=${cacheBust.value}`
})

const currentImageUrl = computed(() => {
  if (!props.ratingKey) return ''
  const path = props.isTv ? 'tv-show' : 'movie'
  return `${apiBase}/api/${path}/${props.ratingKey}/poster?v=${cacheBust.value}`
})

// Bump on open so re-opening for a different card doesn't show a stale cached image.
const cacheBust = ref(0)
const savedImageError = ref(false)
const currentImageError = ref(false)

watch(() => props.isOpen, (open) => {
  if (open) {
    cacheBust.value = Date.now()
    savedImageError.value = false
    currentImageError.value = false
  }
})

const close = () => emit('close')
const confirm = (includeSeasons: boolean) => emit('confirm', includeSeasons)
</script>

<template>
  <div v-if="isOpen" class="modal-overlay" @click.self="close">
    <div class="modal-content">
      <div class="modal-header">
        <h2>Resend to Plex?</h2>
        <button class="close-btn" @click="close">✕</button>
      </div>

      <div class="modal-body">
        <p class="subtitle">{{ title }}</p>
        <div class="compare-row">
          <div class="compare-col">
            <span class="compare-label">Saved poster</span>
            <div class="compare-frame">
              <img
                v-if="!savedImageError"
                :src="savedImageUrl"
                alt="Saved poster"
                @error="savedImageError = true"
              />
              <div v-else class="compare-fallback">No saved poster found</div>
            </div>
          </div>
          <div class="compare-arrow">→</div>
          <div class="compare-col">
            <span class="compare-label">Current in Plex</span>
            <div class="compare-frame">
              <img
                v-if="!currentImageError"
                :src="currentImageUrl"
                alt="Current Plex poster"
                @error="currentImageError = true"
              />
              <div v-else class="compare-fallback">No current poster found</div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-actions">
        <button class="btn-secondary" @click="close">Cancel</button>
        <button v-if="isTv" class="btn-secondary" @click="confirm(false)">Show only</button>
        <button class="btn-primary" @click="confirm(isTv)">
          {{ isTv ? 'Resend + Seasons' : 'Resend' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--surface, #1a1f2e);
  border-radius: 8px;
  max-width: 560px;
  width: 92%;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--border, #2a2f3e);
}

.modal-header h2 {
  margin: 0;
  color: var(--text-primary, #fff);
  font-size: 1.25rem;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.25rem;
  color: var(--text-secondary, #aaa);
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.08);
}

.modal-body {
  padding: 1.25rem 1.5rem;
}

.subtitle {
  margin: 0 0 1rem 0;
  color: var(--text-secondary, #aaa);
  font-size: 0.9rem;
  font-weight: 600;
}

.compare-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.compare-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.compare-label {
  font-size: 0.75rem;
  color: var(--text-secondary, #aaa);
  text-align: center;
}

.compare-frame {
  aspect-ratio: 2 / 3;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border, #2a2f3e);
  display: flex;
  align-items: center;
  justify-content: center;
}

.compare-frame img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.compare-fallback {
  font-size: 0.75rem;
  color: var(--text-secondary, #aaa);
  text-align: center;
  padding: 0 8px;
}

.compare-arrow {
  font-size: 1.25rem;
  color: var(--text-secondary, #aaa);
  flex-shrink: 0;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 1rem 1.5rem 1.25rem;
  border-top: 1px solid var(--border, #2a2f3e);
}

.btn-primary,
.btn-secondary {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: var(--text-secondary, #c8d4f0);
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.12);
}

.btn-primary {
  background: rgba(91, 141, 238, 0.25);
  border: 1px solid rgba(91, 141, 238, 0.5);
  color: #8ab4f8;
}

.btn-primary:hover {
  background: rgba(91, 141, 238, 0.4);
}

@media (max-width: 600px) {
  .modal-content {
    width: 96%;
  }

  .compare-row {
    gap: 6px;
  }

  .compare-arrow {
    font-size: 1rem;
  }
}
</style>
