<script setup lang="ts">
import { useSettingsStore, type Theme } from '../stores/settings'
import { APP_VERSION } from '@/version'
import { useMovies } from '../composables/useMovies'
import { ref, onMounted, watch, computed, onBeforeUnmount, nextTick } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useScanStore } from '@/stores/scan'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { setSessionStorage, getSessionStorage } from '../composables/useSessionStorage'

// Import tab components
import GeneralTab from './settings/GeneralTab.vue'
import LibrariesTab from './settings/LibrariesTab.vue'
// IntegrationsTab removed
import SaveLocationsTab from './settings/SaveLocationsTab.vue'
import PerformanceTab from './settings/PerformanceTab.vue'
import AdvancedTab from './settings/AdvancedTab.vue'
import NotificationsTab from './settings/NotificationsTab.vue'

interface LibraryMapping {
  id: string
  title?: string
  displayName?: string
  autoGenerateEnabled?: boolean
  autoGeneratePresetId?: string | null
  autoGenerateTemplateId?: string | null
  webhookIgnoreLabels?: string[]
}

interface PlexLibrary {
  title: string
  key: string
  type: string
}

interface Movie {
  title: string
  year?: number
}

const settings = useSettingsStore()
const saved = ref('')
const allLibraryLabels = ref<Record<string, { type: 'movie' | 'show'; name: string; labels: string[] }>>({})
const labelsLoading = ref(false)
const { movies: moviesCache, moviesLoaded } = useMovies()
const scan = useScanStore()
const route = useRoute()
const router = useRouter()

// Active tab state - initialize from URL or default to 'general'
const activeTab = ref<'general' | 'libraries' | 'save-locations' | 'performance' | 'notifications' | 'advanced'>(
  (route.query.tab as any) || 'general'
)

// Track unsaved changes
const hasUnsavedChanges = ref(false)
const initialSettingsSnapshot = ref('')
const watchersEnabled = ref(false)

// Track which sections have unsaved changes
const sectionsWithChanges = ref({
  appearance: false,
  output: false,
  connections: false,
  apiKeys: false,
  imageQuality: false,
  performance: false,
  scheduler: false,
  automation: false
})

// Cooldown state to prevent rapid clicking
const scanCooldown = ref(false)
const scanningLibraryId = ref<string | null>(null)

// Computed property to ensure button disable state is reactive
const isScanInProgress = computed(() => scan.running.value || scan.checking.value || scanCooldown.value)

// Local state that will only be applied when save is clicked
const localTheme = ref<Theme>('neon')
const localPosterDensity = ref(20)
const localDeduplicateMovies = ref(false)
const localDefaultSort = ref('added-desc')
const localTimezone = ref('UTC')
const localSaveLocation = ref('')  // Legacy, kept for backwards compatibility
const localMovieSaveLocation = ref('/config/output/{library}/{title}.jpg')
const localTvShowSaveLocation = ref('/config/output/{library}/{title}.jpg')
const localTvShowSaveMode = ref('flat')
const localSaveBatch = ref(false)
const localDefaultLabelsToRemove = ref<Record<string, string[]>>({})
const localDefaultTvLabelsToRemove = ref<Record<string, string[]>>({})
const localPlexUrl = ref('')
const localPlexToken = ref('')
const localPlexLibrary = ref('')
const localLibraries = ref<LibraryMapping[]>([])
const savedLibraryIds = ref<Set<string>>(new Set())
const localTvShowLibraries = ref<LibraryMapping[]>([])
const savedTvShowLibraryIds = ref<Set<string>>(new Set())
const localTmdbApiKey = ref('')
const localTvdbApiKey = ref('')
const localFanartApiKey = ref('')
const apiOrderLocked = ref(true)
const apiOrder = ref<string[]>(['tmdb', 'fanart', 'tvdb'])
const draggingSource = ref<string | null>(null)
// Image Quality
const localOutputFormat = ref('jpg')
const localJpgQuality = ref(95)
const localPngCompression = ref(6)
const localWebpQuality = ref(90)
// Performance
const localConcurrentRenders = ref(2)
const localTmdbRateLimit = ref(40)
const localTvdbRateLimit = ref(20)
const localMemoryLimit = ref(2048)
const localUseOverlayCache = ref(true)
let scanPoller: number | null = null

// Automation settings
const localWebhookAutoSend = ref(true)
const localWebhookAutoLabels = ref('Overlay')
const localWebhookAlwaysRegenerateSeason = ref(false)

// Notification settings
const localDiscordEnabled = ref(false)
const localDiscordWebhookUrl = ref('')
const localDiscordNotifyLibraries = ref<string[]>([])
const localDiscordNotifyBatch = ref(true)
const localDiscordNotifyManual = ref(true)
const localDiscordNotifyWebhook = ref(true)
const localDiscordNotifyAutoGenerate = ref(true)
const localAppriseEnabled = ref(false)
const localAppriseUrls = ref<string[]>([])
const localAppriseNotifyLibraries = ref<string[]>([])
const localAppriseNotifyBatch = ref(true)
const localAppriseNotifyManual = ref(true)
const localAppriseNotifyWebhook = ref(true)
const localAppriseNotifyAutoGenerate = ref(true)

// API key testing
const testingApiKeys = ref<Record<string, boolean>>({})
const apiKeyTestResults = ref<Record<string, string>>({})

// Scheduler - using local refs that sync with store
const localSchedulerEnabled = ref(false)
const localSchedulerCronExpression = ref('0 1 * * *')
const localSchedulerLibraryIds = ref<string[]>([])
const schedulerNextRun = ref<string | null>(null)
const schedulerStatus = ref<string>('not_initialized')

// DB import/export states
const dbExporting = ref(false)
const dbImporting = ref(false)
const showDbImportModal = ref(false)
const dbImportText = ref('')

// Presets data for tag mappings
const presets = ref<Record<string, Record<string, any>>>({})

// Integration testing states (tracks by instance ID)
const testingInstances = ref<Set<string>>(new Set())
const testResults = ref<Record<string, string>>({})

// API key testing states
const testTmdbApiKey = ref<() => Promise<void>>()
const testTvdbApiKey = ref<() => Promise<void>>()
const testFanartApiKey = ref<() => Promise<void>>()
const testTmdbResult = ref('')
const testTvdbResult = ref('')
const testFanartResult = ref('')
const testTmdbLoading = ref(false)
const testTvdbLoading = ref(false)
const testFanartLoading = ref(false)

const testConnection = ref('')
const testConnectionLoading = ref(false)
const plexLibraries = ref<Array<{ title: string; key: string; type: string }>>([])

