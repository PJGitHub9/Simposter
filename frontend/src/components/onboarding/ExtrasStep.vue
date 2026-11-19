<script setup lang="ts">
// Setup wizard step: Maintainerr and the rating/list services, all optional.
// Fields start from the saved settings (keys come back masked); apply() writes
// back only what was changed here, so a masked key is never re-sent as a new value.
import { reactive, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { getApiBase } from '@/services/apiBase'

type Result = { ok: boolean; message: string }
type SectionId = 'maintainerr' | 'mdblist' | 'wetrakr' | 'simkl' | 'floppy'

const settings = useSettingsStore()
const apiBase = getApiBase()

const initial = {
  maintainerrUrl: settings.maintainerr.value.url || '',
  maintainerrKey: settings.maintainerr.value.apiKey || '',
  mdblistKey: settings.mdblist.value.apiKey || '',
  wetrakrId: settings.wetrakr.value.clientId || '',
  simklId: settings.simkl.value.clientId || '',
  floppyUrl: settings.floppy.value.url || '',
  floppyToken: settings.floppy.value.token || '',
}
const f = reactive({ ...initial })
const open = reactive<Record<SectionId, boolean>>({
  maintainerr: !!initial.maintainerrUrl,
  mdblist: !!initial.mdblistKey,
  wetrakr: !!initial.wetrakrId,
  simkl: !!initial.simklId,
  floppy: !!initial.floppyUrl,
})
const testing = reactive<Record<SectionId, boolean>>({ maintainerr: false, mdblist: false, wetrakr: false, simkl: false, floppy: false })
const results = ref<Partial<Record<SectionId, Result>>>({})

const post = async (path: string, body: unknown) => {
  const res = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return res.json()
}

const test = async (id: SectionId) => {
  testing[id] = true
  let r: Result
  try {
    if (id === 'maintainerr') {
      const d = await post('/api/maintainerr/test', { url: f.maintainerrUrl.trim(), apiKey: f.maintainerrKey })
      r = { ok: !!d.ok, message: d.message || (d.ok ? 'Connected' : 'No answer') }
    } else if (id === 'mdblist') {
      const d = await post('/api/test-mdblist', { api_key: f.mdblistKey })
      r = d.status === 'ok' ? { ok: true, message: d.message || 'Valid' } : { ok: false, message: d.error || 'Invalid key' }
    } else {
      const body = id === 'floppy'
        ? { url: f.floppyUrl.trim(), token: f.floppyToken }
        : { client_id: id === 'wetrakr' ? f.wetrakrId.trim() : f.simklId.trim() }
      const d = await post(`/api/list-sources/${id}/test`, body)
      r = d.status === 'ok' ? { ok: true, message: d.message || 'Valid' } : { ok: false, message: d.error || 'Invalid' }
    }
  } catch {
    r = { ok: false, message: 'Could not reach Simposter' }
  }
  results.value = { ...results.value, [id]: r }
  testing[id] = false
}

/** Copy the fields changed on this step into the settings store. */
const apply = () => {
  if (f.maintainerrUrl !== initial.maintainerrUrl || f.maintainerrKey !== initial.maintainerrKey) {
    settings.maintainerr.value = { ...settings.maintainerr.value, url: f.maintainerrUrl.trim(), apiKey: f.maintainerrKey }
  }
  if (f.mdblistKey !== initial.mdblistKey) {
    settings.mdblist.value = { ...settings.mdblist.value, apiKey: f.mdblistKey.trim() }
  }
  if (f.wetrakrId !== initial.wetrakrId) settings.wetrakr.value = { ...settings.wetrakr.value, clientId: f.wetrakrId.trim() }
  if (f.simklId !== initial.simklId) settings.simkl.value = { ...settings.simkl.value, clientId: f.simklId.trim() }
  if (f.floppyUrl !== initial.floppyUrl || f.floppyToken !== initial.floppyToken) {
    settings.floppy.value = { ...settings.floppy.value, url: f.floppyUrl.trim(), token: f.floppyToken }
  }
}

const changed = () => (Object.keys(initial) as (keyof typeof initial)[]).some(k => f[k] !== initial[k])

defineExpose({ apply, changed })
</script>

<template>
  <div class="ob-form">
    <!-- Maintainerr -->
    <div class="ob-server-form">
      <div class="ob-server-heading" @click="open.maintainerr = !open.maintainerr">
        <span>{{ open.maintainerr ? '▾' : '▸' }}</span> Maintainerr <span class="ob-optional">optional</span>
      </div>
      <p class="ob-hint-text" style="margin: 0;">Shows "leaving soon" dates on posters of titles Maintainerr will remove.</p>
      <template v-if="open.maintainerr">
        <input v-model="f.maintainerrUrl" class="ob-input" placeholder="http://maintainerr:6246" />
        <div class="ob-key-input-row">
          <input v-model="f.maintainerrKey" class="ob-input" type="password" placeholder="API key (optional)" />
          <button class="ob-btn-test" :disabled="testing.maintainerr || !f.maintainerrUrl.trim()" @click="test('maintainerr')">
            <span v-if="testing.maintainerr" class="ob-spinner" /> Test
          </button>
        </div>
      </template>
      <div v-if="results.maintainerr" class="ob-key-status" :class="results.maintainerr.ok ? 'ok' : 'error'">
        {{ results.maintainerr.ok ? '✓' : '✗' }} {{ results.maintainerr.message }}
      </div>
    </div>

    <!-- MDBList -->
    <div class="ob-server-form">
      <div class="ob-server-heading" @click="open.mdblist = !open.mdblist">
        <span>{{ open.mdblist ? '▾' : '▸' }}</span> MDBList <span class="ob-optional">optional</span>
      </div>
      <p class="ob-hint-text" style="margin: 0;">Ratings (IMDb, Rotten Tomatoes, ...) and lists for overlays.</p>
      <template v-if="open.mdblist">
        <div class="ob-key-header">
          <span />
          <a class="ob-key-link" href="https://mdblist.com/preferences/" target="_blank" rel="noopener">Get key →</a>
        </div>
        <div class="ob-key-input-row">
          <input v-model="f.mdblistKey" class="ob-input" type="password" placeholder="API key" />
          <button class="ob-btn-test" :disabled="testing.mdblist || !f.mdblistKey" @click="test('mdblist')">
            <span v-if="testing.mdblist" class="ob-spinner" /> Test
          </button>
        </div>
      </template>
      <div v-if="results.mdblist" class="ob-key-status" :class="results.mdblist.ok ? 'ok' : 'error'">
        {{ results.mdblist.ok ? '✓' : '✗' }} {{ results.mdblist.message }}
      </div>
    </div>

    <!-- WeTrakr -->
    <div class="ob-server-form">
      <div class="ob-server-heading" @click="open.wetrakr = !open.wetrakr">
        <span>{{ open.wetrakr ? '▾' : '▸' }}</span> WeTrakr <span class="ob-optional">optional</span>
      </div>
      <p class="ob-hint-text" style="margin: 0;">Lists for "On a list" overlay rules.</p>
      <template v-if="open.wetrakr">
        <div class="ob-key-input-row">
          <input v-model="f.wetrakrId" class="ob-input" type="password" placeholder="Client ID (not the client secret)" />
          <button class="ob-btn-test" :disabled="testing.wetrakr || !f.wetrakrId" @click="test('wetrakr')">
            <span v-if="testing.wetrakr" class="ob-spinner" /> Test
          </button>
        </div>
      </template>
      <div v-if="results.wetrakr" class="ob-key-status" :class="results.wetrakr.ok ? 'ok' : 'error'">
        {{ results.wetrakr.ok ? '✓' : '✗' }} {{ results.wetrakr.message }}
      </div>
    </div>

    <!-- SIMKL -->
    <div class="ob-server-form">
      <div class="ob-server-heading" @click="open.simkl = !open.simkl">
        <span>{{ open.simkl ? '▾' : '▸' }}</span> SIMKL <span class="ob-optional">optional</span>
      </div>
      <p class="ob-hint-text" style="margin: 0;">Lists for "On a list" overlay rules.</p>
      <template v-if="open.simkl">
        <div class="ob-key-input-row">
          <input v-model="f.simklId" class="ob-input" type="password" placeholder="Client ID" />
          <button class="ob-btn-test" :disabled="testing.simkl || !f.simklId" @click="test('simkl')">
            <span v-if="testing.simkl" class="ob-spinner" /> Test
          </button>
        </div>
      </template>
      <div v-if="results.simkl" class="ob-key-status" :class="results.simkl.ok ? 'ok' : 'error'">
        {{ results.simkl.ok ? '✓' : '✗' }} {{ results.simkl.message }}
      </div>
    </div>

    <!-- Floppy -->
    <div class="ob-server-form">
      <div class="ob-server-heading" @click="open.floppy = !open.floppy">
        <span>{{ open.floppy ? '▾' : '▸' }}</span> Floppy <span class="ob-optional">optional</span>
      </div>
      <p class="ob-hint-text" style="margin: 0;">Your self-hosted Floppy lists for "On a list" overlay rules.</p>
      <template v-if="open.floppy">
        <input v-model="f.floppyUrl" class="ob-input" placeholder="http://floppy:8000" />
        <div class="ob-key-input-row">
          <input v-model="f.floppyToken" class="ob-input" type="password" placeholder="App token (lists:read)" />
          <button class="ob-btn-test" :disabled="testing.floppy || !f.floppyUrl.trim() || !f.floppyToken" @click="test('floppy')">
            <span v-if="testing.floppy" class="ob-spinner" /> Test
          </button>
        </div>
      </template>
      <div v-if="results.floppy" class="ob-key-status" :class="results.floppy.ok ? 'ok' : 'error'">
        {{ results.floppy.ok ? '✓' : '✗' }} {{ results.floppy.message }}
      </div>
    </div>

    <p class="ob-hint-text">
      Sign in to your WeTrakr and SIMKL accounts later in Settings → Ratings &amp; Lists.
    </p>
  </div>
</template>

<style scoped src="./onboardingForm.css"></style>
