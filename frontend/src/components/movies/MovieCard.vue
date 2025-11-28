<script setup lang="ts">
const props = defineProps<{
  title: string
  year?: string | number
  addedAt?: number
  poster?: string | null
  status?: string
  ratingKey?: string
}>()

const emit = defineEmits<{
  (e: 'select'): void
}>()
</script>

<template>
  <article class="card glass" @click="emit('select')">
    <div class="thumb" :style="{ backgroundImage: `url(${poster})` }">
      <div class="badge">{{ status || 'Ready' }}</div>
    </div>
    <div class="meta">
      <p class="title">{{ title }}</p>
      <p class="muted">{{ year }}</p>
    </div>
  </article>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  cursor: pointer;
  transition: all 0.2s ease;
}

.card:hover {
  transform: translateY(-4px);
  border-color: rgba(61, 214, 183, 0.4);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.thumb {
  aspect-ratio: 2 / 3;
  border-radius: 10px;
  background-size: cover;
  background-position: center;
  background-image: linear-gradient(180deg, rgba(61, 214, 183, 0.15), rgba(91, 141, 238, 0.25)),
    linear-gradient(160deg, rgba(255, 255, 255, 0.03), rgba(0, 0, 0, 0.4));
  position: relative;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.badge {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 5px 9px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
  color: #d7e6ff;
  font-size: 10px;
  font-weight: 600;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.meta .title {
  font-weight: 600;
  font-size: 14px;
  color: #eef2ff;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.muted {
  color: var(--muted);
  font-size: 12px;
  font-weight: 500;
}
</style>
