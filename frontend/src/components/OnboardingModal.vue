<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { useSettingsStore, type MediaServerEntry } from '@/stores/settings'
import { mediaServerId } from '@/services/mediaServerId'

const emit = defineEmits<{ (e: 'done'): void }>()

const settings = useSettingsStore()
const apiBase = getApiBase()

// Captured once, at mount, before anything in this run could change it --
// true only when the wizard is being RE-RUN on an already-onboarded install
// (Settings -> Advanced -> "Run Startup Wizard", Quirk #73), never for a
// genuine first-time run (App.vue only ever opens this modal automatically
// while onboardingCompleted is still false, and this session's own
// markOnboardingDone() is the only thing that ever sets it true, always at
// the very end). Used to gate the two "do this automatically" behaviors
// below that make sense for a brand-new install walking through setup for
// the first time, but are a real, reported problem for a re-run used just
// to add one more server to an already-configured install: auto-creating
// Library Groups by name-matching every selected library (a re-run's
// candidates would include the user's EXISTING libraries too, since
// movieLibSections/tvLibSections are populated from whatever's already
// configured -- silently duplicating/merging already-deliberately-arranged
// groups the user never asked to touch this run) and auto-scanning
// immediately on leaving the 'libraries' step (before the user has even
// reached Finish, let alone reviewed or saved anything).
const isRerun = settings.onboardingCompleted.value

// ── Steps ──────────────────────────────────────────────────────────────────
// 'servers' picks any combination of Plex/Jellyfin/Emby; 'connect' then shows
// one identical section per picked server (all three treated the same), and
// 'libraries' lists every connected server's libraries together.
const STEPS = ['welcome', 'servers', 'connect', 'libraries', 'apikeys', 'automation', 'performance', 'notifications', 'finish'] as const
type Step = typeof STEPS[number]
const step = ref<Step>('welcome')

// ── Servers step ───────────────────────────────────────────────────────────
// Plex defaults to checked (still the overwhelmingly common case); Jellyfin/Emby
// default unchecked. Any combination -- including Plex alone, Jellyfin+Emby with
// no Plex at all, or all three -- is valid.
const wantsPlex = ref(true)
const wantsJellyfinServer = ref(false)
const wantsEmbyServer = ref(false)
const canAdvanceServers = computed(() => wantsPlex.value || wantsJellyfinServer.value || wantsEmbyServer.value)

// visibleSteps -- the step sequence for this run. Every step currently always
// shows (the per-server choice lives inside 'connect'), but goNext()/goBack()
// still navigate through this list so a future conditional step only needs a
// filter rule here.
const visibleSteps = computed<Step[]>(() => [...STEPS])
const stepIndex = computed(() => visibleSteps.value.indexOf(step.value))

// ── Plex step ──────────────────────────────────────────────────────────────
const plexUrl = ref('')
const plexToken = ref('')
const testingPlex = ref(false)
const plexError = ref('')
const plexOk = ref(false)

type PlexSection = { key: string; title: string; type: string }
const plexSections = ref<PlexSection[]>([])

const testPlex = async () => {
  testingPlex.value = true
  plexError.value = ''
  plexOk.value = false
  plexSections.value = []
  try {
    const params = new URLSearchParams({ plex_url: plexUrl.value, plex_token: plexToken.value })
    const res = await fetch(`${apiBase}/api/test-plex-connection?${params}`)
    const data = await res.json()
    if (data.status === 'ok') {
      plexOk.value = true
      plexSections.value = data.sections || []
    } else {
      plexError.value = data.error || data.message || 'Connection failed'
    }
  } catch (e) {
    plexError.value = e instanceof Error ? e.message : 'Connection failed'
  } finally {
    testingPlex.value = false
  }
}

// ── Media Servers step (only reached when wantsJellyfinServer/wantsEmbyServer
// was checked on the 'servers' step) — two fully independent forms, one per
// type, so a user who wants BOTH Jellyfin and Emby can configure both in this
// one step rather than only ever being able to add one at a time. -────────────
const jellyfinUrl = ref('')
const jellyfinApiKey = ref('')
const testingJellyfin = ref(false)
const jellyfinError = ref('')
const jellyfinOk = ref(false)
const addedJellyfinServer = ref<MediaServerEntry | null>(null)

const embyUrl = ref('')
const embyApiKey = ref('')
const testingEmby = ref(false)
const embyError = ref('')
const embyOk = ref(false)
const addedEmbyServer = ref<MediaServerEntry | null>(null)

// Shared test logic for both forms above -- the two are otherwise fully
// independent state (separate url/key/status per type), this just avoids two
// copies of the same fetch-and-interpret-the-response block.
async function testMediaServerGeneric(
  type: 'jellyfin' | 'emby', url: string, apiKey: string,
  testingRef: typeof testingJellyfin, errorRef: typeof jellyfinError,
  okRef: typeof jellyfinOk, addedRef: typeof addedJellyfinServer,
) {
  testingRef.value = true
  errorRef.value = ''
  okRef.value = false
  addedRef.value = null
  try {
    const res = await fetch(`${apiBase}/api/media-server/test-connection`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, url: url.trim(), apiKey: apiKey.trim() }),
    })
    const data = await res.json()
    if (data.connected) {
      okRef.value = true
      addedRef.value = { id: mediaServerId(type, url), type, url: url.trim(), apiKey: apiKey.trim(), enabled: true }
    } else {
      errorRef.value = 'Could not connect — check the URL and API key'
    }
  } catch (e) {
    errorRef.value = e instanceof Error ? e.message : 'Connection failed'
  } finally {
    testingRef.value = false
  }
}
const testJellyfin = () => testMediaServerGeneric('jellyfin', jellyfinUrl.value, jellyfinApiKey.value, testingJellyfin, jellyfinError, jellyfinOk, addedJellyfinServer)
const testEmby = () => testMediaServerGeneric('emby', embyUrl.value, embyApiKey.value, testingEmby, embyError, embyOk, addedEmbyServer)

// ── Libraries step ─────────────────────────────────────────────────────────
const movieLibSections = computed(() => plexSections.value.filter(s => s.type === 'movie'))
const tvLibSections = computed(() => plexSections.value.filter(s => s.type === 'show'))

const selectedMovieLibs = ref<Set<string>>(new Set())
const selectedTvLibs = ref<Set<string>>(new Set())

const toggleMovieLib = (key: string) => {
  if (selectedMovieLibs.value.has(key)) selectedMovieLibs.value.delete(key)
  else selectedMovieLibs.value.add(key)
}
const toggleTvLib = (key: string) => {
  if (selectedTvLibs.value.has(key)) selectedTvLibs.value.delete(key)
  else selectedTvLibs.value.add(key)
}

const initLibraries = () => {
  selectedMovieLibs.value = new Set(movieLibSections.value.map(s => s.key))
  selectedTvLibs.value = new Set(tvLibSections.value.map(s => s.key))
}

// Jellyfin/Emby libraries -- fetched (GET /api/media-server/libraries, already
// built for Settings -> Media Servers/Libraries) right after the 'connect'
// step saves whichever server(s) were successfully tested, since that endpoint
// only ever sees servers already present in the saved `mediaServers` setting.
// Reuses the exact same "one standalone LibraryGroup per selected library"
// creation shape StandaloneServerLibraries.vue established (Phase 8a) -- see
// saveSettings() below for where those groups actually get built.
interface DiscoveredLibrary { serverId: string; serverType: string; libraryId: string; libraryName: string; mediaType: string }
const nonPlexDiscovered = ref<DiscoveredLibrary[]>([])
const selectedNonPlexLibs = ref<Set<string>>(new Set())  // keyed `${serverId}:${libraryId}`
const nonPlexKey = (d: DiscoveredLibrary) => `${d.serverId}:${d.libraryId}`
const toggleNonPlexLib = (d: DiscoveredLibrary) => {
  const key = nonPlexKey(d)
  if (selectedNonPlexLibs.value.has(key)) selectedNonPlexLibs.value.delete(key)
  else selectedNonPlexLibs.value.add(key)
}
async function fetchNonPlexLibraries() {
  try {
    const res = await fetch(`${apiBase}/api/media-server/libraries`)
    const data = await res.json()
    nonPlexDiscovered.value = (data.libraries || []).filter((l: DiscoveredLibrary) => l.serverId !== 'plex-1')
    // Pre-select everything found, matching initLibraries()'s Plex behavior above.
    selectedNonPlexLibs.value = new Set(nonPlexDiscovered.value.map(nonPlexKey))
  } catch { /* leave empty -- user can add libraries later in Settings */ }
}
const nonPlexMovieLibs = computed(() => nonPlexDiscovered.value.filter(d => d.mediaType === 'movie'))
const nonPlexTvLibs = computed(() => nonPlexDiscovered.value.filter(d => d.mediaType === 'tv'))
const hasTvLibs = computed(() =>
  selectedTvLibs.value.size > 0 ||
  nonPlexTvLibs.value.some(d => selectedNonPlexLibs.value.has(nonPlexKey(d)))
)

