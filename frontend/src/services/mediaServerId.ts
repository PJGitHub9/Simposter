// Stable, deterministic id generation for a new mediaServers entry -- shared
// between MediaServersTab.vue and OnboardingModal.vue's "add a media server"
// step so both can never drift into two subtly different id schemes.
//
// Deliberately NOT Date.now()-based (that was the original v1.6.114 design,
// and caused a real bug: removing and re-adding the same server issued a new
// id every time, silently orphaning any LibraryGroup link that referenced the
// old one -- see CLAUDE.md Quirk #70). Hashing the normalized URL instead
// means the same server always gets the same id, so a remove+re-add of the
// same URL is a no-op for anything that referenced it.
export function stableIdSuffix(text: string): string {
  let hash = 0x811c9dc5
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return (hash >>> 0).toString(16)
}

export function normalizedUrlForId(url: string): string {
  return url.trim().toLowerCase().replace(/\/+$/, '')
}

export function mediaServerId(type: string, url: string): string {
  return `${type}-${stableIdSuffix(normalizedUrlForId(url))}`
}
