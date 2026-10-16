#!/usr/bin/env python3
"""
bambu3mf.py - build a Bambu Studio project 3MF from the user's own template project.

Bambu Studio warns "The 3mf file has invalid config, load geometry data only" for any
3MF without a valid Bambu printer configuration. The fix is not to fake one: the user
saves an empty project once (their printer, filaments and process preset), and this
script fills that template with parts. The template's project_settings.config is
copied byte for byte, so the user's preset stays exactly as they saved it.

Per-object settings are written as differences from that preset, only for keys in
ALLOWED below (object- or region-level keys, checked against the Bambu Studio
02.08.02.61 source), only for keys the template's Bambu Studio version knows, and only
with values that pass type and range checks. Keys that can run programs or rewrite
G-code (post_process, *_gcode) can never be written.

Only the entries a project needs are taken from the template ([Content_Types].xml,
_rels/.rels, project_settings.config, embedded user presets, the plate-1 thumbnails, the
slice_info header);
sliced G-code, plate JSON, auxiliaries and any objects the template held are dropped, and
identifying metadata (designer, account id, MakerWorld model id and region, profile
owner) is blanked or removed. The output path must not exist: the script never
overwrites a file.

Usage (one JSON job file):
  python3 bambu3mf.py job.json

  {"template": ".3dprint/templates/x2d.3mf", "out": "out/aa_box_bambu.3mf",
   "parts": [{"name": "box", "stl": "out/box.stl", "plate": 1, "filament": 1,
              "settings": {"wall_loops": 4}, "reasons": {"wall_loops": "load-bearing"}},
             {"name": "lid", "stl": "out/lid.stl", "plate": 1}]}

Prints one JSON document; exit 0 on success, 1 on error. Standard library only.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import zipfile
from xml.sax.saxutils import quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from threemf import indexed  # noqa: E402
from validate import ArtifactError, convex_hull, fit_rect, read_stl  # noqa: E402

SCHEMA = "3dprint-scout.bambu3mf/1"
CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
BBS_NS = "http://schemas.bambulab.com/package/2021"
MODEL_REL_TYPE = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
# File-format interoperability constants: the fixed p:UUID suffixes Bambu Studio writes into
# its own project files and uses to recognise objects, sub-objects, components and build items
# on load (bbs_3mf.cpp). They are identifiers in a file format, not program code, and carry no
# user data.
OBJECT_UUID_SUFFIX = "-61cb-4c03-9d28-80fed5dfa1dc"
SUB_OBJECT_UUID_SUFFIX = "-81cb-4c03-9d28-80fed5dfa1dc"
COMPONENT_UUID_SUFFIX = "-b206-40ff-9872-83e8017abed1"
BUILD_UUID = "2c7c17d8-22b5-4d84-8835-1976022ea369"
BUILD_UUID_SUFFIX = "-b1ec-4553-aec9-835e5b724bb4"
# Metadata in 3D/3dmodel.model that identifies the template's owner or its MakerWorld origin
# (names from bbs_3mf.cpp). Blanked ones stay as empty elements, as in a freshly saved
# project; removed ones only exist for downloaded or published models and must not be
# inherited by a new design.
PERSONAL_METADATA = ("Designer", "DesignerUserId", "DesignerCover", "ProfileCover",
                     "ProfileUserId", "ProfileUserName", "Origin")
ORIGIN_METADATA = ("model_id", "Region", "DesignId", "MakerLab", "MakerLabVersion")
# Template entries a project needs (everything else in the template is dropped). A project
# saved with a user-made preset embeds that preset as Metadata/<kind>_<name>.config; without
# it the preset names in project_settings.config would point at nothing (bbs_3mf.cpp,
# PROJECT_EMBEDDED_*_PRESETS_FILE), so those stay too.
TEMPLATE_KEEP = ("[Content_Types].xml", "_rels/.rels", "Metadata/project_settings.config")
TEMPLATE_KEEP_PREFIX = ("Metadata/print_setting_", "Metadata/process_settings_",
                        "Metadata/filament_settings_", "Metadata/machine_settings_")
TEMPLATE_THUMBNAIL = re.compile(r"^Metadata/(?:plate|plate_no_light|top|pick)_1(?:_small)?\.png$")
PLATE_GAP = 0.2            # plates are laid out at bed size * (1 + 1/5) (PartPlate.cpp)
PART_SPACING = 10.0        # mm between parts placed on the same plate

# key: (kind, a, b) — float/int/percent: range a..b; enum: allowed values; bool: -
ALLOWED = {
    # object level
    "layer_height": ("float", 0.04, 0.6),
    "enable_support": ("bool", None, None),
    "support_type": ("enum", ["normal(auto)", "tree(auto)", "normal(manual)", "tree(manual)"], None),
    "support_threshold_angle": ("int", 0, 90),
    "support_on_build_plate_only": ("bool", None, None),
    "brim_type": ("enum", ["no_brim", "outer_only", "inner_only", "outer_and_inner", "auto_brim", "brim_ears"], None),
    "brim_width": ("float", 0, 30),
    "brim_object_gap": ("float", 0, 2),
    "raft_layers": ("int", 0, 100),
    "seam_position": ("enum", ["nearest", "aligned", "back", "random"], None),
    "wall_generator": ("enum", ["classic", "arachne"], None),
    "xy_hole_compensation": ("float", -1, 1),
    "xy_contour_compensation": ("float", -1, 1),
    "enable_circle_compensation": ("bool", None, None),
    "elefant_foot_compensation": ("float", 0, 1),
    # region level
    "wall_loops": ("int", 1, 20),
    "top_shell_layers": ("int", 0, 50),
    "bottom_shell_layers": ("int", 0, 50),
    "top_shell_thickness": ("float", 0, 10),
    "bottom_shell_thickness": ("float", 0, 10),
    "sparse_infill_density": ("percent", 0, 100),
    # The sparse_infill_pattern enum of 02.08.02.61 (PrintConfig.cpp); "monotonic" and
    # "monotonicline" are top_surface_pattern values and are not accepted here.
    "sparse_infill_pattern": ("enum", ["concentric", "zig-zag", "grid", "line", "cubic", "triangles", "tri-hexagon",
                                       "gyroid", "honeycomb", "adaptivecubic",
                                       "alignedrectilinear", "3dhoneycomb", "hilbertcurve", "archimedeanchords",
                                       "octagramspiral", "supportcubic", "lightning", "crosshatch", "zigzag",
                                       "crosszag", "lockedzag", "2dlattice"], None),
    "ironing_type": ("enum", ["no ironing", "top", "topmost", "solid"], None),
    "detect_thin_wall": ("bool", None, None),
    "fuzzy_skin": ("enum", ["none", "external", "all", "allwalls", "disabled_fuzzy"], None),
}


class JobError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Settings validation
# --------------------------------------------------------------------------- #
def normalize(key: str, value) -> str:
    """Return the string Bambu Studio stores for this key, or raise JobError."""
    if key not in ALLOWED:
        if key == "post_process" or key.endswith("_gcode"):
            raise JobError(f"'{key}' can run programs or rewrite G-code and is never written")
        raise JobError(f"'{key}' is not on the per-object allowlist")
    kind, a, b = ALLOWED[key]
    if kind == "bool":
        if value in (True, 1, "1", "true", "True"):
            return "1"
        if value in (False, 0, "0", "false", "False"):
            return "0"
        raise JobError(f"{key}: expected true/false, got {value!r}")
    if kind == "enum":
        if value not in a:
            raise JobError(f"{key}: '{value}' is not one of {a}")
        return value
    if kind == "percent":
        text = str(value).strip().rstrip("%")
        try:
            num = float(text)
        except ValueError:
            raise JobError(f"{key}: expected a percentage, got {value!r}")
        if not a <= num <= b:
            raise JobError(f"{key}: {num}% is outside {a}..{b}%")
        return f"{num:g}%"
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise JobError(f"{key}: expected a number, got {value!r}")
    if not math.isfinite(num) or not a <= num <= b:
        raise JobError(f"{key}: {num} is outside {a}..{b}")
    if kind == "int":
        if num != int(num):
            raise JobError(f"{key}: expected a whole number, got {value!r}")
        return str(int(num))
    return f"{num:g}"


def has_values(template_cfg: dict) -> bool:
    """True for a project saved by Bambu Studio (full settings); False for a names-only
    template from bambu_template.py, whose values come from the installed presets."""
    return "layer_height" in template_cfg


def check_settings(settings: dict, template_cfg: dict) -> dict:
    out = {}
    full = has_values(template_cfg)
    for key, value in (settings or {}).items():
        norm = normalize(key, value)
        # A names-only template has no values to check against; ALLOWED itself was checked
        # against the 02.08.02.61 source (all keys defined, none stored per extruder).
        if full and key not in template_cfg:
            raise JobError(f"'{key}' is unknown to the template's Bambu Studio version")
        if full and isinstance(template_cfg[key], list):
            raise JobError(f"'{key}' holds one value per extruder in this preset; per-object override refused")
        out[key] = norm
    return out


# --------------------------------------------------------------------------- #
# Template
# --------------------------------------------------------------------------- #
def load_template(path):
    if not os.path.isfile(path):
        raise JobError(f"template not found: {path}")
    try:
        with zipfile.ZipFile(path) as z:
            entries = {i.filename: (z.read(i.filename), i.compress_type) for i in z.infolist()}
    except zipfile.BadZipFile:
        raise JobError("template is not a 3MF (zip) file")
    need = ["3D/3dmodel.model", "Metadata/project_settings.config", "Metadata/model_settings.config"]
    missing = [n for n in need if n not in entries]
    if missing:
        raise JobError(f"template is not a Bambu Studio project (missing {missing}); "
                       "save an empty project from Bambu Studio and use that file")
    try:
        cfg = json.loads(entries["Metadata/project_settings.config"][0])
    except ValueError:
        raise JobError("template project_settings.config is not valid JSON")
    if not cfg.get("printer_model"):
        raise JobError("template has no printer_model; Bambu Studio would reject it")
    model = entries["3D/3dmodel.model"][0].decode("utf-8")
    if "BambuStudio" not in model:
        raise JobError("template 3dmodel.model was not written by Bambu Studio")
    return entries, cfg, model


def template_warnings(entries, cfg, model_xml) -> list[str]:
    """Things about the user's template worth saying; none of them stops the build."""
    warns = []
    scripts = [str(x) for x in (cfg.get("post_process") or []) if str(x).strip()]
    if scripts:
        warns.append("the template's preset runs a post-processing script after slicing "
                     f"({'; '.join(scripts)[:120]}); it is the user's own preset and is kept as saved")
    if re.search(r"<item\b", model_xml):
        warns.append("the template is not an empty project: its objects are left out, and its plate "
                     "thumbnails may still show them until Bambu Studio saves the file again")
    return warns


