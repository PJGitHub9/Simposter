<script setup lang="ts">
import { ref } from 'vue'
import { setPosterModes, type ModeItem, type PosterMode } from '@/services/posterModes'

const props = defineProps<{
  groupId: string
  mediaType: 'movie' | 'tv'
  items: ModeItem[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'changed', mode: PosterMode | null, updated: number): void
}>()

const busy = ref(false)
const message = ref('')
const choice = ref('')

async function apply() {
  const value = choice.value
  if (!value) return
  const mode = value === 'rules' ? null : (value as PosterMode)
  choice.value = ''
  busy.value = true
  message.value = ''
  try {
    const updated = await setPosterModes(props.groupId, props.mediaType, props.items, mode)
    message.value = updated ? `${updated} title${updated === 1 ? '' : 's'} updated` : 'Nothing to change'
    emit('changed', mode, updated)
  } catch {
    message.value = 'Could not set the mode'
  } finally {
    busy.value = false
    setTimeout(() => { message.value = '' }, 3000)
  }
}
</script>

<template>
  <span class="mode-menu">
    <select v-model="choice" class="mode-select" :disabled="disabled || busy || !items.length" @change="apply">
      <option value="">Set mode...</option>
      <option value="full">Full</option>
      <option value="overlay_only">Overlay only</option>
      <option value="leave_alone">Leave alone</option>
      <option value="rules">Follow rules</option>
    </select>
    <span v-if="message" class="mode-msg">{{ message }}</span>
  </span>
</template>

<style scoped>
.mode-menu {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.mode-select {
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  font-size: 13px;
}

.mode-select:disabled {
  opacity: 0.5;
}

.mode-msg {
  font-size: 12px;
  color: var(--muted);
}
</style>
