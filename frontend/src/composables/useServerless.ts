import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'

/**
 * Server-less mode: onboarding is done and no media server (Plex, Jellyfin or Emby)
 * is configured. The app then shows a reduced nav, lands on the Poster API page and
 * skips every library/scan/media-server request.
 */
export function useServerless() {
  const settings = useSettingsStore()

  const anyServerConfigured = computed(
    () => settings.plexActive.value || settings.mediaServers.value.some(s => s.enabled && s.type !== 'plex')
  )

  const serverless = computed(() => settings.onboardingCompleted.value && !anyServerConfigured.value)

  return { anyServerConfigured, serverless }
}
