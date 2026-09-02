# <img src=".github/icon-512.png" alt="Simposter logo" width="50" height="50"> Simposter

> **Template-based poster generation for Plex** — Create clean, consistent custom posters with TMDb/TVDB/Fanart.tv artwork, overlay badges, and full batch automation.

![Simposter UI](https://github.com/user-attachments/assets/fa22c97f-ad8c-4a7e-b6ef-1aaa3d7a5022)

---

## Features

- **Live-preview poster editor** for movies, TV shows (per-season, independent artwork/logo/text), and **Plex Collections** (two dedicated creators, including a Kometa-style one)
- **Multi-source artwork** — TMDb, TVDB, Fanart.tv, with configurable priority and fallback rules
- **Overlay badges** — resolution, codec, audio, edition, studio, streaming platform, custom images, text
- **Batch edit** — apply a preset across your whole library in one run, with live progress
- **Webhooks** — Radarr, Sonarr, and Tautulli, auto-generate on import
- **Scheduled scans** and a **smart retry queue** for hands-off automation
- **Guided setup wizard** on first launch — Plex, API keys, libraries, automation, all in one flow
- **6 themes**, Discord/Apprise notifications, full History audit log with hover previews

Full breakdown of all of this in the docs below.

---

## Quick Start

```bash
git clone https://github.com/PJGitHub9/Simposter.git
cd Simposter
docker-compose up -d --build
```

Open `http://localhost:8003` — a setup wizard walks you through Plex/API keys/libraries from there. No manual config file editing required.

**Updating:** `git pull && docker-compose up -d --build` — your data lives in the bind-mounted `./config` folder, untouched by rebuilds.

Prefer not to build locally? Pre-built images are published to [ghcr.io/pjgithub9/simposter](https://github.com/PJGithub9/Simposter/pkgs/container/simposter) — see **[Getting Started](docs/GETTING_STARTED.md)** for the compose snippet. That doc also covers local dev (no Docker), alternative install methods, environment variables, the setup wizard step-by-step, and your first poster.

---

## Documentation

| Doc | What's in it |
|-----|--------------|
| **[Getting Started](docs/GETTING_STARTED.md)** | Install (Docker/local dev), the setup wizard, your first poster, Settings reference, environment variables |
| **[Collections & Poster Guide](docs/COLLECTIONS_AND_POSTERS.md)** | Templates/presets, logos, overlay badges, batch processing, the smart retry queue, and Plex Collections (including why a Fanart.tv key matters) |
| **[Webhooks](docs/WEBHOOKS.md)** | Radarr, Sonarr, and Tautulli setup, payload examples, dry-run testing |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | Technical architecture, API routers, rendering pipeline (for contributors) |
| **[WORKFLOW.md](WORKFLOW.md)** | How a poster request flows end-to-end for each trigger type |
| **[CHANGELOG.md](CHANGELOG.md)** | Full version history |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | Dev setup, PR expectations, code conventions |
| **[SECURITY.md](SECURITY.md)** | Security model and how to report a vulnerability |

---

## Why Simposter?

A few related projects solve overlapping problems — no affiliation with any of them, just worth knowing which fits:

- **[Kometa](https://kometa.wiki/)** manages your whole Plex metadata/collection setup, including posters pulled from its own defaults repo. Simposter is poster-generation-only, with a live in-app editor and per-item control — the two pair well together (Simposter's Kometa Creator for Collections is directly modeled on Kometa's own poster conventions).
- **[Posterizarr](https://github.com/fscorrupt/Posterizarr)** is best for mass library operations — a similar automation-first poster tool, but it misses out on manual per-item customization. Simposter leans more toward interactive editing (live preview, manual per-item tuning) alongside its automation, rather than automation-only.
- **[PosterTools](https://postertools.org/square-lab/)** is best for non-selfhosters — a hosted poster/title-card creation tool, no server to run yourself.
- **[TitleCardMaker](https://github.com/CollinHeist/TitleCardMaker)** focuses specifically on TV episode title cards, a different artifact than posters.
- **[UMTK](https://github.com/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa)** generates "coming soon" overlays, a narrower and complementary use case.

**Poster styles that inspired Simposter:** [darkmatte](https://www.reddit.com/r/PlexPosters/) and [ikonok](https://www.reddit.com/r/PlexPosters/) — both from r/PlexPosters.

---

## License

MIT License — See [LICENSE](LICENSE) for details.

---

## Credits

Built with [FastAPI](https://fastapi.tiangolo.com/), [Vue 3](https://vuejs.org/), [Pillow](https://python-pillow.org/), [TMDb API](https://www.themoviedb.org/documentation/api), [TVDB API](https://thetvdb.com/api-information), and [Fanart.tv API](https://fanart.tv/get-an-api-key/).

Developed with the assistance of [Claude](https://claude.ai/). All features are designed, directed, and tested by a human. (Still learning! :D)
