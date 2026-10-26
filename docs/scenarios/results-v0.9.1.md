# Conversation scenario results, 0.9.1

The three design scenarios of `conversation-checks.md` run with Claude from the same prompts as
before (`README.md` in this folder): given-answers, holes-unknown and bambu-template. 0.9.1's
guidance changes reach these three: the pick looks at how references are built, sources that
disagree are settled in an order, and the look lists the load paths. The other six do not reach
those steps (they start from a built project, or end at the pick with D), and the code changes
they do reach are covered by the golden comparison below. The full transcript of each run, with
its checklist marked, is in `runs/claude-0.9.1/<id>.md`; a row only summarises it.

All three ran at cec0f3d (the 0.9.1 guidance and kit), in one pass. The Blender export changed
after the runs (6fd950f: Blender's own triangulation kept unless it leaves a bad triangle); that
changes no message. Correction (0.10.0): it does change STL bytes for these runs' parts. They
were built at cec0f3d, whose export re-triangulated every face, and four of their six part STLs
rebuild to other bytes with the released 0.9.1. An earlier version of this page said no byte
changed; that was not checked for these runs. Their transcripts and grading stand.

The harness was the one 0.9.0 used, with one line added to each brief: the agent knows nothing
about the user beyond their messages and the project folder. In 0.9.0 two run agents had taken
the owner's name and printer from the host's context.

| Scenario | Stops (0.9.0) | Asked | Did | Claimed | finalize | Result |
|---|---|---|---|---|---|---|
| given-answers | 2 (2) | The pick (3 concepts with solid-weight bounds, references under them); the look (the holder with the remotes in place, its sizes, "no part carries a load" and a tipping figure, a try-out print or a prototype) | `printers.json` from the message; both remotes caliper/user; Blender holder; proxy fits; `hold-big`, `hold-small` `by_hand`, prototypes on the look's reply; STL + core 3MF + .blend + bundle | Opens with the prototype and the user's words; each promise with what showed it and what the fit did not cover; the weight as an upper bound | `use` verified, `geometry` verified; hold-big, hold-small verified, prototypes | Matches |
| holes-unknown | 2 (2) | The pick (rod length with a default, an optional re-measure); the look (rings 12.2 / 12.4 / 12.6, or a prototype; the post's root carries about 1/1000 of PLA's strength) | Holes and elephant foot `unknown`; socket 12.4 mm, no compensation; `rod-in-out` `by_hand`, a prototype; rod length `assumed` after the fallback; Blender stand | Opens with the prototype; tight or loose because the hole settings are unknown; tipping assumed on the 30 cm rod | `use` assumed, `geometry` verified; rod-in-out verified, a prototype; no-tip assumed | Matches |
| bambu-template | 2 (2) | The pick (references with a structure line each); the look (what changed from the concept and why, the tongues' strain against PLA's limit, three test rings or a prototype) | `compensation` holes `model`, elephant foot `slicer`; nub circle 21.85 mm (interference + compensation); `on-off` `by_hand`, a prototype; Bambu project from the template + STLs + .blend + bundle | Opens with the prototype; the fit rests on the measured 22.0; slicing and the print not checked | `use` verified, `geometry` verified; on-off verified, a prototype | Matches |

No must item that held in 0.9.0 fails in the rows above, and the new should item (the look's load
paths) holds in all three.

## What changed in the conversations

- **Load paths in the look.** Each look named where force goes, or that none does: given-answers
  said the remotes' weight goes through the floor and gave a tipping figure with the option of a
  deeper base; holes-unknown showed the stand tips before the post is loaded; bambu-template gave
  the tongues' strain, the pull-off force and PLA's creep. No run resized anything for strength
  after the look's reply.
- **Weights from a number.** Every pick and look gave the weight as an upper bound from the build
  ("속을 꽉 채워도 최대 약 63 g"), with the slicer named for the real figure.
- **Reference structure.** The harness gives the run agents no browser, so none could look at a
  reference's photos; each said so and read the structure from the page text. bambu-template wrote
  a structure line per reference. The question about a model the user already uses did not come
  up: none of the three parts fits something the user owns that a reference also fits.

## Golden comparison with v0.9.0

The golden harness (finalize on every earlier scenario project, as found and with each delivery
and a bundle; the scenario start states; every example built) was run at v0.9.0 and at 6fd950f:

- With 0.9.0's Blender builder put back (to see everything else), 45 of 189 outputs differ, all
  expected: the new `bundle_delivered` and `bundle_withheld` fields, the example builds'
  `volume_cm3`, the change-request start state's bundle no longer copying the delivered files, and
  REPRODUCE.md naming the manifest in the delivery folder, where 0.9.0 had taken one from inside an
  earlier bundle. No finalize verdict changed.
- With the 0.9.1 builder, the Blender projects also read their build as stale (the helper module is
  a hashed source): expected, and said in CHANGELOG.md.
- Every Blender project of the earlier scenario runs (0.7.0 to 0.9.0, 22) was rebuilt with 0.9.1: 21 wrote
  byte-identical STLs and finalize gave the same tiers and promise states as 0.9.0 on the original.

## Found, not changed in 0.9.1

- **A generator whose rebuilds differ.** The 0.8.2 re-run of given-answers (`holder.py`:
  `from_manifold`, a boolean, `bed_chamfer`) writes different STL bytes on every rebuild, under
  0.9.0 as under 0.9.1, so its evidence goes stale on any rebuild. The other 21 Blender projects
  rebuild byte-identically.
- **English caller blocks** again in bambu-template (harness, as in 0.7.0 and 0.9.0).
