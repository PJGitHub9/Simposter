// Shared clipboard helper. `navigator.clipboard` is only defined in "secure contexts"
// (HTTPS, or localhost) — accessing it directly on a plain-HTTP LAN address (the normal
// way this self-hosted app is reached) throws "Cannot read properties of undefined
// (reading 'writeText')" before the copy even has a chance to fail gracefully. Falls back
// to the legacy `document.execCommand('copy')` approach via a temporary offscreen textarea,
// which works in insecure contexts. Returns true/false instead of throwing so callers can
// show their own error toast.
export async function copyToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // fall through to legacy method
    }
  }

  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.left = '-9999px'
    textarea.style.top = '-9999px'
    document.body.appendChild(textarea)
    textarea.focus()
    textarea.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(textarea)
    return ok
  } catch {
    return false
  }
}
