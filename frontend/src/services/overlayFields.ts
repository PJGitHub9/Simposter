// Fields an overlay rule can test, for the Rules editor. The names must match
// what backend/overlay_engine.py and services/overlayEngine.ts read.
import type { OverlayCondition } from '@/services/overlayEngine'
import { listDisplayName } from '@/composables/useListSources'

export type FieldKind = 'choice' | 'text' | 'number' | 'path' | 'list' | 'date' | 'today'

export interface FieldOption { value: string; label: string }

export interface FieldDef {
  value: string
  label: string
  group: string
  kind: FieldKind
  hint?: string
  placeholder?: string
  options?: FieldOption[]
  /** Fields that don't apply to every server. */
  note?: string
  /** Checked per country (the condition's region, US by default). */
  regional?: boolean
}

const opts = (pairs: Array<[string, string]>): FieldOption[] => pairs.map(([value, label]) => ({ value, label }))

export const FIELD_GROUPS = ['Video', 'Audio', 'File', 'Ratings', 'Lists', 'Dates', 'Maintainerr', 'Item'] as const

export const FIELDS: FieldDef[] = [
  {
    value: 'resolution', label: 'Resolution', group: 'Video', kind: 'choice',
    options: opts([['4k', '4K'], ['1080p', '1080p'], ['720p', '720p'], ['sd', 'SD']]),
  },
  {
    value: 'video_codec', label: 'Video codec', group: 'Video', kind: 'choice',
    options: opts([['hevc', 'HEVC (H.265)'], ['h264', 'H.264'], ['av1', 'AV1'], ['vc1', 'VC-1'], ['mpeg2video', 'MPEG-2']]),
  },
  {
    value: 'audio_codec', label: 'Audio codec', group: 'Audio', kind: 'choice',
    options: opts([['truehd', 'TrueHD'], ['eac3', 'Dolby Digital Plus'], ['ac3', 'Dolby Digital'], ['dca', 'DTS (Plex)'], ['dts', 'DTS'], ['aac', 'AAC'], ['flac', 'FLAC'], ['opus', 'Opus']]),
  },
  {
    value: 'audio_channels', label: 'Audio channels', group: 'Audio', kind: 'choice',
    options: opts([['2', 'Stereo (2)'], ['6', '5.1 (6)'], ['8', '7.1 (8)']]),
  },
  {
    value: 'audio_language', label: 'Audio language', group: 'Audio', kind: 'text', placeholder: 'en',
    hint: 'Language code of the main audio track.',
  },
  {
    value: 'filepath', label: 'File path / name', group: 'File', kind: 'path',
    placeholder: 'remux', hint: 'Checks every file of the movie (the show folder for TV). Needs a library scan first.',
  },
  {
    value: 'edition', label: 'Edition', group: 'File', kind: 'text', placeholder: 'extended',
    note: 'Plex only; on Jellyfin/Emby use File path instead.',
  },
  {
    value: 'audience_rating', label: 'Audience rating (0-10)', group: 'Ratings', kind: 'number', placeholder: '7.5',
    note: "Your media server's rating (read during scans); pick the source in Settings → Ratings & Lists.",
  },
  {
    value: 'critic_rating', label: 'Critic rating (0-10)', group: 'Ratings', kind: 'number', placeholder: '7.5',
    note: "Your media server's rating (read during scans); pick the source in Settings → Ratings & Lists.",
  },
  { value: 'mdb_rating', label: 'MDBList score (0-100)', group: 'Ratings', kind: 'number', placeholder: '75', note: 'Needs an MDBList API key.' },
  { value: 'mdb_imdb_rating', label: 'IMDb rating (0-10)', group: 'Ratings', kind: 'number', placeholder: '7.5', note: 'Needs an MDBList API key.' },
  { value: 'mdb_tomatoes_rating', label: 'Rotten Tomatoes (0-100)', group: 'Ratings', kind: 'number', placeholder: '80', note: 'Needs an MDBList API key.' },
  { value: 'mdb_tomatoesaudience_rating', label: 'RT audience (0-100)', group: 'Ratings', kind: 'number', placeholder: '80', note: 'Needs an MDBList API key.' },
  { value: 'mdb_metacritic_rating', label: 'Metacritic (0-100)', group: 'Ratings', kind: 'number', placeholder: '70', note: 'Needs an MDBList API key.' },
  { value: 'mdb_tmdb_rating', label: 'TMDb rating (0-100)', group: 'Ratings', kind: 'number', placeholder: '75', note: 'Needs an MDBList API key.' },
  { value: 'mdb_trakt_rating', label: 'Trakt rating (0-100)', group: 'Ratings', kind: 'number', placeholder: '75', note: 'Needs an MDBList API key.' },
  { value: 'mdb_letterboxd_rating', label: 'Letterboxd rating (0-5)', group: 'Ratings', kind: 'number', placeholder: '3.5', note: 'Needs an MDBList API key.' },
  {
    value: 'list', label: 'On a list', group: 'Lists', kind: 'list',
    placeholder: 'Paste a MDBList, WeTrakr, SIMKL or Floppy list link',
    note: 'Lists from MDBList, WeTrakr, SIMKL or Floppy (set them up in Settings → Ratings & Lists).',
  },
  {
    value: 'label', label: 'Label', group: 'Item', kind: 'text', placeholder: '4K',
    note: 'Plex only; Jellyfin/Emby items have no labels.',
  },
  {
    value: 'media_type', label: 'Movie or show', group: 'Item', kind: 'choice',
    options: opts([['movie', 'Movie'], ['tv', 'TV show']]),
  },
  { value: 'year', label: 'Year', group: 'Item', kind: 'number', placeholder: '2024' },
  {
    value: 'today', label: "Today's date", group: 'Dates', kind: 'today',
    hint: 'For seasonal overlays: "is between Dec 1 and Dec 26" shows it every year in that window. Uses the server time zone; a scheduled Overlay Refresh puts it on and takes it off.',
  },
  {
    value: 'added_date', label: 'Date added', group: 'Dates', kind: 'date',
    hint: 'The day it was added to the library. Needs a library scan.',
  },
  {
    value: 'days_since_added', label: 'Days since added', group: 'Dates', kind: 'number', placeholder: '7',
    hint: 'Days since it was added to the library. "is at most 7" = added in the last week. Needs a library scan.',
  },
  {
    value: 'release_date', label: 'Release date', group: 'Dates', kind: 'date',
    hint: 'Release date (movies) or first air date (shows), from TMDb.',
  },
  {
    value: 'days_since_release', label: 'Days since release', group: 'Dates', kind: 'number', placeholder: '30',
    hint: 'From TMDb. Below 0 = not released yet; "is at most 30" = released in the last month.',
  },
  {
    value: 'show_status', label: 'Show status', group: 'Item', kind: 'choice',
    options: opts([['continuing', 'Continuing'], ['ended', 'Ended'], ['canceled', 'Canceled'], ['upcoming', 'Upcoming']]),
    note: 'TV shows; from TMDb.',
  },
  { value: 'tmdb_id', label: 'TMDb ID', group: 'Item', kind: 'text', placeholder: '603', hint: 'Use "is any of" for a list of IDs.' },
  { value: 'tvdb_id', label: 'TVDB ID', group: 'Item', kind: 'text', placeholder: '81189', hint: 'TV shows. Use "is any of" for a list of IDs.' },
  { value: 'title', label: 'Title', group: 'Item', kind: 'text', placeholder: 'Star Wars' },
  { value: 'studio', label: 'Studio', group: 'Item', kind: 'text', placeholder: 'a24' },
  { value: 'streaming_platform', label: 'Streaming platform', group: 'Item', kind: 'text', placeholder: 'netflix' },
  {
    value: 'content_rating', label: 'Content rating', group: 'Item', kind: 'text', placeholder: 'PG-13', regional: true,
    note: "From TMDb: the certification in the chosen country (e.g. PG-13 in US, 12A in GB). Plex's form gb/12A matches too.",
  },
  { value: 'network', label: 'Network', group: 'Item', kind: 'text', placeholder: 'HBO', note: 'TV shows; from TMDb.' },
  {
    value: 'streaming', label: 'Streaming service', group: 'Item', kind: 'text', placeholder: 'Netflix or 8', regional: true,
    note: "From TMDb: subscription services in the chosen country. Use the service's name or its TMDb provider id (Netflix is 8).",
  },
  {
    value: 'removal_date', label: 'Removal date', group: 'Maintainerr', kind: 'date',
    hint: 'The day Maintainerr will act on it.', note: 'Needs Maintainerr',
  },
  {
    value: 'days_until_removal', label: 'Days until removal', group: 'Maintainerr', kind: 'number', placeholder: '7',
    hint: 'Days until Maintainerr acts on it. "exists" = in any Maintainerr collection.', note: 'Needs Maintainerr',
  },
  {
    value: 'maintainerr_collection', label: 'Maintainerr collection', group: 'Maintainerr', kind: 'text', placeholder: 'Leaving Soon',
    hint: "A Maintainerr collection it's in.", note: 'Needs Maintainerr',
  },
]

