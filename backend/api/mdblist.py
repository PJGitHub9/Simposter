# backend/api/mdblist.py
"""MDBList key test (Settings → Ratings & Lists). Ratings and lists themselves are
fetched by backend/mdblist_client.py when overlays need them."""
from fastapi import APIRouter

from .. import mdblist_client as mdb

router = APIRouter()


@router.post("/test-mdblist")
def api_test_mdblist(payload: dict):
    """Test an MDBList API key (body, so the key stays out of access logs)."""
    return mdb.test_key(str(payload.get("api_key") or ""))

