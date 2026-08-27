// Curated "big picture" highlights for major version jumps — distinct from the
// granular per-version releaseNotes.ts. When a user's last-seen version is older
// than a milestone listed here, UpdateAnnouncementModal shows this curated highlight
// reel instead of dumping every intermediate version's bullet points on them (which
// is the right call for a small update gap, but overwhelming for someone crossing
// dozens of versions at once — e.g. `main` users updating past a long-running dev
// branch merge). The regular changelog is still one click away from this view.
//
// Add a new entry here for the next big jump (a major feature merge, a security
// pass, etc.) — small/routine version bumps should NOT get an entry; only genuine
// milestones worth calling out with their own moment, not every release.

export interface MajorHighlight {
  icon: string
  title: string
  description: string
}

export interface MajorRelease {
  version: string // the version this milestone lands on — crossing from before it to on/after it triggers this view
  title: string
  intro: string
  highlights: MajorHighlight[]
}

export const majorReleases: MajorRelease[] = [
  {
    version: 'v1.6.64',
    title: 'A Big One',
    intro: "You've been away for a while — this update brings a lot more than usual, so here's the highlight reel instead of a giant bullet list. The full version-by-version changelog is still one click away below.",
    highlights: [
      {
        icon: '📚',
        title: 'Plex Collections support',
        description: 'Two new poster creators for Plex Collections — a Simposter-style creator and a Kometa-style creator — with automatic franchise/collection logo lookup, dedicated save locations, and Send-to-Plex support.',
      },
      {
        icon: '🧙',
        title: 'Guided setup wizard',
        description: 'New installs now walk through Plex setup, library scanning, API key testing, and automation preferences step by step instead of starting from a blank Settings page.',
      },
      {
        icon: '🔒',
        title: 'Major security hardening',
        description: 'SSRF protection on URL-fetching endpoints, a path-traversal fix, enforced webhook secrets, real rate limiting, tighter CORS, and secrets masked out of settings/export responses.',
      },
      {
        icon: '⚡',
        title: 'Noticeably faster rendering',
        description: 'TMDb/Fanart lookups are now cached and image downloads happen in parallel — live preview and batch rendering are both meaningfully snappier, especially during active editing.',
      },
      {
        icon: '🔁',
        title: 'A retry queue that behaves',
        description: "Won't retry a deleted Plex item forever, and won't re-send a poster to Plex on retry unless it actually meets your template this time.",
      },
      {
        icon: '📺',
        title: 'More reliable TV/season editing',
        description: 'Fixed several stale-preview and preset-syncing bugs in the season editor, added a text bounding box, logo drop shadows, and independent top/bottom fade controls.',
      },
      {
        icon: '🎯',
        title: 'More accurate webhooks',
        description: 'Radarr/Sonarr/Tautulli webhooks now match the exact TMDb/TVDb ID instead of a substring — fixes a rare case where the wrong movie or show could get reprocessed.',
      },
      {
        icon: '🔔',
        title: 'Notifications & new badges',
        description: 'Apprise support for 70+ notification services, plus new studio and streaming-platform overlay badges, full-cover overlay images, and below/above-logo layering.',
      },
    ],
  },
]
