#!/usr/bin/env python3
"""
build.py - run a generator script with OpenSCAD, Python (manifold3d) or Blender, record a
freshness manifest for every STL, write a core 3MF, and validate every part.

Subcommands (all print ONE JSON document to stdout):

  detect                       Phase 0 probe: engines, OpenSCAD backend, Blender, optional libs.
  run SOURCE [options]         Build all parts, write manifests + 3MF, validate.
  record STL... --source F...  Write manifests for parts built elsewhere (Fusion, a live
                               Blender), then validate.

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
A Blender generator (first line `# 3dprint-scout: engine=blender`, or --engine blender)
imports references/engines/blender_builder.py and ends with `bb.main(build, PARAMETERS)`;
it runs in the blender binary (--background --factory-startup) or, without one, in the
Python that has the `bpy` module (--blender-python, or the Python running this script).
Blender 4.5 LTS or newer.
`record` takes STLs built elsewhere (Fusion, a live Blender): one STL per part, named
after the part. An STL that already has a manifest from `run` describing this very file
keeps it: its sources join "sources" (a generator's own imports stay in the hash; R3 hashes
each manifest's own files out of that list), and when that manifest is stale, or none of its
generators is among --source, the part is not re-stamped: R3 FAILs and says why
(parts[].prior_manifest tells what was found). Any other STL, including one an earlier
record stamped, gets a new manifest.

Every STL is checked for sanity (G4) before anything is recorded: a 0-byte, truncated or
NaN mesh gets no manifest, is left out of the 3MF and is listed in "errors" with
"artifact_sane": false on its part; the other parts are still recorded and validated. The
validator's own errors and warnings are repeated in the top-level "errors" / "warnings", and
every hard FAIL of a part, an object or an assembly check is one line in "errors"
("<part> <check> FAIL: <note>"), so those two lists are enough to read first.
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
  blend           the .blend a Blender build saved in --out (engine blender only)
  warnings, errors  everything worth reading, lifted from every part and object (every hard
                  FAIL is one line in errors)

Exit codes: 0 = ran (read "gate"), 1 = build or usage error.
"""
from __future__ import annotations

import argparse
import glob
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
ENGINES_DIR = os.path.join(os.path.dirname(HERE), "references", "engines")   # blender_builder.py lives here
BLENDER_MARKER = "# 3dprint-scout: engine=blender"
MIN_BLENDER = (4, 5)             # Blender 4.5 LTS: the Manifold boolean solver; text and renders tested from there
BPY_PROBE_TIMEOUT = 120          # s; importing bpy loads most of Blender
BLENDER_VERSION_TIMEOUT = 60     # s; `blender --version` on a cold disk


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


# --------------------------------------------------------------------------- #
# Blender: a binary, or the bpy module in some Python
# --------------------------------------------------------------------------- #
def find_blender() -> str | None:
    """BLENDER env, PATH, then the usual install places (installers rarely touch PATH): the
    official installers, the Steam copy, flatpak and snap, an unpacked archive in the home
    folder. The path found goes only into the detect JSON, never into a file."""
    env = os.environ.get("BLENDER")
    if env and os.path.isfile(env):
        return env
    hit = shutil.which("blender")
    if hit:
        return hit
    home = os.path.expanduser("~")
    patterns = []
    if os.name == "nt":
        for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if root:
                patterns.append(os.path.join(root, "Blender Foundation", "Blender *", "blender.exe"))
                patterns.append(os.path.join(root, "Steam", "steamapps", "common", "Blender", "blender.exe"))
    elif sys.platform == "darwin":
        patterns += ["/Applications/Blender.app/Contents/MacOS/Blender",
                     os.path.join(home, "Applications", "Blender.app", "Contents", "MacOS", "Blender"),
                     os.path.join(home, "Library", "Application Support", "Steam", "steamapps", "common", "Blender",
                                  "Blender.app", "Contents", "MacOS", "Blender")]
    else:
        patterns += ["/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender", "/opt/blender*/blender",
                     "/var/lib/flatpak/exports/bin/org.blender.Blender",
                     os.path.join(home, ".local", "share", "flatpak", "exports", "bin", "org.blender.Blender"),
                     os.path.join(home, ".steam", "steam", "steamapps", "common", "Blender", "blender"),
                     os.path.join(home, ".local", "share", "Steam", "steamapps", "common", "Blender", "blender"),
                     os.path.join(home, "blender-*", "blender")]
    for pat in patterns:
        hits = sorted(glob.glob(pat), reverse=True)        # newest version folder first
        for h in hits:
            if os.path.isfile(h):
                return h
    return None


