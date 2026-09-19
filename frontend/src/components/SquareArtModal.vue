<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useRenderService } from '@/services/render'
import type { MovieInput, PresetOptions } from '@/services/types'

type SquareArtItem = {
  key: string
  title: string
  year?: number | string
  poster?: string | null
  logo_url?: string | null
  square_art_url?: string | null
  tmdb_id?: number | null
  mediaType?: 'movie' | 'tv-show'
  library_id?: string | number | null
}

type PresetRecord = { id: string; name?: string; options?: PresetOptions }
type ImageSource = { url: string; thumb?: string; source?: string; has_text?: boolean }

const props = defineProps<{ item: SquareArtItem }>()
const emit = defineEmits<{ close: [] }>()

const apiBase = getApiBase()
const render = useRenderService()
// Template auto-unwrapping only applies to top-level script-setup bindings, not
// nested property access like `render.lastPreview` -- destructure to top-level
// refs, matching the established pattern in EditorPane.vue/TvShowEditorPane.vue.
const { loading: previewLoading, error: previewError, lastPreview } = render

const isTv = computed(() => props.item.mediaType === 'tv-show')

// "Current Square Art" -- what's actually cached/active in Plex right now, as
// opposed to the freshly-generated preview below. Without this there was no way
// to tell whether what Simposter would generate next actually matches what's
// already been sent, which is exactly the gap the user reported. Same plain
// <img> + @error pattern LogoEditorModal.vue/BackdropEditorModal.vue already use
// for their own "Current Logo"/"Current Backdrop" sections -- no JS pre-flight
// fetch needed, the browser's own image load either succeeds or fires @error.
const currentSquareArtFailed = ref(false)
const currentSquareArtRefreshToken = ref(0)
// Default load is local-cache-only (fast, no Plex round-trip -- matches
// LogoEditorModal/BackdropEditorModal's own default behavior). The refresh
// button below explicitly requests force_refresh=1, the one point where this
// actually re-checks Plex live rather than trusting a possibly-stale local copy.
const currentSquareArtForceRefresh = ref(false)
// Set directly from a successful send's response (which already re-caches the
// just-uploaded bytes locally) rather than re-fetching from Plex immediately
// afterward -- Plex may not have finished processing the upload yet, the exact
// race the backend's own post-upload caching already exists to avoid.
const sentSquareArtUrl = ref<string | null>(null)
const currentSquareArtSrc = computed(() => {
  if (sentSquareArtUrl.value) return `${apiBase}${sentSquareArtUrl.value}`
  const params = new URLSearchParams({ v: String(currentSquareArtRefreshToken.value) })
  if (currentSquareArtForceRefresh.value) params.set('force_refresh', '1')
  if (isTv.value) params.set('is_tv', '1')
  return `${apiBase}/api/square-art/${props.item.key}?${params.toString()}`
})

function refreshCurrentSquareArt() {
  currentSquareArtFailed.value = false
  currentSquareArtForceRefresh.value = true
  sentSquareArtUrl.value = null
  currentSquareArtRefreshToken.value = Date.now()
}

// Square Art deliberately reuses the SAME template/preset system as the normal
// editor -- it's not a new template_id, just options.canvas_mode = 'square' sent
// at render time (see backend/templates/canvas.py). Loaded independently here
// rather than through the shared presets.ts composable, since that one only ever
// tracks a single "currently selected" template/preset for the main editor and
// this modal shouldn't perturb that shared state.
// Kometa is a collections-only template (see CLAUDE.md Quirk #21) -- Square Art
// only ever operates on movies/TV items, never collections, so it must never
// appear as a selectable option here regardless of what presets.json lists.
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
        selectedTemplate.value = tplKeys[0]
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

// Vertical poster position (-50..50%, matching EditorPane.vue's "Poster Shift Y %"
// slider exactly -- same existing backend option, poster_shift_y, just exposed here
// too). A square crop throws away much more of a 2:3 poster's height than the
// normal canvas does, so being able to recenter which part of the source image
// survives the crop matters more here than it does for a normal poster.
// Re-seeded from the newly-selected preset's own saved value whenever the
// template/preset changes, then freely overridable by the user afterward.
const posterShiftY = ref(0)
watch(selectedPreset, () => {
  const preset = availablePresets.value.find((p) => p.id === selectedPreset.value)
  posterShiftY.value = Math.round((Number(preset?.options?.poster_shift_y) || 0) * 100)
})

