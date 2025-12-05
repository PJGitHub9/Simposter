const rawBase = import.meta.env.VITE_API_URL as string | undefined

function isLocalhost(url: string) {
  return /localhost|127\.0\.0\.1/i.test(url)
}

export function getApiBase() {
  // If VITE_API_URL is set and not pointing to localhost, use it. Otherwise, use current origin.
  if (rawBase && !isLocalhost(rawBase)) return rawBase
  return window.location.origin
}