// ── API Keys step ──────────────────────────────────────────────────────────
const tmdbApiKey = ref('')
const tvdbApiKey = ref('')
const fanartApiKey = ref('')

const tmdbMissing = computed(() => step.value === 'apikeys' && !tmdbApiKey.value.trim())
const tvdbMissing = computed(() => step.value === 'apikeys' && hasTvLibs.value && !tvdbApiKey.value.trim())
const canAdvanceApiKeys = computed(() => !!tmdbApiKey.value.trim() && (!hasTvLibs.value || !!tvdbApiKey.value.trim()))

type KeyStatus = 'idle' | 'testing' | 'ok' | 'error'
const tmdbStatus = ref<KeyStatus>('idle')
const tmdbStatusMsg = ref('')
const tvdbStatus = ref<KeyStatus>('idle')
const tvdbStatusMsg = ref('')
const fanartStatus = ref<KeyStatus>('idle')
const fanartStatusMsg = ref('')

const testTmdb = async () => {
  if (!tmdbApiKey.value.trim()) return
  tmdbStatus.value = 'testing'
  tmdbStatusMsg.value = ''
  try {
    const res = await fetch(`${apiBase}/api/test-tmdb`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: tmdbApiKey.value.trim() }),
    })
    const data = await res.json()
    if (data.status === 'ok') { tmdbStatus.value = 'ok'; tmdbStatusMsg.value = data.example || 'Valid' }
    else { tmdbStatus.value = 'error'; tmdbStatusMsg.value = data.error || 'Invalid key' }
  } catch (e) { tmdbStatus.value = 'error'; tmdbStatusMsg.value = e instanceof Error ? e.message : 'Test failed' }
}

const testTvdb = async () => {
  if (!tvdbApiKey.value.trim()) return
  tvdbStatus.value = 'testing'
  tvdbStatusMsg.value = ''
  try {
    const res = await fetch(`${apiBase}/api/test-tvdb`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: tvdbApiKey.value.trim() }),
    })
    const data = await res.json()
    if (data.status === 'ok') { tvdbStatus.value = 'ok'; tvdbStatusMsg.value = 'Valid' }
    else { tvdbStatus.value = 'error'; tvdbStatusMsg.value = data.error || 'Invalid key' }
  } catch (e) { tvdbStatus.value = 'error'; tvdbStatusMsg.value = e instanceof Error ? e.message : 'Test failed' }
}

const testFanart = async () => {
  if (!fanartApiKey.value.trim()) return
  fanartStatus.value = 'testing'
  fanartStatusMsg.value = ''
  try {
    const res = await fetch(`${apiBase}/api/test-fanart`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: fanartApiKey.value.trim() }),
    })
    const data = await res.json()
    if (data.status === 'ok') { fanartStatus.value = 'ok'; fanartStatusMsg.value = data.logo_count != null ? `Valid · ${data.logo_count} logos found` : 'Valid' }
    else { fanartStatus.value = 'error'; fanartStatusMsg.value = data.error || 'Invalid key' }
  } catch (e) { fanartStatus.value = 'error'; fanartStatusMsg.value = e instanceof Error ? e.message : 'Test failed' }
}

