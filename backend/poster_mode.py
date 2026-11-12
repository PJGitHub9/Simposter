"""Poster modes: per library group and title, who makes the poster.

full: Simposter makes it. overlay_only: Simposter adds overlays to a clean
copy. leave_alone: Simposter does not touch it. Effective mode = manual, else
rule, else full. A title is keyed by TMDb id (movies) or TVDB-else-TMDb id
(shows); a title with no id is always full.
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from . import database as db

logger = logging.getLogger("simposter")

MODES = ("full", "overlay_only", "leave_alone")


def group_id_for(server_id: str, library_id: str, media_type: str) -> str:
    """The LibraryGroup holding this (server, library); else a pseudo id.
    An ungrouped Plex library uses the id the Settings page backfill gives it."""
    from . import config
    group = config.get_library_group_for(server_id, str(library_id), media_type)
    if group and group.get("id"):
        return str(group["id"])
    if server_id == "plex-1":
        return f"group-{media_type}-{library_id}"
    return f"lib:{server_id}:{library_id}"


def _s(v) -> Optional[str]:
    if v is None or str(v).strip() == "":
        return None
    return str(v).strip()


def item_key(media_type: str, tmdb_id, tvdb_id) -> Optional[Tuple[str, str]]:
    tmdb, tvdb = _s(tmdb_id), _s(tvdb_id)
    if media_type == "movie":
        return ("tmdb", tmdb) if tmdb else None
    if tvdb:
        return ("tvdb", tvdb)
    if tmdb:
        return ("tmdb", tmdb)
    return None


def _eff(row) -> Tuple[str, str]:
    if row is None:
        return ("full", "")
    if row["manual_mode"]:
        return (row["manual_mode"], "manual")
    if row["rule_mode"]:
        return (row["rule_mode"], row["rule_reason"] or "")
    return ("full", "")


_WHERE = "group_id=? AND media_type=? AND id_type=? AND item_id=?"


def _row(conn, group_id, media_type, key):
    return conn.execute(f"SELECT * FROM poster_modes WHERE {_WHERE}",
                        (group_id, media_type, key[0], key[1])).fetchone()


def effective(group_id: str, media_type: str, tmdb_id=None, tvdb_id=None) -> Tuple[str, str]:
    key = item_key(media_type, tmdb_id, tvdb_id)
    if not key:
        return ("full", "")
    with db.get_db() as conn:
        return _eff(_row(conn, group_id, media_type, key))


def effective_for_item(server_id: str, rating_key: str, library_id: Optional[str],
                       is_tv: bool, tmdb_id=None, tvdb_id=None) -> Tuple[str, str]:
    """Mode for a library item by its server key. A season key resolves to its show.
    tmdb_id/tvdb_id: the item's ids when it isn't cached yet (a new webhook item)."""
    try:
        media_type = "tv" if is_tv else "movie"
        tmdb, tvdb = db.get_ids_for_rating_key(rating_key)
        if not tmdb and not tvdb:
            tmdb, tvdb = tmdb_id, tvdb_id
        if not tmdb and not tvdb and is_tv:
            with db.get_db() as conn:
                r = conn.execute("SELECT show_rating_key FROM season_media_info WHERE rating_key=?",
                                 (rating_key,)).fetchone()
            if r and r["show_rating_key"]:
                tmdb, tvdb = db.get_ids_for_rating_key(r["show_rating_key"])
        if not tmdb and not tvdb:
            return ("full", "")
        lib = library_id or db.get_library_id_for_rating_key(rating_key)
        if not lib:
            return ("full", "")
        return effective(group_id_for(server_id, str(lib), media_type), media_type, tmdb, tvdb)
    except Exception as e:
        logger.warning("[MODE] lookup failed for %s, treating it as Full: %s", rating_key, e)
        return ("full", "")


def _log_title(rating_key: str) -> str:
    try:
        title, year = db.get_title_for_rating_key(str(rating_key))
        if title:
            return f"{title} ({year})" if year else str(title)
    except Exception:
        pass
    return f"item {rating_key}"


def gate(server_id: Optional[str], rating_key: str, library_id: Optional[str], is_tv: bool,
         labels: Optional[List[str]] = None, tmdb_id=None, tvdb_id=None) -> str:
    """The effective mode for an automatic path (webhook, auto-generate, retry,
    batch, drift, mirror). `labels`: fresh Plex labels (webhooks) -- applied to
    the group's rules first, so a label added a moment ago counts in the same
    request. Logs once at INFO for a non-full title. Never raises."""
    server_id = server_id or "plex-1"
    if labels is not None and server_id == "plex-1":
        mode, reason = evaluate_item_labels(server_id, rating_key, library_id, is_tv, labels,
                                            tmdb_id=tmdb_id, tvdb_id=tvdb_id)
    else:
        mode, reason = effective_for_item(server_id, rating_key, library_id, is_tv,
                                          tmdb_id=tmdb_id, tvdb_id=tvdb_id)
    if mode != "full":
        logger.info("[MODE] %s: %s (%s)", _log_title(rating_key), mode, reason or "set")
    return mode


def infer_is_tv(rating_key: str) -> bool:
    """True unless the key is a cached movie (shows, seasons and unknown keys)."""
    try:
        with db.get_db() as conn:
            return conn.execute("SELECT 1 FROM movie_cache WHERE rating_key = ? LIMIT 1",
                                (str(rating_key),)).fetchone() is None
    except Exception:
        return False


RULE_SOURCES = ("plex_label",)
_RULE_RANK = {"overlay_only": 1, "leave_alone": 2}


def _find_group(group_id: str) -> Optional[Dict[str, Any]]:
    try:
        ui = db.get_ui_settings() or {}
    except Exception:
        return None
    for g in ui.get("libraryGroups") or []:
        if isinstance(g, dict) and str(g.get("id")) == str(group_id):
            return g
    return None


def _group_shape(group_id: str) -> Tuple[List[str], List[Tuple[str, str]], List[Dict[str, Any]]]:
    """(media types, members as (server_id, library_id), rules) for a group id.

    A real LibraryGroup gives its own values. `group-{type}-{lib}` with no
    group yet is an ungrouped Plex library; `lib:{server}:{lib}` is any other
    ungrouped library (media type unknown, so both). Neither has rules."""
    g = _find_group(group_id)
    if g:
        members = [(str(m.get("serverId")), str(m.get("libraryId")))
                   for m in (g.get("members") or []) if m.get("serverId") and m.get("libraryId") is not None]
        return [g.get("mediaType") or "movie"], members, rules_for(group_id)
    gid = str(group_id)
    for mt in ("movie", "tv"):
        prefix = f"group-{mt}-"
        if gid.startswith(prefix) and len(gid) > len(prefix):
            return [mt], [("plex-1", gid[len(prefix):])], []
    if gid.startswith("lib:"):
        parts = gid.split(":", 2)
        if len(parts) == 3:
            return ["movie", "tv"], [(parts[1], parts[2])], []
    return ["movie", "tv"], [], []


def rules_for(group_id: str) -> List[Dict[str, Any]]:
    """The group's poster mode rules (LibraryGroup.posterModeRules); [] for an
    ungrouped (`lib:`) library or a group with none. Invalid entries dropped."""
    if str(group_id).startswith("lib:"):
        return []
    g = _find_group(group_id)
    out: List[Dict[str, Any]] = []
    for r in (g or {}).get("posterModeRules") or []:
        if not isinstance(r, dict):
            continue
        source = r.get("source") or "plex_label"
        value = str(r.get("value") or "").strip()
        mode = r.get("mode")
        if source in RULE_SOURCES and value and mode in _RULE_RANK:
            out.append({"source": source, "value": value, "mode": mode})
    return out


def _rule_reason(rule: Dict[str, Any]) -> str:
    return f'plex label "{rule["value"]}"'


def _best_rule(rules: List[Dict[str, Any]], labels) -> Tuple[Optional[Dict[str, Any]], List[int]]:
    """Best matching rule for a label list (leave_alone beats overlay_only,
    earlier rule wins a tie) and the indexes of every rule that matched."""
    have = {str(l).strip().lower() for l in (labels or []) if l}
    best, hits = None, []
    for i, r in enumerate(rules):
        if r["source"] == "plex_label" and r["value"].lower() in have:
            hits.append(i)
            if best is None or _RULE_RANK[r["mode"]] > _RULE_RANK[best["mode"]]:
                best = r
    return best, hits


def _labels(raw) -> List[str]:
    try:
        v = json.loads(raw) if raw else []
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _cached_rows(members: List[Tuple[str, str]], media_type: str) -> List[Any]:
    if not members:
        return []
    table = "tv_cache" if media_type == "tv" else "movie_cache"
    cols = "rating_key, server_id, library_id, tmdb_id, labels_json" + (", tvdb_id" if media_type == "tv" else "")
    where = " OR ".join(["(server_id = ? AND library_id = ?)"] * len(members))
    params: List[Any] = []
    for s, l in members:
        params += [s, l]
    with db.get_db() as conn:
        return conn.execute(f"SELECT {cols} FROM {table} WHERE {where}", params).fetchall()


def evaluate_group(group_id: str) -> Dict[str, Any]:
    """Re-apply the group's label rules to its cached items (Plex members'
    labels), replacing every rule mode in the group. Manual modes are kept."""
    media_types, members, rules = _group_shape(group_id)
    matched = changed = 0
    per_rule = [0] * len(rules)
    for mt in media_types:
        matches: Dict[Tuple[str, str], Tuple[str, str]] = {}
        rule_keys: List[set] = [set() for _ in rules]
        if rules:
            for row in _cached_rows([m for m in members if m[0] == "plex-1"], mt):
                key = item_key(mt, row["tmdb_id"], row["tvdb_id"] if mt == "tv" else None)
                if not key:
                    continue
                best, hits = _best_rule(rules, _labels(row["labels_json"]))
                for i in hits:
                    rule_keys[i].add(key)
                if best is None:
                    continue
                prev = matches.get(key)
                if prev is None or _RULE_RANK[best["mode"]] > _RULE_RANK[prev[0]]:
                    matches[key] = (best["mode"], _rule_reason(best))
        for i, keys in enumerate(rule_keys):
            per_rule[i] += len(keys)
        matched += len(matches)
        changed += len(set_rule_modes(group_id, mt, matches))
    if changed:
        logger.info("[MODE] %s: %d title(s) matched poster mode rules, %d changed", group_id, matched, changed)
    return {"matched": matched, "changed": changed, "per_rule": per_rule}


def evaluate_item_labels(server_id: str, rating_key: str, library_id: Optional[str], is_tv: bool,
                         labels: List[str], tmdb_id=None, tvdb_id=None) -> Tuple[str, str]:
    """Apply the group's label rules to one title from fresh labels (webhooks).
    Only Plex labels count. Returns the title's effective (mode, reason).
    tmdb_id/tvdb_id: the item's ids when it isn't cached yet."""
    media_type = "tv" if is_tv else "movie"
    try:
        tmdb, tvdb = db.get_ids_for_rating_key(rating_key)
        if not tmdb and not tvdb:
            tmdb, tvdb = tmdb_id, tvdb_id
        key = item_key(media_type, tmdb, tvdb)
        lib = library_id or db.get_library_id_for_rating_key(rating_key)
        if not key or not lib:
            return ("full", "")
        group_id = group_id_for(server_id, str(lib), media_type)
        if server_id != "plex-1":
            return effective(group_id, media_type, tmdb, tvdb)
        best, _hits = _best_rule(rules_for(group_id), labels)
        new_rule = (best["mode"], _rule_reason(best)) if best else (None, None)
        args = (group_id, media_type, key[0], key[1])
        with db.get_db() as conn:
            row = _row(conn, group_id, media_type, key)
            before = _eff(row)[0]
            if row is None:
                if new_rule[0]:
                    conn.execute("INSERT INTO poster_modes (group_id, media_type, id_type, item_id, rule_mode, rule_reason) "
                                 "VALUES (?,?,?,?,?,?)", args + new_rule)
            elif new_rule[0] is None and not row["manual_mode"]:
                conn.execute(f"DELETE FROM poster_modes WHERE {_WHERE}", args)
            elif (row["rule_mode"], row["rule_reason"]) != new_rule:
                conn.execute(f"UPDATE poster_modes SET rule_mode=?, rule_reason=?, "
                             f"updated_at=CURRENT_TIMESTAMP WHERE {_WHERE}", new_rule + args)
            result = _eff(_row(conn, group_id, media_type, key))
        if result[0] != before:
            on_mode_change(group_id, media_type, key[0], key[1], result[0])
        return result
    except Exception as e:
        logger.warning("[MODE] Couldn't apply label rules to %s: %s", rating_key, e)
        return ("full", "")


def _member_copies(group_id: str, media_type: str, id_type: str, item_id: str) -> List[Tuple[str, str, Optional[int], str]]:
    """Every member server's copy of a title: (server_id, rating_key, tmdb_id, library_id)."""
    _types, members, _rules = _group_shape(group_id)
    if not members:
        return []
    table = "tv_cache" if media_type == "tv" else "movie_cache"
    col = "tvdb_id" if id_type == "tvdb" else "tmdb_id"
    if col == "tvdb_id" and media_type != "tv":
        return []
    where = " OR ".join(["(server_id = ? AND library_id = ?)"] * len(members))
    params: List[Any] = [item_id]
    for s, l in members:
        params += [s, l]
    with db.get_db() as conn:
        rows = conn.execute(f"SELECT server_id, rating_key, tmdb_id, library_id FROM {table} "
                            f"WHERE CAST({col} AS TEXT) = ? AND ({where})", params).fetchall()
    return [(r["server_id"] or "plex-1", str(r["rating_key"]), r["tmdb_id"], r["library_id"]) for r in rows]


