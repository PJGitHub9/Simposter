<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useNotification } from '@/composables/useNotification'
import { useSettingsStore } from '@/stores/settings'

type Preset = {
  id: string
  name: string
  options: Record<string, unknown>
  season_options?: Record<string, unknown>
}
type TemplatePresets = Record<string, { presets: Preset[] }>
type PresetFallback = {
  fallbackPosterAction?: 'continue' | 'skip' | 'template'
  fallbackPosterTemplate?: string
  fallbackPosterPreset?: string
  fallbackLogoAction?: 'continue' | 'skip' | 'template'
  fallbackLogoTemplate?: string
  fallbackLogoPreset?: string
  logoSource?: string
}

const apiBase = getApiBase()
const settings = useSettingsStore()
const { error: showError } = useNotification()

const presets = ref<TemplatePresets>({})
const loading = ref(false)
const exporting = ref(false)
const importing = ref(false)
const importText = ref('')
const fallbackPosterFilter = ref('all')
const fallbackLogoFilter = ref('all')
const fallbackLogoMode = ref('first')
const whiteLogoFallback = ref('use_next')
const languagePreference = ref('en')
const logoSource = ref('tmdb_fanart')
const languageOptions = [
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'it', label: 'Italian' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'ru', label: 'Russian' },
  { code: 'ja', label: 'Japanese' },
  { code: 'ko', label: 'Korean' },
  { code: 'zh', label: 'Chinese' },
  { code: 'hi', label: 'Hindi' },
  { code: 'ar', label: 'Arabic' },
]
const savingFallback = ref(false)
const showDefaultsOpen = ref(true)
const selectedPresets = ref<Set<string>>(new Set())
const deleting = ref<string | null>(null)
const showFallbackModal = ref(false)
const modalPreset = ref<{ templateId: string; preset: Preset } | null>(null)
const modalFallback = ref<PresetFallback>({
  fallbackPosterAction: 'continue',
  fallbackPosterTemplate: '',
  fallbackPosterPreset: '',
  fallbackLogoAction: 'continue',
  fallbackLogoTemplate: '',
  fallbackLogoPreset: '',
  logoSource: ''
})

// Expand/tab state for preset cards
const expandedPresets = ref<Set<string>>(new Set())
const presetActiveTabs = ref<Record<string, 'series' | 'season'>>({})
const showImportExport = ref(false)

// Preview state
const previewUrl = ref('')
const previewLoading = ref(false)
const previewError = ref('')
const previewMovie = ref<{ key: string; title: string } | null>(null)
const previewTemplate = ref<{ templateId: string; presetName: string } | null>(null)
const movies = ref<{ key: string; title: string }[]>([])
const selectedPreviewMovie = ref<{ key: string; title: string } | null>(null)
const showMovieSearch = ref(false)
const movieSearchTerm = ref('')
const movieSearchResults = computed(() => {
  const query = movieSearchTerm.value.trim().toLowerCase()
  if (!query) return movies.value.slice(0, 25)
  return movies.value.filter((m) => (m.title || '').toLowerCase().includes(query)).slice(0, 25)
})

const presetCount = computed(() =>
  Object.values(presets.value).reduce((acc, tpl) => acc + (tpl.presets?.length || 0), 0)
)

const posterFallbackLabel = computed(() => {
  const opts = modalPreset.value?.preset.options || {}
  const pref = opts.poster_filter || opts.posterPreference || ''
  return pref ? `If ${pref} poster not found` : 'If preferred poster not found'
})

const logoFallbackLabel = computed(() => {
  const opts = modalPreset.value?.preset.options || {}
  const pref = opts.logo_preference || opts.logo_mode || ''
  return pref ? `If ${pref} logo not found` : 'If preferred logo not found'
})

