<template>
  <div v-if="isOpen" class="modal-overlay" @click.self="closeModal">
    <div class="modal-content">
      <div class="modal-header">
        <h2>Batch Edit</h2>
        <button class="close-btn" @click="closeModal">✕</button>
      </div>

      <div class="modal-body">
        <div class="two-column-layout">
          <!-- Left Column: Movies Selection -->
          <div class="section">
            <div class="section-header">
              <h3>All Movies ({{ checkedMovies.size }} selected)</h3>
              <div class="selection-controls">
                <button class="btn-small" @click="selectAllFiltered">Select Filtered</button>
                <button class="btn-small" @click="deselectAll">Deselect All</button>
              </div>
            </div>

            <!-- Filter and Sort -->
            <div class="filter-bar">
              <input
                v-model="searchQuery"
                type="text"
                placeholder="Filter movies..."
                class="filter-input"
              />
              <select v-model="sortBy" class="sort-select">
                <option value="title-asc">Title (A-Z)</option>
                <option value="title-desc">Title (Z-A)</option>
                <option value="year-asc">Year (Oldest)</option>
                <option value="year-desc">Year (Newest)</option>
              </select>
            </div>

            <!-- Movies List -->
            <div class="movies-list">
              <div
                v-for="movie in filteredMovies"
                :key="movie.key"
                class="movie-row"
                :class="{ selected: checkedMovies.has(movie.key) }"
                @click="toggleMovie(movie.key)"
              >
                <input
                  type="checkbox"
                  :checked="checkedMovies.has(movie.key)"
                  @click.stop="toggleMovie(movie.key)"
                  class="movie-checkbox"
                />
                <div class="movie-thumbnail-small">
                  <img
                    :src="`/api/movie/${movie.key}/poster?w=30&h=45`"
                    :alt="movie.title"
                    loading="lazy"
                  />
                </div>
                <div class="movie-details">
                  <p class="movie-title">{{ movie.title }}</p>
                  <p class="movie-year">{{ movie.year }}</p>
                </div>
              </div>
            </div>
            <p v-if="checkedMovies.size === 0" class="warning">
              Please select at least one movie
            </p>
          </div>

          <!-- Right Column: Selected Movies Preview -->
          <div class="section selected-preview">
            <h3>Selected Movies ({{ checkedMovies.size }})</h3>
            <div class="selected-list">
              <div
                v-for="movie in selectedMoviesPreview"
                :key="movie.key"
                class="selected-movie-item"
              >
                <div class="movie-thumbnail-small">
                  <img
                    :src="`/api/movie/${movie.key}/poster?w=30&h=45`"
                    :alt="movie.title"
                    loading="lazy"
                  />
                </div>
                <div class="movie-details">
                  <p class="movie-title">{{ movie.title }}</p>
                  <p class="movie-year">{{ movie.year }}</p>
                </div>
                <button class="remove-btn" @click="toggleMovie(movie.key)">✕</button>
              </div>
              <p v-if="checkedMovies.size === 0" class="empty-state">No movies selected</p>
            </div>
          </div>
        </div>

        <!-- Template Selection -->
        <div class="section">
          <label>Template</label>
          <select v-model="selectedTemplate" class="form-control">
            <option value="">Select a template...</option>
            <option v-for="tpl in templates" :key="tpl.id" :value="tpl.id">
              {{ tpl.name }}
            </option>
          </select>
        </div>

        <!-- Preset Selection -->
        <div class="section">
          <label>Preset (Optional)</label>
          <select v-model="selectedPreset" class="form-control">
            <option value="">No preset</option>
            <option v-for="pre in presets" :key="pre.id" :value="pre.id">
              {{ pre.name }}
            </option>
          </select>
        </div>

        <!-- Action Options -->
        <div class="section">
          <h3>Actions</h3>
          <label class="checkbox-label">
            <input type="checkbox" v-model="sendToPlex" />
            Send to Plex
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="saveLocally" />
            Save locally
          </label>
          <label v-if="sendToPlex" class="checkbox-label sub-option">
            <input type="checkbox" v-model="autoRemoveLabels" />
            Auto-remove old labels after send
          </label>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn-cancel" @click="closeModal">Cancel</button>
        <button
          class="btn-send"
          @click="processBatch"
          :disabled="checkedMovies.size === 0 || !selectedTemplate || (!sendToPlex && !saveLocally) || isSending"
        >
          <span v-if="!isSending">Process {{ checkedMovies.size }} Movies</span>
          <span v-else>Processing...</span>
        </button>
      </div>

      <!-- Progress -->
      <div v-if="isSending" class="progress-section">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
        </div>
        <p class="progress-text">
          Processing {{ currentIndex }} of {{ checkedMovies.size }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useNotification } from "@/composables/useNotification";
