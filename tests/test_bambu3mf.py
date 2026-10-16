"""Tests for scripts/bambu3mf.py with a synthetic Bambu-style template (no user data)."""
import io
import json
import os
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import bambu3mf  # noqa: E402
from test_validate import box, write_stl  # noqa: E402

NS = {"m": bambu3mf.CORE_NS, "p": bambu3mf.PROD_NS}
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def make_template(path, extra_entries=None, model_extra="", **cfg_over):
    cfg = {"printer_model": "Test Printer", "print_settings_id": "Test Process",
           "printable_area": ["0x0", "256x0", "256x256", "0x256"], "printable_height": "250",
           "filament_settings_id": ["PLA A", "PLA B", "PLA C", "PLA D"],
           "wall_loops": "2", "sparse_infill_density": "15%", "layer_height": "0.2", "brim_type": "auto_brim",
           "brim_width": "5", "enable_support": "0", "outer_wall_speed": ["200", "200"]}
    cfg.update(cfg_over)
    settings = json.dumps(cfg, indent=4).replace("\n", "\r\n").encode()      # CRLF like Bambu Studio
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             f'xmlns="{bambu3mf.CORE_NS}" xmlns:BambuStudio="{bambu3mf.BBS_NS}" xmlns:p="{bambu3mf.PROD_NS}" '
             'requiredextensions="p">\n <metadata name="Application">BambuStudio-02.08.02.61</metadata>\n'
             ' <metadata name="Designer">Some Person</metadata>\n <metadata name="DesignerUserId">123456789</metadata>\n'
             + model_extra +
             ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n </resources>\n <build/>\n</model>\n')
    ms = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <plate>\n'
          '    <metadata key="plater_id" value="1"/>\n    <metadata key="plater_name" value=""/>\n'
          '    <metadata key="locked" value="false"/>\n    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
          '    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>\n'
          '    <metadata key="thumbnail_no_light_file" value="Metadata/plate_no_light_1.png"/>\n'
          '    <metadata key="top_file" value="Metadata/top_1.png"/>\n'
          '    <metadata key="pick_file" value="Metadata/pick_1.png"/>\n  </plate>\n  <assemble>\n  </assemble>\n</config>\n')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        for stem in ("plate", "plate_no_light", "top", "pick"):
            z.writestr(f"Metadata/{stem}_1.png", PNG, compress_type=zipfile.ZIP_STORED)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/project_settings.config", settings)
        z.writestr("Metadata/model_settings.config", ms)
        z.writestr("Metadata/filament_sequence.json", '{"plate_1":{}}')
        z.writestr("_rels/.rels", "<Relationships/>")
        for name, data in (extra_entries or {}).items():
            z.writestr(name, data)
    return settings


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.template = os.path.join(self.d, "template.3mf")
        self.settings_bytes = make_template(self.template)
        self.box = os.path.join(self.d, "box.stl"); write_stl(self.box, box(60, 40, 30, 5, 5, 0))
        self.lid = os.path.join(self.d, "lid.stl"); write_stl(self.lid, box(60, 40, 10))
        self.out = os.path.join(self.d, "out.3mf")

    def tearDown(self):
        self.tmp.cleanup()

    def job(self, parts, **extra):
        return {"template": self.template, "out": self.out, "parts": parts, **extra}

    def read(self):
        # Closed before returning: Windows cannot delete or replace a zip that is still open.
        with zipfile.ZipFile(self.out) as z:
            return {n: z.read(n) for n in z.namelist()}


