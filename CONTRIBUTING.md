# pyreplay — the roadmap & contribution guide

Everything already built is in FEATURES.md (the 62-feature catalog).
This file is the other half — **every feature we know we want and have
not built yet** — and how to contribute one. It's written so a stranger
can pick an item and implement it. Features are numbered **#25 onward**
(#1–24 are already shipped).

## Start here — how to contribute

New here and want to help? Three steps:

1. **Pick something.** The **Index** below lists features #25–#86; the
   **Good first** lists at the end are the gentlest way in. Bug reports,
   edge cases, and more `example_*.py` programs are just as welcome.
   Adding **another language** is the biggest prize — see "Support
   another language" and the event-log schema at the end of this file.
2. **Follow the constitution** (next section) — standard library only,
   the honesty contract, and `checks.py` green before and after. Match
   the style of whatever file you're editing.
3. **Open an issue** describing the plan before a large change, so the
   approach can be agreed first.

Everything you need is in this repo — no external docs, no chat memory.

## The constitution (rules any implementation must respect)

1. **Three layers, one contract.** Tracer (Python) → event log
   (JSON embedded in HTML) → renderer (vanilla HTML/JS). New data
   means a schema addition, designed first.
2. **Stdlib only** in the tracer/mapper; **no build tools** in the
   renderer. Optional integrations (Hypothesis, py-spy) must degrade
   gracefully when absent.
3. **The honesty contract.** Mark exactly what is known; partial =
   unknown = unmarked; every cap, truncation and approximation is
   announced in the artifact itself. A statistical claim states its N.
4. **Observer effect declared.** Any feature that perturbs the run
   (line tracing, schedule fuzzing, fault injection) must label its
   output as perturbed. Time lives only where it is true.
5. **checks.py green before and after.** New invariants ship with new
   checks.

## The three lenses

In a lost session we asked what three exacting engineers would demand
of a code-study tool. The one idea that survived verbatim — *run the
code many times and do statistics, because code that looks reliable
can hide an error that only sometimes shows up* — headlines Section 1.
The rest is reconstructed as design lenses, not quotes:

- **The Hotz lens — machine truth, zero overhead.** Show the actual
  interpreter (bytecode, specializations), cost nothing when idle,
  attach to anything, never fake a number. → #47, #48, #64, #65, #55.
- **The Torvalds lens — bisect it, diff it, no magic.** Every bug is
  a difference between a world that works and one that doesn't; build
  the tools that find the first divergence. → #26, #32, #33, #57.
- **The Stroustrup lens — types, invariants, resources.** What holds
  always? What type flows here? Who owns this resource and who closed
  it? → #35, #36, #44, #46.

**Effort:** S = a focused day · M = several days · L = a week+, schema
touched · XL = multi-week / research-grade. **Payoff:** ★ nice ·
★★ strong · ★★★ changes what the tool is.

## Index

| # | Feature | Effort | Payoff |
|---|---------|--------|--------|
| 25 | Run it N times; count outcomes, catch flakes | M | ★★★ |
| 26 | First event where two runs diverge | L | ★★★ |
| 27 | Color lines by failing-run correlation (SBFL) | S | ★★★ |
| 28 | Auto-shrink a failing input (ddmin) | M | ★★ |
| 29 | Random-input entry with seed capture | M | ★★ |
| 30 | Perturb thread/task schedules to flush races | L | ★★★ |
| 31 | Inject exceptions/latency on purpose | L | ★★ |
| 32 | git bisect driven by a trace predicate | S | ★★★ |
| 33 | Compare implementations on the same inputs | M | ★★ |
| 34 | Record extra expressions each line (--watch) | S | ★★ |
| 35 | Contracts checked during the run (--invariant) | S | ★★ |
| 36 | Mine the invariants the runs never broke | L | ★★★ |
| 37 | Full backward slice of a value | L | ★★★ |
| 38 | Forward taint from an input | L | ★★ |
| 39 | "Why didn't this line run?" | M | ★★★ |
| 40 | Prove a loop is stuck (state recurrence) | M | ★★ |
| 41 | Catch the first NaN/Inf at birth | S | ★★★ |
| 42 | Strip-charts + phase portraits of variables | M | ★★★ |
| 43 | Object-reference graph at an event | L | ★★ |
| 44 | Per-variable type histograms; None alarms | M | ★★ |
| 45 | Array shape/dtype timeline | M | ★★★ |
| 46 | I/O lane via audit hooks; resource-leak pairing | M | ★★ |
| 47 | Code anatomy: AST + bytecode panel | S–XL | ★★ |
| 48 | Ternary/short-circuit verdicts via BRANCH events | L | ★★ |
| 49 | Memory heat on the map (tracemalloc) | M | ★★ |
| 50 | Who-woke-whom arrows across tasks/threads | L | ★★★ |
| 51 | Critical path through a concurrent run | M | ★★ |
| 52 | Lock-wait attribution | L | ★★ |
| 53 | Multiprocessing children traced into lanes | XL | ★★★ |
| 54 | Live streaming replayer (--serve) | L | ★★ |
| 55 | Attach to a running process (PEP 768) | M | ★★★ |
| 56 | Project-wide static call graph | L | ★★ |
| 57 | Git churn × complexity overlay | M | ★★★ |
| 58 | Declared layering rules; violations in red | S | ★★ |
| 59 | Dead code with runtime evidence | M | ★★ |
| 60 | Per-test chapters in suite traces | M | ★★★ |
| 61 | Startup import-cost view | S | ★★ |
| 62 | Public-API vs actual-use leaks | M | ★★ |
| 63 | Chunked trace + keyframes past 2M events | L | ★★★ |
| 64 | monitoring-backed cheaper LINE tracing | M | ★★ |
| 65 | Black-box flight recorder (ring buffer) | M | ★★★ |
| 66 | Reproducibility capsule (stdin/env/seeds) | S–XL | ★★★ |
| 67 | Schema spec + import/export bridges | M | ★★ |
| 68 | Deep links: a URL that opens a moment | S | ★★★ |
| 69 | Notes pinned to events; exportable | M | ★★ |
| 70 | Recorded walkthroughs (executable lessons) | M | ★★ |
| 71 | Query bar over all events | M | ★★★ |
| 72 | Two traces side by side, cursors synced | M | ★★ |
| 73 | Export a panel as video/GIF | M | ★★ |
| 74 | Sortable table view for list-of-dicts | S | ★★ |
| 75 | Ghost-highlight the untaken branch | S | ★★ |
| 76 | Hear the trace (sonification) | M | ★ |
| 77 | Text bundle of a trace slice | S | ★★ |
| 78 | Symbolic "what input reaches this line" | XL | ★ |
| 79 | Full deterministic record/replay | XL | ★★ |
| 80 | Console & logging lane synced to the trace | M | ★★★ |
| 81 | Dynamic edges: runtime relations the parse can't see | M | ★★★ |
| 82 | Boundary schemas: observed interfaces at the borders | M–L | ★★★ |
| 83 | NVTX bridge: Python names on the GPU timeline | M | ★★ |
| 84 | Shadowing & collision audit | S | ★★ |
| 85 | Float-hygiene probes | S–M | ★★ |
| 86 | Event-loop starvation detector | S | ★★ |
| 87 | Mutation-survivor forensics | M | ★★★ |
| 88 | Metamorphic relations harness | S–M | ★★ |

---

## Section 1 — The reliability lab (statistics over many runs)

The remembered idea, made a subsystem. One run is an anecdote; N runs
are an experiment. Everything here treats program behavior as a
distribution to be measured — the physicist's instinct applied to
software.

### 25. The N-run harness
- **What:** `tracer.py --runs 50 script.py` — execute the target N
  times (fn granularity by default), record per-run outcome (exit,
  exception type+site, wall time, event count) plus one representative
  trace per distinct outcome class.
- **Why:** *sometimes-code* is the worst code: it passes your one run
  and fails in the field. A 50-run table — "47 clean, 3 KeyError at
  cart.py:41" — converts a hidden flake into a measured rate before
  you hunt it.
- **How:** subprocess loop around the existing runner; outcomes
  aggregated into a JSON summary + a small HTML report (bar of
  outcomes, timing distribution: min/median/p95/max per run and per
  function from fn timestamps). Keep one full trace per outcome class
  (first passing, first of each failure) — not 50 traces. Honesty: the
  report states N, the granularity, and that timings are
  tracer-inclusive.
- **Effort:** M. The hard part is choosing what to keep (disk) and
  presenting distributions honestly.
- **Prior art:** every stress-test harness ever; pytest-flakefinder;
  the physicist's repeated-measurement instinct.

### 26. The divergence finder (recovers "trace-vs-trace diffing")
- **What:** given two traces of the same code (pass vs fail, before vs
  after an edit), find the **first event where they diverge** and show
  both timelines side by side from that point.
- **Why:** the whole question "why did THIS run fail?" reduces to
  "where did it first leave the good path?" — the single most valuable
  automated answer a trace tool can give.
- **How:** canonicalize each event to a token (file, line, frame-path,
  event kind — ids and timestamps excluded; fingerprints with
  object-ids normalized); align the two token streams (Myers diff /
  longest-common-subsequence, anchored at call boundaries so the
  alignment survives loop-count differences); report the first
  mismatch and the last common ancestor event. Renderer: dual view
  (see #72) opening at the divergence. Nondeterminism (dict of
  addresses, timing) is why canonicalization is the real work.
- **Effort:** L. Alignment robustness is the hard part; start with
  "identical prefix" (cheap, covers most real cases) and grow.
- **Prior art:** `git bisect` philosophy applied inside one run;
  Pernosco's multi-run analysis; McKeeman's differential testing.

### 27. Spectrum-based fault localization (SBFL)
- **What:** with the #25 harness's passing and failing runs, score
  every line: executed-in-failures vs executed-in-passes, Ochiai
  suspiciousness `ef / sqrt((ef+nf)·(ef+ep))`; paint scores on the
  source and the map as a **suspicion palette** (distinct from heat).
- **Why:** "which lines correlate with failure" narrows a codebase to
  a shortlist *before* you read anything — statistics doing the boring
  half of debugging.
- **How:** per-run line-coverage bitmaps (cheap at line granularity,
  or per-function at fn granularity) + a 20-line scoring pass; a
  ranked "top suspicious" panel with jump links. Honesty: correlation
  ≠ causation, N stated, ties shown as ties.
- **Effort:** S once #25 exists (and #60 makes it work per-test).
- **Prior art:** Tarantula (Jones/Harrold/Stasko 2002), Ochiai (Abreu
  et al.) — a whole academic field, almost never available to working
  Python programmers.

### 28. Automatic input shrinking (delta debugging)
- **What:** `--shrink` — given a failing run and a failure predicate
  (exception type/site or `--start-when`-style expression), minimize
  the stdin/argv that still reproduces it (ddmin: remove chunks,
  re-test, recurse).
- **Why:** a 2 MB input that crashes is a chore; the 3-line core that
  still crashes is a diagnosis. Minimal inputs also make minimal
  traces.
- **How:** harness around the runner: split stdin into lines/tokens,
  ddmin loop with a per-attempt cap; emit the minimized input file +
  auto-trace the minimal case at line level. Input model is
  configurable (lines | whitespace tokens | bytes).
- **Effort:** M.
- **Prior art:** Zeller & Hildebrandt's ddmin ("Simplifying and
  isolating failure-inducing input", 2002); Hypothesis's shrinker;
  creduce.

### 29. Property/fuzz entry
- **What:** `--fuzz GEN.py` — run a user-supplied generator function
  that yields random inputs (seeded, seed recorded per run) through
  the N-run harness; on first failure, keep the seed, re-run traced,
  and hand the input to #28 to shrink.
- **Why:** the runs-statistics idea aimed at *inputs* instead of
  scheduling: you don't have a failing case yet — go find one while
  you sleep.
- **How:** generator protocol = a Python file with `def gen(rng):`
  returning stdin-bytes/argv; seeds logged so every run is
  reproducible forever. Optional bridge: if Hypothesis is installed,
  accept a `@given` strategy as the generator; degrade gracefully
  without it.
- **Effort:** M.
- **Prior art:** Hypothesis (MacIver), AFL's philosophy (keep the
  seed, minimize the case), property-based testing.

