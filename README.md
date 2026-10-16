# 3dprint-scout

[한국어](README.ko.md)

An agent skill for designing things to 3D print, **reference-first**.

Tell your agent what you want to make. It first finds existing models and lets you reference one,
mix several, start from scratch, or just print one that already does the job. Then it models the
part, checks it with numbers, and hands you files ready for your printer and slicer. For Bambu
Studio, that is a project file with the print settings already set per object.

## How a request runs

1. **References** — four existing models from Printables, Thingiverse, MakerWorld and others, with
   their licenses. You pick: **A** reference one, **B** mix ideas, **C** original, **D** use as is.
2. **Printer and slicer** — asked in plain words ("Which printer do you have, and which program do
   you open print files in? It's fine if you don't know the program."). Sensible defaults when you don't know.
3. **Dimensions** — a table of every dimension with its source (your caliper, an official spec,
   or two secondary sources that agree). Nothing is invented. For parts that must fit an object of
   uncertain shape, it offers a small fit-test piece first.
4. **Modeling** — the engine is chosen by the shape: Fusion (through MCP), then OpenSCAD, for
   mechanical parts; Python ([manifold3d](https://github.com/elalish/manifold)) for organic shapes,
   and as the fallback.
5. **Verification** — every part is checked: size, bed fit, watertight mesh, overhangs, wall
   thickness, fresh evidence (the STL must match the current source and parameters).
6. **Delivery** — STL per part plus a 3MF that fits your slicer, with print-setting changes and the
   reason for each.

The agent stops for your choice after references and after the dimension table.

## Install

**Claude (web and desktop).** Download `3dprint-scout-v<version>.zip` from the
[latest release](../../releases/latest), then go to **Customize > Skills**, click **+**, choose
**Create skill > Upload a skill**, and upload the zip. Code execution must be enabled
([how skills work in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)).

**Claude Code.** Clone into your personal skills folder (or a project's `.claude/skills/`):

```bash
git clone https://github.com/madrobotnet/3dprint-scout ~/.claude/skills/3dprint-scout
```

**Other agents.** The skill follows the [Agent Skills](https://agentskills.io) format and names no
agent-specific tools, so any agent that loads `SKILL.md` skills can use the same folder. Copy it to
wherever your agent reads skills from.

Then just ask, in any language: *"I want a wall hook for a 6 mm dowel"*, *"make a case for this
PCB"*, *"X2D 프린터 문 손잡이를 만들고 싶어"*.

## Requirements

- Python 3.9 or newer (tested on 3.9 and 3.13). The scripts use the standard library only, except where noted.
- One modeling engine: **Fusion** with an MCP connection, **OpenSCAD** (2021.01 or a newer build
  with the Manifold backend), or `pip install manifold3d`.
- Optional: `numpy` and `rtree` for the wall-thickness check (skipped and reported as unverified
  without them).

## Bambu Studio

For Bambu Lab printers the skill writes a Bambu Studio project (open it with **File > Open
Project**). It needs a template project, made one of two ways:

- **Generated (default).** `bambu_template.py` writes an empty project that only *names* system
  presets, for example `0.20mm Standard @BBL X2D` and Bambu PLA Basic. When Bambu Studio opens it,
  it fills in every value from the presets installed on your computer. No settings are copied, and
  the file holds no personal data.
- **Saved.** If you print with your own process preset or want your exact AMS filament set, save an
  empty project in Bambu Studio and give it to the skill. Such a file contains your preset and
  your Bambu account ID: the skill blanks the ID in every file it writes, but keep the template
  itself private.

Per-object settings (supports, brim, walls, infill, layer height and a few more) come only from an
allowlist with range checks. Keys that can run programs or rewrite G-code are never written.

## What it writes in your project

| Path | Contents |
|---|---|
| `.3dprint/params.json` | Every dimension, with assumptions taken when you weren't asked |
| `.3dprint/printers.json` | Your printer: bed, nozzles, slicer, template (no serials, access codes or IPs) |
| `.3dprint/templates/` | Bambu Studio template. A saved one holds your account ID: keep it private |
| `out/` | Working folder, rewritten on every build: STLs, build manifests, a core 3MF |
| a new delivery folder | Final files. Existing files are never overwritten |

## Status

**v0.1.0.** Tested end to end on a Bambu Lab X2D with Bambu Studio 02.08.02.61, with OpenSCAD
2021.01 and manifold3d 3.5.4. Generated templates were also checked against the A1 mini, A1, P1S,
X1C, H2D and H2C profiles. Not yet tested in the app: OrcaSlicer. Planned: a preview script, a
printer-profile importer, bridge and minimum-feature checks. FDM only; no resin.

## Development

```bash
python3 -m unittest discover -s tests
```

`SKILL.md` is the entry point. Engine rules, tolerances and the Bambu details live in
`references/` and are read only when needed.

## License

MIT, see [LICENSE](LICENSE). The code is original. Ideas were taken, not code, from other
3D-printing skills, including
[EdwinjJ1/3d-print-skill](https://github.com/EdwinjJ1/3d-print-skill) and
[flowful-ai/cad-skill](https://github.com/flowful-ai/cad-skill). Bambu Studio's project format was
learned from its open-source code; only file-format constants needed to interoperate are used, and
Bambu's profile data is read at run time (from your installation, or Bambu's public profiles),
never shipped.

Not affiliated with Bambu Lab, Autodesk or any other company named here.