def parse_blender_version(text: str) -> str | None:
    """'Blender 4.2.3 LTS\\n\\tbuild date: ...' -> '4.2.3'."""
    m = re.search(r"Blender\s+(\d+\.\d+(?:\.\d+)?)", text)
    return m.group(1) if m else None


def version_tuple(text: str | None) -> tuple:
    try:
        return tuple(int(x) for x in str(text).split(".")[:3])
    except (TypeError, ValueError):
        return ()


def blender_info(exe: str) -> dict:
    """{"path", "version"} of a Blender binary (`--version` runs without a window)."""
    info = {"path": exe, "version": None}
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, timeout=BLENDER_VERSION_TIMEOUT, **TEXT)
        info["version"] = parse_blender_version(r.stdout + r.stderr)
        if info["version"] is None:
            info["error"] = f"could not read a version from `{exe} --version`"
    except (OSError, subprocess.TimeoutExpired) as exc:
        info["error"] = str(exc)
    return info


def bpy_pythons(explicit: str | None = None) -> list[str]:
    """Interpreters to probe for the bpy module: the explicit one, BLENDER_PYTHON, this one."""
    out = []
    for cand in (explicit, os.environ.get("BLENDER_PYTHON"), sys.executable):
        if cand and cand not in out:
            out.append(cand)
    return out


BPY_PROBE = ("import json, sys, importlib.util, bpy; print('@@BPY ' + json.dumps({'version': bpy.app.version_string, "
             "'version_tuple': list(bpy.app.version), 'python': sys.version.split()[0], "
             "'manifold3d': importlib.util.find_spec('manifold3d') is not None}))")
MF_PROBE = "import importlib.util; print('@@MF', importlib.util.find_spec('manifold3d') is not None)"


def blender_manifold3d(exe: str) -> bool | None:
    """Whether the Python inside a Blender binary has manifold3d (parts.py through
    bb.from_manifold), or None when the probe could not tell. Starts Blender in the background
    once, without the user's preferences or add-ons."""
    try:
        with tempfile.TemporaryDirectory() as empty:
            r = subprocess.run([exe, "--background", "--factory-startup", "--python-expr", MF_PROBE],
                               capture_output=True, timeout=BPY_PROBE_TIMEOUT, cwd=empty, **TEXT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for ln in r.stdout.splitlines():
        if ln.startswith("@@MF "):
            return ln.split()[1] == "True"
    return None


def bpy_info(python: str | None = None) -> dict | None:
    """{"version", "python", ...} when `python` (or the usual candidates) can import bpy, else
    None. Always a subprocess with a timeout (importing bpy is slow and must never happen in
    this process), run from an empty temporary folder so a `bpy.py` or `json.py` lying in the
    user's folder is not what gets imported."""
    for exe in bpy_pythons(python):
        try:
            with tempfile.TemporaryDirectory() as empty:
                r = subprocess.run([exe, "-c", BPY_PROBE], capture_output=True, timeout=BPY_PROBE_TIMEOUT, cwd=empty, **TEXT)
        except subprocess.TimeoutExpired:
            return {"error": f"import bpy timed out after {BPY_PROBE_TIMEOUT}s in {exe}", "python": exe}
        except OSError:
            continue
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("@@BPY ")]
        if r.returncode == 0 and lines:
            info = json.loads(lines[-1][len("@@BPY "):])
            info["python"] = exe
            info["version_tuple"] = tuple(info.get("version_tuple", []))
            return info
    return None


def too_old(version) -> str | None:
    """A note when a Blender version is below the floor, else None."""
    ver = version_tuple(version) if isinstance(version, str) else tuple(version or ())
    if ver and ver[:2] < MIN_BLENDER:
        return (f"Blender {'.'.join(map(str, ver))} is older than {MIN_BLENDER[0]}.{MIN_BLENDER[1]} LTS: not usable "
                "(the Manifold boolean solver, text and renders need 4.5 or newer)")
    return None


def blender_status(python: str | None = None) -> dict:
    """The `blender` block of `detect`: binary, bpy module, whether the Manifold boolean solver
    is there on the path that would run (Blender 4.5+, the floor), and notes."""
    exe = find_blender()
    binary = blender_info(exe) if exe else None
    module = bpy_info(python)
    if module and "error" in module:
        notes = [module["error"]]
        module = None
    else:
        notes = []
    binary_ok = bool(binary) and not binary.get("error") and not too_old(binary["version"])
    module_ok = bool(module) and not too_old(module["version_tuple"])
    if binary_ok:
        binary["manifold3d"] = blender_manifold3d(exe)
    for label, ver in (("binary", binary and version_tuple(binary["version"])),
                       ("bpy", module and tuple(module["version_tuple"]))):
        note = too_old(ver) if ver else None
        if note:
            notes.append(f"{label}: {note}")
    if binary_ok and module:
        notes.append("both a binary and the bpy module: build.py uses the binary (--blender-python forces bpy)")
    elif binary and not binary_ok and module_ok:
        notes.append("the binary is not usable: build.py and render.py use the bpy module")
    runs = binary if binary_ok else module if module_ok else None
    if runs is not None and runs.get("manifold3d") is False:
        notes.append("the Python that runs Blender has no manifold3d: parts.py's helpers (screw holes, snaps, hinges, "
                     "threads) cannot reach a Blender build through bb.from_manifold; build such a part with the Python "
                     "engine, or install manifold3d into that Python (ask first)")
    # The same choice as choose_blender: the Manifold solver is there when what runs is 4.5+.
    return {"binary": binary, "bpy": module, "manifold_boolean": binary_ok or module_ok, "notes": notes}


