#!/usr/bin/env python3
"""
calibration.py - the user's own print results, per printer, material and nozzle, kept in the
project at .3dprint/calibration.json (never in the skill): which fit-test ring fit, which
mechanism member broke or held and under what load, measured clearances. Read in Phase 2;
a value measured here, under the same conditions, beats the official spec and the starting
points in design.md. A user-level file in the home folder, ~/.3dprint/calibration.json (the
same schema; THREEDPRINT_USER_CALIBRATION names another path), carries results from one
project to the next: `lookup` and `show` read it after the project file, `add --user` writes it.

  python3 calibration.py add --file .3dprint/calibration.json --printer x2d --material pla_basic --nozzle 0.4 \\
      --layer 0.2 --orientation flat --process "0.20mm Standard @BBL X2D" \\
      --feature fit --result fits --value clearance_per_side_mm=0.3 --value profile_w_mm=45.1 \\
      --note "ring 2 of the fit test slid on by hand without rattle"
  python3 calibration.py add --file .3dprint/calibration.json --printer x2d --material pla_pure --nozzle 0.4 \\
      --layer 0.2 --feature mechanism --kind latch --result failed \\
      --value pin_d_mm=2.6 --value pin_wall_mm=1.3 --value arm_mm=1.2 \\
      --load finger_push --note "print-in-place draw latch: pins, rings and arms broke on first use"
  python3 calibration.py add --user --printer x2d --material pla_basic --nozzle 0.4 --feature fit --result fits \\
      --value housing_w_mm=60.5 --note "sleeve slid onto the housing by hand"      # the user-level file
  python3 calibration.py show --file .3dprint/calibration.json
  python3 calibration.py lookup --file .3dprint/calibration.json --printer x2d --material pla_basic --nozzle 0.4 --feature fit
  python3 calibration.py lookup --file .3dprint/calibration.json --printer x2d --material pla_basic --nozzle 0.4 \\
      --layer 0.2 --orientation flat --feature mechanism --kind lid_hinge

Schema (3dprint.calibration/1): {"schema", "entries": [{"date", "printer", "material", "nozzle_mm",
"layer_mm"?, "orientation"?: a short lowercase id (flat, upright, on_side: how the part lay on the
bed), "process"?: the slicer process preset as the user calls it ("0.20mm Standard @BBL X2D"; one
line of text, 80 characters at most), "feature": fit | mechanism | clearance | hole | other,
"kind"?: a short lowercase id (latch, lid_hinge, lever, clamp, snap: the kind of member, so a floor
applies to the same kind under the same kind of load), "result": fits | tight | loose | worked |
failed | measured, "values": {name: number}, "load"?: number N or a strength.py key, "note"}]}.
Values are finite numbers under 10 000 (mm, N, counts). `kind` is optional for every feature and
meant for mechanism entries; `layer_mm`, `orientation`, `process` and `load` are optional too;
files written without them still load. What the script can recognise
as identifying a person or a machine is refused: value names with id, uid, code, device, mac,
serial, token, account, mail, ip, user, name, key or secret in them; notes with an IPv4, IPv6 or
MAC address, an e-mail address, a run of six or more digits or a long mixed letter-digit token
(serial numbers, access codes), or the words serial, access code, account, password; printers
and materials must be short lowercase ids (x2d, pla_basic; "PLA Basic" is stored as pla_basic,
the strength.py key), never a person's name. It cannot
recognise a name in a note: the agent never writes one.

`lookup` matches on every condition the query gives. --printer, --material, --feature and
--kind select entries; --nozzle, --layer, --load, --orientation and --process are conditions.
An entry that records each given condition with the same value (numbers within 1e-6, a load key
as the same key, the process name regardless of case and repeated spaces) is a same-condition
entry, listed under "entries" newest first (date, then file order). One that differs in a given
condition, or does not record it, is listed under "reference" with "differs" ({field: [the
entry's value or "not recorded", the query's value]}): seen, never a recommendation or a floor.
From the same-condition entries only, per value name: "worked", the newest number from an entry
that fit, worked or was measured, and "bounds", the newest failed, tight and loose numbers, kept
apart so a failure is never read as a setting; every number carries its "date" and "entry" (its
position in the file, from 0). "worked" can take names from different prints: then "combined" is
true and a warning says those values were never printed together as a set; "worked_set" is the
newest same-condition entry that fit, worked or was measured, with all its values together (one
print, one set). Without --nozzle a warning says every nozzle is mixed; without --layer, --load,
--orientation or --process a warning names any of them the same-condition entries record
differently. Every listed entry carries "entry".
With --kind K only entries of that kind set "worked" and "bounds"; matching entries without a
kind are listed under "unclassified" (with "differs" when they differ in a condition) so they are
seen but set no floor for K (a stub pin that broke in a hand-operated latch is not the floor for
a lid hinge's integral pin). Without --kind every matching entry counts, as before, and "kinds"
says how many entries each kind has among those matching printer, material and feature, under
any conditions.
Two files. `lookup` and `show` read the project file (--file) and then the user-level file
(~/.3dprint/calibration.json, or the path in THREEDPRINT_USER_CALIBRATION; --no-user skips it;
read once when it is the project file). Every listed entry, value and set says where it came
from: "from": "project" or "user", and "entry" is its position in that file. Project entries
take precedence: they come first (newest first), then the user-level ones (newest first), so a
same-condition project value sets "worked", "worked_set" and "bounds" before a user-level one.
A user-level file that cannot be read (not JSON, not a calibration file, an entry the checks
refuse) is left out of `lookup` and `show` with a warning; it is never rewritten. "user_file"
names it (~ for the home folder), null with --no-user.
`add` writes the project file (--file); `add --user` writes the user-level file instead
(making ~/.3dprint/ when needed), only after the user agreed to keep the result for every
project. Neither overwrites a file that cannot be read: it is refused, as it is.
Never written without the user's yes (SKILL.md): the agent asks once after a print result, then
runs `add`. Prints one JSON document; exit 0 on success, 1 on error. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import re
import sys

SCHEMA = "3dprint.calibration/1"
USER_ENV = "THREEDPRINT_USER_CALIBRATION"              # another path for the user-level file (tests, a shared folder)
USER_DEFAULT = os.path.join("~", ".3dprint", "calibration.json")
SOURCES = ("project", "user")                          # where an entry came from, in order of precedence
FEATURES = ("fit", "mechanism", "clearance", "hole", "other")
RESULTS = ("fits", "tight", "loose", "worked", "failed", "measured")
GOOD_RESULTS = ("fits", "worked", "measured")          # the only results a value is taken from
MAX_VALUE = 1e4                                        # mm, N or counts: anything larger is not a print result
# Tokens of a value name (split on _ and digits) that point at a person or a machine.
FORBIDDEN_TOKENS = {"id", "ids", "uid", "uuid", "guid", "code", "codes", "dev", "device", "mac", "serial", "sn", "token",
                    "account", "acct", "mail", "email", "ip", "ipv4", "ipv6", "user", "owner", "name", "key", "secret",
                    "password", "passcode", "phone", "address", "login"}
FORBIDDEN_WORDS = re.compile(r"(serial|access\s*code|account|password|passcode|\buid\b|\bsn\b|user\s*id|token)", re.I)
IPV4_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
IPV6_RE = re.compile(r"\b(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{1,4}\b", re.I)
MAC_RE = re.compile(r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", re.I)
DIGITS_RE = re.compile(r"\d{6,}")
MIXED_RE = re.compile(r"\b(?=[0-9a-z]*\d)(?=[0-9a-z]*[a-z])[0-9a-z]{10,}\b", re.I)     # long letter-digit tokens
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
ID_RE = re.compile(r"[a-z0-9][a-z0-9._+-]{0,39}")
KIND_RE = re.compile(r"[a-z][a-z0-9_]{0,23}")           # kind and orientation: latch, lid_hinge; flat, on_side
UNCLASSIFIED = "unclassified"                           # lookup's name for entries without a kind; not a valid kind
KIND_HINT = ("the kind of member", "latch, lid_hinge, lever, clamp, snap")
ORIENTATION_HINT = ("how the part lay on the bed", "flat, upright, on_side")
PROCESS_MAX = 80                                        # characters of a slicer process preset name
# lookup's conditions, as entry fields, in the order they are reported; the query's option for each.
CONDITIONS = (("nozzle_mm", "nozzle"), ("layer_mm", "layer"), ("load", "load"), ("orientation", "orientation"),
              ("process", "process"))
NOT_RECORDED = "not recorded"
NUM_TOL = 1e-6
LOAD_KEYS = ("finger_push", "finger_press", "finger_pull", "pinch_lateral", "pinch_palmar", "grasp")
MATERIAL_KEYS = re.compile(r"(pla|petg|abs|asa|tpu|pa|pc|pet|pps|peek|ppa|pva|hips)(_[a-z0-9]{1,12}){0,3}")   # pla_basic, petg_hf, pla_cf


class CalibrationError(Exception):
    pass


class _JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise CalibrationError(f"usage error: {message}")


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
def material_key(value):
    """'PLA Basic' or 'pla-basic' -> pla_basic, the same spelling strength.py uses, so one log
    serves both scripts; anything else is passed on unchanged to the id check."""
    text = str(value or "").strip()
    key = text.lower().replace("-", "_").replace(" ", "_")
    return key if MATERIAL_KEYS.fullmatch(key) else text


def normalize_id(what: str, value) -> str:
    """A short lowercase id like x2d, a1_mini or pla_basic: no spaces, no capitals, so a person's
    name or a free text is refused by shape (the script cannot tell a name from an id otherwise)."""
    text = str(value or "").strip()
    if not text:
        raise CalibrationError(f"{what} is required")
    if not ID_RE.fullmatch(text):
        raise CalibrationError(f"{what} must be a short lowercase id without spaces (x2d, a1_mini, pla_basic), as in "
                               f"printers.json or strength.py: got {value!r}")
    if FORBIDDEN_WORDS.search(text) or id_tokens(text) & FORBIDDEN_TOKENS:
        raise CalibrationError(f"{what} {value!r} looks like an identifier of a person or a machine; use the printer model "
                               "or the id from printers.json")
    return text


def id_tokens(text: str) -> set:
    """The words of an id, split on separators and on letter-digit boundaries (user1 -> user, 1)."""
    return set(re.split(r"[^a-z0-9]+|(?<=[a-z])(?=\d)", text))


def short_id(what: str, value, hint: tuple, reserved: str = "") -> str:
    """A short lowercase id (a letter, then letters, digits or underscores, 24 at most) through
    the same identifier checks as a printer (the token split, the private words, digit runs and
    long letter-digit tokens), in a stricter shape. Not normalised: capitals or spaces are
    refused by shape, as a person's name would be. `hint` is (what to name, examples)."""
    meaning, examples = hint
    text = str(value or "").strip()
    if not KIND_RE.fullmatch(text):
        raise CalibrationError(f"{what} must be a short lowercase id (a letter, then letters, digits or underscores, 24 at most: "
                               f"{examples}), got {value!r}")
    if reserved and text == reserved:
        raise CalibrationError(f"{what} {text!r} is reserved for entries without a {what}; name {meaning} ({examples})")
    if FORBIDDEN_WORDS.search(text) or id_tokens(text) & FORBIDDEN_TOKENS:
        raise CalibrationError(f"{what} {value!r} looks like an identifier of a person or a machine; name {meaning} ({examples})")
    check_private(text, what)
    return text