class Structure(Base):
    def test_two_parts_one_plate(self):
        res = bambu3mf.build(self.job([{"name": "box", "stl": self.box, "filament": 2},
                                       {"name": "lid", "stl": self.lid}]))
        self.assertEqual(res["plates"], 1)
        files = self.read()
        self.assertEqual(files["Metadata/project_settings.config"], self.settings_bytes)   # byte-for-byte
        main = ET.fromstring(files["3D/3dmodel.model"])
        self.assertIn("BambuStudio", files["3D/3dmodel.model"].decode())
        wrappers = main.findall("m:resources/m:object", NS)
        self.assertEqual(len(wrappers), 2)
        for w in wrappers:                                      # every component resolves to a mesh object
            comp = w.find("m:components/m:component", NS)
            path = comp.get(f"{{{bambu3mf.PROD_NS}}}path").lstrip("/")
            sub = ET.fromstring(files[path]).find("m:resources/m:object", NS)
            self.assertEqual(sub.get("id"), comp.get("objectid"))
            self.assertTrue(w.get(f"{{{bambu3mf.PROD_NS}}}UUID").endswith(bambu3mf.OBJECT_UUID_SUFFIX))
        ids = {w.get("id") for w in wrappers}
        items = main.findall("m:build/m:item", NS)
        self.assertEqual({i.get("objectid") for i in items}, ids)
        rels = files["3D/_rels/3dmodel.model.rels"].decode()
        self.assertEqual(len(re.findall(r"/3D/Objects/object_\d+\.model", rels)), 2)
        ms = ET.fromstring(files["Metadata/model_settings.config"])
        objs = {o.get("id"): {m.get("key"): m.get("value") for m in o.findall("metadata") if m.get("key")}
                for o in ms.findall("object")}
        self.assertEqual({v["name"] for v in objs.values()}, {"box", "lid"})
        self.assertEqual([v["extruder"] for v in objs.values() if v["name"] == "box"], ["2"])
        inst = [m.get("value") for m in ms.findall("plate/model_instance/metadata") if m.get("key") == "object_id"]
        self.assertEqual(set(inst), ids)

    def test_parts_sit_on_their_plates_without_overlap(self):
        parts = [{"name": "a", "stl": self.box, "plate": 1}, {"name": "b", "stl": self.lid, "plate": 1},
                 {"name": "c", "stl": self.lid, "plate": 2}, {"name": "d", "stl": self.lid, "plate": 3}]
        bambu3mf.build(self.job(parts))
        files = self.read()
        main = ET.fromstring(files["3D/3dmodel.model"])
        t = {i.get("objectid"): [float(v) for v in i.get("transform").split()[-3:]]
             for i in main.findall("m:build/m:item", NS)}
        ms = ET.fromstring(files["Metadata/model_settings.config"])
        stride = 256 * 1.2
        for plate in ms.findall("plate"):
            k = int([m.get("value") for m in plate.findall("metadata") if m.get("key") == "plater_id"][0])
            ox, oy = ((k - 1) % 2) * stride, -((k - 1) // 2) * stride      # 3 plates -> 2 columns
            for mi in plate.findall("model_instance"):
                oid = [m.get("value") for m in mi.findall("metadata") if m.get("key") == "object_id"][0]
                x, y, _ = t[oid]
                self.assertTrue(ox <= x <= ox + 256 and oy <= y <= oy + 256, (k, x, y))
        a, b = t["2"], t["4"]                                    # same plate: 60-wide parts 10 mm apart
        self.assertAlmostEqual(abs(a[0] - b[0]), 70, places=3)
        for k in (2, 3):
            self.assertIn(f"Metadata/plate_{k}.png", files)
        self.assertEqual(set(json.loads(files["Metadata/filament_sequence.json"])), {"plate_1", "plate_2", "plate_3"})

    def test_mesh_is_centred_and_keeps_volume(self):
        bambu3mf.build(self.job([{"name": "box", "stl": self.box}]))
        files = self.read()
        sub = ET.fromstring(files["3D/Objects/object_1.model"]).find("m:resources/m:object/m:mesh", NS)
        vs = [(float(v.get("x")), float(v.get("y")), float(v.get("z"))) for v in sub.iter(f"{{{bambu3mf.CORE_NS}}}vertex")]
        for i in range(3):
            self.assertAlmostEqual((min(v[i] for v in vs) + max(v[i] for v in vs)) / 2, 0, places=4)
        vol = 0.0
        for tri in sub.iter(f"{{{bambu3mf.CORE_NS}}}triangle"):
            p, q, r = (vs[int(tri.get(k))] for k in ("v1", "v2", "v3"))
            vol += (p[0] * (q[1] * r[2] - q[2] * r[1]) - p[1] * (q[0] * r[2] - q[2] * r[0])
                    + p[2] * (q[0] * r[1] - q[1] * r[0])) / 6
        self.assertAlmostEqual(vol, 60 * 40 * 30, delta=0.5)
        item = ET.fromstring(files["3D/3dmodel.model"]).find("m:build/m:item", NS)
        self.assertAlmostEqual(float(item.get("transform").split()[-1]), 15)   # lifted by half its height


class Settings(Base):
    def test_overrides_are_normalised_and_written(self):
        res = bambu3mf.build(self.job([{"name": "box", "stl": self.box,
                                        "settings": {"wall_loops": 4, "sparse_infill_density": 25,
                                                     "enable_support": True, "brim_type": "outer_only"}}]))
        self.assertEqual(res["parts"][0]["settings"],
                         {"wall_loops": "4", "sparse_infill_density": "25%", "enable_support": "1", "brim_type": "outer_only"})
        files = self.read()
        text = files["Metadata/model_settings.config"].decode()
        self.assertIn('<metadata key="wall_loops" value="4"/>', text)
        self.assertIn('<metadata key="sparse_infill_density" value="25%"/>', text)

    def test_refusals(self):
        cases = {
            "post_process": "/tmp/x.sh",           # runs programs
            "machine_start_gcode": "G28",          # rewrites G-code
            "outer_wall_speed": "100",             # not on the allowlist
            "sparse_infill_pattern": "monotonic",  # a top_surface_pattern value, not a sparse one
            "wall_loops": 0,                       # out of range
            "brim_type": "huge",                   # not an enum value
            "layer_height": "abc",                 # not a number
        }
        for key, value in cases.items():
            with self.assertRaises(bambu3mf.JobError, msg=key):
                bambu3mf.build(self.job([{"name": "box", "stl": self.box, "settings": {key: value}}]))

    def test_per_extruder_key_refused(self):
        make_template(self.template, brim_width=["5", "5"])
        with self.assertRaisesRegex(bambu3mf.JobError, "one value per extruder"):
            bambu3mf.build(self.job([{"name": "box", "stl": self.box, "settings": {"brim_width": 3}}]))

    def test_key_unknown_to_template_version(self):
        with self.assertRaisesRegex(bambu3mf.JobError, "unknown to the template"):
            bambu3mf.build(self.job([{"name": "box", "stl": self.box, "settings": {"ironing_type": "top"}}]))


class Privacy(Base):
    def test_owner_metadata_is_blanked(self):
        bambu3mf.build(self.job([{"name": "box", "stl": self.box}]))
        files = self.read()
        main = files["3D/3dmodel.model"].decode()
        self.assertNotIn("123456789", main)
        self.assertNotIn("Some Person", main)
        self.assertIn('<metadata name="DesignerUserId"></metadata>', main)
        self.assertIn("BambuStudio-02.08.02.61", main)                  # application tag kept

    def test_makerworld_origin_and_profile_owner_are_removed(self):
        make_template(self.template, model_extra=(
            ' <metadata name="model_id">987654</metadata>\n <metadata name="Region">KR</metadata>\n'
            ' <metadata name="DesignId">42</metadata>\n <metadata name="ProfileUserId">555</metadata>\n'
            ' <metadata name="ProfileUserName">someone</metadata>\n <metadata name="Title">keep me</metadata>\n'))
        bambu3mf.build(self.job([{"name": "box", "stl": self.box}]))
        files = self.read()
        main = files["3D/3dmodel.model"].decode()
        for gone in ("model_id", "Region", "DesignId", "987654", "555", "someone"):
            self.assertNotIn(gone, main)
        self.assertIn('<metadata name="ProfileUserId"></metadata>', main)
        self.assertIn('<metadata name="Title">keep me</metadata>', main)
        ET.fromstring(main)                                              # still well-formed

    def test_only_needed_template_entries_are_copied(self):
        """A template saved after slicing carries G-code, plate JSON and auxiliaries: none of
        that belongs in a new project, and slice_info keeps only its header."""
        extra = {"Metadata/plate_1.gcode": "G28\n", "Metadata/plate_1.gcode.md5": "x", "Metadata/plate_1.json": "{}",
                 "Metadata/process_settings_My HQ.config": "{}",      # the user's own preset: kept
                 "Metadata/Auxiliaries/Model Pictures/photo.jpg": "\xff\xd8", "Metadata/cut_information.xml": "<c/>",
                 "Metadata/custom_gcode_per_layer.xml": "<g/>", "Metadata/plate_2.png": "png",
                 "Metadata/slice_info.config": ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <header>\n'
                                                '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
                                                '    <header_item key="X-BBL-Client-Version" value="02.08.02.61"/>\n'
                                                '  </header>\n  <plate>\n    <metadata key="index" value="1"/>\n'
                                                '    <object identify_id="1" name="their old part" skipped="false"/>\n'
                                                '  </plate>\n</config>\n')}
        make_template(self.template, extra_entries=extra)
        res = bambu3mf.build(self.job([{"name": "box", "stl": self.box}]))
        files = self.read()
        kept = {"Metadata/slice_info.config", "Metadata/process_settings_My HQ.config"}
        for name in extra:
            self.assertEqual(name in files, name in kept, name)
        self.assertEqual(sorted(res["dropped_template_entries"]), sorted(n for n in extra if n not in kept))
        info = files["Metadata/slice_info.config"].decode()
        self.assertIn('value="02.08.02.61"', info)
        self.assertNotIn("their old part", info)
        self.assertNotIn("<plate>", info)
        self.assertEqual(files["Metadata/project_settings.config"], self.settings_bytes)
        self.assertTrue({"[Content_Types].xml", "_rels/.rels", "Metadata/plate_1.png", "3D/3dmodel.model",
                         "3D/_rels/3dmodel.model.rels", "3D/Objects/object_1.model", "Metadata/model_settings.config",
                         "Metadata/filament_sequence.json"} <= set(files))

    def test_post_process_in_preset_is_a_warning_not_a_refusal(self):
        settings = make_template(self.template, post_process=["/home/me/fix.py"])
        res = bambu3mf.build(self.job([{"name": "box", "stl": self.box}]))
        self.assertTrue(any("post-processing" in w for w in res["warnings"]))
        files = self.read()
        self.assertEqual(files["Metadata/project_settings.config"], settings)   # preset untouched, script and all
        make_template(self.template, post_process=[""])
        os.remove(self.out)
        self.assertEqual(bambu3mf.build(self.job([{"name": "box", "stl": self.box}]))["warnings"], [])

    def test_non_empty_template_is_a_warning(self):
        make_template(self.template)
        with zipfile.ZipFile(self.template) as z:
            entries = {n: z.read(n) for n in z.namelist()}
        entries["3D/3dmodel.model"] = entries["3D/3dmodel.model"].replace(
            b"<build/>", b'<build><item objectid="2" transform="1 0 0 0 1 0 0 0 1 0 0 0"/></build>')
        with zipfile.ZipFile(self.template, "w") as z:
            for n, d in entries.items():
                z.writestr(n, d)
        res = bambu3mf.build(self.job([{"name": "box", "stl": self.box}]))
        self.assertTrue(any("not an empty project" in w for w in res["warnings"]))
        files = self.read()
        self.assertEqual(files["3D/3dmodel.model"].decode().count("<item "), 1)         # only our part


