<script setup lang="ts">
// "How overlays work" at the top of the Overlay Manager: the four steps from
// building an overlay to keeping sent posters up to date, one line each.
// Can be hidden; the choice is remembered in this browser.
import { ref } from 'vue'

const KEY = 'simposter-overlay-guide-hidden'
const readHidden = () => {
  try { return localStorage.getItem(KEY) === '1' } catch { return false }
}
const hidden = ref(readHidden())
const toggle = () => {
  hidden.value = !hidden.value
  try { localStorage.setItem(KEY, hidden.value ? '1' : '0') } catch { /* private window */ }
}

const emit = defineEmits<{ openScheduler: []; openAdvanced: [] }>()
</script>

<template>
  <div class="guide">
    <div class="guide-head">
      <h2>How overlays work</h2>
      <button type="button" class="btn-link" @click="toggle">{{ hidden ? 'Show' : 'Hide' }}</button>
    </div>
    <ol v-if="!hidden" class="steps">
      <li>
        <span class="num">1</span>
        <p><strong>Make an overlay:</strong> layers (badges, images, text) with rules for which posters get them. Start new, import Kometa files, or add a
          <button type="button" class="btn-link" @click="emit('openAdvanced')">live Kometa file</button>.</p>
      </li>
      <li>
        <span class="num">2</span>
        <p><strong>Add it to a preset:</strong> in the poster editor, tick it under Extras → Overlays and Save Preset. Batch Edit, webhooks and auto-generate then use it.</p>
      </li>
      <li>
        <span class="num">3</span>
        <p><strong>Send posters:</strong> the overlay is drawn as things are at that moment, and Simposter remembers which posters have it.</p>
      </li>
      <li>
        <span class="num">4</span>
        <p><strong>Keep them current:</strong> Overlay Refresh (each library's Tools page) re-sends posters whose overlay would now look different. The
          <button type="button" class="btn-link" @click="emit('openScheduler')">Scheduler</button> sets how often ratings and lists are re-checked.</p>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.guide {
  background: var(--surface, #1a1f2e); border: 1px solid var(--border, #2a2f3e); border-radius: 12px;
  padding: 0.75rem 1.1rem; margin-bottom: 1.25rem;
}
.guide-head { display: flex; justify-content: space-between; align-items: center; }
.guide-head h2 { margin: 0; font-size: 0.98rem; font-weight: 600; color: var(--text-primary, #fff); }
.steps { list-style: none; margin: 0.6rem 0 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.5rem 1.25rem; }
.steps > li { display: flex; gap: 0.55rem; align-items: flex-start; }
.num {
  flex-shrink: 0; width: 1.35rem; height: 1.35rem; border-radius: 50%; display: inline-flex; align-items: center;
  justify-content: center; font-size: 0.72rem; font-weight: 700; background: rgba(61, 214, 183, 0.15);
  color: var(--accent, #3dd6b7);
}
p { margin: 0; font-size: 0.78rem; line-height: 1.4; color: var(--text-secondary, #9aa4b2); }
strong { color: var(--text-primary, #fff); font-weight: 600; }
.btn-link { padding: 0; background: none; border: none; color: var(--accent, #3dd6b7); cursor: pointer; font-size: inherit; text-decoration: underline; }
</style>
