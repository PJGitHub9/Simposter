<template>
  <div class="linked-servers">
    <!-- The group's own name -- a plain heading with a pencil button to edit
         it, not an always-editable textbox sitting in the layout looking
         like just another form field (the user's own direct feedback: "a
         pencil icon next to the group name vs just a standard textbox").
         Editing still goes through the same debounced-to-blur `nameDraft`
         commit as before (see stopEditingName()'s own comment) -- only the
         resting/display state changed. -->
    <div class="group-heading-row">
      <input
        v-if="editingName"
        ref="nameInputRef"
        v-model="nameDraft"
        type="text"
        placeholder="New Library"
        class="group-heading-input"
        @blur="stopEditingName"
        @keydown.enter="($event.target as HTMLInputElement).blur()"
      />
      <template v-else>
        <h4 class="group-heading">{{ libraryName || 'New Library' }}</h4>
        <button type="button" class="icon-btn" title="Rename" @click="startEditingName">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
          </svg>
        </button>
      </template>
    </div>

    <!-- Plex / Jellyfin / Emby now render as three visually IDENTICAL rows
         inside one bordered card -- badge, then content -- instead of Plex
         looking like a big standalone form field while Jellyfin/Emby looked
         like a separate chip-list section below it (the user's own direct
         feedback: "i dont like how the plex/jellyfin adding server
         libraries to a group is a different style"). Plex's row is still
         functionally special (a single select, always present, never
         removable -- it's the group's own structural anchor, Quirk #62) but
         now SHARES the same row shell/badge/spacing as every other type,
         rather than being its own differently-shaped block above them. -->
    <div class="linked-card">
      <div class="server-row">
        <span class="server-type-badge plex">Plex</span>
        <div class="server-row-body">
          <select
            :value="libraryId"
            class="linked-add-select"
            @change="emit('update:libraryId', ($event.target as HTMLSelectElement).value)"
          >
            <option value="">Select a library...</option>
            <option
              v-for="plexLib in plexLibraries.filter(l => l.type === (mediaType === 'movie' ? 'movie' : 'show'))"
              :key="plexLib.key"
              :value="plexLib.key"
            >
              {{ plexLib.title }} ({{ plexLib.key }})
            </option>
          </select>
          <!-- Not disabled anymore -- changing the Plex library on an already-saved
               card is allowed (Remove+re-add already existed as the only path
               before, which is no safer, just more clicks). Left as a visible,
               non-blocking hint instead of a hard lock, since the real
               consequence (the OLD library's cached posters/labels become
               orphaned under an id nothing points to anymore) is a real cost
               worth knowing about, not a destructive action worth preventing --
               the Cleanup tool (Settings -> Cleanup) already finds and clears
               exactly this kind of orphaned cache safely. -->
          <p v-if="savedLibraryIds.has(String(libraryId))" class="repoint-hint">
            Changing this leaves the previous library's cached posters/labels orphaned (safe to clear later via Settings → Cleanup).
          </p>
          <!-- Explains WHY Plex has to be picked first, rather than just
               silently requiring it with no context -- every library tab in
               Simposter's sidebar, and its Movies/TV grid routing, is keyed
               on a Plex library today, so Plex is this group's required
               anchor, not just "shown first." Jellyfin/Emby libraries link
               to an existing Plex library rather than standing on their own
               (per the user's own direct question about this). -->
          <p v-if="!libraryId" class="anchor-hint">
            Simposter's library pages are organized around Plex, so a group starts with a Plex library — Jellyfin/Emby libraries then link to it below.
          </p>
        </div>
      </div>

      <!-- Jellyfin/Emby always render their own row (even with nothing linked
           yet) so all three types stay visually identical regardless of
           state -- previously a type with zero linked members skipped its
           row entirely, which is part of what made Plex (always shown) and
           Jellyfin/Emby (conditionally shown) read as different kinds of
           things. -->
      <template v-if="libraryId">
        <div v-for="group in otherMemberGroupsAlways" :key="group.type" class="server-row">
          <span class="server-type-badge" :class="group.type">{{ group.label }}</span>
          <div class="server-row-body">
            <div v-if="group.members.length" class="linked-member-list">
              <span
                v-for="m in group.members"
                :key="`${m.serverId}:${m.libraryId}`"
                class="linked-member-chip"
                :class="{ 'chip-broken': !serverExists(m.serverId) }"
                :title="!serverExists(m.serverId) ? `This server (${m.serverId}) is no longer configured -- was it removed and re-added? Unlink and re-add it below.` : undefined"
              >
                {{ serverDisplayLabel(m.serverId) }}: {{ m.libraryName || m.libraryId }}
                <span v-if="!serverExists(m.serverId)" class="chip-warning">⚠ not configured</span>
                <button type="button" class="chip-remove" title="Unlink" @click="removeMember(m)">✕</button>
              </span>
            </div>
            <span v-else class="server-row-empty">Not linked</span>
          </div>
        </div>

        <div class="add-linked-row">
          <select v-model="pickedKey" class="linked-add-select">
            <option value="">Link a library from another server...</option>
            <option v-for="opt in availableToAdd" :key="`${opt.serverId}:${opt.libraryId}`" :value="`${opt.serverId}:${opt.libraryId}`">
              {{ serverDisplayLabel(opt.serverId) }} — {{ opt.libraryName }}
            </option>
          </select>
          <button type="button" class="secondary-small" :disabled="!pickedKey" @click="addPicked">+ Add</button>
        </div>
        <p v-if="!discovered.length" class="no-labels-hint">
          No other media servers configured yet, or none reachable — add one in Media Servers.
        </p>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useSettingsStore, type LibraryGroup, type LibraryGroupMember } from '@/stores/settings'
import { mediaServerLabel } from '@/services/mediaServerLabel'

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

const props = defineProps<{
  libraryId: string
  mediaType: 'movie' | 'tv'
  libraryName: string
  autoGenerateEnabled?: boolean
  autoGeneratePresetId?: string | null
  autoGenerateTemplateId?: string | null
  discovered: DiscoveredLibrary[]
  // Added so the Plex library picker (previously a separate "Library ID"
  // field in LibrariesTab.vue) can live inside this component instead.
  plexLibraries: PlexLibraryOption[]
  savedLibraryIds: Set<string>
}>()

const emit = defineEmits<{
  'update:libraryId': [value: string]
  'update:libraryName': [value: string]
}>()

// Local draft, committed on blur/Enter -- see the template comment above the
// input for why this isn't a plain `:value`/`@input` binding straight onto
// the prop.
const nameDraft = ref(props.libraryName)
watch(() => props.libraryName, (v) => { nameDraft.value = v })

// Resting state is a plain heading + pencil button, not an always-visible
// textbox (the user's own direct feedback -- see the template comment on
// .group-heading-row). Clicking the pencil reveals the same debounced-to-
// blur input as before; nothing about the commit mechanism itself changed.
const editingName = ref(false)
const nameInputRef = ref<HTMLInputElement | null>(null)
function startEditingName() {
  nameDraft.value = props.libraryName
  editingName.value = true
  nextTick(() => nameInputRef.value?.focus())
}
function stopEditingName() {
  if (nameDraft.value !== props.libraryName) emit('update:libraryName', nameDraft.value)
  editingName.value = false
}

const settingsStore = useSettingsStore()
const groups = settingsStore.libraryGroups

const pickedKey = ref('')

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

const ownGroup = computed<LibraryGroup | undefined>(() =>
  groups.value.find(g =>
    g.mediaType === props.mediaType &&
    g.members.some(m => m.serverId === 'plex-1' && m.libraryId === props.libraryId)
  )
)

const otherMembers = computed<LibraryGroupMember[]>(() =>
  (ownGroup.value?.members || []).filter(m => !(m.serverId === 'plex-1' && m.libraryId === props.libraryId))
)

// Grouped by server type (Jellyfin / Emby) into their own labeled rows
// instead of one flat chip row -- requested directly so it's easy to see at
// a glance which libraries from each server are linked here, matching the
// same grouping Settings -> Media Servers now uses. Deliberately NOT
// filtered down to only types with members (unlike the original design) --
// both rows always render, even showing "Not linked" when empty, so Plex/
// Jellyfin/Emby stay visually identical regardless of what's actually
// linked (the user's own direct feedback about the two looking like
// different kinds of things).
const otherMemberGroupDefs = [
  { type: 'jellyfin', label: 'Jellyfin' },
  { type: 'emby', label: 'Emby' },
] as const
const otherMemberGroupsAlways = computed(() =>
  otherMemberGroupDefs.map(g => ({ ...g, members: otherMembers.value.filter(m => serverTypeFor(m.serverId) === g.type) }))
)

const availableToAdd = computed(() => {
  const linkedKeys = new Set((ownGroup.value?.members || []).map(m => `${m.serverId}:${m.libraryId}`))
  // A library already linked to a DIFFERENT Plex library's group can't be linked here too --
  // one (server, library) pair belongs to at most one group.
  const usedElsewhere = new Set<string>()
  for (const g of groups.value) {
    for (const m of g.members) {
      if (!(g === ownGroup.value)) usedElsewhere.add(`${m.serverId}:${m.libraryId}`)
    }
  }
  return props.discovered
    .filter(d => d.mediaType === props.mediaType && d.serverId !== 'plex-1')
    .filter(d => {
      const key = `${d.serverId}:${d.libraryId}`
      return !linkedKeys.has(key) && !usedElsewhere.has(key)
    })
})

function ensureGroup(): LibraryGroup {
  const existing = ownGroup.value
  if (existing) return existing
  const g: LibraryGroup = {
    id: `group-${props.mediaType}-${props.libraryId}`,
    name: props.libraryName || props.libraryId,
    mediaType: props.mediaType,
    members: [{ serverId: 'plex-1', libraryId: props.libraryId, libraryName: props.libraryName }],
    autoGenerateEnabled: !!props.autoGenerateEnabled,
    autoGeneratePresetId: props.autoGeneratePresetId ?? null,
    autoGenerateTemplateId: props.autoGenerateTemplateId ?? null,
    labelsToRemove: [],
  }
  groups.value = [...groups.value, g]
  return g
}

function addPicked() {
  if (!pickedKey.value) return
  const [serverId, libraryId] = pickedKey.value.split(':')
  const lib = props.discovered.find(d => d.serverId === serverId && d.libraryId === libraryId)
  if (!lib) return
  const group = ensureGroup()
  const member: LibraryGroupMember = { serverId: lib.serverId, libraryId: lib.libraryId, libraryName: lib.libraryName }
  groups.value = groups.value.map(g =>
    g.id === group.id ? { ...g, members: [...g.members, member] } : g
  )
  pickedKey.value = ''
}

function removeMember(member: LibraryGroupMember) {
  const group = ownGroup.value
  if (!group) return
  groups.value = groups.value.map(g =>
    g.id === group.id
      ? { ...g, members: g.members.filter(m => !(m.serverId === member.serverId && m.libraryId === member.libraryId)) }
      : g
  )
}
</script>

<style scoped>
.linked-servers {
  margin-top: 10px;
}

.group-heading-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  min-height: 30px;
}

.group-heading {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
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
  color: var(--accent);
  background: rgba(255, 255, 255, 0.06);
}

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

/* One bordered card holding all three server rows -- matches this app's
   established nested-card convention (LibrariesTab.vue's own .library-card:
   a subtle border, not the .section's own full-strength one) instead of
   Plex's picker floating as a big standalone field above a separate,
   differently-shaped Jellyfin/Emby chip section. */
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

.server-row:last-child {
  border-bottom: none;
}

.server-row-body {
  flex: 1;
  min-width: 0;
}

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

.anchor-hint {
  margin: 6px 0 0 0;
  font-size: 11px;
  color: var(--text-muted);
}

.linked-member-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 6px 0;
}

.linked-member-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px 4px 8px;
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

.chip-remove:hover {
  color: #f05d7b;
}

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

/* Vue's scoped styles don't cross component boundaries -- LibrariesTab.vue's
   own .secondary-small rule (its "+ Add" library-card button) never actually
   applied to this button, despite using the same class name, since a child
   component's elements only ever match ITS OWN scoped stylesheet. That left
   this "+ Add" button completely unstyled (bare browser-default button) --
   likely the single most jarring "doesn't align with the rest of the app"
   thing on this whole tab. Defined here too, matching every other Settings
   component's own established pattern of keeping a local copy since there's
   no shared global button stylesheet (see CLAUDE.md Quirk #60). */
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

button.secondary-small:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Same cross-component scoped-style gap as .secondary-small above -- this
   class name is also only ever actually defined in LibrariesTab.vue, which
   never applies here either. */
.no-labels-hint {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
  margin: 0;
  padding: 0 12px 10px;
}
</style>
