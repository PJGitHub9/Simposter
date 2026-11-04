<script setup lang="ts">
// Ready-made overlays, listed from the simposter-assets repo (bundled copies as
// the fallback; backend/api/overlay_starters.py). Adding one downloads
// its images from the creator's repo into "Your images" (backend/api/overlay_starters.py).
import { onMounted, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

interface Starter {
  id: string
  name: string
  description: string
  credit: { author?: string; url?: string }
  layers: number
  installed: boolean
  needs_version: string | null
  source: string | null
}

const emit = defineEmits<{ close: []; added: [configId: string] }>()
const apiBase = getApiBase()
const starters = ref<Starter[]>([])
const loading = ref(true)
const busy = ref<string | null>(null)
const message = ref<{ id: string; ok: boolean; text: string } | null>(null)

const load = async (refresh = false) => {
  loading.value = true
  try {
    const res = await fetch(`${apiBase}/api/overlay-starters${refresh ? '?refresh=true' : ''}`)
    if (res.ok) starters.value = (await res.json()).starters || []
  } finally {
    loading.value = false
  }
}

const add = async (s: Starter) => {
  if (s.installed && !confirm(`Replace "${s.name}" with the latest shipped version? Any changes you made to it (layers, rules, notes) are lost. Presets that use it stay linked.`)) return
  busy.value = s.id
  message.value = null
  try {
    const res = await fetch(`${apiBase}/api/overlay-starters/${encodeURIComponent(s.id)}/install${s.installed ? '?replace=true' : ''}`, { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
    const missing = (data.missing || []).length
    message.value = {
      id: s.id, ok: missing === 0,
      text: missing ? `Added, but ${missing} image(s) couldn't be downloaded.` : `Added with ${data.images} image(s).`,
    }
    s.installed = true
    emit('added', data.config_id)
  } catch (e: any) {
    message.value = { id: s.id, ok: false, text: e.message || String(e) }
  } finally {
    busy.value = null
  }
}

onMounted(() => load())
</script>

<template>
  <Teleport to="body">
    <div class="so-backdrop" @click.self="emit('close')">
      <div class="so-modal" role="dialog" aria-label="Starter overlays">
        <div class="so-head">
          <h3>Starter overlays</h3>
          <span class="so-head-actions">
            <button type="button" class="so-link" :disabled="loading" title="Look for new or updated starter overlays" @click="load(true)">Check for new</button>
            <button type="button" class="so-close" title="Close" @click="emit('close')">✕</button>
          </span>
        </div>
        <p class="so-intro">
          Ready-made overlays shared by their creators. Adding one downloads its images into Your images.
          After adding, tick it in a preset (poster editor → Extras → Overlays) to use it.
        </p>
        <div v-if="loading" class="so-empty">Loading...</div>
        <div v-else-if="!starters.length" class="so-empty">No starter overlays available.</div>
        <div v-for="s in starters" :key="s.id" class="so-item">
          <div class="so-info">
            <div class="so-name">{{ s.name }} <span v-if="s.installed" class="so-added">Added</span></div>
            <div class="so-desc">{{ s.description }}</div>
            <div class="so-meta">
              {{ s.layers }} layer{{ s.layers === 1 ? '' : 's' }}
              <template v-if="s.credit.author"> · by
                <a v-if="s.credit.url" :href="s.credit.url" target="_blank" rel="noopener noreferrer">{{ s.credit.author }}</a>
                <template v-else>{{ s.credit.author }}</template>
              </template>
            </div>
            <div v-if="s.needs_version" class="so-msg bad">Needs Simposter {{ s.needs_version }} or newer.</div>
            <div v-if="message?.id === s.id" class="so-msg" :class="{ bad: !message.ok }">{{ message.text }}</div>
          </div>
          <button type="button" class="so-btn" :disabled="busy !== null || !!s.needs_version" @click="add(s)">
            {{ busy === s.id ? 'Adding...' : s.installed ? 'Replace' : 'Add' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.so-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: 1100; padding: 1rem; }
.so-modal { width: min(620px, 100%); max-height: 85vh; overflow-y: auto; background: var(--surface, #1a1f2e); border: 1px solid var(--border, #2a2f3e); border-radius: 12px; padding: 1.1rem 1.25rem; }
.so-head { display: flex; justify-content: space-between; align-items: center; }
.so-head h3 { margin: 0; font-size: 1.05rem; color: var(--text-primary, #fff); }
.so-head-actions { display: inline-flex; align-items: center; gap: 0.75rem; }
.so-link { background: none; border: none; padding: 0; color: var(--accent, #3dd6b7); font-size: 0.78rem; cursor: pointer; }
.so-link:disabled { opacity: 0.5; cursor: default; }
.so-close { background: none; border: none; color: var(--text-secondary, #8b95a7); font-size: 1rem; cursor: pointer; }
.so-intro { margin: 0.5rem 0 0.9rem; font-size: 0.8rem; color: var(--text-secondary, #9aa4b2); line-height: 1.45; }
.so-empty { padding: 1rem 0; font-size: 0.85rem; color: var(--text-secondary, #8b95a7); }
.so-item { display: flex; gap: 1rem; align-items: flex-start; padding: 0.8rem 0; border-top: 1px solid var(--border, #2a2f3e); }
.so-info { flex: 1; min-width: 0; }
.so-name { font-weight: 600; color: var(--text-primary, #fff); font-size: 0.92rem; }
.so-added { margin-left: 0.35rem; padding: 0.05rem 0.45rem; border-radius: 999px; font-size: 0.65rem; font-weight: 700; text-transform: uppercase; color: var(--accent, #3dd6b7); background: rgba(61, 214, 183, 0.12); }
.so-desc { margin-top: 0.2rem; font-size: 0.8rem; color: var(--text-secondary, #9aa4b2); }
.so-meta { margin-top: 0.25rem; font-size: 0.74rem; color: var(--text-secondary, #8b95a7); }
.so-meta a { color: var(--accent, #3dd6b7); }
.so-msg { margin-top: 0.35rem; font-size: 0.76rem; color: var(--accent, #3dd6b7); }
.so-msg.bad { color: #f87171; }
.so-btn { flex-shrink: 0; padding: 0.4rem 0.95rem; border-radius: 6px; border: 1px solid rgba(61, 214, 183, 0.45); background: rgba(61, 214, 183, 0.12); color: var(--accent, #3dd6b7); font-weight: 600; cursor: pointer; }
.so-btn:disabled { opacity: 0.5; cursor: default; }
</style>