### 30. Schedule fuzzing (concurrency chaos)
- **What:** `--chaos-schedule SEED` — perturb interleavings on
  purpose: randomized micro-delays injected from the trace callback at
  line/call boundaries, `sys.setswitchinterval` jitter for threads, a
  shuffling event-loop wrapper for asyncio ready-queues; combined with
  #25 to measure "fails 7/100 under perturbation, 0/100 without".
- **Why:** race conditions are probability distributions; widening the
  explored interleaving space is how you collapse "works on my
  machine" into a reproducible rate. This is the multi-run idea's
  sharpest edge.
- **How:** the tracer already sits inside every line event — a seeded
  `random` micro-sleep there is a legal scheduler perturbation with
  zero target-code changes. Honesty: traces made under chaos are
  labeled PERTURBED in the banner; timings are not reported as truth.
  Seed recorded → a failing interleaving can be re-run.
- **Effort:** L (asyncio wrapper is the delicate half).
- **Prior art:** rr's chaos mode; Microsoft Coyote; PCT (probabilistic
  concurrency testing, Burckhardt et al. 2010) — PCT's insight (few
  random priority-change points find most races) is directly
  portable.

### 31. Fault injection (chaos engineering for one process)
- **What:** `--inject "shop.pay:raises=TimeoutError:on_call=3"` —
  force a chosen call site to raise / return a sentinel / stall, then
  watch (with the existing exception machinery) how the failure
  propagates and what catches it.