def normalize_kind(value) -> str:
    """The kind of member an entry is about (latch, lid_hinge, lever, clamp, snap), a short_id.
    `unclassified` is reserved (lookup reports entries without a kind under that name)."""
    return short_id("kind", value, KIND_HINT, reserved=UNCLASSIFIED)


def normalize_orientation(value) -> str:
    """How the part lay on the bed when it was printed (flat, upright, on_side), a short_id like
    the kind: the layer lines run differently, so a member that held flat may not upright."""
    return short_id("orientation", value, ORIENTATION_HINT)


def normalize_process(value) -> str:
    """The slicer process preset as the user calls it ("0.20mm Standard @BBL X2D"): one line of
    free text, trimmed, runs of spaces made one, 80 characters at most, through the note's checks
    (a preset name is not a place for an address, a serial or an access code)."""
    if not isinstance(value, str):
        raise CalibrationError("process is the slicer process preset's name as text, e.g. '0.20mm Standard @BBL X2D'")
    text = " ".join(value.split())
    if not text:
        raise CalibrationError("process is empty; leave it out when the preset is not known")
    if len(text) > PROCESS_MAX:
        raise CalibrationError(f"process: {PROCESS_MAX} characters at most (the preset's name as the slicer shows it)")
    if any(ord(c) < 32 or 127 <= ord(c) < 160 for c in text):
        raise CalibrationError("process: one line of text without control characters")
    check_private(text, "process")
    return text


