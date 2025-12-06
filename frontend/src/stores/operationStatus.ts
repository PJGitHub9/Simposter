import { ref } from 'vue'

export type OperationType = 'scan' | 'batch' | null
export type OperationState = 'idle' | 'running' | 'done' | 'error'

export type StatusData = {
  type: OperationType
  state: OperationState
  visible: boolean
  progress: { processed: number; total: number }
  currentMovie: string
  currentStep: string
  error: string | null
}

const type = ref<OperationType>(null)
const state = ref<OperationState>('idle')
const visible = ref(false)
const progress = ref<{ processed: number; total: number }>({ processed: 0, total: 0 })
const currentMovie = ref('')
const currentStep = ref('')
const error = ref<string | null>(null)
const checking = ref(false)
const activeRunStarted = ref(false)
let hideTimer: ReturnType<typeof setTimeout> | null = null

const scheduleHide = () => {
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = setTimeout(() => {
    visible.value = false
    currentMovie.value = ''
    currentStep.value = ''
    type.value = null
  }, 5000)
}

export function useOperationStatus() {
  return {
    type,
    state,
    visible,
    progress,
    currentMovie,
    currentStep,
    error,
    checking,

    applyStatus(status: any, operationType: OperationType) {
      if (!status) return

      const isRunning = status.state === 'running'
      const isDone = status.state === 'done'
      const isError = status.state === 'error'

      // Cancel hide timer when a new run starts
      if (isRunning && hideTimer) {
        clearTimeout(hideTimer)
        hideTimer = null
      }

      state.value = status.state || 'idle'
      type.value = operationType

      if (isRunning) {
        activeRunStarted.value = true
      }

      const showCompletion = (isDone || isError) && activeRunStarted.value

      // Keep overlay visible while running, or briefly after completion
      visible.value = isRunning || showCompletion

      progress.value = {
        processed: status.processed || 0,
        total: status.total || 0,
      }

      // For scan library, use 'current' field; for batch, use 'current_movie'
      currentMovie.value = status.current_movie || status.current || ''
      currentStep.value = status.current_step || ''
      error.value = status.error || null
      checking.value = false

      if (showCompletion) {
        activeRunStarted.value = false
        scheduleHide()
      } else if (!isRunning) {
        visible.value = false
      }
    },

    reset() {
      if (hideTimer) {
        clearTimeout(hideTimer)
        hideTimer = null
      }
      type.value = null
      state.value = 'idle'
      visible.value = false
      progress.value = { processed: 0, total: 0 }
      currentMovie.value = ''
      currentStep.value = ''
      error.value = null
      checking.value = false
      activeRunStarted.value = false
    },
  }
}
