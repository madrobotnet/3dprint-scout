#!/usr/bin/env python3
"""
finalize.py - the final verification report of a build (Phase 6): one place that says what was
verified, with what evidence, and what was not, so a missing fit report or a skipped test print
can never look like a finished check.

  python3 finalize.py --build out/build.json --params .3dprint/params.json \\
      --printer .3dprint/printers.json [--deliver deliver/2026-10-21] [--bundle deliver/2026-10-21/source]

--build is the JSON that `build.py run` or `record` printed, saved (`build.py run ... > out/build.json`).
It names the parts, their STLs and the sources the build hashed. finalize does not trust it for
the verdicts: it validates every part STL again (validate.py, with the part's `expect` from
--params and the build's sources, so R3 says whether the STL still matches the generator and
parameters as they are now) and takes the object checks (A1 / A2, D2 of an object) from the
build only when every STL is still the one that build wrote.

What else counts is declared in params.json under `_verify` (every key optional, but a key that
is missing is reported as "not declared", which keeps the geometry from being verified):

  "_verify": {
    "joints":   [{"name": "lid on box", "report": "out/fit_box_lid.json"},
                 {"name": "clip on the tube", "report": "out/fit_clip.json", "proxy": true}],
    "strength": [{"name": "latch arm", "report": "out/strength_latch.json"}],
    "test_prints": [{"name": "hinge coupon", "status": "skipped", "note": "user had no time"}],
    "accepted": [{"check": "body P2", "reason": "the user wants supports there"}],
    "unverified": ["wall behind the label: estimated from a photo"],
    "references": {"lid": {"front": "real", "top": "real", "back": "estimated", "bottom": "assumed"}}
  }

joints: every joint F3 must cover, with its saved fit.py report: the report must be fresh (its
STLs are the parts being delivered, or a declared proxy) and its own F3 / F3_sweep must PASS.
An empty list says the design has no joint. strength: strength.py reports (saved JSON), their
gate must PASS. test_prints: coupons and mechanism-first prints (status passed, failed,
skipped, offered or pending). accepted: WARNs the user accepted, with their reason; any other
WARN is listed as open. unverified: dimensions taken without a measurement. references: for each
object, which directions a reference shows (`real`), or was generated or inferred
(`estimated`), or given up on (`assumed`); a direction without a real reference is a direction
whose shape is not verified.

The report has four tiers and never folds them into one PASS:
  geometry  verified | not verified   the STLs, joints and members, from the checks above
  shape     per object, the directions a real reference covers
  slicing   unverified                  nothing here slices; say so at delivery
  print     unverified                  test prints and their results, if any
plus `open`: every reason the geometry is not verified, every unaccepted WARN, every
unverified dimension and assumption, in plain lines for the delivery message.

--deliver DIR compares the delivered STLs (same file names) with the verified ones: a copy that
differs is a FAIL. --bundle DIR writes a new folder with the generator sources (not the skill's
own libraries), params.json, this report and REPRODUCE.md (the commands that rebuild and
re-check the parts); it refuses an existing folder. Exit 0 when it ran (read "geometry"), 1 on a
usage or file error.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate  # noqa: E402

SCHEMA = "3dprint-scout.finalize/1"
ENGINES_DIR = os.path.join(os.path.dirname(HERE), "references", "engines")
DIRECTIONS = ("front", "back", "left", "right", "top", "bottom")
COVERAGE = ("real", "estimated", "assumed", "none")
PRINT_STATUS = ("passed", "failed", "skipped", "offered", "pending")


class FinalizeError(Exception):
    pass


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


def part_specs(params):
    parts = params.get("_parts") or {}
    return {str(k): dict(v or {}) for k, v in parts.items()} if isinstance(parts, dict) else {}


def validate_part(stl, spec, sources, params_path, args):
    argv = [stl, "--shells", str(spec.get("shells", 1))]
    if spec.get("expect"):
        argv += ["--expect", ",".join(str(x) for x in spec["expect"])]
    for flag in ("tol", "printer_id", "overhang_angle", "min_wall"):
        if spec.get(flag) is not None:
            argv += ["--" + flag.replace("_", "-"), str(spec[flag])]
    if args.printer:
        argv += ["--printer", args.printer]
    if args.tools:
        argv += ["--tools", args.tools]
    if not args.wall_check:
        argv.append("--no-wall-check")
    argv += ["--source", *sources, "--params", params_path]
    buf = io.StringIO()
    with redirect_stdout(buf):
        validate.main(argv)
    return json.loads(buf.getvalue())


def check_parts(build, specs, params_path, args):
    """Every part STL validated again now. Returns (part entries, reasons, warns, all fresh)."""
    sources = build.get("sources") or []
    missing = [s for s in sources if not os.path.isfile(s)]
    entries, reasons, warns = [], [], []
    fresh_all = True
    if missing:
        reasons.append(f"sources the build hashed are missing: {', '.join(missing)} (run finalize from the folder the "
                       "build ran in)")
    for p in build.get("parts") or []:
        name, stl = p.get("name"), p.get("stl")
        entry = {"name": name, "stl": rel(stl)}
        if not stl or not os.path.isfile(stl):
            entry["state"] = "FAIL"
            reasons.append(f"{name}: STL {stl} not found")
            fresh_all = False
            entries.append(entry)
            continue
        entry["sha256"] = validate.file_sha256(stl)
        if missing:
            entry["state"] = "UNVERIFIED"
            fresh_all = False
            entries.append(entry)
            continue
        rep = validate_part(stl, specs.get(name, {}), sources, params_path, args)
        f = (rep.get("files") or [{}])[0]
        checks = f.get("checks") or {}
        entry["gate"] = rep.get("gate")
        entry["checks"] = {k: v.get("state") for k, v in checks.items()}
        r3 = checks.get("R3", {})
        if r3.get("state") != "PASS":
            fresh_all = False
            reasons.append(f"{name} R3 {r3.get('state')}: {r3.get('note', '')}".rstrip(": "))
        for cid, ck in checks.items():
            if cid == "R3":
                continue
            if ck.get("state") == "FAIL" and ck.get("kind") == "hard":
                reasons.append(f"{name} {cid} FAIL: {ck.get('note', '')}".rstrip(": "))
            elif ck.get("state") == "UNVERIFIED" and ck.get("kind") == "hard":
                reasons.append(f"{name} {cid} UNVERIFIED: {ck.get('note', '')}".rstrip(": "))
            elif ck.get("state") == "WARN":
                warns.append((f"{name} {cid}", ck.get("note", "")))
        for e in rep.get("errors", []):
            reasons.append(f"{name}: {e}")
        entries.append(entry)
    if not entries:
        reasons.append("the build lists no parts")
    return entries, reasons, warns, fresh_all


def check_objects(build, fresh_all):
    """Object checks from the build (A1 / A2, an object's D2 / P1 / P2), only while every STL is
    still the one that build wrote."""
    entries, reasons, warns = [], [], []
    for o in build.get("objects") or []:
        if "checks" not in o and len(o.get("parts", [])) < 2 and "partial" not in o:
            continue
        entry = {"name": o.get("name"), "gate": o.get("gate"), "parts": o.get("parts")}
        if not fresh_all:
            entry["state"] = "UNVERIFIED"
            reasons.append(f"object '{o.get('name')}': its checks are from a build whose STLs changed or could not be "
                           "re-checked; build again")
        else:
            if o.get("partial"):
                reasons.append(f"object '{o.get('name')}' was built in part (--only): not judged as a whole")
            for cid, ck in (o.get("checks") or {}).items():
                if ck.get("state") in ("FAIL", "UNVERIFIED") and ck.get("kind") == "hard":
                    reasons.append(f"object '{o.get('name')}' {cid} {ck['state']}: {ck.get('note', '')}".rstrip(": "))
                elif ck.get("state") == "WARN":
                    warns.append((f"{o.get('name')} {cid}", ck.get("note", "")))
        entries.append(entry)
    for p in build.get("parts") or []:
        asm = p.get("assembly") or {}
        for cid, ck in (asm.get("checks") or {}).items():
            if not fresh_all:
                continue
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
    for j in verify["joints"] or []:
        name, report = j.get("name") or j.get("report"), j.get("report")
        entry = {"name": name, "report": rel(report)}
        if not report or not os.path.isfile(report):
            entry["state"] = "FAIL"
            reasons.append(f"joint '{name}': fit report {report} not found; run fit.py and save it")
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
        unknown = [k for k in ("a", "b") if (rep.get("parts") or {}).get(k, {}).get("sha256") not in part_shas]
        if unknown and not j.get("proxy"):
            reasons.append(f"joint '{name}': the report measured {', '.join(rel((rep['parts'].get(k) or {}).get('path')) for k in unknown)}, "
                           "which is not a part of this build; mark the joint \"proxy\": true if that is a proxy "
                           "of the mating part, or fit the delivered parts")
        if j.get("proxy"):
            entry["proxy"] = True
            notes.append(f"joint '{name}' is checked against a proxy built from numbers: it shows the part agrees "
                         "with those numbers, not that the numbers are right")
        entries.append(entry)
    return entries, reasons, notes


def check_strength(verify):
    if "strength" not in verify:
        return [], ["members not declared (_verify.strength): P7 is not counted; list each member's strength.py "
                    "report, or [] when nothing carries load"]
    entries, reasons = [], []
    for s in verify["strength"] or []:
        name, report = s.get("name") or s.get("report"), s.get("report")
        entry = {"name": name, "report": rel(report)}
        if not report or not os.path.isfile(report):
            entry["state"] = "FAIL"
            reasons.append(f"member '{name}': strength report {report} not found; run strength.py and save it")
        else:
            rep = load_json(report, "strength report")
            if rep.get("schema") != "3dprint-scout.strength/1":
                raise FinalizeError(f"{report}: not a strength.py report")
            entry.update(gate=rep.get("gate"), case=rep.get("case"), worst=rep.get("worst"))
            if rep.get("gate") != "PASS":
                reasons.append(f"member '{name}': strength.py {rep.get('case')} {rep.get('gate')} (worst: "
                               f"{rep.get('worst')})")
        entries.append(entry)
    return entries, reasons


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
    refs = verify["references"] or {}
    for obj, slots in refs.items():
        slots = slots or {}
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


def check_delivered(deliver, parts):
    entries, reasons = [], []
    for p in parts:
        if not p.get("stl"):
            continue
        copy = os.path.join(deliver, os.path.basename(p["stl"]))
        if not os.path.isfile(copy):
            entries.append({"name": p["name"], "delivered": None})
            reasons.append(f"{p['name']}: no {os.path.basename(p['stl'])} in {rel(deliver)}")
            continue
        same = validate.file_sha256(copy) == p.get("sha256")
        entries.append({"name": p["name"], "delivered": rel(copy), "same_as_verified": same})
        if not same:
            reasons.append(f"{p['name']}: the delivered {rel(copy)} is not the STL that was verified")
    return entries, reasons


def own_sources(build):
    """The generator's own files among the build's sources (not the skill's libraries)."""
    lib = {os.path.normcase(os.path.abspath(d)) for d in (HERE, ENGINES_DIR)}
    return [s for s in build.get("sources") or []
            if os.path.normcase(os.path.dirname(os.path.abspath(s))) not in lib]


def write_bundle(folder, build, params_path, report):
    if os.path.exists(folder):
        raise FinalizeError(f"{folder} exists; the bundle goes into a new folder (never overwrites)")
    srcs = own_sources(build)
    os.makedirs(os.path.join(folder, "source"))
    written = []
    for s in srcs:
        dst = os.path.join(folder, "source", os.path.basename(s))
        shutil.copyfile(s, dst)
        written.append(rel(dst))
    pdst = os.path.join(folder, "source", "params.json")
    shutil.copyfile(params_path, pdst)
    written.append(rel(pdst))
    with open(os.path.join(folder, "verification.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    written.append(rel(os.path.join(folder, "verification.json")))
    names = [os.path.basename(s) for s in srcs]
    main = os.path.basename(build.get("source") or (names[0] if names else "model"))
    engine = build.get("engine") or "?"
    lines = ["# Reproduce", "",
             f"Engine: {engine}. Generator: `{main}`. Parameters: `params.json`. Run from the `source` folder, with "
             "`SKILL_DIR` the 3dprint-scout skill folder.", ""]
    if engine in ("openscad", "python", "blender"):
        lines += ["```bash", f'python3 "$SKILL_DIR/scripts/build.py" run {main} --params params.json --out out > out_build.json',
                  "```", ""]
    else:
        lines += [f"This build was recorded (`build.py record`, engine {engine}): run the generator in {engine}, export "
                  "one STL per part named after the part, then:", "", "```bash",
                  f'python3 "$SKILL_DIR/scripts/build.py" record <part>.stl ... --source {" ".join(names) or main} '
                  "--params params.json --engine " + engine + " --out out > out_build.json", "```", ""]
    lines += ["Then re-check, with the same printers.json as the build:", "", "```bash",
              'python3 "$SKILL_DIR/scripts/finalize.py" --build out_build.json --params params.json', "```", "",
              "`verification.json` is the report this delivery was made with: what was verified, and what was not.", ""]
    with open(os.path.join(folder, "REPRODUCE.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    written.append(rel(os.path.join(folder, "REPRODUCE.md")))
    return written


def finalize(args):
    build = load_json(args.build, "build report")
    if not isinstance(build, dict) or build.get("schema") != "3dprint-scout.build/1":
        raise FinalizeError(f"{args.build}: not a build.py run / record report")
    params = load_json(args.params, "params")
    specs = part_specs(params)
    verify = params.get("_verify") or {}
    if not isinstance(verify, dict):
        raise FinalizeError("_verify in params.json must be an object")
    out = {"schema": SCHEMA, "ran": True, "build": rel(args.build), "engine": build.get("engine"),
           "geometry": None, "shape": {}, "slicing": "unverified", "print": "unverified",
           "parts": [], "objects": [], "joints": [], "strength": [], "test_prints": [], "open": [],
           "accepted": [], "assumptions": list(params.get("_assumptions") or []),
           "unverified_dimensions": list(verify.get("unverified") or []), "warnings": [], "errors": []}
    reasons = []
    if not build.get("ran"):
        reasons.append("the build did not run")
    parts, r, warns, fresh_all = check_parts(build, specs, args.params, args)
    out["parts"] = parts
    reasons += r
    objs, r, w = check_objects(build, fresh_all)
    out["objects"] = objs
    reasons += r
    warns += w
    shas = {p.get("sha256") for p in parts if p.get("sha256")}
    joints, r, notes = check_joints(verify, shas)
    out["joints"] = joints
    reasons += r
    out["warnings"] += notes
    strength, r = check_strength(verify)
    out["strength"] = strength
    reasons += r
    prints, print_lines = check_prints(verify)
    out["test_prints"] = prints
    accepted = verify.get("accepted") or []
    out["accepted"] = accepted
    taken = {str(a.get("check", "")).strip().lower() for a in accepted}
    open_warns = [f"{who} WARN: {note}".rstrip(": ") for who, note in warns if who.strip().lower() not in taken]
    if args.deliver:
        delivered, r = check_delivered(args.deliver, parts)
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
                   + print_lines + shape_lines
                   + [f"unverified: {u}" for u in out["unverified_dimensions"]]
                   + [f"assumption: {a}" for a in out["assumptions"]])
    out["summary"] = [
        "geometry: " + ("verified (every part, object, declared joint and member checked against the files being "
                        "delivered)" if geometry_ok else f"not verified ({len(reasons) + len(open_warns)} open items)"),
        "shape: " + ("; ".join(f"{o} from {', '.join(v['verified_from']) or 'no direction'}" for o, v in shape.items())
                     or "not declared"),
        "slicing: unverified (not sliced here)",
        "print: " + out["print"]]
    if args.bundle:
        out["bundle"] = write_bundle(args.bundle, build, args.params, out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="final verification report of a build (Phase 6)")
    ap.add_argument("--build", required=True, help="the saved JSON of build.py run / record")
    ap.add_argument("--params", default=os.path.join(".3dprint", "params.json"))
    ap.add_argument("--printer", help="printers.json, as the build had it (D2)")
    ap.add_argument("--tools", help="tool ids, as the build had them")
    ap.add_argument("--no-wall-check", dest="wall_check", action="store_false", help="skip P3 (ray casting)")
    ap.add_argument("--deliver", help="the delivery folder: its STLs must be the verified ones")
    ap.add_argument("--bundle", help="a new folder for the sources, params, this report and REPRODUCE.md")
    try:
        args = ap.parse_args(argv)
        out = finalize(args)
        code = 0
    except (FinalizeError, OSError) as exc:
        out = {"schema": SCHEMA, "ran": False, "geometry": None, "warnings": [], "errors": [str(exc)]}
        code = 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