// ---------------------------------------------------------------------------
// Poster/logo candidates -- deliberately sourced from TMDb/Fanart, NOT from
// item.poster/item.logo_url. Plex's "current poster" for a Simposter-managed
// library is usually already a Simposter-rendered poster (background + logo
// already composited together) -- squashing THAT into a square canvas and then
// compositing another logo on top of it produces a broken double-composited
// result. Same reasoning EditorPane.vue already follows: its background is
// always a raw TMDb/Fanart candidate, never the already-rendered Plex poster.
// ---------------------------------------------------------------------------
const resolvedTmdbId = ref<number | null>(props.item.tmdb_id ?? null)
const availablePosters = ref<ImageSource[]>([])
const availableLogos = ref<ImageSource[]>([])
const selectedPosterUrl = ref<string | null>(null)
const selectedLogoUrl = ref<string | null>(null)
const loadingCandidates = ref(false)
const candidatesError = ref<string | null>(null)

// A square crop is much less forgiving of a poster with baked-in title text than
// the normal 2:3 canvas is (see the poster-shift bug fix note) -- being able to
// filter down to just textless candidates (or just text ones, for a title with
// few textless options) makes picking a good source image faster.
const posterTextFilter = ref<'all' | 'textless' | 'text'>('all')
const filteredPosters = computed(() => {
  if (posterTextFilter.value === 'textless') return availablePosters.value.filter((p) => p.has_text === false)
  if (posterTextFilter.value === 'text') return availablePosters.value.filter((p) => p.has_text === true)
  return availablePosters.value
})

// TMDb serves `thumb` as a resized w300 PNG and `url` as the original file -- for
// SVG-sourced or newly-added images, the resized thumbnail variant can 404 (a known
// TMDb CDN propagation quirk) even though the original loads fine. Same fallback
// pattern already established in LogoEditorModal.vue/BackdropEditorModal.vue.
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
      candidatesError.value = 'No TMDb match found for this title — cannot fetch poster/logo candidates.'
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
    availablePosters.value = data.posters || []
    availableLogos.value = (data.logos || []).filter((l: ImageSource) => {
      const url = (l.url || '').toLowerCase()
      return !url.endsWith('.svg') && !url.includes('.svg?')
    })

    if (!availablePosters.value.length) {
      candidatesError.value = 'No posters found on TMDb/Fanart for this title.'
      return
    }

    // Default to a textless poster if one exists (best square-art candidate --
    // no baked-in title text to fight with the template's own text/logo), else
    // just the first candidate.
    const textless = availablePosters.value.find((p) => p.has_text === false)
    selectedPosterUrl.value = (textless || availablePosters.value[0]).url
    selectedLogoUrl.value = availableLogos.value[0]?.url || null
  } catch (e: unknown) {
    candidatesError.value = e instanceof Error ? e.message : 'Failed to load poster/logo candidates.'
  } finally {
    loadingCandidates.value = false
  }
}

function selectPoster(url: string) {
  selectedPosterUrl.value = url
}
function selectLogo(url: string | null) {
  selectedLogoUrl.value = url
}

// These are already absolute, publicly-reachable TMDb/Fanart CDN URLs -- unlike
// the old item.poster/item.logo_url (relative internal cache paths that needed
// the app's own origin prefixed before the backend could fetch them back from
// itself), no apiBase prefixing is needed here.
const bgUrl = computed(() => selectedPosterUrl.value || '')
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
  return { ...(preset?.options || {}), canvas_mode: 'square', poster_shift_y: posterShiftY.value / 100 }
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
      // Deliberately a different filename than the normal poster so this never
      // overwrites the item's regular saved poster -- lands alongside it.
      filename: 'square-art.jpg',
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
    saveError.value = e instanceof Error ? e.message : 'Failed to save square art'
  } finally {
    saving.value = false
  }
}

const sendingToPlex = ref(false)

async function doSendToPlex() {
  // Plex's squareArts slot is genuinely separate from the regular poster and
  // background/art (confirmed against python-plexapi's SquareArtMixin source),
  // so this can't overwrite either of those -- unlike the earlier assumption
  // that sending square art meant reusing one of the two existing slots.
  if (!lastPreview.value) {
    saveError.value = 'Render a preview first.'
    return
  }
  sendingToPlex.value = true
  saveMessage.value = null
  saveError.value = null
  try {
    const res = await fetch(`${apiBase}/api/plex/send-square-art`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rating_key: props.item.key,
        art_data: lastPreview.value,
        is_tv: isTv.value,
        is_collection: false,
        library_id: props.item.library_id != null ? String(props.item.library_id) : null,
      }),
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text || `HTTP ${res.status}`)
    }
    const data = await res.json().catch(() => ({}))
    if (typeof data.square_art_url === 'string') {
      sentSquareArtUrl.value = data.square_art_url
      currentSquareArtFailed.value = false
    }
    saveMessage.value = 'Sent to Plex (square art slot).'
  } catch (e: unknown) {
    saveError.value = e instanceof Error ? e.message : 'Failed to send square art to Plex'
  } finally {
    sendingToPlex.value = false
  }
}

