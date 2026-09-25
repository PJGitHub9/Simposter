<template>
  <div class="media-servers-tab">
    <h2>Media Servers</h2>
    <p class="hint">
      Connect Simposter to one or more media servers — Plex, Jellyfin, or Emby.
      More than one can be enabled at once.
    </p>

    <!-- One section per server type (Plex / Jellyfin / Emby), each laid out
         identically -- requested directly so the three "look the same in
         terms of UI design, just in their own sections" instead of Jellyfin/
         Emby being nested sub-groups inside one generic "Other Media Servers"
         wrapper. Plex's section additionally carries the always-present,
         can't-be-removed primary connection card at the top.

         Laid out 2-up (matching LibrariesTab.vue's own .libraries-grid
         convention) rather than one full-width column -- at this tab's
         previous 900px single-column width, the page's real 1600px content
         area left a large, genuinely wasted blank strip on the right on any
         normal-width screen (the user's own direct report, with a
         screenshot). A 2-column grid uses that width for a second section
         instead of leaving it empty, without making any individual
         section's own fields stretch uncomfortably wide either. -->
    <div class="server-groups-grid">
    <div
      v-for="group in serverGroups"
      :key="group.type"
      :class="['section', { 'section-unsaved': group.changed }]"
    >
      <h3>{{ group.label }}</h3>

      <div class="server-list">
        <!-- Primary Plex Connection -- the one auto-seeded 'plex-1' entry
             every install already has. Styled identically to the cards
             below (same badge/name/url/credential row shape) so Plex
             doesn't look like a different kind of thing, just labeled
             "Primary" since it's the connection actually used for
             rendering/sending today and can't be removed. -->
        <div v-if="group.type === 'plex'" class="server-card">
          <div class="server-card-row">
            <span class="server-type-badge plex">PLEX</span>
            <input v-model="primaryPlexName" placeholder="Name (optional, e.g. Plex)" class="server-name-input" />
            <span class="primary-badge">Primary</span>
          </div>
          <div class="server-card-row">
            <input v-model="localPlexUrl" placeholder="http://localhost:32400" class="server-url-input" />
            <input v-model="localPlexToken" type="password" placeholder="X-Plex-Token" class="server-credential-input" />
          </div>
          <div class="server-card-row">
            <button
              class="secondary"
              @click="emit('test-connection')"
              :disabled="testConnectionLoading || !localPlexUrl || !localPlexToken"
            >
              {{ testConnectionLoading ? 'Testing...' : 'Test Connection' }}
            </button>
            <span v-if="testConnection" class="test-result-inline" :class="{ ok: testConnection.startsWith('✓') }">{{ testConnection }}</span>
          </div>
          <p class="scan-hint">Which Plex libraries to track is managed in Settings → Libraries.</p>
        </div>

        <!-- Every other configured server of this type -->
        <div v-for="server in group.servers" :key="server.id" class="server-card">
          <div class="server-card-row">
            <span class="server-type-badge" :class="server.type">{{ typeLabel(server.type) }}</span>
            <input v-model="server.name" placeholder="Name (e.g. pj-jellyfin)" class="server-name-input" />
            <label class="enabled-toggle">
              <input type="checkbox" v-model="server.enabled" /> Enabled
            </label>
          </div>
          <div class="server-card-row">
            <input v-model="server.url" placeholder="Server URL" class="server-url-input" />
            <input
              v-if="server.type === 'plex'"
              v-model="server.token"
              type="password"
              placeholder="Plex Token"
              class="server-credential-input"
            />
            <input
              v-else
              v-model="server.apiKey"
              type="password"
              placeholder="API Key"
              class="server-credential-input"
            />
          </div>
          <div class="server-card-row">
            <button class="secondary" @click="testServerConnection(server)" :disabled="testingId === server.id">
              {{ testingId === server.id ? 'Testing…' : 'Test Connection' }}
            </button>
            <span v-if="testResults[server.id]" class="test-result-inline" :class="{ ok: testResults[server.id]?.ok }">{{ testResults[server.id]?.message }}</span>
          </div>
          <p v-if="server.type === 'plex'" class="scan-hint">
            Simposter currently only renders/sends through the primary Plex connection above —
            this entry can be tested and linked to a library for browsing, but won't receive sends yet.
          </p>
          <p v-else class="scan-hint">
            To browse this server's content in Simposter, link one of its libraries to a
            Plex library in Settings → Libraries, then use that library's "Scan" button —
            scanning happens per linked library, not for this whole server at once.
          </p>
          <!-- Moved to its own row at the bottom of the card, as plain text
               rather than an icon-only red ✕ -- the icon sat right next to
               Test Connection and read as ambiguous/alarming (the user's own
               words: "confusing"), easy to misread as part of the connection
               test itself rather than a separate, deliberate delete action. -->
          <div class="server-card-footer">
            <button class="remove-btn-text" @click="removeServer(server.id)">
              Remove Server
            </button>
          </div>
        </div>

        <p v-if="group.type !== 'plex' && !group.servers.length" class="empty-state">
          No {{ group.label }} servers configured yet — add one below.
        </p>
      </div>

      <!-- Collapsed to a single small button by default -- previously the
           full name/url/credential form sat permanently open under every
           section regardless of whether the user was actually adding
           anything right then, which was a real, direct part of "so
           cluttered" (the user's own words: "dont add all the textboxes,
           just a plus button that makes those items appear"). -->
      <button
        v-if="!addFormOpen[group.type]"
        type="button"
        class="secondary-small add-server-toggle"
        @click="addFormOpen[group.type] = true"
      >
        + {{ group.type === 'plex' ? 'Add Another Plex Server' : `Add a ${group.label} Server` }}
      </button>

      <div v-else class="add-server-form">
        <div class="add-server-header">
          <strong class="add-server-title">{{ group.type === 'plex' ? 'Add another Plex server' : `Add a ${group.label} server` }}</strong>
          <button type="button" class="icon-btn" title="Cancel" @click="cancelAddServer(group.type)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <p v-if="group.type === 'plex'" class="scan-hint">
          Simposter currently only renders/sends through your primary Plex connection above —
          an additional Plex entry can be tested and linked for browsing, but won't receive sends yet.
        </p>
        <div class="add-server-row">
          <input v-model="newServerState[group.type].name" placeholder="Name (e.g. pj-jellyfin)" class="server-name-input" />
          <input v-model="newServerState[group.type].url" placeholder="Server URL" class="server-url-input" />
          <input
            v-model="newServerState[group.type].credential"
            type="password"
            :placeholder="group.type === 'plex' ? 'Plex Token' : 'API Key'"
            class="server-credential-input"
          />
        </div>
        <div class="add-server-row">
          <button
            class="secondary"
            @click="testNewServer(group.type)"
            :disabled="newServerState[group.type].testing || !newServerState[group.type].url || !newServerState[group.type].credential"
          >
            {{ newServerState[group.type].testing ? 'Testing…' : 'Test Connection' }}
          </button>
          <span v-if="newServerState[group.type].testResult" class="test-result-inline" :class="{ ok: newServerState[group.type].testResult!.ok }">{{ newServerState[group.type].testResult!.message }}</span>
          <button
            class="primary"
            @click="addServer(group.type)"
            :disabled="!newServerState[group.type].url || !newServerState[group.type].credential"
          >
            Add {{ group.label }} Server
          </button>
        </div>
      </div>
    </div>
    </div>

    <!-- "When the same item is found on more than one server, prefer..." used
         to live here as one global setting (Quirk #74). Moved to Settings ->
         Libraries, scoped per Library Group instead (see
         LinkedServerLibraries.vue's own preferred-server dropdown) -- one
         global choice applied to every linked group at once wasn't granular
         enough once an install has more than one group linked, and the
         user's own framing ("add it in the library category sections") is
         also just a better fit: this choice is about a specific library's
         merged content, not a server-wide default. -->

    <div class="save-row">
      <button class="primary" @click="emit('save')">Save Media Servers</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useSettingsStore, type MediaServerEntry } from '@/stores/settings'
import { getApiBase } from '@/services/apiBase'
import { mediaServerId } from '@/services/mediaServerId'

// Plex is deliberately threaded through as props/emits (mirroring exactly how
// LibrariesTab.vue received them, since the Plex Connection card moved here
// from that tab) rather than bound straight to the store the way
// mediaServers/automation.preferredPosterServer already are. SettingsView.vue's
// saveSettings() unconditionally rebuilds settings.plex.value from its own
// localPlexUrl/localPlexToken refs on every save (from ANY tab) -- binding
// this card directly to the store instead would let that overwrite silently
// revert a Plex edit made here the next time an unrelated tab's Save runs.
// Jellyfin/Emby entries have no such legacy staging ref, so they stay
// store-bound exactly as before.
const props = defineProps<{
  plexUrl: string
  plexToken: string
  testConnection: string
  testConnectionLoading: boolean
  plexConnectionChanged?: boolean
  // Three granular flags (one per server type) instead of a single combined
  // "mediaServers changed" boolean -- so editing, say, just the Jellyfin
  // section doesn't highlight the untouched Plex/Emby sections yellow too.
  // Computed in SettingsView.vue's checkForChanges() the same way every
  // other per-section flag on this page already is.
  plexServersChanged?: boolean
  jellyfinServersChanged?: boolean
  embyServersChanged?: boolean
}>()

const emit = defineEmits<{
  'update:plexUrl': [value: string]
  'update:plexToken': [value: string]
  'test-connection': []
  save: []
}>()

const localPlexUrl = computed({
  get: () => props.plexUrl,
  set: (val) => emit('update:plexUrl', val)
})
const localPlexToken = computed({
  get: () => props.plexToken,
  set: (val) => emit('update:plexToken', val)
})

const apiBase = getApiBase()
const settingsStore = useSettingsStore()
const servers = settingsStore.mediaServers

// The primary Plex connection can be named too, same as any other server --
// stored on its own 'plex-1' entry inside the mediaServers list (not a new
// field on settings.plex), so mediaServerLabel() picks it up everywhere
// else in the app for free. If the entry doesn't exist yet (a fresh,
// not-yet-onboarded install with nothing seeded there yet -- Quirk #57 only
// seeds it once Plex is already configured), typing a name creates a
// minimal stub entry rather than silently doing nothing.
const primaryPlexEntry = computed(() => servers.value.find(s => s.id === 'plex-1'))
const primaryPlexName = computed({
  get: () => primaryPlexEntry.value?.name || '',
  set: (val: string) => {
    const trimmed = val.trim()
    if (primaryPlexEntry.value) {
      servers.value = servers.value.map(s => (s.id === 'plex-1' ? { ...s, name: trimmed || undefined } : s))
    } else {
      servers.value = [...servers.value, { id: 'plex-1', type: 'plex', name: trimmed || undefined, url: '', enabled: true }]
    }
  }
})

interface ServerGroupDef {
  type: 'plex' | 'jellyfin' | 'emby'
  label: string
}
const groupDefs: ServerGroupDef[] = [
  { type: 'plex', label: 'Plex' },
  { type: 'jellyfin', label: 'Jellyfin' },
  { type: 'emby', label: 'Emby' },
]

const serverGroups = computed(() =>
  groupDefs.map(g => ({
    ...g,
    // The primary 'plex-1' entry has its own dedicated card in the template
    // above (always present, can't be removed) -- excluded here so it
    // doesn't also show up a second time in the generic server-card list.
    servers: servers.value.filter(s => s.type === g.type && s.id !== 'plex-1'),
    changed:
      g.type === 'plex' ? !!props.plexServersChanged
      : g.type === 'jellyfin' ? !!props.jellyfinServersChanged
      : !!props.embyServersChanged,
  }))
)

function typeLabel(type: string): string {
  return ({ plex: 'Plex', jellyfin: 'Jellyfin', emby: 'Emby' } as Record<string, string>)[type] || type
}

interface ServerSection {
  title: string
  key: string
  type: string  // "movie" | "show"
}

// Same message SettingsView.vue's own testPlexConnection() already builds
// for the primary Plex card (see its own local copy) -- shared here so
// every "Test Connection" button on this tab (additional Plex entries,
// every Jellyfin/Emby entry) reports what it actually found instead of a
// bare "✓ Connected" with no detail, matching the user's own direct ask
// ("when testing jellyfin connection it should have a similar message as
// plex"). Deliberately a small local duplicate rather than a shared import --
// this project doesn't have an established shared-formatting-helper module
// for Settings components, and one function used in exactly two places isn't
// enough to justify starting one.
function buildConnectionMessage(sections: ServerSection[]): string {
  if (!sections.length) return '✓ Connected'
  const movieLibs = sections.filter(s => s.type === 'movie')
  const tvShowLibs = sections.filter(s => s.type === 'show')
  const movieList = movieLibs.map(s => s.title).join(', ')
  const tvList = tvShowLibs.map(s => s.title).join(', ')
  return `✓ Connected! Found ${movieLibs.length} movie libraries: ${movieList}` +
    (tvShowLibs.length > 0 ? ` and ${tvShowLibs.length} TV show libraries: ${tvList}` : '')
}

// server_id lets the backend resolve an already-masked credential (see the
// docstring on /api/media-server/test-connection) back to the real stored
// value -- harmless to always send even for a brand-new, not-yet-saved
// server (no matching id, so nothing to resolve).
async function testConnectionRequest(type: string, url: string, credential: string, serverId?: string): Promise<{ ok: boolean; message: string }> {
  const body: Record<string, string> = { type, url }
  if (type === 'plex') body.token = credential
  else body.apiKey = credential
  if (serverId) body.server_id = serverId
  try {
    const res = await fetch(`${apiBase}/api/media-server/test-connection`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
    if (!res.ok) return { ok: false, message: '✗ Could not connect' }
    const data = await res.json()
    if (!data.connected) return { ok: false, message: '✗ Could not connect' }
    return { ok: true, message: buildConnectionMessage(data.sections || []) }
  } catch {
    return { ok: false, message: '✗ Could not connect' }
  }
}

const testingId = ref<string | null>(null)
// Stores the full built message now (not just a boolean) -- see
// buildConnectionMessage() above.
const testResults = reactive<Record<string, { ok: boolean; message: string }>>({})

// Named distinctly from the `testConnection` PROP (the Plex status message
// string) -- <script setup> exposes top-level function declarations to the
// template automatically, same as props, and a same-named local function
// silently shadowed the prop everywhere `testConnection` was referenced bare
// in the template (the Plex status box rendered this function's own
// source text instead of the status message -- a real, visible bug, not a
// style nit).
async function testServerConnection(server: MediaServerEntry) {
  testingId.value = server.id
  try {
    const credential = server.type === 'plex' ? (server.token || '') : (server.apiKey || '')
    testResults[server.id] = await testConnectionRequest(server.type, server.url, credential, server.id)
  } catch {
    testResults[server.id] = { ok: false, message: '✗ Could not connect' }
  } finally {
    testingId.value = null
  }
}

interface NewServerState {
  name: string
  url: string
  credential: string
  testing: boolean
  testResult: { ok: boolean; message: string } | null
}
function freshNewServerState(): NewServerState {
  return { name: '', url: '', credential: '', testing: false, testResult: null }
}
// One independent add-a-server form per type now, instead of a single shared
// form with a type dropdown -- the type is implied by which section the form
// sits in.
const newServerState = reactive<Record<'plex' | 'jellyfin' | 'emby', NewServerState>>({
  plex: freshNewServerState(),
  jellyfin: freshNewServerState(),
  emby: freshNewServerState(),
})

// Whether each type's add-server form is expanded -- collapsed by default
// (a small "+ Add a Server" button instead) so a section with nothing to add
// right now doesn't permanently show three empty text fields.
const addFormOpen = reactive<Record<'plex' | 'jellyfin' | 'emby', boolean>>({
  plex: false,
  jellyfin: false,
  emby: false,
})

function cancelAddServer(type: 'plex' | 'jellyfin' | 'emby') {
  newServerState[type] = freshNewServerState()
  addFormOpen[type] = false
}

async function testNewServer(type: 'plex' | 'jellyfin' | 'emby') {
  const state = newServerState[type]
  state.testing = true
  state.testResult = null
  try {
    state.testResult = await testConnectionRequest(type, state.url, state.credential)
  } catch {
    state.testResult = { ok: false, message: '✗ Could not connect' }
  } finally {
    state.testing = false
  }
}

// A stable hash of the (normalized) URL, not Date.now() -- `mediaServers[].id`
// is referenced by value elsewhere (movie_cache/tv_cache.server_id,
// LibraryGroupMember.serverId, Quirk #57/#62/#64), so removing and re-adding
// the *same* server must keep producing the *same* id, or every existing
// Library Group link silently orphans (the server_id it points at no longer
// resolves to any configured server, and nothing ever surfaced that as an
// error -- see CLAUDE.md Quirk #70, found live by the user re-adding
// Jellyfin after the earlier data-loss incident, Quirk #64's last bullet).
// FNV-1a is deliberately simple/dependency-free -- this only needs to be a
// stable, short, URL-safe fingerprint, not cryptographically strong.
function addServer(type: 'plex' | 'jellyfin' | 'emby') {
  const state = newServerState[type]
  const id = mediaServerId(type, state.url)
  const entry: MediaServerEntry = {
    id,
    type,
    name: state.name.trim() || undefined,
    url: state.url.trim(),
    enabled: true,
  }
  if (type === 'plex') entry.token = state.credential
  else entry.apiKey = state.credential
  servers.value = [...servers.value, entry]
  newServerState[type] = freshNewServerState()
  addFormOpen[type] = false
}

function removeServer(id: string) {
  servers.value = servers.value.filter(s => s.id !== id)
  delete testResults[id]
}

// Saving now goes through the same shared save() every other Settings tab
// already uses (see the props docstring above for why Plex specifically
// needs this rather than the standalone settingsStore.save() this button
// used before) -- mediaServers/automation.preferredPosterServer are bound
// straight to the store either way, so they're included in this save
// exactly as they were in the old standalone one.
</script>

<style scoped>
/* Matches the established Settings-tab conventions (see CleanupTab.vue/
   LibrariesTab.vue) rather than inventing a new visual language -- plain
   `button` + .primary/.secondary/.danger modifiers, and the same
   rgba(255,255,255,0.04)-background input/select treatment, so this tab
   doesn't look like a different app bolted on. See CLAUDE.md Quirk #60's
   follow-up note. */
.media-servers-tab {
  padding: 20px;
  /* Back to the same 1600px other grid-using Settings tabs (Libraries) use --
     a plain 900px single column (tried first) fixed the "fields stretched
     too wide" complaint but then left a large, genuinely wasted blank strip
     on the right of any normal-width screen (the user's own follow-up
     report, with a screenshot). The 2-column .server-groups-grid below is
     what actually uses this width now, instead of the page container doing
     it by simply being wide. */
  max-width: 1600px;
}

.server-groups-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 24px;
}

.server-groups-grid .section {
  margin-bottom: 0;
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

.hint {
  color: var(--text-secondary);
  font-size: 13px;
  margin-bottom: 16px;
}

.empty-state {
  color: var(--text-secondary);
  font-style: italic;
  margin: 0 0 16px 0;
}

.section {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  transition: border-color 0.2s, background 0.2s;
}

.section-unsaved {
  border-color: rgba(255, 193, 7, 0.5);
  background: rgba(255, 193, 7, 0.05);
}

.section h3 {
  margin-top: 0;
  margin-bottom: 16px;
  color: var(--text-secondary);
  font-size: 18px;
}

.server-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.server-card {
  /* Matches LibrariesTab.vue's .library-card exactly (subtle nested border +
     accent-on-hover) rather than the .section's own full-strength
     var(--border) -- two full-strength borders stacked (section, then card)
     read as visually heavier/boxier than the rest of the app's nested-card
     convention. */
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.02);
  transition: all 0.2s;
}

.server-card:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(61, 214, 183, 0.3);
}

