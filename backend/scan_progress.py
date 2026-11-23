"""One progress bar for a whole library scan (CLAUDE.md Quirk #244).

Every stage of a scan used to overwrite scan_status total/processed with its
own scale, so the bar reset to 0 for each linked Jellyfin/Silo library. This
module is the only writer of those two fields. A scan starts with a total in
work units (every stage's estimated size), each stage takes a `phase()` of that
budget, and `processed` only ever moves forward. A stage whose real size turns
out different from its estimate calls `resize()`.

Units: a Plex movie is 5 (labels + poster/logo/backdrop/square art), a Plex
show, a collection and a Jellyfin/Emby/Silo item are 1 each.

It writes into movies.scan_status, so /api/scan-progress keeps its shape.
Outside a running scan every call is a no-op on the shared status.
"""
import threading
from datetime import datetime, timezone
from typing import Optional

_lock = threading.Lock()


def _status() -> dict:
    from .api.movies import scan_status
    return scan_status


def _running() -> bool:
    return _status().get("state") == "running"


def start(total: int, current: str = "") -> None:
    """A new scan: state running, `total` units, nothing done yet."""
    with _lock:
        _status().update({
            "state": "running", "total": max(0, int(total)), "processed": 0, "current": current,
            "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None, "error": None,
        })


def add_budget(n: int) -> None:
    """Grow (or shrink) the scan's total by `n` units; never below what's done."""
    with _lock:
        if not _running():
            return
        s = _status()
        s["total"] = max(int(s.get("processed") or 0), int(s.get("total") or 0) + int(n))


def set_current(message: str) -> None:
    with _lock:
        if _running():
            _status()["current"] = message


def _advance(n: int, current: Optional[str]) -> None:
    with _lock:
        if not _running():
            return
        s = _status()
        total = int(s.get("total") or 0)
        s["processed"] = min(total, int(s.get("processed") or 0) + max(0, int(n)))
        if current is not None:
            s["current"] = current


def finish_scan(state: str = "done", error: Optional[str] = None) -> None:
    """End the scan. A finished scan shows 100%."""
    with _lock:
        s = _status()
        upd = {"state": state, "finished_at": datetime.now(timezone.utc).isoformat()}
        if state == "done":
            upd["processed"] = int(s.get("total") or 0)
        if error is not None:
            upd["error"] = error
        s.update(upd)


class Phase:
    """One stage's share of the total."""

    def __init__(self, budget: int, label: str = ""):
        self.budget = max(0, int(budget))
        self.done = 0
        self.label = label

    def resize(self, actual: int) -> None:
        """The stage's real size is known: move the scan total by the difference."""
        actual = max(0, int(actual))
        add_budget(actual - self.budget)
        self.budget = actual
        self.done = min(self.done, actual)

    def advance(self, n: int = 1, current: Optional[str] = None) -> None:
        step = max(0, min(int(n), self.budget - self.done))
        self.done += step
        _advance(step, current)

    def finish(self) -> None:
        self.advance(self.budget - self.done)


def phase(budget: int, label: str = "") -> Phase:
    if label:
        set_current(label)
    return Phase(budget, label)
