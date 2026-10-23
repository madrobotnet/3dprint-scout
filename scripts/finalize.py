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
                  "dims": ["usb-c-plug"], "proxy_build": "out/plug/build.json"}],
    "strength": [{"name": "latch arm", "report": "out/strength_latch.json"}],
    "measurements": [{"name": "lip height", "report": "out/m_lip.json"}],
    "seen": [{"name": "front look", "image": "out/look.png", "image_sha256": "...", "by": "user",
              "promises": ["wave-back"], "result": "passed"}],
    "test_prints": [{"name": "hinge coupon", "status": "skipped", "note": "user had no time"},
                    {"name": "lid fit", "status": "passed", "promises": ["lid-fits"], "printer": "x2d",
                     "orientation": "as built", "by": "user", "preset": "0.20mm Standard",
                     "parts": {"lid": {"sha256": "...", "material": "pla_basic"}},
                     "photos": ["photos/lid-fit.jpg"]}],
    "accepted": [{"check": "body P2", "reason": "the user wants supports there"},
                 {"check": "object box P2", "reason": "..."},
                 {"check": "joint lid on box F3", "reason": "a snug lid"},
                 {"promise": "wave-back", "reason": "the user judges it on the print", "by": "user"}],
    "unverified": ["wall behind the label: estimated from a photo"],
    "references": {"lid": {"front": "real", "top": "real", "back": "estimated", "bottom": "assumed"}}
  }

joints: every joint F3 must cover, with its saved fit.py report: the report must be fresh (its
STLs are the parts being delivered, or a declared proxy) and its own F3 / F3_sweep must PASS
(a WARN the user accepted as "joint <name> <check>" counts as accepted); a report without F3,
or without F3_sweep for a joint marked "sweep": true (a moving part), is not a passed fit. A
proxy names the dims it is built from and, as proxy_build, the saved JSON of the
`build.py run --proxy` that made it from its own params file; the numbers in that file must be
exactly the ones the dims declare. An empty list says the design has no joint. strength: strength.py reports
(saved JSON), their gate must PASS (a WARN the user accepted as "member <name>" counts as
accepted). A report made with `strength.py --from-build out/build.json --part NAME --param
INPUT=PARAM` (from_build, inputs_from) stands while NAME is a part of this build with the
sha256 it read, every parameter it took has the same value in this build's `parameters`
(a dotted path for a nested one), and its material is the part's material now; otherwise it is
stale, by name ("h was ribbon_t = 4.5, now 5.0"), and the geometry is not verified. An input
typed on the command line (origin `manual`; every input of a report made without --from-build)
is a number from the dimension table, not read from the model, so the report says to keep them
equal. The build records each part's material: one that differs from params.json now is open
("<part>: material changed since the build"). test_prints: coupons and mechanism-first
prints (status passed, failed, skipped, offered or pending; photos, optional: the user's photos
of a print, paths in the project folder, which the bundle carries; they are no evidence).
accepted: WARNs the user accepted, named "<part> <check>" or "object <name> <check>", with their
reason; any other WARN is open
("<part> D1" also accepts a D1 whose expect was copied from the model, when no intended size
exists); and promises the user takes without verifying them ("by": "user"). unverified:
estimated sizes no promise rests on (a real-world size a promise rests on is a dims entry,
assumed when nobody measured it). references: for each object, which directions a
reference shows (`real`), or was generated or inferred (`estimated`), or given up on
(`assumed`); a direction without a real reference is one whose shape is not verified.

