# LEGO use cases — brainstorm

Same multi-agent shape as Ouroboros (scout → deep-dive specialists →
writer), pointed at LEGO problems instead of B2B leads.

## Idea 1 — "Bricks in a pile → buildable plan"

**Input:** a photo (or list) of a scattered, freeform pile of bricks the
user already owns. Mixed colors, mixed sets, no instructions, no theme.

**Output:** 2–3 concrete "you can build this *right now* from what's on
the table" plans, each with stepwise assembly, a preview rendering, and
a difficulty/time estimate.

**Why it's interesting:** the friction in casual LEGO play isn't lack
of bricks — it's the cognitive cost of staring at chaos and inventing
something buildable from it. The agent eats the chaos and hands back a
small, concrete plan. Same emotional shape as Ouroboros: "messy world →
ranked, actionable next step."

### Multi-agent decomposition

| Specialist             | What it does                                                                 |
|------------------------|------------------------------------------------------------------------------|
| `inventory_scanner`    | Photo → brick list. Per-piece: shape ID (e.g. `3001` = 2×4 brick), color, count. |
| `constraint_extractor` | Inventory → feasibility envelope. "No tiles" → no smooth roofs. "Only 4 wheels" → max 1 vehicle. |
| `concept_proposer`     | Inventory + constraints → 3–5 candidate builds ranked by buildability + fun. |
| `step_planner`         | One chosen concept → ordered assembly steps using only available bricks.     |
| `substitute_finder`    | Flags bricks the plan asked for but you don't have; suggests substitutes.    |
| `validator`            | Simulates the build (stud-by-stud) to catch impossible connections / instability. |
| `visual_writer`        | Renders the final build + per-step preview (LDraw / Mecabricks / image gen). |

### Why this fits the Ouroboros engine

- "Scout" pattern → `inventory_scanner` (raw input → structured candidates).
- "Deep-dive sweeps" → `constraint_extractor`, `concept_proposer`,
  `step_planner` per chosen concept.
- "Writer" pattern → `visual_writer` produces the user-facing artifact.
- Per-candidate enrichment bundles map cleanly: each candidate build
  has its own `{steps, missing_pieces, render, difficulty}` dict.

## Idea 2 — "Real-world photo → LEGO replica → BrickLink order"

**Input:** a photo of a real-world object — coffee mug, bicycle, the
user's house, their dog, a Eiffel Tower postcard.

**Output:**
1. A LEGO-ified 3D model of that thing, buildable at a chosen scale.
2. A complete bill of materials (brick IDs, colors, counts).
3. Stepwise assembly instructions.
4. A pre-filled BrickLink Wanted List for any pieces the user doesn't
   already own — one click to "order missing parts."

**Why it's interesting:** the friction here is the gap between "I want
to LEGO-ify *that* thing" and "what bricks do I actually need." Existing
tools cover slices of the pipeline (Mecabricks, BrickLink Studio,
LegoMosaic, Brixel) but no one has stitched them end-to-end into a
"photo in, parcel at your door" loop.

### Multi-agent decomposition

| Specialist             | What it does                                                                 |
|------------------------|------------------------------------------------------------------------------|
| `subject_segmenter`    | Photo → cleaned subject mask + estimated dimensions / depth.                 |
| `scale_chooser`        | User intent ("display piece", "minifig-scale", "mosaic") + subject → target voxel resolution. |
| `lego_modeler`         | 3D shape → voxelized brick layout. Picks brick granularity vs fidelity.      |
| `parts_extractor`      | Voxel model → `{brick_id, color, count}` bill of materials.                  |
| `inventory_diff`       | Parts list − user's existing inventory → missing parts list.                 |
| `bricklink_orderer`    | Missing parts → BrickLink Wanted List XML + checkout link.                   |
| `step_planner`         | Voxel model + parts → ordered assembly steps (bottom-up, support-first).     |
| `visual_writer`        | Renders the final model + per-step previews.                                 |

### Three flavors of "LEGO-ify"

The single hardest design decision. The `scale_chooser` picks one:

- **2D mosaic** (easiest). Photo → pixel art → tiled flat plate. Tools
  exist (LegoMosaic, brickit). Works for portraits, logos, pets.
- **Microscale sculpture** (medium). 3D voxelization at ~1cm³ per brick.
  Recognizable but stylized. Best for buildings, vehicles, animals.
- **Minifig-scale** (hardest). Real proportional model with hinges,
  Technic, decorative tiles. Mostly creative work, hard to automate.

Recommend shipping the 2D mosaic flavor first — it's the only one where
the "creative" step (voxelization) is mostly solved, so the differentiator
becomes the inventory-diff + BrickLink-order glue.

### BrickLink integration

BrickLink has a documented Wanted List XML format and a "Push to
BrickLink" URL pattern that pre-loads a cart. So the order step is real:
emit XML, hand the user a clickable link, they review and pay on
BrickLink. We don't handle money or inventory — BrickLink does.

### Risks / open questions specific to Idea 2

- **3D recognition fidelity.** A coffee mug is solvable; the user's
  dog is not (LEGO has no organic curve vocabulary at most scales).
  Constrain the input class up front: "objects that are mostly boxes,
  cylinders, and right angles" → houses, vehicles, furniture, cameras.
- **Color matching.** Real photos have thousands of colors; LEGO has
  ~60 official palette colors. Need a quantization step that's
  faithful but parts-aware (don't pick a color that comes in 3 brick
  shapes).
