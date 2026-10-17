#!/usr/bin/env python3
"""
build.py - run a generator script with OpenSCAD or Python (manifold3d), record a
freshness manifest for every STL, write a core 3MF, and validate every part.

Subcommands (all print ONE JSON document to stdout):

  detect                       Phase 0 probe: engines, OpenSCAD backend, optional libs.
  run SOURCE [options]         Build all parts, write manifests + 3MF, validate.
  record STL... --source F...  Write manifests for parts built elsewhere (Fusion), then validate.

Parameters live in a JSON file. Keys that start with "_" are metadata and are not
passed to the engine. "_parts" names the parts and what each should look like:

  {"_parts": {"body": {"expect": [60, 40, 25]}, "lid": {"expect": [60, 40, 4]}},
   "wall": 2.0, "lid_clearance": 0.2}

"expect" is the size from the dimension table (design intent), never a measured box.
Parts can be grouped into one object with "object" and "role" ("fused" or "free"),
see assembly.py; every part of an object is modelled in the same frame, so the STLs
already hold the assembled positions.

OpenSCAD receives every other key as -D name=value, plus -D part="<name>" per part.
A Python generator must define build(params) -> {part_name: manifold3d.Manifold}.
`record` takes STLs built elsewhere (Fusion): one STL per part, named after the part.

Every STL is checked for sanity (G4) before anything is recorded: a 0-byte, truncated or
NaN mesh gets no manifest, is left out of the 3MF and is listed in "errors" with
"artifact_sane": false on its part; the other parts are still recorded and validated. The
validator's own errors and warnings are repeated in the top-level "errors" / "warnings".
A missing printers.json is a warning (D2 stays UNVERIFIED), not a failure.

`--out` (default out/) is the build's working folder: every run rewrites its STLs,
manifests and <source>.3mf. Deliverables are copied elsewhere as new files (SKILL.md).
`run --only latch,keeper` builds only those parts: a few-gram test print of a mechanism
before the whole part (SKILL.md, Phase 4). Use a separate --out so the full build's
artifacts stay fresh.

Output (one JSON document, schema 3dprint-scout.build/1; references/parts.md has the
full description):
  gate            PASS | FAIL | INCOMPLETE over every part and object
  R4              PASS when the generator ran and every artifact is sane
  parts[]         name, stl, artifact_sane, object, role, rotation_deg, engine_warnings,
                  validate (the validate.py document for that part: files[0].checks,
                  files[0].metrics), assembly (A1 / A2 for a part in a group)
  objects[]       name, parts, gate, checks (D2, P1, P2 of the whole object when it has
                  several parts), metrics, rotation_deg
  sources         files hashed into the manifests; pass the same list to validate.py
  threemf         the core 3MF written in --out
  warnings, errors  everything worth reading, lifted from every part and object

Exit codes: 0 = ran (read "gate"), 1 = build or usage error.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import math
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import assembly  # noqa: E402
import validate  # noqa: E402
import threemf   # noqa: E402

SCHEMA = "3dprint-scout.build/1"


# --------------------------------------------------------------------------- #
# Engine discovery
# --------------------------------------------------------------------------- #
def find_openscad() -> str | None:
    """PATH first, then the usual install folders (Windows/macOS installers skip PATH)."""
    env = os.environ.get("OPENSCAD")
    if env and os.path.isfile(env):
        return env
    for name in ("openscad.com", "openscad"):          # .com is the console build on Windows
        hit = shutil.which(name)
        if hit:
            return hit
    candidates = []
    if os.name == "nt":
        for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if root:
                candidates += [os.path.join(root, "OpenSCAD", n) for n in ("openscad.com", "openscad.exe")]
    if sys.platform == "darwin":
        candidates += ["/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"]
    return next((c for c in candidates if os.path.isfile(c)), None)


# Subprocess output is decoded as UTF-8 with replacement: on Windows text=True would use
# the ANSI code page and a Korean path or message in OpenSCAD's output would raise
# UnicodeDecodeError. Stray bytes become U+FFFD instead of a crash.
TEXT = {"encoding": "utf-8", "errors": "replace"}


def openscad_info(exe: str) -> dict:
    info = {"path": exe, "version": None, "manifold": False}
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, timeout=30, **TEXT)
        m = re.search(r"version\s+(\S+)", (r.stdout + r.stderr))
        info["version"] = m.group(1) if m else (r.stdout + r.stderr).strip()[:40]
    except (OSError, subprocess.TimeoutExpired) as exc:
        info["error"] = str(exc)
        return info
    # Probe the fast backend for real. Never use the obsolete --enable=manifold: it
    # is accepted silently and falls back to CGAL.
    with tempfile.TemporaryDirectory() as d:
        scad, stl = os.path.join(d, "p.scad"), os.path.join(d, "p.stl")
        with open(scad, "w", encoding="utf-8") as f:
            f.write("cube(1);")
        try:
            r = subprocess.run([exe, "--backend=manifold", "-o", stl, scad],
                               capture_output=True, timeout=60, **TEXT)
            err = (r.stdout + r.stderr).lower()
            info["manifold"] = (r.returncode == 0 and os.path.isfile(stl)
                                and "ignor" not in err and "unknown" not in err and "unrecogni" not in err)
        except (OSError, subprocess.TimeoutExpired):
            info["manifold"] = False
    return info


def python_info() -> dict:
    out = {"python": platform.python_version()}
    for mod in ("manifold3d", "numpy", "trimesh", "rtree", "pyrender", "matplotlib"):
        out[mod] = importlib.util.find_spec(mod) is not None
    return out


def cmd_detect(_args) -> dict:
    exe = find_openscad()
    py = python_info()
    engines = {"openscad": openscad_info(exe) if exe else None,
               "python": {"manifold3d": py["manifold3d"]}}
    order = [e for e, ok in (("openscad", bool(exe)), ("python", py["manifold3d"])) if ok]
    return {"schema": SCHEMA, "ran": True, "engines": engines, "available": order,
            "libraries": py, "fusion": "detect through the host's MCP tools, not here",
            "notes": ([] if not exe or engines["openscad"].get("manifold")
                      else ["OpenSCAD has no Manifold backend (CGAL only): boolean-heavy models are slow; "
                            "a recent nightly build adds --backend=manifold"]),
            "warnings": [], "errors": []}


# --------------------------------------------------------------------------- #
# Parameters
# --------------------------------------------------------------------------- #
def load_params(path: str | None) -> dict:
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("params file must contain a JSON object")
    return data


engine_params = validate.engine_params      # one definition: the freshness hash uses the same filter


def part_specs(params: dict, default_name: str) -> dict:
    parts = params.get("_parts")
    if not parts:
        return {default_name: {}}
    if isinstance(parts, list):
        return {p: {} for p in parts}
    return dict(parts)


def scad_literal(v) -> str:
    """Python value -> OpenSCAD literal for -D overrides."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        if not math.isfinite(v):
            raise ValueError(f"non-finite parameter value {v}")
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)                          # double-quoted, escaped
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(scad_literal(x) for x in v) + "]"
    raise ValueError(f"unsupported parameter type {type(v).__name__}")


