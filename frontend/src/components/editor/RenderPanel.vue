<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRenderService } from '../../services/render'
import type { MovieInput } from '../../services/types'

const props = defineProps<{ movie?: MovieInput | null }>()

const bgUrl = ref('')
const logoUrl = ref('')
const status = ref('')

const service = useRenderService()
const loading = service.loading
const error = service.error

watch(
  () => props.movie,
  (m) => {
    if (m?.poster) {
      bgUrl.value = m.poster
    }
  },
  { immediate: true }
)

const doPreview = async () => {
  if (!props.movie) return
  status.value = 'Rendering…'
  await service.preview(props.movie, bgUrl.value, logoUrl.value, {}, 'default', 'default')
  status.value = error.value || 'Preview done'
}

const doSave = async () => {
  if (!props.movie) return
  status.value = 'Saving…'
  await service.save(props.movie, bgUrl.value, logoUrl.value, {}, 'default', 'default')
  status.value = error.value || 'Saved'
}

const doSend = async () => {
  if (!props.movie) return
  status.value = 'Sending…'
  await service.send(props.movie, bgUrl.value, logoUrl.value, {}, [], 'default', 'default')
  status.value = error.value || 'Sent to Plex'
}
</script>

<template>
  <div class="panel glass">
    <div class="panel__title">Render & Send</div>
    <div class="fields">
      <label>
        <span>Background URL</span>
        <input v-model="bgUrl" type="text" placeholder="TMDb or custom image URL" />
      </label>
      <label>
        <span>Logo URL</span>
        <input v-model="logoUrl" type="text" placeholder="TMDb or custom logo URL" />
      </label>
    </div>
    <div class="actions">
      <button :disabled="loading || !movie" @click="doPreview">Preview</button>
      <button :disabled="loading || !movie" @click="doSave">Save</button>
      <button :disabled="loading || !movie" @click="doSend">Send to Plex</button>
    </div>
    <p class="status">{{ loading ? 'Working…' : status }}</p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<style scoped>
.panel__title {
  font-weight: 700;
  margin-bottom: 8px;
}

.fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #dce6ff;
}

input {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
}

.actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

button {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.05);
  color: #dce6ff;
  cursor: pointer;
}

.status {
  margin-top: 6px;
  color: #a9b4d6;
}

.error {
  color: #ff8f8f;
}
</style>
