<script setup lang="ts">
import MovieCard from './MovieCard.vue'

type Entry = {
  title: string
  year?: number | string
  addedAt?: number
  status?: string
  poster?: string | null
  key: string
  edition?: string | null
  server_id?: string | null
  also_on?: string[] | null
  other_servers?: { server_id: string; rating_key: string }[] | null
}

const props = defineProps<{
  heading: string
  items: Entry[]
  cachedKeys?: Set<string>
  isTV?: boolean
}>()

// A card's own `.key` is whichever server currently "wins" the merged-grid
// dedup (Quirk #67/#74/#84 -- the preferred-server toggle changes which
// server's rating_key a merged item displays under). A resend cache entry
// is written per rating_key, not per tmdb_id -- so a poster rendered/sent
// back when the item only had a Plex rating_key still only has a cache
// entry under THAT rating_key, even after linking a Jellyfin server and
// switching "Show posters from" to prefer it. Checking only `item.key`
// against `cachedKeys` then misses a genuinely resendable render sitting
// under a sibling server's rating_key (`item.other_servers`) -- exactly
// what the multi-server resend picker (Quirk #76) already lets you target.
// User-reported directly: the resend arrow disappeared switching a merged
// library's preferred server from Plex to Jellyfin, even for items already
// sent to Plex.
//
// Resolves to the ACTUAL rating_key the cached bytes live under (home key,
// or whichever sibling's), not just whether one exists -- MovieCard needs
// this real key, not a boolean, because /api/render-cache/{rating_key}/resend
// and /preview both look the cache up by URL-path rating_key. Passing the
// currently-displayed (possibly cache-less) key there would 404 even though
// a cache genuinely exists under a sibling server's key.
function cacheSourceKey(item: Entry): string | null {
  if (!props.cachedKeys) return null
  if (props.cachedKeys.has(item.key)) return item.key
  const match = (item.other_servers || []).find(s => props.cachedKeys!.has(s.rating_key))
  return match ? match.rating_key : null
}

const emit = defineEmits<{
  (e: 'select', movie: Entry): void
  (e: 'refresh', key: string): void
  (e: 'resend-done', key: string): void
}>()
</script>

<template>
  <section class="grid-block">
    <div class="heading-row">
      <h2>{{ heading }}</h2>
      <p class="count">{{ items.length }} items</p>
    </div>
    <div class="grid">
      <MovieCard
        v-for="item in items"
        :key="item.key"
        :title="item.title"
        :year="item.year"
        :addedAt="item.addedAt"
        :poster="item.poster"
        :status="item.status"
        :ratingKey="item.key"
        :cacheRatingKey="cacheSourceKey(item)"
        :edition="item.edition"
        :hasCachedPoster="!!cacheSourceKey(item)"
        :isTV="isTV"
        :serverId="item.server_id"
        :alsoOn="item.also_on"
        :otherServers="item.other_servers"
        @select="emit('select', item)"
        @refresh="emit('refresh', item.key)"
        @resend-done="emit('resend-done', item.key)"
      />
    </div>
  </section>
</template>

<style scoped>
.grid-block {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.heading-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #d8e3ff;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

.heading-row h2 {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.3px;
}

.count {
  font-size: 13px;
  color: var(--muted);
  font-weight: 500;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 14px;
}

/* Mobile responsive styles */
@media (max-width: 900px) {
  .grid-block {
    gap: 12px;
  }

  .heading-row h2 {
    font-size: 18px;
  }

  .count {
    font-size: 12px;
  }

  .grid {
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 10px;
  }
}

@media (max-width: 600px) {
  .grid-block {
    gap: 10px;
  }

  .heading-row {
    padding-bottom: 6px;
  }

  .heading-row h2 {
    font-size: 16px;
  }

  .count {
    font-size: 11px;
  }

  .grid {
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 8px;
  }
}
</style>
