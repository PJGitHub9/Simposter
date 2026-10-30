# backend/api/list_sources.py
"""List sources for overlay "On a list" rules: WeTrakr, SIMKL and Floppy key
tests and sign-ins, your lists for the editor's picker, and looking up a pasted
list link. The logic lives in backend/list_sources.py and the *_client modules."""
from fastapi import APIRouter, HTTPException

from .. import database as db
from .. import list_sources as ls
from ..config import redact_secrets

router = APIRouter()

_PROVIDERS = ("wetrakr", "simkl", "floppy")


def _module(provider: str):
    if provider not in _PROVIDERS:
        raise HTTPException(404, "Unknown list service")
    return ls._providers()[provider]


@router.get("/list-sources/status")
def api_list_sources_status():
    return ls.status()


@router.post("/list-sources/{provider}/test")
def api_list_source_test(provider: str, payload: dict):
    """Test a key (body, so it stays out of access logs). The masked placeholder
    means "the saved value"."""
    return _module(provider).test(payload or {})


@router.post("/list-sources/{provider}/connect")
def api_list_source_connect(provider: str):
    """Start the "approve this code" sign-in."""
    _module(provider)
    try:
        return ls.start_connect(provider)
    except ls.ListSourceError as e:
        raise HTTPException(400, redact_secrets(e))


@router.post("/list-sources/{provider}/connect/poll")
def api_list_source_connect_poll(provider: str):
    _module(provider)
    return ls.poll_connect(provider)


@router.delete("/list-sources/{provider}/connect")
def api_list_source_disconnect(provider: str):
    _module(provider)
    ls.disconnect(provider)
    return {"status": "disconnected"}


@router.get("/list-sources/my-lists")
def api_list_sources_my_lists(refresh: bool = False):
    """Your lists on every connected service, plus every list already cached
    (so a list pasted earlier keeps its name in the picker)."""
    data = ls.my_lists(force=refresh)
    known = {item["key"] for item in data["lists"]}
    cached = []
    for row in db.get_all_list_cache():
        if row["url"] in known:
            continue
        cached.append({"key": row["url"], "title": row["title"], "provider": ls.provider_of(row["url"]),
                       "items": row["movies"] + row["shows"]})
    return {"lists": data["lists"], "cached": cached, "errors": data["errors"]}


@router.post("/list-sources/resolve")
def api_list_source_resolve(payload: dict):
    """Look up a pasted list link: which service, its name and size. Fetches it
    now so the first render doesn't have to."""
    key = ls.normalize_list_key(str((payload or {}).get("url") or ""))
    if not key:
        raise HTTPException(400, "Not a list link Simposter recognizes (MDBList, WeTrakr, SIMKL or Floppy)")
    provider = ls.provider_of(key)
    reason = ls.missing_setup(key)
    if reason:
        return {"key": key, "provider": provider, "title": None, "error": reason}
    try:
        data = ls.get_list(key, force=True)
    except ls.ListSourceError as e:
        return {"key": key, "provider": provider, "title": None, "error": str(e)}
    if not data:
        return {"key": key, "provider": provider, "title": None, "error": "Couldn't read that list"}
    return {"key": key, "provider": provider, "title": data.get("title"),
            "movies": len(data["movie_ids"]), "shows": len(data["show_ids"])}
