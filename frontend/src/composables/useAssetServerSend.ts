// Sends a logo or backdrop to one or more of the servers an item lives on
// (its own server plus any linked copies in other_servers), for the Logo and
// Backdrop editor modals. Plex targets go to /api/plex/send-*, Jellyfin/Emby
// targets to /api/media-server/send-*; every upload is sent with
// notify:false and one combined notification is sent afterwards.
import { computed } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { mediaServerLabel } from '@/services/mediaServerLabel'
import { notifySendSummary } from '@/services/sendNotify'
import { useSettingsStore } from '@/stores/settings'

export type AssetKind = 'logo' | 'backdrop'

export interface AssetSendItem {
  key: string
  title: string
  year?: number | string
  is_tv?: boolean
  server_id?: string | null
  library_id?: string | number | null
  other_servers?: { server_id: string; rating_key: string }[] | null
}

export interface AssetSendSource {
  data?: string | null // base64 data URL (upload)
  url?: string | null  // external URL (TMDb/Fanart candidate)
}

export interface AssetSendResult {
  sent: { serverId: string; url: string | null }[]
  failed: { serverId: string; label: string; message: string }[]
}

const ENDPOINTS: Record<AssetKind, { plex: string; other: string; plexData: string; plexUrl: string; resultKey: string }> = {
  logo: { plex: '/api/plex/send-logo', other: '/api/media-server/send-logo', plexData: 'logo_data', plexUrl: 'logo_url', resultKey: 'logo_url' },
  backdrop: { plex: '/api/plex/send-backdrop', other: '/api/media-server/send-backdrop', plexData: 'art_data', plexUrl: 'art_url', resultKey: 'art_url' },
}

export function useAssetServerSend(getItem: () => AssetSendItem, kind: AssetKind) {
  const apiBase = getApiBase()
  const settings = useSettingsStore()

  const ownServerId = computed(() => getItem().server_id || 'plex-1')

  // The item's own server first, then every linked copy (deduped by server).
  const linkedServers = computed(() => {
    const item = getItem()
    const list = [{ server_id: ownServerId.value, rating_key: item.key }]
    for (const o of item.other_servers || []) {
      if (o?.server_id && o.rating_key && !list.some(l => l.server_id === o.server_id)) {
        list.push({ server_id: o.server_id, rating_key: o.rating_key })
      }
    }
    return list
  })

  const labelFor = (serverId: string) => mediaServerLabel(serverId, settings.mediaServers.value)

  const serverOptions = computed(() =>
    linkedServers.value.map(s => ({ server_id: s.server_id, label: labelFor(s.server_id) })),
  )

  async function sendOne(serverId: string, ratingKey: string, source: AssetSendSource): Promise<string | null> {
    const item = getItem()
    const ep = ENDPOINTS[kind]
    const isPlex = serverId === 'plex-1'
    const body: Record<string, unknown> = {
      rating_key: ratingKey,
      is_tv: item.is_tv ?? false,
      notify: false,
    }
    if (isPlex) {
      if (item.library_id != null && ownServerId.value === 'plex-1') body.library_id = String(item.library_id)
      if (source.data) body[ep.plexData] = source.data
      else body[ep.plexUrl] = source.url
    } else {
      body.server_id = serverId
      if (source.data) body.image_data = source.data
      else body.image_url = source.url
    }
    const res = await fetch(`${apiBase}${isPlex ? ep.plex : ep.other}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
    return data[ep.resultKey] || null
  }

  // Sends to every chosen server in parallel, then one notification for the
  // servers that took it.
  async function sendTo(serverIds: string[], source: AssetSendSource): Promise<AssetSendResult> {
    const targets = linkedServers.value.filter(s => serverIds.includes(s.server_id))
    const settled = await Promise.allSettled(targets.map(t => sendOne(t.server_id, t.rating_key, source)))
    const result: AssetSendResult = { sent: [], failed: [] }
    settled.forEach((r, i) => {
      const t = targets[i]!
      if (r.status === 'fulfilled') result.sent.push({ serverId: t.server_id, url: r.value })
      else result.failed.push({ serverId: t.server_id, label: labelFor(t.server_id), message: (r.reason as Error)?.message || 'Failed' })
    })
    if (result.sent.length) {
      const item = getItem()
      await notifySendSummary({
        ratingKey: item.key,
        serverIds: result.sent.map(s => s.serverId),
        assets: [kind],
        libraryId: item.library_id ?? null,
        title: item.title,
        year: item.year ?? null,
        imageData: source.data || null,
        imageUrl: source.url || null,
      })
    }
    return result
  }

  return { linkedServers, ownServerId, serverOptions, labelFor, sendTo }
}
