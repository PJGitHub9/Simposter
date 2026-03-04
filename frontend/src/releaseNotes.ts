export interface ReleaseNote {
  version: string
  date: string
  sections: {
    title: string
    items: string[]
  }[]
}

// Update this array with each release. Keep the last ~5 versions for users who skip updates.
export const releaseNotes: ReleaseNote[] = [
  {
    version: 'v1.5.52',
    date: '2026-03-04',
    sections: [
      {
        title: 'Overlay System Improvements',
        items: [
          'Uploaded assets now saved using the asset name as the filename (e.g. "4K Badge" → 4k-badge.png) — easier to manage manually',
          'Added Rescan button to Assets Library — detects and registers image files dropped directly into config/assets/ folder',
          'Added per-value Scale and Anchor controls for image-mode badges — scale and position each badge image independently without affecting text values',
          'Anchor point control for image overlays — choose from 9 anchor positions (top-left, center, bottom-right, etc.) so images align consistently with text badges',
          'Removed Width/Height (0-1) and Max Width/Height (px) from badge types — Scale replaces these with a simpler multiplier-based approach',
          'Width, Height, Max Width, Max Height retained on Custom Image elements where precise sizing is still useful',
          'Badge element UI simplified — position, metadata field, and per-value rendering rows only',
        ]
      }
    ]
  },
  {
    version: 'v1.5.51',
    date: '2026-03-01',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed version API crash in Docker containers — subprocess exception handling corrected',
          'Fixed branch detection in containerized environments — reads build-time branch info from build-info.json',
        ]
      }
    ]
  },
  {
    version: 'v1.5.5',
    date: '2026-03-01',
    sections: [
      {
        title: 'UI Improvements',
        items: [
          'Added emoji icons to all page headings and navigation items (🎬 Movies, 📺 TV Shows, ✏️ Batch Edit, 🎨 Template Manager, 📐 Overlay Manager, and more)',
          'Removed duplicate SVG + emoji icons from sidebar — was rendering both icon types together',
          'Version badge now shows git branch — displays "v1.5.5-dev" for dev branches, "v1.5.5" for main',
          'Update available indicator — pulsing yellow badge when newer version exists on your branch',
        ]
      },
      {
        title: 'Overlay System Enhancements',
        items: [
          'Reorganized element types for clarity — Video Badge (resolution, codec), Audio Badge (codec, channels, language), Edition Badge (theatrical, extended, etc.)',
          'Metadata field dropdowns now restricted to relevant fields per badge type',
          'Case-insensitive label matching — show_if_label and hide_if_label now ignore case',
          'Legacy support — resolution_badge and codec_badge still work as aliases',
          'Consolidated rendering — backend uses unified _apply_metadata_badge function for all badge types',
          'Canvas preview uses color-coded badges — blue for video, purple for audio, amber for edition',
        ]
      }
    ]
  },
  {
    version: 'v1.5.4',
    date: '2026-02-27',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed fallback preset settings being reset to blank after v1.5.3 template consolidation — fallback template references now automatically migrate',
          'Fixed overlay badges not rendering — metadata injection, rating key passthrough, and value format mismatches resolved across all render paths',
        ]
      },
      {
        title: 'New Features',
        items: [
          'Overlay Config Manager — create reusable overlay templates with resolution badges, codec badges, custom images, text labels, and label badges (early testing)',
          'Overlay asset library — upload and manage badge images (4K, Atmos, etc.) to use in overlay configs',
          'Badge per-value mode selector — choose None, Text (with custom display text), or Image for each resolution/codec value',
          'Dynamic Plex media metadata — overlay badges use real resolution, codec, and channel info from your Plex library (cached for performance)',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Increased logo bounding box max height (thanks chadwpalm)',
          'Detailed overlay rendering logs for easier debugging',
        ]
      }
    ]
  },
  {
    version: 'v1.5.3',
    date: '2026-02-13',
    sections: [
      {
        title: 'Improvements',
        items: [
          'Template consolidation — merged "Default" template into "Uniform Logo" for simplified template selection',
          'Automatic migration — existing presets and history automatically converted to Uniform Logo template on startup',
          'Logo positioning unified — all logo placement now uses consistent bounding box zones instead of scale/offset',
        ]
      }
    ]
  },
  {
    version: 'v1.5.23',
    date: '2026-02-23',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed Sonarr webhook not generating series poster for newly added TV shows — now creates both series and season posters for new shows',
        ]
      }
    ]
  },
  {
    version: 'v1.5.22',
    date: '2026-02-23',
    sections: [
      {
        title: 'New Features',
        items: [
          'Backup & Restore — save original Plex posters before making changes and restore them later with smart auto-matching',
          'Manual assignment for unmatched backup files — click any backup file to assign it to any Plex library item',
          'TV show season poster backup & restore support — optionally include season posters in backups',
          'Human-readable backup filenames — posters saved as "Title (Year).jpg" or "Show Name (Year) - Season 01.jpg"',
        ]
      }
    ]
  },
  {
    version: 'v1.5.21',
    date: '2026-02-09',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed image output format setting not being respected — posters now save in the correct format (JPG/PNG/WebP) as configured in Settings',
          'Fixed compression/quality slider not affecting output file size — JPEG quality, PNG compression, and WebP quality now apply correctly across all save paths',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Batch progress overlay now floats at top-right and persists across page navigation with real-time backend status',
        ]
      }
    ]
  },
  {
    version: 'v1.5.2',
    date: '2026-02-09',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed TV show batch edit using movie TMDB endpoints — TV show IDs were being looked up as movies, returning wrong (potentially NSFW) posters (sorry chadwpalm)',
          'Fixed TVDB ID extraction regex never matching — TV shows now correctly resolve TVDB IDs for supplementary images',
          'Fixed TV show season preview not updating when switching seasons in the editor',
        ]
      }
    ]
  },
  {
    version: 'v1.5.11',
    date: '2026-02-06',
    sections: [
      {
        title: 'New Features',
        items: [
          'Click version badge to view full changelog (last 10 releases)',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Fixed scan progress overlay blocking UI on mobile — now displays at bottom of screen',
          'Fixed History view "View" button not working on mobile — now uses tap-to-preview',
        ]
      }
    ]
  },
  {
    version: 'v1.5.1',
    date: '2026-02-06',
    sections: [
      {
        title: 'Improvements',
        items: [
          'Mobile responsive UI overhaul — improved usability on phones and tablets',
          'Mobile responsive History view — horizontal scrolling table, stacked filters on small screens',
          'Mobile responsive Editor panes — stacked layout for movie and TV show poster editing',
          'Mobile responsive grid layouts — adaptive card sizing across all views',
        ]
      }
    ]
  },
  {
    version: 'v1.5.02',
    date: '2026-02-06',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed webhook/auto-generate fallback logic not reading preset settings correctly (poster_filter, logo_preference, etc.)',
        ]
      }
    ]
  },
  {
    version: 'v1.5.01',
    date: '2026-02-05',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed scheduled scans not scanning in new posters',
        ]
      }
    ]
  },
  {
    version: 'v1.5',
    date: '2026-02-04',
    sections: [
      {
        title: 'New Features',
        items: [
          'Discord notifications — webhook URL, per-source toggles, poster image attachments, batch progress updates',
          'Radarr, Sonarr, and Tautulli webhook integration for automatic poster generation',
          'Webhook ignore labels — skip poster generation for specific items via Plex labels',
          'Skip existing season posters on webhook — avoids regenerating already-sent season posters (configurable in Settings > Performance)',
          'Update announcement popup — see what changed after each update',
          'Settings page reorganized into tabbed layout (General, Libraries, Save Locations, Performance, Notifications, Advanced)',
          'Auto-generate posters on library scan with per-library template/preset configuration',
          'History view now shows fallback reasoning (poster and logo fallback indicators)',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Fixed missing library name in history for Tautulli webhooks (movies and TV shows)',
          'Fixed private network URL validation blocking local Plex servers in template manager',
          'Fixed Tautulli webhook ignore labels not being checked for movies',
          'Fixed text overlay not being sent to Plex in some cases',
          'Fixed auto scan scheduler not running after app restart',
          'Fixed force poster refresh not updating cache properly',
          'Fixed Sonarr webhook season detection and duplicate handling',
          'Fixed TV batch edit season sending issues',
          'Fixed TMDB API key masking in settings',
          'Fixed history view pagination and filtering',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Webhook cooldown system prevents duplicate poster generation (5-minute window)',
          'Webhook retry logic with delay for newly added Plex items',
          'Batch fallback logic improved — poster and logo fallbacks now work correctly in all scenarios',
          'API key visibility masking in settings for security',
        ]
      }
    ]
  },
  {
    version: 'v1.4.9',
    date: '2026-01-07',
    sections: [
      {
        title: 'New Features',
        items: [
          'Separate save locations for Movies and TV Shows with variable support ({library}, {title}, {year}, {season})',
          'Browser back/forward navigation support with URL state management',
          'Conditional navigation — sidebar adapts when Plex is not yet configured',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Fixed TV show save-to-disk not using correct media type and season paths',
          'Fixed library cache contamination — movies from one library no longer appear in another',
          'Fixed library parameter lost from URL when applying filters/sorting',
          'Fixed save location change detection not triggering unsaved indicator',
        ]
      }
    ]
  },
  {
    version: 'v1.4.8',
    date: '2026-01-06',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed library switching cache contamination in multi-library setups',
          'Fixed settings labels not populating with loading state and refresh button',
          'Template manager fallback wording improved with visual fallback chain',
        ]
      }
    ]
  },
  {
    version: 'v1.4.7',
    date: '2026-01-06',
    sections: [
      {
        title: 'New Features',
        items: [
          'TV show seasons support with season-specific poster generation',
          'Scheduled library scans via cron (configurable in Settings)',
          'Smart SessionStorage caching with LRU eviction',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Database indexing — 5-10x faster queries with 6 new indexes',
          'Debounced editor saves — smoother slider adjustments',
          'Memory leak fixes for intervals and timers',
          'Enhanced rate limiting for scheduler endpoints',
        ]
      }
    ]
  },
  {
    version: 'v1.4.6',
    date: '2026-01-05',
    sections: [
      {
        title: 'New Features',
        items: [
          'Overlay caching for 3-5x faster batch rendering',
          'Logo selection optimization — concurrent analysis with thumbnails',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Batch edit fallback logic matches preview behavior',
          'Settings labels UI consolidated with type badges',
        ]
      }
    ]
  }
]
