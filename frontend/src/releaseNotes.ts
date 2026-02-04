export interface ReleaseNote {
  version: string
  date: string
  sections: {
    title: string
    items: string[]
  }[]
}

// Update this array with each release. Oldest entries can be removed over time.
export const releaseNotes: ReleaseNote[] = [
  {
    version: 'v1.4.98',
    date: '2026-02-04',
    sections: [
      {
        title: 'New Features',
        items: [
          'Update announcement popup on new version',
          'Skip existing season poster on webhook (configurable toggle in Settings)',
          'Discord webhook notifications now include poster image',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Fixed missing library name in history for Tautulli webhooks',
          'Fixed private network URL validation for local Plex servers',
        ]
      }
    ]
  }
]
