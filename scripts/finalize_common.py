"""Shared helpers of finalize.py: constants, JSON loading, machine paths, parameters and settings."""
from __future__ import annotations

from types import SimpleNamespace
import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate  # noqa: E402


SCHEMA = "3dprint-scout.finalize/1"

MANIFEST_3MF = "3dprint-scout.3mf-manifest/1"

ENGINES_DIR = os.path.join(os.path.dirname(HERE), "references", "engines")

DIRECTIONS = ("front", "back", "left", "right", "top", "bottom")

COVERAGE = ("real", "estimated", "assumed", "none")

PRINT_STATUS = ("passed", "failed", "skipped", "offered", "pending")

SETTINGS = ("tol", "printer", "printer_id", "tools", "overhang_angle", "min_wall")

# The use tier: what the user was promised, and the evidence that it holds.
KINDS = ("use", "feature", "look")

EVIDENCE = ("joint", "strength", "measurement", "seen", "test_print")

ALLOWED = {"use": ("joint", "strength", "measurement", "test_print"), "feature": ("joint", "measurement", "test_print"),
           "look": ("seen", "test_print")}

SEEN_KEYS = ("name", "image", "image_sha256", "by", "promises", "result", "note")

IMAGE_SCHEMA = "3dprint-scout.image/1"

NEEDS = {"use": ("conditions", "success"), "feature": ("success",), "look": ()}

PROMISE_KEYS = ("id", "kind", "text", "conditions", "success", "evidence", "assumes", "note")

DIM_SOURCES = ("assumed", "caliper", "spec", "user-file")

DIM_STATE = {"assumed": "assumed", "caliper": "measured", "spec": "spec", "user-file": "measured"}

DIM_KEYS = ("id", "what", "unit", "params", "source", "tol", "by", "url", "where", "from", "note")

STATES = ("error", "failed", "not verified", "excluded", "assumed", "accepted", "verified")

DECIDED_KEYS = ("check", "result", "reason", "sha256")

DECIDED_RESULTS = ("holds", "warn")


class FinalizeError(Exception):
    pass


class JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise FinalizeError(f"usage: {message}")


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as exc:
        raise FinalizeError(f"{what} {path}: {exc.strerror or exc}")
    except ValueError as exc:
        raise FinalizeError(f"{what} {path}: not JSON ({exc})")


LIBRARY_PLACES = ((ENGINES_DIR, ("references", "engines")), (HERE, ("scripts",)))   # folder, its place in a skill


def skill_library(path):
    """This skill's own file for a recorded source that is one of the skill's library files
    (blender_builder.py, parts.py, ...) at its place in a skill folder that is not there any more:
    `.../references/engines/blender_builder.py` or `.../scripts/parts.py`. None for anything else,
    and for a path that exists (it is read as it is)."""
    if not isinstance(path, str) or os.path.isfile(path):
        return None
    bits = [b for b in path.replace("\\", "/").split("/") if b]
    for folder, place in LIBRARY_PLACES:
        n = len(place)
        if len(bits) > n and tuple(bits[-1 - n:-1]) == place and os.path.isfile(os.path.join(folder, bits[-1])):
            return os.path.join(folder, bits[-1])
    return None


def source_file(path):
    """A build's recorded source as the file to read now. A skill library file recorded relative to
    the folder the build ran in is gone once that folder moves, or on another machine where the skill
    is installed elsewhere: it is this skill's file of that name. Its hash still decides freshness,
    so a skill whose library changed still asks for a new build."""
    return skill_library(path) or path


def rel(path):
    """A path as the report shows it: relative to the working folder (no machine path)."""
    if not path:
        return path
    try:
        r = os.path.relpath(path)
    except ValueError:                                   # another drive on Windows
        return os.path.basename(path)
    return os.path.basename(path) if r.startswith("..") else r.replace(os.sep, "/")


def machine_prefixes():
    """Absolute folders of this machine that must not leave it in a report or bundle."""
    out = []
    for p in (os.getcwd(), os.path.realpath(os.getcwd()), os.path.expanduser("~")):
        if p and len(p) > 3 and p not in out:
            out.append(p)
    return sorted(out, key=len, reverse=True)


def path_forms(p):
    """The ways a folder is written in a report or a source: as is, with forward slashes, with
    the doubled backslashes of JSON text, JSON-escaped (\\uXXXX for non-ASCII), and a Windows
    drive as MSYS / WSL write it (/c/Users/..., /mnt/c/Users/...)."""
    p = p.rstrip("/\\") or p
    fwd = p.replace("\\", "/")
    forms = {p, fwd, p.replace("\\", "\\\\"), json.dumps(p)[1:-1], json.dumps(fwd)[1:-1],
             json.dumps(p, ensure_ascii=False)[1:-1]}
    m = re.match(r"^([A-Za-z]):/(.*)$", fwd)
    if m:
        forms |= {f"/{m.group(1).lower()}/{m.group(2)}", f"/mnt/{m.group(1).lower()}/{m.group(2)}"}
    return sorted(forms, key=len, reverse=True)


