#!/usr/bin/env python3
"""
setup.py - the starting state of a conversation scenario (docs/scenarios/README.md).

  python3 docs/scenarios/setup.py ID FOLDER [--skill-dir DIR] > ID.setup.json
  python3 docs/scenarios/setup.py --list
  python3 docs/scenarios/setup.py --check-docs

Makes FOLDER (new, or an existing empty folder) the project folder the scenario starts in. For a
scenario with a starting state it copies the sources from docs/scenarios/fixtures/ into place and
runs the skill's own scripts on them, from inside FOLDER and with relative paths, as the skill
would have in an earlier session: a Bambu Studio template from bambu_template.py, the build
(build.py run, saved as out/build.json), the plug proxy (build.py run --proxy), the fit (fit.py),
the lip measurement (measure.py --expect), the member (strength.py --from-build) and, where the
scenario starts after a delivery, the delivered Bambu project (bambu3mf.py), the part's STL and the
source bundle (finalize.py --deliver --bundle). Then it runs finalize.py on the result and stops
with an error unless every state is the one the scenario file promises. A scenario without a
starting state gets an empty folder.

It prints one JSON document: the scenario, the skill commit, finalize's states and the sha256 of
every file it wrote. Save it outside FOLDER (the agent must not see it); the grader uses the
hashes to show which files a run left untouched.

--skill-dir is the skill checkout whose scripts make the state (default: the checkout this file
is in). Use the same checkout, commit and Python environment the agent will run the skill with:
a rebuild of an unchanged part then gives the same STL. --check-docs compares the expected
behaviour quoted in each scenario file with the table in conversation-checks.md, beside this file
(docs/ is not shipped with the skill, so an agent under test does not read it there), and checks
that every attended scenario file carries the same agreement item.

Python 3.9 or newer; the starting states need the skill's Python modeling environment
(manifold3d, numpy; references/development.md), never bpy. Exit 0 on success, 1 on an error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
CHECKS = os.path.join(HERE, "conversation-checks.md")   # the scenario table the files quote
DEFAULT_SKILL = os.path.dirname(os.path.dirname(HERE))

# The nine rows of conversation-checks.md (this folder), "Conversation checks when editing the skill", in order.
SCENARIOS = ("given-answers", "choice-d", "holes-unknown", "bambu-template", "change-request",
             "unattended", "a-kept-broken", "a2-unmeasured", "c-param-changed")
HOLDER = ("a-kept-broken", "a2-unmeasured", "c-param-changed", "change-request")
ATTENDED = tuple(sid for sid in SCENARIOS if sid != "unattended")
# The checklist item every attended scenario file carries word for word (--check-docs compares them).
AGREEMENT = "The user's agreement (the same item in every attended scenario):\n"
DELIVERED = "deliver/2026-10-20"           # change-request starts after this delivery

# What finalize.py says about each starting state (the scenario files repeat it): the use and
# geometry tiers and each promise's state; change-request with --deliver on its delivery.
EXPECT = {
    "a-kept-broken": ("failed", "not verified", {"seat": "verified", "cable-out": "failed", "holds": "verified"}),
    "a2-unmeasured": ("assumed", "verified", {"seat": "verified", "cable-out": "assumed", "holds": "verified"}),
    "c-param-changed": ("verified", "verified", {"seat": "verified", "cable-out": "verified", "holds": "verified"}),
    "change-request": ("verified", "verified", {"seat": "verified", "cable-out": "verified", "holds": "verified"}),
}

# A synthetic Bambu profile folder for bambu_template.py, standing in for the user's installed
# Bambu Studio: real preset names and the X1 Carbon's bed, no setting values (bambu_template.py
# reads names and a few printer facts only). It lives in a temporary folder, never in the project.
X1C = "Bambu Lab X1 Carbon 0.4 nozzle"
PROCESS = "0.20mm Standard @BBL X1C"
FILAMENT = "Bambu PLA Basic @BBL X1C"
APP_VERSION = "02.08.02.61"
PROFILES = {
    "machine_model_list": {"Bambu Lab X1 Carbon": {
        "type": "machine_model", "name": "Bambu Lab X1 Carbon", "default_bed_type": "Textured PEI Plate"}},
    "machine_list": {X1C: {
        "type": "machine", "name": X1C, "from": "system", "instantiation": "true",
        "printer_model": "Bambu Lab X1 Carbon", "nozzle_diameter": ["0.4"],
        "printable_area": ["0x0", "256x0", "256x256", "0x256"], "printable_height": "250",
        "default_print_profile": PROCESS, "default_filament_profile": [FILAMENT]}},
    "process_list": {PROCESS: {
        "type": "process", "name": PROCESS, "from": "system", "instantiation": "true",
        "compatible_printers": [X1C]}},
    "filament_list": {FILAMENT: {
        "type": "filament", "name": FILAMENT, "from": "system", "instantiation": "true",
        "filament_id": "GFA00", "filament_type": ["PLA"], "filament_vendor": ["Bambu Lab"],
        "filament_diameter": ["1.75"], "compatible_printers": [X1C]}},
}


class SetupError(Exception):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


class Project:
    """FOLDER as the agent will find it; every script runs inside it with relative paths."""

    def __init__(self, folder, skill):
        self.folder = folder
        self.skill = skill

    def path(self, rel):
        return os.path.join(self.folder, *rel.split("/"))

    def copy(self, src, rel):
        os.makedirs(os.path.dirname(self.path(rel)), exist_ok=True)
        shutil.copyfile(src, self.path(rel))

    def script(self, name, *argv, save=None, ok=(0,)):
        """Run scripts/<name> with this Python from inside the folder; save its stdout (a JSON
        document) at the relative path `save`, as the skill's commands do with `>`."""
        cmd = [sys.executable, os.path.join(self.skill, "scripts", name)] + list(argv)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run(cmd, cwd=self.folder, capture_output=True, encoding="utf-8", env=env)
        if r.returncode not in ok:
            raise SetupError("%s %s exited %d:\n%s\n%s" % (name, " ".join(argv), r.returncode,
                                                           r.stdout[-2000:], r.stderr[-2000:]))
        if save:
            os.makedirs(os.path.dirname(self.path(save)), exist_ok=True)
            with open(self.path(save), "w", encoding="utf-8") as f:
                f.write(r.stdout)
        try:
            return json.loads(r.stdout)
        except ValueError:
            raise SetupError("%s printed no JSON:\n%s\n%s" % (name, r.stdout[-2000:], r.stderr[-2000:]))

    def template(self):
        """.3dprint/templates/x1c.3mf, generated by bambu_template.py from the synthetic profiles."""
        tmp = tempfile.mkdtemp(prefix="3dps-profiles-")
        try:
            index = {"name": "BBL", "version": APP_VERSION}
            for lst, items in PROFILES.items():
                sub = "machine" if lst.startswith("machine") else lst.split("_")[0]
                index[lst] = []
                for name, data in items.items():
                    rel = "%s/%s.json" % (sub, name)
                    os.makedirs(os.path.join(tmp, "BBL", sub), exist_ok=True)
                    write_json(os.path.join(tmp, "BBL", sub, name + ".json"), data)
                    index[lst].append({"name": name, "sub_path": rel})
            write_json(os.path.join(tmp, "BBL.json"), index)
            os.makedirs(self.path(".3dprint/templates"), exist_ok=True)
            out = self.script("bambu_template.py", "--profiles", tmp, "--printer", X1C,
                              "--app-version", APP_VERSION, "--out", ".3dprint/templates/x1c.3mf")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if not out.get("ran"):
            raise SetupError("bambu_template.py: %s" % out.get("errors"))