const loadLocalSettings = async () => {
  watchersEnabled.value = false

  localTheme.value = settings.theme.value
  localPosterDensity.value = settings.posterDensity.value
  localDeduplicateMovies.value = settings.deduplicateMovies.value
  localDefaultSort.value = settings.defaultSort.value || 'added-desc'
  localTimezone.value = settings.timezone.value || 'UTC'
  localSaveLocation.value = settings.saveLocation.value
  localMovieSaveLocation.value = settings.movieSaveLocation.value
  localTvShowSaveLocation.value = settings.tvShowSaveLocation.value
  localTvShowSaveMode.value = settings.tvShowSaveMode.value || 'flat'
  localSaveBatch.value = settings.saveBatchInSubfolder.value
  localDefaultLabelsToRemove.value = JSON.parse(JSON.stringify(settings.defaultLabelsToRemove.value))
  localDefaultTvLabelsToRemove.value = JSON.parse(JSON.stringify(settings.defaultTvLabelsToRemove.value))
  localPlexUrl.value = settings.plex.value.url
  localPlexToken.value = settings.plex.value.token
  localPlexLibrary.value = settings.plex.value.movieLibraryName || ''

  // Load movie libraries
  const hasPersistedLibraries = (settings.plex.value.libraryMappings || []).some((l: LibraryMapping) => l && l.id)
  const libraryMappings = hasPersistedLibraries
    ? settings.plex.value.libraryMappings
    : (settings.plex.value.movieLibraryNames || settings.plex.value.movieLibraryName
        ? (settings.plex.value.movieLibraryNames || [settings.plex.value.movieLibraryName]).map((n: string | undefined, idx: number) => ({
            id: n || '',
            title: n || '',
            displayName: n || `Library ${idx + 1}`
          }))
        : [{ id: '', title: '', displayName: '' }]
      )

  localLibraries.value = JSON.parse(JSON.stringify(libraryMappings)) as LibraryMapping[]

  savedLibraryIds.value = hasPersistedLibraries
    ? new Set(
        (libraryMappings || [])
          .map((l: LibraryMapping) => (l && l.id ? String(l.id) : ''))
          .filter(Boolean)
      )
    : new Set()

  // Load TV show libraries
  const hasPersistedTvShowLibraries = (settings.plex.value.tvShowLibraryMappings || []).some((l: LibraryMapping) => l && l.id)
  const tvShowLibraryMappings = hasPersistedTvShowLibraries
    ? settings.plex.value.tvShowLibraryMappings
    : (settings.plex.value.tvShowLibraryNames || settings.plex.value.tvShowLibraryName
        ? (settings.plex.value.tvShowLibraryNames || [settings.plex.value.tvShowLibraryName]).map((n: string | undefined, idx: number) => ({
            id: n || '',
            title: n || '',
            displayName: n || `TV Library ${idx + 1}`
          }))
        : [{ id: '', title: '', displayName: '' }]
      )

  localTvShowLibraries.value = JSON.parse(JSON.stringify(tvShowLibraryMappings)) as LibraryMapping[]

  savedTvShowLibraryIds.value = hasPersistedTvShowLibraries
    ? new Set(
        (tvShowLibraryMappings || [])
          .map((l: LibraryMapping) => (l && l.id ? String(l.id) : ''))
          .filter(Boolean)
      )
    : new Set()

  localTmdbApiKey.value = settings.tmdb.value.apiKey
  localTvdbApiKey.value = settings.tvdb.value.apiKey
  localFanartApiKey.value = settings.fanart.value.apiKey
  localOutputFormat.value = settings.imageQuality.value.outputFormat
  localJpgQuality.value = settings.imageQuality.value.jpgQuality
  localPngCompression.value = settings.imageQuality.value.pngCompression
  localWebpQuality.value = settings.imageQuality.value.webpQuality
  localConcurrentRenders.value = settings.performance.value.concurrentRenders
  localTmdbRateLimit.value = settings.performance.value.tmdbRateLimit
  localTvdbRateLimit.value = settings.performance.value.tvdbRateLimit
  localMemoryLimit.value = settings.performance.value.memoryLimit
  localUseOverlayCache.value = settings.performance.value.useOverlayCache
  localSchedulerEnabled.value = settings.scheduler.value.enabled
  localSchedulerCronExpression.value = settings.scheduler.value.cronExpression
  localSchedulerLibraryIds.value = settings.scheduler.value.libraryIds || []
  localWebhookAutoSend.value = settings.automation?.value?.webhookAutoSend ?? true
  localWebhookAutoLabels.value = settings.automation?.value?.webhookAutoLabels ?? 'Overlay'
  localWebhookAlwaysRegenerateSeason.value = settings.automation?.value?.webhookAlwaysRegenerateSeason ?? false

  // Notification settings
  localDiscordEnabled.value = settings.notifications?.value?.discordEnabled ?? false
  localDiscordWebhookUrl.value = settings.notifications?.value?.discordWebhookUrl ?? ''
  localDiscordNotifyLibraries.value = settings.notifications?.value?.discordNotifyLibraries ?? []
  localDiscordNotifyBatch.value = settings.notifications?.value?.discordNotifyBatch ?? true
  localDiscordNotifyManual.value = settings.notifications?.value?.discordNotifyManual ?? true
  localDiscordNotifyWebhook.value = settings.notifications?.value?.discordNotifyWebhook ?? true
  localDiscordNotifyAutoGenerate.value = settings.notifications?.value?.discordNotifyAutoGenerate ?? true
  localAppriseEnabled.value = settings.notifications?.value?.appriseEnabled ?? false
  localAppriseUrls.value = settings.notifications?.value?.appriseUrls ?? []
  localAppriseNotifyLibraries.value = settings.notifications?.value?.appriseNotifyLibraries ?? []
  localAppriseNotifyBatch.value = settings.notifications?.value?.appriseNotifyBatch ?? true
  localAppriseNotifyManual.value = settings.notifications?.value?.appriseNotifyManual ?? true
  localAppriseNotifyWebhook.value = settings.notifications?.value?.appriseNotifyWebhook ?? true
  localAppriseNotifyAutoGenerate.value = settings.notifications?.value?.appriseNotifyAutoGenerate ?? true

  await nextTick()
}

const captureSettingsSnapshot = () => {
  initialSettingsSnapshot.value = JSON.stringify({
    theme: localTheme.value,
    posterDensity: localPosterDensity.value,
    deduplicateMovies: localDeduplicateMovies.value,
    defaultSort: localDefaultSort.value,
    timezone: localTimezone.value,
    saveLocation: localSaveLocation.value,
    movieSaveLocation: localMovieSaveLocation.value,
    tvShowSaveLocation: localTvShowSaveLocation.value,
    tvShowSaveMode: localTvShowSaveMode.value,
    saveBatch: localSaveBatch.value,
    defaultLabelsToRemove: localDefaultLabelsToRemove.value,
    defaultTvLabelsToRemove: localDefaultTvLabelsToRemove.value,
    plexUrl: localPlexUrl.value,
    plexToken: localPlexToken.value,
    libraries: localLibraries.value,
    tvShowLibraries: localTvShowLibraries.value,
    tmdbApiKey: localTmdbApiKey.value,
    tvdbApiKey: localTvdbApiKey.value,
    fanartApiKey: localFanartApiKey.value,
    apiOrder: apiOrder.value,
    outputFormat: localOutputFormat.value,
    jpgQuality: localJpgQuality.value,
    pngCompression: localPngCompression.value,
    webpQuality: localWebpQuality.value,
    concurrentRenders: localConcurrentRenders.value,
    tmdbRateLimit: localTmdbRateLimit.value,
    tvdbRateLimit: localTvdbRateLimit.value,
    memoryLimit: localMemoryLimit.value,
    useOverlayCache: localUseOverlayCache.value,
    schedulerEnabled: localSchedulerEnabled.value,
    schedulerCronExpression: localSchedulerCronExpression.value,
    schedulerLibraryIds: localSchedulerLibraryIds.value,
    webhookAutoSend: localWebhookAutoSend.value,
    webhookAutoLabels: localWebhookAutoLabels.value,
    webhookAlwaysRegenerateSeason: localWebhookAlwaysRegenerateSeason.value,
    discordEnabled: localDiscordEnabled.value,
    discordWebhookUrl: localDiscordWebhookUrl.value,
    discordNotifyLibraries: localDiscordNotifyLibraries.value,
    discordNotifyBatch: localDiscordNotifyBatch.value,
    discordNotifyManual: localDiscordNotifyManual.value,
    discordNotifyWebhook: localDiscordNotifyWebhook.value,
    discordNotifyAutoGenerate: localDiscordNotifyAutoGenerate.value,
    appriseEnabled: localAppriseEnabled.value,
    appriseUrls: localAppriseUrls.value,
    appriseNotifyLibraries: localAppriseNotifyLibraries.value,
    appriseNotifyBatch: localAppriseNotifyBatch.value,
    appriseNotifyManual: localAppriseNotifyManual.value,
    appriseNotifyWebhook: localAppriseNotifyWebhook.value,
    appriseNotifyAutoGenerate: localAppriseNotifyAutoGenerate.value
  })
  hasUnsavedChanges.value = false

  sectionsWithChanges.value.appearance = false
  sectionsWithChanges.value.output = false
  sectionsWithChanges.value.connections = false
  sectionsWithChanges.value.apiKeys = false
  sectionsWithChanges.value.imageQuality = false
  sectionsWithChanges.value.performance = false
  sectionsWithChanges.value.scheduler = false
  sectionsWithChanges.value.automation = false

  setTimeout(() => {
    watchersEnabled.value = true
  }, 100)
}