# --------------------------------------------------------------------------- #
# Engines
# --------------------------------------------------------------------------- #
def parse_deps(dep_file: str, exclude: str) -> tuple[list[str], list[str]]:
    """OpenSCAD -d writes a Makefile rule: 'out.stl: a.scad b.scad \\'. Returns (deps, warnings).

    A dependency that cannot be resolved to a file (written in an encoding this decoding lost,
    or a path that no longer exists) is reported, never silently dropped: it would otherwise be
    missing from the freshness hash (R3)."""
    if not os.path.isfile(dep_file):
        return [], []
    with open(dep_file, "rb") as f:            # closed before os.remove (Windows locks open files)
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode(sys.getfilesystemencoding() or "utf-8", errors="replace")
    text = text.replace("\\\r\n", " ").replace("\\\n", " ")
    _, _, rhs = text.partition(":")
    # Paths may contain escaped spaces ("\ ").
    tokens = re.findall(r"(?:\\ |[^\s])+", rhs)
    deps, warns = [], []
    for d in (t.replace("\\ ", " ") for t in tokens):
        if os.path.isfile(d):
            if os.path.abspath(d) != os.path.abspath(exclude):
                deps.append(d)
        else:
            warns.append("dependency reported by OpenSCAD could not be read as a file and is not in the "
                         f"freshness hash: {d!r}")
    return deps, warns