import type { Movie } from "@/services/types";

interface Template {
  id: string;
  name: string;
}

interface Preset {
  id: string;
  name: string;
}

const props = defineProps<{
  isOpen: boolean;
  movies: Movie[];
}>();

const emit = defineEmits<{
  close: [];
}>();

const { success, error } = useNotification();

const selectedTemplate = ref<string>("");
const selectedPreset = ref<string>("");
const checkedMovies = ref<Set<string>>(new Set());
const templates = ref<Template[]>([]);
const presets = ref<Preset[]>([]);
const isSending = ref(false);
const currentIndex = ref(0);
const autoRemoveLabels = ref(false);
const sendToPlex = ref(true);
const saveLocally = ref(false);
const searchQuery = ref("");
const sortBy = ref("title-asc");

const filteredMovies = computed(() => {
  // Filter first
  let movies = props.movies;
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase();
    movies = movies.filter(
      (m) =>
        m.title.toLowerCase().includes(query) ||
        (m.year && m.year.toString().includes(query))
    );
  }

  // Then sort
  const sorted = [...movies];
  switch (sortBy.value) {
    case "title-asc":
      sorted.sort((a, b) => a.title.localeCompare(b.title));
      break;
    case "title-desc":
      sorted.sort((a, b) => b.title.localeCompare(a.title));
      break;
    case "year-asc":
      sorted.sort((a, b) => {
        const yearA = typeof a.year === 'number' ? a.year : parseInt(String(a.year || 0));
        const yearB = typeof b.year === 'number' ? b.year : parseInt(String(b.year || 0));
        return yearA - yearB;
      });
      break;
    case "year-desc":
      sorted.sort((a, b) => {
        const yearA = typeof a.year === 'number' ? a.year : parseInt(String(a.year || 0));
        const yearB = typeof b.year === 'number' ? b.year : parseInt(String(b.year || 0));
        return yearB - yearA;
      });
      break;
  }

  return sorted;
});

const progressPercent = computed(() => {
  if (checkedMovies.value.size === 0) return 0;
  return (currentIndex.value / checkedMovies.value.size) * 100;
});

const selectedMoviesPreview = computed(() => {
  // Get all movies that are checked
  return props.movies.filter((m) => checkedMovies.value.has(m.key));
});

watch(
  () => props.isOpen,
  (newVal) => {
    if (newVal) {
      loadTemplatesAndPresets();
      // Pre-select all movies by default
      checkedMovies.value = new Set(props.movies.map((m) => m.key));
    } else {
      checkedMovies.value.clear();
      selectedTemplate.value = "";
      selectedPreset.value = "";
    }
  }
);

const toggleMovie = (key: string) => {
  if (checkedMovies.value.has(key)) {
    checkedMovies.value.delete(key);
  } else {
    checkedMovies.value.add(key);
  }
};

const selectAllFiltered = () => {
  // Add all filtered movies to the existing selection
  filteredMovies.value.forEach((m) => {
    checkedMovies.value.add(m.key);
  });
};

const deselectAll = () => {
  checkedMovies.value.clear();
};

const closeModal = () => {
  emit("close");
};

const loadTemplatesAndPresets = async () => {
  try {
    const response = await fetch("/api/presets");
    const data = await response.json();
    templates.value = data.templates || [];
    presets.value = data.presets || [];
  } catch (err) {
    error("Error loading templates and presets");
    console.error(err);
  }
};