def machine_forms():
    """(form, stand-in) for every form of this machine's folders, longest first."""
    home = os.path.expanduser("~")
    out = [(f, "~" if p == home else ".") for p in machine_prefixes() for f in path_forms(p)]
    return sorted(out, key=lambda x: len(x[0]), reverse=True)

# A machine folder is matched as a whole folder, never as the tail or the start of another name:
# not after a letter, digit or one of `_.~-` (src/root/x is not the home /root), except after an
# option letter (-I/home/ann/inc), and not before a letter, digit, `_` or `-` (/home/anne is not
# /home/ann). The same rule in the report (scrub) and in the files a bundle carries.
FORM_BEFORE = r"(?:(?<=-[A-Za-z])|(?<![\w.~-]))"

FORM_AFTER = r"(?![\w-])"


def scrub(text):
    """The report's text with this machine's folders taken out wherever they appear, in any
    case and form (a file:// link, after -I, in a JSON escape): the working folder becomes `.`,
    the home folder `~`. Never applied to REPRODUCE.md's commands, which hold relative paths."""
    for form, stand_in in machine_forms():
        text = re.sub(FORM_BEFORE + re.escape(form) + FORM_AFTER, lambda _m, s_=stand_in: s_, text,
                      flags=re.IGNORECASE)
    return text


def part_specs(params):
    parts = params.get("_parts")
    if parts is None:
        parts = {}
    if not isinstance(parts, dict):
        raise FinalizeError("_parts in params.json must be an object")
    for name, spec in parts.items():
        if spec is not None and not isinstance(spec, dict):
            raise FinalizeError(f"_parts in params.json: entry {name!r} must be an object or null")
    return {str(k): dict(v or {}) for k, v in parts.items()}


def norm(text):
    """A check or joint name as names are compared: single spaces, lower case."""
    return " ".join(str(text).split()).lower()

PROTOTYPE = re.compile(r"^\s*(\S+): delivered as a prototype, not verified(?:\s+\(.*\))?\s*$")


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def check_verify_shape(verify):
    lists = {"joints": dict, "strength": dict, "measurements": dict, "seen": dict, "test_prints": dict, "accepted": dict,
             "decided": dict, "unverified": str,
             "promises": dict, "dims": dict}
    for key, item in lists.items():
        if key in verify:
            v = verify[key]
            if not isinstance(v, list) or not all(isinstance(x, item) for x in v):
                kind = "objects" if item is dict else "strings"
                raise FinalizeError(f"_verify.{key} must be a list of {kind}")
    for key in ("joints", "strength", "measurements"):
        for e in verify.get(key) or []:
            bad = [f for f in ("name", "report", "proxy_build") if f in e and not isinstance(e[f], str)]
            if key == "joints" and "sweep" in e and not isinstance(e["sweep"], bool):
                raise FinalizeError(f"_verify.joints: sweep must be true or false ({json.dumps(e, ensure_ascii=False)})")
            if bad:
                raise FinalizeError(f"_verify.{key}: {' and '.join(bad)} must be text ({json.dumps(e, ensure_ascii=False)})")
    if "references" in verify and not (isinstance(verify["references"], dict)
                                       and all(isinstance(v, dict) for v in verify["references"].values())):
        raise FinalizeError("_verify.references must map each object to {direction: coverage}")


def settings_for(build, args):
    """The validation settings: the build's, replaced by any given here."""
    s = dict(build.get("validate_settings") or {})
    for f in SETTINGS:
        v = getattr(args, f, None)
        if v is not None:
            s[f] = v
    if args.wall_check is False:
        s["wall_check"] = False
    s.setdefault("wall_check", True)
    return SimpleNamespace(**{f: s.get(f) for f in SETTINGS}, wall_check=s["wall_check"])

VALIDATE_DEFAULTS = {"tol": 0.1, "tools": "0", "overhang_angle": 45.0, "min_wall": 1.2}   # validate.py's own


def _setting(f, v):
    """A setting as validate.py will use it: its default when not given; tools as a set."""
    if v is None:
        v = VALIDATE_DEFAULTS.get(f)
    if v is None:
        return None
    if f == "tools":
        return frozenset(x.strip() for x in str(v).split(",") if x.strip())
    if f in ("tol", "overhang_angle", "min_wall"):
        try:
            return round(float(v), 9)
        except (TypeError, ValueError):
            return str(v)
    return str(v)


