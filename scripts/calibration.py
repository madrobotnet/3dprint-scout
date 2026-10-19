#!/usr/bin/env python3
"""
calibration.py - the user's own print results, per printer, material and nozzle, kept in the
project at .3dprint/calibration.json (never in the skill): which fit-test ring fit, which
mechanism member broke or held and under what load, measured clearances. Read in Phase 2;
a value measured here beats the official spec and the starting points in design.md.

  python3 calibration.py add --file .3dprint/calibration.json --printer x2d --material pla_basic --nozzle 0.4 \\
      --feature fit --result fits --value clearance_per_side_mm=0.3 --value profile_w_mm=45.1 \\
      --note "ring 2 of the fit test slid on by hand without rattle"
  python3 calibration.py add --file .3dprint/calibration.json --printer x2d --material pla_pure --nozzle 0.4 \\
      --feature mechanism --kind latch --result failed --value pin_d_mm=2.6 --value pin_wall_mm=1.3 --value arm_mm=1.2 \\
      --load finger_push --note "print-in-place draw latch: pins, rings and arms broke on first use"
  python3 calibration.py show --file .3dprint/calibration.json
  python3 calibration.py lookup --file .3dprint/calibration.json --printer x2d --material pla_basic --feature fit
  python3 calibration.py lookup --file .3dprint/calibration.json --printer x2d --feature mechanism --kind lid_hinge

Schema (3dprint.calibration/1): {"schema", "entries": [{"date", "printer", "material", "nozzle_mm",
"layer_mm"?, "feature": fit | mechanism | clearance | hole | other, "kind"?: a short lowercase id
(latch, lid_hinge, lever, clamp, snap: the kind of member, so a floor applies to the same kind under
the same kind of load), "result": fits | tight | loose | worked | failed | measured, "values":
{name: number}, "load": number N or a strength.py key, "note"}]}. Values are finite numbers under
10 000 (mm, N, counts). `kind` is optional for every feature and meant for mechanism entries;
files written without it still load. What the script can recognise
as identifying a person or a machine is refused: value names with id, uid, code, device, mac,
serial, token, account, mail, ip, user, name, key or secret in them; notes with an IPv4, IPv6 or
MAC address, an e-mail address, a run of six or more digits or a long mixed letter-digit token
(serial numbers, access codes), or the words serial, access code, account, password; printers
and materials must be short lowercase ids (x2d, pla_basic; "PLA Basic" is stored as pla_basic,
the strength.py key), never a person's name. It cannot
recognise a name in a note: the agent never writes one.

`lookup` prints the matching entries newest first (date, then file order) and, per value name,
"worked": the newest number from an entry that fit, worked or was measured, and "bounds": the
newest failed, tight and loose numbers, kept apart so a failure is never read as a setting.
With --kind K only entries of that kind set "worked" and "bounds"; matching entries without a
kind are listed under "unclassified" so they are seen but set no floor for K (a stub pin that
broke in a hand-operated latch is not the floor for a lid hinge's integral pin). Without --kind
every matching entry counts, as before, and "kinds" says how many entries each kind has.
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
KIND_RE = re.compile(r"[a-z][a-z0-9_]{0,23}")           # the kind of member: latch, lid_hinge, lever, clamp, snap
UNCLASSIFIED = "unclassified"                           # lookup's name for entries without a kind; not a valid kind
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


def normalize_kind(value) -> str:
    """The kind of member an entry is about (latch, lid_hinge, lever, clamp, snap): a short
    lowercase id through the same identifier checks as a printer (the token split, the private
    words, digit runs and long letter-digit tokens), in a stricter shape. Not normalised:
    capitals or spaces are refused by shape, as a person's name would be. `unclassified` is
    reserved (lookup reports entries without a kind under that name)."""
    text = str(value or "").strip()
    if not KIND_RE.fullmatch(text):
        raise CalibrationError(f"kind must be a short lowercase id (a letter, then letters, digits or underscores, 24 at most: "
                               f"latch, lid_hinge, lever, clamp, snap), got {value!r}")
    if text == UNCLASSIFIED:
        raise CalibrationError(f"kind {text!r} is reserved for entries without a kind; name the kind of member "
                               "(latch, lid_hinge, lever, clamp, snap)")
    if FORBIDDEN_WORDS.search(text) or id_tokens(text) & FORBIDDEN_TOKENS:
        raise CalibrationError(f"kind {value!r} looks like an identifier of a person or a machine; name the kind of member "
                               "(latch, lid_hinge, lever, clamp, snap)")
    check_private(text, "kind")
    return text


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
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise CalibrationError(f"{key} must be a number in mm")
        if not math.isfinite(v) or not 0 < v < 5:
            raise CalibrationError(f"{key} {v} is not a plausible size in mm")
        out[key] = v
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
        if isinstance(load, str) and load.strip().lower() in LOAD_KEYS:
            out["load"] = load.strip().lower()
        else:
            try:
                num = float(load)
            except (TypeError, ValueError):
                raise CalibrationError(f"load is a force in N or one of {LOAD_KEYS}")
            if not math.isfinite(num) or num <= 0 or num >= MAX_VALUE:
                raise CalibrationError(f"load must be a positive force in N under {MAX_VALUE:g}")
            out["load"] = num
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
    data = load_file(args.file)
    if args.printers:
        with open(args.printers, encoding="utf-8") as f:
            known = (json.load(f).get("printers") or {})
        if args.printer not in known:
            raise CalibrationError(f"printer '{args.printer}' is not in {args.printers} (known: {', '.join(sorted(known)) or 'none'})")
    entry = validate_entry({"date": args.date or datetime.date.today().isoformat(), "printer": args.printer,
                            "material": args.material, "nozzle_mm": args.nozzle, "layer_mm": args.layer,
                            "feature": args.feature, "kind": args.kind, "result": args.result,
                            "values": parse_values(args.value), "load": args.load, "note": args.note})
    data["entries"].append(entry)
    save_file(args.file, data)
    return {"file": args.file, "added": entry, "entries": len(data["entries"])}


def cmd_show(args) -> dict:
    data = load_file(args.file)
    return {"file": args.file, "entries": data["entries"], "count": len(data["entries"])}


def matches(entry: dict, args) -> bool:
    def same(a, b):
        return normalize_id("query", a) == normalize_id("query", b)
    if args.printer and not same(entry["printer"], args.printer):
        return False
    if args.material and not same(entry["material"], material_key(args.material)):
        return False
    if args.nozzle is not None and abs(entry["nozzle_mm"] - args.nozzle) > 1e-6:
        return False
    if args.feature and entry["feature"] != args.feature.lower():
        return False
    return True


def summarize(entries) -> tuple:
    """(worked, bounds) per value name from entries sorted newest first: the first value seen wins."""
    worked, bounds = {}, {}
    for e in entries:
        for k, v in e["values"].items():
            stamp = {"value": v, "date": e["date"], "result": e["result"], "feature": e["feature"]}
            if "kind" in e:
                stamp["kind"] = e["kind"]
            if e["result"] in GOOD_RESULTS:
                worked.setdefault(k, stamp)
            else:
                bounds.setdefault(k, {}).setdefault(e["result"], stamp)
    return worked, bounds


def cmd_lookup(args) -> dict:
    data = load_file(args.file)
    hits = [(i, e) for i, e in enumerate(data["entries"]) if matches(e, args)]
    hits.sort(key=lambda ie: (ie[1]["date"], ie[0]), reverse=True)      # newest date, then latest in the file
    entries = [e for _i, e in hits]
    kinds = {}
    for e in entries:
        kinds[e.get("kind", UNCLASSIFIED)] = kinds.get(e.get("kind", UNCLASSIFIED), 0) + 1
    out = {"file": args.file,
           "query": {k: getattr(args, k) for k in ("printer", "material", "nozzle", "feature", "kind") if getattr(args, k) is not None}}
    kind = normalize_kind(args.kind) if args.kind else None
    if kind:
        same = [e for e in entries if e.get("kind") == kind]
        unclassified = [e for e in entries if "kind" not in e]
        worked, bounds = summarize(same)
        out.update({"entries": same, "count": len(same), "worked": worked, "bounds": bounds, "kinds": kinds,
                    UNCLASSIFIED: {"entries": unclassified, "count": len(unclassified),
                                   "note": f"entries without a kind: seen, but they set no floor for kind '{kind}' (a member "
                                           "that broke is a floor for the same kind of member under the same kind of load); "
                                           "to classify one, ask the user what it was and `add` it again with --kind "
                                           "(the same values, date and note), the old entry stays as it is"}})
    else:
        worked, bounds = summarize(entries)
        out.update({"entries": entries, "count": len(entries), "worked": worked, "bounds": bounds, "kinds": kinds})
    out["note"] = ("'worked' is the newest value from a result that fit, worked or was measured: it beats the official spec "
                   "and design.md starting points (SKILL.md, Phase 2). 'bounds' are the newest failed, tight and loose "
                   "values: stay above a failure, between tight and loose, for the same kind of member (--kind)")
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
            p.add_argument("--file", required=True, help=".3dprint/calibration.json in the user's project")
            if name != "show":
                p.add_argument("--printer", required=(name == "add"), help="printer id as in printers.json, e.g. x2d")
                p.add_argument("--material", required=(name == "add"), help="e.g. pla_basic (strength.py keys) or a filament name")
                p.add_argument("--nozzle", type=float, required=(name == "add"), help="nozzle diameter in mm")
                p.add_argument("--feature", choices=FEATURES, required=(name == "add"))
                p.add_argument("--kind", help="kind of member, a short lowercase id: latch, lid_hinge, lever, clamp, snap "
                                              "(add: optional, meant for mechanism entries; lookup: only this kind sets floors)")
            if name == "add":
                p.add_argument("--printers", help=".3dprint/printers.json: the printer must be one of its ids")
                p.add_argument("--layer", type=float, help="layer height in mm")
                p.add_argument("--result", choices=RESULTS, required=True)
                p.add_argument("--value", action="append", help="name=number, repeatable, e.g. clearance_per_side_mm=0.3")
                p.add_argument("--load", help="force in N or a strength.py load key, when a mechanism was loaded")
                p.add_argument("--note", default="", help="free text, 500 characters; no serials, IPs or names")
                p.add_argument("--date", help="YYYY-MM-DD (default today)")
        args = ap.parse_args(sys.argv[1:] if argv is None else argv)
        if args.cmd is None:
            raise CalibrationError("usage error: choose a subcommand: add, show, lookup")
        out.update({"add": cmd_add, "show": cmd_show, "lookup": cmd_lookup}[args.cmd](args))
        out["ran"] = True
    except (CalibrationError, OSError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