def start_holder(p, sid):
    """The wall-mounted phone holder of a-kept-broken, a2-unmeasured, c-param-changed and
    change-request: built, its evidence made and saved, declared in params.json's _verify."""
    shared = os.path.join(FIXTURES, "wall-holder")
    own = os.path.join(FIXTURES, sid)
    p.copy(os.path.join(shared, "holder.py"), "holder.py")
    p.copy(os.path.join(shared, "plug.py"), "plug.py")
    p.copy(os.path.join(shared, "printers.json"), ".3dprint/printers.json")
    p.copy(os.path.join(own, "params.json"), ".3dprint/params.json")
    p.copy(os.path.join(own, "usb_c_plug.json"), ".3dprint/usb_c_plug.json")
    p.template()

    os.makedirs(p.path("out/plug"))
    built = p.script("build.py", "run", "holder.py", "--params", ".3dprint/params.json",
                     "--printer", ".3dprint/printers.json", "--out", "out", save="out/build.json")
    if built.get("gate") != "PASS" or built.get("errors") or built.get("warnings"):
        raise SetupError("the holder build is not clean: gate %s, %s, %s"
                         % (built.get("gate"), built.get("errors"), built.get("warnings")))
    p.script("build.py", "run", "plug.py", "--params", ".3dprint/usb_c_plug.json", "--proxy", "plug",
             "--out", "out/plug", save="out/plug/build.json")

    # The plug as it sits under the phone: centred between the prongs, centred on the phone's
    # thickness in the seat, its top at the prong top. A hand calculation from the build's values.
    v = built["parameters"]["values"]
    with open(p.path(".3dprint/usb_c_plug.json"), encoding="utf-8") as f:
        plug = json.load(f)
    at = (((2 * v["prong_w"] + v["notch_w"]) - plug["plug_w"]) / 2,
          v["back_t"] + v["phone_t"] / 2 - plug["plug_h"] / 2,
          v["base_t"] - plug["plug_l"])
    p.script("fit.py", "out/holder.stl", "out/plug/plug.stl", "--b-translate",
             ",".join("%g" % round(c, 3) for c in at), "--min-clearance", "0.2",
             save="out/fit_plug.json", ok=(0, 1))

    # The lip top must stand half the phone above the prong top: a cut across the lips.
    lip_y = v["back_t"] + v["base_d"] - v["lip_t"] / 2
    target = v["base_t"] + v["phone_t"] / 2
    p.script("measure.py", "slice", "out/holder.stl", "--axis", "y", "--z", "%g" % lip_y,
             "--expect", "levels[0].loops[0].size[1]>=%g" % target,
             "--what", "lip top above the bed (base_t + phone_t / 2 = %g)" % target, save="out/m_lip.json")

    p.script("strength.py", "beam", "--from-build", "out/build.json", "--part", "holder",
             "--param", "h=base_t", "--param", "b=prong_w", "--param", "length=base_d",
             "--param", "support=base_support", "--param", "orientation=base_orient",
             "--load", "finger_push", save="out/strength_prong.json")

    if sid == "change-request":
        os.makedirs(p.path(DELIVERED))
        write_json(p.path("out/bambu_job.json"), {
            "template": ".3dprint/templates/x1c.3mf", "out": DELIVERED + "/holder_bambu.3mf",
            "printer": ".3dprint/printers.json", "params": ".3dprint/params.json",
            "parts": [{"name": "holder", "stl": "out/holder.stl", "plate": 1, "filament": 1}]})
        p.script("bambu3mf.py", "out/bambu_job.json")
        p.copy(p.path("out/holder.stl"), DELIVERED + "/holder.stl")
        out = p.script("finalize.py", "--build", "out/build.json", "--params", ".3dprint/params.json",
                       "--printer", ".3dprint/printers.json", "--deliver", DELIVERED,
                       "--bundle", DELIVERED + "/source")
        if out.get("errors"):
            raise SetupError("finalize --bundle: %s" % out["errors"])


