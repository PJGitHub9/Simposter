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
