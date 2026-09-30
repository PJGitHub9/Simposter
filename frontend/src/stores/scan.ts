import { ref } from 'vue'

export type ScanState = {
  running: boolean
  visible: boolean
  progress: { processed: number; total: number }
  current: string
  log: string[]
}

export interface ScanStatus {
  state: 'idle' | 'running' | 'done' | 'error'
  processed?: number
  total?: number
  current?: string
  log?: string[]
  finished_at?: string
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
    applyStatus(status: ScanStatus | null) {
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
      // The backend's /api/scan-progress response has never actually included
      // a "log" field (ScanStatus.log above was aspirational) -- this branch
      // was consequently dead for every real poll. The "X/Y (Z%) {message}"
      // line shown in the overlay's log list was only ever built by
      // SettingsView.vue's OWN separate, hand-rolled polling loop, which
      // constructed it from the same processed/total/current fields already
      // available here -- meaning it only ever updated while SettingsView.vue
      // itself stayed mounted. The moment a user navigated away mid-scan
      // (onBeforeRouteLeave stops that component's own poller), the overlay
      // -- correctly still visible everywhere via this shared store -- froze
      // at whatever the last update happened to be, even though the scan was
      // still genuinely progressing server-side. Centralizing the same line
      // construction here means ANY caller of applyStatus() (including
      // App.vue's own always-mounted poller, wired up below to take over
      // regardless of which page started the scan) keeps it live.
      if (status.log && Array.isArray(status.log)) {
        log.value = status.log
      } else if (isRunning && progress.value.total) {
        const pct = Math.min(100, Math.round((progress.value.processed / progress.value.total) * 100))
        log.value = [`${progress.value.processed}/${progress.value.total} (${pct}%) ${current.value}`]
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
