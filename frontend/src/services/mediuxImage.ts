// MediUX images need the MediUX key, which the browser doesn't have, so <img>
// tags load them through Simposter's proxy (/api/mediux/image). The original
// images.mediux.io URL is still what gets sent to /api/preview and saved.
import { getApiBase } from './apiBase'

const MEDIUX_ASSET = /^https:\/\/images\.mediux\.io\/assets\/([A-Za-z0-9-]+)\?v=(\d+)/

export type MediuxSize = 'thumb' | 'jpg' | 'original'

export function mediuxDisplayUrl<T extends string | null | undefined>(url: T, size: MediuxSize = 'jpg'): T | string {
  const m = MEDIUX_ASSET.exec(url || '')
  if (!m) return url
  return `${getApiBase()}/api/mediux/image?asset=${m[1]}&v=${m[2]}&size=${size}`
}

/** Thumbnail src for a candidate: MediUX through the proxy, anything else unchanged. */
export function candidateThumb(img: { url: string; thumb?: string; source?: string }): string {
  if ((img.source || '').toLowerCase() === 'mediux') return mediuxDisplayUrl(img.url, 'thumb')
  return img.thumb || img.url
}
