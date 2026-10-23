"""finalize.py: each promise's state from its evidence, and the use tier."""
from __future__ import annotations

import json

from finalize_common import (ALLOWED, EVIDENCE, KINDS, NEEDS, PROMISE_KEYS, STATES, flatten, same_value, text_field, valid_check_entry)
from finalize_evidence import (check_dims)


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
