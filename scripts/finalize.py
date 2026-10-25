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
    "decided":  [{"check": "lid P6", "result": "holds", "reason": "the preview shows no bed edge that flares",
                  "sha256": "..."},
                 {"check": "lid P4", "result": "warn", "reason": "a 30 mm bridge under the rim needs supports",
                  "sha256": "..."}],
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
exists); and promises the user takes without verifying them ("by": "user"). decided: your
decision on a soft check finalize leaves to you (a line "<part> <check> UNVERIFIED (yours to
decide)": P3 when the wall check was skipped, P4, P5, P6), named "<part> <check>", with result
holds or warn, a one-line reason, and sha256, the part's STL as the build JSON records it. It
stands while the part's STL is that one; a stale one leaves the line in open, saying "decided
for another build of the part: decide again". holds takes the line out of open and lists the
decision in the report's `decided`; warn lists it there too and leaves "<part> <check> WARN
(decided): <reason>" in open for the user, which they accept in accepted as "<part> <check>".
Naming any other check (a hard one, a part not in this build), or a result, reason or sha256
missing, is a declaration error. Soft checks never change the geometry tier. unverified:
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
A not verified promise delivered unproven has the _assumptions line "<id>: delivered as a
prototype, not verified", optionally ending in a note in parentheses that says who chose it
(the user's reply, or "(unattended run)"): it is marked "prototype": true, named in the use
summary and not counted as an assumption on its own.

The report has five tiers and never folds them into one PASS:
  use       the worst state of its promises (error, failed, not verified, excluded, assumed,
            accepted, verified, in that order), or not declared (no promises, or an empty list)
  geometry  verified | not verified   the STLs, objects, joints and members, from the checks above
  shape     per object, the directions a real reference covers
  slicing   unverified                  nothing here slices; say so at delivery
  print     unverified                  test prints and their results, if any
plus `open`: every promise that is not verified and why, every reason the geometry is not
verified, every unaccepted WARN, the soft checks left to you (P3 skipped, P4, P5, P6) that
_verify.decided does not settle, every unverified dimension and assumption, in plain lines for
the delivery message; and with _verify.decided, `decided`: each decision that stands (check,
result, reason).

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
(building them again shows the verdict is reached again; a proxy no longer built from its params file
is carried as it was, its build JSON listed as left out), with the build's engine, core 3MF
choice and settings. A file that is named but not found is listed in REPRODUCE.md and in
bundle_missing (a missing report is missing in the verdict too; so is a missing printers.json
the build used, which the commands still name). It refuses, before making the folder: an
existing folder; a build that is no longer this project's (an STL or R3 that is not the
build's, a part it did not make, the grouping, a material or printers.json changed since:
the rebuild would not see it) or settings given here that differ from the build's; a source
that is gone; a file, part STL or core 3MF outside the project folder; a carried file that
the commands write again (a delivery in out/, a report on the core 3MF) or two builds that
write one file; a name that is not UTF-8; and a source, params file or carried text file that
holds a path of this machine in any of the usual encodings (the scripts record the paths they
are given: give them relative ones). If writing still fails, nothing is left behind. Exit 0
when it ran (read "use" and "geometry"), 1 on a usage or file error.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from finalize_common import (# noqa: E402, F401  (every name stays importable from finalize)
    ALLOWED,
    COVERAGE,
    DECIDED_KEYS,
    DECIDED_RESULTS,
    DIM_KEYS,
    DIM_SOURCES,
    DIM_STATE,
    DIRECTIONS,
    ENGINES_DIR,
    EVIDENCE,
    FORM_AFTER,
    FORM_BEFORE,
    FinalizeError,
    IMAGE_SCHEMA,
    JsonArgParser,
    KINDS,
    LINKED_ORIGINS,
    MANIFEST_3MF,
    NEEDS,
    PRINT_STATUS,
    PROMISE_KEYS,
    PROTOTYPE,
    SCAN_ENCODINGS,
    SCHEMA,
    SEEN_KEYS,
    SETTINGS,
    STATES,
    VALIDATE_DEFAULTS,
    _byte_bounds,
    _setting,
    check_verify_shape,
    effective_material,
    finite,
    flatten,
    holds_machine_path,
    load_json,
    lookup,
    machine_byte_patterns,
    machine_forms,
    machine_prefixes,
    norm,
    part_specs,
    path_forms,
    plural,
    rel,
    same_file,
    same_value,
    scrub,
    settings_drift,
    settings_for,
    text_field,
    valid_check_entry)
