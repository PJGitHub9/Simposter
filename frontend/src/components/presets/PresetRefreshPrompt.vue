<script setup lang="ts">
// Shown after a preset's overlays changed (Template Manager or an editor's
// Save Preset). Refreshing points the tracked posters at the preset's new
// overlays and runs a normal refresh: only posters that now look different are
// re-rendered and re-sent (backend/api/overlay_refresh.py /run-preset).
import { computed, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'
import type { PresetPromptState } from '@/composables/usePresetRefreshPrompt'

const props = defineProps<{ state: PresetPromptState }>()
const emit = defineEmits<{ close: [] }>()

const selected = ref<Set<string>>(new Set(props.state.groups.filter(g => !g.running).map(g => g.group_id)))
const includeDifferent = ref(false)
const busy = ref(false)
const result = ref<{ started: string[]; busy: string[] } | null>(null)
const error = ref('')

const differentCount = computed(() =>
  props.state.groups.filter(g => selected.value.has(g.group_id)).reduce((n, g) => n + g.different.items.length, 0),
)
const canRun = computed(() =>
  props.state.groups.some(g => selected.value.has(g.group_id) && (g.matching.keys.length || (includeDifferent.value && g.different.keys.length))),
)

function toggle(id: string) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

async function refreshNow() {
  busy.value = true
  error.value = ''
  try {
    const res = await fetch(`${getApiBase()}/api/overlay-refresh/run-preset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        template_id: props.state.templateId,
        preset_id: props.state.presetId,
        old: props.state.old,
        include_different: includeDifferent.value,
        group_ids: [...selected.value],
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    result.value = await res.json()
  } catch (e) {
    error.value = `Couldn't start the refresh: ${e instanceof Error ? e.message : e}`
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="prp-backdrop" @click.self="emit('close')">
      <div class="prp-modal">
        <div class="prp-head">
          <h3>Refresh posters made with "{{ state.presetName }}"?</h3>
          <button class="prp-x" title="Close" @click="emit('close')">✕</button>
        </div>

        <div v-if="result" class="prp-body">
          <p v-if="result.started.length">
            Refresh started for {{ result.started.join(', ') }}. Follow it on that library's Overlay Refresh page.
          </p>
          <p v-if="result.busy.length" class="warn">
            Already running, skipped: {{ result.busy.join(', ') }}. Run it again from Overlay Refresh once it finishes.
          </p>
          <div class="prp-foot"><button class="btn primary" @click="emit('close')">Done</button></div>
        </div>

        <div v-else class="prp-body">
          <p class="hint">
            This preset's overlays changed. {{ state.total_matching }} poster(s) sent with it still have its old
            overlays. Refreshing gives them the new ones and only re-sends the posters that end up looking different.
          </p>
          <div v-for="g in state.groups" :key="g.group_id" class="prp-group">
            <label class="prp-group-head">
              <input type="checkbox" :checked="selected.has(g.group_id)" :disabled="g.running" @change="toggle(g.group_id)" />
              <strong>{{ g.group_name }}</strong>
              <span class="count">{{ g.matching.items.length }}</span>
              <span v-if="g.running" class="warn">(a refresh is already running)</span>
            </label>
            <ul v-if="g.matching.items.length" class="prp-items">
              <li v-for="item in g.matching.items" :key="item.title">
                {{ item.title }} <span class="servers">{{ item.servers.join(', ') }}</span>
              </li>
            </ul>
          </div>
          <label v-if="state.total_different > 0" class="prp-different">
            <input v-model="includeDifferent" type="checkbox" />
            Also refresh {{ differentCount }} posters sent with this preset that currently have different overlays
          </label>
          <p v-if="error" class="warn">{{ error }}</p>
          <div class="prp-foot">
            <button class="btn" @click="emit('close')">Not now</button>
            <button class="btn primary" :disabled="busy || !canRun" @click="refreshNow">
              {{ busy ? 'Starting...' : 'Refresh posters' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.prp-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: 1100; padding: 16px; }
.prp-modal { width: min(620px, 100%); max-height: 85vh; display: flex; flex-direction: column; background: var(--surface, #141824); border: 1px solid var(--border, #2a2f3e); border-radius: 12px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5); }
.prp-head { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.9rem 1.1rem; border-bottom: 1px solid var(--border, #2a2f3e); }
.prp-head h3 { margin: 0; font-size: 1rem; color: var(--text-primary, #fff); }
.prp-x { background: none; border: none; color: var(--text-secondary, #888); cursor: pointer; font-size: 1rem; }
.prp-x:hover { color: var(--text-primary, #fff); }
.prp-body { padding: 1rem 1.1rem; overflow-y: auto; display: flex; flex-direction: column; gap: 0.75rem; color: var(--text-primary, #fff); font-size: 0.85rem; }
.prp-body p { margin: 0; line-height: 1.45; }
.hint { color: var(--text-secondary, #888); font-size: 0.8rem; }
.warn { color: #ffa502; font-size: 0.78rem; }
.prp-group { border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px; padding: 0.6rem 0.75rem; }
.prp-group-head { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; }
.count { padding: 0.05rem 0.45rem; border-radius: 999px; background: rgba(255, 255, 255, 0.08); font-size: 0.72rem; color: var(--text-secondary, #888); }
.prp-items { margin: 0.5rem 0 0; padding: 0 0 0 1.6rem; max-height: 200px; overflow-y: auto; font-size: 0.8rem; }
.prp-items li { margin: 0.15rem 0; }
.servers { color: var(--text-secondary, #888); font-size: 0.72rem; margin-left: 0.3rem; }
.prp-different { display: flex; align-items: flex-start; gap: 0.5rem; font-size: 0.8rem; color: var(--text-secondary, #aab); cursor: pointer; }
.prp-different input { margin-top: 2px; }
.prp-foot { display: flex; justify-content: flex-end; gap: 0.5rem; padding-top: 0.25rem; }
.btn { padding: 0.4rem 0.8rem; border-radius: 7px; border: 1px solid var(--border, #2a2f3e); background: rgba(255, 255, 255, 0.04); color: var(--text-primary, #fff); cursor: pointer; font-size: 0.82rem; }
.btn:hover:not(:disabled) { border-color: var(--accent, #3dd6b7); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn.primary { background: var(--accent, #3dd6b7); border-color: var(--accent, #3dd6b7); color: #04130f; font-weight: 600; }
</style>