def on_mode_change(group_id: str, media_type: str, id_type: str, item_id: str, new_mode: str) -> None:
    """Clean up after a title's effective mode changes. leave_alone: drop its
    retry-queue rows, Overlay Refresh tracking and drift marks on every member
    server. overlay_only: drop its retry-queue rows and drift marks. full: nothing. Never raises."""
    if new_mode not in ("leave_alone", "overlay_only"):
        return
    try:
        copies = _member_copies(group_id, media_type, id_type, item_id)
        if not copies:
            return
        with db.get_db() as conn:
            for server_id, rk, tmdb, lib in copies:
                keys = [rk]
                if media_type == "tv":
                    keys += [str(r["rating_key"]) for r in conn.execute(
                        "SELECT rating_key FROM season_media_info WHERE show_rating_key = ?", (rk,)).fetchall()]
                marks = ",".join("?" * len(keys))
                conn.execute(f"DELETE FROM poster_retry_queue WHERE rating_key IN ({marks})", keys)
                if new_mode == "leave_alone":
                    sql = (f"DELETE FROM overlay_state WHERE server_id = ? AND (rating_key IN ({marks}) "
                           f"OR meta_rating_key IN ({marks})")
                    params: List[Any] = [server_id] + keys + keys
                    if tmdb:
                        sql += " OR (media_type = ? AND tmdb_id = ? AND (library_id IS NULL OR library_id = ?))"
                        params += [media_type, int(tmdb), lib]
                    conn.execute(sql + ")", params)
                conn.execute(f"UPDATE poster_fingerprints SET drift_detected_at = NULL, drift_score = NULL, "
                             f"drift_action = NULL WHERE server_id = ? AND asset_type = 'poster' "
                             f"AND rating_key IN ({marks})", [server_id] + keys)
        logger.info("[MODE] %s %s:%s is now %s; cleared its retry queue%s on %d server cop%s",
                    group_id, id_type, item_id, new_mode,
                    ", Overlay Refresh tracking and drift marks" if new_mode == "leave_alone" else " and drift marks",
                    len(copies), "y" if len(copies) == 1 else "ies")
    except Exception as e:
        logger.warning("[MODE] Cleanup after mode change failed for %s %s:%s: %s", group_id, id_type, item_id, e)