from finalize_geometry import (# noqa: E402, F401  (every name stays importable from finalize)
    STALE_DECISION,
    assembly_drift,
    check_build,
    check_decided,
    check_objects,
    check_parts,
    check_prints,
    check_references)
from finalize_evidence import (# noqa: E402, F401  (every name stays importable from finalize)
    MEASURE_ARGS,
    check_dims,
    check_joints,
    check_material_contract,
    check_material_drift,
    check_measurements,
    check_print_evidence,
    check_seen,
    check_strength,
    current_printer,
    expectation_problem,
    measured_parts,
    photos_problem,
    proxy_provenance,
    remeasure,
    strength_link,
    user_file_problems)
from finalize_promises import (# noqa: E402, F401  (every name stays importable from finalize)
    check_promises,
    evidence_index,
    judged_evidence,
    promise_state)
from finalize_deliver import (# noqa: E402, F401  (every name stays importable from finalize)
    NO_PROJECT,
    check_delivered,
    check_delivered_print,
    manifest_folders,
    threemf_manifest_files,
    threemf_manifests)
from finalize_bundle import (# noqa: E402, F401  (every name stays importable from finalize)
    BUNDLE_OWN,
    NOT_TEXT,
    RUN_ENGINES,
    build_field_problems,
    bundle_contents,
    bundle_path,
    created_root,
    json_object,
    made_by_run,
    not_utf8,
    own_sources,
    rebuild_blockers,
    write_bundle)


def finalize(args):
    build, params, specs, verify = _load_inputs(args)
    settings = settings_for(build, args)
    out = {"schema": SCHEMA, "ran": True, "build": rel(args.build), "engine": build.get("engine"),
           "use": None, "geometry": None, "shape": {}, "slicing": "unverified", "print": "unverified",
           "settings": {f: getattr(settings, f) for f in SETTINGS} | {"wall_check": settings.wall_check},
           "parts": [], "objects": [], "joints": [], "strength": [], "test_prints": [], "open": [],
           "accepted": [], **({"decided": []} if "decided" in verify else {}),
           "assumptions": list(params.get("_assumptions") or []),
           "unverified_dimensions": list(verify.get("unverified") or []), "warnings": [], "errors": []}
    out["settings"]["printer"] = rel(settings.printer)
    reasons = check_build(build)
    soft = []
    parts, r, warns, to_decide, copied, same_as_build = check_parts(build, specs, args.params, settings, soft)
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
    to_decide, decided, decided_errors = check_decided(verify, parts, soft, taken)
    if decided is not None:
        out["decided"] = decided
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
    extra = seen_errors + print_errors + check_material_contract(params, specs) + decided_errors
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
    prototypes, unlinked = _prototypes(out)
    out["summary"] = _summary(out, use, prototypes, unlinked, geometry_ok, len(reasons) + len(open_warns), shape,
                              args.deliver)
    if args.bundle:
        given = {f: getattr(args, f, None) for f in SETTINGS} | {"wall_check": args.wall_check}
        write_bundle(args.bundle, build, args.params, settings, out, verify, args.deliver, given,
                     rebuild_blockers(build, specs, parts, drift, metadata_drift, material_lines, settings))
    return json.loads(scrub(json.dumps(out, ensure_ascii=False)))


