export type PresetOptions = Record<string, any>

export type MovieInput = {
  key: string
  title: string
  year?: number | string
  poster?: string | null
}

export type Movie = {
  key: string
  title: string
  year?: number
  addedAt?: number
  poster?: string | null
}
