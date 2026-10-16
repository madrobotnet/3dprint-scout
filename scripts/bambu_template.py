#!/usr/bin/env python3
"""
bambu_template.py - write an empty Bambu Studio project that names system presets.

A Bambu Studio project stores the full printer, filament and process settings, but
when it opens one, Bambu Studio resets every value that is not listed as changed to
the value of the installed system preset with the same name (PresetCollection::
load_external_preset -> update_non_diff_values_to_base_config, checked in the
02.08.02.61 source). So a project that only names system presets and lists no changes
opens as those presets, with the values from the user's own installation.

This script writes such a project. It copies no settings values: it reads only names
and a few printer facts (printer model, nozzle count, bed area, default bed type,
filament id and type) from a Bambu profile folder, which can be the user's installed
Bambu Studio or Bambu's public profiles at the same version. bambu3mf.py then fills the
project with parts.

Usage:
  python3 bambu_template.py --profiles DIR --printer "Bambu Lab X2D 0.4 nozzle" \
      --app-version 02.08.02.61 --out .3dprint/templates/x2d.3mf
      [--process "0.20mm Standard @BBL X2D"] [--filament NAME ...] [--colour "#RRGGBB" ...]
      [--bed-type "Textured PEI Plate"]

  DIR is a folder with BBL.json (Bambu Studio's resources/profiles, or the updated copy
  in the app's data folder "system"). Without --process / --filament the printer's own
  defaults are used (for most printers "0.20mm Standard" and Bambu PLA Basic).
  --app-version must not be newer than the user's Bambu Studio (Help > About), or it
  opens the file with a "newer version" dialog.

Prints one JSON document; exit 0 on success, 1 on error. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import struct
import sys
import zipfile
import zlib

SCHEMA = "3dprint-scout.bambu_template/1"
VENDOR = "BBL"
DEFAULT_COLOUR = "#FFFFFF"
# File-format interoperability constants: the values Bambu Studio itself writes for a project
# that has never had its flush volumes edited (PrintConfig.cpp defaults for the off-diagonal
# flush_volumes_matrix entries and for flush_volumes_vector). They are facts about the file
# format needed to produce a readable project, not profile data.
FLUSH_DEFAULT = "280"
FLUSH_VECTOR_DEFAULT = "140"


class TemplateError(Exception):
    pass


class _JsonArgParser(argparse.ArgumentParser):
    def error(self, message):
        raise TemplateError(message)


# --------------------------------------------------------------------------- #
# Profiles (names and facts only)
# --------------------------------------------------------------------------- #
class Profiles:
    def __init__(self, folder: str):
        index = os.path.join(folder, f"{VENDOR}.json")
        if not os.path.isfile(index):
            raise TemplateError(f"no {VENDOR}.json in {folder}; pass Bambu Studio's resources/profiles "
                                "folder or the app's data folder 'system'")
        with open(index, encoding="utf-8") as f:
            data = json.load(f)
        self.folder = folder
        self.paths = {}
        for key in ("machine_model_list", "machine_list", "process_list", "filament_list"):
            for entry in data.get(key, []):
                self.paths[entry["name"]] = os.path.join(folder, VENDOR, entry["sub_path"])
        self.profile_version = data.get("version", "")

    def raw(self, name: str) -> dict:
        path = self.paths.get(name)
        if not path or not os.path.isfile(path):
            raise TemplateError(f"preset '{name}' is not in this Bambu Studio's profiles")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def resolve(self, name: str) -> dict:
        """Merge the inherits chain, child values winning (as Bambu Studio does)."""
        chain, seen = [], set()
        while name:
            if name in seen:
                raise TemplateError(f"inheritance loop at '{name}'")
            seen.add(name)
            d = self.raw(name)
            chain.append(d)
            name = d.get("inherits", "")
        merged = {}
        for d in reversed(chain):
            merged.update(d)
        merged["name"] = chain[0].get("name")
        merged["instantiation"] = chain[0].get("instantiation", "false")
        return merged


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _first(v, default=""):
    lst = _as_list(v)
    return str(lst[0]).strip() if lst else default


def _compatible(preset: dict, printer: str) -> bool:
    printers = _as_list(preset.get("compatible_printers"))
    return not printers or printer in printers


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #
def blank_png(w: int, h: int) -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x00" * (4 * w) for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="png" ContentType="image/png"/>
 <Default Extension="gcode" ContentType="text/x.gcode"/>
</Types>
"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
 <Relationship Target="/Metadata/plate_1.png" Id="rel-2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/>
 <Relationship Target="/Metadata/plate_1.png" Id="rel-4" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-middle"/>
 <Relationship Target="/Metadata/plate_1_small.png" Id="rel-5" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-small"/>
</Relationships>
"""

