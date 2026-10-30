# backend/simkl_client.py
"""SIMKL lists (https://api.simkl.org, OpenAPI at api.simkl.org/openapi.json).

Every request carries ?client_id=...&app-name=simposter&app-version=... and a
User-Agent. Every list read needs a signed-in user (AUTH V2 device flow; the
app must be registered as "TV, devices & command line", which has no secret):
  POST /oauth2/device {client_id, scope}            -> user_code, verification_uri(_complete), device_code
  POST /oauth2/token  {grant_type=device_code|refresh_token, client_id, ...}
  GET  /sync/all-items/all/{status}                 watchlist buckets (free accounts)
  GET  /lists/{id}?page=N&limit=50                  custom lists (PRO/VIP only; a free
                                                    account gets 200 {"error": "premium_only"})
  GET  /lists/user/{userId}                         your custom lists
  GET  /users/settings                              your user id and name

SIMKL suspends apps that download whole libraries on a timer, so before
re-fetching a watchlist bucket we ask GET /sync/activities and reuse the cached
copy when nothing changed since the last download.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

import requests

from .config import SECRET_MASK, redact_secrets
from .list_sources import ListSourceError, app_version, save_tokens, ui_settings

API = "https://api.simkl.com"
LIST_PREFIX = "https://simkl.com/lists/"
STATUSES = {
    "plantowatch": "Plan to Watch",
    "watching": "Watching",
    "completed": "Completed",
    "hold": "On Hold",
    "dropped": "Dropped",
}
_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?simkl\.com/(?:[^?#]*/)?lists?/(\d+)", re.I)
_PREMIUM_MSG = "SIMKL custom lists need a SIMKL PRO or VIP account"
_V2_HELP = ("SIMKL doesn't accept this client ID for sign-in. It needs the Client ID of a new (AUTH V2) app "
            "registered as \"TV, devices & command line\" at simkl.com/settings/developer. Older apps' IDs "
            "and client secrets don't work.")


def _client_id(override: Optional[str] = None) -> str:
    if override and override != SECRET_MASK:
        return override
    return str(ui_settings("simkl").get("clientId") or "")


def _auth() -> Dict[str, Any]:
    from . import database as db
    return db.get_list_source_auth("simkl")


def normalize(raw: str) -> Optional[str]:
    s = raw.strip()
    if s.lower().startswith("simkl:"):
        status = s.split(":", 1)[1].strip().lower().replace(" ", "")
        if status in ("watchlist", "plan_to_watch"):
            status = "plantowatch"
        if status in STATUSES:
            return f"simkl:{status}"
        if status.startswith("list:") and status[5:].isdigit():
            return LIST_PREFIX + status[5:]
        return None
    m = _URL_RE.match(s)
    return LIST_PREFIX + m.group(1) if m else None


def owns(key: str) -> bool:
    return key.startswith(LIST_PREFIX) or key.startswith("simkl:")


def missing_setup(key: str) -> Optional[str]:
    if not _client_id():
        return "no SIMKL client id in Settings > General"
    if not _auth().get("access_token"):
        return "SIMKL isn't connected (Settings > General > Connect account)"
    return None


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def _params(extra: Optional[Dict[str, Any]] = None, client_id: Optional[str] = None) -> Dict[str, Any]:
    return {"client_id": _client_id(client_id), "app-name": "simposter", "app-version": app_version(), **(extra or {})}


def _ua() -> Dict[str, str]:
    return {"User-Agent": f"Simposter/{app_version()}"}


def _token_request(body: Dict[str, Any]) -> requests.Response:
    return requests.post(f"{API}/oauth2/token", json=body, headers={**_ua(), "Content-Type": "application/json"}, timeout=20)


def _token() -> Optional[str]:
    auth = _auth()
    token = auth.get("access_token")
    if not token:
        return None
    if time.time() > float(auth.get("expires_at") or 0) - 3600 and auth.get("refresh_token"):
        try:
            r = _token_request({"grant_type": "refresh_token", "client_id": _client_id(),
                                "refresh_token": auth["refresh_token"]})
            if r.status_code == 200:
                return save_tokens("simkl", r.json()).get("access_token")
        except (requests.RequestException, ValueError):
            pass
    return token


def _get(path: str, params: Optional[Dict[str, Any]] = None, signed_in: bool = True,
         client_id: Optional[str] = None) -> Any:
    if not _client_id(client_id):
        raise ListSourceError("No SIMKL client id")
    headers = _ua()
    if signed_in:
        token = _token()
        if not token:
            raise ListSourceError("SIMKL isn't connected")
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(f"{API}{path}", params=_params(params, client_id), headers=headers, timeout=30)
    except requests.RequestException as e:
        raise ListSourceError(f"SIMKL request failed: {redact_secrets(e)}")
    if r.status_code == 412:
        raise ListSourceError("SIMKL doesn't recognize this client ID")
    if r.status_code == 401:
        raise ListSourceError("SIMKL rejected the sign-in; connect your account again")
    if r.status_code == 404:
        raise ListSourceError("SIMKL has no such list")
    if r.status_code == 429:
        raise ListSourceError("SIMKL rate limit reached")
    if not 200 <= r.status_code < 300:
        raise ListSourceError(f"SIMKL returned HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError:
        raise ListSourceError("SIMKL returned invalid JSON")
    if isinstance(data, dict) and data.get("error") == "premium_only":
        raise ListSourceError(_PREMIUM_MSG)
    return data


def _tmdb(item: Dict[str, Any]) -> Optional[int]:
    for source in (item, item.get("movie") or {}, item.get("show") or {}):
        tid = (source.get("ids") or {}).get("tmdb") if isinstance(source, dict) else None
        try:
            return int(tid)
        except (TypeError, ValueError):
            continue
    return None


def _is_movie(item: Dict[str, Any], bucket: str) -> bool:
    if bucket == "movies" or "movie" in item:
        return True
    kind = str(item.get("type") or (item.get("show") or {}).get("anime_type") or item.get("anime_type") or "").lower()
    return kind == "movie"


def _split(items_by_bucket: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = {"movie_ids": [], "show_ids": []}
    for bucket, items in items_by_bucket.items():
        for item in items or []:
            if not isinstance(item, dict):
                continue
            tid = _tmdb(item)
            if tid:
                out["movie_ids" if _is_movie(item, bucket) else "show_ids"].append(tid)
    return out


# --------------------------------------------------------------------------
# Lists
# --------------------------------------------------------------------------

def _activities_stamp() -> Optional[str]:
    try:
        data = _get("/sync/activities")
    except ListSourceError:
        return None
    return str(data.get("all")) if isinstance(data, dict) and data.get("all") else None


def fetch_list(key: str) -> Dict[str, Any]:
    from . import database as db
    if key.startswith("simkl:"):
        status = key.split(":", 1)[1]
        auth = _auth()
        stamp = _activities_stamp()
        cached = db.get_list_cache(key)
        stamps = auth.get("activity_stamps") or {}
        if stamp and cached and stamps.get(key) == stamp:
            # Nothing changed on SIMKL since the last download: keep it.
            return {"title": cached.get("title"), "movie_ids": cached["movie_ids"], "show_ids": cached["show_ids"]}
        data = _get(f"/sync/all-items/all/{status}")
        data = data if isinstance(data, dict) else {}
        ids = _split({"movies": data.get("movies"), "shows": data.get("shows"), "anime": data.get("anime")})
        if stamp:
            current = db.get_list_source_auth("simkl")
            current["activity_stamps"] = {**(current.get("activity_stamps") or {}), key: stamp}
            db.save_list_source_auth("simkl", current)
        return {"title": f"SIMKL {STATUSES.get(status, status)}", **ids}
    list_id = key[len(LIST_PREFIX):]
    title = None
    items: List[Dict[str, Any]] = []
    for page in range(1, 201):
        data = _get(f"/lists/{list_id}", {"page": page, "limit": 50})
        if not isinstance(data, dict):
            break
        title = title or data.get("name")
        page_items = [i for i in (data.get("items") or []) if isinstance(i, dict)]
        items.extend(page_items)
        pages = (data.get("pagination") or {}).get("total_pages") or 1
        if page >= int(pages) or not page_items:
            break
    return {"title": title or f"SIMKL list {list_id}", **_split({"list": items})}


def can_list_own() -> bool:
    return bool(_client_id() and _auth().get("access_token"))


def my_lists() -> List[Dict[str, Any]]:
    out = [{"key": f"simkl:{s}", "title": label, "items": None} for s, label in STATUSES.items()]
    user_id = _auth().get("user_id")
    if user_id:
        try:
            data = _get(f"/lists/user/{user_id}", {"limit": 100})
            for lst in (data.get("lists") or []) if isinstance(data, dict) else []:
                if isinstance(lst, dict) and lst.get("id") is not None:
                    out.append({
                        "key": f"{LIST_PREFIX}{lst['id']}",
                        "title": lst.get("name") or f"List {lst['id']}",
                        "items": (lst.get("counts") or {}).get("items"),
                    })
        except ListSourceError as e:
            if str(e) != _PREMIUM_MSG:
                raise
    return out


def status() -> Dict[str, Any]:
    auth = _auth()
    return {
        "configured": bool(_client_id()),
        "connected": bool(auth.get("access_token")),
        "username": auth.get("username"),
    }


def test(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Checks the client id against SIMKL's sign-in endpoint (POST /oauth2/device),
    the only endpoint that tells a usable AUTH V2 id from a wrong one: catalog
    endpoints answer a V2 id without checking it, and user endpoints refuse a
    bare V2 id. The device code it creates is simply left to expire."""
    client_id = _client_id(str(payload.get("client_id") or ""))
    if not client_id:
        return {"status": "error", "error": "Client ID required"}
    try:
        r = requests.post(f"{API}/oauth2/device", json={"client_id": client_id, "scope": "media:read"},
                          headers={**_ua(), "Content-Type": "application/json"}, timeout=20)
        data = r.json() if r.content else {}
    except (requests.RequestException, ValueError) as e:
        return {"status": "error", "error": f"SIMKL request failed: {redact_secrets(e)}"}
    if r.status_code == 200 and data.get("device_code"):
        return {"status": "ok", "message": "Client ID works. Save, then Connect account."}
    if r.status_code in (400, 401) and data.get("error") in ("invalid_client", "unauthorized_client"):
        return {"status": "error", "error": _V2_HELP}
    return {"status": "error", "error": data.get("error_description") or data.get("message") or f"SIMKL returned HTTP {r.status_code}"}


