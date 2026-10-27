<script setup lang="ts">
// Shown after an overlay is saved when posters sent with it are tracked by
// Overlay Refresh (backend/api/overlay_refresh.py /by-overlay, /run-overlay).
// Refreshing is a normal check-and-refresh: only posters whose overlay now
// comes out differently are re-rendered and re-sent.
import { computed, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

interface PromptGroup {
  group_id: string
  group_name: string
  keys: string[]
  items: Array<{ title: string; servers: string[] }>
  running: boolean
}

const props = defineProps<{ configId: string; configName: string; groups: PromptGroup[] }>()
const emit = defineEmits<{ close: [] }>()

const apiBase = getApiBase()
const selected = ref<Set<string>>(new Set(props.groups.filter(g => !g.running).map(g => g.group_id)))
const busy = ref(false)
const result = ref<{ started: string[]; busy: string[] } | null>(null)
const error = ref('')

const total = computed(() => props.groups.reduce((n, g) => n + g.items.length, 0))

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
    const res = await fetch(`${apiBase}/api/overlay-refresh/run-overlay`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config_id: props.configId, group_ids: [...selected.value] }),
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
    <div class="orp-backdrop" @click.self="emit('close')">
      <div class="orp-modal">
        <div class="orp-head">
          <h3>Refresh posters using "{{ configName }}"?</h3>
          <button class="orp-x" title="Close" @click="emit('close')">✕</button>
        </div>

        <div v-if="result" class="orp-body">
          <p v-if="result.started.length">
            Refresh started for {{ result.started.join(', ') }}. Follow it on that library's Overlay Refresh page.
          </p>
          <p v-if="result.busy.length" class="warn">
            Already running, skipped: {{ result.busy.join(', ') }}. Run it again from Overlay Refresh once it finishes.
          </p>
          <div class="orp-foot"><button class="btn primary" @click="emit('close')">Done</button></div>
        </div>

        <div v-else class="orp-body">
          <p class="hint">
            {{ total }} poster(s) were sent with this overlay. Refreshing re-checks them and only re-renders and
            re-sends the ones whose overlay now looks different.
          </p>
          <div v-for="g in groups" :key="g.group_id" class="orp-group">
            <label class="orp-group-head">
              <input type="checkbox" :checked="selected.has(g.group_id)" :disabled="g.running" @change="toggle(g.group_id)" />
              <strong>{{ g.group_name }}</strong>
              <span class="count">{{ g.items.length }}</span>
              <span v-if="g.running" class="warn">(a refresh is already running)</span>
            </label>
            <ul class="orp-items">
              <li v-for="item in g.items" :key="item.title">
                {{ item.title }} <span class="servers">{{ item.servers.join(', ') }}</span>
              </li>
            </ul>
          </div>
          <p v-if="error" class="warn">{{ error }}</p>
          <div class="orp-foot">
            <button class="btn" @click="emit('close')">Not now</button>
            <button class="btn primary" :disabled="busy || selected.size === 0" @click="refreshNow">
              {{ busy ? 'Starting...' : 'Refresh posters' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.orp-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: 1100; padding: 16px; }
.orp-modal { width: min(620px, 100%); max-height: 85vh; display: flex; flex-direction: column; background: var(--surface, #141824); border: 1px solid var(--border, #2a2f3e); border-radius: 12px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5); }
.orp-head { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.9rem 1.1rem; border-bottom: 1px solid var(--border, #2a2f3e); }
.orp-head h3 { margin: 0; font-size: 1rem; color: var(--text-primary, #fff); }
.orp-x { background: none; border: none; color: var(--text-secondary, #888); cursor: pointer; font-size: 1rem; }
.orp-x:hover { color: var(--text-primary, #fff); }
.orp-body { padding: 1rem 1.1rem; overflow-y: auto; display: flex; flex-direction: column; gap: 0.75rem; color: var(--text-primary, #fff); font-size: 0.85rem; }
.orp-body p { margin: 0; line-height: 1.45; }
.hint { color: var(--text-secondary, #888); font-size: 0.8rem; }
.warn { color: #ffa502; font-size: 0.78rem; }
.orp-group { border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px; padding: 0.6rem 0.75rem; }
.orp-group-head { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; }
.count { padding: 0.05rem 0.45rem; border-radius: 999px; background: rgba(255, 255, 255, 0.08); font-size: 0.72rem; color: var(--text-secondary, #888); }
.orp-items { margin: 0.5rem 0 0; padding: 0 0 0 1.6rem; max-height: 200px; overflow-y: auto; font-size: 0.8rem; }
.orp-items li { margin: 0.15rem 0; }
.servers { color: var(--text-secondary, #888); font-size: 0.72rem; margin-left: 0.3rem; }
.orp-foot { display: flex; justify-content: flex-end; gap: 0.5rem; padding-top: 0.25rem; }
.btn { padding: 0.4rem 0.8rem; border-radius: 7px; border: 1px solid var(--border, #2a2f3e); background: rgba(255, 255, 255, 0.04); color: var(--text-primary, #fff); cursor: pointer; font-size: 0.82rem; }
.btn:hover:not(:disabled) { border-color: var(--accent, #3dd6b7); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn.primary { background: var(--accent, #3dd6b7); border-color: var(--accent, #3dd6b7); color: #04130f; font-weight: 600; }
</style>