const ALIASES: Record<string, string> = {
  file_path: 'filepath', filename: 'filepath', labels: 'label', lists: 'list', mdblist_list: 'list',
}

export const fieldDef = (field: string): FieldDef | undefined => {
  const f = (field || '').trim().toLowerCase()
  return FIELDS.find(d => d.value === (ALIASES[f] || f))
}

export interface OpDef { value: string; label: string; noValue?: boolean; multi?: boolean; range?: boolean }

const OPS_BY_KIND: Record<FieldKind, OpDef[]> = {
  choice: [
    { value: 'eq', label: 'is' },
    { value: 'ne', label: 'is not' },
    { value: 'in', label: 'is any of', multi: true },
    { value: 'not_in', label: 'is none of', multi: true },
  ],
  text: [
    { value: 'eq', label: 'is' },
    { value: 'ne', label: 'is not' },
    { value: 'contains', label: 'contains' },
    { value: 'not_contains', label: "doesn't contain" },
    { value: 'in', label: 'is any of', multi: true },
    { value: 'regex', label: 'matches pattern' },
    { value: 'exists', label: 'is set', noValue: true },
    { value: 'not_exists', label: 'is empty', noValue: true },
  ],
  number: [
    { value: 'gte', label: 'is at least' },
    { value: 'gt', label: 'is above' },
    { value: 'lte', label: 'is at most' },
    { value: 'lt', label: 'is below' },
    { value: 'eq', label: 'is exactly' },
    { value: 'exists', label: 'is known', noValue: true },
    { value: 'not_exists', label: 'is unknown', noValue: true },
  ],
  path: [
    { value: 'contains', label: 'contains' },
    { value: 'not_contains', label: "doesn't contain" },
    { value: 'regex', label: 'matches pattern' },
    { value: 'not_regex', label: "doesn't match pattern" },
  ],
  date: [
    { value: 'between', label: 'is between', range: true },
    { value: 'not_between', label: 'is not between', range: true },
    { value: 'gt', label: 'is after' },
    { value: 'lt', label: 'is before' },
    { value: 'gte', label: 'is on or after' },
    { value: 'lte', label: 'is on or before' },
    { value: 'exists', label: 'is known', noValue: true },
    { value: 'not_exists', label: 'is unknown', noValue: true },
  ],
  today: [
    { value: 'between', label: 'is between', range: true },
    { value: 'not_between', label: 'is not between', range: true },
  ],
  list: [
    { value: 'eq', label: 'is on' },
    { value: 'in', label: 'is on any of', multi: true },
    { value: 'ne', label: 'is not on' },
  ],
}

