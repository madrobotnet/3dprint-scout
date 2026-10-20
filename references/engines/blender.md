# Blender engine (binary, `bpy` module, or a live Blender)

Read this right before Phase 3 when Phase 0 found Blender and the shape is organic, freeform,
sculpted or decorative (rule A in SKILL.md). Blender is never used for a dimension-critical
fit: those go to Fusion, OpenSCAD or Python as before, and a mixed part gets its mechanical
body there and its decorative part here, as a separate `_parts` entry of the same object
("Mixed parts" below).

Contents:

- [What it gives and what it costs](#what-it-gives-and-what-it-costs)
- [Three ways it runs](#three-ways-it-runs)
- [The helper module (`blender_builder.py`, next to this file)](#the-helper-module-blender_builderpy-next-to-this-file)
- [Generator script rules](#generator-script-rules)
- [Units, export, validation](#units-export-validation)
- [Booleans and text](#booleans-and-text)
- [Live session: keep the user's file safe](#live-session-keep-the-users-file-safe)
- [Mixed parts: one object, two engines](#mixed-parts-one-object-two-engines)
- [Renders](#renders)
- [Pitfalls](#pitfalls)
- [Still to confirm](#still-to-confirm)

## What it gives and what it costs

Blender adds what the other engines lack on a freeform body: real fillets and chamfers on any
edge (the Bevel modifier), robust booleans (the Manifold solver, the same library as
`manifold3d`), text in any font, and renders that look like the printed part. It costs the
parametric history: the result is a mesh in an editable `.blend` (meshes, collections per
object, the parameters as custom properties on a `PARAMETERS` empty), not CAD. Tell the user
that in one line before building. The generator script stays the source of truth: editing the
`.blend` by hand is fine for a look, the next rebuild comes from the script.

**Blender 4.5 LTS or newer**, on every path. The Manifold solver arrived in 4.5 (the older
Exact solver leaves unions of touching bodies open), and text and renders are tested from 4.5
on; `blender_builder.require_blender()` refuses anything older with a clear message, and
`build.py detect` says so in its notes.

## Three ways it runs

All three run the **same generator script**; only the launcher differs.

1. **Binary** (a `blender` executable on the machine the agent runs on). `build.py run` finds it
   (PATH, `BLENDER=/path`, the usual install folders including Steam, flatpak and snap) and runs

   ```bash
   python3 "$SKILL_DIR/scripts/build.py" run model_blender.py --params .3dprint/params.json --out out \
     --printer .3dprint/printers.json --tools 0
   ```

   which executes `blender --background --factory-startup --python-exit-code 1 --python-expr
   "<sys.path for the engines folder and the generator's>" --python model_blender.py --
   --params <engine params> --out out` with the usual `--timeout`; the generator saves its
   working copy `out/model_blender.blend` and rewrites it on every build. The first line of the generator, `# 3dprint-scout: engine=blender` (a shebang
   may come before it), picks the engine (or pass `--engine blender`); nothing is guessed from
   imports, and the Python engine refuses such a file by name.
2. **`bpy` module** (no binary, but `import bpy` works in some Python). The same command runs the
   generator with that Python instead, `references/engines` on `PYTHONPATH`; `build.py` tries the
   binary first, then `--blender-python PATH`, `BLENDER_PYTHON`, and the Python running
   `build.py`. `--blender-python` forces this path; a binary older than 4.5 or one that does not
   answer `--version` is passed over for a usable `bpy` module (a note in `engine_info` says so),
   the same choice `detect` and `render.py` make. In a disposable sandbox `pip install bpy`
   (one line to the user: it is a few hundred MB) into a Python that has a 4.5+ wheel is fine;
   on the user's machine, ask first.
3. **Live Blender** (an MCP connector to the user's own Blender; Phase 0 found a tool that runs
   Python there and answered `bpy.app.version_string`). Prefer the tool that runs code in a
   **background Blender process** when the server has one (the official Blender Lab server calls
   them `execute_blender_code_for_cli` and the like; names differ between servers): it cannot
   touch the user's open session. A tool that only runs code in the open GUI session is used
   the same way, with one difference the user hears first: the build adds a scene named
   `3dprint-scout` next to theirs (their window stays on their scene), and when
   `bpy.data.is_dirty` is true, ask before running anything. Send `blender_builder.py` and the
   generator to a folder on the user's machine under a **new name per version**, check the md5
   of both files after the transfer (print `hashlib.md5(open(p, "rb").read()).hexdigest()` there
   and compare with yours), then run a loader that gives the generator its command line and
   makes sure no stale helper from an earlier run is used:

   ```python
   import hashlib, runpy, sys
   folder = r"<folder you sent the files to>"
   expected = {"blender_builder.py": "<md5 you computed before sending>", "model_v3.py": "<md5>"}
   for name, digest in expected.items():
       with open(folder + "/" + name, "rb") as f:
           if hashlib.md5(f.read()).hexdigest() != digest:
               raise SystemExit("STALE FILE: " + name)         # a changed file was not resent
   saved_argv, saved_path = sys.argv, list(sys.path)
   sys.modules.pop("blender_builder", None)                    # never a helper left from an earlier run
   sys.path.insert(0, folder)
   sys.argv = ["blender", "--", "--params", folder + "/params.json", "--out", folder + "/out"]
   try:
       runpy.run_path(folder + "/model_v3.py", run_name="__main__")
   finally:
       sys.argv, sys.path[:] = saved_argv, saved_path          # leave the session as found
       sys.modules.pop("blender_builder", None)
   ```

   The generator writes the STLs and the `.blend` into `--out` only; print the `@@3DPS` line it
   ends with (sizes, solver, notes). Bring the STLs back to where `build.py` runs (the host's
   file tools, or the user copies them), print each file's md5 on the user's side before and
   check it on yours after, then record and validate like Fusion's parts:

   ```bash
   python3 "$SKILL_DIR/scripts/build.py" record out/body.stl out/label.stl --engine blender \
     --source model_v3.py "$SKILL_DIR/references/engines/blender_builder.py" \
     --params .3dprint/params.json --printer .3dprint/printers.json
   ```

   Show the result in the user's open Blender **only when they ask**, and then as below
   ("Live session").

## The helper module (`blender_builder.py`, next to this file)

`import blender_builder as bb` (build.py puts this folder on the path; in a live session the file
sits next to the generator). Millimetres everywhere, Z-up, Z = 0 on the bed.

| Call | Does |
|---|---|
| `bb.main(build, PARAMETERS)` | The runner: command line (`--out` required, `--params`, `--only`, `--blend`, `--no-blend`), the build scene, `build(p)`, parameters → custom properties, a path check, one STL per part, the `.blend`, the `@@3DPS` line. The generator ends with it |
| `bb.new_scene_mm()` | The build scene `3dprint-scout` at 1 unit = 1 mm (`METRIC`, `scale_length` 0.001, `MILLIMETERS`) with its own world, created next to whatever is open and reused on the next run with only the module's own objects removed; nothing is ever reset |
| `bb.box(size, name)`, `bb.cylinder(r, h, segments, name)`, `bb.prism(outline, height, name, z0)`, `bb.ring(r_in, r_out, h, segments, name, z0)` | Primitives on the bed (box corner at the origin; cylinder and ring on the Z axis; outline as `[(x, y), ...]`) |
| `bb.mesh_object(name, bmesh)` | Any bmesh you build yourself, linked and tagged |
| `bb.bevel(obj, width, segments=None, angle=30, bed=False)` | Real fillets on every edge sharper than `angle`, except edges on the bed; `segments` default one per line width along the arc; refuses a result with zero-area faces instead of welding it. `bb.chamfer(obj, width)` is the one-segment case |
| `bb.bed_chamfer(obj, height=0.4)` | The elephant-foot chamfer, cut into the bottom edges (P6), slightly steeper than 45° so P2 never counts it |
| `bb.boolean(target, tool, "difference" \| "union" \| "intersect")`, `bb.join(target, *tools)` | Boolean modifier, Manifold solver (`solver="EXACT"` forces the old one); checks both inputs and the result are manifold; applied, the tool removed (`apply=False` keeps it live, tool hidden) |
| `bb.text(string, height, depth, font=None, align="CENTER")` | Letters as one mesh standing on z = 0, `height` the **cap height**, Blender's built-in font or a font file (`bb.load_font` packs it into the `.blend` under its base name); each glyph welded on its own, touching glyphs unioned ("Booleans and text" below) |
| `bb.part(obj, name, object=None, role=None)` | Registers the part: object renamed, moved into the collection of its object (one collection per `_parts` object, made by the module; a user's collection of the same name is never reused), `role` kept as a property |
| `bb.params_to_props(p)` | The parameters on a `PARAMETERS` empty (numbers, strings, lists; anything else as JSON text; a string that is an absolute path is stored as its base name) |
| `bb.check_props()` | Refuses a string property that holds a path, naming object and property; `main` runs it before any STL is written |
| `bb.export_parts(out, names=None)` | One binary STL per part, modifiers applied, `global_scale` 1, scene unit off, axes unchanged; returns boxes in mm, triangles, bytes |
| `bb.save_blend(path, overwrite=False)` | The build scene's data-blocks only (no UI, no preferences, no window state) via `bpy.data.libraries.write`, compressed; fonts and images packed and renamed to `//<name>`; refuses the open file's path and an existing path; an uncompressed twin is scanned for this machine's folders first and a hit leaves nothing behind |
| `bb.render_views(out, views, colors, engine="workbench", size, overwrite=False)` | The preview grid (iso, front, right, top, as `preview.py`), see "Renders" |
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
    plate = bb.cylinder(12.0, 1.0, name="plate")    # a plaque that carries the letters: its own colour
    mark = bb.text(p["label"], height=6.0, depth=0.9)
    mark.location = (0.0, -3.0, 0.9)                # sunk 0.1 mm into the plaque
    bb.boolean(plate, mark, "union")                # plaque + letters = one body
    plate.location = (p["w"] / 2, p["d"] / 2, p["h"])         # on the top face
    bb.part(body, "body")
    bb.part(plate, "label", object="body", role="fused")
    return {"body": body, "label": plate}

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
- Parameters and properties hold names, never paths: a path in a string parameter is reduced
  to its base name, a path written into a custom property by the script stops the build before
  any STL is written.
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

## Booleans and text

`bb.boolean` uses the Manifold solver and says so in `LOG` (`build.py` repeats it in
`engine_info.boolean_solver`). It needs closed input: the call refuses a tool or target with
non-manifold edges, and refuses a result that came out open (usually a tool that ends exactly
on a face: overshoot cutters by 0.01–0.1 mm).

`bb.text` gives **one body per separate letter**. A text object left as its own part therefore
fails M5 unless its `_parts` entry says how many bodies it has (`"shells": 5` for a five-letter
word, `parts.md`); the better design is to union the letters onto a face that carries them (the
part itself, or a plaque that becomes a `fused` colour part, as above), which makes one body.
Letters that touch are handled inside `bb.text`: every glyph is welded on its own (welding the
whole string would merge "AA" into an open mesh), touching glyphs are unioned, and letters that
only kiss along an edge (the feet of "AA", the tops of "VV") get the character spacing
tightened by 1 % steps, 5 % at most, until the union is one closed body; `LOG` says what
happened, and an error says what did not.

## Live session: keep the user's file safe

- **Never save the user's file in any form** (`wm.save_mainfile`, `wm.save_as_mainfile`, also
  with `copy=True`): the only file this engine writes is the one `bb.save_blend` writes, and it
  refuses the open file's path, any existing path it was not told to rewrite, and any path
  outside `--out` when it comes from the command line. Never `wm.read_homefile`,
  `wm.read_factory_settings`, `wm.open_mainfile`, `wm.quit_blender`, and never delete anything
  you did not create. `new_scene_mm` builds into the `3dprint-scout` scene next to the user's,
  removes only objects it tagged on an earlier run, reuses only collections it made, and never
  switches the user's window; `save_blend` writes only that scene's data and stops if anything
  of the user's sits in it.
- In an open GUI session, say first that a `3dprint-scout` scene will be added, and when
  `bpy.data.is_dirty` is true ask ("your Blender has unsaved changes; save first, or shall I go
  ahead and add the scene?") and stop. Prefer the background tool.
- Before showing a result in their Blender, read `bpy.data.is_dirty` again; prefer appending
  (`bpy.ops.wm.append` of the part's collection from `out/<name>.blend` into a new scene) over
  opening the file.
- Never install Blender add-ons or change preferences without asking.
- A tool call that times out: retry once, then treat Blender as unavailable for this run and
  say why (as for Fusion).

## Mixed parts: one object, two engines

A mechanical body with a decorative part on it: the body in the CAD engine, the decorative part
here, both modelled in the same frame (Z-up, Z = 0 on the bed, the decorative part at its
assembled place) and listed in one `_parts` object (`role: fused` where they meet on a face).
Build each with `--only` into its own folder, then record both STLs together with every source
and the shared parameters, so one manifest hash covers the object:

```bash
python3 "$SKILL_DIR/scripts/build.py" run body.scad --params .3dprint/params.json --out out/body --only body --printer .3dprint/printers.json
python3 "$SKILL_DIR/scripts/build.py" run deco_blender.py --params .3dprint/params.json --out out/deco --only deco --printer .3dprint/printers.json
python3 "$SKILL_DIR/scripts/build.py" record out/body/body.stl out/deco/deco.stl --engine openscad+blender \
  --source body.scad deco_blender.py "$SKILL_DIR/references/engines/blender_builder.py" \
  --params .3dprint/params.json --printer .3dprint/printers.json
```

`record` groups the parts from `_parts`, runs A1 / A2 and the object checks, and writes the core
3MF; the engine name in the manifests is whatever `--engine` says. On the live path the Blender
STL comes back from the user's machine as in "Three ways it runs" (md5 both ways).

## Renders

When Blender is there, concept previews (Phase 1) and the delivery image can be Blender renders:

```bash
python3 "$SKILL_DIR/scripts/render.py" out/body.stl out/label.stl -o out/render.png --color "label=Jade White"
```

Workbench by default (headless, no GPU; about 6 s for a four-view 1200 × 900 grid and 9 s at
1600 × 1200 with the `bpy` module, most of it Blender starting), `--engine eevee` or `cycles`
when asked (slower). Part colours from `--color part=<filament name or #rrggbb>`: a small
built-in table of **approximate** screen colours of common Bambu filaments (whole names only,
"Light Blue" is not "Blue"), the user's AMS colours win when known, unnamed parts take the
palette, an unknown name gets neutral grey and a warning in the JSON; never ask about colours.
Very dark colours are lifted a little for the preview (`drawn` beside `colour` in the JSON)
so black parts still show their edges. Same views, grid and JSON as `preview.py`, same `sane`
check plus two: a render whose pixels nearly all differ from the background (a black or missing
world) is not sane, and neither is one with a blank view (exit 2). The check counts the rendered
views only, without the caption and the grid lines (`fg_views` per view in the JSON).
`preview.py` stays the fallback and the G4 check; the numbers from `validate.py` stay the
evidence.

## Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| D4 FAIL, everything 1000× too small or large | Scene units left at metres, or `use_scene_unit` on | `bb.new_scene_mm()`; export through `bb.export_parts` |
| `bevel ... made N zero-area triangles` | The bevel meets a chamfer, a cut or a dense outline closer than its width | Bevel first, cut and chamfer after; a smaller width; fewer outline points |
| M1 FAIL after a boolean | The tool ends exactly on a face | Overshoot by 0.01–0.1 mm; check `bb.nonmanifold_edges` on the inputs |
| M5 FAIL on a text part | One body per letter | Union the text onto the face or a plaque, or set `shells` in `_parts` |
| `text ...: letters touch only along an edge` | Two glyphs kiss and even 5 % tighter spacing does not make them overlap | Put the text on a plate (union with it), or another font / spacing |
| P3 WARN on text | Strokes thinner than 1.2 mm | Text follows the text rule (strokes ≥ 0.8 mm, `design.md`); say so, or a larger cap height |
| `import bpy` hangs or takes a minute | First import loads most of Blender | `build.py detect` probes it in a subprocess with a timeout; wait once |
| `EGL Error` lines in the output | Headless GPU context on Linux | Harmless: Workbench and Cycles still render; `build.py` drops those lines |
| `Blender ... is older than 4.5` | The floor of this engine | Install Blender 4.5 LTS or newer, or `pip install bpy` (needs a matching Python) |
| The `.blend` save fails with "would hold a path of this machine" | A data-block still pointed at an absolute path | `bb.load_font` for fonts; no external images; nothing linked |
| `custom property 'x' on 'y' holds a path` | The script stored a path in a property | Store a name; the parameters are scrubbed automatically |
| The render is not sane: "no background" | A scene without a world (black background) | `new_scene_mm` and `render_views` set one; a hand-made scene needs `scene.world` |

## Still to confirm

- The binary path on a real `blender` install (the exact flags come from the Blender manual's
  command-line page; here the `bpy` module 4.5.14 and 5.2.2 and an emulated binary ran).
- The live path on a real MCP server (which tool runs in the background, its timeouts).
- EEVEE in a headless Linux session (slow here: about 40 s for a small scene; Workbench and
  Cycles take seconds).
