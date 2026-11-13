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


def _resolve(server_id: str, rating_key: str, library_id: Optional[str], is_tv: bool,
             tmdb_id=None, tvdb_id=None) -> Optional[Tuple[str, str, Tuple[str, str]]]:
    """(group id, media type, item key) for a library item by its server key.
    A season key resolves to its show. tmdb_id/tvdb_id: the item's ids when it
    isn't cached yet (a new webhook item). None when it can't have a mode."""
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
    key = item_key(media_type, tmdb, tvdb)
    if not key:
        return None
    lib = library_id or db.get_library_id_for_rating_key(rating_key)
    if not lib:
        return None
    return group_id_for(server_id, str(lib), media_type), media_type, key


def effective_for_item(server_id: str, rating_key: str, library_id: Optional[str],
                       is_tv: bool, tmdb_id=None, tvdb_id=None) -> Tuple[str, str]:
    """Mode for a library item by its server key (see _resolve())."""
    try:
        res = _resolve(server_id, rating_key, library_id, is_tv, tmdb_id, tvdb_id)
        if not res:
            return ("full", "")
        group_id, media_type, key = res
        with db.get_db() as conn:
            return _eff(_row(conn, group_id, media_type, key))
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
         labels: Optional[List[str]] = None, tmdb_id=None, tvdb_id=None, fresh_tags: bool = False) -> str:
    """The effective mode for an automatic path (webhook, auto-generate, retry,
    batch, drift, mirror). `labels`: fresh Plex labels (webhooks) -- applied to
    the group's rules first, so a label added a moment ago counts in the same
    request. `fresh_tags`: also re-read the linked Radarr/Sonarr's tags (at most
    once a minute) for this title, so a tag added since the last scan counts.
    Logs once at INFO for a non-full title. Never raises."""
    server_id = server_id or "plex-1"
    if (labels is not None and server_id == "plex-1") or fresh_tags:
        mode, reason = evaluate_item(server_id, rating_key, library_id, is_tv,
                                     labels=labels if server_id == "plex-1" else None,
                                     tmdb_id=tmdb_id, tvdb_id=tvdb_id, fresh_tags=fresh_tags)
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


RULE_SOURCES = ("plex_label", "arr_tag")
_ARR_REASONS = ("radarr tag", "sonarr tag")
_MODE_NAMES = {"overlay_only": "Overlay only", "leave_alone": "Leave alone", "full": "Full"}
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


def _rule_reason(rule: Dict[str, Any], arr_type: Optional[str] = None) -> str:
    if rule["source"] == "arr_tag":
        return f'{arr_type or "radarr"} tag "{rule["value"]}"'
    return f'plex label "{rule["value"]}"'


def _has_tag_rules(rules: List[Dict[str, Any]]) -> bool:
    return any(r["source"] == "arr_tag" for r in rules)


def _is_tag_reason(reason) -> bool:
    return str(reason or "").startswith(_ARR_REASONS)


def group_arr(group_id: str, max_age: int = 60) -> Tuple[Optional[str], Optional[str], bool]:
    """The group's linked Radarr/Sonarr: (instance id, type, usable).

    No link: (None, None, False) -- tag rules then match nothing. A link whose
    instance is missing, disabled, of the wrong type, or can't be read is not
    usable: its tags are unknown, so tag-rule modes must be left as they are."""
    g = _find_group(group_id)
    iid = _s((g or {}).get("arrInstanceId"))
    if not iid:
        return (None, None, False)
    from . import arr_client
    inst = arr_client.get_instance(iid)
    want = "sonarr" if (g.get("mediaType") or "movie") == "tv" else "radarr"
    if not inst or inst.get("type") != want:
        return (iid, inst.get("type") if inst else None, False)
    return (iid, want, arr_client.refresh(iid, max_age))


def _lookup_tags(get, media_type: str, key: Tuple[str, str]) -> List[str]:
    """A title's Radarr/Sonarr tags by its item key. A show Simposter only
    knows by TMDb id that Sonarr doesn't list under it is tried by TVDB id."""
    found = get(key)
    if found is None and media_type == "tv" and key[0] == "tmdb":
        from . import arr_client
        tvdb = arr_client.tvdb_for_tmdb(key[1])
        if tvdb:
            found = get(("tvdb", tvdb))
    return found or []


