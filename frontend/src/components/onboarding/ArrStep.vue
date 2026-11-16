<script setup lang="ts">
// Setup wizard step: connect Radarr/Sonarr and create Simposter's webhook in
// them. A connection is saved as soon as it tests fine (like Settings →
// Media Servers), so the webhook button can use the stored key. Linking to
// library groups happens at Finish (the groups don't exist yet here).
import { computed, reactive, ref, watch } from 'vue'
import { useSettingsStore, type ArrInstance } from '@/stores/settings'
import { getApiBase } from '@/services/apiBase'
import { mediaServerId } from '@/services/mediaServerId'

type ArrType = 'radarr' | 'sonarr'
type Result = { ok: boolean; message: string }

const props = defineProps<{ presetId: string }>()

const settings = useSettingsStore()
const apiBase = getApiBase()
const TYPES: ArrType[] = ['radarr', 'sonarr']
const label = (t: ArrType) => (t === 'radarr' ? 'Radarr' : 'Sonarr')
const forType = (t: ArrType) => settings.arrInstances.value.filter(i => i.type === t)

const simposterUrl = ref(window.location.origin)
const drafts = reactive<Record<ArrType, { name: string; url: string; apiKey: string; open: boolean; testing: boolean; result: Result | null }>>({
  radarr: { name: '', url: '', apiKey: '', open: false, testing: false, result: null },
  sonarr: { name: '', url: '', apiKey: '', open: false, testing: false, result: null },
})
const testResults = reactive<Record<string, Result>>({})
const testing = reactive<Record<string, boolean>>({})
const hookBusy = reactive<Record<string, boolean>>({})
// The webhook endpoint reads the saved instance, so its button waits for the save.
const saving = reactive<Record<string, boolean>>({})
const hookResults = reactive<Record<string, Result>>({})
// With several of one type: which one every movie (Radarr) / TV (Sonarr) library uses.
const chosen = reactive<Record<ArrType, string>>({ radarr: '', sonarr: '' })
// Show the instance a library group already uses, else the first one.
const fillChosen = () => {
  for (const t of TYPES) {
    const list = forType(t)
    if (list.some(i => i.id === chosen[t])) continue
    const media = t === 'radarr' ? 'movie' : 'tv'
    const linked = settings.libraryGroups.value.find(g => g.mediaType === media && list.some(i => i.id === g.arrInstanceId))
    chosen[t] = linked?.arrInstanceId || list[0]?.id || ''
  }
}
fillChosen()
watch(() => settings.arrInstances.value.length, fillChosen)
// Set when an instance is added or the "use for all" choice is changed here;
// a wizard re-run only links library groups then.
const touched = ref(false)

const runTest = async (type: ArrType, url: string, apiKey: string, instanceId?: string): Promise<Result> => {
  try {
    const res = await fetch(`${apiBase}/api/arr/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, url, apiKey, instance_id: instanceId }),
    })
    const data = await res.json()
    if (res.ok && data.ok) return { ok: true, message: `Connected to ${data.app} ${data.version}`.trim() }
    return { ok: false, message: data.error || data.detail || 'Could not connect' }
  } catch {
    return { ok: false, message: 'Could not connect' }
  }
}

const testExisting = async (inst: ArrInstance) => {
  testing[inst.id] = true
  testResults[inst.id] = await runTest(inst.type as ArrType, inst.url, inst.apiKey || '', inst.id)
  testing[inst.id] = false
}

const testAndAdd = async (type: ArrType) => {
  const d = drafts[type]
  const url = d.url.trim()
  if (!url || !d.apiKey) return
  d.testing = true
  d.result = await runTest(type, url, d.apiKey)
  d.testing = false
  if (!d.result.ok) return
  const id = mediaServerId(type, url)
  const entry: ArrInstance = { id, type, name: d.name.trim(), url, apiKey: d.apiKey, enabled: true }
  settings.arrInstances.value = [...settings.arrInstances.value.filter(i => i.id !== id), entry]
  saving[id] = true
  try { await settings.save() } catch { /* the page-wide save at Finish sends it too */ }
  saving[id] = false
  testResults[id] = d.result
  touched.value = true
  Object.assign(d, { name: '', url: '', apiKey: '', open: false, result: null })
}

const setUpWebhook = async (inst: ArrInstance) => {
  hookBusy[inst.id] = true
  try {
    const res = await fetch(`${apiBase}/api/arr/${encodeURIComponent(inst.id)}/webhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ simposter_url: simposterUrl.value.trim(), template_id: 'uniformlogo', preset_id: props.presetId }),
    })
    const data = await res.json()
    if (!res.ok) hookResults[inst.id] = { ok: false, message: data.detail || `Failed (${res.status})` }
    else if (data.status === 'created') hookResults[inst.id] = { ok: true, message: 'Webhook created' }
    else if (data.status === 'exists') hookResults[inst.id] = { ok: true, message: `Already set up (${data.name || 'existing webhook'}), left as is` }
    else hookResults[inst.id] = { ok: false, message: data.error || 'Failed' }
  } catch {
    hookResults[inst.id] = { ok: false, message: 'Failed' }
  } finally {
    hookBusy[inst.id] = false
  }
}

