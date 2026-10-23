# Phase 0 — Detect (silent)

Read this on entering Phase 0 (SKILL.md names the rules that hold at all times). Probe, then
report in one line, e.g. "Using OpenSCAD (Fusion not connected); references via web search;
previews via OpenSCAD."

If the user already chose D and named the existing model, use the Phase 1 handoff directly.
Do not install or probe modeling engines just to give them that model's original link.

## 1. Engine

Find what works:

- **Fusion** — a tool whose name contains `fusion` exists and a read call (list open documents)
  returns. If the call times out or returns an error, retry once; if it fails again, treat Fusion as
  unavailable for this run and say why in the report line. Check the active document. If it holds the user's
  own work, ask before the first write and prefer a new document. Never save automatically:
  Fusion for personal use caps editable documents at 10, and the generator script is the source
  of truth anyway.
- **OpenSCAD, Python, Blender** — run `python3 "$SKILL_DIR/scripts/build.py" detect`. It finds
  OpenSCAD (PATH and the default install folders), probes the fast `--backend=manifold` for real
  (a stable 2021.01 build is CGAL-only and slow), checks for manifold3d and the optional
  libraries, and reports Blender in its `blender` block: a `blender` binary (PATH, `BLENDER=`,
  the usual install folders, version from `--version`), the `bpy` module (probed in a
  subprocess with a timeout: importing it is slow), and `manifold_boolean`. Blender 4.5 LTS or
  newer only; an older one is listed with a note and not used. Never pass the obsolete
  `--enable=manifold`, which silently falls back to CGAL.
  A failed OpenSCAD version/cube export probe is excluded from `available` and reported in
  `warnings`. For bpy, a failed or old `BLENDER_PYTHON` candidate falls back to the current
  interpreter. An explicit `--blender-python` is binding and never silently substituted: `detect`
  with it reports only that interpreter (the binary is not probed), as `run` with it would use.
- **Live Blender** — a tool that runs Python in the user's own Blender (an MCP connector; names
  differ between servers) and answers a harmless read, `import bpy; bpy.app.version_string`
  (4.5 or newer), counts as the live Blender path. `detect` runs where your shell is: in a VM
  or a cloud container linked to the user's computer it cannot see their Blender, so "no
  Blender" from `detect` plus a working live tool means the live path, with files passed
  through a folder the user connected. A timeout or an error: retry once, then treat it as
  unavailable and say why. Never install add-ons or change preferences there without asking;
  the build adds a `3dprint-scout` scene next to theirs and writes only into its output folder
  (`references/engines/blender.md`, "Live session").
- **None** — in a disposable sandbox (a cloud code-execution container, not the user's own
  machine) `pip install manifold3d numpy rtree matplotlib` is fine: say so in one line and do
  it; `pip install bpy` too when the shape wants Blender (a few hundred MB; the Python version
  must match a published wheel). On the user's machine, ask before installing anything. Never
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
    the user's call (ask). A comparison on 2026-10-21 (a C-clip and a card-slot block, built
    with these helpers only) measured the same as the Python engine: fit features within
    0.002 mm, the same `fit.py` gap and play, true corner radii; Blender builds take about a
    second longer.
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
scene). It prints JSON with the G4 check of the image (`sane`); exit 2 means a blank image.
With Fusion, the MCP screenshot of the viewport is an extra. Without numpy say there is no
preview; a missing preview is not an error, numbers stay the primary evidence. Do not
use `openscad -o preview.png` headless on Linux: it exits cleanly and writes a **0-byte PNG**
unless it runs under `xvfb-run -a`.

With Blender (any of the three paths), `render.py` draws the same grid through Blender's
Workbench engine, headless, with part colours from filament names, for STLs from any engine:

```bash
python3 "$SKILL_DIR/scripts/render.py" out/body.stl -o out/render.png --color "body=Jade White" --overwrite
```

Same JSON and `sane` check; `preview.py` stays the fallback and the G4 check
(`references/engines/blender.md`, "Renders"). For a user who reads Korean, `--lang ko` draws the
view names in Korean (preview.py's bitmap font keeps them in English). Both write a sidecar next
to the image (`<image>.png.json`: its sha256, the views, each STL's sha256); keep it with the
image, because a user's judgement of the image is tied to the parts through it
(`references/checks.md`, `_verify.seen`).

## 4. Printer

Does `.3dprint/printers.json` exist? Its schema, and what to do when it is missing, are in
`references/phase-2-printer-dimensions.md`.
