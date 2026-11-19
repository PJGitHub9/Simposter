<script setup lang="ts">
// Setup wizard step: the library groups, made from the libraries just picked.
// Libraries with the same name on different servers start out together; the
// user can rename a group and move a library to another group or its own.
// Groups that already existed (a wizard re-run) can be renamed and receive
// libraries, but their own libraries stay put (that's Settings → Libraries).
import { computed } from 'vue'
import type { LibraryGroup, LibraryGroupMember } from '@/stores/settings'
import { useSettingsStore } from '@/stores/settings'
import { mediaServerLabel } from '@/services/mediaServerLabel'
import { memberKey, moveMember, moveTargets } from './groupProposals'

const props = defineProps<{
  existingIds: string[]
  lockedMembers: string[]
}>()
const draft = defineModel<LibraryGroup[]>('groups', { required: true })

const settings = useSettingsStore()
const existing = computed(() => new Set(props.existingIds))
const locked = computed(() => new Set(props.lockedMembers))

const sections = computed(() => [
  { type: 'movie' as const, title: 'Movies', groups: draft.value.filter(g => g.mediaType === 'movie') },
  { type: 'tv' as const, title: 'TV Shows', groups: draft.value.filter(g => g.mediaType === 'tv') },
].filter(s => s.groups.length))

const serverType = (id: string) => (id.split('-')[0] || 'plex')
const serverName = (id: string) => mediaServerLabel(id, settings.mediaServers.value)

const targets = (g: LibraryGroup, m: LibraryGroupMember) => moveTargets(draft.value, g.id, m, g.mediaType)

const onMove = (g: LibraryGroup, m: LibraryGroupMember, to: string) => {
  if (!to) return
  draft.value = moveMember(draft.value, g.id, memberKey(m), to, existing.value)
}

const rename = (g: LibraryGroup, name: string) => {
  draft.value = draft.value.map(x => (x.id === g.id ? { ...x, name } : x))
}
</script>

<template>
  <div class="ob-form">
    <p class="ob-hint-text" style="margin-top: 0;">
      A library group is one library as Simposter sees it, even when it's on more than one server
      (for example Plex "Movies" and Jellyfin "Movies"). Settings like the default preset and
      Radarr/Sonarr rules apply to the whole group. Libraries with the same name were put together;
      move any that don't belong.
    </p>

    <div v-for="sec in sections" :key="sec.type" class="ob-lib-section">
      <div class="ob-lib-heading">{{ sec.title }}</div>
      <div v-for="g in sec.groups" :key="g.id" class="ob-server-form grp-card">
        <div class="grp-name-row">
          <input
            class="ob-input grp-name"
            :value="g.name"
            placeholder="Group name"
            @input="rename(g, ($event.target as HTMLInputElement).value)"
          />
          <span v-if="existing.has(g.id)" class="ob-optional">existing</span>
        </div>
        <div v-for="m in g.members" :key="memberKey(m)" class="grp-member">
          <img class="ob-server-icon" :src="`/icons/${serverType(m.serverId)}.svg`" alt="" />
          <span class="ob-row-body">
            <span class="ob-row-title">{{ m.libraryName || m.libraryId }}</span>
            <span class="ob-row-desc"> · {{ serverName(m.serverId) }}</span>
          </span>
          <select
            v-if="!locked.has(memberKey(m))"
            class="ob-input grp-move"
            :value="''"
            @change="onMove(g, m, ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"
          >
            <option value="">Move to…</option>
            <option v-for="t in targets(g, m)" :key="t.id" :value="t.id">{{ t.name || 'Unnamed group' }}</option>
            <option v-if="g.members.length > 1" value="new">New group</option>
          </select>
        </div>
      </div>
    </div>

    <p v-if="!sections.length" class="ob-hint-text">No libraries were picked, so there are no groups to set up.</p>
  </div>
</template>

<style scoped src="./onboardingForm.css"></style>
<style scoped>
.grp-card { gap: 8px; }
.grp-name-row { display: flex; align-items: center; gap: 8px; }
.grp-name { flex: 1; font-weight: 600; }
.grp-member { display: flex; align-items: center; gap: 8px; padding: 4px 2px; }
.grp-move { width: auto; max-width: 180px; padding: 4px 8px; font-size: 12px; appearance: auto; }
</style>
