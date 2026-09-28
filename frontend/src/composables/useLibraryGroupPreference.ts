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
    const others = group.value.members.filter(m => m.serverId !== 'plex-1')
    const servers = [
      { id: 'plex-1', label: mediaServerLabel('plex-1', settingsStore.mediaServers.value) },
      ...others.map(m => ({ id: m.serverId, label: mediaServerLabel(m.serverId, settingsStore.mediaServers.value) })),
    ]
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
    return group.value?.preferredServerId || 'plex-1'
  })

  async function load(libraryId: string) {
    group.value = null
    if (!libraryId) return
    try {
      const res = await fetch(
        `${apiBase}/api/media-server/library-group?server_id=plex-1&library_id=${encodeURIComponent(libraryId)}&media_type=${mediaType}`
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
          server_id: 'plex-1',
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
