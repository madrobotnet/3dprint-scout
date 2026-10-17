"""Tests for scripts/bambu_template.py with a synthetic profile folder (no Bambu data)."""
import io
import json
import os
import struct
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
import bambu_template  # noqa: E402
from test_validate import box, write_stl  # noqa: E402

PRINTER = "Test Printer 0.4 nozzle"


def make_profiles(root):
    """A tiny vendor folder shaped like Bambu Studio's, with invented presets."""
    presets = {
        "machine_model_list": {"Test Model": {"type": "machine_model", "name": "Test Model",
                                              "default_bed_type": "Textured PEI Plate"}},
        "machine_list": {
            "fdm_test_common": {"type": "machine", "name": "fdm_test_common", "from": "system",
                                "instantiation": "false", "printable_area": ["0x0", "200x0", "200x180", "0x180 "],
                                "nozzle_diameter": ["0.4"]},
            PRINTER: {"type": "machine", "name": PRINTER, "inherits": "fdm_test_common", "from": "system",
                      "instantiation": "true", "printer_model": "Test Model", "nozzle_diameter": ["0.4", "0.4"],
                      "extruder_type": ["Direct Drive", "Bowden"],
                      "default_print_profile": "0.20mm Standard @Test",
                      "default_filament_profile": ["Test PLA @Test"]},
            "Other Printer": {"type": "machine", "name": "Other Printer", "from": "system",
                              "instantiation": "true", "printer_model": "Test Model",
                              "nozzle_diameter": ["0.4"], "printable_area": ["0x0", "100x0", "100x100"]},
        },
        "process_list": {
            "fdm_process_test_common": {"type": "process", "name": "fdm_process_test_common", "from": "system",
                                        "instantiation": "false", "layer_height": "0.2", "wall_loops": "2"},
            "0.20mm Standard @Test": {"type": "process", "name": "0.20mm Standard @Test",
                                      "inherits": "fdm_process_test_common", "from": "system",
                                      "instantiation": "true", "compatible_printers": [PRINTER]},
        },
        "filament_list": {
            "Test PLA @base": {"type": "filament", "name": "Test PLA @base", "from": "system",
                               "instantiation": "false", "filament_id": "TST01", "filament_type": ["PLA"],
                               "filament_vendor": ["Test Co"], "nozzle_temperature": ["220"],
                               "filament_diameter": ["2.85"]},
            "Test PLA @Test": {"type": "filament", "name": "Test PLA @Test", "inherits": "Test PLA @base",
                               "from": "system", "instantiation": "true", "compatible_printers": [PRINTER],
                               "filament_extruder_variant": ["Direct Drive Standard"]},
            "Test PETG @Other": {"type": "filament", "name": "Test PETG @Other", "inherits": "Test PLA @base",
                                 "from": "system", "instantiation": "true", "compatible_printers": ["Other Printer"]},
        },
    }
    index = {"name": "Test", "version": "01.00.00.00"}
    for lst, items in presets.items():
        sub = {"machine_model_list": "machine", "machine_list": "machine",
               "process_list": "process", "filament_list": "filament"}[lst]
        index[lst] = []
        for name, data in items.items():
            rel = f"{sub}/{name}.json"
            path = os.path.join(root, "BBL", rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            index[lst].append({"name": name, "sub_path": rel})
    with open(os.path.join(root, "BBL.json"), "w", encoding="utf-8") as f:
        json.dump(index, f)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.profiles = os.path.join(self.dir, "profiles")
        make_profiles(self.profiles)
        self.out = os.path.join(self.dir, "t.3mf")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *extra, out=None):
        argv = ["--profiles", self.profiles, "--printer", PRINTER, "--app-version", "02.08.02.61",
                "--out", out or self.out, *extra]
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = bambu_template.main(argv)
        return code, json.loads(buf.getvalue())

    def cfg(self, path=None):
        with zipfile.ZipFile(path or self.out) as z:
            return json.loads(z.read("Metadata/project_settings.config"))


