import { ref, computed } from 'vue'
import { getApiBase } from '../services/apiBase'
import { SECRET_MASK, sameOrigin } from '../services/serverOrigin'

const apiBase = getApiBase()

export type Theme = 'neon' | 'slate' | 'dracula' | 'nord' | 'oled' | 'light'

export type LibraryMapping = {
  id: string
  title?: string
  displayName?: string
  autoGenerateEnabled?: boolean
  autoGeneratePresetId?: string | null
  autoGenerateTemplateId?: string | null
}

export type MediaServerEntry = {
  id: string
  type: 'plex' | 'jellyfin' | 'emby'
  name?: string    // user-supplied display label, e.g. "jellyfin-main" -- falls back to
                    // a generic type label everywhere it's shown when unset/blank
  url: string
  token?: string   // Plex
  apiKey?: string  // Jellyfin/Emby
  enabled: boolean
}

export type LibraryGroupMember = {
  serverId: string
  libraryId: string
  libraryName?: string
}

export type MediaMirrorConfig = {
  enabled?: boolean
  sourceServerId?: string | null
  targetServerIds?: string[]
  assetTypes?: string[]
  scheduleEnabled?: boolean
  scheduleCron?: string | null
  lastRunAt?: string | null
  lastRunStats?: {
    checked?: number
    updated?: number
    skipped?: number
    unmapped?: number
    failed?: number
    unmappedSample?: string[]
  } | null
}

export type OverlayRefreshConfig = {
  enabled?: boolean
  scheduleCron?: string | null
  plexLabel?: string
  lastRunAt?: string | null
  lastRunStats?: Record<string, number> | null
}

// A Radarr or Sonarr connection. Simposter only reads its tags, for poster mode rules.
export type ArrInstance = {
  id: string
  type: 'radarr' | 'sonarr'
  name?: string
  url: string
  apiKey?: string
  enabled?: boolean
}

export type PosterModeRule = {
  source: 'plex_label' | 'arr_tag'  // arr_tag: a tag in the group's linked Radarr/Sonarr
  value: string
  mode: 'overlay_only' | 'leave_alone'
}

export type LibraryGroup = {
  id: string
  name: string
  mediaType: 'movie' | 'tv'
  members: LibraryGroupMember[]
  autoGenerateEnabled?: boolean
  autoGeneratePresetId?: string | null
  autoGenerateTemplateId?: string | null
  labelsToRemove?: string[]
  posterModeRules?: PosterModeRule[]  // Poster modes: label/tag rules giving matching titles Overlay only / Leave alone
  arrInstanceId?: string | null       // The Radarr (movies) / Sonarr (TV) whose tags "arr_tag" rules read
  preferredServerId?: string | null  // Which member's row wins when this group's merged
                                      // grid finds the same title on more than one server
                                      // (backend's _dedupe_by_tmdb_id()) -- replaces the
                                      // old global automation.preferredPosterServer.
  mergeItems?: boolean               // True (default) collapses a title present on more
                                      // than one linked server into a single card (the
                                      // behavior preferredServerId above governs). False
                                      // shows every server's copy as its own separate card
                                      // -- no also_on/other_servers populated either, since
                                      // nothing was collapsed to cross-reference.
  collectionMatchOverrides?: Record<string, string>  // manual cross-server collection matches ("serverId:ratingKey" -> match key)
  mirror?: MediaMirrorConfig | null  // Media Mirror (Quirk #123) -- designates one member
                                      // as "the truth" and copies its posters/logos/etc to
                                      // one or more other members. Saved independently of
                                      // this page's own store save cycle -- MediaMirrorView
                                      // POSTs it directly to /api/media-mirror/config.
  overlayRefresh?: OverlayRefreshConfig | null  // saved by OverlayRefreshView only
}

export type PlexSettings = {
  url: string
  token: string
  movieLibraryName: string
  movieLibraryNames?: string[]
  libraryMappings?: LibraryMapping[]
  tvShowLibraryName?: string
  tvShowLibraryNames?: string[]
  tvShowLibraryMappings?: LibraryMapping[]
  sendLogosToPlex?: boolean
}

export type TMDBSettings = {
  apiKey: string
}

export type TVDBSettings = {
  apiKey: string
  comingSoon?: boolean
}

