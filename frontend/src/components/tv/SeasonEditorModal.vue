<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import SeasonSelector from './SeasonSelector.vue'
import SeasonImageSelector, { type SeasonImage } from './SeasonImageSelector.vue'
import { getApiBase } from '@/services/apiBase'

export interface Season {
  key: string
  title: string
  index: number
  thumb?: string
}

interface Props {
  show: {
    key: string
    title: string
    tmdb_id?: number
    tvdb_id?: number
  }
  isOpen: boolean
}

interface Emits {
  (e: 'close'): void
  (e: 'uploaded', seasonKey: string): void
}

defineProps<Props>()
defineEmits<Emits>()

const mode = ref<'seasons' | 'images'>('seasons')
const seasons = ref<Season[]>([])
const loadingSeasons = ref(false)
const selectedSeason = ref<Season | null>(null)

const emit = defineEmits<Emits>()

const loadSeasons = async () => {
  loadingSeasons.value = true
  try {
    const res = await fetch(`${getApiBase()}/api/tv-show/${props.show.key}/seasons`)
    if (!res.ok) throw new Error('Failed to load seasons')
    const data = await res.json()
    seasons.value = data.seasons || []
  } catch (err) {
    console.error('Failed to load seasons:', err)
    seasons.value = []
  } finally {
    loadingSeasons.value = false
  }
}

onMounted(() => {
  if (props.isOpen) {
    loadSeasons()
  }
})

const handleSeasonSelect = (seasonKey: string, seasonIndex: number) => {
  const season = seasons.value.find(s => s.key === seasonKey)
  if (season) {
    selectedSeason.value = season
    mode.value = 'images'
  }
}

const handleImageUpload = async (image: SeasonImage) => {
  if (!selectedSeason.value) return
  
  try {
    const response = await fetch(`${getApiBase()}/api/plex/upload-season-poster`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        rating_key: selectedSeason.value.key,
        image_url: image.url,
      }),
    })

    if (!response.ok) {
      throw new Error('Failed to upload season poster')
    }

    emit('uploaded', selectedSeason.value.key)
    mode.value = 'seasons'
    selectedSeason.value = null
  } catch (err) {
    console.error('Failed to upload season poster:', err)
    alert('Failed to upload season poster. Please try again.')
  }
}

const handleBackFromImages = () => {
  mode.value = 'seasons'
  selectedSeason.value = null
}

const handleClose = () => {
  mode.value = 'seasons'
  selectedSeason.value = null
  emit('close')
}

const props = defineProps<Props>()
</script>

<template>
  <div v-if="isOpen" class="season-editor-modal-overlay" @click.self="handleClose">
    <div class="season-editor-modal">
      <div class="modal-header">
        <h2>{{ show.title }} - Season Posters</h2>
        <button class="close-btn" @click="handleClose" title="Close">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div class="modal-content">
        <!-- Seasons View -->
        <SeasonSelector
          v-if="mode === 'seasons'"
          :show="{ key: show.key, title: show.title }"
          :seasons="seasons"
          :loading="loadingSeasons"
          @season-select="handleSeasonSelect"
          @back="handleClose"
        />

        <!-- Image Selector View -->
        <SeasonImageSelector
          v-else-if="mode === 'images' && selectedSeason"
          :show-tmdb-id="show.tmdb_id || 0"
          :season-number="selectedSeason.index"
          :season-key="selectedSeason.key"
          :tvdb-id="show.tvdb_id"
          @select="() => {}"
          @upload="handleImageUpload"
          @back="handleBackFromImages"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.season-editor-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.season-editor-modal {
  display: flex;
  flex-direction: column;
  background: rgba(15, 23, 42, 0.95);
  border: 1px solid var(--border);
  border-radius: 16px;
  max-width: 900px;
  width: 90%;
  max-height: 90vh;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.modal-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #f5f7fa;
}

.close-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: #dce6ff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(61, 214, 183, 0.5);
}

.modal-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}
</style>
