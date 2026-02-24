<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getApiBase } from '@/services/apiBase'

export interface SeasonImage {
  url: string
  source: 'tmdb' | 'tvdb' | 'fanart'
  rating?: number
  votes?: number
}

interface Props {
  showTmdbId: number
  seasonNumber: number
  seasonKey: string
  tvdbId?: number
  loading?: boolean
}

interface Emits {
  (e: 'select', image: SeasonImage): void
  (e: 'upload', image: SeasonImage): void
  (e: 'back'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const images = ref<SeasonImage[]>([])
const selectedImage = ref<SeasonImage | null>(null)
const loadingImages = ref(false)
const uploading = ref(false)
const error = ref<string | null>(null)

const sourceColors: Record<string, string> = {
  tmdb: '#00D4FF',
  tvdb: '#0C6291',
  fanart: '#FF8C42',
}

const loadImages = async () => {
  loadingImages.value = true
  error.value = null
  images.value = []

  try {
    const params = new URLSearchParams({
      season: props.seasonNumber.toString(),
      ...(props.tvdbId && { tvdb_id: props.tvdbId.toString() }),
    })
    const response = await fetch(`${getApiBase()}/tmdb/tv/${props.showTmdbId}/images?${params}`)

    if (!response.ok) {
      throw new Error('Failed to fetch season images')
    }

    const data = await response.json()

    // Merge images from all sources
    const merged: SeasonImage[] = []

    // Add TMDB images
    if (data.season_posters) {
      for (const poster of data.season_posters) {
        merged.push({
          url: poster.image,
          source: 'tmdb',
          rating: poster.vote_average,
          votes: poster.vote_count,
        })
      }
    }

    // Add TVDB images
    if (data.tvdb_posters) {
      for (const poster of data.tvdb_posters) {
        if (!merged.some(p => p.url === poster.image)) {
          merged.push({
            url: poster.image,
            source: 'tvdb',
            rating: poster.rating,
          })
        }
      }
    }

    // Add Fanart images
    if (data.fanart_posters) {
      for (const poster of data.fanart_posters) {
        if (!merged.some(p => p.url === poster.image)) {
          merged.push({
            url: poster.image,
            source: 'fanart',
          })
        }
      }
    }

    images.value = merged
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load images'
  } finally {
    loadingImages.value = false
  }
}

onMounted(() => {
  loadImages()
})

function selectImage(image: SeasonImage) {
  selectedImage.value = image
  emit('select', image)
}

async function uploadImage() {
  if (!selectedImage.value) return
  
  uploading.value = true
  try {
    emit('upload', selectedImage.value)
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="season-image-selector">
    <div class="selector-header">
      <button @click="$emit('back')" class="back-btn" title="Back">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
      </button>
      <div class="header-content">
        <div>
          <h3>Select Season Poster</h3>
          <p class="muted">Season {{ seasonNumber }}</p>
        </div>
        <button
          v-if="selectedImage"
          @click="uploadImage"
          :disabled="uploading"
          class="upload-btn"
        >
          {{ uploading ? 'Uploading...' : 'Upload to Plex' }}
        </button>
      </div>
    </div>

    <div v-if="loadingImages" class="loading-state">
      Loading images…
    </div>
    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button @click="loadImages" class="retry-btn">Retry</button>
    </div>
    <div v-else-if="images.length === 0" class="empty-state">
      <p>No season posters found</p>
    </div>
    <div v-else class="images-grid">
      <div
        v-for="(image, idx) in images"
        :key="`${image.source}-${idx}`"
        class="image-card"
        :class="{ selected: selectedImage?.url === image.url }"
        @click="selectImage(image)"
      >
        <img :src="image.url" :alt="`Season ${seasonNumber} poster from ${image.source}`" />
        <div class="source-badge" :style="{ background: sourceColors[image.source] }">
          {{ image.source.toUpperCase() }}
        </div>
        <div v-if="image.rating" class="rating-badge">
          ⭐ {{ image.rating.toFixed(1) }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.season-image-selector {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
}

.selector-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 12px;
}

.header-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}

.back-btn {
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

.back-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(61, 214, 183, 0.5);
}

.selector-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #f5f7fa;
}

.selector-header .muted {
  margin: 4px 0 0;
  font-size: 12px;
  color: #8892b0;
}

.upload-btn {
  padding: 8px 16px;
  border: 1px solid rgba(61, 214, 183, 0.5);
  border-radius: 8px;
  background: rgba(61, 214, 183, 0.15);
  color: #3dd6b7;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.upload-btn:hover:not(:disabled) {
  background: rgba(61, 214, 183, 0.25);
  border-color: rgba(61, 214, 183, 0.7);
}

.upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state,
.empty-state,
.error-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  color: #8892b0;
  font-size: 14px;
  flex-direction: column;
  gap: 12px;
}

.retry-btn {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 16px;
  background: rgba(61, 214, 183, 0.15);
  color: #3dd6b7;
  cursor: pointer;
  transition: all 0.2s;
}

.retry-btn:hover {
  background: rgba(61, 214, 183, 0.25);
}

.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 12px;
  max-height: 500px;
  overflow-y: auto;
  padding-right: 4px;
}

.image-card {
  position: relative;
  aspect-ratio: 2 / 3;
  border-radius: 10px;
  border: 2px solid var(--border);
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
  background: rgba(255, 255, 255, 0.04);
}

.image-card:hover {
  border-color: rgba(61, 214, 183, 0.4);
  transform: scale(1.02);
}

.image-card.selected {
  border-color: rgba(61, 214, 183, 0.8);
  box-shadow: 0 0 12px rgba(61, 214, 183, 0.4);
}

.image-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.source-badge,
.rating-badge {
  position: absolute;
  font-size: 10px;
  font-weight: 600;
  color: #fff;
  padding: 4px 6px;
  border-radius: 4px;
  backdrop-filter: blur(4px);
}

.source-badge {
  top: 4px;
  right: 4px;
}

.rating-badge {
  bottom: 4px;
  right: 4px;
  background: rgba(255, 215, 0, 0.8);
  color: #000;
}
</style>
