<script setup lang="ts">
// Setup wizard step: pick the default preset and (optionally) starter overlays.
// The wizard applies the choice at Finish: auto-generate with this preset on
// every library group, and the installed overlays added to the preset for
// movies and series (never seasons).
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { getApiBase } from '@/services/apiBase'

interface PresetRow { id: string; name?: string }
interface Starter {
  id: string
  name: string
  description: string
  credit?: { author?: string; url?: string }
  installed: boolean
  needs_version?: string | null
  preview_url?: string | null
}
type InstallState = 'idle' | 'installing' | 'ok' | 'error'

const props = defineProps<{ presetsReady: boolean }>()
const presetId = defineModel<string>('presetId', { required: true })
const overlayIds = defineModel<string[]>('overlayIds', { required: true })

const apiBase = getApiBase()
const presets = ref<PresetRow[]>([])
const presetsError = ref('')
const starters = ref<Starter[]>([])
const startersLoading = ref(true)
const startersError = ref('')
const installState = ref<Record<string, InstallState>>({})
// The preset shown as selected once the list first loaded; Finish only changes
// libraries on a re-run when the user picked something else.
let firstPick: string | null = null
const installError = ref<Record<string, string>>({})
// Fixed preview pictures from simposter-assets (preset id -> image link).
const presetPreviews = ref<Record<string, string>>({})
const brokenPreviews = ref<Set<string>>(new Set())
const lightbox = ref<string | null>(null)

const loadPresetPreviews = async () => {
  try {
    const res = await fetch(`${apiBase}/api/presets/default-template`)
    if (!res.ok) return
    const list = (await res.json())?.uniformlogo?.presets || []
    const map: Record<string, string> = {}
    for (const p of list) if (p?.id && p?.preview_url) map[p.id] = p.preview_url
    presetPreviews.value = map
  } catch { /* previews are optional */ }
}
const previewFor = (key: string, url?: string | null) => (url && !brokenPreviews.value.has(key) ? url : null)
const markBroken = (key: string) => { brokenPreviews.value = new Set(brokenPreviews.value).add(key) }
const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') lightbox.value = null }

const loadPresets = async () => {
  presetsError.value = ''
  try {
    const res = await fetch(`${apiBase}/api/presets`)
    if (!res.ok) throw new Error(String(res.status))
    presets.value = (await res.json())?.uniformlogo?.presets || []
    // Set through a local value: defineModel only shows the new value after the parent updates.
    let pick = presetId.value
    if (!presets.value.some(p => p.id === pick)) {
      const starter = presets.value.find(p => p.id === 'simposter-main')
      pick = (starter || presets.value[0])?.id || ''
      presetId.value = pick
    }
    if (firstPick === null) firstPick = pick
  } catch {
    presetsError.value = "Couldn't load the presets. You can pick one later in Settings → Libraries."
  }
}

const loadStarters = async () => {
  startersLoading.value = true
  startersError.value = ''
  try {
    const res = await fetch(`${apiBase}/api/overlay-starters`)
    if (!res.ok) throw new Error(String(res.status))
    starters.value = (await res.json())?.starters || []
  } catch {
    startersError.value = "Couldn't load the starter overlays. You can add them later in Overlays."
  } finally {
    startersLoading.value = false
  }
}

const isTicked = (s: Starter) => s.installed || overlayIds.value.includes(s.id)
const toggleStarter = (s: Starter) => {
  if (s.installed || s.needs_version) return
  overlayIds.value = overlayIds.value.includes(s.id)
    ? overlayIds.value.filter(i => i !== s.id)
    : [...overlayIds.value, s.id]
}

/** Install each ticked starter that isn't installed yet. Never throws.
 *  Returns the config ids of the ticked starters that are now installed. */
const installTicked = async (): Promise<string[]> => {
  const done: string[] = []
  for (const id of overlayIds.value) {
    const s = starters.value.find(x => x.id === id)
    if (!s) continue
    if (s.installed) { done.push(id); continue }
    installState.value = { ...installState.value, [id]: 'installing' }
    try {
      const res = await fetch(`${apiBase}/api/overlay-starters/${encodeURIComponent(id)}/install`, { method: 'POST' })
      if (!res.ok) {
        let msg = `Failed (${res.status})`
        try { const j = await res.json(); if (j?.detail) msg = String(j.detail) } catch { /* ignore */ }
        throw new Error(msg)
      }
      const data = await res.json()
      s.installed = true
      done.push(String(data?.config_id || id))
      installState.value = { ...installState.value, [id]: 'ok' }
    } catch (e) {
      installState.value = { ...installState.value, [id]: 'error' }
      installError.value = { ...installError.value, [id]: e instanceof Error ? e.message : 'Failed' }
    }
  }
  return done
}

