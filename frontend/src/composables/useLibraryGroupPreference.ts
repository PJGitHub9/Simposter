// Backs the Movies/TV grid toolbar's live "prefer" dropdown (Quirk #85) --
// only meaningful for a library that's actually linked to another server via
// a Library Group (Quirk #62/#64). Deliberately NOT gated behind Settings'
// own Save button: this control persists on every change, the same way the
// grid's other toolbar controls (Sort by, Filter by Label) already feel
// "live" to the user, even though unlike those two this one genuinely writes
// to the backend immediately (it affects which server's row future page
// loads -- including other users' -- will show, not just this session's
// client-side view).
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore } from '@/stores/settings'
import { mediaServerLabel } from '@/services/mediaServerLabel'

interface GroupMember {
  serverId: string
  libraryId: string
  libraryName?: string
}

interface GroupInfo {
  members: GroupMember[]
  preferredServerId: string | null
  mergeItems?: boolean
}

export function useLibraryGroupPreference(mediaType: 'movie' | 'tv') {
  const apiBase = getApiBase()
  const settingsStore = useSettingsStore()
  const group = ref<GroupInfo | null>(null)
  const saving = ref(false)
  // The page's own `?server=` (set for a Jellyfin/Emby-only library's tab) --
  // the group is looked up by THAT server's library id. Was hardcoded to
  // 'plex-1', so a Jellyfin-only library's group was never found and its
  // "Show posters from" dropdown never appeared.
  const route = useRoute()
  const anchorServerId = () => (route.query.server as string) || 'plex-1'

  // Whether this group merges same-title items across its linked servers into
  // one card (Quirk #120's per-group toggle, Settings -> Libraries). Defaults
  // true when unset, matching the backend's own get_library_group_merge_enabled()
  // default -- every existing group before this field existed behaves exactly
  // as before.
  const mergeEnabled = computed(() => group.value?.mergeItems !== false)

  // The dropdown's meaning flips depending on mergeEnabled (Quirk #121):
  //   - merge on:  "which server wins when the same title is found on more
  //     than one linked server" -- Plex first, then every other member.
  //   - merge off: a genuine FILTER -- "All" (every linked server's own copy
  //     shows as its own card, the default) or one specific server (only that
  //     server's items are shown at all, everything else dropped).
  const options = computed(() => {
    if (!group.value) return []
    // Plex first when it's actually in the group, then every other member
    // (a Jellyfin/Emby-only group gets no phantom Plex option).
    const ids: string[] = []
    if (group.value.members.some(m => m.serverId === 'plex-1')) ids.push('plex-1')
    for (const m of group.value.members) if (m.serverId && !ids.includes(m.serverId)) ids.push(m.serverId)
    const servers = ids.map(id => ({ id, label: mediaServerLabel(id, settingsStore.mediaServers.value) }))
    if (mergeEnabled.value) return servers
    return [{ id: '', label: 'All' }, ...servers]
  })

  // Only worth showing the dropdown at all once there's a real choice to make.
  const hasChoice = computed(() => options.value.length > 1)

  // Merge mode: unset always means "plex-1" (the established default winner).
  // Filter mode: unset means "All" (id: '') -- never silently default to
  // plex-1 here, or turning merge off would look like it also filtered down
  // to Plex-only, which is not what an unset filter is supposed to mean.
  const preferredServerId = computed(() => {
    if (!mergeEnabled.value) return group.value?.preferredServerId || ''
    // Unset: Plex wins when it's in the group, otherwise the first member --
    // mirroring the backend's own merge fallback.
    return group.value?.preferredServerId || options.value[0]?.id || 'plex-1'
  })

  async function load(libraryId: string) {
    group.value = null
    if (!libraryId) return
    try {
      const res = await fetch(
        `${apiBase}/api/media-server/library-group?server_id=${encodeURIComponent(anchorServerId())}&library_id=${encodeURIComponent(libraryId)}&media_type=${mediaType}`
      )
      if (res.ok) {
        const data = await res.json()
        group.value = data.group || null
      }
    } catch {
      group.value = null
    }
  }

  async function setPreferred(libraryId: string, serverId: string): Promise<boolean> {
    if (!group.value) return false
    saving.value = true
    try {
      const res = await fetch(`${apiBase}/api/media-server/library-group/preferred-server`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server_id: anchorServerId(),
          library_id: libraryId,
          media_type: mediaType,
          preferred_server_id: serverId,
        }),
      })
      if (!res.ok) return false
      const data = await res.json()
      group.value = data.group || group.value
      return true
    } catch {
      return false
    } finally {
      saving.value = false
    }
  }

  return { group, options, hasChoice, mergeEnabled, preferredServerId, saving, load, setPreferred }
}
