# Fusion engine (MCP)

Read this right before Phase 3 when Phase 0 found a working Fusion MCP connection and the user
wants editable CAD (Rule A: otherwise every shape goes to Blender when it is usable, else
mechanical parts to Python or OpenSCAD, which are faster and checked the same way).

Contents:

- [Before the first write](#before-the-first-write)
- [The Builder (`fusion_builder.py`, next to this file)](#the-builder-fusion_builderpy-next-to-this-file)
- [Generator script rules](#generator-script-rules)
- [Pitfalls seen in the field](#pitfalls-seen-in-the-field)
- [Sending scripts](#sending-scripts)
- [Still to confirm on a real install](#still-to-confirm-on-a-real-install)

Fusion is driven through whatever Fusion MCP tools the host exposes (tool names differ between
servers). The skill uses one pattern on every server: **a generator script executed inside Fusion**
that rebuilds the whole design from parameters. Never drive Fusion click by click.

## Before the first write

1. Read the active document's name and whether it has bodies or timeline features.
2. If it holds the user's own work, **ask and stop**. Prefer a new document for this part.
3. **Never save** unless the user asks. Fusion for personal use caps editable documents at 10,
   and the generator script is the source of truth anyway (the 2026-10-17 part was never saved).

## The Builder (`fusion_builder.py`, next to this file)

Paste the file above your `run()` or exec it from a file (below). It gives you:

| Call | Does |
|---|---|
| `B = Builder(design)`; `B.clear()` | Deletes the timeline, last entity first (a direct-modelling document has none: its bodies and sketches are deleted instead): every run rebuilds from scratch |
| `P = B.params({"w": 60, "wall": 2})` | One **user parameter** per `params.json` key (`p_w`, `p_wall`, in mm), created or updated; returns the names |
| `B.sketch(name)`, `B.rect(sk, x0, y0, w, d, w_expr=P["w"])`, `B.circle(sk, cx, cy, r, d_expr=...)`, `B.rounded_rect(sk, ...)`, `B.polygon(sk, pts)` | Sketches on the XY plane in mm with **real circles and arcs** (the rounded rectangle is a rectangle with `addFillet` corners, one connected profile); `*_expr` adds a sketch dimension driven by a parameter |
| `B.extrude(sk, z0, z1, name, operation="new"\|"join"\|"cut"\|"intersect", target=...)` | Every closed profile from `z0` to `z1`, numbers or **expressions** (`P["h"] + " - p_floor"`), so the feature follows the parameters |
| `B.revolve(sk, axis_line, name)` | Full revolve of the first profile about a sketch line |
| `B.frame(origin, x_axis, y_axis)`, `B.move(bodies, matrix)` | Right-handed frame (z = x × y, perpendicularity checked) and a free move |
| `B.join(target, tools)`, `B.cut(target, tools)` | Refuse a tool whose box does not touch the target, and report tool bodies still present afterwards |
| `B.bodies()`, `B.export(folder, names, refinement="high")` | Bodies by name; one binary STL per body at High refinement plus `summary.json` (boxes in mm, volumes); print the returned text |

Name every body exactly like its `_parts` entry and export one STL per part; parts of one
object are modelled in the same frame, so the STLs already hold the assembled positions.
Pins, knuckles, levers and links that carry load follow `design-mechanisms.md`, "Mechanisms that carry
load" (pin ≥ 3.2 mm, 2.2 mm of wall around it, members ≥ 2.5 mm): the field-test latch
built at the 1.2 mm printability minimum broke on first use.
Then record and validate:

```bash
python3 "$SKILL_DIR/scripts/build.py" record out/body.stl out/lever.stl --source generator_fusion.py \
  --params .3dprint/params.json --printer .3dprint/printers.json
```

`record` writes the freshness manifests (the generator script and params are the source),
validates every part, groups parts from `_parts` into objects (`parts.md`) and writes the core
3MF. Its JSON is described in `build.py record --help` and `outputs.md`. If an STL comes back
10× too small or large, D4 reports a unit error: fix the export, never scale the mesh.
Preview the recorded STLs with `preview.py` like any other; the MCP screenshot of Fusion's
viewport is an extra.

When your shell is a VM or a cloud container linked to the user's computer, `B.export` writes
on their machine, where `build.py` cannot see it. Export into a folder the user connected (or
bring the files over with the host's file tools), print each STL's md5 on their side (in the
script, `hashlib.md5(open(p, "rb").read()).hexdigest()`) and check it on yours before `record`,
as for a live Blender (`blender-live.md`).

The Builder is derived from the one that ran end to end in the 2026-10-17 field test; this
cleaned version (expressions on features, sketch dimensions, real arcs, the join/cut guards)
has **not yet been run in Fusion**. If a call fails, read the error, fix the call against the
Fusion API reference, and note it here.

## Generator script rules

- **Everything inside `def run(context=None):`.** Code at module level has ended in a
  `NameError` that rolled the whole change back. Wrap the body in `try/except` and `print`
  the traceback: without it the tool returns nothing useful.
- **Units.** The API works in centimetres. The Builder converts (`cm()`, `mm()`); outside it,
  pass lengths as strings with units (`createByString("40 mm")`) or convert explicitly, and
  remember that everything read back (`boundingBox`, `volume`) is in cm and cm³. A literal in
  an expression needs its unit too (`P["h"] + " + 1 mm"`): a bare `1` takes the document's units.
- **Parameters must drive features.** Creating user parameters and then building with
  `createByReal(number)` leaves the parameters decorative (the field test did exactly this).
  Use the names in expressions: extents, offsets, sketch dimensions.
- **Real circles and arcs**, never polylines approximating them: polylines make faceted STLs
  and hundreds of sketch lines that compute slowly.
- **Z-up.** Sketch on `xYConstructionPlane` and extrude along +Z so Z = 0 is the bed. Build
  in the part's own frame and `move` it into print pose at the end. D4 catches a part that
  comes out on its side.
- **Safe order.** Fillets before cuts that would cross them; cuts after joins.

## Pitfalls seen in the field

| Symptom | Cause | Fix |
|---|---|---|
| A feature is missing from the STL, no error | `join` with a tool that does not touch the target: Fusion keeps the tool as a separate body | `B.join` refuses it; list `B.bodies()` after a build and expect exactly the `_parts` names |
| A body ends up mirrored or inside out | Left-handed `Matrix3D` (axes not a right-handed set) | `B.frame()` builds z = x × y and checks perpendicularity |
| A taper or draft goes the wrong way | The sign of a taper angle is not documented | Try ±, keep the one that shrinks, and record the sign in the project's notes |
| The old model is rebuilt after an edit | The tool re-ran a cached script at the same path | New path per version plus an md5 check before `exec` (below) |
| Editing a parameter in Fusion changes nothing | Features were built with `createByReal` | Expressions with parameter names (`B.extrude(sk, 0, P["h"], ...)`) |
| Round parts measure small | Circles drawn as polygons | `B.circle`, `B.rounded_rect` |

## Sending scripts

- A short script (a few hundred lines) goes inline in the execute call.
- A longer one goes to a file on the user's machine, under a **new path or name per version**
  (`adapter_v3.py`), then a tiny loader runs in Fusion and refuses a stale file:

  ```python
  import adsk.core, adsk.fusion, hashlib
  def run(context=None):
      path = r"<folder>\adapter_v3.py"            # the file you just sent
      data = open(path, "rb").read()
      if hashlib.md5(data).hexdigest() != "<md5 you computed before sending>":
          print("STALE FILE, not running"); return
      ns = {"__name__": "generator"}
      exec(compile(data.decode("utf-8"), path, "exec"), ns)
      ns["run"]()
  ```

  Committing a changed file to the same path and re-sending the same execute call has run the
  previous content; the md5 line catches it.
- Transfers across machines: check the md5 after every transfer, both ways.

## Still to confirm on a real install

- The cleaned Builder (sketch dimensions, expression extents, the combine guards).
- The unit Fusion's STL export uses when the document is set to inches.