/** True when the user picked a different preset than the one first shown. */
const presetChanged = () => firstPick !== null && presetId.value !== firstPick

defineExpose({ installTicked, presetChanged })

watch(() => props.presetsReady, (ready) => { if (ready) loadPresets() })
onMounted(() => {
  if (props.presetsReady) loadPresets()
  loadStarters()
  loadPresetPreviews()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="ob-form">
    <div class="ob-lib-section">
      <div class="ob-lib-heading">Default preset</div>
      <div v-if="!presetsReady" class="ob-hint-text"><span class="ob-spinner" /> Importing the starter presets…</div>
      <div v-else-if="presetsError" class="ob-error">{{ presetsError }}</div>
      <label
        v-for="p in presets"
        v-else
        :key="p.id"
        class="ob-lib-row"
        :class="{ selected: presetId === p.id }"
        @click.prevent="presetId = p.id"
      >
        <span class="ob-checkbox radio" :class="{ checked: presetId === p.id }" />
        <img
          v-if="previewFor('p:' + p.id, presetPreviews[p.id])"
          class="ob-thumb"
          :src="presetPreviews[p.id]"
          alt=""
          loading="lazy"
          referrerpolicy="no-referrer"
          title="Click to enlarge"
          @click.stop.prevent="lightbox = presetPreviews[p.id] || null"
          @error="markBroken('p:' + p.id)"
        />
        <span class="ob-row-title">{{ p.name || p.id }}</span>
      </label>
      <p class="ob-hint-text">
        New movies and shows get a poster with this preset. Your existing posters are left alone.
      </p>
    </div>

    <div class="ob-lib-section">
      <div class="ob-lib-heading">Overlays <span class="ob-optional">optional</span></div>
      <div v-if="startersLoading" class="ob-hint-text"><span class="ob-spinner" /> Loading starter overlays…</div>
      <div v-else-if="startersError" class="ob-error">{{ startersError }}</div>
      <template v-else>
        <label
          v-for="s in starters"
          :key="s.id"
          class="ob-lib-row"
          :class="{ selected: isTicked(s), disabled: s.installed || !!s.needs_version }"
          @click.prevent="toggleStarter(s)"
        >
          <span class="ob-checkbox" :class="{ checked: isTicked(s) }">
            <svg v-if="isTicked(s)" width="12" height="12" viewBox="0 0 12 12" fill="none"><polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg>
          </span>
          <img
            v-if="previewFor('s:' + s.id, s.preview_url)"
            class="ob-thumb"
            :src="s.preview_url || ''"
            alt=""
            loading="lazy"
            referrerpolicy="no-referrer"
            title="Click to enlarge"
            @click.stop.prevent="lightbox = s.preview_url || null"
            @error="markBroken('s:' + s.id)"
          />
          <span class="ob-row-body">
            <span class="ob-row-title">{{ s.name }}</span>
            <span v-if="s.description" class="ob-row-desc" style="display: block;">{{ s.description }}</span>
            <span v-if="s.credit?.author" class="ob-row-desc" style="display: block;">By {{ s.credit.author }}</span>
          </span>
          <span v-if="installState[s.id] === 'installing'" class="ob-row-status"><span class="ob-spinner" /></span>
          <span v-else-if="installState[s.id] === 'error'" class="ob-row-status error" :title="installError[s.id]">Failed</span>
          <span v-else-if="s.installed" class="ob-row-status ok">Installed</span>
          <span v-else-if="s.needs_version" class="ob-row-status">Needs {{ s.needs_version }}</span>
        </label>
        <p v-if="!starters.length" class="ob-hint-text">No starter overlays available right now.</p>
        <p class="ob-hint-text">
          Ticked overlays are added to the default preset for movies and shows, not season posters.
          Images are downloaded from their creators' repos when added.
        </p>
      </template>
    </div>
    <Teleport to="body">
      <div v-if="lightbox" class="ob-lightbox" @click="lightbox = null">
        <img :src="lightbox" alt="Preview" referrerpolicy="no-referrer" />
      </div>
    </Teleport>
  </div>
</template>

<style scoped src="./onboardingForm.css"></style>
<style scoped>
.ob-thumb {
  width: 60px;
  height: 90px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
  cursor: zoom-in;
  background: rgba(255, 255, 255, 0.04);
}
.ob-lightbox {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
}
.ob-lightbox img {
  max-height: 80vh;
  max-width: 90vw;
  border-radius: 6px;
}
</style>