.server-card-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}

.server-card-row:last-child {
  margin-bottom: 0;
}

.server-type-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-primary);
}

.server-type-badge.plex { background: rgba(229, 160, 13, 0.15); color: #e5a00d; }
.server-type-badge.jellyfin { background: rgba(170, 92, 195, 0.15); color: #aa5cc3; }
.server-type-badge.emby { background: rgba(82, 181, 75, 0.15); color: #52b54b; }

.primary-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  letter-spacing: 0.5px;
  white-space: nowrap;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary);
}

.server-name-input,
.server-url-input,
.server-credential-input,
.server-type-select {
  flex: 1;
  width: auto;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 13px;
}

.enabled-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  font-size: 13px;
  color: var(--text-secondary);
}

.test-result-inline {
  font-size: 13px;
  color: var(--text-secondary);
}

.test-result-inline.ok {
  color: #3dd6b7;
}

.scan-hint {
  color: var(--text-secondary);
  font-size: 12px;
  margin: 4px 0 0 0;
}

/* Bottom row for the "Remove Server" action -- deliberately separated from
   the Test Connection row above (which used to also hold a red ✕ icon
   right next to it, ambiguous and easy to misread as part of testing the
   connection -- the user's own word was "confusing"). A right-aligned
   footer row with a plain text button reads as a distinct, deliberate,
   lower-prominence action instead. */
