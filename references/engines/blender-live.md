# Blender engine: a live Blender (an MCP connector to the user's own Blender)

Read this only when Phase 0 found a tool that runs Python in the user's own Blender and it
answered (`references/phase-0-detect.md`). Everything else about the Blender engine, the same
generator script included, is in `references/engines/blender.md`.

## Running the generator there

**Live Blender** (an MCP connector to the user's own Blender; Phase 0 found a tool that runs
Python there and answered `bpy.app.version_string`). This is also the only path to the
user's Blender when your shell is a VM or a cloud container linked to their computer:
`detect` there sees only the shell's machine. Prefer the tool that runs code in a
**background Blender process** when the server has one and it works (the official Blender
Lab server calls it `execute_blender_code_for_cli`; names differ between servers): it cannot
touch the user's open session.
- It opens a `.blend` you name: give it a **new empty file in the working folder**, never the
  user's file (the official tool saves a numbered copy of an open file with unsaved changes
  next to it, which this engine never does). Make one through the GUI tool with
  `bpy.data.libraries.write(folder + "/empty.blend", set())`: a file with no data, written
  without touching the open file or its unsaved state.
- It starts `blender` from `PATH` or `BLENDER_PATH`. The Windows and macOS installers put
  Blender on neither, so the call fails with "Blender executable not found". Then use the GUI
  tool for this run and tell the user once: set a user environment variable `BLENDER_PATH` to
  the Blender executable and restart the app that runs the MCP server, for background runs.

A tool that only runs code in the open GUI session (the official `execute_blender_code`) is
used the same way, with one difference the user hears first: the build adds a scene named
`3dprint-scout` next to theirs (their window stays on their scene). When
`bpy.data.is_dirty` is true and the file has a path or holds more than Blender's startup
scene (Camera, Cube, Light), ask before running anything; an untitled startup scene reports
unsaved changes after trivial actions and holds nothing to lose, so say what will be added
and go. Send `blender_builder.py` and the generator to a folder on the user's machine under a
**new name per version**, check the md5 of both files after the transfer (print
`hashlib.md5(open(p, "rb").read()).hexdigest()` there and compare with yours), then run a
loader that gives the generator its command line, makes sure no stale helper from an
earlier run is used, and hands back the `@@3DPS` line (the official server returns only a
variable named `result`, never printed output; other servers return what is printed):

```python
import contextlib, hashlib, io, json, runpy, sys
folder = r"<folder you sent the files to>"
expected = {"blender_builder.py": "<md5 you computed before sending>", "model_v3.py": "<md5>"}
for name, digest in expected.items():
    with open(folder + "/" + name, "rb") as f:
        if hashlib.md5(f.read()).hexdigest() != digest:
            raise SystemExit("STALE FILE: " + name)         # a changed file was not resent
saved_argv, saved_path = sys.argv, list(sys.path)
sys.modules.pop("blender_builder", None)                    # never a helper left from an earlier run
sys.path.insert(0, folder)
sys.argv = ["blender", "--", "--params", folder + "/params.json", "--out", folder + "/out"]
out = io.StringIO()
try:
    with contextlib.redirect_stdout(out):
        runpy.run_path(folder + "/model_v3.py", run_name="__main__")
finally:
    sys.argv, sys.path[:] = saved_argv, saved_path          # leave the session as found
    sys.modules.pop("blender_builder", None)
lines = [ln for ln in out.getvalue().splitlines() if ln.startswith("@@3DPS ")]
result = json.loads(lines[-1][7:]) if lines else {"output": out.getvalue()[-2000:]}
print(lines[-1] if lines else out.getvalue()[-2000:])
```

The generator writes the STLs and the `.blend` into `--out` only; the `@@3DPS` line comes
back as `result` (sizes, solver, notes, `mode: "live"`). Bring the STLs back to where
`build.py` runs (the host's file tools, a folder the user connected, or the user copies
them), print each file's md5 on the user's side before and check it on yours after, then
record and validate like Fusion's parts:

