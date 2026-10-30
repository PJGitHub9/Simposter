<script setup lang="ts">
import { computed, nextTick, ref, type WritableComputedRef } from 'vue'

const props = defineProps<{
  movieSaveLocation: string
  tvShowSaveLocation: string
  collectionSaveLocation: string
  tvShowSaveMode: string
  saveBatchInSubfolder: boolean
  saveToAssetFolderOnSend: boolean
  outputFormat: string
  jpgQuality: number
  pngCompression: number
  webpQuality: number
  unsavedChanges: boolean
  imageQualityChanged?: boolean
}>()

const emit = defineEmits<{
  'update:movieSaveLocation': [value: string]
  'update:tvShowSaveLocation': [value: string]
  'update:collectionSaveLocation': [value: string]
  'update:tvShowSaveMode': [value: string]
  'update:saveBatchInSubfolder': [value: boolean]
  'update:saveToAssetFolderOnSend': [value: boolean]
  'update:outputFormat': [value: string]
  'update:jpgQuality': [value: number]
  'update:pngCompression': [value: number]
  'update:webpQuality': [value: number]
  'save': []
}>()

const localMovieSaveLocation = computed({
  get: () => props.movieSaveLocation,
  set: (val) => emit('update:movieSaveLocation', val)
})

const localTvShowSaveLocation = computed({
  get: () => props.tvShowSaveLocation,
  set: (val) => emit('update:tvShowSaveLocation', val)
})

const localCollectionSaveLocation = computed({
  get: () => props.collectionSaveLocation,
  set: (val) => emit('update:collectionSaveLocation', val)
})

const localTvShowSaveMode = computed({
  get: () => props.tvShowSaveMode,
  set: (val) => emit('update:tvShowSaveMode', val)
})

const localSaveBatchInSubfolder = computed({
  get: () => props.saveBatchInSubfolder,
  set: (val) => emit('update:saveBatchInSubfolder', val)
})

const localSaveToAssetFolderOnSend = computed({
  get: () => props.saveToAssetFolderOnSend,
  set: (val) => emit('update:saveToAssetFolderOnSend', val)
})

const localOutputFormat = computed({
  get: () => props.outputFormat,
  set: (val) => emit('update:outputFormat', val)
})

const localJpgQuality = computed({
  get: () => props.jpgQuality,
  set: (val) => emit('update:jpgQuality', val)
})

const localPngCompression = computed({
  get: () => props.pngCompression,
  set: (val) => emit('update:pngCompression', val)
})

const localWebpQuality = computed({
  get: () => props.webpQuality,
  set: (val) => emit('update:webpQuality', val)
})

interface SavePreset {
  key: string
  label: string
  description: string
  movie: string
  tv: string
}

// The {filename} token resolves to "poster" (movies, TV series poster) or "SeasonNN"
// (TV season poster) at save time — see backend/save_paths.py. Flat and Asset folders
// both use {filename} for per-item naming (poster vs SeasonNN) so movie and season
// posters never collide on disk — they differ only in whether that filename sits
// directly in the library folder (Flat) or inside a per-title subfolder (Asset
// folders, Kometa's own on-disk convention). "Flat" here is Simposter's own take,
// not a Kometa convention — Kometa itself has no flat-file layout for season posters.
const PRESETS: SavePreset[] = [
  {
    key: 'default',
    label: 'Default',
    description: 'One file per item in each library folder.',
    movie: '/config/output/{library}/{title}.jpg',
    tv: '/config/output/{library}/{title} ({year}).jpg',
  },
  {
    key: 'flat',
    label: 'Flat',
    description: 'Title (Year) files in each library folder, no subfolders.',
    movie: '/config/output/{library}/{title} ({year}).jpg',
    tv: '/config/output/{library}/{title} ({year}) {filename}.jpg',
  },
  {
    key: 'assetFolders',
    label: 'Kometa asset folders',
    description: 'A folder per movie or show, ready for Kometa.',
    movie: '/config/output/{library}/{title} ({year})/{filename}.jpg',
    tv: '/config/output/{library}/{title} ({year})/{filename}.jpg',
  },
]

