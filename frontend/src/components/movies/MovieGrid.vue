<script setup lang="ts">
import MovieCard from './MovieCard.vue'

type Entry = {
  title: string
  year?: number | string
  addedAt?: number
  status?: string
  poster?: string | null
  key: string
}

defineProps<{
  heading: string
  items: Entry[]
}>()

const emit = defineEmits<{
  (e: 'select', movie: Entry): void
}>()
</script>

<template>
  <section class="grid-block">
    <div class="heading-row">
      <h2>{{ heading }}</h2>
      <p class="count">{{ items.length }} items</p>
    </div>
    <div class="grid">
      <MovieCard
        v-for="item in items"
        :key="item.key"
        :title="item.title"
        :year="item.year"
        :addedAt="item.addedAt"
        :poster="item.poster"
        :status="item.status"
        @select="emit('select', item)"
      />
    </div>
  </section>
</template>

<style scoped>
.grid-block {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.heading-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #d8e3ff;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

.heading-row h2 {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.3px;
}

.count {
  font-size: 13px;
  color: var(--muted);
  font-weight: 500;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 14px;
}
</style>