def build_openscad(source, params, parts, out_dir, timeout):
    exe = find_openscad()
    if not exe:
        raise RuntimeError("OpenSCAD not found (set OPENSCAD=/path/to/openscad or install it)")
    info = openscad_info(exe)
    defs = []
    for k, v in engine_params(params).items():
        defs += ["-D", f"{k}={scad_literal(v)}"]
    results, deps_all = [], {os.path.abspath(source)}
    for name in parts:
        stl = os.path.join(out_dir, f"{name}.stl")
        dep = stl + ".deps"
        # Binary STL: about a third of the size of OpenSCAD's default ASCII output.
        cmd = [exe, "--export-format", "binstl", "-o", stl, "-d", dep] + defs
        if len(parts) > 1 or params.get("_parts"):
            cmd += ["-D", f"part={scad_literal(name)}"]
        if info.get("manifold"):
            cmd.insert(1, "--backend=manifold")
        cmd.append(source)
        t0 = time.time()
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout, **TEXT)
        except subprocess.TimeoutExpired:
            _remove(dep)
            raise RuntimeError(f"OpenSCAD timed out after {timeout}s on part '{name}'"
                               + ("" if info.get("manifold") else " (CGAL backend; a nightly with Manifold is much faster)"))
        log = (r.stdout + r.stderr).splitlines()
        warns = [ln.strip() for ln in log if ln.strip().startswith("WARNING")]
        errs = [ln.strip() for ln in log if ln.strip().startswith("ERROR")]
        if r.returncode != 0 or errs or not os.path.isfile(stl):
            _remove(dep)                       # no leftover <part>.stl.deps next to a failed build
            tail = "\n".join(log[-12:])
            raise RuntimeError(f"OpenSCAD failed on part '{name}' (exit {r.returncode}):\n{tail}")
        deps, dep_warns = parse_deps(dep, stl)
        deps_all.update(os.path.abspath(d) for d in deps)
        _remove(dep)
        results.append({"name": name, "stl": stl, "seconds": round(time.time() - t0, 2),
                        "engine_warnings": warns + _hint(warns) + dep_warns})
    return results, sorted(deps_all), {"version": info.get("version"),
                                       "backend": "manifold" if info.get("manifold") else "cgal"}


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _hint(warns):
    if any("2-manifold" in w for w in warns):
        return ["hint: coincident faces between a body and a cut; extend cutting bodies by 0.01-0.1 mm"]
    return []


def build_python(source, params, parts, out_dir, timeout):
    if importlib.util.find_spec("manifold3d") is None:
        raise RuntimeError("manifold3d is not installed (pip install manifold3d)")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(engine_params(params), f)
        ptmp = f.name
    try:
        cmd = [sys.executable, os.path.abspath(__file__), "_pyrun", os.path.abspath(source), ptmp,
               os.path.abspath(out_dir), ",".join(parts)]
        env = dict(os.environ, PYTHONIOENCODING="utf-8")   # the child prints its report as UTF-8
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env, **TEXT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Python generator timed out after {timeout}s")
    finally:
        os.unlink(ptmp)
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("@@3DPS ")]
    if r.returncode != 0 or not lines:
        tail = "\n".join((r.stdout + r.stderr).splitlines()[-15:])
        raise RuntimeError(f"Python generator failed (exit {r.returncode}):\n{tail}")
    rep = json.loads(lines[-1][len("@@3DPS "):])
    results = [{"name": p["name"], "stl": p["stl"], "seconds": p["seconds"], "engine_warnings": []}
               for p in rep["parts"]]
    return results, sorted(set(rep["deps"]) | {os.path.abspath(source)}), {"manifold3d": rep["version"]}