MODEL_META = ["Copyright", "Description", "Designer", "DesignerCover", "DesignerUserId", "License", "Origin",
              "ProfileCover", "ProfileDescription", "ProfileTitle", "Title"]


def model_xml(app_version: str, today: str) -> str:
    meta = {"Application": f"BambuStudio-{app_version}", "BambuStudio:3mfVersion": "1",
            "CreationDate": today, "ModificationDate": today}
    meta.update({k: "" for k in MODEL_META})
    lines = "".join(f' <metadata name="{k}">{meta[k]}</metadata>\n' for k in sorted(meta))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
            'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
            'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">\n'
            + lines + " <resources>\n </resources>\n <build/>\n</model>\n")


def model_settings_xml(multi_extruder: bool) -> str:
    extra = '    <metadata key="filament_map_mode" value="Auto For Flush"/>\n' if multi_extruder else ""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <plate>\n'
            '    <metadata key="plater_id" value="1"/>\n'
            '    <metadata key="plater_name" value=""/>\n'
            '    <metadata key="locked" value="false"/>\n' + extra +
            '    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>\n'
            '    <metadata key="thumbnail_no_light_file" value="Metadata/plate_no_light_1.png"/>\n'
            '    <metadata key="top_file" value="Metadata/top_1.png"/>\n'
            '    <metadata key="pick_file" value="Metadata/pick_1.png"/>\n'
            '  </plate>\n  <assemble>\n  </assemble>\n</config>\n')


def slice_info_xml(app_version: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <header>\n'
            '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
            f'    <header_item key="X-BBL-Client-Version" value="{app_version}"/>\n'
            '  </header>\n</config>\n')


# --------------------------------------------------------------------------- #
# Project settings
# --------------------------------------------------------------------------- #
def project_settings(prof: Profiles, args) -> tuple[dict, dict]:
    printer = prof.resolve(args.printer)
    if printer.get("type") != "machine" or printer["instantiation"] != "true":
        raise TemplateError(f"'{args.printer}' is not a selectable printer preset")
    model_name = str(printer.get("printer_model", "")).strip()
    if not model_name:
        raise TemplateError(f"'{args.printer}' has no printer_model")
    model = prof.raw(model_name)

    process_name = args.process or str(printer.get("default_print_profile", "")).strip()
    if not process_name:
        raise TemplateError("the printer names no default process preset; pass --process")
    process = prof.resolve(process_name)
    if process.get("type") != "process" or process["instantiation"] != "true":
        raise TemplateError(f"'{process_name}' is not a selectable process preset")
    if not _compatible(process, args.printer):
        raise TemplateError(f"'{process_name}' is not compatible with '{args.printer}'")

    filament_names = args.filament or [_first(printer.get("default_filament_profile"))]
    if not filament_names or not filament_names[0]:
        raise TemplateError("the printer names no default filament; pass --filament")
    colours = args.colour or []
    if len(colours) > len(filament_names):
        raise TemplateError("more --colour values than filaments")
    for c in colours:
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", c):
            raise TemplateError(f"colour '{c}' is not #RRGGBB")
    colours = [c.upper() for c in colours] + [DEFAULT_COLOUR] * (len(filament_names) - len(colours))

    fil = []
    for name in filament_names:
        f = prof.resolve(name)
        if f.get("type") != "filament" or f["instantiation"] != "true":
            raise TemplateError(f"'{name}' is not a selectable filament preset")
        if not _compatible(f, args.printer):
            raise TemplateError(f"'{name}' is not compatible with '{args.printer}'")
        fil.append({"name": name, "id": _first(f.get("filament_id")), "type": _first(f.get("filament_type")),
                    "vendor": _first(f.get("filament_vendor")),
                    "variant": _first(f.get("filament_extruder_variant"), "Direct Drive Standard")})

    nozzles = [str(x).strip() for x in _as_list(printer.get("nozzle_diameter"))]
    if not nozzles:
        raise TemplateError(f"'{args.printer}' has no nozzle_diameter")
    area = [str(p).strip() for p in _as_list(printer.get("printable_area"))]
    if len(area) < 3:
        raise TemplateError(f"'{args.printer}' has no printable_area")
    bed_type = args.bed_type or str(model.get("default_bed_type", "")).strip()
    if not bed_type:
        raise TemplateError("the printer model names no default bed type; pass --bed-type")

    n, e = len(fil), len(nozzles)
    ys = [float(p.partition("x")[2]) for p in area]
    cfg = {
        "name": "project_settings",
        "from": "project",
        "version": args.app_version,
        "printer_model": model_name,
        "printer_settings_id": args.printer,
        "print_settings_id": process_name,
        "print_compatible_printers": [args.printer],
        "filament_settings_id": [f["name"] for f in fil],
        "filament_ids": [f["id"] for f in fil],
        "filament_type": [f["type"] for f in fil],
        "filament_vendor": [f["vendor"] for f in fil],
        # Nothing differs from the system presets: Bambu Studio fills every value from them.
        "inherits_group": [""] * (n + 2),
        "different_settings_to_system": [""] * (n + 2),
        # One extruder variant per filament keeps the loader's variant bookkeeping trivial.
        "filament_extruder_variant": [f["variant"] for f in fil],
        "filament_self_index": [str(i + 1) for i in range(n)],
        "nozzle_diameter": nozzles,
        "printable_area": area,
        # Project-level values (PresetBundle s_project_options) come from the file, not presets.
        "curr_bed_type": bed_type,
        "filament_colour": colours,
        "filament_multi_colour": list(colours),
        "filament_map": ["1"] * n,
        "filament_volume_map": ["0"] * n,
        "filament_nozzle_map": ["0"] * n,
        "filament_is_mixed": ["0"] * n,
        "flush_volumes_matrix": [("0" if i == j else FLUSH_DEFAULT) for _ in range(e) for i in range(n) for j in range(n)],
        "flush_volumes_vector": [FLUSH_VECTOR_DEFAULT] * (2 * n),
        "flush_multiplier": ["1"] * e,
        "nozzle_volume_type": ["Standard"] * e,
        "wipe_tower_x": ["15"],
        "wipe_tower_y": [f"{max(0.0, min(220.0, max(ys) - 50)):g}"],
    }
    if printer.get("extruder_type"):
        cfg["extruder_type"] = [str(x).strip() for x in _as_list(printer["extruder_type"])]
    facts = {"printer_model": model_name, "printer_preset": args.printer, "process_preset": process_name,
             "filaments": [{"preset": f["name"], "filament_id": f["id"], "type": f["type"], "colour": c}
                           for f, c in zip(fil, colours)],
             "extruders": e, "bed_type": bed_type, "printable_area": area,
             "profile_version": prof.profile_version}
    return cfg, facts