def blender_usable(status: dict) -> bool:
    b = status.get("binary")
    if b and not b.get("error") and version_tuple(b["version"])[:2] >= MIN_BLENDER:
        return True
    p = status.get("bpy")
    return bool(p and tuple(p.get("version_tuple", ()))[:2] >= MIN_BLENDER)


def cmd_detect(args) -> dict:
    exe = find_openscad()
    py = python_info()
    blender = blender_status(getattr(args, "blender_python", None))
    engines = {"openscad": openscad_info(exe) if exe else None,
               "python": {"manifold3d": py["manifold3d"]}}
    order = [e for e, ok in (("openscad", bool(exe)), ("python", py["manifold3d"]),
                             ("blender", blender_usable(blender))) if ok]
    notes = ([] if not exe or engines["openscad"].get("manifold")
             else ["OpenSCAD has no Manifold backend (CGAL only): boolean-heavy models are slow; "
                   "a recent nightly build adds --backend=manifold"])
    notes += [f"blender: {n}" for n in blender["notes"]]
    return {"schema": SCHEMA, "ran": True, "engines": engines, "available": order,
            "libraries": py, "fusion": "detect through the host's MCP tools, not here",
            "blender": blender, "notes": notes, "warnings": [], "errors": []}


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
    """{part name: spec} from params "_parts": an object {"name": {...}} (the documented form),
    a plain list of names, or nothing (one part named after the generator)."""
    parts = params.get("_parts")
    if not parts:
        return {default_name: {}}
    if isinstance(parts, list):
        if not all(isinstance(p, str) and p for p in parts):
            raise ValueError('params.json "_parts": a list holds part names (strings), e.g. ["body", "lid"]; '
                             'the full form is an object {"body": {"expect": [60, 40, 25]}, ...}')
        return {p: {} for p in parts}
    if not isinstance(parts, dict):
        raise ValueError(f'params.json "_parts" must be an object {{"body": {{"expect": [60, 40, 25]}}, ...}} '
                         f'(or a list of part names), got {type(parts).__name__}: {str(parts)[:60]!r}')
    bad = [n for n, spec in parts.items() if spec is not None and not isinstance(spec, dict)]
    if bad:
        raise ValueError(f'params.json "_parts": the entry of {bad[0]!r} must be an object such as '
                         f'{{"expect": [60, 40, 25]}}, got {type(parts[bad[0]]).__name__}')
    return {n: dict(spec or {}) for n, spec in parts.items()}


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
    if engine_marker(source) == "blender":
        raise RuntimeError(f"{os.path.basename(source)} is a Blender generator (its first line is '{BLENDER_MARKER}'); "
                           "run it with --engine blender or --engine auto, not with the Python engine")
    if importlib.util.find_spec("manifold3d") is None:
        raise RuntimeError("manifold3d is not installed (pip install manifold3d)")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(engine_params(params), f)
        ptmp = f.name
    try:
        cmd = [sys.executable, os.path.abspath(__file__), "_pyrun", os.path.abspath(source), ptmp,
               os.path.abspath(out_dir), ",".join(parts)]
        # The child prints its report as UTF-8, and leaves no __pycache__ in the user's project.
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
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
    return (results, sorted(set(rep["deps"]) | {os.path.abspath(source)}),
            {"manifold3d": rep["version"], "warnings": rep.get("warnings", [])})


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
    import warnings
    # A UserWarning the generator or a library raises (parts.text() switching to a font that
    # covers the text) reaches the build report's warnings instead of a stderr nobody reads.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "build"):
            raise SystemExit("generator has no build(params) function")
        t0 = time.time()
        built = mod.build(params)
    notes = list(dict.fromkeys(str(w.message) for w in caught if issubclass(w.category, UserWarning)))
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
    print("@@3DPS " + json.dumps({"parts": out, "deps": deps, "version": getattr(m3d, "__version__", "unknown"),
                                  "warnings": notes}))


