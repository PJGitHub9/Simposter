<script setup lang="ts">
// Thumb Art editor: Jellyfin/Emby's 16:9 "Thumb" image. Built from Square Art's
// editor (SquareArtModal.vue) -- same "existing template/preset rendered against a
// different canvas" approach, here options.canvas_mode = 'thumb' (2000x1125, see
// backend/templates/canvas.py) -- but the background candidates are TMDb/Fanart
// backdrops instead of posters, and it sends to the item's Jellyfin/Emby copies
// instead of Plex (Plex has no Thumb slot).
import { ref, computed, onMounted, watch } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useRenderService } from '@/services/render'
import { mediaServerLabel } from '@/services/mediaServerLabel'
import { notifySendSummary } from '@/services/sendNotify'
import { useSettingsStore } from '@/stores/settings'
import SendToServerModal from '@/components/editor/SendToServerModal.vue'
import type { MovieInput, PresetOptions } from '@/services/types'

type LinkedServer = { server_id: string; rating_key: string }

type ThumbArtItem = {
  key: string
  title: string
  year?: number | string
  tmdb_id?: number | null
  mediaType?: 'movie' | 'tv-show'
  library_id?: string | number | null
  server_id?: string | null
  other_servers?: LinkedServer[] | null
}

type PresetRecord = { id: string; name?: string; options?: PresetOptions }
type ImageSource = { url: string; thumb?: string; source?: string; has_text?: boolean }

const props = defineProps<{ item: ThumbArtItem }>()
const emit = defineEmits<{ close: []; updated: [] }>()

const apiBase = getApiBase()
const settings = useSettingsStore()
const render = useRenderService()
const { loading: previewLoading, error: previewError, lastPreview } = render

const isTv = computed(() => props.item.mediaType === 'tv-show')

// The item's Jellyfin/Emby copies -- the only places Thumb Art can go.
const targets = computed<LinkedServer[]>(() => {
  const list: LinkedServer[] = []
  const own = props.item.server_id || 'plex-1'
  if (own !== 'plex-1') list.push({ server_id: own, rating_key: props.item.key })
  for (const o of props.item.other_servers || []) {
    if (o?.server_id && o.server_id !== 'plex-1' && o.rating_key && !list.some(l => l.server_id === o.server_id)) {
      list.push({ server_id: o.server_id, rating_key: o.rating_key })
    }
  }
  return list
})
const labelFor = (serverId: string) => mediaServerLabel(serverId, settings.mediaServers.value)
const serverOptions = computed(() => targets.value.map(t => ({ server_id: t.server_id, label: labelFor(t.server_id) })))

// "Current Thumb Art" -- what the first Jellyfin/Emby copy has right now, with a
// ‹ › toggle when the item is on more than one of them.
const viewingIndex = ref(0)
const viewing = computed(() => targets.value[viewingIndex.value] || targets.value[0] || null)
function cycleViewing(step: number) {
  const n = targets.value.length
  if (n < 2) return
  viewingIndex.value = (viewingIndex.value + step + n) % n
  currentFailed.value = false
}
const currentFailed = ref(false)
const currentRefreshToken = ref(0)
const currentForceRefresh = ref(false)
const currentSrc = computed(() => {
  if (!viewing.value) return ''
  const params = new URLSearchParams({ t: String(currentRefreshToken.value) })
  if (currentForceRefresh.value) params.set('force_refresh', '1')
  return `${apiBase}/api/thumb-art/${encodeURIComponent(viewing.value.rating_key)}?${params.toString()}`
})
function refreshCurrent() {
  currentFailed.value = false
  currentForceRefresh.value = true
  currentRefreshToken.value = Date.now()
}

// Same template/preset loading as Square Art. Kometa is collections-only.
const EXCLUDED_TEMPLATES = new Set(['kometa'])
const templatesData = ref<Record<string, { presets: PresetRecord[] }>>({})
const selectedTemplate = ref('uniformlogo')
const selectedPreset = ref('')
const availablePresets = computed(() => templatesData.value[selectedTemplate.value]?.presets || [])
const templateKeys = computed(() => Object.keys(templatesData.value).filter((t) => !EXCLUDED_TEMPLATES.has(t)))