const canHook = computed(() => !!props.presetId && /^https?:\/\//i.test(simposterUrl.value.trim()))

/** The instance every movie (radarr) / TV (sonarr) library group should be
 *  linked to at Finish, or null when there is none. */
const defaultLinks = (): Record<ArrType, string | null> => {
  const pick = (t: ArrType) => {
    const list = forType(t).filter(i => i.enabled !== false)
    if (!list.length) return null
    return list.some(i => i.id === chosen[t]) ? chosen[t] : list[0]!.id
  }
  return { radarr: pick('radarr'), sonarr: pick('sonarr') }
}

defineExpose({ defaultLinks, touched: () => touched.value })
</script>

<template>
  <div class="ob-form">
    <div class="ob-key-row">
      <label class="ob-label">Simposter address, as Radarr and Sonarr see it</label>
      <input v-model="simposterUrl" class="ob-input ob-input-mono" placeholder="http://simposter:8003" />
      <p class="ob-hint-text">
        Used for the webhook. In Docker, Radarr usually reaches Simposter by its container name,
        e.g. <code>http://simposter:8003</code>, not the address in your browser.
      </p>
    </div>

    <div v-for="t in TYPES" :key="t" class="ob-server-form">
      <div class="ob-server-heading">{{ label(t) }} <span class="ob-optional">optional</span></div>

      <div v-for="inst in forType(t)" :key="inst.id" class="ob-key-row">
        <div class="ob-lib-row selected" style="cursor: default;">
          <span class="ob-row-body">
            <span class="ob-row-title">{{ inst.name || label(t) }}</span>
            <span class="ob-row-desc" style="display: block;">{{ inst.url }}</span>
          </span>
          <button class="ob-small-btn" :disabled="testing[inst.id]" @click="testExisting(inst)">
            <span v-if="testing[inst.id]" class="ob-spinner" /> Test
          </button>
          <button class="ob-small-btn" :disabled="!canHook || hookBusy[inst.id] || saving[inst.id]" @click="setUpWebhook(inst)">
            <span v-if="hookBusy[inst.id] || saving[inst.id]" class="ob-spinner" /> Set up webhook
          </button>
        </div>
        <div v-if="testResults[inst.id]" class="ob-key-status" :class="testResults[inst.id]!.ok ? 'ok' : 'error'">
          {{ testResults[inst.id]!.ok ? '✓' : '✗' }} {{ testResults[inst.id]!.message }}
        </div>
        <div v-if="hookResults[inst.id]" class="ob-key-status" :class="hookResults[inst.id]!.ok ? 'ok' : 'error'">
          {{ hookResults[inst.id]!.ok ? '✓' : '✗' }} {{ hookResults[inst.id]!.message }}
        </div>
      </div>

      <div v-if="forType(t).length > 1" class="ob-key-row">
        <label class="ob-label">Use for all {{ t === 'radarr' ? 'movie' : 'TV' }} libraries</label>
        <select v-model="chosen[t]" class="ob-input" @change="touched = true">
          <option v-for="inst in forType(t)" :key="inst.id" :value="inst.id">{{ inst.name || inst.url }}</option>
        </select>
        <p class="ob-hint-text">You can pick a different one per library group on the next step.</p>
      </div>

      <template v-if="drafts[t].open">
        <input v-model="drafts[t].name" class="ob-input" placeholder="Name (optional)" />
        <input v-model="drafts[t].url" class="ob-input ob-input-mono" :placeholder="t === 'radarr' ? 'http://radarr:7878' : 'http://sonarr:8989'" />
        <div class="ob-key-input-row">
          <input v-model="drafts[t].apiKey" class="ob-input" type="password" placeholder="API key (Settings → General)" />
          <button class="ob-btn-test" :disabled="drafts[t].testing || !drafts[t].url.trim() || !drafts[t].apiKey" @click="testAndAdd(t)">
            <span v-if="drafts[t].testing" class="ob-spinner" /> Test & add
          </button>
        </div>
        <div v-if="drafts[t].result && !drafts[t].result!.ok" class="ob-key-status error">✗ {{ drafts[t].result!.message }}</div>
      </template>
      <button v-else class="ob-small-btn" style="align-self: flex-start;" @click="drafts[t].open = true">+ Add {{ label(t) }}</button>
    </div>

    <p class="ob-hint-text">
      Simposter reads tags from Radarr and Sonarr (for poster mode rules), and the webhook tells
      Simposter when a movie or episode is imported so its poster is made right away.
    </p>
    <p v-if="!presetId" class="ob-hint-text">Pick a default preset on the previous step to set up webhooks.</p>
  </div>
</template>

<style scoped src="./onboardingForm.css"></style>
<style scoped>
.ob-input-mono { font-family: monospace; }
select.ob-input { appearance: auto; }
</style>
