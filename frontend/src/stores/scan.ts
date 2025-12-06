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
const activeRunStarted = ref(false)
const lastFinishedAt = ref<string | null>(null)
let hideTimer: ReturnType<typeof setTimeout> | null = null

const scheduleHide = () => {
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = setTimeout(() => {
    visible.value = false
    log.value = []
    current.value = ''
  }, 5000)
}

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
      const isRunning = status.state === 'running'
      const isDone = status.state === 'done'

      // Only cancel hide timer when a new run is in progress
      if (isRunning && hideTimer) {
        clearTimeout(hideTimer)
        hideTimer = null
      }

      const wasRunning = running.value
      running.value = isRunning
      if (isRunning) {
        activeRunStarted.value = true
      }
      const showCompletion = isDone && activeRunStarted.value

      // Keep overlay visible while running, or briefly after a run completes we initiated
      visible.value = running.value || showCompletion
      progress.value = {
        processed: status.processed || 0,
        total: status.total || 0,
      }
      current.value = isDone ? '' : status.current || ''
      if (status.log && Array.isArray(status.log)) {
        log.value = status.log
      }
      checking.value = false
      if (showCompletion) {
        const processed = progress.value.processed
        const total = progress.value.total
        log.value = [`Done${total ? `: ${processed}/${total}` : ''}`]
        lastFinishedAt.value = status.finished_at || new Date().toISOString()
        activeRunStarted.value = false
        running.value = false
        scheduleHide()
      } else if (!running.value) {
        // If not running and not a fresh completion we started, keep overlay hidden
        visible.value = false
        if (isDone && status.finished_at) {
          lastFinishedAt.value = status.finished_at
        }
      }
    },
    reset() {
      if (hideTimer) {
        clearTimeout(hideTimer)
        hideTimer = null
      }
      running.value = false
      visible.value = false
      progress.value = { processed: 0, total: 0 }
      current.value = ''
      log.value = []
      checking.value = false
      activeRunStarted.value = false
      lastFinishedAt.value = null
    },
  }
}