def engine_marker(source: str) -> str | None:
    """'blender' when the generator's first line (after a shebang, if any) is the engine
    marker, else None. Selection is explicit (--engine) or by this marker, never guessed from
    imports. A UTF-8 BOM is tolerated."""
    try:
        with open(source, encoding="utf-8-sig", errors="replace") as f:
            first = f.readline().strip()
            if first.startswith("#!"):
                first = f.readline().strip()
    except OSError:
        return None
    return "blender" if first == BLENDER_MARKER else None


def blender_command(exe, source, params_file, out_dir, parts, blend=None):
    """The blender binary command line: background, factory start-up, a non-zero exit on a
    Python exception, the engines folder and the generator's folder on sys.path, then the
    generator with its own arguments after `--`. `blend` is only for a new, explicitly named
    file; without it the generator rewrites its working copy `<out>/<generator>.blend`."""
    expr = ("import sys; sys.path[:0] = [%r, %r]" % (os.path.dirname(os.path.abspath(source)), ENGINES_DIR))
    cmd = [exe, "--background", "--factory-startup", "--python-exit-code", "1",
           "--python-expr", expr, "--python", os.path.abspath(source), "--",
           "--params", params_file, "--out", os.path.abspath(out_dir)]
    if parts:
        cmd += ["--only", ",".join(parts)]
    if blend:
        cmd += ["--blend", blend]
    return cmd


def bpy_command(python, source, params_file, out_dir, parts, blend=None):
    """The same generator under a Python that has the bpy module."""
    cmd = [python, os.path.abspath(source), "--", "--params", params_file, "--out", os.path.abspath(out_dir)]
    if parts:
        cmd += ["--only", ",".join(parts)]
    if blend:
        cmd += ["--blend", blend]
    return cmd


def choose_blender(blender_python=None):
    """How a Blender generator or render runs, the same choice `detect` reports as usable:
    {"mode": "binary", "exe", "info"} for a 4.5+ binary, else {"mode": "bpy", "python", "info"}
    for a 4.5+ bpy module (--blender-python skips the binary), plus "skipped": why an unusable
    binary was passed over. Raises RuntimeError with every reason when neither works."""
    reasons = []
    exe = None if blender_python else find_blender()
    if exe:
        info = blender_info(exe)
        why = info.get("error") or too_old(info["version"])
        if not why:
            return {"mode": "binary", "exe": exe, "python": None, "info": info, "skipped": []}
        reasons.append(f"Blender binary {exe}: {why}")
    probe = bpy_info(blender_python)
    if probe and "error" not in probe:
        why = too_old(probe["version_tuple"])
        if not why:
            return {"mode": "bpy", "exe": None, "python": probe["python"], "info": probe, "skipped": reasons}
        reasons.append(f"bpy module in {probe['python']}: {why}")
    else:
        reasons.append("`import bpy` failed in " + ", ".join(bpy_pythons(blender_python))
                       + ((": " + probe["error"]) if probe else ""))
    if exe:
        head = "Blender not usable: "
    elif blender_python:
        head = "Blender not found: "
    else:
        head = "Blender not found: no `blender` binary on PATH or in the usual folders (set BLENDER=/path), and "
    raise RuntimeError(head + "; ".join(reasons)
                       + ". Install Blender 4.5 LTS or newer, or `pip install bpy` into that Python (--blender-python)")


def build_blender(source, params, parts, out_dir, timeout, blender_python=None):
    """Run a Blender generator in the binary (first) or the bpy module, read its @@3DPS line.
    The .blend is the generator's own default, `<out>/<generator>.blend`: the working copy it
    rewrites on every build (an explicit --blend would be a new file and refused on a rebuild)."""
    chosen = choose_blender(blender_python)
    mode, exe, python, info = chosen["mode"], chosen["exe"], chosen["python"], chosen["info"]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(engine_params(params), f)
        ptmp = f.name
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")   # no __pycache__ in the project
    if mode == "binary":
        cmd = blender_command(exe, source, ptmp, out_dir, parts)
    else:
        cmd = bpy_command(python, source, ptmp, out_dir, parts)
        env["PYTHONPATH"] = os.pathsep.join(p for p in (ENGINES_DIR, env.get("PYTHONPATH")) if p)
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env, **TEXT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Blender ({mode}) timed out after {timeout}s")
    finally:
        os.unlink(ptmp)
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("@@3DPS ")]
    if r.returncode != 0 or not lines:
        tail = "\n".join(ln for ln in (r.stdout + r.stderr).splitlines()
                         if ln.strip() and not ln.startswith("EGL Error"))[-2500:]
        raise RuntimeError(f"Blender generator failed ({mode}, exit {r.returncode}):\n{tail}")
    rep = json.loads(lines[-1][len("@@3DPS "):])
    seconds = round(time.time() - t0, 2)
    results = [{"name": p["name"], "stl": p["stl"], "seconds": p.get("seconds", seconds),
                "engine_warnings": [p["warning"]] if p.get("warning") else []} for p in rep["parts"]]
    sources = sorted(set(rep.get("deps", [])) | {os.path.abspath(source)})
    engine_info = {"blender": rep.get("blender") or info.get("version"), "mode": mode,
                   "boolean_solver": rep.get("solver"), "blend": rep.get("blend"),
                   "notes": [f"{why}; used the bpy module instead" for why in chosen["skipped"]] + rep.get("notes", [])}
    if mode == "binary":
        engine_info["path"] = exe
    else:
        engine_info["python"] = python
    return results, sources, engine_info


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


