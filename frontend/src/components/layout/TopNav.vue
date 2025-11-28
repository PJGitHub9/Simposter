<script setup lang="ts">
import { computed, ref } from 'vue'

type Movie = { key: string; title: string; year?: number | string; poster?: string | null }

const props = defineProps<{
  search?: string
  showBack?: boolean
  movies?: Movie[]
}>()

const emit = defineEmits<{
  (e: 'update:search', value: string): void
  (e: 'back'): void
  (e: 'selectMovie', movie: Movie): void
}>()

const searchFocused = ref(false)

const searchResults = computed(() => {
  if (!props.search || !props.movies) return []
  const term = props.search.trim().toLowerCase()
  if (!term) return []

  return props.movies
    .filter((m) => m.title.toLowerCase().includes(term))
    .slice(0, 8)
})

const showDropdown = computed(() => searchFocused.value && searchResults.value.length > 0)

const handleSelectMovie = (movie: Movie) => {
  emit('selectMovie', movie)
  emit('update:search', '')
  searchFocused.value = false
}

const handleBlur = () => {
  setTimeout(() => {
    searchFocused.value = false
  }, 200)
}
</script>

<template>
  <header class="top-nav glass">
    <div class="nav-left">
      <button v-if="showBack" class="back-btn" @click="emit('back')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
      </button>
      <div class="logo">
        <span class="logo-text">Simposter</span>
      </div>
    </div>
    <div class="search-container">
      <svg class="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.35-4.35" />
      </svg>
      <input
        :value="search"
        @input="emit('update:search', ($event.target as HTMLInputElement).value)"
        @focus="searchFocused = true"
        @blur="handleBlur"
        type="search"
        placeholder="Search for movies, shows, or collections..."
        class="search-input"
      />

      <!-- Search Results Dropdown -->
      <div v-if="showDropdown" class="search-dropdown">
        <div
          v-for="movie in searchResults"
          :key="movie.key"
          class="search-result"
          @click="handleSelectMovie(movie)"
        >
          <div class="result-poster" :style="{ backgroundImage: movie.poster ? `url(${movie.poster})` : 'none' }">
            <div v-if="!movie.poster" class="result-poster-placeholder">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
          </div>
          <div class="result-info">
            <p class="result-title">{{ movie.title }}</p>
            <p v-if="movie.year" class="result-year">{{ movie.year }}</p>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.top-nav {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 18px;
  background: rgba(14, 16, 24, 0.85);
  backdrop-filter: blur(12px);
  position: relative;
  z-index: 30;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  cursor: pointer;
  transition: all 0.2s;
}

.back-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.12);
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.3px;
  background: linear-gradient(120deg, #3dd6b7, #5b8dee);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.search-container {
  flex: 1;
  max-width: 720px;
  position: relative;
  display: flex;
  align-items: center;
  margin: 0 auto;
  z-index: 20;
}

.search-icon {
  position: absolute;
  left: 14px;
  color: var(--muted);
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 10px 14px 10px 42px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
  font-size: 14px;
  transition: all 0.2s;
}

.search-input:focus {
  outline: none;
  border-color: rgba(61, 214, 183, 0.5);
  background: rgba(255, 255, 255, 0.06);
}

.search-input::placeholder {
  color: var(--muted);
}

.search-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  max-height: 400px;
  overflow-y: auto;
  background: rgba(17, 20, 30, 0.98);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(12px);
  z-index: 2000;
}

.search-result {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.search-result:last-child {
  border-bottom: none;
}

.search-result:hover {
  background: rgba(61, 214, 183, 0.1);
}

.result-poster {
  width: 40px;
  height: 60px;
  border-radius: 6px;
  background-size: cover;
  background-position: center;
  background-color: rgba(255, 255, 255, 0.05);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.result-poster-placeholder {
  color: var(--muted);
  opacity: 0.5;
}

.result-info {
  flex: 1;
  min-width: 0;
}

.result-title {
  font-size: 14px;
  font-weight: 600;
  color: #eef2ff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-year {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}
</style>
