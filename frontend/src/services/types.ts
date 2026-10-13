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