def _best_rule(rules: List[Dict[str, Any]], labels, tags=None):
    """(best label rule, best tag rule, indexes of every rule that matched) for a
    title's Plex labels and Radarr/Sonarr tags. Within a source, leave_alone
    beats overlay_only and the earlier rule wins a tie. tags None = unknown:
    tag rules are skipped (the caller then uses the tag result stored earlier)."""
    have = {str(l).strip().lower() for l in (labels or []) if l}
    have_tags = None if tags is None else {str(t).strip().lower() for t in tags if t}
    lab = tag = None
    hits: List[int] = []
    for i, r in enumerate(rules):
        value = r["value"].strip().lower()
        if r["source"] == "plex_label":
            if value in have:
                hits.append(i)
                if lab is None or _RULE_RANK[r["mode"]] > _RULE_RANK[lab["mode"]]:
                    lab = r
        elif have_tags is not None and value in have_tags:
            hits.append(i)
            if tag is None or _RULE_RANK[r["mode"]] > _RULE_RANK[tag["mode"]]:
                tag = r
    return lab, tag, hits


def _combine(lab: Optional[Tuple[str, str]], tag: Optional[Tuple[str, str]]) -> Optional[Tuple[str, str]]:
    """The stronger of a label result and a tag result, each (mode, reason) or None."""
    if lab and tag:
        return tag if _RULE_RANK.get(tag[0], 0) > _RULE_RANK.get(lab[0], 0) else lab
    return lab or tag


def _stored_tag(row) -> Optional[Tuple[str, str]]:
    """What the tag rules last decided for a title (kept apart from the
    combined rule mode, so it survives while Radarr/Sonarr can't be read)."""
    if row is None:
        return None
    if row["tag_mode"]:
        return (row["tag_mode"], row["tag_reason"] or "")
    if row["rule_mode"] and _is_tag_reason(row["rule_reason"]):
        return (row["rule_mode"], row["rule_reason"])
    return None


def _stored_tag_modes(group_id: str, media_type: str) -> Dict[Tuple[str, str], Tuple[str, str]]:
    out: Dict[Tuple[str, str], Tuple[str, str]] = {}
    with db.get_db() as conn:
        for r in conn.execute("SELECT * FROM poster_modes WHERE group_id=? AND media_type=?",
                              (group_id, media_type)).fetchall():
            t = _stored_tag(r)
            if t:
                out[(r["id_type"], r["item_id"])] = t
    return out


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


def evaluate_group(group_id: str, tags_max_age: int = 60) -> Dict[str, Any]:
    """Re-apply the group's rules to its cached items (Plex members' labels,
    the linked Radarr/Sonarr's tags), replacing every rule mode in the group.
    Manual modes are kept. When the linked Radarr/Sonarr can't be read, each
    title keeps the result its tag rules gave last time (label rules are still
    applied), and the match count of a tag rule is None (unknown)."""
    media_types, members, rules = _group_shape(group_id)
    matched = changed = 0
    per_rule: List[Optional[int]] = [0] * len(rules)
    tags: Optional[Dict[Tuple[str, str], List[str]]] = None
    arr_type = None
    outage = False
    if _has_tag_rules(rules):
        iid, arr_type, usable = group_arr(group_id, tags_max_age)
        if iid is None:
            tags = {}
        elif usable:
            from . import arr_client
            tags = arr_client.tags_for(iid)
        else:
            outage = True
            logger.warning("[MODE] %s: its Radarr/Sonarr tags couldn't be read; poster modes set by tag rules "
                           "are kept as they are", group_id)
    for mt in media_types:
        stored = _stored_tag_modes(group_id, mt) if outage else {}
        matches: Dict[Tuple[str, str], Tuple[str, str]] = {}
        tag_modes: Dict[Tuple[str, str], Tuple[str, str]] = {}
        rule_keys: List[set] = [set() for _ in rules]
        if rules:
            for row in _cached_rows(members, mt):
                key = item_key(mt, row["tmdb_id"], row["tvdb_id"] if mt == "tv" else None)
                if not key:
                    continue
                labels = _labels(row["labels_json"]) if (row["server_id"] or "plex-1") == "plex-1" else []
                item_tags = None if tags is None else (_lookup_tags(tags.get, mt, key) if tags else [])
                lab_rule, tag_rule, hits = _best_rule(rules, labels, item_tags)
                for i in hits:
                    rule_keys[i].add(key)
                if outage:
                    tag = stored.get(key)
                else:
                    tag = (tag_rule["mode"], _rule_reason(tag_rule, arr_type)) if tag_rule else None
                if tag:
                    tag_modes[key] = tag
                best = _combine((lab_rule["mode"], _rule_reason(lab_rule)) if lab_rule else None, tag)
                if best is None:
                    continue
                prev = matches.get(key)
                if prev is None or _RULE_RANK[best[0]] > _RULE_RANK[prev[0]]:
                    matches[key] = best
        if outage:
            # A tag-ruled title that isn't in the cache right now keeps its mode too.
            for key, tag in stored.items():
                matches.setdefault(key, tag)
        for i, keys in enumerate(rule_keys):
            if outage and rules[i]["source"] == "arr_tag":
                per_rule[i] = None
            elif per_rule[i] is not None:
                per_rule[i] += len(keys)
        matched += len(matches)
        changed += len(set_rule_modes(group_id, mt, matches, None if outage else tag_modes))
    if changed:
        logger.info("[MODE] %s: %d title(s) matched poster mode rules, %d changed", group_id, matched, changed)
    return {"matched": matched, "changed": changed, "per_rule": per_rule}


