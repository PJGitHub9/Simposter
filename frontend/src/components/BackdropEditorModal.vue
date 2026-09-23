<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getApiBase } from '@/services/apiBase'

type BackdropSource = {
  url: string
  thumb?: string
  source?: string
  language?: string
  likes?: number
  type?: string
}

type BackdropItem = {
  key: string
  title: string
  year?: number | string
  art_url?: string | null
  tmdb_id?: number | null
  is_tv?: boolean
}

const props = defineProps<{ item: BackdropItem }>()
const emit = defineEmits<{
  close: []
  updated: [artUrl: string | null]
}>()

const apiBase = getApiBase()
const availableBackdrops = ref<BackdropSource[]>([])
// Same fallback pattern used by the logo picker (LogoEditorModal.vue) -- TMDb's
// resized w300 thumbnail variant can 404 even when the original loads fine.
const failedThumbs = ref(new Set<string>())
const thumbSrc = (b: BackdropSource) => (failedThumbs.value.has(b.url) ? b.url : (b.thumb || b.url))
const onThumbError = (b: BackdropSource) => {
  if (b.thumb && b.thumb !== b.url && !failedThumbs.value.has(b.url)) {
    failedThumbs.value = new Set(failedThumbs.value).add(b.url)
  }
}
const currentBackdropFailed = ref(false)
// `item` is a prop -- a snapshot taken when the modal opened, not the same object
// instance the parent grid holds in its own `items` array. A successful send only
// ever updates the GRID's copy (via the `updated` emit below), never this modal's
// own `props.item`, so without this override the "Current Backdrop" section kept
// showing the pre-send image until the modal was closed and reopened. Same fix
// shape as SquareArtModal.vue's `sentSquareArtUrl`.
const sentArtUrl = ref<string | null>(null)
const currentBackdropSrc = computed(() => sentArtUrl.value || props.item.art_url)
const selectedUrl = ref<string | null>(null)
const uploadedData = ref<string | null>(null)
const uploadedName = ref<string | null>(null)
const loadingBackdrops = ref(false)
const sending = ref(false)
const error = ref<string | null>(null)
const success = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)

const hasSelection = computed(() => !!(selectedUrl.value || uploadedData.value))

async function fetchAvailableBackdrops() {
  loadingBackdrops.value = true
  try {
    // Always resolve tmdb_id live — the list cache may not have it populated
    let tmdbId = props.item.tmdb_id
    if (!tmdbId) {
      const lookupEndpoint = props.item.is_tv
        ? `${apiBase}/api/tv-show/${props.item.key}/tmdb`
        : `${apiBase}/api/movie/${props.item.key}/tmdb`
      const lookupRes = await fetch(lookupEndpoint)
      if (lookupRes.ok) {
        const data = await lookupRes.json()
        tmdbId = data.tmdb_id || null
      }
    }
    if (!tmdbId) return

    const endpoint = props.item.is_tv
      ? `${apiBase}/api/tmdb/tv/${tmdbId}/images`
      : `${apiBase}/api/tmdb/${tmdbId}/images`
    const res = await fetch(endpoint)
    if (res.ok) {
      const data = await res.json()
      availableBackdrops.value = data.backdrops || []
    }
  } catch {
    // silent
  } finally {
    loadingBackdrops.value = false
  }
}

function selectBackdrop(url: string) {
  selectedUrl.value = url
  uploadedData.value = null
  uploadedName.value = null
}

function clearUpload() {
  uploadedData.value = null
  uploadedName.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function handleFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) loadFile(file)
}

function handleDrop(e: DragEvent) {
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) loadFile(file)
}

function loadFile(file: File) {
  if (!file.type.startsWith('image/')) {
    error.value = 'Please select an image file.'
    return
  }
  const reader = new FileReader()
  reader.onload = (ev) => {
    uploadedData.value = ev.target?.result as string
    uploadedName.value = file.name
    selectedUrl.value = null
  }
  reader.readAsDataURL(file)
}

