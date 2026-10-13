import { ref } from 'vue'

// Tiny cross-component trigger so a deeply-nested routed view (Settings → Advanced tab)
// can reopen the onboarding wizard, which App.vue owns and mounts outside <router-view>
// (see App.vue's `showOnboarding` ref). A counter rather than a boolean so repeated
// requests (re-opening the wizard more than once in a session) always register as a
// change App.vue's watcher can react to, even if it was left open/closed in between.
export const onboardingLaunchRequested = ref(0)

export function launchOnboarding() {
  onboardingLaunchRequested.value++
}

// Reverse direction of the above: the wizard (OnboardingModal.vue) saves
// directly to the shared Pinia settings store (plex/automation/libraryGroups/
// mediaServers, etc. -- see its markOnboardingDone()), bypassing
// SettingsView.vue's own local staging refs and "last saved" snapshot
// entirely. If SettingsView.vue was already mounted when the wizard ran (the
// "Run Startup Wizard" re-run case, Settings -> Advanced), it never finds out
// the store just changed out from under it -- its own watchers correctly
// detect a diff against its now-stale snapshot and flag the page as having
// unsaved changes, even though everything was already saved by the wizard.
// A real, reported bug: finishing the wizard/QuickStartGuide would then
// immediately hit SettingsView.vue's "You have unsaved changes, are you sure
// you want to leave?" confirm the moment the user tried to navigate anywhere.
// A counter (not a boolean) for the same reason onboardingLaunchRequested
// above is one -- repeated wizard runs in one session must each register as
// a change, even if SettingsView.vue already reacted to an earlier one.
export const onboardingJustSaved = ref(0)

export function notifyOnboardingSaved() {
  onboardingJustSaved.value++
}
