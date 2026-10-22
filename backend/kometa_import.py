"""Kometa overlay file importer.

Steps 2 and 3 of the Kometa overlay plan (ai_repo/simposter/kometa-overlay-config-plan.md):

  expand   Kometa's template system (templates, variables, default, optional,
           conditionals, <<var>> substitution, external "default: templates").
           apply_template() is a close port of Kometa's DataFile.apply_template
           (modules/meta.py) so files expand the way Kometa expands them.
  map      each expanded overlay definition onto an overlay-engine-v2 element
           (backend/overlay_engine.py): conditions, group/weight, suppress,
           Kometa placement, back box, text, image.
  report   every overlay gets a status and messages, so anything Simposter can't
           do yet is listed instead of silently dropped.

Nothing here touches the database; backend/api/kometa_import.py saves the result.
"""

from __future__ import annotations

import copy
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import yaml

_DEFAULTS_DIR = Path(__file__).parent / "kometa_defaults"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
FONT_EXTS = {".ttf", ".otf", ".ttc"}
YAML_EXTS = {".yml", ".yaml"}

# Where Kometa's own built-in overlay images and community images live.
KOMETA_DEFAULT_IMAGES_URL = "https://raw.githubusercontent.com/Kometa-Team/Kometa/master/defaults/overlays/images/"
KOMETA_GIT_URL = "https://raw.githubusercontent.com/Kometa-Team/Community-Configs/master/"

# Fields Simposter fills for every render (overlay metadata plus derived fields).
KNOWN_FIELDS = {
    "title", "year", "resolution", "video_resolution", "video_codec", "audio_codec",
    "audio_channels", "audio_language", "edition", "studio", "label", "filepath",
    "media_type", "tmdb_id",
}
RATING_FIELDS = {"audience_rating", "critic_rating", "user_rating"}
# Rating fields MDBList fills (backend/mdblist_client.py). user_rating (your own
# Plex star rating) has no source yet.
MDBLIST_RATING_FIELDS = {
    "audience_rating", "critic_rating", "mdb_rating", "mdb_average_rating",
    "mdb_imdb_rating", "mdb_tmdb_rating", "mdb_trakt_rating", "mdb_tomatoes_rating",
    "mdb_tomatoesaudience_rating", "mdb_metacritic_rating", "mdb_metacriticuser_rating",
    "mdb_letterboxd_rating", "mdb_myanimelist_rating",
}


def _rating_message(field: str) -> Optional[str]:
    if field in MDBLIST_RATING_FIELDS:
        try:
            from .mdblist_client import has_key
            if has_key():
                return None
        except Exception:
            pass
        return f"{field} comes from MDBList; add an MDBList API key in Settings → General or this stays hidden"
    if field in RATING_FIELDS or field.endswith("_rating"):
        return f"{field} isn't available in Simposter yet, so this stays hidden"
    return None

# Kometa list builders: an overlay that only targets items on such a list can't
# be matched yet (Step 4 adds MDBList).
_LIST_BUILDER_PREFIXES = (
    "mdblist", "tmdb", "trakt", "imdb", "tvdb", "letterboxd", "anidb", "anilist",
    "mal", "icheckmovies", "flixpatrol", "reciperr", "stevenlu", "mojo", "radarr",
    "sonarr", "tautulli", "plex_watchlist", "plex_pilots", "plex_collectionless",
    "plex_collection", "boxofficemojo", "trakt_list", "summary",
)

# Builders that are a fixed list of IDs: matched against the item's own ID.
_ID_BUILDERS = {
    "tmdb_movie": ("tmdb_id", "TMDb"),
    "tmdb_show": ("tmdb_id", "TMDb"),
    "tvdb_show": ("tvdb_id", "TVDB"),
}

# Filter attributes Simposter can check, and how a bare (no modifier) value compares.
# "string" filters match when the value is contained; "tag" filters match exactly.
_FILTER_FIELDS = {
    "filepath": ("filepath", "string"),
    "folder": ("filepath", "string"),
    "title": ("title", "string"),
    "label": ("label", "tag"),
    "resolution": ("resolution", "tag"),
    "audio_language": ("audio_language", "tag"),
    "edition": ("edition", "string"),
    "studio": ("studio", "tag"),
    "year": ("year", "number"),
    "audience_rating": ("audience_rating", "number"),
    "critic_rating": ("critic_rating", "number"),
    "user_rating": ("user_rating", "number"),
    "tvdb_status": ("show_status", "status"),
    "tmdb_status": ("show_status", "status"),
    "added": ("days_since_added", "days"),
}

# Kometa's tmdb_status values -> the show_status values the engine fills
# (continuing / ended / canceled / upcoming, from TMDb's show status).
_TMDB_STATUS_MAP = {
    "returning": "continuing", "planned": "upcoming", "production": "upcoming",
    "pilot": "upcoming", "ended": "ended", "canceled": "canceled",
}


class KometaFailed(Exception):
    """A template value referenced a missing optional variable (Kometa's Failed)."""


class ImportError_(Exception):
    """A file couldn't be imported at all."""


# --------------------------------------------------------------------------
# Template expansion (port of Kometa DataFile.apply_template)
# --------------------------------------------------------------------------

def _get_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _quote(value: Any) -> str:
    try:
        return quote(str(value))
    except Exception:
        return ""


def _replace_var(input_item: Any, search_dicts: Any) -> Any:
    if not isinstance(search_dicts, list):
        search_dicts = [search_dicts]
    return_item = input_item
    for search_dict in search_dicts:
        for rk, rv in search_dict.items():
            if rk not in ("name_format", "summary_format"):
                if f"<<{rk}>>" == str(return_item):
                    return_item = rv
                if f"<<{rk}>>" in str(return_item):
                    return_item = str(return_item).replace(f"<<{rk}>>", str(rv))
    return return_item


