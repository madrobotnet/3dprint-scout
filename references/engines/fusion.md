# Fusion engine (MCP)

Read this right before Phase 3 when Phase 0 found a working Fusion MCP connection.

Fusion is driven through whatever Fusion MCP tools the host exposes (tool names differ between
servers). The skill uses one pattern on every server: **a generator script executed inside Fusion**
that rebuilds the whole design from parameters. Never drive Fusion click by click.

## Before the first write

1. Read the active document's name and whether it has bodies or timeline features.
2. If it holds the user's own work, **ask and stop**. Prefer a new document for this part.
3. Do not save automatically. Fusion for personal use limits editable documents to 10, and the
   generator script is the source of truth. Tell the user when a save would be worth it.

## Generator script rules

```python
import adsk.core, adsk.fusion

PARAMS = {"w": "60 mm", "d": "40 mm", "h": "25 mm", "wall": "2 mm"}   # strings with units

def run(context=None):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    ups = design.userParameters
    for name, expr in PARAMS.items():
        p = ups.itemByName(name)
        if p:
            p.expression = expr
        else:
            ups.add(name, adsk.core.ValueInput.createByString(expr), "mm", "3dprint-scout")
    root = design.rootComponent
    # ... sketches on root.xYConstructionPlane, extrusions along +Z ...
```

- **Put everything inside `def run(context=None):`.** Scripts sent through MCP that leave code at
  module level have ended in a `NameError` that rolled the whole change back.
- **Units.** The Fusion API works in centimetres internally. Pass lengths as strings with units
  (`createByString("40 mm")`) or convert explicitly; values read back from the API are in cm.
- **User parameters.** Create one user parameter per entry of `params.json` so the user can still
  tweak the design in Fusion's Change Parameters dialog. Drive features from parameter names
  (expressions such as `"wall * 2"`), not from copied numbers.
- **Z-up.** Sketch on `xYConstructionPlane` and extrude along +Z so Z = 0 is the bed, regardless of
  the document's Y-up/Z-up view preference. D4 catches a part that comes out on its side.
- **Rebuild from scratch.** Each run first removes what the previous run built, then rebuilds in a
  safe order (fillets before cuts that would cross them). How to clear depends on the design type
  and the MCP server; confirm it on first use and record what worked in the project's notes.

## Export and record

Export one STL per body in print orientation, high mesh refinement, then record and validate:

```bash
python3 "$SKILL_DIR/scripts/build.py" record out/body.stl out/lid.stl \
  --source generator_fusion.py --params .3dprint/params.json --printer .3dprint/printers.json
```

`record` writes the freshness manifests (the generator script and params are the source) and
validates every part. If an STL comes back 10× too small or large, D4 reports a unit error; fix the
export units rather than scaling the mesh.

## Moving files between machines

When the generator runs on another computer than the one writing files (for example a cloud agent
sending files to the user's PC), check the file's md5 right after every transfer. A first transfer
has been seen to leave the previous content in place.

## Still to confirm on a real install

- The unit Fusion's API uses when exporting STL.
- The cleanest way to clear the previous build on each MCP server.
