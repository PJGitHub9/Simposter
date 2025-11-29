export type PresetOptions = Record<string, unknown>

export type MovieInput = {
  key: string
  title: string
  year?: number | string
  poster?: string | null
}

export type Movie = {
  key: string
  title: string
  year?: number | string
  addedAt?: number
  poster?: string | null
}
