import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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


# Serve built frontend (includes index.html + assets)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