def apply_template(
    templates: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]],
    call_name: Optional[str],
    mapping_name: str,
    data: Dict[str, Any],
    template_call: Any,
    extra_variables: Dict[str, Any],
    library_type: str = "movie",
    config_vars: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Expand the templates a definition calls into concrete attributes.

    templates maps name -> (template dict, external template_variables). Returns
    the new attributes; the caller adds those the definition doesn't set itself.
    """
    if not templates:
        raise ImportError_("No templates found")
    if not template_call:
        raise ImportError_("template attribute is blank")
    config_vars = config_vars or {}
    new_attributes: Dict[str, Any] = {}

    for call in _get_list(template_call):
        if not isinstance(call, dict) or not call.get("name"):
            raise ImportError_("template must be a list of {name: ...}")
        original_variables = dict(call)
        template_name = str(original_variables["name"])
        if template_name not in templates:
            raise ImportError_(f"template {template_name} not found")
        template, temp_vars = templates[template_name]
        if not isinstance(template, dict):
            raise ImportError_(f"template {template_name} is not a dictionary")

        optional: List[str] = []
        for tm in list(original_variables):
            if original_variables[tm] is None:
                original_variables.pop(tm)
                optional.append(str(tm))

        name = call_name if call_name else (template["name"] if "name" in template else mapping_name)
        now = datetime.now()
        original_variables["overlay_name"] = str(name)
        original_variables["mapping_name"] = mapping_name
        original_variables["current_year"] = now.year
        original_variables["current_month"] = now.month
        original_variables["current_day"] = now.day
        original_variables["library_type"] = library_type
        original_variables["library_typeU"] = library_type.capitalize()
        original_variables["library_name"] = "Simposter"

        conditionals: Dict[str, Any] = {}
        if "conditionals" in template:
            if not isinstance(template["conditionals"], dict) or not template["conditionals"]:
                raise ImportError_(f"template {template_name}: conditionals must be a dictionary")
            conditionals.update(template["conditionals"])

        added_vars: Dict[str, Any] = {}
        init_defaults: Dict[str, Any] = {}
        if "default" in template:
            if not isinstance(template["default"], dict) or not template["default"]:
                raise ImportError_(f"template {template_name}: default must be a dictionary")
            init_defaults = template["default"]
        all_init_defaults = dict(init_defaults)

        variables: Dict[str, Any] = {}
        temp_conditionals: Dict[str, Any] = {}
        for input_dict, overwrite_call in (
            (original_variables, False), (temp_vars or {}, False),
            (extra_variables or {}, False), (config_vars, True),
        ):
            for input_key, input_value in input_dict.items():
                if input_key == "conditionals":
                    if not isinstance(input_value, dict) or not input_value:
                        raise ImportError_("template_variables conditionals must be a dictionary")
                    temp_conditionals.update(input_value)
                elif input_key == "default":
                    if not isinstance(input_value, dict) or not input_value:
                        raise ImportError_("template_variables default must be a dictionary")
                    all_init_defaults.update(input_value)
                else:
                    input_key = _replace_var(input_key, original_variables)
                    if input_value is None:
                        optional.append(str(input_key))
                        variables.pop(input_key, None)
                        added_vars.pop(input_key, None)
                    elif overwrite_call:
                        variables[input_key] = input_value
                    elif input_key not in added_vars:
                        added_vars[input_key] = input_value
        for k, v in added_vars.items():
            if k not in variables:
                variables[k] = v
        for k, v in temp_conditionals.items():
            if k not in variables:
                conditionals[k] = v

        if "key_name" in variables:
            variables["original_key_name"] = variables["key_name"]
            first = str(variables["key_name"]).upper()[:1]
            variables["key_name_first_letter"] = first if first.isalpha() else "#"

        default: Dict[str, Any] = {}
        if all_init_defaults:
            var_default = {
                _replace_var(dk, variables): _replace_var(dv, variables)
                for dk, dv in all_init_defaults.items() if dk not in variables
            }
            for d_key, d_value in var_default.items():
                final_key = _replace_var(d_key, var_default)
                if final_key not in optional and final_key not in variables and final_key not in conditionals:
                    default[final_key] = d_value
                    if "<<" in str(d_value):
                        default[f"{final_key}_encoded"] = re.sub(r"<<(.+)>>", r"<<\1_encoded>>", str(d_value))
                    else:
                        default[f"{final_key}_encoded"] = _quote(d_value)

        if "optional" in template:
            if not template["optional"]:
                raise ImportError_(f"template {template_name}: optional is blank")
            for op in _get_list(template["optional"]):
                op = _replace_var(op, variables)
                if op not in default and op not in conditionals:
                    optional.append(str(op))
                    optional.append(f"{op}_encoded")

        for con_key, con_value in conditionals.items():
            if not isinstance(con_value, dict):
                raise ImportError_(f"conditional {con_key} is not a dictionary")
            final_key = _replace_var(con_key, [variables, default])
            if final_key in variables:
                continue
            if "conditions" not in con_value:
                raise ImportError_(f"conditional {con_key}: conditions sub-attribute required")
            conditions = con_value["conditions"]
            if isinstance(conditions, dict):
                conditions = [conditions]
            if not isinstance(conditions, list):
                raise ImportError_(f"conditional {con_key}: conditions must be a list or dictionary")
            condition_found = False
            for condition in conditions:
                if not isinstance(condition, dict) or "value" not in condition:
                    raise ImportError_(f"conditional {con_key}: each condition needs a value")
                passed = True
                for var_key, var_value in condition.items():
                    if var_key == "value":
                        continue
                    var_key = _replace_var(var_key, [variables, default])
                    var_value = _replace_var(var_value, [variables, default])
                    failed = False
                    if str(var_key).endswith(".exists"):
                        want = str(var_value).strip().lower() in ("true", "1", "yes")
                        base = var_key[:-7]
                        exists = base in variables and variables[base] is not None
                        failed = (want and not exists) or (not want and exists)
                    elif str(var_key).endswith(".not"):
                        base = var_key[:-4]
                        if base in variables:
                            cur = variables[base]
                            failed = cur in var_value if isinstance(var_value, list) else str(cur) == str(var_value)
                    elif str(var_key).endswith(".notdefault"):
                        base = var_key[:-11]
                        if base in variables or base in default:
                            cur = variables[base] if base in variables else default[base]
                            failed = cur in var_value if isinstance(var_value, list) else str(cur) == str(var_value)
                    elif var_key in variables or var_key in default:
                        cur = variables[var_key] if var_key in variables else default[var_key]
                        failed = cur not in var_value if isinstance(var_value, list) else str(cur) != str(var_value)
                    else:
                        failed = True
                    if failed:
                        passed = False
                if passed:
                    condition_found = True
                    if condition["value"] is not None:
                        variables[final_key] = condition["value"]
                        variables[f"{final_key}_encoded"] = _quote(condition["value"])
                    else:
                        optional.append(final_key)
                    break
            if not condition_found:
                if "default" in con_value:
                    variables[final_key] = con_value["default"]
                    variables[f"{final_key}_encoded"] = _quote(con_value["default"])
                else:
                    optional.append(str(final_key))
                    optional.append(f"{final_key}_encoded")

        variables["overlay_sort"] = variables["overlay_name"]
        variables["mapping_sort"] = variables["mapping_name"]

        for key, value in list(variables.items()):
            if "<<" in key and ">>" in key:
                for k, v in variables.items():
                    if f"<<{k}>>" in key:
                        key = key.replace(f"<<{k}>>", f"{v}")
                for k, v in default.items():
                    if f"<<{k}>>" in key:
                        key = key.replace(f"<<{k}>>", f"{v}")
                if key not in variables:
                    variables[key] = value
        for key, value in list(variables.items()):
            variables[f"{key}_encoded"] = _quote(value)

        default = {k: v for k, v in default.items() if k not in variables}
        resolved_optional: List[str] = []
        for key in optional:
            if "<<" in key and ">>" in key:
                for k, v in variables.items():
                    if f"<<{k}>>" in key:
                        key = key.replace(f"<<{k}>>", f"{v}")
                for k, v in default.items():
                    if f"<<{k}>>" in key:
                        key = key.replace(f"<<{k}>>", f"{v}")
            if key not in variables and key not in default:
                resolved_optional.append(key)
        optional = resolved_optional

        def scan_text(og_txt: Any, var: str, actual_value: Any, second: bool = False) -> Any:
            if og_txt is None:
                return og_txt
            if str(og_txt) == f"<<{var}>>":
                return actual_value
            if f"<<{var}" in str(og_txt):
                final = str(og_txt).replace(f"<<{var}>>", str(actual_value)) if f"<<{var}>>" in str(og_txt) else str(og_txt)
                if f"<<{var}" in final and second:
                    match = re.search(f"<<({re.escape(var)}([+-])(\\d+))>>", final)
                    if match:
                        try:
                            delta = int(match.group(3)) * (-1 if match.group(2) == "-" else 1)
                            final = final.replace(f"<<{match.group(1)}>>", str(int(actual_value) + delta))
                        except (ValueError, TypeError):
                            raise KometaFailed()
                return final
            return og_txt

        def check_for_var(method: str, value: Any) -> Any:
            for _ in range(8):
                start = value
                for option in optional:
                    if option not in variables and f"<<{option}>>" in str(value):
                        raise KometaFailed()
                for variable, variable_data in variables.items():
                    if (variable == "name_format" and method != "name") or (variable == "summary_format" and method != "summary"):
                        continue
                    if variable != "name" and (method not in ("name", "summary") or variable != "key_name"):
                        value = scan_text(value, variable, variable_data)
                if re.search(r"<<\w+[+-]\d+>>", str(value)):
                    for variable, variable_data in variables.items():
                        if variable != "name" and (method not in ("name", "summary") or variable != "key_name"):
                            value = scan_text(value, variable, variable_data, second=True)
                for dm, dd in default.items():
                    if (dm == "name_format" and method != "name") or (dm == "summary_format" and method != "summary"):
                        continue
                    if method not in ("name", "summary") or dm != "key_name":
                        value = scan_text(value, dm, dd)
                if value == start:
                    break
            return value

        def check_data(method: str, value: Any) -> Any:
            if isinstance(value, dict):
                out: Dict[Any, Any] = {}
                for sm, sd in value.items():
                    try:
                        out[check_for_var(method, sm)] = check_data(method, sd)
                    except KometaFailed:
                        continue
                if not out:
                    raise KometaFailed()
                return out
            if isinstance(value, list):
                out_list = []
                for item in value:
                    try:
                        out_list.append(check_data(method, item))
                    except KometaFailed:
                        continue
                if not out_list:
                    raise KometaFailed()
                return out_list
            return check_for_var(method, value)

        for method_name, attr_data in template.items():
            if method_name in data or method_name in ("default", "optional", "conditionals", "move_collection_prefix", "move_prefix"):
                continue
            try:
                new_name = check_for_var(method_name, method_name)
                if new_name not in new_attributes:
                    new_attributes[new_name] = check_data(new_name, copy.deepcopy(attr_data))
            except KometaFailed:
                continue

    return new_attributes


# --------------------------------------------------------------------------
# Loading files
# --------------------------------------------------------------------------

def _load_yaml(text: str) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ImportError_(f"YAML error: {e}")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ImportError_("File is not a YAML mapping")
    return data


def _external_templates(
    data: Dict[str, Any], yaml_files: Dict[str, str], messages: List[str]
) -> Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Templates from external_templates: Kometa's built-in "default: templates",
    or a file: that was uploaded alongside (matched by file name)."""
    found: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    ext = data.get("external_templates")
    if not ext:
        return found
    for entry in _get_list(ext):
        if not isinstance(entry, dict):
            messages.append(f"external_templates entry {entry!r} not understood")
            continue
        temp_vars = entry.get("template_variables") or {}
        text = None
        source = None
        if entry.get("default"):
            name = str(entry["default"]).strip().removesuffix(".yml")
            path = _DEFAULTS_DIR / f"{PurePosixPath(name).name}.yml"
            source = f"Kometa default {name}"
            if path.exists():
                text = path.read_text(encoding="utf-8")
            else:
                messages.append(f"Kometa default template file '{name}' isn't bundled with Simposter")
        elif entry.get("file"):
            wanted = PurePosixPath(str(entry["file"]).replace("\\", "/")).name.lower()
            source = f"file {entry['file']}"
            for fname, ftext in yaml_files.items():
                if PurePosixPath(fname).name.lower() == wanted:
                    text = ftext
                    break
            if text is None:
                messages.append(f"external template {entry['file']} wasn't uploaded; add it to the import")
        else:
            kind = next(iter(entry.keys()), "?")
            messages.append(f"external_templates '{kind}' isn't supported; upload the template file instead")
        if text is None:
            continue
        try:
            tdata = _load_yaml(text)
        except ImportError_ as e:
            messages.append(f"{source}: {e}")
            continue
        for k, v in (tdata.get("templates") or {}).items():
            if k not in found:
                found[k] = (v, temp_vars)
    return found