export type MDBListSettings = {
  apiKey: string
  audienceRatingSource: string
  criticRatingSource: string
  cacheDays: number
}

export type PosterApiSettings = {
  enabled: boolean
  key: string // masked (SECRET_MASK) when set; the server keeps the real value
  defaultMoviePreset: string
  defaultTvPreset: string
  waitSeconds: number
  retentionDays: number
  movieGroup?: string // library group id used when a request names none; '' = any library
  tvGroup?: string
}

// List sources for overlay "On a list" rules (backend/list_sources.py).
// Sign-in tokens are stored server-side, never here.
export type WeTrakrSettings = { clientId: string }
export type SimklSettings = { clientId: string }
export type FloppySettings = { url: string; token: string }
export type MaintainerrSettings = { url: string; apiKey: string }

export type FanartSettings = {
  apiKey: string
}

export type ImageQualitySettings = {
  outputFormat: string
  jpgQuality: number
  pngCompression: number
  webpQuality: number
}

export type PerformanceSettings = {
  concurrentRenders: number
  tmdbRateLimit: number
  tvdbRateLimit: number
  memoryLimit: number
  useOverlayCache: boolean
}

export type SchedulerSettings = {
  enabled: boolean
  cronExpression: string
  libraryId?: string | null  // Legacy - kept for backwards compatibility
  libraryIds?: string[]      // New multi-select field
  cleanupEnabled?: boolean
  cleanupCronExpression?: string
  cleanupCategories?: string[]
  cleanupHistoryDays?: number
}

export type AutomationSettings = {
  webhookAutoSend: boolean
  webhookAutoLabels: string
  labelToAdd?: string
  webhookAlwaysRegenerateSeason: boolean
  webhookSecret?: string
  existingContentMode?: 'resend' | 'regenerate'
  retryUntilTemplateMet?: boolean
  retryIntervalHours?: number
  retryMaxAttempts?: number
  kometaCompatibility?: boolean
  reuseCachedPosterDays?: number
  preferredPosterServer?: string
}

export type NotificationSettings = {
  discordEnabled: boolean
  discordWebhookUrl: string
  discordNotifyLibraries: string[]
  discordNotifyBatch: boolean
  discordNotifyManual: boolean
  discordNotifyWebhook: boolean
  discordNotifyAutoGenerate: boolean
  discordNotifyMediaMirror?: boolean
  discordNotifyAppUpdates?: boolean
  discordNotifyOverlayRefresh?: boolean
  appriseEnabled: boolean
  appriseUrls: string[]
  appriseNotifyLibraries: string[]
  appriseNotifyBatch: boolean
  appriseNotifyManual: boolean
  appriseNotifyWebhook: boolean
  appriseNotifyAutoGenerate: boolean
  appriseNotifyMediaMirror?: boolean
  appriseNotifyAppUpdates?: boolean
  appriseNotifyOverlayRefresh?: boolean
}

export type UISettings = {
  theme: Theme
  posterDensity: number
  deduplicateMovies?: boolean
  defaultSort?: string
  timezone?: string
  defaultLabelsToRemove?: string[] | Record<string, string[]>
  defaultTvLabelsToRemove?: string[] | Record<string, string[]>
  saveLocation?: string  // Legacy field for backwards compatibility
  movieSaveLocation?: string
  tvShowSaveLocation?: string
  collectionSaveLocation?: string
  tvShowSaveMode?: string
  saveBatchInSubfolder?: boolean
  saveToAssetFolderOnSend?: boolean
  plex?: PlexSettings
  tmdb?: TMDBSettings
  tvdb?: TVDBSettings
  fanart?: FanartSettings
  mdblist?: Partial<MDBListSettings>
  posterApi?: Partial<PosterApiSettings>
  wetrakr?: Partial<WeTrakrSettings>
  simkl?: Partial<SimklSettings>
  floppy?: Partial<FloppySettings>
  maintainerr?: Partial<MaintainerrSettings>
  imageQuality?: ImageQualitySettings
  performance?: PerformanceSettings
  apiOrder?: string[]
  scheduler?: SchedulerSettings
  automation?: AutomationSettings
  notifications?: NotificationSettings
  onboarding_completed?: boolean
  mediaServers?: MediaServerEntry[]
  libraryGroups?: LibraryGroup[]
  arrInstances?: ArrInstance[]
}