promises: what the user was promised, each judged by its own evidence. kind `use` (a thing the
user does with the object: needs conditions and success), `feature` (needs success) or `look`.
Evidence names a declared joint, member, measurement, seen image or test print; a use takes
joints, members, measurements and test prints, a feature joints, measurements and test prints,
a look seen images and test prints; a part's own check (box M1) is never evidence of a promise.
seen: a person's judgement of a preview image (by user or agent, the promises judged, passed or
failed, and image_sha256, the digest they looked at); it stands while the image is those bytes,
its sidecar says so, and every STL the sidecar lists is a part of this build now; only the
user's judgement verifies. A test print that lists promises stands for them when it printed the
parts as they are now (parts: name -> sha256, material), in each part's material (_material,
_parts.<name>.material: strength.py keys) unchanged since the build, on the build's printer, as
built, under the delivered preset (_print.preset, and with --deliver the process preset of the
Bambu project the part is in; none recorded leaves it assumed), by the user. A member is
evidence of a use only from a --from-build report with nothing typed in. measurements:
saved `measure.py ... --expect` reports, each fresh while the file it read is unchanged (its
sha256), passed when every expectation passed (finalize runs the report's command again on the
file and reads each value itself); as evidence it must have read a part of this
build. dims: the real-world sizes the design rests on, each tied to the params.json values the
model is built from (they must be equal), with its source: assumed, caliper ("by": "user"),
spec (its url, and where each number is in it: finalize reads no spec, so these are listed in
open for the person to check) or user-file (from: each parameter's measurement of the user's
file, which must be fresh, passed, of no part of this build, and within tol of the value;
otherwise the entry is unbacked and a promise on it not verified). A promise rests on the
dims its evidence names (and on its own `assumes`); a proxy joint that names none, or no
proxy_build, or built from numbers its dims do not declare, rests on undeclared sizes. Each promise gets one state: error (declared wrongly),
failed (its evidence failed, whatever else), excluded (the user took it unverified), not
verified (no evidence, stale evidence, evidence on a part whose checks FAIL, a proxy built from
other values, a member's inputs typed in, a material changed since the build or another in the
delivered print file), assumed (it passed on an unmeasured size, or on a print file whose
material cannot be read), accepted (it passed with a WARN the user accepted) or verified.

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
delivered in one or the other; a malformed manifest is a reason, not an error. A Bambu
project's manifest (bambu3mf.py) also names each part's filament and the process preset: a
filament of another material than the part's leaves the part's material-dependent evidence (a
--from-build member of it, a test print of it) not verified, one finalize cannot name
(strength.material_of_filament) leaves it assumed, as does a part in no Bambu project (another
slicer: the print file's material is not checked); a process preset other than _print.preset
keeps test prints of its parts from verifying, and without _print.preset it is the delivered
preset they are compared with; a project that names no process preset leaves them assumed. These are open lines, not geometry reasons. --bundle DIR
writes a new folder that holds what it takes to reach this verdict again from it alone: the
generator sources (not the skill's own libraries) at their places relative to the folder the
build ran in (lib/helper.py stays lib/helper.py, so imports, includes and loaded files still
resolve), params.json, the printers.json the build used, this report, REPRODUCE.md (the
commands that rebuild the parts and each proxy `build.py run --proxy` made, then re-check),
and the evidence: every report _verify names (fit, strength, measurement) with each file it
read that is not a part (a measured user file); a proxy's generator and params file (a
recorded proxy also with its build JSON, STLs and build manifests: it cannot be built again);
each seen image and its sidecar; the test print photos; and with --deliver the delivered STLs
and 3MFs, each 3MF with its manifest beside it (REPRODUCE.md re-checks them with --deliver).
Every file keeps its path relative to the project folder, so the commands run as written
inside the bundle; the parts and the proxies built by `run` are built again there, not copied
(their build JSON records paths of this machine; a proxy no longer built from its params file
is carried as it was, its build JSON listed as left out). A file that is named but not found is
listed in REPRODUCE.md and in bundle_missing (a missing report is missing in the verdict too).
It refuses an existing folder, a file outside the project folder, and a source, params file or
report that holds a path of this machine (the scripts record the paths they are given: give
them relative ones). Exit 0 when it ran (read "use" and "geometry"), 1 on a usage or file error.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import posixpath
import re
import shlex
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
    lists = {"joints": dict, "strength": dict, "measurements": dict, "seen": dict, "test_prints": dict, "accepted": dict,
             "unverified": str,
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
        needed = ["F3"] + (["F3_sweep"] if j.get("sweep") else [])   # a moving joint declares its sweep
        absent = [c for c in needed if c not in states]
        if not states:
            reasons.append(f"joint '{name}': the report has no checks")
        elif absent:
            reasons.append(f"joint '{name}': the report has no {' or '.join(absent)}"
                           + (" (run fit.py with --sweep-angles)" if "F3_sweep" in absent else ""))
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
                reasons.append(f"joint '{name}': the part it was fitted to has changed since (neither STL the report "
                               "measured is a part of this build now): run fit.py again")
            entry["proxy_build"], note, built_from = proxy_provenance(j, [rparts.get(k) or {} for k in unknown])
            if note:
                entry["proxy_note"] = note
            if built_from is not None:
                entry["proxy_params"] = built_from
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
        elif unaccepted or not states or absent:
            entry["result"] = "open"
        else:
            entry["result"] = "accepted" if accepted else "passed"
        if accepted:
            entry["accepted"] = accepted
        entries.append(entry)
    return entries, reasons, notes


def proxy_provenance(j, sides):
    """Whether the proxy a joint was fitted against is tied to the numbers it stands for: generated
    by `build.py run` (the joint's `proxy_build` names that build's JSON; a `record` manifest is
    not the generator's word) from its params file as it is now. Returns (tied | untied | stale,
    note, the engine parameters the proxy was built from when tied)."""
    if len(sides) != 1:                               # two: not this build's fit; none: no proxy in it
        return "stale", ("the fit report measured no proxy, only parts of this build: drop \"proxy\" or fit the proxy"
                         if not sides else "the part it was fitted to has changed since"), None
    pb = j.get("proxy_build")
    if not pb:
        return "untied", "no proxy_build names the build.py run that made the proxy", None
    try:
        b = load_json(pb, "proxy build")
    except FinalizeError as exc:
        return "stale", str(exc), None
    if not isinstance(b, dict) or b.get("schema") != "3dprint-scout.build/1":
        return "stale", f"{rel(pb)} is not a build.py run / record report", None
    if not (isinstance(b.get("sources"), list) and isinstance(b.get("parts"), list)):
        return "stale", f"{rel(pb)} lists no sources or parts", None
    sources = [s for s in b["sources"] if isinstance(s, str)]
    missing = [s for s in sources if not os.path.isfile(s)]
    if not sources or missing:
        return "stale", f"the sources {rel(pb)} hashed are missing: {', '.join(missing) or 'none listed'}", None
    pp = b.get("params")
    if not (isinstance(pp, str) and os.path.isfile(pp)):
        return "stale", f"{rel(pb)} names no params file the proxy was built from (build it again)", None
    try:
        proxy_params = load_json(pp, "proxy params")
    except FinalizeError as exc:
        return "stale", str(exc), None
    if not isinstance(proxy_params, dict):
        return "stale", f"{rel(pp)} is not a params object", None
    for side in sides:
        sha = side.get("sha256")
        part = next((p for p in b["parts"] if isinstance(p, dict) and sha and p.get("sha256") == sha), None)
        if part is None:
            return "stale", f"the proxy {rel(side.get('path'))} the fit measured is not one {rel(pb)} built", None
        stl = part.get("stl")
        mf = validate.manifest_path(stl) if isinstance(stl, str) else None
        try:
            with open(mf, encoding="utf-8") as f:
                man = json.load(f)
        except (OSError, TypeError, ValueError):
            return "stale", f"the proxy {rel(stl)} has no build manifest", None
        built = man.get("sources") if isinstance(man, dict) else None
        if (man.get("schema") if isinstance(man, dict) else None) != "3dprint-scout.manifest/1" or not (
                isinstance(built, list) and all(isinstance(x, str) for x in built)):
            return "stale", f"the proxy {rel(stl)} has a malformed build manifest", None
        if man.get("by") != "run":                     # record stamps the parameters of the day on any STL
            return "untied", (f"the proxy {rel(stl)} was recorded (build.py record), not generated from "
                              "its params by build.py run"), None
        own = ([s for s in sources if os.path.basename(s) in set(built)]
               if set(built) <= set(validate.source_names(sources)) else sources)
        if man.get("artifact_sha256") != sha:
            return "stale", f"the proxy {rel(stl)} is not the STL its build recorded", None
        if man.get("input_hash") != validate.hash_inputs(own, proxy_params):
            return "stale", (f"the proxy {rel(stl)} was not built from {rel(pp)} as it is now (or its generator "
                             "changed): build it again and fit again"), None
    return "tied", "", validate.engine_params(proxy_params)


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


def effective_material(params, specs, name):
    """A part's material as params.json declares it now: _parts.<name>.material, else _material."""
    return (specs.get(name) or {}).get("material") or params.get("_material")


LINKED_ORIGINS = ("param:", "table:", "default:", "build:")    # strength.py inputs_from that nobody typed in


def strength_link(rep, inputs, parts, build, params, specs):
    """How a strength.py report is tied to this build. A report written with --from-build names
    the part, its sha256 and material in the build it read, and each input it took from that
    build's parameters (from_build), and says where every input came from (inputs_from). It
    stands while the part is the same STL now, every parameter it took has the same value in
    this build's parameters, and the material is the part's material now. Returns
    {linked, manual: the inputs typed in (every input of a report not made with --from-build),
    part, parameters: {input: param}, stale: why it does not stand}."""
    fb, origins = rep.get("from_build"), rep.get("inputs_from")
    if not isinstance(fb, dict) or not isinstance(origins, dict):
        return {"linked": False, "manual": list(inputs)}
    manual = [k for k in inputs if not (isinstance(origins.get(k), str) and origins[k].startswith(LINKED_ORIGINS))]
    part, sha, mat, links = fb.get("part"), fb.get("sha256"), fb.get("material"), fb.get("parameters")
    if not (isinstance(part, str) and part and isinstance(sha, str) and isinstance(links, dict)
            and all(isinstance(v, dict) and isinstance(v.get("param"), str) and "value" in v for v in links.values())):
        return {"linked": True, "manual": manual, "stale": ["its from_build is not a strength.py --from-build record"]}
    out = {"linked": True, "manual": manual, "part": part, "parameters": {k: v["param"] for k, v in links.items()}}
    stale = []
    current = next((p for p in parts if p.get("name") == part), None)
    if current is None:
        stale.append(f"calculated for {part}, which is not a part of this build")
    elif current.get("sha256") != sha:
        stale.append(f"calculated for an earlier {part}")
    tied = {k for k, o in origins.items() if isinstance(o, str) and o.startswith("param:")}
    loose = sorted(k for k in tied | set(links) if k not in links or k not in inputs
                   or origins.get(k) != f"param:{links[k]['param']}" or not same_value(inputs[k], links[k]["value"]))
    if loose:
        stale.append(f"its inputs_from and from_build do not agree on {', '.join(loose)}")
    bp = build.get("parameters")
    values = bp.get("values") if isinstance(bp, dict) else None
    if links and not isinstance(values, dict):
        stale.append("the build JSON records no parameters to compare with (built before 0.7.0): build again")
    for k, link in links.items() if isinstance(values, dict) else ():
        found, now = lookup(values, link["param"])
        if not found:
            stale.append(f"{link['param']} is not in the build's parameters")
        elif not same_value(now, link["value"]):
            stale.append(f"{k} was {link['param']} = {json.dumps(link['value'])}, now {json.dumps(now)}")
    rep_mat = rep.get("material").get("key") if isinstance(rep.get("material"), dict) else mat
    eff = effective_material(params, specs, part)
    if rep_mat != mat:
        stale.append(f"it was calculated in {rep_mat}, not in the material its build recorded ({mat})")
    elif mat != eff:
        stale.append(f"calculated in {mat}, " + (f"{part} is {eff} now" if eff else f"no material is declared for {part} now"))
    if stale:
        out["stale"] = stale
    return out


def check_strength(verify, taken=frozenset(), parts=(), build=None, params=None, specs=None):
    """Every declared member's strength.py report; `result` as for joints (missing, stale: a
    --from-build report that no longer matches this build (strength_link), failed, open,
    accepted: a WARN gate the user accepted as "member <name>", passed), `linked` (made with
    --from-build) and `manual`: the inputs typed in, not taken from the build."""
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
            inputs = rep.get("inputs") if isinstance(rep.get("inputs"), dict) else {}
            entry.update(gate=rep.get("gate"), case=rep.get("case"), worst=rep.get("worst"), inputs=rep.get("inputs"))
            entry.update(strength_link(rep, inputs, parts, build or {}, params or {}, specs or {}))
            entry["result"] = {"PASS": "passed", "FAIL": "failed"}.get(rep.get("gate"), "open")
            if entry.get("stale"):
                entry["result"] = "stale"             # a FAIL of an earlier part says nothing of this one
                reasons.append(f"member '{name}': {'; '.join(entry['stale'])}: run strength.py --from-build again")
            if rep.get("gate") == "WARN" and norm(f"member {name}") in taken:
                if not entry.get("stale"):
                    entry["result"] = "accepted"
                entry["accepted"] = ["WARN"]
            elif rep.get("gate") != "PASS":
                reasons.append(f"member '{name}': strength.py {rep.get('case')} {rep.get('gate')} (worst: "
                               f"{rep.get('worst')})")
            if not entry["linked"]:
                notes.append(f"member '{name}': strength.py took its sizes from the numbers it was given "
                             f"({json.dumps(rep.get('inputs'), separators=(',', ':'))}), not from the model: they must "
                             "be the dimension table's")
            elif entry["manual"]:
                notes.append(f"member '{name}': " + ", ".join(f"{k} = {json.dumps(inputs[k])}" for k in entry["manual"])
                             + f" {'was' if len(entry['manual']) == 1 else 'were'} typed in, not taken from the build's "
                             "parameters (strength.py --param): they must be the dimension table's")
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


def check_dims(verify, params, measurements=()):
    """_verify.dims: the real-world sizes the design rests on (a phone, a plug), each tied to the
    params.json values the model is built from, with where they came from. A user-file value is
    backed by a measurement of the user's file for each parameter (`from`); one that is not (the
    measurement missing, stale, failed, of a part of this build, or another value) is `unbacked`,
    with its problems. Returns ({id: entry}, declaration errors)."""
    out, errors = {}, []
    engine = validate.engine_params(params)
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
        bad_text = [k for k in ("unit", "by", "url", "note") if k in d and not isinstance(d[k], str)]
        if bad_text:
            errs.append(f"{label}: {', '.join(bad_text)} must be text")
        src = d.get("source")
        if src not in DIM_SOURCES:
            errs.append(f"{label}: source must be one of {', '.join(DIM_SOURCES)}")
        elif src == "caliper" and d.get("by") != "user":
            errs.append(f"{label}: a caliper value needs \"by\": \"user\" (only the user can measure the object)")
        elif src == "spec" and not text_field(d, "url"):
            errs.append(f"{label}: a spec value needs the url of the spec")
        elif src == "user-file":
            frm = d.get("from") if isinstance(d.get("from"), dict) else {}
            given = d.get("params") if isinstance(d.get("params"), dict) else {}
            unmapped = [k for k in given if not text_field(frm, k)]
            if not isinstance(d.get("from"), dict) or unmapped:
                errs.append(f"{label}: a value from the user's file needs from, for each parameter, the name of the "
                            f"measurement of that file it was read from (missing: {', '.join(unmapped) or 'from'})")
            if "tol" not in d:
                errs.append(f"{label}: a value from the user's file needs tol, how far the measured value may differ")
            for k in given:
                mname = frm.get(k)
                if text_field(frm, k) and not any(m.get("name") == mname for m in measurements):
                    errs.append(f"{label}: {k} comes from measurement '{mname}', which is not in _verify.measurements")
        elif src == "spec":
            where = d.get("where") if isinstance(d.get("where"), dict) else {}
            given = d.get("params") if isinstance(d.get("params"), dict) else {}
            unplaced = [k for k in given if not text_field(where, k)]
            if not isinstance(d.get("where"), dict) or unplaced:
                errs.append(f"{label}: a spec value needs where, for each parameter, the place in the spec its number "
                            f"comes from (missing: {', '.join(unplaced) or 'where'})")
        if "tol" in d and not (finite(d["tol"]) and d["tol"] >= 0):
            errs.append(f"{label}: tol must be a number of 0 or more")
        p = d.get("params")
        if not isinstance(p, dict) or not p:
            errs.append(f"{label}: params must map the params.json keys the model is built from to their values")
        else:
            for k, v in p.items():
                found, cur = lookup(engine, k)          # what the generator gets: no _-prefixed metadata
                if not found:
                    errs.append(f"{label}: {k} is not an engine parameter in params.json (the model must be built "
                                "from these numbers; keys starting with _ never reach the generator)")
                elif not same_value(cur, v):
                    errs.append(f"{label}: {k} is {json.dumps(v)} here but {json.dumps(cur)} in params.json")
        entry = {"id": did, "what": d.get("what"), "source": src, "params": p,
                 "state": "error" if errs else DIM_STATE[src]}
        entry.update({k: d[k] for k in ("unit", "tol", "by", "url", "where", "from") if k in d})
        if not errs and src == "user-file":
            problems = user_file_problems(d, measurements)
            if problems:
                entry.update(state="unbacked", problems=problems)
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


def user_file_problems(d, measurements):
    """Why a user-file dims entry is not backed by its measurements, each parameter by its own:
    the measurement must be a fresh, passed reading of a file that is not a part of this build,
    with one = expectation whose measured value is the params value within the entry's tol."""
    problems = []
    for k, v in d["params"].items():
        mname = d["from"][k]
        same = [m for m in measurements if m.get("name") == mname]
        if len(same) != 1:
            problems.append(f"{k}: {len(same)} measurements are named '{mname}'")
            continue
        m = same[0]
        exp = m.get("expect") or []
        if m.get("result") != "passed":
            problems.append(f"{k}: measurement '{mname}' is {m.get('result')}" + (f" ({m['note']})" if m.get("note") else ""))
        elif m.get("measured"):
            problems.append(f"{k}: measurement '{mname}' read {', '.join(m['measured'])}, a part of this build, not the "
                            "user's file")
        elif len(exp) != 1 or exp[0].get("op") != "=":
            problems.append(f"{k}: measurement '{mname}' must hold one = expectation (it holds {len(exp)})")
        elif not finite(v) or abs(exp[0]["value"] - v) > d["tol"] + 1e-9:
            problems.append(f"{k}: measurement '{mname}' read {exp[0]['value']}, not {json.dumps(v)} within {d['tol']}")
    return problems


def finite(v):
    """A real, finite number; an integer too large for a float (10**400 in edited JSON) is not."""
    try:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    except OverflowError:
        return False


MEASURE_ARGS = {"info": ("file",), "slice": ("file", "z", "axis", "object", "center", "max_loops"),
                "raymap": ("file", "axis", "sign", "u", "v", "max_depth", "object", "center")}


def remeasure(rep):
    """The report's command run again on its file (its `query`), so that no number in the report
    is taken on trust. Returns (output, None) or (None, why not)."""
    import measure
    q = rep.get("query")
    if not isinstance(q, dict) or q.get("cmd") not in MEASURE_ARGS or q.get("file") != rep.get("file"):
        return None, "it records no command that can be run again (query)"
    args = argparse.Namespace(**{k: q.get(k) for k in MEASURE_ARGS[q["cmd"]]}, extract=None)
    try:
        return {"info": measure.cmd_info, "slice": measure.cmd_slice, "raymap": measure.cmd_raymap}[q["cmd"]](args), None
    except Exception as exc:                          # numpy missing, a bad query: the report cannot stand
        return None, f"measuring {rel(q.get('file'))} again failed: {exc}"


def expectation_problem(rep, exp):
    """Why a report's expectations cannot be trusted as written, or None. Every expectation needs
    its path, op, target (and tol for =), a value that is the number its path leads to when the
    report's command runs again on the file, and the state that follows from them; the gate must
    follow from the states. Nothing written in the report is taken on trust."""
    import measure
    fresh, why = remeasure(rep)
    if why:
        return why
    states = []
    for e in exp:
        if not isinstance(e, dict):
            return "an expectation is not an object"
        path, op, target, value, state = (e.get(k) for k in ("path", "op", "target", "value", "state"))
        if not (isinstance(path, str) and path.strip()) or op not in ("=", ">=", "<=") or not finite(target):
            return f"an expectation lacks its path, op or target ({json.dumps(e, ensure_ascii=False)})"
        if op == "=" and not (finite(e.get("tol")) and e["tol"] >= 0):
            return f"expectation {path} = {target} has no tol"
        try:
            found = measure.resolve(fresh, path)
        except measure.MeasureError as exc:
            return str(exc)
        found = found if finite(found) else None
        if value != found or (value is not None and not finite(value)):
            return (f"expectation {path}: value {json.dumps(value)} is not what measure.py reads from the file now "
                    f"({json.dumps(found)})")
        ok = value is not None and (abs(value - target) <= e["tol"] + 1e-9 if op == "=" else
                                    value >= target - 1e-9 if op == ">=" else value <= target + 1e-9)
        if state != ("PASS" if ok else "FAIL"):
            return f"expectation {path}: state {json.dumps(state)} does not follow from its numbers"
        states.append(state)
    if rep.get("gate") != ("PASS" if all(st == "PASS" for st in states) else "FAIL"):
        return "its gate does not follow from its expectations"
    return None


def check_seen(verify, parts):
    """_verify.seen: a person's judgement of a preview image. Each entry names the image, the
    digest of the image they looked at (image_sha256), who looked (by: user or agent), the
    promises they judged from it and the result. The image is fresh while it is still those
    bytes, its sidecar (<image>.json, from preview.py or render.py) says the same, and every STL
    the sidecar lists is a part of this build as it is now. Returns (entries, declaration
    errors); an entry's state is error, missing, stale or fresh, and `shows` names the parts."""
    shas = {}
    for p in parts:
        if p.get("sha256"):
            shas.setdefault(p["sha256"], []).append(p.get("name"))
    entries, errors = [], []
    for i, e in enumerate(verify.get("seen") or []):
        name = e.get("name")
        label = f"seen '{name}'" if isinstance(name, str) and name.strip() else f"seen entry {i + 1}"
        image = e.get("image")
        entry = {"name": name, "image": rel(image) if isinstance(image, str) else None, "by": e.get("by"),
                 "result": e.get("result"), "promises": e.get("promises")}
        entries.append(entry)
        errs = []
        if not text_field(e, "name"):
            errs.append(f"{label}: needs a name")
        unknown = sorted(k for k in e if k not in SEEN_KEYS)
        if unknown:
            errs.append(f"{label}: unknown field {', '.join(unknown)} (fields: {', '.join(SEEN_KEYS)})")
        if not text_field(e, "image"):
            errs.append(f"{label}: needs the image")
        if not text_field(e, "image_sha256"):
            errs.append(f"{label}: needs image_sha256, the digest of the image the person looked at")
        if e.get("by") not in ("user", "agent"):
            errs.append(f"{label}: by must be \"user\" or \"agent\" (who looked)")
        if e.get("result") not in ("passed", "failed"):
            errs.append(f"{label}: result must be passed or failed (the judgement)")
        pr = e.get("promises")
        if not (isinstance(pr, list) and pr and all(isinstance(x, str) and x.strip() for x in pr)):
            errs.append(f"{label}: promises must list the ids of the promises judged from the image")
        if errs:
            entry["state"] = "error"
            errors += errs
            continue
        if not os.path.isfile(image):
            entry.update(state="missing", note=f"{rel(image)} not found")
            continue
        current = validate.file_sha256(image)
        if current != e["image_sha256"]:
            entry.update(state="stale", note="the image is not the one that was judged (drawn again since)")
            continue
        try:
            side = load_json(image + ".json", "image sidecar")
        except FinalizeError:
            entry.update(state="missing", note=f"no sidecar ({rel(image)}.json) says what it shows: draw it with "
                                               "preview.py or render.py")
            continue
        stls = side.get("stls") if isinstance(side, dict) else None
        if not (isinstance(side, dict) and side.get("schema") == IMAGE_SCHEMA and isinstance(stls, list) and stls
                and all(isinstance(x, dict) and isinstance(x.get("sha256"), str) for x in stls)):
            entry.update(state="missing", note=f"{rel(image)}.json is not an image sidecar listing what it shows")
            continue
        if side.get("image_sha256") != current:
            entry.update(state="stale", note=f"{rel(image)}.json describes another image (it was drawn again)")
            continue
        foreign = [str(x.get("path")) for x in stls if x["sha256"] not in shas]
        if foreign:
            entry.update(state="stale", note=f"it shows {', '.join(foreign)}, not a part of this build as it is now")
            continue
        entry.update(state="fresh", shows=sorted({n for x in stls for n in shas[x["sha256"]]}))
    return entries, errors


def current_printer(settings):
    """The id of the printer the build was judged for, or None."""
    if not settings.printer or not os.path.isfile(settings.printer):
        return None
    try:
        return validate.load_printer(settings.printer, settings.printer_id)[0]
    except (OSError, ValueError):
        return None


def photos_problem(photos):
    """Why a test print's photos are not a list of the photos' paths in the project folder
    (relative to it, as every path in params.json), or None. Photos are no evidence: the bundle
    carries them."""
    if not (isinstance(photos, list) and all(isinstance(p, str) and p.strip() for p in photos)):
        return "photos must list the paths of the user's photos of the print"
    far = [p for p in photos if os.path.isabs(p) or re.match(r"^([A-Za-z]:|[\\/~])", p)
           or ".." in re.split(r"[\\/]", p)]
    if far:
        return f"photos must be paths in the project folder, relative to it (not {', '.join(far)})"
    return None


def check_print_evidence(verify, parts, params, specs, printer_id, material_evidence=None, delivered_presets=None):
    """The test prints that list promises, as their evidence: {name: info}, declaration errors.
    A print stands for a promise only when it printed the parts as they are now (each part's
    sha256), in each part's material (_parts.<name>.material, else _material; strength.py keys),
    on the build's printer, as built (orientation), under the delivered preset, reported by the
    user. The delivered preset is _print.preset and, with --deliver, the process preset of each
    Bambu project a printed part is delivered in (delivered_presets: {part: [(file, preset)]});
    with neither, the print is assumed. material_evidence ({part: {notver, assumed}}) adds what
    is known of each printed part's material since the build and in the delivered print file.
    A 0.6 entry (no promises) is left to the print tier; photos, on any entry, must be paths in
    the project folder (photos_problem)."""
    import strength
    mats = sorted(strength.MATERIALS)
    by_name = {p.get("name"): p.get("sha256") for p in parts}
    pr_cfg = params.get("_print")
    preset = pr_cfg.get("preset") if isinstance(pr_cfg, dict) else None
    preset = preset if isinstance(preset, str) and preset.strip() else None
    material_evidence, delivered_presets = material_evidence or {}, delivered_presets or {}
    out, errors = {}, []
    for t in verify.get("test_prints") or []:
        name = t.get("name")
        photos = photos_problem(t["photos"]) if "photos" in t else None
        if "promises" not in t:
            if photos:                                     # no evidence, but declared wrongly all the same
                errors.append(f"test print '{name}': {photos}")
            continue
        label = f"test print '{name}'"
        errs = []
        pr, pp = t.get("promises"), t.get("parts")
        if not (isinstance(pr, list) and pr and all(isinstance(x, str) and x.strip() for x in pr)):
            errs.append(f"{label}: promises must list the ids of the promises it checked")
        if not (isinstance(pp, dict) and pp and all(isinstance(v, dict) and text_field(v, "sha256")
                                                   and v.get("material") in mats for v in pp.values())):
            errs.append(f"{label}: parts must map each printed part to its sha256 (from the build JSON handed over) "
                        f"and the material it was printed in ({', '.join(mats)})")
        errs += [f"{label}: needs {k}" for k in ("printer", "orientation", "by") if not text_field(t, k)]
        if "preset" in t and not text_field(t, "preset"):
            errs.append(f"{label}: preset must be the slicer's process preset name")
        if photos:
            errs.append(f"{label}: {photos}")
        info = {"name": name, "promises": pr if isinstance(pr, list) else [], "status": str(t.get("status", "")).lower(),
                "_raw": t}
        out.setdefault(name, []).append(info)
        if errs:
            info["state"] = "error"
            errors += errs
            continue
        notver, assumed = [], []
        stale = [n for n, v in pp.items() if by_name.get(n) is None or by_name[n] != v["sha256"]]
        if stale:
            notver.append(f"it printed {', '.join(stale)} as they were then, not the parts of this build now")
        if t["by"] != "user":
            notver.append("only the user prints: by must be \"user\"")
        for n, v in pp.items():
            eff = effective_material(params, specs, n)
            if eff is None:
                notver.append(f"no material is declared for {n} (_material, or _parts.{n}.material)")
            elif eff != v["material"]:
                notver.append(f"{n} was printed in {v['material']}, the part is {eff}")
            for key, into in (("notver", notver), ("assumed", assumed)):
                into += [r for r in (material_evidence.get(n) or {}).get(key, []) if r not in into]
        if printer_id is None:
            notver.append("the build names no printer to compare with")
        elif t["printer"] != printer_id:
            notver.append(f"printed on {t['printer']}, the build is for {printer_id}")
        if t["orientation"] != "as built":
            notver.append(f"printed {t['orientation']}, not as built")
        targets = [preset] if preset else []
        for n in pp:
            targets += [p for _f, p in delivered_presets.get(n, []) if p is not None and p not in targets]
        if not targets or (not preset and any(n not in delivered_presets for n in pp)):
            assumed.append("the delivered preset is not recorded (_print.preset)")
        unnamed = sorted({rel(f) for n in pp for f, p in delivered_presets.get(n, []) if p is None})
        if unnamed:                                        # the project's own preset is unknown: _print.preset alone is no proof
            assumed.append(f"the delivered project names no process preset ({', '.join(unnamed)})")
        for p in targets:
            if t.get("preset") != p:
                notver.append(f"printed with preset {json.dumps(t.get('preset'))}, the delivery uses {json.dumps(p)}")
        info.update(state="stale" if stale else "fresh", notver=notver, assumed=assumed)
    return out, errors


def check_material_contract(params, specs):
    """_material, _parts.<name>.material and _print, as declared: strength.py material keys and
    a preset name. Returns declaration errors."""
    import strength
    mats = sorted(strength.MATERIALS)
    errors = []
    if "_material" in params and params["_material"] not in mats:
        errors.append(f"_material must be a strength.py material key ({', '.join(mats)})")
    for n, spec in specs.items():
        if "material" in spec and spec["material"] not in mats:
            errors.append(f"_parts.{n}.material must be a strength.py material key ({', '.join(mats)})")
    if "_print" in params and not (isinstance(params["_print"], dict)
                                   and ("preset" not in params["_print"] or text_field(params["_print"], "preset"))):
        errors.append("_print must be an object whose preset is the slicer's process preset name")
    return errors


def check_material_drift(build, params, specs):
    """Each part's material as the build recorded it (parts[].material) against params.json now.
    A material is not an engine parameter, so changing it leaves the STLs fresh; but what was
    calculated or printed for the recorded material is not evidence for another. A build JSON
    from before 0.7.0 records none, and nothing is said. Returns (open lines, {part: {notver,
    assumed}})."""
    lines, evidence = [], {}
    for p in build.get("parts") or []:
        if not isinstance(p, dict) or "material" not in p:
            continue
        name, was = p.get("name"), p["material"]
        now = effective_material(params, specs, name)
        if was != now:
            line = f"{name}: material changed since the build ({was or 'none'} -> {now or 'none'})"
            lines.append(line)
            evidence[name] = {"notver": [line], "assumed": []}
    return lines, evidence


def check_measurements(verify, parts):
    """_verify.measurements: saved measure.py reports with --expect. Each entry gets a `result`:
    missing (no readable report with expectations), stale (the file it measured has changed or is
    gone), failed (an expectation failed) or passed; `measured` names the parts of this build it
    read (none for the user's own file) and `expect` repeats its expectations."""
    by_sha = {}
    for p in parts:
        if p.get("sha256"):
            by_sha.setdefault(p["sha256"], []).append(p)
    entries = []
    for m in verify.get("measurements") or []:
        name, report = m.get("name") or m.get("report"), m.get("report")
        entry = {"name": name, "report": rel(report)}
        entries.append(entry)
        if not report or not os.path.isfile(report):
            entry.update(result="missing", note=f"report {rel(report)} not found; run measure.py --expect and save it")
            continue
        try:
            rep = load_json(report, "measure report")
        except FinalizeError as exc:
            entry.update(result="missing", note=str(exc))
            continue
        exp = rep.get("expect") if isinstance(rep, dict) else None
        if not isinstance(rep, dict) or rep.get("schema") != "3dprint-scout.measure/1" or not rep.get("ran"):
            entry.update(result="missing", note=f"{rel(report)} is not a measure.py report that ran")
            continue
        if not isinstance(exp, list) or not exp or rep.get("gate") not in ("PASS", "FAIL"):
            entry.update(result="missing", note=f"{rel(report)} has no expectations (measure.py --expect)")
            continue
        f, sha = rep.get("file"), rep.get("file_sha256")
        entry.update(file=rel(f) if isinstance(f, str) else None, expect=exp)
        if not (isinstance(f, str) and isinstance(sha, str) and os.path.isfile(f) and validate.file_sha256(f) == sha):
            entry.update(result="stale", note=f"the file it measured ({rel(f) if isinstance(f, str) else '?'}) has "
                                              "changed since, or is gone")
            continue
        broken = expectation_problem(rep, exp)        # the file is the one it read: read it again
        if broken:
            entry.update(result="missing", note=f"{rel(report)}: {broken}")
            continue
        here = [p for p in by_sha.get(sha, []) if p.get("stl") and
                os.path.normcase(os.path.abspath(p["stl"])) == os.path.normcase(os.path.abspath(f))]
        entry["measured"] = [p.get("name") for p in (here or by_sha.get(sha, []))]
        entry["result"] = "passed" if rep["gate"] == "PASS" else "failed"
    return entries


def valid_check_entry(a):
    """An accepted WARN: a check name and the user's reason, both in words, and no promise."""
    return "promise" not in a and isinstance(a.get("check"), str) and bool(a["check"].strip()) and text_field(a, "reason")


def evidence_index(verify, key, entries):
    """{name: [(declaration, checked entry)]} for joints or strength, in declaration order."""
    index = {}
    for raw, entry in zip(verify.get(key) or [], entries):
        if isinstance(entry.get("name"), str):
            index.setdefault(entry["name"], []).append((raw, entry))
    return index


def judged_evidence(k, name, raw, entry, pid, gate):
    """A seen image or a test print as one promise's evidence: what it adds to the promise's
    errors, failures, not-verified and assumed reasons, and its result for the report."""
    what = f"seen '{name}'" if k == "seen" else f"test print '{name}'"
    out = {"errs": [], "failed": [], "notver": [], "assumed": [], "result": None}
    if k == "test_print" and entry is None:
        out["errs"].append(f"{what} lists no promises: a test print used as evidence names the promises it checked, its "
                           "parts (sha256 and material each), printer, orientation and by")
        return out
    if entry.get("state") == "error":
        out["errs"].append(f"{what} has a declaration error")
        return out
    if pid not in (entry.get("promises") or []):
        out["errs"].append(f"{what} does not list this promise (its promises are what it checked)")
        return out
    state = entry.get("state")
    if k == "seen":
        out["result"] = entry.get("result") if state == "fresh" else state
        if state in ("missing", "stale"):
            out["notver"].append(f"{what}: {entry.get('note')}")
        elif entry.get("result") == "failed":
            out["failed"].append(f"{what}: judged failed by the {entry.get('by')}")
        else:
            if entry.get("by") != "user":
                out["notver"].append(f"{what}: only the agent looked at it")
            bad = [n for n in entry.get("shows") or [] if gate.get(n) == "FAIL"]
            if bad:
                out["notver"].append(f"{what} shows {', '.join(bad)}, whose own checks FAIL")
        return out
    out["result"] = entry.get("status") if state == "fresh" else state
    out["notver"] += [f"{what}: {r}" for r in entry.get("notver") or []]
    out["assumed"] += [f"{what}: {r}" for r in entry.get("assumed") or []]
    if state == "fresh" and entry.get("status") == "failed":
        out["failed"].append(f"{what} failed")
    elif entry.get("status") != "passed" and state == "fresh":
        out["notver"].append(f"{what}: {entry.get('status')}")
    return out


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


def check_promises(verify, params, joints, strength, parts, measurements=(), seen=(), prints=None,
                   material_evidence=None):
    """The use tier: each promise made to the user, judged by its own evidence. A promise is
    verified only when it says under which conditions it holds and what counts as success, its
    evidence is of a kind allowed for it, of the current parts and passed, and nothing it rests
    on is an unmeasured size. A member verifies only from a --from-build report with no input
    typed in, of a part whose own checks pass, whose material (material_evidence: {part:
    {notver, assumed}}) holds. Returns a dict with tier, promises, counts, dims, errors, open."""
    dims, errors = check_dims(verify, params, measurements)
    prints = prints or {}
    out = {"tier": "not declared", "promises": [], "counts": {}, "dims": list(dims.values()), "errors": errors,
           "open": []}
    for key, kind_name in (("joints", "joint"), ("strength", "member"), ("measurements", "measurement")):
        for raw in verify.get(key) or []:
            jd = raw.get("dims")
            if jd is not None and not (isinstance(jd, list) and all(isinstance(x, str) for x in jd)):
                errors.append(f"{kind_name} '{raw.get('name') or raw.get('report')}': dims must be a list of "
                              "_verify.dims ids")
    promises = verify.get("promises")
    ids = [p.get("id") for p in promises or []]
    excluded = {}
    for a in verify.get("accepted") or []:
        if "promise" not in a:
            if not valid_check_entry(a):
                errors.append(f"accepted entry {json.dumps(a, ensure_ascii=False)}: names no check (or a promise), or "
                              "gives no reason (the user's, in words): it accepts nothing")
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
             "strength": evidence_index(verify, "strength", strength),
             "measurement": evidence_index(verify, "measurements", measurements),
             "seen": evidence_index(verify, "seen", seen), "test_print": {}}
    for t in verify.get("test_prints") or []:
        if isinstance(t.get("name"), str):
            info = next((i for i in prints.get(t["name"], []) if i.get("_raw") is t), None)
            index["test_print"].setdefault(t["name"], []).append((t, info))
    where_of = {"joint": "_verify.joints", "strength": "_verify.strength", "measurement": "_verify.measurements",
                "seen": "_verify.seen", "test_print": "_verify.test_prints"}
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
                            f"{', '.join((ALLOWED[kind] if kind in KINDS else ()) or EVIDENCE)}")
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
            where = where_of[k]
            if not matches:
                errs.append(f"there is no {k} '{name}' in {where}")
                continue
            if len(matches) > 1:
                errs.append(f"{len(matches)} entries in {where} are named '{name}'")
                continue
            raw, entry = matches[0]
            if k in ("seen", "test_print"):
                judged = judged_evidence(k, name, raw, entry, pid, gate)
                errs += judged["errs"]
                failed += judged["failed"]
                notver += judged["notver"]
                assumed += judged["assumed"]
                if not judged["errs"]:
                    ev = {k: name, "result": judged["result"]}
                    if "covers" in item:
                        ev["covers"] = item["covers"]
                    ev_out.append(ev)
                continue
            res = entry.get("result")
            ev = {k: name, "result": res}
            if "covers" in item:
                ev["covers"] = item["covers"]
            ev_out.append(ev)
            what = {"joint": f"joint '{name}'", "strength": f"member '{name}'"}.get(k, f"measurement '{name}'")
            if res == "missing":
                notver.append(f"{what}: no report" + (f" ({entry['note']})" if entry.get("note") else ""))
            elif res == "stale":
                notver.append(f"{what}: the file it measured has changed since, or is gone" if k == "measurement" else
                              f"{what}: {'; '.join(entry.get('stale') or [])}" if k == "strength" else
                              f"{what}: its fit report is not of the current parts")
            elif res == "failed":
                failed.append(f"{what} failed" + (": " + "; ".join(
                    f"{e.get('path')} = {json.dumps(e.get('value'))}, expected {e.get('op')} {e.get('target')}"
                    for e in entry.get("expect") or [] if e.get("state") == "FAIL") if k == "measurement" else ""))
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
                elif raw.get("proxy") and entry.get("proxy_build") == "untied":
                    assumed.append(f"{what} names the sizes of its proxy, but nothing ties the proxy to them: "
                                   f"{entry.get('proxy_note')}")
                elif raw.get("proxy") and entry.get("proxy_build") == "stale":
                    notver.append(f"{what}: {entry.get('proxy_note')}")
                elif raw.get("proxy") and isinstance(raw.get("dims"), list):
                    # tied: the proxy got exactly the numbers its dims declare, no fewer and no others
                    declared = {}
                    for did in raw["dims"]:
                        if isinstance(did, str) and isinstance((dims.get(did) or {}).get("params"), dict):
                            declared.update(dims[did]["params"])
                    declared, got = flatten(declared), flatten(entry.get("proxy_params") or {})
                    differ = [k for k in got if k in declared and not same_value(got[k], declared[k])]
                    loose = [k for k in got if k not in declared]
                    unused = [k for k in declared if k not in got]
                    if differ:
                        notver.append(f"{what}: the proxy was built from "
                                      + ", ".join(f"{k} = {json.dumps(got[k])}" for k in differ)
                                      + ", not the values its dims declare")
                    if loose:
                        assumed.append(f"{what}: the proxy was also built from {', '.join(loose)}, which no dims "
                                       "entry it names declares")
                    if unused:
                        assumed.append(f"{what}: the proxy was not given {', '.join(unused)}, which its dims declare")
            elif k == "measurement" and res in ("passed", "failed"):
                if not entry.get("measured"):
                    notver.append(f"{what}: it read {entry.get('file')}, which is not a part of this build")
                bad = [n for n in entry.get("measured") or [] if gate.get(n) == "FAIL"]
                if bad:
                    notver.append(f"{what} read {', '.join(bad)}, whose own checks FAIL")
            elif k == "strength" and res in ("passed", "accepted"):
                manual = entry.get("manual") or []
                if not entry.get("linked"):
                    notver.append(f"{what}: its inputs were typed in, not taken from the build's parameters")
                elif manual:
                    notver.append(f"{what}: {', '.join(manual)} {'was' if len(manual) == 1 else 'were'} typed in, not "
                                  "taken from the build's parameters")
                if entry.get("linked") and gate.get(entry.get("part")) == "FAIL":
                    notver.append(f"{what} is calculated for {entry['part']}, whose own checks FAIL")
                for key, into in (("notver", notver), ("assumed", assumed)):
                    into += [f"{what}: {r}" for r in ((material_evidence or {}).get(entry.get("part")) or {}).get(key, [])
                             if entry.get("linked") and f"{what}: {r}" not in into]
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
            elif d["state"] == "unbacked":
                line = f"dims '{did}' is not backed by its measurements: {'; '.join(d.get('problems') or [])}"
                if line not in notver:
                    notver.append(line)
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
    for d in dims.values():
        if d.get("state") == "spec":
            out["open"].append(f"dims '{d['id']}' is taken from a spec, not checked here: compare "
                               + "; ".join(f"{k} = {json.dumps(v)} ({d['where'][k]})" for k, v in d["params"].items())
                               + f" with {d['url']}")
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
    """Every STL and 3MF in the delivery folder against the verified STLs. Returns (entries,
    reasons, projects): projects are (3MF path, its entry, its manifest) for every delivered 3MF
    with a sound manifest, for check_delivered_print."""
    entries, reasons, projects = [], [], []
    if not os.path.isdir(deliver):
        return [], [f"delivery folder {rel(deliver)} not found"], []
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
                projects.append((path, entry, m))
            entries.append(entry)
    for p in parts:
        if p.get("sha256") and p["name"] not in covered:
            reasons.append(f"{p['name']}: not in the delivery ({rel(deliver)}) as an STL or in a 3MF")
    return entries, reasons, projects


