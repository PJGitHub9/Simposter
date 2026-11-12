export type PresetOptions = Record<string, unknown>

export type MediaType = 'movie' | 'tv-show' | 'collection'

// {server_id, rating_key} for each other linked server a merged item was also
// found on (database.py's _dedupe_by_tmdb_id()) -- lets the editor fetch/send
// against a title's OTHER servers directly, not just the one the merged card
// happened to be sourced from.
export type OtherServerRef = { server_id: string; rating_key: string }

export type MovieInput = {
  key: string
  title: string
  year?: number | string
  poster?: string | null
  mediaType?: MediaType
  library_id?: string | number
  server_id?: string | null
  also_on?: string[] | null
  other_servers?: OtherServerRef[] | null
  // API mode (Poster API page / server-less search): a TMDb-identified item with
  // no media-server item behind it. `key` is then a synthetic `api-<type>-<id>`
  // string that must never be sent to the backend as a rating key.
  apiMode?: boolean
  tmdb_id?: number | string | null
  tvdb_id?: number | string | null
  // Poster mode (backend/poster_mode.py), from the library list.
  poster_mode?: string | null
  poster_mode_reason?: string | null
}

export type Movie = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
  mediaType?: MediaType
  library_id?: string | number
  server_id?: string | null
  also_on?: string[] | null
  other_servers?: OtherServerRef[] | null
}