const onboardingCompleted = ref(false)
const theme = ref<Theme>('neon')
const posterDensity = ref(20)
const deduplicateMovies = ref(false)
const defaultSort = ref('added-desc')
const timezone = ref('UTC')
const defaultLabelsToRemove = ref<Record<string, string[]>>({})
const defaultTvLabelsToRemove = ref<Record<string, string[]>>({})
const loading = ref(false)
const error = ref<string | null>(null)
const loaded = ref(false)
const saveLocation = ref<string>('/output')  // Legacy, kept for backwards compatibility
const movieSaveLocation = ref<string>('/config/output/{library}/{title}.jpg')
const tvShowSaveLocation = ref<string>('/config/output/{library}/{title} ({year}).jpg')
const collectionSaveLocation = ref<string>('/config/output/{library}/Collections/{title}.jpg')
const tvShowSaveMode = ref<string>('flat')
const saveBatchInSubfolder = ref<boolean>(false)
const saveToAssetFolderOnSend = ref<boolean>(false)
const plex = ref<PlexSettings>({ url: '', token: '', movieLibraryName: '', movieLibraryNames: [], libraryMappings: [], tvShowLibraryName: '', tvShowLibraryNames: [], tvShowLibraryMappings: [] })
const mediaServers = ref<MediaServerEntry[]>([])
// The address each saved key belongs to ('plex', 'ms:<id>', 'arr:<id>'), as of
// the last load or save. The backend only reuses a saved (masked) key for that
// same address; the Settings page uses this to say when one must be retyped.
const savedServerUrls = ref<Record<string, string>>({})
// Media servers and library groups as of the last load or save. The Settings
// page edits mediaServers/libraryGroups in place, so anything shown outside it
// (top bar status pills, sidebar library tabs) reads these instead, and only
// changes once Save succeeds.
const savedMediaServers = ref<MediaServerEntry[]>([])
const savedLibraryGroups = ref<LibraryGroup[]>([])

function recordSavedServerUrls() {
  const out: Record<string, string> = { plex: plex.value.url || '' }
  for (const s of mediaServers.value) out[`ms:${s.id}`] = s.url || ''
  for (const i of arrInstances.value) out[`arr:${i.id}`] = i.url || ''
  savedServerUrls.value = out
  savedMediaServers.value = JSON.parse(JSON.stringify(mediaServers.value || []))
  savedLibraryGroups.value = JSON.parse(JSON.stringify(libraryGroups.value || []))
}

