<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { getApiBase } from '@/services/apiBase'

type PresetRecord = { id: string; name?: string }

const props = defineProps<{
  ratingKey: string
  mediaType: 'movie' | 'tv'
  libraryId: string | number | null | undefined
  title: string
  // Pre-fill with the editor's currently-selected template/preset -- a reasonable
  // starting point, but the whole point of this modal is letting the user pick a
  // DIFFERENT one (e.g. a textless+logo template to switch to once a textless
  // poster exists, while right now they're using a fallback template that shows
  // title text because no textless poster is available yet).
  currentTemplate?: string
  currentPreset?: string
}>()
const emit = defineEmits<{
  close: []
  queued: []
}>()

const apiBase = getApiBase()
// Retry-queue items are movies/TV shows only (the button is hidden entirely for
// collections, see EditorPane.vue/TvShowEditorPane.vue) -- kometa is a
// collections-only template (see CLAUDE.md Quirk #21) and must never appear here,
// regardless of what templates the backend's presets.json happens to list.
const EXCLUDED_TEMPLATES = new Set(['kometa'])
const templatesData = ref<Record<string, { presets: PresetRecord[] }>>({})
const selectedTemplate = ref(props.currentTemplate && !EXCLUDED_TEMPLATES.has(props.currentTemplate) ? props.currentTemplate : 'uniformlogo')
const selectedPreset = ref(props.currentPreset || '')
const availablePresets = computed(() => templatesData.value[selectedTemplate.value]?.presets || [])
const templateKeys = computed(() => Object.keys(templatesData.value).filter((t) => !EXCLUDED_TEMPLATES.has(t)))

const loadingPresets = ref(false)
const queueing = ref(false)
const error = ref<string | null>(null)

async function loadPresets() {
  loadingPresets.value = true
  try {
    const res = await fetch(`${apiBase}/api/presets`)
    if (res.ok) {
      templatesData.value = await res.json()
      const tplKeys = templateKeys.value
      if (!tplKeys.includes(selectedTemplate.value)) {
        selectedTemplate.value = tplKeys[0] || 'uniformlogo'
      }
      const presets = templatesData.value[selectedTemplate.value]?.presets || []
      if (!presets.find((p) => p.id === selectedPreset.value)) {
        selectedPreset.value = presets[0]?.id || ''
      }
    }
  } catch {
    // silent
  } finally {
    loadingPresets.value = false
  }
}

watch(selectedTemplate, () => {
  const presets = availablePresets.value
  if (!presets.find((p) => p.id === selectedPreset.value)) {
    selectedPreset.value = presets[0]?.id || ''
  }
})

async function confirmQueue() {
  if (!selectedTemplate.value || !selectedPreset.value) return
  queueing.value = true
  error.value = null
  try {
    const res = await fetch(`${apiBase}/api/retry-queue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rating_key: props.ratingKey,
        media_type: props.mediaType,
        library_id: props.libraryId != null ? String(props.libraryId) : null,
        template_id: selectedTemplate.value,
        preset_id: selectedPreset.value,
        title: props.title,
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    emit('queued')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to add to retry queue'
  } finally {
    queueing.value = false
  }
}

onMounted(loadPresets)
</script>

<template>
  <Teleport to="body">
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal-panel">
      <div class="modal-header">
        <div class="modal-title">
          <span>Add to Retry Queue</span>
        </div>
        <button class="btn-close" @click="emit('close')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <div class="modal-body">
        <div class="section-note">
          Once a poster without title text becomes available for <strong>{{ title }}</strong> on
          TMDb/Fanart, Simposter will automatically render and send it using the template/preset
          you pick below — it does <em>not</em> have to be what's currently selected in the editor.
          Pick the template you actually want used once a textless poster shows up (e.g. a
          textless-and-logo template), not necessarily a fallback template you're using right now
          just to get something live.
        </div>

        <div class="controls-row">
          <div class="control">
            <label>Template</label>
            <select v-model="selectedTemplate" :disabled="loadingPresets">
              <option v-for="t in templateKeys" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>
          <div class="control">
            <label>Preset</label>
            <select v-model="selectedPreset" :disabled="loadingPresets || !availablePresets.length">
              <option v-for="p in availablePresets" :key="p.id" :value="p.id">{{ p.name || p.id }}</option>
            </select>
          </div>
        </div>

        <div v-if="error" class="feedback error">{{ error }}</div>
      </div>

      <div class="modal-footer">
        <button class="btn-cancel" @click="emit('close')" :disabled="queueing">Cancel</button>
        <button class="btn-send" :disabled="!selectedTemplate || !selectedPreset || queueing" @click="confirmQueue">
          <svg v-if="queueing" class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M21 12a9 9 0 11-6.219-8.56"/>
          </svg>
          {{ queueing ? 'Queueing…' : '⏳ Add to Retry Queue' }}
        </button>
      </div>
    </div>
  </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal-panel {
  background: #12151f;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  flex-shrink: 0;
}

.modal-title {
  font-size: 15px;
  font-weight: 600;
  color: #eef2ff;
}

.btn-close {
  background: none;
  border: none;
  color: #6b7a99;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: flex;
  transition: color 0.15s;
}
.btn-close:hover { color: #eef2ff; }

.modal-body {
  padding: 18px 20px;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-note {
  font-size: 12.5px;
  color: #a8b3cf;
  line-height: 1.6;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  padding: 12px 14px;
}

.controls-row {
  display: flex;
  gap: 12px;
}

.control {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.control label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6b7a99;
}

.control select {
  padding: 6px 10px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  outline: none;
}

.feedback {
  font-size: 13px;
  padding: 10px 14px;
  border-radius: 8px;
}
.feedback.error {
  background: rgba(255, 80, 80, 0.1);
  border: 1px solid rgba(255, 80, 80, 0.25);
  color: #ff8080;
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
  flex-shrink: 0;
}

.btn-cancel {
  background: none;
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #a8b3cf;
  border-radius: 8px;
  padding: 7px 16px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-cancel:hover:not(:disabled) { color: #eef2ff; border-color: rgba(255,255,255,0.2); }
.btn-cancel:disabled { opacity: 0.5; cursor: default; }

.btn-send {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--accent, #3dd6b7);
  border: none;
  color: #0a0b12;
  font-weight: 600;
  border-radius: 8px;
  padding: 7px 18px;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn-send:disabled { opacity: 0.45; cursor: default; }
.btn-send:hover:not(:disabled) { opacity: 0.88; }

.spin {
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
