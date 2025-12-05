const rawBase = import.meta.env.VITE_API_URL as string | undefined

function isLocalhost(url: string) {
  return /localhost|127\.0\.0\.1/i.test(url)
}

export function getApiBase() {
  if (rawBase && !isLocalhost(rawBase)) return rawBase
  return window.location.origin
}
