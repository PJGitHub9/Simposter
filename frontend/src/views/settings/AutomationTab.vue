<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'
import { copyToClipboard } from '@/services/clipboard'
import { useSettingsStore } from '@/stores/settings'
import { mediaServerLabel } from '@/services/mediaServerLabel'

interface Preset {
  id: string
  name: string
}

const props = defineProps<{
  webhookAutoSend: boolean
  webhookAutoLabels: string
  labelToAdd: string
  webhookAlwaysRegenerateSeason: boolean
  webhookSecret: string
  existingContentMode: 'resend' | 'regenerate'
  retryUntilTemplateMet: boolean
  retryIntervalHours: number
  retryMaxAttempts: number
  reuseCachedPosterDays: number
  unsavedChanges: boolean
  automationChanged?: boolean
}>()

const emit = defineEmits<{
  'update:webhookAutoSend': [value: boolean]
  'update:webhookAutoLabels': [value: string]
  'update:labelToAdd': [value: string]
  'update:webhookAlwaysRegenerateSeason': [value: boolean]
  'update:webhookSecret': [value: string]
  'update:existingContentMode': [value: 'resend' | 'regenerate']
  'update:retryUntilTemplateMet': [value: boolean]
  'update:retryIntervalHours': [value: number]
  'update:retryMaxAttempts': [value: number]
  'update:reuseCachedPosterDays': [value: number]
  'save': []
}>()

const localWebhookAutoSend = computed({
  get: () => props.webhookAutoSend,
  set: (val) => emit('update:webhookAutoSend', val)
})

const localWebhookAutoLabels = computed({
  get: () => props.webhookAutoLabels,
  set: (val) => emit('update:webhookAutoLabels', val)
})

const localLabelToAdd = computed({
  get: () => props.labelToAdd,
  set: (val) => emit('update:labelToAdd', val)
})

const localReuseCachedPosterDays = computed({
  get: () => props.reuseCachedPosterDays,
  set: (val) => emit('update:reuseCachedPosterDays', val)
})

const localWebhookAlwaysRegenerateSeason = computed({
  get: () => props.webhookAlwaysRegenerateSeason,
  set: (val) => emit('update:webhookAlwaysRegenerateSeason', val)
})

const localWebhookSecret = computed({
  get: () => props.webhookSecret,
  set: (val) => emit('update:webhookSecret', val)
})

const localExistingContentMode = computed({
  get: () => props.existingContentMode,
  set: (val) => emit('update:existingContentMode', val)
})

const localRetryUntilTemplateMet = computed({
  get: () => props.retryUntilTemplateMet,
  set: (val) => emit('update:retryUntilTemplateMet', val)
})

const localRetryIntervalHours = computed({
  get: () => props.retryIntervalHours,
  set: (val) => emit('update:retryIntervalHours', val)
})

const localRetryMaxAttempts = computed({
  get: () => props.retryMaxAttempts,
  set: (val) => emit('update:retryMaxAttempts', val)
})

// --- Webhook URL Generator ---
// Self-contained: fetches its own preset list, no data from other tabs needed.
const apiBase = getApiBase()
const availablePresets = ref<Record<string, any>>({})

