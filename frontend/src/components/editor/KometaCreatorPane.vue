<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { MovieInput } from '../../services/types'
import { useRenderService } from '../../services/render'
import { usePresetService } from '../../services/presets'
import { useNotification } from '../../composables/useNotification'
import { useSettingsStore } from '../../stores/settings'
import { getApiBase } from '../../services/apiBase'

const props = defineProps<{ movie: MovieInput }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const apiBase = getApiBase()
const settings = useSettingsStore()

// ---------------------------------------------------------------------------
// Background — flat color + a Gradient Style dropdown matching create_poster.ps1's
// -gradient 0-4 enum (0=none, 1=center-out, 2=bottom-up, 3=top-down, 4=bottom-top).
// The original tool gets these from 5 pre-rendered bitmaps; here they're produced
// procedurally by reusing the same generic matte/fade/top-matte/top-fade/vignette
// options the Simposter Creator's Poster section already exposes (per your call
// to regenerate procedurally rather than vendor the bitmaps). Selecting a style
// just sets those underlying values to sensible defaults — the sliders stay
// visible below for fine-tuning, same as the original tool's fixed set of looks
// would need manual base_color/gradient re-runs to adjust.
// ---------------------------------------------------------------------------
const kometaBaseColor = ref('#202020')
const swatches = ['#0d0d0d', '#202020', '#1a2b3c', '#2b1a1a', '#1a2b1a', '#2b1a2b', '#3c2b1a']
const randomizeColor = () => {
  const hex = Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, '0')
  kometaBaseColor.value = `#${hex}`
}

// Background textures — real, full 2000x3000 pre-made images, referenced live
// from Kometa-Team/Defaults-Image-Creation's @base/ set (GitHub raw URLs, not
// vendored — see backend/api/uploads.py's api_list_kometa_textures() for why).
// A genuinely separate background layer (not a stand-in for the logo, which
// it was mistakenly wired to at first) — replaces the flat base color as the
// canvas rendering.py synthesizes, so a texture and a real uploaded logo
// composite together (texture underneath, logo on top), same as a logo
// already composites over a flat color.
const kometaTextures = ref<{ name: string; url: string }[]>([])
const kometaTextureUrl = ref<string | null>(null)
// Derived, not a separately-tracked ref: the textures list loads async (fetch
// in onMounted, not awaited before a preset's saved kometaTextureUrl gets
// applied), so a plain ref set once inside applyPresetOptions() would look up
// the name against a still-empty list and permanently stick at null — the
// grid's "active" highlight would never appear for a preset saved with a
// texture, even though the texture itself renders correctly (kometaTextureUrl
// is what actually feeds the render, this is display-only). A computed always
// re-resolves once kometaTextures finishes loading, no race possible.
const selectedTextureName = computed(() => kometaTextures.value.find((t) => t.url === kometaTextureUrl.value)?.name ?? null)
const chooseTexture = (texture: { name: string; url: string }) => {
  kometaTextureUrl.value = texture.url
}
const clearTexture = () => {
  kometaTextureUrl.value = null
}

type GradientStyle = 0 | 1 | 2 | 3 | 4
const gradientStyle = ref<GradientStyle>(1)
const gradientStyleOptions: { value: GradientStyle; label: string }[] = [
  { value: 0, label: 'None' },
  { value: 1, label: 'Center-Out Fade' },
  { value: 2, label: 'Bottom-Up Fade' },
  { value: 3, label: 'Top-Down Fade' },
  { value: 4, label: 'Bottom-Top Fade' },
]

const matteHeight = ref(0)
const fadeHeight = ref(0)
const topMatteHeight = ref(0)
const topFadeHeight = ref(0)
const vignette = ref(0)
const grain = ref(0)

// Applies a style's default slider values. Only fires on an explicit user
// dropdown change — `loadingPreset` is set while a preset's own saved slider
// values are being applied, so that doesn't get immediately clobbered by this.
let loadingPreset = false
const applyGradientStylePreset = (style: GradientStyle) => {
  matteHeight.value = 0
  fadeHeight.value = 0
  topMatteHeight.value = 0
  topFadeHeight.value = 0
  vignette.value = 0
  if (style === 1) {
    // _add_center_fade() (kometa.py) is calibrated against the true canvas
    // corner distance, so this reaches genuine near-black corners at ~85 —
    // not the same numeric scale as the old shared-vignette slider used to be.
    vignette.value = 85
  } else if (style === 2) {
    matteHeight.value = 15
    fadeHeight.value = 35
  } else if (style === 3) {
    topMatteHeight.value = 15
    topFadeHeight.value = 35
  } else if (style === 4) {
    matteHeight.value = 15
    fadeHeight.value = 30
    topMatteHeight.value = 15
    topFadeHeight.value = 30
  }
}
watch(gradientStyle, (style) => {
  if (loadingPreset) return
  applyGradientStylePreset(style)
})

// ---------------------------------------------------------------------------
// Logo — upload your own, or pick one from Kometa's categorized logo library
// (create_defaults/logos_chart/, logos_genre/, etc. — same live-reference
// pattern as the background textures, not vendored). Matches
// create_poster.ps1's model exactly: width-only resize (aspect preserved, no
// height cap) + a vertical-only px offset from center (+down/-up) — always
// horizontally centered, no box/x-offset concept. No drop shadow / override-
// scale mode either (see kometa.py).
// ---------------------------------------------------------------------------
const uploadedLogoUrl = ref<string | null>(null)
const logoUploading = ref(false)
const logoDropActive = ref(false)
const kometaWhiteWash = ref(false)
const kometaLogoWidth = ref(2000)
const kometaLogoOffsetY = ref(0)