const checkForChanges = () => {
  const currentSnapshot = JSON.stringify({
    theme: localTheme.value,
    posterDensity: localPosterDensity.value,
    deduplicateMovies: localDeduplicateMovies.value,
    defaultSort: localDefaultSort.value,
    timezone: localTimezone.value,
    saveLocation: localSaveLocation.value,
    movieSaveLocation: localMovieSaveLocation.value,
    tvShowSaveLocation: localTvShowSaveLocation.value,
    tvShowSaveMode: localTvShowSaveMode.value,
    saveBatch: localSaveBatch.value,
    defaultLabelsToRemove: localDefaultLabelsToRemove.value,
    defaultTvLabelsToRemove: localDefaultTvLabelsToRemove.value,
    plexUrl: localPlexUrl.value,
    plexToken: localPlexToken.value,
    libraries: localLibraries.value,
    tvShowLibraries: localTvShowLibraries.value,
    tmdbApiKey: localTmdbApiKey.value,
    tvdbApiKey: localTvdbApiKey.value,
    fanartApiKey: localFanartApiKey.value,
    apiOrder: apiOrder.value,
    outputFormat: localOutputFormat.value,
    jpgQuality: localJpgQuality.value,
    pngCompression: localPngCompression.value,
    webpQuality: localWebpQuality.value,
    concurrentRenders: localConcurrentRenders.value,
    tmdbRateLimit: localTmdbRateLimit.value,
    tvdbRateLimit: localTvdbRateLimit.value,
    memoryLimit: localMemoryLimit.value,
    useOverlayCache: localUseOverlayCache.value,
    schedulerEnabled: localSchedulerEnabled.value,
    schedulerCronExpression: localSchedulerCronExpression.value,
    schedulerLibraryIds: localSchedulerLibraryIds.value,
    webhookAutoSend: localWebhookAutoSend.value,
    webhookAutoLabels: localWebhookAutoLabels.value,
    webhookAlwaysRegenerateSeason: localWebhookAlwaysRegenerateSeason.value,
    discordEnabled: localDiscordEnabled.value,
    discordWebhookUrl: localDiscordWebhookUrl.value,
    discordNotifyLibraries: localDiscordNotifyLibraries.value,
    discordNotifyBatch: localDiscordNotifyBatch.value,
    discordNotifyManual: localDiscordNotifyManual.value,
    discordNotifyWebhook: localDiscordNotifyWebhook.value,
    discordNotifyAutoGenerate: localDiscordNotifyAutoGenerate.value,
    appriseEnabled: localAppriseEnabled.value,
    appriseUrls: localAppriseUrls.value,
    appriseNotifyLibraries: localAppriseNotifyLibraries.value,
    appriseNotifyBatch: localAppriseNotifyBatch.value,
    appriseNotifyManual: localAppriseNotifyManual.value,
    appriseNotifyWebhook: localAppriseNotifyWebhook.value,
    appriseNotifyAutoGenerate: localAppriseNotifyAutoGenerate.value
  })
  hasUnsavedChanges.value = currentSnapshot !== initialSettingsSnapshot.value

  if (!initialSettingsSnapshot.value) return
  const initial = JSON.parse(initialSettingsSnapshot.value)

  sectionsWithChanges.value.appearance =
    localTheme.value !== initial.theme ||
    localPosterDensity.value !== initial.posterDensity ||
    localDeduplicateMovies.value !== initial.deduplicateMovies ||
    localDefaultSort.value !== initial.defaultSort

  sectionsWithChanges.value.output =
    localSaveLocation.value !== initial.saveLocation ||
    localMovieSaveLocation.value !== initial.movieSaveLocation ||
    localTvShowSaveLocation.value !== initial.tvShowSaveLocation ||
    localTvShowSaveMode.value !== initial.tvShowSaveMode ||
    localSaveBatch.value !== initial.saveBatch

  sectionsWithChanges.value.connections =
    localPlexUrl.value !== initial.plexUrl ||
    localPlexToken.value !== initial.plexToken ||
    JSON.stringify(localLibraries.value) !== JSON.stringify(initial.libraries) ||
    JSON.stringify(localTvShowLibraries.value) !== JSON.stringify(initial.tvShowLibraries)

  sectionsWithChanges.value.performance =
    localConcurrentRenders.value !== initial.concurrentRenders ||
    localUseOverlayCache.value !== initial.useOverlayCache

  sectionsWithChanges.value.scheduler =
    localSchedulerEnabled.value !== initial.schedulerEnabled ||
    localSchedulerCronExpression.value !== initial.schedulerCronExpression ||
    JSON.stringify(localSchedulerLibraryIds.value) !== JSON.stringify(initial.schedulerLibraryIds)


}

