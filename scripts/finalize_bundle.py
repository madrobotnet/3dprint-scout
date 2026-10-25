"""finalize.py --bundle: what a source bundle carries, what refuses it, and REPRODUCE.md."""
from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
import shutil
import validate

from finalize_common import (ENGINES_DIR, FinalizeError, finite, holds_machine_path, rel, same_file, scrub, skill_library,
    HERE)
from finalize_deliver import (manifest_folders, threemf_manifest_files)


def own_sources(build):
    """The generator's own files among the build's sources (not the skill's libraries, here or at
    the place a moved project recorded them, finalize_common.skill_library)."""
    lib = {os.path.normcase(os.path.abspath(d)) for d in (HERE, ENGINES_DIR)}
    return [s for s in build.get("sources") or []
            if os.path.normcase(os.path.dirname(os.path.abspath(s))) not in lib and not skill_library(s)]

BUNDLE_OWN = ("params.json", "printers.json", "REPRODUCE.md", "verification.json", "build.json")   # build.json: rebuilt

RUN_ENGINES = ("openscad", "python", "blender")                  # what `build.py run` builds again


def made_by_run(b):
    """Whether a build JSON is a `build.py run` (built again by REPRODUCE.md) rather than a
    `record` (whose STLs came from Fusion or a live Blender, which a script cannot run). Since
    0.7.0 the JSON says so in `command`; `record --engine blender` names an engine `run` knows,
    so the engine alone cannot tell. An older JSON: a run reports its engine_info, a record none."""
    if b.get("command") in ("run", "record"):
        return b["command"] == "run" and b.get("engine") in RUN_ENGINES
    return b.get("engine") in RUN_ENGINES and isinstance(b.get("engine_info"), dict)

NOT_TEXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".mp4", ".mov",
            ".3mf")                                              # pictures and zips: no path a script reads is in them


def bundle_path(src):
    """Where a source goes in the bundle: its path relative to the working folder (the folder the
    build ran in), so an import, an include or a loaded file still finds it; None outside it."""
    try:
        r = os.path.relpath(os.path.abspath(src))
    except ValueError:                                   # another drive on Windows
        return None
    if r == ".." or r.startswith(".." + os.sep):
        return None
    if os.path.lexists(src):                             # a link inside the folder to a file outside it is outside:
        try:                                             # copying it would carry what it points to
            real = os.path.relpath(os.path.realpath(src), os.path.realpath(os.curdir))
        except ValueError:
            return None
        if real == ".." or real.startswith(".." + os.sep):
            return None
    return r.replace(os.sep, "/")


