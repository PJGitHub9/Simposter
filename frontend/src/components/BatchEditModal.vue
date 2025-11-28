<template>
  <div v-if="isOpen" class="modal-overlay" @click.self="closeModal">
    <div class="modal-content">
      <div class="modal-header">
        <h2>Batch Send to Plex</h2>
        <button class="close-btn" @click="closeModal">✕</button>
      </div>

      <div class="modal-body">
        <!-- Movies Selection -->
        <div class="section">
          <h3>Selected Movies ({{ selectedMovies.length }})</h3>
          <div class="movies-grid">
            <div
              v-for="movie in selectedMovies"
              :key="movie.key"
              class="movie-item"
              @click="toggleMovie(movie.key)"
            >
              <div class="movie-thumbnail">
                <img
                  :src="`/api/movie/${movie.key}/poster?w=80&h=120&v=${Date.now()}`"
                  :alt="movie.title"
                />
              </div>
              <div class="movie-info">
                <p class="movie-title">{{ movie.title }}</p>
                <p class="movie-year">{{ movie.year }}</p>
                <input
                  type="checkbox"
                  :checked="checkedMovies.has(movie.key)"
                  @change="toggleMovie(movie.key)"
                />
              </div>
            </div>
          </div>
          <p v-if="checkedMovies.size === 0" class="warning">
            Please select at least one movie
          </p>
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

        <!-- Options -->
        <div class="section">
          <label>
            <input type="checkbox" v-model="autoRemoveLabels" />
            Auto-remove old labels after send
          </label>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn-cancel" @click="closeModal">Cancel</button>
        <button
          class="btn-send"
          @click="sendBatch"
          :disabled="checkedMovies.size === 0 || !selectedTemplate || isSending"
        >
          <span v-if="!isSending">Send {{ checkedMovies.size }} Movies</span>
          <span v-else>Sending...</span>
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

const selectedMovies = computed(() => {
  return props.movies.filter((m) => checkedMovies.value.has(m.key));
});

const progressPercent = computed(() => {
  if (checkedMovies.value.size === 0) return 0;
  return (currentIndex.value / checkedMovies.value.size) * 100;
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

const sendBatch = async () => {
  if (checkedMovies.value.size === 0 || !selectedTemplate.value) {
    error("Please select movies and a template");
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
      send_to_plex: true,
      labels: autoRemoveLabels.value
        ? ["old_poster", "temp", "edited"] // Common labels to remove
        : [],
    };

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
      throw new Error("Failed to send batch");
    }

    const result = await response.json();
    success(
      `Successfully sent ${checkedMovies.value.size} movies to Plex!`
    );

    // Reset and close
    setTimeout(() => {
      closeModal();
      isSending.value = false;
      checkedMovies.value.clear();
      selectedTemplate.value = "";
      selectedPreset.value = "";
    }, 1500);
  } catch (err) {
    error(`Batch send failed: ${err}`);
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
  max-width: 800px;
  width: 90%;
  max-height: 90vh;
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

.movies-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
}

.movie-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  border-radius: 6px;
  background: var(--surface-alt, #242933);
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.movie-item:hover {
  border-color: var(--accent, #3dd6b7);
  transform: translateY(-2px);
}

.movie-item.selected {
  border-color: var(--accent, #3dd6b7);
  background: var(--surface, #1a1f2e);
}

.movie-thumbnail {
  width: 80px;
  height: 120px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--surface, #1a1f2e);
}

.movie-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.movie-info {
  text-align: center;
  width: 100%;
}

.movie-title {
  color: var(--text-primary, #fff);
  font-size: 0.75rem;
  margin: 0;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  line-clamp: 2;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.movie-year {
  color: var(--text-secondary, #aaa);
  font-size: 0.7rem;
  margin: 0.25rem 0;
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
</style>
