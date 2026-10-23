# Bambu Studio project files and per-object print settings

Read this in Phase 2 (template question) and Phase 5 when `printers.json` says the slicer is
Bambu Studio.

Contents:

- [Templates](#templates)
  - [Generated template (fallback)](#generated-template-fallback)
  - [Saved project (preferred when the user has the app)](#saved-project-preferred-when-the-user-has-the-app)
- [Build the project file](#build-the-project-file)
- [Where settings live](#where-settings-live)
- [What may be written](#what-may-be-written)
- [Tuning rules (starting points; calibrate with real prints)](#tuning-rules-starting-points-calibrate-with-real-prints)
- [Checked so far](#checked-so-far)

## Templates

Bambu Studio warns "The 3mf file has invalid config, load geometry data only" for any 3MF without
a Bambu printer configuration, including a perfectly valid core 3MF. Never fake a configuration:
`bambu3mf.py` fills a template project instead. There are two kinds.

| Template | Use when | Settings come from |
|---|---|---|
| **Saved project**, ask for it first when the user has Bambu Studio open | Any user who can save a file: it keeps their own process tweaks (arc fitting, speeds, ...) and their exact AMS filament set | The empty project the user saved |
| **Generated** (`bambu_template.py`), the fallback | The user cannot or will not save one, or an unattended run; it names system presets only, so personal process changes are lost | The system presets installed in the user's Bambu Studio, picked by name |

Store either at `.3dprint/templates/<printer-id>.3mf` and record it in `printers.json` →
`slicer.template_3mf` and `slicer.template_kind` (`generated` or `saved`). Keep the question to
one line (wording under "Saved project"); do not insist, the generated one works.

### Generated template (fallback)

`bambu_template.py` writes an empty project that only **names** system presets and marks nothing as
changed. When Bambu Studio opens it, every value that is not marked as changed is reset to the
installed preset with that name, so the project opens as exactly those presets with the user's own
values. The script copies no setting values; it reads only names and a few printer facts (printer
model, nozzle count, bed area, default bed type, filament id and type).

```bash
python3 "$SKILL_DIR/scripts/bambu_template.py" --profiles PROFILES \
  --printer "Bambu Lab X2D 0.4 nozzle" --app-version 02.08.02.61 --out .3dprint/templates/x2d.3mf
```

- `--printer`: the printer preset, "<printer name> <nozzle> nozzle".
- `--app-version`: the user's Bambu Studio version (Help > About). **Never newer than the user's
  app**: a newer file opens with a "newer version" dialog. Ask it with the Phase 2 printer
  question, as optional ("Help > About; fine if you do not know"). Unknown, attended or not: use
  the version of the profiles you read, say so, and record it in `_assumptions`.
- Defaults: the printer's own default process (usually `0.20mm Standard @BBL <model>`), its
  default filament (usually Bambu PLA Basic) in white, and the model's default build plate. Pass
  `--filament` and `--colour` once per AMS slot to match what the user has loaded, and `--process`
  or `--bed-type` to change the others.
- `PROFILES` is a folder with `BBL.json`, first one that exists:
  1. The user's Bambu Studio, read-only. The data folder is `%APPDATA%\BambuStudio` on Windows,
     `~/Library/Application Support/BambuStudio` on macOS and `$XDG_CONFIG_HOME/BambuStudio`
     (default `~/.config/BambuStudio`) on Linux (`GUI_App.cpp`, `init_app_config`, app key
     `BambuStudio`); the updated system profiles are in its `system` subfolder and the user's own
     presets under `user/<id>/` (`PresetBundle.cpp`, `PRESET_SYSTEM_DIR` / `PRESET_USER_DIR`). The copy
     shipped with the app is in `resources/profiles` of the install folder. Read the bed and nozzle
     areas from there first (`references/phase-2-printer-dimensions.md`), the manufacturer's spec page second, and the public
     profiles below third; never a reseller page.
  2. Without access to the user's computer: Bambu's public profiles at the tag of the user's
     version (`v` + version), names and facts only:

     ```bash
     git clone -q --depth 1 --branch v02.08.02.61 --filter=blob:none --sparse \
       https://github.com/bambulab/BambuStudio bbs-profiles
     git -C bbs-profiles sparse-checkout set --no-cone /resources/profiles/BBL.json \
       /resources/profiles/BBL/machine/ /resources/profiles/BBL/process/ /resources/profiles/BBL/filament/
     # PROFILES = bbs-profiles/resources/profiles
     ```

  Bambu's profile files are AGPL-licensed: read them on the user's side, never copy them into the
  skill or its outputs.
- If neither source is reachable, fall back to STL plus core 3MF (SKILL.md, Phase 6).

Bambu Studio's command line (`--load-settings`, `--export-3mf`) was checked and is not used: it
needs fully resolved preset files that are not in the profile folders, and it cannot export a
project without a model.

### Saved project (preferred when the user has the app)

Ask once, in plain words: "In Bambu Studio, pick your printer, filaments and print profile, then
save an empty project (File > Save Project As) and send me the file. If you are not sure which
print profile to pick, the standard one (for example `0.20mm Standard`) is fine." If no file comes,
generate one.

Do not ask for the user's Bambu account id or read it from the app: nothing needs it. A saved
project does contain the owner's name and account id as metadata; `bambu3mf.py` blanks them in every
file it writes (Bambu Studio fills them in again when a signed-in user saves). Still treat a saved
template as private: never commit it to a public repository or send it anywhere else.

Do not ship ready-made templates with the skill: a template newer than the user's Bambu Studio
opens with a "newer version" dialog, every printer and nozzle needs its own, and a saved project
holds values from Bambu's AGPL-licensed profiles.

## Build the project file

```bash
python3 "$SKILL_DIR/scripts/bambu3mf.py" job.json
```

```json
{"template": ".3dprint/templates/x2d.3mf", "out": "out/part_bambu.3mf",
 "printer": ".3dprint/printers.json", "params": ".3dprint/params.json",
 "parts": [{"name": "body", "stl": "out/body.stl", "plate": 1, "filament": 1,
            "settings": {"wall_loops": 4}, "reasons": {"wall_loops": "load-bearing hook"}},
           {"name": "label", "stl": "out/label.stl", "object": "body", "filament": 2},
           {"name": "lid", "stl": "out/lid.stl", "plate": 1}]}
```

- The template's `project_settings.config` is copied byte for byte: the preset is untouched. If
  that preset runs a post-processing script (`post_process`), the output carries a warning and
  the preset is still left as the user saved it.
- From the template only what a project needs is taken: `[Content_Types].xml`, `_rels/.rels`,
  `project_settings.config`, the user's embedded presets (`Metadata/process_settings_*.config`
  and the print, filament and machine equivalents, written when the template uses a preset the
  user made), the plate-1 thumbnails and the `slice_info.config` header. Sliced
  G-code, plate JSON, auxiliaries, cut or layer-range files and any objects the template held are
  dropped (listed in `dropped_template_entries`; a non-empty template gets a warning). Owner
  metadata is blanked (`Designer`, `DesignerUserId`, `DesignerCover`, `ProfileCover`,
  `ProfileUserId`, `ProfileUserName`, `Origin`) and MakerWorld markers are removed (`model_id`,
  `Region`, `DesignId`, `MakerLab`, `MakerLabVersion`).
- **Objects and parts.** A part with `object` joins the object of that name: one Bambu object
  with several parts, each shown and selectable in the object list, placed as modelled (the STL
  coordinates are the assembled positions). The first part listed is the main part: its `plate`,
  `filament`, `settings` and `reasons` apply to the object; other parts take the main filament
  unless they name their own (a `settings` entry on another part is refused). `params` lets the
  job take `object` and `filament` from `_parts` so the grouping is written once (`parts.md`).
- Objects are centred on the plate, side by side; `plate` puts an object on another plate (plates
  are laid out at bed size × 1.2, as Bambu Studio does). `filament` is the template's filament slot
  (1-based). An object that only fits rotated is placed with that Z rotation in the build item (the
  same angle validate.py's D2 reports; the STLs are unchanged) and the output says so in `warnings`.
- **Nozzle areas (X2D, H2D).** With `printer`, the usable area is the intersection of the tools'
  reachable areas from `printers.json` whenever an object has several parts or the job uses more
  than one filament, support and interface filaments included (which nozzle prints which filament
  is decided in the app, so both must reach the part); a single-filament job of single-part
  objects keeps the full bed. `"tools": "all"` or
  `[0, 1]` forces it. `usable_area` and `usable_area_reason` are in the output.
- The output's `warnings` end with one line naming the separate parts and their filaments; repeat
  it at delivery with "select the part in the object list to change its filament".
- The script refuses to overwrite an existing file; there is no override, choose a new name. Tell
  the user to open the result with **Open Project** so plates and settings are kept.
- Next to the project it writes `<out>.manifest.json` (the project's sha256 and each part STL's),
  replacing a stale one of that name: `finalize.py --deliver` takes the project as verified only
  with it. Write the project straight into the delivery folder, or copy the sidecar along.
- The manifest also records what the project selects: `filaments`, each part's filament slot and
  the template's filament preset name for that slot (`filament_settings_id`), and `process`, the
  template's process preset name (`print_settings_id`); a name the template does not give is
  `null`. `finalize.py --deliver` compares them with each part's declared material (`_material`,
  `_parts.<name>.material`) and `_print.preset`. A core 3MF selects neither, so its manifest has
  neither key.

## Where settings live

| Level | Stored in | Used by this skill |
|---|---|---|
| Global (the user's preset) | `Metadata/project_settings.config` | Never changed |
| Plate | `<plate>` in `model_settings.config` | Not in v1 |
| Object | `<object>` metadata in `model_settings.config` | **Yes: every change goes here** |
| Part / modifier, height range | `<part>` metadata, `layer_config_ranges.xml` | Not in v1 |

Object-level overrides show up in Bambu Studio's object list and can be removed per object, so the
user keeps full control.

## What may be written

`bambu3mf.py` accepts only keys on its allowlist (object- or region-level keys of Bambu Studio
02.08): layer height; supports (on/off, type, threshold angle, build plate only); support
interface (`support_interface_filament`, `support_filament`: a filament slot or 0 for the object's
own; `support_top_z_distance`, `support_bottom_z_distance`: 0–1 mm, 0 when the interface filament
is meant to touch the part); brim (type, width, gap); raft layers; seam position; wall generator;
hole, contour, circle and elephant-foot compensation; wall loops; top and bottom shell layers and
thickness; sparse infill density and pattern; ironing type; thin-wall detection; fuzzy skin.

It refuses, with a message:
- anything that can run programs or rewrite G-code (`post_process`, `*_gcode`);
- keys the template's Bambu Studio version does not know;
- keys the preset stores per extruder (a list, as with speeds on dual-nozzle printers);
- values out of range or not one of the allowed choices.

## Tuning rules (starting points; calibrate with real prints)

Only change what the part needs, and give every change a reason in `reasons`.

| Signal (from validate.py or the user) | Setting |
|---|---|
| P2 overhang WARN, user chose supports | `enable_support: true`, `support_type: "tree(auto)"` |
| Height ÷ smallest base width > 3 (tipping risk) | `brim_type: "outer_only"`, `brim_width: 5`–`8` |
| Purpose load-bearing | `wall_loops: 4`, `sparse_infill_density: 25`–`40`, `sparse_infill_pattern: "gyroid"` |
| Purpose decorative with large flat tops | `ironing_type: "top"` |
| Smallest feature under twice the nozzle size | `layer_height: 0.12`–`0.16` (see constraint below) |
| Thin walls detected (P3 WARN), or text strokes under 1.2 mm (`design.md`, text) | `wall_generator: "arachne"`, `detect_thin_wall: true` |
| Part holds water or soil (a planter, a tray, a cup) | `wall_loops`: enough lines to fill the designed wall (wall ÷ 0.45 mm, `design.md`); `bottom_shell_layers`: 6 or more, or the whole floor (floor ÷ layer height), so no infill sits under the water (starting point: the system presets have 3; a planter reference in a 2026-10 test run asked for 6) |
| Supports on a PETG part and a PLA slot is loaded (or the reverse) | `support_interface_filament: <that slot>`, `support_top_z_distance: 0`: the interface peels off cleanly because the two materials do not bond (starting point; the user set this by hand three times in the 2026-10-17 test) |

Constraints:
- Compensation lives in one place (tolerances.md). If the template's preset has
  `enable_circle_compensation: "1"` or a nonzero `xy_hole_compensation`, `compensation.holes` is
  `"slicer"`: holes at nominal size plus the fit clearance, no model compensation. The system
  process presets have both off (`fdm_process_common`, 02.08.02.61) and the project carries them,
  so a generated template means `"model"` (`phase-2-printer-dimensions.md`, step 4).
- Do not give one object a different layer height on a plate that uses a prime tower
  (`enable_prime_tower: "1"`) and several filaments; as far as known the prime tower needs one layer
  height for all objects (not yet confirmed in the app).
- Change only what this part needs: a row of the table, or another need you can name, each with
  its reason (Phase 5). With no such need, write no overrides. The user's preset is the baseline.

## Checked so far

- Structure follows Bambu Studio's own exporter (`bbs_3mf.cpp`): mesh in `3D/Objects/object_N.model`,
  a wrapper object with a component in `3D/3dmodel.model`, Bambu `p:UUID` suffixes, plate membership
  by position.
- Generated from a real Bambu Studio 02.08.02.61 template: settings identical to the template,
  meshes watertight with the same volume as the source STL.
- Generated template (names only), Bambu Studio 02.08.02.61 on an X2D, checked by the user in the
  app (2026-10-16): opened as expected with standard presets, one and two filaments, two plates,
  per-object settings.
- Names-only templates have no values to check keys against, so `bambu3mf.py` relies on its
  allowlist there: every allowed key exists in 02.08.02.61 and none is stored per extruder.
- A build item with a Z rotation (a 300 mm bar that only fits diagonally on a 256 mm bed), checked
  in the app (2026-10-16): placed diagonally inside the plate at the expected size.
- Layout on printers with a strip only one nozzle reaches (X2D, H2D): since v0.3 the job's
  `printer` narrows the usable area to the tools' intersection when more than one tool may be
  involved (several parts in an object, or several filaments); a single-filament job of single-part
  objects still uses the full bed, so a very wide part can land in the strip and Bambu Studio
  shows it (move it or assign the other nozzle).
- Not yet checked in the app: a project built from a template that was saved after slicing (extra
  entries dropped); an object with several parts written by `bambu3mf.py` (the format follows
  `bbs_3mf.cpp`, see `parts.md`); the support interface keys; whether the slicing preview shows no
  inner wall between two same-filament touching parts (the source says they are merged).