const fetchPresets = async () => {
  try {
    const res = await fetch(`${apiBase}/api/presets`)
    if (res.ok) {
      availablePresets.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to fetch presets:', e)
  }
}

onMounted(() => {
  fetchPresets()
})

const webhookType = ref<'radarr' | 'sonarr' | 'tautulli'>('radarr')
const webhookTemplate = ref('universal')
const webhookPreset = ref('default')
const webhookIncludeSeasons = ref(true)
const webhookEventTypes = ref('added,watched')
const copiedWebhook = ref(false)

// Scopes the generated webhook to one specific Plex library, so a title that
// exists in more than one library (e.g. "Movies" + "4k Movies") resolves
// unambiguously instead of the webhook handler's own default behavior --
// search every library of the right type and use whichever has a match
// first, which can silently pick the wrong copy. '' = "Any library" (the
// backend's own pre-existing default, and what every already-configured
// webhook URL still gets since this is a purely additive query param).
const settingsStore = useSettingsStore()
const webhookLibraryId = ref('')

// Radarr scopes to a movie library, Sonarr to a TV library -- Tautulli
// handles both media types in one webhook (media_type comes from its own
// payload, not the URL), so a single library picker doesn't map cleanly
// there and isn't offered in this generator; the backend still accepts the
// same ?library_id= param for Tautulli (aliased internally to avoid a real
// local-variable name collision in that handler), just not exposed here.
//
// Under the hood this is still a raw Plex library id (that's what the
// backend actually searches on) -- but the picker now surfaces each
// library's Library Group membership (Quirk #62/#64) in its label, since
// that's what a user picking "which library" actually needs to know here:
// as of Quirk #95, the webhook's cross-server poster sync
// (_sync_poster_to_other_servers()) only reaches Jellyfin/Emby servers that
// are linked to the RESOLVED library via a Library Group -- a library with
// no group (or a single-member, Plex-only group) syncs nowhere but Plex,
// same as before Jellyfin/Emby existed. This picker doesn't need its own
// separate "group" concept in the URL because a group always anchors to
// exactly one Plex library (Quirk #62) -- selecting that library already
// unambiguously selects its group.
const webhookLibraryOptions = computed(() => {
  const mappings = webhookType.value === 'sonarr'
    ? settingsStore.plex.value.tvShowLibraryMappings
    : settingsStore.plex.value.libraryMappings
  const mediaType = webhookType.value === 'sonarr' ? 'tv' : 'movie'
  return (mappings || []).map(lib => {
    const id = String(lib.id)
    const baseLabel = lib.displayName || lib.title || id
    const group = settingsStore.libraryGroups.value.find(g =>
      g.mediaType === mediaType &&
      g.members.some(m => m.serverId === 'plex-1' && m.libraryId === id)
    )
    const otherMembers = (group?.members || []).filter(m => m.serverId !== 'plex-1')
    if (otherMembers.length === 0) {
      return { id, label: baseLabel, linked: false }
    }
    const otherNames = otherMembers.map(m => mediaServerLabel(m.serverId, settingsStore.mediaServers.value)).join(', ')
    return { id, label: `${baseLabel} (also syncs to: ${otherNames})`, linked: true }
  })
})

// Read-only summary of which Jellyfin/Emby servers a webhook of the
// currently-selected type will actually reach (Quirk #95) -- Plex has
// always been "there" in this generator via the library picker above;
// Jellyfin/Emby had no presence in this tab at all before this, even
// though Quirk #71's cross-server sync has existed since Phase 6. There's
// deliberately no separate enable/disable toggle here: a Library Group
// link (Settings -> Libraries) IS the control, exactly like the merged
// browsing grid (Quirk #65) and the manual editor's send picker
// (Quirk #75) -- adding a second, independent "sync enabled" flag on top
// of group membership would just be two ways to express the same on/off
// state and risk them drifting out of sync with each other.
const webhookCrossServerGroups = computed(() => {
  const mediaType = webhookType.value === 'sonarr' ? 'tv' : 'movie'
  return settingsStore.libraryGroups.value
    .filter(g => g.mediaType === mediaType && g.members.some(m => m.serverId !== 'plex-1'))
    .map(g => {
      const plexLib = g.members.find(m => m.serverId === 'plex-1')
      const others = g.members.filter(m => m.serverId !== 'plex-1')
      return {
        id: g.id,
        plexLabel: plexLib
          ? (webhookLibraryOptions.value.find(o => o.id === plexLib.libraryId)?.label.split(' (also syncs')[0] || plexLib.libraryId)
          : g.name,
        otherLabels: others.map(m => mediaServerLabel(m.serverId, settingsStore.mediaServers.value)),
      }
    })
})

const webhookTemplates = computed(() => {
  return Object.keys(availablePresets.value)
})

const webhookPresets = computed((): Preset[] => {
  const templateData = availablePresets.value[webhookTemplate.value]
  if (!templateData) return []
  const presets = (templateData as any).presets
  return Array.isArray(presets) ? presets : []
})

const generatedWebhookUrl = computed(() => {
  const baseUrl = window.location.origin.replace(':5173', ':8003') // Replace frontend port with API port
  // Empty (the default, "Any library") omits the param entirely -- every
  // already-configured webhook URL out there keeps working byte-for-byte
  // the same, since the backend's own default is identical to "not scoped".
  const libSuffix = webhookLibraryId.value ? `library_id=${encodeURIComponent(webhookLibraryId.value)}` : ''

  if (webhookType.value === 'radarr') {
    const base = `${baseUrl}/api/webhook/radarr/${webhookTemplate.value}/${webhookPreset.value}`
    return libSuffix ? `${base}?${libSuffix}` : base
  } else if (webhookType.value === 'sonarr') {
    const base = `${baseUrl}/api/webhook/sonarr/${webhookTemplate.value}/${webhookPreset.value}?include_seasons=${webhookIncludeSeasons.value}`
    return libSuffix ? `${base}&${libSuffix}` : base
  } else if (webhookType.value === 'tautulli') {
    return `${baseUrl}/api/webhook/tautulli?template_id=${webhookTemplate.value}&preset_id=${webhookPreset.value}&event_types=${webhookEventTypes.value}`
  }
  return ''
})

const copyWebhookUrl = async () => {
  const ok = await copyToClipboard(generatedWebhookUrl.value)
  if (!ok) return
  copiedWebhook.value = true
  setTimeout(() => {
    copiedWebhook.value = false
  }, 2000)
}

const tautulliHeaders = JSON.stringify({ "Content-Type": "application/json" }, null, 2)

const tautulliJsonData = JSON.stringify({
  event: "{action}",
  media_type: "{media_type}",
  title: "{title}",
  year: "{year}",
  rating_key: "{rating_key}",
  tmdb_id: "{tmdb_id}",
  tvdb_id: "{thetvdb_id}"
}, null, 2)

const webhookInstructions = computed(() => {
  if (webhookType.value === 'radarr') {
    return 'In Radarr: Settings → Connect → Webhook. Set URL above, triggers: "On Import" and "On Upgrade"'
  } else if (webhookType.value === 'sonarr') {
    return 'In Sonarr: Settings → Connect → Webhook. Set URL above, triggers: "On Import Complete"'
  } else if (webhookType.value === 'tautulli') {
    return 'In Tautulli: Settings → Notification Agents → Add Webhook. Trigger: "Recently Added". Use the JSON headers and data below.'
  }
  return ''
})
</script>

<template>
  <div class="tab-content">
    <h2>Automation</h2>

    <!-- Automatic Poster Generation -->
    <div class="section" :class="{ 'unsaved-changes': automationChanged }">
      <h3>Automatic Poster Generation</h3>
      <p class="section-description">
        Configure automatic poster generation and delivery via webhooks (Radarr, Sonarr, Tautulli).
        Webhooks automatically trigger poster generation when new media is added.
      </p>

      <label class="checkbox-label">
        <input type="checkbox" v-model="localWebhookAutoSend" />
        <span>Automatically Send to Plex</span>
      </label>
      <p class="help-text" style="margin: -8px 0 16px 0;">
        When enabled, webhook-generated posters are automatically sent to Plex and replace the existing poster
      </p>

      <label class="checkbox-label">
        <input type="checkbox" v-model="localWebhookAlwaysRegenerateSeason" />
        <span>Always Regenerate Season Poster</span>
      </label>
      <p class="help-text" style="margin: -8px 0 16px 0;">
        When enabled, a new season poster is generated every time a new episode webhook is received. When disabled, season posters that have already been sent to Plex are skipped.
      </p>

      <label>
        <span class="label-text">Existing Content — Poster Behaviour</span>
        <select v-model="localExistingContentMode">
          <option value="regenerate">Regenerate — always create a new poster</option>
          <option value="resend">Resend — reuse the last sent poster if available</option>
        </select>
        <span class="help-text">
          When a webhook or scheduled scan fires for a title that already has a Simposter-generated poster,
          <strong>Resend</strong> pushes the cached rendered poster straight back to Plex without regenerating.
          Useful when you have manually tuned a poster and don't want it overwritten by future Radarr/Sonarr events.
        </span>
      </label>

      <label class="checkbox-label">
        <input type="checkbox" v-model="localRetryUntilTemplateMet" />
        <span>Retry Poster Generation Until Ideal Template Is Met</span>
      </label>
      <p class="help-text" style="margin: -8px 0 16px 0;">
        When enabled, if a poster is generated but the ideal template conditions weren't met (e.g. a logo was required but none was available, or a textless poster was needed), Simposter will keep a retry queue and attempt to regenerate on the interval below. Once the ideal poster is created it stops retrying. A manual send always overrides and stops retries for that title.
      </p>

      <template v-if="localRetryUntilTemplateMet">
        <label>
          <span class="label-text">Retry Interval (hours)</span>
          <input type="number" v-model.number="localRetryIntervalHours" min="1" max="720" step="1" style="width:100px" />
          <span class="help-text">How often (in hours) to check the retry queue and attempt regeneration.</span>
        </label>

        <label>
          <span class="label-text">Max Retry Attempts (0 = unlimited)</span>
          <input type="number" v-model.number="localRetryMaxAttempts" min="0" max="9999" step="1" style="width:100px" />
          <span class="help-text">Stop retrying after this many attempts. Set to 0 to retry indefinitely.</span>
        </label>
      </template>

      <label>
        <span class="label-text">Reuse Cached Poster For (days, 0 = disabled)</span>
        <input type="number" v-model.number="localReuseCachedPosterDays" min="0" max="365" step="1" style="width:100px" />
        <span class="help-text">
          If a webhook or scheduled scan discovers what looks like a brand-new item, but a poster was already sent for the same TMDb title within this many days, Simposter resends that cached poster instead of generating a fresh one. Protects against a tool like Radarr/Sonarr (or something re-grabbing a trailer file) causing Plex to re-match an item under a new internal ID — which otherwise looks identical to a genuinely new library addition, and would silently overwrite a poster you already tuned. Only applies to webhook/auto-generate — manual batch, save, and send always render fresh.
        </span>
      </label>

      <!-- The global "Labels to Remove After Sending" field (webhookAutoLabels) was removed
           from this UI — it duplicated Settings → Libraries' per-library "Default Labels to
           Remove", which is the actually-used mechanism (and more precise, since it's scoped
           per library). The underlying webhookAutoLabels setting/merge logic is untouched
           server-side for any install that already has a value stored there; it's just no
           longer editable from this tab. -->

      <label>
        <span class="label-text">Label to Add After Sending</span>
        <input
          type="text"
          v-model="localLabelToAdd"
          placeholder="e.g. Simposter"
        />
        <span class="help-text">Optional — tags an item with this label after Simposter successfully sends a poster to Plex, so you can see (or filter/smart-collection on) which items got a Simposter-generated poster. Leave blank to disable. Applies to every send path: manual, batch, webhook, auto-generate, and resend.</span>
      </label>

      <label>
        <span class="label-text">Webhook Secret (optional)</span>
        <input
          type="password"
          v-model="localWebhookSecret"
          placeholder="Leave blank to accept any request (default)"
          autocomplete="new-password"
        />
        <span class="help-text">
          When set, webhook requests must include this value or they're rejected. Without it, anyone who can
          reach this server's webhook URLs can trigger poster generation. Radarr/Sonarr/Tautulli don't have a
          custom-header field for webhooks, so add it directly to the webhook URL you already configured in
          each app: append <code>?secret=your-secret</code>, or <code>&amp;secret=your-secret</code> if the URL
          already has a <code>?</code> in it (e.g. Sonarr's <code>?include_seasons=true</code>).
          A <code>X-Webhook-Secret</code> header also works if you're calling the webhook from something that
          supports custom headers.
        </span>
      </label>
    </div>

    <!-- Webhook URL Generator -->
    <div class="section">
      <h3>Webhook URL Generator</h3>
      <p class="section-description">
        Generate webhook URLs for Radarr, Sonarr, and Tautulli integration
      </p>

      <div class="webhook-generator">
        <div class="webhook-config-grid">
          <label>
            <span class="label-text">Webhook Type</span>
            <select v-model="webhookType">
              <option value="radarr">Radarr (Movies)</option>
              <option value="sonarr">Sonarr (TV Shows)</option>
              <option value="tautulli">Tautulli (Plex)</option>
            </select>
          </label>

          <label>
            <span class="label-text">Template</span>
            <select v-model="webhookTemplate">
              <option v-for="template in webhookTemplates" :key="template" :value="template">
                {{ template }}
              </option>
            </select>
          </label>

          <label>
            <span class="label-text">Preset</span>
            <select v-model="webhookPreset">
              <option v-for="preset in webhookPresets" :key="preset.id" :value="preset.id">
                {{ preset.name }}
              </option>
            </select>
          </label>

          <!-- Only for Radarr/Sonarr -- Tautulli handles both movie and TV
               events in one webhook (its own payload says which), so a
               single library picker here wouldn't map cleanly to it; the
               backend still accepts the same ?library_id= param for
               Tautulli, just not exposed as a picker in this generator. -->
          <label v-if="webhookType === 'radarr' || webhookType === 'sonarr'">
            <span class="label-text">Library (optional)</span>
            <select v-model="webhookLibraryId">
              <option value="">Any library (default)</option>
              <option v-for="lib in webhookLibraryOptions" :key="lib.id" :value="lib.id">{{ lib.label }}</option>
            </select>
            <span class="help-text">
              Scopes the lookup to one library, for when the same title could exist in more than one
              (e.g. "Movies" + "4k Movies"). Leave as "Any library" unless you actually have that overlap.
              A library shown with "also syncs to: ..." is linked to a Jellyfin/Emby server via a
              Library Group (Settings &rarr; Libraries) -- picking it means the poster this webhook
              generates also gets pushed to those linked server(s), not just Plex. An unlinked library,
              or "Any library", only ever reaches Plex.
            </span>
          </label>

          <!-- Jellyfin/Emby visibility (Quirk #95) -- Radarr/Sonarr only,
               matching the library picker above's own scope. No control to
               toggle here on purpose (see webhookCrossServerGroups' own
               comment) -- this is confirmation, and a pointer to where the
               real control (Library Groups) actually lives. -->
          <div v-if="(webhookType === 'radarr' || webhookType === 'sonarr')" class="webhook-cross-server-note">
            <template v-if="webhookCrossServerGroups.length > 0">
              <strong>Also reaches Jellyfin/Emby:</strong>
              <span v-for="(g, i) in webhookCrossServerGroups" :key="g.id">
                {{ g.plexLabel }} &rarr; {{ g.otherLabels.join(', ') }}<span v-if="i < webhookCrossServerGroups.length - 1">; </span>
              </span>
            </template>
            <template v-else>
              No libraries linked to a Jellyfin/Emby server yet -- this webhook will only ever reach Plex.
              Link one in Settings &rarr; Libraries to also sync generated posters there.
            </template>
          </div>

          <!-- Sonarr-specific option -->
          <label v-if="webhookType === 'sonarr'" class="checkbox-label">
            <input type="checkbox" v-model="webhookIncludeSeasons" />
            <span>Generate season posters (not just series)</span>
          </label>

          <!-- Tautulli-specific option -->
          <label v-if="webhookType === 'tautulli'">
            <span class="label-text">Event Types</span>
            <input
              v-model="webhookEventTypes"
              type="text"
              placeholder="added,watched,updated"
            />
            <span class="help-text">Comma-separated: added, watched, updated</span>
          </label>
        </div>

        <div class="webhook-url-output">
          <label>
            <span class="label-text">Generated Webhook URL</span>
            <div class="url-with-copy">
              <input
                :value="generatedWebhookUrl"
                readonly
                class="webhook-url-input"
              />
              <button @click="copyWebhookUrl" class="copy-btn" type="button">
                {{ copiedWebhook ? '✓ Copied!' : 'Copy' }}
              </button>
            </div>
          </label>

          <div class="webhook-instructions">
            <strong>Setup Instructions:</strong>
            <p>{{ webhookInstructions }}</p>
          </div>

          <!-- Tautulli JSON config -->
          <div v-if="webhookType === 'tautulli'" class="tautulli-config">
            <div class="config-block">
              <span class="config-label">Trigger</span>
              <div class="config-value">Recently Added</div>
            </div>
            <div class="config-block">
              <span class="config-label">JSON Headers</span>
              <pre class="config-code">{{ tautulliHeaders }}</pre>
            </div>
            <div class="config-block">
              <span class="config-label">JSON Data</span>
              <pre class="config-code">{{ tautulliJsonData }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="actions">
      <button @click="emit('save')" class="primary" :disabled="!unsavedChanges">
        {{ unsavedChanges ? 'Save Changes' : 'No Changes' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.tab-content {
  padding: 20px;
  max-width: 1600px;
}

h2 {
  margin-top: 0;
  margin-bottom: 24px;
  color: var(--text-primary);
  font-size: 24px;
}

h3 {
  margin-top: 0;
  margin-bottom: 16px;
  color: var(--text-secondary);
  font-size: 18px;
}

.section {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.section.unsaved-changes {
  background: rgba(255, 200, 0, 0.08);
  border-color: rgba(255, 200, 0, 0.4);
}

.section-description {
  color: var(--text-muted);
  font-size: 13px;
  margin: -8px 0 16px 0;
  line-height: 1.5;
}

label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.label-text {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 14px;
}

.help-text {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: -4px;
}

.help-text code {
  background: rgba(255, 255, 255, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 11px;
  color: var(--accent);
}

.checkbox-label {
  flex-direction: row;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  width: auto;
  cursor: pointer;
}

.checkbox-label span {
  font-weight: 500;
  color: var(--text-primary);
}

select,
input[type="text"],
input[type="password"],
input[type="number"] {
  width: 100%;
  max-width: 400px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
}

select:focus,
input:focus {
  outline: none;
  border-color: var(--accent);
  background: rgba(255, 255, 255, 0.06);
}

.webhook-generator {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.webhook-config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.webhook-cross-server-note {
  grid-column: 1 / -1;
  font-size: 12px;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  line-height: 1.5;
}

.webhook-cross-server-note strong {
  color: var(--text-secondary);
  font-weight: 600;
  margin-right: 6px;
}

.webhook-url-output {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.url-with-copy {
  display: flex;
  gap: 8px;
  align-items: center;
}

.webhook-url-input {
  flex: 1;
  max-width: none;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.02);
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-primary);
}

.copy-btn {
  white-space: nowrap;
  padding: 10px 16px;
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.copy-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.webhook-instructions {
  padding: 12px;
  background: rgba(255, 193, 7, 0.1);
  border: 1px solid rgba(255, 193, 7, 0.3);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.webhook-instructions strong {
  color: var(--text-primary);
  display: block;
  margin-bottom: 6px;
}

.webhook-instructions p {
  margin: 0;
  line-height: 1.5;
}

.tautulli-config {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.config-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-2);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.config-value {
  font-size: 13px;
  color: var(--text-primary);
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.config-code {
  margin: 0;
  padding: 10px 12px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  font-family: monospace;
  color: #c9d1e3;
  white-space: pre;
  overflow-x: auto;
  line-height: 1.5;
}

.actions {
  display: flex;
  gap: 12px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
}

button {
  padding: 10px 20px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

button:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.08);
  border-color: var(--accent);
}

button.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

button.primary:hover:not(:disabled) {
  opacity: 0.9;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