def _load_inputs(args):
    """The build JSON and params.json, each as finalize reads it, or a FinalizeError naming what is wrong."""
    build = load_json(args.build, "build report")
    if not isinstance(build, dict) or build.get("schema") != "3dprint-scout.build/1":
        raise FinalizeError(f"{args.build}: not a build.py run / record report")
    for key, kind, ok in (("sources", "file names", lambda x: isinstance(x, str)),
                          ("parts", "objects", lambda x: isinstance(x, dict))):
        if build.get(key) is not None and not (isinstance(build[key], list) and all(ok(x) for x in build[key])):
            raise FinalizeError(f"{args.build}: {key} must be a list of {kind}, as build.py writes it")
    vs = build.get("validate_settings")
    if vs is not None and not (isinstance(vs, dict) and (vs.get("printer") is None or isinstance(vs["printer"], str))):
        raise FinalizeError(f"{args.build}: validate_settings must be an object whose printer is a file name, as "
                            "build.py writes it")
    params = load_json(args.params, "params")
    if not isinstance(params, dict):
        raise FinalizeError(f"{args.params}: not a params object")
    specs = part_specs(params)
    verify = params.get("_verify") or {}
    if not isinstance(verify, dict):
        raise FinalizeError("_verify in params.json must be an object")
    check_verify_shape(verify)
    return build, params, specs, verify


def _prototypes(out):
    """The promises delivered as prototypes, and how many assumptions are not linked to a promise."""
    # A promise delivered unproven (phase 4, "Leaving Phase 4") is recorded as the _assumptions
    # line "<id>: delivered as a prototype, not verified", with an optional note in parentheses
    # saying who chose it: it belongs to that promise while the promise is not verified, so it is
    # not counted as an assumption on its own.
    by_id = {p["id"]: p for p in out["promises"] if isinstance(p.get("id"), str)}
    prototypes = []
    for a in out["assumptions"]:
        m = PROTOTYPE.match(a) if isinstance(a, str) else None
        if m and m.group(1) in by_id and by_id[m.group(1)]["state"] == "not verified" and m.group(1) not in prototypes:
            prototypes.append(m.group(1))
            by_id[m.group(1)]["prototype"] = True
    unlinked = (sum(1 for a in out["assumptions"] if not (isinstance(a, str) and PROTOTYPE.match(a)
                                                          and PROTOTYPE.match(a).group(1) in prototypes))
                + len(out["unverified_dimensions"]))
    return prototypes, unlinked


def _summary(out, use, prototypes, unlinked, geometry_ok, n_open, shape, deliver):
    """The report's summary lines, one per tier."""
    if out["use"] == "not declared":
        use_line = "use: not declared (_verify.promises)"
    else:
        tally = {}
        for p in out["promises"]:
            tally[p["state"]] = tally.get(p["state"], 0) + 1
        parts_of = ([plural(len(out["promises"]), "promise") + ": "
                     + ", ".join(f"{tally[s]} {s}" for s in STATES if s in tally)] if out["promises"] else [])
        parts_of += [plural(len(use["errors"]), "declaration error")] if use["errors"] else []
        parts_of += [f"delivered as a prototype: {', '.join(prototypes)}"] if prototypes else []
        parts_of += [plural(unlinked, "assumption") + " not linked to a promise"] if unlinked else []
        use_line = f"use: {out['use']} ({'; '.join(parts_of)})"
    return [
        use_line,
        "geometry: " + ("verified (every part, object, declared joint and member checked; the delivered files are "
                        "the verified ones)" if geometry_ok and deliver else
                        "verified (every part, object, declared joint and member checked)" if geometry_ok else
                        f"not verified ({n_open} open items)"),
        "shape: " + ("; ".join(f"{o} from {', '.join(v['verified_from']) or 'no direction'}" for o, v in shape.items())
                     or "not declared"),
        "slicing: unverified (not sliced here)",
        "print: " + out["print"]]


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
    text = json.dumps(out, indent=2, ensure_ascii=False)
    # A file name that is not UTF-8 (a delivered file named in another encoding) reaches the report
    # as surrogates, which no UTF-8 stdout can print: written as JSON escapes, it reads back the same.
    print(re.sub(r"[\ud800-\udfff]", lambda m: f"\\u{ord(m.group()):04x}", text))
    return code


if __name__ == "__main__":
    sys.exit(main())
