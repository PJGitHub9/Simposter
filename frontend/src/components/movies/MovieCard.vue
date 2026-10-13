<script setup lang="ts">
import { computed, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'
import ResendPreviewModal from './ResendPreviewModal.vue'

const props = defineProps<{
  title: string
  year?: string | number
  addedAt?: number
  poster?: string | null
  status?: string
  ratingKey?: string
  // The rating_key the cached render bytes actually live under, resolved by
  // MovieGrid.vue -- may differ from `ratingKey` (the currently-displayed
  // server's key) once a merged item's preferred-server toggle no longer
  // matches whichever server the poster was originally rendered/sent under.
  // Falls back to `ratingKey` itself when unset (every pre-multi-server
  // card, where the two are always the same value anyway).
  cacheRatingKey?: string | null
  edition?: string | null
  hasCachedPoster?: boolean
  isTV?: boolean
  serverId?: string | null
  alsoOn?: string[] | null
  otherServers?: { server_id: string; rating_key: string }[] | null
}>()

// This card's own server plus every other linked server (Quirk #75's
// {server_id, rating_key} pairs) -- what the resend picker offers, and what
// doResend() below maps a picker selection back to an actual rating_key for.
const linkedServers = computed(() => {
  const home = { server_id: props.serverId || 'plex-1', rating_key: props.ratingKey || '' }
  return [home, ...(props.otherServers || [])]
})

// Server ids are always "{type}-{...}" (see MediaServersTab.vue's addServer()),
// so the type is derivable without needing the full mediaServers list passed
// down through the grid -- 'plex-1' is the only id that doesn't follow a
// "-<timestamp>" shape, still splits to "plex" correctly either way.
function serverTypeFor(id: string): string {
  return id.split('-')[0] || id
}

// Always includes the card's own server (Plex included) plus every server
// the same title was also found on (Quirk #67's `alsoOn`) -- previously only
// showed a badge for a NON-Plex server, which meant a plain Plex-only card
// showed nothing at all and a merged card only showed the "other" server,
// never confirming Plex was also one of them. The user's own reasoning:
// "this could be because there could be an item thats in jellyfin only, or
// plex only. the icons really help distinguish it" -- so every card now
// always shows at least one icon, identifying every server it actually
// lives on, not just the non-default ones.
const serverBadges = computed(() => {
  const badges: string[] = [serverTypeFor(props.serverId || 'plex-1')]
  for (const id of props.alsoOn || []) badges.push(serverTypeFor(id))
  return [...new Set(badges)]
})

function displayServerLabel(type: string): string {
  return type === 'jellyfin' ? 'Jellyfin' : type === 'emby' ? 'Emby' : type === 'plex' ? 'Plex' : type
}

// Real official brand marks (simple-icons, MIT-licensed for exactly this kind
// of identification use), not hand-drawn approximations -- static files under
// frontend/public/icons/, colored to each brand's own accent at fetch time
// (see the icons/ files themselves), served like any other frontend/public
// asset (Quirk #39's fix already makes the built app serve these correctly).
function serverIconSrc(type: string): string {
  return `/icons/${type}.svg`
}

const emit = defineEmits<{
  (e: 'select'): void
  (e: 'refresh'): void
  (e: 'resend-done', ratingKey: string): void
}>()

type ResendState = 'idle' | 'previewing' | 'loading' | 'done' | 'error'
const resendState = ref<ResendState>('idle')

function onResendClick(e: MouseEvent) {
  e.stopPropagation()
  resendState.value = 'previewing'
}

function cancelPreview() {
  resendState.value = 'idle'
}

async function doResend(includeSeasons: boolean, targetServerIds: string[]) {
  if (!props.ratingKey) return
  resendState.value = 'loading'
  try {
    const apiBase = getApiBase()
    // Map the modal's selected server_ids back to {server_id, rating_key}
    // targets -- omitted (undefined) whenever nothing was explicitly picked
    // (the single-server, non-linked case), so the backend falls through to
    // its own default (resend to whichever server this rating_key actually
    // belongs to) rather than sending an empty targets list.
    const targets = targetServerIds.length
      ? linkedServers.value.filter(s => targetServerIds.includes(s.server_id))
      : undefined
    // /resend looks the cached bytes up by the URL-path rating_key -- must be
    // whichever key the cache actually lives under (cacheRatingKey), not
    // necessarily this card's currently-displayed ratingKey (see MovieGrid.vue's
    // cacheSourceKey()). Falls back to ratingKey for any pre-multi-server card,
    // where the two are always identical.
    const cacheKey = props.cacheRatingKey || props.ratingKey
    const res = await fetch(`${apiBase}/api/render-cache/${cacheKey}/resend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ include_seasons: includeSeasons, is_tv: props.isTV ?? false, targets }),
    })
    if (!res.ok) throw new Error(await res.text())
    resendState.value = 'done'
    emit('resend-done', props.ratingKey)
    setTimeout(() => { resendState.value = 'idle' }, 2500)
  } catch {
    resendState.value = 'error'
    setTimeout(() => { resendState.value = 'idle' }, 2500)
  }
}
</script>

<template>
  <article class="card glass" @click="emit('select')">
    <div class="thumb" :style="{ backgroundImage: `url(${poster})` }">
      <button class="refresh-btn" title="Refresh poster" @click.stop="emit('refresh')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="23 4 23 10 17 10" />
          <polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
      </button>

      <!-- Resend button (only when cached poster exists) -->
      <button
        v-if="hasCachedPoster && resendState === 'idle'"
        class="resend-btn"
        title="Resend previously generated poster to Plex"
        @click.stop="onResendClick($event)"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>

      <!-- Loading state -->
      <div v-if="resendState === 'loading'" class="resend-feedback" @click.stop>
        <svg class="spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 12a9 9 0 1 1-6.219-8.56" />
        </svg>
      </div>

      <!-- Done state -->
      <div v-if="resendState === 'done'" class="resend-feedback done" @click.stop>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>

      <!-- Error state -->
      <div v-if="resendState === 'error'" class="resend-feedback error" @click.stop>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </div>
    </div>
    <div class="meta">
      <p class="title">{{ title }}</p>
      <p class="edition" :class="{ 'edition-empty': !edition }">{{ edition || ' ' }}</p>
      <div class="meta-row">
        <p class="muted">{{ year }}</p>
        <div v-if="serverBadges.length" class="server-icons" :title="`Also on: ${serverBadges.map(displayServerLabel).join(', ')}`">
          <img
            v-for="s in serverBadges"
            :key="s"
            :src="serverIconSrc(s)"
            :alt="displayServerLabel(s)"
            :title="displayServerLabel(s)"
            class="server-icon"
          />
        </div>
      </div>
    </div>
  </article>

  <!-- Teleported to <body> so the modal isn't clipped/mispositioned by the card's
       hover transform (a transformed ancestor creates a new containing block for
       position:fixed descendants). -->
  <Teleport to="body">
    <ResendPreviewModal
      :is-open="resendState === 'previewing'"
      :rating-key="ratingKey || ''"
      :cache-rating-key="cacheRatingKey"
      :title="title"
      :is-tv="isTV ?? false"
      :linked-servers="linkedServers"
      @close="cancelPreview"
      @confirm="doResend"
    />
  </Teleport>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  cursor: pointer;
  transition: all 0.2s ease;
}

.card:hover {
  transform: translateY(-2px);
  border-color: rgba(61, 214, 183, 0.35);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
}

.thumb {
  aspect-ratio: 2 / 3;
  border-radius: 10px;
  background-size: cover;
  background-position: center;
  background-image: linear-gradient(180deg, rgba(61, 214, 183, 0.15), rgba(91, 141, 238, 0.25)),
    linear-gradient(160deg, rgba(255, 255, 255, 0.03), rgba(0, 0, 0, 0.4));
  position: relative;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

/* --- server icons (below the poster, next to the year) -- deliberately NOT
   an overlay on the thumb anymore (see CLAUDE.md's multi-server Quirks):
   the user asked for identification without blocking the artwork, so this
   sits in the text metadata row instead of on top of the image. Real
   official brand marks (frontend/public/icons/, simple-icons-sourced --
   see serverIconSrc() above), not hand-drawn shapes. --- */
.meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.server-icons {
  display: flex;
  align-items: center;
  gap: 5px;
}

.server-icon {
  display: block;
  width: 13px;
  height: 13px;
}

/* --- refresh button (top-right) --- */
.refresh-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 6px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(8px);
  color: #d7e6ff;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid rgba(255, 255, 255, 0.12);
  opacity: 0;
  transform: translateY(-6px);
  transition: all 0.18s ease;
  cursor: pointer;
}

.refresh-btn:hover {
  background: rgba(61, 214, 183, 0.18);
  color: #3dd6b7;
  border-color: rgba(61, 214, 183, 0.5);
}

.card:hover .refresh-btn {
  opacity: 1;
  transform: translateY(0);
}

/* --- resend button (bottom-left) --- */
.resend-btn {
  position: absolute;
  bottom: 8px;
  left: 8px;
  padding: 6px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(8px);
  color: #d7e6ff;
  border: 1px solid rgba(255, 255, 255, 0.12);
  opacity: 0;
  transform: translateY(6px);
  transition: all 0.18s ease;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.resend-btn:hover {
  background: rgba(91, 141, 238, 0.25);
  color: #8ab4f8;
  border-color: rgba(91, 141, 238, 0.5);
}

.card:hover .resend-btn {
  opacity: 1;
  transform: translateY(0);
}

/* --- loading/done/error feedback --- */
.resend-feedback {
  position: absolute;
  bottom: 8px;
  left: 8px;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(6px);
  border: 1px solid rgba(255, 255, 255, 0.12);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #d7e6ff;
}

.resend-feedback.done {
  background: rgba(61, 214, 183, 0.2);
  border-color: rgba(61, 214, 183, 0.5);
  color: #3dd6b7;
}

.resend-feedback.error {
  background: rgba(255, 107, 107, 0.2);
  border-color: rgba(255, 107, 107, 0.5);
  color: #ff6b6b;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.spin {
  animation: spin 0.8s linear infinite;
}

.meta .title {
  font-weight: 600;
  font-size: 14px;
  color: #eef2ff;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  /* Always reserves 2 lines' worth of height, even for a 1-line title --
     otherwise a shorter title left .meta-row (year + server icons) sitting
     at a different vertical offset card-to-card, which is exactly what the
     user flagged as icons looking misaligned across the grid. */
  min-height: calc(1.3em * 2);
}

.edition {
  color: var(--muted);
  font-size: 11px;
  font-weight: 400;
  font-style: italic;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  /* Always rendered (a non-breaking space when there's no real edition, see
     the template) so this line's height is reserved on every card -- same
     alignment reasoning as .title's min-height above. */
  line-height: 1.4;
}

.edition-empty {
  visibility: hidden;
}

.muted {
  color: var(--muted);
  font-size: 12px;
  font-weight: 500;
}

/* Mobile responsive styles */
@media (max-width: 900px) {
  .card {
    gap: 8px;
    padding: 8px;
    border-radius: 10px;
  }

  .thumb {
    border-radius: 8px;
  }

  .refresh-btn {
    opacity: 1;
    transform: translateY(0);
    top: 6px;
    right: 6px;
    padding: 5px;
    border-radius: 6px;
  }

  .resend-btn {
    opacity: 1;
    transform: translateY(0);
    bottom: 6px;
    left: 6px;
    padding: 5px;
    border-radius: 6px;
  }

  .meta .title {
    font-size: 13px;
  }

  .muted {
    font-size: 11px;
  }
}

@media (max-width: 600px) {
  .card {
    gap: 6px;
    padding: 6px;
    border-radius: 8px;
  }

  .card:hover {
    transform: none;
  }

  .thumb {
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
  }

  .refresh-btn {
    top: 4px;
    right: 4px;
    padding: 4px;
    border-radius: 4px;
  }

  .refresh-btn svg {
    width: 12px;
    height: 12px;
  }

  .resend-btn {
    bottom: 4px;
    left: 4px;
    padding: 4px;
    border-radius: 4px;
  }

  .resend-btn svg {
    width: 11px;
    height: 11px;
  }

  .meta .title {
    font-size: 11px;
    -webkit-line-clamp: 1;
  }

  .muted {
    font-size: 10px;
  }
}
</style>
