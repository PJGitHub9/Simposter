<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-unused-vars */
import { computed, onMounted, ref, watch } from 'vue'
import type { MovieInput } from '../../services/types'
import { useRenderService } from '../../services/render'
import { usePresetService } from '../../services/presets'

type Poster = { url: string; thumb?: string; has_text?: boolean }
type Logo = { url: string; thumb?: string; color?: string }

const props = defineProps<{ movie: MovieInput }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const apiBase = import.meta.env.VITE_API_URL || window.location.origin

const tmdbId = ref<number | null>(null)
const posters = ref<Poster[]>([])
const logos = ref<Logo[]>([])
const labels = ref<string[]>([])
const selectedLabels = ref<Set<string>>(new Set())
const existingPoster = ref<string | null>(null)

const posterFilter = ref<'all' | 'textless' | 'text'>('all')
const logoPreference = ref<'first' | 'white' | 'color'>('first')
const logoMode = ref<'original' | 'match' | 'hex'>('original')
const logoHex = ref('#ffffff')

const selectedPoster = ref<string | null>(null)
const selectedLogo = ref<string | null>(null)

const options = ref({
  posterZoom: 100,
  posterShiftY: 0,
  matteHeight: 0,
  fadeHeight: 0,
  vignette: 0,
  grain: 0,
  logoScale: 50,
  logoOffset: 75,
  borderEnabled: false,
  borderThickness: 0,
  borderColor: '#ffffff',
  overlayFile: '',
  overlayOpacity: 40,
  overlayMode: 'screen'
})

const render = useRenderService()
const loading = render.loading
const error = render.error
const lastPreview = render.lastPreview

const filteredPosters = computed(() => {
  if (posterFilter.value === 'textless') return posters.value.filter((p) => p.has_text === false)
  if (posterFilter.value === 'text') return posters.value.filter((p) => p.has_text === true)
  return posters.value
})

const filteredLogos = computed(() => logos.value)

const optionsPayload = computed(() => ({
  poster_zoom: options.value.posterZoom / 100,
  poster_shift_y: options.value.posterShiftY / 100,
  matte_height_ratio: options.value.matteHeight / 100,
  fade_height_ratio: options.value.fadeHeight / 100,
  vignette_strength: options.value.vignette / 100,
  grain_amount: options.value.grain / 100,
  logo_scale: options.value.logoScale / 100,
  logo_offset: options.value.logoOffset / 100,
  border_enabled: options.value.borderEnabled,
  border_px: options.value.borderThickness,
  border_color: options.value.borderColor,
  overlay_file: options.value.overlayFile || null,
  overlay_opacity: options.value.overlayOpacity / 100,
  overlay_mode: options.value.overlayMode,
  logo_mode: logoMode.value,
  logo_hex: logoHex.value,
  poster_filter: posterFilter.value,
  logo_preference: logoPreference.value
}))

const bgUrl = computed(() => selectedPoster.value || props.movie.poster || '')
const logoUrl = computed(() => selectedLogo.value || '')

// Presets / templates
const presetService = usePresetService()
const templates = presetService.templates
const presets = presetService.presets
const selectedTemplate = presetService.selectedTemplate
const selectedPreset = presetService.selectedPreset

watch(
  selectedPreset,
  (id) => {
    const p = presets.value.find((x) => x.id === id)
    if (p?.options) {
      // try to map known options
      const o = p.options
      options.value.posterZoom = Math.round((Number(o.poster_zoom) || 1) * 100)
      options.value.posterShiftY = Math.round((Number(o.poster_shift_y) || 0) * 100)
      options.value.matteHeight = Math.round((Number(o.matte_height_ratio) || 0) * 100)
      options.value.fadeHeight = Math.round((Number(o.fade_height_ratio) || 0) * 100)
      options.value.vignette = Math.round((Number(o.vignette_strength) || 0) * 100)
      options.value.grain = Math.round((Number(o.grain_amount) || 0) * 100)
      options.value.logoScale = Math.round((Number(o.logo_scale) || 0.5) * 100)
      options.value.logoOffset = Math.round((Number(o.logo_offset) || 0.75) * 100)
      options.value.borderEnabled = !!o.border_enabled
      options.value.borderThickness = Number(o.border_px) || 0
      if (o.border_color) options.value.borderColor = String(o.border_color)
      if (o.overlay_file) options.value.overlayFile = String(o.overlay_file)
      if (typeof o.overlay_opacity === 'number') options.value.overlayOpacity = Math.round(o.overlay_opacity * 100)
      if (o.overlay_mode) options.value.overlayMode = String(o.overlay_mode)
      if (typeof o.poster_filter === 'string' && ['all', 'textless', 'text'].includes(o.poster_filter)) {
        posterFilter.value = o.poster_filter as 'all' | 'textless' | 'text'
      }
      if (typeof o.logo_preference === 'string' && ['first', 'white', 'color'].includes(o.logo_preference)) {
        logoPreference.value = o.logo_preference as 'first' | 'white' | 'color'
      }
    }
  },
  { immediate: true }
)