# --------------------------------------------------------------------------
# Sign-in (AUTH V2 device flow)
# --------------------------------------------------------------------------

def start_device() -> Dict[str, Any]:
    client_id = _client_id()
    if not client_id:
        raise ListSourceError("Save your SIMKL client id first")
    try:
        r = requests.post(f"{API}/oauth2/device", json={"client_id": client_id, "scope": "media:read"},
                          headers={**_ua(), "Content-Type": "application/json"}, timeout=20)
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        raise ListSourceError(f"SIMKL request failed: {redact_secrets(e)}")
    if r.status_code != 200:
        err = data.get("error") if isinstance(data, dict) else None
        if err in ("invalid_client", "unauthorized_client"):
            raise ListSourceError(_V2_HELP)
        raise ListSourceError((data or {}).get("error_description") or err or f"SIMKL returned HTTP {r.status_code}")
    return {
        "device_code": data.get("device_code"),
        "user_code": data.get("user_code"),
        "verification_url": data.get("verification_uri") or "https://simkl.com/pin",
        "verification_url_complete": data.get("verification_uri_complete"),
        "interval": data.get("interval") or 5,
        "expires_in": data.get("expires_in") or 900,
    }


def poll_device(device_code: str) -> Dict[str, Any]:
    try:
        r = _token_request({"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                            "device_code": device_code, "client_id": _client_id()})
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return {"status": "pending", "message": redact_secrets(e)}
    if r.status_code == 200 and data.get("access_token"):
        save_tokens("simkl", data)
        extra: Dict[str, Any] = {}
        try:
            account = _get("/users/settings")
            user = (account or {}).get("user") or {}
            acct = (account or {}).get("account") or {}
            extra = {"username": user.get("name"), "user_id": acct.get("id")}
        except ListSourceError:
            pass
        if extra:
            save_tokens("simkl", data, extra)
        return {"status": "connected", "username": extra.get("username")}
    err = str(data.get("error") or "")
    if err in ("authorization_pending", "slow_down"):
        return {"status": "pending"}
    if err == "expired_token":
        return {"status": "expired", "error": "The code expired. Start again."}
    if err == "access_denied":
        return {"status": "error", "error": "The sign-in was declined on SIMKL."}
    return {"status": "error", "error": data.get("error_description") or err or f"SIMKL returned HTTP {r.status_code}"}
