# Phase 0 — Detect (silent)

Read this on entering Phase 0 (SKILL.md names the rules that hold at all times). Probe, then
report in one line, e.g. "Using OpenSCAD (Fusion not connected); references via web search;
previews via OpenSCAD."

## 1. Engine

Find what works:

- **Fusion** — a tool whose name contains `fusion` exists and a read call (list open documents)
  returns. If the call times out or returns an error, retry once; if it fails again, treat Fusion as
  unavailable for this run and say why in the report line. Check the active document. If it holds the user's
  own work, ask before the first write and prefer a new document. Never save automatically:
  Fusion for personal use caps editable documents at 10, and the generator script is the source
  of truth anyway.
- **OpenSCAD, Python** — run `python3 "$SKILL_DIR/scripts/build.py" detect`. It finds OpenSCAD
  (PATH and the default install folders), probes the fast `--backend=manifold` for real (a stable
  2021.01 build is CGAL-only and slow), and checks for manifold3d and the optional libraries.
  Never pass the obsolete `--enable=manifold`, which silently falls back to CGAL.
- **None** — in a disposable sandbox (a cloud code-execution container, not the user's own
  machine) `pip install manifold3d numpy rtree matplotlib` is fine: say so in one line and do
  it. On the user's machine, ask before installing anything. Never try `apt` or `brew` for
  OpenSCAD in a sandbox (minutes lost, and there is no display). If nothing works after that,
  say what to install and stop.

Then choose **by the shape**, among the engines that work (rule A in SKILL.md):

- **Mechanical or prismatic** (dimensions that must fit, holes, bosses, fillets, a part the user
  may want to edit later) → Fusion, else OpenSCAD, else Python.
- **Organic or freeform** (leaves, sculpted grips, terrain, reliefs, smooth blends) → Python,
  which builds such surfaces directly from height functions; CAD sketches and CSG handle them
  poorly.

Before modeling, tell the user what the choice costs: OpenSCAD and Python have no native fillets
(chamfers instead), and Python leaves a mesh, not editable CAD (every dimension stays a
parameter in the script).

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

## 4. Printer

Does `.3dprint/printers.json` exist? Its schema, and what to do when it is missing, are in
`references/phase-2-printer-dimensions.md`.
