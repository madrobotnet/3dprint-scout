# Examples

Four parts built with the skill's own scripts, one per engine or tool. Each folder has the
source, its parameters and a preview, and rebuilds with the commands in its README. Sizes are
example values, not measured against your objects.

| | Example | Engine and tools | What it shows |
|---|---|---|---|
| <img src="aa-battery-box/thumb.png" width="240"> | [aa-battery-box](aa-battery-box/) | OpenSCAD | Dimensions with sources, fit clearances, a slip-on lid checked with `fit.py` |
| <img src="snap-box/thumb.png" width="240"> | [snap-box](snap-box/) | Python, `parts.py` | Rounded box, bed-edge chamfer, insert bosses, snap hooks with a strain check, `fit.py` |
| <img src="leaf-handle/thumb.png" width="240"> | [leaf-handle](leaf-handle/) | Python, `sdf.py` | An organic shape: a leaf dome and a round grip blended into one watertight part |
| <img src="fit-test/thumb.png" width="240"> | [fit-test](fit-test/) | `fit_test.py` | Three test rings in clearance steps, marked 1, 2, 3, to print before the real part |

## Running them

Run the commands from the example's folder. You need Python 3.9 or newer and:

- `pip install manifold3d numpy` for all examples (`rtree` too for the wall-thickness check);
- [OpenSCAD](https://openscad.org) for `aa-battery-box`.

Builds write to `out/` (STL per part, a build manifest, a core 3MF and the validation results);
`out/` is not committed. `printers.x2d.json` describes a Bambu Lab X2D with its bed and the area each
nozzle reaches, as in Bambu Studio's X2D 0.4 nozzle profile. It names no slicer template, so the
builds write a slicer-neutral 3MF. In a real request the skill asks for your printer and slicer,
and for Bambu Studio it also writes a project with per-object settings.

`place.py` moves a copy of an STL so `preview.py` can draw parts side by side or assembled; it uses
the same rotate-then-translate convention as `fit.py`.

## What a request looks like

These parts are what the modeling and verification phases produce. A full request also starts
with existing models and their licenses, concept previews, and a dimension table you confirm; see
[How a request runs](../README.md#how-a-request-runs).
