/**
 * SessionStorage utility with LRU cache eviction
 * Prevents QuotaExceededError by managing cache size
 */

const CACHE_KEY_PREFIX = 'simposter-'
const MAX_CACHE_SIZE_MB = 4 // Leave 1MB buffer (browsers typically limit to 5-10MB)
const MAX_CACHE_SIZE_BYTES = MAX_CACHE_SIZE_MB * 1024 * 1024

interface CacheMetadata {
  key: string
  size: number
  lastAccessed: number
}

/**
 * Get approximate size of sessionStorage usage
 */
function getStorageSize(): number {
  let totalSize = 0
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i)
    if (key) {
      const value = sessionStorage.getItem(key)
      if (value) {
        // Approximate: 2 bytes per character (UTF-16)
        totalSize += (key.length + value.length) * 2
      }
    }
  }
  return totalSize
}

/**
 * Get all cache keys with metadata
 */
function getCacheMetadata(): CacheMetadata[] {
  const metadata: CacheMetadata[] = []
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i)
    if (key && key.startsWith(CACHE_KEY_PREFIX)) {
      const value = sessionStorage.getItem(key)
      if (value) {
        const size = (key.length + value.length) * 2
        // Try to parse metadata from value if it exists
        try {
          const parsed = JSON.parse(value)
          const lastAccessed = parsed._lastAccessed || Date.now()
          metadata.push({ key, size, lastAccessed })
        } catch {
          // If not JSON, use current time
          metadata.push({ key, size, lastAccessed: Date.now() })
        }
      }
    }
  }
  return metadata
}

/**
 * Evict least recently used items until size is under limit
 */
function evictLRU(targetSize: number = MAX_CACHE_SIZE_BYTES) {
  let currentSize = getStorageSize()
  if (currentSize <= targetSize) return

  const metadata = getCacheMetadata()
  // Sort by lastAccessed ascending (oldest first)
  metadata.sort((a, b) => a.lastAccessed - b.lastAccessed)

  let evicted = 0
  for (const item of metadata) {
    if (currentSize <= targetSize) break
    try {
      sessionStorage.removeItem(item.key)
      currentSize -= item.size
      evicted++
    } catch (e) {
      console.warn(`[Cache] Failed to evict ${item.key}:`, e)
    }
  }

  if (evicted > 0) {
    console.log(`[Cache] Evicted ${evicted} items, freed ${((getStorageSize() / 1024 / 1024).toFixed(2))}MB`)
  }
}

/**
 * Safe setItem with LRU eviction
 */
export function setSessionStorage(key: string, value: any): boolean {
  const fullKey = key.startsWith(CACHE_KEY_PREFIX) ? key : `${CACHE_KEY_PREFIX}${key}`

  try {
    // Add metadata for LRU tracking
    const wrappedValue = {
      _lastAccessed: Date.now(),
      data: value
    }
    const serialized = JSON.stringify(wrappedValue)

    // Check if this would exceed quota
    const itemSize = (fullKey.length + serialized.length) * 2
    const currentSize = getStorageSize()

    if (currentSize + itemSize > MAX_CACHE_SIZE_BYTES) {
      // Evict old items to make room
      evictLRU(MAX_CACHE_SIZE_BYTES - itemSize)
    }

    sessionStorage.setItem(fullKey, serialized)
    return true
  } catch (e) {
    if (e instanceof DOMException && e.name === 'QuotaExceededError') {
      console.warn(`[Cache] Quota exceeded for ${fullKey}, attempting eviction`)
      // Aggressive eviction: free up 50% of cache
      evictLRU(MAX_CACHE_SIZE_BYTES * 0.5)

      try {
        // Retry after eviction
        const wrappedValue = { _lastAccessed: Date.now(), data: value }
        sessionStorage.setItem(fullKey, JSON.stringify(wrappedValue))
        return true
      } catch (retryError) {
        console.error(`[Cache] Failed to cache ${fullKey} even after eviction`, retryError)
        return false
      }
    }
    console.error(`[Cache] Failed to cache ${fullKey}:`, e)
    return false
  }
}

/**
 * Safe getItem with access time tracking
 */
export function getSessionStorage<T = any>(key: string): T | null {
  const fullKey = key.startsWith(CACHE_KEY_PREFIX) ? key : `${CACHE_KEY_PREFIX}${key}`

  try {
    const value = sessionStorage.getItem(fullKey)
    if (!value) return null

    const parsed = JSON.parse(value)

    // Update last accessed time
    if (parsed._lastAccessed !== undefined) {
      parsed._lastAccessed = Date.now()
      try {
        sessionStorage.setItem(fullKey, JSON.stringify(parsed))
      } catch {
        // Ignore update errors
      }
      return parsed.data as T
    }

    // Legacy data without metadata
    return parsed as T
  } catch (e) {
    console.warn(`[Cache] Failed to read ${fullKey}:`, e)
    return null
  }
}

/**
 * Clear all Simposter cache items
 */
export function clearCache() {
  const keys = []
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i)
    if (key && key.startsWith(CACHE_KEY_PREFIX)) {
      keys.push(key)
    }
  }

  keys.forEach(key => {
    try {
      sessionStorage.removeItem(key)
    } catch (e) {
      console.warn(`[Cache] Failed to clear ${key}:`, e)
    }
  })

  console.log(`[Cache] Cleared ${keys.length} cache items`)
}

/**
 * Get cache statistics
 */
export function getCacheStats() {
  const metadata = getCacheMetadata()
  const totalSize = metadata.reduce((sum, item) => sum + item.size, 0)

  return {
    itemCount: metadata.length,
    totalSizeMB: (totalSize / 1024 / 1024).toFixed(2),
    maxSizeMB: MAX_CACHE_SIZE_MB,
    utilizationPercent: ((totalSize / MAX_CACHE_SIZE_BYTES) * 100).toFixed(1),
    oldestItem: metadata.length > 0
      ? new Date(Math.min(...metadata.map(m => m.lastAccessed))).toISOString()
      : null
  }
}