def annotate(items: List[Dict[str, Any]], server_id: str, library_id: Optional[str], media_type: str) -> List[Dict[str, Any]]:
    """Add poster_mode/poster_mode_reason to list items with one lookup per request."""
    modes: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if library_id:
        try:
            modes = modes_for_group(group_id_for(server_id or "plex-1", str(library_id), media_type), media_type)
        except Exception as e:
            logger.debug("[MODE] Couldn't load poster modes for %s: %s", library_id, e)
    for it in items:
        key = item_key(media_type, it.get("tmdb_id"), it.get("tvdb_id") if media_type == "tv" else None)
        m = modes.get(key) if key else None
        it["poster_mode"] = m["mode"] if m else "full"
        it["poster_mode_reason"] = m["reason"] if m else ""
    return items


def set_manual(group_id: str, media_type: str, items: List[Dict[str, Any]], mode: Optional[str]) -> int:
    if mode is not None and mode not in MODES:
        raise ValueError(f"Invalid poster mode: {mode!r}")
    changes: List[Tuple[str, str, str]] = []
    count = 0
    with db.get_db() as conn:
        for it in items:
            key = item_key(media_type, it.get("tmdb_id"), it.get("tvdb_id"))
            if not key:
                continue
            row = _row(conn, group_id, media_type, key)
            before = _eff(row)[0]
            args = (group_id, media_type, key[0], key[1])
            if row is None:
                if mode is None:
                    continue
                conn.execute(
                    "INSERT INTO poster_modes (group_id, media_type, id_type, item_id, manual_mode) VALUES (?,?,?,?,?)",
                    args + (mode,))
            else:
                if row["manual_mode"] == mode:
                    continue
                if mode is None and not row["rule_mode"]:
                    conn.execute(f"DELETE FROM poster_modes WHERE {_WHERE}", args)
                else:
                    conn.execute(f"UPDATE poster_modes SET manual_mode=?, updated_at=CURRENT_TIMESTAMP WHERE {_WHERE}",
                                 (mode,) + args)
            count += 1
            after = _eff(_row(conn, group_id, media_type, key))[0]
            if after != before:
                changes.append((key[0], key[1], after))
    for id_type, item_id, new_mode in changes:
        on_mode_change(group_id, media_type, id_type, item_id, new_mode)
    return count