def _unjudge_partial(rep: dict, info: dict) -> None:
    """An object built only in part (--only): what the subset cannot decide becomes UNVERIFIED.
    A verdict the built parts reach on their own stays: D2 FAIL (the whole is larger still),
    A1 / A2 FAIL on an overlap or a contact between built parts. A PASS, a WARN, P1 and P2 (the
    subset's lowest face is not the bed) and A1 "touches nothing" need the missing parts."""
    why = (f"object built in part with --only ({len(info['built'])} of {info['total']} parts, "
           f"missing {', '.join(info['missing'])})")
    for cid, ck in rep["checks"].items():
        if cid == "D2" and ck["state"] == "FAIL":
            continue
        ck.update(state="UNVERIFIED", note=f"{why}: {ck.get('note') or 'not judged on the subset'}")
        ck.pop("return_to", None)
    for pr in rep["parts"].values():
        for cid, ck in pr["checks"].items():
            definite = ck["state"] == "FAIL" and ("overlap" in ck.get("note", "") or "touches or" in ck.get("note", ""))
            if not definite:
                ck.update(state="UNVERIFIED", note=f"{why}: {ck.get('note') or 'not judged on the subset'}")
                ck.pop("return_to", None)
    rep["warnings"] = [w for w in rep["warnings"] if " P1: " not in w and " P2: " not in w
                       and " A1: " not in w and " A2: " not in w]