// ---- Preset card helpers ----
const toggleExpand = (key: string) => {
  const s = new Set(expandedPresets.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  expandedPresets.value = s
}

const getPresetTab = (key: string): 'series' | 'season' =>
  presetActiveTabs.value[key] || 'series'

const setPresetTab = (key: string, tab: 'series' | 'season') => {
  presetActiveTabs.value = { ...presetActiveTabs.value, [key]: tab }
}

const logoLabel = (opts: Record<string, unknown>) => {
  const mode = String(opts.logo_preference || opts.logo_mode || 'first')
  const map: Record<string, string> = { white: 'White', color: 'Color', first: 'Any', none: 'No logo', original: 'Original', stock: 'Stock' }
  return map[mode] || mode
}

const logoChipClass = (opts: Record<string, unknown>) => {
  const mode = String(opts.logo_preference || opts.logo_mode || 'first')
  const map: Record<string, string> = { white: 'chip-white', color: 'chip-accent', none: 'chip-muted', first: 'chip-default', original: 'chip-default', stock: 'chip-default' }
  return map[mode] || 'chip-default'
}

const posterLabel = (opts: Record<string, unknown>) => {
  const f = String(opts.poster_filter || 'all')
  const map: Record<string, string> = { all: 'Any', textless: 'Textless', text: 'With text', en: 'English', original: 'Original' }
  return map[f] || f
}

const pct = (v: unknown) => (v != null && v !== '' && !isNaN(Number(v))) ? `${Math.round(Number(v) * 100)}%` : '—'

const hasFallback = (opts: Record<string, unknown>) =>
  (opts.fallbackPosterAction && opts.fallbackPosterAction !== 'continue') ||
  (opts.fallbackLogoAction && opts.fallbackLogoAction !== 'continue')

const fallbackSummary = (opts: Record<string, unknown>) => {
  const parts: string[] = []
  if (opts.fallbackPosterAction && opts.fallbackPosterAction !== 'continue')
    parts.push(`Poster: ${opts.fallbackPosterAction}`)
  if (opts.fallbackLogoAction && opts.fallbackLogoAction !== 'continue')
    parts.push(`Logo: ${opts.fallbackLogoAction}`)
  return parts.join(' · ')
}

const hasSeasonOptions = (preset: Preset) => {
  const s = preset.season_options
  return s && typeof s === 'object' && Object.keys(s).length > 0
}

const getActiveOpts = (key: string, preset: Preset): Record<string, unknown> => {
  const tab = getPresetTab(key)
  return (tab === 'season' && hasSeasonOptions(preset))
    ? preset.season_options as Record<string, unknown>
    : preset.options
}

const logoSourceLabel = (src: unknown) => {
  if (!src) return '—'
  const map: Record<string, string> = {
    tmdb: 'TMDb only', fanart: 'Fanart.tv only',
    tmdb_fanart: 'TMDb → Fanart', fanart_tmdb: 'Fanart → TMDb', both: 'Both merged'
  }
  return map[String(src)] || String(src)
}
// ---- End helpers ----

const fetchPresets = async () => {
  loading.value = true
  try {
    const res = await fetch(`${apiBase}/api/presets`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    presets.value = await res.json()
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Failed to load presets')
  } finally {
    loading.value = false
  }
}

const handleExportAll = async () => {
  exporting.value = true
  try {
    const res = await fetch(`${apiBase}/api/presets/export`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    importText.value = JSON.stringify(data, null, 2)
    showImportExport.value = true
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Export failed')
  } finally {
    exporting.value = false
  }
}

const openFallbackModal = (templateId: string, preset: Preset) => {
  modalPreset.value = { templateId, preset }
  const opts = preset.options || {}
  modalFallback.value = {
    fallbackPosterAction: (opts.fallbackPosterAction as 'template' | 'continue' | 'skip' | undefined) || 'continue',
    fallbackPosterTemplate: (opts.fallbackPosterTemplate as string) || '',
    fallbackPosterPreset: (opts.fallbackPosterPreset as string) || '',
    fallbackLogoAction: (opts.fallbackLogoAction as 'template' | 'continue' | 'skip' | undefined) || 'continue',
    fallbackLogoTemplate: (opts.fallbackLogoTemplate as string) || '',
    fallbackLogoPreset: (opts.fallbackLogoPreset as string) || '',
    logoSource: (opts.logoSource as string) || ''
  }
  showFallbackModal.value = true
}

const savePresetFallback = async () => {
  if (!modalPreset.value) return
  try {
    const { templateId, preset } = modalPreset.value
    const normalized: PresetFallback = { ...modalFallback.value }
    if (normalized.fallbackPosterAction !== 'template') {
      normalized.fallbackPosterTemplate = ''
      normalized.fallbackPosterPreset = ''
    }
    if (normalized.fallbackLogoAction !== 'template') {
      normalized.fallbackLogoTemplate = ''
      normalized.fallbackLogoPreset = ''
    }
    const updated = { ...preset.options, ...normalized }
    const res = await fetch(`${apiBase}/api/presets/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_id: templateId, preset_id: preset.id, options: updated })
    })
    if (!res.ok) throw new Error(`API error ${res.status}`)
    await fetchPresets()
    showFallbackModal.value = false
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Failed to save fallback rules')
  }
}

const handleExportSelected = () => {
  const map: TemplatePresets = {}
  selectedPresets.value.forEach((key) => {
    const [tpl, pid] = key.split('::')
    if (!tpl || !pid) return
    const preset = presets.value[tpl]?.presets.find((p) => p.id === pid)
    if (!preset) return
    if (!map[tpl]) map[tpl] = { presets: [] }
    map[tpl].presets.push(preset)
  })
  if (Object.keys(map).length === 0) { handleExportAll(); return }
  importText.value = JSON.stringify(map, null, 2)
  showImportExport.value = true
}

const toggleSelected = (tplId: string, presetId: string) => {
  const key = `${tplId}::${presetId}`
  const set = new Set(selectedPresets.value)
  if (set.has(key)) set.delete(key)
  else set.add(key)
  selectedPresets.value = set
}

const deletePreset = async (templateId: string, presetId: string) => {
  if (!window.confirm(`Delete preset "${presetId}"?`)) return
  deleting.value = `${templateId}::${presetId}`
  try {
    const res = await fetch(`${apiBase}/api/presets/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_id: templateId, preset_id: presetId })
    })
    if (!res.ok) throw new Error(`API error ${res.status}`)
    await fetchPresets()
    const set = new Set(selectedPresets.value)
    set.delete(`${templateId}::${presetId}`)
    selectedPresets.value = set
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Delete failed')
  } finally {
    deleting.value = null
  }
}

