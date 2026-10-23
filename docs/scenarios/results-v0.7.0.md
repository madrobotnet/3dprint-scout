# Conversation scenario results, 0.7.0

The nine scenarios of `references/development.md` ("Conversation checks when editing the
skill"), each run with Claude and with Codex from the same prompts, as `README.md` in this folder
describes. One row per run; the columns are development.md's "Recording a run". The full
transcript of each run, with its checklist marked, is in `runs/<agent>/<id>.md`
(`runs/claude/a2-unmeasured.md`, `runs/codex/a2-unmeasured.md`); a row only summarises it.

- **Prompt**: the scenario file and the commit it was taken from (`a2-unmeasured.md @ abc1234`):
  its opening message and scripted replies are the exact text given.
- **Asked**, **Did**: in order, short; "(fallback)" marks a fallback reply.
- **Claimed**: the last message's claims, quoted: what it called verified, assumed or not checked.
- **finalize**: `use`, `geometry` and each promise's state, from finalize run after the agent
  finished (with `--deliver` on its delivery folder).
- **Result**: "matches", or what differs, with the checklist items that failed.

| Scenario | Prompt | Agent and model | Skill commit | Asked | Did | Claimed | finalize | Result |
|---|---|---|---|---|---|---|---|---|
| given-answers | | Claude | | | | | | |
| given-answers | | Codex | | | | | | |
| choice-d | | Claude | | | | | | |
| choice-d | | Codex | | | | | | |
| holes-unknown | | Claude | | | | | | |
| holes-unknown | | Codex | | | | | | |
| bambu-template | | Claude | | | | | | |
| bambu-template | | Codex | | | | | | |
| change-request | | Claude | | | | | | |
| change-request | | Codex | | | | | | |
| unattended | | Claude | | | | | | |
| unattended | | Codex | | | | | | |
| A (a-kept-broken) | | Claude | | | | | | |
| A (a-kept-broken) | | Codex | | | | | | |
| A2 (a2-unmeasured) | | Claude | | | | | | |
| A2 (a2-unmeasured) | | Codex | | | | | | |
| C (c-param-changed) | | Claude | | | | | | |
| C (c-param-changed) | | Codex | | | | | | |