/** Every operator the engine understands, for rules whose field we don't know. */
export const ALL_OPS: OpDef[] = [
  { value: 'eq', label: 'is' },
  { value: 'ne', label: 'is not' },
  { value: 'in', label: 'is any of', multi: true },
  { value: 'not_in', label: 'is none of', multi: true },
  { value: 'contains', label: 'contains' },
  { value: 'not_contains', label: "doesn't contain" },
  { value: 'regex', label: 'matches pattern' },
  { value: 'not_regex', label: "doesn't match pattern" },
  { value: 'gt', label: 'is above' },
  { value: 'gte', label: 'is at least' },
  { value: 'lt', label: 'is below' },
  { value: 'lte', label: 'is at most' },
  { value: 'exists', label: 'is set', noValue: true },
  { value: 'not_exists', label: 'is empty', noValue: true },
  { value: 'between', label: 'is between', range: true },
  { value: 'not_between', label: 'is not between', range: true },
]

export const opsFor = (field: string, currentOp?: string): OpDef[] => {
  const def = fieldDef(field)
  const list = def ? OPS_BY_KIND[def.kind] : ALL_OPS
  // Keep an imported rule's operator selectable even if this field doesn't normally offer it.
  if (currentOp && !list.some(o => o.value === currentOp)) {
    const extra = ALL_OPS.find(o => o.value === currentOp)
    if (extra) return [...list, extra]
  }
  return list
}