const loadingPresets = ref(false)
const saving = ref(false)
const saveMessage = ref<string | null>(null)
const saveError = ref<string | null>(null)

async function loadPresets() {
  loadingPresets.value = true
  try {
    const res = await fetch(`${apiBase}/api/presets`)
    if (res.ok) {
      templatesData.value = await res.json()
      const tplKeys = templateKeys.value
      if (tplKeys.length && !tplKeys.includes(selectedTemplate.value)) {
        selectedTemplate.value = tplKeys[0] ?? selectedTemplate.value
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

// Vertical position of the backdrop within the 16:9 frame, and logo size. A
// preset's logo box is tuned for a tall poster; on the short landscape canvas its
// height-limited logo comes out small, so the size can be raised here.
const posterShiftY = ref(0)
const logoScale = ref(150)
watch(selectedPreset, () => {
  const preset = availablePresets.value.find((p) => p.id === selectedPreset.value)
  posterShiftY.value = Math.round((Number(preset?.options?.poster_shift_y) || 0) * 100)
})

// Backdrop/logo candidates from TMDb/Fanart -- never the item's current server
// art, which for a managed library is already a composited render (Quirk #43).
const resolvedTmdbId = ref<number | null>(props.item.tmdb_id ?? null)
const availableBackdrops = ref<ImageSource[]>([])
const availableLogos = ref<ImageSource[]>([])
const selectedBackdropUrl = ref<string | null>(null)
const selectedLogoUrl = ref<string | null>(null)
const loadingCandidates = ref(false)
const candidatesError = ref<string | null>(null)

const backdropTextFilter = ref<'all' | 'textless' | 'text'>('all')
const filteredBackdrops = computed(() => {
  if (backdropTextFilter.value === 'textless') return availableBackdrops.value.filter((p) => p.has_text === false)
  if (backdropTextFilter.value === 'text') return availableBackdrops.value.filter((p) => p.has_text === true)
  return availableBackdrops.value
})

const failedThumbs = ref(new Set<string>())
const thumbSrc = (i: ImageSource) => (failedThumbs.value.has(i.url) ? i.url : (i.thumb || i.url))
const onThumbError = (i: ImageSource) => {
  if (i.thumb && i.thumb !== i.url && !failedThumbs.value.has(i.url)) {
    failedThumbs.value = new Set(failedThumbs.value).add(i.url)
  }
}

async function loadCandidates() {
  loadingCandidates.value = true
  candidatesError.value = null
  try {
    let tmdbId = resolvedTmdbId.value
    if (!tmdbId) {
      const lookupEndpoint = isTv.value
        ? `${apiBase}/api/tv-show/${props.item.key}/tmdb`
        : `${apiBase}/api/movie/${props.item.key}/tmdb`
      const lookupRes = await fetch(lookupEndpoint)
      if (lookupRes.ok) {
        const data = await lookupRes.json()
        tmdbId = data.tmdb_id || null
        resolvedTmdbId.value = tmdbId
      }
    }
    if (!tmdbId) {
      candidatesError.value = 'No TMDb match found for this title — cannot fetch backdrop/logo candidates.'
      return
    }

    const endpoint = isTv.value
      ? `${apiBase}/api/tmdb/tv/${tmdbId}/images`
      : `${apiBase}/api/tmdb/${tmdbId}/images`
    const res = await fetch(endpoint)
    if (!res.ok) {
      candidatesError.value = `Failed to fetch TMDb images (HTTP ${res.status}).`
      return
    }
    const data = await res.json()
    availableBackdrops.value = data.backdrops || []
    availableLogos.value = (data.logos || []).filter((l: ImageSource) => {
      const url = (l.url || '').toLowerCase()
      return !url.endsWith('.svg') && !url.includes('.svg?')
    })

    if (!availableBackdrops.value.length) {
      candidatesError.value = 'No backdrops found on TMDb/Fanart for this title.'
      return
    }

    // A textless backdrop is the best default -- the template adds its own logo.
    const textless = availableBackdrops.value.find((p) => p.has_text === false)
    const defaultBackdrop = textless || availableBackdrops.value[0]
    if (defaultBackdrop) selectedBackdropUrl.value = defaultBackdrop.url
    selectedLogoUrl.value = availableLogos.value[0]?.url || null
  } catch (e: unknown) {
    candidatesError.value = e instanceof Error ? e.message : 'Failed to load backdrop/logo candidates.'
  } finally {
    loadingCandidates.value = false
  }
}

const bgUrl = computed(() => selectedBackdropUrl.value || '')
const logoUrl = computed(() => selectedLogoUrl.value)

const movieInput = computed<MovieInput>(() => ({
  key: props.item.key,
  title: props.item.title,
  year: props.item.year,
  mediaType: props.item.mediaType || 'movie',
  library_id: props.item.library_id ?? undefined,
}))

const presetOptions = computed<PresetOptions>(() => {
  const preset = availablePresets.value.find((p) => p.id === selectedPreset.value)
  const opts: Record<string, unknown> = { ...(preset?.options || {}) }
  const scale = logoScale.value / 100
  if (opts.uniform_logo_max_w != null) opts.uniform_logo_max_w = Number(opts.uniform_logo_max_w) * scale
  // uniform_logo_max_h is rescaled for the short canvas on the backend
  // (scale_options_for_canvas); this multiplies on top of that.
  if (opts.uniform_logo_max_h != null) opts.uniform_logo_max_h = Number(opts.uniform_logo_max_h) * scale
  return { ...opts, canvas_mode: 'thumb', poster_shift_y: posterShiftY.value / 100 } as PresetOptions
})

const canRender = computed(() => !!bgUrl.value && !!selectedTemplate.value && !!selectedPreset.value)

async function doPreview() {
  if (!canRender.value) return
  await render.preview(movieInput.value, bgUrl.value, logoUrl.value, presetOptions.value, selectedTemplate.value, selectedPreset.value, false, false)
}

async function doSaveToDisk() {
  if (!canRender.value) return
  saving.value = true
  saveMessage.value = null
  saveError.value = null
  try {
    const payload = {
      template_id: selectedTemplate.value,
      preset_id: selectedPreset.value,
      background_url: bgUrl.value,
      logo_url: logoUrl.value,
      movie_title: props.item.title,
      movie_year: props.item.year ?? null,
      options: presetOptions.value,
      is_collection: false,
      rating_key: props.item.key,
      // A different filename than the poster/square art so neither is overwritten.
      filename: 'thumb.jpg',
      library_id: props.item.library_id != null ? String(props.item.library_id) : null,
      is_tv: isTv.value,
    }
    const res = await fetch(`${apiBase}/api/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text || `HTTP ${res.status}`)
    }
    const data = await res.json().catch(() => ({}))
    saveMessage.value = typeof data.saved_path === 'string' ? `Saved to ${data.saved_path}` : 'Saved to disk'
  } catch (e: unknown) {
    saveError.value = e instanceof Error ? e.message : 'Failed to save thumb art'
  } finally {
    saving.value = false
  }
}

const sending = ref(false)
const showSendModal = ref(false)

function onSendClick() {
  if (targets.value.length > 1) showSendModal.value = true
  else doSend(targets.value.map(t => t.server_id))
}

function onSendModalConfirm(serverIds: string[]) {
  showSendModal.value = false
  doSend(serverIds)
}

async function doSend(serverIds: string[]) {
  if (!lastPreview.value) {
    saveError.value = 'Render a preview first.'
    return
  }
  const chosen = targets.value.filter(t => serverIds.includes(t.server_id))
  if (!chosen.length) return
  sending.value = true
  saveMessage.value = null
  saveError.value = null
  const image = lastPreview.value
  const results = await Promise.all(chosen.map(async (t) => {
    try {
      const res = await fetch(`${apiBase}/api/media-server/send-thumb-art`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rating_key: t.rating_key,
          server_id: t.server_id,
          image_data: image,
          is_tv: isTv.value,
          notify: false,
        }),
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `HTTP ${res.status}`)
      }
      return { serverId: t.server_id, ok: true, message: '' }
    } catch (e: unknown) {
      return { serverId: t.server_id, ok: false, message: e instanceof Error ? e.message : 'Send failed' }
    }
  }))
  const sent = results.filter(r => r.ok).map(r => r.serverId)
  const failed = results.filter(r => !r.ok)
  if (sent.length) {
    notifySendSummary({
      ratingKey: props.item.key,
      serverIds: sent,
      assets: ['thumb_art'],
      templateId: selectedTemplate.value,
      presetId: selectedPreset.value,
      libraryId: props.item.library_id,
      title: props.item.title,
      year: props.item.year,
      imageData: image,
    })
    saveMessage.value = `Sent Thumb Art to ${sent.map(labelFor).join(', ')}.`
    currentFailed.value = false
    currentForceRefresh.value = false
    currentRefreshToken.value = Date.now()
    emit('updated')
  }
  if (failed.length) {
    saveError.value = failed.map(f => `${labelFor(f.serverId)}: ${f.message}`).join(' · ')
  }
  sending.value = false
}

watch([selectedTemplate, selectedPreset, selectedBackdropUrl, selectedLogoUrl], () => {
  if (canRender.value) doPreview()
})

// Sliders fire many rapid changes -- debounce like the other editors (400ms).
let sliderDebounce: ReturnType<typeof setTimeout> | null = null
watch([posterShiftY, logoScale], () => {
  if (sliderDebounce) clearTimeout(sliderDebounce)
  sliderDebounce = setTimeout(() => {
    if (canRender.value) doPreview()
  }, 400)
})

onMounted(async () => {
  await Promise.all([loadPresets(), loadCandidates()])
  if (canRender.value) await doPreview()
})
</script>

<template>
  <Teleport to="body">
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal-panel">
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
        <div class="section">
          <div class="section-label">
            <span>Current Thumb Art<template v-if="viewing"> (in {{ labelFor(viewing.server_id) }})</template></span>
            <span v-if="targets.length > 1" class="server-toggle">
              <button class="refresh-btn" title="Previous server" @click="cycleViewing(-1)">‹</button>
              <button class="refresh-btn" title="Next server" @click="cycleViewing(1)">›</button>
            </span>
            <button class="refresh-btn" title="Check the server for its current Thumb Art" @click="refreshCurrent">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
          </div>
          <div class="current-square-art-area">
            <img
              v-if="viewing && !currentFailed"
              :src="currentSrc"
              :alt="`Current Thumb Art for ${item.title}`"
              class="current-square-art-img"
              @error="currentFailed = true"
            />
            <div v-else class="no-current">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
                <rect x="2" y="5" width="20" height="14" rx="2"/>
                <path d="M2 11l4-4 4 4 4-4 4 4"/>
              </svg>
              <span>No Thumb Art yet</span>
            </div>
          </div>
        </div>

        <div v-if="loadingCandidates" class="feedback">Loading backdrop/logo candidates from TMDb/Fanart…</div>
        <div v-else-if="candidatesError" class="feedback error">{{ candidatesError }}</div>

        <template v-else>
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

          <div class="main-row">
            <div class="preview-column">
              <div class="preview-area">
                <img v-if="lastPreview" :src="lastPreview" alt="Thumb Art preview" class="preview-img" />
                <div v-else-if="previewLoading" class="preview-loading">Rendering…</div>
                <div v-else class="preview-empty">Pick a backdrop to preview</div>
                <div v-if="previewLoading && lastPreview" class="preview-loading-overlay">Rendering…</div>
              </div>
              <div class="slider-pair">
                <div class="poster-shift-control">
                  <label>Backdrop Position (Up/Down)</label>
                  <div class="slider-row">
                    <input v-model.number="posterShiftY" type="range" min="-50" max="50" />
                    <input v-model.number="posterShiftY" type="number" min="-50" max="50" class="slider-num" />
                  </div>
                </div>
                <div class="poster-shift-control">
                  <label>Logo Size %</label>
                  <div class="slider-row">
                    <input v-model.number="logoScale" type="range" min="50" max="300" step="5" />
                    <input v-model.number="logoScale" type="number" min="50" max="300" class="slider-num" />
                  </div>
                </div>
              </div>
            </div>

            <div class="picker-column">
              <div class="section">
                <div class="section-label">
                  <span>Backdrop ({{ filteredBackdrops.length }})</span>
                  <select v-model="backdropTextFilter" class="mini-select">
                    <option value="all">All</option>
                    <option value="textless">Textless</option>
                    <option value="text">Has Text</option>
                  </select>
                </div>
                <div class="poster-grid">
                  <div
                    v-for="p in filteredBackdrops"
                    :key="p.url"
                    class="poster-thumb"
                    :class="{ active: selectedBackdropUrl === p.url }"
                    @click="selectedBackdropUrl = p.url"
                  >
                    <img :src="thumbSrc(p)" :alt="p.source" @error="onThumbError(p)" />
                    <div v-if="p.has_text === false" class="textless-badge">Textless</div>
                  </div>
                  <div v-if="!filteredBackdrops.length" class="section-empty">No backdrops match this filter.</div>
                </div>
              </div>

              <div class="section">
                <div class="section-label">Logo ({{ availableLogos.length }})</div>
                <div class="logo-grid">
                  <div class="logo-thumb no-logo" :class="{ active: selectedLogoUrl === null }" @click="selectedLogoUrl = null">
                    No Logo
                  </div>
                  <div
                    v-for="l in availableLogos"
                    :key="l.url"
                    class="logo-thumb"
                    :class="{ active: selectedLogoUrl === l.url }"
                    @click="selectedLogoUrl = l.url"
                  >
                    <img :src="thumbSrc(l)" :alt="l.source" @error="onThumbError(l)" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="section-note">
            Renders this title's template/preset on a 16:9 canvas with the backdrop and logo you
            pick, then sends it to Jellyfin/Emby's Thumb image (separate from the poster and
            backdrop, so neither is overwritten). Plex has no Thumb slot.
          </div>
        </template>

        <div v-if="previewError" class="feedback error">{{ previewError }}</div>
        <div v-if="saveError" class="feedback error">{{ saveError }}</div>
        <div v-if="saveMessage" class="feedback success">{{ saveMessage }}</div>
      </div>

      <div class="modal-footer">
        <button class="btn-cancel" @click="emit('close')" :disabled="saving || sending">Close</button>
        <button class="btn-cancel" :disabled="!canRender || saving" @click="doSaveToDisk">
          <svg v-if="saving" class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M21 12a9 9 0 11-6.219-8.56"/>
          </svg>
          {{ saving ? 'Saving…' : '💾 Save to Disk' }}
        </button>
        <button class="btn-send" :disabled="!lastPreview || sending || !targets.length" @click="onSendClick">
          <svg v-if="sending" class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M21 12a9 9 0 11-6.219-8.56"/>
          </svg>
          {{ sending ? 'Sending…' : (targets.length === 1 ? `Send to ${labelFor(targets[0]!.server_id)}` : 'Send to Media Server') }}
        </button>
      </div>
    </div>
  </div>

  <SendToServerModal
    v-if="showSendModal"
    :options="serverOptions"
    hint="Choose which server(s) to send this Thumb Art to."
    @close="showSendModal = false"
    @send="onSendModalConfirm"
  />
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
  max-width: 760px;
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
  gap: 14px;
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

.main-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.preview-column {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.preview-area {
  position: relative;
  background: #0a0b12;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  aspect-ratio: 1 / 1;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.poster-shift-control {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.poster-shift-control label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6b7a99;
}

.poster-shift-control .slider-row {
  display: grid;
  grid-template-columns: 1fr 56px;
  gap: 8px;
  align-items: center;
}

.poster-shift-control input[type='range'] {
  width: 100%;
  accent-color: var(--accent, #3dd6b7);
}

.poster-shift-control .slider-num {
  width: 100%;
  padding: 5px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  font-size: 12px;
  text-align: center;
}

.preview-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.preview-loading, .preview-empty {
  color: #6b7a99;
  font-size: 13px;
  text-align: center;
  padding: 0 16px;
}

.preview-loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #eef2ff;
  font-size: 13px;
}

.picker-column {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.section-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6b7a99;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.refresh-btn {
  background: none;
  border: none;
  color: #6b7a99;
  cursor: pointer;
  padding: 3px;
  border-radius: 5px;
  display: flex;
  transition: color 0.15s;
}
.refresh-btn:hover { color: #eef2ff; }

.mini-select {
  padding: 2px 6px;
  font-size: 10px;
  text-transform: none;
  letter-spacing: normal;
  font-weight: 500;
  border-radius: 5px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #c9d1e0;
  cursor: pointer;
  outline: none;
}

.section-empty {
  grid-column: 1 / -1;
  color: #4a5568;
  font-size: 12px;
  padding: 4px 0;
}

.current-square-art-area {
  background: #0a0b12;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  aspect-ratio: 1 / 1;
  width: 140px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.current-square-art-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.no-current {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: rgba(255, 255, 255, 0.25);
  font-size: 11px;
  text-align: center;
  padding: 0 8px;
}

.poster-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(64px, 1fr));
  gap: 8px;
  max-height: 150px;
  overflow-y: auto;
}

.poster-thumb {
  position: relative;
  aspect-ratio: 2 / 3;
  background: #0a0b12;
  border: 2px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  cursor: pointer;
  overflow: hidden;
  transition: border-color 0.15s, transform 0.1s;
}
.poster-thumb:hover { border-color: rgba(61, 214, 183, 0.35); }
.poster-thumb.active { border-color: var(--accent, #3dd6b7); }
.poster-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }

.textless-badge {
  position: absolute;
  bottom: 2px;
  left: 2px;
  right: 2px;
  font-size: 8px;
  font-weight: 700;
  text-align: center;
  color: #0a0b12;
  background: var(--accent, #3dd6b7);
  border-radius: 3px;
  padding: 1px 2px;
}

.logo-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 100px;
  overflow-y: auto;
}

.logo-thumb {
  position: relative;
  background: #0a0b12;
  border: 2px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  padding: 6px 10px;
  cursor: pointer;
  transition: border-color 0.15s;
  min-width: 60px;
  min-height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.logo-thumb:hover { border-color: rgba(61, 214, 183, 0.35); }
.logo-thumb.active { border-color: var(--accent, #3dd6b7); }
.logo-thumb img { max-height: 28px; max-width: 100px; object-fit: contain; display: block; }
.logo-thumb.no-logo { font-size: 11px; color: #6b7a99; }

.section-note {
  font-size: 12px;
  color: #6b7a99;
  line-height: 1.5;
}

.feedback {
  font-size: 13px;
  padding: 10px 14px;
  border-radius: 8px;
  color: #a8b3cf;
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

@media (max-width: 640px) {
  .main-row {
    flex-direction: column;
  }
  .preview-column {
    width: 100%;
  }
}

/* Thumb Art: landscape layout -- full-width 16:9 preview on top, pickers below. */
.modal-panel { max-width: 880px; }
.main-row { flex-direction: column; }
.preview-column { width: 100%; }
.preview-area { aspect-ratio: 16 / 9; }
.current-square-art-area { aspect-ratio: 16 / 9; width: 240px; }
.poster-grid { grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); max-height: 180px; }
.poster-thumb { aspect-ratio: 16 / 9; }
.slider-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.server-toggle { display: inline-flex; gap: 2px; margin-left: auto; }
@media (max-width: 640px) {
  .slider-pair { grid-template-columns: 1fr; }
}
</style>
