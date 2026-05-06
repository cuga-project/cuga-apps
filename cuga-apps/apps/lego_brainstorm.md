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

## Idea 2 — "See it → build it in LEGO → order what's missing"

**Input:** a photo of a real-world object — coffee mug, chair, small
house, bookshelf, vintage camera.

**Output:**
1. A buildable LEGO model representing what was in the photo (not a
   pixel-faithful voxelization — a *recognizable LEGO version*).
2. Complete bill of materials (brick IDs, colors, counts).
3. Stepwise assembly instructions.
4. A pre-filled BrickLink Wanted List for any pieces the user doesn't
   already own — one click to "order missing parts."

**Why it's interesting:** the friction here is the gap between "I want
to LEGO-ify *that* thing" and "what bricks do I need to do it." Pieces
of the pipeline exist in isolation (mosaic generators, MOC libraries,
LegoGPT, BrickLink ordering) but **no one has stitched them end-to-end
into a "photo in, parcel at your door" loop**. That stitched loop is
the actual product.

### What changed the feasibility math: LegoGPT (May 2025)

The previously-hard middle of this pipeline — "go from a noun to a
buildable LEGO model" — now has an open-source solution. Carnegie
Mellon's **LegoGPT** is an autoregressive model that takes a text prompt
("small red car", "blue chair with a tall back") and emits a
**physically stable, buildable** LDraw `.ldr` file. Trained on 47K real
LEGO designs. MIT-licensed, public weights and code. Outputs a render,
a brick-by-brick text file, and an LDraw file.

That collapses the hardest step from "month of work" to "one model
call." The remaining work is glue.

LegoGPT's limitations to plan around:
- 20×20×20 brick grid only.
- 8 standard rectangular brick types — no curves, no Technic, no
  hinges, no studs-not-on-top.
- Text prompt input — so we still need a vision step *before* it that
  produces a clean caption ("small red car"), not the raw photo.

In practice that means **blocky, microscale-ish LEGO versions**: chairs,
cars, houses, mugs, bookshelves, simple animals — yes; roses, dogs,
detailed minifig-scale anything — no.

### The two paths (and the hybrid)

There's more than one way to "go from recognized object to buildable
model." The agent should try both:

1. **Retrieval** — search **Rebrickable's MOC database** (40K+ fan-built
   designs, all with full parts lists and instructions) for a matching
   design. If someone already designed a great LEGO truck, use theirs.
   Cheap, fast, often higher quality than generation. Has an API.
2. **Generative (LegoGPT)** — fall back when retrieval misses or when
   the user wants something custom.
3. **Hybrid (recommended)** — retrieval first, LegoGPT second. Best of
   both: production-grade community designs when they exist, generative
   tail when they don't.

### Multi-agent decomposition

| Specialist             | What it does                                                                 |
|------------------------|------------------------------------------------------------------------------|
| `vision_recognizer`    | Photo → object class + 1–2 attributes ("small red car"). Vision-LM call.    |
| `moc_retriever`        | Caption + attributes → Rebrickable MOC search. Returns ranked candidates with parts lists. |
| `legogpt_generator`    | Caption → LDraw `.ldr` file. Fallback when retrieval fails or user wants custom. |
| `parts_extractor`      | LDraw model → `{brick_id, color, count}` bill of materials.                  |
| `inventory_diff`       | Parts list − user's existing inventory = missing parts list.                 |
| `shop_optimizer`       | Missing parts → "split across N BrickLink shops to minimize total cost+shipping." (v2) |
| `bricklink_orderer`    | Missing parts → BrickLink Wanted List XML + push-to-BrickLink URL.           |
| `step_planner`         | LDraw model → ordered assembly steps (bottom-up, support-first).             |
| `visual_writer`        | Renders the final model + per-step previews.                                 |

Map onto Ouroboros's pattern: `vision_recognizer` is the scout;
retrieval/generation/parts/diff are the deep-dive sweeps; `step_planner`
+ `visual_writer` are the writer.

### Pipeline shape

```
photo
  │
  ▼
[vision_recognizer]    ── "this is a small red car"
  │
  ├─► [moc_retriever]      ── Rebrickable MOC search (try first)
  │     │
  │     └── if good match → ldr file
  │
  └─► [legogpt_generator]  ── fallback if retrieval misses
        │
        └── generated ldr file
              │
              ▼
        [parts_extractor]   ── ldr → parts list
              │
        [inventory_diff]    ── - your inventory = missing parts
              │
        ┌─────┴─────┐
        ▼           ▼
  [shop_optimizer]  [step_planner]
        │           │
  [bricklink_orderer]  [visual_writer]
```

### Risks / open questions specific to Idea 2

- **Vision step needs a clean caption, not a free description.** "Small
  red car" works; "the second-floor balcony of my apartment building"
  doesn't. Prompt engineering on the vision-LM matters; consider
  constraining to a fixed taxonomy of recognizable object classes.
- **LegoGPT's box of 8 brick types is small.** Out-of-distribution
  prompts (organic shapes, very large/small scales) will produce
  ugly results. Plan to filter aggressively in the retrieval step
  before falling through to LegoGPT.
- **BrickLink shop fragmentation.** Even with a Wanted List, the user
  lands on BrickLink staring at 4–8 different sellers each with their
  own shipping fee. Without a "split this list across N shops to
  minimize total cost" optimizer the experience feels broken. That
  optimizer is the genuinely hard piece, but it's deferrable to v2.
