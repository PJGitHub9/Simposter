import { ref } from 'vue'
import type { MovieInput, PresetOptions } from './types'

const apiBase = import.meta.env.VITE_API_URL || window.location.origin

export function useRenderService() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastPreview = ref<string | null>(null)

  const post = async (path: string, body: any) => {
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
    } catch (e: any) {
      error.value = e?.message || `Request to ${path} failed`
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
    presetId?: string
  ) => {
    const payload = basePayload(movie, bgUrl, logoUrl, templateId, presetId, options)
    const data = await post('preview', payload)
    if (data?.image_base64) {
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
    presetId?: string
  ) => {
    const payload = {
      ...basePayload(movie, bgUrl, logoUrl, templateId, presetId, options),
      movie_title: movie.title,
      movie_year: movie.year ?? null,
      filename: 'poster.jpg'
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
    const payload: any = {
      ...basePayload(movie, bgUrl, logoUrl, templateId, presetId, options),
      rating_key: movie.key,
      send_to_plex: true
    }
    if (labels?.length) {
      payload.labels = labels
    }
    return post('plex/send', payload)
  }

  return { loading, error, lastPreview, preview, save, send }
}
