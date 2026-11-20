"""Sign in with Plex: get a Plex server URL and token through plex.tv instead
of pasting them.

Flow (Plex's PIN sign-in, the same one Overseerr and Tautulli use; checked
against a real PIN request and Overseerr's source, 2026-11-19):

1. POST /api/plex-auth/pin creates a PIN at plex.tv and returns the
   app.plex.tv sign-in URL for the browser to open in a popup.
2. The browser polls GET /api/plex-auth/pin/{id}; once the user has signed
   in, plex.tv puts the account token on the PIN.
3. GET /api/plex-auth/pin/{id}/servers lists the account's servers from
   plex.tv's resources list, and Simposter's server tests each connection
   (Simposter has to reach Plex, not the browser).
4. POST /api/plex-auth/pin/{id}/use returns the chosen server's address and
   its own access token, which fill the Plex URL/token fields; they're saved
   with the page's normal Save.

The account token is kept in memory for PIN_TTL_SECONDS and never returned or
logged. Only the chosen server's own token leaves this module.
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import logger, settings

router = APIRouter(prefix="/plex-auth", tags=["plex-auth"])

PLEX_TV = "https://plex.tv/api/v2"
AUTH_APP_URL = "https://app.plex.tv/auth/#!?"
PRODUCT = "Simposter"
PIN_TTL_SECONDS = 15 * 60
_CONNECT_TIMEOUT = 4

_pins: dict[int, dict[str, Any]] = {}
_lock = threading.Lock()


def _client_id() -> str:
    """A stable id for this Simposter install, so plex.tv lists it as one
    device under Authorized Devices. Kept in a file (the settings table is
    rebuilt on every Settings save)."""
    path = Path(settings.CONFIG_DIR) / "settings" / "plex_client_id"
    try:
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    value = f"simposter-{uuid.uuid4().hex}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    except OSError as e:
        logger.debug("[PLEX_AUTH] Couldn't save the client id: %s", e)
    return value


def _headers(token: Optional[str] = None) -> dict[str, str]:
    h = {
        "Accept": "application/json",
        "X-Plex-Product": PRODUCT,
        "X-Plex-Client-Identifier": _client_id(),
        "X-Plex-Device-Name": PRODUCT,
        "X-Plex-Platform": "Web",
    }
    if token:
        h["X-Plex-Token"] = token
    return h


def _prune() -> None:
    now = time.time()
    with _lock:
        for pin_id in [k for k, v in _pins.items() if now - v["created"] > PIN_TTL_SECONDS]:
            _pins.pop(pin_id, None)


def _get_pin(pin_id: int) -> dict[str, Any]:
    _prune()
    with _lock:
        entry = _pins.get(pin_id)
    if entry is None:
        raise HTTPException(404, "This sign-in has expired. Start again.")
    return entry


def _truthy(value: Any) -> bool:
    return value is True or str(value).lower() in ("1", "true")


@router.post("/pin")
def api_create_pin():
    try:
        r = requests.post(f"{PLEX_TV}/pins", params={"strong": "true"}, headers=_headers(), timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning("[PLEX_AUTH] Couldn't start a Plex sign-in: %s", e)
        raise HTTPException(502, "Couldn't reach plex.tv. Check Simposter's internet connection and try again.")
    pin_id, code = data.get("id"), data.get("code")
    if not pin_id or not code:
        raise HTTPException(502, "plex.tv sent an unexpected answer. Try again.")
    with _lock:
        _pins[int(pin_id)] = {"code": code, "created": time.time(), "account_token": None, "servers": None}
    query = urlencode({
        "clientID": _client_id(),
        "code": code,
        "context[device][product]": PRODUCT,
    })
    return {"id": pin_id, "auth_url": AUTH_APP_URL + query, "expires_in": data.get("expiresIn")}


@router.get("/pin/{pin_id}")
def api_check_pin(pin_id: int):
    """"pending" until the user has signed in, then "authorized"."""
    entry = _get_pin(pin_id)
    if entry["account_token"]:
        return {"status": "authorized"}
    try:
        r = requests.get(f"{PLEX_TV}/pins/{pin_id}", params={"code": entry["code"]}, headers=_headers(), timeout=10)
        if r.status_code == 404:
            with _lock:
                _pins.pop(pin_id, None)
            return {"status": "expired"}
        r.raise_for_status()
        token = r.json().get("authToken")
    except Exception as e:
        logger.debug("[PLEX_AUTH] PIN check failed: %s", e)
        return {"status": "pending"}
    if token:
        with _lock:
            entry["account_token"] = token
        logger.info("[PLEX_AUTH] Plex sign-in completed")
        return {"status": "authorized"}
    return {"status": "pending"}


def _reachable(uri: str, token: str) -> bool:
    try:
        r = requests.get(f"{uri.rstrip('/')}/identity", headers=_headers(token),
                         timeout=_CONNECT_TIMEOUT, allow_redirects=False)
        return r.status_code == 200
    except Exception:
        return False


def _connection_label(c: dict) -> str:
    if c["relay"]:
        return "Relay (through plex.tv, slow)"
    return "Local" if c["local"] else "Remote"


def _load_servers(entry: dict[str, Any]) -> list[dict[str, Any]]:
    r = requests.get(f"{PLEX_TV}/resources", params={"includeHttps": 1, "includeRelay": 1},
                     headers=_headers(entry["account_token"]), timeout=15)
    r.raise_for_status()
    servers = []
    for res in r.json() or []:
        provides = res.get("provides") or ""
        if "server" not in (provides if isinstance(provides, list) else str(provides).split(",")):
            continue
        token = res.get("accessToken")
        if not token:
            continue
        conns = []
        for c in res.get("connections") or []:
            uri = c.get("uri")
            if uri:
                conns.append({"uri": uri, "local": _truthy(c.get("local")), "relay": _truthy(c.get("relay"))})
        servers.append({
            "id": res.get("clientIdentifier") or res.get("name") or "plex",
            "name": res.get("name") or "Plex",
            "owned": _truthy(res.get("owned")),
            "token": token,
            "connections": conns,
        })
    # Test every connection at once; each has a short timeout.
    jobs = [(s, c) for s in servers for c in s["connections"]]
    if jobs:
        with ThreadPoolExecutor(max_workers=min(16, len(jobs))) as pool:
            results = list(pool.map(lambda sc: _reachable(sc[1]["uri"], sc[0]["token"]), jobs))
        for (s, c), ok in zip(jobs, results):
            c["reachable"] = ok
    for s in servers:
        # Best first: reachable, then local, then not relay, then https.
        s["connections"].sort(key=lambda c: (not c.get("reachable"), not c["local"], c["relay"], not c["uri"].startswith("https")))
    servers.sort(key=lambda s: (not s["owned"], s["name"].lower()))
    return servers


@router.get("/pin/{pin_id}/servers")
def api_list_servers(pin_id: int, refresh: bool = False):
    entry = _get_pin(pin_id)
    if not entry["account_token"]:
        raise HTTPException(409, "Sign in to Plex first.")
    if entry["servers"] is None or refresh:
        try:
            servers = _load_servers(entry)
        except Exception as e:
            logger.warning("[PLEX_AUTH] Couldn't list Plex servers: %s", e)
            raise HTTPException(502, "Couldn't get your servers from plex.tv. Try again.")
        with _lock:
            entry["servers"] = servers
    return {"servers": [
        {
            "id": s["id"],
            "name": s["name"],
            "owned": s["owned"],
            "connections": [
                {"uri": c["uri"], "label": _connection_label(c), "reachable": bool(c.get("reachable"))}
                for c in s["connections"]
            ],
        }
        for s in entry["servers"] or []
    ]}


class PlexAuthUseRequest(BaseModel):
    server_id: str
    uri: str


@router.post("/pin/{pin_id}/use")
def api_use_server(pin_id: int, req: PlexAuthUseRequest):
    entry = _get_pin(pin_id)
    server = next((s for s in entry.get("servers") or [] if s["id"] == req.server_id), None)
    if server is None:
        raise HTTPException(404, "That server isn't in your Plex account's list.")
    if not any(c["uri"].rstrip("/") == req.uri.rstrip("/") for c in server["connections"]):
        raise HTTPException(400, "That address isn't one of this server's connections.")
    with _lock:
        _pins.pop(pin_id, None)
    return {"url": req.uri.rstrip("/"), "token": server["token"], "name": server["name"]}