def size_mm(key: str, value) -> float:
    """A nozzle or layer size in mm: a finite number between 0 and 5."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise CalibrationError(f"{key} must be a number in mm")
    if not math.isfinite(v) or not 0 < v < 5:
        raise CalibrationError(f"{key} {v} is not a plausible size in mm")
    return v


def parse_load(value):
    """A load: one of strength.py's hand-force keys (finger_push, ...) or a force in N."""
    if isinstance(value, str) and value.strip().lower() in LOAD_KEYS:
        return value.strip().lower()
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise CalibrationError(f"load is a force in N or one of {LOAD_KEYS}")
    if not math.isfinite(num) or num <= 0 or num >= MAX_VALUE:
        raise CalibrationError(f"load must be a positive force in N under {MAX_VALUE:g}")
    return num


def forbidden_key(key: str) -> bool:
    tokens = {t for t in re.split(r"[^a-z]+", key.lower()) if t}
    return bool(tokens & FORBIDDEN_TOKENS) or bool(re.search(r"(serial|token|account|passw|secret)", key, re.I))


def check_private(text: str, where: str) -> None:
    """What the script can recognise: addresses, e-mail, long digit runs, serial-like tokens and
    the words that announce them. It cannot recognise a person's name."""
    for m in IPV4_RE.finditer(text):
        parts = m.group(0).split(".")
        # A version such as 02.08.02.61 has leading zeros; an address does not.
        if all(p == "0" or not p.startswith("0") for p in parts) and all(int(p) <= 255 for p in parts):
            raise CalibrationError(f"{where} contains an IP address; calibration.json holds print results only")
    reasons = (
        (MAC_RE, "a MAC address"), (IPV6_RE, "an IPv6 address"),
        (EMAIL_RE, "an e-mail address"), (DIGITS_RE, "a run of six or more digits (a serial, code or account number)"),
        (MIXED_RE, "a long letter-digit token (a serial number or access code)"),
        (FORBIDDEN_WORDS, "a word that announces a serial number, access code, account or password"),
    )
    for rx, why in reasons:
        if rx.search(text):
            raise CalibrationError(f"{where} contains {why}; calibration.json holds print results only")


