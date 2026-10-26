"""finalize.py: each promise's state from its evidence, and the use tier."""
from __future__ import annotations

import json

from finalize_common import (ALLOWED, EVIDENCE, KINDS, NEEDS, PROMISE_KEYS, STATES, FinalizeError, finite, flatten,
    load_json, same_value, text_field, valid_check_entry)
from finalize_evidence import (check_dims)
from finalize_section import Regions

LOAD = "it carries a load and no strength check names it"

CLOSE_PLAY_MM = 0.2          # a fit closer than this, confirmed by a print in another material, is named


def evidence_index(verify, key, entries):
    """{name: [(declaration, checked entry)]} for joints or strength, in declaration order."""
    index = {}
    for raw, entry in zip(verify.get(key) or [], entries):
        if isinstance(entry.get("name"), str):
            index.setdefault(entry["name"], []).append((raw, entry))
    return index


def judged_evidence(k, name, raw, entry, pid, gate, promise=None):
    """A seen image or a test print as one promise's evidence: what it adds to the promise's
    errors, failures, not-verified and assumed reasons, and its result for the report. For a test
    print, `promise` ({force, related, regions}, from _judge_promise) says whether the promise is
    geometric and what its joints and measurements check: a print in another material than the
    part's, or of a section, stands for a geometric promise only (judged_print)."""
    what = f"seen '{name}'" if k == "seen" else f"test print '{name}'"
    out = {"errs": [], "failed": [], "notver": [], "assumed": [], "result": None, "info": [], "warn": []}
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
    judged_print(what, entry, promise or {}, out)
    if state == "fresh" and entry.get("status") == "failed":
        out["failed"].append(f"{what} failed")
    elif entry.get("status") != "passed" and state == "fresh":
        out["notver"].append(f"{what}: {entry.get('status')}")
    if out.get("scope") == "geometry" and entry.get("status") == "passed" and state == "fresh" and not (
            out["notver"] or out["assumed"]):
        out["info"].append(_print_covers(what, entry))
        out["warn"] += _close_fits(what, entry, promise or {})
    return out


def judged_print(what, entry, promise, out):
    """A test print's own reasons as evidence of one promise. A part printed in another material
    than its own, or a section of a part, shows the geometry, not the strength: for a promise that
    carries a force (`force`: a `load` use, or one with strength evidence) a section does not
    stand and a print in another material keeps its line; for a geometric one the material line
    is dropped (the print's `scope` is "geometry"), and a section stands only when every joint
    and measurement of the promise that checks the cut part checks it inside the box (`scope`
    "none", with the reason, otherwise)."""
    force, sections = bool(promise.get("force")), entry.get("sections")
    other = entry.get("other_material") or []
    drop = set() if force else {o["line"] for o in other}
    out["notver"] += [f"{what}: {r}" for r in entry.get("notver") or [] if r not in drop]
    out["assumed"] += [f"{what}: {r}" for r in entry.get("assumed") or []]
    if sections is None:
        if other and not force:
            out["scope"] = "geometry"
        return
    cut = ", ".join(sorted(n for n, v in (entry["_raw"].get("parts") or {}).items() if "section" in v))
    if force:
        out["scope"] = "none"
        out["notver"].append(f"{what} is a section of {cut}: a section shows the fit, not the strength this promise "
                             "needs (it carries a load or names a strength check)")
        return
    out["scope"] = "geometry"
    if entry.get("state") != "fresh":
        out["scope"] = "none"                          # the piece is not the part cut by its box now: its line says so
        return
    problems = []
    for part, sec in sorted(sections.items()):
        box = (tuple(sec["box"][0]), tuple(sec["box"][1]))
        items = [r for r in promise.get("related") or [] if part in (r[3].get("measured") or [])]
        for kind, name, raw, item in items:
            why = promise["regions"].problem(kind, name, raw, item, part, box)
            if why:
                problems.append(f"{what} is a section of {part}: {why}")
    if not any(part in (r[3].get("measured") or []) for r in promise.get("related") or [] for part in sections):
        problems.append(f"{what} is a section of {cut}, and no joint or measurement of this promise checks "
                        f"{'it' if len(sections) == 1 else 'them'}: nothing shows that what it checks is inside the "
                        "section box")
    if problems:
        out["scope"] = "none"
        out["notver"] += problems