def _fail_lines(who: str, checks: dict) -> list[str]:
    """One line per hard FAIL, '<part> <check> FAIL: <note>', for the top-level errors list:
    a part's D1 or M5, an object's D2, a fused part's A1 (soft checks only WARN, G8)."""
    return [f"{who} {cid} FAIL" + (f": {ck['note']}" if ck.get("note") else "")
            for cid, ck in checks.items() if ck.get("state") == "FAIL" and ck.get("kind") == "hard"]


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
    # record (S3-1): a part whose earlier manifest describes this very STL keeps it. A fresh one
    # is the better record (that engine, that part's own sources); a stale one must not be
    # re-stamped, which would bless an STL its own generator no longer produces.
    prior = {p["stl"]: p.pop("_prior") for p in parts if p.get("_prior")}
    stale = {stl: pr for stl, pr in prior.items() if not pr["fresh"]}
    by = "record" if getattr(args, "cmd", None) == "record" else "run"
    for p in sane:
        if p["stl"] not in prior:
            validate.write_manifest(p["stl"], sources, params, engine, by=by)

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

    # Objects with some of their parts built (--only, S3-5): no core 3MF item, the subset would
    # be dropped onto the bed where the missing parts should carry it.
    partial = getattr(args, "partial_objects", None) or {}
    partial_parts = {n for g in groups if g["name"] in partial for n in g["parts"]}
    for g in groups:
        info = partial.get(g["name"])
        if info:
            out["warnings"].append(f"object '{info['object']}': built {len(info['built'])} of {info['total']} parts with "
                                   f"--only (missing: {', '.join(info['missing'])}); the whole object is not judged "
                                   "(D2 / P1 / P2 and A1 / A2 UNVERIFIED unless the built parts fail on their own) "
                                   "and it gets no core 3MF item; place the test print in the slicer")
    whole = [p for p in sane if p["name"] not in partial_parts]
    if not args.no_3mf and sane and not whole:
        out["warnings"].append("core 3MF not written: every part belongs to an object built only in part (--only)")
    if not args.no_3mf and whole:
        stem = getattr(args, "threemf_stem", None) or os.path.splitext(os.path.basename(args.source_main))[0]
        name = args.threemf or stem + ".3mf"
        path = os.path.join(args.out, name)
        try:
            # out/ is the build's working folder: this file is rewritten on every build.
            placed = threemf.write_core_3mf([(p["name"], p["stl"]) for p in whole], path,
                                            bed=usable_bed(args), objects=[g for g in groups if g["name"] not in partial])
            out["threemf"] = path
            for p in whole:
                p["rotation_deg"] = placed[p["name"]]["rotation_deg"]
                if p["rotation_deg"]:
                    out["warnings"].append(f"{p['name']}: placed rotated {p['rotation_deg']} deg in the 3MF "
                                           "so it fits the bed (the STL itself is unchanged)")
        except (validate.ArtifactError, OSError) as exc:
            out["errors"].append(f"core 3MF not written: {exc}")

    reports = []
    for p in sane:
        own = stale.get(p["stl"])
        rep = validate_part(p["stl"], specs.get(p["name"], {}), sources, params_path, args)
        if own:
            for f in rep.get("files", []):
                if "checks" in f:
                    f["checks"]["R3"] = validate.chk(
                        "FAIL", "hard", {"manifest_engine": own["engine"], "manifest_sources": own["names"]},
                        own.get("why") or
                        f"STALE: the manifest of the {own['engine']} build that made this STL does not match its "
                        f"sources ({', '.join(own['names']) or 'none recorded'}) and the current parameters; record did "
                        "not re-stamp it. Rebuild this part with build.py run, then record again", return_to="current")
            rep["gate"] = validate.gate_of(rep.get("files", []))
        p["validate"] = rep
        reports.append(rep)
        # Lift the validator's own errors and warnings, and every hard FAIL as one line, so the
        # two top-level lists are enough to read; nothing stays hidden in parts[].validate.
        out["errors"] += [f"{p['name']}: {e}" for e in rep.get("errors", [])]
        for f in rep.get("files", []):
            out["errors"] += _fail_lines(p["name"], f.get("checks", {}))
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
                    if g["name"] in partial:
                        _unjudge_partial(rep, partial[g["name"]])
                    entry.update(checks=rep["checks"], metrics=rep["metrics"], rotation_deg=rep["rotation_deg"],
                                 method=rep["method"], gate=assembly.object_gate(rep))
                    if g["name"] in partial:
                        entry["partial"] = partial[g["name"]]
                    for n, pr in rep["parts"].items():
                        by_name[n]["assembly"] = {"object": g["name"], "role": pr["role"], "checks": pr["checks"]}
                    out["warnings"] += [f"object '{g['name']}': {w}" for w in rep["warnings"]]
                    out["errors"] += _fail_lines(f"object '{g['name']}'", rep["checks"])
                    for n, pr in rep["parts"].items():
                        out["errors"] += _fail_lines(n, pr["checks"])
            else:
                entry["gate"] = "FAIL"
            object_gates.append(entry["gate"])
        elif g["name"] in partial:
            # One part of a larger object built alone (--only): its own checks stand, but the
            # object it belongs to is not judged, as for a subset of several parts (review N6).
            own = by_name[g["parts"][0]].get("validate", {}).get("gate")
            entry.update(partial=partial[g["name"]], gate="FAIL" if own == "FAIL" or g["parts"][0] not in sane_names
                         else "INCOMPLETE")
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
        if engine == "python" and engine_marker(source) == "blender":
            engine = "blender"
        if not engine:
            raise ValueError("cannot infer engine from file extension; pass --engine")
    stem = os.path.splitext(os.path.basename(source))[0]
    specs = part_specs(params, stem)
    only_notes = []
    args.partial_objects = {}
    if args.only is not None:
        wanted = [n.strip() for n in args.only.split(",") if n.strip()]
        if not wanted:
            raise ValueError("--only names no part; give a comma list of _parts names")
        unknown = [n for n in wanted if n not in specs]
        if unknown:
            raise ValueError(f"--only names parts that are not in _parts: {unknown} (known: {list(specs)})")
        full = specs
        specs = {n: dict(spec or {}) for n, spec in full.items() if n in wanted}      # _parts order, not --only order
        def object_of(m):
            return (full.get(m) or {}).get("object") or m
        for n, spec in specs.items():
            obj = spec.get("object")
            if obj and not any(m != n and object_of(m) == obj for m in specs):
                spec.pop("object", None)
                spec.pop("role", None)
                only_notes.append(f"{n}: built alone with --only, the other parts of object '{obj}' were not; "
                                  "object checks (A1 / A2, D2 of the whole) skipped")
        # An object with some but not all of its parts built (S3-5): its checks cannot judge the
        # whole, and a core 3MF item would drop the subset onto the bed. Keyed as finish() groups
        # them: the object's name, or the part's own name for a part built alone.
        for obj in dict.fromkeys(object_of(m) for m in full):
            members = [m for m in full if object_of(m) == obj]
            built = [m for m in members if m in specs]
            if 0 < len(built) < len(members):
                info = {"object": obj, "built": built, "missing": [m for m in members if m not in built],
                        "total": len(members)}
                args.partial_objects[built[0] if len(built) == 1 else obj] = info
    os.makedirs(args.out, exist_ok=True)
    out = {"schema": SCHEMA, "ran": True, "engine": engine, "source": source, "gate": None,
           "warnings": [], "errors": []}
    try:
        if engine == "openscad":
            parts, sources, info = build_openscad(source, params, list(specs), args.out, args.timeout)
        elif engine == "python":
            parts, sources, info = build_python(source, params, list(specs), args.out, args.timeout)
        elif engine == "blender":
            parts, sources, info = build_blender(source, params, list(specs), args.out, args.timeout,
                                                 getattr(args, "blender_python", None))
        else:
            raise ValueError(f"engine '{engine}' is not run by build.py; use 'record' for Fusion")
    except RuntimeError as exc:
        out.update(ran=False, gate="FAIL", R4="FAIL")
        out["errors"].append(str(exc))
        return out
    out["warnings"] += info.pop("warnings", [])
    out["engine_info"] = info
    args.source_main = source
    out = finish(out, parts, sources, params, args.params, specs, args, engine)
    if engine == "blender" and info.get("blend"):
        out["blend"] = info["blend"]
    out["warnings"] += only_notes
    out["seconds"] = round(time.time() - t0, 2)
    return out


