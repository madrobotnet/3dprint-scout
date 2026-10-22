# Development environments and readiness checks

Run these commands from the skill's checkout (the directory containing `SKILL.md`). When the
skill is installed elsewhere, set `SKILL_DIR` to that directory rather than hard-coding an
agent-specific location. Keep project work outside the skill, or in its ignored `out/` folder.
The unittest commands below need a source checkout with `tests/`; the installable release ZIP
contains the runtime scripts and references but does not include the test suite.
Finish installation before running builds/tests; do not reinstall bpy while Blender subprocesses
are using it. On a user's machine, ask before installing tools as Phase 0 requires.

## Choose the smallest environment that supports the work

| Workflow | Python and dependencies | What it establishes |
|---|---|---|
| Inspect/validate existing STLs and write core 3MF | Python 3.9+, standard library | Mesh/size checks; optional wall, joint and render checks may remain unverified |
| Python modeling, fit/assembly checks and previews | Python 3.11 with `requirements/python-modeling.txt` | manifold3d generation, numpy previews, rtree wall checks, matplotlib text |
| Blender modeling and rendering through bpy | Python 3.11 with `requirements/blender-4.5.txt` | Blender 4.5.14 LTS and the Python modeling libraries |

The pinned files record a known working **top-level dependency combination**, not a complete
lock of transitive packages or operating-system libraries. They are optional: CI also tests
the latest compatible dependencies on Python 3.9/3.13 and a newer bpy version. The general
Python 3.9+ support floor does not mean that bpy publishes a wheel for every Python version.
The Blender CI pairs are Python 3.11 / bpy 4.5.14 and Python 3.13 / bpy 5.2.2.

## 1. Standard-library checks

No package installation is needed for this path:

```bash
python3 scripts/validate.py --help
python3 -m unittest discover -s tests -p test_validate.py -v
```

Read skipped tests and `UNVERIFIED` results as missing coverage, not successes. This environment
does not by itself provide a modeling engine. Existing OpenSCAD or a connected Fusion/Blender
can supply geometry; the other checks need the next environment.

## 2. Python modeling environment

Use an installed Python 3.11 to create a virtual environment. Choose a new name if `.venv`
already belongs to a different setup; do not overwrite another project's environment.

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r references/requirements/python-modeling.txt
python scripts/build.py detect
python -m unittest discover -s tests -v
```

On Windows, use `py -3.11 -m venv .venv`, then `.venv\Scripts\Activate.ps1` in PowerShell;
the subsequent `python` commands are the same. If `uv` is already installed, the equivalent
installation is `uv venv --python 3.11 .venv`, followed by
`uv pip install --python .venv/bin/python -r references/requirements/python-modeling.txt`
(use `.venv\Scripts\python.exe` on Windows).

`detect` should list `python` in `available` and report manifold3d, numpy, rtree and matplotlib.
The suite skips Blender and OpenSCAD examples if those engines are absent. For the OpenSCAD
example, install OpenSCAD 2021.01 or newer through the platform's trusted package manager or
official distribution; follow Phase 0's permission and sandbox rules. A version/cube-export
probe failure excludes OpenSCAD from `available` and is explained in `warnings`.

## 3. Blender through bpy

In the Python 3.11 virtual environment above:

```bash
python -m pip install -r references/requirements/blender-4.5.txt
python -c "import bpy; print(bpy.app.version_string)"
python scripts/build.py detect
python -m unittest discover -s tests -v
```

Linux needs the shared libraries used by the wheel and headless Mesa renderer. The Ubuntu CI
installs `libgl1 libegl1 libglx-mesa0 libgl1-mesa-dri libsm6 libice6 libxi6 libxrender1 libxfixes3
libxkbcommon0 libxxf86vm1 libxext6` with apt before installing the wheel. On other platforms,
use the platform's supported libraries rather than copying Linux commands. A wheel import
alone does not prove that rendering works: the suite's Blender coaster and render tests do.

`build.py` and `render.py` prefer a supported binary, otherwise a supported bpy interpreter.
An old/unresponsive `BLENDER_PYTHON` candidate does not hide the current interpreter. To force
one interpreter, use `--blender-python /path/to/venv/python`; an explicit choice fails rather
than silently switching to a different interpreter, and `detect --blender-python` reports that
interpreter alone, so it lists Blender only when that build would work.

If pip reports no matching bpy distribution, check the Python version, OS and architecture
against the published wheel first. Keep TLS, artifact checksum and package verification enabled.
A package metadata error is not a reason to edit the wheel's tags or bypass verification.

## Real Blender executable smoke test

The bpy suite and its emulated-binary test do not establish that an installed Blender binary
works. With a real Blender 4.5+ executable, use the host Python environment with numpy:

```bash
python scripts/smoke_blender.py --blender /path/to/blender --out out/binary-smoke
```

Use a new output directory on each run. The script refuses an unsupported binary and does not
count a bpy fallback as success. It builds a block with a boolean hole, requires the mesh/size
gate to pass, reopens the generated `.blend` with a separate factory-startup binary process,
and renders a sane four-view PNG through that binary. Artifacts and subprocess logs stay in
the output directory. It does not slice, print, connect to a live Blender or change preferences.

The `tests` workflow has a separate weekly/manual `blender-binary-smoke` job on Linux x86_64.
It checks that the pinned archive and SHA256 list are present in the official
`https://download.blender.org/release/Blender4.5/` directory, downloads them over verified HTTPS,
checks the archive SHA256, then extracts and runs the executable. A missing release/checksum
or a mismatch fails the job; no unverified fallback is installed. The job preserves artifacts
and logs. Other jobs retain the full bpy and cross-platform Python checks.

Behind a restricted network the job needs `download.blender.org`; allowing that host is a
separate decision from running the test.

## Conversation checks when editing the skill

These are review scenarios for instructions, not Python unit tests or a claim that an agent
has executed the conversations successfully. Exercise them with the target agent before a
release and record its actual questions, actions and final claims.

| Scenario | Expected behavior |
|---|---|
| Request already gives printer, slicer, dimensions and choice C | Reuse those answers; do not ask again because a settings file is absent. New concept/base-shape reviews still apply. |
| User chooses D, an existing model | Deliver the source link, licence/download guidance and remaining checks; do not generate a substitute or claim mesh verification. |
| Hole compensation settings unknown | Follow the single `unknown` row in tolerances.md; do not assume compensation is off. |
| Bambu printer, project from a generated template | Record `model`: the delivered project carries the system preset with both corrections off. Do not ask the user for settings the project already fixes. |
| User requests a change to the working project | Update relevant generator/state fields, preserve unrelated content, and write new delivery versions without overwriting originals. |
| User explicitly requests unattended execution | Preserve supplied answers, record defaults at remaining stops, and stop for unsourced critical fit dimensions. Mere silence does not enable the mode. |

## Release readiness

Run the relevant tests and inspect their counts and skips, then the full suite once the
implementation is stable. Validate the Agent Skills format with `agentskills validate .`
(`skills-ref==0.1.1` provides that command). Documentation and requirements live under
`references/`, and the binary smoke command under `scripts/`, so the existing release ZIP
includes them. A release candidate is not a published GitHub release; tagging/publishing is
a separate action.