const processBatch = async () => {
  if (checkedMovies.value.size === 0 || !selectedTemplate.value) {
    error("Please select movies and a template");
    return;
  }

  if (!sendToPlex.value && !saveLocally.value) {
    error("Please select at least one action (Send to Plex or Save locally)");
    return;
  }

  isSending.value = true;
  currentIndex.value = 0;

  try {
    const ratingKeys = Array.from(checkedMovies.value);

    const payload = {
      rating_keys: ratingKeys,
      template_id: selectedTemplate.value,
      preset_id: selectedPreset.value || undefined,
      options: {
        poster_filter: "all",
        logo_preference: "first",
      },
      send_to_plex: sendToPlex.value,
      save_locally: saveLocally.value,
      labels: autoRemoveLabels.value && sendToPlex.value
        ? ["old_poster", "temp", "edited"] // Common labels to remove
        : [],
    };

    // Start batch progress polling in App.vue
    if ((window as any).startBatchPolling) {
      (window as any).startBatchPolling();
    }

    // Simulate progress updates
    const progressInterval = setInterval(() => {
      currentIndex.value = Math.min(
        currentIndex.value + 1,
        checkedMovies.value.size
      );
      if (currentIndex.value >= checkedMovies.value.size) {
        clearInterval(progressInterval);
      }
    }, 300);

    const response = await fetch("/api/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    clearInterval(progressInterval);
    currentIndex.value = checkedMovies.value.size;

    if (!response.ok) {
      throw new Error("Failed to process batch");
    }

    await response.json();

    let message = `Successfully processed ${checkedMovies.value.size} movies`;
    if (sendToPlex.value && saveLocally.value) {
      message += " (sent to Plex and saved locally)";
    } else if (sendToPlex.value) {
      message += " (sent to Plex)";
    } else if (saveLocally.value) {
      message += " (saved locally)";
    }
    success(message);

    // Reset and close
    setTimeout(() => {
      closeModal();
      isSending.value = false;
      checkedMovies.value.clear();
      selectedTemplate.value = "";
      selectedPreset.value = "";
    }, 1500);
  } catch (err) {
    error(`Batch processing failed: ${err}`);
    console.error(err);
    isSending.value = false;
  }
};
</script>

<style scoped>
.modal-overlay {
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
}

.modal-content {
  background: var(--surface, #1a1f2e);
  border-radius: 8px;
  max-width: 1200px;
  width: 95%;
  max-height: 95vh;
  overflow-y: auto;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid var(--border, #2a2f3e);
}

.modal-header h2 {
  margin: 0;
  color: var(--text-primary, #fff);
  font-size: 1.5rem;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
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
  background-color: var(--hover, #2a2f3e);
}

.modal-body {
  padding: 1.5rem;
}

.two-column-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-bottom: 1.5rem;
}

.section {
  margin-bottom: 1.5rem;
}

.section h3 {
  color: var(--text-primary, #fff);
  margin-top: 0;
  margin-bottom: 1rem;
}

.section label {
  display: block;
  color: var(--text-primary, #fff);
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.section input[type="checkbox"] {
  margin-right: 0.5rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.selection-controls {
  display: flex;
  gap: 0.5rem;
}

.btn-small {
  padding: 0.4rem 0.8rem;
  background: var(--surface-alt, #242933);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-small:hover {
  background: var(--accent, #3dd6b7);
  color: #000;
  border-color: var(--accent, #3dd6b7);
}

.filter-bar {
  margin-bottom: 1rem;
  display: flex;
  gap: 0.75rem;
}

.filter-input {
  flex: 1;
  padding: 0.6rem;
  background: var(--input-bg, #242933);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  font-size: 0.9rem;
}

.filter-input:focus {
  outline: none;
  border-color: var(--accent, #3dd6b7);
}

.sort-select {
  padding: 0.6rem;
  background: var(--input-bg, #242933);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  font-size: 0.9rem;
  cursor: pointer;
  min-width: 150px;
}

.sort-select:focus {
  outline: none;
  border-color: var(--accent, #3dd6b7);
}

.movies-list {
  max-height: 600px;
  overflow-y: auto;
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 6px;
  background: var(--surface-alt, #242933);
}

.movie-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  border-bottom: 1px solid var(--border, #2a2f3e);
  cursor: pointer;
  transition: background 0.2s;
}

.movie-row:last-child {
  border-bottom: none;
}

.movie-row:hover {
  background: rgba(61, 214, 183, 0.05);
}

.movie-row.selected {
  background: rgba(61, 214, 183, 0.1);
  border-left: 3px solid var(--accent, #3dd6b7);
}

.movie-checkbox {
  flex-shrink: 0;
  cursor: pointer;
  width: 16px;
  height: 16px;
  accent-color: var(--accent, #3dd6b7);
}

.movie-thumbnail-small {
  width: 30px;
  height: 45px;
  border-radius: 3px;
  overflow: hidden;
  background: var(--surface, #1a1f2e);
  flex-shrink: 0;
}

.movie-thumbnail-small img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.movie-details {
  flex: 1;
  min-width: 0;
}

.movie-title {
  color: var(--text-primary, #fff);
  font-size: 0.85rem;
  margin: 0;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.movie-year {
  color: var(--text-secondary, #aaa);
  font-size: 0.75rem;
  margin: 0.15rem 0 0 0;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  color: var(--text-primary, #fff);
  cursor: pointer;
}

.checkbox-label.sub-option {
  margin-left: 1.5rem;
  color: var(--text-secondary, #aaa);
}

.form-control {
  width: 100%;
  padding: 0.75rem;
  background: var(--input-bg, #242933);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  font-size: 1rem;
}

.form-control:focus {
  outline: none;
  border-color: var(--accent, #3dd6b7);
}

.form-control option {
  background: var(--surface, #1a1f2e);
  color: var(--text-primary, #fff);
}

.warning {
  color: #ff6b6b;
  margin: 0;
  padding: 0.75rem;
  background: rgba(255, 107, 107, 0.1);
  border-radius: 4px;
  font-size: 0.9rem;
}

.modal-footer {
  display: flex;
  gap: 1rem;
  padding: 1.5rem;
  border-top: 1px solid var(--border, #2a2f3e);
  background: var(--surface-alt, #242933);
  border-radius: 0 0 8px 8px;
}

.btn-cancel {
  flex: 1;
  padding: 0.75rem 1.5rem;
  background: var(--surface, #1a1f2e);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 4px;
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-cancel:hover {
  background: var(--surface-alt, #242933);
}

.btn-send {
  flex: 1;
  padding: 0.75rem 1.5rem;
  background: var(--accent, #3dd6b7);
  color: #000;
  border: none;
  border-radius: 4px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-send:hover:not(:disabled) {
  background: #2bc4a3;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(61, 214, 183, 0.3);
}

.btn-send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.progress-section {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border, #2a2f3e);
  background: var(--surface-alt, #242933);
}

.progress-bar {
  width: 100%;
  height: 6px;
  background: var(--border, #2a2f3e);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: var(--accent, #3dd6b7);
  transition: width 0.3s ease;
}

.progress-text {
  color: var(--text-secondary, #aaa);
  margin: 0;
  font-size: 0.9rem;
}

.selected-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.selected-list {
  flex: 1;
  max-height: 660px;
  overflow-y: auto;
  border: 1px solid var(--border, #2a2f3e);
  border-radius: 6px;
  background: var(--surface-alt, #242933);
  padding: 0.5rem;
}

.selected-movie-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  border-bottom: 1px solid var(--border, #2a2f3e);
  background: rgba(61, 214, 183, 0.05);
  border-radius: 4px;
  margin-bottom: 0.5rem;
  transition: background 0.2s;
}

.selected-movie-item:hover {
  background: rgba(61, 214, 183, 0.1);
}

.selected-movie-item:last-child {
  margin-bottom: 0;
}

.remove-btn {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--text-secondary, #aaa);
  font-size: 1rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  transition: all 0.2s;
}

.remove-btn:hover {
  background: rgba(255, 107, 107, 0.2);
  color: #ff6b6b;
}

.empty-state {
  text-align: center;
  color: var(--text-secondary, #aaa);
  padding: 2rem;
  margin: 0;
}
</style>
