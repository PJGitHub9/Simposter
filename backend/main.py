import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api import router as api_router
from .config import FRONTEND_DIR


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
