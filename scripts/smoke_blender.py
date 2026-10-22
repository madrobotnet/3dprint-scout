#!/usr/bin/env python3
"""Exercise an installed Blender binary: boolean geometry, STL, .blend reopening and PNG.

Run with the host Python (numpy installed), not Blender's Python. The explicit binary must
be 4.5 or newer; a bpy fallback is an error. Writes only to a new --out directory.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import build


GENERATOR = '''# 3dprint-scout: engine=blender
import blender_builder as bb

PARAMETERS = {"width": 20.0, "depth": 16.0, "height": 6.0, "hole_radius": 2.0}

def build(p):
    body = bb.box([p["width"], p["depth"], p["height"]], "body")
    hole = bb.cylinder(p["hole_radius"], p["height"] + 2.0, name="cutter")
    hole.location = (p["width"] / 2, p["depth"] / 2, -1.0)
    bb.boolean(body, hole, "difference")
    bb.part(body, "body")
    return {"body": body}

if __name__ == "__main__":
    bb.main(build, PARAMETERS)
'''


def run_json(command, cwd, env, log_name):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                            encoding="utf-8", errors="replace", timeout=300)
    (cwd / (log_name + ".stdout.log")).write_text(result.stdout, encoding="utf-8")
    (cwd / (log_name + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{log_name} exited {result.returncode}: {result.stdout[-1500:]} {result.stderr[-1500:]}")
    return json.loads(result.stdout)


def smoke(executable, output):
    executable = str(Path(executable).resolve())
    info = build.blender_info(executable)
    problem = info.get("error") or build.too_old(info.get("version"))
    if problem or not info.get("version"):
        raise RuntimeError(f"explicit Blender binary is not usable: {problem or 'unknown version'}")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "smoke.py").write_text(GENERATOR, encoding="utf-8")
    (output / "params.json").write_text(json.dumps({"_parts": {"body": {"expect": [20, 16, 6]}}}), encoding="utf-8")
    printer = {"schema": "3dprint.printers/1", "default": "smoke", "printers": {
        "smoke": {"process": "fdm", "bed": {"area": [[0, 0], [100, 0], [100, 100], [0, 100]],
                                              "height": 100, "source": "smoke fixture"}}}}
    (output / "printers.json").write_text(json.dumps(printer), encoding="utf-8")
    env = dict(os.environ, BLENDER=executable)
    scripts = Path(__file__).resolve().parent
    built = run_json([sys.executable, str(scripts / "build.py"), "run", "smoke.py",
                      "--params", "params.json", "--printer", "printers.json", "--out", "out",
                      "--no-wall-check", "--no-3mf"], output, env, "build")
    if built.get("gate") != "PASS" or built.get("engine_info", {}).get("mode") != "binary":
        raise RuntimeError(f"binary build did not pass: {built}")
    metrics = built["parts"][0]["validate"]["files"][0]["metrics"]
    expected_volume = 20 * 16 * 6 - math.pi * 2 ** 2 * 6
    if abs(metrics["volume_mm3"] - expected_volume) > 0.5:
        raise RuntimeError(f"boolean hole volume is wrong: {metrics['volume_mm3']} mm3")
    blend = output / built["blend"]
    if not blend.is_file() or not blend.stat().st_size:
        raise RuntimeError("build did not write a nonempty .blend")
    # Reopen the delivered scene in a separate, factory-startup binary process.
    code = ("import bpy; "
            f"bpy.ops.wm.open_mainfile(filepath={str(blend)!r}); "
            "assert any(o.type == 'MESH' for o in bpy.data.objects), 'no saved mesh'; "
            "print('SCOUT_BLEND_REOPENED')")
    reopened = subprocess.run([executable, "--background", "--factory-startup", "--python-exit-code", "1",
                               "--python-expr", code], cwd=output, env=env, capture_output=True,
                              encoding="utf-8", errors="replace", timeout=120)
    (output / "reopen.log").write_text(reopened.stdout + reopened.stderr, encoding="utf-8")
    if reopened.returncode or "SCOUT_BLEND_REOPENED" not in reopened.stdout:
        raise RuntimeError(f".blend reopen failed: {reopened.stdout[-1000:]} {reopened.stderr[-1000:]}")
    rendered = run_json([sys.executable, str(scripts / "render.py"), "out/body.stl", "-o", "out/preview.png",
                         "--size", "640x480"], output, env, "render")
    if not rendered.get("sane") or "(binary)" not in rendered.get("renderer", ""):
        raise RuntimeError(f"binary render did not pass: {rendered}")
    return {"passed": True, "blender": info["version"], "mode": "binary", "gate": built["gate"],
            "blend_reopened": True, "render_sane": rendered["sane"], "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", required=True, help="path to a real Blender 4.5+ executable")
    parser.add_argument("--out", required=True, help="new directory for artifacts and logs; refuses overwrite")
    args = parser.parse_args()
    try:
        report = smoke(args.blender, args.out)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
