<script setup lang="ts">
import { useNotification } from '../composables/useNotification'

const { notifications, remove } = useNotification()
</script>

<template>
  <div class="notification-container">
    <div
      v-for="notification in notifications"
      :key="notification.id"
      :class="['notification', notification.type]"
      @click="remove(notification.id)"
    >
      <div class="notification-icon">
        <svg v-if="notification.type === 'success'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
        <svg v-else-if="notification.type === 'error'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
        <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
      </div>
      <p class="notification-message">{{ notification.message }}</p>
    </div>
  </div>
</template>

<style scoped>
.notification-container {
  position: fixed;
  top: 80px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 400px;
}

.notification {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  background: rgba(17, 20, 30, 0.95);
  border: 1px solid var(--border);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(12px);
  cursor: pointer;
  animation: slideIn 0.3s ease;
  transition: all 0.2s;
}

.notification:hover {
  transform: translateX(-4px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5);
}

@keyframes slideIn {
  from {
    transform: translateX(400px);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.notification-icon {
  flex-shrink: 0;
}

.notification.success {
  border-color: rgba(61, 214, 183, 0.4);
}

.notification.success .notification-icon {
  color: #3dd6b7;
}

.notification.error {
  border-color: rgba(255, 107, 107, 0.4);
}

.notification.error .notification-icon {
  color: #ff6b6b;
}

.notification.info {
  border-color: rgba(91, 141, 238, 0.4);
}

.notification.info .notification-icon {
  color: #5b8dee;
}

.notification-message {
  font-size: 14px;
  color: #eef2ff;
  font-weight: 500;
}
</style>