const kometaLogoCategoryLabels: Record<string, string> = {
  aspect: 'Aspect Ratio', award: 'Award', chart: 'Chart / Streaming Service', content_rating: 'Content Rating',
  country: 'Country', franchise: 'Franchise', genre: 'Genre', network: 'Network', playlist: 'Playlist',
  resolution: 'Resolution', seasonal: 'Seasonal', streaming: 'Streaming Platform', studio: 'Studio',
  universe: 'Universe', video_format: 'Video Format',
}
const kometaLogoCategories = ref<string[]>([])
const selectedLogoCategory = ref<string | null>(null)
const kometaLogoOptions = ref<{ name: string; url: string }[]>([])
const kometaLogoOptionsLoading = ref(false)

const loadKometaLogoOptions = async (category: string) => {
  kometaLogoOptionsLoading.value = true
  kometaLogoOptions.value = []
  try {
    const res = await fetch(`${apiBase}/api/kometa-logos/${category}`)
    if (res.ok) {
      const data = await res.json()
      kometaLogoOptions.value = data.logos || []
    }
  } catch (e) {
    console.error('[KometaCreatorPane] Failed to load logo category:', e)
  } finally {
    kometaLogoOptionsLoading.value = false
  }
}
watch(selectedLogoCategory, (category) => {
  if (category) loadKometaLogoOptions(category)
  else kometaLogoOptions.value = []
})

const chooseKometaLogo = (logo: { name: string; url: string }) => {
  uploadedLogoUrl.value = logo.url
}

// Franchise-wide logos from Fanart.tv — same source as the Simposter Creator's
// collection logo import (see EditorPane.vue's fetchTmdbAssets): Fanart tags
// collection-wide art under the TMDb collection ID in its /v3/movies/{id}
// namespace, verified live against the LOTR collection (12 hdmovielogo +
// 3 hdmovieclearart, none belonging to any single film). This pane always
// edits a collection, so no mediaType gate is needed — fetched unconditionally
// alongside textures/logo-categories in onMounted.
const fanartCollectionLogos = ref<{ url: string; thumb?: string; language?: string; type?: string }[]>([])
const loadingFanartLogos = ref(false)

const fetchFanartCollectionLogos = async () => {
  loadingFanartLogos.value = true
  fanartCollectionLogos.value = []
  try {
    const tmdbRes = await fetch(`${apiBase}/api/collection/${props.movie.key}/tmdb`)
    if (!tmdbRes.ok) return
    const tmdb = await tmdbRes.json()
    const collectionTmdbId = tmdb.tmdb_id
    if (!collectionTmdbId) return
    const logoRes = await fetch(`${apiBase}/api/tmdb/collection/${collectionTmdbId}/fanart-logos`)
    if (!logoRes.ok) return
    const data = await logoRes.json()
    fanartCollectionLogos.value = data.logos || []
  } catch (e) {
    console.error('[KometaCreatorPane] Failed to load Fanart collection logos:', e)
  } finally {
    loadingFanartLogos.value = false
  }
}

const uploadLogoFile = async (file: File) => {
  if (!file.type.startsWith('image/')) return
  logoUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('kind', 'logo')
    const res = await fetch(`${apiBase}/api/upload/background`, { method: 'POST', body: fd })
    if (!res.ok) throw new Error('Upload failed')
    const data = await res.json()
    uploadedLogoUrl.value = `${apiBase}${data.url}`
  } catch (e) {
    console.error('[KometaCreatorPane] Logo upload failed:', e)
  } finally {
    logoUploading.value = false
  }
}
const onLogoFileInput = (e: Event) => {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) uploadLogoFile(file)
  ;(e.target as HTMLInputElement).value = ''
}
const onLogoDrop = (e: DragEvent) => {
  logoDropActive.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) uploadLogoFile(file)
}
const clearUploadedLogo = () => { uploadedLogoUrl.value = null }

// ---------------------------------------------------------------------------
// Text — matches create_poster.ps1's actual model (-text/-font/-font_color/
// -font_size/-text_offset): plain text, no per-collection template variables,
// no shadow/stroke/align/transform/letter-spacing controls. Vertical offset
// uses the same "px from center, +down/-up" idiom as the logo, converted to
// the shared text renderer's position_y (which is the text block's center
// fraction of canvas height — see universal.py's _render_text_overlay).
// ---------------------------------------------------------------------------
const textOverlayEnabled = ref(false)
const customText = ref('')
const fontFamily = ref('Arial')
const fontSize = ref(150)
const textColor = ref('#ffffff')
const textOffsetY = ref(0)
const availableFonts = ref<string[]>([])
const CANVAS_H = 3000

// ---------------------------------------------------------------------------
// Border
// ---------------------------------------------------------------------------
const borderEnabled = ref(false)
const borderThickness = ref(0)
const borderColor = ref('#ffffff')

// ---------------------------------------------------------------------------
// Preset (its own "kometa" template — see backend/templates/kometa.py for why
// this is a separate, smaller option set rather than reusing uniformlogo's)
// ---------------------------------------------------------------------------
const presetService = usePresetService()
const presets = presetService.presets
const selectedPreset = presetService.selectedPreset
const presetLoading = presetService.loading
const newPresetId = ref('')

// /api/presets only returns a template_id once at least one preset exists under
// it, so the generic usePresetService().load() (which resets selectedTemplate
// to whatever it *does* find) can't be used here — it would silently fall back
// to 'uniformlogo' until a first kometa preset is saved. Load kometa's preset
// list directly instead, always keeping selectedTemplate pinned to 'kometa'.
const loadKometaPresets = async () => {
  presetService.loading.value = true
  try {
    const res = await fetch(`${apiBase}/api/presets`)
    if (res.ok) {
      const data = await res.json()
      presets.value = data.kometa?.presets || []
    }
  } catch (e) {
    console.error('[KometaCreatorPane] Failed to load presets:', e)
  } finally {
    presetService.loading.value = false
  }
  presetService.templates.value = ['kometa']
  presetService.selectedTemplate.value = 'kometa'
  if (!presets.value.find((p) => p.id === selectedPreset.value)) {
    selectedPreset.value = presets.value[0]?.id || ''
  }
}

