# Phase 0 — Detect (silent)

Read this on entering Phase 0 (SKILL.md names the rules that hold at all times). Probe, then
report in one line, e.g. "Using OpenSCAD (Fusion not connected); references via web search;
previews via OpenSCAD."

If the user already chose D and named the existing model, go to the Phase 1 handoff: probe and
install nothing.

## 1. Engine

Find what works:

- **Fusion** — a tool whose name contains `fusion` exists and a read call (list open documents)
  returns. If the call times out or returns an error, retry once; if it fails again, treat Fusion as
  unavailable for this run and say why in the report line. Check the active document. If it holds the user's
  own work, ask before the first write and prefer a new document (`references/engines/fusion.md`).
- **OpenSCAD, Python, Blender** — run `python3 "$SKILL_DIR/scripts/build.py" detect` (`--help`
  for what it probes). It reports what works in `available`, OpenSCAD's manifold backend,
  manifold3d and the optional libraries, and Blender (binary, `bpy` module, 4.5 LTS or newer) in
  its `blender` block; anything that failed its probe is in `warnings`. Never pass the obsolete
  `--enable=manifold`, which silently falls back to CGAL.
- **Live Blender** — a tool that runs Python in the user's own Blender and answers a harmless
  read (`import bpy; bpy.app.version_string`, 4.5 or newer). `detect` cannot see it from a VM
  or a cloud container, so "no Blender" from `detect` plus a working live tool means the live
  path. A timeout or an error: retry once, then treat it as unavailable and say why
  (`references/engines/blender-live.md`). When the sandbox has Blender too (a `bpy` module),
  build there with `build.py run`, where the checks see the generator, and use the live one to
  show the user the result and, if wanted, to cross-check it: compare triangle count and volume,
  never the STL's sha256 (the exporters write different headers).
- **None** — in a disposable sandbox (a cloud code-execution container, not the user's own
  machine) `pip install manifold3d numpy rtree matplotlib` is fine: say so in one line and do
  it, and install `bpy` first (a few hundred MB; the Python version must match a published
  wheel). `detect` lists both commands in `suggest`, for the interpreter it checked and only for
  what is missing (`for: "blender"`, `for: "python"`): Blender is the first engine for every shape, so a
  sandbox that lacks it installs it, and builds with another engine only when the install
  fails, with the reason in `_assumptions`. On the user's machine, ask before installing anything. Never
  try `apt` or `brew` for OpenSCAD in a sandbox (minutes lost, and there is no display). If
  nothing works after that, report what is missing. Reference discovery and choice D still work
  without a modeling engine; stop before modeling if the user chooses A, B or C.

For reproducible virtual environments and supported Python/bpy combinations, use
`references/development.md`. Do not assume the general Python 3.9+ floor means a bpy wheel
exists for that Python. Finish dependency installation before starting builds or tests.

Then choose among the engines that work (rule A in SKILL.md):

- **Blender first, for every shape, when it is usable** (binary, `bpy` module or live):
  - **Mechanical or prismatic** (dimensions that must fit, holes, bosses, screw fits, snaps,
    hinges): holes and slots as booleans of primitives made with `bb.circle_segments` (never
    Blender's default 32-vertex primitives), rounds with `bb.fillet` (a true radius) or, along a
    curved face, in the 2D profile with `bb.round_profile`. parts.py's tested helpers
    (countersinks, teardrops, snaps, hinges, threads) come in through `bb.from_manifold` when
    `detect` reports manifold3d in the Python that runs Blender (`blender.*.manifold3d`); when it
    does not, a part that needs one of them is built with the Python engine (or from
    `cylinder` / `cone` when that is enough), and installing manifold3d into Blender's Python is
    the user's call (ask). Fit features built this way measured the same as the Python engine's
    (2026-10-21, within 0.002 mm).
  - **Organic, freeform, sculpted or decorative** (leaves, sculpted grips, terrain, reliefs,
    smooth blends, surface patterns, embossed art, fillets on a freeform body): what Blender is
    best at.
- **Without Blender:** mechanical or prismatic → **Python** (manifold3d with the part library in
  `scripts/parts.py`), or **OpenSCAD** when the user wants an editable `.scad` (idioms in
  `references/engines/openscad.md`); organic or freeform → **Python**, which builds such
  surfaces from height functions (`sdf.py`); CAD sketches and CSG handle them poorly.
- **Fusion** only when the user wants an editable CAD design (a Fusion document, STEP) and Fusion
  is connected: through MCP it is slow, and freeform shapes are hard to drive there.
- **Mixed engines** stay possible: a part built in another engine (a Fusion body, a Python part
  that needs a parts.py helper Blender cannot reach) is its own `_parts` entry of the same object
  (`role: fused` where they meet on a face, `references/parts.md`), or is brought into the
  Blender build with `bb.import_stl`; say so.

Before modeling, tell the user what the choice costs: OpenSCAD and Python have no native fillets
(chamfers instead), Python leaves a mesh, not editable CAD (every dimension stays a parameter in
the script), and Blender leaves an editable `.blend` (meshes, parameters as custom properties),
not a parametric CAD history. The choice holds for the project: changing the engine later
(Fusion → Python, say, because a Fusion call failed or the shape turned out organic) is said to
the user in one line with the reason before anything is built in the new engine, and recorded in
`_assumptions`; never a silent switch between what was announced and what was delivered.

## 2. Reference search tier

A: a model-marketplace tool exists; B: web search exists; C: neither.

## 3. Preview

`preview.py` renders any STL (numpy only, no display needed), so every engine has a preview once
a part is built:

```bash
python3 "$SKILL_DIR/scripts/preview.py" out/body.stl -o out/preview.png --overwrite
```

One PNG with iso, front, right and top views (`--views`, `--separate`, several STLs in one
scene) and JSON with the G4 check of the image (`sane`; exit 2 means a blank image). Without
numpy say there is no preview; numbers stay the primary evidence. Never `openscad -o
preview.png` headless on Linux: it writes a **0-byte PNG** unless under `xvfb-run -a`.

With Blender, `render.py` draws the same grid with part colours from filament names
(`--color "body=Jade White"`), for STLs from any engine (`references/engines/blender.md`,
"Renders"); `--lang ko` draws the view names in Korean. Both write a sidecar
(`<image>.png.json`) that ties a user's look at the image to the parts: keep it with the image.

## 4. Printer

Does `.3dprint/printers.json` exist? Its schema, and what to do when it is missing, are in
`references/phase-2-printer-dimensions.md`.
