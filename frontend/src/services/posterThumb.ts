// Grid tiles load a small copy of a cached poster (`thumb=1`) instead of the
// full-size file: a poster Simposter sent is a 2000x3000 render of several MB.
// Only Simposter's own poster URLs get it; anything else is returned as is.
const POSTER_PATH = /\/api\/(movie|tv-show)\/[^/?]+\/poster(\?|$)/

export function posterThumbUrl(url?: string | null): string | null | undefined {
  if (!url || !POSTER_PATH.test(url) || /[?&]thumb=1/.test(url)) return url
  return url + (url.includes('?') ? '&' : '?') + 'thumb=1'
}
