// Client-side mirror of backend/overlay_engine.py, used by the Overlay Manager
// preview. Keep the selection rules in step with the backend so the preview
// shows the same elements a real render would.

export interface OverlayCondition {
  field: string
  op: string
  value?: string | number | string[]
}

export interface OverlayRuleFields {
  name?: string
  group?: string
  weight?: number
  suppress?: string[]
  conditions?: OverlayCondition[]
  show_if_label?: string
  hide_if_label?: string
  placement?: string
  horizontal_align?: string
  vertical_align?: string
  horizontal_offset?: number | string
  vertical_offset?: number | string
  back_color?: string
  back_width?: number
  back_height?: number
  back_radius?: number
  back_padding?: number
  back_align?: string
  back_line_color?: string
  back_line_width?: number
  url?: string
  stroke_width?: number
  stroke_color?: string
  box_only?: boolean
  type?: string
  font_style?: string
  addon_position?: string
  addon_offset?: number
  addon_scale?: number
  blur_amount?: number
  queue?: string
  queue_positions?: Array<Record<string, unknown>>
}

export type OverlayContext = Record<string, unknown> & {
  labels?: string[]
  file_paths?: string[]
  lists?: string[]
}

/** Condition fields that test list membership (value = a list key, see normalizeListUrl). */
export const LIST_FIELDS = ['list', 'lists', 'mdblist_list']

const LIST_URL_PREFIX = 'https://mdblist.com/lists/'
const WETRAKR_STATUSES = ['planning', 'watching', 'watched', 'hold', 'dropped']
const SIMKL_STATUSES = ['plantowatch', 'watching', 'completed', 'hold', 'dropped']

/** Canonical list key, the same rules as backend list_sources.normalize_list_key:
 *  MDBList and WeTrakr/SIMKL list links, wetrakr:/simkl: tracking lists and
 *  floppy:list:N. A pasted Floppy link needs the server address, so the editor
 *  resolves it through /api/list-sources/resolve and stores the key. */
