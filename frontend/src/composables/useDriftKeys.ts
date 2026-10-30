// Items whose poster/logo/backdrop was changed outside Simposter
// (backend/poster_drift.py), for the "Changed" badges on the library grids.
// One shared set, reloaded whenever a grid page mounts.
import { ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

export type DriftAsset = 'poster' | 'logo' | 'backdrop'

const keys = ref<Set<string>>(new Set())
let inFlight: Promise<void> | null = null

const load = () => {
  if (inFlight) return inFlight
  inFlight = (async () => {
    try {
      const res = await fetch(`${getApiBase()}/api/poster-drift/keys`)
      if (!res.ok) return
      const data = await res.json()
      keys.value = new Set(
        (data.items || []).map((i: { rating_key: string; asset_type?: string }) => `${i.rating_key}:${i.asset_type || 'poster'}`),
      )
    } catch {
      // Badges are optional; leave the old set.
    } finally {
      inFlight = null
    }
  })()
  return inFlight
}

export function useDriftKeys() {
  /** True when any of these rating keys has a changed asset of this type. */
  const changed = (ratingKeys: Array<string | null | undefined>, asset: DriftAsset = 'poster') =>
    ratingKeys.some(k => !!k && keys.value.has(`${k}:${asset}`))
  return { load, changed }
}
