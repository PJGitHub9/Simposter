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
    version: 'v1.5.72',
    date: '2026-03-18',
    sections: [
      {
        title: 'New Features',
        items: [
          'Apprise notifications — send poster generation events to 70+ services (Slack, Telegram, Pushover, Gotify, ntfy, email, and more) via Apprise URL schemes. Configurable per-library and per-event-type, with a test button. Discord and Apprise fire independently.',
        ]
      },
      {
        title: 'Bug Fix',
        items: [
          'Text shadow no longer defaults to enabled when turning on the custom text overlay.',
          'Webhook notifications are no longer sent for TV episodes that don\'t result in a new poster being created (e.g. Sonarr episode webhooks for shows that already have a season poster).',
        ]
      }
    ]
  },
  {
    version: 'v1.5.71',
    date: '2026-03-14',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Fixed manual editor (Template Manager preview) applying fallback logic when it shouldn\'t — if no logo was found for the selected movie the preset would silently switch to the configured fallback template/preset (e.g. a "text" preset), making it appear the selected preset was broken. The editor now always renders the selected preset as-is regardless of fallback configuration.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.7',
    date: '2026-03-13',
    sections: [
      {
        title: 'New Features',
        items: [
          'Simposter Asset badge mode — pulls logos directly from the simposter-assets GitHub repo (logos.json refreshed hourly)',
          'TMDb company ID matching — studio badges now resolve assets by stable numeric ID instead of name, eliminating mismatches from name variations (e.g. "CJ ENM" vs "CJ ENM Studios")',
          'Slug alias system — map any unexpected TMDb slug to the correct asset slug per-element for edge cases',
          'Unmaintained branch warning — logo turns amber/red with a pulsing warning badge when running a Docker tag that is not "latest" or "webui-overhaul-dev"',
          'Docker tag exposed in /api/version-info — baked into build-info.json at build time via --build-arg DOCKER_TAG, overridable at runtime via DOCKER_TAG env var',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Studio company ID now cached alongside studio name — asset lookup by TMDb ID works immediately on subsequent renders',
          'Stale studio cache entries (pre-dating company ID tracking) are automatically re-fetched from TMDb on next render',
          'Thread-safe asset cache with double-checked locking prevents race conditions during server startup prewarm',
        ]
      }
    ]
  },
  {
    version: 'v1.5.68',
    date: '2026-03-11',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Fixed black background appearing on URL-mode badge images with anti-aliased edges (e.g. Apple TV+ logo) — caused by PIL using a linear alpha-blend that corrupted the canvas alpha channel before JPEG conversion',
        ]
      }
    ]
  },
  {
    version: 'v1.5.67',
    date: '2026-03-10',
    sections: [
      {
        title: 'URL Mode for Badge Images',
        items: [
          'New badge rendering mode: URL — paste any direct image URL and Simposter fetches and caches it automatically (7-day disk cache)',
          'Available for all badge types: video, audio, edition, streaming platform, and studio',
          'Streaming Platform badges in URL mode automatically use the official TMDb provider logo when no URL is set — zero configuration required',
          'URL images support the same scale and anchor position overrides as uploaded assets',
          'Canvas preview attempts to load the URL image directly; falls back to a "URL" indicator if CORS-blocked',
        ]
      }
    ]
  },
  {
    version: 'v1.5.66',
    date: '2026-03-10',
    sections: [
      {
        title: 'Studio Badge',
        items: [
          'New overlay element type: Studio Badge — auto-detects the production studio (movies) or TV network from TMDb and renders the appropriate badge',
          'Covers 29 studios and networks including A24, Netflix, Marvel Studios, Warner Bros., Universal, HBO, FX, AMC, and more',
          'Unlike the streaming platform badge, studio data is permanent (who made it, not where to watch it) and is not region-dependent',
          'Results are cached alongside streaming provider data — no extra API calls in most cases',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Fixed streaming platform badge not rendering — metadata field was stored as null by Pydantic, causing the backend to look up field "None" instead of "streaming_platform"',
        ]
      }
    ]
  },
  {
    version: 'v1.5.65',
    date: '2026-03-09',
    sections: [
      {
        title: 'Streaming Platform Badge',
        items: [
          'New overlay element type: Streaming Platform Badge — auto-detects a title\'s streaming platform (Netflix, Disney+, Hulu, Max, etc.) via TMDb Watch Providers and renders the appropriate badge',
          'Configure text, image, or none per platform — same flexible per-value badge system used by video, audio, and edition badges',
          'Supports 12 streaming platforms: Netflix, Prime Video, Disney+, Max, Hulu, Apple TV+, Paramount+, Peacock, Tubi, Crunchyroll, Shudder, MUBI',
          'Region selector per overlay config (US, UK, CA, AU, DE, FR, ES, IT, JP, KR, BR, MX) — watch provider availability varies by region',
          'Provider data is cached in the database for 7 days, minimising TMDb API calls',
          'Platform is resolved lazily at render time — no extra work unless a streaming badge element is present in the overlay config',
        ]
      }
    ]
  },
  {
    version: 'v1.5.64',
    date: '2026-03-09',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed auto-generate on scan silently skipping new movies and TV shows — library ID type mismatch (int vs string) caused the settings lookup to always fail, so autoGenerateEnabled was never read',
          'Auto-generate now correctly triggers for any new content detected during a library scan when enabled in Settings → Plex Libraries',
        ]
      }
    ]
  },
  {
    version: 'v1.5.63',
    date: '2026-03-08',
    sections: [
      {
        title: 'Auto-Generate: Recently Added Detection',
        items: [
          'Added check_recently_added() — efficiently polls Plex for items added in the last 20 minutes instead of scanning the full library',
          'New content from any source (downloaders, import tools, manual adds) is detected and auto-processed without requiring a Radarr/Sonarr webhook',
          'New items are cached immediately so subsequent scans never double-process the same item',
          'Works with the existing "Auto-generate on scan" setting per library — enable it in Settings → Plex Libraries to activate',
        ]
      }
    ]
  },
  {
    version: 'v1.5.62',
    date: '2026-03-06',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed poster background thumbnail click not updating the preview in the manual movie editor — backend was ignoring the selected poster URL and auto-picking from TMDB instead',
          'Logo thumbnail clicks were already working correctly; this only affected poster selection',
          'Sending to Plex was unaffected — only the live preview was showing the wrong poster',
        ]
      }
    ]
  },
  {
    version: 'v1.5.61',
    date: '2026-03-05',
    sections: [
      {
        title: 'TV Show Batch Edit',
        items: [
          'Added "Include Series Poster" checkbox — independently control whether the series-level poster is generated during a batch run',
          'Series Poster and Include Seasons can now be toggled independently: generate series only, seasons only, or both',
          '"Include Series Poster" defaults to checked; "Include Seasons" defaults to unchecked (matching previous behavior)',
          'Preview correctly shows the first season when "Include Series Poster" is unchecked — no longer defaults to series poster',
        ]
      },
      {
        title: 'Code Cleanup',
        items: [
          'Removed dead template selector block (v-if="false") from both Batch Edit views',
          'Removed unused defineProps/defineEmits from TV Batch Edit',
          'Fixed log prefix in TV Batch Edit — was incorrectly logging as [BatchEdit]',
        ]
      }
    ]
  },
  {
    version: 'v1.5.53',
    date: '2026-03-04',
    sections: [
      {
        title: 'Code Cleanup',
        items: [
          'Removed duplicate _add_grain_fast function — was identical to _add_grain',
          'Extracted shared _apply_canvas_size_constraints helper — custom_image resize logic no longer duplicated',
          'Text label overlay now uses full font search (_load_font) — respects config/fonts, bundled fonts, and system fonts instead of falling back to default immediately',
          'Updated OverlayElement schema comment to clearly distinguish active types from legacy aliases',
        ]
      }
    ]
  },
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