const applyLogoPreference = () => {
  if (!logos.value.length) return
  if (logoPreference.value === 'first') {
    const firstLogo = logos.value[0]
    if (firstLogo) selectedLogo.value = firstLogo.url
    return
  }
  // naive white/color preference: pick first where thumb endswith "white"/"color" or by heuristic
  const target = logoPreference.value === 'white' ? 'white' : 'color'
  const match = logos.value.find((l) => (l.thumb || l.url).toLowerCase().includes(target))
  const fallback = logos.value[0]
  if (match) selectedLogo.value = match.url
  else if (fallback) selectedLogo.value = fallback.url
}

const fetchTmdbAssets = async () => {
  posters.value = []
  logos.value = []
  selectedPoster.value = props.movie.poster || null
  selectedLogo.value = null
  try {
    const tmdbRes = await fetch(`${apiBase}/api/movie/${props.movie.key}/tmdb`)
    const tmdb = await tmdbRes.json()
    tmdbId.value = tmdb.tmdb_id || null
    if (!tmdbId.value) return
    const imgRes = await fetch(`${apiBase}/api/tmdb/${tmdbId.value}/images`)
    const imgs = await imgRes.json()
    posters.value = imgs.posters || []
    logos.value = imgs.logos || []
    applyLogoPreference()
  } catch (e) {
    console.error(e)
  }
}

const fetchLabels = async () => {
  try {
    const res = await fetch(`${apiBase}/api/movie/${props.movie.key}/labels`)
    if (!res.ok) return
    const data = await res.json()
    labels.value = data.labels || []
    selectedLabels.value = new Set(labels.value)
  } catch (e) {
    console.error(e)
  }
}

const toggleLabel = (label: string) => {
  const set = new Set(selectedLabels.value)
  if (set.has(label)) set.delete(label)
  else set.add(label)
  selectedLabels.value = set
}

const fetchExistingPoster = async () => {
  try {
    const res = await fetch(`${apiBase}/api/movie/${props.movie.key}/poster`)
    const data = await res.json()
    existingPoster.value = data.url || null
  } catch {
    existingPoster.value = null
  }
}

const doPreview = async () => {
  if (!bgUrl.value) return

  console.log("Preview Payload:", {
    templateId: selectedTemplate.value,
    presetId: selectedPreset.value,
    options: optionsPayload.value
  })

  await render.preview(
    props.movie,
    bgUrl.value,
    logoUrl.value || null,
    optionsPayload.value,
    selectedTemplate.value,
    selectedPreset.value || 'default'
  )
}


const doSave = async () => {
  if (!bgUrl.value) return
  await render.save(
    props.movie,
    bgUrl.value,
    logoUrl.value || null,
    optionsPayload.value,
    selectedTemplate.value,
    selectedPreset.value || 'default'
  )
}

const doSend = async () => {
  if (!bgUrl.value) return
  await render.send(
    props.movie,
    bgUrl.value,
    logoUrl.value || null,
    optionsPayload.value,
    Array.from(selectedLabels.value),
    selectedTemplate.value,
    selectedPreset.value || 'default'
  )
}


watch(
  () => props.movie.key,
  async () => {
    await fetchTmdbAssets()
    await fetchLabels()
    await fetchExistingPoster()
    await presetService.load()
  },
  { immediate: true }
)