const handleImport = async () => {
  if (!importText.value.trim()) return
  importing.value = true
  try {
    const json = JSON.parse(importText.value)
    const res = await fetch(`${apiBase}/api/presets/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(json)
    })
    if (!res.ok) throw new Error(`API error ${res.status}`)
    importText.value = ''
    await fetchPresets()
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Invalid JSON')
  } finally {
    importing.value = false
  }
}

const fetchFallback = async () => {
  try {
    const res = await fetch(`${apiBase}/api/template-fallback`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    fallbackPosterFilter.value = data.poster_filter || 'all'
    fallbackLogoFilter.value = data.logo_filter || 'all'
    fallbackLogoMode.value = data.logo_mode || 'first'
    whiteLogoFallback.value = data.white_logo_fallback || 'use_next'
    languagePreference.value = data.language_preference || 'en'
    logoSource.value = data.logo_source || 'tmdb_fanart'
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Failed to load default settings')
  }
}

const saveFallback = async () => {
  savingFallback.value = true
  try {
    const res = await fetch(`${apiBase}/api/template-fallback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        poster_filter: fallbackPosterFilter.value,
        logo_filter: fallbackLogoFilter.value,
        logo_mode: fallbackLogoMode.value,
        white_logo_fallback: whiteLogoFallback.value,
        language_preference: languagePreference.value,
        logo_source: logoSource.value
      })
    })
    if (!res.ok) throw new Error(`API error ${res.status}`)
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Failed to save default settings')
  } finally {
    savingFallback.value = false
  }
}

const fetchMovies = async () => {
  try {
    const res = await fetch(`${apiBase}/api/movies`)
    if (res.ok) {
      const data = await res.json()
      const list = Array.isArray(data) ? data.map((m: { key: string; title: string }) => ({ key: m.key, title: m.title })) : []
      movies.value = list
      if (selectedPreviewMovie.value && !list.some((m) => m.key === selectedPreviewMovie.value?.key))
        selectedPreviewMovie.value = null
    }
  } catch { /* ignore */ }
}

const pickRandomMovie = () =>
  movies.value.length ? movies.value[Math.floor(Math.random() * movies.value.length)] || null : null

const resolvePreviewMovie = () => {
  if (selectedPreviewMovie.value) {
    const match = movies.value.find((m) => m.key === selectedPreviewMovie.value?.key)
    if (match) return match
    selectedPreviewMovie.value = null
  }
  return pickRandomMovie()
}

const selectPreviewMovie = (movie: { key: string; title: string }) => {
  selectedPreviewMovie.value = movie
  previewMovie.value = movie
  previewUrl.value = ''
  previewError.value = ''
  showMovieSearch.value = false
  movieSearchTerm.value = ''
}

const useRandomPreviewMovie = () => {
  selectedPreviewMovie.value = null
  previewMovie.value = pickRandomMovie()
  previewUrl.value = ''
  previewError.value = ''
}

const clearSelectedPreviewMovie = () => {
  selectedPreviewMovie.value = null
  previewUrl.value = ''
  previewError.value = ''
}

