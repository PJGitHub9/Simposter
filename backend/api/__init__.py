from fastapi import APIRouter

from . import (
    presets,
    templates,
    movies,
    tv_shows,
    plexsend,
    preview,
    save,
    batch,
    uploads,
    logs,
    # webhooks module removed (Radarr/Tautulli integrations deprecated)
    ui_settings,
    history,
    template_manager,
    cache as cache_api,
    test_api_keys,
    scheduler,
    database,
)

router = APIRouter()

router.include_router(presets.router)
router.include_router(templates.router)
router.include_router(movies.router)
router.include_router(tv_shows.router)
router.include_router(plexsend.router)
router.include_router(preview.router)
router.include_router(save.router)
router.include_router(batch.router)
router.include_router(uploads.router)
router.include_router(logs.router)
router.include_router(ui_settings.router)
router.include_router(history.router)
router.include_router(template_manager.router)
router.include_router(cache_api.router)
router.include_router(test_api_keys.router)
router.include_router(scheduler.router)
router.include_router(database.router)