// After a save, a masked key whose address changed was dropped by the backend
// (it never moves a saved key to another address); show it as empty here too.
function clearKeysWithChangedAddress() {
  const saved = savedServerUrls.value
  if (plex.value.token === SECRET_MASK && !sameOrigin(plex.value.url, saved.plex)) {
    plex.value = { ...plex.value, token: '' }
  }
  mediaServers.value = mediaServers.value.map(s => {
    if (sameOrigin(s.url, saved[`ms:${s.id}`])) return s
    const next = { ...s }
    if (next.token === SECRET_MASK) next.token = ''
    if (next.apiKey === SECRET_MASK) next.apiKey = ''
    return next
  })
  arrInstances.value = arrInstances.value.map(i =>
    i.apiKey === SECRET_MASK && !sameOrigin(i.url, saved[`arr:${i.id}`]) ? { ...i, apiKey: '' } : i)
}
// Plex is in use when it has a URL + token and its main server ('plex-1') isn't
// switched off with the Enabled checkbox in Settings -> Media Servers -- the
// same rule as Jellyfin/Emby, whose entries are skipped when disabled.
const plexActive = computed(() =>
  !!(plex.value.url && plex.value.token) &&
  mediaServers.value.find(s => s.id === 'plex-1')?.enabled !== false
)
const libraryGroups = ref<LibraryGroup[]>([])
const arrInstances = ref<ArrInstance[]>([])
const tmdb = ref<TMDBSettings>({ apiKey: '' })
const tvdb = ref<TVDBSettings>({ apiKey: '', comingSoon: false })
const fanart = ref<FanartSettings>({ apiKey: '' })
const mdblist = ref<MDBListSettings>({ apiKey: '', audienceRatingSource: 'server', criticRatingSource: 'server', cacheDays: 7 })
const posterApi = ref<PosterApiSettings>({ enabled: false, key: '', defaultMoviePreset: '', defaultTvPreset: '', waitSeconds: 10, retentionDays: 90 })
// Whether the Poster API is on as last saved/loaded. The sidebar reads this, not
// posterApi.enabled, so unticking the Settings checkbox doesn't hide the page until Save.
const posterApiEnabledSaved = ref(false)
const wetrakr = ref<WeTrakrSettings>({ clientId: '' })
const simkl = ref<SimklSettings>({ clientId: '' })
const floppy = ref<FloppySettings>({ url: '', token: '' })
const maintainerr = ref<MaintainerrSettings>({ url: '', apiKey: '' })
const imageQuality = ref<ImageQualitySettings>({ outputFormat: 'jpg', jpgQuality: 95, pngCompression: 6, webpQuality: 90 })
const performance = ref<PerformanceSettings>({ concurrentRenders: 2, tmdbRateLimit: 40, tvdbRateLimit: 20, memoryLimit: 2048, useOverlayCache: true })
const apiOrder = ref<string[]>(['tmdb', 'fanart', 'tvdb'])
export const DEFAULT_CLEANUP_CATEGORIES = [
  'poster_cache', 'logo_cache', 'backdrop_cache', 'square_art_cache',
  'overlay_effect_cache', 'uploaded_files', 'overlay_assets', 'poster_history',
]
const scheduler = ref<SchedulerSettings>({
  enabled: false, cronExpression: '0 1 * * *', libraryId: null, libraryIds: [],
  cleanupEnabled: false, cleanupCronExpression: '0 3 * * 0', cleanupCategories: [...DEFAULT_CLEANUP_CATEGORIES], cleanupHistoryDays: 180,
})
const automation = ref<AutomationSettings>({ webhookAutoSend: true, webhookAutoLabels: 'Simposter', labelToAdd: '', webhookAlwaysRegenerateSeason: false, webhookSecret: '', existingContentMode: 'regenerate', retryUntilTemplateMet: false, retryIntervalHours: 24, retryMaxAttempts: 0, kometaCompatibility: false, reuseCachedPosterDays: 0, preferredPosterServer: 'plex-1' })
const notifications = ref<NotificationSettings>({
  discordEnabled: false,
  discordWebhookUrl: '',
  discordNotifyLibraries: [],
  discordNotifyBatch: true,
  discordNotifyManual: true,
  discordNotifyWebhook: true,
  discordNotifyAutoGenerate: true,
  discordNotifyMediaMirror: true,
  discordNotifyAppUpdates: true,
  discordNotifyOverlayRefresh: true,
  appriseEnabled: false,
  appriseUrls: [],
  appriseNotifyLibraries: [],
  appriseNotifyBatch: true,
  appriseNotifyManual: true,
  appriseNotifyWebhook: true,
  appriseNotifyAutoGenerate: true,
  appriseNotifyMediaMirror: true,
  appriseNotifyAppUpdates: true,
  appriseNotifyOverlayRefresh: true
})

// Calls made while a load is already running share it (a page load used to
// start three at once: router guard, App.vue and the view), and a refused or
// failed request is retried a few times. A failed load must never look like a
// fresh install: App.vue only opens the setup wizard once `loaded` is true.
let loadInFlight: Promise<void> | null = null

function loadSettings(): Promise<void> {
  if (!loadInFlight) {
    loadInFlight = doLoadSettings().finally(() => { loadInFlight = null })
  }
  return loadInFlight
}

async function fetchSettingsWithRetry(): Promise<Response> {
  const delays = [1000, 2000, 4000, 8000]
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(`${apiBase}/api/ui-settings`)
      const retryable = res.status === 429 || res.status >= 500
      if (res.ok || !retryable || attempt >= delays.length) return res
    } catch (e) {
      if (attempt >= delays.length) throw e
    }
    await new Promise((r) => setTimeout(r, delays[attempt]))
  }
}

