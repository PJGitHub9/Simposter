import { ref } from 'vue'

export type ScanState = {
  running: boolean
  visible: boolean
  progress: { processed: number; total: number }
  current: string
  log: string[]
}

const running = ref(false)
const visible = ref(false)
const progress = ref<{ processed: number; total: number }>({ processed: 0, total: 0 })
const current = ref('')
const log = ref<string[]>([])
const checking = ref(false)

export function useScanStore() {
  return {
    running,
    visible,
    progress,
    current,
    log,
    checking,
    applyStatus(status: any) {
      if (!status) return
      running.value = status.state === 'running'
      visible.value = running.value
      progress.value = {
        processed: status.processed || 0,
        total: status.total || 0,
      }
      current.value = status.current || ''
      if (status.log && Array.isArray(status.log)) {
        log.value = status.log
      }
      checking.value = false
    },
    reset() {
      running.value = false
      visible.value = false
      progress.value = { processed: 0, total: 0 }
      current.value = ''
      log.value = []
      checking.value = false
    },
  }
}