NO_PROJECT = "the print file's material is not checked (no Bambu project)"


def check_delivered_print(projects, part_names, params, specs):
    """The slicer settings a delivered Bambu project carries (its manifest's `filaments` and
    `process`, written by bambu3mf.py) against what params.json declares. Each part's filament
    (strength.material_of_filament of its settings name) must be the part's material: another
    material leaves the part's material-dependent evidence (a --from-build strength report, a
    test print of it) not verified, a filament finalize cannot name leaves it assumed, and so
    does a part in no Bambu project (another slicer: its filament cannot be read). A project's
    process preset must be _print.preset when one is declared; without one it is the delivered
    preset test prints are compared with. Returns (open lines, {part: {notver, assumed}},
    {part: [(file, preset)]})."""
    import strength
    lines, evidence, presets = [], {}, {}
    declared = (params.get("_print") or {}).get("preset") if isinstance(params.get("_print"), dict) else None
    checked = set()
    for path, entry, m in projects:
        fil, proc = m.get("filaments"), m.get("process")
        if isinstance(fil, dict):                          # a core 3MF (build.py) has no slicer settings
            entry["filaments"] = {}
        for n in sorted(set(entry.get("parts") or []) | set(fil)) if isinstance(fil, dict) else ():
            if n not in part_names:
                continue
            checked.add(n)
            f = fil.get(n) if isinstance(fil.get(n), dict) else {}
            settings = f.get("settings") if isinstance(f.get("settings"), str) else None
            key, eff = strength.material_of_filament(settings), effective_material(params, specs, n)
            entry["filaments"][n] = {"slot": f.get("slot"), "settings": settings, "material": key}
            ev = evidence.setdefault(n, {"notver": [], "assumed": []})
            if key is None:
                why = (f"{json.dumps(settings)} is not a filament of a known material" if settings else
                       "the project names no filament for its slot")
                lines.append(f"{rel(path)}: the slicer's filament for {n} is not checked ({why}); set it to "
                             f"{eff or 'the part material'} in the slicer")
                ev["assumed"].append(f"the slicer's filament for {n} is not checked")
            elif eff is None:
                lines.append(f"{rel(path)}: {n} is printed in {settings} ({key}), and no material is declared for {n} "
                             f"(_material, or _parts.{n}.material) to compare it with")
                ev["notver"].append(f"no material is declared for {n} to compare the print file's filament with")
            elif key != eff:
                lines.append(f"{rel(path)}: {n} is printed in {settings} ({key}), the part is {eff}: choose the "
                             "filament of its material in the project, or change the part's material and build again")
                ev["notver"].append(f"the print file prints {n} in {key}, the part is {eff}")
        p = proc.get("settings") if isinstance(proc, dict) else None
        if isinstance(p, str) and p.strip():
            entry["preset"] = p
            for n in entry.get("parts") or []:
                presets.setdefault(n, []).append((path, p))
            if isinstance(declared, str) and declared.strip() and p != declared:
                lines.append(f"{rel(path)}: its process preset is {json.dumps(p)}, not _print.preset "
                             f"{json.dumps(declared)}: a test print under one does not stand for the other")
        elif "filaments" in m or "process" in m:           # a Bambu project that names no process preset
            entry["preset"] = None
            for n in entry.get("parts") or []:
                presets.setdefault(n, []).append((path, None))
            lines.append(f"{rel(path)}: the project names no process preset, so a test print cannot be compared "
                         "with it" + (f": choose {json.dumps(declared)} in the slicer"
                                      if isinstance(declared, str) and declared.strip() else ""))
    unchecked = [n for n in part_names if n not in checked]
    for n in unchecked:
        evidence.setdefault(n, {"notver": [], "assumed": []})["assumed"].append(NO_PROJECT)
    if unchecked:
        lines.append(f"{NO_PROJECT}" + (f" for {', '.join(unchecked)}" if checked else "") + ": set the slicer's "
                     "filament to " + ", ".join(f"{n}: {effective_material(params, specs, n) or 'its material'}"
                                                for n in unchecked))
    return lines, evidence, presets


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


