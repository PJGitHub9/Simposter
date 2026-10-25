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
  {
    version: 'v1.6.109',
    title: 'New Asset Types & Housekeeping',
    intro: "Another batch of updates while you were away — square art, backdrop browsing, a real cleanup tool, and a much smarter backup/restore. Here's the highlight reel; the full changelog is still one click away below.",
    highlights: [
      {
        icon: '🔳',
        title: 'Square Art library section',
        description: 'Generate square (1:1) art from your existing templates and presets for movies and TV shows — browse, save, and send straight to Plex.',
      },
      {
        icon: '🎞️',
        title: 'Backdrops library section',
        description: 'Browse, preview, and send Plex background art per item, mirroring the existing Logos tab — plus a per-card refresh button to re-check what Plex currently has.',
      },
      {
        icon: '🧹',
        title: 'A real Cleanup tool',
        description: 'A dry-run scan finds orphaned cache files, stale overlay renders, and old History entries, then moves them to a reversible trash instead of deleting outright — plus one-click Plex maintenance (Empty Trash, Clean Bundles, Optimize Database) and an optional weekly schedule.',
      },
      {
        icon: '📦',
        title: 'Backup/Restore now covers everything',
        description: 'Previously posters-only — now back up and restore Logos, Backdrops, and Square Art too, with a per-type checklist so you choose exactly what to protect.',
      },
      {
        icon: '🔁',
        title: 'A smarter Retry Queue',
        description: 'Manually queue an item to auto-retry once a textless poster becomes available, and items whose Plex source is genuinely gone are removed outright instead of lingering as duplicate "abandoned" entries.',
      },
      {
        icon: '⚡',
        title: 'Logos/Backdrops/Square Art feel instant now',
        description: 'Caching, pagination, and generated thumbnails bring these three tabs up to the same snappy, cache-first loading Movies and TV Shows already had.',
      },
      {
        icon: '🔗',
        title: 'Quick jumps to TMDb, TVDB, Fanart.tv & MediUX',
        description: 'A row of external links under the title in the manual editor, so you can pop open the source pages for a movie, show, or collection in one click.',
      },
      {
        icon: '🔔',
        title: 'Notifications know what got sent',
        description: 'Discord/Apprise notifications now say whether a poster, logo, backdrop, or square art was sent — and Logos/Backdrops/Square Art gained date-added sorting and label filtering to match the Movies/TV grids.',
      },
    ],
  },
  {
    version: 'v1.7.0',
    title: 'Jellyfin & Emby Support',
    intro: "Simposter now works with Jellyfin and Emby as well as Plex — use any one of them, or several at once. Here's the highlight reel; the full changelog is still one click away below.",
    highlights: [
      {
        icon: '🖥️',
        title: 'Plex, Jellyfin and Emby',
        description: 'Add any mix of servers in Settings → Media Servers, test the connection, and give each one a name. Plex is no longer required — a Jellyfin-only or Emby-only setup works on its own.',
      },
      {
        icon: '🔗',
        title: 'Library groups',
        description: 'Group the same library across servers (for example Plex "Movies" + Jellyfin "Movies") in Settings → Libraries. A group shares one set of settings, scans together, and can show each title once or once per server.',
      },
      {
        icon: '📤',
        title: 'Send to any server',
        description: 'The editors, Batch Edit, resend and Local Assets let you pick which servers get a poster, logo or backdrop — with one notification per send. Server icons on each card show where a title lives.',
      },
      {
        icon: '🪞',
        title: 'Media Mirror',
        description: 'Copy posters, logos, backdrops and collection art from one server to the others in a group, on demand or on a schedule. Only changed images are copied again.',
      },
      {
        icon: '🪝',
        title: 'Webhooks and auto-generate everywhere',
        description: 'Radarr/Sonarr webhooks can target a library group by name, and new items found by a Jellyfin or Emby scan get posters automatically, just like Plex.',
      },
      {
        icon: '🌄',
        title: 'Thumb Art for Jellyfin & Emby',
        description: "A new page for Jellyfin/Emby's 16:9 Thumb image — the counterpart to Plex's Square Art — built from your existing templates.",
      },
      {
        icon: '📚',
        title: 'Collections, backups and cleanup across servers',
        description: 'Jellyfin collections show up next to Plex ones (with manual matching when names differ), Backup/Restore works on Jellyfin, and Cleanup can run each server\'s own maintenance tasks.',
      },
      {
        icon: '🔄',
        title: 'Scans that keep up',
        description: 'Library scans are much faster and now pick up posters changed outside Simposter (for example by Kometa) without a force refresh.',
      },
      {
        icon: '✏️',
        title: 'A tidier poster editor',
        description: 'Settings in tabs and collapsible cards, separate logo and text boxes you can drag right on the preview, guides, and backdrops as poster backgrounds.',
      },
    ],
  },
  {
    version: 'v1.8.0',
    title: 'Overlays, rebuilt',
    intro: "This update is mostly about overlays: what you can put on a poster, when it shows, and how easy it is to build. Here's the short version; the full changelog is one click away below.",
    highlights: [
      {
        icon: '🧱',
        title: 'A friendlier overlay editor',
        description: 'Layers listed top-down, Look / Position / Show when tabs for each one, grouped settings, warnings when a layer would show nothing, and a preview that can compare several posters at once.',
      },
      {
        icon: '🎯',
        title: 'Show when',
        description: 'Put a layer, or a whole overlay, only on the posters that match: 4K only, Atmos only, remux files, highly rated movies, items on an MDBList list, and more.',
      },
      {
        icon: '🏷️',
        title: 'Badge sets',
        description: "Group badges that shouldn't appear together, like 4K, 1080p and 720p, and only the first match is drawn.",
      },
      {
        icon: '⭐',
        title: 'Ratings on posters',
        description: 'With an MDBList API key, show IMDb, Rotten Tomatoes, Metacritic and other ratings as text or use them in conditions.',
      },
      {
        icon: '📥',
        title: 'Kometa import (beta)',
        description: 'Bring in your Kometa overlay files, or point Simposter at files another tool like UMTK keeps rewriting and it re-imports them on a schedule. It maps what it can and tells you what it skipped.',
      },
      {
        icon: '🔁',
        title: 'Overlay Refresh',
        description: 'Keep posters up to date when their overlay would change, e.g. a movie upgraded to 4K, on a schedule per library.',
      },
      {
        icon: '🔔',
        title: 'Changed outside Simposter',
        description: 'Simposter notices when a poster, logo or backdrop it sent was changed on the server by something else. A badge marks it on the grid, and History lets you put Simposter\'s version back or keep the new one.',
      },
      {
        icon: '🔤',
        title: 'Starter presets and fonts',
        description: 'Two new starter presets, a set of free fonts that comes with the Simposter defaults, and Kometa\'s own fonts for imported overlays.',
      },
      {
        icon: '🔔',
        title: 'Branch-aware updates',
        description: 'The version badge now shows updates for the branch you run, and tells you when that branch was merged and where to move.',
      },
    ],
  },
]