def json_object(path):
    """A JSON object from a file, or {}: a missing or malformed report is the verdict's to judge."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def bundle_contents(verify, build, deliver=None, joints=None):
    """What a bundle carries besides the generator, params.json and printers.json, so that the
    verdict can be reached again from the bundle alone: every report _verify names, and each
    file a report read by its sha256 that REPRODUCE.md does not build again (a measured user
    file, a recorded proxy's STL with its build manifest; never a part); a proxy's generator and
    params file (a `build.py run --proxy` proxy tied to them, joints[i].proxy_build "tied" in the
    report, is built again; a recorded one is carried with its build JSON); each seen image and
    its sidecar; the test print photos; and with --deliver
    every delivered STL and 3MF with the manifest finalize compares it with. Returns (files:
    {place: (path, what)}, missing: {place: what}, proxies: {build JSON place: {joint, out: the
    folder it is built into, writes: the places it writes, command: the `build.py run --proxy`
    command that builds it again}}, outside: the paths outside the project folder). A
    place is the path relative to the project folder; a 3MF's manifest found only elsewhere
    (out/, which a rebuild rewrites) goes beside the 3MF."""
    c = _Contents(build)
    _carry_proxies(c, verify, joints)
    _carry_reports(c, verify)
    _carry_delivery(c, deliver, build)
    return c.files, c.missing, c.proxies, c.outside


class _Contents:
    """What bundle_contents collects: files carried, missing, proxies built again, paths outside."""

    def __init__(self, build):
        self.built = {os.path.normcase(os.path.abspath(p["stl"])) for p in build.get("parts") or []
                      if isinstance(p, dict) and isinstance(p.get("stl"), str)}
        self.files, self.missing, self.proxies, self.outside = {}, {}, {}, []

    def carry(self, path, what, place=None):
        """Carry the file at its place (True), or note it missing or outside (False)."""
        if not (isinstance(path, str) and path.strip()):
            return False
        own = bundle_path(path)
        if own is None:
            if path not in self.outside:
                self.outside.append(path)
            return False
        place = place or own
        if not os.path.isfile(path):
            self.missing.setdefault(place, what)
            return False
        self.files.setdefault(place, (path, what))
        return True

    def hashed(self, path, what):
        """A file a report read by its sha256: a part of this build is rebuilt; any other file is
        carried, with its build manifest when it has one (fit.py and the proxy check read it)."""
        if not isinstance(path, str) or os.path.normcase(os.path.abspath(path)) in self.built:
            return
        if self.carry(path, what) and os.path.isfile(validate.manifest_path(path)):
            self.carry(validate.manifest_path(path), f"build manifest of {bundle_path(path)}")

    def proxy(self, path, joint, tied):
        """A proxy's build: one `build.py run --proxy` made is made again by REPRODUCE.md, as the
        parts are (built again, it shows the verdict is reached again, as the parts do): its
        generator and params file are carried, its STLs, manifests and JSON are not. Any other
        (a recorded proxy) is carried as it is, with its inputs."""
        b = json_object(path) if isinstance(path, str) and os.path.isfile(path) else {}
        if b.get("schema") != "3dprint-scout.build/1":
            self.carry(path, f"proxy build of {joint}")          # missing or malformed: as the verdict sees it
            return
        srcs = [s for s in b["sources"] if isinstance(s, str)] if isinstance(b.get("sources"), list) else []
        for s in own_sources({"sources": srcs}):
            self.carry(s, f"proxy generator of {joint}")
        self.carry(b.get("params"), f"params file of the proxy of {joint}")
        stls = ([p for p in b["parts"] if isinstance(p, dict) and isinstance(p.get("stl"), str)]
                if isinstance(b.get("parts"), list) else [])
        src, prm, place = b.get("source"), b.get("params"), bundle_path(path)
        out = bundle_path(os.path.dirname(stls[0]["stl"]) or ".") if stls else None
        if not (b.get("proxy") is True and made_by_run(b) and isinstance(src, str) and bundle_path(src)
                and isinstance(prm, str) and bundle_path(prm) and out and place):
            self.carry(path, f"proxy build of {joint}")
            for p in stls:
                self.hashed(p["stl"], f"proxy STL of {joint}")
        elif tied:
            writes = [w for w in (bundle_path(p["stl"]) for p in stls) if w]
            writes += [w + ".manifest.json" for w in writes]
            if b["engine"] == "blender":                         # bb.main saves <out>/<generator>.blend
                stem = posixpath.splitext(posixpath.basename(bundle_path(src)))[0]
                writes.append(posixpath.normpath(posixpath.join(out, stem + ".blend")))
            self.proxies.setdefault(place, {"joint": joint, "out": out, "writes": writes, "command": (
                f'python3 "$SKILL_DIR/scripts/build.py" run {shlex.quote(bundle_path(src))} --params '
                f"{shlex.quote(bundle_path(prm))} --proxy {shlex.quote(','.join(str(p.get('name')) for p in stls))} "
                f"--engine {shlex.quote(b['engine'])} --out {shlex.quote(out)} > {shlex.quote(place)}")})   # as built
            self.built.update(os.path.normcase(os.path.abspath(p["stl"])) for p in stls)
        else:                                                    # built again it would be another proxy
            for p in stls:
                self.hashed(p["stl"], f"proxy STL of {joint}")
            if place not in self.proxies:                        # another joint's fit ties it: built again
                self.missing.setdefault(place, f"proxy build of {joint}, left out: a build.py run JSON is made again, "
                                               "not carried, and this proxy was not built from its params file as it "
                                               "is now (build the proxy and fit it again)")


def _carry_proxies(c, verify, joints):
    """The proxies first, tied ones first: an STL built again is not carried."""
    states = [e.get("proxy_build") for e in joints or []]
    declared = verify.get("joints") or []
    tied = [i < len(states) and states[i] == "tied" for i in range(len(declared))]
    for i in sorted(range(len(declared)), key=lambda i: not tied[i]):
        j = declared[i]
        if j.get("proxy") and isinstance(j.get("proxy_build"), str):
            c.proxy(j["proxy_build"], f"joint '{j.get('name') or j.get('report')}'", tied[i])


def _carry_reports(c, verify):
    """Every report _verify names, and what each read: fitted STLs, measured files, images, photos."""
    for j in verify.get("joints") or []:
        joint = f"joint '{j.get('name') or j.get('report')}'"
        if c.carry(j.get("report"), f"fit report of {joint}"):
            sides = json_object(j["report"]).get("parts")
            for k in ("a", "b"):
                side = sides.get(k) if isinstance(sides, dict) else None
                if isinstance(side, dict):
                    c.hashed(side.get("path"), f"STL fitted in {joint}")
    for s in verify.get("strength") or []:
        c.carry(s.get("report"), f"strength report of member '{s.get('name') or s.get('report')}'")
    for m in verify.get("measurements") or []:
        what = f"measurement '{m.get('name') or m.get('report')}'"
        if c.carry(m.get("report"), f"report of {what}"):
            c.hashed(json_object(m["report"]).get("file"), f"file read by {what}")
    for e in verify.get("seen") or []:
        what = f"seen '{e.get('name') or e.get('image')}'"
        if c.carry(e.get("image"), f"image of {what}"):
            c.carry(e["image"] + ".json", f"sidecar of the image of {what}")
    for t in verify.get("test_prints") or []:
        for p in t["photos"] if isinstance(t.get("photos"), list) else []:
            c.carry(p, f"photo of test print '{t.get('name')}'")


def _carry_delivery(c, deliver, build):
    """Every delivered STL and 3MF, each 3MF with the manifest check_delivered judged it by."""
    if deliver and bundle_path(deliver) is None:
        c.outside.append(deliver)
    elif deliver and os.path.isdir(deliver):
        manifests = threemf_manifest_files(manifest_folders(deliver, build))
        for fn in sorted(os.listdir(deliver)):                 # the files check_delivered judges
            path = os.path.join(deliver, fn)
            if not (os.path.isfile(path) and fn.lower().endswith((".stl", ".3mf"))):
                continue
            c.carry(path, "delivered file")
            if not fn.lower().endswith(".3mf") or bundle_path(path) is None:
                continue
            place = bundle_path(path)
            chosen = manifests.get(validate.file_sha256(path))   # the one check_delivered judged it by
            if chosen:
                pick, mine = chosen[0], bundle_path(chosen[0])
                c.carry(pick, f"manifest of {place}" + ("" if mine == place + ".manifest.json" else f", found at {mine}"),
                        place=place + ".manifest.json")     # beside its 3MF: out/ is written again by the rebuild


def build_field_problems(build):
    """The build JSON's fields the bundle reads that are not as build.py writes them."""
    bad = [k for k in ("source", "threemf", "blend") if build.get(k) is not None and not isinstance(build[k], str)]
    if not (isinstance(build.get("engine"), str) and build["engine"].strip()):
        bad.append("engine")
    srcs = build.get("sources")
    if srcs is not None and not (isinstance(srcs, list) and all(isinstance(s, str) for s in srcs)):
        bad.append("sources")
    parts = build.get("parts")
    if not (isinstance(parts, list) and all(isinstance(p, dict) and isinstance(p.get("name"), str)
                                            and isinstance(p.get("stl"), str) for p in parts)):
        bad.append("parts")
    vs = build.get("validate_settings")
    if vs is not None and not isinstance(vs, dict):
        bad.append("validate_settings")
    elif vs:
        bad += [f"validate_settings.{k}" for k in ("printer", "printer_id", "tools")
                if vs.get(k) is not None and not isinstance(vs[k], str)]
        bad += [f"validate_settings.{k}" for k in ("tol", "overhang_angle", "min_wall")
                if vs.get(k) is not None and not finite(vs[k])]
        if "wall_check" in vs and not isinstance(vs["wall_check"], bool):
            bad.append("validate_settings.wall_check")
    return bad


def rebuild_blockers(build, specs, parts, drift, metadata_drift, material_lines, settings=None):
    """Why a bundle could not reach this verdict again: REPRODUCE.md builds the parts again from
    the project as it is now and with the build's own settings, so every reason that compares the
    saved build with the project now (an STL or R3 that is not the build's, a part it did not
    make, the grouping or a material changed since, printers.json edited, or gone while the
    build's object checks were made with it) would be gone there, and so would a setting given to
    finalize that differs from the build's. Returns (reasons to build again, settings given here
    that differ from the build's)."""
    again, overrides = [], []
    for p in parts:
        r3 = (p.get("checks") or {}).get("R3")
        if p.get("state") == "FAIL" and not p.get("sha256"):
            again.append(f"{p.get('name')}: STL {p.get('stl')} not found")
        elif not p.get("same_as_build"):
            again.append(f"{p.get('name')}: {p.get('stl')} is not the STL the build judged")
        elif r3 != "PASS":
            again.append(f"{p.get('name')} R3 {r3 or 'not checked'}")
    built = {p.get("name") for p in build.get("parts") or [] if isinstance(p, dict)}
    again += [f"{n}: in _parts but not built" for n in specs if n not in built]
    again += list(metadata_drift) + list(material_lines)
    for d in drift:
        (again if d.endswith("changed since the build") else overrides).append(d)
    vs = build.get("validate_settings") if isinstance(build.get("validate_settings"), dict) else {}
    pr = getattr(settings, "printer", None)
    if (vs.get("printer_sha256") and isinstance(pr, str) and not os.path.isfile(pr)
            and any(isinstance(o, dict) and o.get("checks") for o in build.get("objects") or [])):
        again.append(f"{rel(pr)} is gone since the build, which judged its objects with it")
    return again, overrides


def created_root(folder):
    """The outermost folder that os.makedirs(folder) creates: what a failed write takes away."""
    top = os.path.abspath(folder)
    while os.path.dirname(top) != top and not os.path.exists(os.path.dirname(top)):
        top = os.path.dirname(top)
    return top


def not_utf8(names):
    """The names that cannot be written as UTF-8 text (a file name in another encoding, which
    Python reads as surrogates), each shown with the bad bytes escaped."""
    out = []
    for n in names:
        try:
            n.encode("utf-8")
        except UnicodeEncodeError:
            out.append(n.encode("utf-8", "backslashreplace").decode("utf-8"))
    return out


def write_bundle(folder, build, params_path, settings, report, verify=None, deliver=None, given=None,
                 stale=((), ())):
    """The bundle (module docstring, --bundle). Everything that can refuse it, or make writing it
    fail, is checked before the folder is made; if writing still fails, the folders this run
    made are taken away again and the error is finalize's. `given` holds the settings given to
    finalize itself, `stale` what rebuild_blockers found."""
    if os.path.lexists(folder):
        raise FinalizeError(f"{folder} exists; the bundle goes into a new folder (never overwrites)")
    c = {"deliver_found": bool(deliver) and os.path.isdir(deliver)}  # before the bundle folder, which may be inside it
    _bundle_preflight(c, build, params_path, settings, stale)
    _rebuild_plan(c, build, given)
    inputs, missing, proxies = _bundle_inputs(c, build, params_path, verify, deliver, report)
    _check_rewrites(c, build, inputs, missing, proxies)
    delivered = bundle_path(deliver) if deliver else None    # named even when missing: the rerun says so too
    reproduce_text = _reproduce_text(c, delivered, inputs, missing, proxies)
    return _write_files(folder, c, params_path, report, delivered, inputs, missing, proxies, reproduce_text)


def _bundle_preflight(c, build, params_path, settings, stale):
    """What refuses the bundle before anything is read: the build JSON, its sources, a build that is
    no longer this project's, other settings, and files outside the project or holding machine paths."""
    bad = build_field_problems(build)
    if bad:
        raise FinalizeError(f"the build JSON's {', '.join(bad)} {'is' if len(bad) == 1 else 'are'} not as build.py "
                            "writes it: build again and save its JSON before bundling")
    srcs = own_sources(build)
    gone = [s for s in srcs if not os.path.isfile(s)]
    if gone:
        raise FinalizeError(f"{', '.join(rel(s) for s in gone)}: a source the build hashed is gone or not a file, and "
                            "the bundle carries every source: build again from the sources as they are now, save that "
                            "build's JSON and bundle again")
    again, overrides = stale
    if again:
        raise FinalizeError("REPRODUCE.md builds the parts again from the project as it is now, so a bundle holds only "
                            f"a build that is still this project's, and this one is not ({'; '.join(again)}): build "
                            "again, save that build's JSON and bundle again")
    if overrides:
        raise FinalizeError(f"finalize was given settings other than the build's ({'; '.join(overrides)}): the bundle "
                            "builds again with the build's own settings, so bundle without those options (or build "
                            "again with them and save that build's JSON)")
    if not os.path.isfile(params_path):
        raise FinalizeError(f"{rel(params_path)} is not a file")
    printer = settings.printer if isinstance(settings.printer, str) and settings.printer.strip() else None
    printers = printer if printer and os.path.isfile(printer) else None
    if printer and not printers and os.path.exists(printer):
        raise FinalizeError(f"{rel(printer)} (the printers.json the build used) is not a file")
    files = [*srcs, params_path] + ([printers] if printers else [])
    far_cfg = [rel(f) for f in [params_path] + ([printer] if printer else []) if bundle_path(f) is None]
    if far_cfg:                                          # a link to one outside counts as outside (copied, it is carried)
        raise FinalizeError(f"{', '.join(far_cfg)} is outside the project folder (the folder the build ran in): keep "
                            "params.json and printers.json in the project's .3dprint/ folder before bundling")
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
    parts = build.get("parts") or []
    threemf = build.get("threemf")
    far_out = [p["stl"] for p in parts if bundle_path(p["stl"]) is None] + (
        [threemf] if threemf and bundle_path(threemf) is None else [])
    if far_out:                                          # the reports would name them where the bundle has nothing
        raise FinalizeError(f"{', '.join(rel(p) for p in far_out)} is outside the project folder (the folder the build "
                            "ran in): REPRODUCE.md builds the parts again inside the bundle, where the reports would "
                            "not find them; build into a folder of the project (--out out), fit and measure again, and "
                            "bundle again")
    c.update(srcs=srcs, printer=printer, printers=printers, places=places, reserved=reserved, parts=parts,
             threemf=threemf)


def _rebuild_plan(c, build, given):
    """The rebuild, as the build was made: its engine, its core 3MF (or none), its own settings;
    and the settings the re-check gives finalize."""
    srcs, parts, threemf, printer, printers = c["srcs"], c["parts"], c["threemf"], c["printer"], c["printers"]
    by_run = made_by_run(build)                           # built again by REPRODUCE.md, or recorded STLs exported again
    main_src = build.get("source") or (srcs[0] if srcs else None)
    main = (bundle_path(main_src) or os.path.basename(main_src)) if main_src else "model"
    part_places = [bundle_path(p["stl"]) for p in parts]
    dirs = {posixpath.dirname(p) or "." for p in part_places}
    tm_place = bundle_path(threemf) if threemf else None
    if tm_place:
        out = posixpath.dirname(tm_place) or "."         # the core 3MF is written in --out
        if by_run and dirs and dirs != {out}:
            raise FinalizeError(f"the core 3MF {tm_place} is not in the folder the build wrote its parts to, so "
                                "REPRODUCE.md cannot write it again where it was: build again and save that "
                                "build's JSON")
        threemf_flags = ["--3mf", posixpath.basename(tm_place)]
    else:
        notes = [str(x) for k in ("errors", "warnings") if isinstance(build.get(k), list) for x in build[k]]
        if any("core 3MF not written" in n for n in notes):
            raise FinalizeError("the build JSON records no core 3MF and says one could not be written, so it does not "
                                "tell whether one was asked for: build again and save that build's JSON")
        out = dirs.pop() if len(dirs) == 1 else "out"
        threemf_flags = ["--no-3mf"]
    printer_place = ("printers.json" if printers else bundle_path(printer)) if printer else None
    vs = build.get("validate_settings") or {}
    rebuild = ["--printer", printer_place] if printer_place else []     # the printer finalize used is the build's
    for f in ("printer_id", "tools", "tol", "overhang_angle", "min_wall"):
        if vs.get(f) is not None:
            rebuild += [f"--{f.replace('_', '-')}", str(vs[f])]
    if vs.get("wall_check") is False:
        rebuild.append("--no-wall-check")
    given = given or {}
    recheck = ["--printer", printer_place] if given.get("printer") is not None and printer_place else []
    for f in ("printer_id", "tools", "tol", "overhang_angle", "min_wall"):
        if given.get(f) is not None:
            recheck += [f"--{f.replace('_', '-')}", str(given[f])]
    if given.get("wall_check") is False:
        recheck.append("--no-wall-check")
    c.update(engine=build["engine"], by_run=by_run, main=main, part_places=part_places, tm_place=tm_place, out=out,
             threemf_flags=threemf_flags, printer_place=printer_place, rebuild=rebuild, recheck=recheck)


def _bundle_inputs(c, build, params_path, verify, deliver, report):
    """The evidence files the verdict reads ({place: (source, what)}), those named but missing, and
    the proxies built again; refused where one would take a place the bundle writes itself."""
    reserved, places = c["reserved"], c["places"]
    inputs, missing, proxies, far = bundle_contents(verify or {}, build, deliver, report.get("joints"))
    taken = sorted(place for place in missing if place.lower() in reserved)
    if taken:                         # REPRODUCE.md would make it, and the verdict would read that, not "missing"
        raise FinalizeError(f"{', '.join(taken)} would take the place of a file the bundle writes itself; rename it")
    if far:
        raise FinalizeError(f"{', '.join(rel(p) for p in far)} is outside the project folder (the folder the build ran "
                            "in); the bundle keeps every file at its place relative to that folder, so that "
                            "REPRODUCE.md runs as written inside it: move it into the project folder and name it there")
    for place, (src, _what) in list(inputs.items()):
        if place in places.values() or (place.lower() in reserved and (same_file(src, params_path)
                                                                     or same_file(src, c["printers"]))):
            del inputs[place]                                    # already in the bundle (a source, params.json)
        elif place.lower() in reserved:
            raise FinalizeError(f"{place} would take the place of a file the bundle writes itself; rename it")
    if c["printer"] and not c["printers"]:                       # named, not found: the re-check says so too
        if c["printer_place"].lower() in reserved - {"printers.json"}:
            raise FinalizeError(f"{c['printer_place']} would take the place of a file the bundle writes itself; "
                                "rename it")
        missing.setdefault(c["printer_place"], "the printers.json the build used")
    return inputs, missing, proxies


def _check_rewrites(c, build, inputs, missing, proxies):
    """What the commands of REPRODUCE.md write: nothing carried may be one of them (the rebuild would
    replace what was judged), no two builds may write the same file, and no carried text file may
    hold a path of this machine."""
    reserved, tm_place = c["reserved"], c["tm_place"]
    writes = {"build.json": ("build.json", "the build JSON")}
    names = [p["name"] for p in c["parts"]]
    for n, place in zip(names, c["part_places"]):
        writes.setdefault(place.lower(), (place, f"the part {n}"))
        writes.setdefault((place + ".manifest.json").lower(), (place + ".manifest.json", f"the build manifest of {n}"))
    if tm_place:
        writes.setdefault(tm_place.lower(), (tm_place, "the core 3MF"))
        writes.setdefault((tm_place + ".manifest.json").lower(),
                          (tm_place + ".manifest.json", "the core 3MF's manifest"))
    if c["engine"] == "blender":                                  # bb.main saves <out>/<generator>.blend
        stem = posixpath.splitext(posixpath.basename(c["main"]))[0]
        for blend in [posixpath.normpath(posixpath.join(c["out"], stem + ".blend"))] + (
                [bundle_path(build["blend"])] if build.get("blend") and bundle_path(build["blend"]) else []):
            writes.setdefault(blend.lower(), (blend, "the .blend"))
    for place, px in sorted(proxies.items()):
        own = [n for n in (place, px["out"]) if n.lower() in reserved]
        if own:
            raise FinalizeError(f"the proxy build of {px['joint']} is saved as or built into {', '.join(own)}, a file "
                                "the bundle writes itself: build the proxy into a folder of its own and save its JSON "
                                "under another name")
        hits = [f"{w} ({writes[w.lower()][1]})" for w in [place] + px["writes"] if w.lower() in writes]
        if hits:
            raise FinalizeError(f"the proxy of {px['joint']} is built again into {', '.join(hits)}, which another "
                                "build in REPRODUCE.md writes too: build the proxy into a folder of its own and save "
                                "its JSON under another name")
        for w in [place] + px["writes"]:
            writes[w.lower()] = (w, f"the proxy of {px['joint']}")
    rewritten = [f"{place} ({what}; REPRODUCE.md writes {writes[place.lower()][1]} there)"
                 for place, what in sorted([(p, w) for p, (_s, w) in inputs.items()] + list(missing.items())
                                           + [(p, "a source") for p in c["places"].values()])
                 if place.lower() in writes]
    if rewritten:
        raise FinalizeError(f"{'; '.join(rewritten)}: the commands in REPRODUCE.md write this again, so the bundle "
                            "could not keep what was judged; deliver into a folder of its own, and keep evidence out "
                            "of the files a build writes (copy it and name the copy)")
    leaking = [place for place, (src, _what) in inputs.items()
               if not src.lower().endswith(NOT_TEXT) and holds_machine_path(src)]
    if leaking:
        raise FinalizeError(f"{', '.join(leaking)} holds a path of this machine: write it again with paths relative "
                            "to the project folder (fit.py, measure.py, strength.py --from-build, preview.py and "
                            "render.py record the paths they are given) before bundling")


def _reproduce_text(c, delivered, inputs, missing, proxies):
    """REPRODUCE.md: the prose is scrubbed, the commands (relative paths, each quoted) are not."""
    q = shlex.quote
    engine, main, out = c["engine"], c["main"], c["out"]
    tail = " ".join(q(w) for w in c["threemf_flags"] + c["rebuild"])
    lines = [("# Reproduce", False), ("", False),
             (f"Engine: {engine}. Generator: `{main}`. Parameters: `params.json`. Run from this folder, with "
              "`SKILL_DIR` the 3dprint-scout skill folder.", False), ("", False)]
    if c["by_run"]:
        lines += [("```bash", False),
                  (f'python3 "$SKILL_DIR/scripts/build.py" run {q(main)} --engine {q(engine)} --params params.json '
                   f"--out {q(out)} {tail} > build.json", True), ("```", False), ("", False)]
    else:
        recorded = " ".join(q(p) for p in c["part_places"]) or f"{q(out)}/<part>.stl ..."
        lines += [(f"This build was recorded (`build.py record`, engine {engine}): run the generator in {engine}, "
                   f"export one STL per part named after the part into `{out}/`, then:", False), ("", False),
                  ("```bash", False),
                  (f'python3 "$SKILL_DIR/scripts/build.py" record {recorded} --source '
                   f"{' '.join(q(c['places'][s]) for s in c['srcs']) or q(main)} --params params.json "
                   f"--engine {q(engine)} --out {q(out)} {tail} > build.json", True), ("```", False), ("", False)]
    if proxies:
        lines += [("Then the proxies the fit reports measured, built again from their own generators and params "
                   "files as the parts are (a fit report holds while each STL is the one it measured):", False),
                  ("", False), ("```bash", False)]
        lines += [(px["command"], True) for _place, px in sorted(proxies.items())] + [("```", False), ("", False)]
    lines += [("Then re-check" + (f", with the delivered files in `{delivered}`" if delivered else "") + ":", False),
              ("", False), ("```bash", False),
              ('python3 "$SKILL_DIR/scripts/finalize.py" --build build.json --params params.json'
               + "".join(f" {q(w)}" for w in c["recheck"]) + (f" --deliver {q(delivered)}" if delivered else ""), True),
              ("```", False), ("", False),
              ("`verification.json` is the report this delivery was made with: what was verified, and what was not.",
               False), ("", False)]
    if inputs:
        lines += [("## The evidence", False), ("", False),
                  ("Besides the generator, `params.json` and `printers.json`, the files the verdict reads, each at its "
                   "place in the project folder. The parts, and the proxies built again, are not here: the commands "
                   "above make them, and a report holds while each STL it read is the same (sha256).", False),
                  ("", False)]
        lines += [(f"- `{place}`: {inputs[place][1]}", False) for place in sorted(inputs)] + [("", False)]
    if missing:
        lines += [("## Not in this bundle", False), ("", False),
                  ("Named, but not here: not there when the bundle was made, unless the line says why. A re-check "
                   "here finds them missing:", False), ("", False)]
        lines += [(f"- `{place}`: {missing[place]}", False) for place in sorted(missing)] + [("", False)]
    return "\n".join(text if command else scrub(text) for text, command in lines)


def _write_files(folder, c, params_path, report, delivered, inputs, missing, proxies, reproduce_text):
    """Copy the files, make the folders REPRODUCE.md writes into, write REPRODUCE.md and
    verification.json; never a half-written bundle. Returns the files written."""
    srcs, places, printers = c["srcs"], c["places"], c["printers"]
    copies = ([(src, places[src]) for src in srcs] + [(params_path, "params.json")]
              + ([(printers, "printers.json")] if printers else []) + [(inputs[p][0], p) for p in sorted(inputs)])
    made = ([delivered] if delivered and c["deliver_found"] else []) + [posixpath.dirname(p) for p in proxies]
    written = [rel(os.path.join(folder, *place.split("/"))) for _src, place in copies]
    written += [rel(os.path.join(folder, "REPRODUCE.md")), rel(os.path.join(folder, "verification.json"))]
    final = dict(report, bundle=written, bundle_missing=[f"{place}: {missing[place]}" for place in sorted(missing)])
    verification_text = scrub(json.dumps(final, indent=2, ensure_ascii=False))
    bad = not_utf8([place for _src, place in copies] + list(missing) + list(proxies) + made) or not_utf8([folder])
    if bad:
        raise FinalizeError(f"{', '.join(bad)}: a name the bundle would write is not UTF-8 text (a file name in "
                            "another encoding): rename it before bundling")
    for text in (reproduce_text, verification_text):
        bad = not_utf8([text])
        if bad:
            at = re.search(r"\\ud[89a-f][0-9a-f]{2}", bad[0])
            raise FinalizeError("the report holds text that is not UTF-8 (near "
                                f"{bad[0][max(0, at.start() - 30):at.end() + 10]!r}): write it again in UTF-8 before "
                                "bundling")
    top = created_root(folder)
    try:
        os.makedirs(folder)
        for src, place in copies:                                 # copied, never moved
            dst = os.path.join(folder, *place.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
        for place in made:                                        # where REPRODUCE.md writes and reads
            if place:
                os.makedirs(os.path.join(folder, *place.split("/")), exist_ok=True)
        with open(os.path.join(folder, "REPRODUCE.md"), "w", encoding="utf-8") as f:
            f.write(reproduce_text)
        with open(os.path.join(folder, "verification.json"), "w", encoding="utf-8") as f:
            f.write(verification_text)
    except Exception as exc:                                      # never a half-written bundle
        shutil.rmtree(top, ignore_errors=True)
        raise FinalizeError(f"writing the bundle failed ({exc}); what this run had written of {rel(folder)} was "
                            "taken away again") from exc
    report.update(bundle=final["bundle"], bundle_missing=final["bundle_missing"])
    return written