const saveSettings = async () => {
  settings.theme.value = localTheme.value
  settings.posterDensity.value = localPosterDensity.value
  settings.deduplicateMovies.value = localDeduplicateMovies.value
  settings.defaultSort.value = localDefaultSort.value
  settings.timezone.value = localTimezone.value
  settings.saveLocation.value = localSaveLocation.value
  settings.movieSaveLocation.value = localMovieSaveLocation.value
  settings.tvShowSaveLocation.value = localTvShowSaveLocation.value
  settings.tvShowSaveMode.value = localTvShowSaveMode.value
  settings.saveBatchInSubfolder.value = localSaveBatch.value
  settings.defaultLabelsToRemove.value = JSON.parse(JSON.stringify(localDefaultLabelsToRemove.value))
  settings.defaultTvLabelsToRemove.value = JSON.parse(JSON.stringify(localDefaultTvLabelsToRemove.value))
  settings.apiOrder.value = [...apiOrder.value]
  const libs = localLibraries.value.filter(l => l.id || l.title)
  const tvShowLibs = localTvShowLibraries.value.filter(l => l.id || l.title)
  settings.plex.value = {
    url: localPlexUrl.value,
    token: localPlexToken.value,
    movieLibraryName: libs[0]?.id || localPlexLibrary.value || '',
    movieLibraryNames: libs.length > 0 ? libs.map(l => l.id) : undefined,
    libraryMappings: libs.map(l => ({
      id: l.id || '',
      title: l.title || l.id || '',
      displayName: l.displayName || l.title || l.id || '',
      autoGenerateEnabled: l.autoGenerateEnabled || false,
      autoGeneratePresetId: l.autoGeneratePresetId || null,
      autoGenerateTemplateId: l.autoGenerateTemplateId || null,
      webhookIgnoreLabels: l.webhookIgnoreLabels || [],
    })),
    tvShowLibraryName: tvShowLibs[0]?.id || '',
    tvShowLibraryNames: tvShowLibs.length > 0 ? tvShowLibs.map(l => l.id) : undefined,
    tvShowLibraryMappings: tvShowLibs.map(l => ({
      id: l.id || '',
      title: l.title || l.id || '',
      displayName: l.displayName || l.title || l.id || '',
      autoGenerateEnabled: l.autoGenerateEnabled || false,
      autoGeneratePresetId: l.autoGeneratePresetId || null,
      autoGenerateTemplateId: l.autoGenerateTemplateId || null,
      webhookIgnoreLabels: l.webhookIgnoreLabels || [],
    }))
  }
  settings.tmdb.value = { apiKey: localTmdbApiKey.value }
  settings.tvdb.value = { apiKey: localTvdbApiKey.value, comingSoon: settings.tvdb.value.comingSoon }
  settings.fanart.value = { apiKey: localFanartApiKey.value }
  settings.imageQuality.value = {
    outputFormat: localOutputFormat.value,
    jpgQuality: localJpgQuality.value,
    pngCompression: localPngCompression.value,
    webpQuality: localWebpQuality.value
  }
  settings.performance.value = {
    concurrentRenders: localConcurrentRenders.value,
    tmdbRateLimit: localTmdbRateLimit.value,
    tvdbRateLimit: localTvdbRateLimit.value,
    memoryLimit: localMemoryLimit.value,
    useOverlayCache: localUseOverlayCache.value
  }
  settings.scheduler.value = {
    enabled: localSchedulerEnabled.value,
    cronExpression: localSchedulerCronExpression.value,
    libraryIds: localSchedulerLibraryIds.value
  }
  settings.automation.value = {
    webhookAutoSend: localWebhookAutoSend.value,
    webhookAutoLabels: localWebhookAutoLabels.value,
    webhookAlwaysRegenerateSeason: localWebhookAlwaysRegenerateSeason.value
  }
  settings.notifications.value = {
    discordEnabled: localDiscordEnabled.value,
    discordWebhookUrl: localDiscordWebhookUrl.value,
    discordNotifyLibraries: localDiscordNotifyLibraries.value,
    discordNotifyBatch: localDiscordNotifyBatch.value,
    discordNotifyManual: localDiscordNotifyManual.value,
    discordNotifyWebhook: localDiscordNotifyWebhook.value,
    discordNotifyAutoGenerate: localDiscordNotifyAutoGenerate.value,
    appriseEnabled: localAppriseEnabled.value,
    appriseUrls: localAppriseUrls.value,
    appriseNotifyLibraries: localAppriseNotifyLibraries.value,
    appriseNotifyBatch: localAppriseNotifyBatch.value,
    appriseNotifyManual: localAppriseNotifyManual.value,
    appriseNotifyWebhook: localAppriseNotifyWebhook.value,
    appriseNotifyAutoGenerate: localAppriseNotifyAutoGenerate.value
  }

  await settings.save()

  if (!settings.error.value) {
    await updateScheduler()
  }

  saved.value = settings.error.value ? `Error: ${settings.error.value}` : 'Saved!'
  setTimeout(() => (saved.value = ''), 1500)
  savedLibraryIds.value = new Set(localLibraries.value.filter(l => l.id).map(l => String(l.id)))
  savedTvShowLibraryIds.value = new Set(localTvShowLibraries.value.filter(l => l.id).map(l => String(l.id)))

  watchersEnabled.value = false
  await nextTick()
  captureSettingsSnapshot()
}

const testPlexConnection = async () => {
  testConnectionLoading.value = true
  testConnection.value = 'Testing connection...'
  plexLibraries.value = []

  try {
    const apiBase = getApiBase()
    const params = new URLSearchParams({
      plex_url: localPlexUrl.value,
      plex_token: localPlexToken.value
    })
    const res = await fetch(`${apiBase}/api/test-plex-connection?${params}`)
    const data = await res.json()

    if (data.status === 'ok') {
      plexLibraries.value = data.sections || []
      const movieLibs = plexLibraries.value.filter(s => s.type === 'movie')
      const tvShowLibs = plexLibraries.value.filter(s => s.type === 'show')
      const movieSectionsList = movieLibs.map((s: PlexLibrary) => s.title).join(', ')
      const tvShowSectionsList = tvShowLibs.map((s: PlexLibrary) => s.title).join(', ')
      testConnection.value = `✓ Connected! Found ${movieLibs.length} movie libraries: ${movieSectionsList}${tvShowLibs.length > 0 ? ` and ${tvShowLibs.length} TV show libraries: ${tvShowSectionsList}` : ''}`
      if (movieLibs.length > 0) {
        if (!localLibraries.value.length || localLibraries.value.every(l => !l.id)) {
          localLibraries.value = movieLibs.map((s: PlexLibrary, idx: number) => ({
            id: s.key,
            title: s.title,
            displayName: s.title || `Library ${idx + 1}`,
          }))
        }
      }
      if (tvShowLibs.length > 0) {
        if (!localTvShowLibraries.value.length || localTvShowLibraries.value.every(l => !l.id)) {
          localTvShowLibraries.value = tvShowLibs.map((s: PlexLibrary, idx: number) => ({
            id: s.key,
            title: s.title,
            displayName: s.title || `TV Library ${idx + 1}`,
          }))
        }
      }
    } else {
      testConnection.value = `✗ ${data.error}: ${data.message}`
    }
  } catch (e) {
    testConnection.value = `✗ Connection failed: ${e instanceof Error ? e.message : 'Unknown error'}`
  } finally {
    testConnectionLoading.value = false
    setTimeout(() => (testConnection.value = ''), 10000)
  }
}

const testApiKeys = async () => {
  testingApiKeys.value = { tmdb: true, tvdb: true, fanart: true }
  apiKeyTestResults.value = {}

  try {
    const apiBase = getApiBase()
    const res = await fetch(`${apiBase}/api/test-api-keys`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tmdb: localTmdbApiKey.value,
        tvdb: localTvdbApiKey.value,
        fanart: localFanartApiKey.value
      })
    })
    const data = await res.json()

    if (res.ok) {
      const results = []
      if (data.tmdb?.status === 'ok') results.push('✓ TMDb')
      else if (data.tmdb?.status === 'error') results.push('✗ TMDb')
      if (data.tvdb?.status === 'ok') results.push('✓ TVDB')
      else if (data.tvdb?.status === 'error') results.push('✗ TVDB')
      if (data.fanart?.status === 'ok') results.push('✓ Fanart.tv')
      else if (data.fanart?.status === 'error') results.push('✗ Fanart.tv')
      apiKeyTestResults.value.all = results.length > 0 ? results.join(' | ') : 'No keys to test'
    } else {
      apiKeyTestResults.value.all = `Error: ${data.detail || 'Failed to test API keys'}`
    }
  } catch (e) {
    apiKeyTestResults.value.all = `Error: ${e instanceof Error ? e.message : 'Unknown error'}`
  } finally {
    testingApiKeys.value = {}
    setTimeout(() => { apiKeyTestResults.value = {} }, 10000)
  }
}

