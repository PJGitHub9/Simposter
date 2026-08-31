# Contributing to Simposter

Thanks for considering a contribution! Simposter is a small, mostly solo-maintained project, so contributions of any size — bug fixes, features, docs — are genuinely appreciated.

## Before you start

- **Bug fixes / small changes** — feel free to open a PR directly.
- **New features / larger changes** — please open an issue first (use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.yml)) so we can talk through the approach before you put time into it.

## Development setup

```bash
# Backend
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8003

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Or `cd frontend && npm install && npm run dev:full` to run both concurrently in one terminal.

See [Getting Started](docs/GETTING_STARTED.md#local-development-no-docker) for the full local dev setup, and [ARCHITECTURE.md](ARCHITECTURE.md) for how the backend, frontend, and rendering pipeline fit together.

## Before opening a PR

- **Type-check the frontend**: `cd frontend && npx vue-tsc --noEmit`
- **Build the frontend**: `cd frontend && npx vite build`
- **Import-check the backend**: `python -c "import backend.main"`
- **Actually test the feature** — preview, save, and (if relevant) send-to-Plex — not just that the code compiles or type-checks

## Versioning a change

If your change is user-facing (a fix or a feature — not a docs-only or pure-refactor change), bump the version alongside it:

1. Bump `frontend/src/version.ts`
2. Add an entry to `CHANGELOG.md` — technical detail: what broke/changed, why, and how it was fixed
3. Add a matching entry to `frontend/src/releaseNotes.ts` — user-facing, shown in the app's changelog modal, keep it short and non-technical

Keep each version bump to one logical change. It's easier to review, and easier to revert if something turns out to be wrong.

## Code conventions

- Match the existing style in the file you're editing over introducing a new pattern.
- Any new endpoint that fetches a user-supplied URL server-side must go through the existing SSRF guards in `backend/middleware/validation.py` — don't write a new ad-hoc `requests.get(user_url)`.
- Any new credential/API-key field needs to be added to `SECRET_FIELD_PATHS` in `backend/config.py`, or it'll be returned in plaintext by settings endpoints and included in database exports.
- Final-output JPEG encodes (posters/logos actually sent to Plex or saved to disk) must set `subsampling=0` — Pillow's default 4:2:0 chroma subsampling produces visible color bleeding around saturated edges like clearlogos and badges.
- Simposter has no login/API-key gate in front of its API by design (self-hosted, trusted-network model) — don't add auth-adjacent code without discussing it in an issue first.

## Reporting bugs / requesting features

Use the issue templates — they ask for the details (version, deployment method, logs) that make bugs much faster to track down.