- **BrickLink shop fragmentation.** Even with a Wanted List, the user
  ends up ordering from 4–8 different sellers + 4–8 shipping fees.
  An optimizer step ("here's the 3-shop split that minimizes total
  cost") is the difference between a toy and a tool.
- **Cost transparency before clicking.** Show estimated total cost +
  shipping count *before* generating the LEGO model. "This will be
  $84 from 3 shops" is the qualifying gate.
- **Spending real money** raises the stakes vs. all the other ideas in
  this doc. Want explicit user confirmation between every step.

### Combo with Idea 1 — "build what you see, with what you have"

Ideas 1 and 2 share the same agent shape, just reversed:
- Idea 1: inventory is fixed, output is variable ("what can I make?")
- Idea 2: output is fixed, inventory is variable ("what do I need?")

Combining them is the most product-ready form: take a photo of the
target, voxelize, **subtract the user's existing inventory first**, and
only push to BrickLink for the remainder. That gives the user a real
answer to "what's the smallest amount of money I need to spend to build
this?" — which is the actual question casual builders are asking.

The shared sub-graph:
```
inventory (idea 1's scout)        target (idea 2's modeler)
        \                                /
         \______ inventory_diff ________/
                       │
                       ▼
              {can_build, missing_parts}
                       │
              ┌────────┴────────┐
              │                 │
       step_planner       bricklink_orderer
              │                 │
              └─────────────────┘
                       │
                       ▼
                 visual_writer
```

## Adjacent ideas

Order is roughly "easiest reuse of the core engine" → "biggest stretch."

1. **Set restoration assistant.** Photo of a partial pile + the original
   set name. Agent identifies missing pieces, lists them with BrickLink
   prices, and produces a "buy these 7 pieces for $8.40" report. A
   pure tooling change to the existing pipeline.

2. **Skill-/age-matched plan.** Inventory + "kid is 6, attention span
   ~15 min, just learned hinges." Plan filters concepts to that
   envelope; step planner caps complexity. New constraint, same shape.

3. **Multi-build chain (no teardown).** Plan 5–10 sequential builds
   where each one rearranges a small subset of bricks from the previous
   build — no full disassembly between. The agent has to pick a brick
   "vocabulary" once and reuse it. (This is the most genuinely novel
   one — it would actually save kids 30 min of dumping bins.)

4. **Storytelling layer.** After the plan is generated, narrate it:
   "this little red car drives to the green castle — chapter 1, build
   the car." Makes the artifact more useful for parent + child play.

5. **Bulk Tetris / organization plan.** Given a chaotic pile, generate
   a sorting/storage plan (by color, by family, by frequency-of-use)
   matched to the user's actual storage furniture. Image in, "put bricks
   into bins like this" out.

6. **MOC (My Own Creation) translator.** Free-form prompt ("cyberpunk
   taco truck") + inventory → buildable spec that approximates the
   prompt within the inventory. Hardest stretch — the concept proposer
   has to do real visual reasoning, not pattern matching.

7. **Trade matchmaker.** Two users share inventories. Agent finds
   complementary surpluses ("you have 40 red 2×4s, they have 35 blue
   2×2s") and proposes a Pareto-improving swap. Marketplace pattern,
   not really a building agent — but fits the same multi-agent shape.

8. **Themed party planner.** Theme + N kids' pooled inventories → per-
   kid plan that (a) fits the theme, (b) doesn't double-up rare bricks,
   (c) takes ~30 min each. Constraint-satisfaction problem dressed up
   as a party game.

9. **Time-boxed challenge generator.** "I have 20 minutes and this
   pile, make me a fun build." Step planner is bounded by step count.
   Useful for parents who want structured play without thinking.

## Open questions / risks

- **Inventory scanning is the hard part.** A photo of a chaotic pile is
  much harder to parse than an organized layout. May need user help
  ("flatten the pile, take 4 photos") or a vision model genuinely good
  at occluded small parts. Could fall back to manual input + barcode
  scan of any unopened sets.
- **Validator is non-trivial.** Detecting "this build won't stand" needs
  more than text reasoning — wants a mini physics/connection simulator
  (LDraw + LDCad-like checks). Could ship without it and let humans
  catch instability.
- **Render fidelity.** A bad preview makes the whole product feel
  cheap. Mecabricks / LDraw / Studio render quality varies; need to
  pick one early.
- **Audience.** Two very different users — kids/parents (low ceremony,
  fun-first) vs. adult AFOLs (precision, BrickLink integration). Pick
  one before tuning the writer's voice.

## Quickest demo path

If we want to validate the engine on this domain in a weekend:

**For Idea 1:**
1. Skip vision — let the user paste a JSON inventory (or pick a
   pre-built sample).
2. Wire 3 specialists: `concept_proposer`, `step_planner`,
   `visual_writer`. Skip the validator.
3. Render previews via Mecabricks or LDraw image export.
4. Demo on 3 fixed inventories + a shared "build chain" example.

**For Idea 2 (2D mosaic flavor):**
1. Photo → quantized pixel art using a fixed LEGO color palette.
2. Pixel art → 1×1 / 2×2 / plate-only bill of materials (small parts
   universe — keeps the parts_extractor trivial).
3. `inventory_diff` against a sample inventory.
4. Emit BrickLink Wanted List XML + push-to-BrickLink URL.
5. Demo on 4 fixed photos (a face, a logo, a city skyline, a pet).

Both share the same architectural pattern as Ouroboros — different
cast of specialists, same scout / sweep / writer shape. The combined
"photo in + use what you have first" version is the most defensible
product, but is also the most plumbing.
