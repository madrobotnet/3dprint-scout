# Mixed parts: one object, two engines

Read this only for an object whose parts come from two engines (a CAD body with a Blender
part, or a Blender body with a part that needs a parts.py helper Blender cannot reach).

A part built in another engine next to a Blender part: a Fusion body the user keeps as CAD, or a
mechanical part that needs a parts.py helper when Blender's Python has no manifold3d (the Python
engine builds it). When the two must become one body, bring the other STL in with
`bb.import_stl` and union it here (its sources go into `--source` with the generator's). When
they stay two parts of one object, both are modelled in the same frame (Z-up, Z = 0 on the bed, the decorative part at its
assembled place) and listed in one `_parts` object (`role: fused` where they meet on a face).
Build each with `--only` and `--no-3mf` into its own folder (half an object makes no 3MF;
`record` writes the object's), then record both STLs together with the union of the `sources`
both runs printed (each generator's includes and local imports too) and the shared parameters,
so one manifest hash covers the object:

```bash
python3 "$SKILL_DIR/scripts/build.py" run body.scad --params .3dprint/params.json --out out/body --only body --no-3mf --printer .3dprint/printers.json
python3 "$SKILL_DIR/scripts/build.py" run deco_blender.py --params .3dprint/params.json --out out/deco --only deco --no-3mf --printer .3dprint/printers.json
python3 "$SKILL_DIR/scripts/build.py" record out/body/body.stl out/deco/deco.stl --engine openscad+blender \
  --source body.scad deco_blender.py "$SKILL_DIR/references/engines/blender_builder.py" \
  --params .3dprint/params.json --printer .3dprint/printers.json
```

`record` groups the parts from `_parts`, runs A1 / A2 and the object checks, and writes the core
3MF; the engine name in the manifests is whatever `--engine` says. It also adds the sources each
STL's own build manifest lists, and an STL whose manifest is stale is an R3 FAIL: rebuild it. On the live path the Blender
STL comes back from the user's machine as in `blender-live.md` (md5 both ways). The `.blend`
of `out/deco` holds the Blender parts only; the CAD parts are delivered as STLs (and their
source).

The reverse case, a decorative body with a fit feature (an organic plaque with keyholes on its
back): split it along a plane into a CAD part that carries the fit (a flat back plate) and the
Blender body on it, `fused` on that face. Compute a shared outline once and put it in
`params.json` (a list of `[x, y]` points both generators read; OpenSCAD gets it through `-D`)
instead of implementing it twice: two copies drift apart, and the seam with them.
