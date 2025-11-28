<script setup lang="ts">
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
      options.value.posterZoom = Math.round((o.poster_zoom ?? 1) * 100)
      options.value.posterShiftY = Math.round((o.poster_shift_y ?? 0) * 100)
      options.value.matteHeight = Math.round((o.matte_height_ratio ?? 0) * 100)
      options.value.fadeHeight = Math.round((o.fade_height_ratio ?? 0) * 100)
      options.value.vignette = Math.round((o.vignette_strength ?? 0) * 100)
      options.value.grain = Math.round((o.grain_amount ?? 0) * 100)
      options.value.logoScale = Math.round((o.logo_scale ?? 0.5) * 100)
      options.value.logoOffset = Math.round((o.logo_offset ?? 0.75) * 100)
      options.value.borderEnabled = !!o.border_enabled
      options.value.borderThickness = o.border_px ?? 0
      if (o.border_color) options.value.borderColor = o.border_color
      if (o.overlay_file) options.value.overlayFile = o.overlay_file
      if (typeof o.overlay_opacity === 'number') options.value.overlayOpacity = Math.round(o.overlay_opacity * 100)
      if (o.overlay_mode) options.value.overlayMode = o.overlay_mode
      if (o.poster_filter) posterFilter.value = o.poster_filter
      if (o.logo_preference) logoPreference.value = o.logo_preference
    }
  },
  { immediate: true }
)

const applyLogoPreference = () => {
  if (!logos.value.length) return
  if (logoPreference.value === 'first') {
    selectedLogo.value = logos.value[0].url
    return
  }
  // naive white/color preference: pick first where thumb endswith "white"/"color" or by heuristic
  const target = logoPreference.value === 'white' ? 'white' : 'color'
  const match = logos.value.find((l) => (l.thumb || l.url).toLowerCase().includes(target))
  selectedLogo.value = (match || logos.value[0]).url
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
          <img v-if="generatedPoster" :src="generatedPoster" class="poster-img" />
          <div v-else class="poster-placeholder">Working...</div>
        </div>

        <div class="preview-block">
          <h3>Existing Plex Poster</h3>
          <img v-if="plexPoster" :src="plexPoster" class="poster-img" />
          <div v-else class="poster-placeholder">Loading...</div>
        </div>

      </div>

      <!-- Right: Tools -->
      <div class="tools-pane">
        <slot></slot>
        <!-- Your entire tools panel goes here -->
        <EditorTools
          :movie="movie"
          :settings="settings"
          @update="updateSetting"
          @refresh="refreshPreview"
          @save="savePoster"
        />
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
</style>

