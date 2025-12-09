<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useNotification } from '@/composables/useNotification'

type Preset = { id: string; name: string; options: Record<string, any> }
type TemplatePresets = Record<string, { presets: Preset[] }>
type PresetFallback = {
  fallbackPosterAction?: 'continue' | 'skip' | 'template'
  fallbackPosterTemplate?: string
  fallbackPosterPreset?: string
  fallbackLogoAction?: 'continue' | 'skip' | 'template'
  fallbackLogoTemplate?: string
  fallbackLogoPreset?: string
}

const apiBase = getApiBase()
const { error: showError } = useNotification()

const presets = ref<TemplatePresets>({})
const loading = ref(false)
const exporting = ref(false)
const importing = ref(false)
const importText = ref('')
const fallbackPosterFilter = ref('all')
const fallbackLogoMode = ref('first')
const languagePreference = ref('en')
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
  fallbackLogoPreset: ''
})

// Preview state
const previewUrl = ref('')
const previewLoading = ref(false)
const previewError = ref('')
const previewMovie = ref<{ key: string; title: string } | null>(null)
const previewTemplate = ref<{ templateId: string; presetName: string } | null>(null)
const movies = ref<{ key: string; title: string }[]>([])

const presetCount = computed(() =>
  Object.values(presets.value).reduce((acc, tpl) => acc + (tpl.presets?.length || 0), 0)
)

const posterFallbackLabel = computed(() => {
  const opts = modalPreset.value?.preset.options || {}
  const pref = opts.poster_filter || opts.posterPreference || ''
  return pref ? `If ${pref} poster missing` : 'If poster preference missing'
})

const logoFallbackLabel = computed(() => {
  const opts = modalPreset.value?.preset.options || {}
  const pref = opts.logo_preference || ''
  return pref ? `If ${pref} logo missing` : 'If logo preference missing'
})

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
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Export failed')
  } finally {
    exporting.value = false
  }
}

const exportSingle = (templateId: string, preset: Preset) => {
  const payload: TemplatePresets = { [templateId]: { presets: [preset] } }
  importText.value = JSON.stringify(payload, null, 2)
}

const openFallbackModal = (templateId: string, preset: Preset) => {
  modalPreset.value = { templateId, preset }
  const opts = preset.options || {}
  modalFallback.value = {
    fallbackPosterAction: opts.fallbackPosterAction || 'continue',
    fallbackPosterTemplate: opts.fallbackPosterTemplate || '',
    fallbackPosterPreset: opts.fallbackPosterPreset || '',
    fallbackLogoAction: opts.fallbackLogoAction || 'continue',
    fallbackLogoTemplate: opts.fallbackLogoTemplate || '',
    fallbackLogoPreset: opts.fallbackLogoPreset || ''
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
      body: JSON.stringify({
        template_id: templateId,
        preset_id: preset.id,
        options: updated
      })
    })
    if (!res.ok) throw new Error(`API error ${res.status}`)
    await fetchPresets()
    showFallbackModal.value = false
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Failed to save fallback settings')
  }
}

const handleExportSelected = () => {
  const map: TemplatePresets = {}
  selectedPresets.value.forEach((key) => {
    const [tpl, pid] = key.split('::')
    const preset = presets.value[tpl]?.presets.find((p) => p.id === pid)
    if (!preset) return
    if (!map[tpl]) map[tpl] = { presets: [] }
    map[tpl].presets.push(preset)
  })
  if (Object.keys(map).length === 0) {
    handleExportAll()
    return
  }
  importText.value = JSON.stringify(map, null, 2)
}

const toggleSelected = (tplId: string, presetId: string) => {
  const key = `${tplId}::${presetId}`
  const set = new Set(selectedPresets.value)
  if (set.has(key)) set.delete(key)
  else set.add(key)
  selectedPresets.value = set
}

const deletePreset = async (templateId: string, presetId: string) => {
  if (!window.confirm(`Delete preset "${presetId}" from ${templateId}?`)) return
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
    fallbackLogoMode.value = data.logo_mode || 'first'
    languagePreference.value = data.language_preference || 'en'
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Failed to load fallback settings')
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
        logo_mode: fallbackLogoMode.value,
        language_preference: languagePreference.value
      })
    })
    if (!res.ok) throw new Error(`API error ${res.status}`)
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Failed to save fallback settings')
  } finally {
    savingFallback.value = false
  }
}