async function doLoadSettings() {
  loading.value = true
  error.value = null
  try {
    const res = await fetchSettingsWithRetry()
    if (!res.ok) throw new Error(`API error ${res.status}`)
    const data = (await res.json()) as UISettings
    theme.value = data.theme || 'neon'
    posterDensity.value = Number(data.posterDensity) || 20
    deduplicateMovies.value = data.deduplicateMovies ?? false
    defaultSort.value = data.defaultSort || 'added-desc'
    timezone.value = data.timezone || 'UTC'
    // Handle both legacy array format and new Record format
    if (Array.isArray(data.defaultLabelsToRemove)) {
      // Legacy format: convert to new format using first library as default
      defaultLabelsToRemove.value = { 'default': data.defaultLabelsToRemove }
    } else {
      defaultLabelsToRemove.value = data.defaultLabelsToRemove || {}
    }
    // Load TV labels (same logic as movie labels)
    if (Array.isArray(data.defaultTvLabelsToRemove)) {
      defaultTvLabelsToRemove.value = { 'default': data.defaultTvLabelsToRemove }
    } else {
      defaultTvLabelsToRemove.value = data.defaultTvLabelsToRemove || {}
    }
    loaded.value = true
    onboardingCompleted.value = data.onboarding_completed ?? false
    saveLocation.value = data.saveLocation ?? "/output"
    // New separate save locations with backwards compatibility
    movieSaveLocation.value = data.movieSaveLocation ?? data.saveLocation ?? "/config/output/{library}/{title}.jpg"
    tvShowSaveLocation.value = data.tvShowSaveLocation ?? data.saveLocation ?? "/config/output/{library}/{title} ({year}).jpg"
    collectionSaveLocation.value = data.collectionSaveLocation ?? "/config/output/{library}/Collections/{title}.jpg"
    tvShowSaveMode.value = data.tvShowSaveMode ?? 'flat'
    saveBatchInSubfolder.value = !!data.saveBatchInSubfolder
    saveToAssetFolderOnSend.value = !!data.saveToAssetFolderOnSend
    plex.value = {
      url: data.plex?.url ?? '',
      token: data.plex?.token ?? '',
      movieLibraryName: data.plex?.movieLibraryName ?? '',
      movieLibraryNames: data.plex?.movieLibraryNames ?? (data.plex?.movieLibraryName ? [data.plex.movieLibraryName] : []),
      libraryMappings: data.plex?.libraryMappings ?? [],
      tvShowLibraryName: data.plex?.tvShowLibraryName ?? '',
      tvShowLibraryNames: data.plex?.tvShowLibraryNames ?? (data.plex?.tvShowLibraryName ? [data.plex.tvShowLibraryName] : []),
      tvShowLibraryMappings: data.plex?.tvShowLibraryMappings ?? [],
      sendLogosToPlex: data.plex?.sendLogosToPlex ?? false
    }
    mediaServers.value = data.mediaServers ?? []
    libraryGroups.value = data.libraryGroups ?? []
    arrInstances.value = data.arrInstances ?? []
    recordSavedServerUrls()
    tmdb.value = { apiKey: data.tmdb?.apiKey ?? '' }
    tvdb.value = { apiKey: data.tvdb?.apiKey ?? '', comingSoon: data.tvdb?.comingSoon ?? true }
    fanart.value = { apiKey: data.fanart?.apiKey ?? '' }
    mdblist.value = {
      apiKey: data.mdblist?.apiKey ?? '',
      audienceRatingSource: data.mdblist?.audienceRatingSource ?? 'server',
      criticRatingSource: data.mdblist?.criticRatingSource ?? 'server',
      cacheDays: data.mdblist?.cacheDays ?? 7
    }
    posterApi.value = {
      enabled: data.posterApi?.enabled ?? false,
      key: data.posterApi?.key ?? '',
      defaultMoviePreset: data.posterApi?.defaultMoviePreset ?? '',
      defaultTvPreset: data.posterApi?.defaultTvPreset ?? '',
      waitSeconds: data.posterApi?.waitSeconds ?? 10,
      retentionDays: data.posterApi?.retentionDays ?? 90,
      movieGroup: data.posterApi?.movieGroup ?? '',
      tvGroup: data.posterApi?.tvGroup ?? ''
    }
    posterApiEnabledSaved.value = posterApi.value.enabled
    wetrakr.value = { clientId: data.wetrakr?.clientId ?? '' }
    simkl.value = { clientId: data.simkl?.clientId ?? '' }
    floppy.value = { url: data.floppy?.url ?? '', token: data.floppy?.token ?? '' }
    maintainerr.value = { url: data.maintainerr?.url ?? '', apiKey: data.maintainerr?.apiKey ?? '' }
    imageQuality.value = {
      outputFormat: data.imageQuality?.outputFormat ?? 'jpg',
      jpgQuality: data.imageQuality?.jpgQuality ?? 95,
      pngCompression: data.imageQuality?.pngCompression ?? 6,
      webpQuality: data.imageQuality?.webpQuality ?? 90
    }
    performance.value = {
      concurrentRenders: data.performance?.concurrentRenders ?? 2,
      tmdbRateLimit: data.performance?.tmdbRateLimit ?? 40,
      tvdbRateLimit: data.performance?.tvdbRateLimit ?? 20,
      memoryLimit: data.performance?.memoryLimit ?? 2048,
      useOverlayCache: data.performance?.useOverlayCache ?? true
    }
    apiOrder.value = data.apiOrder ?? ['tmdb', 'fanart', 'tvdb']
    scheduler.value = {
      enabled: data.scheduler?.enabled ?? false,
      cronExpression: data.scheduler?.cronExpression ?? '0 1 * * *',
      libraryId: data.scheduler?.libraryId ?? null,
      libraryIds: data.scheduler?.libraryIds ?? [],
      cleanupEnabled: data.scheduler?.cleanupEnabled ?? false,
      cleanupCronExpression: data.scheduler?.cleanupCronExpression ?? '0 3 * * 0',
      cleanupCategories: data.scheduler?.cleanupCategories ?? [...DEFAULT_CLEANUP_CATEGORIES],
      cleanupHistoryDays: data.scheduler?.cleanupHistoryDays ?? 180
    }
    automation.value = {
      webhookAutoSend: data.automation?.webhookAutoSend ?? true,
      webhookAutoLabels: data.automation?.webhookAutoLabels ?? 'Simposter',
      labelToAdd: data.automation?.labelToAdd ?? '',
      kometaCompatibility: data.automation?.kometaCompatibility ?? false,
      webhookAlwaysRegenerateSeason: data.automation?.webhookAlwaysRegenerateSeason ?? false,
      webhookSecret: data.automation?.webhookSecret ?? '',
      existingContentMode: data.automation?.existingContentMode ?? 'regenerate',
      retryUntilTemplateMet: data.automation?.retryUntilTemplateMet ?? false,
      retryIntervalHours: data.automation?.retryIntervalHours ?? 24,
      retryMaxAttempts: data.automation?.retryMaxAttempts ?? 0,
      reuseCachedPosterDays: data.automation?.reuseCachedPosterDays ?? 0,
      preferredPosterServer: data.automation?.preferredPosterServer ?? 'plex-1',
    }
    notifications.value = {
      discordEnabled: data.notifications?.discordEnabled ?? false,
      discordWebhookUrl: data.notifications?.discordWebhookUrl ?? '',
      discordNotifyLibraries: data.notifications?.discordNotifyLibraries ?? [],
      discordNotifyBatch: data.notifications?.discordNotifyBatch ?? true,
      discordNotifyManual: data.notifications?.discordNotifyManual ?? true,
      discordNotifyWebhook: data.notifications?.discordNotifyWebhook ?? true,
      discordNotifyAutoGenerate: data.notifications?.discordNotifyAutoGenerate ?? true,
      discordNotifyMediaMirror: data.notifications?.discordNotifyMediaMirror ?? true,
      discordNotifyAppUpdates: data.notifications?.discordNotifyAppUpdates ?? true,
      discordNotifyOverlayRefresh: data.notifications?.discordNotifyOverlayRefresh ?? true,
      appriseEnabled: data.notifications?.appriseEnabled ?? false,
      appriseUrls: data.notifications?.appriseUrls ?? [],
      appriseNotifyLibraries: data.notifications?.appriseNotifyLibraries ?? [],
      appriseNotifyBatch: data.notifications?.appriseNotifyBatch ?? true,
      appriseNotifyManual: data.notifications?.appriseNotifyManual ?? true,
      appriseNotifyWebhook: data.notifications?.appriseNotifyWebhook ?? true,
      appriseNotifyAutoGenerate: data.notifications?.appriseNotifyAutoGenerate ?? true,
      appriseNotifyMediaMirror: data.notifications?.appriseNotifyMediaMirror ?? true,
      appriseNotifyAppUpdates: data.notifications?.appriseNotifyAppUpdates ?? true,
      appriseNotifyOverlayRefresh: data.notifications?.appriseNotifyOverlayRefresh ?? true
    }

  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'Failed to load settings'
    error.value = message
  } finally {
    loading.value = false
  }
}

