# Phase 6 — The print file and the source bundle

Read this only when `finalize.py --deliver` names a finding about the print file (another
material, a filament or preset it cannot read), when `--bundle` refuses, or when the user means
to share the bundle. The rest of Phase 6 is in `references/phase-6-deliver.md`.

## The print file (`--deliver`)

A Bambu project must print each part in its material (`_parts.<name>.material`, else `_material`)
and under `_print.preset`. finalize compares its manifest with them; what each finding leaves of
the evidence that depends on the material or the preset is in `references/outputs.md` (the
`--deliver` paragraph). Act on its `open` lines:

- **Another material** ("stand is printed in Bambu PETG HF @BBL X1C (petg_hf), the part is
  pla_basic"): ask which material the user prints with. The part's own: write the project again
  into a new version folder with that part's `filament` set to the slot that holds it. Another:
  change the material in params.json, build again, renew what went stale
  (`references/phase-5-gate.md`, step 1) and offer a new test print. Never edit a manifest.
- **A filament finalize cannot name** ("the slicer's filament for stand is not checked ("My PLA"
  is not a filament of a known material)"): tell the user which filament to choose for each part
  in the slicer ("select stand in the object list and choose Bambu PLA Basic"), or, when they
  print with a system preset, write the project from a template that names it.
- **Another process preset** ("its process preset is "0.16mm Optimal @BBL X1C", not
  _print.preset "0.20mm Standard @BBL X1C""): ask which one the user prints with. The project's:
  set `_print.preset` to it and offer a new test print. `_print.preset`'s: write the project from
  a template with that preset.
- **No process preset in the project** ("the project names no process preset ..."): tell the
  user to choose the preset `_print.preset` names in the slicer, or write the project from a
  template that names it.
- **STL per part, or a core 3MF** (another slicer, or no Bambu template: "the print file's
  material is not checked (no Bambu project)"): say in the message which filament to choose for
  each part.

None of these is a geometry reason: they reach the user through the `use` tier and `open`.

## The source bundle (`--bundle`)

`--bundle` writes a new folder that holds what the verdicts were made from, each file at its
path in the project folder (`lib/helper.py` stays `lib/helper.py`):

- the generator and its own files (not the skill's libraries), `params.json`, the
  `printers.json` the build used, the report as `verification.json`, and `REPRODUCE.md`;
- the reports `_verify` names (fit, strength and measurement JSON); a proxy's generator and
  params file (a proxy taken in with `record` also with its build JSON, STLs and manifests); a
  `user-file` dims entry's file and its measurement reports; the seen images with their
  sidecars; the photos of a test print (its `photos`);
- with `--deliver`, the delivered files (every STL and 3MF), each 3MF with its manifest.

`REPRODUCE.md` holds the commands that rebuild the parts (and the proxies `build.py run` made)
and re-check them from the bundle alone (finalize with `--deliver` on the bundled delivery
folder); the reports hold while the rebuild makes the same STLs, so with the same engine and
library versions. A recorded build (Fusion, a live Blender) needs the user to export the part
STLs again first; REPRODUCE.md lists them. A file `_verify` names that is missing does not stop
the bundle: it is left out and listed in `bundle_missing` and in REPRODUCE.md; make it again and
bundle into a new folder, or say it is missing.

Bundle a build that is the project as it is now: the bundle rebuilds the parts, so a verdict
that says the build differs from the project (an STL or a source changed since, the settings,
grouping or material changed since, a part not built, or finalize run with other settings than
the build) is refused: build again (`build.py run`, with `--printer`), re-check, then bundle.
It also refuses a carried file that the rebuild writes again (a core 3MF a measurement read,
or a delivery made into `out/`: deliver into a folder of its own) or a file at a name the
bundle writes itself (`build.json`, `REPRODUCE.md`, ...), and a printers.json the build used
that is gone when the build judged an object of several parts with it.
A generator that reads a data file of its own is rebuilt without it (Phase 3, "Read no data
file of your own").

The bundle refuses any file it would carry, or the `--deliver` folder, outside the project
folder (a part STL or the core 3MF too, and a link inside the folder to a file outside it),
and any carried text file that holds a path of this machine: keep the user's files,
photos and reports in the project folder (`ref/plug.stl`, `photos/notch.jpg`), run the scripts
from there with relative paths (Phase 4), move a source in and build again, and put a name, not
a path, in a source or `params.json`. The bundle carries the user's own files, photos and the
delivered files, and a delivered Bambu project may carry metadata from the user's template
(`bambu3mf.py` blanks the designer and account fields it knows): when the user means to share
it, say so, and that sharing it is their call. Deliver it with the files so a later change can
start from it.
