<script setup lang="ts">
const sliders = [
  { label: 'Glow', value: 60 },
  { label: 'Fog', value: 45 },
  { label: 'Contrast', value: 72 },
  { label: 'Logo Scale', value: 84 }
]
</script>

<template>
  <div class="panel glass">
    <p class="panel__title">Look Controls</p>
    <div class="rows">
      <label v-for="slider in sliders" :key="slider.label">
        <span>{{ slider.label }}</span>
        <input type="range" min="0" max="100" :value="slider.value" />
      </label>
    </div>
  </div>
</template>

<style scoped>
.panel {
  padding: 12px;
}

.panel__title {
  font-weight: 600;
  margin-bottom: 8px;
  color: #dce6ff;
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--muted);
  font-size: 13px;
}

input[type='range'] {
  accent-color: var(--accent);
}
</style>
