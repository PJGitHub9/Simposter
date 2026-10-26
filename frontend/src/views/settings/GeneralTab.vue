<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { getApiBase } from '@/services/apiBase'

const props = defineProps<{
  theme: string
  posterDensity: number
  deduplicateMovies: boolean
  defaultSort: string
  timezone: string
  tmdbApiKey: string
  tvdbApiKey: string
  fanartApiKey: string
  unsavedChanges: boolean
  testingKeys?: Record<string, boolean>
  apiKeyTestResults?: Record<string, string>
}>()

const emit = defineEmits<{
  'update:theme': [value: string]
  'update:posterDensity': [value: number]
  'update:deduplicateMovies': [value: boolean]
  'update:defaultSort': [value: string]
  'update:timezone': [value: string]
  'update:tmdbApiKey': [value: string]
  'update:tvdbApiKey': [value: string]
  'update:fanartApiKey': [value: string]
  'test-api-key': [keyType: string, apiKey: string]
  'save': []
}>()

const localTheme = computed({
  get: () => props.theme,
  set: (val) => emit('update:theme', val)
})

const localPosterDensity = computed({
  get: () => props.posterDensity,
  set: (val) => emit('update:posterDensity', val)
})

const localDeduplicateMovies = computed({
  get: () => props.deduplicateMovies,
  set: (val) => emit('update:deduplicateMovies', val)
})

const localDefaultSort = computed({
  get: () => props.defaultSort,
  set: (val) => emit('update:defaultSort', val)
})

const localTimezone = computed({
  get: () => props.timezone,
  set: (val) => emit('update:timezone', val)
})

const localTmdbApiKey = computed({
  get: () => props.tmdbApiKey,
  set: (val) => emit('update:tmdbApiKey', val)
})

const localTvdbApiKey = computed({
  get: () => props.tvdbApiKey,
  set: (val) => emit('update:tvdbApiKey', val)
})

const settingsStore = useSettingsStore()
const ratingSources = [
  { value: 'imdb', label: 'IMDb' },
  { value: 'tomatoes', label: 'Rotten Tomatoes (critics)' },
  { value: 'tomatoesaudience', label: 'Rotten Tomatoes (audience)' },
  { value: 'tmdb', label: 'TMDb' },
  { value: 'trakt', label: 'Trakt' },
  { value: 'metacritic', label: 'Metacritic' },
  { value: 'metacriticuser', label: 'Metacritic (users)' },
  { value: 'letterboxd', label: 'Letterboxd' },
  { value: 'myanimelist', label: 'MyAnimeList' },
  { value: 'score', label: 'MDBList score' },
]
// Planned rating/list sources, shown greyed out (no settings yet).
const upcomingSources = [
  { name: 'AniList', note: 'Anime scores and lists.' },
  { name: 'MyAnimeList', note: 'Anime scores and lists.' },
  { name: 'WeTrakr, SIMKL, Floppy ratings', note: 'Their lists work now (above); ratings come later.' },
]

// ---- List sources (WeTrakr, SIMKL, Floppy): key tests and "approve this code" sign-ins.
// Sign-in tokens live server-side (list_source_auth table), never in this page.
type ListProvider = 'wetrakr' | 'simkl' | 'floppy'
type SourceStatus = { configured: boolean; connected: boolean; username?: string | null }
type ConnectState = { userCode: string; url: string; urlComplete?: string | null }
const sourceStatus = ref<Record<string, SourceStatus>>({})
const sourceTest = ref<Record<string, { ok: boolean; message: string } | null>>({})
const sourceTesting = ref<Record<string, boolean>>({})
const connectState = ref<Record<string, ConnectState | null>>({})
const connectError = ref<Record<string, string>>({})
const pollTimers: Record<string, number> = {}

async function loadSourceStatus() {
  try {
    const res = await fetch(`${getApiBase()}/api/list-sources/status`)
    if (res.ok) sourceStatus.value = await res.json()
  } catch { /* keep what we have */ }
}