def _cached_labels(group_id: str, media_type: str, key: Tuple[str, str]) -> List[str]:
    """The cached Plex labels of a title's Plex copies in the group."""
    _types, members, _rules = _group_shape(group_id)
    plex = [m for m in members if m[0] == "plex-1"]
    if not plex or (key[0] == "tvdb" and media_type != "tv"):
        return []
    table = "tv_cache" if media_type == "tv" else "movie_cache"
    col = "tvdb_id" if key[0] == "tvdb" else "tmdb_id"
    where = " OR ".join(["(server_id = ? AND library_id = ?)"] * len(plex))
    params: List[Any] = [key[1]]
    for s_id, lib in plex:
        params += [s_id, lib]
    with db.get_db() as conn:
        rows = conn.execute(f"SELECT labels_json FROM {table} WHERE CAST({col} AS TEXT) = ? AND ({where})",
                            params).fetchall()
    out: List[str] = []
    for r in rows:
        out += _labels(r["labels_json"])
    return out


def evaluate_item(server_id: str, rating_key: str, library_id: Optional[str], is_tv: bool,
                  labels: Optional[List[str]] = None, tmdb_id=None, tvdb_id=None,
                  fresh_tags: bool = False) -> Tuple[str, str]:
    """Apply the group's rules to one title and return its effective (mode, reason).

    labels: fresh Plex labels (a Plex webhook); None = use the cached ones.
    fresh_tags: re-read the linked Radarr/Sonarr (at most once a minute) and
    use this title's tags. When tags aren't read now, or can't be, the result
    the tag rules gave last time is used. tmdb_id/tvdb_id: the item's ids when
    it isn't cached yet. On an error the stored mode is returned."""
    try:
        res = _resolve(server_id, rating_key, library_id, is_tv, tmdb_id, tvdb_id)
        if not res:
            return ("full", "")
        group_id, media_type, key = res
        rules = rules_for(group_id)
        tag_rules = _has_tag_rules(rules)
        use_labels = labels is not None and server_id == "plex-1"
        use_tags = fresh_tags and tag_rules
        if not (use_labels or use_tags):
            with db.get_db() as conn:
                return _eff(_row(conn, group_id, media_type, key))
        if not use_labels:
            labels = _cached_labels(group_id, media_type, key)
        item_tags: Optional[List[str]] = None
        arr_type = None
        if use_tags:
            iid, arr_type, usable = group_arr(group_id, 60)
            if iid is None:
                item_tags = []
            elif usable:
                from . import arr_client
                item_tags = _lookup_tags(lambda k: arr_client.tags_of(iid, k), media_type, key)
        lab_rule, tag_rule, _hits = _best_rule(rules, labels, item_tags)
        lab = (lab_rule["mode"], _rule_reason(lab_rule)) if lab_rule else None
        with db.get_db() as conn:
            row = _row(conn, group_id, media_type, key)
            before = _eff(row)[0]
            if not tag_rules:
                tag_val, tag_write = None, (None, None)
            elif item_tags is not None:
                tag_val = (tag_rule["mode"], _rule_reason(tag_rule, arr_type)) if tag_rule else None
                tag_write = tag_val or (None, None)
            else:
                tag_val, tag_write = _stored_tag(row), _KEEP
            best = _combine(lab, tag_val)
            _apply_rule(conn, group_id, media_type, key, row,
                        best[0] if best else None, best[1] if best else None, tag_write)
            result = _eff(_row(conn, group_id, media_type, key))
        if result[0] != before:
            on_mode_change(group_id, media_type, key[0], key[1], result[0])
        return result
    except Exception as e:
        logger.warning("[MODE] Couldn't apply rules to %s, using its stored mode: %s", rating_key, e)
        return effective_for_item(server_id, rating_key, library_id, is_tv, tmdb_id=tmdb_id, tvdb_id=tvdb_id)