def _print_covers(what, entry):
    """What a print that stands for the geometry only shows, in one line."""
    other = {o["part"]: o for o in entry.get("other_material") or []}
    shown = []
    for n in sorted(set(other) | set(entry.get("sections") or {})):
        o = other.get(n)
        made = f" printed in {o['printed']}, the part is {o['material']}" if o else ""
        shown.append(f"a section of {n}{made}" if n in (entry.get("sections") or {}) else f"{n}{made}")
    return f"{what} shows the fit, not the strength: {'; '.join(shown)}"


def _close_fits(what, entry, promise):
    """A fit with less than CLOSE_PLAY_MM of play (its F3's min_play_mm) that a print in another
    material confirmed: one line each, since another material shrinks and squishes differently."""
    lines = []
    for o in entry.get("other_material") or []:
        for kind, name, raw, item in promise.get("related") or []:
            if kind != "joint" or o["part"] not in (item.get("measured") or []):
                continue
            try:
                rep = load_json(raw.get("report"), "fit report")
            except FinalizeError:
                continue
            checks = rep.get("checks") if isinstance(rep, dict) else None
            f3 = checks.get("F3") if isinstance(checks, dict) else None
            value = f3.get("value") if isinstance(f3, dict) else None
            play = value.get("min_play_mm") if isinstance(value, dict) else None
            if finite(play) and play < CLOSE_PLAY_MM - 1e-9:
                lines.append(f"joint '{name}' has {play:.3f} mm of play, under {CLOSE_PLAY_MM} mm, and {what} printed "
                             f"{o['part']} in {o['printed']}, not {o['material']}: another material shrinks and "
                             f"squishes differently, so a fit this close may not come out the same in {o['material']}")
    return lines


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

BY_HAND = "the motion by hand is not confirmed by a print (no passed test print among its evidence)"

WHERE_OF = {"joint": "_verify.joints", "strength": "_verify.strength", "measurement": "_verify.measurements",
            "seen": "_verify.seen", "test_print": "_verify.test_prints"}


def check_promises(verify, params, joints, strength, parts, measurements=(), seen=(), prints=None,
                   material_evidence=None):
    """The use tier: each promise made to the user, judged by its own evidence. A promise is
    verified only when it says under which conditions it holds and what counts as success, its
    evidence is of a kind allowed for it, of the current parts and passed, and nothing it rests
    on is an unmeasured size. A member verifies only from a --from-build report with no input
    typed in, of a part whose own checks pass, whose material (material_evidence: {part:
    {notver, assumed}}) holds. Returns a dict with tier, promises, counts, dims, errors, open."""
    dims, errors = check_dims(verify, params, measurements)
    out = {"tier": "not declared", "promises": [], "counts": {}, "dims": list(dims.values()), "errors": errors,
           "open": []}
    _check_evidence_dims(verify, errors)
    promises = verify.get("promises")
    ids = [p.get("id") for p in promises or []]
    excluded = _excluded_promises(verify, ids, errors)
    if promises is None:
        out["open"].append("promises not declared (_verify.promises): what the user was promised is not checked; "
                           "list each promise with its evidence")
    elif not promises:
        out["open"].append("the promise list (_verify.promises) is empty: an empty list verifies nothing; list what "
                           "the user was promised")
    ctx = {"gate": {p.get("name"): p.get("gate") for p in parts}, "dims": dims, "material": material_evidence,
           "index": _evidence_tables(verify, joints, strength, measurements, seen, prints or {}),
           "regions": Regions(parts)}
    for i, pr in enumerate(promises or []):
        _judge_promise(i, pr, ids, excluded, ctx, out)
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


def _check_evidence_dims(verify, errors):
    """A joint, member or measurement names the sizes it rests on as a list of _verify.dims ids."""
    for key, kind_name in (("joints", "joint"), ("strength", "member"), ("measurements", "measurement")):
        for raw in verify.get(key) or []:
            jd = raw.get("dims")
            if jd is not None and not (isinstance(jd, list) and all(isinstance(x, str) for x in jd)):
                errors.append(f"{kind_name} '{raw.get('name') or raw.get('report')}': dims must be a list of "
                              "_verify.dims ids")


def _excluded_promises(verify, ids, errors):
    """{promise id: the user's reason} for each promise the user took without verifying it."""
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
    return excluded


def _evidence_tables(verify, joints, strength, measurements, seen, prints):
    """{evidence kind: {name: [(declaration, checked entry)]}}."""
    index = {"joint": evidence_index(verify, "joints", joints),
             "strength": evidence_index(verify, "strength", strength),
             "measurement": evidence_index(verify, "measurements", measurements),
             "seen": evidence_index(verify, "seen", seen), "test_print": {}}
    for t in verify.get("test_prints") or []:
        if isinstance(t.get("name"), str):
            info = next((i for i in prints.get(t["name"], []) if i.get("_raw") is t), None)
            index["test_print"].setdefault(t["name"], []).append((t, info))
    return index


