const rawBase = import.meta.env.VITE_API_URL as string | undefined

export function getApiBase() {
  // If explicitly provided, always use it
  if (rawBase) return rawBase
  // Default to same origin as the served UI
  return window.location.origin
}