def start_bambu_template(p, sid):
    """A project folder with only the printer saved: an X1 Carbon, Bambu Studio and the
    generated template, and no compensation entry yet."""
    p.copy(os.path.join(FIXTURES, sid, "printers.json"), ".3dprint/printers.json")
    p.template()


STARTS = {"bambu-template": start_bambu_template}
STARTS.update({sid: start_holder for sid in HOLDER})


def check_start(p, sid):
    """finalize.py on the starting state; an error unless it says what the scenario file says."""
    if sid not in EXPECT:
        return None
    argv = ["--build", "out/build.json", "--params", ".3dprint/params.json", "--printer", ".3dprint/printers.json"]
    if sid == "change-request":
        argv += ["--deliver", DELIVERED]
    out = p.script("finalize.py", *argv)
    got = (out.get("use"), out.get("geometry"), {q["id"]: q["state"] for q in out.get("promises") or []})
    if got != EXPECT[sid]:
        raise SetupError("finalize does not give the starting state %s promises:\n  expected %s\n  got      %s\n%s"
                         % (sid, EXPECT[sid], got, "\n".join(out.get("open") or [])))
    return {"argv": ["finalize.py"] + argv, "use": got[0], "geometry": got[1], "promises": got[2],
            "reasons": {q["id"]: q["reasons"] for q in out["promises"] if q["reasons"]}}