def _judge_promise(i, pr, ids, excluded, ctx, out):
    """One promise: its declaration, each evidence item, the sizes it rests on, its state."""
    pid, kind = pr.get("id"), pr.get("kind")
    ok_id = isinstance(pid, str) and bool(pid.strip())
    label = f"promise '{pid}'" if ok_id else f"promise {i + 1}"
    v = {"errs": [], "failed": [], "notver": [], "assumed": [], "acc": [], "info": [], "warn": [], "ev": [],
         "rests": []}
    _promise_declaration(pr, pid, kind, ok_id, ids, v)
    evidence = pr.get("evidence")
    if evidence is None or evidence == []:
        v["notver"].append("no evidence yet")
    elif not isinstance(evidence, list):
        v["errs"].append("evidence must be a list")
        evidence = []
    items = [it for it in evidence or [] if isinstance(it, dict)]
    # A use that carries a force (a `load` use, or one a strength check is evidence of) is proven
    # only by what shows the strength: a print in another material, or a section, shows the fit.
    strong = any("strength" in it for it in items)
    ctx["promise"] = {"force": kind == "use" and (pr.get("load") is True or strong),
                      "related": _related(items, ctx), "regions": ctx["regions"]}
    for item in evidence or []:
        _judge_item(item, pid, kind, ctx, v)
    if kind == "use" and pr.get("load") is True and not strong:
        v["notver"].append(LOAD)
    rests_on = _rests_on(v, ctx["dims"])
    state = promise_state(v["errs"], v["failed"], v["notver"], ok_id and pid in excluded, v["assumed"], v["acc"])
    reasons = v["errs"] + v["failed"] + v["notver"] + v["assumed"] + v["acc"] + v["info"] + v["warn"]
    if state == "excluded":
        reasons.insert(0, f"taken by the user without verifying it: {excluded[pid]}")
    # A motion done by hand (pushing a phone in, a peg in and out): the fit numbers say nothing of
    # how it moves, or whether the printed hole comes out at its size. Its state stays what its
    # evidence gives; without a passed test print among that evidence, finalize says so itself.
    # A section that does not stand for the promise (scope "none") confirms no motion.
    by_hand = kind == "use" and pr.get("by_hand") is True and not any(
        "test_print" in ev and ev.get("result") == "passed" and ev.get("scope") != "none" for ev in v["ev"])
    if by_hand:
        reasons.append(BY_HAND)
    entry = {"id": pid, "kind": kind, "text": pr.get("text")}
    entry.update({f: pr[f] for f in ("conditions", "success", "by_hand", "load") if f in pr})
    entry.update(state=state, reasons=reasons, evidence=v["ev"], rests_on=rests_on)
    out["promises"].append(entry)
    counts = out["counts"].setdefault(kind if kind in KINDS else "?", {})
    counts[state] = counts.get(state, 0) + 1
    if state != "verified":
        out["open"].append(f"{label} ({kind}) {state}: {'; '.join(reasons)}")
    else:                                          # a verified promise has no line of its own
        out["open"] += [f"{label} ({kind}): {w}" for w in v["warn"]]
        if by_hand:
            out["open"].append(f"{label} ({kind}): {BY_HAND}")


def _related(items, ctx):
    """The joints and measurements a promise names, as (kind, name, declaration, checked entry):
    where a section of a part is checked against its box. Wrong items are the main loop's to name."""
    out = []
    for it in items:
        named = [k for k in it if k != "covers"]
        if len(named) == 1 and named[0] in ("joint", "measurement") and isinstance(it[named[0]], str):
            matches = ctx["index"][named[0]].get(it[named[0]], [])
            if len(matches) == 1:
                out.append((named[0], it[named[0]]) + matches[0])
    return out


def _promise_declaration(pr, pid, kind, ok_id, ids, v):
    """The promise's own fields: id, kind, text, conditions and success, and assumes."""
    errs = v["errs"]
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
    if "by_hand" in pr:
        if not isinstance(pr["by_hand"], bool):
            errs.append("by_hand must be true or false")
        elif kind in KINDS and kind != "use":
            errs.append(f"by_hand is for a use promise (a motion done by hand), not a {kind}")
    if "load" in pr:
        if not isinstance(pr["load"], bool):
            errs.append("load must be true or false")
        elif kind in KINDS and kind != "use":
            errs.append(f"load is for a use promise (a use that carries a force), not a {kind}")
    assumes = pr.get("assumes", [])
    if not (isinstance(assumes, list) and all(isinstance(x, str) for x in assumes)):
        errs.append("assumes must be a list of _verify.dims ids")
    else:
        v["rests"] += [(d, "the promise") for d in assumes]