def _pyrun(source, params_file, out_dir, parts_csv):
    """Runs in a child process: import the generator, call build(params), export STLs."""
    import manifold3d as m3d
    src_dir = os.path.dirname(source)
    sys.path.insert(0, src_dir)
    # The skill's own libraries (parts.py, sdf.py) are importable by name from any generator.
    # The generator's folder comes first, so a local module of the same name wins.
    sys.path.append(HERE)
    with open(params_file, encoding="utf-8") as f:
        params = json.load(f)
    spec = importlib.util.spec_from_file_location("_generator", source)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "build"):
        raise SystemExit("generator has no build(params) function")
    t0 = time.time()
    built = mod.build(params)
    wanted = [p for p in parts_csv.split(",") if p]
    if isinstance(built, m3d.Manifold):
        built = {wanted[0] if wanted else "part": built}
    out = []
    for name in wanted or list(built):
        if name not in built:
            raise SystemExit(f"build() did not return part '{name}' (got {sorted(built)})")
        man = built[name]
        if man.status() != m3d.Error.NoError:
            raise SystemExit(f"part '{name}': manifold status {man.status()}")
        if man.is_empty():
            raise SystemExit(f"part '{name}' is empty")
        stl = os.path.join(out_dir, f"{name}.stl")
        mesh = man.to_mesh()
        write_binary_stl(stl, mesh.vert_properties[:, :3].tolist(), mesh.tri_verts.tolist())
        out.append({"name": name, "stl": stl, "seconds": round(time.time() - t0, 2)})
    # Freshness (R3): every .py the generator imported from its own folder, plus any library it
    # imported from the skill's scripts folder (parts.py, sdf.py), is hashed into the manifest.
    # build.py's own imports (validate, threemf) were loaded before the generator and are not
    # part of what the generator depends on.
    norm = lambda p: os.path.normcase(os.path.abspath(p))     # noqa: E731 - Windows paths differ in case
    own = {norm(os.path.join(HERE, n)) for n in ("build.py", "validate.py", "threemf.py")}
    roots = (norm(src_dir) + os.sep, norm(HERE) + os.sep)
    deps = sorted({os.path.abspath(m.__file__) for m in list(sys.modules.values())
                   if getattr(m, "__file__", None) and m.__file__.endswith(".py")
                   and norm(m.__file__).startswith(roots) and norm(m.__file__) not in own})
    print("@@3DPS " + json.dumps({"parts": out, "deps": deps, "version": getattr(m3d, "__version__", "unknown")}))