// Explicit "I want to hand-edit" override — lets a user unlock the fields from a
// preset baseline without having typed anything yet (so activePresetKey would still
// otherwise match that preset exactly).
const customUnlocked = ref(false)

const activePresetKey = computed(() => {
  const match = PRESETS.find(p => p.movie === localMovieSaveLocation.value && p.tv === localTvShowSaveLocation.value)
  return match ? match.key : 'custom'
})

const isCustomActive = computed(() => customUnlocked.value || activePresetKey.value === 'custom')

const applyPreset = (preset: SavePreset) => {
  customUnlocked.value = false
  localMovieSaveLocation.value = preset.movie
  localTvShowSaveLocation.value = preset.tv
}

const unlockCustom = () => {
  customUnlocked.value = true
}

// The flat/nested structure toggle only affects templates that don't use the newer
// {filename} token — Kometa presets always include it, so the toggle would have no
// effect there and is hidden to avoid implying it does something.
const showTvStructureMode = computed(() => !localTvShowSaveLocation.value.includes('{filename}'))

// ---- Live examples -------------------------------------------------------
// A faithful port of backend/save_paths.py's apply_save_location_variables(),
// _sanitize() and resolve_save_path()'s extension handling, so the examples
// show exactly the file a save would write. Keep the two in step.

interface SampleCtx {
  title: string
  year?: number
  season?: number | null
  isTv: boolean
  library: string
  key: string
  folder?: string
}

const SAMPLE_MOVIE: SampleCtx = { title: 'Inception', year: 2010, isTv: false, library: 'Movies', key: '12345', folder: 'Inception (2010)' }
const SAMPLE_SHOW: SampleCtx = { title: 'Breaking Bad', year: 2008, isTv: true, library: 'TV Shows', key: '67890', folder: 'Breaking Bad (2008)', season: null }
const SAMPLE_SEASON: SampleCtx = { ...SAMPLE_SHOW, season: 1 }
const SAMPLE_COLLECTION: SampleCtx = { title: 'The Dark Knight Collection', isTv: false, library: 'Movies', key: '555' }

const pad2 = (n: number) => String(n).padStart(2, '0')
const replaceAll = (s: string, find: string, rep: string) => s.split(find).join(rep)

function substitute(template: string, ctx: SampleCtx, tvMode: string): string {
  let r = template
  r = replaceAll(r, '{library}', ctx.library)
  r = replaceAll(r, '{year}', ctx.year ? String(ctx.year) : '')
  r = replaceAll(r, '{key}', ctx.key)
  r = replaceAll(r, '{folder}', ctx.folder || ctx.title)
  const season = ctx.isTv && ctx.season != null ? ctx.season : null
  if (r.includes('{filename}')) {
    r = replaceAll(r, '{filename}', season != null ? `Season${pad2(season)}` : 'poster')
    r = replaceAll(r, '{title}', ctx.title)
    r = replaceAll(r, '{season}', season != null ? `s${pad2(season)}` : '')
  } else if (ctx.isTv) {
    const nested = tvMode === 'nested'
    if (season != null) {
      const s = `s${pad2(season)}`
      r = replaceAll(r, '{title}', nested ? `${ctx.title}/${s}` : `${ctx.title} - ${s}`)
      r = replaceAll(r, '{season}', s)
    } else {
      r = replaceAll(r, '{title}', nested ? `${ctx.title}/series` : `${ctx.title} - series`)
      r = replaceAll(r, '{season}', '')
    }
  } else {
    r = replaceAll(r, '{title}', ctx.title)
    r = replaceAll(r, '{season}', ctx.season ? `s${pad2(ctx.season)}` : '')
  }
  r = replaceAll(r, '//', '/')
  r = r.split(/\s+/).filter(Boolean).join(' ')
  r = r.replace(/\s*[-_]\s*\./g, '.')
  r = r.replace(/\s*\(\s*\)/g, '')
  r = r.replace(/\s*\[\s*\]/g, '')
  r = r.replace(/\s{2,}/g, ' ')
  return r
}

const outputExt = computed(() => '.' + (localOutputFormat.value || 'jpg'))

// Characters the backend's _sanitize() removes (Windows/Linux-illegal + control).
const ILLEGAL_CHARS = new Set(['<', '>', ':', '"', '\\', '|', '?', '*'])

