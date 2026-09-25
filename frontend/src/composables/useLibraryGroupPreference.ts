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
}

export function useLibraryGroupPreference(mediaType: 'movie' | 'tv') {
  const apiBase = getApiBase()
  const settingsStore = useSettingsStore()
  const group = ref<GroupInfo | null>(null)
  const saving = ref(false)

  // Options always list the Plex member first (it's the group's structural
  // anchor -- Quirk #62 -- so it's always present when a group exists at all),
  // then every other linked member.
  const options = computed(() => {
    if (!group.value) return []
    const others = group.value.members.filter(m => m.serverId !== 'plex-1')
    return [
      { id: 'plex-1', label: mediaServerLabel('plex-1', settingsStore.mediaServers.value) },
      ...others.map(m => ({ id: m.serverId, label: mediaServerLabel(m.serverId, settingsStore.mediaServers.value) })),
    ]
  })

  // Only worth showing the dropdown at all once there's a real choice to make.
  const hasChoice = computed(() => options.value.length > 1)

  const preferredServerId = computed(() => group.value?.preferredServerId || 'plex-1')

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

  return { group, options, hasChoice, preferredServerId, saving, load, setPreferred }
}