const testSingleApiKey = async (keyType: string, apiKey: string) => {
  if (!apiKey) return

  testingApiKeys.value[keyType] = true

  try {
    const apiBase = getApiBase()
    let endpoint: string
    let options: RequestInit

    if (keyType === 'tmdb') {
      endpoint = `/api/test-tmdb?api_key=${encodeURIComponent(apiKey)}`
      options = { method: 'GET' }
    } else if (keyType === 'tvdb') {
      endpoint = `/api/test-tvdb?api_key=${encodeURIComponent(apiKey)}`
      options = { method: 'GET' }
    } else if (keyType === 'fanart') {
      endpoint = '/api/test-fanart'
      options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey })
      }
    } else {
      return
    }

    const res = await fetch(`${apiBase}${endpoint}`, options)
    const data = await res.json()

    if (data.status === 'ok') {
      apiKeyTestResults.value[keyType] = `✓ Valid${data.example ? ` (${data.example})` : ''}`
    } else {
      apiKeyTestResults.value[keyType] = `Error: ${data.error || 'Invalid key'}`
    }
  } catch (e) {
    apiKeyTestResults.value[keyType] = `Error: ${e instanceof Error ? e.message : 'Unknown error'}`
  } finally {
    testingApiKeys.value[keyType] = false
    setTimeout(() => {
      apiKeyTestResults.value[keyType] = ''
    }, 10000)
  }
}

const clearCache = () => {
  if (scan.running.value) {
    saved.value = 'Scan in progress - cannot clear session cache'
    setTimeout(() => (saved.value = ''), 2000)
    return
  }
  if (!window.confirm('This will clear cached movies/posters/labels from this browser session. Continue?')) {
    return
  }
  try {
    sessionStorage.removeItem('simposter-poster-cache')
    sessionStorage.removeItem('simposter-labels-cache')
    sessionStorage.removeItem('simposter-movies-cache')
    saved.value = 'Session cache cleared!'
    setTimeout(() => (saved.value = ''), 1500)
  } catch (e) {
    console.error('Failed to clear cache', e)
  }
}

const scanLibrary = async (libraryId?: string) => {
  if (scan.running.value || scan.checking.value) {
    saved.value = 'Scan already in progress'
    setTimeout(() => (saved.value = ''), 2000)
    return
  }

  if (scanCooldown.value) {
    saved.value = 'Please wait before starting another scan'
    setTimeout(() => (saved.value = ''), 2000)
    return
  }

  try {
    scan.running.value = true
    scanningLibraryId.value = libraryId || null
    scanCooldown.value = true
    setTimeout(() => {
      if (!scan.running.value && !scan.checking.value) {
        scanCooldown.value = false
        scanningLibraryId.value = null
      } else {
        const checkScanStatus = () => {
          if (!scan.running.value && !scan.checking.value) {
            scanCooldown.value = false
            scanningLibraryId.value = null
          } else {
            setTimeout(checkScanStatus, 5000)
          }
        }
        setTimeout(checkScanStatus, 5000)
      }
    }, 10000)
    saved.value = libraryId ? `Rescanning library ${libraryId}...` : 'Rescanning all libraries...'
    scan.visible.value = true
    scan.log.value = ['Starting rescan...']
    scan.progress.value = { processed: 0, total: 0 }
    scan.current.value = ''
    startScanPolling()

    const apiBase = getApiBase()
    const url = new URL(`${apiBase}/api/scan-library`)
    if (libraryId) url.searchParams.set('library_id', libraryId)
    const res = await fetch(url.toString(), { method: 'POST' })
    if (!res.ok) {
      if (res.status === 409) {
        throw new Error('Scan already in progress on server')
      }
      throw new Error(`API error ${res.status}`)
    }
    const data = await res.json()

    if (Array.isArray(data.movies)) {
      moviesCache.value = data.movies
      moviesLoaded.value = true
      scan.progress.value = { processed: data.movies.length, total: data.movies.length }
      scan.log.value = data.movies.slice(0, 20).map((m: Movie) => `${m.title}${m.year ? ` (${m.year})` : ''}`)
      if (data.movies.length > 20) {
        scan.log.value.push(`...and ${data.movies.length - 20} more`)
      }
      try {
        setSessionStorage('movies-cache', data.movies)
      } catch (err) {
        console.error('Failed to cache movies', err)
      }
    }

    if (data.posters && typeof sessionStorage !== 'undefined') {
      try {
        setSessionStorage('poster-cache', data.posters)
      } catch (err) {
        console.error('Failed to cache posters', err)
      }
    }

    if (data.labels && typeof sessionStorage !== 'undefined') {
      try {
        setSessionStorage('labels-cache', data.labels)
      } catch (err) {
        console.error('Failed to cache labels', err)
      }
    }

    saved.value = `Rescanned ${data.count || 0} items`
    setTimeout(() => (saved.value = ''), 2000)
    scan.log.value = [`Done: ${scan.progress.value.processed || data.count || 0} items`]
    scan.running.value = false
    scanCooldown.value = false
    setTimeout(() => {
      scan.visible.value = false
      scan.log.value = []
      scan.current.value = ''
    }, 2000)
  } catch (e) {
    saved.value = `Scan failed: ${e instanceof Error ? e.message : 'Unknown error'}`
    scan.log.value = [`Scan failed: ${e instanceof Error ? e.message : 'Unknown error'}`]
    setTimeout(() => {
      saved.value = ''
      scan.visible.value = false
    }, 3000)
  }
  stopScanPolling()
  scan.running.value = false
  scanCooldown.value = false
}

const fetchSchedulerStatus = async () => {
  try {
    const apiBase = getApiBase()
    const res = await fetch(`${apiBase}/api/scheduler/library-scan`)
    if (!res.ok) return
    const data = await res.json()

    if (data.settings) {
      localSchedulerEnabled.value = data.settings.enabled
      localSchedulerCronExpression.value = data.settings.cronExpression || '0 1 * * *'
      localSchedulerLibraryIds.value = data.settings.libraryIds || []
    }

    if (data.status === 'scheduled' && data.schedule) {
      schedulerNextRun.value = data.schedule.next_run_time || null
    } else {
      schedulerNextRun.value = null
    }
  } catch (e) {
    console.error('Failed to fetch scheduler status:', e)
  }
}