- **Why:** error-handling paths are the least-executed, least-tested
  code in any codebase; injection is the only way to *see* them run.
  The propagation-chain view (#32 in FEATURES) was built for exactly
  this moment.
- **How:** an import-time wrapper installed by the tracer around the
  named callable (we own the process bootstrap); every injection is
  recorded as a first-class INJECTED event so the trace never lies
  about what really happened.
- **Effort:** L.
- **Prior art:** Netflix chaos engineering, aerospace HALT testing —
  break it on the bench, not in the air.

### 32. Behavioral bisect (git × tracer)
- **What:** a documented `--check EXPR` mode: run the target, exit 0/1
  on a predicate over the run (exception happened, output contains X,
  event-count over N, `--start-when`-style state test) — precisely
  what `git bisect run` needs to find **the commit where behavior
  changed**.
- **Why:** connects the two most powerful bisection tools the user
  has: git's history search and the tracer's ability to *ask questions
  about a run*. "Which commit made f() start returning None?" becomes
  one command.
- **How:** mostly plumbing: reuse the `--start-when` evaluator as a
  run-level predicate + clean exit codes + a TUTORIAL recipe
  (`git bisect start BAD GOOD; git bisect run python3 tracer.py
  --check "..." entry.py`).
- **Effort:** S.
- **Prior art:** `git bisect run` — the Torvalds lens in its purest
  form.

### 33. Differential testing against a reference implementation
- **What:** `--oracle brute.py fast.py --fuzz GEN.py` — run two
  implementations on the same inputs; on output mismatch, keep the
  input, trace **both**, and open the divergence finder (#26) on the
  pair.
- **Why:** the repo already contains
  `strategy_1_brute_force.py … strategy_4_segment_tree.py` — the
  AtCoder workflow IS differential testing done by hand. Automate the
  loop: the brute force is the specification.
- **How:** harness compares stdout (configurable normalizer); wire to
  #28 to shrink the disagreement input. No schema changes.
- **Effort:** M.
- **Prior art:** McKeeman, "Differential testing for software" (1998);
  Csmith; competitive programmers' stress-test scripts everywhere.

---

## Section 2 — Deeper causality (from "what changed" to "why")

### 34. Watch expressions at record time (reframes a rejected idea)
- **What:** `--watch "len(queue)" --watch "cart.total()"` — arbitrary
  expressions evaluated **during the run** at each line event of
  chosen frames, recorded as synthetic variables with full life
  navigation, plots (#42), and provenance participation.
- **Why:** the old rejection ("replay-side eval belongs to Python, not
  the viewer") stands — so evaluate at *record* time, where Python is
  alive. Derived quantities (lengths, sums, ratios) are often the real
  signal; physicists call them observables.
- **How:** the `--start-when` compile-and-eval machinery, run
  unconditionally and stored under a `watch:` namespace; failures
  record as "not evaluable here" (honest), never crash the run. Cost
  is per-line eval — announced, and scopable with `--include`.
- **Effort:** S.
- **Prior art:** every debugger's watch pane — but recorded over the
  whole run instead of one paused moment.

### 35. Continuous invariants (`--invariant`)
- **What:** `--invariant "balance >= 0" --invariant "i <= j"` —
  expressions that must hold; every violation is recorded as a soft
  VIOLATION event (amber, scrubber markers, count in the banner) while
  the run continues.
- **Why:** assertions you don't have to edit into the code, checked
  everywhere, with the trace showing state at each violation. The
  contract mindset without touching the target.
- **How:** same evaluator as #34; a violation stores the expression,
  values of its names, and links into provenance ("which assignment
  broke it"). Also honest about scope: checked only where the frame
  defines the names.
- **Effort:** S.
- **Prior art:** Design by Contract (Meyer/Eiffel), C's assert —
  Stroustrup lens distilled.

### 36. Invariant mining (Daikon-lite)
- **What:** observe many runs (#25) and **propose** the invariants
  that never broke: `x > 0`, `i < len(a)`, `a is sorted at return`,
  `type(x) constant`, `total is monotonically nondecreasing` — per
  function entry/exit and per loop.
- **Why:** mined invariants are executable documentation ("what this
  code actually guarantees") and bug detectors (a run that breaks a
  99%-invariant is your suspect — feed it to #26).
- **How:** a template library checked against the recorded
  fingerprints offline (no run-time cost): candidate set instantiated
  per variable/pair, killed on first counterexample, survivors ranked
  by support. Displayed on function rows in map and replayer. Honesty:
  "held in N observed runs" is an observation, never a proof.
- **Effort:** L (noise control is the craft: too many trivial
  invariants = spam).
- **Prior art:** Daikon (Michael Ernst et al.) — the canonical dynamic
  invariant detector; almost never applied to everyday Python.

### 37. Full backward slice (transitive provenance)
- **What:** today's provenance panel is one hop ("← from a, b").
  Slice mode: click a value → compute the closure — **every event
  that contributed to it** — and dim the rest of the trace; the
  scrubber shows only slice events; step keys walk the slice.
- **Why:** "how did this wrong answer come to be" as a first-class
  navigation mode: the trace reduced to the 2% of events that matter
  for one value.
- **How:** iterate the existing per-line target←sources dataflow over
  the change index (BFS backwards through assignments and, at call
  boundaries, from return values to return statements to their
  sources). Honesty carries over: attribute/subscript writes and
  C-level effects are marked as slice frontier ("beyond this point the
  chain is not tracked").
- **Effort:** L.
- **Prior art:** program slicing (Weiser 1981; Korel/Laski dynamic
  slicing; Agrawal); Cyberbrain — ours stands on ast dataflow instead
  of fragile bytecode value-stacks.

### 38. Forward taint ("descendants of this input")
- **What:** the same walk, forward: mark a value (an stdin field, a
  config entry, a function argument) and highlight every variable and
  branch verdict it influenced downstream.
- **Why:** "if I change this config, what is affected?" and "which
  outputs depend on this input?" — impact analysis and data lineage in
  one gesture; the security cousin is classic taint analysis.
- **How:** transpose the #37 graph; tainted verdicts (a branch whose
  condition read a tainted value) mark whole control regions as
  control-tainted, displayed distinctly (data vs control influence —
  the honest split).
- **Effort:** L (shares 80% of its machinery with #37 — build
  together).
- **Prior art:** taint tracking (Perl's taint mode, TaintDroid);
  data-lineage tooling in databases.

### 39. Whyline queries — "why didn't this line run?"
- **What:** click any line that never executed (or a variable that
  never changed) and get the causal answer: "the guard at
  cart.py:38 evaluated False on all 12 arrivals — here they are",
  chained upward ("and that condition was False because…").
- **Why:** debugging is half *absence*: the branch not taken, the
  handler not reached, the function never called. We already record
  every verdict — the missing piece is the question-answering UI.
- **How:** static dominator analysis on the function's ast (which
  branches guard this line) + the recorded verdicts at those guards +
  coverage. No new events; renderer feature over existing data. The
  chain view recurses one level per click (keeps it honest and cheap).
- **Effort:** M.
- **Prior art:** the Whyline (Amy Ko & Brad Myers) — repeatedly shown
  to halve debugging time in studies, and virtually absent from real
  tools.

### 40. Nontermination detector (state recurrence)
- **What:** for a loop suspected of hanging: hash (line, frame's
  fingerprint set) each iteration; an **exact repeat proves** the loop
  can never exit (pure state) — banner: "iteration state at event
  1,204 identical to event 980: proven cycle, period 224 events."
- **Why:** the difference between "it seems stuck" (heartbeat already
  tells you) and "it IS stuck, here is the cycle" — with the cycle's
  events right there to study.
- **How:** rolling hash per loop head (loop heads known from the ast);
  Floyd/Brent-style memory-bounded detection. Honesty: any I/O,
  randomness, time or untracked external state in the loop downgrades
  "proven" to "state recurring at line level" — the banner says which.
- **Effort:** M.
- **Prior art:** cycle detection (Floyd 1967, Brent); the physicist's
  framing is Poincaré recurrence — a closed system returning to a
  previous state must repeat forever.

### 41. NaN/Inf tripwire (first-origin of numerical poison)
- **What:** `--trip nan` — the fingerprint encoder tests floats as it
  sees them; the FIRST NaN/Inf in the run raises a first-class TRIP
  event with the provenance link to the operands that produced it;
  every later spread is marked quietly.
- **Why:** for scientific code the question is never "is there a NaN"
  (the crash tells you) but "**where was it born**" — usually
  thousands of operations earlier. This is the single highest-value
  scientific-Python feature on this list relative to cost.
- **How:** an `isnan/isinf` check inside the existing encoder
  (bounded, only on floats already being fingerprinted); works with
  triggers ("start recording AT the first NaN" = `--start-trip nan` —
  the pre-trigger cheap watch loop does the testing). Generalize:
  `--trip "negative"` for domain tripwires via #35's machinery.
- **Effort:** S.
- **Prior art:** numpy's errstate/seterr (raises where it happens, not
  where it *came from* — provenance is our edge); debuggers' hardware
  watchpoints, in spirit.

---

## Section 3 — New instruments (measure what is invisible)

### 42. The variable oscilloscope (strip-charts + phase portraits)
- **What:** any numeric variable (or #34 watch) gets a `chart` view:
  value vs event-axis as a strip-chart with change points, crash and
  trip markers aligned; pick TWO variables → a **phase portrait**
  (x vs y trajectory).
- **Why:** the life strip shows *when* a value changed; the chart
  shows *how it evolved* — drift, oscillation, plateaus, blow-up. A
  phase portrait makes relationships visible: convergence spirals,
  limit cycles (a loop stuck orbiting), the moment two quantities
  decouple. This is the physicist's instrument panel aimed at code.
- **How:** renderer-only — the change index already holds the series;
  a small canvas plotter (no libraries), log-scale toggle, honest gaps
  where the value was non-numeric. Effort M.
- **Prior art:** oscilloscopes and strip-chart recorders; dynamical
  systems' phase-space analysis; no mainstream debugger has this.

### 43. Heap topology view (the pointer graph)
- **What:** at the current event, draw the object-reference graph
  around a chosen variable: nodes = objects (typed, sized), edges =
  references; shared objects (our 🔗 aliases) visibly shared; cycles
  drawn as cycles; depth/size caps announced.
- **Why:** Python's actual data model is a graph of references —
  aliasing bugs, accidental sharing and reference cycles live in the
  topology, which repr trees cannot show. The 🔗 glyph says "same
  object"; this shows the whole neighborhood.
- **How:** schema addition: on selected events (or on demand in
  watch()), record shallow edge lists via `gc.get_referents` for
  visible objects (ids canonicalized to stable labels, hard caps,
  honesty flags when cut). Renderer reuses the graph-view engine.
- **Effort:** L.
- **Prior art:** Python Tutor's heap diagrams (Philip Guo) — the best
  teaching visualization Python has ever had, absent from tools for
  real codebases.

### 44. Type-flow histograms & instability alarms
- **What:** aggregate the types every variable/argument/return
  actually had across a run (and across #25 runs): function rows gain
  "x: int 98% · None 2%" — with the 2% linked to their events; a ⚠
  on unstable types.
- **Why:** the sneaky None, the str that is sometimes bytes, the
  float that becomes np.float64 — type instability is where dynamic
  code rots. Observed types complement annotations: this is what the
  code DID, not what it promised.
- **How:** types are already recorded per fingerprint; this is an
  offline aggregation + display (map function rows, replayer variable
  header). Compare against annotations when present (`typing` imported
  → "annotation says str, observed 3% bytes" — honest, not a linter
  verdict).
- **Effort:** M.
- **Prior art:** JIT deoptimization analysis (V8/PyPy treat type
  instability as the enemy); MonkeyType (Instagram) records call types
  — ours ties them to moments you can jump to.

### 45. Array shape/dtype timeline
- **What:** for objects exposing `.shape`/`.dtype` (numpy, torch,
  pandas) — record that metadata even though internals are opaque:
  each variable gets a shape timeline; a SHAPE-CHANGE badge when it
  transitions ((3,N)→(N,3) is the classic silent transpose).
- **Why:** the tracer honestly cannot see inside C extensions (the
  brian2 lesson) — but shapes at Python boundaries are where
  broadcasting bugs are visible. For scientific users this is the
  microscope's missing objective.
- **How:** the encoder, on meeting an opaque object, safely probes
  `shape/dtype/len` under try/except and stores a compact header
  fingerprint; diffing marks shape changes as first-class. Works
  today at line granularity; cheap.
- **Effort:** M.
- **Prior art:** every numpy debugging session ever conducted by
  printing `.shape`; TensorBoard's graph shapes, made local.

### 46. The I/O lane (strace-lite) + resource pairing
- **What:** record `sys.addaudithook` events — file opens, socket
  connects, subprocess spawns, `exec/eval`, imports — as a parallel
  I/O lane in the replayer, each linked to the frame that caused it;
  pair opens with closes (via weakref finalizers on returned handles)
  and report unclosed resources at exit.
- **Why:** "what did this program touch?" — files read, hosts
  contacted, commands run — answered from the trace; plus the
  Stroustrup-lens question "who owns this resource and did they
  release it". Also a light supply-chain audit: an import that opens
  a socket stands out.
- **How:** audit hooks are stdlib, near-free, and fire regardless of
  granularity (they even work in fn mode). Close-pairing needs a
  small in-process shim in the runner (wrap `open`'s return with a
  finalizer track) — labeled honestly as instrumentation. Socket
  events carry their target addresses (an endpoints inventory for
  free); payload capture stays external on purpose (mitmproxy et
  al. — we bridge specialists, we don't clone them).
- **Effort:** M.
- **Prior art:** strace/ltrace; PEP 578 audit hooks (designed for
  security auditing, almost never surfaced to developers).

### 47. Code anatomy panel (recovers "opcode-level" — AST + bytecode)
- **What:** Tier 0 (static): a collapsible AST tree of the selected
  function — the syntax layer above the bytecode, instaviz-style.
  Tier 1 (static): a panel showing `dis` output for the
  current line — the actual instructions, with 3.12+
  `dis(adaptive=True)` revealing specialized/quickened opcodes. Tier
  2 (dynamic, XL): per-instruction stepping via `f_trace_opcodes` /
  `sys.monitoring` INSTRUCTION events for one chosen line range.
- **Why:** the Hotz lens: the interpreter is not magic; `a < b` is
  COMPARE_OP plus method dispatch; `x += y` on a list is not what it
  is on an int — and the adaptive interpreter shows WHERE CPython
  specialized your hot code.
- **How:** Tier 1 is renderer+mapper work over `dis.get_instructions`
  with `co_positions()` mapping (3.11+) — no schema change, effort S.
  Tier 2 multiplies event volume ~10× — only sane inside a
  `--include`+trigger microscope; effort XL; honesty: instruction
  events are 3.12+, labeled per-version.
- **Prior art:** `dis` module; PEP 659 specializing interpreter —
  visible in no mainstream tool.

### 48. Sub-line branch verdicts (BRANCH events)
- **What:** the documented blind spot — ternaries, `and`/`or`
  short-circuits, comprehension `if`s — closed on 3.12+ via
  `sys.monitoring` BRANCH/JUMP events: verdicts for branches *inside*
  a line, shown at column precision (`co_positions`).
- **Why:** today the honesty note says "sub-line branching is not
  visible"; this deletes the caveat where the interpreter allows it.
- **How:** extend the monitoring backend (line mode, #64) to register
  BRANCH; map instruction offsets to source columns; the Event panel
  underlines the sub-expression with its verdict. Falls back honestly
  pre-3.12.
- **Effort:** L.
- **Prior art:** PEP 669's event set (refined further in 3.14);
  coverage.py's branch coverage — which counts, but never *shows*.

### 49. Memory heat (calorimetry)
- **What:** `--memory` — sample `tracemalloc` snapshots at intervals
  (and at call boundaries in fn mode); the map gains a third palette:
  **BYTES ALLOCATED (net / peak)** per module; the replayer shows a
  memory strip-chart with event-aligned markers.
- **Why:** time-heat says where the run computed; memory-heat says
  where it *retained* — leaks, caches gone wrong, the 38 GB brian2
  incident announced while it grows rather than at the OOM kill.
- **How:** tracemalloc is stdlib with per-file statistics
  (`snapshot.statistics('filename')` aggregates straight onto map
  modules); overhead is real and announced (banner: "recorded under
  tracemalloc ×N overhead"). Schema: periodic MEM events. Honesty —
  the C-extension trap: tracemalloc sees only Python-level
  allocations; a numpy/torch tensor allocated in C shows ~zero here
  while system RSS climbs — the banner must say so, and the
  native-allocation specialist in the funnel is Memray (external,
  used as-is). `statistics('lineno')` also enables per-line
  attribution inside a microscope view.
- **Effort:** M.
- **Prior art:** tracemalloc/memray; the physics analogy is
  calorimetry — measure what the system absorbed, not just what it
  did.

---

## Section 4 — Concurrency truth

### 50. Happens-before arrows (who woke whom)
- **What:** causality edges drawn between lanes: task A *created* B,
  cancelled C, `gather`ed D; a queue `put` in one lane linked to the
  `get` that received the same item in another; thread `start`/`join`
  edges.
- **Why:** lanes show interleaving; they don't show **causation**.
  Race debugging is precisely about the arrows — which write was
  visible to which read, who released whom.
- **How:** creation/cancel/join/gather are visible at call events
  today (record task-id args); queue correlation needs object-id +
  item-fingerprint matching (honest: "same-value items may alias" —
  mark uncertain matches). Renderer: arrows across lanes, click to
  jump both ends. Trio/greenlet support rides on the same schema if
  someone contributes the hooks.
- **Effort:** L.
- **Prior art:** Lamport's happens-before; vector clocks; distributed
  tracing span links (OpenTelemetry) — imported into a single
  process.

### 51. Critical-path highlight
- **What:** for an fn-granularity concurrent trace: compute the
  longest dependency chain (through awaits, joins and #50 edges) that
  determined total wall time; paint it gold in lanes and Perfetto
  export.
- **Why:** "we are 40% async" is trivia; "these five awaits ARE your
  runtime, everything else overlaps for free" is an optimization
  order. Speeding up anything off the critical path is wasted work.
- **How:** classic CPM/PERT longest-path over the slice DAG (slices +
  happens-before edges); needs #50. Honest about untracked externals
  (network waits show as gaps attributed to the awaiting slice).
- **Effort:** M after #50.
- **Prior art:** PERT/critical-path method (1950s operations
  research); Chrome's flame charts have it for the web — Python
  doesn't.

### 52. Lock-wait attribution
- **What:** time spent *waiting* vs *holding* each lock/semaphore:
  which call sites contend, who blocked whom, longest queue.
- **Why:** contention is invisible in source and dominant in threaded
  performance; "3 threads spent 4.1 s waiting for the lock acquired
  at cache.py:60" ends the guessing.
- **How:** `threading.Lock.acquire` is a C call — invisible to
  settrace, but `sys.monitoring` CALL + C_RETURN events (3.12+) can
  time it; correlate holder/waiter by lock id. fn-granularity only
  (times must be true). Falls back to a documented "not on <3.12".
- **Effort:** L.
- **Prior art:** Linux `perf lock`; JVM contention profilers — a
  category Python tooling barely has.

### 53. Multiprocessing lanes (recovers a "documented limit")
- **What:** children of `multiprocessing`/`concurrent.futures`
  traced too (fn granularity), each child writing
  `trace_…pid.html`-part files, merged into one replayer as extra
  lanes with fork/spawn arrows from the parent.
- **Why:** the "one process only" limit excludes the standard way
  Python escapes the GIL — pools, workers, joblib. The map's heat
  also silently under-counts pooled work today.
- **How:** the coverage.py pattern: the runner sets an env hook
  (`.pth`/sitecustomize) so any child Python auto-starts a tracer in
  fn mode writing to a shared session directory; merge aligns per-
  process monotonic clocks via the fork/spawn call's timestamp pair
  (skew honestly labeled ±). Renderer scales via #63.
- **Effort:** XL (bootstrap is fiddly, merge is careful work) —
  arguably the largest single unlock on this list for real codebases.
- **Prior art:** coverage.py's multiprocessing support; VizTracer's
  multiprocess tracing; Perfetto's multi-track model (already our
  export target).

### 54. Live mission control (`--serve`)
- **What:** watch the trace **while the program runs**: tracer
  streams events over a localhost `http.server` + SSE; the replayer
  follows live (or you scrub back while it continues), heartbeat
  becomes a live event counter.
- **Why:** for long simulations the current loop is run→wait→open;
  live mode turns pyreplay into a control room — see the phase you're
  in (density strip growing), spot the exception the moment it
  happens, decide to Ctrl-C with evidence.
- **How:** stdlib-only (http.server thread + Server-Sent Events; the
  replayer already renders incrementally by design of the event log).
  The written file at exit stays the durable artifact — the honesty
  contract's single source of truth.
- **Effort:** L.
- **Prior art:** every observability dashboard; py-spy top's live
  view — but with full event fidelity instead of samples.

### 55. Attach to a running process (PEP 768)
- **What:** `tracer.py --attach PID` — on Python 3.14+, inject a
  `watch()`-style recorder into an ALREADY-RUNNING process via the
  new safe external debugger interface (`sys.remote_exec`), record a
  bracket, detach cleanly.
- **Why:** the documented gap vs py-spy ("we always launch the script
  ourselves") closes: the server that misbehaves NOW, the notebook
  kernel you forgot to instrument — reachable without a restart.
- **How:** `sys.remote_exec(pid, bootstrap.py)` where bootstrap
  imports our watch() with a time/event budget and writes the trace
  to an agreed path; all watch() semantics (cap without killing the
  host, restore prior settrace) already exist — that groundwork was
  #24.
- **Effort:** M once 3.14 is the floor; the safety analysis is the
  work.
- **Prior art:** PEP 768 (accepted for 3.14); py-spy --dump; rr's
  attach.

---

## Section 5 — The map grows

### 56. Project-wide static call graph
- **What:** today's call routes are module→module counts and the
  intra-file graph is per-file; the completion: resolve `from x
  import f` / `x.f()` across files into one project call graph —
  function-level edges everywhere, with the unresolved remainder
  counted per module (the existing honesty style).
- **Why:** "who can reach this function from where?" across the whole
  codebase — the static skeleton the dynamic trace is drawn onto,
  finished.
- **How:** symbol table per module (defs, imports, aliases) + a
  resolution pass (direct names, `self.method` within a class,
  best-effort attribute chains); every edge labeled resolved/guessed.
  Feeds better ⌖ commands and #59.
- **Effort:** L.
- **Prior art:** pyan3 (unmaintained), Sourcetrail (discontinued —
  its niche is empty), IDE indexers (closed and per-symbol).

### 57. Crime-scene overlay (git churn × complexity)
- **What:** a second map palette from history: per-module change
  frequency (`git log --numstat`) × a stdlib-computed complexity
  score; the risk quadrant = **churns often AND complex AND hot at
  runtime** (when heat exists) — the strongest bug predictor known.
- **Why:** the map currently shows structure and one run's behavior;
  history is the third axis. "This module changed 44 times in 6
  months, is the most complex in the repo, and carries 90% of the
  runtime" is where you send review effort first.
- **How:** subprocess `git log` parse (no deps), cyclomatic-ish score
  from the ast we already walk; palette toggle CHURN / RISK with the
  legend naming the window ("last 12 months, 214 commits"). Works on
  any git repo, degrades to absent without git.
- **Effort:** M.
- **Prior art:** Adam Tornhill's *Your Code as a Crime Scene*;
  Nagappan & Ball's defect-prediction studies; CodeScene
  (commercial) — none of it free and local.

### 58. Layering rules (declared architecture, enforced visually)
- **What:** an optional `.pyreplay-layers` file ("ui → logic → data;
  data must not import ui"); the map paints violating import edges
  red with a VIOLATION list in the notes.
- **Why:** every codebase has an intended architecture that erodes
  silently; the map already draws every import — one config file
  turns it into the architecture's guardian.
- **How:** tiny rule parser + edge classification at render time;
  `--check-layers` exits non-zero for CI use.
- **Effort:** S.
- **Prior art:** import-linter; ArchUnit (Java) — the visual half is
  ours for free.

### 59. Dead-code evidence report
- **What:** combine static reachability (#56, from entry points and
  `__init__` exports) with dynamic never-executed (across every trace
  the auto-heat scanner can find): a ranked list — "statically
  unreachable AND never executed in 9 recorded runs" down to "only
  unreached in traces".
- **Why:** deleting code is the highest-leverage refactor and the
  scariest; two independent kinds of evidence make it a decision
  instead of a bet. The honesty contract does the labeling
  ("evidence, not proof — reflection and plugins can hide callers").
- **How:** set algebra over data both tools already produce; report
  as a map mode (ghost-gray candidates) + text list.
- **Effort:** M.
- **Prior art:** vulture (static-only); coverage.py (dynamic-only) —
  the join is the feature.

### 60. Per-test chapters (the suite dissected)
- **What:** when the entry is `-m pytest`, record test boundaries as
  chapter events (a tiny auto-injected pytest plugin): the density
  strip gains test-colored segments with names; heat can be filtered
  per test; "which tests touch module X" appears on every map box.
- **Why:** a suite trace today is one undifferentiated river. Chapters
  make it navigable — jump to test_checkout's segment — and unlock
  the killer join: **failing test × SBFL (#27) = ranked suspect
  lines** from one suite run.
- **How:** we own the pytest invocation (#21) — add `-p pyreplay_shim`
  injecting start/end/outcome marker events; everything downstream is
  aggregation and rendering.
- **Effort:** M.
- **Prior art:** pytest's own reporting; Google's test-impact
  analysis — miniaturized to one repo.

### 61. Import-cost view (startup autopsy)
- **What:** a dedicated report from any fn trace: time under each
  `<module>` frame at startup, as a treemap-ish list on the map —
  "1.9 s before main(): pandas 1.1 s, your plugins 0.4 s…".
- **Why:** slow CLI/test startup is pure import cost and nobody knows
  whose; the data is already in every fn trace — this is a lens, not
  a recorder.
- **How:** aggregate existing events beneath import frames (the ⚙
  badge machinery knows them); render as a sorted panel with map
  links.
- **Effort:** S.
- **Prior art:** `python -X importtime` (text, per-process, hard to
  read) — ours lands on the map with jump links.

### 62. API-surface honesty (encapsulation leaks)
- **What:** per package: what it exports (`__all__`, public names) vs
  what outsiders ACTUALLY import from it (the map knows every import
  edge): a leak list — "7 modules reach into `store._internal`".
- **Why:** the gap between intended and real interfaces is where
  refactors break the world; measuring it turns "please don't import
  private stuff" into a number that can go down.
- **How:** pure aggregation over existing mapper data; a per-package
  panel + underscore-import edges drawn dashed-red on demand.
- **Effort:** M (mostly presentation).
- **Prior art:** the `_underscore` convention itself; no common tool
  audits it.

---

## Section 6 — Scale & interchange

### 63. Chunked trace + keyframes (recovers backlog #20)
- **What:** break the single embedded JSON into gzipped chunks with
  periodic full-state **keyframes**; the replayer loads O(window)
  around the cursor instead of O(run).
- **Why:** the ~2M-event / ~512 MB browser wall is the hard ceiling on
  everything else (multiprocessing lanes, whole-suite line traces,
  #65 dumps). Keyframes also make seek instant at any size.
- **How:** browser-native `DecompressionStream('gzip')` (no build
  tools broken); tracer writes chunk boundaries at call-depth-zero
  points; a keyframe = full variables snapshot (the trigger
  machinery already knows how to reconstruct state — reuse it).
  Honesty: the banner shows chunk count and any missing chunk loudly.
- **Effort:** L.
- **Prior art:** video codecs (I-frames/P-frames — this is literally
  that); Perfetto's trace processor.

### 64. Cheap LINE tracing via sys.monitoring
- **What:** extend the monitoring backend (#19/fn-only today) to LINE
  events with surgical enable/disable per code object — line-level
  microscopes at a fraction of settrace's ~100× tax (target ~10–20×).
- **Why:** every line-level feature (verdicts, provenance, machinery)
  gets cheaper; triggers get cheaper still (watch mode = LINE events
  on ONE code object only, near-free).
- **How:** register LINE + the existing exception set; per-code
  `set_local_events` is the whole trick; keep byte-parity checks vs
  settrace in checks.py (the #19 discipline).
- **Effort:** M.
- **Prior art:** PEP 669's stated purpose; coverage.py 7.x's
  sysmon-based speedups prove the win is real.

### 65. Black-box flight recorder
- **What:** `--black-box` — near-zero-cost fn-granularity ring buffer
  (last N events only, in memory); on crash OR on signal
  (`SIGUSR1`), dump the buffer as a normal trace. Run it always.
- **Why:** the bug that happens once a week at minute 40 will never
  happen under a full trace. A flight recorder inverts the deal: pay
  ~nothing forever, have the last 100k events the moment it matters.
- **How:** fixed-size deque of encoded events (fn mode + monitoring
  backend = cheap enough); dump path reuses _write_trace(); the
  banner states the window honestly ("events before N are lost —
  ring buffer"). Pairs beautifully with watch() for servers.
- **Effort:** M.
- **Prior art:** aviation FDR/CVR; automotive EDR; VizTracer's ring
  buffer — none produce a self-contained replayer file.

### 66. Reproducibility capsule (tiers of rr)
- **What:** Tier 1 (S): every trace embeds the run's capsule — argv,
  cwd, env subset, python/platform versions, stdin **tee'd** into
  the file, PYTHONHASHSEED — plus a "reproduce" box printing the
  exact rerun command. Tier 2 (M): `--seed-all` sets/records seeds
  (random, PYTHONHASHSEED; numpy if present). Tier 3 (XL):
  record-side interception of `time`/`random`/`os.urandom` returns,
  replayed on demand — deterministic re-execution for pure-ish
  programs.
- **Why:** a trace answers "what happened"; the capsule answers "can
  anyone make it happen again" — the difference between a report and
  a specimen. Tier 1 alone upgrades every GitHub issue this tool
  ever produces.
- **How:** Tier 1 is bookkeeping in the runner + a replayer panel.
  Tier 3 is honest rr-lite: wrap the nondeterminism sources at
  bootstrap, record return streams, label the trace REPLAYABLE with
  its coverage limits (no sockets, no threads-timing).
- **Effort:** S → XL by tier.
- **Prior art:** rr (Mozilla); Pernosco; Jupyter's reproducibility
  crisis literature — Tier 1 is what every scientific workflow
  wishes it had by default.

### 67. Rosetta bridges (spec + import/export)
- **What:** publish the event schema as a versioned JSON-Schema spec
  (the layer-2 contract, made public); importers: py-spy speedscope
  and VizTracer JSON drawn as heat/lanes on our map/replayer;
  exporters: OpenTelemetry spans from fn traces (Perfetto export
  already exists).
- **Why:** the Phase-5 promise. A documented schema is what lets
  "maybe other python experts work on it" actually happen — tools
  compose through formats, not through code.
- **How:** spec + validators in checks.py; each bridge is an isolated
  translator module with honesty notes (sampled data drawn as
  sampled — dashed heat for py-spy, since samples ≠ counts).
- **Effort:** M per bridge; S for the spec.
- **Prior art:** Chrome Trace Event format's ecosystem; speedscope;
  OpenTelemetry.

---

## Section 7 — The replayer as a medium

### 68. Deep links — a URL that opens a moment
- **What:** the full viewer state (event index, file tab, selected
  variable, view choices, overlay) serialized into the URL fragment;
  paste `trace_x.html#ev=8412&var=dist&view=graph` into an issue and
  the reader lands exactly there.
- **Why:** debugging is collaborative; today you paste screenshots.
  A trace file + a fragment is a *pointer into an execution* — the
  cheapest feature on this list with the largest social payoff.
- **How:** location.hash read on load / written on navigation
  (debounced); zero schema changes.
- **Effort:** S.
- **Prior art:** every good web app; Perfetto's permalink (theirs
  needs a server — ours is a file).

### 69. Annotations — notes pinned to events
- **What:** press `N` at any event: attach a note ("HERE total goes
  negative — why?"); notes listed in a side panel, exported/imported
  as a JSON sidecar so they travel with the trace file.
- **Why:** a long investigation IS a set of annotated moments; today
  they live in a text file with event numbers. Make the trace the
  notebook.
- **How:** localStorage (the bookmarks pattern) + sidecar
  export/import; annotations render as pins on the scrubber.
- **Effort:** M.
- **Prior art:** PDF annotations; Pernosco's shared notes.

### 70. Guided tours — executable lessons
- **What:** an ordered sequence of annotated stops (#69 + #68) saved
  as a tour: the replayer gains "next stop" navigation and a narration
  box — a recorded walkthrough someone else can replay.
- **Why:** the project's teaching soul, weaponized: "watch quicksort
  partition go wrong on duplicate keys, stop 4 of 7". Onboarding a
  codebase = handing someone three tours instead of a wiki.
- **How:** tour = JSON list of (event, note, view-state); author mode
  is just "save current state as stop". Ships with the teaching
  fleet's examples as built-in tours.
- **Effort:** M.
- **Prior art:** Jupyter notebooks' narrative computing; museum audio
  guides; CodeTour (VS Code) — which tours *source*, not *execution*.

### 71. The query bar (omniscient search)
- **What:** search over events, not text: `x == 42`,
  `type:exception KeyError`, `fn:push after:5000`, `changed:total` —
  results as a jump list + scrubber pins (the bookmarks machinery).
- **Why:** a trace is a database currently navigable only by
  scrubbing. "Find the three moments total exceeded 100" should be a
  query, not an hour.
- **How:** in-memory scan over decoded events with a tiny predicate
  grammar (no eval of user Python in the viewer — parse a fixed
  grammar honestly); progress + cost shown on big traces (#63 makes
  it windowed).
- **Effort:** M.
- **Prior art:** Bil Lewis's Omniscient Debugger (2003); Pernosco's
  queries — the feature that makes recorded execution *better* than
  live debugging, not just equal.

### 72. Dual synced replayers
- **What:** open two traces side by side with linked cursors —
  aligned by the #26 divergence map when available, by manual anchor
  pairs otherwise; divergence point marked in both scrubbers.
- **Why:** before/after a fix, pass vs fail, brute vs fast (#33):
  humans diff by eye extremely well when the two films are locked in
  step.
- **How:** two iframes + postMessage cursor protocol + an alignment
  table; degrade to proportional sync with an honest "unaligned"
  badge.
- **Effort:** M (L with full alignment — build after #26).
- **Prior art:** diff tools' two-pane discipline applied to
  executions.

### 73. Movie export
- **What:** select a panel (the bars view, the graph+overlay, the
  grid) and an event range → export a WebM (canvas captureStream +
  MediaRecorder, browser-native) or animated GIF of it playing.
- **Why:** the README, the bug report, the lecture slide: "watch the
  heap invariant break" as a 5-second loop is worth three
  paragraphs. Also the publish-day demo artifact, automated.
- **How:** replay the range off-screen at fixed fps into a canvas
  recorder; no external encoders; size/length caps announced.
- **Effort:** M.
- **Prior art:** asciinema for terminals; nothing equivalent for
  execution state.

### 74. Records table view
- **What:** a `table` view for list-of-dicts / list-of-tuples with
  uniform keys: sortable columns, the changed cell highlighted, +K
  windowing rules inherited.
- **Why:** rows-of-records is THE shape of real program data
  (queries, CSV rows, API responses) and currently renders as nested
  cells; a table is its native habitat.
- **How:** renderer-only; reuses diff flags; column sort is
  display-order only (honesty: data order unchanged, sort indicator
  shown).
- **Effort:** S.
- **Prior art:** every dataframe viewer; ours diffs per-cell across
  time.

### 75. Ghost branch — the road not taken
- **What:** at any verdict event, faintly highlight the suite that
  was NOT entered (the else that didn't run, the loop body skipped on
  0 iterations) for exactly one step.
- **Why:** makes absence visible at the moment of decision — the
  gentle sibling of #39, and for a learner the moment branching
  *clicks*.
- **How:** ast extents per branch arm are already computed for
  dataflow; renderer tints the untaken range. Off by default,
  toggleable.
- **Effort:** S.
- **Prior art:** none we know of — cheap and genuinely novel.

### 76. Sonification — hear the trace
- **What:** map events to sound while playing: pitch by call depth,
  timbre by file, a tick per loop iteration, dissonance on
  exceptions; a run becomes a rhythm you learn.
- **Why:** ears detect pattern breaks in streams better than eyes
  (that's why Geiger counters click). A 100k-event run at turbo speed
  is noise to the eye and a *texture* to the ear — the anomaly is the
  hiccup. Also a real accessibility door for blind programmers.
- **How:** WebAudio oscillators driven by the event stream;
  renderer-only; off by default.
- **Effort:** M.
- **Prior art:** auditory display research (ICAD); program
  auralization literature of the 90s — never shipped in a mainstream
  tool.

### 77. The explain bundle
- **What:** export a compact, human/LLM-readable text slice of the
  trace: N events around the cursor with source lines, variable
  states, verdicts and provenance, formatted for pasting into an
  issue, a code review — or an AI assistant.
- **Why:** the trace knows the ground truth of what happened;
  everyone else (humans and models alike) reasons better when handed
  that truth in text. pyreplay stays offline — the bundle is a file;
  where it goes is the user's business.
- **How:** a serializer over existing data + a "copy bundle" button;
  size-capped, self-describing header (script, capsule info if #66
  exists).
- **Effort:** S.
- **Prior art:** crash reporters' minidumps, made narrative.

---

## Section 8 — Research-grade (flagged honestly as such)

### 78. Symbolic branch exploration
- **What:** for a chosen never-taken branch: attempt to solve the
  path condition ("what stdin reaches line 84?") via symbolic
  execution of the guarding expressions.
- **Why:** #39 answers why a line didn't run; this answers what WOULD
  make it run — test-input generation for the untested path.
- **How:** realistically, an optional bridge to CrossHair (Z3-based,
  exists today) fed with our dataflow; a from-scratch solver is a
  thesis, not a feature. Degrade to "not installed".
- **Effort:** XL (bridge: L).
- **Prior art:** CrossHair; KLEE; concolic testing (DART/SAGE).

### 79. Full deterministic record/replay
- **What:** #66 Tier 3 completed into rr-class fidelity: every
  nondeterminism source intercepted so any recorded run re-executes
  identically — enabling reverse-execution debugging on top of our
  replayer.
- **Why:** the end-state of the whole field: the recording IS the
  bug, forever. Kept here as the north star and marked honestly:
  CPython offers no cheap path to syscall-level capture; the
  pure-Python subset (#66 Tier 3) is the realistic 80%.
- **Effort:** XL.
- **Prior art:** rr (Mozilla), Pernosco, UndoDB — all C/C++-world;
  Python's equivalent does not exist, which is exactly why it's
  listed.

---

## Section 9 — The second pass (bug-taxonomy review, 2026-07-20)

A 10-category bug taxonomy and 20-tool observability inventory were
checked against this list; most of both were already covered
(FEATURES.md or #25–79), but seven real gaps surfaced. Each entry
notes the section it thematically belongs to.

### 80. Console & logging lane (stdout/stderr/logging as events)
*(belongs with Section 3 — instruments)*
- **What:** capture everything the program prints or logs as
  first-class events tied to the emitting frame and line: a console
  panel in the replayer synced to the timeline — click a log line to
  jump to the exact moment it was written, and vice versa; log levels
  colored; with #60, output attributed per test.
- **Why:** print-debugging is the most-used debugger on Earth and
  logs are the one signal every codebase already emits — yet they are
  divorced from state. Tying each line to its execution moment turns
  the terminal dump into an index into the trace ("ERROR at line
  40,312 of the log" becomes "event 8,214, with all variables live").
- **How:** the runner tees `sys.stdout`/`sys.stderr` (output still
  reaches the real terminal) and auto-attaches a `logging.Handler`;
  each write records (stream, text, frame). Schema: LOG events.
  Honesty: writes made by C extensions below the Python layer bypass
  the tee — announced.
- **Effort:** M.
- **Prior art:** pytest's capsys; every log viewer ever — none of
  them can jump from a log line to the program state that produced
  it.

### 81. Dynamic edges — what the run saw that the parse couldn't
*(belongs with Section 5 — the map)*
- **What:** overlay trace-observed relations on the static map:
  caller→callee module pairs from fn traces drawn as distinct "dark
  edges" wherever no static route exists (dispatch tables, callbacks,
  `bind()`-style frameworks, plugin registries); runtime-observed
  imports reconciled against static import edges; and
  `importlib.import_module`/`__import__` call sites flagged
  statically as "dynamic import — target unknown until traced".
- **Why:** the map's documented blind spot is dynamic binding — an
  event-driven app can look disconnected statically while being
  densely wired at runtime. One overlay makes the map stop
  under-reporting exactly where under-reporting is most dangerous,
  and the honesty note ("N calls not statically resolvable") becomes
  a picture instead of a number.
- **How:** fn events already carry caller/callee files — aggregate
  pairs, diff against the static edge set, render with counts in a
  distinct style; ⚙ import events reconcile the import half. Honesty:
  labeled "observed in N traced runs" — the absence of a dark edge
  is never evidence of absence.
- **Effort:** M (both halves of the data already exist; the work is
  reconciliation + rendering).
- **Prior art:** the static-vs-dynamic gap every AST tool ships
  with; pyreplay is unusually placed to close it because it owns both
  layers.

### 82. Boundary schemas — observed interfaces at the borders
*(belongs with Section 2/3 — causality & instruments)*
- **What:** at function/module boundaries, record the *structural
  schema* of arguments and returns — keys, types, nesting, lengths,
  not values: "returns dict{id:int, items:list[dict{sku,qty}]} —
  14 calls, stable"; show it as the def's observed interface on map
  rows and in the replayer; diff schemas across runs (#25) and
  across traces ("returned a list last week, a dict today");
  optionally check against a declared expectation.
- **Why:** the data-assumption bug — the wrong-shape payload, the
  guessed dictionary key, the API that returns a dict when the code
  expects a list — crashes far downstream of its cause. A schema
  checkpoint at the border catches it at the door, *before* anyone
  reaches for line-level tracing. In the LLM era this may be the
  single most common bug class.
- **How:** the encoder already fingerprints structure; add a
  shape-abstraction pass (values → types) aggregated per call site
  at fn granularity; declared-schema checks reuse the #35 evaluator.
- **Effort:** M–L.
- **Prior art:** consumer-driven contracts (Pact), pydantic — but
  observed rather than declared; MonkeyType's cousin for shapes.

### 83. NVTX bridge — Python meaning on the GPU timeline
*(belongs with Section 6 — interchange; recovers Phase 5 of the
original brief)*
- **What:** `--export-nvtx` — at fn granularity, emit NVTX ranges
  around traced calls (via the optional `nvtx` package or
  `torch.cuda.nvtx` when present) so Nsight Systems timelines show
  your Python function names wrapped around the CUDA kernels they
  caused.
- **Why:** hardware timelines are dense and semantically empty; the
  bridge maps a millisecond GPU stall straight back to the Python
  call that owned it. This was Phase 5 in the project brief and had
  fallen off the horizon — the taxonomy review caught the omission.
- **How:** a thin push/pop-range emitter in the fn hot path behind
  the flag; degrades gracefully without the package. Honesty: the
  annotation itself costs microseconds — don't label micro-functions
  (the observer-effect rule), and say so in the docs.
- **Effort:** M.
- **Prior art:** NVTX / Nsight Systems; PyTorch profiler's
  `emit_nvtx`.

### 84. Shadowing & collision audit
*(belongs with Section 5 — the map, plus a replayer badge)*
- **What:** detect name masking at three levels: a local shadowing a
  global/enclosing name or a builtin (`sum`, `list`, `id`…); a
  module-level assignment shadowing an import; and a project file
  shadowing a stdlib module name (`email.py`, `random.py` — the
  classic import horror). Map note per file, replayer badge on
  shadowing variables.
- **Why:** scope-collision bugs read correctly and *resolve*
  wrongly — the code looks fine because it is fine, somewhere else.
  The stdlib-filename case can break a codebase at import time in
  ways that look supernatural.
- **How:** static tier is pure ast symbol tables + the builtins list
  + a stdlib-names list checked against filenames (the mapper already
  walks everything needed); the tracer confirms at runtime when a
  frame actually holds both names. Zero run-time cost for the static
  tier.
- **Effort:** S.
- **Prior art:** pylint's redefined-builtin / redefined-outer-name
  warnings — per-file lint text; ours lands on the map and on the
  live variable row.

### 85. Float-hygiene probes
*(belongs with Section 1/3 — the lab & instruments; pairs with #41)*
- **What:** (a) flag float equality as it executes — the verdict
  machinery already sees the compare and the operand types; flag
  `== `/`!=` between floats statically too; (b) a harness probe:
  re-run a chosen reduction under #25 with permuted operand order
  and a `math.fsum`/`decimal` shadow, reporting the spread ("your
  sum varies by 3e-9 across orderings — the accumulation is
  ill-conditioned").
- **Why:** precision errors accumulate silently and bite numerical
  code hardest; float `==` is the classic silent trap. pyreplay
  cannot fix floating point, but it can measure the wobble and show
  the door it came in through.
- **How:** (a) rides existing verdict + type data (S); (b) a
  `--probe-reduction` hook over watch() + the N-run harness (M).
  Honesty: a spread report is evidence of sensitivity, not proof of
  error.
- **Effort:** S–M.
- **Prior art:** Kahan summation lore; Herbie; FpDebug — none of it
  reachable from a working Python session today.

### 86. Event-loop starvation detector
*(belongs with Section 4 — concurrency)*
- **What:** in asyncio traces, badge any slice that held the event
  loop beyond a threshold without yielding — "task worker-A blocked
  the loop 840 ms inside parse()" — with the starved tasks visible
  waiting in their lanes; banner counts starvation incidents.
- **Why:** a blocked loop is the "program/UI frozen" bug class and
  is invisible in source; at fn granularity every slice duration is
  already recorded — the detector is one comparison away.
- **How:** threshold check over existing slice durations (fn mode),
  default borrowed from asyncio debug mode's 100 ms
  slow-callback warning; configurable.
- **Effort:** S.
- **Prior art:** `PYTHONASYNCIODEBUG`'s slow_callback_duration — a
  logged line nobody sees; ours lands on the lane where it
  happened.

## Section 10 — The verification pass (2026-07-31)

A posterior-verification canon (the full gauntlet: typing gates →
static analysis → property-based testing → mutation testing → formal
methods → production gates) was checked against this list. Most rungs
were already covered by the reliability lab and its neighbors
(#25–#36, #66, #78) — pyreplay's role there is the instrument *under*
the gauntlet: when a gate goes red, it shows why; before properties
exist, it drafts them from observed behavior. Two real gaps surfaced,
both places where recording the execution adds something the
standalone gate lacks.

### 87. Mutation-survivor forensics
*(belongs with Section 1 — the reliability lab)*
- **What:** mutation testing's chore is the *surviving* mutant — a
  planted bug no test killed. Bridge to mutmut/cosmic-ray (used
  as-is): for each survivor, run the nearest test twice at fn/line
  granularity — original code vs mutant — align the two traces with
  the divergence finder (#26), and report the first behavioral
  divergence plus the values that differed with no assertion
  consuming them. That's not just "this mutant survived" — it's *the
  assertion you forgot to write*, located.
- **Why:** in a no-reading regime the mutation score is your
  eyesight (the only direct measurement of the test suite itself),
  and survivors are exactly where the suite is blind. Today killing
  a survivor means reading the diff and guessing; a traced
  divergence turns it into a mechanical fix.
- **How:** thin reader over the mutation tool's results cache →
  re-run the covering test under the tracer for both versions
  (#25's runner) → #26 alignment → report. Honesty note (the
  equivalent-mutant problem): some mutants change nothing
  observable; when the traces never diverge, say exactly that —
  "no behavioral divergence found; possibly an equivalent mutant" —
  never invent a difference.
- **Effort:** M (needs #25 + #26; the bridge itself is thin).
- **Prior art:** mutmut, cosmic-ray; the equivalent-mutant
  literature. No tool today explains *why* a survivor survived.

### 88. Metamorphic relations harness
*(belongs with Section 1 — the reliability lab; sibling of #33)*
- **What:** differential testing (#33) needs a second
  implementation; metamorphic testing needs only a *symmetry*: the
  true output may be unknown, but `f(perm(x)) == f(x)`,
  `dist(a,b) == dist(b,a)`, `f(2x) == 2·f(x)` must still hold.
  `--relation "f(sorted(x)) == f(x)"`-style declarations run under
  the N-run harness (#25) over generated inputs (#29); a violation
  keeps the input, shrinks it (#28), and traces both sides of the
  broken symmetry.
- **Why:** the oracle problem is the hard wall of testing numerical
  and scientific code — you often *can't* say what the right answer
  is, but you always know its invariances. This is the cheapest
  verification instrument that works with no oracle at all, and a
  natural fit for the physicist's instinct (conservation laws as
  tests).
- **How:** a relation is a pair (input transform, output relation)
  evaluated by the existing `--start-when`/`--invariant` expression
  machinery; violations become first-class events with the usual
  scrubber markers; #26 diffs the two runs of a broken relation.
- **Effort:** S–M on top of #25/#29.
- **Prior art:** metamorphic testing (T.Y. Chen et al., 1998) —
  standard in compiler and search-engine testing, almost never
  available to everyday Python.

## Deliberately still rejected

- **Viewer-side eval / edit-and-continue** — replay must never
  pretend to compute; recording-side #34/#35 cover the need honestly.
- **3D visualization** — aggregation and filtering, not rendering
  heroics (unchanged since the brief).
- **Rebuilding samplers/profilers** — py-spy and friends exist; we
  bridge (#67), not clone.
- **Auto-running composed commands from the map** — the ⌖ copy box is
  the interface on purpose: the funnel teaches; a button would
  obscure.

## If you only build five

1. **#25 + #26** — the reliability lab and the divergence finder: the
   remembered idea, and the tool it makes possible.
2. **#60** — per-test chapters (it unlocks #27's ranked suspects for
   free).
3. **#63** — chunked keyframes: every ambitious feature above hits
   the 2M wall without it.
4. **#68** — deep links: one day of work, changes how traces are
   shared forever.
5. **#42** — the oscilloscope: the demo that shows people what kind
   of tool this is.

## Good first features (S-effort, self-contained)

#27 (after 25) · #32 · #34 · #35 · #41 · #47-static · #58 · #61 ·
#66-Tier1 · #68 · #74 · #75 · #77 · #84 · #86.

---

## Good first contributions (tasks, not numbered features)

Not everything useful is a numbered feature. These are self-contained
and a good way in:

- A new `example_*.py` exercising an edge case (unusual containers,
  recursion, decorators…) plus a matching check in `checks.py`.
- Hardening the element-level diffing in `encode()` / `windowed_value()`
  in `tracer.py` on data shapes it doesn't handle gracefully yet.
- Viewer polish: accessibility, keyboard shortcuts, mobile layout.
- More recipes in `TUTORIAL.md`, or documentation anywhere.
- A static-map backend for a second language (see below).

## Support another language

The whole architecture exists so pyreplay can outgrow Python, and this is
the highest-leverage contribution of all. Two decoupled seams:

1. **A static map for another language** *(medium effort, self-contained).*
   `mapper.py`'s `ModuleScan` walks Python's `ast` to collect imports,
   defs and calls. Swap it for a parser of your target language (e.g.
   [tree-sitter](https://tree-sitter.github.io/)) that emits the same
   `modules` / `imports` / `defs` payload, and the existing map viewer —
   package folding, cycle detection, fan-in metrics — all just work.
2. **A tracer for another language** *(bigger, fully decoupled).* Write a
   recorder in/for that language that produces the event-log JSON below.
   The existing `replayer_template.html` plays it back with no changes.
   Start with `fn` granularity (calls/returns only) — the smallest useful
   trace.

You never reimplement the viewer; you just emit the JSON.

## The event log — the language-neutral contract

The seam that lets pyreplay grow beyond Python. A trace payload:

```jsonc
{
  "script": "your_script.py",
  "granularity": "line",          // "line" | "fn"
  "sources": { "your_script.py": "<full source text>" },
  "events": [ /* see below */ ],
  "truncated": false,
  "error": null
}
```

A minimal **event** the replayer can play back:

```jsonc
{
  "e": "line",           // "call" | "line" | "return" | "exc"
  "f": "your_script.py", // file (a key into "sources")
  "l": 12,               // line number
  "fn": "main",          // enclosing function name
  "ch": {                // variables that CHANGED at this event
    "total": { "t": "p", "c": "int", "v": "42" }
  }
}
```

Values in `ch` (and `ret`) are **structured encodings**, not raw reprs,
so the viewer can render them semantically:

```jsonc
{ "t": "p",    "c": "int",  "v": "42" }              // primitive
{ "t": "s",    "c": "str",  "v": "hi" }              // string
{ "t": "list", "c": "list", "n": 3,                  // n = REAL length
  "v": [ {"t":"p","c":"int","v":"1"}, … ] }          // v = encoded head
{ "t": "obj",  "c": "Point", "n": 2,                 // instance: attrs as pairs
  "v": [ ["x", {…}], ["y", {…}] ] }
```

Richer, all optional: `ret` (return value), `x` (`{t,m,soft}`
exception), `g` (generator/coroutine lifecycle), `t`/`tk` (thread /
asyncio task lane), `ts` (µs delta, `fn` granularity only), `mut`/`ali`
(mutation vs. rebind and aliasing), `mro`, `cl`, `da`, `cond`. The
authoritative source is `encode()` and `Tracer._record` in `tracer.py`;
the viewer side is `renderValue()` in `replayer_template.html`. **To add
a language you emit this — you don't reimplement any of it.**

Thanks for helping.
