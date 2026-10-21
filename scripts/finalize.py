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
is missing is reported as "not declared", which keeps the geometry from being verified):

  "_verify": {
    "joints":   [{"name": "lid on box", "report": "out/fit_box_lid.json"},
                 {"name": "clip on the tube", "report": "out/fit_clip.json", "proxy": true}],
    "strength": [{"name": "latch arm", "report": "out/strength_latch.json"}],
    "test_prints": [{"name": "hinge coupon", "status": "skipped", "note": "user had no time"}],
    "accepted": [{"check": "body P2", "reason": "the user wants supports there"},
                 {"check": "object box P2", "reason": "..."}],
    "unverified": ["wall behind the label: estimated from a photo"],
    "references": {"lid": {"front": "real", "top": "real", "back": "estimated", "bottom": "assumed"}}
  }

joints: every joint F3 must cover, with its saved fit.py report: the report must be fresh (its
STLs are the parts being delivered, or a declared proxy) and its own F3 / F3_sweep must PASS.
An empty list says the design has no joint. strength: strength.py reports (saved JSON), their
gate must PASS; their inputs are numbers from the dimension table, not read from the model, so
the report says to keep them equal. test_prints: coupons and mechanism-first prints (status
passed, failed, skipped, offered or pending). accepted: WARNs the user accepted, named
"<part> <check>" or "object <name> <check>", with their reason; any other WARN is open ("<part>
D1" also accepts a D1 whose expect was copied from the model, when no intended size exists).
unverified: dimensions taken without a measurement. references: for each object, which
directions a reference shows (`real`), or was generated or inferred (`estimated`), or given up
on (`assumed`); a direction without a real reference is one whose shape is not verified.

The report has four tiers and never folds them into one PASS:
  geometry  verified | not verified   the STLs, objects, joints and members, from the checks above
  shape     per object, the directions a real reference covers
  slicing   unverified                  nothing here slices; say so at delivery
  print     unverified                  test prints and their results, if any
plus `open`: every reason the geometry is not verified, every unaccepted WARN, the soft checks
left to you (P3 skipped, P4, P5, P6), every unverified dimension and assumption, in plain lines
for the delivery message.

--deliver DIR checks the delivery folder: every STL in it must be one of the verified STLs,
every 3MF must carry a manifest (`<file>.3mf.manifest.json`, written by build.py and bambu3mf.py
next to the 3MF; copy it along) that lists exactly the verified STLs, and every part must be
delivered in one or the other; a malformed manifest is a reason, not an error. --bundle DIR
writes a new folder with the generator sources (not the skill's own libraries) at their places
relative to the folder the build ran in (lib/helper.py stays lib/helper.py, so imports, includes
and loaded files still resolve), params.json, the printers.json the build used, this report and
REPRODUCE.md (the commands that rebuild and re-check the parts); it refuses an existing folder,
a source outside the project folder, and a source or params file that holds a path of this
machine. Exit 0 when it ran (read "geometry"), 1 on a usage or file error.
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
    parts = params.get("_parts") or {}
    if not isinstance(parts, dict):
        raise FinalizeError("_parts in params.json must be an object")
    return {str(k): dict(v or {}) for k, v in parts.items()}


def check_verify_shape(verify):
    lists = {"joints": dict, "strength": dict, "test_prints": dict, "accepted": dict, "unverified": str}
    for key, item in lists.items():
        if key in verify:
            v = verify[key]
            if not isinstance(v, list) or not all(isinstance(x, item) for x in v):
                kind = "objects" if item is dict else "strings"
                raise FinalizeError(f"_verify.{key} must be a list of {kind}")
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
            same = old == new or (old is not None and new is not None and str(old) == str(new))
        if not same:
            out.append(f"{f} {old} -> {new}")
    if bool(b.get("wall_check", True)) != bool(settings.wall_check):
        out.append("wall_check")
    pr = settings.printer
    if b.get("printer_sha256") and pr and os.path.isfile(pr) and validate.file_sha256(pr) != b["printer_sha256"]:
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
    if same_as_build:
        for p in build.get("parts") or []:
            for cid, ck in ((p.get("assembly") or {}).get("checks") or {}).items():
                if ck.get("state") in ("FAIL", "UNVERIFIED") and ck.get("kind") == "hard":
                    reasons.append(f"{p.get('name')} {cid} {ck['state']}: {ck.get('note', '')}".rstrip(": "))
                elif ck.get("state") == "WARN":
                    warns.append((f"{p.get('name')} {cid}", ck.get("note", "")))
    return entries, reasons, warns


def check_joints(verify, part_shas):
    if "joints" not in verify:
        return [], ["joints not declared (_verify.joints): F3 is not counted; list every joint with its fit "
                    "report, or [] when the design has none"], []
    entries, reasons, notes = [], [], []
    import fit
    for j in verify["joints"]:
        name, report = j.get("name") or j.get("report"), j.get("report")
        entry = {"name": name, "report": rel(report)}
        if not report or not os.path.isfile(report):
            entry["state"] = "FAIL"
            reasons.append(f"joint '{name}': fit report {rel(report)} not found; run fit.py and save it")
            entries.append(entry)
            continue
        try:
            fresh = fit.check_report(report)
        except (fit.FitError, OSError, ValueError) as exc:
            entry["state"] = "FAIL"
            reasons.append(f"joint '{name}': {exc}")
            entries.append(entry)
            continue
        rep = load_json(report, "fit report")
        f3f = fresh["checks"]["F3_fresh"]
        states = {k: v.get("state") for k, v in (rep.get("checks") or {}).items()}
        entry.update(fresh=f3f["state"], checks=states)
        if f3f["state"] != "PASS":
            reasons.append(f"joint '{name}': F3_fresh {f3f['state']}: {f3f.get('note', '')}")
        for cid, st in states.items():
            if st != "PASS":
                reasons.append(f"joint '{name}': {cid} {st}: {(rep['checks'][cid].get('note') or '')}".rstrip(": "))
        if not states:
            reasons.append(f"joint '{name}': the report has no checks")
        parts = rep.get("parts") or {}
        unknown = [k for k in ("a", "b") if (parts.get(k) or {}).get("sha256") not in part_shas]
        if j.get("proxy"):
            entry["proxy"] = True
            notes.append(f"joint '{name}' is checked against a proxy built from numbers: it shows the part agrees "
                         "with those numbers, not that the numbers are right")
            if len(unknown) == 2:
                reasons.append(f"joint '{name}': neither STL the report measured is a part of this build")
        elif unknown:
            reasons.append(f"joint '{name}': the report measured "
                           f"{', '.join(rel((parts.get(k) or {}).get('path')) or k for k in unknown)}, which is not "
                           "a part of this build; mark the joint \"proxy\": true if that is a proxy of the mating "
                           "part, or fit the delivered parts")
        entries.append(entry)
    return entries, reasons, notes


def check_strength(verify):
    if "strength" not in verify:
        return [], ["members not declared (_verify.strength): P7 is not counted; list each member's strength.py "
                    "report, or [] when nothing carries load"], []
    entries, reasons, notes = [], [], []
    for s in verify["strength"]:
        name, report = s.get("name") or s.get("report"), s.get("report")
        entry = {"name": name, "report": rel(report)}
        if not report or not os.path.isfile(report):
            entry["state"] = "FAIL"
            reasons.append(f"member '{name}': strength report {rel(report)} not found; run strength.py and save it")
        else:
            rep = load_json(report, "strength report")
            if not isinstance(rep, dict) or rep.get("schema") != "3dprint-scout.strength/1":
                raise FinalizeError(f"{report}: not a strength.py report")
            entry.update(gate=rep.get("gate"), case=rep.get("case"), worst=rep.get("worst"), inputs=rep.get("inputs"))
            if rep.get("gate") != "PASS":
                reasons.append(f"member '{name}': strength.py {rep.get('case')} {rep.get('gate')} (worst: "
                               f"{rep.get('worst')})")
            notes.append(f"member '{name}': strength.py took its sizes from the numbers it was given "
                         f"({json.dumps(rep.get('inputs'), separators=(',', ':'))}), not from the model: they must "
                         "be the dimension table's")
        entries.append(entry)
    return entries, reasons, notes


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
    by_sha = {p["sha256"]: p["name"] for p in parts if p.get("sha256")}
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
            name = by_sha.get(sha)
            entries.append({"file": rel(path), "kind": "stl", "part": name, "same_as_verified": name is not None})
            if name is None:
                reasons.append(f"{rel(path)} is not one of the verified STLs (an older build, or another part): "
                               "copy the verified file, or take it out of the delivery")
            else:
                covered.add(name)
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
                    covered.update(by_sha[s] for s in m["parts"].values())
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
           "geometry": None, "shape": {}, "slicing": "unverified", "print": "unverified",
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
    objs, r, w = check_objects(build, same_as_build, drift)
    out["objects"] = objs
    reasons += r
    warns += w
    shas = {p.get("sha256") for p in parts if p.get("sha256")}
    joints, r, notes = check_joints(verify, shas)
    out["joints"] = joints
    reasons += r
    out["warnings"] += notes
    strength, r, notes = check_strength(verify)
    out["strength"] = strength
    reasons += r
    out["warnings"] += notes
    prints, print_lines = check_prints(verify)
    out["test_prints"] = prints
    accepted = verify.get("accepted") or []
    out["accepted"] = accepted
    taken = {" ".join(str(a.get("check", "")).split()).lower() for a in accepted}
    open_warns = [f"{who} WARN: {note}".rstrip(": ") for who, note in warns if " ".join(who.split()).lower() not in taken]
    reasons += [text for who, text in copied if " ".join(who.split()).lower() not in taken]
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
    out["open"] = (reasons + [f"open warning (not accepted in _verify.accepted): {w}" for w in open_warns]
                   + to_decide + print_lines + shape_lines
                   + [f"unverified: {u}" for u in out["unverified_dimensions"]]
                   + [f"assumption: {a}" for a in out["assumptions"]])
    out["summary"] = [
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
        out = {"schema": SCHEMA, "ran": False, "geometry": None, "warnings": [], "errors": [scrub(str(exc))]}
        code = 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