const updateScheduler = async () => {
  try {
    const apiBase = getApiBase()

    if (localSchedulerEnabled.value) {
      const res = await fetch(`${apiBase}/api/scheduler/library-scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cron_expression: localSchedulerCronExpression.value,
          library_ids: localSchedulerLibraryIds.value
        })
      })

      if (!res.ok) {
        const error = await res.json()
        throw new Error(error.detail || 'Failed to schedule scan')
      }

      const data = await res.json()
      schedulerNextRun.value = data.schedule?.next_run_time || null
      saved.value = 'Library scan scheduled successfully'
    } else {
      const res = await fetch(`${apiBase}/api/scheduler/library-scan`, {
        method: 'DELETE'
      })

      if (!res.ok) throw new Error('Failed to cancel schedule')

      schedulerNextRun.value = null
      saved.value = 'Library scan schedule cancelled'
    }

    setTimeout(() => (saved.value = ''), 2000)
  } catch (e) {
    saved.value = `Scheduler error: ${e instanceof Error ? e.message : 'Unknown error'}`
    setTimeout(() => (saved.value = ''), 3000)
  }
}

const clearBackendCache = async () => {
  if (scan.running.value || scan.checking.value) {
    saved.value = 'Scan in progress - cannot clear cache'
    setTimeout(() => (saved.value = ''), 2000)
    return
  }
  if (!window.confirm('⚠️ This will delete backend cache (posters + DB cache). Continue?')) {
    return
  }
  try {
    const apiBase = getApiBase()
    const res = await fetch(`${apiBase}/api/cache`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    saved.value = `Backend cache cleared (${data.removed_posters || 0} poster files removed)`
    sessionStorage.removeItem('simposter-poster-cache')
    sessionStorage.removeItem('simposter-labels-cache')
    sessionStorage.removeItem('simposter-movies-cache')
  } catch (e) {
    saved.value = `Failed to clear backend cache: ${e instanceof Error ? e.message : 'Unknown error'}`
  } finally {
    setTimeout(() => (saved.value = ''), 2500)
  }
}

const handleDbExport = async () => {
  dbExporting.value = true
  try {
    const apiBase = getApiBase()
    const res = await fetch(`${apiBase}/api/database/export`)
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = await res.json()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const stamp = new Date().toISOString().replace(/[:.]/g, '-')
    a.download = `simposter-db-backup-${stamp}.json`
    a.click()
    URL.revokeObjectURL(url)
    saved.value = 'Database exported'
  } catch (e) {
    saved.value = `Export failed: ${e instanceof Error ? e.message : 'Unknown error'}`
  } finally {
    dbExporting.value = false
    setTimeout(() => (saved.value = ''), 2000)
  }
}

const handleDbImport = async () => {
  if (!dbImportText.value.trim()) {
    saved.value = 'Paste database JSON to import'
    setTimeout(() => (saved.value = ''), 2000)
    return
  }
  if (!window.confirm('⚠️ This will completely replace your current database. Are you sure?')) {
    return
  }
  dbImporting.value = true
  try {
    const json = JSON.parse(dbImportText.value)
    const apiBase = getApiBase()
    const res = await fetch(`${apiBase}/api/database/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(json)
    })
    if (!res.ok) throw new Error(`API error ${res.status}`)
    saved.value = 'Database imported successfully! Reloading...'
    showDbImportModal.value = false
    dbImportText.value = ''
    setTimeout(() => {
      window.location.reload()
    }, 2000)
  } catch (e) {
    saved.value = `Import failed: ${e instanceof Error ? e.message : 'Invalid JSON'}`
  } finally {
    dbImporting.value = false
    setTimeout(() => (saved.value = ''), 2500)
  }
}

const startScanPolling = () => {
  stopScanPolling()
  const apiBase = getApiBase()
  scanPoller = window.setInterval(async () => {
    try {
      const res = await fetch(`${apiBase}/api/scan-progress`)
      if (!res.ok) return
      const data = await res.json()
      if (data.total) {
        scan.progress.value = { processed: data.processed || 0, total: data.total || 0 }
      }
      if (data.current) {
        scan.current.value = data.current
      }
      if (scan.progress.value.total) {
        const pct = Math.min(100, Math.round((scan.progress.value.processed / scan.progress.value.total) * 100))
        const line = `${scan.progress.value.processed}/${scan.progress.value.total} (${pct}%) ${scan.current.value || ''}`
        scan.log.value = [line]
      }
      if (data.state && data.state !== 'running') {
        stopScanPolling()
        scan.running.value = false
        scan.visible.value = false
      }
    } catch {
      // ignore polling errors
    }
  }, 1000)
}

const stopScanPolling = () => {
  if (scanPoller !== null) {
    clearInterval(scanPoller)
    scanPoller = null
  }
}

const fetchPresets = async () => {
  try {
    const apiBase = getApiBase()
    const response = await fetch(`${apiBase}/api/presets`)
    if (response.ok) {
      const data = await response.json()
      presets.value = data || {}
    }
  } catch (error) {
    console.error('Failed to fetch presets:', error)
    presets.value = {}
  }
}

onMounted(async () => {
  watchersEnabled.value = false

  if (!settings.loaded.value) {
    await settings.load()
  }

  await loadLocalSettings()
  await fetchPresets()

  if (settings.plex.value.url && settings.plex.value.token) {
    await testPlexConnection()
  }

  await fetchSchedulerStatus()

  await nextTick()
  captureSettingsSnapshot()
})

watch(
  () => settings.loaded.value,
  async (val) => {
    if (val) {
      watchersEnabled.value = false
      await loadLocalSettings()

      if (settings.plex.value.url && settings.plex.value.token) {
        await testPlexConnection()
      }

      await nextTick()
      captureSettingsSnapshot()
    }
  }
)

watch([
  localTheme,
  localPosterDensity,
  localDeduplicateMovies,
  localDefaultSort,
  localTimezone,
  localSaveLocation,
  localMovieSaveLocation,
  localTvShowSaveLocation,
  localSaveBatch,
  localDefaultLabelsToRemove,
  localDefaultTvLabelsToRemove,
  localPlexUrl,
  localPlexToken,
  localLibraries,
  localTvShowLibraries,
  localTmdbApiKey,
  localTvdbApiKey,
  localFanartApiKey,
  apiOrder,
  localOutputFormat,
  localJpgQuality,
  localPngCompression,
  localWebpQuality,
  localConcurrentRenders,
  localTmdbRateLimit,
  localTvdbRateLimit,
  localMemoryLimit,
  localUseOverlayCache,
  localSchedulerEnabled,
  localSchedulerCronExpression,
  localSchedulerLibraryIds,
  localDiscordEnabled,
  localDiscordWebhookUrl,
  localDiscordNotifyLibraries,
  localDiscordNotifyBatch,
  localDiscordNotifyManual,
  localDiscordNotifyWebhook,
  localDiscordNotifyAutoGenerate,
  localWebhookAlwaysRegenerateSeason
], () => {
  if (watchersEnabled.value) {
    checkForChanges()
  }
}, {
  deep: true,
  flush: 'post'
})

// Watch for tab changes and update URL
watch(activeTab, (newTab) => {
  router.replace({ query: { ...route.query, tab: newTab } })
})

// Watch for URL changes and update active tab
watch(() => route.query.tab, (newTab) => {
  if (newTab && typeof newTab === 'string') {
    activeTab.value = newTab as any
  }
})

onBeforeRouteLeave((_to, _from, next) => {
  stopScanPolling()

  if (hasUnsavedChanges.value) {
    const answer = window.confirm('You have unsaved changes. Are you sure you want to leave?')
    if (answer) {
      next()
    } else {
      next(false)
    }
  } else {
    next()
  }
})

onMounted(() => {
  const handleBeforeUnload = (e: BeforeUnloadEvent) => {
    if (hasUnsavedChanges.value) {
      e.preventDefault()
      e.returnValue = ''
    }
  }
  window.addEventListener('beforeunload', handleBeforeUnload)

  onBeforeUnmount(() => {
    stopScanPolling()
    window.removeEventListener('beforeunload', handleBeforeUnload)
  })
})
</script>