// Best-effort reverse mapping from loaded slider values back to a Gradient Style
// dropdown selection, purely for display — the actual render always uses the
// slider values themselves (matte/fade/etc.), not the inferred style.
const inferGradientStyle = (): GradientStyle => {
  const hasBottom = matteHeight.value > 0 || fadeHeight.value > 0
  const hasTop = topMatteHeight.value > 0 || topFadeHeight.value > 0
  const hasVignette = vignette.value > 0
  if (hasBottom && hasTop) return 4
  if (hasTop) return 3
  if (hasBottom) return 2
  if (hasVignette) return 1
  return 0
}

const applyPresetOptions = (o: Record<string, any>) => {
  loadingPreset = true
  kometaBaseColor.value = typeof o.kometa_base_color === 'string' ? o.kometa_base_color : '#202020'
  kometaWhiteWash.value = !!o.kometa_white_wash
  kometaLogoWidth.value = Number(o.kometa_logo_width) || 2000
  kometaLogoOffsetY.value = typeof o.kometa_logo_offset_y === 'number' ? Math.round(o.kometa_logo_offset_y) : 0

  kometaTextureUrl.value = typeof o.kometa_texture_url === 'string' && o.kometa_texture_url ? o.kometa_texture_url : null
  uploadedLogoUrl.value = typeof o.kometa_logo_url === 'string' && o.kometa_logo_url ? o.kometa_logo_url : null

  matteHeight.value = Math.round((Number(o.matte_height_ratio) || 0) * 100)
  fadeHeight.value = Math.round((Number(o.fade_height_ratio) || 0) * 100)
  topMatteHeight.value = Math.round((Number(o.top_matte_height_ratio) || 0) * 100)
  topFadeHeight.value = Math.round((Number(o.top_fade_height_ratio) || 0) * 100)
  vignette.value = Math.round((Number(o.kometa_center_fade_strength) || 0) * 100)
  grain.value = Math.round((Number(o.grain_amount) || 0) * 100)
  gradientStyle.value = inferGradientStyle()

  borderEnabled.value = !!o.border_enabled
  borderThickness.value = Number(o.border_px) || 0
  borderColor.value = typeof o.border_color === 'string' ? o.border_color : '#ffffff'

  textOverlayEnabled.value = !!o.text_overlay_enabled
  customText.value = typeof o.custom_text === 'string' ? o.custom_text : ''
  fontFamily.value = typeof o.font_family === 'string' ? o.font_family : 'Arial'
  fontSize.value = Number(o.font_size) || 150
  textColor.value = typeof o.text_color === 'string' ? o.text_color : '#ffffff'
  textOffsetY.value = typeof o.position_y === 'number' ? Math.round((o.position_y - 0.5) * CANVAS_H) : 0
  // gradientStyle's watcher runs on Vue's next flush, not synchronously — clear
  // the guard after that flush (not immediately) so it's still up when the
  // watcher checks it, and this load doesn't get overwritten by the style preset.
  nextTick(() => { loadingPreset = false })
}

const reloadPreset = async () => {
  await loadKometaPresets()
  const p = presets.value.find((x) => x.id === selectedPreset.value)
  if (p?.options) applyPresetOptions(p.options)
}

const slugify = (raw: string) => raw.trim().replace(/\s+/g, '-').replace(/[^a-zA-Z0-9_-]/g, '')

const saveCurrentPreset = async () => {
  await presetService.savePreset(optionsPayload.value)
  if (!presetService.error.value) {
    success('Preset saved!')
  } else {
    notifyError(`Failed to save: ${presetService.error.value}`)
  }
  await loadKometaPresets()
}

const saveAsNewPreset = async () => {
  const slug = slugify(newPresetId.value)
  if (!slug) return
  if (slug !== newPresetId.value.trim()) {
    notifyInfo(`Preset id sanitized to "${slug}"`)
  }
  await presetService.savePresetAs(slug, optionsPayload.value)
  if (!presetService.error.value) {
    success('Preset saved!')
  } else {
    notifyError(`Failed to save: ${presetService.error.value}`)
  }
  newPresetId.value = ''
  await loadKometaPresets()
}

watch(selectedPreset, () => {
  const p = presets.value.find((x) => x.id === selectedPreset.value)
  if (p?.options) applyPresetOptions(p.options)
})

