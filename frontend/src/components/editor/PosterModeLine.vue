<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import PosterModeMenu from '../PosterModeMenu.vue'
import { getApiBase } from '@/services/apiBase'
import { groupIdFor, modeLabel, modeReasonText, type PosterMode } from '@/services/posterModes'
import type { MovieInput } from '@/services/types'

const props = defineProps<{ movie: MovieInput }>()

const apiBase = getApiBase()
const mode = ref<string>(props.movie.poster_mode || 'full')
const reason = ref<string>(props.movie.poster_mode_reason || '')
const groupInfo = ref<{ id?: string } | null>(null)
// The group lookup decides which group the menu writes to; until it finishes
// the pseudo id (group-{type}-{library}) could be the wrong group.
const groupLoaded = ref(false)
let loadSeq = 0

const mediaType = computed<'movie' | 'tv'>(() => (props.movie.mediaType === 'tv-show' ? 'tv' : 'movie'))
const serverId = computed(() => props.movie.server_id || 'plex-1')
const libraryId = computed(() => (props.movie.library_id != null ? String(props.movie.library_id) : ''))
// Collections and Poster API items have no poster mode.
const applicable = computed(() => !props.movie.apiMode && props.movie.mediaType !== 'collection' && !!libraryId.value)
const groupId = computed(() => groupIdFor(groupInfo.value, serverId.value, libraryId.value, mediaType.value))
const modeItems = computed(() => [{ tmdb_id: props.movie.tmdb_id, tvdb_id: props.movie.tvdb_id }])
const hasIds = computed(() => !!(props.movie.tmdb_id || props.movie.tvdb_id))

async function loadGroup() {
  const seq = ++loadSeq
  groupInfo.value = null
  groupLoaded.value = false
  if (!applicable.value) return
  try {
    const res = await fetch(
      `${apiBase}/api/media-server/library-group?server_id=${encodeURIComponent(serverId.value)}&library_id=${encodeURIComponent(libraryId.value)}&media_type=${mediaType.value}`,
    )
    if (res.ok) groupInfo.value = (await res.json()).group || null
  } catch {
    groupInfo.value = null
  }
  if (seq !== loadSeq) return
  groupLoaded.value = true
  // The item's own mode/reason (search and History items carry none), now that
  // the group is known.
  await reloadMode(seq)
}

async function reloadMode(seq: number = loadSeq) {
  if (!applicable.value || !hasIds.value) return
  try {
    const res = await fetch(`${apiBase}/api/poster-modes?group_id=${encodeURIComponent(groupId.value)}&media_type=${mediaType.value}`)
    if (!res.ok || seq !== loadSeq) return
    const data = await res.json()
    const idType = mediaType.value === 'movie' ? 'tmdb' : (props.movie.tvdb_id ? 'tvdb' : 'tmdb')
    const id = String(idType === 'tvdb' ? props.movie.tvdb_id : props.movie.tmdb_id)
    const found = (data.items || []).find((i: { id_type: string; item_id: string }) => i.id_type === idType && String(i.item_id) === id)
    mode.value = found?.mode || 'full'
    reason.value = found?.reason || ''
  } catch {
    /* keep what the list said */
  }
}

async function onChanged(_m: PosterMode | null, updated: number) {
  if (updated > 0) await reloadMode()
}

watch(() => props.movie.key, () => {
  mode.value = props.movie.poster_mode || 'full'
  reason.value = props.movie.poster_mode_reason || ''
  loadGroup()
}, { immediate: true })
</script>

<template>
  <div v-if="applicable && hasIds" class="poster-mode-line" :class="'pm-' + mode">
    <span class="pm-label">Poster mode: <strong>{{ modeLabel(mode) }}</strong><template v-if="mode !== 'full' && reason"> ({{ modeReasonText(reason) }})</template></span>
    <PosterModeMenu :group-id="groupId" :media-type="mediaType" :items="modeItems" :disabled="!groupLoaded" @changed="onChanged" />
    <p v-if="mode === 'overlay_only'" class="pm-note">Sending replaces the other app's poster on this server.</p>
    <p v-else-if="mode === 'leave_alone'" class="pm-note pm-warn">Simposter leaves this title alone; sending will still replace its poster.</p>
  </div>
</template>

<style scoped>
.poster-mode-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  margin: 6px 0;
  font-size: 12px;
  color: var(--muted);
}

.pm-label strong {
  color: inherit;
}

.pm-overlay_only .pm-label strong {
  color: #3dd6b7;
}

.pm-leave_alone .pm-label strong {
  color: #fbbf24;
}

.pm-note {
  flex-basis: 100%;
  margin: 0;
}

.pm-warn {
  color: #fbbf24;
}
</style>
