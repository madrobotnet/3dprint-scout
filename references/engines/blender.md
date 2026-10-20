# Blender engine (binary, `bpy` module, or a live Blender)

Read this right before Phase 3 when Phase 0 found Blender and the shape is organic, freeform,
sculpted or decorative (rule A in SKILL.md). Blender is never used for a dimension-critical
fit: those go to Fusion, OpenSCAD or Python as before, and a mixed part gets its mechanical
body there and its decorative part here, as a separate `_parts` entry of the same object.

Contents:

- [What it gives and what it costs](#what-it-gives-and-what-it-costs)
- [Three ways it runs](#three-ways-it-runs)
- [The helper module (`blender_builder.py`, next to this file)](#the-helper-module-blender_builderpy-next-to-this-file)
- [Generator script rules](#generator-script-rules)
- [Units, export, validation](#units-export-validation)
- [Booleans](#booleans)
- [Live session: keep the user's file safe](#live-session-keep-the-users-file-safe)
- [Renders](#renders)
- [Pitfalls](#pitfalls)
- [Still to confirm](#still-to-confirm)

## What it gives and what it costs

Blender adds what the other engines lack on a freeform body: real fillets and chamfers on any
edge (the Bevel modifier), robust booleans (the Manifold solver from Blender 4.5, the same
library as `manifold3d`; the Exact solver before), text in any font, and renders that look like
the printed part. It costs the parametric history: the result is a mesh in an editable `.blend`
(meshes, collections per object, the parameters as custom properties on a `PARAMETERS` empty),
not CAD. Tell the user that in one line before building. The generator script stays the source
of truth: editing the `.blend` by hand is fine for a look, the next rebuild comes from the script.

Blender 4.2 or newer (`wm.stl_export`); 4.5 or newer for the Manifold solver. Older versions
fail with a clear error from `blender_builder.require_blender()`.

## Three ways it runs

All three run the **same generator script**; only the launcher differs.

1. **Binary** (a `blender` executable on the machine the agent runs on). `build.py run` finds it
   (PATH, `BLENDER=/path`, the usual install folders) and runs

   ```bash
   python3 "$SKILL_DIR/scripts/build.py" run model_blender.py --params .3dprint/params.json --out out \
     --printer .3dprint/printers.json --tools 0
   ```

   which executes `blender --background --factory-startup --python-exit-code 1 --python-expr
   "<sys.path for the engines folder and the generator's>" --python model_blender.py --
   --params <engine params> --out out --blend out/model_blender.blend` with the usual
   `--timeout`. The first line of the generator, `# 3dprint-scout: engine=blender`, picks the
   engine (or pass `--engine blender`); nothing is guessed from imports.
2. **`bpy` module** (no binary, but `import bpy` works in some Python). The same command runs the
   generator with that Python instead, `references/engines` on `PYTHONPATH`; `build.py` tries the
   binary first, then `--blender-python PATH`, `BLENDER_PYTHON`, and the Python running
   `build.py`. `--blender-python` forces this path. In a disposable sandbox `pip install bpy`
   (one line to the user: it is a few hundred MB) into the Python of the matching version is fine;
   on the user's machine, ask first.
3. **Live Blender** (an MCP connector to the user's own Blender; Phase 0 found a tool that runs
   Python there and answered `bpy.app.version_string`). Prefer the tool that runs code in a
   **background Blender process** when the server has one (the official Blender Lab server calls
   them `execute_blender_code_for_cli` and the like; names differ between servers). Send
   `blender_builder.py` and the generator to a folder on the user's machine (a new name per
   version and an md5 check, as `fusion.md`, "Sending scripts"), then run a loader that gives the
   generator its command line:

   ```python
   import runpy, sys
   folder = r"<folder you sent the files to>"
   saved_argv, saved_path = sys.argv, list(sys.path)
   sys.path.insert(0, folder)
   sys.argv = ["blender", "--", "--params", folder + "/params.json", "--out", folder + "/out"]
   try:
       runpy.run_path(folder + "/model_blender.py", run_name="__main__")
   finally:
       sys.argv, sys.path[:] = saved_argv, saved_path          # leave the session as found
   ```

   The generator writes the STLs and the `.blend` into `--out`; print the `@@3DPS` line it ends
   with (sizes, solver, notes). Then record and validate like Fusion's parts:

   ```bash
   python3 "$SKILL_DIR/scripts/build.py" record out/body.stl out/label.stl --engine blender \
     --source model_blender.py "$SKILL_DIR/references/engines/blender_builder.py" \
     --params .3dprint/params.json --printer .3dprint/printers.json
   ```

   Show the result in the user's open Blender **only when they ask**, and then as below
   ("Live session"). A tool that only runs code in the open session (no background twin) is used
   the same way; `blender_builder.new_scene_mm()` then builds into a scene of its own.

## The helper module (`blender_builder.py`, next to this file)

`import blender_builder as bb` (build.py puts this folder on the path; in a live session the file
sits next to the generator). Millimetres everywhere, Z-up, Z = 0 on the bed.

| Call | Does |
|---|---|
| `bb.main(build, PARAMETERS)` | The runner: command line (`--params`, `--out`, `--only`, `--blend`, `--no-blend`), fresh scene, `build(p)`, parameters → custom properties, one STL per part, the `.blend`, the `@@3DPS` line. The generator ends with it |
| `bb.new_scene_mm()` | A scene at 1 unit = 1 mm (`METRIC`, `scale_length` 0.001, `MILLIMETERS`); empties the session only in a background run with no file open, otherwise its own scene |
| `bb.box(size, name)`, `bb.cylinder(r, h, segments, name)`, `bb.prism(outline, height, name, z0)`, `bb.ring(r_in, r_out, h, segments, name, z0)` | Primitives on the bed (box corner at the origin; cylinder and ring on the Z axis; outline as `[(x, y), ...]`) |
| `bb.mesh_object(name, bmesh)` | Any bmesh you build yourself, linked and tagged |
| `bb.bevel(obj, width, segments=None, angle=30, bed=False)` | Real fillets on every edge sharper than `angle`, except edges on the bed; `segments` default one per line width along the arc; refuses a result with zero-area faces instead of welding it. `bb.chamfer(obj, width)` is the one-segment case |
| `bb.bed_chamfer(obj, height=0.4)` | The elephant-foot chamfer, cut into the bottom edges (P6), slightly steeper than 45° so P2 never counts it |
| `bb.boolean(target, tool, "difference" \| "union" \| "intersect")`, `bb.join(target, *tools)` | Boolean modifier, Manifold solver on 4.5+, Exact before; checks both inputs and the result are manifold; applied, the tool removed (`apply=False` keeps it live, tool hidden) |
| `bb.text(string, height, depth, font=None, align="CENTER")` | Letters as one welded mesh standing on z = 0, `height` the **cap height**, Blender's built-in font or a font file (`bb.load_font` packs it into the `.blend` under its base name) |
| `bb.part(obj, name, object=None, role=None)` | Registers the part: object renamed, moved into the collection of its object (one collection per `_parts` object), `role` kept as a property |
| `bb.params_to_props(p)` | The parameters on a `PARAMETERS` empty (numbers, strings, lists; anything else as JSON text) |
| `bb.export_parts(out, names=None)` | One binary STL per part, modifiers applied, `global_scale` 1, scene unit off, axes unchanged; returns boxes in mm, triangles, bytes |
| `bb.save_blend(path, overwrite=False)` | The scene's data-blocks only (no UI, no preferences, no window state) via `bpy.data.libraries.write`; fonts and images packed and renamed to `//<name>`; refuses an existing path; scans the bytes for this machine's folders and deletes the file on a hit |
| `bb.render_views(out, views, colors, engine="workbench", size)` | The preview grid (iso, front, right, top, as `preview.py`), see "Renders" |
| `bb.world_bbox(obj)`, `bb.nonmanifold_edges(obj)`, `bb.LOG` | Numbers to assert on inside `build`, and the notes the runner prints |

Run as a script (`blender_builder.py -- render a.stl b.stl -o out.png`) it renders STLs;
`scripts/render.py` is the front end.

## Generator script rules

```python
# 3dprint-scout: engine=blender
import blender_builder as bb

PARAMETERS = {"w": 40.0, "d": 30.0, "h": 6.0, "fillet": 1.5, "label": "A"}   # mm, source per value

def build(p):
    body = bb.box([p["w"], p["d"], p["h"]], "body")
    bb.bevel(body, p["fillet"])                     # fillets first
    hole = bb.cylinder(3.0, p["h"] + 2, name="hole"); hole.location = (8, 8, -1)    # overshoot
    bb.boolean(body, hole, "difference")            # cuts after
    bb.bed_chamfer(body, 0.4)                       # the bed edge last
    mark = bb.text(p["label"], height=6.0, depth=0.8)
    mark.location = (p["w"] / 2, p["d"] / 2, p["h"])          # on the top face
    bb.part(body, "body")
    bb.part(mark, "label", object="body", role="fused")
    return {"body": body, "label": mark}

if __name__ == "__main__":
    bb.main(build, PARAMETERS)
```

- The first line is the engine marker. `PARAMETERS` holds every dimension with its source;
  `params.json` overrides by key (keys starting with `_` never arrive).
- `build(p)` returns `{part_name: Object}`, names exactly as `_parts`; parts of one object share
  a frame, so the STLs hold the assembled positions (`parts.md`).
- Rebuilt from scratch on every run: never read state from a previous run or from the file.
- Order: fillets, then cuts, then the bed chamfer. A bevel that meets another feature closer than
  its width is clamped into slivers; `bb.bevel` refuses such a mesh with a message rather than
  welding it (never paper over a failure).
- Assert derived sizes (`raise ValueError(...)`) so an impossible combination stops the build
  with a readable message, as the coaster example does for its text width.
- Allowed inside a generator: `bpy`, `bmesh`, `mathutils`, the standard library. **Not allowed**:
  writing outside `--out`, the network, `subprocess` / `os.system`, deleting anything, and
  anything that touches the user's file (below). The official MCP server runs code without
  guards, so a generator must be safe to run blind.

## Units, export, validation

1 Blender unit = 1 mm (`new_scene_mm`). STLs are exported with modifiers applied, triangulated
by Blender, `global_scale=1.0`, `use_scene_unit=False`, forward Y / up Z, so a 10 mm cube
arrives as a 10 mm STL (a test checks it). Validation is unchanged and authoritative:
`build.py` runs `validate.py` on the exported STLs (D1–D4, M1–M5, P1–P3, A1/A2, objects);
nothing Blender reports about sizes is trusted, and a mesh Blender shows as closed can still
fail M1 after export, so read the build's `warnings` and `errors` first. D4 reports a 1000×
error when the scene was left at metres: call `new_scene_mm` (the runner does) and never
scale an exported mesh.

## Booleans

`bb.boolean` picks the Manifold solver on Blender 4.5+ and the Exact solver before, and says
which ran in `LOG` (`build.py` repeats it in `engine_info.boolean_solver`). Both need closed
input: the call refuses a tool or target with non-manifold edges, and refuses a result that
came out open (usually a tool that ends exactly on a face: overshoot cutters by 0.01–0.1 mm).
Letters are separate bodies until they sit on a face: emboss with `boolean(disc, text,
"union")` or place the text as a `fused` part.

## Live session: keep the user's file safe

- **Never** `wm.read_homefile`, `wm.read_factory_settings`, `wm.open_mainfile`, `wm.save_mainfile`,
  `wm.save_as_mainfile` without `copy=True`, `wm.quit_blender`, or delete anything you did not
  create. `new_scene_mm` builds into a scene named `3dprint-scout` next to the user's and removes
  only objects it tagged on an earlier run; `save_blend` writes a new file from that scene's data
  and never touches theirs.
- Before opening a result in their Blender, read `bpy.data.is_dirty`; if true, ask ("your Blender
  has unsaved changes; save first, or shall I just add the result as a new scene?") and stop.
  Prefer appending (`bpy.ops.wm.append` of the `coaster` collection from `out/<name>.blend`
  into a new scene) over opening the file.
- Never install Blender add-ons or change preferences without asking.
- A tool call that times out: retry once, then treat Blender as unavailable for this run and
  say why (as for Fusion).

## Renders

When Blender is there, concept previews (Phase 1) and the delivery image can be Blender renders:

```bash
python3 "$SKILL_DIR/scripts/render.py" out/body.stl out/label.stl -o out/render.png --color "label=Jade White"
```

Workbench by default (headless, no GPU, a second or two), `--engine eevee` or `cycles` when
asked (slower). Part colours from `--color part=<filament name or #rrggbb>`: a small table of
common Bambu filament colours is built in, the user's AMS colours win when known, unnamed parts
take the palette; never ask about colours. Same views, grid and JSON as `preview.py`, same
`sane` check (exit 2 on a blank image). `preview.py` stays the fallback and the G4 check; the
numbers from `validate.py` stay the evidence.

## Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| D4 FAIL, everything 1000× too small or large | Scene units left at metres, or `use_scene_unit` on | `bb.new_scene_mm()`; export through `bb.export_parts` |
| `bevel ... made N zero-area triangles` | The bevel meets a chamfer, a cut or a dense outline closer than its width | Bevel first, cut and chamfer after; a smaller width; fewer outline points |
| M1 FAIL after a boolean | The tool ends exactly on a face, or the Exact solver on self-intersecting input | Overshoot by 0.01–0.1 mm; check `bb.nonmanifold_edges` on the inputs |
| M5 FAIL on text | Letters are separate bodies | Union them onto the face, or make the text a `fused` part |
| P3 WARN on text | Strokes thinner than 1.2 mm | Text follows the text rule (strokes ≥ 0.8 mm, `design.md`); say so, or a larger cap height |
| `import bpy` hangs or takes a minute | First import loads most of Blender | `build.py detect` probes it in a subprocess with a timeout; wait once |
| `EGL Error` lines in the output | Headless GPU context on Linux | Harmless: Workbench and Cycles still render; `build.py` drops those lines |
| `Blender ... is older than 4.2` | No `wm.stl_export` before 4.2 | Install a newer Blender, or `pip install bpy` (needs a matching Python) |
| The `.blend` save fails with "held a path of this machine" | A data-block still pointed at an absolute path | `bb.load_font` for fonts; no external images; nothing linked |

## Still to confirm

- The binary path on a real `blender` install (the exact flags come from the Blender manual's
  command-line page; here only the `bpy` module and an emulated binary ran).
- The live path on a real MCP server (which tool runs in the background, its timeouts).
- EEVEE in a headless Linux session (slow here: 37 s for a small scene; Workbench and Cycles
  take about a second).
