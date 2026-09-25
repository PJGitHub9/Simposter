<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore } from '@/stores/settings'
import { mediaServerLabel } from '@/services/mediaServerLabel'

type LinkedServer = { server_id: string; rating_key: string }

const props = defineProps<{
  isOpen: boolean
  ratingKey: string
  // The rating_key the cached render bytes actually live under -- may differ
  // from `ratingKey` (the card's currently-displayed server) once a merged
  // item's preferred-server toggle no longer matches whichever server the
  // poster was originally rendered/sent under (see MovieGrid.vue's
  // cacheSourceKey()). Only used for the "Saved poster" preview fetch below;
  // falls back to `ratingKey` when unset, matching every pre-multi-server card.
  cacheRatingKey?: string | null
  title: string
  isTv: boolean
  // Every server this item is linked to (its own home server first, then
  // any others from Movie.other_servers -- Quirk #75) -- lets this modal
  // offer a per-server "send to..." picker instead of always resending to
  // whichever single server the card happens to be sourced from.
  linkedServers?: LinkedServer[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'confirm', includeSeasons: boolean, targetServerIds: string[]): void
}>()

const apiBase = getApiBase()
const settings = useSettingsStore()

const hasMultipleServers = computed(() => (props.linkedServers?.length || 0) > 1)

function serverTypeLabel(serverId: string): string {
  return mediaServerLabel(serverId, settings.mediaServers.value)
}

// Defaults to just the item's own home server -- reproducing this modal's
// pre-multi-server behavior exactly (resend to wherever this card is
// actually from) for anyone who doesn't touch the picker.
const selectedTargets = ref<Set<string>>(new Set())
watch(() => props.isOpen, (open) => {
  if (open) {
    selectedTargets.value = new Set(props.linkedServers?.[0] ? [props.linkedServers[0].server_id] : [])
  }
})
function toggleTarget(serverId: string) {
  const next = new Set(selectedTargets.value)
  if (next.has(serverId)) next.delete(serverId)
  else next.add(serverId)
  selectedTargets.value = next
}

// Which linked server's "Current in ..." column is shown -- a separate
// concept from `selectedTargets` above (you can preview one server's live
// poster while sending to a different set, or all of them). Defaults to the
// item's own home server, matching this modal's pre-multi-server behavior
// exactly when there's nothing else to toggle to.
const viewingServerId = ref('')
watch(() => props.isOpen, (open) => {
  if (open) {
    viewingServerId.value = props.linkedServers?.[0]?.server_id || 'plex-1'
  }
})
function cycleViewingServer(direction: 1 | -1) {
  const ids = (props.linkedServers || []).map(s => s.server_id)
  if (ids.length < 2) return
  const idx = ids.indexOf(viewingServerId.value)
  viewingServerId.value = ids[(idx + direction + ids.length) % ids.length]!
}
const viewingRatingKey = computed(() =>
  props.linkedServers?.find(s => s.server_id === viewingServerId.value)?.rating_key || props.ratingKey
)

const savedImageUrl = computed(() => {
  const key = props.cacheRatingKey || props.ratingKey
  if (!key) return ''
  return `${apiBase}/api/render-cache/${key}/preview?is_tv=${props.isTv}&v=${cacheBust.value}`
})

const currentImageUrl = computed(() => {
  if (!viewingRatingKey.value) return ''
  const path = props.isTv ? 'tv-show' : 'movie'
  return `${apiBase}/api/${path}/${viewingRatingKey.value}/poster?v=${cacheBust.value}`
})
const currentImageLabel = computed(() => `Current in ${serverTypeLabel(viewingServerId.value)}`)

// Bump on open so re-opening for a different card doesn't show a stale cached image.
const cacheBust = ref(0)
const savedImageError = ref(false)
const currentImageError = ref(false)

watch(() => props.isOpen, (open) => {
  if (open) {
    cacheBust.value = Date.now()
    savedImageError.value = false
    currentImageError.value = false
  }
})
// Switching which server's "current" state is previewed re-checks that
// server's own image, independent of the cache-bust timestamp above.
watch(viewingServerId, () => {
  currentImageError.value = false
})

const close = () => emit('close')
const confirm = (includeSeasons: boolean) => emit('confirm', includeSeasons, Array.from(selectedTargets.value))
</script>