watch([selectedTemplate, selectedPreset, selectedPosterUrl, selectedLogoUrl], () => {
  if (canRender.value) doPreview()
})

// posterShiftY is dragged via a range slider (many rapid changes), unlike the
// discrete click-based selections above -- debounce it the same way EditorPane.vue
// debounces its own slider-driven preview re-renders (400ms).
let posterShiftDebounce: ReturnType<typeof setTimeout> | null = null
watch(posterShiftY, () => {
  if (posterShiftDebounce) clearTimeout(posterShiftDebounce)
  posterShiftDebounce = setTimeout(() => {
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
            Current Square Art (in Plex)
            <button class="refresh-btn" title="Check Plex for the currently active square art" @click="refreshCurrentSquareArt">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
          </div>
          <div class="current-square-art-area">
            <img
              v-if="!currentSquareArtFailed"
              :src="currentSquareArtSrc"
              :alt="`Current square art for ${item.title}`"
              class="current-square-art-img"
              @error="currentSquareArtFailed = true"
            />
            <div v-else class="no-current">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <path d="M3 9l4-4 4 4 4-4 4 4"/>
              </svg>
              <span>No square art in Plex yet</span>
            </div>
          </div>
        </div>

        <div v-if="loadingCandidates" class="feedback">Loading poster/logo candidates from TMDb/Fanart…</div>
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
                <img v-if="lastPreview" :src="lastPreview" alt="Square art preview" class="preview-img" />
                <div v-else-if="previewLoading" class="preview-loading">Rendering…</div>
                <div v-else class="preview-empty">Pick a poster to preview</div>
                <div v-if="previewLoading && lastPreview" class="preview-loading-overlay">Rendering…</div>
              </div>
              <div class="poster-shift-control">
                <label>Poster Position (Up/Down)</label>
                <div class="slider-row">
                  <input v-model.number="posterShiftY" type="range" min="-50" max="50" />
                  <input v-model.number="posterShiftY" type="number" min="-50" max="50" class="slider-num" />
                </div>
              </div>
            </div>

            <div class="picker-column">
              <div class="section">
                <div class="section-label">
                  <span>Poster ({{ filteredPosters.length }})</span>
                  <select v-model="posterTextFilter" class="mini-select">
                    <option value="all">All</option>
                    <option value="textless">Textless</option>
                    <option value="text">Has Text</option>
                  </select>
                </div>
                <div class="poster-grid">
                  <div
                    v-for="p in filteredPosters"
                    :key="p.url"
                    class="poster-thumb"
                    :class="{ active: selectedPosterUrl === p.url }"
                    @click="selectPoster(p.url)"
                  >
                    <img :src="thumbSrc(p)" :alt="p.source" @error="onThumbError(p)" />
                    <div v-if="p.has_text === false" class="textless-badge">Textless</div>
                  </div>
                  <div v-if="!filteredPosters.length" class="section-empty">No posters match this filter.</div>
                </div>
              </div>

              <div class="section">
                <div class="section-label">Logo ({{ availableLogos.length }})</div>
                <div class="logo-grid">
                  <div class="logo-thumb no-logo" :class="{ active: selectedLogoUrl === null }" @click="selectLogo(null)">
                    No Logo
                  </div>
                  <div
                    v-for="l in availableLogos"
                    :key="l.url"
                    class="logo-thumb"
                    :class="{ active: selectedLogoUrl === l.url }"
                    @click="selectLogo(l.url)"
                  >
                    <img :src="thumbSrc(l)" :alt="l.source" @error="onThumbError(l)" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="section-note">
            Renders this title's existing template/preset against a square (1:1) canvas, using
            the poster/logo you pick above. Sends to Plex's dedicated square art slot (separate
            from the regular poster and background/art — sending it won't overwrite either),
            and/or saves a copy to disk for use with an external tool or client.
          </div>
        </template>

        <div v-if="previewError" class="feedback error">{{ previewError }}</div>
        <div v-if="saveError" class="feedback error">{{ saveError }}</div>
        <div v-if="saveMessage" class="feedback success">{{ saveMessage }}</div>
      </div>

      <div class="modal-footer">
        <button class="btn-cancel" @click="emit('close')" :disabled="saving || sendingToPlex">Close</button>
        <button class="btn-cancel" :disabled="!canRender || saving" @click="doSaveToDisk">
          <svg v-if="saving" class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M21 12a9 9 0 11-6.219-8.56"/>
          </svg>
          {{ saving ? 'Saving…' : '💾 Save to Disk' }}
        </button>
        <button class="btn-send" :disabled="!lastPreview || sendingToPlex" @click="doSendToPlex">
          <svg v-if="sendingToPlex" class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M21 12a9 9 0 11-6.219-8.56"/>
          </svg>
          {{ sendingToPlex ? 'Sending…' : '📺 Send to Plex' }}
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
</style>