def skill_commit(skill):
    try:
        r = subprocess.run(["git", "-C", skill, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
        dirty = subprocess.run(["git", "-C", skill, "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True)
    except OSError:
        return None
    if r.returncode:
        return None
    return r.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")


def setup(sid, folder, skill):
    if sid not in SCENARIOS:
        raise SetupError("unknown scenario %r; one of: %s" % (sid, ", ".join(SCENARIOS)))
    for need in ("SKILL.md", os.path.join("scripts", "finalize.py")):
        if not os.path.isfile(os.path.join(skill, need)):
            raise SetupError("%s is not a skill checkout (no %s): pass --skill-dir" % (skill, need))
    folder = os.path.abspath(folder)
    if os.path.exists(folder) and (not os.path.isdir(folder) or os.listdir(folder)):
        raise SetupError("%s exists and is not an empty folder: give a new one" % folder)
    if os.path.commonpath([folder, os.path.abspath(skill)]) == os.path.abspath(skill):
        raise SetupError("%s is inside the skill checkout: keep project folders outside it" % folder)
    os.makedirs(folder, exist_ok=True)
    p = Project(folder, os.path.abspath(skill))
    start = STARTS.get(sid)
    if start:
        start(p, sid)
    checked = check_start(p, sid)
    files = {}
    for root, dirs, names in os.walk(folder):
        dirs.sort()
        for name in sorted(names):
            full = os.path.join(root, name)
            files[os.path.relpath(full, folder).replace(os.sep, "/")] = sha256(full)
    return {"schema": "3dprint-scout.scenario-setup/1", "scenario": sid, "starting_state": bool(start),
            "skill_commit": skill_commit(skill), "python": sys.version.split()[0],
            "finalize": checked, "files": files}


def scenario_rows():
    """The scenario table of conversation-checks.md: [(scenario, expected behavior)]. It is the
    file's first table, before "## Recording a run"."""
    with open(CHECKS, encoding="utf-8") as f:
        text = f.read()
    section = text.split("# Conversation checks when editing the skill", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 2 and cells[0] not in ("Scenario", "---"):
            rows.append((cells[0], cells[1]))
    return rows


def agreement_item(text):
    """The text of the shared agreement item in a scenario file, or None."""
    if AGREEMENT not in text:
        return None
    rest = text.split(AGREEMENT, 1)[1]
    return rest.split("\n\n", 1)[0].strip()


def check_docs():
    """Each scenario file quotes its row of conversation-checks.md word for word, and every attended
    scenario file carries the same agreement item; a drift is named."""
    rows = scenario_rows()
    problems = []
    if len(rows) != len(SCENARIOS):
        problems.append("conversation-checks.md has %d scenario rows, the kit %d" % (len(rows), len(SCENARIOS)))
    agreement = {}
    for sid in ATTENDED:
        with open(os.path.join(HERE, sid + ".md"), encoding="utf-8") as f:
            agreement[sid] = agreement_item(f.read())
        if agreement[sid] is None:
            problems.append("%s.md has no agreement item" % sid)
        elif agreement[sid] != agreement[ATTENDED[0]]:
            problems.append("%s.md words the agreement item differently from %s.md" % (sid, ATTENDED[0]))
    for sid, (scenario, expected) in zip(SCENARIOS, rows):
        with open(os.path.join(HERE, sid + ".md"), encoding="utf-8") as f:
            text = f.read()
        quoted = {}
        for key in ("Scenario", "Expected behavior"):
            m = re.search(r"^> \*\*%s:\*\* (.*)$" % key, text, re.M)
            quoted[key] = m.group(1).strip() if m else None
        if quoted["Scenario"] != scenario:
            problems.append("%s.md quotes the scenario as %r; conversation-checks.md: %r"
                            % (sid, quoted["Scenario"], scenario))
        if quoted["Expected behavior"] != expected:
            problems.append("%s.md quotes the expected behaviour differently from conversation-checks.md" % sid)
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="the starting state of a conversation scenario")
    ap.add_argument("scenario", nargs="?", help="scenario id (--list)")
    ap.add_argument("folder", nargs="?", help="the new project folder")
    ap.add_argument("--skill-dir", default=DEFAULT_SKILL, help="the skill checkout (default: this repository)")
    ap.add_argument("--list", action="store_true", help="list the scenarios and which have a starting state")
    ap.add_argument("--check-docs", action="store_true", help="compare the quoted rows with conversation-checks.md")
    args = ap.parse_args(argv)
    try:
        if args.list:
            for sid in SCENARIOS:
                print("%-16s %s" % (sid, "starting state" if sid in STARTS else "empty folder"))
            return 0
        if args.check_docs:
            problems = check_docs()
            print("\n".join(problems) if problems else
                  "the nine scenario files quote conversation-checks.md as it is; the agreement item is the same in all eight attended ones")
            return 1 if problems else 0
        if not (args.scenario and args.folder):
            ap.error("give a scenario id and a new folder (or --list, --check-docs)")
        print(json.dumps(setup(args.scenario, args.folder, args.skill_dir), ensure_ascii=False, indent=2))
        return 0
    except SetupError as exc:
        print("setup.py: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
