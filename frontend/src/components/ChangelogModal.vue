<script setup lang="ts">
import { computed } from 'vue'
import { releaseNotes } from '../releaseNotes'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

// Show last 10 releases
const displayedNotes = computed(() => releaseNotes.slice(0, 10))
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="changelog-overlay" @click.self="emit('close')">
      <div class="changelog-modal glass">
        <div class="changelog-header">
          <h2>Changelog</h2>
          <button class="close-btn" @click="emit('close')">&times;</button>
        </div>
        <div class="changelog-body">
          <div v-for="note in displayedNotes" :key="note.version" class="version-block">
            <div class="version-header">
              <span class="version-badge">{{ note.version }}</span>
              <span class="release-date">{{ note.date }}</span>
            </div>
            <div v-for="section in note.sections" :key="section.title" class="release-section">
              <h3>{{ section.title }}</h3>
              <ul>
                <li v-for="item in section.items" :key="item">{{ item }}</li>
              </ul>
            </div>
          </div>
        </div>
        <div class="changelog-footer">
          <button class="btn-close" @click="emit('close')">Close</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.changelog-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  animation: fadeIn 0.2s ease;
}

.changelog-modal {
  width: 90%;
  max-width: 560px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  animation: modalIn 0.25s ease;
}

.changelog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 12px;
  border-bottom: 1px solid var(--border);
}

.changelog-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--accent);
}

.close-btn {
  background: none;
  border: none;
  color: #8892b0;
  font-size: 22px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
  transition: color 0.2s ease;
}

.close-btn:hover {
  color: #fff;
}

.changelog-body {
  padding: 16px 24px;
  overflow-y: auto;
  flex: 1;
}

.version-block {
  margin-bottom: 24px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}

.version-block:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.version-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.version-badge {
  background: linear-gradient(120deg, var(--accent), var(--accent-2));
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 6px;
  letter-spacing: 0.3px;
}

.release-date {
  font-size: 13px;
  color: #8892b0;
}

.release-section {
  margin-bottom: 14px;
}

.release-section:last-child {
  margin-bottom: 0;
}

.release-section h3 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-2);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.release-section ul {
  margin: 0;
  padding-left: 20px;
  list-style: disc;
}

.release-section li {
  margin-bottom: 5px;
  font-size: 13px;
  color: #c9d1e3;
  line-height: 1.5;
}

.release-section li:last-child {
  margin-bottom: 0;
}

.changelog-footer {
  padding: 12px 24px 20px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid var(--border);
}

.btn-close {
  background: rgba(255, 255, 255, 0.08);
  color: #c9d1e3;
  border: 1px solid var(--border);
  padding: 10px 28px;
  border-radius: 10px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-close:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.2);
  color: #fff;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes modalIn {
  from {
    opacity: 0;
    transform: scale(0.95) translateY(8px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

/* Mobile responsive */
@media (max-width: 600px) {
  .changelog-modal {
    width: 95%;
    max-height: 90vh;
  }

  .changelog-header {
    padding: 16px 16px 10px;
  }

  .changelog-header h2 {
    font-size: 18px;
  }

  .changelog-body {
    padding: 12px 16px;
  }

  .version-block {
    margin-bottom: 18px;
    padding-bottom: 14px;
  }

  .release-section h3 {
    font-size: 12px;
  }

  .release-section li {
    font-size: 12px;
  }

  .changelog-footer {
    padding: 10px 16px 16px;
  }

  .btn-close {
    padding: 8px 20px;
    font-size: 13px;
  }
}

/* Light theme overrides */
:root[data-theme='light'] .release-section li {
  color: #4a5568;
}

:root[data-theme='light'] .close-btn:hover {
  color: #1a202c;
}

:root[data-theme='light'] .release-date {
  color: #718096;
}

:root[data-theme='light'] .btn-close {
  color: #4a5568;
}

:root[data-theme='light'] .btn-close:hover {
  color: #1a202c;
}
</style>
