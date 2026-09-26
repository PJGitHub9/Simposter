<script setup lang="ts">
import { ref, watch } from 'vue'

// Replaces the inline "which server(s)" <select> + separate checkbox/button
// row both EditorPane.vue and TvShowEditorPane.vue had -- user-reported
// directly that the toolbar felt cluttered once a merged item had several
// server targets to choose between. Genuinely multi-select (not just "one
// server or all") so a user can pick e.g. two of three linked servers.
const props = defineProps<{
  options: { server_id: string; label: string }[]
}>()

const emit = defineEmits<{
  close: []
  send: [serverIds: string[]]
}>()

const selected = ref<Set<string>>(new Set(props.options.map(o => o.server_id)))

// The modal is re-created fresh each time it's opened (v-if in the parent),
// but options can still change identity if the parent re-renders it while
// open (e.g. server resolution finishing async) -- keep the selection in
// sync with whatever's actually offered rather than pointing at a
// server_id that's no longer in the list.
watch(() => props.options, (opts) => {
  const validIds = new Set(opts.map(o => o.server_id))
  const next = new Set(Array.from(selected.value).filter(id => validIds.has(id)))
  if (next.size === 0) opts.forEach(o => next.add(o.server_id))
  selected.value = next
})

function toggle(serverId: string) {
  const next = new Set(selected.value)
  if (next.has(serverId)) next.delete(serverId)
  else next.add(serverId)
  selected.value = next
}

function selectAll() {
  selected.value = new Set(props.options.map(o => o.server_id))
}

function selectNone() {
  selected.value = new Set()
}

function confirm() {
  if (selected.value.size === 0) return
  emit('send', Array.from(selected.value))
}
</script>

<template>
  <Teleport to="body">
    <div class="send-modal-backdrop" @click.self="emit('close')">
      <div class="send-modal">
        <h3>Send to Media Server</h3>
        <p class="send-modal-hint">Choose which server(s) to send the current poster to.</p>
        <div class="send-modal-list">
          <label v-for="opt in options" :key="opt.server_id" class="send-modal-option">
            <input type="checkbox" :checked="selected.has(opt.server_id)" @change="toggle(opt.server_id)" />
            <span>{{ opt.label }}</span>
          </label>
        </div>
        <div class="send-modal-quick-actions">
          <button type="button" class="link-btn" @click="selectAll">Select All</button>
          <button type="button" class="link-btn" @click="selectNone">Select None</button>
        </div>
        <div class="send-modal-actions">
          <button type="button" class="secondary" @click="emit('close')">Cancel</button>
          <button type="button" class="primary" :disabled="selected.size === 0" @click="confirm">
            Send{{ selected.size > 1 ? ` to ${selected.size} servers` : '' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.send-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.send-modal {
  background: #14161f;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  padding: 24px;
  width: 100%;
  max-width: 380px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.send-modal h3 {
  margin: 0 0 6px;
  font-size: 16px;
  color: var(--text-primary, #eef2ff);
}

.send-modal-hint {
  margin: 0 0 16px;
  font-size: 12px;
  color: var(--muted, #a8b3cf);
}

.send-modal-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
  max-height: 260px;
  overflow-y: auto;
}

.send-modal-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  font-size: 14px;
  color: var(--text-primary, #eef2ff);
  transition: all 0.15s;
}

.send-modal-option:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(61, 214, 183, 0.3);
}

.send-modal-option input {
  margin: 0;
  accent-color: var(--accent, #3dd6b7);
}

.send-modal-quick-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.link-btn {
  background: none;
  border: none;
  color: #3dd6b7;
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}

.link-btn:hover {
  text-decoration: underline;
}

.send-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.send-modal-actions .secondary,
.send-modal-actions .primary {
  padding: 9px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
}

.send-modal-actions .secondary {
  background: rgba(255, 255, 255, 0.06);
  color: #dce6ff;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.12));
}

.send-modal-actions .secondary:hover {
  background: rgba(255, 255, 255, 0.1);
}

.send-modal-actions .primary {
  background: linear-gradient(120deg, #ff8a65, #ff7043);
  color: #fff;
}

.send-modal-actions .primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.send-modal-actions .primary:hover:not(:disabled) {
  transform: translateY(-1px);
}
</style>