def write_binary_stl(path, verts, tris):
    with open(path, "wb") as f:
        f.write(b"3dprint-scout".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            p, q, r = verts[a], verts[b], verts[c]
            u = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
            v = (r[0] - p[0], r[1] - p[1], r[2] - p[2])
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
            f.write(struct.pack("<12fH", n[0] / ln, n[1] / ln, n[2] / ln, *p, *q, *r, 0))


# --------------------------------------------------------------------------- #
# Validation of every part
# --------------------------------------------------------------------------- #
VALIDATE_FLAGS = ("tol", "printer", "printer_id", "tools", "overhang_angle", "min_wall")


def validate_part(stl, spec, sources, params_path, args) -> dict:
    argv = [stl]
    expect = spec.get("expect")
    if expect:
        argv += ["--expect", ",".join(str(x) for x in expect)]
    argv += ["--shells", str(spec.get("shells", 1))]
    for flag in VALIDATE_FLAGS:
        val = spec.get(flag, getattr(args, flag, None))
        if val is not None:
            argv += ["--" + flag.replace("_", "-"), str(val)]
    if not args.wall_check:
        argv.append("--no-wall-check")
    argv += ["--source", *sources]
    if params_path:
        argv += ["--params", params_path]
    buf = io.StringIO()
    with redirect_stdout(buf):
        validate.main(argv)
    return json.loads(buf.getvalue())


def overall_gate(reports) -> str:
    gates = [r.get("gate") for r in reports]
    if any(g == "FAIL" for g in gates):
        return "FAIL"
    if any(g != "PASS" for g in gates):
        return "INCOMPLETE"
    return "PASS"


def printer_bed(args, all_tools=False):
    """(bed dict from validate.effective_bed, bed source, tool ids) for the printer file and tool
    list of this build, or (None, reason, []) when the printer is not known. With all_tools the
    bed is the intersection of every tool's area (what an object printed by several nozzles
    needs). Errors are left for validate.py to report; here they only mean "no bed"."""
    if not args.printer:
        return None, "no printer profile given", []
    if not os.path.isfile(args.printer):
        return None, f"printer file not found: {args.printer}", []
    try:
        _, printer = validate.load_printer(args.printer, args.printer_id)
        tool_ids = [int(x) for x in str(args.tools if args.tools is not None else "0").split(",") if x.strip()]
        if all_tools and printer.get("tools"):
            tool_ids = list(range(len(printer["tools"])))
        bed = validate.effective_bed(printer, tool_ids)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return None, str(exc), []
    return bed, printer.get("bed", {}).get("source", "user"), tool_ids


def usable_bed(args):
    """(width, depth) of the usable bed for the core 3MF layout, or None when unknown.
    Uses the same printer file and tool list as the D2 check, so an object that D2 passes
    "when rotated" is placed with that rotation."""
    bed, source, _ = printer_bed(args)
    if bed is None or source == "default" or not bed.get("rect"):
        return None
    x0, y0, x1, y1 = bed["rect"]
    return (x1 - x0, y1 - y0)


def _relpath(path: str) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:                       # Windows: another drive than the working directory
        return os.path.abspath(path)


def finish(out, parts, sources, params, params_path, specs, args, engine):
    # G4: artifact sanity first. A broken STL gets no manifest, is left out of the 3MF, and is
    # reported; the sane parts still get their full treatment.
    for p in parts:
        try:
            validate.read_stl(p["stl"])
            p["artifact_sane"] = True
        except validate.ArtifactError as exc:
            p["artifact_sane"] = False
            p["artifact_error"] = str(exc)
            out["errors"].append(f"{p['name']}: broken artifact ({exc}); no manifest written, left out of the 3MF")
    sane = [p for p in parts if p["artifact_sane"]]
    for p in sane:
        validate.write_manifest(p["stl"], sources, params, engine)

    # Parts grouped into objects (assembly.py). A bad grouping is a usage error, not a build error.
    try:
        groups = assembly.group_parts({p["name"]: specs.get(p["name"], {}) for p in parts})
    except assembly.AssemblyError as exc:
        out["errors"].append(f"params.json _parts: {exc}")
        groups = [{"name": p["name"], "parts": [p["name"]], "main": p["name"]} for p in parts]
    of_part = {n: g for g in groups for n in g["parts"]}
    for p in parts:
        p["object"] = of_part[p["name"]]["name"]
        p["role"] = assembly.part_role(specs.get(p["name"])) if len(of_part[p["name"]]["parts"]) > 1 else None

    if not args.no_3mf and sane:
        name = args.threemf or os.path.splitext(os.path.basename(args.source_main))[0] + ".3mf"
        path = os.path.join(args.out, name)
        try:
            # out/ is the build's working folder: this file is rewritten on every build.
            placed = threemf.write_core_3mf([(p["name"], p["stl"]) for p in sane], path,
                                            bed=usable_bed(args), objects=groups)
            out["threemf"] = path
            for p in sane:
                p["rotation_deg"] = placed[p["name"]]["rotation_deg"]
                if p["rotation_deg"]:
                    out["warnings"].append(f"{p['name']}: placed rotated {p['rotation_deg']} deg in the 3MF "
                                           "so it fits the bed (the STL itself is unchanged)")
        except (validate.ArtifactError, OSError) as exc:
            out["errors"].append(f"core 3MF not written: {exc}")

    reports = []
    for p in sane:
        rep = validate_part(p["stl"], specs.get(p["name"], {}), sources, params_path, args)
        p["validate"] = rep
        reports.append(rep)
        # Lift the validator's own errors and warnings; nothing stays hidden in parts[].validate.
        out["errors"] += [f"{p['name']}: {e}" for e in rep.get("errors", [])]
        out["warnings"] += [f"{p['name']}: {w}" for w in p.get("engine_warnings", [])]
        out["warnings"] += [f"{p['name']}: {w}" for w in rep.get("warnings", [])]

    # Objects with several parts: D2 / P1 / P2 of the whole, A1 / A2 per part.
    sane_names = {p["name"] for p in sane}
    by_name = {p["name"]: p for p in parts}
    # An object with several parts, or any object of a job that uses several filaments, may be
    # printed by more than one nozzle: its D2 uses the intersection of every tool's area, as
    # bambu3mf.py lays such jobs out (printers.json "tools"; a single-nozzle printer is unchanged).
    filaments = {int((specs.get(p["name"]) or {}).get("filament") or 1) for p in parts}
    multi_tool = any(len(g["parts"]) > 1 for g in groups) or len(filaments) > 1
    bed, bed_source, tool_ids = printer_bed(args, all_tools=multi_tool)
    out["objects"] = []
    object_gates = []
    for g in groups:
        entry = {"name": g["name"], "parts": list(g["parts"]), "main": g["main"]}
        if len(g["parts"]) > 1:
            if all(n in sane_names for n in g["parts"]):
                try:
                    rep = assembly.check_object(g, {n: by_name[n]["stl"] for n in g["parts"]}, specs,
                                                bed=bed, bed_source=bed_source,
                                                overhang_angle=args.overhang_angle or 45.0,
                                                no_bed_reason=None if bed else bed_source)
                except (assembly.AssemblyError, validate.ArtifactError) as exc:
                    out["errors"].append(f"object '{g['name']}': {exc}")
                    entry["gate"] = "FAIL"
                else:
                    if bed is not None and multi_tool:
                        rep["checks"]["D2"].setdefault("value", {})
                        if isinstance(rep["checks"]["D2"]["value"], dict):
                            rep["checks"]["D2"]["value"]["tools"] = tool_ids
                        rep["checks"]["D2"]["note"] = (rep["checks"]["D2"].get("note", "") +
                                                       f"; usable area = intersection of tools {tool_ids} (several parts or "
                                                       "filaments may need every nozzle)").lstrip("; ")
                    entry.update(checks=rep["checks"], metrics=rep["metrics"], rotation_deg=rep["rotation_deg"],
                                 method=rep["method"], gate=assembly.object_gate(rep))
                    for n, pr in rep["parts"].items():
                        by_name[n]["assembly"] = {"object": g["name"], "role": pr["role"], "checks": pr["checks"]}
                    out["warnings"] += [f"object '{g['name']}': {w}" for w in rep["warnings"]]
                    for cid, ck in rep["checks"].items():
                        if ck["state"] == "FAIL":
                            out["warnings"].append(f"object '{g['name']}' {cid} FAIL: {ck.get('note', '')}")
                    for n, pr in rep["parts"].items():
                        for cid, ck in pr["checks"].items():
                            if ck["state"] == "FAIL":
                                out["warnings"].append(f"{n} {cid} FAIL: {ck.get('note', '')}")
            else:
                entry["gate"] = "FAIL"
            object_gates.append(entry["gate"])
        out["objects"].append(entry)

    out["parts"] = parts
    out["sources"] = [_relpath(s) for s in sources]
    gate = overall_gate(reports)
    if object_gates:
        gate = overall_gate([{"gate": gate}] + [{"gate": g} for g in object_gates])
    out["gate"] = "FAIL" if len(sane) < len(parts) else gate
    out["R4"] = "PASS" if len(sane) == len(parts) else "FAIL"   # the generator ran, but left a broken artifact
    return out


def cmd_run(args) -> dict:
    t0 = time.time()
    source = args.source
    if not os.path.isfile(source):
        raise ValueError(f"source not found: {source}")
    params = load_params(args.params)
    engine = args.engine
    if engine == "auto":
        engine = {".scad": "openscad", ".py": "python"}.get(os.path.splitext(source)[1].lower())
        if not engine:
            raise ValueError("cannot infer engine from file extension; pass --engine")
    stem = os.path.splitext(os.path.basename(source))[0]
    specs = part_specs(params, stem)
    if args.only:
        wanted = [n.strip() for n in args.only.split(",") if n.strip()]
        unknown = [n for n in wanted if n not in specs]
        if unknown:
            raise ValueError(f"--only names parts that are not in _parts: {unknown} (known: {sorted(specs)})")
        specs = {n: specs[n] for n in wanted}
    os.makedirs(args.out, exist_ok=True)
    out = {"schema": SCHEMA, "ran": True, "engine": engine, "source": source, "gate": None,
           "warnings": [], "errors": []}
    try:
        if engine == "openscad":
            parts, sources, info = build_openscad(source, params, list(specs), args.out, args.timeout)
        elif engine == "python":
            parts, sources, info = build_python(source, params, list(specs), args.out, args.timeout)
        else:
            raise ValueError(f"engine '{engine}' is not run by build.py; use 'record' for Fusion")
    except RuntimeError as exc:
        out.update(ran=False, gate="FAIL", R4="FAIL")
        out["errors"].append(str(exc))
        return out
    out["engine_info"] = info
    args.source_main = source
    out = finish(out, parts, sources, params, args.params, specs, args, engine)
    out["seconds"] = round(time.time() - t0, 2)
    return out


def cmd_record(args) -> dict:
    params = load_params(args.params)
    missing = [s for s in args.source if not os.path.isfile(s)]
    if missing:
        raise ValueError(f"source not found: {missing}")
    specs = part_specs(params, "part")
    parts = []
    for stl in args.stl:
        name = os.path.splitext(os.path.basename(stl))[0]
        parts.append({"name": name, "stl": stl, "engine_warnings": []})
        specs.setdefault(name, {})
    out = {"schema": SCHEMA, "ran": True, "engine": args.engine, "source": args.source[0], "gate": None,
           "warnings": [], "errors": []}
    os.makedirs(args.out, exist_ok=True)
    args.source_main = args.source[0]
    return finish(out, parts, sorted(os.path.abspath(s) for s in args.source), params, args.params, specs, args,
                  args.engine)


class _JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(f"usage error: {message}")


OUTPUT_HELP = """\
Prints one JSON document (schema 3dprint-scout.build/1):
  gate      PASS | FAIL | INCOMPLETE over every part and object; R4 = the generator ran
  parts[]   name, stl, artifact_sane, object, role, rotation_deg, validate (validate.py's
            document: files[0].checks, files[0].metrics), assembly (A1 / A2 in a group)
  objects[] name, parts, gate, checks (D2 / P1 / P2 of the whole object when it has
            several parts), metrics, rotation_deg
  sources   files hashed into the manifests (pass the same list to validate.py)
  threemf   core 3MF written in --out;  warnings / errors: read these two lists first
Full description: references/parts.md. Exit 0 = ran (read gate), 1 = build or usage error."""


def _common(p):
    p.add_argument("--params", help="params.json: _parts (expect, object, role), engine parameters")
    p.add_argument("--out", default="out", help="working folder, rewritten on every build (default out)")
    p.add_argument("--3mf", dest="threemf", help="3MF file name (default: <source>.3mf)")
    p.add_argument("--no-3mf", action="store_true", help="skip the core 3MF")
    p.add_argument("--tol", type=float, help="D1 tolerance in mm (default 0.1)")
    p.add_argument("--printer", help=".3dprint/printers.json (a missing file leaves D2 UNVERIFIED)")
    p.add_argument("--printer-id", help="printer id in printers.json when it holds several")
    p.add_argument("--tools", help="tool indices this print uses, e.g. 0 or 0,1 (bed = their intersection)")
    p.add_argument("--overhang-angle", type=float, help="P2 limit from vertical in degrees (default 45)")
    p.add_argument("--min-wall", type=float, help="P3 minimum wall in mm (default 1.2)")
    p.add_argument("--no-wall-check", dest="wall_check", action="store_false", help="skip P3 (ray casting)")


def main(argv=None):
    if argv is None and len(sys.argv) > 1 and sys.argv[1] == "_pyrun":
        _pyrun(*sys.argv[2:6])
        return 0
    ap = _JsonArgParser(description="3dprint-scout build runner: build, record, validate, write a core 3MF",
                        epilog=OUTPUT_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", metavar="{detect,run,record}")
    sub.add_parser("detect", help="Phase 0 probe: OpenSCAD (and its Manifold backend), manifold3d, optional libraries")
    r = sub.add_parser("run", help="build every part of _parts with OpenSCAD (.scad) or Python (.py), then validate",
                       epilog=OUTPUT_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    r.add_argument("source", help="generator: model.scad or model.py")
    r.add_argument("--engine", default="auto", choices=["auto", "openscad", "python"])
    r.add_argument("--timeout", type=int, default=900, help="seconds per generator run (default 900)")
    r.add_argument("--only", help="build only these _parts (comma list), e.g. the mechanism and the bit of its mating "
                                  "part it needs, for a test print before the full part")
    _common(r)
    rec = sub.add_parser("record", help="record STLs built elsewhere (Fusion): manifests, core 3MF, validation",
                         epilog=("Each STL is one part named after its file (out/lid.stl -> part 'lid'); with\n"
                                 "--params the names match _parts and parts grouped there form objects.\n\n"
                                 + OUTPUT_HELP),
                         formatter_class=argparse.RawDescriptionHelpFormatter)
    rec.add_argument("stl", nargs="+", help="one STL per part, exported in print orientation (mm)")
    rec.add_argument("--source", nargs="+", required=True,
                     help="the generator script(s) that built the STLs; hashed with --params for freshness (R3)")
    rec.add_argument("--engine", default="fusion", help="engine name written to the manifests (default fusion)")
    _common(rec)
    try:
        args = ap.parse_args(argv)
        if args.cmd is None:
            raise ValueError("usage error: choose a subcommand: detect, run, record")
        out = {"detect": cmd_detect, "run": cmd_run, "record": cmd_record}[args.cmd](args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        out = {"schema": SCHEMA, "ran": False, "gate": "FAIL", "warnings": [], "errors": [str(exc)]}
    print(json.dumps(out, indent=2))
    return 0 if out.get("ran") else 1


if __name__ == "__main__":
    sys.exit(main())