const fetchMovies = async () => {
  try {
    const res = await fetch(`${apiBase}/api/movies`)
    if (res.ok) {
      const data = await res.json()
      movies.value = Array.isArray(data) ? data.map((m: any) => ({ key: m.key, title: m.title })) : []
    }
  } catch {
    /* ignore */
  }
}

const pickRandomMovie = () => {
  if (!movies.value.length) return null
  const random = movies.value[Math.floor(Math.random() * movies.value.length)]
  return random
}

const previewPreset = async (templateId: string, preset: Preset) => {
  const movie = pickRandomMovie()
  if (!movie) {
    previewError.value = 'No movies available to preview'
    return
  }
  previewMovie.value = movie
  previewTemplate.value = { templateId, presetName: preset.name || preset.id }
  const posterUrl = `${apiBase}/api/movie/${movie.key}/poster`
  previewUrl.value = ''
  previewLoading.value = true
  previewError.value = ''
  try {
    const res = await fetch(`${apiBase}/api/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        template_id: templateId,
        background_url: posterUrl,
        logo_url: null,
        options: preset.options || {},
        preset_id: preset.id,
        movie_title: movie.title
      })
    })
    if (!res.ok) throw new Error(`Preview failed (${res.status})`)
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
        <h2>Template Manager</h2>
        <p class="subtitle">Manage presets and fallback rules for poster/logo selection.</p>
      </div>
      <span class="pill">{{ presetCount }} presets</span>
    </div>

    <div class="layout">
      <div class="column">
        <div class="section">
          <div class="section-header">
            <h3>Global Preset Preferences</h3>
            <span class="help">Applied before per-preset fallbacks</span>
          </div>
          <div class="grid preferences-grid">
            <label>
              <span class="label-text">Language preference (TMDb)</span>
              <select v-model="languagePreference">
                <option v-for="lang in languageOptions" :key="lang.code" :value="lang.code">
                  {{ lang.label }} ({{ lang.code }})
                </option>
              </select>
              <span class="help small">Falls back to the movie's original language, then English/any.</span>
            </label>
            <label>
              <span class="label-text">Default poster filter</span>
              <select v-model="fallbackPosterFilter">
                <option value="all">All posters (no filter)</option>
                <option value="en">English only</option>
                <option value="original">Original language only</option>
                <option value="no_text">No text/textless only</option>
              </select>
              <span class="help small">Filter posters by language or text presence.</span>
            </label>
            <label>
              <span class="label-text">Default logo selection</span>
              <select v-model="fallbackLogoMode">
                <option value="first">First available logo</option>
                <option value="white">White/light logo (low saturation)</option>
                <option value="color">Colored logo (high saturation)</option>
                <option value="none">No logo</option>
              </select>
              <span class="help small">Logo color detection uses HSV analysis for accurate selection.</span>
            </label>
          </div>
          <div class="actions" style="justify-content: flex-end;">
            <button class="primary" type="button" @click="saveFallback" :disabled="savingFallback">
              {{ savingFallback ? 'Saving…' : 'Save Preferences' }}
            </button>
          </div>
        </div>

        <div class="section">
          <div class="section-header">
            <h3>Presets</h3>
            <span class="help">Click a preset to preview, or select multiple to export.</span>
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
                  :class="{ selected: selectedPresets.has(`${templateId}::${preset.id}`) }"
                >
                  <label class="checkbox" @click.stop>
                    <input
                      type="checkbox"
                      :checked="selectedPresets.has(`${templateId}::${preset.id}`)"
                      @change="toggleSelected(templateId, preset.id)"
                    />
                  </label>
                  <div class="preset-text" @click="previewPreset(templateId, preset)">
                    <p class="preset-name">{{ preset.name || preset.id }}</p>
                    <p class="preset-id">{{ preset.id }}</p>
                  </div>
                  <div class="preset-actions">
                    <button
                      class="icon-btn"
                      @click.stop="openFallbackModal(templateId, preset)"
                      title="Configure fallback"
                    >
                      ⚙
                    </button>
                    <button
                      class="icon-btn danger"
                      @click.stop="deletePreset(templateId, preset.id)"
                      :disabled="deleting === `${templateId}::${preset.id}`"
                      title="Delete preset"
                    >
                      ×
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="actions" style="justify-content:flex-start;">
            <button class="secondary" @click="handleExportSelected" :disabled="exporting">
              {{ exporting ? 'Exporting…' : selectedPresets.size > 0 ? `Export ${selectedPresets.size} selected` : 'Export all' }}
            </button>
          </div>
        </div>

        <div class="section">
          <div class="section-header">
            <h3>Import JSON</h3>
            <span class="help">Paste preset JSON to import</span>
          </div>
          <textarea
            v-model="importText"
            placeholder='Paste preset JSON here...'
            rows="8"
            class="import-box"
          ></textarea>
          <div class="actions" style="justify-content:flex-start;">
            <button class="primary" @click="handleImport" :disabled="importing || !importText.trim()">
              {{ importing ? 'Importing…' : 'Import JSON' }}
            </button>
            <button class="secondary" @click="importText = ''" :disabled="!importText.trim()">
              Clear
            </button>
          </div>
        </div>
      </div>

      <div class="section preview-panel">
        <div class="section-header">
          <h3>Preview</h3>
          <span class="help">Click any preset to render</span>
        </div>
        <div class="preview-box">
          <div v-if="previewLoading" class="loading-state">
            <div class="spinner"></div>
            <p>Rendering preview...</p>
          </div>
          <div v-else-if="previewError" class="error-state">
            <p>{{ previewError }}</p>
          </div>
          <div v-else-if="previewUrl" class="preview-content">
            <img :src="previewUrl" alt="Preview" />
            <div class="preview-info">
              <div class="preview-details">
                <p class="preview-template" v-if="previewTemplate">
                  <strong>{{ previewTemplate.templateId }}</strong> / {{ previewTemplate.presetName }}
                </p>
                <p class="preview-movie" v-if="previewMovie">{{ previewMovie.title }}</p>
              </div>
              <button class="secondary tiny" @click="previewMovie = pickRandomMovie(); previewUrl = ''">
                Change Movie
              </button>
            </div>
          </div>
          <div v-else class="placeholder-state">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
              <circle cx="8.5" cy="8.5" r="1.5"></circle>
              <polyline points="21 15 16 10 5 21"></polyline>
            </svg>
            <p>Click a preset to preview</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Fallback modal -->
    <div v-if="showFallbackModal && modalPreset" class="modal-overlay" @click="showFallbackModal = false">
      <div class="modal" @click.stop>
        <div class="modal-header">
          <h4>Fallback settings — {{ modalPreset.preset.name || modalPreset.preset.id }}</h4>
          <button class="icon-btn" @click="showFallbackModal = false">×</button>
        </div>
        <div class="modal-body">
          <h5>Poster fallback</h5>
          <div class="grid">
            <label>
              <span class="label-text">{{ posterFallbackLabel }}</span>
              <select v-model="modalFallback.fallbackPosterAction">
                <option value="continue">Continue with render (first available)</option>
                <option value="skip">Don't render</option>
                <option value="template">Use different template/preset</option>
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
                  <option value="">Use default / first preset</option>
                  <option
                    v-for="p in (presets[modalFallback.fallbackPosterTemplate]?.presets || [])"
                    :key="p.id"
                    :value="p.id"
                  >
                    {{ p.name || p.id }}
                  </option>
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
                <option value="skip">Don't render</option>
                <option value="template">Use different template/preset</option>
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
                  <option value="">Use default / first preset</option>
                  <option
                    v-for="p in (presets[modalFallback.fallbackLogoTemplate]?.presets || [])"
                    :key="p.id"
                    :value="p.id"
                  >
                    {{ p.name || p.id }}
                  </option>
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
  margin-bottom: 8px;
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
.section {
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 12px;
  padding: 20px;
  background: var(--surface, #161b28);
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.section-header h3 {
  margin: 0;
  font-size: 1.1rem;
}
.help {
  color: var(--text-secondary, #9aa4b5);
  font-size: 0.85rem;
}
.help.small {
  display: block;
  font-size: 0.8rem;
  margin-top: 4px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  align-items: flex-end;
}
.grid.preferences-grid {
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}
.grid.subgrid {
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
}
.label-text {
  display: block;
  margin-bottom: 6px;
  color: var(--text-secondary, #9aa4b5);
  font-size: 0.9rem;
}
select,
textarea,
input {
  width: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--border, #2a2f3e);
  background: var(--input-bg, #111623);
  color: var(--text-primary, #fff);
  font-family: inherit;
  transition: border-color 0.2s, box-shadow 0.2s;
}
select:focus,
textarea:focus,
input:focus {
  outline: none;
  border-color: rgba(61, 214, 183, 0.5);
  box-shadow: 0 0 0 3px rgba(61, 214, 183, 0.1);
}
.primary,
.secondary {
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
.primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(61, 214, 183, 0.3);
}
.secondary:hover:not(:disabled) {
  background: var(--surface-hover, #252b3f);
  border-color: rgba(61, 214, 183, 0.3);
}
.primary:disabled,
.secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.secondary.tiny {
  padding: 6px 12px;
  font-size: 0.85rem;
}
.actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.import-box {
  width: 100%;
  min-height: 140px;
  resize: vertical;
  font-family: 'Courier New', monospace;
  font-size: 0.9rem;
}
.loading {
  color: var(--text-secondary, #9aa4b5);
  padding: 20px;
  text-align: center;
}
.presets-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.template-block {
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 10px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.template-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.template-header h4 {
  margin: 0;
  font-size: 1rem;
  color: var(--accent, #3dd6b7);
}
.count {
  color: var(--text-secondary, #9aa4b5);
  font-size: 0.85rem;
}
.preset-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
}
.preset-card {
  border: 2px solid var(--border, #2a2f3e);
  border-radius: 10px;
  padding: 12px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 12px;
  align-items: center;
  background: rgba(0, 0, 0, 0.2);
  transition: all 0.2s;
  cursor: pointer;
}
.preset-card:hover {
  border-color: rgba(61, 214, 183, 0.4);
  background: rgba(61, 214, 183, 0.05);
  transform: translateY(-1px);
}
.preset-card.selected {
  border-color: rgba(61, 214, 183, 0.6);
  background: rgba(61, 214, 183, 0.08);
}
.preset-text {
  cursor: pointer;
}
.preset-name {
  margin: 0 0 4px 0;
  font-weight: 600;
  font-size: 0.95rem;
}
.preset-id {
  margin: 0;
  color: var(--text-secondary, #9aa4b5);
  font-size: 0.8rem;
}
.checkbox {
  display: flex;
  align-items: center;
  justify-content: center;
}
.checkbox input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
  margin: 0;
}
.preset-actions {
  display: flex;
  gap: 6px;
}
.icon-btn {
  border: 1px solid var(--border, #2a2f3e);
  background: rgba(0, 0, 0, 0.3);
  color: var(--text-secondary, #9aa4b5);
  border-radius: 6px;
  padding: 6px 10px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 1rem;
  line-height: 1;
}
.icon-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary, #fff);
}
.icon-btn.danger {
  border-color: rgba(255, 107, 107, 0.4);
  color: #ff6b6b;
}
.icon-btn.danger:hover:not(:disabled) {
  background: rgba(255, 107, 107, 0.15);
  border-color: #ff6b6b;
}
.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.layout {
  display: grid;
  grid-template-columns: 1.3fr 0.7fr;
  gap: 20px;
}
@media (max-width: 1200px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
.column {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.preview-panel {
  position: sticky;
  top: 24px;
  align-self: flex-start;
}
.preview-box {
  min-height: 400px;
  border: 2px dashed var(--border, #2a2f3e);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.2);
}
.preview-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  width: 100%;
}
.preview-box img {
  max-width: 100%;
  max-height: 600px;
  border-radius: 8px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
}
.preview-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  width: 100%;
}
.preview-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  text-align: center;
}
.preview-template {
  margin: 0;
  color: var(--accent, #3dd6b7);
  font-size: 0.95rem;
  font-weight: 500;
}
.preview-template strong {
  font-weight: 700;
}
.preview-movie {
  margin: 0;
  color: var(--text-secondary, #9aa4b5);
  font-size: 0.85rem;
}
.placeholder-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary, #9aa4b5);
  opacity: 0.6;
}
.placeholder-state svg {
  opacity: 0.5;
}
.placeholder-state p {
  margin: 0;
  font-size: 0.95rem;
}
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  color: var(--text-secondary, #9aa4b5);
}
.loading-state p {
  margin: 0;
}
.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(61, 214, 183, 0.2);
  border-top-color: #3dd6b7;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.error-state {
  color: #ff6b6b;
  text-align: center;
  padding: 20px;
}
.error-state p {
  margin: 0;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
  padding: 1rem;
  backdrop-filter: blur(4px);
}
.modal {
  background: var(--surface, #161b28);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 12px;
  padding: 24px;
  width: 560px;
  max-width: 95vw;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.modal-header h4 {
  margin: 0;
  font-size: 1.2rem;
}
.modal-body h5 {
  margin: 16px 0 8px;
  color: var(--accent, #3dd6b7);
  font-size: 1rem;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 8px;
}
</style>