// ---------------------------------------------------------------------------
// Accordion sections
// ---------------------------------------------------------------------------
const sectionOpen = ref({ preset: false, background: true, logo: true, text: false, border: false })
const toggleSection = (key: keyof typeof sectionOpen.value) => {
  sectionOpen.value[key] = !sectionOpen.value[key]
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------
const render = useRenderService()
const loading = render.loading
const lastPreview = render.lastPreview
const { success, error: notifyError, info: notifyInfo } = useNotification()

// Existing Plex poster — same endpoint the movie/TV editors use
// (/api/movie/{rating_key}/poster is really rating-key-agnostic under the
// hood: it fetches Plex's generic /library/metadata/{id}/thumb, which works
// for a collection's rating key just as well as a movie's).
const existingPoster = ref<string | null>(null)
const posterRefreshKey = ref(0)
const fetchExistingPoster = async (forceRefresh = false) => {
  try {
    const endpoint = `${apiBase}/api/movie/${props.movie.key}/poster?meta=1${forceRefresh ? '&force_refresh=1' : ''}`
    const res = await fetch(endpoint)
    if (!res.ok) {
      existingPoster.value = null
      return
    }
    const data = await res.json()
    existingPoster.value = data.url
      ? (data.url.startsWith('http') ? data.url : `${apiBase}${data.url}`)
      : null
  } catch (e) {
    console.error('[KometaCreatorPane] Failed to fetch existing poster:', e)
    existingPoster.value = null
  } finally {
    posterRefreshKey.value += 1
  }
}

// Existing Plex logo — same /api/logo/{rating_key} endpoint the movie/TV
// editors use (reads a collection's clearLogo via Plex's generic
// /library/metadata/{id} JSON metadata, which works the same for a
// collection's rating key as it does for a movie's).
const existingLogo = ref<string | null>(null)
const logoRefreshKey = ref(0)
const fetchExistingLogo = async (forceRefresh = false) => {
  try {
    const params = `${forceRefresh ? 'force_refresh=1&' : ''}v=${Date.now()}`
    const url = `${apiBase}/api/logo/${props.movie.key}?${params}`
    const res = await fetch(url)
    existingLogo.value = res.ok ? url : null
  } catch {
    existingLogo.value = null
  } finally {
    logoRefreshKey.value += 1
  }
}

// Send logo to Plex — same standalone endpoint the movie/TV editors use.
// No is_collection flag needed: /api/plex/send-logo uploads via Plex's
// /library/metadata/{id}/clearLogos path, which works for a collection's
// rating key the same as a movie's (verified working by direct testing).
const sendLogo = ref((settings.plex.value as any).sendLogosToPlex ?? false)
const logoSending = ref(false)
const doSendLogoOnly = async () => {
  if (!logoUrl.value) {
    notifyError('No logo selected to send.')
    return
  }
  logoSending.value = true
  try {
    const res = await fetch(`${apiBase}/api/plex/send-logo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rating_key: props.movie.key,
        logo_url: logoUrl.value,
        is_tv: false,
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    success('Logo sent to Plex!')
    await fetchExistingLogo()
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to send logo to Plex'
    notifyError(message)
  } finally {
    logoSending.value = false
  }
}

const optionsPayload = computed(() => ({
  kometa_base_color: kometaBaseColor.value,
  kometa_white_wash: kometaWhiteWash.value,
  kometa_logo_width: kometaLogoWidth.value,
  kometa_logo_offset_y: kometaLogoOffsetY.value,
  // Explicit '' (not undefined) when cleared: undefined gets dropped by
  // JSON.stringify, so if a preset is active the backend's options merge
  // ({**preset_options, **request_options}) would see no override key at all
  // and fall back to whatever texture URL was last saved in the preset —
  // exactly the "Clear Texture doesn't clear it" bug. An explicit '' is a
  // real key in the request that correctly overrides the merge, and
  // kometa.py's `if texture_url:` already treats '' as falsy (no texture).
  kometa_texture_url: kometaTextureUrl.value || '',
  // Unlike the movie/TV editors (where a preset is a reusable style applied
  // across many different items, so the item-specific logo is deliberately
  // NOT saved into the preset), a Kometa preset is normally built for one
  // specific collection — its logo is part of that poster's design, not
  // something you'd want a different collection's preset save to overwrite
  // with. Same explicit-'' pattern as the texture URL above.
  kometa_logo_url: uploadedLogoUrl.value || '',
  matte_height_ratio: matteHeight.value / 100,
  fade_height_ratio: fadeHeight.value / 100,
  top_matte_height_ratio: topMatteHeight.value / 100,
  top_fade_height_ratio: topFadeHeight.value / 100,
  kometa_center_fade_strength: vignette.value / 100,
  grain_amount: grain.value / 100,
  border_enabled: borderEnabled.value,
  border_px: borderThickness.value,
  border_color: borderColor.value,
  text_overlay_enabled: textOverlayEnabled.value,
  custom_text: customText.value,
  font_family: fontFamily.value,
  font_size: fontSize.value,
  text_color: textColor.value,
  // position_y is the text block's CENTER as a fraction of canvas height (see
  // universal.py's _render_text_overlay) — convert the px-from-center offset
  // the same way the logo does, for the same "+down/-up from center" idiom.
  position_y: 0.5 + textOffsetY.value / CANVAS_H,
  // _render_text_overlay defaults letter_spacing to 2 when absent — and its
  // implementation is literally `char + (' ' * letter_spacing)` per character,
  // not a subtle kerning tweak, so an unset value renders as huge gaps between
  // every letter. Simplified Text section has no control for this (matches
  // create_poster.ps1, which has no letter-spacing concept at all), so it must
  // be sent explicitly as 0 or every render inherits that default.
  letter_spacing: 0,
}))

const logoUrl = computed(() => uploadedLogoUrl.value || '')

const doPreview = async () => {
  await render.preview(props.movie, '', logoUrl.value, optionsPayload.value, 'kometa', selectedPreset.value)
}

const doSave = async () => {
  const libraryId = props.movie.library_id != null ? String(props.movie.library_id) : null
  const res = await render.save(props.movie, '', logoUrl.value, optionsPayload.value, 'kometa', selectedPreset.value, libraryId)
  if (res && typeof res.saved_path === 'string') {
    success(`Saved to ${res.saved_path}`)
  } else if (res) {
    success('Saved to disk')
  }
}

const doSend = async () => {
  try {
    const result = await render.send(props.movie, '', logoUrl.value, optionsPayload.value, [], 'kometa', selectedPreset.value, sendLogo.value)
    if (result) {
      success('Successfully sent poster to Plex!')
      await new Promise((resolve) => setTimeout(resolve, 600))
      await fetchExistingPoster(true)
      await fetchExistingLogo()
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to send poster to Plex'
    notifyError(message)
  }
}

let previewTimer: ReturnType<typeof setTimeout> | null = null
watch(
  [
    kometaBaseColor, kometaWhiteWash, kometaLogoWidth, kometaLogoOffsetY, kometaTextureUrl,
    matteHeight, fadeHeight, topMatteHeight, topFadeHeight, vignette, grain,
    borderEnabled, borderThickness, borderColor,
    textOverlayEnabled, customText, fontFamily, fontSize, textColor, textOffsetY, logoUrl,
  ],
  () => {
    if (previewTimer) clearTimeout(previewTimer)
    previewTimer = setTimeout(() => doPreview(), 300)
  }
)

onMounted(async () => {
  fetch(`${apiBase}/api/fonts`)
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => { if (d?.fonts) availableFonts.value = d.fonts })
    .catch(() => {})

  fetch(`${apiBase}/api/kometa-textures`)
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => { if (d?.textures) kometaTextures.value = d.textures })
    .catch(() => {})

  fetch(`${apiBase}/api/kometa-logo-categories`)
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => { if (d?.categories) kometaLogoCategories.value = d.categories })
    .catch(() => {})

  fetchFanartCollectionLogos()
  fetchExistingPoster()
  fetchExistingLogo()

  await loadKometaPresets()
  const p = presets.value.find((x) => x.id === selectedPreset.value)
  if (p?.options) applyPresetOptions(p.options)
  await doPreview()
})
</script>

<template>
  <div class="editor-shell">
    <div class="controls-sidebar">
      <div class="pane-header">
        <div>
          <p class="kicker">Kometa Creator</p>
          <h2>{{ movie.title }}</h2>
        </div>
        <button class="close-btn" title="Close" @click="emit('close')">✕</button>
      </div>

      <div class="controls-scroll">
        <!-- Preset -->
        <div class="acc-section">
          <button class="acc-header" @click="toggleSection('preset')">
            <span>Preset</span>
            <svg class="acc-chevron" :class="{ open: sectionOpen.preset }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9" /></svg>
          </button>
          <div v-show="sectionOpen.preset" class="acc-body">
            <div class="preset-row">
              <label class="field-label preset-select">
                Preset
                <select v-model="selectedPreset">
                  <option v-if="presetLoading">Loading…</option>
                  <option v-if="!presets.length" value="">No presets yet</option>
                  <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name || p.id }}</option>
                </select>
              </label>
              <button class="reload-preset-btn" title="Reload preset values" @click="reloadPreset">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></svg>
              </button>
              <button class="save-preset-btn" title="Save current settings to preset" :disabled="!selectedPreset" @click="saveCurrentPreset">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" /></svg>
              </button>
            </div>
            <div class="preset-row new-preset-row">
              <input v-model="newPresetId" type="text" placeholder="New preset id" class="new-preset-input" />
              <button class="save-preset-btn wide" @click="saveAsNewPreset">Save As</button>
            </div>
          </div>
        </div>

        <!-- Background -->
        <div class="acc-section">
          <button class="acc-header" @click="toggleSection('background')">
            <span>Background</span>
            <svg class="acc-chevron" :class="{ open: sectionOpen.background }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9" /></svg>
          </button>
          <div v-show="sectionOpen.background" class="acc-body">
            <div class="sub-section-title" style="margin-top: 0">Color</div>
            <div class="color-row">
              <input type="color" v-model="kometaBaseColor" class="color-swatch-input" />
              <input type="text" v-model="kometaBaseColor" class="color-hex-input" />
              <button class="randomize-btn" @click="randomizeColor">🎲 Randomize</button>
            </div>
            <div class="swatch-row">
              <button
                v-for="s in swatches"
                :key="s"
                class="swatch"
                :style="{ background: s }"
                :class="{ active: kometaBaseColor.toLowerCase() === s }"
                @click="kometaBaseColor = s"
              />
            </div>

            <div v-if="kometaTextures.length" class="sub-section-title">Or Use a Background Texture</div>
            <div v-if="kometaTextures.length" class="texture-grid">
              <button
                v-for="texture in kometaTextures"
                :key="texture.name"
                class="texture-swatch"
                :class="{ active: selectedTextureName === texture.name }"
                :title="texture.name"
                @click="chooseTexture(texture)"
              >
                <img :src="texture.url" :alt="texture.name" loading="lazy" />
              </button>
            </div>
            <button v-if="kometaTextureUrl" class="randomize-btn" style="margin-bottom: 10px" @click="clearTexture">
              Clear Texture (use flat color instead)
            </button>
            <div v-if="kometaTextureUrl" class="field-hint" style="margin-bottom: 10px">
              A texture is active — it replaces the flat color as the background. The gradient/fade sliders below still apply on top of it, and your logo composites over it independently.
            </div>

            <div class="sub-section-title">Gradient</div>
            <label class="field-label">
              Gradient Style
              <select v-model.number="gradientStyle">
                <option v-for="opt in gradientStyleOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </label>

            <details class="fine-tune">
              <summary>Fine-tune gradient</summary>
              <div class="sub-section-title" style="margin-top: 10px">Top</div>
              <div class="slider">
                <label>Top Matte Height</label>
                <div class="slider-row">
                  <input type="range" min="0" max="50" v-model.number="topMatteHeight" />
                  <input type="number" min="0" max="50" v-model.number="topMatteHeight" class="slider-num" />
                </div>
              </div>
              <div class="slider">
                <label>Top Fade Height</label>
                <div class="slider-row">
                  <input type="range" min="0" max="100" v-model.number="topFadeHeight" />
                  <input type="number" min="0" max="100" v-model.number="topFadeHeight" class="slider-num" />
                </div>
              </div>

              <div class="sub-section-title">Bottom</div>
              <div class="slider">
                <label>Bottom Matte Height</label>
                <div class="slider-row">
                  <input type="range" min="0" max="50" v-model.number="matteHeight" />
                  <input type="number" min="0" max="50" v-model.number="matteHeight" class="slider-num" />
                </div>
              </div>
              <div class="slider">
                <label>Bottom Fade Height</label>
                <div class="slider-row">
                  <input type="range" min="0" max="100" v-model.number="fadeHeight" />
                  <input type="number" min="0" max="100" v-model.number="fadeHeight" class="slider-num" />
                </div>
              </div>

              <div class="sub-section-title">Center Fade</div>
              <div class="slider">
                <label>Center Fade Strength</label>
                <div class="slider-row">
                  <input type="range" min="0" max="100" v-model.number="vignette" />
                  <input type="number" min="0" max="100" v-model.number="vignette" class="slider-num" />
                </div>
                <div class="field-hint">Radial fade to black from center — reaches genuine black at the corners near 100, unlike a subtle photo vignette.</div>
              </div>
            </details>

            <div class="sub-section-title">Effects</div>
            <div class="slider">
              <label>Grain</label>
              <div class="slider-row">
                <input type="range" min="0" max="60" v-model.number="grain" />
                <input type="number" min="0" max="60" v-model.number="grain" class="slider-num" />
              </div>
            </div>
          </div>
        </div>

        <!-- Logo -->
        <div class="acc-section">
          <button class="acc-header" @click="toggleSection('logo')">
            <span>Logo</span>
            <svg class="acc-chevron" :class="{ open: sectionOpen.logo }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9" /></svg>
          </button>
          <div v-show="sectionOpen.logo" class="acc-body">
            <div
              class="poster-upload-zone"
              :class="{ 'drag-over': logoDropActive, 'has-upload': !!uploadedLogoUrl }"
              @dragover.prevent="logoDropActive = true"
              @dragleave="logoDropActive = false"
              @drop.prevent="onLogoDrop"
              @click="!uploadedLogoUrl && ($refs.logoFileInput as HTMLInputElement)?.click()"
            >
              <template v-if="uploadedLogoUrl">
                <img :src="uploadedLogoUrl" class="upload-preview" alt="Uploaded logo" />
                <div class="upload-overlay">
                  <button class="upload-replace" @click.stop="($refs.logoFileInput as HTMLInputElement)?.click()">Replace</button>
                  <button class="upload-remove" @click.stop="clearUploadedLogo">✕</button>
                </div>
              </template>
              <template v-else>
                <div class="upload-prompt">
                  <span v-if="logoUploading">Uploading…</span>
                  <span v-else>&#8679; Drop logo image or click to upload</span>
                </div>
              </template>
            </div>
            <input ref="logoFileInput" type="file" accept="image/*" style="display:none" @change="onLogoFileInput" />

            <div v-if="loadingFanartLogos" class="field-hint">Loading franchise logos from Fanart.tv…</div>
            <template v-if="fanartCollectionLogos.length">
              <div class="sub-section-title">Or Use a Franchise Logo (Fanart.tv)</div>
              <div class="texture-grid logo-grid">
                <button
                  v-for="(fl, idx) in fanartCollectionLogos"
                  :key="fl.url"
                  class="texture-swatch logo-swatch"
                  :class="{ active: uploadedLogoUrl === fl.url }"
                  :title="fl.language ? `Fanart logo (${fl.language})` : 'Fanart logo'"
                  @click="uploadedLogoUrl = fl.url"
                >
                  <img :src="fl.thumb || fl.url" :alt="`Fanart logo ${idx + 1}`" loading="lazy" />
                </button>
              </div>
            </template>

            <div class="sub-section-title">Or Choose from Kometa's Logo Library</div>
            <label class="field-label">
              Category
              <select v-model="selectedLogoCategory">
                <option :value="null">— Select a category —</option>
                <option v-for="cat in kometaLogoCategories" :key="cat" :value="cat">
                  {{ kometaLogoCategoryLabels[cat] || cat }}
                </option>
              </select>
            </label>
            <div v-if="kometaLogoOptionsLoading" class="field-hint">Loading logos…</div>
            <div v-else-if="selectedLogoCategory && !kometaLogoOptions.length" class="field-hint">No logos found in this category.</div>
            <div v-if="kometaLogoOptions.length" class="texture-grid logo-grid">
              <button
                v-for="logo in kometaLogoOptions"
                :key="logo.name"
                class="texture-swatch logo-swatch"
                :class="{ active: uploadedLogoUrl === logo.url }"
                :title="logo.name"
                @click="chooseKometaLogo(logo)"
              >
                <img :src="logo.url" :alt="logo.name" loading="lazy" />
              </button>
            </div>

            <label class="checkbox-label" style="margin-top: 10px">
              <input type="checkbox" v-model="kometaWhiteWash" />
              <span>White-wash logo</span>
            </label>

            <div class="sub-section-title">Position &amp; Size</div>
            <div class="slider">
              <label>Logo Width (px)</label>
              <div class="slider-row">
                <input type="range" min="100" max="2000" v-model.number="kometaLogoWidth" />
                <input type="number" min="1" max="2000" v-model.number="kometaLogoWidth" class="slider-num" />
              </div>
              <div class="field-hint">Height scales automatically to match the logo's own aspect ratio.</div>
            </div>
            <div class="slider">
              <label>Vertical Offset (px from center)</label>
              <div class="slider-row">
                <input type="range" min="-1500" max="1500" v-model.number="kometaLogoOffsetY" />
                <input type="number" min="-1500" max="1500" v-model.number="kometaLogoOffsetY" class="slider-num" />
              </div>
              <div class="field-hint">Positive pushes the logo down from center, negative pushes it up. Always horizontally centered.</div>
            </div>
          </div>
        </div>

        <!-- Text -->
        <div class="acc-section">
          <button class="acc-header" @click="toggleSection('text')">
            <span>Text</span>
            <svg class="acc-chevron" :class="{ open: sectionOpen.text }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9" /></svg>
          </button>
          <div v-show="sectionOpen.text" class="acc-body">
            <label class="checkbox-label">
              <input type="checkbox" v-model="textOverlayEnabled" />
              <span>Enable Text</span>
            </label>
            <template v-if="textOverlayEnabled">
              <label class="field-label">
                Text
                <input v-model="customText" type="text" placeholder="e.g. PJ'S TV REQUESTS" />
              </label>
              <label class="field-label">
                Font
                <select v-model="fontFamily">
                  <optgroup v-if="availableFonts.length" label="Available Fonts">
                    <option v-for="f in availableFonts" :key="f" :value="f">{{ f }}</option>
                  </optgroup>
                  <optgroup v-else label="Fonts">
                    <option value="Arial">Arial</option>
                    <option value="Helvetica">Helvetica</option>
                  </optgroup>
                </select>
              </label>
              <label class="field-label">
                Font Color
                <input type="color" v-model="textColor" />
              </label>
              <div class="slider">
                <label>Font Size</label>
                <div class="slider-row">
                  <input type="range" min="10" max="500" v-model.number="fontSize" />
                  <input type="number" min="10" max="500" v-model.number="fontSize" class="slider-num" />
                </div>
              </div>
              <div class="slider">
                <label>Vertical Offset (px from center)</label>
                <div class="slider-row">
                  <input type="range" min="-1500" max="1500" v-model.number="textOffsetY" />
                  <input type="number" min="-1500" max="1500" v-model.number="textOffsetY" class="slider-num" />
                </div>
                <div class="field-hint">Positive pushes text down from center, negative pushes it up.</div>
              </div>
            </template>
          </div>
        </div>

        <!-- Border -->
        <div class="acc-section">
          <button class="acc-header" @click="toggleSection('border')">
            <span>Border</span>
            <svg class="acc-chevron" :class="{ open: sectionOpen.border }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9" /></svg>
          </button>
          <div v-show="sectionOpen.border" class="acc-body">
            <label class="checkbox-label">
              <input type="checkbox" v-model="borderEnabled" />
              <span>Enable Border</span>
            </label>
            <template v-if="borderEnabled">
              <div class="slider">
                <label>Thickness (px)</label>
                <div class="slider-row">
                  <input type="range" min="0" max="100" v-model.number="borderThickness" />
                  <input type="number" min="0" max="100" v-model.number="borderThickness" class="slider-num" />
                </div>
              </div>
              <label class="field-label">
                Border Color
                <input type="color" v-model="borderColor" />
              </label>
            </template>
          </div>
        </div>
      </div>
    </div>

    <div class="preview-pane">
      <div class="preview-inner">
        <div class="preview-existing">
          <div class="preview-label">
            <span>Current Plex Poster</span>
            <button class="refresh-btn" title="Refresh poster" @click="fetchExistingPoster(true)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
          </div>
          <img v-if="existingPoster" :key="posterRefreshKey" :src="existingPoster" alt="Existing poster" class="existing-img" />
          <div v-else class="preview-empty small">No poster</div>

          <div class="preview-label" style="margin-top: 14px;">
            <span>Current Plex Logo</span>
            <button class="refresh-btn" title="Fetch logo from Plex" @click="fetchExistingLogo(true)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
          </div>
          <div class="existing-logo-area">
            <img v-if="existingLogo" :key="logoRefreshKey" :src="existingLogo" alt="Existing logo" class="existing-logo-img" />
            <div v-else class="preview-empty small">No logo</div>
          </div>
        </div>
        <div class="preview-main">
          <div class="preview-label">
            <span>Preview</span>
            <div class="preview-actions float-right">
              <label class="send-logo-toggle" title="Also send the selected logo to Plex">
                <input type="checkbox" v-model="sendLogo" />
                <span>Send logo</span>
              </label>
              <button title="Send Logo to Plex" class="btn-send-logo btn-inline" :disabled="logoSending || !logoUrl" @click="doSendLogoOnly">
                <svg v-if="logoSending" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                <span class="btn-label">{{ logoSending ? 'Sending...' : 'Send Logo' }}</span>
              </button>
              <button title="Save to Disk" class="btn-save btn-inline" :disabled="loading" @click="doSave">💾 <span class="btn-label">Save to Disk</span></button>
              <button title="Send to Plex" class="btn-plex btn-inline" :disabled="loading" @click="doSend">📺 <span class="btn-label">Send to Plex</span></button>
            </div>
          </div>
          <div class="preview-container">
            <img v-if="lastPreview" :src="lastPreview" alt="Preview" class="preview-img" />
            <div v-else class="preview-empty">{{ loading ? 'Rendering…' : 'No preview yet' }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-shell {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 16px;
  height: calc(100vh - 60px);
  min-height: 0;
}

.controls-sidebar {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid var(--border);
  padding-right: 12px;
}

.pane-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 4px;
  border-bottom: 1px solid var(--border);
}

.kicker {
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 1px;
  color: var(--muted);
}

.close-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--muted);
  cursor: pointer;
  padding: 6px 10px;
}

.controls-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 8px 4px 24px;
}

.acc-section {
  border: 1px solid var(--border);
  border-radius: 12px;
  margin-bottom: 10px;
  overflow: hidden;
}

.acc-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.03);
  border: none;
  color: inherit;
  font-weight: 600;
  cursor: pointer;
}

.acc-chevron {
  transition: transform 0.2s;
}

.acc-chevron.open {
  transform: rotate(180deg);
}

.acc-body {
  padding: 14px;
}

.sub-section-title {
  font-size: 12px;
  font-weight: 600;
  color: #c9d6ff;
  margin: 14px 0 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.field-label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 12px;
  font-weight: 500;
  color: #c4cceb;
}

.field-label select,
.field-label input[type='color'],
.new-preset-input,
.color-hex-input {
  width: 100%;
  padding: 8px;
  border-radius: 7px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 13px;
}

.preset-row {
  display: flex;
  gap: 6px;
  align-items: flex-end;
  margin-bottom: 8px;
}

.preset-select {
  flex: 1;
}

.reload-preset-btn,
.save-preset-btn {
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #c4cceb;
  border-radius: 8px;
  padding: 8px 10px;
  cursor: pointer;
}

.save-preset-btn.wide {
  padding: 8px 14px;
}

.new-preset-row {
  gap: 8px;
}

.new-preset-input {
  flex: 1;
}

.color-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.color-swatch-input {
  width: 44px;
  height: 38px;
  padding: 2px;
  border-radius: 8px;
  border: 1px solid var(--border);
  cursor: pointer;
}

.color-hex-input {
  flex: 1;
}

.randomize-btn {
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #c4cceb;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  white-space: nowrap;
}

.swatch-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.swatch {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 2px solid transparent;
  cursor: pointer;
}

.swatch.active {
  border-color: var(--accent);
}

.texture-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 6px;
  margin-bottom: 10px;
}

.texture-swatch {
  aspect-ratio: 2 / 3;
  border-radius: 6px;
  border: 2px solid transparent;
  padding: 0;
  overflow: hidden;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.03);
}

.texture-swatch img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.texture-swatch.active {
  border-color: var(--accent);
}

.logo-grid {
  grid-template-columns: repeat(3, 1fr);
}

.logo-swatch {
  aspect-ratio: 1 / 1;
  background: rgba(0, 0, 0, 0.35);
}

.logo-swatch img {
  object-fit: contain;
  padding: 6px;
}

.slider {
  margin-bottom: 12px;
}

.field-hint {
  font-size: 11px;
  color: var(--muted);
  margin-top: 4px;
}

.fine-tune {
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
}

.fine-tune summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: #c4cceb;
}

.slider label {
  font-size: 12px;
  font-weight: 500;
  color: #c4cceb;
  margin-bottom: 6px;
  display: block;
}

.slider-row {
  display: grid;
  grid-template-columns: 1fr 70px;
  gap: 8px;
  align-items: center;
}

.slider-row input[type='range'] {
  width: 100%;
}

.slider-num {
  width: 100%;
  padding: 6px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 12px;
  text-align: center;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #dce6ff;
  cursor: pointer;
  margin-bottom: 10px;
}

.checkbox-label input[type='checkbox'] {
  cursor: pointer;
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
}

.poster-upload-zone {
  border: 2px dashed var(--border);
  border-radius: 12px;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  cursor: pointer;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.02);
}

.poster-upload-zone.drag-over {
  border-color: var(--accent);
  background: rgba(61, 214, 183, 0.08);
}

.poster-upload-zone.has-upload {
  cursor: default;
}

.upload-prompt {
  color: var(--muted);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

.upload-preview {
  max-width: 100%;
  max-height: 200px;
  object-fit: contain;
}

.upload-overlay {
  position: absolute;
  bottom: 8px;
  right: 8px;
  display: flex;
  gap: 6px;
}

.upload-replace,
.upload-remove {
  border: 1px solid var(--border);
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
}

.preview-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.preview-inner {
  display: flex;
  gap: 20px;
  align-items: flex-start;
  height: 100%;
}

.preview-existing {
  text-align: center;
  flex-shrink: 0;
}

.existing-img {
  width: 160px;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
}

.preview-empty.small {
  font-size: 11px;
  padding: 20px 8px;
  width: 160px;
  box-sizing: border-box;
}

.existing-logo-area {
  width: 160px;
  background: #0a0b12;
  border-radius: 6px;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  box-sizing: border-box;
}

.existing-logo-img {
  width: 100%;
  max-height: 72px;
  object-fit: contain;
  display: block;
}

.send-logo-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: #a8b3cf;
  cursor: pointer;
  user-select: none;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
  transition: all 0.15s;
}
.send-logo-toggle:has(input:checked) {
  color: #eef2ff;
  border-color: rgba(61, 214, 183, 0.35);
}
.send-logo-toggle input {
  margin: 0;
  accent-color: var(--accent, #3dd6b7);
}

.btn-send-logo {
  background: rgba(61, 214, 183, 0.12);
  color: #3dd6b7;
  border: 1px solid rgba(61, 214, 183, 0.3);
  cursor: pointer;
  transition: all 0.15s;
}
.btn-send-logo:hover:not(:disabled) {
  background: rgba(61, 214, 183, 0.22);
  border-color: rgba(61, 214, 183, 0.55);
}
.btn-send-logo:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn-send-logo .spin {
  animation: spin-inline 0.9s linear infinite;
}
@keyframes spin-inline {
  to { transform: rotate(360deg); }
}

.preview-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  max-width: 800px;
}

.preview-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--muted);
  padding: 8px 0;
}

.preview-actions {
  display: flex;
  gap: 8px;
}

.btn-inline {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  font-size: 13px;
}

.btn-plex {
  border-color: rgba(229, 160, 13, 0.4);
}

.preview-container {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 12px;
  overflow: hidden;
}

.preview-img {
  max-height: 80vh;
  max-width: 100%;
  width: auto;
  object-fit: contain;
  border-radius: 10px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
}

.preview-empty {
  color: var(--muted);
  font-size: 13px;
}
</style>
