<script setup lang="ts">
import { ref } from 'vue'
import { usePresetService } from '../../services/presets'
import type { PresetOptions } from '../../services/types'

const { templates, presets, loading, error, selectedTemplate, selectedPreset, load, savePreset } = usePresetService()

const optionsJson = ref('')

const handleSave = async () => {
  let parsed: PresetOptions | undefined
  if (optionsJson.value.trim()) {
    try {
      parsed = JSON.parse(optionsJson.value)
    } catch (e) {
      alert('Invalid JSON')
      return
    }
  }
  await savePreset(parsed)
}

load()
</script>

<template>
  <div class="panel glass">
    <div class="panel__title">Presets & Templates</div>
    <div v-if="error" class="callout error">{{ error }}</div>
    <div v-else>
      <label class="field">
        <span>Template</span>
        <select v-model="selectedTemplate.value">
          <option v-for="tpl in templates.value" :key="tpl" :value="tpl">{{ tpl }}</option>
        </select>
      </label>
      <label class="field">
        <span>Preset</span>
        <select v-model="selectedPreset.value">
          <option v-for="p in presets.value" :key="p.id" :value="p.id">{{ p.name || p.id }}</option>
        </select>
      </label>
      <label class="field">
        <span>Options (JSON, optional when saving)</span>
        <textarea v-model="optionsJson" rows="4" placeholder='{"poster_zoom":0.9}'></textarea>
      </label>
      <div class="actions">
        <button :disabled="loading.value" @click="savePreset()">Save Current</button>
        <button :disabled="loading.value" class="ghost" @click="handleSave">Save with JSON</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel__title {
  font-weight: 700;
  margin-bottom: 8px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

select,
textarea {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: #e6edff;
}

.actions {
  display: flex;
  gap: 8px;
}

button {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.05);
  color: #dce6ff;
  cursor: pointer;
}

button.ghost {
  background: transparent;
}

.callout.error {
  border: 1px solid rgba(255, 126, 126, 0.4);
  padding: 8px;
  border-radius: 8px;
}
</style>