// allowEmptyMediaServers: the user deliberately removed their last media
// server(s) this save. The backend otherwise refuses an empty mediaServers
// list when entries are already saved (a guard against accidental wipes).
async function saveSettings(opts: { allowEmptyMediaServers?: boolean } = {}) {
  // Never save before a successful load: every field would still hold its
  // in-memory default, and saving those would overwrite the real settings
  // (blank API keys, default automation, ...). Refuse and reload instead.
  if (!loaded.value) {
    await loadSettings()
    error.value = 'Settings had not loaded yet, so nothing was saved. Check the values and save again.'
    return
  }
  loading.value = true
  error.value = null
  try {
    const payload: UISettings = {
      theme: theme.value,
      posterDensity: posterDensity.value,
      deduplicateMovies: deduplicateMovies.value,
      defaultSort: defaultSort.value,
      timezone: timezone.value,
      defaultLabelsToRemove: defaultLabelsToRemove.value,
      defaultTvLabelsToRemove: defaultTvLabelsToRemove.value,
      saveLocation: saveLocation.value,
      movieSaveLocation: movieSaveLocation.value,
      tvShowSaveLocation: tvShowSaveLocation.value,
      collectionSaveLocation: collectionSaveLocation.value,
      tvShowSaveMode: tvShowSaveMode.value,
      saveBatchInSubfolder: saveBatchInSubfolder.value,
      saveToAssetFolderOnSend: saveToAssetFolderOnSend.value,
      plex: { ...plex.value },
      mediaServers: mediaServers.value.map(s => ({ ...s })),
      libraryGroups: libraryGroups.value.map(g => ({ ...g, members: g.members.map(m => ({ ...m })) })),
      arrInstances: arrInstances.value.map(i => ({ ...i })),
      tmdb: { ...tmdb.value },
      tvdb: { ...tvdb.value },
      fanart: { ...fanart.value },
      mdblist: { ...mdblist.value },
      posterApi: { ...posterApi.value },
      wetrakr: { ...wetrakr.value },
      simkl: { ...simkl.value },
      floppy: { ...floppy.value },
      maintainerr: { ...maintainerr.value },
      imageQuality: { ...imageQuality.value },
      performance: { ...performance.value },
      apiOrder: apiOrder.value,
      scheduler: { ...scheduler.value },
      automation: { ...automation.value },
      notifications: { ...notifications.value },
      onboarding_completed: onboardingCompleted.value,
    }
    const query = opts.allowEmptyMediaServers ? '?allow_empty_media_servers=true' : ''
    const res = await fetch(`${apiBase}/api/ui-settings${query}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!res.ok) throw new Error(`API error ${res.status}`)
    posterApiEnabledSaved.value = !!payload.posterApi?.enabled
    clearKeysWithChangedAddress()
    recordSavedServerUrls()
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'Failed to save settings'
    error.value = message
  } finally {
    loading.value = false
  }
}

export function useSettingsStore() {
  if (!loaded.value && !loading.value) {
    loadSettings()
  }

  return {
    theme,
    posterDensity,
    deduplicateMovies,
    defaultSort,
    timezone,
    defaultLabelsToRemove,
    defaultTvLabelsToRemove,
    plex,
    plexActive,
    mediaServers,
    savedServerUrls,
    savedMediaServers,
    savedLibraryGroups,
    libraryGroups,
    arrInstances,
    tmdb,
    tvdb,
    fanart,
    mdblist,
    posterApi,
    posterApiEnabledSaved,
    wetrakr,
    simkl,
    floppy,
    maintainerr,
    imageQuality,
    performance,
    apiOrder,
    scheduler,
    automation,
    notifications,
    onboardingCompleted,
    loading,
    error,
    loaded,
    saveLocation,
    movieSaveLocation,
    tvShowSaveLocation,
    collectionSaveLocation,
    tvShowSaveMode,
    saveBatchInSubfolder,
    saveToAssetFolderOnSend,
    load: loadSettings,
    save: saveSettings
  }
}