let previewTimer: ReturnType<typeof setTimeout> | null = null
watch(
  [bgUrl, logoUrl, options],
  () => {
    if (previewTimer) clearTimeout(previewTimer)
    previewTimer = setTimeout(() => {
      doPreview()
    }, 400)
  },
  { deep: true }
)
</script>

<template>
  <div class="editor-fullscreen">
    <!-- Header -->
    <div class="editor-header">
      <button class="back-btn" @click="$emit('close')">← Back</button>
      <div class="title">{{ movie.title }} ({{ movie.year }})</div>
    </div>

    <!-- Main editing area -->
    <div class="editor-body">
      <!-- Left: Previews -->
      <div class="preview-pane">

        <div class="preview-block">
          <h3>Generated Preview</h3>
          <img v-if="lastPreview" :src="lastPreview" class="poster-img" />
          <div v-else-if="loading" class="poster-placeholder">Generating...</div>
          <div v-else class="poster-placeholder">No preview yet</div>
        </div>

        <div class="preview-block">
          <h3>Existing Plex Poster</h3>
          <img v-if="existingPoster" :src="existingPoster" class="poster-img" />
          <div v-else class="poster-placeholder">No poster</div>
        </div>

      </div>

      <!-- Right: Tools -->
      <div class="tools-pane">
        <!-- Template Selection -->
        <div class="section">
          <h3>Template</h3>
          <select v-model="selectedTemplate" class="select-input">
            <option v-for="t in templates" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>

        <!-- Preset Selection -->
        <div class="section">
          <h3>Preset</h3>
          <select v-model="selectedPreset" class="select-input">
            <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name || p.id }}</option>
          </select>
        </div>

        <!-- Poster Selection -->
        <div class="section">
          <h3>Posters</h3>
          <div class="filter-tabs">
            <button
              :class="{ active: posterFilter === 'all' }"
              @click="posterFilter = 'all'"
            >All</button>
            <button
              :class="{ active: posterFilter === 'textless' }"
              @click="posterFilter = 'textless'"
            >Textless</button>
            <button
              :class="{ active: posterFilter === 'text' }"
              @click="posterFilter = 'text'"
            >With Text</button>
          </div>
          <div class="thumbnail-grid">
            <img
              v-for="p in filteredPosters"
              :key="p.url"
              :src="p.thumb || p.url"
              :class="{ selected: selectedPoster === p.url }"
              @click="selectedPoster = p.url"
              class="thumbnail"
            />
          </div>
        </div>

        <!-- Logo Selection -->
        <div class="section">
          <h3>Logos</h3>
          <div class="filter-tabs">
            <button
              :class="{ active: logoPreference === 'first' }"
              @click="logoPreference = 'first'; applyLogoPreference()"
            >First</button>
            <button
              :class="{ active: logoPreference === 'white' }"
              @click="logoPreference = 'white'; applyLogoPreference()"
            >White</button>
            <button
              :class="{ active: logoPreference === 'color' }"
              @click="logoPreference = 'color'; applyLogoPreference()"
            >Color</button>
          </div>
          <div class="thumbnail-grid">
            <img
              v-for="l in filteredLogos"
              :key="l.url"
              :src="l.thumb || l.url"
              :class="{ selected: selectedLogo === l.url }"
              @click="selectedLogo = l.url"
              class="thumbnail logo-thumb"
            />
          </div>
        </div>

        <!-- Options -->
        <div class="section">
          <h3>Options</h3>

          <label>Poster Zoom: {{ options.posterZoom }}%</label>
          <input type="range" v-model.number="options.posterZoom" min="50" max="200" />

          <label>Poster Shift Y: {{ options.posterShiftY }}%</label>
          <input type="range" v-model.number="options.posterShiftY" min="-50" max="50" />

          <label>Matte Height: {{ options.matteHeight }}%</label>
          <input type="range" v-model.number="options.matteHeight" min="0" max="100" />

          <label>Fade Height: {{ options.fadeHeight }}%</label>
          <input type="range" v-model.number="options.fadeHeight" min="0" max="100" />

          <label>Vignette: {{ options.vignette }}%</label>
          <input type="range" v-model.number="options.vignette" min="0" max="100" />

          <label>Grain: {{ options.grain }}%</label>
          <input type="range" v-model.number="options.grain" min="0" max="100" />

          <label>Logo Scale: {{ options.logoScale }}%</label>
          <input type="range" v-model.number="options.logoScale" min="0" max="100" />

          <label>Logo Offset: {{ options.logoOffset }}%</label>
          <input type="range" v-model.number="options.logoOffset" min="0" max="100" />
        </div>

        <!-- Labels -->
        <div class="section" v-if="labels.length">
          <h3>Labels</h3>
          <div class="label-chips">
            <button
              v-for="label in labels"
              :key="label"
              :class="{ active: selectedLabels.has(label) }"
              @click="toggleLabel(label)"
              class="label-chip"
            >{{ label }}</button>
          </div>
        </div>

        <!-- Actions -->
        <div class="section actions">
          <button @click="doPreview" :disabled="loading" class="btn btn-primary">
            {{ loading ? 'Generating...' : 'Preview' }}
          </button>
          <button @click="doSave" :disabled="loading" class="btn btn-secondary">Save</button>
          <button @click="doSend" :disabled="loading" class="btn btn-secondary">Send to Plex</button>
        </div>

        <div v-if="error" class="error-message">{{ error }}</div>
      </div>
    </div>
  </div>
