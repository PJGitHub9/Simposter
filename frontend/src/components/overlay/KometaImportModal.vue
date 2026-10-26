<script setup lang="ts">
// Import Kometa overlay files (backend/api/kometa_import.py). Pick the YAML
// files plus the images/fonts they use (loose, a folder, or a zip), or paste
// YAML text, check the report, then import. Each overlay file becomes one
// overlay config. Pasted text is sent as a .yml file like a picked one.
import { computed, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

const emit = defineEmits<{ close: []; imported: [configIds: string[]] }>()

interface OverlayEntry {
  name: string
  status: 'ok' | 'warning' | 'hidden' | 'skipped'
  messages: string[]
  element_type?: string
  image?: string
  image_match?: string | null
}
interface FileResult {
  path: string
  kind: 'overlays' | 'templates' | 'other' | 'error' | 'excluded'
  error?: string
  messages: string[]
  config_name?: string
  config_id?: string
  replaces_existing?: boolean
  element_count?: number
  counts?: Record<string, number>
  overlays?: OverlayEntry[]
}
interface ImportResult {
  dry_run: boolean
  files: FileResult[]
  uploaded: { yaml: number; image: number; font: number }
  missing_images: Array<{ path: string; used_by: string[] }>
  assets_saved: number
  assets_reused: number
  fonts_saved: number
}

const apiBase = getApiBase()
const picked = ref<Array<{ file: File; path: string }>>([])
const libraryType = ref<'movie' | 'show' | 'both'>('movie')
const result = ref<ImportResult | null>(null)
const busy = ref(false)
const error = ref('')
const done = ref<ImportResult | null>(null)
const configNames = ref<Record<string, string>>({})
const excluded = ref<Set<string>>(new Set())
const expanded = ref<Set<string>>(new Set())
const statusFilter = ref<'all' | 'problems'>('problems')
const dragOver = ref(false)

const fileInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)

const ACCEPT = '.yml,.yaml,.zip,.png,.jpg,.jpeg,.webp,.ttf,.otf'
const KEEP = /\.(ya?ml|zip|png|jpe?g|webp|ttf|otf|ttc)$/i

const addFiles = (list: FileList | File[] | null) => {
  if (!list) return
  const next = [...picked.value]
  for (const f of Array.from(list)) {
    const path = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name
    if (!KEEP.test(path)) continue
    if (!next.some(p => p.path === path && p.file.size === f.size)) next.push({ file: f, path })
  }
  picked.value = next
  result.value = null
}

const onDrop = (e: DragEvent) => {
  dragOver.value = false
  addFiles(e.dataTransfer?.files || null)
}