def settings_drift(build, settings):
    """What differs between the settings the build judged its objects with and this report's
    (a field given here, or the printers.json changed since): the build's object checks do not
    hold for these."""
    b = build.get("validate_settings") or {}
    out = []
    for f in SETTINGS:
        old, new = b.get(f), getattr(settings, f)
        if f == "printer":
            same = (not old and not new) or bool(old and new and os.path.normcase(os.path.abspath(old)) ==
                                                  os.path.normcase(os.path.abspath(new)))
        else:
            same = _setting(f, old) == _setting(f, new)       # --tools 0 and no --tools are the same
        if not same:
            if f == "printer":                                # as the report shows paths: relative, with /
                old, new = (rel(v) if isinstance(v, str) else v for v in (old, new))
            out.append(f"{f} {old} -> {new}")
    if bool(b.get("wall_check", True)) != bool(settings.wall_check):
        out.append("wall_check")
    pr = settings.printer
    same_file = bool(pr and b.get("printer") and os.path.normcase(os.path.abspath(pr)) ==
                     os.path.normcase(os.path.abspath(b["printer"])))
    if same_file and b.get("printer_sha256") and os.path.isfile(pr) and validate.file_sha256(pr) != b["printer_sha256"]:
        out.append(f"{rel(pr)} changed since the build")
    return out


def effective_material(params, specs, name):
    """A part's material as params.json declares it now: _parts.<name>.material, else _material."""
    return (specs.get(name) or {}).get("material") or params.get("_material")

LINKED_ORIGINS = ("param:", "table:", "default:", "build:")    # strength.py inputs_from that nobody typed in


def lookup(params, key):
    """A params.json value by its key, or by a dotted path into nested objects ("phone.t")."""
    if key in params:
        return True, params[key]
    cur = params
    for k in str(key).split("."):
        if not (isinstance(cur, dict) and k in cur):
            return False, None
        cur = cur[k]
    return True, cur


def flatten(d, prefix=""):
    """Nested parameters as dotted leaf paths ({"plug": {"w": 13}} -> {"plug.w": 13}), so a dims
    entry bound to "plug.w" and a proxy given {"plug": {"w": 13}} name the same number."""
    out = {}
    for k, v in d.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict) and v:
            out.update(flatten(v, path + "."))
        else:
            out[path] = v
    return out


def same_value(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return a == b


def text_field(entry, key):
    v = entry.get(key)
    return isinstance(v, str) and bool(v.strip())


def finite(v):
    """A real, finite number; an integer too large for a float (10**400 in edited JSON) is not."""
    try:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    except OverflowError:
        return False


def valid_check_entry(a):
    """An accepted WARN: a check name and the user's reason, both in words, and no promise."""
    return "promise" not in a and isinstance(a.get("check"), str) and bool(a["check"].strip()) and text_field(a, "reason")

SCAN_ENCODINGS = ("utf-8", "utf-16-le", "utf-16-be", "latin-1", "cp1252")   # what a text file may be saved in


def _byte_bounds(enc):
    """FORM_BEFORE and FORM_AFTER as byte patterns for a form encoded in `enc` (the marks are
    ASCII: one byte, or a two-byte unit in UTF-16)."""
    before, after = rb"[A-Za-z0-9_.~\-]", rb"[A-Za-z0-9_\-]"
    if enc == "utf-16-le":
        return rb"(?:(?<=-\x00[A-Za-z]\x00)|(?<!" + before + rb"\x00))", rb"(?!" + after + rb"\x00)"
    if enc == "utf-16-be":
        return rb"(?:(?<=\x00-\x00[A-Za-z])|(?<!\x00" + before + rb"))", rb"(?!\x00" + after + rb")"
    return rb"(?:(?<=-[A-Za-z])|(?<!" + before + rb"))", rb"(?!" + after + rb")"


def machine_byte_patterns():
    """[(pattern, its forms in lower case)], one per encoding in SCAN_ENCODINGS, matching every form
    of this machine's folders that the encoding can write (a folder with a non-Latin letter has
    no Latin-1 form). The forms let a file without any of them be passed over quickly."""
    pats = {}
    for enc in SCAN_ENCODINGS:
        forms = set()
        for form, _ in machine_forms():
            try:
                forms.add(form.encode(enc, "surrogateescape" if enc == "utf-8" else "strict"))
            except UnicodeEncodeError:
                continue
        if forms:
            before, after = _byte_bounds(enc)
            pat = before + b"(?:" + b"|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True)) + b")" + after
            pats.setdefault(pat, {f.lower() for f in forms})     # Latin-1, cp1252 and UTF-8 write ASCII alike
    return [(re.compile(p, re.IGNORECASE), lows) for p, lows in pats.items()]


def holds_machine_path(path):
    """Whether a file holds a folder of this machine, in any form machine_forms knows, searched in
    its bytes as each encoding in SCAN_ENCODINGS writes it (decoded as UTF-8 alone, a Latin-1
    file hides /home/josé)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return False
    low = data.lower()                                   # ASCII letters only, as IGNORECASE folds bytes
    return any(any(f in low for f in lows) and p.search(data) for p, lows in machine_byte_patterns())


def same_file(a, b):
    try:
        return bool(a and b) and os.path.samefile(a, b)
    except OSError:
        return False
