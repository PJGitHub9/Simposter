import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api import router as api_router
from .config import FRONTEND_DIR
from .middleware.rate_limit import RateLimitMiddleware
from .scheduler import init_scheduler, shutdown_scheduler


app = FastAPI()

# Initialize the background scheduler on startup
@app.on_event("startup")
async def startup_event():
    init_scheduler()
    # Pre-warm simposter asset cache so the first render doesn't block on a
    # synchronous GitHub HTTP fetch.
    import threading
    from .simposter_assets import _fetch_logos
    threading.Thread(target=_fetch_logos, daemon=True, name="simposter-assets-prewarm").start()
    # Overlay effect caches for every preset (series and season settings), so the
    # first batch render of a preset is already fast.
    from .overlay_cache import warm_all
    threading.Thread(target=warm_all, daemon=True, name="overlay-cache-warm").start()
    # Shrink image caches written before cached images were stored downscaled (once).
    from .cache_images import start_shrink_existing
    start_shrink_existing()
    # Once: logo/backdrop drift fingerprints that ignore the colour under transparent pixels.
    from .poster_drift import recheck_art_fingerprints
    threading.Thread(target=recheck_art_fingerprints, daemon=True, name="drift-fp-recheck").start()
    # Overlay Refresh no longer tracks posters sent without overlays; drop old ones.
    from .overlay_refresh import prune_without_overlays
    threading.Thread(target=prune_without_overlays, daemon=True, name="overlay-refresh-prune").start()

# Shutdown the scheduler gracefully
@app.on_event("shutdown")
async def shutdown_event():
    shutdown_scheduler()

# Rate limiting: per-IP, per-endpoint sliding window (see middleware/rate_limit.py for
# the per-endpoint limits, e.g. batch render: 5/min, webhooks: 10/min). Sits in front of
# CORS so it also throttles unauthenticated/cross-origin abuse.
app.add_middleware(
    RateLimitMiddleware,
    default_limit=300,  # 300 requests per minute for endpoints without a specific limit
    window_seconds=60
)

# allow_credentials=False: this API does not use cookies/session auth, so there is no
# credential for a malicious origin to ride along with. Wildcard origins + credentials
# is a dangerous combination (browsers would let any site make authenticated requests on
# a user's behalf); disabling credentials here removes that risk even though wildcard
# origins remain, which is required for the Vite dev server (different port) to reach
# the API directly (see frontend/src/services/apiBase.ts).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


# Root alias for the public Poster API. Registered BEFORE the SPA catch-all below so
# the catch-all (which would return index.html) never sees it. Exact path only:
# /poster-api is a Vue route and must still fall through to the SPA.
@app.get("/poster")
def root_poster(request: Request, tmdb_id: Optional[int] = None, type: Optional[str] = None,
                season: Optional[int] = None, preset: Optional[str] = None):
    from .api.poster_api import handle_poster_request
    return handle_poster_request(request, tmdb_id, type, season, preset)


# Serve built frontend
frontend_path = Path(FRONTEND_DIR)
if (frontend_path / "index.html").exists():
    # Serve static files (JS, CSS, images)
    if (frontend_path / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")

    # Catch-all route to serve index.html for SPA routing. Only /assets is mounted as
    # StaticFiles above -- everything else under frontend_path (favicon.svg, favicon.ico,
    # and anything else dropped in frontend/public/) was previously swallowed by this
    # route unconditionally returning index.html, so those files 404'd in effect (got
    # index.html's HTML bytes back with the wrong content-type instead of the real file)
    # in the built/Docker app, while working fine against the Vite dev server locally
    # (which serves frontend/public/* directly, never reaching this backend route at all).
    frontend_path_resolved = frontend_path.resolve()

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve a real static file under frontend_path if one exists at this path
        (e.g. favicon.svg); otherwise fall back to index.html for Vue Router."""
        candidate = (frontend_path / full_path).resolve()
        try:
            candidate.relative_to(frontend_path_resolved)
        except ValueError:
            # Path traversal attempt (e.g. ../../etc/passwd) -- never serve outside frontend_path
            return FileResponse(str(frontend_path / "index.html"))
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(frontend_path / "index.html"))
else:
    # Development mode - mount source directory
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