def _evidence_item(item, kind, ctx, errs):
    """(kind, name, declaration, checked entry) of one evidence item, or None after an error."""
    if not isinstance(item, dict):
        errs.append(f"evidence item {json.dumps(item, ensure_ascii=False)} must be an object")
        return None
    if "covers" in item and not isinstance(item["covers"], str):
        errs.append("covers must be text (what the evidence covers)")
    named = [k for k in item if k != "covers"]
    if len(named) != 1:
        errs.append(f"evidence item {json.dumps(item, ensure_ascii=False)} must name one of "
                    f"{', '.join(EVIDENCE)}")
        return None
    k, name = named[0], item[named[0]]
    if not (isinstance(name, str) and name.strip()):
        errs.append(f"evidence item {json.dumps(item, ensure_ascii=False)}: name the {k} with its text name")
        return None
    if k == "check":
        errs.append(f"'{name}' is a check of a part: it proves the part, not a promise; use "
                    f"{', '.join((ALLOWED[kind] if kind in KINDS else ()) or EVIDENCE)}")
        return None
    if k not in EVIDENCE:
        errs.append(f"unknown evidence kind '{k}' (finalize reads {', '.join(EVIDENCE)})")
        return None
    if kind in KINDS and k not in ALLOWED[kind]:
        errs.append(f"{k} is not evidence for a {kind} promise ("
                    + (f"it takes {', '.join(ALLOWED[kind])}" if ALLOWED[kind] else
                       "no evidence of it is read here yet") + ")")
        return None
    matches = ctx["index"][k].get(name, [])
    where = WHERE_OF[k]
    if not matches:
        errs.append(f"there is no {k} '{name}' in {where}")
        return None
    if len(matches) > 1:
        errs.append(f"{len(matches)} entries in {where} are named '{name}'")
        return None
    return (k, name) + matches[0]


def _judge_item(item, pid, kind, ctx, v):
    """One evidence item of a promise, into its reasons, evidence list and the sizes it rests on."""
    found = _evidence_item(item, kind, ctx, v["errs"])
    if found is None:
        return
    k, name, raw, entry = found
    if k in ("seen", "test_print"):
        judged = judged_evidence(k, name, raw, entry, pid, ctx["gate"], ctx.get("promise"))
        for key in ("errs", "failed", "notver", "assumed", "info", "warn"):
            v[key] += judged[key]
        if not judged["errs"]:
            ev = {k: name, "result": judged["result"]}
            if "covers" in item:
                ev["covers"] = item["covers"]
            if "scope" in judged:
                ev["scope"] = judged["scope"]
            v["ev"].append(ev)
        return
    res = entry.get("result")
    ev = {k: name, "result": res}
    if "covers" in item:
        ev["covers"] = item["covers"]
    v["ev"].append(ev)
    what = {"joint": f"joint '{name}'", "strength": f"member '{name}'"}.get(k, f"measurement '{name}'")
    _report_result(k, what, res, entry, v)
    if k == "joint":
        _joint_reasons(what, raw, entry, ctx, v)
    elif k == "measurement" and res in ("passed", "failed"):
        if not entry.get("measured"):
            v["notver"].append(f"{what}: it read {entry.get('file')}, which is not a part of this build")
        bad = [n for n in entry.get("measured") or [] if ctx["gate"].get(n) == "FAIL"]
        if bad:
            v["notver"].append(f"{what} read {', '.join(bad)}, whose own checks FAIL")
    elif k == "strength" and res in ("passed", "accepted"):
        _member_reasons(what, entry, ctx, v)
    jd = raw.get("dims")
    if isinstance(jd, list):
        v["rests"] += [(d, what) for d in jd if isinstance(d, str)]