def validate_entry(entry: dict) -> dict:
    """Return a clean copy or raise CalibrationError."""
    if not isinstance(entry, dict):
        raise CalibrationError("an entry must be an object")
    for key in entry:
        if forbidden_key(str(key)):
            raise CalibrationError(f"field '{key}' is not allowed: no serials, IPs, access codes, accounts, ids or names")
    out = {}
    date = str(entry.get("date") or "").strip()
    try:
        out["date"] = datetime.date.fromisoformat(date).isoformat()
    except ValueError:
        raise CalibrationError(f"date must be YYYY-MM-DD, got {date!r}")
    out["printer"] = normalize_id("printer", entry.get("printer"))
    out["material"] = normalize_id("material", material_key(entry.get("material")))
    for key in ("nozzle_mm", "layer_mm"):
        v = entry.get(key)
        if v is None:
            if key == "nozzle_mm":
                raise CalibrationError("nozzle_mm is required")
            continue
        out[key] = size_mm(key, v)
    orientation = entry.get("orientation")
    if orientation is not None and str(orientation).strip():
        out["orientation"] = normalize_orientation(orientation)
    process = entry.get("process")
    if process is not None and (not isinstance(process, str) or process.strip()):
        out["process"] = normalize_process(process)
    feature = str(entry.get("feature") or "").strip().lower()
    if feature not in FEATURES:
        raise CalibrationError(f"feature must be one of {FEATURES}")
    result = str(entry.get("result") or "").strip().lower()
    if result not in RESULTS:
        raise CalibrationError(f"result must be one of {RESULTS}")
    out["feature"], out["result"] = feature, result
    kind = entry.get("kind")
    if kind is not None and str(kind).strip():
        out["kind"] = normalize_kind(kind)
    values = entry.get("values") or {}
    if not isinstance(values, dict):
        raise CalibrationError("values must be an object of name: number")
    clean = {}
    for k, v in values.items():
        k = str(k).strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", k):
            raise CalibrationError(f"value name {k!r}: letters, digits and underscores, e.g. clearance_per_side_mm")
        if forbidden_key(k):
            raise CalibrationError(f"value '{k}' is not allowed: no serials, IPs, access codes, accounts, ids or names")
        if isinstance(v, bool):
            raise CalibrationError(f"value '{k}' must be a number")
        try:
            num = float(v)
        except (TypeError, ValueError):
            raise CalibrationError(f"value '{k}' must be a number (got {v!r}); put words in the note")
        if not math.isfinite(num):
            raise CalibrationError(f"value '{k}' must be a finite number")
        if abs(num) >= MAX_VALUE or re.search(r"\d{6,}", str(v)):
            raise CalibrationError(f"value '{k}' = {v!r} is too large for a print result (mm, N, counts under {MAX_VALUE:g}); "
                                   "ids and codes do not belong here")
        clean[k] = num
    out["values"] = clean
    load = entry.get("load")
    if load is not None:
        out["load"] = parse_load(load)
    note = str(entry.get("note") or "").strip()
    if len(note) > 500:
        raise CalibrationError("note: 500 characters at most")
    check_private(note, "note")
    out["note"] = note
    return out


