# backend/wetrakr_client.py
"""WeTrakr lists (https://api.wetrakr.com, docs inside that site's own app).

Every request sends the app key as the wetrakr-api-key header and
wetrakr-api-version: 1. Public lists need only the key:
  GET /lists/{id}/items/{movies|shows}?page=N&limit=100
Your own lists and tracking lists need a sign-in (device code flow):
  POST /oauth/device/code {client_id}     -> user_code, verification_url, device_code
  POST /oauth/device/token {code, client_id} -> access_token (7 days) + refresh_token
  POST /oauth/token/refresh {refresh_token}
  GET  /sync/lists                         your lists
  GET  /sync/tracking/{status}/{movies|shows}  (planning = watchlist)
Items carry ids.tmdb. Anonymous reads are limited to 1,000 a day per key, which
the list cache keeps us far below.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

import requests

from .config import SECRET_MASK, redact_secrets
from .list_sources import ListSourceError, app_version, save_tokens, ui_settings

API = "https://api.wetrakr.com"
LIST_PREFIX = "https://wetrakr.com/lists/"
STATUSES = {
    "planning": "Watchlist",
    "watching": "Watching",
    "watched": "Watched",
    "hold": "On hold",
    "dropped": "Dropped",
}
_URL_RE = re.compile(r"^(?:https?://)?(?:www\.|api\.)?wetrakr\.com/(?:[^?#]*/)?lists?/(\d+)", re.I)


def _client_id(override: Optional[str] = None) -> str:
    if override and override != SECRET_MASK:
        return override
    return str(ui_settings("wetrakr").get("clientId") or "")


def _auth() -> Dict[str, Any]:
    from . import database as db
    return db.get_list_source_auth("wetrakr")


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------

def normalize(raw: str) -> Optional[str]:
    s = raw.strip()
    if s.lower().startswith("wetrakr:"):
        status = s.split(":", 1)[1].strip().lower()
        if status == "paused":
            status = "hold"
        if status in STATUSES:
            return f"wetrakr:{status}"
        if status.startswith("list:") and status[5:].isdigit():
            return LIST_PREFIX + status[5:]
        return None
    m = _URL_RE.match(s)
    return LIST_PREFIX + m.group(1) if m else None


def owns(key: str) -> bool:
    return key.startswith(LIST_PREFIX) or key.startswith("wetrakr:")


def missing_setup(key: str) -> Optional[str]:
    if not _client_id():
        return "no WeTrakr app key in Settings > General"
    if key.startswith("wetrakr:") and not _auth().get("access_token"):
        return "WeTrakr isn't connected (Settings > General > Connect account)"
    return None


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def _token() -> Optional[str]:
    auth = _auth()
    token = auth.get("access_token")
    if not token:
        return None
    if time.time() > float(auth.get("expires_at") or 0) - 3600 and auth.get("refresh_token"):
        try:
            r = requests.post(f"{API}/oauth/token/refresh", json={"refresh_token": auth["refresh_token"]},
                              headers=_headers(None), timeout=20)
            if r.status_code == 200:
                return save_tokens("wetrakr", r.json()).get("access_token")
        except (requests.RequestException, ValueError):
            pass
    return token


def _headers(token: Optional[str], client_id: Optional[str] = None) -> Dict[str, str]:
    h = {
        "wetrakr-api-key": _client_id(client_id),
        "wetrakr-api-version": "1",
        "Content-Type": "application/json",
        "User-Agent": f"Simposter/{app_version()}",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(path: str, params: Optional[Dict[str, Any]] = None, auth: str = "optional",
         client_id: Optional[str] = None):
    """auth: "none", "optional" (send the token when signed in) or "required"."""
    token = _token() if auth != "none" else None
    if auth == "required" and not token:
        raise ListSourceError("WeTrakr isn't connected")
    if not _client_id(client_id):
        raise ListSourceError("No WeTrakr app key")
    try:
        r = requests.get(f"{API}{path}", params=params, headers=_headers(token, client_id), timeout=20)
    except requests.RequestException as e:
        raise ListSourceError(f"WeTrakr request failed: {redact_secrets(e)}")
    try:
        message = str((r.json() or {}).get("message") or "") if r.status_code >= 400 else ""
    except (ValueError, AttributeError):
        message = ""
    if r.status_code == 400 and "client" in message.lower():
        # What WeTrakr answers for an unknown key, e.g. the client secret pasted by mistake.
        raise ListSourceError("WeTrakr doesn't recognize this Client ID (use the Client ID, not the client secret)")
    if r.status_code == 401:
        if token:
            raise ListSourceError("WeTrakr rejected the sign-in; connect your account again")
        raise ListSourceError("WeTrakr doesn't recognize this Client ID (use the Client ID, not the client secret)")
    if r.status_code == 403:
        raise ListSourceError("That WeTrakr list is private")
    if r.status_code == 404:
        raise ListSourceError("WeTrakr has no such list")
    if r.status_code == 429:
        raise ListSourceError("WeTrakr rate limit reached")
    if not 200 <= r.status_code < 300:
        raise ListSourceError(f"WeTrakr returned HTTP {r.status_code}")
    try:
        return r.json(), r.headers
    except ValueError:
        raise ListSourceError("WeTrakr returned invalid JSON")


def _items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    if isinstance(data, dict):
        for k in ("items", "results", "data"):
            if isinstance(data.get(k), list):
                return [i for i in data[k] if isinstance(i, dict)]
    return []


def _tmdb(item: Dict[str, Any]) -> Optional[int]:
    for source in (item, item.get("movie") or {}, item.get("show") or {}):
        tid = ((source.get("ids") or {}) if isinstance(source, dict) else {}).get("tmdb")
        try:
            return int(tid)
        except (TypeError, ValueError):
            continue
    return None


def _collect(path_for, auth: str) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = {"movie_ids": [], "show_ids": []}
    for target, bucket in (("movies", "movie_ids"), ("shows", "show_ids")):
        for page in range(1, 201):  # 20,000 items per type at most
            data, _headers_ = _get(path_for(target), {"page": page, "limit": 100}, auth=auth)
            items = _items(data)
            for item in items:
                kind = str(item.get("type") or "").lower()
                if kind in ("season", "episode", "person"):
                    continue
                tid = _tmdb(item)
                if tid:
                    out[bucket].append(tid)
            if len(items) < 100:
                break
    return out


def fetch_list(key: str) -> Dict[str, Any]:
    if key.startswith("wetrakr:"):
        status = key.split(":", 1)[1]
        ids = _collect(lambda target: f"/sync/tracking/{status}/{target}", auth="required")
        return {"title": f"WeTrakr {STATUSES.get(status, status)}", **ids}
    list_id = key[len(LIST_PREFIX):]
    title = None
    try:
        meta, _h = _get(f"/lists/{list_id}")
        if isinstance(meta, dict):
            title = meta.get("name")
    except ListSourceError:
        pass
    ids = _collect(lambda target: f"/lists/{list_id}/items/{target}", auth="optional")
    return {"title": title or f"WeTrakr list {list_id}", **ids}


# --------------------------------------------------------------------------
# Your lists, status, test
# --------------------------------------------------------------------------

def can_list_own() -> bool:
    return bool(_client_id() and _auth().get("access_token"))


def my_lists() -> List[Dict[str, Any]]:
    out = [{"key": f"wetrakr:{s}", "title": f"{label} (tracking)", "items": None} for s, label in STATUSES.items()]
    data, _h = _get("/sync/lists", auth="required")
    for lst in _items(data):
        if lst.get("id") is None:
            continue
        out.append({
            "key": f"{LIST_PREFIX}{lst['id']}",
            "title": lst.get("name") or f"List {lst['id']}",
            "items": lst.get("items_count", lst.get("total_items")),
        })
    return out


def status() -> Dict[str, Any]:
    auth = _auth()
    return {
        "configured": bool(_client_id()),
        "connected": bool(auth.get("access_token")),
        "username": auth.get("username"),
    }


def test(payload: Dict[str, Any]) -> Dict[str, Any]:
    client_id = _client_id(str(payload.get("client_id") or ""))
    if not client_id:
        return {"status": "error", "error": "App key required"}
    try:
        _get("/lists/trending", {"limit": 1}, auth="none", client_id=client_id)
    except ListSourceError as e:
        return {"status": "error", "error": str(e)}
    return {"status": "ok", "message": "App key valid"}


# --------------------------------------------------------------------------
# Sign-in
# --------------------------------------------------------------------------

def start_device() -> Dict[str, Any]:
    client_id = _client_id()
    if not client_id:
        raise ListSourceError("Save your WeTrakr app key first")
    try:
        r = requests.post(f"{API}/oauth/device/code", json={"client_id": client_id}, headers=_headers(None), timeout=20)
    except requests.RequestException as e:
        raise ListSourceError(f"WeTrakr request failed: {redact_secrets(e)}")
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200:
        raise ListSourceError(data.get("message") or f"WeTrakr returned HTTP {r.status_code}")
    url = data.get("verification_url") or "https://wetrakr.com/activate"
    return {
        "device_code": data.get("device_code"),
        "user_code": data.get("user_code"),
        "verification_url": url,
        "verification_url_complete": None,
        "interval": data.get("interval") or 5,
        "expires_in": data.get("expires_in") or 600,
    }


def poll_device(device_code: str) -> Dict[str, Any]:
    try:
        r = requests.post(f"{API}/oauth/device/token", json={"code": device_code, "client_id": _client_id()},
                          headers=_headers(None), timeout=20)
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return {"status": "pending", "message": redact_secrets(e)}
    if r.status_code == 200 and data.get("access_token"):
        extra: Dict[str, Any] = {}
        save_tokens("wetrakr", data)
        try:
            account, _h = _get("/account/settings", auth="required")
            user = (account or {}).get("user") or account or {}
            extra["username"] = user.get("display_name") or user.get("username")
        except ListSourceError:
            pass
        if extra:
            save_tokens("wetrakr", data, extra)
        return {"status": "connected", "username": extra.get("username")}
    err = str(data.get("error") or "")
    if err in ("authorization_pending", "slow_down") or (r.status_code == 400 and not err):
        return {"status": "pending"}
    if err in ("expired_token",):
        return {"status": "expired", "error": "The code expired. Start again."}
    if err in ("access_denied",):
        return {"status": "error", "error": "The sign-in was declined on WeTrakr."}
    return {"status": "error", "error": data.get("message") or err or f"WeTrakr returned HTTP {r.status_code}"}