// ---- Paste YAML ----
const showPaste = ref(false)
const pasteText = ref('')
const pasteName = ref('')
const pasteError = ref('')
const addPasted = () => {
  pasteError.value = ''
  const text = pasteText.value.trim()
  if (!text) return
  if (!/^(overlays|templates)\s*:/m.test(text)) {
    pasteError.value = "Paste a whole Kometa overlay file: it should have a line starting with 'overlays:'."
    return
  }
  const base = (pasteName.value.trim() || 'Pasted overlay').replace(/[\/:*?"<>|]+/g, ' ').trim() || 'Pasted overlay'
  const path = `${base}.yml`
  // Pasting again under the same name replaces the earlier paste.
  picked.value = picked.value.filter(p => p.path !== path)
  addFiles([new File([text + '\n'], path, { type: 'text/yaml' })])
  pasteText.value = ''
  pasteName.value = ''
  showPaste.value = false
}

const removePicked = (i: number) => {
  picked.value.splice(i, 1)
  result.value = null
}

const pickedSummary = computed(() => {
  const yml = picked.value.filter(p => /\.ya?ml$/i.test(p.path)).length
  const zip = picked.value.filter(p => /\.zip$/i.test(p.path)).length
  const other = picked.value.length - yml - zip
  return { yml, zip, other }
})

const send = async (dryRun: boolean): Promise<ImportResult | null> => {
  const form = new FormData()
  for (const p of picked.value) form.append('files', p.file, p.path)
  form.append('library_type', libraryType.value)
  form.append('dry_run', dryRun ? 'true' : 'false')
  form.append('names', JSON.stringify(configNames.value))
  if (result.value) {
    const selected = result.value.files
      .filter(f => f.kind === 'overlays' && !excluded.value.has(f.path))
      .map(f => f.path)
    form.append('selected', JSON.stringify(selected))
  }
  const res = await fetch(`${apiBase}/api/overlay-configs/kometa-import`, { method: 'POST', body: form })
  if (!res.ok) {
    let msg = `Import failed (${res.status})`
    try { msg = (await res.json()).detail || msg } catch { /* keep default */ }
    throw new Error(msg)
  }
  return (await res.json()) as ImportResult
}

const check = async () => {
  if (!picked.value.length) return
  busy.value = true
  error.value = ''
  try {
    const keepNames = { ...configNames.value }
    result.value = null
    const r = await send(true)
    result.value = r
    for (const f of r?.files || []) {
      if (f.kind === 'overlays' && f.config_name && !keepNames[f.path]) keepNames[f.path] = f.config_name
    }
    configNames.value = keepNames
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

const runImport = async () => {
  busy.value = true
  error.value = ''
  try {
    const r = await send(false)
    done.value = r
    const ids = (r?.files || []).filter(f => f.kind === 'overlays' && f.config_id && (f.element_count || 0) > 0).map(f => f.config_id as string)
    emit('imported', ids)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

const overlayFiles = computed(() => (result.value?.files || []).filter(f => f.kind === 'overlays'))
const otherFiles = computed(() => (result.value?.files || []).filter(f => f.kind !== 'overlays'))
const importCount = computed(() => overlayFiles.value.filter(f => !excluded.value.has(f.path)).length)

const toggleExcluded = (path: string) => {
  const s = new Set(excluded.value)
  if (s.has(path)) s.delete(path)
  else s.add(path)
  excluded.value = s
}
const toggleExpanded = (path: string) => {
  const s = new Set(expanded.value)
  if (s.has(path)) s.delete(path)
  else s.add(path)
  expanded.value = s
}

const shownOverlays = (f: FileResult) =>
  (f.overlays || []).filter(o => statusFilter.value === 'all' || o.status !== 'ok')

const STATUS_LABEL: Record<string, string> = {
  ok: 'Ready',
  warning: 'Check',
  hidden: 'Hidden',
  skipped: 'Skipped',
}
const KIND_LABEL: Record<string, string> = {
  templates: 'Template file (used by the others)',
  other: 'No overlays found',
  error: 'Could not read',
  excluded: 'Not imported',
}
</script>

<template>
  <Teleport to="body">
    <div class="ki-backdrop" @click.self="emit('close')">
      <div class="ki-modal">
        <div class="ki-head">
          <h3>Import Kometa overlays <span class="beta-badge" title="Beta: works, but may still have small issues. Please report anything odd.">Beta</span></h3>
          <button class="ki-x" title="Close" @click="emit('close')">✕</button>
        </div>

        <div v-if="done" class="ki-body">
          <div class="ki-done">
            <div class="ki-done-title">Imported</div>
            <p>
              {{ done.files.filter(f => f.kind === 'overlays' && (f.element_count || 0) > 0).length }} overlay(s) saved,
              {{ done.assets_saved }} image(s) added{{ done.assets_reused ? `, ${done.assets_reused} reused` : '' }}{{ done.fonts_saved ? `, ${done.fonts_saved} font(s) added` : '' }}.
            </p>
            <p class="hint">Turn an overlay on in a preset or in the editor (Extras → Overlays) to use it. Layers marked Hidden stay off until their rule can be checked; open the overlay to see or edit them.</p>
          </div>
          <div class="ki-foot">
            <button class="btn primary" @click="emit('close')">Done</button>
          </div>
        </div>

        <div v-else class="ki-body">
          <p class="hint">
            Add your Kometa overlay files (.yml) and the images and fonts they use. A zip or a whole folder works too;
            images are matched to the paths in the files. Each overlay file becomes one overlay.
          </p>

          <div
            class="ki-drop"
            :class="{ over: dragOver }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <span>Drop files here, or</span>
            <button class="btn" @click="fileInput?.click()">Add files</button>
            <button class="btn" @click="folderInput?.click()">Add folder</button>
            <button class="btn" :class="{ on: showPaste }" @click="showPaste = !showPaste">Paste YAML</button>
            <input ref="fileInput" type="file" multiple :accept="ACCEPT" hidden @change="addFiles(($event.target as HTMLInputElement).files); ($event.target as HTMLInputElement).value = ''" />
            <input ref="folderInput" type="file" webkitdirectory multiple hidden @change="addFiles(($event.target as HTMLInputElement).files); ($event.target as HTMLInputElement).value = ''" />
          </div>

          <div v-if="showPaste" class="ki-paste">
            <textarea
              v-model="pasteText"
              class="ki-paste-text"
              rows="10"
              spellcheck="false"
              placeholder="overlays:&#10;  my_overlay:&#10;    overlay:&#10;      name: text(4K)&#10;      ..."
            ></textarea>
            <div class="ki-paste-row">
              <input v-model="pasteName" type="text" class="ki-paste-name" placeholder="Overlay name (optional)" @keyup.enter="addPasted" />
              <button class="btn primary" :disabled="!pasteText.trim()" @click="addPasted">Add to import</button>
              <button class="link" @click="showPaste = false; pasteError = ''">Cancel</button>
            </div>
            <p v-if="pasteError" class="ki-error">{{ pasteError }}</p>
            <p class="hint">
              If the YAML points to local images or fonts (e.g. <code>file: overlays/4k.png</code>), add those files too with
              Add files or by dropping them above. Images it links to on the web are downloaded during the import.
            </p>
          </div>

          <div v-if="picked.length" class="ki-picked">
            <div class="ki-picked-sum">
              {{ pickedSummary.yml }} YAML · {{ pickedSummary.zip }} zip · {{ pickedSummary.other }} image/font
              <button class="link" @click="picked = []; result = null">Clear</button>
            </div>
            <div class="ki-chips">
              <span v-for="(p, i) in picked.slice(0, 40)" :key="p.path + i" class="chip" :title="p.path">
                {{ p.path.split('/').pop() }}
                <button title="Remove" @click="removePicked(i)">✕</button>
              </span>
              <span v-if="picked.length > 40" class="chip more">+{{ picked.length - 40 }} more</span>
            </div>
          </div>

          <div class="ki-row">
            <label class="ki-lib">
              <span>Library type</span>
              <select v-model="libraryType" @change="result = null">
                <option value="movie">Movies</option>
                <option value="show">TV Shows</option>
                <option value="both">Movies and TV Shows</option>
              </select>
            </label>
            <span class="hint">{{ libraryType === 'both'
              ? 'One overlay for both kinds of library, like a Kometa file both libraries use. Layers that only apply to one kind (or look different) get a movie/show rule.'
              : 'Overlays that Kometa only runs for the other type are skipped.' }}</span>
          </div>

          <div v-if="error" class="ki-error">{{ error }}</div>

          <template v-if="result">
            <div class="ki-report-head">
              <span>Report</span>
              <div class="seg">
                <button :class="{ active: statusFilter === 'problems' }" @click="statusFilter = 'problems'">Needs attention</button>
                <button :class="{ active: statusFilter === 'all' }" @click="statusFilter = 'all'">All</button>
              </div>
            </div>

            <div v-for="f in overlayFiles" :key="f.path" class="ki-file" :class="{ off: excluded.has(f.path) }">
              <div class="ki-file-head">
                <input type="checkbox" :checked="!excluded.has(f.path)" title="Import this file" @change="toggleExcluded(f.path)" />
                <div class="ki-file-main">
                  <div class="ki-file-path">{{ f.path }}</div>
                  <div class="ki-counts">
                    <span class="badge ok">{{ f.counts?.ok || 0 }} ready</span>
                    <span v-if="f.counts?.warning" class="badge warning">{{ f.counts.warning }} check</span>
                    <span v-if="f.counts?.hidden" class="badge hidden">{{ f.counts.hidden }} hidden</span>
                    <span v-if="f.counts?.skipped" class="badge skipped">{{ f.counts.skipped }} skipped</span>
                  </div>
                </div>
                <label class="ki-name">
                  <span>Config name</span>
                  <input v-model="configNames[f.path]" type="text" />
                  <small v-if="f.replaces_existing" class="replace">replaces the existing config</small>
                </label>
                <button class="link" @click="toggleExpanded(f.path)">{{ expanded.has(f.path) ? 'Hide' : 'Details' }}</button>
              </div>
              <ul v-if="f.messages.length" class="ki-msgs">
                <li v-for="m in f.messages" :key="m">{{ m }}</li>
              </ul>
              <div v-if="expanded.has(f.path)" class="ki-overlays">
                <div v-if="!shownOverlays(f).length" class="hint">Everything in this file is ready.</div>
                <div v-for="o in shownOverlays(f)" :key="o.name" class="ki-ov">
                  <span class="badge" :class="o.status">{{ STATUS_LABEL[o.status] }}</span>
                  <span class="ki-ov-name">{{ o.name }}</span>
                  <span v-if="o.element_type" class="ki-ov-type">{{ o.element_type }}</span>
                  <span v-if="o.image" class="ki-ov-img" :class="{ missing: !o.image_match }" :title="o.image">
                    {{ o.image_match ? '✓' : '✗' }} {{ o.image.split('/').pop() }}
                  </span>
                  <ul v-if="o.messages.length" class="ki-ov-msgs">
                    <li v-for="m in o.messages" :key="m">{{ m }}</li>
                  </ul>
                </div>
              </div>
            </div>

            <div v-if="otherFiles.length" class="ki-others">
              <div v-for="f in otherFiles" :key="f.path" class="ki-other">
                <span class="ki-file-path">{{ f.path }}</span>
                <span class="hint">{{ KIND_LABEL[f.kind] || f.kind }}{{ f.error ? `: ${f.error}` : '' }}</span>
              </div>
            </div>

            <div v-if="result.missing_images.length" class="ki-missing">
              <div class="ki-missing-title">{{ result.missing_images.length }} image(s) not uploaded</div>
              <p class="hint">Those elements are created anyway and stay empty until you add the images (here, then Check again, or later in the element).</p>
              <div class="ki-chips">
                <span v-for="m in result.missing_images.slice(0, 60)" :key="m.path" class="chip missing" :title="`${m.path}\nUsed by: ${m.used_by.join(', ')}`">
                  {{ m.path.split('/').pop() }}
                </span>
                <span v-if="result.missing_images.length > 60" class="chip more">+{{ result.missing_images.length - 60 }} more</span>
              </div>
            </div>
          </template>

          <div class="ki-foot">
            <button class="btn" @click="emit('close')">Cancel</button>
            <button class="btn" :disabled="busy || !picked.length" @click="check">{{ busy && !result ? 'Checking…' : result ? 'Check again' : 'Check' }}</button>
            <button class="btn primary" :disabled="busy || !result || importCount === 0" @click="runImport">
              {{ busy && result ? 'Importing…' : `Import ${importCount} config${importCount === 1 ? '' : 's'}` }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ki-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 16px; }
.ki-modal { width: min(860px, 100%); max-height: 90vh; display: flex; flex-direction: column; background: var(--surface, #141824); border: 1px solid var(--border, #2a2f3e); border-radius: 12px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5); }
.ki-head { display: flex; align-items: center; justify-content: space-between; padding: 0.9rem 1.1rem; border-bottom: 1px solid var(--border, #2a2f3e); }
.ki-head h3 { margin: 0; font-size: 1rem; color: var(--text-primary, #fff); }
.ki-x { background: none; border: none; color: var(--text-secondary, #888); cursor: pointer; font-size: 1rem; }
.ki-x:hover { color: var(--text-primary, #fff); }
.ki-body { padding: 1rem 1.1rem; overflow-y: auto; display: flex; flex-direction: column; gap: 0.75rem; }
.hint { margin: 0; color: var(--text-secondary, #888); font-size: 0.78rem; line-height: 1.4; }
.ki-drop { display: flex; align-items: center; justify-content: center; gap: 0.6rem; flex-wrap: wrap; padding: 1.1rem; border: 1px dashed var(--border, #2a2f3e); border-radius: 10px; color: var(--text-secondary, #888); font-size: 0.85rem; }
.ki-drop.over { border-color: var(--accent, #3dd6b7); background: rgba(61, 214, 183, 0.06); }
.btn { padding: 0.4rem 0.8rem; border-radius: 7px; border: 1px solid var(--border, #2a2f3e); background: rgba(255, 255, 255, 0.04); color: var(--text-primary, #fff); cursor: pointer; font-size: 0.82rem; }
.btn:hover:not(:disabled) { border-color: var(--accent, #3dd6b7); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn.primary { background: var(--accent, #3dd6b7); border-color: var(--accent, #3dd6b7); color: #04130f; font-weight: 600; }
.link { background: none; border: none; color: var(--accent, #3dd6b7); cursor: pointer; font-size: 0.78rem; padding: 0; }
.btn.on { border-color: var(--accent, #3dd6b7); color: var(--accent, #3dd6b7); }
.ki-paste { display: flex; flex-direction: column; gap: 0.45rem; }
.ki-paste-text { width: 100%; box-sizing: border-box; padding: 0.55rem 0.65rem; border-radius: 8px; border: 1px solid var(--border, #2a2f3e); background: rgba(0, 0, 0, 0.25); color: var(--text-primary, #fff); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.78rem; line-height: 1.45; resize: vertical; }
.ki-paste-text:focus, .ki-paste-name:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.ki-paste-row { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.ki-paste-name { flex: 1; min-width: 180px; padding: 0.4rem 0.55rem; border-radius: 7px; border: 1px solid var(--border, #2a2f3e); background: rgba(255, 255, 255, 0.04); color: var(--text-primary, #fff); font-size: 0.82rem; }
.ki-picked-sum { display: flex; align-items: center; gap: 0.6rem; font-size: 0.8rem; color: var(--text-secondary, #888); margin-bottom: 0.35rem; }
.ki-chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
.chip { display: inline-flex; align-items: center; gap: 0.25rem; padding: 0.15rem 0.45rem; border-radius: 999px; background: rgba(255, 255, 255, 0.06); color: var(--text-primary, #fff); font-size: 0.72rem; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip button { background: none; border: none; color: var(--text-secondary, #888); cursor: pointer; font-size: 0.65rem; padding: 0; }
.chip.more { color: var(--text-secondary, #888); }
.chip.missing { background: rgba(248, 113, 113, 0.12); color: #fca5a5; }
.ki-row { display: flex; align-items: center; gap: 0.8rem; flex-wrap: wrap; }
.ki-lib { display: flex; align-items: center; gap: 0.45rem; font-size: 0.8rem; color: var(--text-secondary, #888); }
.ki-lib select, .ki-name input { padding: 0.32rem 0.45rem; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e); border-radius: 6px; color: var(--text-primary, #fff); font-size: 0.8rem; }
.ki-error { padding: 0.55rem 0.7rem; border-radius: 7px; background: rgba(248, 113, 113, 0.12); color: #fca5a5; font-size: 0.82rem; }
.ki-report-head { display: flex; align-items: center; justify-content: space-between; color: var(--text-primary, #fff); font-weight: 600; font-size: 0.88rem; margin-top: 0.25rem; }
.seg { display: inline-flex; border: 1px solid var(--border, #2a2f3e); border-radius: 6px; overflow: hidden; }
.seg button { padding: 0.25rem 0.6rem; background: none; border: none; color: var(--text-secondary, #888); font-size: 0.74rem; cursor: pointer; }
.seg button + button { border-left: 1px solid var(--border, #2a2f3e); }
.seg button.active { background: rgba(61, 214, 183, 0.15); color: var(--accent, #3dd6b7); }
.ki-file { border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 9px; padding: 0.6rem 0.7rem; background: rgba(255, 255, 255, 0.02); }
.ki-file.off { opacity: 0.5; }
.ki-file-head { display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap; }
.ki-file-main { flex: 1; min-width: 180px; }
.ki-file-path { color: var(--text-primary, #fff); font-size: 0.85rem; font-weight: 600; word-break: break-all; }
.ki-counts { display: flex; gap: 0.3rem; flex-wrap: wrap; margin-top: 0.2rem; }
.ki-name { display: flex; flex-direction: column; gap: 0.15rem; font-size: 0.7rem; color: var(--text-secondary, #888); }
.ki-name .replace { color: #fbbf24; }
.badge { display: inline-block; padding: 0.08rem 0.4rem; border-radius: 5px; font-size: 0.68rem; font-weight: 600; letter-spacing: 0.3px; }
.badge.ok { background: rgba(61, 214, 183, 0.15); color: #3dd6b7; }
.badge.warning { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
.badge.hidden { background: rgba(148, 163, 184, 0.18); color: #cbd5e1; }
.badge.skipped { background: rgba(248, 113, 113, 0.15); color: #fca5a5; }
.ki-msgs, .ki-ov-msgs { margin: 0.35rem 0 0; padding-left: 1.1rem; color: var(--text-secondary, #888); font-size: 0.74rem; }
.ki-overlays { margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.35rem; max-height: 320px; overflow-y: auto; }
.ki-ov { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.4rem; padding: 0.3rem 0.4rem; border-radius: 6px; background: rgba(255, 255, 255, 0.02); }
.ki-ov-name { color: var(--text-primary, #fff); font-size: 0.8rem; }
.ki-ov-type { color: var(--text-secondary, #888); font-size: 0.72rem; }
.ki-ov-img { font-size: 0.72rem; color: #3dd6b7; }
.ki-ov-img.missing { color: #fca5a5; }
.ki-ov-msgs { flex-basis: 100%; margin-top: 0.1rem; }
.ki-others { display: flex; flex-direction: column; gap: 0.25rem; }
.ki-other { display: flex; gap: 0.6rem; align-items: baseline; flex-wrap: wrap; }
.ki-missing { border: 1px solid rgba(248, 113, 113, 0.25); border-radius: 9px; padding: 0.6rem 0.7rem; display: flex; flex-direction: column; gap: 0.4rem; }
.ki-missing-title { color: #fca5a5; font-size: 0.82rem; font-weight: 600; }
.ki-foot { display: flex; justify-content: flex-end; gap: 0.5rem; padding-top: 0.25rem; }
.ki-done { display: flex; flex-direction: column; gap: 0.4rem; color: var(--text-primary, #fff); font-size: 0.85rem; }
.ki-done-title { font-weight: 700; font-size: 0.95rem; color: var(--accent, #3dd6b7); }
.ki-done p { margin: 0; }

.beta-badge {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  vertical-align: middle;
  background: rgba(139, 92, 246, 0.18);
  color: #a78bfa;
}
</style>
