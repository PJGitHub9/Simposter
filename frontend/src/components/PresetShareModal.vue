<script setup lang="ts">
// Share one or more presets as a file (backend/api/preset_share.py).
// Overlays are optional; the download is a .zip only when overlay images or
// fonts need to go with it, otherwise a .json.
import { computed, onMounted, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

const props = defineProps<{ keys: Array<{ template_id: string; preset_id: string }>; title: string }>()
const emit = defineEmits<{ close: [] }>()

interface ShareInfo {
  overlays: Array<{ id: string; name: string }>
  images: number
  fonts: string[]
  fonts_without_overlays: string[]
}

const apiBase = getApiBase()
const info = ref<ShareInfo | null>(null)
const loadError = ref('')
const includeOverlays = ref(true)
const compact = ref(true)
const downloading = ref(false)
const error = ref('')

const fonts = computed(() => (includeOverlays.value ? info.value?.fonts : info.value?.fonts_without_overlays) || [])
const images = computed(() => (includeOverlays.value ? info.value?.images || 0 : 0))
const isZip = computed(() => images.value > 0 || fonts.value.length > 0)

onMounted(async () => {
  try {
    const res = await fetch(`${apiBase}/api/presets/share-info`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keys: props.keys }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    info.value = await res.json()
  } catch (e) {
    loadError.value = `Couldn't read the preset: ${e instanceof Error ? e.message : e}`
  }
})

async function download() {
  downloading.value = true
  error.value = ''
  try {
    const res = await fetch(`${apiBase}/api/presets/share`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keys: props.keys, include_overlays: includeOverlays.value, compact: compact.value }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const match = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = match?.[1] || (isZip.value ? 'simposter-presets.zip' : 'simposter-presets.json')
    a.click()
    URL.revokeObjectURL(a.href)
    emit('close')
  } catch (e) {
    error.value = `Download failed: ${e instanceof Error ? e.message : e}`
  } finally {
    downloading.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="psm-backdrop" @click.self="emit('close')">
      <div class="psm-modal">
        <div class="psm-head">
          <h3>Share {{ title }}</h3>
          <button class="psm-x" title="Close" @click="emit('close')">✕</button>
        </div>
        <div class="psm-body">
          <p v-if="loadError" class="warn">{{ loadError }}</p>
          <p v-else-if="!info" class="hint">Loading…</p>
          <template v-else>
            <label class="psm-check" :class="{ disabled: !info.overlays.length }">
              <input v-model="includeOverlays" type="checkbox" :disabled="!info.overlays.length" />
              <span>
                Include overlays
                <span v-if="info.overlays.length" class="hint">
                  ({{ info.overlays.map(o => o.name).join(', ') }}{{ info.images ? `, ${info.images} image${info.images === 1 ? '' : 's'}` : '' }})
                </span>
                <span v-else class="hint">(this preset uses none)</span>
              </span>
            </label>
            <label class="psm-check">
              <input v-model="compact" type="checkbox" />
              <span>Leave out default settings <span class="hint">(smaller file, same look)</span></span>
            </label>
            <p class="hint">
              <template v-if="isZip">
                Downloads a <strong>.zip</strong> with the preset{{ images ? ', its overlay images' : '' }}{{ fonts.length ? `${images ? ' and' : ','} these fonts: ${fonts.join(', ')}` : '' }}.
              </template>
              <template v-else>Downloads a <strong>.json</strong> file.</template>
              Open it in Template Manager → Import / Export → Open file.
            </p>
            <p v-if="!includeOverlays && info.overlays.length" class="hint">
              The preset's overlays are turned off in the shared copy.
            </p>
          </template>
          <p v-if="error" class="warn">{{ error }}</p>
          <div class="psm-foot">
            <button class="btn" @click="emit('close')">Cancel</button>
            <button class="btn primary" :disabled="!info || downloading" @click="download">
              {{ downloading ? 'Preparing…' : isZip ? 'Download .zip' : 'Download .json' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.psm-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: 1100; padding: 16px; }
.psm-modal { width: min(520px, 100%); background: var(--surface, #141824); border: 1px solid var(--border, #2a2f3e); border-radius: 12px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5); }
.psm-head { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.9rem 1.1rem; border-bottom: 1px solid var(--border, #2a2f3e); }
.psm-head h3 { margin: 0; font-size: 1rem; color: var(--text-primary, #fff); }
.psm-x { background: none; border: none; color: var(--text-secondary, #888); cursor: pointer; font-size: 1rem; }
.psm-x:hover { color: var(--text-primary, #fff); }
.psm-body { padding: 1rem 1.1rem; display: flex; flex-direction: column; gap: 0.7rem; color: var(--text-primary, #fff); font-size: 0.85rem; }
.psm-body p { margin: 0; line-height: 1.45; }
.psm-check { display: flex; align-items: flex-start; gap: 0.5rem; cursor: pointer; }
.psm-check input { margin-top: 0.2rem; }
.psm-check.disabled { opacity: 0.6; cursor: default; }
.hint { color: var(--text-secondary, #888); font-size: 0.78rem; }
.warn { color: #ffa502; font-size: 0.8rem; }
.psm-foot { display: flex; justify-content: flex-end; gap: 0.5rem; padding-top: 0.25rem; }
.btn { padding: 0.4rem 0.8rem; border-radius: 7px; border: 1px solid var(--border, #2a2f3e); background: rgba(255, 255, 255, 0.04); color: var(--text-primary, #fff); cursor: pointer; font-size: 0.82rem; }
.btn:hover:not(:disabled) { border-color: var(--accent, #3dd6b7); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn.primary { background: var(--accent, #3dd6b7); border-color: var(--accent, #3dd6b7); color: #04130f; font-weight: 600; }
</style>
