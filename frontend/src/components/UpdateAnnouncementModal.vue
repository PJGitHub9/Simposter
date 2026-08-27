<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { APP_VERSION } from '../version'
import { releaseNotes, type ReleaseNote } from '../releaseNotes'
import { majorReleases, type MajorRelease } from '../majorReleases'

const STORAGE_KEY = 'simposter-last-seen-version'

const emit = defineEmits<{
  (e: 'view-full-changelog'): void
}>()

const visible = ref(false)
const missedNotes = ref<ReleaseNote[]>([])
const activeMajorRelease = ref<MajorRelease | null>(null)

// Compares two 'vX.Y.Z'-style version strings. Returns <0 if a<b, 0 if equal, >0 if a>b.
function compareVersions(a: string, b: string): number {
  const parts = (v: string) => v.replace(/^v/i, '').split('.').map((n) => parseInt(n, 10) || 0)
  const [pa, pb] = [parts(a), parts(b)]
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const diff = (pa[i] || 0) - (pb[i] || 0)
    if (diff !== 0) return diff
  }
  return 0
}

onMounted(() => {
  const lastSeen = localStorage.getItem(STORAGE_KEY)
  if (lastSeen === APP_VERSION) return

  // A returning user (has a lastSeen) whose last visit predates a curated major-
  // release milestone gets that highlight reel instead of the granular per-version
  // dump below — crossing dozens of versions at once is exactly what majorReleases.ts
  // exists for. Fresh installs (no lastSeen) skip this — onboarding already covers
  // the intro for them, they don't need a "look what you missed" tour of the past.
  if (lastSeen) {
    const crossed = majorReleases.find(
      (m) => compareVersions(APP_VERSION, m.version) >= 0 && compareVersions(lastSeen, m.version) < 0
    )
    if (crossed) {
      activeMajorRelease.value = crossed
      visible.value = true
      return
    }
  }

  // Collect all release notes newer than the last seen version.
  // releaseNotes is ordered newest-first. If no lastSeen, only show the current version.
  const notes: ReleaseNote[] = []
  for (const note of releaseNotes) {
    if (note.version === lastSeen) break
    notes.push(note)
  }

  // If user has never seen any version, just show the latest
  if (!lastSeen && notes.length > 1) {
    notes.length = 1
  }

  if (notes.length === 0) return

  missedNotes.value = notes
  visible.value = true
})

function dismiss() {
  localStorage.setItem(STORAGE_KEY, APP_VERSION)
  visible.value = false
}

function viewFullChangelog() {
  dismiss()
  emit('view-full-changelog')
}
</script>

<template>
  <Teleport to="body">
    <!-- Major-release highlight reel -->
    <div v-if="visible && activeMajorRelease" class="announcement-overlay" @click.self="dismiss">
      <div class="announcement-modal major glass">
        <div class="announcement-header major-header">
          <div>
            <span class="major-eyebrow">Major Update</span>
            <h2>{{ activeMajorRelease.title }}</h2>
          </div>
          <button class="close-btn" @click="dismiss">&times;</button>
        </div>
        <div class="announcement-body">
          <p class="major-intro">{{ activeMajorRelease.intro }}</p>
          <div class="highlight-grid">
            <div v-for="h in activeMajorRelease.highlights" :key="h.title" class="highlight-card">
              <div class="highlight-icon">{{ h.icon }}</div>
              <div class="highlight-title">{{ h.title }}</div>
              <div class="highlight-desc">{{ h.description }}</div>
            </div>
          </div>
        </div>
        <div class="announcement-footer">
          <button class="btn-link" @click="viewFullChangelog">View full changelog</button>
          <button class="btn-dismiss" @click="dismiss">Got it</button>
        </div>
      </div>
    </div>

    <!-- Regular per-version "what's new" -->
    <div v-else-if="visible && missedNotes.length" class="announcement-overlay" @click.self="dismiss">
      <div class="announcement-modal glass">
        <div class="announcement-header">
          <h2 v-if="missedNotes.length === 1">What's New in {{ missedNotes[0]!.version }}</h2>
          <h2 v-else>What's New</h2>
          <button class="close-btn" @click="dismiss">&times;</button>
        </div>
        <div class="announcement-body">
          <div v-for="note in missedNotes" :key="note.version" class="version-block">
            <div v-if="missedNotes.length > 1" class="version-header">
              <span class="version-badge">{{ note.version }}</span>
              <span class="release-date">{{ note.date }}</span>
            </div>
            <p v-else class="release-date">{{ note.date }}</p>
            <div v-for="section in note.sections" :key="section.title" class="release-section">
              <h3>{{ section.title }}</h3>
              <ul>
                <li v-for="item in section.items" :key="item">{{ item }}</li>
              </ul>
            </div>
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

.version-block {
  margin-bottom: 20px;
  padding-bottom: 16px;
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
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  border-top: 1px solid var(--border);
}

.btn-link {
  background: none;
  border: none;
  color: #8892b0;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  padding: 8px 4px;
  margin-right: auto;
  transition: color 0.15s ease;
}

.btn-link:hover {
  color: var(--accent-2);
  text-decoration: underline;
}

/* ── Major release highlight reel ───────────────────────────────────────── */

.announcement-modal.major {
  max-width: 720px;
}

.major-header {
  align-items: flex-start;
}

.major-eyebrow {
  display: block;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--accent-2);
  margin-bottom: 4px;
}

.major-header h2 {
  font-size: 22px;
}

.major-intro {
  margin: 0 0 20px;
  font-size: 14px;
  line-height: 1.6;
  color: #c9d1e3;
}

.highlight-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}

@media (max-width: 640px) {
  .highlight-grid {
    grid-template-columns: 1fr;
  }
}

.highlight-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
}

.highlight-icon {
  font-size: 24px;
  margin-bottom: 8px;
}

.highlight-title {
  font-size: 14px;
  font-weight: 700;
  color: #eef2ff;
  margin-bottom: 6px;
}

.highlight-desc {
  font-size: 13px;
  line-height: 1.5;
  color: #a9b2c8;
}

:root[data-theme='light'] .major-intro {
  color: #4a5568;
}

:root[data-theme='light'] .highlight-desc {
  color: #718096;
}

:root[data-theme='light'] .btn-link {
  color: #718096;
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
