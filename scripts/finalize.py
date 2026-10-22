#!/usr/bin/env python3
"""
finalize.py - the final verification report of a build (Phase 6): one place that says what was
verified, with what evidence, and what was not, so a missing fit report or a skipped test print
can never look like a finished check.

  python3 finalize.py --build out/build.json --params .3dprint/params.json \\
      [--deliver deliver/2026-10-21] [--bundle deliver/2026-10-21/source]

--build is the JSON that `build.py run` or `record` printed, saved (`build.py run ... > out/build.json`).
It names the parts, the sha256 of each STL it judged, the sources it hashed and the settings it
validated with (printer, printer id, tools, tolerances). finalize does not take its verdicts on
trust: it validates every part STL again with the same settings (R3 says whether the STL still
matches the generator and parameters as they are now), checks that every part in `_parts` was
built, and takes the object checks (A1 / A2, an object's D2) from the build only while every STL
is still the one that build judged. A build that reported errors, or whose gate was FAIL, is
not verified (an INCOMPLETE gate is named by the UNVERIFIED checks behind it). Settings given here (--printer, --printer-id, --tools, ...) replace the build's.

What else counts is declared in params.json under `_verify` (every key optional, but a key that
is missing is reported as "not declared", which keeps its tier from being verified):

  "_verify": {
    "promises": [{"id": "cable-out", "kind": "use", "text": "a right-angle USB-C cable plugs in",
                  "conditions": "phone on the seat", "success": "plug and cable clear the part",
                  "evidence": [{"joint": "plug through notch", "covers": "the plug at rest"}]},
                 {"id": "wave-back", "kind": "look", "text": "the back waves once"}],
    "dims":     [{"id": "usb-c-plug", "what": "right-angle plug head", "unit": "mm",
                  "params": {"plug_w": 13, "plug_h": 8}, "source": "assumed"}],
    "joints":   [{"name": "lid on box", "report": "out/fit_box_lid.json"},
                 {"name": "plug through notch", "report": "out/fit_plug.json", "proxy": true,
                  "dims": ["usb-c-plug"]}],
    "strength": [{"name": "latch arm", "report": "out/strength_latch.json"}],
    "test_prints": [{"name": "hinge coupon", "status": "skipped", "note": "user had no time"}],
    "accepted": [{"check": "body P2", "reason": "the user wants supports there"},
                 {"check": "object box P2", "reason": "..."},
                 {"check": "joint lid on box F3", "reason": "a snug lid"},
                 {"promise": "wave-back", "reason": "the user judges it on the print", "by": "user"}],
    "unverified": ["wall behind the label: estimated from a photo"],
    "references": {"lid": {"front": "real", "top": "real", "back": "estimated", "bottom": "assumed"}}
  }

joints: every joint F3 must cover, with its saved fit.py report: the report must be fresh (its
STLs are the parts being delivered, or a declared proxy) and its own F3 / F3_sweep must PASS
(a WARN the user accepted as "joint <name> <check>" counts as accepted). A proxy names the dims
it is built from. An empty list says the design has no joint. strength: strength.py reports
(saved JSON), their gate must PASS; their inputs are numbers from the dimension table, not read
from the model, so the report says to keep them equal. test_prints: coupons and mechanism-first
prints (status passed, failed, skipped, offered or pending). accepted: WARNs the user accepted,
named "<part> <check>" or "object <name> <check>", with their reason; any other WARN is open
("<part> D1" also accepts a D1 whose expect was copied from the model, when no intended size
exists); and promises the user takes without verifying them ("by": "user"). unverified:
dimensions taken without a measurement. references: for each object, which directions a
reference shows (`real`), or was generated or inferred (`estimated`), or given up on
(`assumed`); a direction without a real reference is one whose shape is not verified.

promises: what the user was promised, each judged by its own evidence. kind `use` (a thing the
user does with the object: needs conditions and success), `feature` (needs success) or `look`.
Evidence names a declared joint or member; a use takes joints and members, a feature joints; a
part's own check (box M1) is never evidence of a promise. dims: the real-world sizes the design
rests on, each tied to the params.json values the model is built from (they must be equal),
with its source: assumed, caliper ("by": "user") or spec (its url). A promise rests on the dims its evidence names (and on its own `assumes`); a proxy
joint that names none rests on undeclared sizes. Each promise gets one state: error (declared
wrongly), failed (its evidence failed, whatever else), excluded (the user took it unverified),
not verified (no evidence, stale evidence, evidence on a part whose checks FAIL, a member's
inputs typed in), assumed (it passed on an unmeasured size), accepted (it passed with a WARN the
user accepted) or verified.

The report has five tiers and never folds them into one PASS:
  use       the worst state of its promises (error, failed, not verified, excluded, assumed,
            accepted, verified, in that order), or not declared (no promises, or an empty list)
  geometry  verified | not verified   the STLs, objects, joints and members, from the checks above
  shape     per object, the directions a real reference covers
  slicing   unverified                  nothing here slices; say so at delivery
  print     unverified                  test prints and their results, if any
plus `open`: every promise that is not verified and why, every reason the geometry is not
verified, every unaccepted WARN, the soft checks left to you (P3 skipped, P4, P5, P6), every
unverified dimension and assumption, in plain lines for the delivery message.

--deliver DIR checks the delivery folder: every STL in it must be one of the verified STLs,
every 3MF must carry a manifest (`<file>.3mf.manifest.json`, written by build.py and bambu3mf.py
next to the 3MF; copy it along) that lists exactly the verified STLs, and every part must be
delivered in one or the other; a malformed manifest is a reason, not an error. --bundle DIR
writes a new folder with the generator sources (not the skill's own libraries) at their places
relative to the folder the build ran in (lib/helper.py stays lib/helper.py, so imports, includes
and loaded files still resolve), params.json, the printers.json the build used, this report and
REPRODUCE.md (the commands that rebuild and re-check the parts); it refuses an existing folder,
a source outside the project folder, and a source or params file that holds a path of this
machine. Exit 0 when it ran (read "use" and "geometry"), 1 on a usage or file error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from types import SimpleNamespace

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
EVIDENCE = ("joint", "strength")
ALLOWED = {"use": ("joint", "strength"), "feature": ("joint",), "look": ()}
NEEDS = {"use": ("conditions", "success"), "feature": ("success",), "look": ()}
PROMISE_KEYS = ("id", "kind", "text", "conditions", "success", "evidence", "assumes", "note")
DIM_SOURCES = ("assumed", "caliper", "spec")
DIM_STATE = {"assumed": "assumed", "caliper": "measured", "spec": "spec"}
DIM_KEYS = ("id", "what", "unit", "params", "source", "tol", "by", "url", "note")
STATES = ("error", "failed", "not verified", "excluded", "assumed", "accepted", "verified")


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


def scrub(text):
    """The report's text with this machine's folders taken out wherever they appear, in any
    case and form (a file:// link, after -I, in a JSON escape): the working folder becomes `.`,
    the home folder `~`. Taking out too much is harmless here."""
    for form, stand_in in machine_forms():
        text = re.sub(re.escape(form), lambda _m, s_=stand_in: s_, text, flags=re.IGNORECASE)
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


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def check_verify_shape(verify):
    lists = {"joints": dict, "strength": dict, "test_prints": dict, "accepted": dict, "unverified": str,
             "promises": dict, "dims": dict}
    for key, item in lists.items():
        if key in verify:
            v = verify[key]
            if not isinstance(v, list) or not all(isinstance(x, item) for x in v):
                kind = "objects" if item is dict else "strings"
                raise FinalizeError(f"_verify.{key} must be a list of {kind}")
    for key in ("joints", "strength"):
        for e in verify.get(key) or []:
            bad = [f for f in ("name", "report") if f in e and not isinstance(e[f], str)]
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
            out.append(f"{f} {old} -> {new}")
    if bool(b.get("wall_check", True)) != bool(settings.wall_check):
        out.append("wall_check")
    pr = settings.printer
    same_file = bool(pr and b.get("printer") and os.path.normcase(os.path.abspath(pr)) ==
                     os.path.normcase(os.path.abspath(b["printer"])))
    if same_file and b.get("printer_sha256") and os.path.isfile(pr) and validate.file_sha256(pr) != b["printer_sha256"]:
        out.append(f"{rel(pr)} changed since the build")
    return out


def check_parts(build, specs, params_path, settings):
    """Every part STL validated again now, as the build did. Returns (entries, reasons, warns,
    to_decide, same_as_build) where same_as_build says every STL is the one the build judged."""
    import build as build_mod
    sources = build.get("sources") or []
    missing = [s for s in sources if not os.path.isfile(s)]
    entries, reasons, warns, to_decide, copied = [], [], [], [], []
    same_as_build = True
    if missing:
        reasons.append(f"sources the build hashed are missing: {', '.join(missing)} (run finalize from the folder the "
                       "build ran in)")
    built = {p.get("name") for p in build.get("parts") or []}
    for name in specs:
        if name not in built:
            reasons.append(f"{name}: in _parts but not in this build (built with --only, or not recorded): build "
                           "every part, save that build's JSON")
    for p in build.get("parts") or []:
        name, stl = p.get("name"), p.get("stl")
        entry = {"name": name, "stl": rel(stl)}
        if not stl or not os.path.isfile(stl):
            entry["state"] = "FAIL"
            reasons.append(f"{name}: STL {rel(stl)} not found")
            same_as_build = False
            entries.append(entry)
            continue
        entry["sha256"] = validate.file_sha256(stl)
        entry["same_as_build"] = bool(p.get("sha256")) and p["sha256"] == entry["sha256"]
        if not entry["same_as_build"]:
            same_as_build = False
            reasons.append(f"{name}: {rel(stl)} is not the STL this build JSON judged" if p.get("sha256") else
                           f"{name}: the build JSON has no sha256 for its STLs (made before 0.6): build again and save it")
        if missing:
            entry["state"] = "UNVERIFIED"
            entries.append(entry)
            continue
        rep = build_mod.validate_part(stl, specs.get(name, {}), sources, params_path, settings)
        f = (rep.get("files") or [{}])[0]
        checks = f.get("checks") or {}
        entry["gate"] = rep.get("gate")
        entry["checks"] = {k: v.get("state") for k, v in checks.items()}
        for cid, ck in checks.items():
            state, note = ck.get("state"), ck.get("note", "")
            if cid == "D1" and ck.get("copied_expect"):
                copied.append((f"{name} D1", f"{name} D1: its expect was copied from the model's own box, so D1 "
                               "compares the part with itself; give the intended size (or accept it in "
                               f"_verify.accepted as \"{name} D1\")"))
            if state == "FAIL" and ck.get("kind") == "hard":
                reasons.append(f"{name} {cid} FAIL: {note}".rstrip(": "))
            elif state == "UNVERIFIED" and ck.get("kind") == "hard":
                reasons.append(f"{name} {cid} UNVERIFIED: {note}".rstrip(": "))
            elif state == "UNVERIFIED":
                to_decide.append(f"{name} {cid} UNVERIFIED (yours to decide): {note}".rstrip(": "))
            elif state == "WARN":
                warns.append((f"{name} {cid}", note))
        for e in rep.get("errors", []):
            reasons.append(f"{name}: {e}")
        entries.append(entry)
    if not entries:
        reasons.append("the build lists no parts")
    return entries, reasons, warns, to_decide, copied, same_as_build


def check_build(build):
    reasons = []
    if not build.get("ran"):
        reasons.append("the build did not run")
    for e in build.get("errors") or []:
        reasons.append(f"the build reported: {e}")
    if build.get("gate") not in ("PASS", "INCOMPLETE"):           # INCOMPLETE: its UNVERIFIED checks say why
        reasons.append(f"the build's gate was {build.get('gate')}, not PASS")
    return reasons


def check_objects(build, same_as_build, drift=()):
    """Object checks from the build (A1 / A2, an object's D2 / P1 / P2), only while every STL is
    the one that build judged."""
    entries, reasons, warns = [], [], []
    for o in build.get("objects") or []:
        if "checks" not in o and "gate" not in o:
            continue
        entry = {"name": o.get("name"), "gate": o.get("gate"), "parts": o.get("parts")}
        if not same_as_build:
            entry["state"] = "UNVERIFIED"
            reasons.append(f"object '{o.get('name')}': its checks are from a build whose STLs have changed since; "
                           "build again and save that build's JSON")
        elif drift:
            entry["state"] = "UNVERIFIED"
            reasons.append(f"object '{o.get('name')}': its checks (A1 / A2, D2, P1 / P2 on the whole) were made with "
                           f"other settings than this report's ({'; '.join(drift)}); build again with them and save "
                           "that build's JSON")
        else:
            if o.get("partial"):
                reasons.append(f"object '{o.get('name')}' was built in part (--only): not judged as a whole")
            if o.get("gate") == "FAIL" and not any(ck.get("state") == "FAIL" for ck in (o.get("checks") or {}).values()):
                reasons.append(f"object '{o.get('name')}': its gate was FAIL")
            for cid, ck in (o.get("checks") or {}).items():
                if ck.get("state") in ("FAIL", "UNVERIFIED") and ck.get("kind") == "hard":
                    reasons.append(f"object '{o.get('name')}' {cid} {ck['state']}: {ck.get('note', '')}".rstrip(": "))
                elif ck.get("state") == "WARN":
                    warns.append((f"object {o.get('name')} {cid}", ck.get("note", "")))
        entries.append(entry)
    if same_as_build and not drift:
        for p in build.get("parts") or []:
            for cid, ck in ((p.get("assembly") or {}).get("checks") or {}).items():
                if ck.get("state") in ("FAIL", "UNVERIFIED") and ck.get("kind") == "hard":
                    reasons.append(f"{p.get('name')} {cid} {ck['state']}: {ck.get('note', '')}".rstrip(": "))
                elif ck.get("state") == "WARN":
                    warns.append((f"{p.get('name')} {cid}", ck.get("note", "")))
    return entries, reasons, warns


def assembly_drift(build, specs):
    """Old object checks cannot prove a new grouping, role or free-part clearance."""
    import assembly
    # record can include STLs without an explicit _parts entry. They remain independent
    # objects by default, just as in build.finish. Keep newly declared, unbuilt parts too:
    # their membership is part of the current contract, and check_parts reports them.
    effective = {p["name"]: {} for p in build.get("parts") or []}
    effective.update(specs)
    try:
        current = assembly.input_fingerprint(effective)
    except assembly.AssemblyError as exc:
        return [f"invalid assembly metadata: {exc}"]
    if not build.get("assembly_sha256"):
        return ["build has no assembly fingerprint (before 0.6.1): build again and save the new JSON"]
    if current != build["assembly_sha256"]:
        unbuilt = sorted(set(specs) - {p["name"] for p in build.get("parts") or []})
        if unbuilt:                                   # --only, or a part dropped from the generator
            return [f"the build has only some of the parts in _parts (not built: {', '.join(unbuilt)}): "
                    "object checks need a build of every part; build them all and save the new JSON"]
        return ["assembly metadata changed since the build: build again and save the new JSON"]
    return []


def check_joints(verify, parts, taken=frozenset()):
    """Every declared joint's fit report. Each entry gets a `result` a promise can read: missing
    (no readable report), stale (not a report of the current parts), failed, open (a check that
    is neither PASS nor an accepted WARN), accepted (PASS apart from WARNs the user accepted as
    "joint <name> <check>") or passed; `measured` names the parts of this build it fitted."""
    if "joints" not in verify:
        return [], ["joints not declared (_verify.joints): F3 is not counted; list every joint with its fit "
                    "report, or [] when the design has none"], []
    entries, reasons, notes = [], [], []
    by_sha = {}
    for p in parts:
        if p.get("sha256"):
            by_sha.setdefault(p["sha256"], []).append(p)
    import fit
    for j in verify["joints"]:
        name, report = j.get("name") or j.get("report"), j.get("report")
        entry = {"name": name, "report": rel(report)}
        if not report or not os.path.isfile(report):
            entry.update(state="FAIL", result="missing")
            reasons.append(f"joint '{name}': fit report {rel(report)} not found; run fit.py and save it")
            entries.append(entry)
            continue
        try:
            fresh = fit.check_report(report)
        except (fit.FitError, OSError, ValueError) as exc:
            entry.update(state="FAIL", result="missing")
            reasons.append(f"joint '{name}': {exc}")
            entries.append(entry)
            continue
        rep = load_json(report, "fit report")
        f3f = fresh["checks"]["F3_fresh"]
        states = {k: v.get("state") for k, v in (rep.get("checks") or {}).items()}
        entry.update(fresh=f3f["state"], checks=states)
        if f3f["state"] != "PASS":
            reasons.append(f"joint '{name}': F3_fresh {f3f['state']}: {f3f.get('note', '')}")
        accepted, unaccepted = [], []
        for cid, st in states.items():
            if st == "PASS":
                continue
            if st == "WARN" and norm(f"joint {name} {cid}") in taken:
                accepted.append(cid)
                continue
            unaccepted.append(st)
            reasons.append(f"joint '{name}': {cid} {st}: {(rep['checks'][cid].get('note') or '')}".rstrip(": "))
        if not states:
            reasons.append(f"joint '{name}': the report has no checks")
        rparts = rep.get("parts") or {}
        shas = [(rparts.get(k) or {}).get("sha256") for k in ("a", "b")]
        unknown = [k for k, s in zip(("a", "b"), shas) if s not in by_sha]
        entry["measured"] = measured_parts(rparts, by_sha)
        foreign = False
        if j.get("proxy"):
            entry["proxy"] = True
            notes.append(f"joint '{name}' is checked against a proxy built from numbers: it shows the part agrees "
                         "with those numbers, not that the numbers are right")
            if len(unknown) == 2:
                foreign = True
                reasons.append(f"joint '{name}': neither STL the report measured is a part of this build")
        elif unknown:
            foreign = True
            reasons.append(f"joint '{name}': the report measured "
                           f"{', '.join(rel((rparts.get(k) or {}).get('path')) or k for k in unknown)}, which is not "
                           "a part of this build; mark the joint \"proxy\": true if that is a proxy of the mating "
                           "part, or fit the delivered parts")
        if f3f["state"] != "PASS" or foreign:
            entry["result"] = "stale"
        elif "FAIL" in unaccepted:
            entry["result"] = "failed"
        elif unaccepted or not states:
            entry["result"] = "open"
        else:
            entry["result"] = "accepted" if accepted else "passed"
        if accepted:
            entry["accepted"] = accepted
        entries.append(entry)
    return entries, reasons, notes


def measured_parts(rparts, by_sha):
    """The parts of this build a fit report measured. Byte-identical parts share a hash, so a
    side is matched by its path first and otherwise stands for every part with that hash."""
    names = []
    for k in ("a", "b"):
        side = rparts.get(k) or {}
        same = by_sha.get(side.get("sha256")) or []
        path = side.get("path")
        at = [p for p in same if path and p.get("stl")
              and os.path.normcase(os.path.abspath(p["stl"])) == os.path.normcase(os.path.abspath(path))]
        for p in at or same:
            if p.get("name") not in names:
                names.append(p.get("name"))
    return names


def check_strength(verify):
    """Every declared member's strength.py report; `result` as for joints (missing, failed, open,
    passed) and `manual`: its inputs were typed in, not taken from the build."""
    if "strength" not in verify:
        return [], ["members not declared (_verify.strength): P7 is not counted; list each member's strength.py "
                    "report, or [] when nothing carries load"], []
    entries, reasons, notes = [], [], []
    for s in verify["strength"]:
        name, report = s.get("name") or s.get("report"), s.get("report")
        entry = {"name": name, "report": rel(report)}
        if not report or not os.path.isfile(report):
            entry.update(state="FAIL", result="missing")
            reasons.append(f"member '{name}': strength report {rel(report)} not found; run strength.py and save it")
        else:
            rep = load_json(report, "strength report")
            if not isinstance(rep, dict) or rep.get("schema") != "3dprint-scout.strength/1":
                raise FinalizeError(f"{report}: not a strength.py report")
            entry.update(gate=rep.get("gate"), case=rep.get("case"), worst=rep.get("worst"), inputs=rep.get("inputs"),
                         manual=True)
            entry["result"] = {"PASS": "passed", "FAIL": "failed"}.get(rep.get("gate"), "open")
            if rep.get("gate") != "PASS":
                reasons.append(f"member '{name}': strength.py {rep.get('case')} {rep.get('gate')} (worst: "
                               f"{rep.get('worst')})")
            notes.append(f"member '{name}': strength.py took its sizes from the numbers it was given "
                         f"({json.dumps(rep.get('inputs'), separators=(',', ':'))}), not from the model: they must "
                         "be the dimension table's")
        entries.append(entry)
    return entries, reasons, notes


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


def same_value(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return a == b


def text_field(entry, key):
    v = entry.get(key)
    return isinstance(v, str) and bool(v.strip())


def check_dims(verify, params):
    """_verify.dims: the real-world sizes the design rests on (a phone, a plug), each tied to the
    params.json values the model is built from, with where they came from. Returns ({id: entry},
    declaration errors)."""
    out, errors = {}, []
    raw = verify.get("dims") or []
    ids = [d.get("id") for d in raw]
    for i, d in enumerate(raw):
        did = d.get("id")
        ok_id = isinstance(did, str) and bool(did.strip())
        label = f"dims '{did}'" if ok_id else f"dims entry {i + 1}"
        errs = []
        if not ok_id:
            errs.append(f"{label}: needs an id")
        elif ids.count(did) > 1:
            errs.append(f"{label}: the id is used more than once")
        unknown = sorted(k for k in d if k not in DIM_KEYS)
        if unknown:
            errs.append(f"{label}: unknown field {', '.join(unknown)} (fields: {', '.join(DIM_KEYS)})")
        if not text_field(d, "what"):
            errs.append(f"{label}: needs what (the object and the sizes, in words)")
        src = d.get("source")
        if src not in DIM_SOURCES:
            errs.append(f"{label}: source must be one of {', '.join(DIM_SOURCES)}")
        elif src == "caliper" and d.get("by") != "user":
            errs.append(f"{label}: a caliper value needs \"by\": \"user\" (only the user can measure the object)")
        elif src == "spec" and not text_field(d, "url"):
            errs.append(f"{label}: a spec value needs the url of the spec")
        if "tol" in d and not (isinstance(d["tol"], (int, float)) and not isinstance(d["tol"], bool)
                               and d["tol"] == d["tol"] and 0 <= d["tol"] < float("inf")):
            errs.append(f"{label}: tol must be a number of 0 or more")
        p = d.get("params")
        if not isinstance(p, dict) or not p:
            errs.append(f"{label}: params must map the params.json keys the model is built from to their values")
        else:
            for k, v in p.items():
                found, cur = lookup(params, k)
                if not found:
                    errs.append(f"{label}: {k} is not in params.json (the model must be built from these numbers)")
                elif not same_value(cur, v):
                    errs.append(f"{label}: {k} is {json.dumps(v)} here but {json.dumps(cur)} in params.json")
        entry = {"id": did, "what": d.get("what"), "source": src, "params": p,
                 "state": "error" if errs else DIM_STATE[src]}
        entry.update({k: d[k] for k in ("unit", "tol", "by", "url") if k in d})
        if errs:
            entry["errors"] = errs
            errors += errs
        if ok_id and did not in out:
            out[did] = entry
        elif ok_id:
            out[did]["state"] = "error"
        else:
            out[f"#{i + 1}"] = entry
    return out, errors


def evidence_index(verify, key, entries):
    """{name: [(declaration, checked entry)]} for joints or strength, in declaration order."""
    index = {}
    for raw, entry in zip(verify.get(key) or [], entries):
        if isinstance(entry.get("name"), str):
            index.setdefault(entry["name"], []).append((raw, entry))
    return index


def promise_state(errs, failed, notver, excluded, assumed, accepted):
    if errs:
        return "error"
    if failed:
        return "failed"
    if excluded:
        return "excluded"
    if notver:
        return "not verified"
    if assumed:
        return "assumed"
    if accepted:
        return "accepted"
    return "verified"


def check_promises(verify, params, joints, strength, parts):
    """The use tier: each promise made to the user, judged by its own evidence. A promise is
    verified only when it says under which conditions it holds and what counts as success, its
    evidence is of a kind allowed for it, of the current parts and passed, and nothing it rests
    on is an unmeasured size. Returns a dict with tier, promises, counts, dims, errors, open."""
    dims, errors = check_dims(verify, params)
    out = {"tier": "not declared", "promises": [], "counts": {}, "dims": list(dims.values()), "errors": errors,
           "open": []}
    for key in ("joints", "strength"):
        for raw in verify.get(key) or []:
            jd = raw.get("dims")
            if jd is not None and not (isinstance(jd, list) and all(isinstance(x, str) for x in jd)):
                errors.append(f"{key[:-1] if key == 'joints' else 'member'} '{raw.get('name') or raw.get('report')}': "
                              "dims must be a list of _verify.dims ids")
    promises = verify.get("promises")
    ids = [p.get("id") for p in promises or []]
    excluded = {}
    for a in verify.get("accepted") or []:
        if "promise" not in a:
            continue
        pid = a.get("promise")
        if not (isinstance(pid, str) and pid.strip()):
            errors.append(f"accepted entry {json.dumps(a, ensure_ascii=False)}: promise must be a promise id")
        elif "check" in a:
            errors.append(f"accepted entry for promise '{pid}': name a promise or a check, not both")
        elif pid not in ids:
            errors.append(f"accepted entry: there is no promise '{pid}' in _verify.promises")
        elif not text_field(a, "reason"):
            errors.append(f"accepted entry for promise '{pid}': needs the user's reason")
        elif a.get("by") != "user":
            errors.append(f"accepted entry for promise '{pid}': only the user can take a promise without "
                          "verifying it (\"by\": \"user\")")
        else:
            excluded[pid] = a["reason"]
    if promises is None:
        out["open"].append("promises not declared (_verify.promises): what the user was promised is not checked; "
                           "list each promise with its evidence")
    elif not promises:
        out["open"].append("the promise list (_verify.promises) is empty: an empty list verifies nothing; list what "
                           "the user was promised")
    gate = {p.get("name"): p.get("gate") for p in parts}
    index = {"joint": evidence_index(verify, "joints", joints),
             "strength": evidence_index(verify, "strength", strength)}
    for i, pr in enumerate(promises or []):
        pid, kind = pr.get("id"), pr.get("kind")
        ok_id = isinstance(pid, str) and bool(pid.strip())
        label = f"promise '{pid}'" if ok_id else f"promise {i + 1}"
        errs, failed, notver, assumed, acc = [], [], [], [], []
        if not ok_id:
            errs.append("needs an id")
        elif ids.count(pid) > 1:
            errs.append("the id is used more than once")
        unknown = sorted(k for k in pr if k not in PROMISE_KEYS)
        if unknown:
            errs.append(f"unknown field {', '.join(unknown)} (fields: {', '.join(PROMISE_KEYS)})")
        if kind not in KINDS:
            errs.append(f"kind must be one of {', '.join(KINDS)}")
        if not text_field(pr, "text"):
            errs.append("needs text (the promise in the user's words)")
        for f in NEEDS[kind] if kind in KINDS else ():
            if not text_field(pr, f):
                errs.append(f"a {kind} promise needs {f} ("
                            + ("under which conditions it must hold" if f == "conditions" else "what counts as success")
                            + ")")
        rests = []
        assumes = pr.get("assumes", [])
        if not (isinstance(assumes, list) and all(isinstance(x, str) for x in assumes)):
            errs.append("assumes must be a list of _verify.dims ids")
        else:
            rests += [(d, "the promise") for d in assumes]
        evidence, ev_out = pr.get("evidence"), []
        if evidence is None or evidence == []:
            notver.append("no evidence yet")
        elif not isinstance(evidence, list):
            errs.append("evidence must be a list")
            evidence = []
        for item in evidence or []:
            if not isinstance(item, dict):
                errs.append(f"evidence item {json.dumps(item, ensure_ascii=False)} must be an object")
                continue
            if "covers" in item and not isinstance(item["covers"], str):
                errs.append("covers must be text (what the evidence covers)")
            named = [k for k in item if k != "covers"]
            if len(named) != 1:
                errs.append(f"evidence item {json.dumps(item, ensure_ascii=False)} must name one of "
                            f"{', '.join(EVIDENCE)}")
                continue
            k, name = named[0], item[named[0]]
            if not (isinstance(name, str) and name.strip()):
                errs.append(f"evidence item {json.dumps(item, ensure_ascii=False)}: name the {k} with its text name")
                continue
            if k == "check":
                errs.append(f"'{name}' is a check of a part: it proves the part, not a promise; use "
                            f"{', '.join(ALLOWED.get(kind) or EVIDENCE)}")
                continue
            if k not in EVIDENCE:
                errs.append(f"unknown evidence kind '{k}' (finalize reads {', '.join(EVIDENCE)})")
                continue
            if kind in KINDS and k not in ALLOWED[kind]:
                errs.append(f"{k} is not evidence for a {kind} promise ("
                            + (f"it takes {', '.join(ALLOWED[kind])}" if ALLOWED[kind] else
                               "no evidence of it is read here yet") + ")")
                continue
            matches = index[k].get(name, [])
            where = "_verify.joints" if k == "joint" else "_verify.strength"
            if not matches:
                errs.append(f"there is no {k} '{name}' in {where}")
                continue
            if len(matches) > 1:
                errs.append(f"{len(matches)} entries in {where} are named '{name}'")
                continue
            raw, entry = matches[0]
            res = entry.get("result")
            ev = {k: name, "result": res}
            if "covers" in item:
                ev["covers"] = item["covers"]
            ev_out.append(ev)
            what = f"joint '{name}'" if k == "joint" else f"member '{name}'"
            if res == "missing":
                notver.append(f"{what}: no report")
            elif res == "stale":
                notver.append(f"{what}: its fit report is not of the current parts")
            elif res == "failed":
                failed.append(f"{what} failed")
            elif res == "open":
                notver.append(f"{what}: not every check passed" if k == "joint" else
                              f"{what}: strength.py gate {entry.get('gate')}")
            elif res == "accepted":
                acc.append(f"{what}: passed apart from WARNs the user accepted ({', '.join(entry['accepted'])})")
            if k == "joint":
                bad = [n for n in entry.get("measured") or [] if gate.get(n) == "FAIL"]
                if bad:
                    notver.append(f"{what} fitted {', '.join(bad)}, whose own checks FAIL")
                if raw.get("proxy") and not raw.get("dims"):
                    assumed.append(f"{what} is fitted against a proxy whose sizes are not declared (dims)")
            elif res == "passed" and entry.get("manual"):
                notver.append(f"{what}: its inputs were typed in, not taken from the build's parameters")
            jd = raw.get("dims")
            if isinstance(jd, list):
                rests += [(d, what) for d in jd if isinstance(d, str)]
        rests_on = []
        for did, via in rests:
            if did not in rests_on:
                rests_on.append(did)
            d = dims.get(did)
            if d is None:
                errs.append(f"{via} rests on dims '{did}', which is not in _verify.dims")
            elif d["state"] == "error":
                errs.append(f"dims '{did}' has a declaration error")
            elif d["state"] == "assumed":
                line = f"rests on '{did}' ({d.get('what')}), which is assumed, not measured"
                if line not in assumed:
                    assumed.append(line)
        state = promise_state(errs, failed, notver, ok_id and pid in excluded, assumed, acc)
        reasons = errs + failed + notver + assumed + acc
        if state == "excluded":
            reasons.insert(0, f"taken by the user without verifying it: {excluded[pid]}")
        entry = {"id": pid, "kind": kind, "text": pr.get("text")}
        entry.update({f: pr[f] for f in ("conditions", "success") if f in pr})
        entry.update(state=state, reasons=reasons, evidence=ev_out, rests_on=rests_on)
        out["promises"].append(entry)
        counts = out["counts"].setdefault(kind if kind in KINDS else "?", {})
        counts[state] = counts.get(state, 0) + 1
        if state != "verified":
            out["open"].append(f"{label} ({kind}) {state}: {'; '.join(reasons)}")
    states = [p["state"] for p in out["promises"]]
    if errors:
        out["tier"] = "error"
        out["open"][:0] = errors
    elif states:
        out["tier"] = min(states, key=STATES.index)
    return out


def check_prints(verify):
    entries, lines = [], []
    for t in verify.get("test_prints") or []:
        st = str(t.get("status", "")).lower()
        if st not in PRINT_STATUS:
            raise FinalizeError(f"test print '{t.get('name')}': status must be one of {', '.join(PRINT_STATUS)}")
        entries.append({"name": t.get("name"), "status": st, "note": t.get("note")})
        if st != "passed":
            lines.append(f"test print '{t.get('name')}': {st}" + (f" ({t['note']})" if t.get("note") else ""))
    return entries, lines


def check_references(verify, objects):
    if "references" not in verify:
        return {}, ["reference coverage not declared (_verify.references): the shape is not verified from any "
                    "direction"]
    out, lines = {}, []
    refs = verify["references"]
    for obj, slots in refs.items():
        bad = [d for d in slots if d not in DIRECTIONS]
        if bad:
            raise FinalizeError(f"references for '{obj}': unknown direction {bad} (use {', '.join(DIRECTIONS)})")
        cov = {d: str(slots.get(d, "none")).lower() for d in DIRECTIONS}
        wrong = {d: v for d, v in cov.items() if v not in COVERAGE}
        if wrong:
            raise FinalizeError(f"references for '{obj}': {wrong} (use {', '.join(COVERAGE)})")
        real = [d for d in DIRECTIONS if cov[d] == "real"]
        out[obj] = {"coverage": cov, "verified_from": real,
                    "not_verified_from": [d for d in DIRECTIONS if cov[d] != "real"]}
        if len(real) < len(DIRECTIONS):
            lines.append(f"{obj}: shape not verified from " + ", ".join(f"{d} ({cov[d]})" for d in DIRECTIONS
                                                                          if cov[d] != "real"))
    for name in objects:
        if name not in refs:
            lines.append(f"{name}: no reference coverage declared")
    return out, lines


def threemf_manifests(folders):
    """Every 3MF manifest in the folders: {artifact sha256: manifest}; a manifest whose `parts`
    is not a map of part names to sha256 strings is {"_malformed": its file name}."""
    found = {}
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for root, _dirs, files in os.walk(folder):
            for fn in files:
                if fn.endswith(".3mf.manifest.json"):
                    try:
                        with open(os.path.join(root, fn), encoding="utf-8") as f:
                            m = json.load(f)
                    except (OSError, ValueError):
                        continue
                    if not (isinstance(m, dict) and m.get("schema") == MANIFEST_3MF
                            and isinstance(m.get("artifact_sha256"), str) and m["artifact_sha256"]):
                        continue
                    sha, parts = m["artifact_sha256"], m.get("parts")
                    if isinstance(parts, dict) and parts and all(isinstance(k, str) and isinstance(v, str)
                                                                 for k, v in parts.items()):
                        found[sha] = m
                    elif sha not in found:              # never in place of a sound one
                        found[sha] = {"_malformed": fn}
    return found


def check_delivered(deliver, parts, build):
    """Every STL and 3MF in the delivery folder against the verified STLs."""
    entries, reasons = [], []
    if not os.path.isdir(deliver):
        return [], [f"delivery folder {rel(deliver)} not found"]
    by_sha = {}
    for p in parts:
        if p.get("sha256"):
            by_sha.setdefault(p["sha256"], []).append(p["name"])
    covered = set()
    out_dirs = {os.path.dirname(p["stl"]) for p in parts if p.get("stl")} | {os.path.dirname(build.get("threemf") or "")}
    manifests = threemf_manifests([deliver, *out_dirs])
    for fn in sorted(os.listdir(deliver)):
        path = os.path.join(deliver, fn)
        if not os.path.isfile(path):
            continue
        low = fn.lower()
        if low.endswith(".stl"):
            sha = validate.file_sha256(path)
            names = by_sha.get(sha) or []
            stem = os.path.splitext(fn)[0]
            name = (stem if stem in names else next((n for n in names if n not in covered), names[0])) if names else None
            entries.append({"file": rel(path), "kind": "stl", "part": name, "same_as_verified": bool(names)})
            if not names:
                reasons.append(f"{rel(path)} is not one of the verified STLs (an older build, or another part): "
                               "copy the verified file, or take it out of the delivery")
            else:
                covered.add(name)                         # one file per part, even for identical parts
        elif low.endswith(".3mf"):
            sha = validate.file_sha256(path)
            m = manifests.get(sha)
            entry = {"file": rel(path), "kind": "3mf", "manifest": bool(m)}
            if m and m.get("_malformed"):
                entry["manifest"] = False
                reasons.append(f"{rel(path)}: its manifest {m['_malformed']} is malformed (`parts` must map each part "
                               "name to its STL's sha256): write the 3MF again with build.py / bambu3mf.py")
            elif not m:
                reasons.append(f"{rel(path)}: no 3MF manifest says which STLs it was written from (copy "
                               f"{fn}.manifest.json along, or write it with build.py / bambu3mf.py from the verified STLs)")
            else:
                stale = [n for n, s in (m.get("parts") or {}).items() if s not in by_sha]
                entry["parts"] = sorted((m.get("parts") or {}).keys())
                entry["same_as_verified"] = not stale
                if stale:
                    reasons.append(f"{rel(path)} was written from STLs that are not the verified ones "
                                   f"({', '.join(stale)}): write it again from the verified STLs")
                else:
                    covered.update(n if n in by_sha[s] else by_sha[s][0] for n, s in m["parts"].items())
            entries.append(entry)
    for p in parts:
        if p.get("sha256") and p["name"] not in covered:
            reasons.append(f"{p['name']}: not in the delivery ({rel(deliver)}) as an STL or in a 3MF")
    return entries, reasons


def own_sources(build):
    """The generator's own files among the build's sources (not the skill's libraries)."""
    lib = {os.path.normcase(os.path.abspath(d)) for d in (HERE, ENGINES_DIR)}
    return [s for s in build.get("sources") or []
            if os.path.normcase(os.path.dirname(os.path.abspath(s))) not in lib]


def holds_machine_path(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    return any(re.search(re.escape(form) + r"(?![\w-])", text, flags=re.IGNORECASE) for form, _ in machine_forms())


BUNDLE_OWN = ("params.json", "printers.json", "REPRODUCE.md", "verification.json")


def bundle_path(src):
    """Where a source goes in the bundle: its path relative to the working folder (the folder the
    build ran in), so an import, an include or a loaded file still finds it; None outside it."""
    try:
        r = os.path.relpath(os.path.abspath(src))
    except ValueError:                                   # another drive on Windows
        return None
    return None if r == ".." or r.startswith(".." + os.sep) else r.replace(os.sep, "/")


def write_bundle(folder, build, params_path, settings, report):
    if os.path.exists(folder):
        raise FinalizeError(f"{folder} exists; the bundle goes into a new folder (never overwrites)")
    srcs = own_sources(build)
    printers = settings.printer if settings.printer and os.path.isfile(settings.printer) else None
    files = [*srcs, params_path] + ([printers] if printers else [])
    leaking = [rel(f) for f in files if holds_machine_path(f)]
    if leaking:
        raise FinalizeError(f"{', '.join(leaking)} holds a path of this machine; take it out (a name, not a path) "
                            "before bundling")
    places = {src: bundle_path(src) for src in srcs}
    outside = [os.path.basename(src) for src, place in places.items() if place is None]
    if outside:
        raise FinalizeError(f"{', '.join(outside)} is outside the folder the build ran in; the bundle keeps every "
                            "source at its place relative to that folder (imports, includes and loaded files depend "
                            "on it): move it into the project folder and build again")
    clash = [place for place in places.values() if place.lower() in {n.lower() for n in BUNDLE_OWN}]
    if clash:
        raise FinalizeError(f"{', '.join(clash)} would take the place of a file the bundle writes itself; rename it")
    os.makedirs(folder)
    written = []
    for src in srcs:
        dst = os.path.join(folder, *places[src].split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(rel(dst))
    shutil.copyfile(params_path, os.path.join(folder, "params.json"))
    written.append(rel(os.path.join(folder, "params.json")))
    if printers:
        shutil.copyfile(printers, os.path.join(folder, "printers.json"))
        written.append(rel(os.path.join(folder, "printers.json")))
    main_src = build.get("source") or (srcs[0] if srcs else None)
    main = (bundle_path(main_src) or os.path.basename(main_src)) if main_src else "model"
    engine = build.get("engine") or "?"
    flags = []
    if printers:
        flags.append("--printer printers.json")
    for f in ("printer_id", "tools", "tol", "overhang_angle", "min_wall"):
        if getattr(settings, f, None) is not None:
            flags.append(f"--{f.replace('_', '-')} {getattr(settings, f)}")
    if settings.wall_check is False:
        flags.append("--no-wall-check")
    flag_text = (" " + " ".join(flags)) if flags else ""
    lines = ["# Reproduce", "",
             f"Engine: {engine}. Generator: `{main}`. Parameters: `params.json`. Run from this folder, with "
             "`SKILL_DIR` the 3dprint-scout skill folder.", ""]
    if engine in ("openscad", "python", "blender"):
        lines += ["```bash", f'python3 "$SKILL_DIR/scripts/build.py" run {main} --params params.json --out out{flag_text} > build.json',
                  "```", ""]
    else:
        lines += [f"This build was recorded (`build.py record`, engine {engine}): run the generator in {engine}, export "
                  "one STL per part named after the part into `out/`, then:", "", "```bash",
                  f'python3 "$SKILL_DIR/scripts/build.py" record out/<part>.stl ... --source '
                  f'{" ".join(places[s] for s in srcs) or main} --params params.json --engine {engine} '
                  f"--out out{flag_text} > build.json", "```", ""]
    lines += ["Then re-check:", "", "```bash",
              'python3 "$SKILL_DIR/scripts/finalize.py" --build build.json --params params.json', "```", "",
              "`verification.json` is the report this delivery was made with: what was verified, and what was not.", ""]
    with open(os.path.join(folder, "REPRODUCE.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    written.append(rel(os.path.join(folder, "REPRODUCE.md")))
    written.append(rel(os.path.join(folder, "verification.json")))
    report["bundle"] = written
    with open(os.path.join(folder, "verification.json"), "w", encoding="utf-8") as f:
        f.write(scrub(json.dumps(report, indent=2, ensure_ascii=False)))
    return written


def finalize(args):
    build = load_json(args.build, "build report")
    if not isinstance(build, dict) or build.get("schema") != "3dprint-scout.build/1":
        raise FinalizeError(f"{args.build}: not a build.py run / record report")
    params = load_json(args.params, "params")
    if not isinstance(params, dict):
        raise FinalizeError(f"{args.params}: not a params object")
    specs = part_specs(params)
    verify = params.get("_verify") or {}
    if not isinstance(verify, dict):
        raise FinalizeError("_verify in params.json must be an object")
    check_verify_shape(verify)
    settings = settings_for(build, args)
    out = {"schema": SCHEMA, "ran": True, "build": rel(args.build), "engine": build.get("engine"),
           "use": None, "geometry": None, "shape": {}, "slicing": "unverified", "print": "unverified",
           "settings": {f: getattr(settings, f) for f in SETTINGS} | {"wall_check": settings.wall_check},
           "parts": [], "objects": [], "joints": [], "strength": [], "test_prints": [], "open": [],
           "accepted": [], "assumptions": list(params.get("_assumptions") or []),
           "unverified_dimensions": list(verify.get("unverified") or []), "warnings": [], "errors": []}
    out["settings"]["printer"] = rel(settings.printer)
    reasons = check_build(build)
    parts, r, warns, to_decide, copied, same_as_build = check_parts(build, specs, args.params, settings)
    out["parts"] = parts
    reasons += r
    drift = settings_drift(build, settings)
    out["settings_drift"] = drift
    metadata_drift = assembly_drift(build, specs)
    out["assembly_drift"] = metadata_drift
    reasons += metadata_drift
    objs, r, w = check_objects(build, same_as_build, drift + metadata_drift)
    out["objects"] = objs
    reasons += r
    warns += w
    accepted = verify.get("accepted") or []
    out["accepted"] = accepted
    taken = {norm(a["check"]) for a in accepted if "check" in a}
    joints, r, notes = check_joints(verify, parts, taken)
    out["joints"] = joints
    reasons += r
    out["warnings"] += notes
    strength, r, notes = check_strength(verify)
    out["strength"] = strength
    reasons += r
    out["warnings"] += notes
    prints, print_lines = check_prints(verify)
    out["test_prints"] = prints
    use = check_promises(verify, params, joints, strength, parts)
    out["use"] = use["tier"]
    out["promises"], out["promise_counts"], out["dims"] = use["promises"], use["counts"], use["dims"]
    out["promise_errors"] = use["errors"]
    open_warns = [f"{who} WARN: {note}".rstrip(": ") for who, note in warns if norm(who) not in taken]
    reasons += [text for who, text in copied if norm(who) not in taken]
    if args.deliver:
        delivered, r = check_delivered(args.deliver, parts, build)
        out["delivered"] = delivered
        reasons += r
    shape, shape_lines = check_references(verify, [o["name"] for o in build.get("objects") or []])
    out["shape"] = shape
    geometry_ok = not reasons and not open_warns
    out["geometry"] = "verified" if geometry_ok else "not verified"
    passed = [t["name"] for t in prints if t["status"] == "passed"]
    out["print"] = ("unverified (test prints passed: " + ", ".join(passed) + "; the final part is not printed)"
                    if passed else "unverified")
    out["open"] = (use["open"] + reasons
                   + [f"open warning (not accepted in _verify.accepted): {w}" for w in open_warns]
                   + to_decide + print_lines + shape_lines
                   + [f"unverified: {u}" for u in out["unverified_dimensions"]]
                   + [f"assumption: {a}" for a in out["assumptions"]])
    unlinked = len(out["assumptions"]) + len(out["unverified_dimensions"])
    if out["use"] == "not declared":
        use_line = "use: not declared (_verify.promises)"
    else:
        tally = {}
        for p in out["promises"]:
            tally[p["state"]] = tally.get(p["state"], 0) + 1
        parts_of = ([plural(len(out["promises"]), "promise") + ": "
                     + ", ".join(f"{tally[s]} {s}" for s in STATES if s in tally)] if out["promises"] else [])
        parts_of += [plural(len(use["errors"]), "declaration error")] if use["errors"] else []
        parts_of += [plural(unlinked, "assumption") + " not linked to a promise"] if unlinked else []
        use_line = f"use: {out['use']} ({'; '.join(parts_of)})"
    out["summary"] = [
        use_line,
        "geometry: " + ("verified (every part, object, declared joint and member checked; the delivered files are "
                        "the verified ones)" if geometry_ok and args.deliver else
                        "verified (every part, object, declared joint and member checked)" if geometry_ok else
                        f"not verified ({len(reasons) + len(open_warns)} open items)"),
        "shape: " + ("; ".join(f"{o} from {', '.join(v['verified_from']) or 'no direction'}" for o, v in shape.items())
                     or "not declared"),
        "slicing: unverified (not sliced here)",
        "print: " + out["print"]]
    if args.bundle:
        write_bundle(args.bundle, build, args.params, settings, out)
    return json.loads(scrub(json.dumps(out, ensure_ascii=False)))


def main(argv=None):
    ap = JsonArgParser(description="final verification report of a build (Phase 6)")
    ap.add_argument("--build", required=True, help="the saved JSON of build.py run / record")
    ap.add_argument("--params", default=os.path.join(".3dprint", "params.json"))
    ap.add_argument("--printer", help="printers.json (default: the one the build used)")
    ap.add_argument("--printer-id", help="printer id in printers.json (default: the build's)")
    ap.add_argument("--tools", help="tool ids (default: the build's)")
    ap.add_argument("--tol", type=float, help="D1 tolerance (default: the build's)")
    ap.add_argument("--overhang-angle", type=float, help="P2 limit (default: the build's)")
    ap.add_argument("--min-wall", type=float, help="P3 minimum wall (default: the build's)")
    ap.add_argument("--no-wall-check", dest="wall_check", action="store_false", default=None,
                    help="skip P3 (default: as the build did)")
    ap.add_argument("--deliver", help="the delivery folder: its STLs and 3MFs must be the verified ones")
    ap.add_argument("--bundle", help="a new folder for the sources, params, this report and REPRODUCE.md")
    try:
        args = ap.parse_args(argv)
        out = finalize(args)
        code = 0
    except (FinalizeError, OSError) as exc:
        out = {"schema": SCHEMA, "ran": False, "use": None, "geometry": None, "warnings": [],
               "errors": [scrub(str(exc))]}
        code = 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