```bash
python3 "$SKILL_DIR/scripts/build.py" record out/body.stl out/label.stl --engine blender \
  --source model_v3.py "$SKILL_DIR/references/engines/blender_builder.py" \
  --params .3dprint/params.json --printer .3dprint/printers.json
```

Show the result in the user's open Blender **only when they ask**, and then as below
("Live session").


## Live session: keep the user's file safe

- **Never save the user's file in any form** (`wm.save_mainfile`, `wm.save_as_mainfile`, also
  with `copy=True`): the only file this engine writes is the one `bb.save_blend` writes, and it
  refuses the open file's path, any existing path it was not told to rewrite, and any path
  outside `--out` when it comes from the command line. Never `wm.read_homefile`,
  `wm.read_factory_settings`, `wm.open_mainfile`, `wm.quit_blender`, and never delete anything
  you did not create. `new_scene_mm` builds into the `3dprint-scout` scene next to the user's,
  removes only objects it tagged on an earlier run, reuses only collections it made, and never
  switches the user's window; `save_blend` writes only that scene's data and stops if anything
  of the user's sits in it.
- In an open GUI session, say first that a `3dprint-scout` scene will be added, and when
  `bpy.data.is_dirty` is true ask ("your Blender has unsaved changes; save first, or shall I go
  ahead and add the scene?") and stop. Prefer the background tool.
- Before showing a result in their Blender, read `bpy.data.is_dirty` again; prefer appending
  (`bpy.ops.wm.append` of the part's collection from `out/<name>.blend` into a new scene) over
  opening the file.
- Never install Blender add-ons or change preferences without asking.
- A tool call that times out: retry once, then treat Blender as unavailable for this run and
  say why (as for Fusion).
- Make the harmless read (`import bpy; bpy.app.version_string`) again before **each** live run,
  not only in Phase 0: in a long session the add-on's bridge can stop while Blender stays open.
  Keep each call to one step (send files, load, check), so a failure says which step failed.
- Setting up the official Blender Lab server, when the user asks how: Blender 5.1 or newer, the
  MCP add-on installed (Preferences → Get Extensions → Install from Disk, the `.zip`), the MCP
  server bundle (`.mcpb`) installed in the client (Claude Desktop: Settings → Extensions →
  Advanced settings → Install Extension…). The add-on's bridge listens on `localhost:9876` and
  starts only with Preferences → System → Network → **Allow Online Access** on (it refuses
  otherwise: "Online access must be enabled"), from the add-on's preferences or by autostart.
  Its own page warns that it runs generated code in Blender without guards; say so.

## Pitfalls of a live session

| Symptom | Cause | Fix |
|---|---|---|
| `NameError: name 'bpy' is not defined` from the live tool | The server's namespace has nothing imported | Start every snippet with the imports it uses |
| `Blender executable not found at 'blender'` from the background tool | Blender is not on `PATH` and `BLENDER_PATH` is not set | Use the GUI tool for this run; tell the user how to set `BLENDER_PATH` (above) |
| `Online access must be enabled in the system preferences` | The official add-on's bridge needs it to start | The user turns on Preferences → System → Network → Allow Online Access (ask first) |

## Still to confirm

- The binary path on macOS and Linux installs. Confirmed on Windows with Blender 5.2.2 LTS
  (2026-10-20: `detect` found it in Program Files; build, rebuild and render passed; no path of
  the machine in the STLs, manifests, 3MF or `.blend`), and with the `bpy` module 4.5.14 and 5.2.2.
- The background tool of the official server with `BLENDER_PATH` set. Its GUI tool
  (`execute_blender_code`, add-on 1.0.3) ran the loader on 2026-10-20: 0.17 s for the coaster,
  the user's scene and window untouched.
- EEVEE in a headless Linux session (slow here: about 40 s for a small scene; Workbench and
  Cycles take seconds).