async function testSource(provider: ListProvider) {
  sourceTesting.value = { ...sourceTesting.value, [provider]: true }
  sourceTest.value = { ...sourceTest.value, [provider]: null }
  const body = provider === 'floppy'
    ? { url: settingsStore.floppy.value.url, token: settingsStore.floppy.value.token }
    : { client_id: provider === 'wetrakr' ? settingsStore.wetrakr.value.clientId : settingsStore.simkl.value.clientId }
  let result: { ok: boolean; message: string }
  try {
    const res = await fetch(`${getApiBase()}/api/list-sources/${provider}/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    result = data.status === 'ok'
      ? { ok: true, message: '✓ ' + (data.message || 'Valid') }
      : { ok: false, message: 'Error: ' + (data.error || 'Invalid') }
  } catch {
    result = { ok: false, message: 'Error: could not reach the server' }
  }
  sourceTest.value = { ...sourceTest.value, [provider]: result }
  sourceTesting.value = { ...sourceTesting.value, [provider]: false }
}

function stopPolling(provider: string) {
  if (pollTimers[provider]) window.clearTimeout(pollTimers[provider])
  delete pollTimers[provider]
}

function setConnectError(provider: string, message: string) {
  connectError.value = { ...connectError.value, [provider]: message }
}

async function connectSource(provider: ListProvider) {
  setConnectError(provider, '')
  stopPolling(provider)
  let data: { user_code?: string; verification_url?: string; verification_url_complete?: string | null; interval?: number; detail?: string }
  try {
    const res = await fetch(`${getApiBase()}/api/list-sources/${provider}/connect`, { method: 'POST' })
    data = await res.json()
    if (!res.ok) {
      setConnectError(provider, data.detail || 'Could not start the sign-in')
      return
    }
  } catch {
    setConnectError(provider, 'Could not reach the server')
    return
  }
  connectState.value = {
    ...connectState.value,
    [provider]: { userCode: data.user_code || '', url: data.verification_url || '', urlComplete: data.verification_url_complete },
  }
  const interval = Math.max(Number(data.interval) || 5, 2) * 1000
  const poll = async () => {
    try {
      const r = await fetch(`${getApiBase()}/api/list-sources/${provider}/connect/poll`, { method: 'POST' })
      const d = await r.json()
      if (d.status === 'pending') {
        pollTimers[provider] = window.setTimeout(poll, interval)
        return
      }
      stopPolling(provider)
      connectState.value = { ...connectState.value, [provider]: null }
      if (d.status === 'connected') await loadSourceStatus()
      else setConnectError(provider, d.error || 'The sign-in did not finish')
    } catch {
      pollTimers[provider] = window.setTimeout(poll, interval)
    }
  }
  pollTimers[provider] = window.setTimeout(poll, interval)
}

function cancelConnect(provider: ListProvider) {
  stopPolling(provider)
  connectState.value = { ...connectState.value, [provider]: null }
}

async function disconnectSource(provider: ListProvider) {
  if (!window.confirm('Disconnect this account? Lists that need the sign-in stop updating until you connect again.')) return
  await fetch(`${getApiBase()}/api/list-sources/${provider}/connect`, { method: 'DELETE' }).catch(() => null)
  await loadSourceStatus()
}

onMounted(loadSourceStatus)
// A key can only be used for a sign-in once it's saved, so refresh the status after a save.
watch(() => props.unsavedChanges, (now, before) => { if (before && !now) loadSourceStatus() })
onBeforeUnmount(() => { Object.keys(pollTimers).forEach(stopPolling) })

const mdblistTesting = ref(false)
const mdblistResult = ref<{ ok: boolean; message: string } | null>(null)
async function testMdblist() {
  mdblistTesting.value = true
  mdblistResult.value = null
  try {
    const res = await fetch(`${getApiBase()}/api/test-mdblist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: settingsStore.mdblist.value.apiKey }),
    })
    const data = await res.json()
    mdblistResult.value = data.status === 'ok'
      ? { ok: true, message: `✓ ${data.message || 'Valid'}` }
      : { ok: false, message: `Error: ${data.error || 'Invalid key'}` }
  } catch {
    mdblistResult.value = { ok: false, message: 'Error: could not reach the server' }
  } finally {
    mdblistTesting.value = false
  }
}

const localFanartApiKey = computed({
  get: () => props.fanartApiKey,
  set: (val) => emit('update:fanartApiKey', val)
})