<template>
  <div class="view">
    <div class="settings-header">
      <div class="settings-title-row">
        <div>
          <h2>&#x2699;&#xFE0F; Settings</h2>
          <p class="header-subtitle">Customize your Simposter experience</p>
        </div>
        <div class="header-status">
          <span v-if="hasUnsavedChanges" class="unsaved-badge">Unsaved Changes</span>
          <span class="version-chip">{{ APP_VERSION }}</span>
          <span v-if="saved" :class="['save-status', saved.startsWith('Error') ? 'error' : 'success']">
            {{ saved }}
          </span>
        </div>
      </div>
    </div>

    <!-- Tab Navigation -->
    <div class="tabs-container">
      <div class="tabs">
        <button
          :class="['tab', { active: activeTab === 'general' }]"
          @click="activeTab = 'general'"
        >
          General
        </button>
        <button
          :class="['tab', { active: activeTab === 'libraries' }]"
          @click="activeTab = 'libraries'"
        >
          Libraries
        </button>
        <!-- Integrations tab removed -->
        <button
          :class="['tab', { active: activeTab === 'save-locations' }]"
          @click="activeTab = 'save-locations'"
        >
          Save Locations
        </button>
        <button
          :class="['tab', { active: activeTab === 'performance' }]"
          @click="activeTab = 'performance'"
        >
          Performance
        </button>
        <button
          :class="['tab', { active: activeTab === 'notifications' }]"
          @click="activeTab = 'notifications'"
        >
          Notifications
        </button>
        <button
          :class="['tab', { active: activeTab === 'advanced' }]"
          @click="activeTab = 'advanced'"
        >
          Advanced
        </button>
      </div>
    </div>

    <!-- Tab Content -->
    <div class="tab-content-wrapper">
      <GeneralTab
        v-if="activeTab === 'general'"
        :theme="localTheme"
        :posterDensity="localPosterDensity"
        :deduplicateMovies="localDeduplicateMovies"
        :defaultSort="localDefaultSort"
        :timezone="localTimezone"
        :tmdbApiKey="localTmdbApiKey"
        :tvdbApiKey="localTvdbApiKey"
        :fanartApiKey="localFanartApiKey"
        :testingKeys="testingApiKeys"
        :apiKeyTestResults="apiKeyTestResults"
        :unsavedChanges="hasUnsavedChanges"
        @update:theme="localTheme = $event as Theme"
        @update:posterDensity="localPosterDensity = $event"
        @update:deduplicateMovies="localDeduplicateMovies = $event"
        @update:defaultSort="localDefaultSort = $event"
        @update:timezone="localTimezone = $event"
        @update:tmdbApiKey="localTmdbApiKey = $event"
        @update:tvdbApiKey="localTvdbApiKey = $event"
        @update:fanartApiKey="localFanartApiKey = $event"
        @test-api-key="testSingleApiKey"
        @save="saveSettings"
      />

      <LibrariesTab
        v-if="activeTab === 'libraries'"
        :plexUrl="localPlexUrl"
        :plexToken="localPlexToken"
        :libraries="localLibraries"
        :tvShowLibraries="localTvShowLibraries"
        :savedLibraryIds="savedLibraryIds"
        :savedTvShowLibraryIds="savedTvShowLibraryIds"
        :testConnection="testConnection"
        :testConnectionLoading="testConnectionLoading"
        :plexLibraries="plexLibraries"
        :scanCooldown="scanCooldown"
        :scanningLibraryId="scanningLibraryId"
        :schedulerEnabled="localSchedulerEnabled"
        :schedulerCronExpression="localSchedulerCronExpression"
        :schedulerLibraryIds="localSchedulerLibraryIds"
        :schedulerNextRun="schedulerNextRun"
        :defaultLabelsToRemove="localDefaultLabelsToRemove"
        :defaultTvLabelsToRemove="localDefaultTvLabelsToRemove"
        :unsavedChanges="hasUnsavedChanges"
        :schedulerChanged="sectionsWithChanges.scheduler"
        :connectionsChanged="sectionsWithChanges.connections"
        @update:plexUrl="localPlexUrl = $event"
        @update:plexToken="localPlexToken = $event"
        @update:libraries="localLibraries = $event; hasUnsavedChanges = true"
        @update:tvShowLibraries="localTvShowLibraries = $event; hasUnsavedChanges = true"
        @update:schedulerEnabled="localSchedulerEnabled = $event"
        @update:schedulerCronExpression="localSchedulerCronExpression = $event"
        @update:schedulerLibraryIds="localSchedulerLibraryIds = $event"
        @update:defaultLabelsToRemove="localDefaultLabelsToRemove = $event; hasUnsavedChanges = true"
        @update:defaultTvLabelsToRemove="localDefaultTvLabelsToRemove = $event; hasUnsavedChanges = true"
        @test-connection="testPlexConnection"
        @scan-library="scanLibrary"
        @save="saveSettings"
      />

      <!-- Integrations content removed -->

      <SaveLocationsTab
        v-if="activeTab === 'save-locations'"
        :movieSaveLocation="localMovieSaveLocation"
        :tvShowSaveLocation="localTvShowSaveLocation"
        :tvShowSaveMode="localTvShowSaveMode"
        :saveBatchInSubfolder="localSaveBatch"
        :unsavedChanges="hasUnsavedChanges"
        @update:movieSaveLocation="localMovieSaveLocation = $event"
        @update:tvShowSaveLocation="localTvShowSaveLocation = $event"
        @update:tvShowSaveMode="localTvShowSaveMode = $event"
        @update:saveBatchInSubfolder="localSaveBatch = $event"
        @save="saveSettings"
      />

      <PerformanceTab
        v-if="activeTab === 'performance'"
        :concurrentRenders="localConcurrentRenders"
        :useOverlayCache="localUseOverlayCache"
        :unsavedChanges="hasUnsavedChanges"
        :scanRunning="scan.running.value"
        :outputFormat="localOutputFormat"
        :jpgQuality="localJpgQuality"
        :pngCompression="localPngCompression"
        :webpQuality="localWebpQuality"
        :tmdbRateLimit="localTmdbRateLimit"
        :tvdbRateLimit="localTvdbRateLimit"
        :memoryLimit="localMemoryLimit"
        :webhookAutoSend="localWebhookAutoSend"
        :webhookAutoLabels="localWebhookAutoLabels"
        :webhookAlwaysRegenerateSeason="localWebhookAlwaysRegenerateSeason"
        :imageQualityChanged="sectionsWithChanges.imageQuality"
        :performanceChanged="sectionsWithChanges.performance"
        :automationChanged="sectionsWithChanges.automation"
        @update:concurrentRenders="localConcurrentRenders = $event; sectionsWithChanges.performance = true; hasUnsavedChanges = true"
        @update:useOverlayCache="localUseOverlayCache = $event; sectionsWithChanges.performance = true; hasUnsavedChanges = true"
        @update:outputFormat="localOutputFormat = $event; sectionsWithChanges.imageQuality = true; hasUnsavedChanges = true"
        @update:jpgQuality="localJpgQuality = $event; sectionsWithChanges.imageQuality = true; hasUnsavedChanges = true"
        @update:pngCompression="localPngCompression = $event; sectionsWithChanges.imageQuality = true; hasUnsavedChanges = true"
        @update:webpQuality="localWebpQuality = $event; sectionsWithChanges.imageQuality = true; hasUnsavedChanges = true"
        @update:tmdbRateLimit="localTmdbRateLimit = $event; sectionsWithChanges.performance = true; hasUnsavedChanges = true"
        @update:tvdbRateLimit="localTvdbRateLimit = $event; sectionsWithChanges.performance = true; hasUnsavedChanges = true"
        @update:memoryLimit="localMemoryLimit = $event; sectionsWithChanges.performance = true; hasUnsavedChanges = true"
        @update:webhookAutoSend="localWebhookAutoSend = $event; sectionsWithChanges.automation = true; hasUnsavedChanges = true"
        @update:webhookAutoLabels="localWebhookAutoLabels = $event; sectionsWithChanges.automation = true; hasUnsavedChanges = true"
        @update:webhookAlwaysRegenerateSeason="localWebhookAlwaysRegenerateSeason = $event; sectionsWithChanges.automation = true; hasUnsavedChanges = true"
        @clear-frontend-cache="clearCache"
        @clear-backend-cache="clearBackendCache"
        @save="saveSettings"
      />

      <NotificationsTab
        v-if="activeTab === 'notifications'"
        :discordEnabled="localDiscordEnabled"
        :discordWebhookUrl="localDiscordWebhookUrl"
        :discordNotifyLibraries="localDiscordNotifyLibraries"
        :discordNotifyBatch="localDiscordNotifyBatch"
        :discordNotifyManual="localDiscordNotifyManual"
        :discordNotifyWebhook="localDiscordNotifyWebhook"
        :discordNotifyAutoGenerate="localDiscordNotifyAutoGenerate"
        :appriseEnabled="localAppriseEnabled"
        :appriseUrls="localAppriseUrls"
        :appriseNotifyLibraries="localAppriseNotifyLibraries"
        :appriseNotifyBatch="localAppriseNotifyBatch"
        :appriseNotifyManual="localAppriseNotifyManual"
        :appriseNotifyWebhook="localAppriseNotifyWebhook"
        :appriseNotifyAutoGenerate="localAppriseNotifyAutoGenerate"
        :libraries="localLibraries"
        :tvShowLibraries="localTvShowLibraries"
        :unsavedChanges="hasUnsavedChanges"
        @update:discordEnabled="localDiscordEnabled = $event; hasUnsavedChanges = true"
        @update:discordWebhookUrl="localDiscordWebhookUrl = $event; hasUnsavedChanges = true"
        @update:discordNotifyLibraries="localDiscordNotifyLibraries = $event; hasUnsavedChanges = true"
        @update:discordNotifyBatch="localDiscordNotifyBatch = $event; hasUnsavedChanges = true"
        @update:discordNotifyManual="localDiscordNotifyManual = $event; hasUnsavedChanges = true"
        @update:discordNotifyWebhook="localDiscordNotifyWebhook = $event; hasUnsavedChanges = true"
        @update:discordNotifyAutoGenerate="localDiscordNotifyAutoGenerate = $event; hasUnsavedChanges = true"
        @update:appriseEnabled="localAppriseEnabled = $event; hasUnsavedChanges = true"
        @update:appriseUrls="localAppriseUrls = $event; hasUnsavedChanges = true"
        @update:appriseNotifyLibraries="localAppriseNotifyLibraries = $event; hasUnsavedChanges = true"
        @update:appriseNotifyBatch="localAppriseNotifyBatch = $event; hasUnsavedChanges = true"
        @update:appriseNotifyManual="localAppriseNotifyManual = $event; hasUnsavedChanges = true"
        @update:appriseNotifyWebhook="localAppriseNotifyWebhook = $event; hasUnsavedChanges = true"
        @update:appriseNotifyAutoGenerate="localAppriseNotifyAutoGenerate = $event; hasUnsavedChanges = true"
        @save="saveSettings"
      />

      <AdvancedTab
        v-if="activeTab === 'advanced'"
        :dbExporting="dbExporting"
        :dbImporting="dbImporting"
        :showDbImportModal="showDbImportModal"
        :dbImportText="dbImportText"
        :apiOrder="apiOrder"
        :unsavedChanges="hasUnsavedChanges"
        @update:showDbImportModal="showDbImportModal = $event"
        @update:dbImportText="dbImportText = $event"
        @update:apiOrder="apiOrder = $event; sectionsWithChanges.apiKeys = true; hasUnsavedChanges = true"
        @export-db="handleDbExport"
        @import-db="handleDbImport"
        @save="saveSettings"
      />
    </div>
  </div>