def set_rule_modes(group_id: str, media_type: str,
                   matches: Dict[Tuple[str, str], Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Replace rule_mode/rule_reason for the whole group+type.

    Keys in `matches` get the value, all others are cleared. Returns the keys
    whose effective mode changed."""
    for mode, _reason in matches.values():
        if mode not in MODES:
            raise ValueError(f"Invalid poster mode: {mode!r}")
    changed: List[Tuple[str, str]] = []
    new_modes: Dict[Tuple[str, str], str] = {}
    with db.get_db() as conn:
        rows = conn.execute("SELECT * FROM poster_modes WHERE group_id=? AND media_type=?",
                            (group_id, media_type)).fetchall()
        existing = {(r["id_type"], r["item_id"]): r for r in rows}
        for key, r in existing.items():
            if key in matches or not (r["rule_mode"] or r["rule_reason"]):
                continue
            before = _eff(r)[0]
            args = (group_id, media_type, key[0], key[1])
            if r["manual_mode"]:
                conn.execute(f"UPDATE poster_modes SET rule_mode=NULL, rule_reason=NULL, "
                             f"updated_at=CURRENT_TIMESTAMP WHERE {_WHERE}", args)
            else:
                conn.execute(f"DELETE FROM poster_modes WHERE {_WHERE}", args)
            after = r["manual_mode"] or "full"
            if after != before:
                changed.append(key)
                new_modes[key] = after
        for key, (mode, reason) in matches.items():
            r = existing.get(key)
            before = _eff(r)[0]
            args = (group_id, media_type, key[0], key[1])
            if r is None:
                conn.execute(
                    "INSERT INTO poster_modes (group_id, media_type, id_type, item_id, rule_mode, rule_reason) "
                    "VALUES (?,?,?,?,?,?)", args + (mode, reason))
            else:
                conn.execute(f"UPDATE poster_modes SET rule_mode=?, rule_reason=?, "
                             f"updated_at=CURRENT_TIMESTAMP WHERE {_WHERE}", (mode, reason) + args)
            after = r["manual_mode"] if (r is not None and r["manual_mode"]) else mode
            if after != before:
                changed.append(key)
                new_modes[key] = after
    for key in changed:
        on_mode_change(group_id, media_type, key[0], key[1], new_modes[key])
    return changed


def modes_for_group(group_id: str, media_type: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    with db.get_db() as conn:
        for r in conn.execute("SELECT * FROM poster_modes WHERE group_id=? AND media_type=?",
                              (group_id, media_type)).fetchall():
            mode, reason = _eff(r)
            out[(r["id_type"], r["item_id"])] = {"mode": mode, "reason": reason, "manual": r["manual_mode"]}
    return out


def tv_lookup(modes: Dict[Tuple[str, str], Dict[str, Any]], tmdb_id, tvdb_id) -> Optional[Dict[str, Any]]:
    key = item_key("tv", tmdb_id, tvdb_id)
    return modes.get(key) if key else None