const previewPreset = async (templateId: string, preset: Preset) => {
  const movie = resolvePreviewMovie()
  if (!movie) { previewError.value = 'No movies available to preview'; return }
  previewMovie.value = movie
  previewTemplate.value = { templateId, presetName: preset.name || preset.id }
  previewUrl.value = ''
  previewLoading.value = true
  previewError.value = ''
  try {
    const res = await fetch(`${apiBase}/api/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        template_id: templateId,
        background_url: `${apiBase}/api/movie/${movie.key}/poster`,
        logo_url: null,
        options: preset.options || {},
        preset_id: preset.id,
        movie_title: movie.title,
        disableOverlayCache: !settings.performance.value.useOverlayCache,
        skip_fallback: true,
      })
    })
    if (!res.ok) {
      let message = `Preview failed (${res.status})`
      try { const err = await res.json(); if (err?.detail) message = err.detail } catch { /* ignore */ }
      throw new Error(message)
    }
    const data = await res.json()
    previewUrl.value = `data:image/jpeg;base64,${data.image_base64}`
  } catch (e) {
    previewError.value = e instanceof Error ? e.message : 'Preview failed'
  } finally {
    previewLoading.value = false
  }
}

onMounted(async () => {
  await fetchPresets()
  await fetchFallback()
  await fetchMovies()
})
</script>

<template>
  <div class="template-manager">
    <div class="header">
      <div>
        <h2>&#x1F3A8; Template Manager</h2>
        <p class="subtitle">Manage presets, view settings at a glance, and configure fallback behaviour.</p>
      </div>
      <span class="pill">{{ presetCount }} preset{{ presetCount === 1 ? '' : 's' }}</span>
    </div>

    <div class="layout">
      <div class="column">

        <!-- Default Batch Settings (collapsible) -->
        <div class="section">
          <button class="section-toggle" @click="showDefaultsOpen = !showDefaultsOpen">
            <div class="toggle-left">
              <h3>Default Batch Settings</h3>
              <span class="help">Applied when a preset doesn't override — batch, webhook &amp; scheduled renders</span>
            </div>
            <svg class="acc-chevron" :class="{ open: showDefaultsOpen }" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <div v-show="showDefaultsOpen" class="defaults-body">
            <div class="grid preferences-grid">
              <label>
                <span class="label-text">Language preference (TMDb)</span>
                <select v-model="languagePreference">
                  <option v-for="lang in languageOptions" :key="lang.code" :value="lang.code">{{ lang.label }} ({{ lang.code }})</option>
                </select>
              </label>
              <label>
                <span class="label-text">Logo source priority</span>
                <select v-model="logoSource">
                  <option value="tmdb">TMDb only</option>
                  <option value="fanart">Fanart.tv only</option>
                  <option value="tmdb_fanart">TMDb first, Fanart fallback (recommended)</option>
                  <option value="fanart_tmdb">Fanart first, TMDb fallback</option>
                  <option value="both">Both merged (all results)</option>
                </select>
              </label>
              <label>
                <span class="label-text">Default poster filter</span>
                <select v-model="fallbackPosterFilter">
                  <option value="all">All posters (no filter)</option>
                  <option value="en">English only</option>
                  <option value="original">Original language only</option>
                  <option value="no_text">Textless only</option>
                </select>
              </label>
              <label>
                <span class="label-text">Default logo filter</span>
                <select v-model="fallbackLogoFilter">
                  <option value="all">All logos (no filter)</option>
                  <option value="en">English only</option>
                  <option value="original">Original language only</option>
                </select>
              </label>
              <label>
                <span class="label-text">Default logo selection</span>
                <select v-model="fallbackLogoMode">
                  <option value="first">First available</option>
                  <option value="white">White / light (low saturation)</option>
                  <option value="color">Colored (high saturation)</option>
                  <option value="none">No logo</option>
                </select>
              </label>
              <label>
                <span class="label-text">White logo fallback</span>
                <select v-model="whiteLogoFallback">
                  <option value="use_next">Use next available logo</option>
                  <option value="skip">Render without logo</option>
                </select>
              </label>
            </div>
            <div class="actions" style="justify-content: flex-end; margin-top: 4px;">
              <button class="primary" type="button" @click="saveFallback" :disabled="savingFallback">
                {{ savingFallback ? 'Saving…' : 'Save Defaults' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Presets -->
        <div class="section">
          <div class="section-header">
            <h3>Presets</h3>
            <div class="actions">
              <button class="secondary tiny" @click="handleExportSelected" :disabled="exporting">
                {{ exporting ? 'Exporting…' : selectedPresets.size > 0 ? `Export ${selectedPresets.size} selected` : 'Export all' }}
              </button>
            </div>
          </div>

          <div v-if="loading" class="loading">Loading presets…</div>
          <div v-else class="presets-list">
            <div v-for="(tpl, templateId) in presets" :key="templateId" class="template-block">
              <div class="template-header">
                <h4>{{ templateId }}</h4>
                <span class="count">{{ tpl.presets?.length || 0 }} preset{{ tpl.presets?.length === 1 ? '' : 's' }}</span>
              </div>

              <div class="preset-cards">
                <div
                  v-for="preset in tpl.presets"
                  :key="preset.id"
                  class="preset-card"
                  :class="{
                    expanded: expandedPresets.has(`${templateId}::${preset.id}`),
                    selected: selectedPresets.has(`${templateId}::${preset.id}`)
                  }"
                >
                  <!-- Card header row -->
                  <div class="preset-card-header">
                    <label class="checkbox" @click.stop>
                      <input
                        type="checkbox"
                        :checked="selectedPresets.has(`${templateId}::${preset.id}`)"
                        @change="toggleSelected(templateId, preset.id)"
                      />
                    </label>

                    <div class="preset-card-title" @click="toggleExpand(`${templateId}::${preset.id}`)">
                      <span class="preset-name">{{ preset.name || preset.id }}</span>
                      <span class="preset-id">{{ preset.id }}</span>
                    </div>

                    <!-- Summary chips -->
                    <div class="preset-chips" @click="toggleExpand(`${templateId}::${preset.id}`)">
                      <span class="chip" :class="logoChipClass(preset.options)">
                        <span class="chip-key">Logo</span>
                        <span class="chip-val">{{ logoLabel(preset.options) }}</span>
                      </span>
                      <span class="chip chip-default">
                        <span class="chip-key">Poster</span>
                        <span class="chip-val">{{ posterLabel(preset.options) }}</span>
                      </span>
                      <span v-if="preset.options.text_overlay_enabled" class="chip chip-accent">Text overlay</span>
                      <span v-if="hasSeasonOptions(preset)" class="chip chip-season">Season config</span>
                      <span v-if="hasFallback(preset.options)" class="chip chip-warn" :title="fallbackSummary(preset.options)">Fallback</span>
                    </div>

                    <div class="preset-actions">
                      <button class="icon-btn" @click.stop="previewPreset(templateId, preset)" title="Preview">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
                      </button>
                      <button class="icon-btn" @click.stop="openFallbackModal(templateId, preset)" title="Fallback rules">⚙</button>
                      <button
                        class="icon-btn danger"
                        @click.stop="deletePreset(templateId, preset.id)"
                        :disabled="deleting === `${templateId}::${preset.id}`"
                        title="Delete"
                      >×</button>
                      <button class="icon-btn expand-btn" @click.stop="toggleExpand(`${templateId}::${preset.id}`)" title="Expand">
                        <svg class="chevron" :class="{ open: expandedPresets.has(`${templateId}::${preset.id}`) }" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                          <polyline points="6 9 12 15 18 9"/>
                        </svg>
                      </button>
                    </div>
                  </div>

                  <!-- Expanded body -->
                  <div v-show="expandedPresets.has(`${templateId}::${preset.id}`)" class="preset-card-body">
                    <!-- Series / Season tabs -->
                    <div class="preset-tabs">
                      <button
                        :class="['preset-tab', { active: getPresetTab(`${templateId}::${preset.id}`) === 'series' }]"
                        @click="setPresetTab(`${templateId}::${preset.id}`, 'series')"
                      >Series</button>
                      <button
                        :class="['preset-tab', { active: getPresetTab(`${templateId}::${preset.id}`) === 'season' }]"
                        @click="setPresetTab(`${templateId}::${preset.id}`, 'season')"
                      >
                        Season
                        <span v-if="!hasSeasonOptions(preset)" class="tab-note">(uses series)</span>
                      </button>
                    </div>

                    <!-- Settings grid -->
                    <div class="preset-settings">
                      <div v-if="getPresetTab(`${templateId}::${preset.id}`) === 'season' && !hasSeasonOptions(preset)" class="no-season-note">
                        No season-specific settings saved — season posters use the series preset above.
                      </div>
                      <template v-else>
                        <div class="settings-grid">
                          <div class="setting-item">
                            <span class="setting-label">Logo</span>
                            <span class="setting-value">{{ logoLabel(getActiveOpts(`${templateId}::${preset.id}`, preset)) }}</span>
                          </div>
                          <div class="setting-item">
                            <span class="setting-label">Poster</span>
                            <span class="setting-value">{{ posterLabel(getActiveOpts(`${templateId}::${preset.id}`, preset)) }}</span>
                          </div>
                          <div class="setting-item">
                            <span class="setting-label">Logo source</span>
                            <span class="setting-value">{{ logoSourceLabel(getActiveOpts(`${templateId}::${preset.id}`, preset).logoSource) || 'Default' }}</span>
                          </div>
                          <div class="setting-item">
                            <span class="setting-label">Matte</span>
                            <span class="setting-value">{{ pct(getActiveOpts(`${templateId}::${preset.id}`, preset).matte_height_ratio) }}</span>
                          </div>
                          <div class="setting-item">
                            <span class="setting-label">Fade</span>
                            <span class="setting-value">{{ pct(getActiveOpts(`${templateId}::${preset.id}`, preset).fade_height_ratio) }}</span>
                          </div>
                          <div class="setting-item">
                            <span class="setting-label">Vignette</span>
                            <span class="setting-value">{{ getActiveOpts(`${templateId}::${preset.id}`, preset).vignette_strength != null ? getActiveOpts(`${templateId}::${preset.id}`, preset).vignette_strength : '—' }}</span>
                          </div>
                          <div class="setting-item">
                            <span class="setting-label">Text overlay</span>
                            <span class="setting-value" :class="getActiveOpts(`${templateId}::${preset.id}`, preset).text_overlay_enabled ? 'val-on' : 'val-off'">
                              {{ getActiveOpts(`${templateId}::${preset.id}`, preset).text_overlay_enabled ? 'On' : 'Off' }}
                            </span>
                          </div>
                          <div class="setting-item" v-if="getActiveOpts(`${templateId}::${preset.id}`, preset).text_overlay_enabled">
                            <span class="setting-label">Text</span>
                            <span class="setting-value setting-value-text">{{ getActiveOpts(`${templateId}::${preset.id}`, preset).custom_text || '—' }}</span>
                          </div>
                          <div class="setting-item">
                            <span class="setting-label">Border</span>
                            <span class="setting-value" :class="getActiveOpts(`${templateId}::${preset.id}`, preset).border_enabled ? 'val-on' : 'val-off'">
                              {{ getActiveOpts(`${templateId}::${preset.id}`, preset).border_enabled ? 'On' : 'Off' }}
                            </span>
                          </div>
                          <div class="setting-item" v-if="hasFallback(getActiveOpts(`${templateId}::${preset.id}`, preset))">
                            <span class="setting-label">Fallback</span>
                            <span class="setting-value">{{ fallbackSummary(getActiveOpts(`${templateId}::${preset.id}`, preset)) }}</span>
                          </div>
                        </div>
                      </template>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Import / Export (collapsible) -->
        <div class="section">
          <button class="section-toggle" @click="showImportExport = !showImportExport">
            <div class="toggle-left">
              <h3>Import / Export</h3>
              <span class="help">Backup or transfer presets as JSON</span>
            </div>
            <svg class="acc-chevron" :class="{ open: showImportExport }" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <div v-show="showImportExport" class="defaults-body">
            <textarea
              v-model="importText"
              placeholder="Paste preset JSON to import, or click Export to populate this field…"
              rows="8"
              class="import-box"
            ></textarea>
            <div class="actions" style="justify-content:flex-start;">
              <button class="primary" @click="handleImport" :disabled="importing || !importText.trim()">
                {{ importing ? 'Importing…' : 'Import JSON' }}
              </button>
              <button class="secondary" @click="importText = ''" :disabled="!importText.trim()">Clear</button>
            </div>
          </div>
        </div>

      </div><!-- /column -->

      <!-- Preview panel -->
      <div class="section preview-panel">
        <div class="section-header">
          <h3>Preview</h3>
          <span class="help">Click ▶ on any preset</span>
        </div>
        <div class="preview-controls">
          <div class="actions">
            <button class="secondary tiny" @click="movieSearchTerm = ''; showMovieSearch = true" :disabled="movies.length === 0">Search movie</button>
            <button class="secondary tiny" @click="useRandomPreviewMovie" :disabled="movies.length === 0">Random</button>
          </div>
          <div v-if="selectedPreviewMovie" class="selected-movie-chip">
            <span class="chip-label">Using</span>
            <span class="chip-title">{{ selectedPreviewMovie.title }}</span>
            <button class="icon-btn tiny" @click="clearSelectedPreviewMovie" title="Clear">×</button>
          </div>
        </div>
        <div class="preview-box">
          <div v-if="previewLoading" class="loading-state">
            <div class="spinner"></div>
            <p>Rendering…</p>
          </div>
          <div v-else-if="previewError" class="error-state"><p>{{ previewError }}</p></div>
          <div v-else-if="previewUrl" class="preview-content">
            <img :src="previewUrl" alt="Preview" />
            <div class="preview-info">
              <div class="preview-details">
                <p class="preview-template" v-if="previewTemplate">
                  <strong>{{ previewTemplate.templateId }}</strong> / {{ previewTemplate.presetName }}
                </p>
                <p class="preview-movie" v-if="previewMovie">{{ previewMovie.title }}</p>
              </div>
              <button class="secondary tiny" @click="useRandomPreviewMovie">Random</button>
            </div>
          </div>
          <div v-else class="placeholder-state">
            <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
            </svg>
            <p>Click ▶ on a preset to preview</p>
          </div>
        </div>
      </div>
    </div><!-- /layout -->

    <!-- Movie search modal -->
    <div v-if="showMovieSearch" class="modal-overlay" @click="showMovieSearch = false">
      <div class="modal search-modal" @click.stop>
        <div class="modal-header">
          <h4>Select preview movie</h4>
          <button class="icon-btn" @click="showMovieSearch = false">×</button>
        </div>
        <div class="modal-body">
          <input type="text" v-model="movieSearchTerm" placeholder="Search by title…" autofocus />
          <div class="search-results">
            <button v-for="movie in movieSearchResults" :key="movie.key" class="search-result" @click="selectPreviewMovie(movie)">
              <span class="title">{{ movie.title }}</span>
            </button>
            <p v-if="!movieSearchResults.length" class="help small">No movies match.</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Fallback rules modal -->
    <div v-if="showFallbackModal && modalPreset" class="modal-overlay" @click="showFallbackModal = false">
      <div class="modal" @click.stop>
        <div class="modal-header">
          <h4>Fallback rules — {{ modalPreset.preset.name || modalPreset.preset.id }}</h4>
          <button class="icon-btn" @click="showFallbackModal = false">×</button>
        </div>
        <div class="modal-body">
          <p class="help small" style="margin-bottom: 12px;">
            Defines what happens when this preset's preferred poster or logo can't be found.
            Only applies in batch, webhook and scheduled renders — not the manual editor.
          </p>

          <h5>Logo source override</h5>
          <div class="grid">
            <label>
              <span class="label-text">Logo source</span>
              <select v-model="modalFallback.logoSource">
                <option value="">Use default setting</option>
                <option value="tmdb">TMDb only</option>
                <option value="fanart">Fanart.tv only</option>
                <option value="tmdb_fanart">TMDb first, Fanart fallback</option>
                <option value="fanart_tmdb">Fanart first, TMDb fallback</option>
                <option value="both">Both merged</option>
              </select>
            </label>
          </div>

          <h5>Poster fallback</h5>
          <div class="grid">
            <label>
              <span class="label-text">{{ posterFallbackLabel }}</span>
              <select v-model="modalFallback.fallbackPosterAction">
                <option value="continue">Continue with first available</option>
                <option value="skip">Skip — don't render</option>
                <option value="template">Use a different preset</option>
              </select>
            </label>
            <div v-if="modalFallback.fallbackPosterAction === 'template'" class="grid subgrid">
              <label>
                <span class="label-text">Fallback template</span>
                <select v-model="modalFallback.fallbackPosterTemplate">
                  <option value="">Select template</option>
                  <option v-for="(_, tplId) in presets" :key="tplId" :value="tplId">{{ tplId }}</option>
                </select>
              </label>
              <label>
                <span class="label-text">Fallback preset</span>
                <select v-model="modalFallback.fallbackPosterPreset" :disabled="!modalFallback.fallbackPosterTemplate">
                  <option value="">Use first preset</option>
                  <option v-for="p in (modalFallback.fallbackPosterTemplate ? presets[modalFallback.fallbackPosterTemplate]?.presets || [] : [])" :key="p.id" :value="p.id">{{ p.name || p.id }}</option>
                </select>
              </label>
            </div>
          </div>

          <h5>Logo fallback</h5>
          <div class="grid">
            <label>
              <span class="label-text">{{ logoFallbackLabel }}</span>
              <select v-model="modalFallback.fallbackLogoAction">
                <option value="continue">Continue with render</option>
                <option value="skip">Skip — don't render</option>
                <option value="template">Use a different preset</option>
              </select>
            </label>
            <div v-if="modalFallback.fallbackLogoAction === 'template'" class="grid subgrid">
              <label>
                <span class="label-text">Fallback template</span>
                <select v-model="modalFallback.fallbackLogoTemplate">
                  <option value="">Select template</option>
                  <option v-for="(_, tplId) in presets" :key="tplId" :value="tplId">{{ tplId }}</option>
                </select>
              </label>
              <label>
                <span class="label-text">Fallback preset</span>
                <select v-model="modalFallback.fallbackLogoPreset" :disabled="!modalFallback.fallbackLogoTemplate">
                  <option value="">Use first preset</option>
                  <option v-for="p in (modalFallback.fallbackLogoTemplate ? presets[modalFallback.fallbackLogoTemplate]?.presets || [] : [])" :key="p.id" :value="p.id">{{ p.name || p.id }}</option>
                </select>
              </label>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="secondary" @click="showFallbackModal = false">Cancel</button>
          <button class="primary" @click="savePresetFallback">Save</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.template-manager {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1400px;
  margin: 0 auto;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header h2 {
  margin: 0;
  font-size: 1.75rem;
  background: linear-gradient(135deg, #3dd6b7, #5b8dee);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.subtitle {
  color: var(--text-secondary, #9aa4b5);
  margin: 6px 0 0;
  font-size: 0.95rem;
}
.pill {
  padding: 8px 14px;
  border-radius: 999px;
  background: rgba(61, 214, 183, 0.15);
  color: var(--accent, #3dd6b7);
  font-weight: 600;
  font-size: 0.9rem;
}
.layout {
  display: grid;
  grid-template-columns: 1.4fr 0.6fr;
  gap: 20px;
  align-items: start;
}
@media (max-width: 1200px) {
  .layout { grid-template-columns: 1fr; }
}
.column {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.section {
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 12px;
  padding: 20px;
  background: var(--surface, #161b28);
  display: flex;
  flex-direction: column;
  gap: 0;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.section-header h3 { margin: 0; font-size: 1.1rem; }

/* Collapsible section toggle */
.section-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  width: 100%;
  text-align: left;
  color: inherit;
  font-family: inherit;
  margin-bottom: 0;
}
.toggle-left { display: flex; flex-direction: column; gap: 2px; }
.toggle-left h3 { margin: 0; font-size: 1.1rem; }
.defaults-body { display: flex; flex-direction: column; gap: 14px; margin-top: 16px; }

.acc-chevron { transition: transform 0.2s; flex-shrink: 0; color: var(--text-secondary); }
.acc-chevron.open { transform: rotate(180deg); }

.help {
  color: var(--text-secondary, #9aa4b5);
  font-size: 0.85rem;
}
.help.small { display: block; font-size: 0.8rem; margin-top: 4px; }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  align-items: flex-end;
}
.grid.preferences-grid { grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); }
.grid.subgrid { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }

.label-text { display: block; margin-bottom: 6px; color: var(--text-secondary, #9aa4b5); font-size: 0.9rem; }

select, textarea, input {
  width: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--border, #2a2f3e);
  background: var(--input-bg, #111623);
  color: var(--text-primary, #fff);
  font-family: inherit;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
}
select:focus, textarea:focus, input:focus {
  outline: none;
  border-color: rgba(61, 214, 183, 0.5);
  box-shadow: 0 0 0 3px rgba(61, 214, 183, 0.1);
}

.primary, .secondary {
  padding: 10px 16px;
  border-radius: 8px;
  border: 1px solid var(--border, #2a2f3e);
  background: var(--surface, #1e2435);
  color: var(--text-primary, #fff);
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
  font-family: inherit;
}
.primary {
  background: linear-gradient(135deg, #3dd6b7, #5b8dee);
  border: none;
  color: #0a0f1a;
  font-weight: 600;
}
.primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(61, 214, 183, 0.3); }
.secondary:hover:not(:disabled) { background: var(--surface-hover, #252b3f); border-color: rgba(61, 214, 183, 0.3); }
.primary:disabled, .secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.secondary.tiny { padding: 6px 12px; font-size: 0.85rem; }

.actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.import-box {
  width: 100%;
  min-height: 140px;
  resize: vertical;
  font-family: 'Courier New', monospace;
  font-size: 0.9rem;
}
.loading { color: var(--text-secondary, #9aa4b5); padding: 20px; text-align: center; }

/* Presets list */
.presets-list { display: flex; flex-direction: column; gap: 16px; }
.template-block {
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 10px;
  padding: 14px;
  background: rgba(255,255,255,0.02);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.template-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.template-header h4 { margin: 0; font-size: 0.95rem; color: var(--accent, #3dd6b7); }
.count { color: var(--text-secondary, #9aa4b5); font-size: 0.85rem; }

/* Preset cards — now full-width list items */
.preset-cards { display: flex; flex-direction: column; gap: 6px; }

.preset-card {
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 8px;
  background: rgba(0,0,0,0.15);
  transition: border-color 0.2s;
  overflow: hidden;
}
.preset-card:hover { border-color: rgba(61, 214, 183, 0.3); }
.preset-card.selected { border-color: rgba(61, 214, 183, 0.6); background: rgba(61, 214, 183, 0.04); }
.preset-card.expanded { border-color: rgba(91, 141, 238, 0.5); }

/* Card header row */
.preset-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: default;
}
.checkbox { display: flex; align-items: center; flex-shrink: 0; }
.checkbox input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; margin: 0; }

.preset-card-title {
  display: flex;
  flex-direction: column;
  gap: 1px;
  cursor: pointer;
  min-width: 0;
  flex-shrink: 0;
  width: 130px;
}
.preset-name { font-weight: 600; font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.preset-id { color: var(--text-secondary, #9aa4b5); font-size: 0.75rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Chip summary row */
.preset-chips {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  flex: 1;
  cursor: pointer;
}
.chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 600;
  border: 1px solid transparent;
  white-space: nowrap;
}
.chip-default { background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.1); color: #c0cce0; }
.chip-white { background: rgba(220,230,255,0.1); border-color: rgba(220,230,255,0.25); color: #dce6ff; }
.chip-accent { background: rgba(61,214,183,0.12); border-color: rgba(61,214,183,0.3); color: #3dd6b7; }
.chip-muted { background: rgba(150,160,180,0.1); border-color: rgba(150,160,180,0.2); color: #8090a8; }
.chip-warn { background: rgba(255,170,80,0.12); border-color: rgba(255,170,80,0.3); color: #ffaa50; cursor: help; }
.chip-season { background: rgba(139,92,246,0.12); border-color: rgba(139,92,246,0.3); color: #a78bfa; }
.chip-key { opacity: 0.55; font-weight: 500; margin-right: 4px; }
.chip-val { font-weight: 700; }

/* Action buttons */
.preset-actions { display: flex; gap: 4px; flex-shrink: 0; }
.icon-btn {
  border: 1px solid var(--border, #2a2f3e);
  background: rgba(0,0,0,0.3);
  color: var(--text-secondary, #9aa4b5);
  border-radius: 6px;
  padding: 5px 8px;
  cursor: pointer;
  transition: all 0.15s;
  font-size: 0.9rem;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.icon-btn.tiny { padding: 3px 7px; font-size: 0.8rem; }
.icon-btn:hover:not(:disabled) { background: rgba(255,255,255,0.1); color: var(--text-primary, #fff); }
.icon-btn.danger { border-color: rgba(255,107,107,0.4); color: #ff6b6b; }
.icon-btn.danger:hover:not(:disabled) { background: rgba(255,107,107,0.15); border-color: #ff6b6b; }
.icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.chevron { transition: transform 0.2s; }
.chevron.open { transform: rotate(180deg); }

/* Expanded card body */
.preset-card-body {
  border-top: 1px solid var(--border, #2a2f3e);
  padding: 12px 14px;
  background: rgba(0,0,0,0.1);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Series/Season tabs */
.preset-tabs { display: flex; gap: 4px; }
.preset-tab {
  padding: 4px 14px;
  border-radius: 6px;
  border: 1px solid var(--border, #2a2f3e);
  background: none;
  color: var(--text-secondary, #9aa4b5);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.preset-tab:hover { background: rgba(255,255,255,0.05); color: var(--text-primary); }
.preset-tab.active {
  background: rgba(61,214,183,0.12);
  border-color: rgba(61,214,183,0.35);
  color: #3dd6b7;
}
.tab-note { color: var(--text-secondary); font-weight: 400; margin-left: 4px; font-size: 0.75rem; }

/* Settings grid */
.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 6px 12px;
}
.setting-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.05);
}
.setting-label { font-size: 0.72rem; color: var(--text-secondary, #9aa4b5); text-transform: uppercase; letter-spacing: 0.5px; }
.setting-value { font-size: 0.85rem; font-weight: 600; color: var(--text-primary, #dce6ff); }
.setting-value-text { font-size: 0.8rem; font-weight: 400; font-style: italic; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.val-on { color: #3dd6b7; }
.val-off { color: var(--text-secondary, #9aa4b5); font-weight: 400; }

.no-season-note {
  font-size: 0.85rem;
  color: var(--text-secondary);
  font-style: italic;
  padding: 8px;
}

/* Preview panel */
.preview-panel { position: sticky; top: 24px; align-self: flex-start; gap: 16px; }
.preview-controls { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
.selected-movie-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 10px;
  background: rgba(61,214,183,0.08);
  font-size: 0.85rem;
}
.chip-label { font-size: 0.75rem; color: var(--text-secondary, #9aa4b5); text-transform: uppercase; letter-spacing: 0.04em; }
.chip-title { font-weight: 600; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.preview-box {
  min-height: 380px;
  border: 2px dashed var(--border, #2a2f3e);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.2);
}
.preview-content { display: flex; flex-direction: column; gap: 12px; align-items: center; width: 100%; }
.preview-box img { max-width: 100%; max-height: 560px; border-radius: 8px; box-shadow: 0 12px 40px rgba(0,0,0,0.4); }
.preview-info { display: flex; flex-direction: column; gap: 8px; align-items: center; width: 100%; }
.preview-details { display: flex; flex-direction: column; gap: 4px; align-items: center; text-align: center; }
.preview-template { margin: 0; color: var(--accent, #3dd6b7); font-size: 0.9rem; }
.preview-movie { margin: 0; color: var(--text-secondary, #9aa4b5); font-size: 0.82rem; }

.placeholder-state { display: flex; flex-direction: column; align-items: center; gap: 12px; color: var(--text-secondary, #9aa4b5); opacity: 0.5; }
.placeholder-state p { margin: 0; font-size: 0.9rem; }
.loading-state { display: flex; flex-direction: column; align-items: center; gap: 16px; color: var(--text-secondary); }
.loading-state p { margin: 0; }
.error-state { color: #ff6b6b; text-align: center; padding: 20px; }
.error-state p { margin: 0; }

.spinner {
  width: 36px; height: 36px;
  border: 3px solid rgba(61,214,183,0.2);
  border-top-color: #3dd6b7;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Modals */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.7);
  display: flex; align-items: center; justify-content: center;
  z-index: 999; padding: 1rem;
  backdrop-filter: blur(4px);
}
.modal {
  background: var(--surface, #161b28);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 12px;
  padding: 24px;
  width: 560px;
  max-width: 95vw;
  display: flex; flex-direction: column; gap: 16px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
  max-height: 90vh;
  overflow-y: auto;
}
.modal.search-modal { width: 480px; }
.modal-header { display: flex; align-items: center; justify-content: space-between; }
.modal-header h4 { margin: 0; font-size: 1.1rem; }
.modal-body h5 { margin: 16px 0 8px; color: var(--accent, #3dd6b7); font-size: 0.95rem; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }

.search-results { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; max-height: 300px; overflow: auto; }
.search-result {
  width: 100%; text-align: left; padding: 9px 12px;
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 8px; background: rgba(255,255,255,0.03);
  color: var(--text-primary, #fff); cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  font-family: inherit;
}
.search-result:hover { border-color: rgba(61,214,183,0.4); background: rgba(61,214,183,0.06); }
.search-result .title { font-weight: 600; display: block; font-size: 0.9rem; }

@media (max-width: 900px) {
  .preset-chips { display: none; }
  .preset-card-title { width: auto; flex: 1; }
  .settings-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
