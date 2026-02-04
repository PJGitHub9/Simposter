<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { APP_VERSION } from '../version'
import { releaseNotes, type ReleaseNote } from '../releaseNotes'

const STORAGE_KEY = 'simposter-last-seen-version'

const visible = ref(false)
const currentNote = ref<ReleaseNote | null>(null)

onMounted(() => {
  const lastSeen = localStorage.getItem(STORAGE_KEY)
  if (lastSeen === APP_VERSION) return

  // Find release notes for the current version
  const note = releaseNotes.find(n => n.version === APP_VERSION)
  if (!note) return

  currentNote.value = note
  visible.value = true
})

function dismiss() {
  localStorage.setItem(STORAGE_KEY, APP_VERSION)
  visible.value = false
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible && currentNote" class="announcement-overlay" @click.self="dismiss">
      <div class="announcement-modal glass">
        <div class="announcement-header">
          <h2>What's New in {{ currentNote.version }}</h2>
          <button class="close-btn" @click="dismiss">&times;</button>
        </div>
        <div class="announcement-body">
          <p class="release-date">{{ currentNote.date }}</p>
          <div v-for="section in currentNote.sections" :key="section.title" class="release-section">
            <h3>{{ section.title }}</h3>
            <ul>
              <li v-for="item in section.items" :key="item">{{ item }}</li>
            </ul>
          </div>
        </div>
        <div class="announcement-footer">
          <button class="btn-dismiss" @click="dismiss">Got it</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.announcement-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  animation: fadeIn 0.2s ease;
}

.announcement-modal {
  width: 90%;
  max-width: 520px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  animation: modalIn 0.25s ease;
}

.announcement-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 12px;
  border-bottom: 1px solid var(--border);
}

.announcement-header h2 {
  margin: 0;
  font-size: 18px;
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

.announcement-body {
  padding: 16px 24px;
  overflow-y: auto;
  flex: 1;
}

.release-date {
  margin: 0 0 16px;
  font-size: 13px;
  color: #8892b0;
}

.release-section {
  margin-bottom: 16px;
}

.release-section:last-child {
  margin-bottom: 0;
}

.release-section h3 {
  margin: 0 0 8px;
  font-size: 14px;
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
  margin-bottom: 6px;
  font-size: 14px;
  color: #c9d1e3;
  line-height: 1.5;
}

.release-section li:last-child {
  margin-bottom: 0;
}

.announcement-footer {
  padding: 12px 24px 20px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid var(--border);
}

.btn-dismiss {
  background: linear-gradient(120deg, var(--accent), var(--accent-2));
  color: #fff;
  border: none;
  padding: 10px 28px;
  border-radius: 10px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  box-shadow: 0 4px 14px rgba(61, 214, 183, 0.15);
}

.btn-dismiss:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(61, 214, 183, 0.25);
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
</style>