export const opDef = (op: string): OpDef | undefined => ALL_OPS.find(o => o.value === op)

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "12-25" -> "Dec 25", "2026-12-25" -> "Dec 25, 2026". */
export const formatDateValue = (v: unknown): string => {
  const s = String(v ?? '').trim()
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/)
  if (m) return `${MONTHS[Number(m[2]) - 1] || m[2]} ${Number(m[3])}, ${m[1]}`
  m = s.match(/^(\d{1,2})-(\d{1,2})$/)
  if (m) return `${MONTHS[Number(m[1]) - 1] || m[1]} ${Number(m[2])}`
  return s
}

/** A between value as [start, end] (stored as a two-item list; "a..b" also read). */
export const rangeParts = (v: unknown): [string, string] => {
  const parts = Array.isArray(v) ? v.map(x => String(x)) : String(v ?? '').split(/\.\.|~/)
  return [String(parts[0] ?? '').trim(), String(parts[1] ?? '').trim()]
}

const valueLabel = (field: string, v: unknown): string => {
  const def = fieldDef(field)
  const hit = def?.options?.find(o => o.value === String(v))
  if (hit) return hit.label
  if (def?.kind === 'list') return listDisplayName(v)
  return String(v)
}

/** "Resolution is 4K", for summaries. */
export const describeCondition = (c: OverlayCondition): string => {
  const field = String(c.field || '')
  if (!field) return '(choose a field)'
  if (field.startsWith('_')) return 'never (unsupported import)'
  const def = fieldDef(field)
  const name = def ? def.label.replace(/ \(.*\)$/, '') : field
  const op = opDef(String(c.op || 'eq'))
  const opText = def ? (opsFor(field).find(o => o.value === c.op)?.label || op?.label || c.op) : (op?.label || c.op)
  if (op?.noValue) return `${name} ${opText}`
  if (op?.range) {
    const [a, b] = rangeParts(c.value)
    return `${name} ${opText} ${a && b ? `${formatDateValue(a)} and ${formatDateValue(b)}` : '…'}`
  }
  if (def?.kind === 'date' || def?.kind === 'today') return `${name} ${opText} ${formatDateValue(c.value) || '…'}`
  const values = Array.isArray(c.value) ? c.value : [c.value]
  const shown = values.filter(v => v !== undefined && v !== null && v !== '').map(v => valueLabel(field, v))
  const valText = shown.length > 3 ? `${shown.slice(0, 3).join(', ')} +${shown.length - 3}` : shown.join(', ')
  const where = def?.regional ? ` (${(String(c.region || '').toUpperCase() || 'US')})` : ''
  return `${name}${where} ${opText} ${valText || '…'}`
}

export interface TextVariable { key: string; label: string; group: string; example: string; note?: string }

/** {variables} a text layer can use. Must match what fill_text() can find in the
 *  overlay context (backend/overlay_engine.py, services/overlayEngine.ts). */