// Common timezones list
const TIMEZONE_LIST = [
  { value: 'UTC', label: 'UTC (Coordinated Universal Time)' },
  { value: 'America/New_York', label: 'Eastern Time (US & Canada)' },
  { value: 'America/Chicago', label: 'Central Time (US & Canada)' },
  { value: 'America/Denver', label: 'Mountain Time (US & Canada)' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (US & Canada)' },
  { value: 'America/Toronto', label: 'Toronto' },
  { value: 'America/Vancouver', label: 'Vancouver' },
  { value: 'America/Anchorage', label: 'Alaska' },
  { value: 'Pacific/Honolulu', label: 'Hawaii' },
  { value: 'America/Sao_Paulo', label: 'São Paulo' },
  { value: 'America/Argentina/Buenos_Aires', label: 'Buenos Aires' },
  { value: 'Europe/London', label: 'London' },
  { value: 'Europe/Paris', label: 'Paris' },
  { value: 'Europe/Berlin', label: 'Berlin' },
  { value: 'Europe/Amsterdam', label: 'Amsterdam' },
  { value: 'Europe/Rome', label: 'Rome' },
  { value: 'Europe/Madrid', label: 'Madrid' },
  { value: 'Europe/Stockholm', label: 'Stockholm' },
  { value: 'Europe/Athens', label: 'Athens, Istanbul' },
  { value: 'Europe/Moscow', label: 'Moscow' },
  { value: 'Asia/Dubai', label: 'Dubai' },
  { value: 'Asia/Kolkata', label: 'India' },
  { value: 'Asia/Bangkok', label: 'Bangkok' },
  { value: 'Asia/Singapore', label: 'Singapore' },
  { value: 'Asia/Shanghai', label: 'Beijing, Shanghai' },
  { value: 'Asia/Hong_Kong', label: 'Hong Kong' },
  { value: 'Asia/Tokyo', label: 'Tokyo' },
  { value: 'Asia/Seoul', label: 'Seoul' },
  { value: 'Australia/Perth', label: 'Perth' },
  { value: 'Australia/Sydney', label: 'Sydney' },
  { value: 'Australia/Melbourne', label: 'Melbourne' },
  { value: 'Pacific/Auckland', label: 'Auckland' },
]

// Include any currently-saved timezone that isn't in the standard list
const timezones = computed(() => {
  const known = new Set(TIMEZONE_LIST.map(t => t.value))
  const current = props.timezone
  const detected = Intl.DateTimeFormat().resolvedOptions().timeZone
  const extras: { value: string; label: string }[] = []
  for (const tz of [current, detected]) {
    if (tz && !known.has(tz)) {
      known.add(tz)
      extras.push({ value: tz, label: tz })
    }
  }
  return extras.length ? [...extras, ...TIMEZONE_LIST] : TIMEZONE_LIST
})
</script>

<template>
  <div class="tab-content">
    <h2>General Settings</h2>

    <div class="section">
      <h3>Appearance</h3>

      <label>
        <span class="label-text">Theme</span>
        <select v-model="localTheme">
          <option value="neon">Neon</option>
          <option value="slate">Slate</option>
          <option value="dracula">Dracula</option>
          <option value="nord">Nord</option>
          <option value="oled">OLED</option>
          <option value="light">Light</option>
        </select>
      </label>

      <label>
        <span class="label-text">Items per page: {{ localPosterDensity }}</span>
        <input
          type="range"
          v-model.number="localPosterDensity"
          min="10"
          max="100"
          step="1"
        />
        <span class="help-text">Number of posters shown per page in the library grid</span>
      </label>

      <label>
        <span class="label-text">Timezone</span>
        <select v-model="localTimezone">
          <option v-for="tz in timezones" :key="tz.value" :value="tz.value">
            {{ tz.label }}
          </option>
        </select>
        <span class="help-text">Used for scheduling and timestamps in history</span>
      </label>
    </div>

    <div class="section">
      <h3>Library Display</h3>
      <p class="section-description">
        Configure how movies and TV shows are displayed in library and batch edit views.
      </p>

      <div class="display-options">
        <label class="checkbox-option">
          <input type="checkbox" v-model="localDeduplicateMovies" />
          <div class="checkbox-content">
            <span class="checkbox-label-text">Hide duplicate movies (multiple editions)</span>
            <span class="checkbox-description">
              Only shows the most recently added version when you have multiple editions of the same movie (e.g., Extended Edition, Director's Cut)
            </span>
          </div>
        </label>

        <label>
          <span class="label-text">Default Sort Order</span>
          <select v-model="localDefaultSort">
            <option value="title-asc">Title (A-Z)</option>
            <option value="title-desc">Title (Z-A)</option>
            <option value="year-desc">Year (Newest First)</option>
            <option value="year-asc">Year (Oldest First)</option>
            <option value="added-desc">Recently Added</option>
            <option value="added-asc">Oldest Added</option>
          </select>
          <span class="help-text">Default sorting for library and batch edit screens</span>
        </label>
      </div>
    </div>

    <div class="section">
      <h3>API Keys</h3>
      <p class="section-description">
        Configure API keys for accessing metadata from external services.
      </p>

      <div class="api-keys-grid">
        <label>
          <span class="label-text">TMDb API Key <span class="required">*</span></span>
          <div class="input-with-button">
            <input
              v-model="localTmdbApiKey"
              type="password"
              placeholder="Enter your TMDb API key"
            />
            <button
              @click="emit('test-api-key', 'tmdb', localTmdbApiKey)"
              class="secondary"
              :disabled="!localTmdbApiKey || testingKeys?.tmdb"
              type="button"
            >
              {{ testingKeys?.tmdb ? 'Testing...' : 'Test' }}
            </button>
          </div>
          <span v-if="apiKeyTestResults?.tmdb" :class="['api-test-result', apiKeyTestResults.tmdb.includes('error') || apiKeyTestResults.tmdb.includes('Error') ? 'error' : 'success']">
            {{ apiKeyTestResults.tmdb }}
          </span>
          <span class="help-text">Required for movie and TV show posters and metadata. Get one at <a href="https://www.themoviedb.org/settings/api" target="_blank">tmdb.org</a></span>
        </label>

        <label>
          <span class="label-text">TVDB API Key</span>
          <div class="input-with-button">
            <input
              v-model="localTvdbApiKey"
              type="password"
              placeholder="Enter your TVDB API key"
            />
            <button
              @click="emit('test-api-key', 'tvdb', localTvdbApiKey)"
              class="secondary"
              :disabled="!localTvdbApiKey || testingKeys?.tvdb"
              type="button"
            >
              {{ testingKeys?.tvdb ? 'Testing...' : 'Test' }}
            </button>
          </div>
          <span v-if="apiKeyTestResults?.tvdb" :class="['api-test-result', apiKeyTestResults.tvdb.includes('error') || apiKeyTestResults.tvdb.includes('Error') ? 'error' : 'success']">
            {{ apiKeyTestResults.tvdb }}
          </span>
          <span class="help-text">Required for TV. Provides TV show artwork. Get one at <a href="https://www.thetvdb.com/api" target="_blank">thetvdb.com</a></span>
        </label>

        <label>
          <span class="label-text">Fanart.tv API Key</span>
          <div class="input-with-button">
            <input
              v-model="localFanartApiKey"
              type="password"
              placeholder="Enter your Fanart.tv API key"
            />
            <button
              @click="emit('test-api-key', 'fanart', localFanartApiKey)"
              class="secondary"
              :disabled="!localFanartApiKey || testingKeys?.fanart"
              type="button"
            >
              {{ testingKeys?.fanart ? 'Testing...' : 'Test' }}
            </button>
          </div>
          <span v-if="apiKeyTestResults?.fanart" :class="['api-test-result', apiKeyTestResults.fanart.includes('error') || apiKeyTestResults.fanart.includes('Error') ? 'error' : 'success']">
            {{ apiKeyTestResults.fanart }}
          </span>
          <span class="help-text">Optional, but recommended. Provides high-quality clearlogos and artwork — and it's the <strong>only</strong> source of franchise/collection logos, since TMDb doesn't offer any artwork for Collections at all. Without a Fanart key, Collection posters won't be able to auto-find a logo. Get one at <a href="https://fanart.tv/api/" target="_blank">fanart.tv</a></span>
        </label>
      </div>

      <div class="api-test-section">
      </div>
    </div>

    <div class="section">
      <h3>MDBList (overlay ratings &amp; lists)</h3>
      <p class="section-description">
        Overlays can show ratings (IMDb, Rotten Tomatoes, TMDb, Trakt, Metacritic, Letterboxd and more) and only appear on
        items in an MDBList list (for example a "trending" ribbon). Kometa overlay files that use <code>audience_rating</code>,
        <code>critic_rating</code> or <code>mdblist_list</code> need this. Results are cached, so a render rarely calls MDBList.
      </p>
      <div class="api-keys-grid">
        <label>
          <span class="label-text">MDBList API Key</span>
          <div class="input-with-button">
            <input v-model="settingsStore.mdblist.value.apiKey" type="password" placeholder="Enter your MDBList API key" />
            <button
              @click="testMdblist"
              class="secondary"
              :disabled="!settingsStore.mdblist.value.apiKey || mdblistTesting"
              type="button"
            >
              {{ mdblistTesting ? 'Testing...' : 'Test' }}
            </button>
          </div>
          <span v-if="mdblistResult" :class="['api-test-result', mdblistResult.ok ? 'success' : 'error']">
            {{ mdblistResult.message }}
          </span>
          <span class="help-text">Free key at <a href="https://mdblist.com/preferences/" target="_blank">mdblist.com/preferences</a> (API section). The free tier has a daily request limit.</span>
        </label>
        <label>
          <span class="label-text">Audience rating comes from</span>
          <select v-model="settingsStore.mdblist.value.audienceRatingSource">
            <option v-for="s in ratingSources" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
          <span class="help-text">Fills <code>audience_rating</code> (0–10). In Kometa this is your Plex library's audience rating; pick the source your library uses.</span>
        </label>
        <label>
          <span class="label-text">Critic rating comes from</span>
          <select v-model="settingsStore.mdblist.value.criticRatingSource">
            <option v-for="s in ratingSources" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
          <span class="help-text">Fills <code>critic_rating</code> (0–10).</span>
        </label>
        <label>
          <span class="label-text">Keep ratings and lists for (days)</span>
          <input v-model.number="settingsStore.mdblist.value.cacheDays" type="number" min="1" max="90" />
          <span class="help-text">After this, fresh values are fetched. Also used for WeTrakr, SIMKL and Floppy lists.</span>
        </label>
      </div>
    </div>

    <div class="section">
      <h3>WeTrakr (overlay lists)</h3>
      <p class="section-description">
        Show an overlay layer only on items in a WeTrakr list. Public lists work with just the Client ID. Your own private
        lists and your tracking lists (Watchlist, Watching, ...) need you to connect your account once.
      </p>
      <div class="api-keys-grid">
        <label>
          <span class="label-text">WeTrakr Client ID</span>
          <div class="input-with-button">
            <input v-model="settingsStore.wetrakr.value.clientId" type="password" placeholder="Paste the Client ID (not the secret)" />
            <button class="secondary" type="button" :disabled="!settingsStore.wetrakr.value.clientId || sourceTesting.wetrakr" @click="testSource('wetrakr')">
              {{ sourceTesting.wetrakr ? 'Testing...' : 'Test' }}
            </button>
          </div>
          <span v-if="sourceTest.wetrakr" :class="['api-test-result', sourceTest.wetrakr.ok ? 'success' : 'error']">{{ sourceTest.wetrakr.message }}</span>
          <span class="help-text">Create an app at <a href="https://wetrakr.com/profile/settings/api" target="_blank">wetrakr.com → Settings → API</a> and copy its <strong>Client ID</strong>. Simposter doesn't need the client secret or the redirect URL (any value works there). Free for personal use.</span>
        </label>
        <div class="connect-box">
          <span class="label-text">Your account</span>
          <template v-if="connectState.wetrakr">
            <p class="connect-code">Go to <a :href="connectState.wetrakr.url" target="_blank">{{ connectState.wetrakr.url }}</a> and enter <strong>{{ connectState.wetrakr.userCode }}</strong></p>
            <span class="help-text">Waiting for you to approve it on WeTrakr…</span>
            <button class="secondary" type="button" @click="cancelConnect('wetrakr')">Cancel</button>
          </template>
          <template v-else-if="sourceStatus.wetrakr?.connected">
            <p class="connect-ok">✓ Connected{{ sourceStatus.wetrakr.username ? ' as ' + sourceStatus.wetrakr.username : '' }}</p>
            <button class="secondary" type="button" @click="disconnectSource('wetrakr')">Disconnect</button>
          </template>
          <template v-else>
            <button class="secondary" type="button" :disabled="!sourceStatus.wetrakr?.configured || unsavedChanges" @click="connectSource('wetrakr')">Connect account</button>
            <span class="help-text">{{ !sourceStatus.wetrakr?.configured || unsavedChanges ? 'Save the Client ID first.' : 'Only needed for your private lists and tracking lists.' }}</span>
          </template>
          <span v-if="connectError.wetrakr" class="api-test-result error">{{ connectError.wetrakr }}</span>
        </div>
      </div>
    </div>

    <div class="section">
      <h3>SIMKL (overlay lists)</h3>
      <p class="section-description">
        Show an overlay layer only on items in your SIMKL Plan to Watch, Watching, Completed, On Hold or Dropped list, or in a
        SIMKL custom list. Every SIMKL list needs you to connect your account, and custom lists need SIMKL PRO or VIP.
      </p>
      <div class="api-keys-grid">
        <label>
          <span class="label-text">SIMKL Client ID</span>
          <div class="input-with-button">
            <input v-model="settingsStore.simkl.value.clientId" type="password" placeholder="Enter your SIMKL client ID" />
            <button class="secondary" type="button" :disabled="!settingsStore.simkl.value.clientId || sourceTesting.simkl" @click="testSource('simkl')">
              {{ sourceTesting.simkl ? 'Testing...' : 'Test' }}
            </button>
          </div>
          <span v-if="sourceTest.simkl" :class="['api-test-result', sourceTest.simkl.ok ? 'success' : 'error']">{{ sourceTest.simkl.message }}</span>
          <span class="help-text">Register an app at <a href="https://simkl.com/settings/developer/" target="_blank">simkl.com/settings/developer</a> as a new app of type <strong>TV, devices &amp; command line</strong>, and copy its <strong>Client ID</strong>. That type has no secret and supports the code sign-in; Client IDs of older SIMKL apps don't work.</span>
        </label>
        <div class="connect-box">
          <span class="label-text">Your account</span>
          <template v-if="connectState.simkl">
            <p class="connect-code">
              Open <a :href="connectState.simkl.urlComplete || connectState.simkl.url" target="_blank">{{ connectState.simkl.url }}</a>
              and approve code <strong>{{ connectState.simkl.userCode }}</strong>
            </p>
            <span class="help-text">Waiting for you to approve it on SIMKL…</span>
            <button class="secondary" type="button" @click="cancelConnect('simkl')">Cancel</button>
          </template>
          <template v-else-if="sourceStatus.simkl?.connected">
            <p class="connect-ok">✓ Connected{{ sourceStatus.simkl.username ? ' as ' + sourceStatus.simkl.username : '' }}</p>
            <button class="secondary" type="button" @click="disconnectSource('simkl')">Disconnect</button>
          </template>
          <template v-else>
            <button class="secondary" type="button" :disabled="!sourceStatus.simkl?.configured || unsavedChanges" @click="connectSource('simkl')">Connect account</button>
            <span class="help-text">{{ !sourceStatus.simkl?.configured || unsavedChanges ? 'Save the client ID first.' : 'Needed for every SIMKL list.' }}</span>
          </template>
          <span v-if="connectError.simkl" class="api-test-result error">{{ connectError.simkl }}</span>
        </div>
      </div>
    </div>

    <div class="section">
      <h3>Floppy (overlay lists)</h3>
      <p class="section-description">
        Show an overlay layer only on items in a list on your own Floppy server.
      </p>
      <div class="api-keys-grid">
        <label>
          <span class="label-text">Floppy server address</span>
          <input v-model="settingsStore.floppy.value.url" type="text" placeholder="http://192.168.1.10:8000" />
          <span class="help-text">The address you open Floppy at, including the port.</span>
        </label>
        <label>
          <span class="label-text">Floppy App Token</span>
          <div class="input-with-button">
            <input v-model="settingsStore.floppy.value.token" type="password" placeholder="flp_..." />
            <button class="secondary" type="button" :disabled="!settingsStore.floppy.value.url || !settingsStore.floppy.value.token || sourceTesting.floppy" @click="testSource('floppy')">
              {{ sourceTesting.floppy ? 'Testing...' : 'Test' }}
            </button>
          </div>
          <span v-if="sourceTest.floppy" :class="['api-test-result', sourceTest.floppy.ok ? 'success' : 'error']">{{ sourceTest.floppy.message }}</span>
          <span class="help-text">In Floppy: Settings → Integrations → App tokens, with the <code>lists:read</code> scope.</span>
        </label>
      </div>
    </div>

    <div class="section section-coming-soon" aria-disabled="true">
      <h3>More rating &amp; list sources <span class="coming-soon-badge">Coming soon</span></h3>
      <p class="section-description">
        More places to get ratings and lists for overlays, alongside MDBList.
      </p>
      <div class="source-grid">
        <div v-for="src in upcomingSources" :key="src.name" class="source-card">
          <span class="source-name">{{ src.name }}</span>
          <span class="help-text">{{ src.note }}</span>
        </div>
      </div>
    </div>

    <div class="section">
      <button @click="emit('save')" class="primary" :disabled="!unsavedChanges">
        {{ unsavedChanges ? 'Save Changes' : 'No Changes' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.connect-box {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.connect-code {
  margin: 0;
  color: var(--text-primary);
}

.connect-code strong {
  font-family: monospace;
  font-size: 1.1em;
  letter-spacing: 1px;
}

.connect-ok {
  margin: 0;
  color: #3dd6b7;
}

.section-coming-soon {
  opacity: 0.5;
  pointer-events: none;
  user-select: none;
}

.coming-soon-badge {
  margin-left: 8px;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  vertical-align: middle;
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-secondary, #9aa4b2);
}

.source-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.source-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.source-name {
  font-weight: 600;
  color: var(--text-primary);
}

.section-description code,
.help-text code {
  font-size: 0.85em;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.06);
}

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

.help-text a {
  color: var(--accent);
  text-decoration: none;
}

.help-text a:hover {
  text-decoration: underline;
}

.api-keys-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

@media (max-width: 1200px) {
  .api-keys-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .api-keys-grid {
    grid-template-columns: 1fr;
  }
}

.api-test-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.api-test-result {
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  font-weight: 500;
}

.api-test-result.success {
  background: rgba(76, 175, 80, 0.15);
  color: #4caf50;
  border: 1px solid rgba(76, 175, 80, 0.3);
}

.api-test-result.error {
  background: rgba(255, 71, 87, 0.15);
  color: #ff4757;
  border: 1px solid rgba(255, 71, 87, 0.3);
}

select,
input[type="range"] {
  width: 100%;
  max-width: 400px;
}

input[type="text"],
input[type="password"] {
  width: 100%;
  max-width: 400px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
}

input[type="text"]:focus,
input[type="password"]:focus {
  outline: none;
  border-color: var(--accent);
  background: rgba(255, 255, 255, 0.06);
}

.input-with-button {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.input-with-button input {
  flex: 1;
  margin: 0;
}

.input-with-button button {
  padding: 10px 16px;
  white-space: nowrap;
  margin-top: 0;
  height: 40px;
}

.required {
  color: #ff6b6b;
}

.section-description {
  margin: -8px 0 16px 0;
  color: var(--text-muted);
  font-size: 13px;
}

select,
input[type="range"] {
  width: 100%;
  max-width: 400px;
}

select {
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
}

input[type="range"] {
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

.display-options {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.checkbox-option {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 0;
}

.checkbox-option:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--accent);
}

.checkbox-option input[type="checkbox"] {
  margin-top: 2px;
  width: 18px;
  height: 18px;
  cursor: pointer;
  flex-shrink: 0;
}

.checkbox-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.checkbox-label-text {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 14px;
}

.checkbox-description {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}
</style>