def _resolve_source(name: str, given: list[str]) -> str | None:
    """The file a manifest's recorded source name (a base name) stands for: a --source of that
    name, else a file of that name next to one of them, in the skill's own library folders
    (blender_builder.py, parts.py, sdf.py) or in the working directory."""
    for s in given:
        if os.path.basename(s) == name:
            return s
    folders = [os.path.dirname(s) for s in given] + [ENGINES_DIR, HERE, os.getcwd()]
    for folder in folders:
        cand = os.path.join(folder, name)
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    return None


def _library_name(name: str) -> bool:
    """A source name that is one of the skill's own library files (blender_builder.py, parts.py,
    sdf.py, ...), shared by every generator: it says nothing about which generator built a part."""
    return any(os.path.isfile(os.path.join(folder, name)) for folder in (ENGINES_DIR, HERE))


def prior_manifest(stl: str, given: list[str], params: dict) -> tuple[dict | None, list[str]]:
    """What `run` recorded for this STL, when its manifest describes this very file
    (artifact_sha256 matches) and `run` wrote it: {"engine", "names", "sources" (resolved paths),
    "fresh", "why"} and the notes to lift. `fresh` is that manifest's own verdict against its
    recorded sources and the current parameters; a source that cannot be found makes it not
    fresh, and so does a manifest none of whose generators is among --source (a renamed or newer
    generator that never built this STL). A manifest `record` wrote (or one from before 0.5,
    without "by") is not kept: record re-stamps it, as an STL exported elsewhere has no other
    word on it. None when there is no manifest to keep."""
    mf = validate.manifest_path(stl)
    if not os.path.isfile(mf):
        return None, []
    try:
        with open(mf, encoding="utf-8") as f:
            man = json.load(f)
        if not isinstance(man, dict) or man.get("artifact_sha256") != validate.file_sha256(stl):
            return None, []
    except (OSError, json.JSONDecodeError, ValueError):
        return None, [f"{os.path.basename(stl)}: its manifest could not be read; a new one is written"]
    if man.get("by") != "run":
        return None, []
    names = [str(n) for n in (man.get("sources") or [])]
    resolved, notes = [], []
    for n in names:
        path = _resolve_source(n, given)
        if path:
            resolved.append(path)
        else:
            notes.append(f"{os.path.basename(stl)}: its manifest names the source {n!r}, which is not among --source "
                         "and was not found next to them; pass it with --source, or rebuild the part")
    fresh = bool(names) and len(resolved) == len(names) and man.get("input_hash") == validate.hash_inputs(resolved, params)
    why = None
    generators = [n for n in names if not _library_name(n)]
    given_names = {os.path.basename(s) for s in given}
    if generators and not given_names.intersection(generators):
        fresh = False
        why = (f"STALE: {os.path.basename(stl)} was built from {', '.join(generators)}, not from the given "
               f"--source ({', '.join(sorted(given_names))}); rebuild it from the generator you mean, then record again")
    return ({"engine": man.get("engine") or "unknown", "names": names, "sources": resolved, "fresh": fresh, "why": why},
            notes)


def threemf_stem(objects: list[str]) -> str:
    """The core 3MF's name for `record`: the object (one), the objects joined, or the first
    and a count when that would be long; never the first source's name (S3-15)."""
    joined = "_".join(objects)
    return objects[0] if len(objects) == 1 else joined if len(joined) <= 60 else f"{objects[0]}_and_{len(objects) - 1}_more"