.server-card-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.remove-btn-text {
  background: none;
  border: none;
  padding: 2px 4px;
  font-size: 12px;
  font-weight: 600;
  color: #f05d7b;
  cursor: pointer;
}

.remove-btn-text:hover {
  text-decoration: underline;
}

/* Collapsed resting state -- a plain small button, matching LibrariesTab.vue's
   own "+ Add" convention, instead of the form's three text fields always
   sitting open underneath every section regardless of whether the user is
   adding anything right now (the user's own direct ask: "dont add all the
   textboxes, just a plus button that makes those items appear"). */
.add-server-toggle {
  width: 100%;
}

/* Vue's scoped styles don't cross component boundaries -- .secondary-small
   is only ever actually defined in LibrariesTab.vue's own scoped styles
   (see Quirk #86, which fixed this exact gap in LinkedServerLibraries.vue).
   Defined locally here too now that this file uses the class for the first
   time, rather than letting the same silent-failure bug happen a third
   time. */
button.secondary-small {
  padding: 6px 12px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

button.secondary-small:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  border-color: var(--accent);
}

.add-server-form {
  /* Same nested-card shape as .server-card above (a dashed border was the
     one pattern in this app associated with drag-and-drop upload zones
     elsewhere, not "an always-visible form" -- borrowing it here read as a
     different kind of control than it actually is). */
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.015);
}

.add-server-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.add-server-title {
  color: var(--text-primary);
  font-size: 14px;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
}

.icon-btn:hover {
  color: #f05d7b;
  background: rgba(255, 255, 255, 0.06);
}

.add-server-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.add-server-row:last-child {
  margin-bottom: 0;
}

.save-row {
  display: flex;
  align-items: center;
  gap: 12px;
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
  white-space: nowrap;
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

button.secondary {
  background: rgba(255, 255, 255, 0.06);
}

button.danger {
  background: rgba(240, 93, 123, 0.12);
  border-color: rgba(240, 93, 123, 0.4);
  color: #f05d7b;
}

button.danger:hover:not(:disabled) {
  background: rgba(240, 93, 123, 0.22);
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