def slice_info_header(entries, cfg) -> bytes:
    """slice_info.config with the header only: a sliced template's per-plate results would
    describe the template owner's old plates, not these parts."""
    version = str(cfg.get("version") or "").strip()
    if "Metadata/slice_info.config" in entries:
        m = re.search(r'key="X-BBL-Client-Version"\s+value="([^"]*)"', entries["Metadata/slice_info.config"][0].decode("utf-8", "replace"))
        if m:
            version = m.group(1)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <header>\n'
            '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
            f'    <header_item key="X-BBL-Client-Version" value="{version}"/>\n'
            '  </header>\n</config>\n').encode("utf-8")


def bed_rect(cfg):
    pts = []
    for p in cfg.get("printable_area", []):
        x, _, y = str(p).strip().partition("x")
        pts.append((float(x), float(y)))
    if len(pts) < 3:
        raise JobError("template has no printable_area")
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def plate_template_block(model_settings: str) -> str:
    m = re.search(r"<plate>(.*?)</plate>", model_settings, re.S)
    if not m:
        raise JobError("template model_settings.config has no <plate> block")
    return m.group(1)


# --------------------------------------------------------------------------- #
# Writer
# --------------------------------------------------------------------------- #
def _f(x: float) -> str:
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def placement(verts, bed_w, bed_d):
    """Z rotation (deg, counter-clockwise) that lets the footprint fit the bed, as D2 decides it,
    plus the footprint [w, d] and the XY centre of the rotated bounding box.

    verts are centred on their unrotated bounding box; rotating about the origin is rotating
    about that centre, so the rotated box's centre is the offset the build item must cancel."""
    xy = [(v[0], v[1]) for v in verts]
    w = max(p[0] for p in xy) - min(p[0] for p in xy)
    d = max(p[1] for p in xy) - min(p[1] for p in xy)
    if w <= bed_w + 1e-6 and d <= bed_d + 1e-6:
        return 0, [w, d], (0.0, 0.0), True
    ok, deg, _, _ = fit_rect(convex_hull(xy), bed_w, bed_d)
    if not ok:
        return 0, [w, d], (0.0, 0.0), False
    cs, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    xs = [x * cs - y * sn for x, y in xy]
    ys = [x * sn + y * cs for x, y in xy]
    return deg, [max(xs) - min(xs), max(ys) - min(ys)], ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2), True


