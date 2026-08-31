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
    version: 'v1.6.80',
    date: '2026-08-31',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed "Test Connection" (Settings and the setup wizard) failing with a Plex URL that has a trailing slash — it built a double-slash path that Plex rejects. The URL is also cleaned up automatically when saved, so this can\'t linger even if it was already saved with a trailing slash.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.79',
    date: '2026-08-31',
    sections: [
      {
        title: 'Improvements',
        items: [
          'Docs: Getting Started now covers pulling the pre-built Docker image from GHCR, not just building from source — the old docs incorrectly said no registry image existed.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.78',
    date: '2026-08-31',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          '"Label to Add After Sending" now actually applies the label. The previous fix only added better detection that it wasn\'t working — this release fixes the actual cause: Plex doesn\'t support the "append one label" API call this used, so it now fetches an item\'s existing labels and writes the full set back (existing + new) the way Plex\'s API actually expects.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.77',
    date: '2026-08-31',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'The new "Label to Add After Sending" feature could report success without the label actually landing on the Plex item — it now verifies the label actually stuck (re-checking the item) before considering it done, and tries every fallback method until one genuinely works.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Removed the redundant "Labels to Remove After Sending" field from Settings → Automation — Settings → Libraries\' per-library "Default Labels to Remove" is the one that actually matters and was already covering this.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.76',
    date: '2026-08-31',
    sections: [
      {
        title: 'New Features',
        items: [
          'Added "Kometa Compatibility" (Settings → Libraries) — when enabled, any library you add from now on automatically gets "Overlay" checked in Default Labels to Remove, matching what the startup wizard\'s "Using Kometa?" step already does for libraries selected during onboarding.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Refreshed the "budget-daps" starter preset\'s look (repositioned/resized logo box, lower vignette).',
        ]
      }
    ]
  },
  {
    version: 'v1.6.75',
    date: '2026-08-31',
    sections: [
      {
        title: 'New Features',
        items: [
          'Added a new "textless-border" starter preset and refreshed "budget-daps" with an updated look — now 4 Uniform Logo presets + 2 Kometa presets ship as starter presets (onboarding and Template Manager\'s "Import Simposter defaults").',
        ]
      }
    ]
  },
  {
    version: 'v1.6.74',
    date: '2026-08-31',
    sections: [
      {
        title: 'New Features',
        items: [
          'Simposter can now actually tag Plex items with a label after sending a poster (Settings → Automation → "Label to Add After Sending"). Works across every send path — manual, batch, webhook, auto-generate, and resend.',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the onboarding wizard\'s "Apply a label after sending a poster?" toggle silently doing nothing — it was wired to the (unrelated) label-removal setting instead of actually adding a label.',
          'Relabeled Settings → Automation\'s "Default Labels for Webhook Posters" to "Labels to Remove After Sending" and clarified its description — it strips labels, it never added them, despite the old name suggesting otherwise.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.73',
    date: '2026-08-31',
    sections: [
      {
        title: 'New Features',
        items: [
          'Added a "Run Startup Wizard" button to Settings → Advanced, so the first-time setup wizard can be re-run any time (e.g. if it was skipped) instead of only appearing on first launch.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.72',
    date: '2026-08-31',
    sections: [
      {
        title: 'New Features',
        items: [
          'Added an "Import Simposter defaults" button to Template Manager\'s Import/Export section — pulls in the same 5 starter presets onboarding offers, any time, not just on first run.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.71',
    date: '2026-08-31',
    sections: [
      {
        title: 'New Features',
        items: [
          'Onboarding now imports a full set of 5 starter presets (3 Uniform Logo looks + 2 Kometa collection presets) instead of just one.',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          '"Copy Compact" (Template Manager) and the webhook URL copy button in Settings → Automation no longer fail with "navigator.clipboard is undefined" when the app is reached over plain HTTP.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.70',
    date: '2026-08-28',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed "Save As" in the TV editor always failing with "Cannot save season options as new preset" when creating a new preset while viewing a season poster.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.69',
    date: '2026-08-28',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the TV editor\'s "Save to Disk" sometimes saving a poster with a logo even when Logo Mode was set to "No Logo", and sometimes not applying a season\'s own text color or other custom settings.',
          'Fixed editing one show or season\'s settings occasionally bleeding into a different season\'s or the series\' saved poster.',
          'Fixed the "Rendered Posters" thumbnail strip not updating after a settings change until you clicked into that season.',
          'Fixed adding or removing a Plex library in Settings silently not saving — picking a library from the dropdown could look like it worked but never actually persisted.',
          'Fixed the "Flat" TV save layout creating a subfolder per show instead of truly flat files, and season posters sometimes saving with the season\'s own label (e.g. "Season 1") instead of the show\'s name.',
        ]
      },
      {
        title: 'New Features',
        items: [
          'Removing a library in Settings now works properly, with a confirmation and full cleanup of its cached posters/labels once you save.',
          'Adding a new library now automatically scans it as soon as you save, instead of leaving it empty until the next scheduled scan.',
          'Settings sections now only show "unsaved changes" for the specific section you actually changed.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.68',
    date: '2026-08-27',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed logo thumbnails sometimes showing up as a blank tile in the logo picker — a resized preview image occasionally failed to load even though the logo itself was fine; it now automatically falls back to the full-size image.',
          'Fixed logo tiles in the Logos tab sometimes showing up blank after a batch or webhook send — the cached logo was pointing at an external image link instead of a local copy, so it depended on that external source staying available.',
          'Fixed the "Current Logo" preview at the top of the logo editor popup showing a broken image icon instead of a clean "No logo cached yet" message when its logo failed to load.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.67',
    date: '2026-08-27',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed "No Logo" mode being ignored when using Save to Disk for TV show posters — a logo could still get added even with Logo Mode set to "No Logo". Only affected the manual TV editor\'s Save to Disk button; Send to Plex was never affected.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.66',
    date: '2026-08-27',
    sections: [
      {
        title: 'Performance',
        items: [
          'Sending a poster to Plex (manual or batch) is noticeably faster — the PNG encode now tries a quick pass first and only falls back to the slower, maximum-effort one on the rare poster that actually needs it, with no change in image quality either way.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Backend logs now show the actual movie/show name and how long each step took, instead of just an internal ID — makes it much easier to see what\'s happening during a batch run or troubleshoot a slow send.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.65',
    date: '2026-08-27',
    sections: [
      {
        title: 'New Features',
        items: [
          'Added a Plex status indicator in the top bar so you know right away if your Plex server goes down, instead of finding out when something silently stops working.',
          'Settings and the setup wizard now note that a Fanart.tv API key is needed for Collection posters to auto-find a logo — TMDb has no artwork for Collections at all.',
        ]
      },
      {
        title: 'Performance',
        items: [
          "Sending a poster to Plex (manual or batch) now reuses an existing connection instead of opening a new one for every upload, and label removal no longer re-fetches metadata it just fetched moments earlier.",
        ]
      }
    ]
  },
  {
    version: 'v1.6.64',
    date: '2026-08-24',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the manual "Retry Now" button (History → Retry Queue) always re-sending a poster to Plex even when it still didn\'t meet the template (missing logo, fallback poster/logo used) — it now checks first and only sends when the render actually meets spec, matching how the automatic background retry already worked.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.63',
    date: '2026-08-24',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed posters getting stuck failing to load when quickly cycling through several library pages — the poster/logo endpoints had a rate limit too low for large "Poster Density" page sizes and were getting tripped by normal browsing.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.62',
    date: '2026-08-24',
    sections: [
      {
        title: 'Performance',
        items: [
          'Live preview and rendering could take several seconds to over 10 seconds in some cases — TMDb and Fanart.tv lookups were being re-fetched from scratch on every slider change instead of being reused. These are now cached briefly, which should make editing noticeably snappier.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.61',
    date: '2026-08-24',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the movie/collection editor preview sometimes showing a different movie\'s poster after switching items, or "jumping" back to an older slider value while dragging — a slower, stale render could land after a newer one and overwrite it.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.60',
    date: '2026-08-24',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed a webhook bug that could reprocess the wrong movie or TV show when one TMDb/TVDb ID happened to be a numeric prefix of another (e.g. ID 58 vs ID 5825) — the item matching logic was doing a substring check instead of an exact match.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.59',
    date: '2026-08-23',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the Kometa Creator not showing a "Preset saved!" confirmation when saving a preset.',
          'Fixed the Kometa Creator not saving the selected logo with a preset — reloading or reselecting the preset now correctly restores the logo you had set.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.58',
    date: '2026-08-23',
    sections: [
      {
        title: 'New Features',
        items: [
          'The {folder} save-path variable now works for TV shows, not just movies — resolves to the real on-disk show folder name instead of falling back to the title. Thank you romquenin for the contribution!',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Fixed TV series poster filenames including a stray "(Series)" when using {title} in a save path. Thank you romquenin for the contribution!',
        ]
      }
    ]
  },
  {
    version: 'v1.6.57',
    date: '2026-08-21',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed items that were deleted or reorganized in Plex getting stuck in the retry queue forever, silently adding a new "failed" entry to History every retry cycle. These are now automatically detected and removed from the queue.',
          'Failed History entries now show the actual movie/show title when available, instead of just "(rating key 12345)".',
        ]
      }
    ]
  },
  {
    version: 'v1.6.56',
    date: '2026-08-21',
    sections: [
      {
        title: 'New Features',
        items: [
          'Kometa Creator now has full logo parity with the Simposter Creator: a "Current Plex Logo" preview, a "Send logo" toggle, and a standalone "Send Logo" button.',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the "Choose your creator" popup on the Collections page sometimes appearing off-screen (requiring a scroll to find it) if you\'d scrolled down a long collections list before clicking one.',
          'Fixed API rate-limiting returning a generic server error instead of a proper "please slow down" response when a client sent too many requests too quickly.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.55',
    date: '2026-08-21',
    sections: [
      {
        title: 'New Features',
        items: [
          'Plex Collections now have two dedicated poster creators, alongside Movies and TV Shows: the Simposter Creator (the familiar manual editor, now genuinely collection-aware — pulls real posters from TMDb) and the new Kometa Creator, a from-scratch poster style with flat/textured backgrounds, gradient fades, a centered logo, text, and a border — modeled on the Kometa community\'s own poster conventions.',
          'Collection logos: if Fanart.tv has franchise-wide art for a collection (e.g. a shared "The Lord of the Rings" logo), it now loads automatically in both creators. If not, you can manually import a logo from any movie in the collection instead.',
          'Collections gained their own Save Location setting (Settings → Output), a "Refresh Cache" button, and a working per-card refresh button.',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Fixed collections occasionally showing duplicate or blank poster cards after a library scan.',
          'Fixed some collections resolving to the wrong TMDb collection (e.g. a documentary about a franchise instead of the actual trilogy).',
        ]
      }
    ]
  },
  {
    version: 'v1.6.54',
    date: '2026-08-20',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the onboarding wizard\'s TMDb and TVDB "Test" buttons failing with a generic error instead of actually validating the key — they were still using an old request format that pre-dated a security change to those endpoints. Testing keys from Settings was not affected.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.53',
    date: '2026-08-19',
    sections: [
      {
        title: 'New Features',
        items: [
          'Added a new {season number} template variable for Custom Text — just the season number (e.g. "3"), separate from {season} which always spells out "Season 3" in English. Great for other languages or a custom format.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Raised the logo drop shadow\'s Size/Blur slider max from 150px to 250px.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.52',
    date: '2026-08-19',
    sections: [
      {
        title: 'Improvements',
        items: [
          'Moved the logo Drop Shadow controls from the Bounding Box section into the Logo section, since the shadow only ever applies to the logo.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.51',
    date: '2026-08-19',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the movie editor not saving overlay config selections into presets — enabling an overlay and saving a preset now actually sticks, so it loads (and applies during batch/webhook renders) next time.',
        ]
      },
      {
        title: 'New Features',
        items: [
          'Deleting an overlay config now tells you which presets use it by name before you confirm, instead of a generic warning — and actually removes it from those presets once deleted.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.50',
    date: '2026-08-19',
    sections: [
      {
        title: 'New Features',
        items: [
          'Added a "Full Cover" overlay image type that stretches an uploaded gradient/vignette image to fill the whole poster — no positioning needed. Thank you romquenin for the contribution!',
          'Overlay configs can now be placed below the logo and custom text instead of above, per config, in the Overlay & Border section. Thank you romquenin for the contribution!',
          'Added a logo drop shadow (color, opacity, angle, distance, size) in the Logo section of both editors. Thank you romquenin for the contribution!',
        ]
      }
    ]
  },
  {
    version: 'v1.6.49',
    date: '2026-08-18',
    sections: [
      {
        title: 'Improvements',
        items: [
          'Manual editor decluttering pass: renamed the Logo "Preference" dropdown to "Logo Style" (it sat too close to a similarly-worded but unrelated Logo Mode option), the Preset section starts collapsed to reduce initial clutter, and the Poster section\'s controls are now grouped into Source / Upload & Selection alongside the existing sliders.',
          'TV editor: fixed a bug where clicking the season you were already viewing would silently remove it from the render batch — it now just does nothing, as expected. Also renamed the "None" season button to "Series Only" (it never actually cleared the selection), added clarifying tooltips around season navigation, and made the "Rendered Posters" strip read-only since its highlight could point at a different season than the one actually in focus.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.48',
    date: '2026-08-18',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed "Save As" letting you save a preset name with spaces, which then silently failed to preview or render afterward. Spaces/special characters are now converted automatically (e.g. "Top Overlay" → "Top-Overlay") with a heads-up when that happens.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.47',
    date: '2026-08-18',
    sections: [
      {
        title: 'New Features',
        items: [
          'Added an independent Top Matte + Fade effect — mirrors the existing bottom matte/fade, but fully separate. Use one, both, or neither.',
          'The Poster section in the manual editor is now organized into labeled groups (Position, Top Fade, Bottom Fade, Effects) instead of one long list, making room for the new sliders without adding clutter.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.46',
    date: '2026-08-18',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the {folder} save-path variable never working when sending to Plex (only Save to Disk had it) — it silently fell back to the plain title with no year, or the Plex-localized title for non-English libraries, instead of the real on-disk folder name.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.45',
    date: '2026-08-17',
    sections: [
      {
        title: 'New Features',
        items: [
          'Local Assets now supports bulk delete, alongside the existing bulk resend — select multiple posters and delete them all at once.',
        ]
      },
      {
        title: 'Performance',
        items: [
          'Faster preview loading when opening a movie or TV show in the editor for the first time — the poster and logo now download at the same time instead of one after the other. No change to how posters look or render.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.44',
    date: '2026-08-13',
    sections: [
      {
        title: 'Security',
        items: [
          'Routine dependency security updates (backend and frontend). No user-facing changes.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.43',
    date: '2026-08-13',
    sections: [
      {
        title: 'New Features',
        items: [
          'Added a {folder} save-path variable (Settings → Output) that resolves to the real on-disk folder name Plex knows for a movie, independent of its display-language title — useful when your save-location template needs to match folder names created by Radarr/Sonarr/Kometa rather than Plex\'s metadata title. Falls back to {title} for TV shows/seasons or when it can\'t be resolved. (Thank you romquenin!)',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the filename sanitizer stripping valid punctuation (commas, apostrophes, ampersands, etc.) from saved poster filenames, causing them to drift from the real on-disk names Radarr/Sonarr/Kometa use (e.g. "Widow\'s Bay" became "Widows Bay").',
        ]
      }
    ]
  },
  {
    version: 'v1.6.42',
    date: '2026-08-13',
    sections: [
      {
        title: 'Improvements',
        items: [
          'Changing the preset in the TV show editor now re-renders every other selected season/series in the background, not just the one you\'re currently viewing — switching to another poster now shows the new preset right away instead of stale settings from the old one.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.41',
    date: '2026-08-13',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed "Restrict Custom Text to this box" sometimes not applying a season\'s saved preset value — it was missing from the internal tracking that lets other season-specific settings correctly fall back to what\'s actually saved instead of getting stuck on whatever was last displayed.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.40',
    date: '2026-08-13',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed text overflowing past the bounding box when top or bottom aligned — a small measurement/draw mismatch that barely showed with center alignment became visible once flush top/bottom alignment (added in v1.6.39) had no slack left to absorb it.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.39',
    date: '2026-08-13',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the Bounding Box section\'s Horizontal/Vertical Align buttons having no effect on Custom Text — they only ever moved the logo. Text now honors them too, positioning itself within the box instead of always sitting dead-center.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.38',
    date: '2026-08-13',
    sections: [
      {
        title: 'Improvements',
        items: [
          '"Show bounding box" moved from the preview toolbar into the Bounding Box section, next to the other box-related controls.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.37',
    date: '2026-08-13',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the TV show editor\'s ‹ › season-navigation arrows not loading that season\'s settings (bounding box and everything else) — they moved focus but skipped the save/restore step every other way of switching seasons already did.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.36',
    date: '2026-08-13',
    sections: [
      {
        title: 'Improvements',
        items: [
          '"Bounding Box" is now its own section in the manual editor (between Custom Text and Overlay & Border) instead of being tucked inside Logo — it holds the box size/position controls plus the "Restrict Custom Text to this box" toggle, since the box is shared between Logo and Custom Text rather than belonging to either one.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.35',
    date: '2026-08-13',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed "Restrict to Logo Bounding Box" (Custom Text) leaving you with no way to adjust the box — the Position & Size sliders were hidden whenever Logo Mode was set to "No Logo," which is exactly the setup this feature is meant for. They now stay visible regardless of Logo Mode.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.34',
    date: '2026-08-13',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed a bug where editing a season poster\'s settings (like the logo bounding box) could, under the right timing, get saved into the series poster\'s settings too instead of staying season-specific — a stale internal flag could momentarily point at the wrong poster type right after switching between series and season.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.33',
    date: '2026-08-13',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the TV show editor\'s "Rendered Posters" strip sometimes highlighting the wrong thumbnail after switching between already-rendered seasons — the big preview was always correct, just the highlight lagged behind.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.32',
    date: '2026-08-12',
    sections: [
      {
        title: 'Improvements',
        items: [
          'TV presets are much smaller now. Season poster settings were always saved as a full duplicate of every field, even though only a handful usually differ from the series settings — they are now stored as just the differences, roughly halving preset size. Existing presets are shrunk automatically the first time the app starts on this version, with no change to how they render.',
          '"Copy Compact" exports of TV presets are correspondingly smaller too.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.31',
    date: '2026-08-07',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed a TV show editor bug where switching seasons while a preview was still rendering could cause that render to land on the wrong season once it finished, making it look like the preview was stuck or showing the wrong poster.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.30',
    date: '2026-08-07',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed "Simposter Asset" studio/streaming badges failing to load in the Overlay Manager preview (502 error, "Private/internal network URLs are not allowed" in the logs). Actual poster generation was never affected — this was preview-only.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.29',
    date: '2026-08-07',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the retry queue silently emptying itself when a retry attempt hit a transient failure (e.g. a brief network blip) — it was being misread as "fixed" instead of "still needs another try," so a single bad retry pass could wipe out the whole queue at once.',
          'Fixed "Unknown"-titled FAILED entries in History being impossible to identify — they now show the Plex rating key instead of just "Unknown" when a render fails before the title could be fetched.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.28',
    date: '2026-08-05',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'The previous logo-cropping fix only covered the standalone "Send Logo" button. Batch renders, webhooks, the retry queue, and auto-generate (i.e. the "Also send logos to Plex" option) were sending logos through a separate, still-unfixed code path — now fixed the same way.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.27',
    date: '2026-08-04',
    sections: [
      {
        title: 'New Features',
        items: [
          'Text overlays can now be restricted to a bounding box — turn on "Restrict to Logo Bounding Box" in the Custom Text section and the font size automatically shrinks to fit the same box your logo uses (Logo section → Max Width/Height/Position), instead of overflowing. Handy for season posters or any preset where text takes the place of a logo. The "Show bounding box" preview toggle moved from the Logo section to the preview toolbar, since it is now useful for both.',
        ]
      },
      {
        title: 'Documentation',
        items: [
          'Clarified in Settings → Output that Image Quality settings only affect Preview and Save to Disk — sending to Plex always uses the best quality that fits, regardless of what\'s configured there. (Resending an already-saved file is the one exception — it reuses that file\'s original quality.)',
        ]
      }
    ]
  },
  {
    version: 'v1.6.26',
    date: '2026-08-04',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the standalone "Send Logo to Plex" button sometimes producing a cropped-looking logo once uploaded, even though it looked correct everywhere in Simposter. The logo is now cleaned up through the same image pipeline as everything else before sending.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.25',
    date: '2026-08-04',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed the search bar sometimes bouncing you back to the library grid instead of opening the item you selected, when used while already editing something.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.24',
    date: '2026-07-31',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Found the real cause of the "500 Internal Server Error" some users hit sending to Plex: Plex rejects poster uploads over ~10MB, and a high-detail or heavy-grain poster saved as PNG can cross that line. Sending to Plex still uses PNG (full quality, no compression artifacts) whenever it fits, and now automatically falls back to a high-quality JPEG only for the rare poster that would otherwise be too large — so sends can no longer fail this way.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.23',
    date: '2026-07-31',
    sections: [
      {
        title: 'Security',
        items: [
          'Routine dependency security patching — updated several backend and frontend libraries to their latest secure versions. No user-facing behavior changes.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.22',
    date: '2026-07-31',
    sections: [
      {
        title: 'Improvements',
        items: [
          'Sending to Plex now always uploads a lossless, uncompressed version of the poster, regardless of your Output format setting — no more guessing at the "right" quality level. This should fully resolve the lingering artifacts some users saw even after the last release\'s fix.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.21',
    date: '2026-07-31',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Sending to Plex could still show visible JPEG artifacts on some setups, even after last release\'s fix. If your Output format is set to PNG, sending to Plex now uploads PNG (lossless) instead of always converting to JPEG, matching what you\'d get manually re-uploading a saved file. Still-JPEG users get a quality bump on the Plex-bound copy specifically. (This one is a best-effort fix — let us know if it doesn\'t fully resolve it for you.)',
        ]
      }
    ]
  },
  {
    version: 'v1.6.20',
    date: '2026-07-31',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed a Docker build failure ("Unable to connect to deb.debian.org", missing font packages) caused by the build hitting Debian\'s package servers twice instead of once — a transient network blip on the second pass could fail the whole build. Combined into one pass with automatic retries.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.19',
    date: '2026-07-31',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed visible artifacts (color bleeding/blockiness, especially around colored logos) that only showed up on the poster after sending to Plex, never in preview or a local save. Root cause: posters sent to Plex are always converted to JPEG, and the JPEG encoder was using a lower-quality default color setting that\'s more noticeable on that conversion than elsewhere. Fixed for all previews, saves, and sends going forward.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.18',
    date: '2026-07-31',
    sections: [
      {
        title: 'New Features',
        items: [
          'You can now upload your own logo in the editor, the same way you could already upload a custom poster — drag and drop or click to upload, in the Logo section for both movies and TV shows. (Thanks Spyro!)',
        ]
      }
    ]
  },
  {
    version: 'v1.6.17',
    date: '2026-07-31',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed uploading a custom poster or background failing with "Private/internal network URLs are not allowed for this host" — the security check protecting against malicious URLs didn\'t recognize the app\'s own upload endpoint as safe. Uploaded posters/backgrounds now preview, save, and send to Plex normally.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.16',
    date: '2026-07-31',
    sections: [
      {
        title: 'Documentation',
        items: [
          'README\'s setup instructions rewritten — Simposter has never been published to a container registry, so "docker pull"-style examples were misleading. Now leads with the actual supported flow (docker-compose build + run) and explains updating is just "pull the code, rebuild."',
          'Fixed the Mac/Linux build script (build-docker.sh) so it tags images the same way the Windows one does — previously it never set the Docker tag, so Mac/Linux-built images silently lost the "unmaintained tag" warning banner in the UI.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.15',
    date: '2026-07-27',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed library scan progress appearing stuck at "0/..." for movie libraries — it now updates live as posters, logos, and labels are fetched instead of only jumping to done at the very end.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.14',
    date: '2026-07-23',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Local Assets refreshing was slow — it was re-reading every saved poster file from disk on every refresh. Unchanged files are now served from a cache instead, so refreshing should be much faster, especially with a lot of saved posters.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.13',
    date: '2026-07-23',
    sections: [
      {
        title: 'Improvements',
        items: [
          'Settings reorganized into clearer groups: a new "Output" tab combines Save Locations and Image Quality; a new "Automation" tab combines the Webhook URL Generator and Automatic Poster Generation settings, which used to be split across three different tabs. Nothing was removed — everything just moved to a more logical home.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.12',
    date: '2026-07-23',
    sections: [
      {
        title: 'New Features',
        items: [
          'Save Locations now has quick-select presets — Default, Flat (Kometa), Asset folders (Kometa), or Custom — so you can save posters in a layout Kometa (and other tools) can read directly, without hand-writing template strings.',
          'New "Save to asset folder on send" option (Settings → Save Locations): when on, sending a poster to Plex also saves it to your configured folder, so other tools can reuse the file.',
          'Resending a poster now shows a quick preview — saved poster vs. what\'s currently live in Plex — before it actually sends, instead of sending immediately.',
          'Local Assets can now select multiple saved posters and resend them to Plex all at once, with a summary of how many succeeded, were skipped, or failed. Only applies to posters saved from this release onward.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Simplified and fixed the save-location settings — consolidated four slightly different copies of the same logic, fixed TV batch saves not respecting your configured output folder correctly, fixed the batch "save in subfolder" option not working for TV shows, and fixed JPEG-format TV/season saves missing metadata that PNG saves already had.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.11',
    date: '2026-07-14',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed a crash where setting the new Webhook Secret (or any API key) to a value made only of digits (e.g. "123") would break Settings entirely, including scheduled library scans, until it was changed to something else. This resolves itself automatically on update — no need to re-enter anything.',
          'Corrected the Webhook Secret help text — Radarr and Sonarr don\'t support a custom header for webhooks, so the secret needs to be added to the webhook URL itself (?secret=your-secret) rather than as a header.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.10',
    date: '2026-07-14',
    sections: [
      {
        title: 'Security',
        items: [
          'API keys and your Plex token are no longer shown in plain text in Settings responses — they\'re masked, and saving only changes them if you actually edit the field. The "Test" buttons still work as before.',
          'Database export now leaves API keys/tokens out by default (there\'s a checkbox in Settings → Advanced to include them for a full migration backup).',
          'Closed a gap where image URLs (posters, logos, custom badges) could be pointed at internal/private network addresses, including cloud metadata endpoints — now blocked with a narrow exception for your own Plex server.',
          'Fixed a path-traversal bug in the local save feature that could, in theory, write a rendered poster outside the configured output folder.',
          'The webhook secret setting (Settings → Performance → Automatic Poster Generation) is now actually enforced when set — previously it had no effect.',
          'Turned on request rate-limiting to prevent accidental or malicious request floods on expensive endpoints (batch render, webhooks).',
          'Tightened an overly permissive CORS setting (no functional impact — the app doesn\'t use browser cookies for authentication).',
        ]
      }
    ]
  },
  {
    version: 'v1.6.09',
    date: '2026-07-08',
    sections: [
      {
        title: 'Improvements',
        items: [
          'Retry queue no longer re-sends the same poster on every attempt — each retry now checks whether the new render actually meets the template spec (logo found, no fallback used) before uploading to Plex. Attempts that still don\'t meet spec are skipped and left pending for the next retry, instead of re-uploading an unchanged fallback poster. For TV shows, this is checked per season/series poster, so shows with a mix of ready and not-ready seasons only send the ones that are ready.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.08',
    date: '2026-07-06',
    sections: [
      {
        title: 'New Features',
        items: [
          'Resend cached poster to Plex — hover any movie or TV show card to reveal a send button (bottom-left). For TV shows, a prompt lets you choose to resend the show poster only or include all cached season posters. No re-render required.',
          '"Cached only" filter button in the Movies and TV Shows toolbars — instantly filters the grid to items that have a locally cached render, with a live count shown while active.',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Resend now removes configured labels from Plex (e.g. Simposter, Overlay) and syncs the label cache — consistent with the full render pipeline.',
          'Resending a cached poster now refreshes the thumbnail in the grid immediately after upload.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.07',
    date: '2026-06-30',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Labels were not removed after a successful retry — items processed by the retry queue (e.g. "retried until template met") now have their configured labels removed from Plex just like auto-generate and webhooks do.',
          'Labels were not removed when a cached poster was resent (existingContentMode=resend) — resend paths in webhooks and scheduled scans now remove the configured labels after uploading, matching the behaviour of a full render.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.06',
    date: '2026-06-26',
    sections: [
      {
        title: 'New Features',
        items: [
          'Preset names are now shown in History and Retry Queue instead of the internal preset ID — renaming a preset is immediately reflected everywhere.',
          'Preset duplication — click the ⎘ button on any preset card to create a copy with all options preserved.',
          'History search box — filter the history table by title without leaving the page.',
          'Retry queue thumbnail — hover or click the View button on any retry queue item to preview the current Plex poster.',
          'Compact preset export — "Copy compact" button in Template Manager → Import/Export copies a minified version of your presets to the clipboard with default values stripped (typically 80–90% smaller). Ideal for sharing.',
          'Preset rename — click the pencil icon on any preset card to rename it inline. The internal ID never changes so all history records, webhook configs, and settings stay linked correctly.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Preset exports (both regular and compact) no longer include internal IDs — IDs are Simposter-managed and invisible to users. On import, a fresh ID is always generated so imported presets never conflict with or overwrite existing ones.',
          'Preset rename is instant — the new name appears immediately without waiting for the backend to respond.',
          'History and Retry Queue preset column resolves the current display name from the presets list, so renames are reflected in past records too.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.05',
    date: '2026-06-24',
    sections: [
      {
        title: 'New Features',
        items: [
          'Clickable titles in History and Retry Queue — click any movie or TV show title to navigate directly to its editor, bypassing the need to search or scroll through the library.',
        ]
      },
      {
        title: 'Bug Fixes',
        items: [
          'Fixed retry queue not receiving items when a logo fallback preset was used during auto-generate or scheduled scan.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.02',
    date: '2026-06-22',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed retry queue not receiving items when a logo fallback preset was used during auto-generate or scheduled scan. When no logo is found and the fallback preset switches to one with logo_mode "none", the original needs_retry check evaluated to false — items are now correctly enqueued whenever a logo or poster fallback fires.',
        ]
      }
    ]
  },
  {
    version: 'v1.6.01',
    date: '2026-06-19',
    sections: [
      {
        title: 'Bug Fixes',
        items: [
          'Fixed timezone selection appearing blank in Settings after onboarding — the Settings timezone dropdown now includes all timezones available in the onboarding wizard, and any saved or browser-detected timezone not in the standard list is automatically added as an option.',
          'Fixed Kometa "Overlay" label not appearing in Default Labels to Remove after onboarding — labels are now saved with library IDs as keys, matching the format Settings expects.',
          'Fixed scheduled scan having no libraries selected after onboarding — all configured libraries are now included in the scheduler settings saved during setup.',
          'Retry poster generation (Retry Until Template Is Met) is now enabled by default on new installs.',
        ]
      }
    ]
  },
  {
    version: 'v1.6',
    date: '2026-06-19',
    sections: [
      {
        title: 'New Features',
        items: [
          'Onboarding wizard for new users — guided setup covering Plex connection, library selection, API keys (TMDb, TVDb, Fanart) with inline test buttons, automation preferences (Kometa, scan schedule, timezone, label tracking), performance defaults, and Apprise notifications.',
          'Library scan starts immediately after the libraries step so content is ready by the time setup finishes.',
          'Default preset (Uniformlogo) is automatically imported on completion — no manual step needed.',
          'Quick start guide appears after onboarding — a feature overview card grid covering Libraries, Batch Edit, Template Manager, Overlay Manager, Local Assets, and Backup & Restore.',
          'Fixed clearlogo fetch from Plex: the Image[].url from Plex\'s JSON API is a relative path and now correctly has the Plex base URL and auth token prepended before download.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.998',
    date: '2026-06-18',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Fixed "Existing Content — Poster Behaviour" (Resend/Regenerate) setting not persisting after save. The backend Pydantic schema for AutomationSettings was missing the field, causing it to be silently stripped on every POST. The setting now saves and restores correctly.',
          'Fixed batch runs not adding items to the retry queue when a fallback preset was used. Batch results are now evaluated for retry eligibility the same way webhooks and auto-generate runs are.',
          'Resent posters are now tracked in History with a distinct "Resent to Plex" action badge (purple). Includes a hover thumbnail preview and appears in the Action filter dropdown. Previously resend events were logged to file only and invisible in the History page.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.997',
    date: '2026-06-17',
    sections: [
      {
        title: 'New Feature',
        items: [
          'New "Retry Until Template Is Met" automation setting. When auto-generate or a webhook fires and the ideal poster cannot be made (logo not found, or no textless poster available), Simposter now queues the item for automatic retry at a configurable interval. Once the ideal poster is generated it is saved, uploaded to Plex, and removed from the queue. Manually sending a poster for any title immediately removes it from the queue.',
          'New Retry Queue tab in History — shows all pending retries with reason (no logo / no textless poster), attempt count, last tried timestamp, and per-item Retry Now / Dismiss actions.',
          'Settings → Performance: toggle retry on/off, set retry interval (hours), and optionally cap the max retry attempts (0 = unlimited).',
          'Diagnostic logging added for auto-generate logo sends ([AUTO_GEN] sendLogosToPlex=) and batch logo upload path ([BATCH] Logo upload check:) to help troubleshoot missing logo uploads.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.996',
    date: '2026-06-11',
    sections: [
      {
        title: 'New Feature',
        items: [
          'New automation setting: "Existing Content — Poster Behaviour". Set to Resend to push the last generated poster back to Plex when a webhook or scan fires for a title that already has a Simposter poster, instead of regenerating from scratch. Useful for protecting manually tuned posters from being overwritten by Radarr/Sonarr events.',
          'Rendered posters are now cached locally to /config/cache/poster_renders/ whenever sent to Plex (manual, batch, webhook, or auto-scan). Deleting the cache directory gracefully falls back to regeneration.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.995',
    date: '2026-05-08',
    sections: [
      {
        title: 'ClearLogos Support',
        items: [
          'New Logos page — browse all clearlogos in your movie/TV library, see what\'s missing, and click any card to open the Logo Editor.',
          'Logo Editor — pick from TMDb/Fanart.tv logos or upload your own, then send it to Plex\'s clearLogo slot with one click.',
          'Send Logo button in both manual editors — push the selected logo to Plex independently of the poster.',
          'Send logos during batch runs and via the manual editor\'s Send to Plex action (optional checkbox).',
          '"Send logos to Plex by default" setting in Settings → Libraries — also applies to webhook triggers and automatic scan sends.',
          'Current Plex Logo display in both manual editors with a refresh button.',
          'Logos page now has sort, filter (all / has logo / missing), and search.',
        ]
      },
      {
        title: 'Bug Fix',
        items: [
          'Custom text overlay now correctly uses the selected font. Liberation Sans, Serif, and Mono fonts are bundled in Docker; the font picker shows all available fonts.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.99',
    date: '2026-04-28',
    sections: [
      {
        title: 'New Feature',
        items: [
          'Batch Results panel now appears after every batch run in both Movie and TV Show Batch Edit. Shows succeeded / failed / poster fallback / logo fallback counts, a collapsible list of failed items with human-readable error reasons, and a collapsible list of items that used a fallback preset.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.98',
    date: '2026-04-24',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Fixed edition label being wiped from the movie card after sending a poster to Plex or refreshing poster metadata. Cache upserts now use COALESCE to preserve the existing edition value when the update does not supply one.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.97',
    date: '2026-04-24',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Fixed {title} text overlay variable including the Plex edition tag (e.g. "Hokum (Coming Soon)" instead of "Hokum"). Movie titles are now stored without the edition appended; the edition is displayed separately in the movie grid card as before.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.96',
    date: '2026-04-23',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Fixed poster and logo fallback presets not applying their overlay cache in the movie preview/save/send path. When a fallback preset fired, the original preset\'s overlay effects (matte/fade/vignette) were still used instead of the fallback preset\'s. The movie path in preview.py now updates req.preset_id when poster or logo fallback triggers, matching the existing behavior in batch rendering and the TV show path.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.95',
    date: '2026-04-22',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Fixed fallback rules (Logo Fallback / Poster Fallback configured in Template Manager) being silently wiped whenever a preset was saved from the movie or TV editor. The EditorPane save now merges onto the existing preset options, so fallback configuration, overlay config links, and any other settings not exposed by the editor sliders are preserved.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.94',
    date: '2026-04-22',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Label removal is now immediately reflected in Simposter\'s label filter. Previously, after auto-generate or batch removed labels from Plex (e.g. "Overlay", "Simposter"), the local cache still showed the item under those labels until the next full library scan. The cache is now updated in-place right after each label is removed.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.93',
    date: '2026-04-22',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Auto-generate and webhook renders now read the global "White Logo Fallback" setting from the database (matching normal batch behaviour). Previously the setting was always read from the preset options, which defaulted to "continue" even when the global setting was "use_next" — so movies with logos that didn\'t match the white preference would silently render without a logo instead of falling back to the next available one.',
          'Added a log line whenever no logo is found during auto-generate or batch, showing which fallback action will be applied (e.g. "continue", "skip", or "template"). This makes it visible in the logs whether the Logo Fallback in Template Manager is configured or not.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Fade Height slider maximum increased from 40% to 100%.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.92',
    date: '2026-04-07',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Auto-generate no longer re-processes items that were already handled by a Radarr/Sonarr webhook within the cooldown window. Previously, items added via webhook could be picked up again by the next auto-scan.',
          'Fixed duplicate notifications from auto-generation: previously one notification was sent per poster plus a second batch-summary notification for the same items. Now only the per-poster notification fires.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.91',
    date: '2026-04-11',
    sections: [
      {
        title: 'New Feature',
        items: [
          'Sidebar can now be collapsed to an icon-only rail by clicking the chevron button in the header. Collapsed state is saved across page reloads. Collapsing gives the content area (poster grid, editor, etc.) the full extra space.',
        ]
      },
      {
        title: 'Bug Fix',
        items: [
          'Auto-generated poster notifications now include the poster preview image. Previously the notification was sent without an image because the poster bytes were not passed through the auto-generate code path.',
          'Fixed a preview crash where the TV show editor would construct a broken double-proxied URL (/api/plex-poster?path=/api/movie/...) when a show had no poster in the cache. The backend would then fail to decode the response as an image.',
          'Tightened the internal-API URL detection in the preview endpoint so a URL containing /api/movie/ in a query parameter is no longer mistaken for a direct internal path, preventing malformed URLs from bypassing validation.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.9',
    date: '2026-04-10',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Bounding box overlay now correctly aligns to the image when the preview panel is wider than the poster. Previously the box was offset because the image\'s position inside the container wasn\'t accounted for, causing users to compensate by setting X% to non-center values.',
          'Auto-generated posters now appear as "Auto" in History instead of "Manual". The source value "auto_generate" was falling through to the default manual case.',
          'Default "Labels to Remove" configured per-library in Settings are now respected during auto-generation and webhooks. Previously only the global auto-labels field was used, so per-library label removal had no effect on automatic sends.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Border thickness slider maximum increased from 30px to 60px.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.89',
    date: '2026-04-06',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Fixed a phantom "Library 1" appearing on fresh installs with no Plex configured. The backend was hardcoding "1" as a fallback library ID when no libraries were set up, causing the Settings page to show an unremovable stub entry. New installs now start with an empty library list.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'History now records failed renders with a status of "Failed" and the error reason. Failed entries are filterable in the Action dropdown and display the error message in red in the Path column. Batch logs also now show the movie/show title instead of just the internal rating key when reporting errors.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.88',
    date: '2026-04-06',
    sections: [
      {
        title: 'New Feature',
        items: [
          'Manual editor: you can now upload your own poster image directly in the Poster section. Drag and drop an image onto the upload zone or click to browse. The uploaded image is used as the background and goes through all the same template effects, logo overlays, matte, fade, vignette etc. as any TMDb poster. Hover the uploaded thumbnail to swap it or clear it. Works in both the movie and TV show editors.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.87',
    date: '2026-04-06',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Logo bounding box is now a manual checkbox in the Logo section ("Show bounding box") instead of auto-toggling based on section open state. Previously it would inconsistently appear and disappear as the accordion opened/closed.',
          'Browser back button now correctly returns to the exact page, sort, and filter state when closing the poster editor. Previously, opening the editor replaced the history entry, making the back button go to the wrong page.',
          'TV show editor: selecting individual seasons no longer silently includes the series poster. The series was auto-selected on load and never cleared when the user picked specific seasons, causing unintended series poster sends.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Settings: "Items per page" slider maximum raised from 40 to 100.',
          'Batch edit (Movies & TV): Sort By and Order dropdowns merged into a single combined selector (e.g. "Date Added (Newest First)", "Title (A-Z)") to reduce toolbar clutter.',
          'Template Manager: preset summary chips now show labeled key/value pairs ("Logo · White", "Poster · Textless") instead of bare values for clarity.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.86',
    date: '2026-04-06',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'TV show editor: selecting specific seasons no longer automatically includes the series poster. Previously, the series was auto-selected on load and never dropped when the user picked individual seasons — so sending Season 1 + Season 2 would also send the series. Now, clicking a season when only the series is selected (the default) replaces it rather than appending to it.',
          'Template Manager: fixed missing clearSelectedPreviewMovie function that caused an error when clicking × to clear a pinned preview movie.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Template Manager redesigned: presets now display as full-width list items with labeled summary chips (Logo · White, Poster · Textless, etc.) instead of plain text. Each card expands to show a settings grid with Series/Season tabs. "Global Preset Preferences" renamed to "Default Batch Settings" and made collapsible. Import/Export section also collapsible.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.85',
    date: '2026-03-31',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Studio and streaming platform overlay badges now render correctly when sending to Plex or saving locally. Previously, tmdb_id was only injected during preview — the send and save paths were missing it, so studio/streaming badge lookups always returned empty.',
          'Mobile TV show editor now shows season selection correctly: pills display a checkmark and distinct highlight for selected seasons, plus All/None buttons to bulk-select.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'Apprise notifications sent to Discord webhook URLs now render as rich embeds (with poster thumbnail, color coding, library/template/action fields) instead of plain text — identical to the native Discord integration. Other Apprise services (Slack, Telegram, Pushover, etc.) are unaffected.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.841',
    date: '2026-03-29',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Notification settings (Discord and Apprise) now save and persist correctly. Previously, all Apprise fields were silently stripped by the backend schema before reaching the database, and the notifications object was not included in the settings merge — causing settings to revert on page refresh.',
        ]
      },
      {
        title: 'Improvements',
        items: [
          'TV batch preview now preloads selected shows concurrently (up to 3 in parallel) instead of staggering requests 300ms apart. With 10 shows selected, previews are ready significantly faster.',
          'Manual editor: settings panel reorganised into collapsible accordion sections (Preset, Poster, Logo, Custom Text, Overlay & Border). Template dropdown removed since only one template exists. Logo bounding box auto-shows when the Logo section is expanded and hides when collapsed or when No Logo is selected.',
          'TV show editor now includes horizontal/vertical alignment controls (previously missing). Mobile layout gains a scrollable season pill strip so seasons are accessible on narrow screens.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.83',
    date: '2026-03-27',
    sections: [
      {
        title: 'Improvements',
        items: [
          'Cleaned up backend and frontend logging — removed ~150 debug console.log/print statements across the codebase. Backend template modules (uniformlogo, universal) now use the structured logger instead of raw print(). Frontend views and editor panes no longer emit verbose debug output to the browser console. Warnings and errors are preserved.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.82',
    date: '2026-03-22',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Season poster settings (poster filter, text overlay, logo mode, etc.) are no longer wiped when saving the series preset from the editor. Previously, saving the series preset would overwrite season_options with an empty object, causing webhooks and batch to render seasons with the wrong settings.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.81',
    date: '2026-03-20',
    sections: [
      {
        title: 'New Features',
        items: [
          'Logo alignment within the bounding box — choose horizontal (left / center / right) and vertical (top / center / bottom) alignment independently. Saved per-preset. Defaults to center/center so existing presets are unaffected.',
        ]
      }
    ]
  },
  {
    version: 'v1.5.8',
    date: '2026-03-19',
    sections: [
      {
        title: 'Bug Fix',
        items: [
          'Matte height, fade height, and vignette sliders now update the preview in real-time for all presets. Previously, presets with a saved overlay cache (e.g. a custom preset with effects enabled) would show a stale preview because the baked-in cache was used instead of the new slider values. (Thanks chadwpalm!)',
        ]
      }
    ]
  },
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