</template>

<style scoped>
.view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.settings-header {
  padding: 20px 24px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
}

.settings-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.settings-title-row h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 28px;
  font-weight: 600;
}

.header-subtitle {
  margin: 4px 0 0 0;
  color: var(--text-muted);
  font-size: 14px;
}

.header-status {
  display: flex;
  align-items: center;
  gap: 12px;
}

.unsaved-badge {
  padding: 6px 12px;
  background: rgba(255, 193, 7, 0.15);
  border: 1px solid rgba(255, 193, 7, 0.3);
  border-radius: 6px;
  color: #ffb000;
  font-size: 13px;
  font-weight: 500;
}

.version-chip {
  padding: 6px 12px;
  background: rgba(61, 214, 183, 0.15);
  border: 1px solid rgba(61, 214, 183, 0.3);
  border-radius: 6px;
  color: var(--accent);
  font-size: 13px;
  font-weight: 500;
  font-family: monospace;
}

.save-status {
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
}

.save-status.success {
  background: rgba(0, 255, 0, 0.15);
  border: 1px solid rgba(0, 255, 0, 0.3);
  color: #00ff00;
}

.save-status.error {
  background: rgba(255, 0, 0, 0.15);
  border: 1px solid rgba(255, 0, 0, 0.3);
  color: #ff6b6b;
}

.tabs-container {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  padding: 0 24px;
}

.tabs {
  display: flex;
  gap: 4px;
  overflow-x: auto;
}

.tab {
  padding: 12px 20px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.tab:hover {
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.03);
}

.tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  background: rgba(61, 214, 183, 0.05);
}

.tab-content-wrapper {
  flex: 1;
  overflow-y: auto;
  background: var(--bg-primary);
}

/* Mobile responsive styles */
@media (max-width: 900px) {
  .settings-header {
    padding: 16px;
  }

  .settings-title-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .settings-title-row h2 {
    font-size: 24px;
  }

  .header-status {
    flex-wrap: wrap;
    gap: 8px;
  }

  .tabs-container {
    padding: 0 12px;
  }

  .tabs {
    gap: 2px;
    -webkit-overflow-scrolling: touch;
  }

  .tab {
    padding: 10px 14px;
    font-size: 13px;
  }
}

@media (max-width: 600px) {
  .settings-header {
    padding: 12px;
  }

  .settings-title-row h2 {
    font-size: 20px;
  }

  .header-subtitle {
    font-size: 13px;
  }

  .header-status {
    width: 100%;
  }

  .unsaved-badge,
  .version-chip,
  .save-status {
    padding: 4px 8px;
    font-size: 11px;
  }

  .tabs-container {
    padding: 0 8px;
  }

  .tabs {
    gap: 0;
  }

  .tab {
    padding: 10px 12px;
    font-size: 12px;
  }
}
</style>
