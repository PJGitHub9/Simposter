<script setup lang="ts">
const templates = [
  { name: 'Neon Mist', mood: 'Vibrant fog' },
  { name: 'Gridline', mood: 'Sharp sci-fi' },
  { name: 'Archive', mood: 'Muted monochrome' }
]
</script>

<template>
  <div class="panel glass">
    <p class="panel__title">Template</p>
    <div class="list">
      <button v-for="tpl in templates" :key="tpl.name" class="item">
        <div>
          <p class="name">{{ tpl.name }}</p>
          <p class="mood">{{ tpl.mood }}</p>
        </div>
        <span class="pill">Use</span>
      </button>
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
}

.list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.03);
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}

.name {
  font-weight: 600;
}

.mood {
  color: var(--muted);
  font-size: 12px;
}

.pill {
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(61, 214, 183, 0.18);
  color: #d8fff4;
}
</style>
