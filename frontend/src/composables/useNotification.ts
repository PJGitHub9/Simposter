import { ref } from 'vue'

type NotificationType = 'success' | 'error' | 'info'

interface Notification {
  id: number
  message: string
  type: NotificationType
}

const notifications = ref<Notification[]>([])
let nextId = 1

export function useNotification() {
  const show = (message: string, type: NotificationType = 'info', duration = 3000) => {
    const id = nextId++
    notifications.value.push({ id, message, type })

    if (duration > 0) {
      setTimeout(() => {
        remove(id)
      }, duration)
    }
  }

  const remove = (id: number) => {
    const index = notifications.value.findIndex((n) => n.id === id)
    if (index !== -1) {
      notifications.value.splice(index, 1)
    }
  }

  const success = (message: string, duration = 3000) => show(message, 'success', duration)
  const error = (message: string, duration = 4000) => show(message, 'error', duration)
  const info = (message: string, duration = 3000) => show(message, 'info', duration)

  return {
    notifications,
    show,
    remove,
    success,
    error,
    info
  }
}
