// Lists the overlay editor can offer for "On a list" rules: your own lists on
// every connected service (WeTrakr, SIMKL, Floppy) plus every list already
// cached (MDBList and pasted links), from /api/list-sources/my-lists.
// Shared module state, so every rule editor and summary uses one copy.
import { computed, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { listProvider, normalizeListUrl } from '@/services/overlayEngine'

export interface ListOption {
  key: string
  title: string | null
  provider: string | null
  items?: number | null
}

const PROVIDER_LABELS: Record<string, string> = {
  mdblist: 'MDBList', wetrakr: 'WeTrakr', simkl: 'SIMKL', floppy: 'Floppy',
}

const mine = ref<ListOption[]>([])
const cached = ref<ListOption[]>([])
const errors = ref<Record<string, string>>({})
const loaded = ref(false)
const loading = ref(false)
const titles = ref<Record<string, string>>({})

function remember(items: ListOption[]) {
  const next = { ...titles.value }
  for (const item of items) if (item.title) next[item.key] = item.title
  titles.value = next
}

async function load(refresh = false) {
  if (loading.value || (loaded.value && !refresh)) return
  loading.value = true
  try {
    const res = await fetch(`${getApiBase()}/api/list-sources/my-lists${refresh ? '?refresh=true' : ''}`)
    if (res.ok) {
      const data = await res.json()
      mine.value = data.lists || []
      cached.value = data.cached || []
      errors.value = data.errors || {}
      remember([...mine.value, ...cached.value])
    }
  } catch { /* the picker still takes pasted links */ }
  loaded.value = true
  loading.value = false
}

/** Look up a pasted link. Returns the canonical key and its name, or an error. */
async function resolve(url: string): Promise<{ key?: string; title?: string | null; error?: string }> {
  try {
    const res = await fetch(`${getApiBase()}/api/list-sources/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
    const data = await res.json()
    if (!res.ok) return { error: data.detail || 'Not a list link Simposter recognizes' }
    if (data.title) remember([{ key: data.key, title: data.title, provider: data.provider }])
    return { key: data.key, title: data.title, error: data.error }
  } catch {
    return { error: 'Could not reach the server' }
  }
}

export function providerLabel(provider: string | null | undefined): string {
  return PROVIDER_LABELS[provider || ''] || 'List'
}

/** "WeTrakr: Autumn watchlist" for a list key (falls back to the short link). */
export function listDisplayName(value: unknown): string {
  const key = normalizeListUrl(value) || String(value ?? '')
  const provider = listProvider(key)
  const title = titles.value[key]
  if (title) return `${providerLabel(provider)}: ${title}`
  const short = key
    .replace('https://mdblist.com/lists/', '')
    .replace('https://wetrakr.com/lists/', 'list ')
    .replace('https://simkl.com/lists/', 'list ')
    .replace('floppy:list:', 'list ')
  return provider ? `${providerLabel(provider)}: ${short}` : short
}

export function useListSources() {
  /** Every known list, grouped by service, for a picker. */
  const groups = computed(() => {
    const seen = new Set<string>()
    const out: Record<string, ListOption[]> = {}
    for (const item of [...mine.value, ...cached.value]) {
      if (seen.has(item.key)) continue
      seen.add(item.key)
      const label = providerLabel(item.provider || listProvider(item.key))
      ;(out[label] ||= []).push(item)
    }
    return Object.entries(out).map(([label, items]) => ({ label, items }))
  })
  return { groups, errors, loaded, loading, load, resolve, listDisplayName }
}
