const rawBase = import.meta.env.VITE_API_URL as string | undefined

function isLocalhost(url: string) {
  return /localhost|127\.0\.0\.1/i.test(url)
}

export function getApiBase() {
  // In development, always use the backend port directly to bypass Vite proxy issues
  if (import.meta.env.DEV) {
    return 'http://localhost:8003'
  }
  
  // If VITE_API_URL is set and not pointing to localhost, use it. Otherwise, use current origin.
  if (rawBase && !isLocalhost(rawBase)) return rawBase
  return window.location.origin
}
