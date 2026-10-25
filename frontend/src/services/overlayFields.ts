// Fields an overlay rule can test, for the Rules editor. The names must match
// what backend/overlay_engine.py and services/overlayEngine.ts read.
import type { OverlayCondition } from '@/services/overlayEngine'

export type FieldKind = 'choice' | 'text' | 'number' | 'path' | 'list'

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
}

const opts = (pairs: Array<[string, string]>): FieldOption[] => pairs.map(([value, label]) => ({ value, label }))

export const FIELD_GROUPS = ['Video', 'Audio', 'File', 'Ratings', 'Lists', 'Item'] as const

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
    note: 'Needs an MDBList API key.',
  },
  {
    value: 'critic_rating', label: 'Critic rating (0-10)', group: 'Ratings', kind: 'number', placeholder: '7.5',
    note: 'Needs an MDBList API key.',
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
    value: 'list', label: 'On an MDBList list', group: 'Lists', kind: 'list',
    placeholder: 'https://mdblist.com/lists/user/list-name', note: 'Needs an MDBList API key.',
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
    value: 'days_since_added', label: 'Days since added', group: 'Item', kind: 'number', placeholder: '7',
    hint: 'Days since it was added to the library. "is at most 7" = added in the last week. Needs a library scan.',
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
]

const ALIASES: Record<string, string> = {
  file_path: 'filepath', filename: 'filepath', labels: 'label', lists: 'list', mdblist_list: 'list',
}

export const fieldDef = (field: string): FieldDef | undefined => {
  const f = (field || '').trim().toLowerCase()
  return FIELDS.find(d => d.value === (ALIASES[f] || f))
}

export interface OpDef { value: string; label: string; noValue?: boolean; multi?: boolean }

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

const valueLabel = (field: string, v: unknown): string => {
  const def = fieldDef(field)
  const hit = def?.options?.find(o => o.value === String(v))
  if (hit) return hit.label
  if (def?.kind === 'list') return String(v).replace('https://mdblist.com/lists/', '')
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
  const values = Array.isArray(c.value) ? c.value : [c.value]
  const shown = values.filter(v => v !== undefined && v !== null && v !== '').map(v => valueLabel(field, v))
  const valText = shown.length > 3 ? `${shown.slice(0, 3).join(', ')} +${shown.length - 3}` : shown.join(', ')
  return `${name} ${opText} ${valText || '…'}`
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
  { key: 'resolution', label: 'Resolution', group: 'Video', example: '4k' },
  { key: 'video_codec', label: 'Video codec', group: 'Video', example: 'hevc' },
  { key: 'audio_codec', label: 'Audio codec', group: 'Audio', example: 'truehd' },
  { key: 'audio_channels', label: 'Audio channels', group: 'Audio', example: '8' },
  { key: 'audio_language', label: 'Audio language', group: 'Audio', example: 'en' },
  { key: 'audience_rating', label: 'Audience rating (0-10)', group: 'Ratings', example: '8.4', note: 'Needs an MDBList API key' },
  { key: 'critic_rating', label: 'Critic rating (0-10)', group: 'Ratings', example: '9.1', note: 'Needs an MDBList API key' },
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
]

export const TEXT_VARIABLE_GROUPS = ['Item', 'Video', 'Audio', 'Ratings'] as const

/** Fields and {text} values that only have data with an MDBList API key. */
export const needsMdblist = (item: { note?: string }): boolean => /MDBList/i.test(item.note || '')
