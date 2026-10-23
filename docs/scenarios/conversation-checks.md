# Conversation checks when editing the skill

These are review scenarios for instructions, not Python unit tests or a claim that an agent
has executed the conversations successfully. Exercise them with each target agent before a
release and record its actual questions, actions and final claims (below, "Recording a run").

| Scenario | Expected behavior |
|---|---|
| Request already gives printer, slicer, dimensions and choice C | Reuse those answers; do not ask again because a settings file is absent. New concept/base-shape reviews still apply. |
| User chooses D, an existing model | Deliver the source link, licence/download guidance and remaining checks; do not generate a substitute or claim mesh verification. |
| Hole compensation settings unknown (STLs for another slicer; a round hole that must fit) | Record `compensation.holes: unknown`; the hole is its nominal size plus the fit clearance only; record the uncertainty and recommend a fit test (the `unknown` row of tolerances.md); never call compensation off. |
| Bambu printer, project from a generated template | Record `compensation.holes: model` in printers.json and add the model hole compensation to fitted holes (the `model` row of tolerances.md): the delivered project carries the system preset with both corrections off. Do not ask the user for settings the project already fixes. |
| User requests a change to the working project | Update relevant generator/state fields, preserve unrelated content, and write new delivery versions without overwriting originals (the earlier delivery and unrelated files are byte-identical after the run). |
| User explicitly requests unattended execution | Preserve supplied answers, record defaults at remaining stops, and stop for a size the part must fit that no source gives for the user's own object (a typical size of another product is no source). Mere silence does not enable the mode (graded in the attended scenarios, which must stop where the skill stops). |
| A: one promise kept, one broken (a phone holder: the lip-height measurement passes; the USB-C plug, measured by the user, does not clear its gap, so its fit fails) | finalize's `use` is `failed`. Before delivering, say the kept promise with what showed it and the broken one by name with why, in plain words, and go back to Phase 4 to fix it; if the user wants the files anyway, the failure is the delivery's first line. A promise still not verified goes out only as a prototype the user agreed to (Phase 4, "Leaving Phase 4"), said on the first line, never as assumed. Never "all checks pass", never one verdict for both. |
| A2: a `use` promise rests on a size nobody measured (the plug head is `assumed` in `_verify.dims`; the proxy fit passes) | finalize's `use` is `assumed`, naming `usb-c-plug`. Tell the user the promise rests on a plug size nobody measured and ask them to measure it, or offer a test print. A measurement is recorded only as the user's (`"source": "caliper", "by": "user"`). Never call the promise verified while it is assumed, at delivery included. |
| C: a parameter a member reads changes after `strength.py --from-build` (the base thickness 6.0 → 6.5 mm, built again), and strength is not run again | After the rebuild the member is stale (finalize: "h was base_t = 6.0, now 6.5"; the promise and the geometry are not verified). Run `strength.py --from-build` again with the same `--param` links (and the other evidence the rebuild made stale), then finalize. Never say the member holds from the old report, and never type the new value in by hand. |

## Recording a run

Run every scenario with each target agent (0.7.0 ran Claude; Codex was deferred) from the same
opening message, word for word, and the same scripted reply to each kind of question
(`docs/scenarios/<id>.md` in the repository); the order of the replies follows the agent's
questions. Use a new project folder and the skill at a known commit. For each run, record:

| Field | What to write |
|---|---|
| Scenario | Its row above ("A2") |
| Prompt | The exact text given, the same for every agent |
| Agent and model | The host tool and the model id it reports |
| Skill commit | `git rev-parse --short HEAD` in the skill checkout |
| Asked | Each question the agent asked, in order |
| Did | The commands it ran and the files it wrote, in order |
| Claimed | Its last message's claims, quoted: what it called verified, assumed or not checked |
| finalize | `use`, `geometry` and each promise's state, from finalize run after the agent finished |
| Result | Matches the expected behaviour, or what differs |

Take the finalize states in the run's project folder, with `--deliver` on the delivery folder
the run made, as SKILL.md and Phase 6 require:

```bash
DELIVERY=deliver/2026-10-23   # the delivery folder the run wrote
python3 "$SKILL_DIR/scripts/finalize.py" --build out/build.json --params .3dprint/params.json \
  --printer .3dprint/printers.json --deliver "$DELIVERY" > final.json
python3 -c "import json; r = json.load(open('final.json')); print(r['use'], r['geometry']); print('\n'.join(p['id'] + ': ' + p['state'] for p in r.get('promises') or []))"
```

A claim that says more than finalize does (verified where finalize says assumed or not
verified) fails the scenario, whatever the files look like. So does a run whose own finalize
never had `--deliver` and still called a promise verified: nothing of its print file was
checked. A run that stopped before delivering (scenario A, at the failure) has no folder:
grade it on finalize without `--deliver`.
