// Same rule as backend/config.py's same_origin(): a saved API key or token is
// only ever used for the address it was saved with. Keep the two in step.

export const SECRET_MASK = '********'

const DEFAULT_PORTS: Record<string, string> = { http: '80', https: '443' }

export function urlOrigin(url: string | null | undefined): string {
  let s = String(url ?? '').trim()
  if (!s) return ''
  if (!s.includes('://')) s = 'http://' + s
  try {
    const u = new URL(s)
    const scheme = u.protocol.replace(':', '').toLowerCase()
    const port = u.port || DEFAULT_PORTS[scheme] || ''
    return `${scheme}://${u.hostname.toLowerCase()}:${port}`
  } catch {
    return s.toLowerCase()
  }
}

export function sameOrigin(a: string | null | undefined, b: string | null | undefined): boolean {
  return urlOrigin(a) === urlOrigin(b)
}

/** The key field still shows the saved (masked) key, but the address now points
 *  somewhere else, so the saved key won't be used: it has to be typed again. */
export function keyNeedsReentry(url: string | null | undefined, key: string | null | undefined,
                                savedUrl: string | null | undefined): boolean {
  return key === SECRET_MASK && !sameOrigin(url, savedUrl)
}
