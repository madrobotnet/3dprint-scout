"""finalize.py --deliver: the delivered STLs and 3MFs, and each Bambu project's filaments and preset."""
from __future__ import annotations

import json
import os
import validate

from finalize_common import (MANIFEST_3MF, effective_material, rel)


def threemf_manifest_files(folders):
    """Every 3MF manifest in the folders, walked in a fixed order: {artifact sha256: (its file,
    the manifest)}. A sound manifest found later takes the place of an earlier one for the same
    3MF; one whose `parts` is not a map of part names to sha256 strings is {"_malformed": its
    file name}, and never takes the place of a sound one."""
    found = {}
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for root, dirs, files in os.walk(folder):
            dirs.sort()
            for fn in sorted(files):
                if fn.endswith(".3mf.manifest.json"):
                    path = os.path.join(root, fn)
                    try:
                        with open(path, encoding="utf-8") as f:
                            m = json.load(f)
                    except (OSError, ValueError):
                        continue
                    if not (isinstance(m, dict) and m.get("schema") == MANIFEST_3MF
                            and isinstance(m.get("artifact_sha256"), str) and m["artifact_sha256"]):
                        continue
                    sha, parts = m["artifact_sha256"], m.get("parts")
                    if isinstance(parts, dict) and parts and all(isinstance(k, str) and isinstance(v, str)
                                                                 for k, v in parts.items()):
                        found[sha] = (path, m)
                    elif sha not in found:              # never in place of a sound one
                        found[sha] = (path, {"_malformed": fn})
    return found


def manifest_folders(deliver, build):
    """Where a delivered 3MF's manifest is looked for, in this order: the delivery folder, then
    the folders the build wrote its STLs and core 3MF to (sorted, so the choice is the same in
    the report and in the bundle)."""
    dirs = {os.path.dirname(p["stl"]) for p in build.get("parts") or []
            if isinstance(p, dict) and isinstance(p.get("stl"), str)}
    dirs |= {os.path.dirname(build["threemf"]) if isinstance(build.get("threemf"), str) else ""}
    return [deliver, *sorted(dirs)]


def threemf_manifests(folders):
    """{artifact sha256: manifest}, as threemf_manifest_files chooses them."""
    return {sha: m for sha, (_path, m) in threemf_manifest_files(folders).items()}


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
    manifests = threemf_manifests(manifest_folders(deliver, build))
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


def _inherited_material(key, settings, f, strength):
    """(material key, taken from the parent preset, why not) for one part's filament in a Bambu
    project's manifest. A filament preset finalize cannot name (a user's own "My PLA") takes the
    material of the system preset it inherits from (the manifest's `inherits`, bambu3mf.py 0.8.2),
    but only when the slot's `filament_type` is that material's type: a preset saved from PLA and
    switched to PETG is not PLA. Otherwise the key stays as it was (None: not checked), with the
    reason when a parent was named but its type does not agree."""
    parent = f.get("inherits") if isinstance(f.get("inherits"), str) else None
    if key is not None or not settings or not parent:
        return key, False, None
    pkey = strength.material_of_filament(parent)
    if pkey is None:
        return key, False, None
    ftype = f.get("filament_type") if isinstance(f.get("filament_type"), str) else ""
    want = strength.material_type(pkey)
    if ftype.strip().upper() == want:
        return pkey, True, None
    return key, False, (f"{json.dumps(settings)} is not a filament of a known material; it inherits "
                        f"{json.dumps(parent)} ({pkey}), but "
                        + (f"its filament type is {ftype.strip()}, not {want}" if ftype.strip() else
                           "the project records no filament type for its slot"))


def check_delivered_print(projects, part_names, params, specs):
    """The slicer settings a delivered Bambu project carries (its manifest's `filaments` and
    `process`, written by bambu3mf.py) against what params.json declares. Each part's filament
    (strength.material_of_filament of its settings name; for a preset it cannot name, the
    material of the preset it inherits from when the slot's filament_type is that material's
    type, recorded as "material_from": "inherits") must be the part's material: another
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
            report = {"slot": f.get("slot"), "settings": settings, "material": key}
            key, inherited, why = _inherited_material(key, settings, f, strength)
            if inherited:
                report.update(material=key, material_from="inherits", inherits=f["inherits"])
            entry["filaments"][n] = report
            printed = f"{settings} ({key}" + (f", inherited from {f['inherits']})" if inherited else ")")
            ev = evidence.setdefault(n, {"notver": [], "assumed": []})
            if key is None:
                why = why or (f"{json.dumps(settings)} is not a filament of a known material" if settings else
                              "the project names no filament for its slot")
                lines.append(f"{rel(path)}: the slicer's filament for {n} is not checked ({why}); set it to "
                             f"{eff or 'the part material'} in the slicer")
                ev["assumed"].append(f"the slicer's filament for {n} is not checked")
            elif eff is None:
                lines.append(f"{rel(path)}: {n} is printed in {printed}, and no material is declared for {n} "
                             f"(_material, or _parts.{n}.material) to compare it with")
                ev["notver"].append(f"no material is declared for {n} to compare the print file's filament with")
            elif key != eff:
                lines.append(f"{rel(path)}: {n} is printed in {printed}, the part is {eff}: choose the "
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