def write(out: str, cfg: dict, app_version: str, multi_extruder: bool) -> None:
    if os.path.exists(out):
        raise TemplateError(f"{out} already exists; refusing to overwrite")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    today = datetime.date.today().isoformat()
    big, small = blank_png(512, 512), blank_png(128, 128)
    entries = [
        ("[Content_Types].xml", CONTENT_TYPES.encode()),
        ("Metadata/plate_1.png", big),
        ("Metadata/plate_1_small.png", small),
        ("Metadata/plate_no_light_1.png", big),
        ("Metadata/top_1.png", big),
        ("Metadata/pick_1.png", big),
        ("3D/3dmodel.model", model_xml(app_version, today).encode()),
        ("Metadata/project_settings.config", json.dumps(cfg, indent=4, ensure_ascii=False).encode()),
        ("Metadata/model_settings.config", model_settings_xml(multi_extruder).encode()),
        ("Metadata/slice_info.config", slice_info_xml(app_version).encode()),
        ("Metadata/filament_sequence.json",
         json.dumps({"plate_1": {"nozzle_sequence": [], "optimal_assignment": [], "sequence": []}},
                    separators=(",", ":")).encode()),
        ("_rels/.rels", RELS.encode()),
    ]
    with zipfile.ZipFile(out, "w") as z:
        for name, data in entries:
            z.writestr(name, data, compress_type=zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED)


def main(argv=None):
    out = {"schema": SCHEMA, "ran": False, "errors": []}
    try:
        ap = _JsonArgParser(add_help=False)
        ap.add_argument("--profiles", required=True)
        ap.add_argument("--printer", required=True)
        ap.add_argument("--app-version", required=True)
        ap.add_argument("--out", required=True)
        ap.add_argument("--process")
        ap.add_argument("--filament", action="append")
        ap.add_argument("--colour", action="append")
        ap.add_argument("--bed-type")
        args = ap.parse_args(sys.argv[1:] if argv is None else argv)
        if not re.fullmatch(r"\d{2}\.\d{2}\.\d{2}\.\d{2}", args.app_version):
            raise TemplateError("--app-version looks like 02.08.02.61 (Bambu Studio > Help > About)")
        cfg, facts = project_settings(Profiles(args.profiles), args)
        write(args.out, cfg, args.app_version, facts["extruders"] > 1)
        out.update({"ran": True, "out": args.out, "app_version": args.app_version, **facts})
    except (TemplateError, OSError, ValueError, KeyError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