- **Cost transparency before clicking.** Show estimated total cost +
  shop count *before* generating the model. "This will be $84 from 3
  shops" is the qualifying gate.
- **Spending real money** raises the stakes vs. all the other ideas
  here. Explicit user confirmation between every step.

### Effort estimate (with LegoGPT in the picture)

- **Weekend MVP:** vision-LM caption + LegoGPT call + LDraw parser +
  BrickLink XML output. No retrieval, no shop optimizer, no inventory
  diff. End-to-end demo: photo in, parts list out, BrickLink link to
  click. Real, but rough.
- **2-week v1:** add Rebrickable MOC retrieval + inventory diff +
  step_planner + a basic visual_writer.
- **Month-ish v2:** add the multi-shop cost optimizer (the actual
  UX-defining piece for adult AFOLs).

The hardest engineering pieces are commodity now (LegoGPT, LDraw
parsing, BrickLink XML). The real work is the integration, the agent
loop, and the shop optimizer.

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

## API & tooling landscape

What exists, verified May 2026:

### Catalog / metadata APIs

- **LEGO Group itself: NO public catalog API.** They have developer
  programs for MINDSTORMS / Powered Up hardware, not for sets/parts/
  colors data.
- **Rebrickable API** — the de-facto standard for LEGO data. Free with
  an API key. Comprehensive parts / sets / colors / inventories. Hosts
  40K+ MOCs with parts lists and instructions. Auto-updated daily.
  Also offers full CSV downloads if you want to avoid the API.
- **Brickset API v3** — set/theme metadata, free with key.
- **BrickOwl API** — secondary marketplace (BrickLink competitor),
  cleaner API (no OAuth1 dance).

### Marketplace / ordering APIs

- **BrickLink Store API** — REST + OAuth1 (consumer-key, IP-locked
  tokens). Operational (acquired by LEGO Group 2019, API kept alive).
  Maintained Python / C# / JS client libraries.
- **BrickLink Wanted List XML upload** — no auth required. Generate
  XML, hand the user a `https://www.bricklink.com/v2/wanted/upload.page`
  URL, they review and pay on BrickLink. **This is the v1 path.** We
  never touch money or inventory.

### Photo → LEGO tooling

- **LegoGPT** (Carnegie Mellon, May 2025) — text → buildable LDraw,
  physically stable, MIT-licensed, public. Constrained to 20³ grid +
  8 brick types but covers the common case. **Best generative option
  for Idea 2.**
- **Image2Lego** — academic, photo → voxel → bricks pipeline.
- **Brick-a-Pic, Brickmos, DemiBrick, Lego Art Remix, Brickwork** — 2D
  mosaic generators, several with BrickLink Wanted List export.
- **Mecabricks / BrickLink Studio / LDraw + LeoCAD** — 3D editors and
  renderers, canonical formats.

### File formats

- **LDraw** — open text format for LEGO models. Documented, parser
  libraries exist in every language.
- **BrickLink XML** — the Wanted List upload format. Documented on
  BrickLink's site.

### What this means for picking a stack

- **Idea 1 (inventory → plan):** Rebrickable for catalog metadata,
  LDraw for model representation, optional BrickLink for "if you had
  these 3 extra bricks…" upsell.
- **Idea 2 (photo → replica → order):** Vision-LM (Claude / GPT-4V /
  Gemini) for recognition + caption, Rebrickable MOC API for
  retrieval, LegoGPT for generative fallback, LDraw for model rep,
  BrickLink XML for ordering. **No piece of this stack is missing.**

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

**For Idea 2 (recognition + LegoGPT flavor):**
1. Vision-LM call: photo → caption ("small red car"). Use a constrained
   prompt that forces a clean noun + 1–2 attributes.
2. LegoGPT call: caption → LDraw `.ldr` file.
3. LDraw parser: `.ldr` → `[{brick_id, color, count}]`.
4. Skip retrieval, skip inventory_diff, skip shop optimizer for this
   pass — emit a BrickLink Wanted List XML + push-to-BrickLink URL.
5. Demo on 4 fixed photos: a chair, a small house, a coffee mug, a
   simple car. (Avoid organic shapes — they're outside LegoGPT's
   distribution.)

That's the full minimum loop: photo in → BrickLink link out. The
v1/v2 increments add MOC retrieval, inventory diff, and the shop
optimizer.

Both share the same architectural pattern as Ouroboros — different
cast of specialists, same scout / sweep / writer shape. The combined
"photo in + use what you have first" version is the most defensible
product, but is also the most plumbing.

## Sources / reference links

- [LegoGPT project page (CMU, MIT-licensed)](https://avalovelace1.github.io/LegoGPT/)
- [LegoGPT paper — "Generating Physically Stable and Buildable LEGO Designs from Text"](https://arxiv.org/html/2505.05469v1)
- [Rebrickable API docs](https://rebrickable.com/api/)
- [Rebrickable MOC database](https://rebrickable.com/mocs/)
- [Rebrickable bulk CSV downloads](https://rebrickable.com/downloads/)
- [BrickLink Store API](https://www.bricklink.com/v2/api/welcome.page)
- [Brickset API v3](https://brickset.com/article/52664/api-version-3-documentation)
- [Brick Owl API](https://www.brickowl.com/api_docs)
- [Brick-a-Pic mosaic generator (open source)](https://brick-a-pic.github.io/)
- [Brickmos — image-to-LEGO with BrickLink integration](https://github.com/merschformann/brickmos)
- [Awesome LEGO machine-learning curated list](https://github.com/360er0/awesome-lego-machine-learning)
