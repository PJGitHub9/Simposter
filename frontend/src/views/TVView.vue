<script setup lang="ts">
import MovieGrid from '../components/movies/MovieGrid.vue'

const items = [
  { key: 'a', title: 'Foundation', year: 'S02', status: 'Ready' },
  { key: 'b', title: 'The Expanse', year: 'S06', status: 'Ready' },
  { key: 'c', title: 'Severance', year: 'S01', status: 'Queued' },
  { key: 'd', title: 'Andor', year: 'S01', status: 'Tweaking' }
]
</script>

<template>
  <div class="view">
    <MovieGrid heading="TV Shows" :items="items" />
  </div>
</template>

<style scoped>
.view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>
