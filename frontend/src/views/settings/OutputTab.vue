<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  movieSaveLocation: string
  tvShowSaveLocation: string
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
// (TV season poster) at save time — see backend/save_paths.py. Kometa has no flat-file
// convention for season posters, so Flat and Asset folders necessarily produce the
// same TV layout; they only differ for movies.
const PRESETS: SavePreset[] = [
  {
    key: 'default',
    label: 'Default',
    description: 'Simposter\'s original layout — movies and TV shows saved by library.',
    movie: '/config/output/{library}/{title}.jpg',
    tv: '/config/output/{library}/{title} ({year}).jpg',
  },
  {
    key: 'flat',
    label: 'Flat (Kometa)',
    description: 'Movies as flat "Title (Year).ext" files. TV shows use per-item folders — Kometa has no flat season-poster naming.',
    movie: '/config/output/{library}/{title} ({year}).jpg',
    tv: '/config/output/{library}/{title} ({year})/{filename}.jpg',
  },
  {
    key: 'assetFolders',
    label: 'Asset folders (Kometa)',
    description: 'Every movie and show gets its own folder with poster.ext / SeasonNN.ext — Kometa\'s asset-folder convention.',
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
</script>

<template>
  <div class="tab-content">
    <h2>Output</h2>

    <!-- Image Quality Settings -->
    <div class="section" :class="{ 'unsaved-changes': imageQualityChanged }">
      <h3>Image Quality</h3>
      <p class="section-description">
        Configure output format and compression settings. <strong>This only affects the live Preview and "Save to Disk"</strong> — it does not control the quality of a fresh "Send to Plex".
      </p>
      <p class="section-description">
        Sending to Plex always uses the best quality that fits (PNG when it's under Plex's upload size limit, otherwise a high-quality JPEG), regardless of what's configured here. The one exception: <em>resending</em> an already-saved file (e.g. bulk resend from Local Assets) reuses that file's original bytes as-is — so if you saved it at a lower quality here, a later resend of that same file will still be that lower quality.
      </p>

      <label>
        <span class="label-text">Output Format</span>
        <select v-model="localOutputFormat">
          <option value="jpg">JPEG</option>
          <option value="png">PNG</option>
          <option value="webp">WebP</option>
        </select>
      </label>

      <div v-if="localOutputFormat === 'jpg'" class="quality-control">
        <label>
          <span class="label-text">JPEG Quality: {{ localJpgQuality }}%</span>
          <input
            type="range"
            v-model.number="localJpgQuality"
            min="1"
            max="100"
            step="1"
          />
          <span class="help-text">Higher = better quality, larger file size</span>
        </label>
      </div>

      <div v-if="localOutputFormat === 'png'" class="quality-control">
        <label>
          <span class="label-text">PNG Compression: {{ localPngCompression }}</span>
          <input
            type="range"
            v-model.number="localPngCompression"
            min="0"
            max="9"
            step="1"
          />
          <span class="help-text">0 = no compression (fast), 9 = max compression (slow)</span>
        </label>
      </div>

      <div v-if="localOutputFormat === 'webp'" class="quality-control">
        <label>
          <span class="label-text">WebP Quality: {{ localWebpQuality }}</span>
          <input
            type="range"
            v-model.number="localWebpQuality"
            min="1"
            max="100"
            step="1"
          />
          <span class="help-text">Higher = better quality, larger file size</span>
        </label>
      </div>
    </div>

    <div class="section">
      <h3>Local Asset Save Paths</h3>
      <p class="section-description">
        Configure where generated posters are saved when using the "Save to Disk" feature.
        Pick a layout below, or choose Custom to hand-edit the templates.
      </p>

      <div class="preset-row">
        <button
          v-for="preset in PRESETS"
          :key="preset.key"
          type="button"
          class="preset-btn"
          :class="{ active: !isCustomActive && activePresetKey === preset.key }"
          @click="applyPreset(preset)"
        >
          {{ preset.label }}
        </button>
        <button
          type="button"
          class="preset-btn"
          :class="{ active: isCustomActive }"
          @click="unlockCustom"
        >
          Custom
        </button>
      </div>
      <p class="help-text preset-description">
        {{ isCustomActive
          ? 'Hand-edit the templates below.'
          : PRESETS.find(p => p.key === activePresetKey)?.description }}
      </p>

      <label>
        <span class="label-text">Movie Save Location</span>
        <input
          v-model="localMovieSaveLocation"
          type="text"
          placeholder="/config/output/{library}/{title}.jpg"
          :readonly="!isCustomActive"
        />
        <span class="help-text">
          Available variables: <code>{library}</code>, <code>{title}</code>, <code>{folder}</code>, <code>{year}</code>, <code>{key}</code>, <code>{filename}</code>
        </span>
        <span class="help-text extra-note">
          <code>{folder}</code> resolves to the real on-disk folder name Plex knows for this movie
          (independent of Plex's display-language title) — falls back to <code>{title}</code> if it
          can't be resolved.
        </span>
      </label>

      <label>
        <span class="label-text">TV Show Save Location</span>
        <input
          v-model="localTvShowSaveLocation"
          type="text"
          placeholder="/config/output/{library}/{title} ({year}).jpg"
          :readonly="!isCustomActive"
        />
        <span class="help-text">
          Available variables: <code>{library}</code>, <code>{title}</code>, <code>{year}</code>, <code>{season}</code>, <code>{filename}</code>
        </span>
        <span class="help-text extra-note">
          <code>{filename}</code> resolves to <code>poster</code> (movie or show poster) or <code>SeasonNN</code> (a season
          poster) — Kometa's exact asset-naming convention. Templates without <code>{filename}</code> fall back to the
          "TV Show File Structure" setting below instead.
        </span>
      </label>

      <label v-if="showTvStructureMode">
        <span class="label-text">TV Show File Structure</span>
        <select v-model="localTvShowSaveMode">
          <option value="flat">Flat - All in one folder (e.g., "Show - series (Year).jpg", "Show - s01 (Year).jpg")</option>
          <option value="nested">Nested - Each show in its own folder (e.g., "Show (Year)/series.jpg", "Show (Year)/s01.jpg")</option>
        </select>
        <span class="help-text">
          Only used when the TV Show Save Location above doesn't include <code>{filename}</code>.
        </span>
      </label>

      <label class="checkbox-label">
        <input type="checkbox" v-model="localSaveBatchInSubfolder" />
        <span>Save batch operations in timestamped subfolder</span>
      </label>
      <span class="help-text checkbox-help">
        When enabled, every item in the same batch run is saved under one shared folder like "batch-2025-01-08-143022".
      </span>
    </div>

    <div class="section">
      <h3>Send to Plex</h3>
      <label class="checkbox-label">
        <input type="checkbox" v-model="localSaveToAssetFolderOnSend" />
        <span>Also save to the local asset folder when sending to Plex</span>
      </label>
      <span class="help-text checkbox-help">
        When enabled, sending a poster to Plex also writes it to your configured save location above (using the
        same template) — so other tools like Kometa can reuse the file, and so you can resend it later straight
        from that file. When disabled (default), sent posters are kept in an internal cache instead, invisible to
        other tools but still resendable from the library grid.
      </span>
    </div>

    <div class="section info-section">
      <h3>Path Variable Examples</h3>
      <div class="examples">
        <div class="example-item">
          <div class="example-label">Default — movie:</div>
          <code>/config/output/{library}/{title}.jpg</code>
          <div class="example-result">→ /config/output/4K Movies/The Matrix.jpg</div>
        </div>

        <div class="example-item">
          <div class="example-label">Default — TV show (flat structure):</div>
          <code>/config/output/{library}/{title} ({year}).jpg</code>
          <div class="example-result">→ /config/output/TV Shows/Breaking Bad - series (2008).jpg</div>
          <div class="example-result">→ /config/output/TV Shows/Breaking Bad - s01 (2008).jpg</div>
        </div>

        <div class="example-item">
          <div class="example-label">Flat (Kometa) — movie:</div>
          <code>/config/output/{library}/{title} ({year}).jpg</code>
          <div class="example-result">→ /config/output/Movies/Inception (2010).jpg</div>
        </div>

        <div class="example-item">
          <div class="example-label">Asset folders (Kometa) — movie and TV:</div>
          <code>/config/output/{library}/{title} ({year})/{filename}.jpg</code>
          <div class="example-result">→ /config/output/Movies/Inception (2010)/poster.jpg</div>
          <div class="example-result">→ /config/output/TV Shows/Breaking Bad (2008)/poster.jpg</div>
          <div class="example-result">→ /config/output/TV Shows/Breaking Bad (2008)/Season01.jpg</div>
        </div>

        <div class="example-item">
          <div class="example-label">Organized by year folder (Custom):</div>
          <code>/config/output/{library}/{year}/{title}.jpg</code>
          <div class="example-result">→ /config/output/Movies/2024/Dune Part Two.jpg</div>
        </div>

        <div class="example-item">
          <div class="example-label">Using the real on-disk folder name (Custom):</div>
          <code>/config/output/{library}/{folder}/poster.jpg</code>
          <div class="example-result">→ /config/output/Films/Before Sunrise (1995)/poster.jpg</div>
        </div>
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

.info-section {
  background: rgba(100, 200, 255, 0.03);
  border-color: rgba(100, 200, 255, 0.2);
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

.extra-note {
  margin-top: 4px;
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

.quality-control {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.examples {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.example-item {
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
}

.example-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.example-item code {
  display: block;
  background: rgba(255, 255, 255, 0.08);
  padding: 8px 12px;
  border-radius: 6px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: var(--accent);
  margin: 6px 0;
}

.example-result {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
  margin-top: 6px;
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

.preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.preset-btn {
  padding: 8px 16px;
  font-size: 13px;
}

.preset-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.preset-description {
  margin-top: 0;
  margin-bottom: 20px;
}

input[type="text"][readonly] {
  opacity: 0.7;
  cursor: not-allowed;
}
</style>