def cmd_record(args) -> dict:
    t0 = time.time()
    params = load_params(args.params)
    missing = [s for s in args.source if not os.path.isfile(s)]
    if missing:
        raise ValueError(f"source not found: {missing}")
    specs = part_specs(params, "part")
    given = [os.path.abspath(s) for s in args.source]
    out = {"schema": SCHEMA, "ran": True, "engine": args.engine, "source": args.source[0], "gate": None,
           "warnings": [], "errors": []}
    parts, extra = [], set()
    for stl in args.stl:
        name = os.path.splitext(os.path.basename(stl))[0]
        part = {"name": name, "stl": stl, "engine_warnings": []}
        # An STL that `run` already described: its manifest's own freshness decides whether it may
        # be re-stamped, and its sources join the freshness hash (S3-1, S3-2). A manifest an earlier
        # record wrote is no such word and is re-stamped (review B1).
        prior, notes = prior_manifest(stl, given, params)
        out["warnings"] += notes
        if prior:
            extra.update(prior["sources"])
            part["prior_manifest"] = {"engine": prior["engine"], "sources": prior["names"], "fresh": prior["fresh"]}
            part["_prior"] = prior                             # finish() keeps it; a stale one is an R3 FAIL
        parts.append(part)
        specs.setdefault(name, {})
    os.makedirs(args.out, exist_ok=True)
    args.source_main = args.source[0]
    try:
        objects = [g["name"] for g in assembly.group_parts({p["name"]: specs.get(p["name"], {}) for p in parts})]
    except assembly.AssemblyError:                            # finish() reports it; the file is named after the parts
        objects = [p["name"] for p in parts]
    args.threemf_stem = threemf_stem(objects)
    sources = sorted(set(given) | extra, key=lambda s: (os.path.basename(s), s))
    out = finish(out, parts, sources, params, args.params, specs, args, args.engine)
    out["seconds"] = round(time.time() - t0, 2)
    return out


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
  threemf   core 3MF written in --out;  warnings / errors: read these two lists first (every
            hard FAIL of a part, object or assembly check is one line in errors)
Full description: references/parts.md. Exit 0 = ran (read gate), 1 = build or usage error."""


def _common(p):
    p.add_argument("--params", help="params.json: _parts (expect, object, role), engine parameters")
    p.add_argument("--out", default="out", help="working folder, rewritten on every build (default out)")
    p.add_argument("--3mf", dest="threemf", help="3MF file name (default: run: <source>.3mf; record: <object>.3mf)")
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
    det = sub.add_parser("detect", help="Phase 0 probe: OpenSCAD (and its Manifold backend), manifold3d, Blender "
                                        "(binary or bpy module), optional libraries")
    det.add_argument("--blender-python", help="Python interpreter to probe for the bpy module (default: BLENDER_PYTHON, "
                                              "then this one)")
    r = sub.add_parser("run", help="build every part of _parts with OpenSCAD (.scad), Python (.py) or Blender "
                                   "(.py with the engine marker), then validate",
                       epilog=OUTPUT_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    r.add_argument("source", help="generator: model.scad or model.py")
    r.add_argument("--engine", default="auto", choices=["auto", "openscad", "python", "blender"],
                   help="auto: .scad -> openscad, .py -> python, or blender when the first line is "
                        f"'{BLENDER_MARKER}'")
    r.add_argument("--blender-python", help="run a Blender generator with this Python's bpy module instead of the binary")
    r.add_argument("--timeout", type=int, default=900, help="seconds per generator run (default 900)")
    r.add_argument("--only", help="build only these _parts (comma list), e.g. the mechanism and the bit of its mating "
                                  "part it needs, for a test print before the full part")
    _common(r)
    rec = sub.add_parser("record", help="record STLs built elsewhere (Fusion, a live Blender): manifests, core 3MF, "
                                        "validation",
                         epilog=("Each STL is one part named after its file (out/lid.stl -> part 'lid'); with\n"
                                 "--params the names match _parts and parts grouped there form objects.\n\n"
                                 + OUTPUT_HELP),
                         formatter_class=argparse.RawDescriptionHelpFormatter)
    rec.add_argument("stl", nargs="+", help="one STL per part, exported in print orientation (mm)")
    rec.add_argument("--source", nargs="+", required=True,
                     help="the generator script(s) that built the STLs; hashed with --params for freshness (R3)")
    rec.add_argument("--engine", default="fusion", help="engine name written to the manifests (default fusion; "
                                                        "blender for STLs exported from a live Blender)")
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