def load_file(path: str) -> dict:
    if not os.path.isfile(path):
        return {"schema": SCHEMA, "entries": []}
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except ValueError as exc:
            raise CalibrationError(f"{path} is not valid JSON: {exc}")
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("entries"), list):
        raise CalibrationError(f'{path} is not a calibration file (expected {{"schema": "{SCHEMA}", "entries": [...]}})')
    data["entries"] = [validate_entry(e) for e in data["entries"]]
    return data


def user_file() -> str:
    """The user-level file: THREEDPRINT_USER_CALIBRATION when set, else ~/.3dprint/calibration.json."""
    return os.path.expanduser(os.environ.get(USER_ENV) or USER_DEFAULT)


def shown_path(path: str) -> str:
    """A path as the output names it: the home folder as ~, so no account name leaves the machine."""
    home = os.path.expanduser("~")
    full = os.path.abspath(path)
    if home and len(home) > 1 and (full == home or full.startswith(home.rstrip(os.sep) + os.sep)):
        return "~" + full[len(home.rstrip(os.sep)):].replace(os.sep, "/")
    return path


def same_path(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def read_entries(args) -> tuple:
    """[(source, index in its file, entry)], project entries first, then the user-level file's
    (unless --no-user, or it is the project file); the user-level file's name as shown, or None;
    and warnings. A project file that cannot be read is an error; a user-level one is left out
    with a warning, never rewritten."""
    out = [("project", i, e) for i, e in enumerate(load_file(args.file)["entries"])]
    if getattr(args, "no_user", False):
        return out, None, []
    path = user_file()
    if same_path(path, args.file):
        return out, shown_path(path), []
    try:
        entries = load_file(path)["entries"]
    except (CalibrationError, OSError) as exc:
        why = str(exc).replace(path, shown_path(path))
        return out, shown_path(path), [f"the user-level file {shown_path(path)} was left out: {why}; fix it (it is "
                                       "never rewritten while it cannot be read) or pass --no-user"]
    return out + [("user", i, e) for i, e in enumerate(entries)], shown_path(path), []


def save_file(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def parse_values(items) -> dict:
    out = {}
    for item in items or []:
        name, sep, value = str(item).partition("=")
        if not sep:
            raise CalibrationError(f"--value takes name=number, got {item!r}")
        out[name.strip()] = value.strip()
    return out


def cmd_add(args) -> dict:
    if args.user and args.file:
        raise CalibrationError("add writes one file: --file (the project's) or --user (the user-level file), not both")
    if not args.user and not args.file:
        raise CalibrationError("add needs --file (the project's .3dprint/calibration.json), or --user for the "
                               "user-level file the user agreed to keep results in")
    path = user_file() if args.user else args.file
    try:
        data = load_file(path)                          # a file that cannot be read is refused, never overwritten
    except CalibrationError as exc:
        raise CalibrationError(str(exc).replace(path, shown_path(path)) if args.user else str(exc))
    if args.printers:
        with open(args.printers, encoding="utf-8") as f:
            known = (json.load(f).get("printers") or {})
        if args.printer not in known:
            raise CalibrationError(f"printer '{args.printer}' is not in {args.printers} (known: {', '.join(sorted(known)) or 'none'})")
    entry = validate_entry({"date": args.date or datetime.date.today().isoformat(), "printer": args.printer,
                            "material": args.material, "nozzle_mm": args.nozzle, "layer_mm": args.layer,
                            "orientation": args.orientation, "process": args.process,
                            "feature": args.feature, "kind": args.kind, "result": args.result,
                            "values": parse_values(args.value), "load": args.load, "note": args.note})
    data["entries"].append(entry)
    save_file(path, data)
    return {"file": shown_path(path) if args.user else args.file, "from": "user" if args.user else "project",
            "added": entry, "entries": len(data["entries"])}


def cmd_show(args) -> dict:
    rows, user, warnings = read_entries(args)
    entries = []
    for src, _i, e in rows:
        row = dict(e)
        row["from"] = src
        entries.append(row)
    return {"file": args.file, "user_file": user, "entries": entries, "count": len(entries), "warnings": warnings}


def selects(entry: dict, args) -> bool:
    """Printer, material and feature: what an entry is about. The conditions it was printed under
    are compared apart (differs), so an entry under other conditions is still seen."""
    def same(a, b):
        return normalize_id("query", a) == normalize_id("query", b)
    if args.printer and not same(entry["printer"], args.printer):
        return False
    if args.material and not same(entry["material"], material_key(args.material)):
        return False
    if args.feature and entry["feature"] != args.feature.lower():
        return False
    return True


def query_conditions(args) -> dict:
    """The conditions the query gives, as entry fields in the entry's spelling and the CONDITIONS
    order, through the same checks as `add`."""
    given = {"nozzle_mm": None if args.nozzle is None else size_mm("nozzle_mm", args.nozzle),
             "layer_mm": None if args.layer is None else size_mm("layer_mm", args.layer),
             "load": None if args.load is None else parse_load(args.load),
             "orientation": normalize_orientation(args.orientation) if args.orientation else None,
             "process": normalize_process(args.process) if args.process and args.process.strip() else None}
    return {field: given[field] for field, _opt in CONDITIONS if given[field] is not None}


def same_condition(field: str, recorded, wanted) -> bool:
    if field == "process":
        return recorded.casefold() == wanted.casefold()
    if isinstance(recorded, str) or isinstance(wanted, str):        # a load key never equals a force in N
        return recorded == wanted
    return abs(recorded - wanted) <= NUM_TOL


def differs(entry: dict, conditions: dict) -> dict:
    """{field: [the entry's value or "not recorded", the query's value]} for every condition the
    query gives that the entry does not record with the same value; {} for a same-condition entry."""
    out = {}
    for field, wanted in conditions.items():
        recorded = entry.get(field)
        if recorded is None:
            out[field] = [NOT_RECORDED, wanted]
        elif not same_condition(field, recorded, wanted):
            out[field] = [recorded, wanted]
    return out


def listed(i: int, entry: dict, diff: dict = None, src: str = "project") -> dict:
    """An entry as lookup lists it: its position in its file and the file (from) first, then its fields."""
    out = {"entry": i, "from": src}
    out.update(entry)
    if diff:
        out["differs"] = diff
    return out


def summarize(hits) -> tuple:
    """(worked, bounds, worked_set) from (source, index, entry) triples, project entries first,
    each newest first. worked and bounds: per value name, the first value seen wins, stamped with
    its date, entry and file. worked_set: the first entry that fit, worked or was measured and has
    values, all of them together."""
    worked, bounds, worked_set = {}, {}, None
    for src, i, e in hits:
        good = e["result"] in GOOD_RESULTS
        if good and worked_set is None and e["values"]:
            worked_set = listed(i, e, src=src)
        for k, v in e["values"].items():
            stamp = {"value": v, "date": e["date"], "entry": i, "from": src, "result": e["result"],
                     "feature": e["feature"]}
            if "kind" in e:
                stamp["kind"] = e["kind"]
            if good:
                worked.setdefault(k, stamp)
            else:
                bounds.setdefault(k, {}).setdefault(e["result"], stamp)
    return worked, bounds, worked_set


def shown(value) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def mixed_warnings(selected, same, conditions: dict) -> list:
    """What the query leaves open: without --nozzle every nozzle is mixed; without --layer, --load,
    --orientation or --process, any of them the same-condition entries record differently."""
    warnings = []
    if "nozzle_mm" not in conditions:
        nozzles = sorted({e["nozzle_mm"] for _s, _i, e in selected})
        found = f" (these entries: {', '.join(shown(n) for n in nozzles)} mm)" if nozzles else ""
        warnings.append(f"no --nozzle: results from every nozzle are mixed{found}; give --nozzle for the nozzle this "
                        "print uses, so entries from another nozzle are only references")
    words = {"layer_mm": "layer heights", "load": "loads", "orientation": "orientations", "process": "process presets"}
    for field, opt in CONDITIONS[1:]:
        if field in conditions:
            continue
        seen, unrecorded = {}, False
        for _s, _i, e in same:
            v = e.get(field)
            if v is None:
                unrecorded = True
            else:
                key = v.casefold() if field == "process" else (v if isinstance(v, str) else round(v, 6))
                seen.setdefault(key, v)
        if seen and unrecorded:
            seen.setdefault(None, "not recorded")         # recorded and unrecorded mixed: as different
        if len(seen) > 1:
            warnings.append(f"no --{opt}: the entries behind 'worked' and 'bounds' record different {words[field]} "
                            f"({', '.join(shown(v) for v in seen.values())}); give --{opt} for this print, so the "
                            "others are only references")
    return warnings


def entry_label(src: str, i: int) -> str:
    """How a warning names an entry: its position in the project file, or "user N"."""
    return str(i) if src == "project" else f"{src} {i}"


def cmd_lookup(args) -> dict:
    rows, user, read_warnings = read_entries(args)
    kind = normalize_kind(args.kind) if args.kind else None
    conditions = query_conditions(args)
    selected = [(src, i, e) for src, i, e in rows if selects(e, args)]
    # The project file first, then the user-level file; in each, the newest date, then the latest in the file.
    selected.sort(key=lambda r: (-SOURCES.index(r[0]), r[2]["date"], r[1]), reverse=True)
    kinds = {}
    for _s, _i, e in selected:
        kinds[e.get("kind", UNCLASSIFIED)] = kinds.get(e.get("kind", UNCLASSIFIED), 0) + 1
    same, reference, unclassified = [], [], []
    for src, i, e in selected:
        diff = differs(e, conditions)
        if kind and "kind" not in e:
            unclassified.append(listed(i, e, diff, src))
        elif kind and e["kind"] != kind:
            continue                                                         # another kind of member: counted in kinds
        elif diff:
            reference.append(listed(i, e, diff, src))
        else:
            same.append((src, i, e))
    worked, bounds, worked_set = summarize(same)
    sources = sorted({(SOURCES.index(s["from"]), s["entry"]) for s in worked.values()})
    query = {k: getattr(args, k) for k in ("printer", "material", "feature", "kind") if getattr(args, k) is not None}
    query.update({opt: conditions[field] for field, opt in CONDITIONS if field in conditions})
    out = {"file": args.file, "user_file": user, "query": query,
           "entries": [listed(i, e, src=src) for src, i, e in same], "count": len(same),
           "worked": worked, "worked_set": worked_set, "combined": len(sources) > 1, "bounds": bounds,
           "reference": reference, "kinds": kinds}
    if kind:
        out[UNCLASSIFIED] = {"entries": unclassified, "count": len(unclassified),
                             "note": f"entries without a kind: seen, but they set no floor for kind '{kind}' (a member "
                                     "that broke is a floor for the same kind of member under the same kind of load); "
                                     "to classify one, ask the user what it was and `add` it again with --kind "
                                     "(the same values, date and note), the old entry stays as it is"}
    warnings = read_warnings + mixed_warnings(selected, same, conditions)
    if out["combined"]:
        warnings.append(f"'worked' takes its values from {len(sources)} different test prints (entries "
                        f"{', '.join(entry_label(SOURCES[s], i) for s, i in sources)}): they were never printed "
                        "together as a set, so the combination is not verified; for a combination use 'worked_set' "
                        f"(entry {entry_label(worked_set['from'], worked_set['entry'])}, {worked_set['date']}), one "
                        "print's values together")
    out["warnings"] = warnings
    out["note"] = ("'entries' match every condition the query gives (nozzle, layer, load, orientation, process): only they "
                   "set 'worked', 'worked_set' and 'bounds'. 'worked' is, per value name, the newest value from a result "
                   "that fit, worked or was measured: it beats the official spec and design.md starting points (SKILL.md, "
                   "Phase 2); each value names its 'entry' and 'date', and when they come from more than one entry "
                   "('combined') they were never printed together, so take a combination from 'worked_set'. 'bounds' are "
                   "the newest failed, tight and loose values: stay above a failure, between tight and loose, for the "
                   "same kind of member (--kind). 'reference' entries differ in, or do not record, a condition the query "
                   "gives ('differs': the entry's value, then the query's): references only, never a setting or a floor. "
                   "'from' says which file an entry came from: 'project' (this project's) or 'user' (the user-level "
                   "file, results from other projects); project entries come first and take precedence")
    return out


def utf8_stdout():
    """Windows consoles and pipes may not be UTF-8; notes may be. Best effort."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


def main(argv=None):
    utf8_stdout()
    out = {"schema": "3dprint-scout.calibration/1", "ran": False, "warnings": [], "errors": []}
    try:
        ap = _JsonArgParser(description="the user's own print results per printer, material and nozzle")
        sub = ap.add_subparsers(dest="cmd")
        for name in ("add", "show", "lookup"):
            p = sub.add_parser(name)
            p.add_argument("--file", required=(name != "add"), help=".3dprint/calibration.json in the user's project")
            if name == "add":
                p.add_argument("--user", action="store_true",
                               help="write the user-level file (~/.3dprint/calibration.json, or the path in "
                                    f"{USER_ENV}) instead of --file: only when the user agreed to keep it for "
                                    "every project")
            else:
                p.add_argument("--no-user", action="store_true",
                               help="read the project file only, not the user-level file")
            if name != "show":
                p.add_argument("--printer", required=(name == "add"), help="printer id as in printers.json, e.g. x2d")
                p.add_argument("--material", required=(name == "add"), help="e.g. pla_basic (strength.py keys) or a filament name")
                p.add_argument("--nozzle", type=float, required=(name == "add"), help="nozzle diameter in mm")
                p.add_argument("--feature", choices=FEATURES, required=(name == "add"))
                p.add_argument("--kind", help="kind of member, a short lowercase id: latch, lid_hinge, lever, clamp, snap "
                                              "(add: optional, meant for mechanism entries; lookup: only this kind sets floors)")
                p.add_argument("--layer", type=float, help="layer height in mm (lookup: a condition)")
                p.add_argument("--load", help="force in N or a strength.py load key, when a mechanism was loaded "
                                              "(lookup: a condition)")
                p.add_argument("--orientation", help="how the part lay on the bed, a short lowercase id: flat, upright, "
                                                     "on_side (lookup: a condition)")
                p.add_argument("--process", help="the slicer process preset as the user calls it, e.g. "
                                                 "'0.20mm Standard @BBL X2D', 80 characters (lookup: a condition)")
            if name == "add":
                p.add_argument("--printers", help=".3dprint/printers.json: the printer must be one of its ids")
                p.add_argument("--result", choices=RESULTS, required=True)
                p.add_argument("--value", action="append", help="name=number, repeatable, e.g. clearance_per_side_mm=0.3")
                p.add_argument("--note", default="", help="free text, 500 characters; no serials, IPs or names")
                p.add_argument("--date", help="YYYY-MM-DD (default today)")
        args = ap.parse_args(sys.argv[1:] if argv is None else argv)
        if args.cmd is None:
            raise CalibrationError("usage error: choose a subcommand: add, show, lookup")
        result = {"add": cmd_add, "show": cmd_show, "lookup": cmd_lookup}[args.cmd](args)
        out["warnings"].extend(result.pop("warnings", []))
        out.update(result)
        out["ran"] = True
    except (CalibrationError, OSError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