# --------------------------------------------------------------------------
# Mapping an expanded definition onto an overlay element
# --------------------------------------------------------------------------

def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _offset(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith("%"):
        return text
    n = _num(text)
    if n is None:
        return None
    return int(n) if n == int(n) else n


def _kometa_text(text: str, messages: List[str]) -> str:
    """Kometa text(<<var>>) -> Simposter {var}. Formatting suffixes are dropped."""
    old_special = {f"{a}{s}" for a in ("audience_rating", "critic_rating", "user_rating") for s in ("", "0", "%", "#")}
    if text in old_special:
        text = f"<<{text}>>"

    def repl(m: "re.Match[str]") -> str:
        var = m.group(1)
        base = re.sub(r"[%#]+$", "", var)
        base = re.sub(r"\[.*\]$", "", base)
        if base != var:
            messages.append(f"formatting in <<{var}>> isn't supported; shows the plain value")
        return "{" + base + "}"

    return re.sub(r"<<([^<>]+?)>>", repl, text)


def _text_vars(text: str) -> List[str]:
    return re.findall(r"\{([A-Za-z0-9_.]+)\}", text)


def _regex_escape_list(values: List[Any]) -> str:
    return "|".join(re.escape(str(v)) for v in values)


def _filter_conditions(key: str, value: Any, messages: List[str]) -> Optional[List[Dict[str, Any]]]:
    """One Kometa filter -> engine conditions. None means unsupported."""
    attr, _, modifier = str(key).partition(".")
    attr = attr.strip().lower()
    modifier = modifier.strip().lower()
    spec = _FILTER_FIELDS.get(attr)
    if not spec:
        return None
    field, kind = spec
    values = _get_list(value)
    if modifier != "regex":
        # Kometa splits comma-separated filter values ("label.not: A, B").
        split: List[Any] = []
        for v in values:
            if isinstance(v, str) and "," in v:
                split.extend(p.strip() for p in v.split(",") if p.strip())
            else:
                split.append(v)
        values = split
    if field in RATING_FIELDS:
        msg = _rating_message(field)
        if msg:
            messages.append(msg)

    if kind == "days":
        # Kometa date filters: "added: 7" = added within the last 7 days,
        # "added.not: 7" = not within the last 7 days.
        days = _num(values[0]) if values else None
        if days is None or modifier not in ("", "not"):
            return None
        return [{"field": field, "op": "lte" if modifier == "" else "gt", "value": days}]
    if kind == "status":
        wanted: List[str] = []
        for v in values:
            sv = str(v).strip().lower()
            sv = _TMDB_STATUS_MAP.get(sv, sv) if attr == "tmdb_status" else sv
            if sv and sv not in wanted:
                wanted.append(sv)
        if not wanted or modifier not in ("", "not"):
            return None
        if modifier == "not":
            return [{"field": field, "op": "not_in", "value": wanted}]
        return [{"field": field, "op": "eq", "value": wanted[0]} if len(wanted) == 1
                else {"field": field, "op": "in", "value": wanted}]

    if modifier in ("gt", "gte", "lt", "lte"):
        if kind == "number" or field == "year":
            return [{"field": field, "op": modifier, "value": _num(values[0]) if values else None}]
        return None
    if modifier == "regex":
        pats = [str(v) for v in values]
        return [{"field": field, "op": "regex", "value": pats[0] if len(pats) == 1 else pats}]
    if modifier in ("begins", "ends"):
        pats = [("^" + re.escape(str(v))) if modifier == "begins" else (re.escape(str(v)) + "$") for v in values]
        return [{"field": field, "op": "regex", "value": "(?i)" + "|".join(f"(?:{p})" for p in pats)}]
    if modifier in ("", "is"):
        if kind == "string" and modifier == "":
            if len(values) == 1:
                return [{"field": field, "op": "contains", "value": str(values[0])}]
            return [{"field": field, "op": "regex", "value": "(?i)" + _regex_escape_list(values)}]
        if len(values) == 1:
            return [{"field": field, "op": "eq", "value": values[0] if kind == "number" else str(values[0])}]
        return [{"field": field, "op": "in", "value": [str(v) for v in values]}]
    if modifier in ("not", "isnot"):
        if kind == "string" and modifier == "not":
            return [{"field": field, "op": "not_contains", "value": str(v)} for v in values]
        if len(values) == 1:
            return [{"field": field, "op": "ne", "value": str(values[0])}]
        return [{"field": field, "op": "not_in", "value": [str(v) for v in values]}]
    return None


def _never(reason_field: str) -> Dict[str, Any]:
    """A condition that never passes, so an element whose rule Simposter can't
    check is imported but hidden (visible and editable in its Rules)."""
    return {"field": reason_field, "op": "exists"}


def _resolve_image_source(ov: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """(local file path to match against uploads, url) the way Kometa picks it."""
    file_ = ov.get("file")
    builtin = ov.get("default") or ov.get("pmm") or (
        str(ov.get("git")) if ov.get("git") and str(ov.get("git")).startswith("PMM/") else None
    )
    if not file_ and builtin:
        temp = str(ov.get("default") or ov.get("pmm") or str(ov["git"])[4:])
        if temp.startswith("overlays/images/"):
            temp = temp[16:]
        if not temp.endswith(".png"):
            temp = f"{temp}.png"
        return None, KOMETA_DEFAULT_IMAGES_URL + quote(temp)
    if file_:
        return str(file_), None
    if ov.get("git"):
        return None, KOMETA_GIT_URL + quote(str(ov["git"])) + ".png"
    if ov.get("url"):
        return None, str(ov["url"])
    return None, None


def map_definition(
    mapping_name: str, definition: Dict[str, Any], library_type: str,
    queues: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Expanded definition -> (element or None, report entry)."""
    messages: List[str] = []
    info: List[str] = []  # notes that don't make the overlay a warning
    entry: Dict[str, Any] = {"name": mapping_name, "status": "ok", "messages": messages}
    methods = {str(k).lower(): k for k in definition}

    def get(key: str) -> Any:
        return definition.get(methods[key]) if key in methods else None

    def skip(reason: str):
        entry["status"] = "skipped"
        messages.append(reason)
        return None, entry

    # run_definition / allowed_library_types
    run_key = "run_definition" if "run_definition" in methods else ("allowed_library_types" if "allowed_library_types" in methods else None)
    allowed_types: Optional[set] = None
    if run_key:
        rd = get(run_key)
        if rd is None:
            return skip("run_definition has no value (Kometa skips this overlay)")
        types = set()
        for v in _get_list(rd):
            s = str(v).strip().lower()
            if s == "false":
                return skip("run_definition is false (turned off in this file)")
            if s != "true":
                types.add(s)
        if types:
            allowed_types = types
            if library_type not in types:
                return skip(f"only runs for {', '.join(sorted(types))} libraries")

    ov = get("overlay")
    if ov is None:
        ov = {"name": mapping_name}
    elif not isinstance(ov, dict):
        ov = {"name": str(ov)}
    ov = {str(k).lower(): v for k, v in ov.items()}
    oname = str(ov.get("name") or "").strip()
    if not oname:
        return skip("overlay has no name")
    if "|" in oname:
        return skip("overlay name can't contain '|'")
    element: Dict[str, Any] = {"name": mapping_name}
    conditions: List[Dict[str, Any]] = []

    # Queue: Kometa places the queue's layers, highest weight first, into its positions.
    queue_name = str(ov["queue"]) if ov.get("queue") else None
    if queue_name:
        if ov.get("group"):
            return skip("'group' and 'queue' can't be used together")
        if _num(ov.get("weight")) is None:
            return skip("'queue' needs a 'weight'")
        positions = (queues or {}).get(queue_name)
        if not positions:
            return skip(f"queue '{queue_name}' isn't defined in this file's queues")
        element["queue"] = queue_name
        element["queue_positions"] = positions

    # Group / weight / suppress
    if ov.get("group"):
        weight = _num(ov.get("weight"))
        if weight is None:
            return skip("'group' needs a 'weight'")
        element["group"] = str(ov["group"])
        element["weight"] = int(weight) if weight == int(weight) else weight
    elif ov.get("weight") is not None and _num(ov.get("weight")) is not None:
        element["weight"] = _num(ov.get("weight"))
    sup = get("suppress_overlays")
    if sup:
        element["suppress"] = [str(s) for s in _get_list(sup)]

    # Builders and filters -> conditions
    for key in methods:
        raw = definition[methods[key]]
        if key in ("plex_all",):
            continue
        if key == "plex_search":
            search = raw if isinstance(raw, dict) else {}
            for mode, terms in search.items():
                mode = str(mode).lower()
                terms = terms if isinstance(terms, dict) else {}
                if mode == "any" and len(terms) > 1:
                    messages.append("plex_search 'any' with several fields isn't supported; element hidden")
                    conditions.append(_never("_unsupported_plex_search_any"))
                    continue
                for tk, tv in terms.items():
                    conds = _filter_conditions(str(tk), tv, messages)
                    if conds is None:
                        messages.append(f"plex_search {tk} isn't supported; element hidden")
                        conditions.append(_never(f"_unsupported_{str(tk).replace('.', '_')}"))
                    else:
                        conditions.extend(conds)
            continue
        if key == "filters":
            filters = raw if isinstance(raw, dict) else {}
            for fk, fv in filters.items():
                conds = _filter_conditions(str(fk), fv, messages)
                if conds is None:
                    messages.append(f"filter {fk} isn't supported; element hidden")
                    conditions.append(_never(f"_unsupported_{str(fk).replace('.', '_')}"))
                else:
                    conditions.extend(conds)
            continue
        if key == "mdblist_list":
            urls = []
            for item in _get_list(raw):
                if isinstance(item, dict):
                    if item.get("limit") or item.get("sort_by"):
                        messages.append("mdblist_list limit/sort_by is ignored; every item on the list matches")
                    item = item.get("url")
                if item:
                    urls.append(str(item).strip())
            from .mdblist_client import has_key, normalize_list_url
            norm = [normalize_list_url(u) for u in urls]
            if not urls or not all(norm):
                messages.append(f"mdblist_list {raw} isn't a https://mdblist.com/lists/... URL; element hidden")
                conditions.append(_never("_list_mdblist_list"))
                continue
            if not has_key():
                messages.append("mdblist_list needs an MDBList API key (Settings → General); hidden until one is added")
            conditions.append({"field": "list", "op": "eq", "value": norm[0]} if len(norm) == 1
                              else {"field": "list", "op": "in", "value": norm})
            continue
        if key in _ID_BUILDERS:
            field, kind = _ID_BUILDERS[key]
            ids = []
            for item in _get_list(raw):
                for part in str(item).split(","):
                    part = part.strip()
                    if part.isdigit() and part not in ids:
                        ids.append(part)
            if not ids:
                messages.append(f"{key} has no {kind} IDs; element hidden")
                conditions.append(_never(f"_list_{key}"))
                continue
            info.append(f"{key}: matched by {kind} ID ({len(ids)} item{'s' if len(ids) != 1 else ''}); re-import to pick up changes to the list")
            conditions.append({"field": field, "op": "eq", "value": ids[0]} if len(ids) == 1
                              else {"field": field, "op": "in", "value": ids})
            continue
        if key.startswith(_LIST_BUILDER_PREFIXES):
            messages.append(f"{key} (a list of items) isn't supported yet; element hidden")
            conditions.append(_never(f"_list_{key}"))
            continue
        if key == "builder_level" and raw:
            messages.append(f"builder_level {raw} is ignored (applies to the poster being rendered)")

    if allowed_types and len(allowed_types) == 1:
        only = next(iter(allowed_types))
        if only in ("movie", "show"):
            conditions.append({"field": "media_type", "op": "ne", "value": "tv" if only == "movie" else "movie"})

    # Placement
    h_off = _offset(ov.get("horizontal_offset"))
    v_off = _offset(ov.get("vertical_offset"))
    has_coords = (h_off is not None and v_off is not None) or bool(queue_name)
    if (h_off is None) != (v_off is None) and not queue_name:
        return skip("horizontal_offset and vertical_offset must be used together")

    def placement() -> None:
        element["placement"] = "kometa"
        element["horizontal_align"] = str(ov.get("horizontal_align") or "left").lower()
        element["vertical_align"] = str(ov.get("vertical_align") or "top").lower()
        element["horizontal_offset"] = h_off if h_off is not None else 0
        element["vertical_offset"] = v_off if v_off is not None else 0
        for k in ("back_color", "back_line_color", "back_align"):
            if ov.get(k):
                element[k] = str(ov[k])
        for k in ("back_width", "back_height", "back_radius", "back_padding", "back_line_width"):
            n = _num(ov.get(k))
            if n is not None:
                element[k] = int(n)
        if element.get("back_line_color") and "back_line_width" not in element:
            element["back_line_width"] = 1

    image_path, image_url = _resolve_image_source(ov)

    if oname.startswith("blur"):
        m = re.search(r"\(([^)]+)\)", oname)
        amount = _num(m.group(1)) if m else None
        if amount is None or not 1 <= amount <= 100:
            amount = 50  # Kometa's default for a missing or bad blur value
        element["type"] = "blur"
        element["blur_amount"] = int(amount)
        entry["element_type"] = "blur"
    elif oname.startswith("backdrop"):
        element["type"] = "text_label"
        element["box_only"] = True
        placement()
        element["text"] = ""
        entry["element_type"] = "box"
        if not element.get("back_color") and not element.get("back_line_width"):
            messages.append("backdrop has no back_color, so it draws nothing until you pick a color")
    elif oname.startswith("text"):
        m = re.search(r"\((.+)\)", oname)
        if not m:
            return skip(f"couldn't read text from {oname}")
        if not has_coords:
            return skip("text overlays need horizontal_offset and vertical_offset")
        element["type"] = "text_label"
        placement()
        text = _kometa_text(m.group(1), messages)
        element["text"] = text
        element["font_size"] = int(_num(ov.get("font_size")) or 36)
        if ov.get("font_color"):
            element["font_color"] = str(ov["font_color"])
        if _num(ov.get("stroke_width")):
            element["stroke_width"] = int(_num(ov["stroke_width"]))
        if ov.get("stroke_color"):
            element["stroke_color"] = str(ov["stroke_color"])
        font = str(ov.get("font") or "Roboto-Medium.ttf")
        element["font_family"] = PurePosixPath(font.replace("\\", "/")).stem
        entry["font"] = font
        if ov.get("font_style"):
            element["font_style"] = str(ov["font_style"])
        if image_path or image_url:
            # Image drawn next to the text (Kometa's text addon).
            pos = str(ov.get("addon_position") or "left").lower()
            element["addon_position"] = pos if pos in ("left", "right", "top", "bottom") else "left"
            off = _num(ov.get("addon_offset"))
            if off:
                element["addon_offset"] = int(off)
            sw, sh = ov.get("scale_width"), ov.get("scale_height")
            if sw or sh:
                pct = str(sw or sh)
                if pct.endswith("%") and _num(pct[:-1]) is not None:
                    element["addon_scale"] = _num(pct[:-1]) / 100
                else:
                    entry["scale_px"] = {"width": _num(sw), "height": _num(sh)}
            if image_url:
                element["url"] = image_url
            if image_path:
                entry["image"] = image_path
        for var in _text_vars(text):
            if var in RATING_FIELDS or var in MDBLIST_RATING_FIELDS:
                msg = _rating_message(var)
                if msg:
                    messages.append(msg)
            elif var not in KNOWN_FIELDS:
                messages.append(f"variable {{{var}}} isn't filled by Simposter; the text is skipped when it's missing")
        entry["element_type"] = "text"
    else:
        if not image_path and not image_url:
            image_path = f"{oname}.png"  # Kometa's overlay folder: <name>.png
        if has_coords:
            element["type"] = "custom_image"
            placement()
            sw, sh = ov.get("scale_width"), ov.get("scale_height")
            if sw or sh:
                pct = str(sw or sh)
                if pct.endswith("%") and _num(pct[:-1]) is not None:
                    element["scale"] = _num(pct[:-1]) / 100
                else:
                    entry["scale_px"] = {"width": _num(sw), "height": _num(sh)}
            entry["element_type"] = "image"
        else:
            element["type"] = "full_cover_image"
            entry["element_type"] = "full image"
        if image_url:
            element["url"] = image_url
        if image_path:
            entry["image"] = image_path

    if conditions:
        element["conditions"] = conditions
    messages[:] = list(dict.fromkeys(messages))
    has_warnings = bool(messages)
    messages.extend(m for m in dict.fromkeys(info) if m not in messages)
    if any(c.get("op") == "exists" and str(c.get("field", "")).startswith("_") for c in conditions):
        entry["status"] = "hidden"
    elif has_warnings:
        entry["status"] = "warning"
    return element, entry


# --------------------------------------------------------------------------
# One overlay file
# --------------------------------------------------------------------------

def _fill_vars(text: str, *dicts: Dict[str, Any]) -> str:
    for d in dicts:
        for k, v in d.items():
            text = text.replace(f"<<{k}>>", str(v))
    return text


def parse_queues(raw: Any, temp_vars: Dict[str, Any], messages: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """A file's queues -> {name: [positions]}, following Kometa's OverlayFile:
    a list of positions, or a dict of named position lists with an optional
    settings block (position, overlay_limit, default, dynamic_position). Each
    position inherits the align/offset keys it leaves out from the one before."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    keys = ("horizontal_align", "vertical_align", "horizontal_offset", "vertical_offset")
    position = temp_vars.get("position") or None
    limit_all = _num(temp_vars.get("overlay_limit"))
    for name, queue in raw.items():
        name = str(name)
        queue_position = temp_vars.get(f"position_{name}") or position
        limit = limit_all
        defaults: Dict[str, Any] = {k: None for k in keys}
        settings = queue.get("settings") if isinstance(queue, dict) else None
        if isinstance(settings, dict):
            if settings.get("position") and not queue_position:
                queue_position = settings["position"]
            if settings.get("overlay_limit") is not None and limit is None:
                limit = _num(settings["overlay_limit"])
            for k, v in (settings.get("default") or {}).items():
                defaults[k] = v
            if settings.get("conditionals"):
                messages.append(f"queue '{name}': conditionals aren't supported; their default values are used")
                for k, v in settings["conditionals"].items():
                    if isinstance(v, dict) and "default" in v:
                        defaults[k] = v["default"]
            dyn = settings.get("dynamic_position")
            if isinstance(dyn, dict) and dyn and not queue_position:
                def dv(key, default):
                    val = dyn.get(key, default)
                    return _fill_vars(str(val), temp_vars, defaults) if val is not None else default
                v_align = str(dv("initial_vertical_align", "top")).lower()
                h_align = str(dv("initial_horizontal_align", "left")).lower()
                v0 = int(_num(dv("initial_vertical_offset", 0)) or 0)
                h0 = int(_num(dv("initial_horizontal_offset", 0)) or 0)
                vs = int(_num(dv("vertical_spacing", 0)) or 0)
                hs = int(_num(dv("horizontal_spacing", 0)) or 0)
                surround = str(dv("surround", False)).lower() in ("true", "1", "yes")
                queue_position = [{
                    "vertical_align": v_align if v_align in ("top", "center", "bottom") else "top",
                    "horizontal_align": h_align if h_align in ("left", "center", "right") else "left",
                    "vertical_offset": v0, "horizontal_offset": h0,
                }]
                for x in range(20):
                    factor = ((x // 2 + 1) * (-1 if x % 2 == 1 else 1)) if surround else (x + 1)
                    queue_position.append({"vertical_offset": v0 + factor * vs, "horizontal_offset": h0 + factor * hs})
        initial = None
        if isinstance(queue_position, list) and queue_position:
            initial = queue_position
        elif isinstance(queue, list):
            initial = queue
        elif isinstance(queue, dict):
            if queue_position:
                key = _fill_vars(str(queue_position), temp_vars, defaults)
                if key in queue:
                    initial = queue[key]
                else:
                    messages.append(f"queue '{name}': position '{key}' doesn't exist; queue skipped")
                    continue
            if not initial:
                initial = next((v for k, v in queue.items() if k != "settings"), None)
        if not isinstance(initial, list):
            messages.append(f"queue '{name}' must be a list of positions; queue skipped")
            continue
        final: List[Dict[str, Any]] = []
        ok = True
        for pos in initial:
            pos = pos if isinstance(pos, dict) else {}
            for k in keys:
                if k in pos:
                    defaults[k] = pos[k]
            if any(defaults[k] is None for k in keys):
                messages.append(f"queue '{name}' is missing an align or offset; queue skipped")
                ok = False
                break
            final.append({
                "horizontal_align": str(defaults["horizontal_align"]).lower(),
                "vertical_align": str(defaults["vertical_align"]).lower(),
                "horizontal_offset": _offset(defaults["horizontal_offset"]) or 0,
                "vertical_offset": _offset(defaults["vertical_offset"]) or 0,
            })
            if limit and len(final) >= limit:
                break
        if ok and final:
            out[name] = final
    return out


def expand_file(
    text: str, library_type: str, yaml_files: Dict[str, str], config_vars: Optional[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Returns (elements, report entries, file-level messages)."""
    data = _load_yaml(text)
    file_messages: List[str] = []
    if not data:
        # UMTK/TSSK write a comment-only file when nothing matches right now.
        return [], [], ["The file has no overlays right now (empty or only comments); the overlay is saved with no layers."]
    overlays = data.get("overlays")
    if overlays is None and "overlays" in data:
        return [], [], ["The file's overlays section is empty; the overlay is saved with no layers."]
    if not isinstance(overlays, dict) or not overlays:
        raise ImportError_("No 'overlays:' section (is this a Kometa overlay file?)")
    queues = parse_queues(data.get("queues"), config_vars or {}, file_messages)

    templates: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    for k, v in (data.get("templates") or {}).items():
        templates[k] = (v, {})
    for k, v in _external_templates(data, yaml_files, file_messages).items():
        if k not in templates:
            templates[k] = v

    elements: List[Dict[str, Any]] = []
    report: List[Dict[str, Any]] = []
    for mapping_name, definition in overlays.items():
        mapping_name = str(mapping_name)
        if not isinstance(definition, dict):
            definition = {"overlay": definition} if definition else {}
        definition = copy.deepcopy(definition)
        methods = {str(k).lower(): k for k in definition}
        try:
            if "template" in methods:
                new_vars = definition.get(methods["variables"]) if "variables" in methods else {}
                if new_vars is not None and not isinstance(new_vars, dict):
                    raise ImportError_("variables must be a dictionary")
                name = definition.get(methods["name"]) if "name" in methods else None
                attrs = apply_template(
                    templates, name, mapping_name, definition, definition[methods["template"]],
                    new_vars or {}, library_type=library_type, config_vars=config_vars,
                )
                for attr, value in attrs.items():
                    if str(attr).lower() not in methods:
                        definition[attr] = value
                        methods[str(attr).lower()] = attr
            element, entry = map_definition(mapping_name, definition, library_type, queues)
        except ImportError_ as e:
            element, entry = None, {"name": mapping_name, "status": "skipped", "messages": [str(e)]}
        except Exception as e:  # never let one definition kill the file
            element, entry = None, {"name": mapping_name, "status": "skipped", "messages": [f"couldn't expand: {e}"]}
        report.append(entry)
        if element is not None:
            elements.append(element)
    return elements, report, file_messages


# --------------------------------------------------------------------------
# Uploaded bundle (yml files, images, fonts, zips)
# --------------------------------------------------------------------------

MAX_TOTAL_BYTES = 300 * 1024 * 1024
MAX_FILES = 3000


def collect_uploads(uploads: List[Tuple[str, bytes]]) -> Dict[str, Dict[str, bytes]]:
    """Sort uploads (zips expanded) into {"yaml": {path: bytes}, "image": ..., "font": ...}.
    Paths are the relative path the browser sent (or the path inside a zip)."""
    out: Dict[str, Dict[str, bytes]] = {"yaml": {}, "image": {}, "font": {}}
    total = 0
    count = 0

    def add(path: str, content: bytes) -> None:
        nonlocal total, count
        path = path.replace("\\", "/").lstrip("/")
        suffix = PurePosixPath(path).suffix.lower()
        kind = "yaml" if suffix in YAML_EXTS else "image" if suffix in IMAGE_EXTS else "font" if suffix in FONT_EXTS else None
        if not kind:
            return
        if any(part in ("__MACOSX",) or part.startswith("._") for part in PurePosixPath(path).parts):
            return
        total += len(content)
        count += 1
        if total > MAX_TOTAL_BYTES or count > MAX_FILES:
            raise ImportError_("Upload is too large")
        out[kind][path] = content

    for name, content in uploads:
        if name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for info in zf.infolist():
                        if info.is_dir() or info.file_size > MAX_TOTAL_BYTES:
                            continue
                        add(info.filename, zf.read(info))
            except zipfile.BadZipFile:
                raise ImportError_(f"{name} isn't a valid zip")
        else:
            add(name, content)
    return out


def match_upload(wanted: str, available: Dict[str, bytes]) -> Optional[str]:
    """Best uploaded path for a Kometa file path: the most matching trailing path
    parts, at least the file name."""
    want_parts = [p.lower() for p in PurePosixPath(wanted.replace("\\", "/")).parts if p not in ("/", ".")]
    if not want_parts:
        return None
    best, best_score = None, 0
    for path in available:
        parts = [p.lower() for p in PurePosixPath(path).parts]
        score = 0
        while score < len(parts) and score < len(want_parts) and parts[-1 - score] == want_parts[-1 - score]:
            score += 1
        if score > best_score:
            best, best_score = path, score
    return best if best_score >= 1 else None
