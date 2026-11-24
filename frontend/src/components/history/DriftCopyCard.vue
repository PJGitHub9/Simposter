<script setup lang="ts">
// One server copy on History -> Changed Outside Simposter: what Simposter sent
// next to what the server has now, with Put back / Keep.
defineProps<{
  title: string
  assetLabel: string
  meta: string
  sentUrl: string
  currentUrl: string
  wide: boolean
  /** 'resend' | 'dismiss' while this card's own request runs. */
  busy: string | null
  disabled: boolean
  keepTitle: string
  showTitle?: boolean
}>()
const emit = defineEmits<{ resend: []; dismiss: [] }>()
</script>

<template>
  <div class="drift-card">
    <div v-if="showTitle !== false" class="drift-title">{{ title }} <span class="drift-asset">{{ assetLabel }}</span></div>
    <div class="drift-meta">{{ meta }}</div>
    <div class="drift-images" :class="{ wide }">
      <figure>
        <img :src="sentUrl" alt="" loading="lazy" @error="($event.target as HTMLImageElement).style.visibility = 'hidden'" />
        <figcaption>Simposter sent</figcaption>
      </figure>
      <figure>
        <img :src="currentUrl" alt="" loading="lazy" />
        <figcaption>On the server now</figcaption>
      </figure>
    </div>
    <div class="drift-actions">
      <button class="btn-retry-now" :disabled="disabled" @click="emit('resend')">
        {{ busy === 'resend' ? '...' : "Put Simposter's back" }}
      </button>
      <button class="btn-dismiss" :disabled="disabled" :title="keepTitle" @click="emit('dismiss')">
        {{ busy === 'dismiss' ? '...' : "Keep server's" }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.drift-card {
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.drift-title { font-weight: 600; }
.drift-meta { color: var(--text-secondary, #9aa4b2); font-size: 0.8rem; }
.drift-images { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.drift-images figure { margin: 0; }
.drift-images img { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 6px; background: rgba(0, 0, 0, 0.3); }
.drift-images figcaption { font-size: 0.75rem; text-align: center; color: var(--text-secondary, #9aa4b2); margin-top: 4px; }
.drift-images.wide img { aspect-ratio: 16 / 9; object-fit: contain; background: repeating-conic-gradient(rgba(255, 255, 255, 0.06) 0% 25%, transparent 0% 50%) 50% / 16px 16px; }
.drift-asset { margin-left: 6px; padding: 1px 7px; border-radius: 999px; font-size: 0.68rem; font-weight: 600; background: rgba(61, 214, 183, 0.15); color: var(--accent, #3dd6b7); vertical-align: middle; }
.drift-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.btn-retry-now {
  padding: 5px 12px;
  border: 1px solid rgba(61, 214, 183, 0.4);
  border-radius: 4px;
  background: rgba(61, 214, 183, 0.1);
  color: #3dd6b7;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-retry-now:hover:not(:disabled) { background: rgba(61, 214, 183, 0.2); border-color: rgba(61, 214, 183, 0.6); }
.btn-dismiss {
  padding: 5px 12px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 4px;
  background: rgba(148, 163, 184, 0.08);
  color: #94a3b8;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-dismiss:hover:not(:disabled) { background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.4); color: #ef4444; }
.btn-retry-now:disabled, .btn-dismiss:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
