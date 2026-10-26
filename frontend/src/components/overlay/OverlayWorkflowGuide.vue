<script setup lang="ts">
// "How overlays work" at the top of the Overlay Manager: the four steps from
// building an overlay to keeping sent posters up to date. Can be hidden; the
// choice is remembered in this browser.
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
        <div>
          <strong>Make an overlay</strong>
          <p>
            An overlay is a set of layers (badges, images, text) with rules for which posters get each one, like
            "4K badge only on 4K movies". Build one with <em>New overlay</em>, bring in Kometa files with
            <em>Import Kometa</em>, or add a <button type="button" class="btn-link" @click="emit('openAdvanced')">live Kometa file</button>
            that re-imports itself when another tool (like UMTK) rewrites it.
          </p>
        </div>
      </li>
      <li>
        <span class="num">2</span>
        <div>
          <strong>Turn it on in a preset</strong>
          <p>
            An overlay does nothing until a preset uses it. Open any poster in the editor, tick the overlay under
            Extras → Overlays, then click Save Preset. Batch Edit, webhooks and auto-generate then use it for every
            poster made with that preset (pick the preset per library in Settings → Libraries, or in the webhook link).
            Without saving, the ticks only apply to the poster you're editing.
          </p>
        </div>
      </li>
      <li>
        <span class="num">3</span>
        <div>
          <strong>Send posters</strong>
          <p>
            Every way of sending a poster (editor, Batch Edit, webhooks, auto-generate) draws the overlay as it is right
            then. Simposter remembers each poster it sent with an overlay, so it can update it later.
          </p>
        </div>
      </li>
      <li>
        <span class="num">4</span>
        <div>
          <strong>Keep them up to date</strong>
          <p>
            Some things an overlay shows change on their own: ratings, list membership, labels. Two schedules handle that:
          </p>
          <ul>
            <li>
              <button type="button" class="btn-link" @click="emit('openScheduler')">Scheduler</button> (below): how often
              ratings and lists are fetched again. These are the only steps that call outside services (MDBList, WeTrakr,
              SIMKL, Floppy).
            </li>
            <li>
              <strong>Overlay Refresh</strong> (🔁 in each library's menu): on its own schedule, re-checks the posters
              Simposter sent and re-sends only the ones whose overlay would now look different (a new rating, joining or
              leaving a list, a label change, or an edit to the overlay itself). It uses the stored ratings and lists,
              fetching any that are due first.
            </li>
          </ul>
          <p class="aside">
            File name, quality and edition don't need a schedule: a library scan or webhook picks up those changes, and
            the next Overlay Refresh redraws the badge.
          </p>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.guide {
  background: var(--surface, #1a1f2e); border: 1px solid var(--border, #2a2f3e); border-radius: 12px;
  padding: 1rem 1.25rem; margin-bottom: 1.5rem;
}
.guide-head { display: flex; justify-content: space-between; align-items: center; }
.guide-head h2 { margin: 0; font-size: 1.05rem; font-weight: 600; color: var(--text-primary, #fff); }
.steps { list-style: none; margin: 0.9rem 0 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; }
.steps > li { display: flex; gap: 0.7rem; align-items: flex-start; }
.num {
  flex-shrink: 0; width: 1.6rem; height: 1.6rem; border-radius: 50%; display: inline-flex; align-items: center;
  justify-content: center; font-size: 0.8rem; font-weight: 700; background: rgba(61, 214, 183, 0.15);
  color: var(--accent, #3dd6b7);
}
strong { color: var(--text-primary, #fff); font-size: 0.88rem; }
p, ul { margin: 0.3rem 0 0; font-size: 0.8rem; line-height: 1.45; color: var(--text-secondary, #9aa4b2); }
ul { padding-left: 1rem; display: flex; flex-direction: column; gap: 0.3rem; }
ul strong { font-size: 0.8rem; }
.aside { font-size: 0.74rem; }
a { color: var(--accent, #3dd6b7); }
.btn-link { padding: 0; background: none; border: none; color: var(--accent, #3dd6b7); cursor: pointer; font-size: inherit; text-decoration: underline; }
</style>