def evaluate_item_labels(server_id: str, rating_key: str, library_id: Optional[str], is_tv: bool,
                         labels: List[str], tmdb_id=None, tvdb_id=None) -> Tuple[str, str]:
    """Apply the group's label rules to one title from fresh labels (webhooks)."""
    return evaluate_item(server_id, rating_key, library_id, is_tv, labels=labels,
                         tmdb_id=tmdb_id, tvdb_id=tvdb_id)


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
        it["poster_mode_warning"] = m["warning"] if m else ""
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
                if row["manual_mode"] == mode and not row["lost_mode"]:
                    continue
                if mode is None and not row["rule_mode"]:
                    conn.execute(f"DELETE FROM poster_modes WHERE {_WHERE}", args)
                else:
                    # Setting a mode by hand also answers a "lost its rule" heads-up.
                    conn.execute(f"UPDATE poster_modes SET manual_mode=?, lost_mode=NULL, lost_reason=NULL, "
                                 f"lost_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE {_WHERE}", (mode,) + args)
            count += 1
            after = _eff(_row(conn, group_id, media_type, key))[0]
            if after != before:
                changes.append((key[0], key[1], after))
    for id_type, item_id, new_mode in changes:
        on_mode_change(group_id, media_type, id_type, item_id, new_mode)
    return count


_KEEP = object()  # _apply_rule(tag=_KEEP): leave the stored tag result untouched


def _apply_rule(conn, group_id: str, media_type: str, key: Tuple[str, str], row,
                mode: Optional[str], reason: Optional[str], tag=_KEEP) -> None:
    """Write one title's rule result (mode None = no rule matches it).

    tag: what the tag rules alone decided, (mode, reason) or (None, None);
    _KEEP when tags weren't read. A title that had a rule mode, has no hand-set
    mode and now matches nothing drops to Full; its row is kept with
    lost_mode/lost_reason so the UI can show a heads-up (see warning_text())."""
    args = (group_id, media_type, key[0], key[1])
    set_tag = tag is not _KEEP
    tm, tr = tag if set_tag else (None, None)
    if mode:
        if row is None:
            conn.execute("INSERT INTO poster_modes (group_id, media_type, id_type, item_id, rule_mode, rule_reason, "
                         "tag_mode, tag_reason) VALUES (?,?,?,?,?,?,?,?)", args + (mode, reason, tm, tr))
            return
        tag_changed = set_tag and (row["tag_mode"], row["tag_reason"]) != (tm, tr)
        if (row["rule_mode"], row["rule_reason"]) != (mode, reason) or row["lost_mode"] or tag_changed:
            if not set_tag:
                tm, tr = row["tag_mode"], row["tag_reason"]
            conn.execute(f"UPDATE poster_modes SET rule_mode=?, rule_reason=?, tag_mode=?, tag_reason=?, "
                         f"lost_mode=NULL, lost_reason=NULL, lost_at=NULL, updated_at=CURRENT_TIMESTAMP "
                         f"WHERE {_WHERE}", (mode, reason, tm, tr) + args)
        return
    if row is None or not (row["rule_mode"] or row["rule_reason"] or row["tag_mode"]):
        return
    if row["manual_mode"]:
        conn.execute(f"UPDATE poster_modes SET rule_mode=NULL, rule_reason=NULL, tag_mode=NULL, tag_reason=NULL, "
                     f"updated_at=CURRENT_TIMESTAMP WHERE {_WHERE}", args)
    elif row["rule_mode"]:
        conn.execute(f"UPDATE poster_modes SET rule_mode=NULL, rule_reason=NULL, tag_mode=NULL, tag_reason=NULL, "
                     f"lost_mode=?, lost_reason=?, lost_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP "
                     f"WHERE {_WHERE}", (row["rule_mode"], row["rule_reason"]) + args)
    elif row["lost_mode"]:
        conn.execute(f"UPDATE poster_modes SET rule_reason=NULL, tag_mode=NULL, tag_reason=NULL WHERE {_WHERE}", args)
    else:
        conn.execute(f"DELETE FROM poster_modes WHERE {_WHERE}", args)