export const TEXT_VARIABLES: TextVariable[] = [
  { key: 'title', label: 'Title', group: 'Item', example: 'Dune' },
  { key: 'year', label: 'Year', group: 'Item', example: '2021' },
  { key: 'edition', label: 'Edition', group: 'Item', example: "Director's Cut", note: 'Plex only' },
  { key: 'studio', label: 'Studio', group: 'Item', example: 'Legendary' },
  { key: 'days_since_added', label: 'Days since added', group: 'Item', example: '3' },
  { key: 'show_status', label: 'Show status', group: 'Item', example: 'continuing', note: 'TV shows only' },
  { key: 'added_date', label: 'Date added', group: 'Item', example: '2026-11-02' },
  { key: 'release_date', label: 'Release date', group: 'Item', example: '2021-10-22' },
  { key: 'days_since_release', label: 'Days since release', group: 'Item', example: '12' },
  { key: 'resolution', label: 'Resolution', group: 'Video', example: '4k' },
  { key: 'video_codec', label: 'Video codec', group: 'Video', example: 'hevc' },
  { key: 'audio_codec', label: 'Audio codec', group: 'Audio', example: 'truehd' },
  { key: 'audio_channels', label: 'Audio channels', group: 'Audio', example: '8' },
  { key: 'audio_language', label: 'Audio language', group: 'Audio', example: 'en' },
  { key: 'audience_rating', label: 'Audience rating (0-10)', group: 'Ratings', example: '8.4', note: "Your media server's rating (read during scans); pick the source in Settings → Ratings & Lists." },
  { key: 'critic_rating', label: 'Critic rating (0-10)', group: 'Ratings', example: '9.1', note: "Your media server's rating (read during scans); pick the source in Settings → Ratings & Lists." },
  { key: 'mdb_rating', label: 'MDBList score (0-100)', group: 'Ratings', example: '82', note: 'Needs an MDBList API key' },
  { key: 'mdb_imdb_rating', label: 'IMDb rating', group: 'Ratings', example: '8.0', note: 'Needs an MDBList API key' },
  { key: 'mdb_tomatoes_rating', label: 'Rotten Tomatoes', group: 'Ratings', example: '83', note: 'Needs an MDBList API key' },
  { key: 'mdb_tomatoesaudience_rating', label: 'RT audience', group: 'Ratings', example: '90', note: 'Needs an MDBList API key' },
  { key: 'mdb_metacritic_rating', label: 'Metacritic', group: 'Ratings', example: '74', note: 'Needs an MDBList API key' },
  { key: 'mdb_tmdb_rating', label: 'TMDb rating', group: 'Ratings', example: '78', note: 'Needs an MDBList API key' },
  { key: 'mdb_trakt_rating', label: 'Trakt rating', group: 'Ratings', example: '81', note: 'Needs an MDBList API key' },
  { key: 'mdb_letterboxd_rating', label: 'Letterboxd rating', group: 'Ratings', example: '3.9', note: 'Needs an MDBList API key' },
  { key: 'mdb_metacriticuser_rating', label: 'Metacritic user score', group: 'Ratings', example: '7.6', note: 'Needs an MDBList API key' },
  { key: 'mdb_myanimelist_rating', label: 'MyAnimeList score', group: 'Ratings', example: '8.7', note: 'Needs an MDBList API key' },
  { key: 'mdb_average_rating', label: 'MDBList average', group: 'Ratings', example: '79', note: 'Needs an MDBList API key' },
  { key: 'leaving', label: 'Leaving (today, tomorrow, Wednesday, Nov 12)', group: 'Maintainerr', example: 'tomorrow', note: 'Needs Maintainerr' },
  { key: 'leaving_date', label: 'Leaving date', group: 'Maintainerr', example: 'Nov 12', note: 'Needs Maintainerr' },
  { key: 'leaving_day', label: 'Leaving weekday', group: 'Maintainerr', example: 'Wednesday', note: 'Needs Maintainerr' },
  { key: 'leaving_days', label: 'Days until leaving', group: 'Maintainerr', example: '6', note: 'Needs Maintainerr' },
]

export const TEXT_VARIABLE_GROUPS = ['Item', 'Video', 'Audio', 'Ratings', 'Maintainerr'] as const

/** Fields and {text} values that only have data with an MDBList API key. */
export const needsMdblist = (item: { note?: string }): boolean => /MDBList/i.test(item.note || '')

/** Fields and {text} values that only have data once Maintainerr is set up. */
export const needsMaintainerr = (item: { note?: string }): boolean => /Maintainerr/i.test(item.note || '')

/** Context keys that come from Maintainerr (rule fields and {text} values). */
export const MAINTAINERR_KEYS = new Set(['removal_date', 'days_until_removal', 'maintainerr_collection',
  'leaving', 'leaving_date', 'leaving_day', 'leaving_days'])
