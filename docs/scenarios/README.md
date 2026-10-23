# Conversation scenarios for 0.7.0

A kit for running the nine conversation checks of `references/development.md` ("Conversation
checks when editing the skill") with any agent, the same way every time, and recording what
happened so that runs of different agents (for 0.7.0, Claude and Codex) can be compared. It
does not run anything by itself: a person plays the user, from a script.

| File | What it holds |
|---|---|
| `<id>.md`, one per scenario | The row's expected behaviour (a copy), the starting state, the opening message, the scripted replies, the grading checklist |
| `setup.py` | Makes the project folder a scenario starts in, with the skill's own scripts |
| `fixtures/` | The sources `setup.py` copies into place (`wall-holder/` is shared by four scenarios) |
| `results-v0.7.0.md` | One row per scenario per agent, filled after each run |
| `runs/<agent>/<id>.md` | The full transcript of each run (written by whoever runs it) |

The scenarios, in the order of development.md's table:

| Id | Row | Starts from |
|---|---|---|
| [`given-answers`](given-answers.md) | Request already gives printer, slicer, dimensions and choice C | An empty folder |
| [`choice-d`](choice-d.md) | User chooses D, an existing model | An empty folder |
| [`holes-unknown`](holes-unknown.md) | Hole compensation settings unknown | An empty folder |
| [`bambu-template`](bambu-template.md) | Bambu printer, project from a generated template | The printer saved, with a generated template |
| [`change-request`](change-request.md) | User requests a change to the working project | A delivered wall phone holder |
| [`unattended`](unattended.md) | User explicitly requests unattended execution | An empty folder |
| [`a-kept-broken`](a-kept-broken.md) | A: one promise kept, one broken | The holder, its plug fit failing |
| [`a2-unmeasured`](a2-unmeasured.md) | A2: a `use` promise rests on a size nobody measured | The holder, its plug size assumed |
| [`c-param-changed`](c-param-changed.md) | C: a parameter a member reads changes | The holder, every promise verified |

`docs/` is not part of the release ZIP: nothing here reaches the skill's users.

## The wall holder project

Four scenarios (`change-request`, `a-kept-broken`, `a2-unmeasured`, `c-param-changed`) start
from one project in different states: a phone charging holder taped to the wall. A back plate,
and two prongs the phone stands on, each with a lip at its front; the charging cable's plug
passes down through the gap between the prongs. Each scenario file says how its state differs.

- `holder.py` (`fixtures/wall-holder/`): the Python generator, every size in `DEFAULTS`. Back
  plate 49 × 4 × 70 mm; prongs 18 mm wide, 15 mm long, 6.0 mm thick (`base_t`), 13.0 mm apart
  (`notch_w`); lips 3 mm deep, 7 mm above the prong top. Modelled in the print orientation, which
  is also the use orientation.
- `plug.py`: the proxy of the plug head, a box from its own params file `.3dprint/usb_c_plug.json`.
- `.3dprint/params.json` (`fixtures/<id>/params.json`): every parameter, `_material` `pla_basic`,
  `_print.preset` `0.20mm Standard @BBL X1C`, `_parts.holder.expect` `[49.0, 19.0, 70.0]`,
  `_assumptions`, and `_verify` with three `use` promises (their texts in Korean, the user's
  language):
  - `seat`: the lip holds the phone, 11.0 mm thick in its case (dims `phone-case`, measured by
    the user); evidence: the measurement `lip height`, the lip top at least 11.5 mm above the bed.
  - `cable-out`: the straight USB-C plug passes between the prongs with 0.2 mm or more on each
    side (dims `usb-c-plug`); evidence: the proxy joint `plug through notch`.
  - `holds`: one prong takes a hard finger push at a safety factor of 2; evidence: the member
    `prong`.
- `.3dprint/printers.json` (`fixtures/wall-holder/printers.json`): a Bambu Lab X1 Carbon with
  Bambu Studio, the generated template `.3dprint/templates/x1c.3mf` (made as in
  `bambu-template.md`), `compensation` `model` for holes and `slicer` for elephant foot.

`setup.py` builds it and makes the evidence from inside the folder, as the skill would have:

```bash
python3 "$SKILL_DIR/scripts/build.py" run holder.py --params .3dprint/params.json \
  --printer .3dprint/printers.json --out out > out/build.json
python3 "$SKILL_DIR/scripts/build.py" run plug.py --params .3dprint/usb_c_plug.json --proxy plug \
  --out out/plug > out/plug/build.json
python3 "$SKILL_DIR/scripts/fit.py" out/holder.stl out/plug/plug.stl --b-translate X,Y,Z \
  --min-clearance 0.2 > out/fit_plug.json
python3 "$SKILL_DIR/scripts/measure.py" slice out/holder.stl --axis y --z 17.5 \
  --expect "levels[0].loops[0].size[1]>=11.5" --what "lip top above the bed (base_t + phone_t / 2 = 11.5)" \
  > out/m_lip.json
python3 "$SKILL_DIR/scripts/strength.py" beam --from-build out/build.json --part holder \
  --param h=base_t --param b=prong_w --param length=base_d --param support=base_support \
  --param orientation=base_orient --load finger_push > out/strength_prong.json
```

`X,Y,Z` places the plug as it sits under the phone: centred between the prongs
(`(2 prong_w + notch_w − plug_w) / 2`), centred on the phone's thickness in the seat
(`back_t + phone_t / 2 − plug_h / 2`), its top at the prong top (`base_t − plug_l`). The run
starts a new conversation, so the agent has no record of these commands beyond what the reports
hold (the fit's placement, the measurement's command, the member's `inputs_from`): finding the
links again is part of the run.

## Before a run

1. **The skill at a known commit.** Check out the commit to test in a skill checkout and note it
   (`git rev-parse --short HEAD`). Install that checkout the way the agent loads skills (the
   repository's `README.md`, "Install"): for a fixed commit, put the checkout, or a link to it,
   where the agent reads skills from. Every agent in a comparison runs the same commit. The kit's own files are read
   from the same checkout.
2. **The Python environment.** The skill's Python modeling environment
   (`references/development.md`, section 2: manifold3d, numpy, rtree, matplotlib), active in the
   shell you start the agent from, so that its `python3` finds them and Phase 0 has nothing to
   install. `setup.py` must run with the same environment: a rebuild of an unchanged part then
   gives the same STL as the starting state's.
3. **Web search on.** Phase 1 looks for existing models on the web. A run without web search is
   tier C (the agent asks for links): note it in the run file; `choice-d` cannot run that way.
4. **A new project folder**, outside the skill checkout, and its starting state. Run `setup.py`
   for every scenario, also those that start empty (it then only makes the empty folder), and
   keep its output outside the folder, where the agent will not see it:

   ```bash
   python3 "$SKILL_DIR/docs/scenarios/setup.py" a2-unmeasured ~/scenario-runs/codex/a2-unmeasured \
     > ~/scenario-runs/codex/a2-unmeasured.setup.json
   ```

   `setup.py` refuses a folder that exists and is not empty. For a scenario with a starting
   state it builds the project with the skill's scripts, runs `finalize.py` on it and stops
   with an error unless the states are the ones the scenario file lists. Its JSON holds the skill
   commit, those states and the sha256 of every file it wrote (the grader uses them to see which
   files a run left alone). `setup.py --list` lists the scenarios; `setup.py --check-docs` checks
   that each scenario file still quotes development.md as it is.

## Running one scenario

1. Start a **new conversation** with the agent, its working folder the project folder
   (`cd ~/scenario-runs/codex/a2-unmeasured`, then start the agent). The agent knows the project
   only from the folder: no earlier conversation, no memory of other runs. Allow it to run
   commands in that folder and to read the skill.
2. Send the scenario's **opening message**, word for word, copied from its file.
3. Answer each message of the agent from the scenario's **scripted replies**, word for word:
   - Find the row that matches what the agent asks or shows (the rows are keyed by the stop:
     printer and slicer, the reference choice A–D, the concept pick, the base-shape look, the
     Phase 4 decisions, the delivery, and the questions the scenario expects).
   - Several questions in one message: one reply each, in the order the agent asked them, joined
     with a space into one message.
   - A question no row covers: the **fallback reply**, word for word, once per message:

     ```text
     잘 모르겠어요. 알아서 정해 주세요.
     ```

     Mark it "(fallback)" in the transcript. The fallback is not the user's agreement to exclude
     a promise or to accept a warning, and it does not start the unattended mode: an agent that
     records it as either has made a mistake to grade.
   - A message that asks nothing and shows nothing to look at (a progress note that ended the
     turn): `계속해 주세요.`
   - A scenario's own table overrides these rules where it says so (`unattended` has no fallback).
   - Never add anything: no hints, no corrections, no mention of the kit or of grading. If the
     agent's question seems to need another answer, still give the scripted one and write what
     you noticed in the run file.
   - Approval prompts of the host tool (run this command? write this file?) are not part of the
     conversation: approve what acts inside the project folder or reads the skill, deny what
     writes elsewhere, and note each denial.
4. **The run ends** at the agent's delivery message (files written and reported), at its
   handoff in `choice-d`, after 15 replies, or when the agent says it cannot go on. Do not send
   a closing message. Stop the agent if it is still working after the last reply.

## Recording a run

Save the transcript as `docs/scenarios/runs/<agent>/<id>.md` (`runs/codex/a2-unmeasured.md`):

```markdown
# a2-unmeasured, Codex

- Agent and model: <host tool and version>, <the model id it reports>
- Skill commit: <git rev-parse --short HEAD in the skill checkout>
- Kit: the scenario file at <the same commit, or another>
- Date, OS, Python: 2026-10-24, macOS 15, Python 3.11 (manifold3d 3.x)
- Web search: on | off; denied approvals: none
- setup.py output: <path, or "empty folder">

## Conversation
**User:** <opening message>
**Agent:** <its message, as shown; tool calls summarised as `command` lines in order>
**User:** <reply> (row: "measure the plug")
...

## finalize after the run
<the two commands below and their output>

## Checklist
<the scenario's checklist, each item marked yes / no / n/a with a word on what showed it>
```

Keep the agent's messages whole: the language check and the claims are graded on them.

## Grading

Grade as development.md's "Recording a run" says, in the run's project folder, with
`$SKILL_DIR` the skill checkout and `--deliver` on the delivery folder the run made:

```bash
DELIVERY=deliver/2026-10-24   # the delivery folder the run wrote
python3 "$SKILL_DIR/scripts/finalize.py" --build out/build.json --params .3dprint/params.json \
  --printer .3dprint/printers.json --deliver "$DELIVERY" > final.json
python3 -c "import json; r = json.load(open('final.json')); print(r['use'], r['geometry']); print('\n'.join(p['id'] + ': ' + p['state'] for p in r.get('promises') or []))"
```

Write `final.json` outside the project folder if you want to keep the folder as the agent left
it. A run that made no delivery folder (it stopped before delivering) is graded on finalize
without `--deliver`; `choice-d` builds nothing and has no finalize.

Then go through the scenario's checklist. Items marked **must** are the row's expected
behaviour, or the skill rules the row rests on: one that fails makes the result "differs". Items
marked **should** are other rules of the skill the run touches: report a miss under Result, but
it does not fail the scenario on its own. Two rules hold in every scenario:

- **must** Every message the user sees is in Korean, the user's language: the questions, the
  progress notes between tool calls and the delivery (file names, commands and numbers aside).
- **must** The last message claims no more than finalize says: nothing called verified (or
  "checked", "confirmed", "all good") that finalize reports assumed, not verified, excluded or
  failed, and no single verdict for all promises. A run whose own finalize never had `--deliver`
  and still called a promise verified fails, as development.md says.

## Sending the result back

Fill one row of `results-v0.7.0.md` per run (the columns are development.md's), add the
transcript under `runs/<agent>/`, and commit both on a branch (or send the two files). In the
row, "Prompt" names the scenario file and the commit it was taken from; "Asked", "Did" and
"Claimed" are short, in order (the transcript has the rest); "finalize" is the output of the
command above; "Result" is "matches" or what differs, with the checklist items that failed.