class Safety(Base):
    def test_refuses_to_overwrite(self):
        open(self.out, "w").close()
        with self.assertRaisesRegex(bambu3mf.JobError, "refusing to overwrite"):
            bambu3mf.build(self.job([{"name": "box", "stl": self.box}]))
        with self.assertRaisesRegex(bambu3mf.JobError, "refusing to overwrite"):   # no secret override
            bambu3mf.build(self.job([{"name": "box", "stl": self.box}], overwrite=True))

    def test_rejects_non_bambu_template(self):
        with zipfile.ZipFile(self.template, "w") as z:
            z.writestr("3D/3dmodel.model", "<model/>")
        with self.assertRaisesRegex(bambu3mf.JobError, "not a Bambu Studio project"):
            bambu3mf.build(self.job([{"name": "box", "stl": self.box}]))

    def test_part_too_big_and_bad_filament(self):
        big = os.path.join(self.d, "big.stl"); write_stl(big, box(400, 20, 10))
        with self.assertRaisesRegex(bambu3mf.JobError, "does not fit .* at any rotation"):
            bambu3mf.build(self.job([{"name": "big", "stl": big}]))
        with self.assertRaisesRegex(bambu3mf.JobError, "filament 9"):
            bambu3mf.build(self.job([{"name": "box", "stl": self.box, "filament": 9}]))

    def test_part_that_fits_rotated_is_placed_rotated(self):
        """Same decision as validate.py's D2: a 300 mm bar fits a 256 mm bed diagonally."""
        bar = os.path.join(self.d, "bar.stl"); write_stl(bar, box(300, 20, 10) + box(20, 60, 10, 0, 20, 0))
        res = bambu3mf.build(self.job([{"name": "bar", "stl": bar}, {"name": "lid", "stl": self.lid, "plate": 2}]))
        self.assertGreater(res["parts"][0]["rotation_deg"], 0)
        self.assertEqual(res["parts"][1]["rotation_deg"], 0)
        self.assertTrue(any("rotated" in w for w in res["warnings"]))
        files = self.read()
        main = ET.fromstring(files["3D/3dmodel.model"])
        for item in main.findall("m:build/m:item", NS):
            m = [float(v) for v in item.get("transform").split()]
            path = f"3D/Objects/object_{int(item.get('objectid')) // 2}.model"
            sub = ET.fromstring(files[path]).find("m:resources/m:object/m:mesh", NS)
            vs = [(float(v.get("x")), float(v.get("y")), float(v.get("z"))) for v in sub.iter(f"{{{bambu3mf.CORE_NS}}}vertex")]
            placed = [(x * m[0] + y * m[3] + z * m[6] + m[9], x * m[1] + y * m[4] + z * m[7] + m[10],
                       x * m[2] + y * m[5] + z * m[8] + m[11]) for x, y, z in vs]
            ox = 0 if item.get("objectid") == "2" else 256 * 1.2                 # plate 2 sits to the right
            self.assertGreaterEqual(min(p[0] for p in placed), ox - 1e-3)
            self.assertLessEqual(max(p[0] for p in placed), ox + 256 + 1e-3)
            self.assertGreaterEqual(min(p[1] for p in placed), -1e-3)
            self.assertLessEqual(max(p[1] for p in placed), 256 + 1e-3)
            self.assertAlmostEqual(min(p[2] for p in placed), 0, places=3)
        self.assertEqual(ET.fromstring(files["3D/3dmodel.model"]).find("m:build/m:item", NS)
                         .get("transform").split()[:9] != ["1", "0", "0", "0", "1", "0", "0", "0", "1"], True)

    def test_cli_prints_json(self):
        job = os.path.join(self.d, "job.json")
        with open(job, "w") as f:
            json.dump(self.job([{"name": "box", "stl": self.box}]), f)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = bambu3mf.main([job])
        out = json.loads(buf.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(out["ran"])
        self.assertEqual(out["printer_model"], "Test Printer")


if __name__ == "__main__":
    unittest.main()
