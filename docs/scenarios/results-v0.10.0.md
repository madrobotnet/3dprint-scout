# Conversation scenario results, 0.10.0

0.10.0 changes what finalize counts as evidence (a section of the part as a test print, a print in
another filament, a use that carries a load) and adds `strength_cases.py`. None of the nine
scenarios records a test print or a section piece: their scripted replies skip every offered
print. Those changes are covered by unit tests (a section that verifies a geometric promise, a
piece that differs, a promise checked outside the box, another filament for a fit and for a
load, the 0.2 mm warning, `load` without strength) and by an end-to-end check with a real build,
a second params file for the piece, a proxy and `fit.py`.

The guidance changes that a conversation reaches are the look's lines on load paths and test
pieces and the new `load` flag. bambu-template reaches all three (a part held by friction, a test
print offer, nothing that carries a load), so it was run once with Claude at ec955c3, with the
harness of 0.9.1. The full transcript, with its checklist marked, is in
`runs/claude-0.10.0/bambu-template.md`.

| Scenario | Stops (0.9.1) | Asked | Did | Claimed | finalize | Result |
|---|---|---|---|---|---|---|
| bambu-template | 2 (2) | The pick (references with a structure line each); the look (the cap with the pipe proxy, "nothing carries a load", rings 22.30 / 22.50 / 22.70 or a prototype) | `compensation` holes `model`; bore 22.50 mm (fit + compensation); `on-off` `by_hand`, a prototype; no `load` use (rightly); Bambu project from the template + STL + .blend + bundle | Opens with the prototype and the user's words; slicing and the print not done; another filament may change the fit | `use` verified, `geometry` verified; on-off verified, a prototype | Matches |

No must item fails. The run also shows that `load` is not over-applied: a cap held on by friction
has no use that carries a force, and the agent marked none.
