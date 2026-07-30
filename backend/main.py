import os
from pathlib import Path

from fastapi import FastAPI
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


# Serve built frontend
frontend_path = Path(FRONTEND_DIR)
if (frontend_path / "index.html").exists():
    # Serve static files (JS, CSS, images)
    if (frontend_path / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")

    # Catch-all route to serve index.html for SPA routing
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve index.html for all non-API routes to support Vue Router."""
        return FileResponse(str(frontend_path / "index.html"))
else:
    # Development mode - mount source directory
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
