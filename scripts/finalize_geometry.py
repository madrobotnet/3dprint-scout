"""finalize.py: the parts, the build, the objects, the print tier and the reference directions."""
from __future__ import annotations

import os
import validate

from finalize_common import (source_file, COVERAGE, DECIDED_KEYS, DECIDED_RESULTS, DIRECTIONS, FinalizeError, PRINT_STATUS,
    norm, rel, text_field)

STALE_DECISION = "decided for another build of the part: decide again"


def check_parts(build, specs, params_path, settings, soft=None):
    """Every part STL validated again now, as the build did. Returns (entries, reasons, warns,
    to_decide, same_as_build) where same_as_build says every STL is the one the build judged.
    `soft`, a list, gets one {"check": "<part> <check>", "line", "sha256"} per to_decide line,
    in the same order (check_decided reads it)."""
    import build as build_mod
    sources = [source_file(s) for s in build.get("sources") or []]
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
                if soft is not None:
                    soft.append({"check": f"{name} {cid}", "line": to_decide[-1], "sha256": entry["sha256"]})
            elif state == "WARN":
                warns.append((f"{name} {cid}", note))
        for e in rep.get("errors", []):
            reasons.append(f"{name}: {e}")
        entries.append(entry)
    if not entries:
        reasons.append("the build lists no parts")
    return entries, reasons, warns, to_decide, copied, same_as_build


SOFT_LEFT = ("p3", "p4", "p5", "p6")          # the soft checks finalize can leave to you (norm'd)


def check_decided(verify, parts, soft, taken):
    """_verify.decided: the agent's decision on a soft check finalize leaves to it (the to_decide
    lines: P3 when the wall check was skipped, P4, P5, P6), each {"check": "<part> <check>",
    "result": "holds" | "warn", "reason", "sha256": the part's STL as the build JSON records it}.
    A decision stands while the part's STL is that one (sha256); a stale one leaves the line as it
    was, saying so. `holds` takes the line out of open; `warn` turns it into a WARN the user
    decides ("<part> <check> WARN (decided): <reason>"), which _verify.accepted can accept as
    "<part> <check>" (taken). Soft checks never touch the gate or the geometry tier. Returns (the
    to_decide lines as they now read, the decided entries {check, result, reason} or None when
    nothing is declared, the declaration errors)."""
    lines = [s["line"] for s in soft]
    if "decided" not in verify:
        return lines, None, []
    left = {norm(s["check"]): s for s in soft}
    names = sorted({p.get("name") for p in parts if isinstance(p.get("name"), str)}, key=len, reverse=True)
    judged = {p.get("name") for p in parts if "checks" in p}         # validated again now
    fresh, stale, done, decided, errors = {}, set(), set(), [], []
    for i, e in enumerate(verify.get("decided") or []):
        check = e.get("check")
        ok_check = text_field(e, "check")
        label = f"decided '{check}'" if ok_check else f"decided entry {i + 1}"
        errs = []
        unknown = sorted(k for k in e if k not in DECIDED_KEYS)
        if unknown:
            errs.append(f"{label}: unknown field {', '.join(unknown)} (fields: {', '.join(DECIDED_KEYS)})")
        key = norm(check) if ok_check else None
        part = next((n for n in names if key and key.startswith(norm(n) + " ")), None) if ok_check else None
        if not ok_check:
            errs.append(f"{label}: needs check, the soft check as finalize names it (\"<part> <check>\")")
        elif key in done:
            errs.append(f"{label}: decided more than once")
        elif key not in left and part is None:
            errs.append(f"{label}: names no part of this build (\"<part> <check>\", as finalize names it)")
        elif key not in left and part in judged and key[len(norm(part)) + 1:] not in SOFT_LEFT:
            errs.append(f"{label}: not a check finalize leaves you to decide (only the soft checks it lists as "
                        "UNVERIFIED (yours to decide): " + (", ".join(s["check"] for s in soft) or "none now") + ")")
        if e.get("result") not in DECIDED_RESULTS:
            errs.append(f"{label}: result must be holds or warn (your decision on the check)")
        if not text_field(e, "reason"):
            errs.append(f"{label}: needs a reason, in one line (why it holds, or what the user must decide)")
        if not text_field(e, "sha256"):
            errs.append(f"{label}: needs sha256, the digest of the part's STL as the build JSON records it")
        if ok_check:
            done.add(key)
        if errs:
            errors += errs
            continue
        if key not in left:                       # a part not validated again now (its reasons say why), or a
            continue                              # P3 that the wall check now decides itself
        if e["sha256"] != left[key]["sha256"]:
            stale.add(key)
            continue
        fresh[key] = (e["result"], e["reason"])
        decided.append({"check": left[key]["check"], "result": e["result"], "reason": e["reason"]})
    lines = []
    for s in soft:
        key = norm(s["check"])
        if key in fresh:
            result, reason = fresh[key]
            if result == "warn" and key not in taken:
                lines.append(f"{s['check']} WARN (decided): {reason}")
        elif key in stale:
            lines.append(f"{s['line']}; {STALE_DECISION}")
        else:
            lines.append(s["line"])
    return lines, decided, errors


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