BUNDLE_OWN = ("params.json", "printers.json", "REPRODUCE.md", "verification.json", "build.json")   # build.json: rebuilt
RUN_ENGINES = ("openscad", "python", "blender")                  # what `build.py run` builds again
NOT_TEXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".mp4", ".mov",
            ".3mf")                                              # pictures and zips: no path a script reads is in them


def bundle_path(src):
    """Where a source goes in the bundle: its path relative to the working folder (the folder the
    build ran in), so an import, an include or a loaded file still finds it; None outside it."""
    try:
        r = os.path.relpath(os.path.abspath(src))
    except ValueError:                                   # another drive on Windows
        return None
    return None if r == ".." or r.startswith(".." + os.sep) else r.replace(os.sep, "/")


def json_object(path):
    """A JSON object from a file, or {}: a missing or malformed report is the verdict's to judge."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def manifests_of_3mf(folders, sha):
    """The 3MF manifests in the folders (walked as threemf_manifests walks them) written for the
    3MF with this sha256: [(path, sound)], sound when its parts map part names to sha256."""
    found, seen = [], set()
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for root, dirs, names in os.walk(folder):
            dirs.sort()
            for fn in sorted(names):
                path = os.path.join(root, fn)
                key = os.path.normcase(os.path.abspath(path))
                if not fn.endswith(".3mf.manifest.json") or key in seen:
                    continue
                seen.add(key)
                m = json_object(path)
                if m.get("schema") != MANIFEST_3MF or m.get("artifact_sha256") != sha:
                    continue
                parts = m.get("parts")
                found.append((path, isinstance(parts, dict) and bool(parts)
                              and all(isinstance(k, str) and isinstance(v, str) for k, v in parts.items())))
    return found


def bundle_contents(verify, build, deliver=None, joints=None):
    """What a bundle carries besides the generator, params.json and printers.json, so that the
    verdict can be reached again from the bundle alone: every report _verify names, and each
    file a report read by its sha256 that REPRODUCE.md does not build again (a measured user
    file, a recorded proxy's STL with its build manifest; never a part); a proxy's generator and
    params file (a `build.py run --proxy` proxy tied to them, joints[i].proxy_build "tied" in the
    report, is built again; a recorded one is carried with its build JSON); each seen image and
    its sidecar; the test print photos; and with --deliver
    every delivered STL and 3MF with the manifest finalize compares it with. Returns (files:
    {place: (path, what)}, missing: {place: what}, proxies: {build JSON place: the `build.py run
    --proxy` command that builds it again}, outside: the paths outside the project folder). A
    place is the path relative to the project folder; a 3MF's manifest found only elsewhere
    (out/, which a rebuild rewrites) goes beside the 3MF."""
    built = {os.path.normcase(os.path.abspath(p["stl"])) for p in build.get("parts") or []
             if isinstance(p, dict) and isinstance(p.get("stl"), str)}
    files, missing, proxies, outside = {}, {}, {}, []

    def carry(path, what, place=None):
        """Carry the file at its place (True), or note it missing or outside (False)."""
        if not (isinstance(path, str) and path.strip()):
            return False
        own = bundle_path(path)
        if own is None:
            if path not in outside:
                outside.append(path)
            return False
        place = place or own
        if not os.path.isfile(path):
            missing.setdefault(place, what)
            return False
        files.setdefault(place, (path, what))
        return True

    def hashed(path, what):
        """A file a report read by its sha256: a part of this build is rebuilt; any other file is
        carried, with its build manifest when it has one (fit.py and the proxy check read it)."""
        if not isinstance(path, str) or os.path.normcase(os.path.abspath(path)) in built:
            return
        if carry(path, what) and os.path.isfile(validate.manifest_path(path)):
            carry(validate.manifest_path(path), f"build manifest of {bundle_path(path)}")

    def proxy(path, joint, tied):
        """A proxy's build: one `build.py run --proxy` made is made again by REPRODUCE.md, as the
        parts are (its build JSON records paths of this machine, as the main one does): its
        generator and params file are carried, its STLs, manifests and JSON are not. Any other
        (a recorded proxy) is carried as it is, with its inputs."""
        b = json_object(path) if isinstance(path, str) and os.path.isfile(path) else {}
        if b.get("schema") != "3dprint-scout.build/1":
            carry(path, f"proxy build of {joint}")               # missing or malformed: as the verdict sees it
            return
        srcs = [s for s in b["sources"] if isinstance(s, str)] if isinstance(b.get("sources"), list) else []
        for s in own_sources({"sources": srcs}):
            carry(s, f"proxy generator of {joint}")
        carry(b.get("params"), f"params file of the proxy of {joint}")
        stls = ([p for p in b["parts"] if isinstance(p, dict) and isinstance(p.get("stl"), str)]
                if isinstance(b.get("parts"), list) else [])
        src, prm, place = b.get("source"), b.get("params"), bundle_path(path)
        out = bundle_path(os.path.dirname(stls[0]["stl"]) or ".") if stls else None
        if not (b.get("proxy") is True and b.get("engine") in RUN_ENGINES and isinstance(src, str) and bundle_path(src)
                and isinstance(prm, str) and bundle_path(prm) and out and place):
            carry(path, f"proxy build of {joint}")
            for p in stls:
                hashed(p["stl"], f"proxy STL of {joint}")
        elif tied:
            proxies.setdefault(place, (
                f'python3 "$SKILL_DIR/scripts/build.py" run {shlex.quote(bundle_path(src))} --params '
                f"{shlex.quote(bundle_path(prm))} --proxy {shlex.quote(','.join(str(p.get('name')) for p in stls))} "
                f"--out {shlex.quote(out)} > {shlex.quote(place)}"))
            built.update(os.path.normcase(os.path.abspath(p["stl"])) for p in stls)
        else:                                                    # built again it would be another proxy
            for p in stls:
                hashed(p["stl"], f"proxy STL of {joint}")
            missing.setdefault(place, f"proxy build of {joint}, left out: a build.py run JSON is made again, not "
                                      "carried, and this proxy was not built from its params file as it is now (build "
                                      "the proxy and fit it again)")

    states = [e.get("proxy_build") for e in joints or []]
    for i, j in enumerate(verify.get("joints") or []):       # the proxies first: an STL rebuilt is not carried
        if j.get("proxy") and isinstance(j.get("proxy_build"), str):
            proxy(j["proxy_build"], f"joint '{j.get('name') or j.get('report')}'",
                  i < len(states) and states[i] == "tied")
    for j in verify.get("joints") or []:
        joint = f"joint '{j.get('name') or j.get('report')}'"
        if carry(j.get("report"), f"fit report of {joint}"):
            sides = json_object(j["report"]).get("parts")
            for k in ("a", "b"):
                side = sides.get(k) if isinstance(sides, dict) else None
                if isinstance(side, dict):
                    hashed(side.get("path"), f"STL fitted in {joint}")
    for s in verify.get("strength") or []:
        carry(s.get("report"), f"strength report of member '{s.get('name') or s.get('report')}'")
    for m in verify.get("measurements") or []:
        what = f"measurement '{m.get('name') or m.get('report')}'"
        if carry(m.get("report"), f"report of {what}"):
            hashed(json_object(m["report"]).get("file"), f"file read by {what}")
    for e in verify.get("seen") or []:
        what = f"seen '{e.get('name') or e.get('image')}'"
        if carry(e.get("image"), f"image of {what}"):
            carry(e["image"] + ".json", f"sidecar of the image of {what}")
    for t in verify.get("test_prints") or []:
        for p in t["photos"] if isinstance(t.get("photos"), list) else []:
            carry(p, f"photo of test print '{t.get('name')}'")
    if deliver and bundle_path(deliver) is None:
        outside.append(deliver)
    elif deliver and os.path.isdir(deliver):
        here = os.path.normcase(os.path.abspath(deliver))
        out_dirs = sorted({os.path.dirname(p["stl"]) for p in build.get("parts") or []
                           if isinstance(p, dict) and isinstance(p.get("stl"), str)}
                          | {os.path.dirname(build["threemf"]) if isinstance(build.get("threemf"), str) else ""})
        for fn in sorted(os.listdir(deliver)):                 # the files check_delivered judges
            path = os.path.join(deliver, fn)
            if not (os.path.isfile(path) and fn.lower().endswith((".stl", ".3mf"))):
                continue
            carry(path, "delivered file")
            if not fn.lower().endswith(".3mf") or bundle_path(path) is None:
                continue
            place = bundle_path(path)
            found = manifests_of_3mf([deliver, *out_dirs], validate.file_sha256(path))
            beside = [(m, ok) for m, ok in found if os.path.normcase(os.path.dirname(os.path.abspath(m))) == here]
            for m, _ok in beside:
                carry(m, f"manifest of {place}")
            elsewhere = [(m, ok) for m, ok in found if (m, ok) not in beside]
            pick = None if any(ok for _m, ok in beside) else next((m for m, ok in elsewhere if ok), None)
            if pick is None and elsewhere and not beside:
                pick = elsewhere[0][0]                          # a malformed one: the verdict names it so
            if pick:
                to = place + ".manifest.json"
                if to in files:
                    to = place[:len(place) - len(fn)] + "bundle-" + fn + ".manifest.json"
                carry(pick, f"manifest of {place}, found at {bundle_path(pick)}", place=to)
    return files, missing, proxies, outside


def same_file(a, b):
    try:
        return bool(a and b) and os.path.samefile(a, b)
    except OSError:
        return False


def write_bundle(folder, build, params_path, settings, report, verify=None, deliver=None):
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
    reserved = {n.lower() for n in BUNDLE_OWN}
    clash = [place for place in places.values() if place.lower() in reserved]
    if clash:
        raise FinalizeError(f"{', '.join(clash)} would take the place of a file the bundle writes itself; rename it")
    inputs, missing, proxies, far = bundle_contents(verify or {}, build, deliver, report.get("joints"))
    if far:
        raise FinalizeError(f"{', '.join(rel(p) for p in far)} is outside the project folder (the folder the build ran "
                            "in); the bundle keeps every file at its place relative to that folder, so that "
                            "REPRODUCE.md runs as written inside it: move it into the project folder and name it there")
    for place, (src, _what) in list(inputs.items()):
        if place in places.values() or (place.lower() in reserved and (same_file(src, params_path)
                                                                     or same_file(src, printers))):
            del inputs[place]                                    # already in the bundle (a source, params.json)
        elif place.lower() in reserved:
            raise FinalizeError(f"{place} would take the place of a file the bundle writes itself; rename it")
    leaking = [place for place, (src, _what) in inputs.items()
               if not src.lower().endswith(NOT_TEXT) and holds_machine_path(src)]
    if leaking:
        raise FinalizeError(f"{', '.join(leaking)} holds a path of this machine: write it again with paths relative "
                            "to the project folder (fit.py, measure.py, strength.py --from-build, preview.py and "
                            "render.py record the paths they are given) before bundling")
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
    for place in sorted(inputs):                                  # copied, never moved
        dst = os.path.join(folder, *place.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(inputs[place][0], dst)
        written.append(rel(dst))
    delivered = bundle_path(deliver) if deliver and os.path.isdir(deliver) else None
    for place in [delivered] + [posixpath.dirname(p) for p in proxies]:      # where REPRODUCE.md writes and reads
        if place:
            os.makedirs(os.path.join(folder, *place.split("/")), exist_ok=True)
    main_src = build.get("source") or (srcs[0] if srcs else None)
    main = (bundle_path(main_src) or os.path.basename(main_src)) if main_src else "model"
    engine = build.get("engine") or "?"
    stls = [p["stl"] for p in build.get("parts") or [] if isinstance(p, dict) and isinstance(p.get("stl"), str)]
    dirs = {bundle_path(os.path.dirname(s) or ".") for s in stls}
    out = dirs.pop() if len(dirs) == 1 and None not in dirs else "out"       # where the reports find the parts
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
    if engine in RUN_ENGINES:
        lines += ["```bash", f'python3 "$SKILL_DIR/scripts/build.py" run {shlex.quote(main)} --params params.json '
                             f"--out {shlex.quote(out)}{flag_text} > build.json", "```", ""]
    else:
        recorded = [bundle_path(s) for s in stls]
        lines += [f"This build was recorded (`build.py record`, engine {engine}): run the generator in {engine}, export "
                  f"one STL per part named after the part into `{out}/`, then:", "", "```bash",
                  'python3 "$SKILL_DIR/scripts/build.py" record '
                  + (" ".join(shlex.quote(r) for r in recorded) if recorded and None not in recorded
                     else f"{shlex.quote(out)}/<part>.stl ...")
                  + f' --source {" ".join(shlex.quote(places[s]) for s in srcs) or shlex.quote(main)} --params params.json '
                  f"--engine {engine} --out {shlex.quote(out)}{flag_text} > build.json", "```", ""]
    if proxies:
        lines += ["Then the proxies the fit reports measured, built again from their own generators and params "
                  "files as the parts are (a fit report holds while each STL is the one it measured):", "", "```bash",
                  *proxies.values(), "```", ""]
    lines += ["Then re-check" + (f", with the delivered files in `{delivered}`" if delivered else "") + ":", "",
              "```bash", 'python3 "$SKILL_DIR/scripts/finalize.py" --build build.json --params params.json'
              + (f" --deliver {shlex.quote(delivered)}" if delivered else ""), "```", "",
              "`verification.json` is the report this delivery was made with: what was verified, and what was not.", ""]
    if inputs:
        lines += ["## The evidence", "",
                  "Besides the generator, `params.json` and `printers.json`, the files the verdict reads, each at its "
                  "place in the project folder. The parts, and the proxies built again, are not here: the commands "
                  "above make them, and a report holds while each STL it read is the same (sha256).", ""]
        lines += [f"- `{place}`: {inputs[place][1]}" for place in sorted(inputs)] + [""]
    if missing:
        lines += ["## Not in this bundle", "",
                  "Named, but not here: not there when the bundle was made, unless the line says why. A re-check "
                  "here finds them missing:", ""]
        lines += [f"- `{place}`: {missing[place]}" for place in sorted(missing)] + [""]
    with open(os.path.join(folder, "REPRODUCE.md"), "w", encoding="utf-8") as f:
        f.write(scrub("\n".join(lines)))
    written.append(rel(os.path.join(folder, "REPRODUCE.md")))
    written.append(rel(os.path.join(folder, "verification.json")))
    report["bundle"] = written
    report["bundle_missing"] = [f"{place}: {missing[place]}" for place in sorted(missing)]
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
    taken = {norm(a["check"]) for a in accepted if valid_check_entry(a)}   # a malformed entry accepts nothing
    joints, r, notes = check_joints(verify, parts, taken)
    out["joints"] = joints
    reasons += r
    out["warnings"] += notes
    strength, r, notes = check_strength(verify, taken, parts, build, params, specs)
    out["strength"] = strength
    reasons += r
    out["warnings"] += notes
    prints, print_lines = check_prints(verify)
    out["test_prints"] = prints
    measurements = check_measurements(verify, parts)
    out["measurements"] = measurements
    seen, seen_errors = check_seen(verify, parts)
    out["seen"] = seen
    material_lines, material_evidence = check_material_drift(build, params, specs)
    out["material_drift"] = material_lines
    delivery_lines, presets = [], {}
    if args.deliver:
        delivered, r, projects = check_delivered(args.deliver, parts, build)
        out["delivered"] = delivered
        reasons += r
        delivery_lines, ev, presets = check_delivered_print(projects, [p.get("name") for p in parts], params, specs)
        for n, e in ev.items():
            mine = material_evidence.setdefault(n, {"notver": [], "assumed": []})
            mine["notver"] += e["notver"]
            mine["assumed"] += e["assumed"]
    print_info, print_errors = check_print_evidence(verify, parts, params, specs, current_printer(settings),
                                                    material_evidence, presets)
    use = check_promises(verify, params, joints, strength, parts, measurements, seen, print_info, material_evidence)
    extra = seen_errors + print_errors + check_material_contract(params, specs)
    if extra:
        use["errors"] += extra
        use["open"][:0] = extra
        use["tier"] = "error"
    out["use"] = use["tier"]
    out["promises"], out["promise_counts"], out["dims"] = use["promises"], use["counts"], use["dims"]
    out["promise_errors"] = use["errors"]
    open_warns = [f"{who} WARN: {note}".rstrip(": ") for who, note in warns if norm(who) not in taken]
    reasons += [text for who, text in copied if norm(who) not in taken]
    shape, shape_lines = check_references(verify, [o["name"] for o in build.get("objects") or []])
    out["shape"] = shape
    geometry_ok = not reasons and not open_warns
    out["geometry"] = "verified" if geometry_ok else "not verified"
    passed = [t["name"] for t in prints if t["status"] == "passed"]
    out["print"] = ("unverified (test prints passed: " + ", ".join(passed) + "; the final part is not printed)"
                    if passed else "unverified")
    out["open"] = (use["open"] + reasons
                   + [f"open warning (not accepted in _verify.accepted): {w}" for w in open_warns]
                   + material_lines + delivery_lines + to_decide + print_lines + shape_lines
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
        write_bundle(args.bundle, build, args.params, settings, out, verify, args.deliver)
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