function resolveExample(template: string, ctx: SampleCtx): string {
  if (!template) return ''
  const substituted = substitute(template, ctx, localTvShowSaveMode.value)
  const safe = Array.from(substituted).filter(c => !ILLEGAL_CHARS.has(c) && c.charCodeAt(0) >= 32).join('').trim()
  const parts = safe.split('/')
  const name = parts.pop() || ''
  const dot = name.lastIndexOf('.')
  const file = dot > 0 ? name.slice(0, dot) + outputExt.value : `${name}/poster${outputExt.value}`
  const full = [...parts, file].join('/')
  return full.startsWith('/config/output/') ? full.slice('/config/output/'.length) : full
}

function examplesFor(movieTpl: string, tvTpl: string) {
  return [
    { label: 'Movie', path: resolveExample(movieTpl, SAMPLE_MOVIE) },
    { label: 'Show', path: resolveExample(tvTpl, SAMPLE_SHOW) },
    { label: 'Season', path: resolveExample(tvTpl, SAMPLE_SEASON) },
  ]
}

// ---- Custom templates ----------------------------------------------------

type FieldKey = 'movie' | 'tv' | 'collection'

const VAR_HELP: Record<string, string> = {
  '{library}': 'Library name, e.g. "Movies"',
  '{title}': 'Title, e.g. "Inception"',
  '{year}': 'Release year, e.g. 2010',
  '{folder}': "The item's real folder name on disk (from the media server); falls back to the title. Show level only for TV.",
  '{key}': "The item's id on the media server",
  '{filename}': '"poster", or "Season01" for a season poster (Kometa asset naming)',
  '{season}': 'Season as "s01" (season posters only)',
}

const TEMPLATE_FIELDS: { key: FieldKey; label: string; placeholder: string; vars: string[] }[] = [
  { key: 'movie', label: 'Movies', placeholder: '/config/output/{library}/{title} ({year}).jpg', vars: ['{library}', '{title}', '{year}', '{folder}', '{key}', '{filename}'] },
  { key: 'tv', label: 'TV shows and seasons', placeholder: '/config/output/{library}/{title} ({year})/{filename}.jpg', vars: ['{library}', '{title}', '{year}', '{folder}', '{season}', '{filename}'] },
  { key: 'collection', label: 'Collections', placeholder: '/config/output/{library}/Collections/{title}.jpg', vars: ['{library}', '{title}', '{key}', '{filename}'] },
]

function templateModel(key: FieldKey): WritableComputedRef<string> {
  return key === 'movie' ? localMovieSaveLocation : key === 'tv' ? localTvShowSaveLocation : localCollectionSaveLocation
}

function fieldExample(key: FieldKey): string {
  const tpl = templateModel(key).value
  if (key === 'movie') return resolveExample(tpl, SAMPLE_MOVIE)
  if (key === 'collection') return resolveExample(tpl, SAMPLE_COLLECTION)
  return `${resolveExample(tpl, SAMPLE_SHOW)}  ·  ${resolveExample(tpl, SAMPLE_SEASON)}`
}

const inputRefs: Partial<Record<FieldKey, HTMLInputElement>> = {}
function setInputRef(key: FieldKey, el: unknown) {
  if (el instanceof HTMLInputElement) inputRefs[key] = el
}

function insertVar(key: FieldKey, token: string) {
  const model = templateModel(key)
  const el = inputRefs[key]
  const value = model.value || ''
  const start = el?.selectionStart ?? value.length
  const end = el?.selectionEnd ?? value.length
  model.value = value.slice(0, start) + token + value.slice(end)
  nextTick(() => {
    if (!el) return
    el.focus()
    const pos = start + token.length
    el.setSelectionRange(pos, pos)
  })
}
</script>

