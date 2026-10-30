<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { getApiBase } from '../../services/apiBase'

const props = defineProps<{
  // Only changes wording + the 'kind' form field the backend uses to prefix
  // the saved filename (bg_/logo_) -- the upload endpoint itself is identical
  // either way (POST /api/upload/background).
  kind: 'poster' | 'logo'
}>()
const emit = defineEmits<{
  close: []
  uploaded: [url: string]
}>()

const apiBase = getApiBase()
const label = computed(() => (props.kind === 'logo' ? 'Logo' : 'Poster'))

type Tab = 'local' | 'url'
const activeTab = ref<Tab>('local')

// ── Local file upload ───────────────────────────────────────────────────
const dropActive = ref(false)
const uploading = ref(false)
const localError = ref<string | null>(null)
const fileInputEl = ref<HTMLInputElement | null>(null)

async function uploadFile(file: File) {
  localError.value = null
  // A file with no detectable image MIME type (happens with some OS file
  // pickers/extensions) used to fail this check silently with zero feedback
  // -- the whole "upload just does nothing" complaint this modal exists to
  // fix. Now it says exactly why nothing happened.
  if (!file.type.startsWith('image/')) {
    localError.value = `"${file.name}" doesn't look like an image file.`
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('kind', props.kind === 'logo' ? 'logo' : 'background')
    const res = await fetch(`${apiBase}/api/upload/background`, { method: 'POST', body: fd })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(text || `Upload failed (HTTP ${res.status})`)
    }
    const data = await res.json()
    emit('uploaded', `${apiBase}${data.url}`)
  } catch (e: unknown) {
    localError.value = e instanceof Error ? e.message : 'Upload failed — please try again.'
  } finally {
    uploading.value = false
  }
}

function onFileInputChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) uploadFile(file)
  ;(e.target as HTMLInputElement).value = ''
}
function onDrop(e: DragEvent) {
  dropActive.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) uploadFile(file)
}

// ── Remote URL ───────────────────────────────────────────────────────────
const urlInput = ref('')
const previewSrc = ref('')
const urlPreviewState = ref<'idle' | 'ok' | 'error'>('idle')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const isValidUrl = computed(() => /^https?:\/\/.+/i.test(urlInput.value.trim()))

watch(urlInput, (val) => {
  urlPreviewState.value = 'idle'
  if (debounceTimer) clearTimeout(debounceTimer)
  const trimmed = val.trim()
  if (!/^https?:\/\//i.test(trimmed)) {
    previewSrc.value = ''
    return
  }
  // Debounced so a live preview request doesn't fire on every keystroke
  // while the user is still typing/pasting the URL.
  debounceTimer = setTimeout(() => { previewSrc.value = trimmed }, 450)
})

function onPreviewLoad() { urlPreviewState.value = 'ok' }
function onPreviewError() { urlPreviewState.value = 'error' }

function useUrl() {
  if (!isValidUrl.value) return
  emit('uploaded', urlInput.value.trim())
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="emit('close')">
      <div class="modal-panel">
        <div class="modal-header">
          <div class="modal-title">Upload {{ label }}</div>
          <button class="btn-close" @click="emit('close')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div class="modal-body">
          <div class="tab-row">
            <button class="tab-btn" :class="{ active: activeTab === 'local' }" @click="activeTab = 'local'">
              📁 Upload Local File
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'url' }" @click="activeTab = 'url'">
              🔗 Enter URL
            </button>
          </div>

          <div v-if="activeTab === 'local'" class="tab-panel">
            <div
              class="drop-zone"
              :class="{ 'drag-over': dropActive, uploading }"
              @dragover.prevent="dropActive = true"
              @dragleave="dropActive = false"
              @drop.prevent="onDrop"
              @click="!uploading && fileInputEl?.click()"
            >
              <svg v-if="uploading" class="spin" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M21 12a9 9 0 11-6.219-8.56"/>
              </svg>
              <span v-if="uploading">Uploading…</span>
              <span v-else>&#8679; Drop an image here, or click to browse</span>
            </div>
            <input ref="fileInputEl" type="file" accept="image/*" style="display:none" @change="onFileInputChange" />
            <div v-if="localError" class="feedback error">{{ localError }}</div>
          </div>

          <div v-else class="tab-panel">
            <label class="field-label">Image URL</label>
            <input
              v-model="urlInput"
              type="text"
              class="url-input"
              placeholder="https://example.com/poster.jpg"
              @keydown.enter="useUrl"
            />
            <div v-if="previewSrc" class="url-preview">
              <img :src="previewSrc" alt="Preview" referrerpolicy="no-referrer" @load="onPreviewLoad" @error="onPreviewError" />
              <span v-if="urlPreviewState === 'ok'" class="preview-status ok">✓ Image loads correctly</span>
              <span v-else-if="urlPreviewState === 'error'" class="preview-status error">✗ Couldn't load this image — double-check the URL</span>
            </div>
            <div v-else-if="urlInput.trim() && !isValidUrl" class="feedback error">
              URL must start with http:// or https://
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn-cancel" @click="emit('close')">Cancel</button>
          <button v-if="activeTab === 'url'" class="btn-send" :disabled="!isValidUrl" @click="useUrl">Use This URL</button>
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
  max-width: 460px;
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
  gap: 14px;
}

.tab-row {
  display: flex;
  gap: 8px;
}

.tab-btn {
  flex: 1;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #a8b3cf;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12.5px;
  cursor: pointer;
  transition: all 0.15s;
}
.tab-btn:hover { border-color: rgba(255, 255, 255, 0.2); color: #eef2ff; }
.tab-btn.active {
  background: rgba(61, 214, 183, 0.12);
  border-color: #3dd6b7;
  color: #3dd6b7;
}

.tab-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.drop-zone {
  border: 1.5px dashed rgba(255, 255, 255, 0.18);
  border-radius: 8px;
  height: 110px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  color: #a8b3cf;
  font-size: 13px;
  text-align: center;
  transition: border-color 0.2s, background 0.2s;
}
.drop-zone:hover, .drop-zone.drag-over {
  border-color: rgba(61, 214, 183, 0.6);
  background: rgba(61, 214, 183, 0.05);
}
.drop-zone.uploading { cursor: default; }

.field-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6b7a99;
}

.url-input {
  padding: 8px 10px;
  font-size: 13px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  outline: none;
  font-family: inherit;
}
.url-input:focus { border-color: rgba(61, 214, 183, 0.5); }

.url-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.url-preview img {
  max-height: 180px;
  max-width: 100%;
  object-fit: contain;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.preview-status { font-size: 12px; }
.preview-status.ok { color: #3dd6b7; }
.preview-status.error { color: #ff8080; }

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
.btn-cancel:hover:not(:disabled) { color: #eef2ff; border-color: rgba(255, 255, 255, 0.2); }

.btn-send {
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

.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
