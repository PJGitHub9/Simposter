<script setup lang="ts">
// Small row of "open on the source site" links for the item currently being edited,
// shown under the title in EditorPane.vue/TvShowEditorPane.vue
//
// URL schemes (verified live, 2026-09-21, against Breaking Bad tmdb_id=1396/
// tvdb_id=81189 and The Matrix tmdb_id=603 -- Fanart.tv couldn't be verified the
// same way, it 403s automated fetches, but "https://fanart.tv/{movie|series}/{id}/"
// is the long-established community convention other Plex poster tools use, and
// matches the id kind (tmdb for movies, tvdb for TV) fanart_client.py's own API
// calls already use):
// - TMDb:      themoviedb.org/movie/{tmdb_id}  or  /tv/{tmdb_id}  or  /collection/{tmdb_id}
// - TVDB:      thetvdb.com/dereferrer/series/{tvdb_id}  (TV only -- movies/collections
//              in this app have no tracked TVDB id)
// - Fanart.tv: fanart.tv/movie/{tmdb_id}/  or  fanart.tv/series/{tvdb_id}/  (movies/TV
//              only -- Fanart.tv has no collection-level resource, see CLAUDE.md Quirk #21)
// - MediUX:    mediux.pro/movies/{tmdb_id}  or  /shows/{tmdb_id}  (movies/TV only --
//              no verified collection URL scheme, so not linked for those)
import { computed } from 'vue'

const props = defineProps<{
  mediaType: 'movie' | 'tv' | 'collection'
  tmdbId?: number | string | null
  tvdbId?: number | string | null
}>()

type LinkDef = { key: string; label: string; url: string; color: string }

const links = computed<LinkDef[]>(() => {
  const out: LinkDef[] = []
  const tmdb = props.tmdbId
  const tvdb = props.tvdbId
  const isTv = props.mediaType === 'tv'
  const isCollection = props.mediaType === 'collection'

  if (tmdb) {
    const segment = isCollection ? 'collection' : isTv ? 'tv' : 'movie'
    out.push({ key: 'tmdb', label: 'TMDB', color: '#01b4e4', url: `https://www.themoviedb.org/${segment}/${tmdb}` })
  }
  if (isCollection) return out
  if (isTv && tvdb) {
    out.push({ key: 'tvdb', label: 'TVDB', color: '#4bc178', url: `https://www.thetvdb.com/dereferrer/series/${tvdb}` })
  }
  if (isTv ? tvdb : tmdb) {
    out.push({ key: 'fanart', label: 'Fanart.tv', color: '#3ba8d1', url: isTv ? `https://fanart.tv/series/${tvdb}/` : `https://fanart.tv/movie/${tmdb}/` })
  }
  if (tmdb) {
    out.push({ key: 'mediux', label: 'MediUX', color: '#a855f7', url: `https://mediux.pro/${isTv ? 'shows' : 'movies'}/${tmdb}` })
  }
  return out
})
</script>

<template>
  <div v-if="links.length" class="external-links-row">
    <a
      v-for="l in links"
      :key="l.key"
      :href="l.url"
      target="_blank"
      rel="noopener noreferrer"
      class="external-link-pill"
      :title="`Open on ${l.label}`"
    >
      <span class="external-link-dot" :style="{ background: l.color }" />
      {{ l.label }}
    </a>
  </div>
</template>

<style scoped>
.external-links-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}

.external-link-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #c9d1e0;
  font-size: 11px;
  font-weight: 600;
  text-decoration: none;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
  white-space: nowrap;
}

.external-link-pill:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.22);
  color: #eef2ff;
}

.external-link-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
