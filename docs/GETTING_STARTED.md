# Getting Started

This walks through installing Simposter, the first-launch setup wizard, generating your first poster, and a reference for every Settings tab. For webhook setup (Radarr/Sonarr/Tautulli), see [WEBHOOKS.md](WEBHOOKS.md). For templates, logos, badges, and Collections, see [COLLECTIONS_AND_POSTERS.md](COLLECTIONS_AND_POSTERS.md).

---

## Install

### Docker Compose (recommended)

Two ways to get the image — pull the pre-built one from GHCR (fastest, no local build), or build it yourself from source. Both use the same `./config` bind mount, so your database, presets, and saved posters live outside the container either way.

**Option A — pull the pre-built image (no clone/build needed):**

```yaml
# docker-compose.yml
services:
  simposter:
    image: ghcr.io/pjgithub9/simposter:latest
    container_name: simposter
    ports:
      - "8003:8003"
    environment:
      - CONFIG_DIR=/config
    volumes:
      - ./config:/config
    restart: unless-stopped
```

```bash
docker-compose up -d
```

Images are built and pushed to [ghcr.io/pjgithub9/simposter](https://github.com/PJGithub9/Simposter/pkgs/container/simposter) automatically on every push, tagged both by branch name and `latest` (which tracks `main`). If `main` is behind whatever branch has the newest work (check the repo's branch list and [CHANGELOG.md](../CHANGELOG.md) on each branch to compare), pin the compose file's `image:` tag to that branch name instead (e.g. `ghcr.io/pjgithub9/simposter:webui-overhaul-dev`) to track it — the app also shows an update-available banner in Settings that tells you if you're behind.

**Updating (Option A):**
```bash
docker-compose pull
docker-compose up -d
```

**Option B — build from source (what the repo's own `docker-compose.yml` does by default):**

```bash
git clone https://github.com/PJGitHub9/Simposter.git
cd Simposter
docker-compose up -d --build
```

This builds from the included `Dockerfile` instead of pulling an image — useful if you want to run a fork, a local branch, or verify exactly what's running by building it yourself. The shipped `docker-compose.yml` uses `build: .`; swap it for `image: ghcr.io/pjgithub9/simposter:<tag>` (Option A above) if you'd rather not build locally at all.

Open `http://localhost:8003` — the setup wizard takes it from there (see below).

**Updating (Option B):**
```bash
git pull
docker-compose up -d --build
```
`./config` is a bind-mounted folder, not part of the image — pulling or rebuilding never touches your settings, database, or saved posters, in either option.

**File permissions:** if `./config` is owned by a specific user/group on your host (common on Unraid/NAS setups) and the container's default user can't write to it, set `PUID`/`PGID` (and optionally `UMASK`) under `environment:` in `docker-compose.yml` — the container's entrypoint creates a matching user and takes ownership of `/config` before starting, the same convention LinuxServer.io images use:
```yaml
environment:
  - PUID=1000
  - PGID=1000
  - UMASK=0002
```

### Alternative: build script + `docker run`

If you'd rather manage the container yourself instead of using Compose:

```bash
# Windows
build-docker.bat

# Linux/Mac
./build-docker.sh

# Then run it
docker run -d \
  --name simposter \
  -p 8003:8003 \
  -v /path/to/config:/config \
  simposter:latest
```

Both scripts accept an optional tag argument (e.g. `build-docker.bat dev`) if you want to label the image something other than `latest`/`local`.

### Local development (no Docker)

Requires Python 3.x and Node.js `^20.19.0` or `>=22.12.0` (see `frontend/package.json`).

The simplest path — one command, one terminal, both servers with hot-reload:

```bash
cd frontend
npm install
npm run dev:full
```

This runs the backend (`uvicorn` on port 8003) and frontend (Vite dev server) concurrently. The backend half reads a `.env` file from the repo root (`../.env` relative to `frontend/`) — copy [`.env.example`](../.env.example) to `.env` first if you want to pre-fill Plex/API keys; if you skip that, `npm run dev:full` still works, you'll just configure everything through the onboarding wizard/Settings UI instead once the app is running.

Prefer two separate terminals (e.g. to see backend/frontend logs independently)?
```bash
# Terminal 1 — backend (from the repo root)
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8003

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

---

## First Launch: Setup Wizard

The first time you open Simposter with no Plex connection configured, a guided wizard walks you through setup instead of dropping you on a blank Settings page:

1. **Welcome**
2. **Plex** — server URL and token
3. **Libraries** — pick which Plex libraries to manage (movies and/or TV)
4. **API Keys** — TMDb (required), TVDB and Fanart.tv (optional, each has a "Test" button that validates the key live). See [Collections & Posters](COLLECTIONS_AND_POSTERS.md#fanarttv-and-collections) for why a Fanart key specifically matters if you plan to make Collection posters.
5. **Automation** — auto-send to Plex, labels to remove/apply, retry-until-template-met
6. **Performance** — overlay cache, concurrent render workers
7. **Notifications** — Discord webhook and/or Apprise URLs (70+ services)
8. **Finish** — a set of starter presets is imported automatically (a few Uniform Logo looks and Kometa Creator presets, so Template Manager isn't empty on first run) and a library scan kicks off in the background

You can change anything from this wizard later in **Settings** — none of it is one-shot, and Settings → Advanced has a **Run Startup Wizard** button if you want to go through it again (e.g. it was skipped, or you want to redo Plex/library setup). If you skip the wizard or delete a starter preset later, Template Manager's Import/Export section has an **Import Simposter defaults** button to pull the same starter presets back in on demand.

---

## Your First Poster

1. Open **Movies** or **TV Shows** and click a title
2. Pick a template and preset in the editor panel that opens
3. The preview updates live as you switch poster/logo source or adjust sliders
4. **Save to disk** and/or **Send to Plex** when you're happy with it

For batches instead of one at a time, see **Batch Processing** in [COLLECTIONS_AND_POSTERS.md](COLLECTIONS_AND_POSTERS.md).

---

## Settings Reference

| Tab | What's in it |
|-----|--------------|
| **General** | Theme, poster display density, deduplication, default sort, API key management |
| **Libraries** | Plex connection, library mappings, auto-generate preset, webhook ignore labels, per-library default labels to remove, **Kometa Compatibility** (auto-checks "Overlay" for any library added from now on), add/remove libraries (removing purges that library's cache/DB rows, keeping History) |
| **Output** | Save-location path templates (with Kometa-compatible presets, including a `{folder}` variable that matches Radarr/Sonarr's real on-disk folder names) for movies, TV shows, and collections; batch subfolder option; image format/quality |
| **Automation** | Webhook URL generator, automatic poster generation (auto-send, retry queue, existing content mode, webhook secret), **Label to Add After Sending** (optional — tags an item after a poster's sent, so you can filter/smart-collection on what Simposter has touched) |
| **Performance** | Concurrent renders (up to 10 — see the tip below), overlay cache, API rate limits, cache management |
| **Notifications** | Discord webhook and Apprise URLs, per-event toggles (batch / manual / webhook / auto-generate) |
| **Advanced** | **Run Startup Wizard** button, API source priority order, database backup/restore |

> **Tip:** if batch renders feel slow, try raising **Concurrent Rendering** in Performance — it's not capped at a low number the way some tools are. Going from 2 to ~8-9 workers has been measured cutting total batch time by more than half on real libraries, at the cost of each individual item taking a bit longer (worth it for the total time saved). Overlay cache should also stay on; it's the single biggest speed lever for the Uniform Logo template.

---

## Environment Variables

All of these can also be set (and changed later) via the Settings UI or the onboarding wizard — you don't need to set any of them up front.

| Variable | Required | Example |
|----------|----------|---------|
| `PLEX_URL` | Yes | `http://plex:32400` |
| `PLEX_TOKEN` | Yes | `xxxyyyzzz` |
| `PLEX_MOVIE_LIBRARY_NAME` | No | `Movies` |
| `TMDB_API_KEY` | Recommended | `abcd1234` |
| `TVDB_API_KEY` | No | `efgh5678` |
| `FANART_API_KEY` | No | `ijkl9012` |
| `CONFIG_DIR` | No (Docker default: `/config`) | `/config` |

For Docker, set these under `environment:` in `docker-compose.yml`. For local dev, put them in a `.env` file at the repo root (see [`.env.example`](../.env.example)).

---

## File Layout

```
config/
├── settings/
│   └── simposter.db       # SQLite — settings, presets, history, cache
├── logs/
│   └── simposter.log      # Application logs
├── cache/
│   └── poster_renders/    # Cached rendered posters for resend mode
└── output/                # Saved poster files
    └── {Library}/
        └── {Title} ({Year}).jpg
```

Legacy `presets.json` and `ui_settings.json` migrate automatically to SQLite on first run. A database backup is created automatically on version upgrades.