def _report_result(k, what, res, entry, v):
    """What a joint, member or measurement report's own result adds to the promise."""
    if res == "missing":
        v["notver"].append(f"{what}: no report" + (f" ({entry['note']})" if entry.get("note") else ""))
    elif res == "stale":
        v["notver"].append(f"{what}: the file it measured has changed since, or is gone" if k == "measurement" else
                           f"{what}: {'; '.join(entry.get('stale') or [])}" if k == "strength" else
                           f"{what}: its fit report is not of the current parts")
    elif res == "failed":
        v["failed"].append(f"{what} failed" + (": " + "; ".join(
            f"{e.get('path')} = {json.dumps(e.get('value'))}, expected {e.get('op')} {e.get('target')}"
            for e in entry.get("expect") or [] if e.get("state") == "FAIL") if k == "measurement" else ""))
    elif res == "open":
        v["notver"].append(f"{what}: not every check passed" if k == "joint" else
                           f"{what}: strength.py gate {entry.get('gate')}")
    elif res == "accepted":
        v["acc"].append(f"{what}: passed apart from WARNs the user accepted ({', '.join(entry['accepted'])})")


def _joint_reasons(what, raw, entry, ctx, v):
    """A joint's parts, and its proxy: undeclared, untied, stale, or tied to exactly its dims."""
    bad = [n for n in entry.get("measured") or [] if ctx["gate"].get(n) == "FAIL"]
    if bad:
        v["notver"].append(f"{what} fitted {', '.join(bad)}, whose own checks FAIL")
    if raw.get("proxy") and not raw.get("dims"):
        v["assumed"].append(f"{what} is fitted against a proxy whose sizes are not declared (dims)")
    elif raw.get("proxy") and entry.get("proxy_build") == "untied":
        v["assumed"].append(f"{what} names the sizes of its proxy, but nothing ties the proxy to them: "
                            f"{entry.get('proxy_note')}")
    elif raw.get("proxy") and entry.get("proxy_build") == "stale":
        v["notver"].append(f"{what}: {entry.get('proxy_note')}")
    elif raw.get("proxy") and isinstance(raw.get("dims"), list):
        # tied: the proxy got exactly the numbers its dims declare, no fewer and no others
        dims, declared = ctx["dims"], {}
        for did in raw["dims"]:
            if isinstance(did, str) and isinstance((dims.get(did) or {}).get("params"), dict):
                declared.update(dims[did]["params"])
        declared, got = flatten(declared), flatten(entry.get("proxy_params") or {})
        differ = [k for k in got if k in declared and not same_value(got[k], declared[k])]
        loose = [k for k in got if k not in declared]
        unused = [k for k in declared if k not in got]
        if differ:
            v["notver"].append(f"{what}: the proxy was built from "
                               + ", ".join(f"{k} = {json.dumps(got[k])}" for k in differ)
                               + ", not the values its dims declare")
        if loose:
            v["assumed"].append(f"{what}: the proxy was also built from {', '.join(loose)}, which no dims "
                                "entry it names declares")
        if unused:
            v["assumed"].append(f"{what}: the proxy was not given {', '.join(unused)}, which its dims declare")


def _member_reasons(what, entry, ctx, v):
    """A member: linked to the build with nothing typed in, of a part that passes, in its material."""
    notver, assumed = v["notver"], v["assumed"]
    manual = entry.get("manual") or []
    if not entry.get("linked"):
        notver.append(f"{what}: its inputs were typed in, not taken from the build's parameters")
    elif manual:
        notver.append(f"{what}: {', '.join(manual)} {'was' if len(manual) == 1 else 'were'} typed in, not "
                      "taken from the build's parameters")
    if entry.get("linked") and ctx["gate"].get(entry.get("part")) == "FAIL":
        notver.append(f"{what} is calculated for {entry['part']}, whose own checks FAIL")
    for key, into in (("notver", notver), ("assumed", assumed)):
        into += [f"{what}: {r}" for r in ((ctx["material"] or {}).get(entry.get("part")) or {}).get(key, [])
                 if entry.get("linked") and f"{what}: {r}" not in into]


def _rests_on(v, dims):
    """The dims ids the promise rests on, in order, with what each adds to it."""
    rests_on = []
    for did, via in v["rests"]:
        if did not in rests_on:
            rests_on.append(did)
        d = dims.get(did)
        if d is None:
            v["errs"].append(f"{via} rests on dims '{did}', which is not in _verify.dims")
        elif d["state"] == "error":
            v["errs"].append(f"dims '{did}' has a declaration error")
        elif d["state"] == "unbacked":
            line = f"dims '{did}' is not backed by its measurements: {'; '.join(d.get('problems') or [])}"
            if line not in v["notver"]:
                v["notver"].append(line)
        elif d["state"] == "assumed":
            line = f"rests on '{did}' ({d.get('what')}), which is assumed, not measured"
            if line not in v["assumed"]:
                v["assumed"].append(line)
    return rests_on