def set_rule_modes(group_id: str, media_type: str,
                   matches: Dict[Tuple[str, str], Tuple[str, str]],
                   tag_modes: Optional[Dict[Tuple[str, str], Tuple[str, str]]] = None) -> List[Tuple[str, str]]:
    """Replace rule_mode/rule_reason for the whole group+type.

    Keys in `matches` get the value, all others are cleared. tag_modes: what
    the tag rules alone decided per title this pass ({} = nothing matched);
    None = tags weren't read, leave each matched title's stored tag result.
    Returns the keys whose effective mode changed."""
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
            if key in matches or not (r["rule_mode"] or r["rule_reason"] or r["tag_mode"]):
                continue
            before = _eff(r)[0]
            _apply_rule(conn, group_id, media_type, key, r, None, None, (None, None))
            after = r["manual_mode"] or "full"
            if after != before:
                changed.append(key)
                new_modes[key] = after
        for key, (mode, reason) in matches.items():
            r = existing.get(key)
            before = _eff(r)[0]
            tag = _KEEP if tag_modes is None else (tag_modes.get(key) or (None, None))
            _apply_rule(conn, group_id, media_type, key, r, mode, reason, tag)
            after = r["manual_mode"] if (r is not None and r["manual_mode"]) else mode
            if after != before:
                changed.append(key)
                new_modes[key] = after
    for key in changed:
        on_mode_change(group_id, media_type, key[0], key[1], new_modes[key])
    return changed


def warning_text(row) -> str:
    """The heads-up for a title that dropped to Full because its rule stopped matching."""
    if row is None or not row["lost_mode"] or row["manual_mode"] or row["rule_mode"]:
        return ""
    was = _MODE_NAMES.get(row["lost_mode"], row["lost_mode"])
    why = f" ({row['lost_reason']})" if row["lost_reason"] else ""
    return (f"Was {was}{why}. That rule no longer matches, so Simposter treats this title as Full "
            f"and may replace its poster.")


def clear_lost(group_id: str, media_type: str, keys: List[Tuple[str, str]]) -> int:
    """Dismiss the "lost its rule" heads-up for these titles. Returns how many had one."""
    n = 0
    with db.get_db() as conn:
        for key in keys:
            args = (group_id, media_type, key[0], key[1])
            row = _row(conn, group_id, media_type, key)
            if row is None or not row["lost_mode"]:
                continue
            if row["manual_mode"] or row["rule_mode"]:
                conn.execute(f"UPDATE poster_modes SET lost_mode=NULL, lost_reason=NULL, lost_at=NULL WHERE {_WHERE}", args)
            else:
                conn.execute(f"DELETE FROM poster_modes WHERE {_WHERE}", args)
            n += 1
    return n


def clear_lost_for_item(server_id: Optional[str], rating_key: str, is_tv: Optional[bool] = None) -> None:
    """Simposter sent a full poster for this title: nothing left to warn about. Never raises."""
    try:
        with db.get_db() as conn:
            if conn.execute("SELECT 1 FROM poster_modes WHERE lost_mode IS NOT NULL LIMIT 1").fetchone() is None:
                return
        tv = infer_is_tv(rating_key) if is_tv is None else is_tv
        res = _resolve(server_id or "plex-1", str(rating_key), None, tv)
        if res:
            clear_lost(res[0], res[1], [res[2]])
    except Exception as e:
        logger.debug("[MODE] Clearing the lost-rule heads-up for %s failed: %s", rating_key, e)


def modes_for_group(group_id: str, media_type: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    with db.get_db() as conn:
        for r in conn.execute("SELECT * FROM poster_modes WHERE group_id=? AND media_type=?",
                              (group_id, media_type)).fetchall():
            mode, reason = _eff(r)
            out[(r["id_type"], r["item_id"])] = {"mode": mode, "reason": reason, "manual": r["manual_mode"],
                                                 "warning": warning_text(r)}
    return out


def tv_lookup(modes: Dict[Tuple[str, str], Dict[str, Any]], tmdb_id, tvdb_id) -> Optional[Dict[str, Any]]:
    key = item_key("tv", tmdb_id, tvdb_id)
    return modes.get(key) if key else None
