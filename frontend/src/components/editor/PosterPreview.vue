<script setup lang="ts">
defineProps<{
  title?: string
  subtitle?: string
  imageUrl?: string
}>()
</script>

<template>
  <div class="preview-card glass">
    <div class="frame">
      <div class="poster" :style="imageUrl ? { backgroundImage: `url(${imageUrl})` } : {}">
        <span class="tag">Preview</span>
        <div class="text">
          <p class="eyebrow">Simposter</p>
          <h3>{{ title || 'Blade Runner 2049' }}</h3>
          <p class="subtitle">{{ subtitle || 'Layered template • Gradient fog • Logo locked' }}</p>
        </div>
      </div>
    </div>
    <div class="meta">
      <div>
        <p class="label">Format</p>
        <p class="value">2:3 • 300 DPI</p>
      </div>
      <div>
        <p class="label">Template</p>
        <p class="value">Neon Mist</p>
      </div>
      <div>
        <p class="label">Overrides</p>
        <p class="value">Logo + Bounding boxes</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.preview-card {
  padding: 14px;
}

.frame {
  display: flex;
  justify-content: center;
  padding: 10px;
}

.poster {
  position: relative;
  width: 220px;
  aspect-ratio: 2 / 3;
  border-radius: 16px;
  background: linear-gradient(180deg, #1a1d2a, #0a0c14 70%),
    radial-gradient(circle at 40% 20%, rgba(61, 214, 183, 0.25), transparent 45%),
    radial-gradient(circle at 70% 60%, rgba(91, 141, 238, 0.35), transparent 40%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
  overflow: hidden;
}

.tag {
  position: absolute;
  top: 10px;
  right: 10px;
  font-size: 11px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  color: #dce6ff;
}

.text {
  position: absolute;
  bottom: 16px;
  left: 16px;
  right: 16px;
}

.eyebrow {
  letter-spacing: 1.2px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.7);
  text-transform: uppercase;
}

h3 {
  margin: 4px 0;
  font-size: 18px;
  line-height: 1.2;
}

.subtitle {
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
}

.meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
  margin-top: 12px;
  color: #c4cceb;
}

.label {
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.5px;
}

.value {
  font-weight: 600;
}
</style>