</template>


<style scoped>
.editor-fullscreen {
  width: 100%;
  height: calc(100vh - 60px); /* subtract top nav height */
  display: flex;
  flex-direction: column;
  background: #0d0f16;
  padding: 12px;
}

.editor-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-bottom: 10px;
}

.back-btn {
  background: #1a1d27;
  padding: 8px 14px;
  border-radius: 6px;
  color: white;
  border: none;
  cursor: pointer;
}

.title {
  font-size: 20px;
  font-weight: 700;
}

.editor-body {
  flex: 1;
  display: flex;
  gap: 20px;
  overflow: hidden;
}

/* Left side previews */
.preview-pane {
  flex: 1.2;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
}

.preview-block {
  background: #12141c;
  padding: 12px;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.poster-img {
  width: 320px;
  border-radius: 12px;
  box-shadow: 0 0 20px rgba(0,0,0,0.6);
}

.poster-placeholder {
  height: 480px;
  width: 320px;
  border-radius: 12px;
  background: #1b1e27;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.4;
}

/* Right side tools */
.tools-pane {
  width: 380px;
  background: #13151d;
  border-left: 2px solid #1e2230;
  border-radius: 12px;
  overflow-y: auto;
  padding: 20px;
}

.section {
  margin-bottom: 24px;
}

.section h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #a0a0a0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.select-input {
  width: 100%;
  background: #1a1d27;
  color: white;
  border: 1px solid #2a2d37;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 14px;
  cursor: pointer;
}

.select-input:focus {
  outline: none;
  border-color: #3b82f6;
}

.filter-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.filter-tabs button {
  flex: 1;
  background: #1a1d27;
  color: #999;
  border: 1px solid #2a2d37;
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-tabs button.active {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.thumbnail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.thumbnail {
  width: 100%;
  aspect-ratio: 2/3;
  object-fit: cover;
  border-radius: 6px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s;
}

.thumbnail:hover {
  border-color: #555;
}

.thumbnail.selected {
  border-color: #3b82f6;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.5);
}

.logo-thumb {
  aspect-ratio: 16/9;
  background: #1a1d27;
  padding: 8px;
}

.section label {
  display: block;
  font-size: 13px;
  color: #ccc;
  margin-bottom: 6px;
  margin-top: 12px;
}

.section input[type="range"] {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #2a2d37;
  outline: none;
  -webkit-appearance: none;
  appearance: none;
}

.section input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
}

.section input[type="range"]::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
  border: none;
}

.label-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.label-chip {
  background: #1a1d27;
  color: #999;
  border: 1px solid #2a2d37;
  border-radius: 16px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.label-chip.active {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.btn {
  width: 100%;
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #3b82f6;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-secondary {
  background: #1a1d27;
  color: white;
  border: 1px solid #2a2d37;
}

.btn-secondary:hover:not(:disabled) {
  background: #2a2d37;
}

.error-message {
  margin-top: 12px;
  padding: 10px;
  background: #dc2626;
  color: white;
  border-radius: 6px;
  font-size: 13px;
}
</style>
