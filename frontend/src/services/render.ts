import { ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import type { MovieInput, PresetOptions } from './types'
import { getApiBase } from './apiBase'

const apiBase = getApiBase()

export function useRenderService() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastPreview = ref<string | null>(null)
  const settings = useSettingsStore()

  const post = async (path: string, body: unknown) => {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(`${apiBase}/api/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`API ${path} failed (${res.status}): ${text || res.statusText}`)
      }
      return await res.json()
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : `Request to ${path} failed`
      error.value = message
      return null
    } finally {
      loading.value = false
    }
  }

  const basePayload = (
    movie: MovieInput,
    bgUrl: string,
    logoUrl?: string | null,
    templateId?: string,
    presetId?: string,
    options?: PresetOptions
  ) => ({
    template_id: templateId || 'default',
    preset_id: presetId || 'default',
    background_url: bgUrl,
    logo_url: logoUrl || null,
    movie_title: movie.title,
    movie_year: movie.year ?? null,
    options: options ?? undefined
  })

  const preview = async (
    movie: MovieInput,
    bgUrl: string,
    logoUrl?: string | null,
    options?: PresetOptions,
    templateId?: string,
    presetId?: string,
    disableCache?: boolean,
    skipLastPreviewUpdate?: boolean
  ) => {
    const payload = basePayload(movie, bgUrl, logoUrl, templateId, presetId, options)
    // Allow overlay caching by default for better performance
    const disableOverlayCache = disableCache ?? false
    const data = await post('preview', {
      ...payload,
      // Only disable when explicitly requested
      disableOverlayCache
    })
    if (data?.image_base64 && !skipLastPreviewUpdate) {
      lastPreview.value = `data:image/jpeg;base64,${data.image_base64}`
    }
    return data
  }

  const save = async (
    movie: MovieInput,
    bgUrl: string,
    logoUrl?: string | null,
    options?: PresetOptions,
    templateId?: string,
    presetId?: string,
    libraryId?: string | null,
    seasonIndex?: number | null
  ) => {
    const payload = {
      ...basePayload(movie, bgUrl, logoUrl, templateId, presetId, options),
      movie_title: movie.title,
      movie_year: movie.year ?? null,
      filename: 'poster.jpg',
      library_id: libraryId ?? null,
      is_tv: movie.mediaType === 'tv-show',
      season_index: seasonIndex ?? null,
      rating_key: movie.key
    }
    return post('save', payload)
  }

  const send = async (
    movie: MovieInput,
    bgUrl: string,
    logoUrl?: string | null,
    options?: PresetOptions,
    labels?: string[],
    templateId?: string,
    presetId?: string
  ) => {
    const payload: Record<string, unknown> = {
      ...basePayload(movie, bgUrl, logoUrl, templateId, presetId, options),
      rating_key: movie.key,
      send_to_plex: true,
      library_id: movie.library_id ?? null
    }
    if (labels?.length) {
      payload.labels = labels
    }
    return post('plex/send', payload)
  }

  return { loading, error, lastPreview, preview, save, send }
}
