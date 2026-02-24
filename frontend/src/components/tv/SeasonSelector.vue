<script setup lang="ts">
import { ref, computed } from 'vue'

export interface Season {
  key: string
  title: string
  index: number
  thumb?: string
}

export interface TvShow {
  key: string
  title: string
  year?: number | string
  poster?: string | null
}

interface Props {
  show: TvShow
  seasons: Season[]
  loading?: boolean
}

interface Emits {
  (e: 'season-select', seasonKey: string, seasonIndex: number): void
  (e: 'back'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const selectedSeasonKey = ref<string | null>(null)

const sortedSeasons = computed(() => {
  return [...props.seasons].sort((a, b) => a.index - b.index)
})

function selectSeason(season: Season) {
  selectedSeasonKey.value = season.key
  emit('season-select', season.key, season.index)
}
</script>

<template>
  <div class="season-selector">
    <div class="season-header">
      <button @click="$emit('back')" class="back-btn" title="Back to TV shows">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
      </button>
      <div class="show-info">
        <h2>{{ show.title }}</h2>
        <p class="muted">{{ show.year ? `(${show.year})` : '' }} • {{ seasons.length }} season<span v-if="seasons.length !== 1">s</span></p>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      Loading seasons…
    </div>
    <div v-else-if="sortedSeasons.length === 0" class="empty-state">
      <p>No seasons found</p>
    </div>
    <div v-else class="seasons-grid">
      <div
        v-for="season in sortedSeasons"
        :key="season.key"
        class="season-card"
        :class="{ selected: selectedSeasonKey === season.key }"
        @click="selectSeason(season)"
      >
        <div class="season-thumb" :style="{ backgroundImage: season.thumb ? `url(${season.thumb})` : 'none' }">
          <div class="season-badge">S{{ String(season.index).padStart(2, '0') }}</div>
        </div>
        <div class="season-meta">
          <p class="title">{{ season.title }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.season-selector {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
}

.season-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 12px;
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

.show-info {
  flex: 1;
  min-width: 0;
}

.show-info h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #f5f7fa;
}

.show-info .muted {
  margin: 4px 0 0;
  font-size: 13px;
  color: #8892b0;
}

.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: #8892b0;
  font-size: 14px;
}

.seasons-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}

.season-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  cursor: pointer;
  transition: all 0.2s;
}

.season-card:hover {
  transform: translateY(-2px);
  border-color: rgba(61, 214, 183, 0.4);
  background: rgba(255, 255, 255, 0.04);
}

.season-card.selected {
  border-color: rgba(61, 214, 183, 0.8);
  background: rgba(61, 214, 183, 0.15);
}

.season-thumb {
  aspect-ratio: 2 / 3;
  background-size: cover;
  background-position: center;
  border-radius: 8px;
  background-color: rgba(255, 255, 255, 0.04);
  position: relative;
  border: 1px solid var(--border);
}

.season-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  padding: 4px 8px;
  background: rgba(0, 0, 0, 0.7);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  backdrop-filter: blur(4px);
}

.season-meta {
  min-width: 0;
}

.season-meta .title {
  margin: 0;
  font-size: 13px;
  font-weight: 500;
  color: #e1e8ff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
