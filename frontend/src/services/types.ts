export type PresetOptions = Record<string, unknown>

export type MediaType = 'movie' | 'tv-show'

export type MovieInput = {
  key: string
  title: string
  year?: number | string
  poster?: string | null
  mediaType?: MediaType
  library_id?: string | number
}

export type Movie = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
  mediaType?: MediaType
  library_id?: string | number
}