class Content(Base):
    def test_defaults_come_from_the_printer(self):
        code, res = self.run_cli()
        self.assertEqual(code, 0, res["errors"])
        cfg = self.cfg()
        self.assertEqual(cfg["printer_model"], "Test Model")
        self.assertEqual(cfg["printer_settings_id"], PRINTER)
        self.assertEqual(cfg["print_settings_id"], "0.20mm Standard @Test")
        self.assertEqual(cfg["filament_settings_id"], ["Test PLA @Test"])
        self.assertEqual(cfg["filament_ids"], ["TST01"])                 # read through inherits
        self.assertEqual(cfg["curr_bed_type"], "Textured PEI Plate")
        self.assertEqual(cfg["printable_area"], ["0x0", "200x0", "200x180", "0x180"])   # inherited, trimmed
        self.assertEqual(cfg["version"], "02.08.02.61")

    def test_names_only_no_setting_values(self):
        self.run_cli()
        cfg = self.cfg()
        for key in ("layer_height", "wall_loops", "nozzle_temperature"):
            self.assertNotIn(key, cfg)
        self.assertEqual(cfg["different_settings_to_system"], [""] * 3)    # 1 filament + print + printer
        self.assertEqual(cfg["inherits_group"], [""] * 3)
        self.assertFalse(bambu3mf.has_values(cfg))

    def test_vector_sizes_match_filaments_and_extruders(self):
        code, res = self.run_cli("--filament", "Test PLA @Test", "--filament", "Test PLA @Test",
                                 "--colour", "#0acc38")
        self.assertEqual(code, 0, res["errors"])
        cfg = self.cfg()
        n, e = 2, 2
        for key in ("filament_settings_id", "filament_ids", "filament_colour", "filament_extruder_variant",
                    "filament_self_index", "filament_map", "filament_diameter"):
            self.assertEqual(len(cfg[key]), n, key)
        self.assertEqual(cfg["filament_colour"], ["#0ACC38", "#FFFFFF"])
        self.assertEqual(len(cfg["flush_volumes_matrix"]), e * n * n)
        self.assertEqual(cfg["flush_volumes_matrix"][:4], ["0", "280", "280", "0"])
        self.assertEqual(len(cfg["flush_multiplier"]), e)
        self.assertEqual(len(cfg["different_settings_to_system"]), n + 2)

    def test_filament_names_survive_normalize(self):
        # Bambu Studio's Preset::normalize resizes every per-filament vector, filament_settings_id
        # included, to len(filament_diameter) before matching presets (Preset.cpp, 02.08.02.61).
        # Without filament_diameter the default has one element and filaments 2..n open as
        # project presets named after the file. Mirror that resize here.
        names = ["Test PLA @Test", "Test PLA @Test", "Test PLA @Test"]
        code, res = self.run_cli(*[a for n in names for a in ("--filament", n)])
        self.assertEqual(code, 0, res["errors"])
        cfg = self.cfg()
        n = len(cfg.get("filament_diameter", ["1.75"]))
        kept = (cfg["filament_settings_id"] + [""] * n)[:n]
        self.assertEqual(kept, names)

    def test_filament_diameter_is_read_through_inherits(self):
        self.run_cli()
        self.assertEqual(self.cfg()["filament_diameter"], ["2.85"])     # from "Test PLA @base"

    def test_package_parts(self):
        self.run_cli()
        with zipfile.ZipFile(self.out) as z:
            names = set(z.namelist())
            for n in ("[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model", "Metadata/model_settings.config",
                      "Metadata/slice_info.config", "Metadata/plate_1.png", "Metadata/plate_1_small.png"):
                self.assertIn(n, names)
            model = z.read("3D/3dmodel.model").decode()
            ET.fromstring(model)
            self.assertIn("BambuStudio-02.08.02.61", model)
            self.assertIn('<metadata name="DesignerUserId"></metadata>', model)
            png = z.read("Metadata/plate_1.png")
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", png[16:24]), (512, 512))
            self.assertIn("filament_map_mode", z.read("Metadata/model_settings.config").decode())  # 2 extruders


class Refusals(Base):
    def test_refusals(self):
        cases = [
            (["--app-version", "2.8"], "app-version"),
            (["--printer", "No Such Printer"], "not in this Bambu Studio"),
            (["--printer", "fdm_test_common"], "not a selectable printer"),
            (["--filament", "Test PETG @Other"], "not compatible"),
            (["--filament", "Test PLA @base"], "not a selectable filament"),
            (["--colour", "green"], "#RRGGBB"),
        ]
        for i, (extra, msg) in enumerate(cases):
            argv = ["--profiles", self.profiles, "--printer", PRINTER, "--app-version", "02.08.02.61",
                    "--out", os.path.join(self.dir, f"r{i}.3mf")]
            for flag_i in range(0, len(extra), 2):     # later flags override earlier ones
                if extra[flag_i] in argv and extra[flag_i] not in ("--filament", "--colour"):
                    j = argv.index(extra[flag_i]); argv[j + 1] = extra[flag_i + 1]
                else:
                    argv += extra[flag_i:flag_i + 2]
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = bambu_template.main(argv)
            res = json.loads(buf.getvalue())
            self.assertEqual(code, 1, extra)
            self.assertIn(msg, " ".join(res["errors"]), extra)
            self.assertFalse(os.path.exists(os.path.join(self.dir, f"r{i}.3mf")))

    def test_refuses_to_overwrite_and_missing_index(self):
        self.run_cli()
        code, res = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("refusing to overwrite", res["errors"][0])
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = bambu_template.main(["--profiles", self.dir, "--printer", PRINTER, "--app-version",
                                        "02.08.02.61", "--out", os.path.join(self.dir, "x.3mf")])
        self.assertEqual(code, 1)
        self.assertIn("no BBL.json", json.loads(buf.getvalue())["errors"][0])


class WithBambu3mf(Base):
    def test_project_from_generated_template(self):
        self.run_cli("--filament", "Test PLA @Test", "--filament", "Test PLA @Test")
        stl = os.path.join(self.dir, "a.stl")
        write_stl(stl, box(20, 10, 5))
        out = os.path.join(self.dir, "p.3mf")
        res = bambu3mf.build({"template": self.out, "out": out, "parts": [
            {"name": "a", "stl": stl, "plate": 1, "filament": 2, "settings": {"wall_loops": 4}},
            {"name": "b", "stl": stl, "plate": 2}]})
        self.assertEqual(res["plates"], 2)
        self.assertIn("preset names", res["template_kind"])
        with zipfile.ZipFile(out) as z:
            ms = z.read("Metadata/model_settings.config").decode()
            self.assertIn('<metadata key="wall_loops" value="4"/>', ms)
            self.assertIn('<metadata key="extruder" value="2"/>', ms)
            self.assertIn("Metadata/plate_2.png", z.namelist())
            self.assertEqual(json.loads(z.read("Metadata/project_settings.config"))["print_settings_id"],
                             "0.20mm Standard @Test")
        # The allowlist still applies to names-only templates.
        with self.assertRaises(bambu3mf.JobError):
            bambu3mf.build({"template": self.out, "out": os.path.join(self.dir, "q.3mf"),
                            "parts": [{"name": "a", "stl": stl, "settings": {"post_process": "x"}}]})


if __name__ == "__main__":
    unittest.main()