async function sendToPlexBackdrop() {
  if (!hasSelection.value) return
  sending.value = true
  error.value = null
  success.value = false
  try {
    const body: Record<string, unknown> = {
      rating_key: props.item.key,
      is_tv: props.item.is_tv ?? false,
    }
    if (uploadedData.value) {
      body.art_data = uploadedData.value
    } else {
      body.art_url = selectedUrl.value
    }
    const res = await fetch(`${apiBase}/api/plex/send-backdrop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || `HTTP ${res.status}`)
    }
    const data = await res.json().catch(() => ({}))
    success.value = true
    const newArtUrl = data.art_url || selectedUrl.value
    // Update this modal's own "Current Backdrop" display, not just the grid --
    // emitting alone only ever reaches the grid's separate copy of the item.
    sentArtUrl.value = newArtUrl
    currentBackdropFailed.value = false
    // Pass back the new cached art_url so the grid card updates too
    emit('updated', newArtUrl)
    setTimeout(() => emit('close'), 1200)
  } catch (e: any) {
    error.value = e.message || 'Failed to send backdrop to Plex.'
  } finally {
    sending.value = false
  }
}

onMounted(fetchAvailableBackdrops)
</script>

<template>
  <Teleport to="body">
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal-panel">
      <!-- Header -->
      <div class="modal-header">
        <div class="modal-title">
          <span>{{ item.title }}</span>
          <span v-if="item.year" class="modal-year">{{ item.year }}</span>
        </div>
        <button class="btn-close" @click="emit('close')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <div class="modal-body">
        <!-- Current backdrop -->
        <div class="section">
          <div class="section-label">Current Backdrop</div>
          <div class="current-backdrop-area">
            <img v-if="currentBackdropSrc && !currentBackdropFailed" :src="currentBackdropSrc" :alt="item.title" class="current-backdrop-img" @error="currentBackdropFailed = true" />
            <div v-else class="no-current">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <path d="M3 9l4-4 4 4 4-4 4 4"/>
              </svg>
              <span>No backdrop cached yet</span>
            </div>
          </div>
        </div>

        <!-- Available backdrops from TMDb / Fanart -->
        <div class="section">
          <div class="section-label">
            Select Backdrop
            <span v-if="!item.tmdb_id" class="section-note">(no TMDb ID — upload only)</span>
          </div>

          <div v-if="loadingBackdrops" class="backdrop-loading">Loading backdrops…</div>

          <div v-else-if="availableBackdrops.length" class="backdrop-grid">
            <div
              v-for="backdrop in availableBackdrops"
              :key="backdrop.url"
              class="backdrop-thumb"
              :class="{ active: selectedUrl === backdrop.url }"
              @click="selectBackdrop(backdrop.url)"
            >
              <img :src="thumbSrc(backdrop)" :alt="backdrop.source" @error="onThumbError(backdrop)" />
              <div class="source-badge">{{ (backdrop.source || 'tmdb').toUpperCase() }}</div>
            </div>
          </div>

          <div v-else-if="item.tmdb_id" class="section-empty">No backdrops found from external sources.</div>
        </div>

        <!-- Upload -->
        <div class="section">
          <div class="section-label">Upload Custom Backdrop</div>
          <div
            class="upload-area"
            :class="{ 'drag-over': dragOver, 'has-file': !!uploadedData }"
            @dragover.prevent="dragOver = true"
            @dragleave="dragOver = false"
            @drop.prevent="handleDrop"
            @click="fileInput?.click()"
          >
            <template v-if="uploadedData">
              <img :src="uploadedData" class="upload-preview" :alt="uploadedName || ''" />
              <div class="upload-filename">{{ uploadedName }}</div>
              <button class="btn-clear-upload" @click.stop="clearUpload()">Remove</button>
            </template>
            <template v-else>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.45">
                <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
                <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
              </svg>
              <span>Drop an image here or <u>click to browse</u></span>
            </template>
            <input ref="fileInput" type="file" accept="image/*" style="display:none" @change="handleFileSelect" />
          </div>
        </div>

        <!-- Error / Success -->
        <div v-if="error" class="feedback error">{{ error }}</div>
        <div v-if="success" class="feedback success">Backdrop sent to Plex successfully!</div>
      </div>

      <!-- Footer -->
      <div class="modal-footer">
        <button class="btn-cancel" @click="emit('close')" :disabled="sending">Cancel</button>
        <button
          class="btn-send"
          :disabled="!hasSelection || sending"
          @click="sendToPlexBackdrop"
        >
          <svg v-if="sending" class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M21 12a9 9 0 11-6.219-8.56"/>
          </svg>
          {{ sending ? 'Sending…' : 'Send to Plex' }}
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
  max-width: 680px;
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
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.modal-year {
  font-size: 13px;
  color: #6b7a99;
  font-weight: 400;
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
  gap: 20px;
}

.section {}

.section-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #6b7a99;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-note {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
  color: #4a5568;
}

.current-backdrop-area {
  background: #0a0b12;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 16 / 9;
}

.current-backdrop-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.no-current {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: rgba(255, 255, 255, 0.25);
  font-size: 12px;
}

.backdrop-loading {
  color: #6b7a99;
  font-size: 13px;
  padding: 8px 0;
}

.backdrop-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.backdrop-thumb {
  position: relative;
  background: #0a0b12;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 4px;
  cursor: pointer;
  transition: border-color 0.15s, transform 0.1s;
  width: 140px;
  aspect-ratio: 16 / 9;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.backdrop-thumb:hover {
  border-color: rgba(61, 214, 183, 0.35);
  transform: translateY(-1px);
}

.backdrop-thumb.active {
  border-color: var(--accent, #3dd6b7);
  box-shadow: 0 0 0 1px var(--accent, #3dd6b7);
}

.backdrop-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.source-badge {
  position: absolute;
  top: 4px;
  right: 5px;
  font-size: 8px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.85);
  letter-spacing: 0.05em;
  background: rgba(0, 0, 0, 0.55);
  padding: 1px 4px;
  border-radius: 3px;
}

.section-empty {
  color: #4a5568;
  font-size: 13px;
  padding: 4px 0;
}

.upload-area {
  border: 1.5px dashed rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #6b7a99;
  font-size: 13px;
  transition: border-color 0.15s, background 0.15s;
  text-align: center;
}

.upload-area:hover, .upload-area.drag-over {
  border-color: rgba(61, 214, 183, 0.5);
  background: rgba(61, 214, 183, 0.03);
  color: #c9d1e0;
}

.upload-area.has-file {
  border-style: solid;
  border-color: rgba(61, 214, 183, 0.3);
  background: rgba(61, 214, 183, 0.04);
}

.upload-preview {
  max-height: 70px;
  max-width: 100%;
  object-fit: contain;
  background: #0a0b12;
  border-radius: 6px;
  padding: 6px 12px;
}

.upload-filename {
  font-size: 11px;
  color: #a8b3cf;
  word-break: break-all;
}

.btn-clear-upload {
  background: none;
  border: 1px solid rgba(255, 100, 100, 0.4);
  color: rgba(255, 100, 100, 0.8);
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-clear-upload:hover {
  background: rgba(255, 100, 100, 0.1);
  color: #ff6464;
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
.feedback.success {
  background: rgba(61, 214, 183, 0.1);
  border: 1px solid rgba(61, 214, 183, 0.25);
  color: #3dd6b7;
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