export const normalizeListUrl = (url: unknown): string | null => {
  const raw = String(url ?? '').trim()
  if (!raw) return null
  const lower = raw.toLowerCase()
  if (lower.startsWith('wetrakr:')) {
    let st = lower.slice(8).trim()
    if (st === 'paused') st = 'hold'
    if (WETRAKR_STATUSES.includes(st)) return `wetrakr:${st}`
    return /^list:\d+$/.test(st) ? `https://wetrakr.com/lists/${st.slice(5)}` : null
  }
  if (lower.startsWith('simkl:')) {
    let st = lower.slice(6).trim().replace(/\s+/g, '')
    if (st === 'watchlist' || st === 'plan_to_watch') st = 'plantowatch'
    if (SIMKL_STATUSES.includes(st)) return `simkl:${st}`
    return /^list:\d+$/.test(st) ? `https://simkl.com/lists/${st.slice(5)}` : null
  }
  if (lower.startsWith('floppy:list:')) return /^\d+$/.test(raw.slice(12)) ? `floppy:list:${raw.slice(12)}` : null
  const wt = /^(?:https?:\/\/)?(?:www\.|api\.)?wetrakr\.com\/(?:[^?#]*\/)?lists?\/(\d+)/i.exec(raw)
  if (wt) return `https://wetrakr.com/lists/${wt[1]}`
  const sk = /^(?:https?:\/\/)?(?:www\.)?simkl\.com\/(?:[^?#]*\/)?lists?\/(\d+)/i.exec(raw)
  if (sk) return `https://simkl.com/lists/${sk[1]}`
  let u = raw.split('?')[0]!.replace(/\/+$/, '')
  if (u.startsWith('http://')) u = 'https://' + u.slice('http://'.length)
  if (u.startsWith('https://www.mdblist.com/')) u = 'https://mdblist.com/' + u.slice('https://www.mdblist.com/'.length)
  if (!u.startsWith('http')) u = LIST_URL_PREFIX + u.replace(/^\/+/, '')
  if (!u.startsWith(LIST_URL_PREFIX) || u.length <= LIST_URL_PREFIX.length) return null
  return u
}

/** Which service a list key belongs to. */
export const listProvider = (key: string): 'mdblist' | 'wetrakr' | 'simkl' | 'floppy' | null => {
  if (key.startsWith(LIST_URL_PREFIX)) return 'mdblist'
  if (key.startsWith('wetrakr:') || key.startsWith('https://wetrakr.com/')) return 'wetrakr'
  if (key.startsWith('simkl:') || key.startsWith('https://simkl.com/')) return 'simkl'
  if (key.startsWith('floppy:')) return 'floppy'
  return null
}

/** Every list key the elements' conditions refer to. */
export const referencedLists = (elements: OverlayRuleFields[]): string[] => {
  const out: string[] = []
  for (const el of elements) {
    for (const c of el.conditions || []) {
      if (!LIST_FIELDS.includes(String(c.field || '').toLowerCase())) continue
      for (const v of Array.isArray(c.value) ? c.value : [c.value]) {
        const n = normalizeListUrl(v)
        if (n && !out.includes(n)) out.push(n)
      }
    }
  }
  return out
}

export const KOMETA_W = 1000
export const KOMETA_H = 1500

export const CONDITION_FIELDS: Array<{ value: string; label: string }> = [
  { value: 'resolution', label: 'Resolution (4k / 1080p / 720p / sd)' },
  { value: 'video_codec', label: 'Video codec' },
  { value: 'audio_codec', label: 'Audio codec' },
  { value: 'audio_channels', label: 'Audio channels' },
  { value: 'audio_language', label: 'Audio language' },
  { value: 'edition', label: 'Edition' },
  { value: 'filepath', label: 'File path' },
  { value: 'label', label: 'Label' },
  { value: 'studio', label: 'Studio' },
  { value: 'streaming_platform', label: 'Streaming platform' },
  { value: 'audience_rating', label: 'Audience rating (0-10)' },
  { value: 'critic_rating', label: 'Critic rating (0-10)' },
  { value: 'mdb_rating', label: 'MDBList score (0-100)' },
  { value: 'mdb_imdb_rating', label: 'IMDb rating' },
  { value: 'mdb_tomatoes_rating', label: 'Rotten Tomatoes (0-100)' },
  { value: 'mdb_metacritic_rating', label: 'Metacritic (0-100)' },
  { value: 'mdb_tmdb_rating', label: 'TMDb rating' },
  { value: 'mdb_trakt_rating', label: 'Trakt rating' },
  { value: 'mdb_letterboxd_rating', label: 'Letterboxd rating' },
  { value: 'list', label: 'On MDBList list (URL)' },
]

export const CONDITION_OPS: Array<{ value: string; label: string; noValue?: boolean }> = [
  { value: 'eq', label: 'is' },
  { value: 'ne', label: 'is not' },
  { value: 'in', label: 'is one of' },
  { value: 'not_in', label: 'is none of' },
  { value: 'contains', label: 'contains' },
  { value: 'not_contains', label: 'does not contain' },
  { value: 'regex', label: 'matches regex' },
  { value: 'not_regex', label: 'does not match regex' },
  { value: 'gt', label: '>' },
  { value: 'gte', label: '>=' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '<=' },
  { value: 'exists', label: 'has a value', noValue: true },
  { value: 'not_exists', label: 'has no value', noValue: true },
]

const RESOLUTION_ALIASES: Record<string, string> = {
  '4k': '4k', '2160': '4k', '2160p': '4k', uhd: '4k',
  '1080': '1080p', '1080p': '1080p', '1080i': '1080p', fhd: '1080p',
  '720': '720p', '720p': '720p', hd: '720p',
  '576': 'sd', '576p': 'sd', '480': 'sd', '480p': 'sd', sd: 'sd',
}

export const normalizeResolution = (value: unknown): string | null => {
  if (value === null || value === undefined) return null
  const key = String(value).trim().toLowerCase()
  return RESOLUTION_ALIASES[key] ?? (key || null)
}

export const buildContext = (meta: Record<string, unknown>): OverlayContext => {
  const ctx: OverlayContext = { ...meta }
  ctx.resolution = normalizeResolution(ctx.video_resolution)
  if (ctx.year == null && ctx.movie_year != null && ctx.movie_year !== '') ctx.year = ctx.movie_year
  if (ctx.title == null && ctx.movie_title) ctx.title = ctx.movie_title
  ctx.labels = ((meta.labels as unknown[]) || []).map(String)
  ctx.file_paths = ((meta.file_paths as unknown[]) || []).map(String)
  ctx.lists = ((meta.lists as unknown[]) || []).map(l => normalizeListUrl(l) || String(l))
  return ctx
}

const asNumber = (v: unknown): number | null => {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

const fieldValues = (field: string, ctx: OverlayContext): unknown[] => {
  const f = (field || '').trim().toLowerCase()
  if (f === 'filepath' || f === 'file_path' || f === 'filename') return [...(ctx.file_paths || [])]
  if (f === 'label' || f === 'labels') return [...(ctx.labels || [])]
  if (LIST_FIELDS.includes(f)) return [...(ctx.lists || [])]
  const v = ctx[f]
  if (v === null || v === undefined || v === '') return []
  return Array.isArray(v) ? v : [v]
}

// Python's re and JS RegExp differ on a few things (named groups, inline flags
// like (?i)). Translate the common (?i) prefix; anything else invalid fails closed.
const toRegExp = (pattern: string): RegExp | null => {
  let flags = ''
  let p = pattern
  const m = p.match(/^\(\?([imsx]+)\)/)
  if (m && m[1]) {
    if (m[1].includes('i')) flags += 'i'
    if (m[1].includes('s')) flags += 's'
    if (m[1].includes('m')) flags += 'm'
    p = p.slice(m[0].length)
  }
  try { return new RegExp(p, flags) } catch { return null }
}

export const checkCondition = (cond: OverlayCondition, ctx: OverlayContext): boolean => {
  const op = String(cond.op || 'eq').trim().toLowerCase()
  const field = String(cond.field || '').trim().toLowerCase()
  let target: unknown = cond.value
  const values = fieldValues(field, ctx)
  if (field === 'resolution') {
    target = Array.isArray(target) ? target.map(normalizeResolution) : normalizeResolution(target)
  }
  if (LIST_FIELDS.includes(field)) {
    target = Array.isArray(target) ? target.map(t => normalizeListUrl(t) || t) : (normalizeListUrl(target) || target)
  }

  if (op === 'exists') return values.length > 0
  if (op === 'not_exists') return values.length === 0

  if (op === 'regex' || op === 'not_regex') {
    // A list of patterns matches when any of them does (Kometa filter lists).
    const res = (Array.isArray(target) ? target : [target]).map(t => toRegExp(String(t ?? '')))
    if (res.some(r => r === null)) return false
    const hit = values.some(v => res.some(r => (r as RegExp).test(String(v))))
    return op === 'regex' ? hit : !hit
  }

  if (['gt', 'gte', 'lt', 'lte'].includes(op)) {
    const t = asNumber(target)
    const nums = values.map(asNumber).filter((n): n is number => n !== null)
    if (t === null || nums.length === 0) return false
    const n = nums[0] as number
    return op === 'gt' ? n > t : op === 'gte' ? n >= t : op === 'lt' ? n < t : n <= t
  }

  const lowered = values.map(v => String(v).trim().toLowerCase())
  if (op === 'in' || op === 'not_in') {
    const opts = Array.isArray(target) ? target : String(target ?? '').split(',')
    const wanted = new Set(opts.map(o => String(o).trim().toLowerCase()).filter(Boolean))
    const hit = lowered.some(v => wanted.has(v))
    return op === 'in' ? hit : !hit
  }
  const want = target === null || target === undefined ? '' : String(target).trim().toLowerCase()
  if (op === 'eq' || op === 'is') return lowered.includes(want)
  if (op === 'contains') return lowered.some(v => v.includes(want))
  if (op === 'ne' || op === 'not') return !lowered.includes(want)
  if (op === 'not_contains') return !lowered.some(v => v.includes(want))
  return false
}

const labelsPass = (el: OverlayRuleFields, ctx: OverlayContext): boolean => {
  const labels = (ctx.labels || []).map(l => l.toLowerCase())
  if (el.show_if_label && !labels.includes(el.show_if_label.toLowerCase())) return false
  if (el.hide_if_label && labels.includes(el.hide_if_label.toLowerCase())) return false
  return true
}

/** Indices of the elements that render for this item (same rules as the backend). */
export const selectElementIndices = (elements: OverlayRuleFields[], ctx: OverlayContext): Set<number> => {
  const passing: number[] = []
  elements.forEach((el, i) => {
    if (labelsPass(el, ctx) && (el.conditions || []).every(c => checkCondition(c, ctx))) passing.push(i)
  })
  const winners = new Map<string, { weight: number; idx: number }>()
  for (const i of passing) {
    const el = elements[i]
    if (!el || !el.group) continue
    const w = asNumber(el.weight) ?? 0
    const best = winners.get(el.group)
    if (!best || w > best.weight) winners.set(el.group, { weight: w, idx: i })
  }
  const kept = passing.filter(i => {
    const g = elements[i]?.group
    return !g || winners.get(g)?.idx === i
  })
  const suppressed = new Set<string>()
  for (const i of kept) for (const n of elements[i]?.suppress || []) suppressed.add(String(n))
  return new Set(kept.filter(i => !suppressed.has(String(elements[i]?.name || ''))))
}

/** Kometa blur(N): the strongest blur among the drawn layers (0 = none), in Kometa px. */
export const blurAmount = (elements: OverlayRuleFields[], visible: Set<number>): number => {
  let best = 0
  elements.forEach((el, i) => {
    if (el.type === 'blur' && visible.has(i)) best = Math.max(best, asNumber(el.blur_amount) ?? 0)
  })
  return best
}

/** Kometa queues: drawn layers of each queue, highest weight first, take the
 * queue's positions in order. null = the queue ran out of positions. Same as
 * queue_placements() in backend/overlay_engine.py. */
export const queuePlacements = (
  elements: OverlayRuleFields[], visible: Set<number>
): Map<number, Record<string, unknown> | null> => {
  const queues = new Map<string, Array<{ w: number; i: number }>>()
  elements.forEach((el, i) => {
    if (!visible.has(i) || !el.queue || !Array.isArray(el.queue_positions)) return
    const list = queues.get(el.queue) || []
    list.push({ w: asNumber(el.weight) ?? 0, i })
    queues.set(el.queue, list)
  })
  const out = new Map<number, Record<string, unknown> | null>()
  for (const members of queues.values()) {
    members.sort((a, b) => b.w - a.w || a.i - b.i)
    members.forEach((m, slot) => {
      const pos = elements[m.i]?.queue_positions?.[slot]
      out.set(m.i, pos && typeof pos === 'object' ? pos : null)
    })
  }
  return out
}

export const fillText = (template: string, ctx: OverlayContext): string | null => {
  let missing = false
  const out = (template || '').replace(/\{([A-Za-z0-9_.]+)\}/g, (_m, key: string) => {
    let v: unknown
    if (key === 'title' || key === 'movie_title') v = ctx.movie_title ?? ctx.title
    else if (key === 'year' || key === 'movie_year') v = ctx.movie_year ?? ctx.year
    else v = ctx[key]
    if (v === null || v === undefined || String(v).trim() === '') { missing = true; return '' }
    return typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(1) : String(v)
  })
  return missing ? null : out
}

const offsetPx = (value: unknown, span: number, kometaSpan: number): number => {
  if (value === null || value === undefined || value === '') return 0
  const text = String(value).trim()
  if (text.endsWith('%')) return Math.round(span * (asNumber(text.slice(0, -1)) ?? 0) / 100)
  return Math.round((asNumber(text) ?? 0) * span / kometaSpan)
}

/** Top-left corner of a bw x bh box placed with Kometa's align + offset. */
export const placeBox = (el: OverlayRuleFields, W: number, H: number, bw: number, bh: number) => {
  const ha = (el.horizontal_align || 'left').toLowerCase()
  const va = (el.vertical_align || 'top').toLowerCase()
  const hx = offsetPx(el.horizontal_offset, W, KOMETA_W)
  const vy = offsetPx(el.vertical_offset, H, KOMETA_H)
  const x = ha === 'right' ? W - bw - hx : ha === 'center' ? Math.floor((W - bw) / 2) + hx : hx
  const y = va === 'bottom' ? H - bh - vy : va === 'center' ? Math.floor((H - bh) / 2) + vy : vy
  return { x, y }
}

/** Kometa offsets edited by dragging: convert a new box corner back to offsets. */
export const offsetsFromBox = (el: OverlayRuleFields, W: number, H: number, bw: number, bh: number, x: number, y: number) => {
  const ha = (el.horizontal_align || 'left').toLowerCase()
  const va = (el.vertical_align || 'top').toLowerCase()
  const toK = (px: number, span: number, k: number) => Math.round(px * k / span)
  const hx = ha === 'right' ? W - bw - x : ha === 'center' ? x - Math.floor((W - bw) / 2) : x
  const vy = va === 'bottom' ? H - bh - y : va === 'center' ? y - Math.floor((H - bh) / 2) : y
  return { horizontal_offset: toK(hx, W, KOMETA_W), vertical_offset: toK(vy, H, KOMETA_H) }
}

/** #RGB / #RRGGBB / #RRGGBBAA to a CSS color. */
export const cssColor = (value: string | undefined, fallback: string): string => {
  if (!value) return fallback
  const t = value.trim().replace(/^#/, '')
  const hex = (s: string) => parseInt(s, 16)
  if (/^[0-9a-f]{3}$/i.test(t)) return `#${t}`
  if (/^[0-9a-f]{6}$/i.test(t)) return `#${t}`
  if (/^[0-9a-f]{8}$/i.test(t)) {
    return `rgba(${hex(t.slice(0, 2))}, ${hex(t.slice(2, 4))}, ${hex(t.slice(4, 6))}, ${(hex(t.slice(6, 8)) / 255).toFixed(3)})`
  }
  return fallback
}