<template>
  <div class="tab-content">
    <h2>Output</h2>

    <!-- Image Quality -->
    <div class="section" :class="{ 'unsaved-changes': imageQualityChanged }">
      <h3>Image Quality</h3>
      <p class="section-description">
        Applies to the Preview and Save to Disk. Sending to a media server always uses the best quality that fits.
        <span
          class="info-dot"
          title="A send uses PNG when it's under the server's upload size limit, otherwise a high-quality JPEG. Resending an already-saved file (e.g. from Local Assets) reuses that file as it is, so a file saved at a lower quality here is resent at that quality."
        >ⓘ</span>
      </p>

      <div class="quality-row">
        <label class="inline-field">
          <span class="label-text">Format</span>
          <select v-model="localOutputFormat">
            <option value="jpg">JPEG</option>
            <option value="png">PNG</option>
            <option value="webp">WebP</option>
          </select>
        </label>

        <label v-if="localOutputFormat === 'jpg'" class="inline-field grow">
          <span class="label-text">Quality: {{ localJpgQuality }}%</span>
          <input type="range" v-model.number="localJpgQuality" min="1" max="100" step="1" />
        </label>
        <label v-else-if="localOutputFormat === 'png'" class="inline-field grow">
          <span class="label-text">Compression: {{ localPngCompression }} <span class="muted">(0 fast, 9 smallest)</span></span>
          <input type="range" v-model.number="localPngCompression" min="0" max="9" step="1" />
        </label>
        <label v-else class="inline-field grow">
          <span class="label-text">Quality: {{ localWebpQuality }}</span>
          <input type="range" v-model.number="localWebpQuality" min="1" max="100" step="1" />
        </label>
      </div>
    </div>

    <!-- Saving -->
    <div class="section">
      <h3>Saving</h3>
      <p class="section-description">How Save to Disk names its files. The examples update as you choose.</p>

      <div class="layout-grid">
        <button
          v-for="preset in PRESETS"
          :key="preset.key"
          type="button"
          class="layout-card"
          :class="{ active: !isCustomActive && activePresetKey === preset.key }"
          @click="applyPreset(preset)"
        >
          <span class="layout-title">{{ preset.label }}</span>
          <span class="layout-desc">{{ preset.description }}</span>
          <span class="layout-example">
            <span v-for="line in examplesFor(preset.movie, preset.tv)" :key="line.label" class="example-line">
              <span class="example-kind">{{ line.label }}</span>
              <code>{{ line.path }}</code>
            </span>
          </span>
        </button>

        <button
          type="button"
          class="layout-card"
          :class="{ active: isCustomActive }"
          @click="unlockCustom"
        >
          <span class="layout-title">Custom</span>
          <span class="layout-desc">Write your own naming with variables like {title} and {year}.</span>
          <span v-if="isCustomActive" class="layout-example">
            <span v-for="line in examplesFor(localMovieSaveLocation, localTvShowSaveLocation)" :key="line.label" class="example-line">
              <span class="example-kind">{{ line.label }}</span>
              <code>{{ line.path }}</code>
            </span>
          </span>
        </button>
      </div>
      <p class="help-text root-note">Paths are shown inside <code>/config/output</code>.</p>

      <label v-if="showTvStructureMode" class="inline-field structure-field">
        <span class="label-text">Show and season posters</span>
        <select v-model="localTvShowSaveMode">
          <option value="flat">All in the library folder</option>
          <option value="nested">In a folder per show</option>
        </select>
      </label>

      <!-- Templates: only when Custom is chosen -->
      <div v-if="isCustomActive" class="custom-fields">
        <div v-for="field in TEMPLATE_FIELDS" :key="field.key" class="template-field">
          <span class="label-text">{{ field.label }}</span>
          <input
            :ref="el => setInputRef(field.key, el)"
            :value="templateModel(field.key).value"
            type="text"
            :placeholder="field.placeholder"
            @input="templateModel(field.key).value = ($event.target as HTMLInputElement).value"
          />
          <div class="var-chips">
            <button
              v-for="v in field.vars"
              :key="v"
              type="button"
              class="var-chip"
              :title="VAR_HELP[v]"
              @click="insertVar(field.key, v)"
            >{{ v }}</button>
          </div>
          <span class="help-text">e.g. <code>{{ fieldExample(field.key) }}</code></span>
        </div>
      </div>

      <div class="options">
        <label class="checkbox-label">
          <input type="checkbox" v-model="localSaveToAssetFolderOnSend" />
          <span>Also save a copy when sending to a media server</span>
        </label>
        <span class="help-text checkbox-help">
          Writes the sent poster here too, so tools like Kometa can use it. Off: sent posters stay in Simposter's own cache (still resendable).
        </span>

        <label class="checkbox-label">
          <input type="checkbox" v-model="localSaveBatchInSubfolder" />
          <span>Put each batch run in its own folder</span>
        </label>
        <span class="help-text checkbox-help">
          e.g. <code>batch-2025-01-08-143022/Movies/…</code>
        </span>
      </div>
    </div>

    <div class="actions">
      <button @click="emit('save')" class="primary" :disabled="!unsavedChanges">
        {{ unsavedChanges ? 'Save Changes' : 'No Changes' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.tab-content {
  padding: 20px;
  max-width: 1600px;
}

h2 {
  margin-top: 0;
  margin-bottom: 24px;
  color: var(--text-primary);
  font-size: 24px;
}

h3 {
  margin-top: 0;
  margin-bottom: 16px;
  color: var(--text-secondary);
  font-size: 18px;
}

.section {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.section.unsaved-changes {
  background: rgba(255, 200, 0, 0.08);
  border-color: rgba(255, 200, 0, 0.4);
}

.section-description {
  color: var(--text-muted);
  font-size: 14px;
  margin-bottom: 20px;
  line-height: 1.5;
}


label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.label-text {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 14px;
}

.help-text {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: -4px;
}

.help-text code {
  background: rgba(255, 255, 255, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 11px;
  color: var(--accent);
}


.checkbox-label {
  flex-direction: row;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  margin-bottom: 4px;
}

.checkbox-label input[type="checkbox"] {
  width: auto;
  cursor: pointer;
}

.checkbox-label span {
  font-weight: 500;
  color: var(--text-primary);
}

.checkbox-help {
  margin-left: 30px;
  margin-top: 0;
}

input[type="text"],
select {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
}

input[type="text"] {
  font-family: 'Courier New', monospace;
}

select {
  cursor: pointer;
}

select option {
  background: var(--bg-primary);
  color: var(--text-primary);
}

input[type="range"] {
  width: 100%;
  max-width: 400px;
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  outline: none;
}

input[type="range"]::-webkit-slider-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
}

input[type="range"]::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  border: none;
}







.actions {
  display: flex;
  gap: 12px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
}

button {
  padding: 10px 20px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

button:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.08);
  border-color: var(--accent);
}

button.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

button.primary:hover:not(:disabled) {
  opacity: 0.9;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}






.muted {
  color: var(--text-muted);
  font-weight: 400;
}

.info-dot {
  cursor: help;
  color: var(--accent);
  margin-left: 4px;
}

.quality-row {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  align-items: flex-end;
}

.inline-field {
  margin-bottom: 0;
  min-width: 160px;
}

.inline-field.grow {
  flex: 1;
  min-width: 220px;
}

.inline-field select {
  width: auto;
  min-width: 160px;
}

.layout-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.layout-card {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  text-align: left;
  padding: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: var(--text-primary);
  font-weight: 400;
}

.layout-card:hover:not(:disabled) {
  border-color: var(--accent);
  transform: none;
}

.layout-card.active {
  border-color: var(--accent);
  background: rgba(61, 214, 183, 0.08);
  box-shadow: 0 0 0 1px var(--accent) inset;
}

.layout-title {
  font-weight: 600;
  font-size: 15px;
}

.layout-desc {
  font-size: 12px;
  color: var(--text-muted);
}

.layout-example {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 6px;
}

.example-line {
  display: grid;
  grid-template-columns: 48px 1fr;
  gap: 6px;
  align-items: baseline;
}

.example-kind {
  font-size: 11px;
  color: var(--text-muted);
}

.example-line code {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  color: var(--accent);
  word-break: break-all;
}

.root-note {
  margin-top: 8px;
}

.structure-field {
  margin-top: 16px;
}

.custom-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.template-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.var-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.var-chip {
  padding: 3px 8px;
  font-size: 12px;
  font-family: 'Courier New', monospace;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--accent);
}

.options {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.options .checkbox-help {
  margin-bottom: 10px;
}
</style>