def rotation_matrix(deg):
    """3MF transform prefix (row-vector convention) for a counter-clockwise Z rotation."""
    if not deg:
        return "1 0 0 0 1 0 0 0 1"
    cs, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return f"{_f(cs)} {_f(sn)} 0 {_f(-sn)} {_f(cs)} 0 0 0 1"


def layout(parts, bed):
    """Shelf-pack each plate's parts, centred on the bed. Returns {index: (x, y)} of part centres."""
    x0, y0, x1, y1 = bed
    W, D = x1 - x0, y1 - y0
    by_plate = {}
    for i, p in enumerate(parts):
        by_plate.setdefault(p["plate"], []).append(i)
    pos = {}
    for plate, idx in by_plate.items():
        rows, row, row_w, row_d = [], [], 0.0, 0.0
        for i in idx:
            w, d = parts[i]["footprint"][0], parts[i]["footprint"][1]
            if not parts[i]["fits"]:
                raise JobError(f"part '{parts[i]['name']}' ({w:.1f} x {d:.1f} mm) does not fit the "
                               f"{W:.0f} x {D:.0f} mm bed at any rotation")
            if row and row_w + PART_SPACING + w > W:
                rows.append((row, row_w, row_d)); row, row_w, row_d = [], 0.0, 0.0
            row_w += (PART_SPACING if row else 0) + w
            row_d = max(row_d, d)
            row.append(i)
        rows.append((row, row_w, row_d))
        total_d = sum(r[2] for r in rows) + PART_SPACING * (len(rows) - 1)
        if total_d > D:
            raise JobError(f"parts on plate {plate} do not fit together; put some on another plate")
        y = y0 + D / 2 + total_d / 2
        for row, rw, rd in rows:
            x = x0 + W / 2 - rw / 2
            for i in row:
                w, d = parts[i]["footprint"][0], parts[i]["footprint"][1]
                pos[i] = (x + w / 2, y - rd / 2)
                x += w + PART_SPACING
            y -= rd + PART_SPACING
    return pos


