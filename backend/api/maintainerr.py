# backend/api/maintainerr.py
"""Maintainerr connection: Test button and the collection names the overlay
editor offers for the "Maintainerr collection" rule."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/maintainerr/test")
def api_maintainerr_test(payload: dict):
    from .. import maintainerr_client
    result = maintainerr_client.test(payload or {})
    try:
        from .. import maintainerr_data
        maintainerr_data.clear()
    except ImportError:
        pass
    return result


@router.get("/maintainerr/collections")
def api_maintainerr_collections():
    try:
        from .. import maintainerr_data
        return {"collections": maintainerr_data.collection_names()}
    except ImportError:
        return {"collections": []}