// ── Automation step ────────────────────────────────────────────────────────
// Timezone (auto-detect from browser, allow override)
const timezone = ref(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
const COMMON_TIMEZONES = [
  'UTC',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Toronto', 'America/Vancouver', 'America/Sao_Paulo', 'America/Argentina/Buenos_Aires',
  'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Amsterdam',
  'Europe/Rome', 'Europe/Madrid', 'Europe/Stockholm', 'Europe/Athens', 'Europe/Moscow',
  'Asia/Dubai', 'Asia/Kolkata', 'Asia/Bangkok', 'Asia/Singapore',
  'Asia/Tokyo', 'Asia/Seoul', 'Asia/Shanghai', 'Asia/Hong_Kong',
  'Australia/Sydney', 'Australia/Melbourne', 'Australia/Perth',
  'Pacific/Auckland', 'Pacific/Honolulu',
]
// Ensure detected timezone is in the list
const timezoneOptions = computed(() => {
  const list = [...COMMON_TIMEZONES]
  const detected = Intl.DateTimeFormat().resolvedOptions().timeZone
  if (detected && !list.includes(detected)) list.unshift(detected)
  return list
})

// Kometa
const usingKometa = ref(false)

// Send logos to Plex
const sendLogosToPlex = ref(false)

// Label when poster is sent
const sendLabel = ref(true)
const labelName = ref('Simposter')

// Scan schedule
type ScanFreq = 'never' | 'daily' | 'weekly' | 'custom'
const scanFrequency = ref<ScanFreq>('daily')
const customCron = ref('0 1 * * *')
const scanCronExpression = computed(() => {
  if (scanFrequency.value === 'never') return ''
  if (scanFrequency.value === 'daily') return '0 1 * * *'
  if (scanFrequency.value === 'weekly') return '0 1 * * 0'
  return customCron.value
})

// ── Performance step ───────────────────────────────────────────────────────
const existingContentMode = ref<'regenerate' | 'resend'>('regenerate')
const concurrentRenders = ref(2)
const outputFormat = ref<'jpg' | 'png' | 'webp'>('jpg')
const jpgQuality = ref(95)
const webpQuality = ref(90)

// ── Notifications step ─────────────────────────────────────────────────────
const wantsNotifications = ref(false)
const appriseUrls = ref('')  // one URL per line

// ── Save settings ──────────────────────────────────────────────────────────
const saving = ref(false)
const settingsSaved = ref(false)

const saveSettings = async () => {
  if (settingsSaved.value) return
  saving.value = true
  try {
    const movieMappings = movieLibSections.value
      .filter(s => selectedMovieLibs.value.has(s.key))
      .map(s => ({ id: s.key, title: s.title, displayName: s.title }))

    const tvMappings = tvLibSections.value
      .filter(s => selectedTvLibs.value.has(s.key))
      .map(s => ({ id: s.key, title: s.title, displayName: s.title }))

    // Labels to remove after sending (Kometa adds "Overlay") -- Plex-only concept
    // (Quirk #93), only meaningful when Plex was actually chosen.
    const labelsToRemove = wantsPlex.value && usingKometa.value ? ['Overlay'] : []

    // sendLogosToPlex applies to any linked server today (Quirk #93 relabeled the UI
    // to say so, though the underlying field name stayed the same) so it's always
    // written -- but the rest of this object (url/token/library mappings) is
    // Plex-specific and only overwritten when Plex was actually chosen this run, so
    // re-running the wizard without Plex can't blank out a real prior Plex connection.
    settings.plex.value = wantsPlex.value ? {
      ...settings.plex.value,
      url: plexUrl.value,
      token: plexToken.value,
      movieLibraryName: movieMappings[0]?.title || '',
      movieLibraryNames: movieMappings.map(m => m.title),
      libraryMappings: movieMappings.map(m => ({ ...m })),
      tvShowLibraryName: tvMappings[0]?.title || '',
      tvShowLibraryNames: tvMappings.map(m => m.title),
      tvShowLibraryMappings: tvMappings.map(m => ({ ...m })),
      sendLogosToPlex: sendLogosToPlex.value,
    } : {
      ...settings.plex.value,
      sendLogosToPlex: sendLogosToPlex.value,
    }
    settings.tmdb.value = { apiKey: tmdbApiKey.value.trim() }
    settings.tvdb.value = { ...settings.tvdb.value, apiKey: tvdbApiKey.value.trim() }
    settings.fanart.value = { apiKey: fanartApiKey.value.trim() }
    settings.performance.value = {
      ...settings.performance.value,
      concurrentRenders: concurrentRenders.value,
    }
    settings.imageQuality.value = {
      ...settings.imageQuality.value,
      outputFormat: outputFormat.value,
      jpgQuality: jpgQuality.value,
      webpQuality: webpQuality.value,
    }
    settings.timezone.value = timezone.value
    settings.automation.value = {
      ...settings.automation.value,
      existingContentMode: existingContentMode.value,
      webhookAutoSend: true,
      // "Apply a label after sending" (this step's toggle) tags an item with a label
      // once Simposter sends its poster — that's labelToAdd, not webhookAutoLabels
      // (which instead strips a pre-existing label, e.g. one Kometa/Radarr/Sonarr
      // applied to mark "needs a poster" — handled separately above via
      // defaultLabelsToRemove/usingKometa). Previously this toggle was wired to
      // webhookAutoLabels by mistake, which meant "apply a label" silently did
      // nothing (removing a label that was never there is a no-op) — see CLAUDE.md.
      webhookAlwaysRegenerateSeason: false,
      retryUntilTemplateMet: true,
      // labelToAdd/kometaCompatibility are Plex-only (Quirk #93) -- only include them
      // (overwriting whatever's already there) when Plex was actually chosen this run,
      // matching this step's controls being hidden entirely otherwise.
      ...(wantsPlex.value ? {
        labelToAdd: sendLabel.value ? labelName.value : '',
        kometaCompatibility: usingKometa.value,
      } : {}),
    }
    const allLibIds = [
      ...movieMappings.map(m => m.id),
      ...tvMappings.map(m => m.id),
    ]
    // The scheduled scan covers every server: the Plex libraries listed here (empty =
    // all of them), plus every library group's Jellyfin/Emby libraries. With no Plex,
    // libraryIds is empty and the scheduler just scans the Jellyfin/Emby groups.
    settings.scheduler.value = {
      ...settings.scheduler.value,
      enabled: scanFrequency.value !== 'never',
      cronExpression: scanCronExpression.value || '0 1 * * *',
      // Empty = every library on every server (narrow it later in Settings -> Libraries).
      libraryIds: [],
    }
    // defaultLabelsToRemove keyed by library ID so SettingsView renders correctly --
    // Plex-only concept, skipped entirely when Plex wasn't chosen.
    if (wantsPlex.value) {
      const labelsRecord: Record<string, string[]> = {}
      allLibIds.forEach(id => { labelsRecord[id] = labelsToRemove })
      settings.defaultLabelsToRemove.value = labelsRecord
    }

    // Auto-matched Library Group creation -- FIRST-TIME ONBOARDING ONLY
    // (isRerun guard below). Covers every library selected across every
    // server (not just standalone Jellyfin/Emby ones) -- every selection
    // becomes ITS OWN group unless another selection of the SAME media type has
    // the exact same name (case/whitespace-insensitive), in which case they're
    // merged into one shared group instead. This is the "auto-match" design the
    // user picked directly (over a manual-pairing step) after being asked: pick
    // 3 Plex libraries and 2 Jellyfin libraries whose names each match one of
    // those 3, and you get exactly 3 groups (2 linked, 1 Plex-only) -- no name
    // match anywhere still yields one group per selection, same as the plain
    // standalone-group behavior this replaces. Every group gets a real sidebar
    // tab immediately (App.vue's nonPlexGroupTabs(), Quirk #116) with no separate
    // trip to Settings required; a user can always add/remove members or split a
    // wrongly-matched group apart afterward via Settings -> Libraries -> Linked
    // Libraries (LinkedServerLibraries.vue), exactly as they already can today.
    //
    // Skipped entirely on a re-run (a real, reported bug): movieMappings/
    // tvMappings/nonPlexDiscovered are built from whatever's CURRENTLY
    // configured, not just what changed this run -- on an already-onboarded
    // install, that includes the user's existing, already-deliberately-
    // arranged libraries too. A newly-added Plex library whose name happens
    // to match an existing Jellyfin-only group's name would then bucket
    // together with it, but existingGroupIds.has(g.id) never recognizes the
    // match: the bucket's computed id uses the PLEX-anchored scheme
    // (group-{mediaType}-{plexLibraryId}) while the existing group was
    // created under the standalone scheme (group-{mediaType}-{serverId}-
    // {libraryId}) -- two different ids for what should be one group, so
    // this created a brand-new, DUPLICATE group instead of linking into the
    // existing one, on every wizard re-run. A re-run should only ever touch
    // groups the user explicitly edits in Settings -> Libraries and saves.
    if (!isRerun) {
      interface LibCandidate { serverId: string; libraryId: string; libraryName: string; mediaType: 'movie' | 'tv' }
      const candidates: LibCandidate[] = []
      if (wantsPlex.value) {
        movieMappings.forEach(m => candidates.push({ serverId: 'plex-1', libraryId: String(m.id), libraryName: m.title, mediaType: 'movie' }))
        tvMappings.forEach(m => candidates.push({ serverId: 'plex-1', libraryId: String(m.id), libraryName: m.title, mediaType: 'tv' }))
      }
      nonPlexDiscovered.value
        .filter(d => selectedNonPlexLibs.value.has(nonPlexKey(d)))
        .forEach(d => candidates.push({ serverId: d.serverId, libraryId: d.libraryId, libraryName: d.libraryName, mediaType: d.mediaType as 'movie' | 'tv' }))

      if (candidates.length) {
        // Bucket by (mediaType, normalized name) -- exact match only (no fuzzy/
        // substring matching), so "Movies" and "4K Movies" are deliberately kept
        // separate rather than risking a false-positive merge.
        const buckets = new Map<string, LibCandidate[]>()
        for (const c of candidates) {
          const key = `${c.mediaType}:${c.libraryName.trim().toLowerCase()}`
          if (!buckets.has(key)) buckets.set(key, [])
          buckets.get(key)!.push(c)
        }
        const existingGroupIds = new Set(settings.libraryGroups.value.map(g => g.id))
        const newGroups = Array.from(buckets.values())
          .map(members => {
            const plexMember = members.find(m => m.serverId === 'plex-1')
            const anchor = plexMember || members[0]!
            // Matches the id scheme ensureGroup()/the startup migration already use
            // for a Plex-anchored group (LinkedServerLibraries.vue, Quirk #62), and
            // StandaloneServerLibraries.vue's scheme for a server-only one (Quirk
            // #116) -- so a later manual link/unlink in Settings resolves the SAME
            // group instead of creating a duplicate.
            const id = plexMember
              ? `group-${anchor.mediaType}-${anchor.libraryId}`
              : `group-${anchor.mediaType}-${anchor.serverId}-${anchor.libraryId}`
            return {
              id,
              name: anchor.libraryName || anchor.libraryId,
              mediaType: anchor.mediaType,
              members: members.map(m => ({ serverId: m.serverId, libraryId: m.libraryId, libraryName: m.libraryName })),
              autoGenerateEnabled: false,
              autoGeneratePresetId: null,
              autoGenerateTemplateId: null,
              labelsToRemove: [] as string[],
            }
          })
          .filter(g => !existingGroupIds.has(g.id))
        if (newGroups.length) {
          settings.libraryGroups.value = [...settings.libraryGroups.value, ...newGroups]
        }
      }
    }

    await settings.save()
    settingsSaved.value = true
  } catch { /* still advance */ }
  finally { saving.value = false }
}

// ── Default preset import ──────────────────────────────────────────────────
const importingPreset = ref(false)
const presetImported = ref(false)
const presetError = ref('')

const importDefaultPreset = async () => {
  importingPreset.value = true
  presetError.value = ''
  try {
    const res = await fetch(`${apiBase}/api/presets/default-template`)
    if (!res.ok) throw new Error('Failed to fetch default preset')
    const data = await res.json()
    const importRes = await fetch(`${apiBase}/api/presets/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!importRes.ok) throw new Error('Failed to import preset')
    presetImported.value = true
  } catch (e) {
    presetError.value = e instanceof Error ? e.message : 'Import failed'
  } finally {
    importingPreset.value = false
  }
}

// ── Save Plex settings early (before full saveSettings) ───────────────────
const savePlexEarly = async () => {
  const movieMappings = movieLibSections.value
    .filter(s => selectedMovieLibs.value.has(s.key))
    .map(s => ({ id: s.key, title: s.title, displayName: s.title }))
  const tvMappings = tvLibSections.value
    .filter(s => selectedTvLibs.value.has(s.key))
    .map(s => ({ id: s.key, title: s.title, displayName: s.title }))
  settings.plex.value = {
    ...settings.plex.value,
    url: plexUrl.value,
    token: plexToken.value,
    movieLibraryName: movieMappings[0]?.title || '',
    movieLibraryNames: movieMappings.map(m => m.title),
    libraryMappings: movieMappings,
    tvShowLibraryName: tvMappings[0]?.title || '',
    tvShowLibraryNames: tvMappings.map(m => m.title),
    tvShowLibraryMappings: tvMappings,
  }
  await settings.save()
}

// ── Navigation ─────────────────────────────────────────────────────────────
// Plex, Jellyfin and Emby are treated the same on the 'connect' step: Next is
// enabled once at least one picked server has connected. Picked servers that
// weren't tested are dropped from this run (they can be added later in
// Settings -> Media Servers).
const connectedCount = computed(() =>
  (wantsPlex.value && plexOk.value ? 1 : 0) +
  (wantsJellyfinServer.value && jellyfinOk.value ? 1 : 0) +
  (wantsEmbyServer.value && embyOk.value ? 1 : 0)
)

const canAdvance = computed(() => {
  if (step.value === 'servers') return canAdvanceServers.value
  if (step.value === 'connect') return connectedCount.value > 0
  if (step.value === 'apikeys') return canAdvanceApiKeys.value
  return true
})

// Navigate by scanning forward/backward through the FULL step list for the next
// one that's in visibleSteps, rather than indexing into visibleSteps -- safe even
// if a handler changes what's visible in the same tick it calls goNext().
const goNext = async () => {
  if (step.value === 'connect') {
    // A picked server that wasn't connected is skipped for this run.
    if (wantsPlex.value && !plexOk.value) wantsPlex.value = false
    if (wantsJellyfinServer.value && !jellyfinOk.value) wantsJellyfinServer.value = false
    if (wantsEmbyServer.value && !embyOk.value) wantsEmbyServer.value = false
    if (plexOk.value) initLibraries()
    // Save Jellyfin/Emby immediately, same reasoning as the Plex early-save below — don't let a
    // real, successfully-tested server sit only in local component state until
    // the wizard's much-later final save, in case the user closes out early.
    // Merge rather than overwrite: mediaServers may already hold entries seeded
    // by the backend (Quirk #57) or from a prior run — replace by id, don't
    // just append blindly (Quirk #70).
    const toAdd = [
      jellyfinOk.value ? addedJellyfinServer.value : null,
      embyOk.value ? addedEmbyServer.value : null,
    ].filter((s): s is MediaServerEntry => !!s)
    if (toAdd.length) {
      const addIds = new Set(toAdd.map(s => s.id))
      const existing = settings.mediaServers.value.filter(s => !addIds.has(s.id))
      settings.mediaServers.value = [...existing, ...toAdd]
      await settings.save()
    }
    // Discover what's actually on the server(s) just saved, for the upcoming
    // 'libraries' step -- GET /api/media-server/libraries only sees servers
    // already present in the saved mediaServers setting, hence fetching this
    // only after the save above, not any earlier.
    await fetchNonPlexLibraries()
  }
  if (step.value === 'libraries') {
    if (wantsPlex.value) {
      // Save Plex connection + selected library mappings either way -- a
      // re-run still needs this persisted so the wizard doesn't lose it if
      // closed early. Only the SCAN itself (below) is skipped on a re-run.
      await savePlexEarly()
      if (!isRerun) {
        // Fire-and-forget — scan runs in the background while user completes setup.
        // First-time onboarding only: a re-run's own auto-scan-on-save (Quirk #33,
        // triggered by the normal Settings -> Libraries save path once the wizard
        // finishes) already covers whatever the user actually changed, scoped to
        // just that -- firing this too would additionally rescan every
        // already-configured library the user didn't touch this run.
        fetch(`${apiBase}/api/scan-library`, { method: 'POST' }).catch(() => {})
      }
    }
    // Same fire-and-forget pattern for whichever Jellyfin/Emby libraries were
    // selected -- POST /api/media-server/{server_id}/scan (Quirk #66's scoped
    // scan), the exact same call StandaloneServerLibraries.vue's own "Scan"
    // button makes. The LibraryGroups these libraries belong to are created
    // later in saveSettings() (called from the 'performance' step below) --
    // scanning doesn't need the group to exist first (Quirk #116: a standalone
    // library's rows filter correctly by library_id alone). First-time only,
    // same reasoning as the Plex scan above.
    if (!isRerun) {
      nonPlexDiscovered.value
        .filter(d => selectedNonPlexLibs.value.has(nonPlexKey(d)))
        .forEach(d => {
          const params = new URLSearchParams({ library_id: d.libraryId, media_type: d.mediaType })
          fetch(`${apiBase}/api/media-server/${d.serverId}/scan?${params.toString()}`, { method: 'POST' }).catch(() => {})
        })
    }
  }
  if (step.value === 'performance') await saveSettings()
  if (step.value === 'notifications') {
    // Save notification prefs, then auto-import the default preset in the background
    settings.notifications.value = {
      ...settings.notifications.value,
      appriseEnabled: wantsNotifications.value && !!appriseUrls.value.trim(),
      appriseUrls: wantsNotifications.value
        ? appriseUrls.value.split('\n').map(u => u.trim()).filter(Boolean)
        : [],
    }
    await settings.save()
    importDefaultPreset()  // fire-and-forget; finish step shows progress passively
  }
  let nextIdx = STEPS.indexOf(step.value) + 1
  while (nextIdx < STEPS.length && !visibleSteps.value.includes(STEPS[nextIdx]!)) nextIdx++
  if (nextIdx < STEPS.length) step.value = STEPS[nextIdx]!
}

const goBack = () => {
  let idx = STEPS.indexOf(step.value) - 1
  while (idx >= 0 && !visibleSteps.value.includes(STEPS[idx]!)) idx--
  if (idx >= 0) step.value = STEPS[idx]!
}

// ── Close ──────────────────────────────────────────────────────────────────
const markOnboardingDone = async () => {
  try {
    // Defense-in-depth: saveSettings() (above) is only ever triggered from
    // ONE specific step-transition (`if (step.value === 'performance')` in
    // goNext()) -- if that exact moment is ever missed for any reason (an
    // odd navigation path, a step-index edge case, etc.), the wizard's real
    // collected automation/performance/Plex/library-group fields never make
    // it to the backend at all, and they'd otherwise stay stranded at their
    // plain in-memory defaults -- which the unconditional settings.save()
    // below would then persist AS the final result, silently discarding
    // whatever the user actually configured (a real, reported case: the
    // "existing content mode" toggle showing its default in the DB despite
    // being set to "resend" in the wizard). Calling it again here is a safe
    // no-op in the normal case (its own settingsSaved guard already fired),
    // and the real save in the bug case -- either way, this function is the
    // ONE path guaranteed to run on every close/skip.
    await saveSettings()
    settings.onboardingCompleted.value = true
    await settings.save()
  } catch { /* non-fatal */ }
}

const close = async () => {
  await markOnboardingDone()
  await settings.load()
  emit('done')
  // Scan was already started when the user advanced from the libraries step;
  // just hook into polling so the UI reflects scan progress
  ;(window as any).startScanPolling?.()
}

const skip = async () => {
  await markOnboardingDone()
  await settings.load()
  emit('done')
}

onMounted(() => {
  if (settings.plex.value.url) plexUrl.value = settings.plex.value.url
  if (settings.plex.value.token) plexToken.value = settings.plex.value.token
  if (settings.tmdb.value.apiKey) tmdbApiKey.value = settings.tmdb.value.apiKey
  if (settings.tvdb.value.apiKey) tvdbApiKey.value = settings.tvdb.value.apiKey
  if (settings.fanart.value.apiKey) fanartApiKey.value = settings.fanart.value.apiKey
  // Re-running the wizard (Settings → Advanced → Run Startup Wizard) with servers
  // already configured: pre-check/prefill for context, but deliberately leave API
  // keys/tokens blank rather than the masked placeholder GET /api/ui-settings
  // returns (Quirk #60's secret masking) — sending that placeholder straight into
  // Test Connection would just fail, since restore-if-unchanged only applies on
  // save, not on this endpoint. Plex defaults to checked either way (matches this
  // step's own default for a fresh install); Jellyfin/Emby only pre-check if a
  // real entry of that type already exists.
  wantsPlex.value = true
  const existingJellyfin = settings.mediaServers.value.find(s => s.type === 'jellyfin')
  if (existingJellyfin) {
    wantsJellyfinServer.value = true
    jellyfinUrl.value = existingJellyfin.url
  }
  const existingEmby = settings.mediaServers.value.find(s => s.type === 'emby')
  if (existingEmby) {
    wantsEmbyServer.value = true
    embyUrl.value = existingEmby.url
  }
})
</script>

<template>
  <Teleport to="body">
    <div class="ob-backdrop">
      <div class="ob-modal">
        <!-- Progress dots -->
        <div class="ob-dots">
          <span
            v-for="(s, i) in visibleSteps"
            :key="s"
            class="ob-dot"
            :class="{ active: i === stepIndex, done: i < stepIndex }"
          />
        </div>

        <!-- ── Welcome ── -->
        <template v-if="step === 'welcome'">
          <div class="ob-icon">🎬</div>
          <h2 class="ob-title">Welcome to Simposter</h2>
          <p class="ob-sub">Let's get you set up in a few quick steps. You'll connect your media server(s), pick your libraries, and configure your defaults.</p>
          <div class="ob-actions">
            <button class="ob-btn-ghost" @click="skip">Skip setup</button>
            <button class="ob-btn-primary" @click="goNext">Get started</button>
          </div>
        </template>

        <!-- ── Servers (which to configure) ── -->
        <template v-else-if="step === 'servers'">
          <div class="ob-icon">🖥️</div>
          <h2 class="ob-title">Which media server(s) do you use?</h2>
          <p class="ob-sub">Pick any combination — Simposter can send posters to more than one server at once.</p>
          <label class="ob-lib-row" :class="{ selected: wantsPlex }" @click="wantsPlex = !wantsPlex">
            <span class="ob-checkbox" :class="{ checked: wantsPlex }">
              <svg v-if="wantsPlex" width="12" height="12" viewBox="0 0 12 12" fill="none"><polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </span>
            <img src="/icons/plex.svg" class="ob-server-icon" alt="" />
            Plex
          </label>
          <label class="ob-lib-row" :class="{ selected: wantsJellyfinServer }" @click="wantsJellyfinServer = !wantsJellyfinServer">
            <span class="ob-checkbox" :class="{ checked: wantsJellyfinServer }">
              <svg v-if="wantsJellyfinServer" width="12" height="12" viewBox="0 0 12 12" fill="none"><polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </span>
            <img src="/icons/jellyfin.svg" class="ob-server-icon" alt="" />
            Jellyfin
          </label>
          <label class="ob-lib-row" :class="{ selected: wantsEmbyServer }" @click="wantsEmbyServer = !wantsEmbyServer">
            <span class="ob-checkbox" :class="{ checked: wantsEmbyServer }">
              <svg v-if="wantsEmbyServer" width="12" height="12" viewBox="0 0 12 12" fill="none"><polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </span>
            <img src="/icons/emby.svg" class="ob-server-icon" alt="" />
            Emby
          </label>
          <div class="ob-actions">
            <button class="ob-btn-ghost" @click="goBack">Back</button>
            <button class="ob-btn-primary" :disabled="!canAdvance" @click="goNext">Next</button>
          </div>
        </template>

        <!-- ── Connect: one identical section per picked server ── -->
        <template v-else-if="step === 'connect'">
          <div class="ob-icon">🖥️</div>
          <h2 class="ob-title">Connect your servers</h2>
          <p class="ob-sub">Enter the connection details for each server you picked, and test it.</p>

          <div v-if="wantsPlex" class="ob-form ob-server-form">
            <div class="ob-server-heading"><img src="/icons/plex.svg" class="ob-server-icon" alt="" /> Plex</div>
            <label class="ob-label">Server URL</label>
            <input v-model="plexUrl" class="ob-input" type="url" placeholder="http://192.168.1.100:32400" @keyup.enter="testPlex" @input="plexOk = false" />
            <label class="ob-label">Token</label>
            <input v-model="plexToken" class="ob-input" type="password" placeholder="Plex Web → Account → Authorized Devices" @keyup.enter="testPlex" @input="plexOk = false" />
            <div v-if="plexError" class="ob-error">{{ plexError }}</div>
            <div v-if="plexOk" class="ob-success">
              Connected! Found {{ plexSections.filter(s => s.type === 'movie').length }} movie {{ plexSections.filter(s => s.type === 'movie').length === 1 ? 'library' : 'libraries' }}<template v-if="plexSections.filter(s => s.type === 'show').length > 0"> and {{ plexSections.filter(s => s.type === 'show').length }} TV {{ plexSections.filter(s => s.type === 'show').length === 1 ? 'library' : 'libraries' }}</template>.
            </div>
            <div class="ob-actions ob-server-actions">
              <button class="ob-btn-secondary" :disabled="testingPlex || !plexUrl || !plexToken" @click="testPlex">
                <span v-if="testingPlex" class="ob-spinner" />
                {{ testingPlex ? 'Testing...' : 'Test connection' }}
              </button>
            </div>
          </div>

          <div v-if="wantsJellyfinServer" class="ob-form ob-server-form">
            <div class="ob-server-heading"><img src="/icons/jellyfin.svg" class="ob-server-icon" alt="" /> Jellyfin</div>
            <label class="ob-label">Server URL</label>
            <input v-model="jellyfinUrl" class="ob-input" type="url" placeholder="http://192.168.1.100:8096" @keyup.enter="testJellyfin" @input="jellyfinOk = false" />
            <label class="ob-label">API Key</label>
            <input v-model="jellyfinApiKey" class="ob-input" type="password" placeholder="Dashboard → API Keys" @keyup.enter="testJellyfin" @input="jellyfinOk = false" />
            <div v-if="jellyfinError" class="ob-error">{{ jellyfinError }}</div>
            <div v-if="jellyfinOk" class="ob-success">Connected!</div>
            <div class="ob-actions ob-server-actions">
              <button class="ob-btn-secondary" :disabled="testingJellyfin || !jellyfinUrl || !jellyfinApiKey" @click="testJellyfin">
                <span v-if="testingJellyfin" class="ob-spinner" />
                {{ testingJellyfin ? 'Testing...' : 'Test connection' }}
              </button>
            </div>
          </div>

          <div v-if="wantsEmbyServer" class="ob-form ob-server-form">
            <div class="ob-server-heading"><img src="/icons/emby.svg" class="ob-server-icon" alt="" /> Emby</div>
            <label class="ob-label">Server URL</label>
            <input v-model="embyUrl" class="ob-input" type="url" placeholder="http://192.168.1.100:8096" @keyup.enter="testEmby" @input="embyOk = false" />
            <label class="ob-label">API Key</label>
            <input v-model="embyApiKey" class="ob-input" type="password" placeholder="Dashboard → API Keys" @keyup.enter="testEmby" @input="embyOk = false" />
            <div v-if="embyError" class="ob-error">{{ embyError }}</div>
            <div v-if="embyOk" class="ob-success">Connected!</div>
            <div class="ob-actions ob-server-actions">
              <button class="ob-btn-secondary" :disabled="testingEmby || !embyUrl || !embyApiKey" @click="testEmby">
                <span v-if="testingEmby" class="ob-spinner" />
                {{ testingEmby ? 'Testing...' : 'Test connection' }}
              </button>
            </div>
          </div>

          <p class="ob-hint-text" style="margin-top: 12px;">
            Connect at least one server to continue. Any you don't test now are skipped — add them later in Settings → Media Servers.
          </p>
          <div class="ob-actions">
            <button class="ob-btn-ghost" @click="goBack">Back</button>
            <button class="ob-btn-primary" :disabled="!canAdvance" @click="goNext">Next</button>
          </div>
        </template>

        <!-- ── Libraries (covers whichever server(s) were picked) ── -->
        <template v-else-if="step === 'libraries'">
          <div class="ob-icon">📚</div>
          <h2 class="ob-title">Select your libraries</h2>
          <p class="ob-sub">Choose which libraries Simposter should manage.</p>
          <!-- One list per media type, every server's libraries side by side and
               tagged with their server. Plex libraries come from the connection
               test; Jellyfin/Emby ones are discovered right after the 'connect'
               step saves those servers (fetchNonPlexLibraries()). -->
          <div class="ob-lib-section" v-if="(wantsPlex && movieLibSections.length > 0) || nonPlexMovieLibs.length > 0">
            <div class="ob-lib-heading">Movie libraries</div>
            <template v-if="wantsPlex">
              <label v-for="lib in movieLibSections" :key="'plex:' + lib.key" class="ob-lib-row" :class="{ selected: selectedMovieLibs.has(lib.key) }" @click="toggleMovieLib(lib.key)">
                <span class="ob-checkbox" :class="{ checked: selectedMovieLibs.has(lib.key) }">
                  <svg v-if="selectedMovieLibs.has(lib.key)" width="12" height="12" viewBox="0 0 12 12" fill="none"><polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </span>
                🎬 {{ lib.title }} <span class="ob-optional">(plex)</span>
              </label>
            </template>
            <label v-for="lib in nonPlexMovieLibs" :key="nonPlexKey(lib)" class="ob-lib-row" :class="{ selected: selectedNonPlexLibs.has(nonPlexKey(lib)) }" @click="toggleNonPlexLib(lib)">
              <span class="ob-checkbox" :class="{ checked: selectedNonPlexLibs.has(nonPlexKey(lib)) }">
                <svg v-if="selectedNonPlexLibs.has(nonPlexKey(lib))" width="12" height="12" viewBox="0 0 12 12" fill="none"><polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </span>
              🎬 {{ lib.libraryName }} <span class="ob-optional">({{ lib.serverType }})</span>
            </label>
          </div>
          <div class="ob-lib-section" v-if="(wantsPlex && tvLibSections.length > 0) || nonPlexTvLibs.length > 0">
            <div class="ob-lib-heading">TV show libraries</div>
            <template v-if="wantsPlex">
              <label v-for="lib in tvLibSections" :key="'plex:' + lib.key" class="ob-lib-row" :class="{ selected: selectedTvLibs.has(lib.key) }" @click="toggleTvLib(lib.key)">
                <span class="ob-checkbox" :class="{ checked: selectedTvLibs.has(lib.key) }">
                  <svg v-if="selectedTvLibs.has(lib.key)" width="12" height="12" viewBox="0 0 12 12" fill="none"><polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </span>
                📺 {{ lib.title }} <span class="ob-optional">(plex)</span>
              </label>
            </template>
            <label v-for="lib in nonPlexTvLibs" :key="nonPlexKey(lib)" class="ob-lib-row" :class="{ selected: selectedNonPlexLibs.has(nonPlexKey(lib)) }" @click="toggleNonPlexLib(lib)">
              <span class="ob-checkbox" :class="{ checked: selectedNonPlexLibs.has(nonPlexKey(lib)) }">
                <svg v-if="selectedNonPlexLibs.has(nonPlexKey(lib))" width="12" height="12" viewBox="0 0 12 12" fill="none"><polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </span>
              📺 {{ lib.libraryName }} <span class="ob-optional">({{ lib.serverType }})</span>
            </label>
          </div>
          <div class="ob-actions">
            <button class="ob-btn-ghost" @click="goBack">Back</button>
            <button class="ob-btn-primary" :disabled="!canAdvance" @click="goNext">Next</button>
          </div>
        </template>

        <!-- ── API Keys ── -->
        <template v-else-if="step === 'apikeys'">
          <div class="ob-icon">🔑</div>
          <h2 class="ob-title">API keys</h2>
          <p class="ob-sub">Simposter uses these to fetch posters and logos. Get free keys from each provider's developer portal.</p>
          <div class="ob-form">
            <div class="ob-key-row">
              <div class="ob-key-header">
                <label class="ob-label">TMDb API key <span class="ob-required">required</span></label>
                <a class="ob-key-link" href="https://www.themoviedb.org/settings/api" target="_blank" rel="noopener">Get key →</a>
              </div>
              <div class="ob-key-input-row">
                <input v-model="tmdbApiKey" class="ob-input" :class="{ 'ob-input-error': tmdbMissing }" type="password" placeholder="eyJhbGciOiJIUzI1NiJ9..." @input="tmdbStatus = 'idle'" />
                <button class="ob-btn-test" :disabled="!tmdbApiKey.trim() || tmdbStatus === 'testing'" @click="testTmdb">
                  <span v-if="tmdbStatus === 'testing'" class="ob-spinner" />
                  <span v-else>Test</span>
                </button>
              </div>
              <div v-if="tmdbStatus === 'ok'" class="ob-key-status ok">✓ {{ tmdbStatusMsg }}</div>
              <div v-else-if="tmdbStatus === 'error'" class="ob-key-status error">✗ {{ tmdbStatusMsg }}</div>
            </div>
            <div class="ob-key-row">
              <div class="ob-key-header">
                <label class="ob-label">TVDb API key
                  <span v-if="hasTvLibs" class="ob-required">required for TV</span>
                  <span v-else class="ob-optional">optional</span>
                </label>
                <a class="ob-key-link" href="https://thetvdb.com/api-information" target="_blank" rel="noopener">Get key →</a>
              </div>
              <div class="ob-key-input-row">
                <input v-model="tvdbApiKey" class="ob-input" :class="{ 'ob-input-error': tvdbMissing }" type="password" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" @input="tvdbStatus = 'idle'" />
                <button class="ob-btn-test" :disabled="!tvdbApiKey.trim() || tvdbStatus === 'testing'" @click="testTvdb">
                  <span v-if="tvdbStatus === 'testing'" class="ob-spinner" />
                  <span v-else>Test</span>
                </button>
              </div>
              <div v-if="tvdbStatus === 'ok'" class="ob-key-status ok">✓ {{ tvdbStatusMsg }}</div>
              <div v-else-if="tvdbStatus === 'error'" class="ob-key-status error">✗ {{ tvdbStatusMsg }}</div>
            </div>
            <div class="ob-key-row">
              <div class="ob-key-header">
                <label class="ob-label">Fanart.tv API key <span class="ob-optional">optional</span></label>
                <a class="ob-key-link" href="https://fanart.tv/get-an-api-key/" target="_blank" rel="noopener">Get key →</a>
              </div>
              <div class="ob-key-input-row">
                <input v-model="fanartApiKey" class="ob-input" type="password" placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" @input="fanartStatus = 'idle'" />
                <button class="ob-btn-test" :disabled="!fanartApiKey.trim() || fanartStatus === 'testing'" @click="testFanart">
                  <span v-if="fanartStatus === 'testing'" class="ob-spinner" />
                  <span v-else>Test</span>
                </button>
              </div>
              <div v-if="fanartStatus === 'ok'" class="ob-key-status ok">✓ {{ fanartStatusMsg }}</div>
              <div v-else-if="fanartStatus === 'error'" class="ob-key-status error">✗ {{ fanartStatusMsg }}</div>
              <div class="ob-hint-text">Recommended if you plan to make posters for Plex Collections — it's the only source of franchise/collection logos (TMDb has none).</div>
            </div>
          </div>
          <div class="ob-actions">
            <button class="ob-btn-ghost" @click="goBack">Back</button>
            <button class="ob-btn-primary" :disabled="!canAdvance" @click="goNext">Next</button>
          </div>
        </template>

        <!-- ── Automation ── -->
        <template v-else-if="step === 'automation'">
          <div class="ob-icon">⚙️</div>
          <h2 class="ob-title">Automation</h2>
          <p class="ob-sub">A few quick preferences for how Simposter runs in the background.</p>

          <div class="ob-form">
            <!-- Kometa / "Apply a label" — both Plex-only concepts (label add/remove
                 has no Jellyfin/Emby equivalent, Quirk #59/#93), hidden entirely rather
                 than shown-but-inert when Plex wasn't picked on the 'servers' step. -->
            <template v-if="wantsPlex">
              <div class="ob-switch-row" @click="usingKometa = !usingKometa">
                <div class="ob-switch-body">
                  <div class="ob-switch-label">Using Kometa?</div>
                  <div class="ob-switch-desc">If yes, Simposter will remove the "Overlay" label from Plex items after sending a poster so Kometa doesn't overwrite your artwork.</div>
                </div>
                <div class="ob-switch" :class="{ on: usingKometa }"><div class="ob-switch-thumb" /></div>
              </div>

              <div class="ob-switch-row" @click="sendLabel = !sendLabel">
                <div class="ob-switch-body">
                  <div class="ob-switch-label">Apply a label after sending a poster?</div>
                  <div class="ob-switch-desc">Tags Plex items with a label so you can track which posters were generated by Simposter.</div>
                </div>
                <div class="ob-switch" :class="{ on: sendLabel }"><div class="ob-switch-thumb" /></div>
              </div>
              <div v-if="sendLabel" class="ob-indent">
                <label class="ob-label">Label name</label>
                <input v-model="labelName" class="ob-input" type="text" placeholder="Simposter" />
              </div>
            </template>

            <!-- Applies to any linked server today, not Plex-only (Quirk #93) -- shown
                 regardless of which server(s) were picked. -->
            <div class="ob-switch-row" @click="sendLogosToPlex = !sendLogosToPlex">
              <div class="ob-switch-body">
                <div class="ob-switch-label">Send logos to your media server(s)?</div>
                <div class="ob-switch-desc">After generating a poster, also upload the clear logo so it appears in your media info panels.</div>
              </div>
              <div class="ob-switch" :class="{ on: sendLogosToPlex }"><div class="ob-switch-thumb" /></div>
            </div>

            <!-- Timezone -->
            <div class="ob-field-group">
              <div class="ob-field-label">Timezone</div>
              <div class="ob-field-desc">Used for scheduled scan times. Auto-detected from your browser.</div>
              <select v-model="timezone" class="ob-input ob-select">
                <option v-for="tz in timezoneOptions" :key="tz" :value="tz">{{ tz }}</option>
              </select>
            </div>

            <!-- Scan schedule -- covers every connected server's libraries. -->
            <div class="ob-field-group">
              <div class="ob-field-label">How often should Simposter scan for new content?</div>
              <div class="ob-seg">
                <button class="ob-seg-btn" :class="{ active: scanFrequency === 'never' }" @click="scanFrequency = 'never'">Never</button>
                <button class="ob-seg-btn" :class="{ active: scanFrequency === 'daily' }" @click="scanFrequency = 'daily'">Daily</button>
                <button class="ob-seg-btn" :class="{ active: scanFrequency === 'weekly' }" @click="scanFrequency = 'weekly'">Weekly</button>
                <button class="ob-seg-btn" :class="{ active: scanFrequency === 'custom' }" @click="scanFrequency = 'custom'">Custom</button>
              </div>
              <div v-if="scanFrequency === 'custom'" class="ob-indent">
                <label class="ob-label">Cron expression</label>
                <input v-model="customCron" class="ob-input ob-input-mono" type="text" placeholder="0 1 * * *" />
                <div class="ob-hint-text">minute hour day month weekday — e.g. <code>0 1 * * *</code> = daily at 1 AM</div>
              </div>
              <div v-else-if="scanFrequency !== 'never'" class="ob-hint-text">{{ scanFrequency === 'daily' ? 'Runs at 1 AM every day' : 'Runs at 1 AM every Sunday' }}</div>
            </div>
          </div>

          <div class="ob-actions">
            <button class="ob-btn-ghost" @click="goBack">Back</button>
            <button class="ob-btn-primary" @click="goNext">Next</button>
          </div>
        </template>

        <!-- ── Performance ── -->
        <template v-else-if="step === 'performance'">
          <div class="ob-icon">⚡</div>
          <h2 class="ob-title">Performance</h2>
          <p class="ob-sub">Set rendering defaults. These can be changed any time in Settings → Performance.</p>
          <div class="ob-form">
            <div class="ob-field-group">
              <div class="ob-field-label">When a poster already exists</div>
              <div class="ob-field-desc">What should Simposter do when an item already has a custom poster?</div>
              <div class="ob-toggle-group">
                <button class="ob-toggle-btn" :class="{ active: existingContentMode === 'regenerate' }" @click="existingContentMode = 'regenerate'">
                  <span class="ob-toggle-icon">🔄</span>
                  <div><div class="ob-toggle-name">Regenerate</div><div class="ob-toggle-desc">Always recreate from scratch</div></div>
                </button>
                <button class="ob-toggle-btn" :class="{ active: existingContentMode === 'resend' }" @click="existingContentMode = 'resend'">
                  <span class="ob-toggle-icon">📤</span>
                  <div><div class="ob-toggle-name">Resend</div><div class="ob-toggle-desc">Reuse the cached poster if one exists</div></div>
                </button>
              </div>
            </div>
            <div class="ob-field-group">
              <div class="ob-field-label">Concurrent renders</div>
              <div class="ob-field-desc">Posters generated in parallel during batch runs (1–4).</div>
              <div class="ob-slider-row">
                <input v-model.number="concurrentRenders" type="range" min="1" max="4" class="ob-slider" />
                <span class="ob-slider-val">{{ concurrentRenders }}</span>
              </div>
            </div>
            <div class="ob-field-group">
              <div class="ob-field-label">Output format</div>
              <div class="ob-field-desc">File format for generated posters. JPEG is recommended for Plex compatibility.</div>
              <div class="ob-seg">
                <button class="ob-seg-btn" :class="{ active: outputFormat === 'jpg' }" @click="outputFormat = 'jpg'">JPEG</button>
                <button class="ob-seg-btn" :class="{ active: outputFormat === 'png' }" @click="outputFormat = 'png'">PNG</button>
                <button class="ob-seg-btn" :class="{ active: outputFormat === 'webp' }" @click="outputFormat = 'webp'">WebP</button>
              </div>
            </div>
            <div v-if="outputFormat === 'jpg'" class="ob-field-group">
              <div class="ob-field-label">JPEG quality <span class="ob-quality-val">{{ jpgQuality }}</span></div>
              <div class="ob-slider-row">
                <input v-model.number="jpgQuality" type="range" min="60" max="100" class="ob-slider" />
                <span class="ob-slider-val">{{ jpgQuality }}</span>
              </div>
            </div>
            <div v-if="outputFormat === 'webp'" class="ob-field-group">
              <div class="ob-field-label">WebP quality <span class="ob-quality-val">{{ webpQuality }}</span></div>
              <div class="ob-slider-row">
                <input v-model.number="webpQuality" type="range" min="60" max="100" class="ob-slider" />
                <span class="ob-slider-val">{{ webpQuality }}</span>
              </div>
            </div>
          </div>
          <div class="ob-actions">
            <button class="ob-btn-ghost" @click="goBack">Back</button>
            <button class="ob-btn-primary" :disabled="saving" @click="goNext">
              <span v-if="saving" class="ob-spinner" />
              {{ saving ? 'Saving...' : 'Next' }}
            </button>
          </div>
        </template>

        <!-- ── Notifications ── -->
        <template v-else-if="step === 'notifications'">
          <div class="ob-icon">🔔</div>
          <h2 class="ob-title">Notifications</h2>
          <p class="ob-sub">Get notified when posters are generated via Discord, Slack, email, or 70+ services through Apprise.</p>

          <div class="ob-switch-row" @click="wantsNotifications = !wantsNotifications">
            <div class="ob-switch-body">
              <div class="ob-switch-label">Enable notifications?</div>
              <div class="ob-switch-desc">Uses Apprise — supports Discord, Slack, Telegram, email, and 70+ more via URL schemes.</div>
            </div>
            <div class="ob-switch" :class="{ on: wantsNotifications }"><div class="ob-switch-thumb" /></div>
          </div>

          <div v-if="wantsNotifications" class="ob-indent ob-notif-urls">
            <label class="ob-label">Apprise URL(s) <span class="ob-optional">one per line</span></label>
            <textarea
              v-model="appriseUrls"
              class="ob-input ob-textarea"
              rows="3"
              placeholder="discord://webhook_id/webhook_token&#10;slack://tokenA/tokenB/tokenC"
            />
            <div class="ob-hint-text">Find your URL scheme at <a href="https://github.com/caronc/apprise/wiki" target="_blank" rel="noopener" class="ob-key-link">Apprise wiki →</a></div>
          </div>

          <div class="ob-actions">
            <button class="ob-btn-ghost" @click="goBack">Back</button>
            <button class="ob-btn-primary" @click="goNext">Next</button>
          </div>
        </template>

        <!-- ── Finish ── -->
        <template v-else-if="step === 'finish'">
          <div class="ob-icon">🎉</div>
          <h2 class="ob-title">You're all set!</h2>
          <p class="ob-sub">Simposter is configured and your library scan has started. A set of starter presets is ready to go.</p>

          <div class="ob-preset-card" :class="{ imported: presetImported }">
            <div class="ob-preset-card-icon">{{ importingPreset ? '⏳' : presetImported ? '✅' : '🎨' }}</div>
            <div class="ob-preset-card-body">
              <div class="ob-preset-card-name">Starter presets</div>
              <div class="ob-preset-card-desc">
                <span v-if="importingPreset">Importing...</span>
                <span v-else-if="presetImported">Imported — simposter-main, budget-daps, textless-border, stock-poster (Uniform Logo) + Plex-Requests, LEAVING-SOON (Kometa)</span>
                <span v-else-if="presetError" class="ob-preset-card-err">{{ presetError }}</span>
                <span v-else>4 Uniform Logo looks + 2 Kometa collection presets</span>
              </div>
            </div>
            <div class="ob-preset-card-action">
              <span v-if="importingPreset" class="ob-spinner" />
              <span v-else-if="presetImported" class="ob-imported-badge">✓</span>
            </div>
          </div>

          <div class="ob-actions">
            <button class="ob-btn-ghost" @click="goBack">Back</button>
            <button class="ob-btn-primary" @click="close">Go to Simposter</button>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ob-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9000;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.ob-modal {
  background: #12141f;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  padding: 32px 28px 24px;
  width: 100%;
  max-width: 520px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.6);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Progress dots */
.ob-dots { display: flex; gap: 6px; justify-content: center; }
.ob-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  transition: all 0.2s;
}
.ob-dot.active { background: var(--accent, #3dd6b7); width: 20px; border-radius: 4px; }
.ob-dot.done { background: rgba(61, 214, 183, 0.4); }

.ob-icon { font-size: 34px; text-align: center; line-height: 1; }
.ob-title { margin: 0; font-size: 21px; font-weight: 700; color: #eef2ff; text-align: center; }
.ob-sub { margin: 0; font-size: 13px; color: #8892aa; text-align: center; line-height: 1.5; }

/* Form */
.ob-form { display: flex; flex-direction: column; gap: 14px; }

.ob-label {
  font-size: 11px; font-weight: 600; color: #a8b3cf;
  text-transform: uppercase; letter-spacing: 0.05em;
  margin-bottom: 4px; display: block;
}

.ob-input {
  width: 100%; padding: 9px 11px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px; color: #eef2ff; font-size: 14px;
  box-sizing: border-box; transition: border-color 0.15s;
}
.ob-input:focus { outline: none; border-color: var(--accent, #3dd6b7); }
.ob-input-error { border-color: rgba(255, 100, 100, 0.5) !important; }
.ob-input-mono { font-family: monospace; }

/* API key rows */
.ob-key-row { display: flex; flex-direction: column; gap: 5px; }
.ob-key-header { display: flex; align-items: center; justify-content: space-between; }
.ob-key-input-row { display: flex; gap: 6px; }
.ob-key-input-row .ob-input { flex: 1; }
.ob-key-link { font-size: 11px; color: var(--accent, #3dd6b7); text-decoration: none; }
.ob-key-link:hover { text-decoration: underline; }
.ob-key-status { font-size: 12px; padding: 3px 0; }
.ob-key-status.ok { color: var(--accent, #3dd6b7); }
.ob-key-status.error { color: #ff8080; }
.ob-btn-test {
  padding: 0 14px; background: rgba(255, 255, 255, 0.07); color: #dbe4ff;
  border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px; font-size: 13px;
  font-weight: 600; cursor: pointer; white-space: nowrap; display: flex; align-items: center; gap: 6px;
  transition: background 0.15s; flex-shrink: 0;
}
.ob-btn-test:disabled { opacity: 0.45; cursor: not-allowed; }
.ob-btn-test:not(:disabled):hover { background: rgba(255, 255, 255, 0.11); }
.ob-required { font-size: 10px; font-weight: 700; color: #ff8080; text-transform: uppercase; margin-left: 6px; }
.ob-optional { font-size: 10px; color: #8892aa; text-transform: uppercase; margin-left: 6px; }

/* Notifications */
.ob-notif-urls { margin-top: 4px; }
.ob-textarea { resize: vertical; min-height: 72px; font-family: monospace; font-size: 13px; line-height: 1.5; }

/* Preset card error text */
.ob-preset-card-err { color: #ff8080; }

/* Status messages */
.ob-error { padding: 10px 12px; background: rgba(255, 100, 100, 0.1); border: 1px solid rgba(255, 100, 100, 0.25); border-radius: 8px; color: #ff8080; font-size: 13px; }
.ob-success { padding: 10px 12px; background: rgba(61, 214, 183, 0.1); border: 1px solid rgba(61, 214, 183, 0.25); border-radius: 8px; color: #3dd6b7; font-size: 13px; }
.ob-info-box { padding: 10px 12px; background: rgba(91, 141, 238, 0.1); border: 1px solid rgba(91, 141, 238, 0.25); border-radius: 8px; color: #a8c4f0; font-size: 13px; line-height: 1.5; }

/* Library picker */
.ob-lib-section { display: flex; flex-direction: column; gap: 6px; }
.ob-server-form { margin-top: 16px; padding: 14px; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; }
.ob-server-heading { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #eef2ff; margin-bottom: 4px; }
.ob-server-actions { justify-content: flex-start; margin-top: 8px; }
.ob-lib-heading { font-size: 11px; font-weight: 600; color: #a8b3cf; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px; }
.ob-lib-row {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px;
  cursor: pointer; font-size: 14px; color: #c8d0e0; transition: all 0.15s; user-select: none;
}
.ob-lib-row:hover { background: rgba(255, 255, 255, 0.04); }
.ob-lib-row.selected { border-color: rgba(61, 214, 183, 0.4); background: rgba(61, 214, 183, 0.08); color: #eef2ff; }
.ob-checkbox {
  width: 18px; height: 18px; border: 2px solid rgba(255, 255, 255, 0.2);
  border-radius: 4px; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: all 0.15s;
}
.ob-checkbox.checked { background: var(--accent, #3dd6b7); border-color: var(--accent, #3dd6b7); color: #0b0d14; }
.ob-server-icon { width: 18px; height: 18px; flex-shrink: 0; }

/* Select */
.ob-select { appearance: none; cursor: pointer; }
.ob-quality-val { font-size: 11px; font-weight: 700; color: var(--accent, #3dd6b7); margin-left: 6px; }

/* Toggle switch */
.ob-switch-row {
  display: flex; align-items: flex-start; gap: 14px; padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px;
  cursor: pointer; transition: background 0.15s; user-select: none;
}
.ob-switch-row:hover { background: rgba(255, 255, 255, 0.03); }
.ob-switch-body { flex: 1; }
.ob-switch-label { font-size: 14px; font-weight: 600; color: #dbe4ff; margin-bottom: 3px; }
.ob-switch-desc { font-size: 12px; color: #8892aa; line-height: 1.4; }
.ob-switch {
  width: 38px; height: 22px; border-radius: 11px; flex-shrink: 0;
  background: rgba(255, 255, 255, 0.12); position: relative;
  transition: background 0.2s; margin-top: 2px;
}
.ob-switch.on { background: var(--accent, #3dd6b7); }
.ob-switch-thumb {
  position: absolute; top: 3px; left: 3px;
  width: 16px; height: 16px; border-radius: 50%; background: #fff;
  transition: transform 0.2s;
}
.ob-switch.on .ob-switch-thumb { transform: translateX(16px); }

/* Indent (for conditional sub-fields) */
.ob-indent { padding-left: 4px; display: flex; flex-direction: column; gap: 4px; }

/* Segmented control */
.ob-seg { display: flex; gap: 4px; margin-top: 4px; }
.ob-seg-btn {
  flex: 1; padding: 7px 4px; font-size: 13px; font-weight: 600;
  border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 7px;
  background: rgba(255, 255, 255, 0.03); color: #8892aa;
  cursor: pointer; transition: all 0.15s;
}
.ob-seg-btn:hover { background: rgba(255, 255, 255, 0.06); color: #dbe4ff; }
.ob-seg-btn.active { background: rgba(61, 214, 183, 0.12); border-color: rgba(61, 214, 183, 0.4); color: var(--accent, #3dd6b7); }

.ob-hint-text { font-size: 12px; color: #8892aa; margin-top: 4px; }
.ob-hint-text code { font-family: monospace; background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 4px; }

/* Performance toggles */
.ob-field-group { display: flex; flex-direction: column; gap: 6px; }
.ob-field-label { font-size: 13px; font-weight: 600; color: #dbe4ff; }
.ob-field-desc { font-size: 12px; color: #8892aa; line-height: 1.4; }
.ob-toggle-group { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.ob-toggle-btn {
  display: flex; align-items: center; gap: 12px; padding: 11px 14px;
  border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px;
  background: rgba(255, 255, 255, 0.03); color: #a8b3cf;
  cursor: pointer; text-align: left; transition: all 0.15s; width: 100%;
}
.ob-toggle-btn:hover { background: rgba(255, 255, 255, 0.06); }
.ob-toggle-btn.active { border-color: rgba(61, 214, 183, 0.45); background: rgba(61, 214, 183, 0.1); color: #eef2ff; }
.ob-toggle-icon { font-size: 20px; flex-shrink: 0; }
.ob-toggle-name { font-size: 14px; font-weight: 600; margin-bottom: 2px; }
.ob-toggle-desc { font-size: 12px; opacity: 0.7; }

/* Slider */
.ob-slider-row { display: flex; align-items: center; gap: 12px; margin-top: 4px; }
.ob-slider { flex: 1; accent-color: var(--accent, #3dd6b7); }
.ob-slider-val { font-size: 15px; font-weight: 700; color: var(--accent, #3dd6b7); min-width: 20px; text-align: center; }

/* Preset card */
.ob-preset-card {
  display: flex; align-items: center; gap: 14px; padding: 14px 16px;
  border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 10px;
  background: rgba(255, 255, 255, 0.03); transition: border-color 0.2s, background 0.2s;
}
.ob-preset-card.imported { border-color: rgba(61, 214, 183, 0.4); background: rgba(61, 214, 183, 0.07); }
.ob-preset-card-icon { font-size: 28px; flex-shrink: 0; }
.ob-preset-card-body { flex: 1; min-width: 0; }
.ob-preset-card-name { font-size: 15px; font-weight: 700; color: #eef2ff; margin-bottom: 3px; }
.ob-preset-card-desc { font-size: 12px; color: #8892aa; line-height: 1.4; }
.ob-preset-card-action { flex-shrink: 0; }
.ob-btn-import {
  padding: 8px 16px; background: var(--accent, #3dd6b7); color: #0b0d14;
  border: none; border-radius: 7px; font-size: 13px; font-weight: 700;
  cursor: pointer; display: flex; align-items: center; gap: 6px; transition: opacity 0.15s;
}
.ob-btn-import:disabled { opacity: 0.5; cursor: not-allowed; }
.ob-btn-import:not(:disabled):hover { opacity: 0.85; }
.ob-imported-badge { font-size: 13px; font-weight: 600; color: var(--accent, #3dd6b7); }

/* Actions */
.ob-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  margin-top: 4px; padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.ob-btn-primary {
  padding: 9px 22px; background: var(--accent, #3dd6b7); color: #0b0d14;
  border: none; border-radius: 8px; font-size: 14px; font-weight: 700;
  cursor: pointer; display: flex; align-items: center; gap: 8px; transition: opacity 0.15s;
}
.ob-btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }
.ob-btn-primary:not(:disabled):hover { opacity: 0.88; }
.ob-btn-secondary {
  padding: 9px 18px; background: rgba(255, 255, 255, 0.07); color: #dbe4ff;
  border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px; font-size: 14px;
  font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: background 0.15s;
}
.ob-btn-secondary:disabled { opacity: 0.45; cursor: not-allowed; }
.ob-btn-secondary:not(:disabled):hover { background: rgba(255, 255, 255, 0.11); }
.ob-btn-secondary.ob-btn-active {
  background: var(--accent, #3dd6b7); color: #0b0d14; border-color: transparent;
}
.ob-btn-ghost {
  padding: 9px 14px; background: transparent; color: #8892aa;
  border: none; border-radius: 8px; font-size: 14px; cursor: pointer; transition: color 0.15s;
}
.ob-btn-ghost:hover { color: #dbe4ff; }

/* Spinner */
.ob-spinner {
  display: inline-block; width: 14px; height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.25); border-top-color: currentColor;
  border-radius: 50%; animation: ob-spin 0.8s linear infinite;
}
@keyframes ob-spin { to { transform: rotate(360deg); } }

@media (max-width: 520px) {
  .ob-modal { padding: 22px 16px 18px; }
  .ob-title { font-size: 19px; }
  .ob-seg { flex-wrap: wrap; }
  .ob-seg-btn { flex: none; width: calc(50% - 2px); }
  .ob-preset-card { flex-wrap: wrap; }
}
</style>