def object_model_xml(sub_id: int, backup_id: int, verts, faces) -> str:
    uuid = f"{(backup_id << 16):08x}{SUB_OBJECT_UUID_SUFFIX}"
    vx = "".join(f'<vertex x="{_f(v[0])}" y="{_f(v[1])}" z="{_f(v[2])}"/>' for v in verts)
    tr = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}" xmlns:BambuStudio="{BBS_NS}" '
            f'xmlns:p="{PROD_NS}" requiredextensions="p">\n'
            ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
            f'  <object id="{sub_id}" p:UUID="{uuid}" type="model">\n'
            f"   <mesh><vertices>{vx}</vertices><triangles>{tr}</triangles></mesh>\n"
            "  </object>\n </resources>\n <build/>\n</model>\n")


def build(job: dict) -> dict:
    entries, cfg, model_xml = load_template(job["template"])
    tmpl_settings = entries["Metadata/model_settings.config"][0].decode("utf-8")
    plate_block = plate_template_block(tmpl_settings)
    bed = bed_rect(cfg)
    n_filaments = len(cfg.get("filament_settings_id") or cfg.get("filament_colour") or [1])

    parts = []
    for raw in job.get("parts") or []:
        name = str(raw.get("name") or "").strip()
        if not name:
            raise JobError("every part needs a name")
        try:
            tris = read_stl(raw["stl"])
        except (KeyError, ArtifactError) as exc:
            raise JobError(f"part '{name}': {exc}")
        verts, faces = indexed(tris)
        lo = [min(v[i] for v in verts) for i in range(3)]
        hi = [max(v[i] for v in verts) for i in range(3)]
        centre = [(lo[i] + hi[i]) / 2 for i in range(3)]
        filament = int(raw.get("filament", 1))
        if not 1 <= filament <= n_filaments:
            raise JobError(f"part '{name}': filament {filament} not in the template's 1..{n_filaments}")
        plate = int(raw.get("plate", 1))
        if plate < 1:
            raise JobError(f"part '{name}': plate numbers start at 1")
        # Bambu stores meshes centred on their bounding box; the build item places them.
        centred = [(v[0] - centre[0], v[1] - centre[1], v[2] - centre[2]) for v in verts]
        rot, footprint, offset, fits = placement(centred, bed[2] - bed[0], bed[3] - bed[1])
        parts.append({
            "name": name, "plate": plate, "filament": filament,
            "settings": check_settings(raw.get("settings"), cfg),
            "reasons": raw.get("reasons") or {},
            "verts": centred, "faces": faces, "size": [hi[i] - lo[i] for i in range(3)],
            "rotation_deg": rot, "footprint": footprint, "offset": offset, "fits": fits,
        })
    if not parts:
        raise JobError("job has no parts")
    warnings = template_warnings(entries, cfg, model_xml)
    for p in parts:
        if p["rotation_deg"]:
            warnings.append(f"part '{p['name']}' only fits the bed rotated {p['rotation_deg']} deg; "
                            "placed with that rotation (the STL itself is unchanged)")

    n_plates = max(p["plate"] for p in parts)
    cols = math.ceil(math.sqrt(n_plates) - 1e-9)
    stride_x = (bed[2] - bed[0]) * (1 + PLATE_GAP)
    stride_y = (bed[3] - bed[1]) * (1 + PLATE_GAP)
    pos = layout(parts, bed)

    files = {}
    resources, items, rels = [], [], []
    obj_entries, plate_instances = [], {k: [] for k in range(1, n_plates + 1)}
    next_id = 1
    for i, p in enumerate(parts):
        backup_id = i + 1
        sub_id, object_id = next_id, next_id + 1          # Bambu numbering: mesh object, then wrapper
        next_id += 2
        path = f"3D/Objects/object_{backup_id}.model"
        files[path] = object_model_xml(sub_id, backup_id, p["verts"], p["faces"]).encode("utf-8")
        rels.append(f'<Relationship Target="/{path}" Id="rel-{backup_id}" Type="{MODEL_REL_TYPE}"/>')
        resources.append(
            f'  <object id="{object_id}" p:UUID="{backup_id:08x}{OBJECT_UUID_SUFFIX}" type="model">\n'
            f'   <components>\n    <component p:path="/{path}" objectid="{sub_id}" '
            f'p:UUID="{(backup_id << 16):08x}{COMPONENT_UUID_SUFFIX}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
            "   </components>\n  </object>")
        k = p["plate"] - 1
        ox, oy = (k % cols) * stride_x, -(k // cols) * stride_y   # plate origin (PartPlate.cpp)
        cx, cy = pos[i]
        tx, ty, tz = ox + cx - p["offset"][0], oy + cy - p["offset"][1], p["size"][2] / 2
        items.append(f'  <item objectid="{object_id}" p:UUID="{object_id:08x}{BUILD_UUID_SUFFIX}" '
                     f'transform="{rotation_matrix(p["rotation_deg"])} {_f(tx)} {_f(ty)} {_f(tz)}" printable="1"/>')
        meta = [f'    <metadata key="name" value={quoteattr(p["name"])}/>',
                f'    <metadata key="extruder" value="{p["filament"]}"/>']
        meta += [f'    <metadata key="{k2}" value={quoteattr(v)}/>' for k2, v in p["settings"].items()]
        fc = len(p["faces"])
        obj_entries.append(
            f'  <object id="{object_id}">\n' + "\n".join(meta) + "\n"
            f'    <metadata face_count="{fc}"/>\n'
            f'    <part id="{sub_id}" subtype="normal_part">\n'
            f'      <metadata key="name" value={quoteattr(p["name"])}/>\n'
            '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            f'      <mesh_stat face_count="{fc}" edges_fixed="0" degenerate_facets="0" facets_removed="0" '
            'facets_reversed="0" backwards_edges="0"/>\n    </part>\n  </object>')
        plate_instances[p["plate"]].append(
            "    <model_instance>\n"
            f'      <metadata key="object_id" value="{object_id}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{1000 + object_id}"/>\n'
            "    </model_instance>")

    # Main model: the template's header and metadata, then our resources and build. Personal
    # metadata (the template owner's name and Bambu account id) is blanked: files get shared, and
    # Bambu Studio fills these in again when a signed-in user saves. MakerWorld origin markers
    # (model_id, Region, ...) are removed: this is a new design, not a derivative of a download.
    head = model_xml.split("<resources>")[0].rstrip() + "\n"
    for tag in PERSONAL_METADATA:
        head = re.sub(rf'(<metadata name="{tag}">)[^<]*(</metadata>)', r"\1\2", head)
    for tag in ORIGIN_METADATA:
        head = re.sub(rf'[ \t]*<metadata name="{tag}">[^<]*</metadata>[ \t]*\r?\n?', "", head)
    files["3D/3dmodel.model"] = (head + " <resources>\n" + "\n".join(resources) + "\n </resources>\n"
                                 f' <build p:UUID="{BUILD_UUID}">\n' + "\n".join(items) + "\n </build>\n</model>\n"
                                 ).encode("utf-8")
    files["3D/_rels/3dmodel.model.rels"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/'
        'package/2006/relationships">\n ' + "\n ".join(rels) + "\n</Relationships>\n").encode("utf-8")

    plates_xml = []
    for k in range(1, n_plates + 1):
        block = plate_block.replace('key="plater_id" value="1"', f'key="plater_id" value="{k}"')
        block = re.sub(r"(Metadata/(?:plate|plate_no_light|top|pick))_1(\.png)", rf"\g<1>_{k}\2", block)
        plates_xml.append("  <plate>" + block.rstrip() + "\n" + "\n".join(plate_instances[k]) + "\n  </plate>")
        if k > 1:   # thumbnails for extra plates: copy the template's blank images
            for stem in ("plate", "plate_no_light", "top", "pick"):
                src = f"Metadata/{stem}_1.png"
                if src in entries:
                    files[f"Metadata/{stem}_{k}.png"] = entries[src][0]
    files["Metadata/model_settings.config"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "\n".join(obj_entries) + "\n"
        + "\n".join(plates_xml) + "\n  <assemble>\n  </assemble>\n</config>\n").encode("utf-8")
    files["Metadata/filament_sequence.json"] = json.dumps(
        {f"plate_{k}": {"nozzle_sequence": [], "optimal_assignment": [], "sequence": []}
         for k in range(1, n_plates + 1)}, separators=(",", ":")).encode("utf-8")

    files["Metadata/slice_info.config"] = slice_info_header(entries, cfg)

    # From the template, only what a project needs; project_settings.config byte for byte.
    kept = [n for n in entries if n in TEMPLATE_KEEP or n.startswith(TEMPLATE_KEEP_PREFIX) or TEMPLATE_THUMBNAIL.match(n)]
    dropped = [n for n in entries if n not in kept and n not in files]

    out = job["out"]
    if os.path.exists(out):
        raise JobError(f"{out} already exists; refusing to overwrite (choose a new file name)")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    order = [n for n in entries if n in kept or n in files] + [n for n in files if n not in entries]
    with zipfile.ZipFile(out, "w") as z:
        for name in order:
            data = files[name] if name in files else entries[name][0]
            ctype = zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED
            z.writestr(name, data, compress_type=ctype)

    return {
        "out": out, "printer_model": cfg.get("printer_model"), "process_preset": cfg.get("print_settings_id"),
        "template_kind": "saved project" if has_values(cfg) else "preset names (values from installed presets)",
        "plates": n_plates,
        "parts": [{"name": p["name"], "plate": p["plate"], "filament": p["filament"], "settings": p["settings"],
                   "reasons": p["reasons"], "size_mm": [round(s, 2) for s in p["size"]],
                   "rotation_deg": p["rotation_deg"]} for p in parts],
        "dropped_template_entries": dropped,
        "warnings": warnings,
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = {"schema": SCHEMA, "ran": False, "warnings": [], "errors": []}
    try:
        if len(argv) != 1:
            raise JobError("usage: bambu3mf.py job.json")
        with open(argv[0], encoding="utf-8") as f:
            job = json.load(f)
        for key in ("template", "out", "parts"):
            if key not in job:
                raise JobError(f"job is missing '{key}'")
        out.update(build(job))
        out["ran"] = True
    except (JobError, OSError, ValueError) as exc:
        out["errors"].append(str(exc))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
