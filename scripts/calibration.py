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
      --feature mechanism --result failed --value pin_d_mm=2.6 --value pin_wall_mm=1.3 --value arm_mm=1.2 \\
      --load finger_push --note "print-in-place draw latch: pins, rings and arms broke on first use"
  python3 calibration.py show --file .3dprint/calibration.json
  python3 calibration.py lookup --file .3dprint/calibration.json --printer x2d --material pla_basic --feature fit

Schema (3dprint.calibration/1): {"schema", "entries": [{"date", "printer", "material", "nozzle_mm",
"layer_mm"?, "feature": fit | mechanism | clearance | hole | other, "result": fits | tight | loose |
worked | failed | measured, "values": {name: number}, "load": number N or a strength.py key,
"note"}]}. Values are numbers only. Fields that could identify a person or a machine are refused:
serial numbers, IP addresses, access codes, account or user ids, e-mail addresses, tokens, names
of people; the note is checked for an IP address or a serial-number-like string.

`lookup` prints the matching entries newest first and, for every value name, the latest number
("latest"), so a later ring that fit replaces an earlier one. Never written without the user's
yes (SKILL.md): the agent asks once after a print result, then runs `add`. Prints one JSON
document; exit 0 on success, 1 on error. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

SCHEMA = "3dprint.calibration/1"
FEATURES = ("fit", "mechanism", "clearance", "hole", "other")
RESULTS = ("fits", "tight", "loose", "worked", "failed", "measured")
FORBIDDEN_KEYS = re.compile(r"(serial|^sn$|_sn$|\bip\b|ip_?addr|access.?code|account|user.?id|owner|e-?mail|token|"
                            r"password|passcode|phone|address|name$)", re.I)
IP_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
SERIAL_RE = re.compile(r"\b[0-9A-Z]{2,4}[0-9]{2}[0-9A-Z]{8,}\b")      # long upper-case alphanumeric runs
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
LOAD_KEYS = ("finger_push", "finger_press", "finger_pull", "pinch_lateral", "pinch_palmar", "grasp")


class CalibrationError(Exception):
    pass


class _JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise CalibrationError(f"usage error: {message}")


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
def _ident(what: str, value) -> str:
    text = str(value or "").strip()
    if not text:
        raise CalibrationError(f"{what} is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._+-]{0,39}", text):
        raise CalibrationError(f"{what} must be a short identifier (letters, digits, space, . _ + -): {text!r}")
    return text


def check_private(text: str, where: str) -> None:
    if IP_RE.search(text):
        raise CalibrationError(f"{where} contains an IP address; calibration.json holds print results only")
    if EMAIL_RE.search(text):
        raise CalibrationError(f"{where} contains an e-mail address; calibration.json holds print results only")
    if SERIAL_RE.search(text):
        raise CalibrationError(f"{where} contains what looks like a serial number; leave it out")


def validate_entry(entry: dict) -> dict:
    """Return a clean copy or raise CalibrationError."""
    if not isinstance(entry, dict):
        raise CalibrationError("an entry must be an object")
    for key in entry:
        if FORBIDDEN_KEYS.search(str(key)):
            raise CalibrationError(f"field '{key}' is not allowed: no serials, IPs, access codes, accounts or names")
    out = {}
    date = str(entry.get("date") or "").strip()
    try:
        out["date"] = datetime.date.fromisoformat(date).isoformat()
    except ValueError:
        raise CalibrationError(f"date must be YYYY-MM-DD, got {date!r}")
    out["printer"] = _ident("printer", entry.get("printer"))
    out["material"] = _ident("material", entry.get("material"))
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
        if not 0 < v < 5:
            raise CalibrationError(f"{key} {v} is not a plausible size in mm")
        out[key] = v
    feature = str(entry.get("feature") or "").strip().lower()
    if feature not in FEATURES:
        raise CalibrationError(f"feature must be one of {FEATURES}")
    result = str(entry.get("result") or "").strip().lower()
    if result not in RESULTS:
        raise CalibrationError(f"result must be one of {RESULTS}")
    out["feature"], out["result"] = feature, result
    values = entry.get("values") or {}
    if not isinstance(values, dict):
        raise CalibrationError("values must be an object of name: number")
    clean = {}
    for k, v in values.items():
        k = str(k).strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", k):
            raise CalibrationError(f"value name {k!r}: letters, digits and underscores, e.g. clearance_per_side_mm")
        if FORBIDDEN_KEYS.search(k):
            raise CalibrationError(f"value '{k}' is not allowed: no serials, IPs, access codes, accounts or names")
        if isinstance(v, bool):
            raise CalibrationError(f"value '{k}' must be a number")
        try:
            num = float(v)
        except (TypeError, ValueError):
            raise CalibrationError(f"value '{k}' must be a number (got {v!r}); put words in the note")
        clean[k] = num
    out["values"] = clean
    load = entry.get("load")
    if load is not None:
        if isinstance(load, str) and load.strip().lower() in LOAD_KEYS:
            out["load"] = load.strip().lower()
        else:
            try:
                out["load"] = float(load)
            except (TypeError, ValueError):
                raise CalibrationError(f"load is a force in N or one of {LOAD_KEYS}")
    note = str(entry.get("note") or "").strip()
    if len(note) > 500:
        raise CalibrationError("note: 500 characters at most")
    check_private(note, "note")
    for key in ("printer", "material"):
        check_private(out[key], key)
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
    entry = validate_entry({"date": args.date or datetime.date.today().isoformat(), "printer": args.printer,
                            "material": args.material, "nozzle_mm": args.nozzle, "layer_mm": args.layer,
                            "feature": args.feature, "result": args.result, "values": parse_values(args.value),
                            "load": args.load, "note": args.note})
    data["entries"].append(entry)
    save_file(args.file, data)
    return {"file": args.file, "added": entry, "entries": len(data["entries"])}


def cmd_show(args) -> dict:
    data = load_file(args.file)
    return {"file": args.file, "entries": data["entries"], "count": len(data["entries"])}


def matches(entry: dict, args) -> bool:
    def same(a, b):
        return str(a).strip().lower() == str(b).strip().lower()
    if args.printer and not same(entry["printer"], args.printer):
        return False
    if args.material and not same(entry["material"], args.material):
        return False
    if args.nozzle is not None and abs(entry["nozzle_mm"] - args.nozzle) > 1e-6:
        return False
    if args.feature and entry["feature"] != args.feature.lower():
        return False
    return True


def cmd_lookup(args) -> dict:
    data = load_file(args.file)
    hits = [e for e in data["entries"] if matches(e, args)]
    hits.sort(key=lambda e: e["date"], reverse=True)
    latest = {}
    for e in hits:                                   # newest first: the first value seen wins
        for k, v in e["values"].items():
            latest.setdefault(k, {"value": v, "date": e["date"], "result": e["result"], "feature": e["feature"]})
    return {"file": args.file, "query": {k: getattr(args, k) for k in ("printer", "material", "nozzle", "feature") if getattr(args, k) is not None},
            "entries": hits, "count": len(hits), "latest": latest,
            "note": "a measured value here beats the official spec and design.md starting points (SKILL.md, Phase 2)"}


def main(argv=None):
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
            if name == "add":
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
