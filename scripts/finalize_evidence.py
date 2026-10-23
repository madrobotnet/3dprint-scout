"""finalize.py: the evidence promises rest on (joints, strength, dims, measurements, seen images,
test prints, materials)."""
from __future__ import annotations

import argparse
import json
import os
import re
import validate

from finalize_common import (DIM_KEYS, DIM_SOURCES, DIM_STATE, FinalizeError, IMAGE_SCHEMA, LINKED_ORIGINS,
    SEEN_KEYS, effective_material, finite, load_json, lookup, norm, rel, same_value, text_field)


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
        entry.update({k: d[k] for k in ("unit", "tol", "by", "url", "where", "from", "note") if k in d})
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