<template>
  <div v-if="isOpen" class="modal-overlay" @click.self="close">
    <div class="modal-content">
      <div class="modal-header">
        <h2>Resend saved poster?</h2>
        <button class="close-btn" @click="close">✕</button>
      </div>

      <div class="modal-body">
        <p class="subtitle">{{ title }}</p>

        <div v-if="hasMultipleServers" class="target-picker">
          <span class="target-picker-label">Send to:</span>
          <label v-for="s in linkedServers" :key="s.server_id" class="target-checkbox">
            <input
              type="checkbox"
              :checked="selectedTargets.has(s.server_id)"
              @change="toggleTarget(s.server_id)"
            />
            {{ serverTypeLabel(s.server_id) }}
          </label>
        </div>

        <div class="compare-row">
          <div class="compare-col">
            <span class="compare-label">Saved poster</span>
            <div class="compare-frame">
              <img
                v-if="!savedImageError"
                :src="savedImageUrl"
                alt="Saved poster"
                @error="savedImageError = true"
              />
              <div v-else class="compare-fallback">No saved poster found</div>
            </div>
          </div>
          <div class="compare-arrow">→</div>
          <div class="compare-col">
            <div class="compare-label-row">
              <button v-if="hasMultipleServers" class="server-toggle-btn" title="Previous server" @click="cycleViewingServer(-1)">‹</button>
              <span class="compare-label">{{ currentImageLabel }}</span>
              <button v-if="hasMultipleServers" class="server-toggle-btn" title="Next server" @click="cycleViewingServer(1)">›</button>
            </div>
            <div class="compare-frame">
              <img
                v-if="!currentImageError"
                :key="viewingServerId"
                :src="currentImageUrl"
                alt="Current poster"
                @error="currentImageError = true"
              />
              <div v-else class="compare-fallback">No current poster found</div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-actions">
        <button class="btn-secondary" @click="close">Cancel</button>
        <button v-if="isTv" class="btn-secondary" :disabled="hasMultipleServers && selectedTargets.size === 0" @click="confirm(false)">Show only</button>
        <button class="btn-primary" :disabled="hasMultipleServers && selectedTargets.size === 0" @click="confirm(isTv)">
          {{ isTv ? 'Resend + Seasons' : 'Resend' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--surface, #1a1f2e);
  border-radius: 8px;
  max-width: 560px;
  width: 92%;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--border, #2a2f3e);
}

.modal-header h2 {
  margin: 0;
  color: var(--text-primary, #fff);
  font-size: 1.25rem;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.25rem;
  color: var(--text-secondary, #aaa);
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.08);
}

.modal-body {
  padding: 1.25rem 1.5rem;
}

.subtitle {
  margin: 0 0 1rem 0;
  color: var(--text-secondary, #aaa);
  font-size: 0.9rem;
  font-weight: 600;
}

.target-picker {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 10px;
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.03);
}
.target-picker-label {
  font-size: 0.8rem;
  color: var(--text-secondary, #aaa);
  font-weight: 600;
}
.target-checkbox {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.8rem;
  color: var(--text-secondary, #c8d4f0);
  cursor: pointer;
}

.compare-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.compare-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.compare-label {
  font-size: 0.75rem;
  color: var(--text-secondary, #aaa);
  text-align: center;
}

.compare-label-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.server-toggle-btn {
  width: 18px;
  height: 18px;
  border-radius: 5px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-secondary, #c8d4f0);
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  flex-shrink: 0;
}
.server-toggle-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

.compare-frame {
  aspect-ratio: 2 / 3;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border, #2a2f3e);
  display: flex;
  align-items: center;
  justify-content: center;
}

.compare-frame img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.compare-fallback {
  font-size: 0.75rem;
  color: var(--text-secondary, #aaa);
  text-align: center;
  padding: 0 8px;
}

.compare-arrow {
  font-size: 1.25rem;
  color: var(--text-secondary, #aaa);
  flex-shrink: 0;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 1rem 1.5rem 1.25rem;
  border-top: 1px solid var(--border, #2a2f3e);
}

.btn-primary,
.btn-secondary {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: var(--text-secondary, #c8d4f0);
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.12);
}

.btn-primary {
  background: rgba(91, 141, 238, 0.25);
  border: 1px solid rgba(91, 141, 238, 0.5);
  color: #8ab4f8;
}

.btn-primary:hover {
  background: rgba(91, 141, 238, 0.4);
}

@media (max-width: 600px) {
  .modal-content {
    width: 96%;
  }

  .compare-row {
    gap: 6px;
  }

  .compare-arrow {
    font-size: 1rem;
  }
}
</style>
