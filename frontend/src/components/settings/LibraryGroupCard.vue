<template>
  <div class="group-card">
    <!-- The group's own name -- a plain heading with a pencil button to edit it,
         not an always-editable textbox (matches this app's already-established
         group-heading pattern). Always lives on the LibraryGroup itself now,
         regardless of whether a Plex member is present -- if it is, this is
         mirrored into that mapping's own displayName via the update:mapping
         emit, so anything reading it there stays in sync. -->
    <div class="group-heading-row">
      <input
        v-if="editingName"
        ref="nameInputRef"
        v-model="nameDraft"
        type="text"
        placeholder="New Group"
        class="group-heading-input"
        @blur="stopEditingName"
        @keydown.enter="($event.target as HTMLInputElement).blur()"
      />
      <template v-else>
        <h4 class="group-heading">{{ group.name || 'New Group' }}</h4>
        <button type="button" class="icon-btn" title="Rename" @click="startEditingName">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
          </svg>
        </button>
      </template>
    </div>

    <!-- One row per server type (Plex, Jellyfin, Emby), all identical: a chip
         per linked library ("Server name: Library") with an ✕ to unlink, or
         "Not linked". One shared picker below adds a library from any server. -->
    <div class="linked-card">
      <div v-for="row in serverRows" :key="row.type" class="server-row">
        <span class="server-type-badge" :class="row.type">{{ row.label }}</span>
        <div class="server-row-body">
          <div v-if="row.members.length" class="linked-member-list">
            <span
              v-for="m in row.members"
              :key="`${m.serverId}:${m.libraryId}`"
              class="linked-member-chip"
              :class="{ 'chip-broken': !memberAvailable(m) }"
              :title="!memberAvailable(m) ? `This server (${m.serverId}) isn't configured or is disabled -- unlink it, or re-enable the server in Media Servers.` : undefined"
            >
              {{ serverDisplayLabel(m.serverId) }}: {{ memberLibraryName(m) }}
              <span v-if="!memberAvailable(m)" class="chip-warning">⚠ not configured</span>
              <button type="button" class="chip-remove" title="Unlink" @click="unlinkMember(m)">✕</button>
            </span>
          </div>
          <span v-else class="server-row-empty">Not linked</span>
        </div>
      </div>

      <div class="add-linked-row">
        <select v-model="pickedKey" class="linked-add-select" @change="addPicked">
          <option value="">+ Link a library...</option>
          <optgroup v-for="srv in pickerGroups" :key="srv.serverId" :label="srv.label">
            <option v-for="o in srv.options" :key="`${o.serverId}:${o.libraryId}`" :value="`${o.serverId}:${o.libraryId}`">
              {{ o.libraryName }}
            </option>
          </optgroup>
        </select>
      </div>
      <p class="link-hint">Picking a library links it immediately — click Save Changes to keep it.</p>
      <p v-if="!pickerGroups.length && !group.members.length" class="no-labels-hint">
        No media servers configured yet, or none reachable — add one in Settings → Media Servers.
      </p>
    </div>

    <!-- Merge-items toggle -- only meaningful once this group actually links
         more than one server, since with a single member there's nothing to
         ever collapse. True (default) is the original, always-existing
         behavior (_dedupe_by_tmdb_id() -- one card per matched tmdb_id,
         governed by the preferred-server picker on the Movies/TV grid
         toolbar itself, Quirk #85). False shows every linked server's own
         copy of a title as its own separate card. -->
    <div v-if="hasMultipleMembers" class="merge-toggle-section">
      <label class="checkbox-label">
        <input type="checkbox" :checked="mergeEnabled" @change="onMergeToggle" />
        <span>Merge items found on more than one linked server into a single poster</span>
        <span v-if="mergeUnsaved" class="unsaved-dot" :title="mergeSaveFailed ? 'Could not save -- check your connection, or use Save Changes below' : 'Not saved yet'">● Unsaved</span>
      </label>
      <span class="help-text">
        On (default): the same movie/show on Plex and Jellyfin shows as one card, using whichever server the grid's "Show posters from" preference picks.
        Off: each linked server's own copy shows as its own separate card.
        Applies immediately to the Movies/TV grid -- no need to click Save Changes.
      </span>
    </div>

    <!-- Auto-generate settings -- when a Plex member exists, this reads/writes
         that Plex library's own mapping entry (still the source of truth
         auto_generate.py/webhooks.py/scheduler.py actually consume); when
         there's no Plex member, it reads/writes the LibraryGroup's own
         fields directly (the only storage a Plex-less group has). -->
    <div v-if="hasAnyMember" class="auto-gen-section">
      <label class="checkbox-label">
        <input type="checkbox" :checked="autoGenEnabled" @change="onAutoGenToggle" />
        <span>Enable automatic poster generation for new content</span>
      </label>

      <div v-if="autoGenEnabled" class="preset-selection">
        <label>
          <span class="label-text">Template & Preset</span>
          <select :value="presetValue" @change="onPresetChange(($event.target as HTMLSelectElement).value)">
            <option value="">Select a preset...</option>
            <option v-for="preset in allPresets" :key="preset.id" :value="preset.id">{{ preset.name }}</option>
          </select>
          <span class="help-text">Choose which template/preset to use for auto-generation</span>
        </label>
      </div>
    </div>

    <!-- Webhook ignore labels -- Plex-only (no Jellyfin/Emby label mechanism
         exists, Quirk #59/#93), only shown once this group has a Plex member. -->
    <div v-if="plexMember" class="webhook-ignore-section">
      <label>
        <span class="label-text">Webhook Ignore Labels <span class="plex-only-tag">Plex only</span></span>
        <span class="help-text">Items with these labels will be skipped when webhooks trigger poster generation</span>
      </label>
      <div v-if="availableLabels.length > 0" class="ignore-labels-grid">
        <label
          v-for="label in availableLabels"
          :key="`ignore-${mapping?.id}-${label}`"
          class="label-checkbox ignore-label-checkbox"
        >
          <input
            type="checkbox"
            :checked="(mapping?.webhookIgnoreLabels || []).includes(label)"
            @change="emit('toggle-ignore-label', label)"
          />
          <span>{{ label }}</span>
        </label>
      </div>
      <p v-else class="no-labels-hint">
        No labels available. Scan the library and click "Refresh Labels" in the Labels section below.
      </p>
    </div>

    <div class="library-actions">
      <!-- One Scan button for every group, disabled while ANY scan is running
           (one scan at a time, server-wide). A group with a main-Plex library
           scans through the parent (Plex scan + its linked libraries); any
           other group scans each of its libraries directly. -->
      <button
        v-if="hasAnyMember"
        @click="plexMember ? emit('scan-plex') : scanNonPlex()"
        :disabled="scanCooldown || anyScanRunning"
        class="scan-btn"
        :title="anyScanRunning && !thisGroupScanning ? 'Another scan is running' : `Scan ${group.name || 'this group'}`"
      >
        {{ thisGroupScanning ? 'Scanning...' : 'Scan' }}
      </button>
      <button @click="removeGroup" class="remove-btn">Remove Group</button>
    </div>
    <p v-if="scanError" class="scan-error">{{ scanError }}</p>
  </div>
</template>

<script setup lang="ts">
// Replaces LinkedServerLibraries.vue + StandaloneServerLibraries.vue with one
// unified card -- a LibraryGroup is just a LibraryGroup now, regardless of
// whether it happens to have a Plex member, matching the user's own direct
// feedback: "there shouldnt be a jellyfin/emby only... if i only had
// jellyfin libraries, then in the groups, id have groups with only 1
// jellyfin library per group." Plex is no longer structurally special in
// this component -- it's just one more row that can be linked or not -- the
// one thing that's still genuinely different about it is the SEPARATE
// plex.libraryMappings/tvShowLibraryMappings array LibrariesTab.vue still
// has to keep in sync, since backend automation (auto_generate.py,
// webhooks.py, scheduler.py) reads that array directly, not LibraryGroup
// (CLAUDE.md's own documented, deliberate scope limit -- rewiring those
// consumers to LibraryGroup directly is real, separate, larger work).
import { computed, nextTick, ref, watch } from 'vue'
import { useSettingsStore, type LibraryGroup, type LibraryGroupMember } from '@/stores/settings'
import { mediaServerLabel } from '@/services/mediaServerLabel'
import { getApiBase } from '@/services/apiBase'
import { useScanStore } from '@/stores/scan'

interface DiscoveredLibrary {
  serverId: string
  serverType: string
  libraryId: string
  libraryName: string
  mediaType: string
}
interface PlexLibraryOption {
  title: string
  key: string
  type: string
}
interface LibraryMapping {
  id: string
  title?: string
  displayName?: string
  autoGenerateEnabled?: boolean
  autoGeneratePresetId?: string | null
  autoGenerateTemplateId?: string | null
  webhookIgnoreLabels?: string[]
}
interface Preset {
  id: string
  name: string
}

const props = defineProps<{
  group: LibraryGroup
  mediaType: 'movie' | 'tv'
  discovered: DiscoveredLibrary[]
  plexLibraries: PlexLibraryOption[]
  usedPlexLibraryIds: Set<string>
  allPresets: Preset[]
  // The corresponding plex.libraryMappings[i]/tvShowLibraryMappings[i] entry
  // IF this group currently has a plex-1 member, else undefined.
  mapping?: LibraryMapping
  savedLibraryIds: Set<string>
  availableLabels: string[]
  scanCooldown: boolean
  scanningLibraryId: string | null
  // This group's own last-SAVED shape (from the backend), or null for a
  // brand-new not-yet-saved group. Used only to show a small "unsaved" dot
  // on specific fields (currently just "Merge items") -- the live `group`
  // prop above is always the current, possibly-unsaved, editable value.
  initialGroup?: LibraryGroup | null
}>()

const emit = defineEmits<{
  // Parent creates the corresponding mapping-array entry.
  'link-plex': [key: string, title: string]
  // Parent confirms (if already saved), splices the mapping entry, strips the
  // plex-1 member, and deletes the group entirely if it's now empty.
  'unlink-plex': []
  'update:mapping': [patch: Partial<LibraryMapping>]
  'toggle-ignore-label': [label: string]
  'scan-plex': []
  // Only emitted when a Plex member exists -- parent confirms (if saved),
  // splices the mapping entry, then deletes the whole group. A Plex-less
  // group's removal is handled entirely inside this component instead
  // (no mapping-array entry to coordinate).
  'remove-group': []
}>()

const settingsStore = useSettingsStore()
const groups = settingsStore.libraryGroups
const apiBase = getApiBase()
const scan = useScanStore()

function serverTypeFor(serverId: string): string {
  const s = settingsStore.mediaServers.value.find(s => s.id === serverId)
  return s?.type || serverId.split('-')[0] || 'plex'
}
function serverDisplayLabel(serverId: string): string {
  return mediaServerLabel(serverId, settingsStore.mediaServers.value)
}
function serverExists(serverId: string): boolean {
  return settingsStore.mediaServers.value.some(s => s.id === serverId)
}

// Plex is in use (URL + token, and its main server isn't switched off).
const plexConfigured = computed(() => settingsStore.plexActive.value)
const plexMember = computed<LibraryGroupMember | undefined>(() =>
  props.group.members.find(m => m.serverId === 'plex-1')
)

// One row per server type. A row shows when a server of that type is in use
// (so a library CAN be linked) or the group already has a member of that type
// (so an orphaned link stays visible and can be unlinked).
const serverRowDefs = [
  { type: 'plex', label: 'Plex' },
  { type: 'jellyfin', label: 'Jellyfin' },
  { type: 'emby', label: 'Emby' },
] as const
const serverRows = computed(() =>
  serverRowDefs
    .map(d => ({ ...d, members: props.group.members.filter(m => serverTypeFor(m.serverId) === d.type) }))
    .filter(d =>
      d.members.length > 0 ||
      (d.type === 'plex' && plexConfigured.value) ||
      settingsStore.mediaServers.value.some(s => s.type === d.type && s.id !== 'plex-1' && s.enabled !== false)
    )
)

function memberAvailable(m: LibraryGroupMember): boolean {
  return m.serverId === 'plex-1' ? plexConfigured.value : serverExists(m.serverId)
}
function memberLibraryName(m: LibraryGroupMember): string {
  if (m.serverId === 'plex-1') {
    const opt = props.plexLibraries.find(p => p.key === m.libraryId)
    if (opt) return opt.title
  }
  return m.libraryName || m.libraryId
}
function unlinkMember(m: LibraryGroupMember) {
  // The main Plex server's library also has a library-mapping entry the parent
  // owns (auto-generate settings etc.), so its unlink goes through the parent.
  if (m.serverId === 'plex-1') emit('unlink-plex')
  else removeMember(m)
}

const availablePlexLibraries = computed(() =>
  props.plexLibraries
    .filter(p => p.type === (props.mediaType === 'movie' ? 'movie' : 'show'))
    .filter(p => !props.usedPlexLibraryIds.has(p.key))
)

function linkPlex(key: string) {
  const opt = props.plexLibraries.find(p => p.key === key)
  if (!opt) return
  groups.value = groups.value.map(g =>
    g.id === props.group.id
      ? { ...g, members: [...g.members, { serverId: 'plex-1', libraryId: opt.key, libraryName: opt.title }] }
      : g
  )
  emit('link-plex', opt.key, opt.title)
}

const availableToAdd = computed(() => {
  const linkedKeys = new Set(props.group.members.map(m => `${m.serverId}:${m.libraryId}`))
  const usedElsewhere = new Set<string>()
  for (const g of groups.value) {
    if (g.id === props.group.id) continue
    for (const m of g.members) usedElsewhere.add(`${m.serverId}:${m.libraryId}`)
  }
  return props.discovered
    .filter(d => d.mediaType === props.mediaType && d.serverId !== 'plex-1')
    .filter(d => {
      const key = `${d.serverId}:${d.libraryId}`
      return !linkedKeys.has(key) && !usedElsewhere.has(key)
    })
})

// The shared picker: every server's unlinked libraries, grouped by server. A
// group holds at most one library from the main Plex server.
type PickerOption = { serverId: string; libraryId: string; libraryName: string }
const pickerGroups = computed(() => {
  const options: PickerOption[] = []
  if (plexConfigured.value && !plexMember.value) {
    for (const p of availablePlexLibraries.value) options.push({ serverId: 'plex-1', libraryId: p.key, libraryName: p.title })
  }
  for (const d of availableToAdd.value) options.push({ serverId: d.serverId, libraryId: d.libraryId, libraryName: d.libraryName })
  const byServer: { serverId: string; label: string; options: PickerOption[] }[] = []
  for (const o of options) {
    let g = byServer.find(b => b.serverId === o.serverId)
    if (!g) {
      g = { serverId: o.serverId, label: serverDisplayLabel(o.serverId), options: [] }
      byServer.push(g)
    }
    g.options.push(o)
  }
  return byServer
})

const pickedKey = ref('')
function addPicked() {
  if (!pickedKey.value) return
  const sep = pickedKey.value.indexOf(':')
  const serverId = pickedKey.value.slice(0, sep)
  const libraryId = pickedKey.value.slice(sep + 1)
  pickedKey.value = ''
  if (serverId === 'plex-1') {
    linkPlex(libraryId)
    return
  }
  const lib = props.discovered.find(d => d.serverId === serverId && d.libraryId === libraryId)
  if (!lib) return
  groups.value = groups.value.map(g =>
    g.id === props.group.id
      ? { ...g, members: [...g.members, { serverId: lib.serverId, libraryId: lib.libraryId, libraryName: lib.libraryName }] }
      : g
  )
}

function removeMember(member: LibraryGroupMember) {
  groups.value = groups.value.map(g =>
    g.id === props.group.id
      ? { ...g, members: g.members.filter(m => !(m.serverId === member.serverId && m.libraryId === member.libraryId)) }
      : g
  )
}

const nameDraft = ref(props.group.name)
watch(() => props.group.name, v => { if (!editingName.value) nameDraft.value = v })
const editingName = ref(false)
const nameInputRef = ref<HTMLInputElement | null>(null)
function startEditingName() {
  nameDraft.value = props.group.name
  editingName.value = true
  nextTick(() => nameInputRef.value?.focus())
}
function stopEditingName() {
  if (nameDraft.value !== props.group.name) {
    groups.value = groups.value.map(g => g.id === props.group.id ? { ...g, name: nameDraft.value } : g)
    if (plexMember.value) emit('update:mapping', { displayName: nameDraft.value })
  }
  editingName.value = false
}

const hasAnyMember = computed(() => props.group.members.length > 0)
const hasMultipleMembers = computed(() => props.group.members.length > 1)
const mergeEnabled = computed(() => props.group.mergeItems !== false)
// Auto-saves immediately, matching the sibling "Show posters from" control
// on the Movies/TV grid toolbar (Quirk #85) -- unlike every other field on
// this card, this one can't wait for Settings' own page-wide Save button,
// since forgetting to click it (or dismissing the "unsaved changes" confirm
// dialog the wrong way when navigating off Settings) would otherwise leave
// the Movies/TV grid silently out of sync with what the checkbox shows.
// `mergeSavedOverride` tracks what was actually confirmed persisted this
// session, independent of `initialGroup` (a prop only refreshed on a full
// Settings mount) -- `mergeSaveFailed` covers the rare case the background
// POST itself fails (offline, etc.), in which case the local store edit
// still applies (nothing is lost), it just isn't confirmed saved yet; the
// page's own Save Changes button remains a working fallback either way.
const mergeSavedOverride = ref<boolean | null>(null)
const mergeSaveFailed = ref(false)
async function onMergeToggle(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  groups.value = groups.value.map(g => g.id === props.group.id ? { ...g, mergeItems: checked } : g)
  const anyMember = props.group.members[0]
  if (!anyMember) return // a brand-new group with no members yet has nothing to resolve server-side
  mergeSaveFailed.value = false
  try {
    const res = await fetch(`${apiBase}/api/media-server/library-group/merge-items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        server_id: anyMember.serverId,
        library_id: anyMember.libraryId,
        media_type: props.mediaType,
        merge_items: checked,
      }),
    })
    if (res.ok) {
      mergeSavedOverride.value = checked
    } else {
      mergeSaveFailed.value = true
    }
  } catch {
    mergeSaveFailed.value = true
  }
}
// Shows a small dot next to the checkbox whenever it differs from what's
// actually confirmed persisted -- normally cleared the instant the
// auto-save above succeeds, so this only lingers for the two edge cases
// noted above (a brand-new group with no members, or a failed save).
// `initialGroup` is null for a brand-new group, which never counts as
// "unsaved" here -- the whole-section yellow border already covers "a new
// group exists at all."
const mergeUnsaved = computed(() => {
  if (mergeSaveFailed.value) return true
  if (mergeSavedOverride.value !== null) return mergeEnabled.value !== mergeSavedOverride.value
  if (!props.initialGroup) return false
  return mergeEnabled.value !== (props.initialGroup.mergeItems !== false)
})
const autoGenEnabled = computed(() =>
  plexMember.value ? !!props.mapping?.autoGenerateEnabled : !!props.group.autoGenerateEnabled
)
function onAutoGenToggle(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  if (plexMember.value) {
    emit('update:mapping', { autoGenerateEnabled: checked })
  } else {
    groups.value = groups.value.map(g => g.id === props.group.id ? { ...g, autoGenerateEnabled: checked } : g)
  }
}
const presetValue = computed(() => {
  const tId = plexMember.value ? props.mapping?.autoGenerateTemplateId : props.group.autoGenerateTemplateId
  const pId = plexMember.value ? props.mapping?.autoGeneratePresetId : props.group.autoGeneratePresetId
  // A main-Plex group's value comes from LibrariesTab's localLibraries, whose
  // getter already hands back the combined "template:preset" form -- adding the
  // template again produced "template:template:preset", which matches no option,
  // so the dropdown went blank right after every pick.
  if (pId && pId.includes(':')) return pId
  if (tId && pId) return `${tId}:${pId}`
  return pId || ''
})
function onPresetChange(value: string) {
  let templateId: string | null = null
  let presetId: string | null = value || null
  if (value.includes(':')) {
    const [t, p] = value.split(':')
    templateId = t ?? null
    presetId = p ?? null
  }
  if (plexMember.value) {
    emit('update:mapping', { autoGenerateTemplateId: templateId, autoGeneratePresetId: presetId })
  } else {
    groups.value = groups.value.map(g =>
      g.id === props.group.id ? { ...g, autoGenerateTemplateId: templateId, autoGeneratePresetId: presetId } : g
    )
  }
}

// Plex-anchored groups delegate scanning to the parent (fires the existing
// scan-library emit, which SettingsView.vue's scanLibrary() already also
// runs scan-linked for afterward -- Quirk #66); a Plex-less group scans each
// of its own members directly (mirrors StandaloneServerLibraries.vue's
// original scanGroup()).
const scanningNonPlex = ref(false)
const scanError = ref('')
// Any scan anywhere (the shared status the progress popup follows), or this
// card's own scan between its per-library requests.
const anyScanRunning = computed(() => scan.running.value || scan.checking.value || scanningNonPlex.value)
const thisGroupScanning = computed(() =>
  plexMember.value ? props.scanningLibraryId === props.mapping?.id && !!props.mapping?.id : scanningNonPlex.value
)
async function scanNonPlex() {
  if (anyScanRunning.value) return
  scanningNonPlex.value = true
  scan.running.value = true
  scanError.value = ''
  // Connects this scan to the SAME global scan-progress overlay the Plex
  // scan already uses (App.vue's startScanPolling() is triggered by this
  // exact visible flip, matching SettingsView.vue's own scanLibrary()) --
  // previously a Plex-less group's "Scan" click had no visible feedback
  // anywhere outside this card's own small busy state, even though the
  // backend (as of this fix) now reports real per-library/per-phase
  // progress into scan_status the whole time.
  scan.visible.value = true
  scan.log.value = ['Starting scan...']
  scan.progress.value = { processed: 0, total: 0 }
  scan.current.value = ''
  try {
    for (const m of props.group.members) {
      // Each request returns once that library's scan has finished, so this
      // card knows when it's busy -- re-assert the shared flag per library in
      // case the progress poller saw the gap between two and cleared it.
      scan.running.value = true
      const params = new URLSearchParams({
        library_id: m.libraryId,
        media_type: props.mediaType,
        library_name: m.libraryName || m.libraryId,
      })
      const res = await fetch(`${apiBase}/api/media-server/${m.serverId}/scan?${params.toString()}`, { method: 'POST' })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data?.detail || `Scan failed (${res.status})`)
      }
    }
  } catch (e) {
    scanError.value = e instanceof Error ? e.message : 'Scan failed'
  } finally {
    // Every request has returned, so the scan is over either way.
    scan.running.value = false
    scanningNonPlex.value = false
  }
}

function removeGroup() {
  if (plexMember.value) {
    emit('remove-group')
    return
  }
  if (!window.confirm('Remove this group from Simposter? Its cache/settings are dropped, but nothing is deleted from the media server itself.')) return
  groups.value = groups.value.filter(g => g.id !== props.group.id)
}
</script>

<style scoped>
.group-card {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 12px;
  transition: all 0.2s;
}
.group-card:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(61, 214, 183, 0.3);
}
.group-card:last-of-type { margin-bottom: 0; }

.group-heading-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  min-height: 30px;
}
.group-heading { margin: 0; font-size: 15px; font-weight: 600; color: var(--text-primary); }
.group-heading-input {
  display: block;
  width: 100%;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  padding: 6px 8px;
  border: 1px solid var(--accent);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
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
.icon-btn:hover { color: var(--accent); background: rgba(255, 255, 255, 0.06); }

.linked-card {
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.015);
  overflow: hidden;
}

.server-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.server-row:last-child { border-bottom: none; }
.server-row-body { flex: 1; min-width: 0; }
.server-row-empty {
  display: inline-block;
  padding: 6px 0;
  color: var(--text-muted);
  font-size: 12px;
  font-style: italic;
}

.repoint-hint {
  margin: 6px 0 0 0;
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
}

.linked-member-list { display: flex; flex-wrap: wrap; gap: 8px; margin: 6px 0; }
.linked-member-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.03);
  font-size: 13px;
}
.linked-member-chip.chip-broken {
  border-color: rgba(240, 93, 123, 0.5);
  background: rgba(240, 93, 123, 0.08);
}
.chip-warning {
  color: #f05d7b;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.chip-remove {
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0 2px;
  font-size: 12px;
}
.chip-remove:hover { color: #f05d7b; }

.server-type-badge {
  display: inline-block;
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
.server-row .server-type-badge {
  flex-shrink: 0;
  width: 68px;
  text-align: center;
  margin-top: 4px;
}
.server-type-badge.plex { background: rgba(229, 160, 13, 0.15); color: #e5a00d; }
.server-type-badge.jellyfin { background: rgba(170, 92, 195, 0.15); color: #aa5cc3; }
.server-type-badge.emby { background: rgba(82, 181, 75, 0.15); color: #52b54b; }

.add-linked-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}
.linked-add-select {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 13px;
}

.merge-toggle-section {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}
.merge-toggle-section .help-text { margin-left: 24px; margin-top: 4px; }

.auto-gen-section {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}
.checkbox-label { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.checkbox-label input[type="checkbox"] { width: auto; cursor: pointer; }
.checkbox-label span { font-weight: 500; color: var(--text-primary); font-size: 13px; }
.unsaved-dot { font-weight: 600 !important; color: #f0c040 !important; font-size: 11px !important; white-space: nowrap; }
.preset-selection { margin-top: 10px; margin-left: 24px; }
.preset-selection select {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 13px;
  width: 100%;
}
.label-text { display: block; font-weight: 500; color: var(--text-primary); font-size: 13px; margin-bottom: 4px; }
.help-text { display: block; font-size: 11px; color: var(--text-muted); margin-top: 4px; line-height: 1.3; }

.plex-only-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 5px;
  background: rgba(229, 160, 13, 0.12);
  color: #e5a00d;
  vertical-align: middle;
  margin-left: 4px;
}

.webhook-ignore-section {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}
.webhook-ignore-section > label { margin-bottom: 10px; }
.ignore-labels-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.ignore-label-checkbox {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 107, 107, 0.08);
  border: 1px solid rgba(255, 107, 107, 0.2);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  transition: all 0.2s;
  cursor: pointer;
}
.ignore-label-checkbox:has(input:checked) {
  background: rgba(255, 107, 107, 0.2);
  border-color: rgba(255, 107, 107, 0.5);
}
.ignore-label-checkbox:hover { border-color: rgba(255, 107, 107, 0.4); }

.no-labels-hint {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
  margin: 0;
  padding: 0 12px 10px;
}

.library-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}
.scan-btn {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(61, 214, 183, 0.1);
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.scan-btn:hover:not(:disabled) { background: rgba(61, 214, 183, 0.2); border-color: var(--accent); }
.scan-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.remove-btn {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(255, 0, 0, 0.1);
  color: #ff6b6b;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.remove-btn:hover:not(:disabled) { background: rgba(255, 0, 0, 0.2); border-color: #ff6b6b; }

.scan-error {
  margin: 8px 0 0 0;
  font-size: 11px;
  color: #f05d7b;
}

.link-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
  padding: 0 12px 10px;
}
</style>
