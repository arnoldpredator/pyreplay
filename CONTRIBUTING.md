# pyreplay — the roadmap & contribution guide

Everything already built is in FEATURES.md (the 62-feature catalog).
This file is the other half — **every feature we know we want and have
not built yet** — and how to contribute one. It's written so a stranger
can pick an item and implement it. Features are numbered **#63 onward**, continuing the shipped catalog
in FEATURES.md. Fifteen roadmap items have shipped since the list was
written (63, 64, 65, 70, 77, 79, 80, 98, 101 v1, 103, 104 Tier 1,
106, 109, 118, 120 v1) — their rows below are struck through;
**32 remain unbuilt** (plus the stated remainders of 66/74/75/85/88/89/101/104/119/120/126/127/128/132/134).

## Start here — how to contribute

New here and want to help? Three steps:

1. **Pick something.** The **Index** below lists features #63–#135; the
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
  attach to anything, never fake a number. → #85, #86, #102, #103, #93.
- **The Torvalds lens — bisect it, diff it, no magic.** Every bug is
  a difference between a world that works and one that doesn't; build
  the tools that find the first divergence. → #64, #70, #71, #95.
- **The Stroustrup lens — types, invariants, resources.** What holds
  always? What type flows here? Who owns this resource and who closed
  it? → #73, #74, #82, #84.

**Effort:** S = a focused day · M = several days · L = a week+, schema
touched · XL = multi-week / research-grade. **Payoff:** ★ nice ·
★★ strong · ★★★ changes what the tool is.

## Index

| # | Feature | Effort | Payoff |
|---|---------|--------|--------|
| 63 | ~~Run it N times; count outcomes, catch flakes~~ **shipped** | — | ★★★ |
| 64 | ~~First event where two runs diverge~~ **shipped (v1)** | — | ★★★ |
| 65 | ~~Color lines by failing-run correlation (SBFL)~~ **shipped** | — | ★★★ |
| 66 | ~~Input shrinking: ddmin over stdin/argv~~ **shipped (argv model remains)** | M | ★★ |
| 67 | Random-input entry with seed capture | M | ★★ |
| 68 | ~~Perturb thread/task schedules to flush races~~ **shipped** | — | ★★★ |
| 69 | Inject exceptions/latency on purpose | L | ★★ |
| 70 | ~~git bisect driven by a trace predicate~~ **shipped** | — | ★★★ |
| 71 | Compare implementations on the same inputs | M | ★★ |
| 72 | ~~Record extra expressions each line (--watch)~~ **shipped** | — | ★★ |
| 73 | ~~Contracts checked during the run (--invariant)~~ **shipped** | — | ★★ |
| 74 | ~~Mine the invariants the runs never broke~~ **shipped (map rows remain)** | L | ★★★ |
| 75 | ~~Full backward slice of a value~~ **shipped (v1; caller-arg crossing remains)** | — | ★★★ |
| 76 | Forward taint from an input | L | ★★ |
| 77 | ~~"Why didn't this line run?"~~ **shipped** | — | ★★★ |
| 78 | ~~Nontermination detector (state recurrence)~~ **shipped** | M | ★★ |
| 79 | ~~Catch the first NaN/Inf at birth~~ **shipped** | — | ★★★ |
| 80 | ~~Strip-charts + phase portraits of variables~~ **shipped** | — | ★★★ |
| 81 | Object-reference graph at an event | L | ★★ |
| 82 | Per-variable type histograms; None alarms | M | ★★ |
| 83 | Array shape/dtype timeline | M | ★★★ |
| 84 | I/O lane via audit hooks; resource-leak pairing | M | ★★ |
| 85 | ~~Code anatomy: AST + bytecode panel~~ **static tiers shipped; Tier 2 (instruction events) remains** | S–XL | ★★ |
| 86 | Ternary/short-circuit verdicts via BRANCH events | L | ★★ |
| 87 | Memory heat on the map (tracemalloc) | M | ★★ |
| 88 | ~~Who-woke-whom arrows across tasks/threads~~ **shipped (v1; queue correlation remains)** | — | ★★★ |
| 89 | ~~Critical path through a concurrent run~~ **shipped (v1; multi-core DAG remains)** | — | ★★ |
| 90 | Lock-wait attribution | L | ★★ |
| 91 | Multiprocessing children traced into lanes | XL | ★★★ |
| 92 | Live streaming replayer (--serve) | L | ★★ |
| 93 | Attach to a running process (PEP 768) | M | ★★★ |
| 94 | ~~Project-wide static call graph~~ **shipped (drawn edges remain)** | L | ★★★ |
| 95 | ~~Git churn × complexity overlay~~ **shipped** | — | ★★★ |
| 96 | Declared layering rules; violations in red | S | ★★ |
| 97 | ~~Dead-code evidence (static x dynamic join)~~ **shipped** | M | ★★ |
| 98 | ~~Per-test chapters in suite traces~~ **shipped** | — | ★★★ |
| 99 | ~~Startup import-cost view~~ **shipped** | — | ★★ |
| 100 | ~~API-surface honesty (encapsulation leaks)~~ **shipped** | M | ★★ |
| 101 | ~~Chunked trace + keyframes~~ **shipped (v1; windowed replayer remains)** | — | ★★★ |
| 102 | monitoring-backed cheaper LINE tracing | M | ★★ |
| 103 | ~~Black-box flight recorder (ring buffer)~~ **shipped** | — | ★★★ |
| 104 | ~~Reproducibility capsule~~ **Tier 1 shipped; seeds/replay remain** | M–XL | ★★★ |
| 105 | Schema spec + import/export bridges | M | ★★ |
| 106 | ~~Deep links: a URL that opens a moment~~ **shipped** | — | ★★★ |
| 107 | Notes pinned to events; exportable | M | ★★ |
| 108 | Recorded walkthroughs (executable lessons) | M | ★★ |
| 109 | ~~Query bar over all events~~ **shipped** | — | ★★★ |
| 110 | Two traces side by side, cursors synced | M | ★★ |
| 111 | Export a panel as video/GIF | M | ★★ |
| 112 | Sortable table view for list-of-dicts | S | ★★ |
| 113 | Ghost-highlight the untaken branch | S | ★★ |
| 114 | Hear the trace (sonification) | M | ★ |
| 115 | Text bundle of a trace slice | S | ★★ |
| 116 | Symbolic "what input reaches this line" | XL | ★ |
| 117 | Full deterministic record/replay | XL | ★★ |
| 118 | ~~Console & logging lane synced to the trace~~ **shipped** | — | ★★★ |
| 119 | ~~Dynamic edges: runtime relations the parse can't see~~ **shipped (v1; import reconciliation remains)** | — | ★★★ |
| 120 | ~~Boundary schemas~~ **shipped (v1; cross-run diff + map rows remain)** | M | ★★★ |
| 121 | NVTX bridge: Python names on the GPU timeline | M | ★★ |
| 122 | Shadowing & collision audit | S | ★★ |
| 123 | Float-hygiene probes | S–M | ★★ |
| 124 | Event-loop starvation detector | S | ★★ |
| 125 | ~~Mutation-survivor forensics (mutmut bridge)~~ **shipped** | M | ★★★ |
| 126 | ~~Metamorphic relations harness~~ **shipped (shrinking awaits #66)** | S–M | ★★ |
| 127 | ~~Scaling bench: measured growth exponents~~ **shipped (minimal gen protocol; full #67 remains)** | M | ★★★ |
| 128 | ~~Prediction gate: commit a claim, get scored~~ **shipped (tour stops await #108)** | M | ★★★ |
| 129 | ~~Graph lens on the map (centrality, communities)~~ **shipped** | M | ★★ |
| 130 | ~~Trace compressibility (regularity strip)~~ **shipped** | S | ★ |
| 131 | ~~CFG view: the code as a graph, the run as a path~~ **shipped** | M | ★★★ |
| 132 | ~~Observed state machine (one declared variable)~~ **shipped (row-click binding remains)** | M | ★★ |
| 133 | ~~Recursion tree view~~ **shipped** | S | ★★ |
| 134 | ~~Subproblem DAG (memo dependency view)~~ **shipped (cross-frame edges remain with #75)** | M | ★★ |
| 135 | ~~Motion layer (tweened transitions, honest)~~ **shipped** | M | ★★ |
| 136 | ~~Sequence diagram — lifelines from the log~~ **shipped** | M | ★★★ |
| 137 | ~~Observed decision table (guard truth summary)~~ **shipped** | S | ★★ |
| 138 | Classic grammar skins: flowchart / structogram | S–M | ★ |

---

## Section 1 — The reliability lab (statistics over many runs)

The remembered idea, made a subsystem. One run is an anecdote; N runs
are an experiment. Everything here treats program behavior as a
distribution to be measured — the physicist's instinct applied to
software.

### 63. The N-run harness
**Shipped 2026-08-01** — now catalog entry #63 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 64. The divergence finder (recovers "trace-vs-trace diffing")
**Shipped 2026-08-01 (v1: identical-prefix alignment)** — now catalog entry #64 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 65. Spectrum-based fault localization (SBFL)
**Shipped 2026-08-01** — now catalog entry #65 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 66. Automatic input shrinking (delta debugging)
**Shipped 2026-08-01** — now catalog entry #66 in [FEATURES.md](FEATURES.md): `--shrink` + `--shrink-model lines|tokens|bytes` + `--shrink-cap` — ddmin with the --check oracle or the same-crash-type oracle, minimal input written + auto-traced at line level + rerun command composed. What remains: shrinking argv (stdin only today) and the #126 hookup (shrink a violated relation's input automatically).
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

### 67. Property/fuzz entry
- **What:** `--fuzz GEN.py` — run a user-supplied generator function
  that yields random inputs (seeded, seed recorded per run) through
  the N-run harness; on first failure, keep the seed, re-run traced,
  and hand the input to #66 to shrink.
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

### 68. Schedule fuzzing (concurrency chaos)
**Shipped 2026-08-01** — now catalog entry #68 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record (and `example_race.py` to fire it at).
- **What:** `--chaos-schedule SEED` — perturb interleavings on
  purpose: randomized micro-delays injected from the trace callback at
  line/call boundaries, `sys.setswitchinterval` jitter for threads, a
  shuffling event-loop wrapper for asyncio ready-queues; combined with
  #63 to measure "fails 7/100 under perturbation, 0/100 without".
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

### 69. Fault injection (chaos engineering for one process)
- **What:** `--inject "shop.pay:raises=TimeoutError:on_call=3"` —
  force a chosen call site to raise / return a sentinel / stall, then
  watch (with the existing exception machinery) how the failure
  propagates and what catches it.
- **Why:** error-handling paths are the least-executed, least-tested
  code in any codebase; injection is the only way to *see* them run.
  The propagation-chain view (#70 in FEATURES) was built for exactly
  this moment.
- **How:** an import-time wrapper installed by the tracer around the
  named callable (we own the process bootstrap); every injection is
  recorded as a first-class INJECTED event so the trace never lies
  about what really happened.
- **Effort:** L.
- **Prior art:** Netflix chaos engineering, aerospace HALT testing —
  break it on the bench, not in the air.

### 70. Behavioral bisect (git × tracer)
**Shipped 2026-08-01** — now catalog entry #70 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 71. Differential testing against a reference implementation
- **What:** `--oracle brute.py fast.py --fuzz GEN.py` — run two
  implementations on the same inputs; on output mismatch, keep the
  input, trace **both**, and open the divergence finder (#64) on the
  pair.
- **Why:** the repo already contains
  `strategy_1_brute_force.py … strategy_4_segment_tree.py` — the
  AtCoder workflow IS differential testing done by hand. Automate the
  loop: the brute force is the specification.
- **How:** harness compares stdout (configurable normalizer); wire to
  #66 to shrink the disagreement input. No schema changes.
- **Effort:** M.
- **Prior art:** McKeeman, "Differential testing for software" (1998);
  Csmith; competitive programmers' stress-test scripts everywhere.

---

## Section 2 — Deeper causality (from "what changed" to "why")

### 72. Watch expressions at record time (reframes a rejected idea)
**Shipped 2026-08-01** — now catalog entry #72 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.
- **What:** `--watch "len(queue)" --watch "cart.total()"` — arbitrary
  expressions evaluated **during the run** at each line event of
  chosen frames, recorded as synthetic variables with full life
  navigation, plots (#80), and provenance participation.
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

### 73. Continuous invariants (`--invariant`)
**Shipped 2026-08-01** — now catalog entry #73 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.
- **What:** `--invariant "balance >= 0" --invariant "i <= j"` —
  expressions that must hold; every violation is recorded as a soft
  VIOLATION event (amber, scrubber markers, count in the banner) while
  the run continues.
- **Why:** assertions you don't have to edit into the code, checked
  everywhere, with the trace showing state at each violation. The
  contract mindset without touching the target.
- **How:** same evaluator as #72; a violation stores the expression,
  values of its names, and links into provenance ("which assignment
  broke it"). Also honest about scope: checked only where the frame
  defines the names.
- **Effort:** S.
- **Prior art:** Design by Contract (Meyer/Eiffel), C's assert —
  Stroustrup lens distilled.

### 74. Invariant mining (Daikon-lite)
**Shipped 2026-08-01** — now catalog entry #74 in [FEATURES.md](FEATURES.md): template library (constants, types, signs, len, sorted-at-return, per-call monotonicity, numeric-arg order pairs) killed on first counterexample, survivors ranked by support; three surfaces — ⚗ on every line trace's boundary events (self-mined at write time), `--runs N --mine` aggregation into the runs report, standalone `--mine a.html b.html` with JSON sidecar. Machinery objects never mined; windowed containers never judged; "an observation, never a proof" verbatim everywhere. What remains: mined facts on MAP function rows.
- **What:** observe many runs (#63) and **propose** the invariants
  that never broke: `x > 0`, `i < len(a)`, `a is sorted at return`,
  `type(x) constant`, `total is monotonically nondecreasing` — per
  function entry/exit and per loop.
- **Why:** mined invariants are executable documentation ("what this
  code actually guarantees") and bug detectors (a run that breaks a
  99%-invariant is your suspect — feed it to #64).
- **How:** a template library checked against the recorded
  fingerprints offline (no run-time cost): candidate set instantiated
  per variable/pair, killed on first counterexample, survivors ranked
  by support. Displayed on function rows in map and replayer. Honesty:
  "held in N observed runs" is an observation, never a proof.
- **Effort:** L (noise control is the craft: too many trivial
  invariants = spam).
- **Prior art:** Daikon (Michael Ernst et al.) — the canonical dynamic
  invariant detector; almost never applied to everyday Python.

### 75. Full backward slice (transitive provenance)
**v1 shipped 2026-08-01** — now catalog entry #75 in [FEATURES.md](FEATURES.md): ✂ slice from any provenance row — closure walk with return-crossing, green scrubber pins, ←/→ walks the slice, frontier stops listed with reasons. What remains: caller-argument crossing, container-element flow.
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

### 76. Forward taint ("descendants of this input")
- **What:** the same walk, forward: mark a value (an stdin field, a
  config entry, a function argument) and highlight every variable and
  branch verdict it influenced downstream.
- **Why:** "if I change this config, what is affected?" and "which
  outputs depend on this input?" — impact analysis and data lineage in
  one gesture; the security cousin is classic taint analysis.
- **How:** transpose the #75 graph; tainted verdicts (a branch whose
  condition read a tainted value) mark whole control regions as
  control-tainted, displayed distinctly (data vs control influence —
  the honest split).
- **Effort:** L (shares 80% of its machinery with #75 — build
  together).
- **Prior art:** taint tracking (Perl's taint mode, TaintDroid);
  data-lineage tooling in databases.

### 77. Whyline queries — "why didn't this line run?"
**Shipped 2026-08-01** — now catalog entry #77 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 78. Nontermination detector (state recurrence)
**Shipped 2026-08-01** — now catalog entry #78 in [FEATURES.md](FEATURES.md): per-head state fingerprints, PROVEN only for statically pure while-loops with complete encodings and a quiet window (impurities counted PER WINDOW); everything else downgrades with named reasons; banner + jump links; the event cap is the honest hang-catcher.
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

### 79. NaN/Inf tripwire (first-origin of numerical poison)
**Shipped 2026-08-01** — now catalog entry #79 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 80. The variable oscilloscope (strip-charts + phase portraits)
**Shipped 2026-08-01** — now catalog entry #80 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 81. Heap topology view (the pointer graph)
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

### 82. Type-flow histograms & instability alarms
- **What:** aggregate the types every variable/argument/return
  actually had across a run (and across #63 runs): function rows gain
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

### 83. Array shape/dtype timeline
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

### 84. The I/O lane (strace-lite) + resource pairing
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

### 85. Code anatomy panel (recovers "opcode-level" — AST + bytecode)
**Static tiers (0+1) shipped 2026-08-01** — now catalog entry #85 in [FEATURES.md](FEATURES.md): Anatomy panel — per-record AST tree + dis listing (innermost enclosing record per line, current line lit in both, "as compiled, not adaptive" honesty header). What remains: Tier 2 — per-instruction dynamic stepping, and the live specialized/quickened opcodes it would reveal.
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

### 86. Sub-line branch verdicts (BRANCH events)
- **What:** the documented blind spot — ternaries, `and`/`or`
  short-circuits, comprehension `if`s — closed on 3.12+ via
  `sys.monitoring` BRANCH/JUMP events: verdicts for branches *inside*
  a line, shown at column precision (`co_positions`).
- **Why:** today the honesty note says "sub-line branching is not
  visible"; this deletes the caveat where the interpreter allows it.
- **How:** extend the monitoring backend (line mode, #102) to register
  BRANCH; map instruction offsets to source columns; the Event panel
  underlines the sub-expression with its verdict. Falls back honestly
  pre-3.12.
- **Effort:** L.
- **Prior art:** PEP 669's event set (refined further in 3.14);
  coverage.py's branch coverage — which counts, but never *shows*.

### 87. Memory heat (calorimetry)
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

### 88. Happens-before arrows (who woke whom)
**v1 shipped 2026-08-01** — now catalog entry #88 in [FEATURES.md](FEATURES.md): create/start/join edges as first-class ⤳ events with other-end jumps, plus Perfetto flow arrows between lanes. What remains: cancel edges, queue put→get correlation (uncertain-match honesty), trio/greenlet hooks.
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

### 89. Critical-path highlight
**v1 shipped 2026-08-01** — now catalog entry #89 in [FEATURES.md](FEATURES.md): the GIL-true spine (innermost-active attribution) with gold pins, banner verdict, untracked-wait accounting and a dedicated ★ row in the Perfetto export. What remains: true multi-core DAG analysis for genuinely overlapping threads.
- **What:** for an fn-granularity concurrent trace: compute the
  longest dependency chain (through awaits, joins and #88 edges) that
  determined total wall time; paint it gold in lanes and Perfetto
  export.
- **Why:** "we are 40% async" is trivia; "these five awaits ARE your
  runtime, everything else overlaps for free" is an optimization
  order. Speeding up anything off the critical path is wasted work.
- **How:** classic CPM/PERT longest-path over the slice DAG (slices +
  happens-before edges); needs #88. Honest about untracked externals
  (network waits show as gaps attributed to the awaiting slice).
- **Effort:** M after #88.
- **Prior art:** PERT/critical-path method (1950s operations
  research); Chrome's flame charts have it for the web — Python
  doesn't.

### 90. Lock-wait attribution
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

### 91. Multiprocessing lanes (recovers a "documented limit")
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
  (skew honestly labeled ±). Renderer scales via #101.
- **Effort:** XL (bootstrap is fiddly, merge is careful work) —
  arguably the largest single unlock on this list for real codebases.
- **Prior art:** coverage.py's multiprocessing support; VizTracer's
  multiprocess tracing; Perfetto's multi-track model (already our
  export target).

### 92. Live mission control (`--serve`)
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

### 93. Attach to a running process (PEP 768)
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
  host, restore prior settrace) already exist — that groundwork shipped as watch() (catalog feature 12).
- **Effort:** M once 3.14 is the floor; the safety analysis is the
  work.
- **Prior art:** PEP 768 (accepted for 3.14); py-spy --dump; rr's
  attach.

---

## Section 5 — The map grows

### 94. Project-wide static call graph
**Shipped 2026-08-01** — now catalog entry #94 in [FEATURES.md](FEATURES.md): def→def edges project-wide (from-imports, module attributes, self.method within its class), every edge labeled resolved/guessed, unresolved counted and named; walls panel ranks the load-bearing FUNCTIONS by cross-module fan-in; full edge list in the payload (capped, stated). What remains: drawing the def-level edges on the canvas, and feeding the sharper graph into ⌖ commands and #97.
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
  Feeds better ⌖ commands and #97.
- **Effort:** L.
- **Prior art:** pyan3 (unmaintained), Sourcetrail (discontinued —
  its niche is empty), IDE indexers (closed and per-symbol).

### 95. Crime-scene overlay (git churn × complexity)
**Shipped 2026-08-01** — now catalog entry #95 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record (heat/churn/risk lens select; window named in the banner; degrades to absent without git).
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

### 96. Layering rules (declared architecture, enforced visually)
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

### 97. Dead-code evidence report
**Shipped 2026-08-01** — now catalog entry #97 in [FEATURES.md](FEATURES.md): tiered join over #94's graph + importable surface + adopted heat (A unreferenced / B surface-only / C never-ran), ran-beats-static rule, class-body import-time execution excluded from liveness, 👻 rows + module counts + banner on the map, ranked terminal list, cap announced.
- **What:** combine static reachability (#94, from entry points and
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

### 98. Per-test chapters (the suite dissected)
**Shipped 2026-08-01** — now catalog entry #98 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 99. Import-cost view (startup autopsy)
**Shipped 2026-08-01** — now catalog entry #99 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.
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

### 100. API-surface honesty (encapsulation leaks)
**Shipped 2026-08-01** — now catalog entry #100 in [FEATURES.md](FEATURES.md): three leak classes (private-module reach / private-name import / name outside a literal __all__), outsider = outside the privacy owner's package, intra-package reaches exempt by design, computed __all__ = honest absence, star imports counted as unaudited; walls 🔓 audit + dashed-red edge toggle + banner + terminal.
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

### 101. Chunked trace + keyframes (the long-planned scale unlock)
**v1 shipped 2026-08-01** — now catalog entry #101 in [FEATURES.md](FEATURES.md): gzip+base64 chunks past 100k events, async loading, lazy keyframes every 64k. What REMAINS of this entry is the XL sequel: the truly windowed O(window) replayer.

- **What:** break the single embedded JSON into gzipped chunks with
  periodic full-state **keyframes**; the replayer loads O(window)
  around the cursor instead of O(run).
- **Why:** the ~2M-event / ~512 MB browser wall is the hard ceiling on
  everything else (multiprocessing lanes, whole-suite line traces,
  #103 dumps). Keyframes also make seek instant at any size.
- **How:** browser-native `DecompressionStream('gzip')` (no build
  tools broken); tracer writes chunk boundaries at call-depth-zero
  points; a keyframe = full variables snapshot (the trigger
  machinery already knows how to reconstruct state — reuse it).
  Honesty: the banner shows chunk count and any missing chunk loudly.
- **Effort:** L.
- **Prior art:** video codecs (I-frames/P-frames — this is literally
  that); Perfetto's trace processor.

### 102. Cheap LINE tracing via sys.monitoring
- **What:** extend the monitoring backend (shipped fn-only — catalog feature 06) to LINE
  events with surgical enable/disable per code object — line-level
  microscopes at a fraction of settrace's ~100× tax (target ~10–20×).
- **Why:** every line-level feature (verdicts, provenance, machinery)
  gets cheaper; triggers get cheaper still (watch mode = LINE events
  on ONE code object only, near-free).
- **How:** register LINE + the existing exception set; per-code
  `set_local_events` is the whole trick; keep byte-parity checks vs
  settrace in checks.py (the same parity discipline that audited the fn backend).
- **Effort:** M.
- **Prior art:** PEP 669's stated purpose; coverage.py 7.x's
  sysmon-based speedups prove the win is real.

### 103. Black-box flight recorder
**Shipped 2026-08-01** — now catalog entry #103 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 104. Reproducibility capsule (tiers of rr)
**Tier 1 shipped 2026-08-01** — now catalog entry #104 in [FEATURES.md](FEATURES.md): capsule embedded (cmd, cwd, env facts, lazily-tee'd consumed stdin) with the viewer's Reproduce box. Tiers 2–3 below (--seed-all; deterministic replay) remain.

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

### 105. Rosetta bridges (spec + import/export)
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

### 106. Deep links — a URL that opens a moment
**Shipped 2026-08-01** — now catalog entry #106 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 107. Annotations — notes pinned to events
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

### 108. Guided tours — executable lessons
- **What:** an ordered sequence of annotated stops (#107 + #106) saved
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

### 109. The query bar (omniscient search)
**Shipped 2026-08-01** — now catalog entry #109 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 110. Dual synced replayers
- **What:** open two traces side by side with linked cursors —
  aligned by the #64 divergence map when available, by manual anchor
  pairs otherwise; divergence point marked in both scrubbers.
- **Why:** before/after a fix, pass vs fail, brute vs fast (#71):
  humans diff by eye extremely well when the two films are locked in
  step.
- **How:** two iframes + postMessage cursor protocol + an alignment
  table; degrade to proportional sync with an honest "unaligned"
  badge.
- **Effort:** M (L with full alignment — build after #64).
- **Prior art:** diff tools' two-pane discipline applied to
  executions.

### 111. Movie export
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

### 112. Records table view
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

### 113. Ghost branch — the road not taken
- **What:** at any verdict event, faintly highlight the suite that
  was NOT entered (the else that didn't run, the loop body skipped on
  0 iterations) for exactly one step.
- **Why:** makes absence visible at the moment of decision — the
  gentle sibling of #77, and for a learner the moment branching
  *clicks*.
- **How:** ast extents per branch arm are already computed for
  dataflow; renderer tints the untaken range. Off by default,
  toggleable.
- **Effort:** S.
- **Prior art:** none we know of — cheap and genuinely novel.

### 114. Sonification — hear the trace
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

### 115. The explain bundle
- **What:** export a compact, human/LLM-readable text slice of the
  trace: N events around the cursor with source lines, variable
  states, verdicts and provenance, formatted for pasting into an
  issue, a code review — or an AI assistant.
- **Why:** the trace knows the ground truth of what happened;
  everyone else (humans and models alike) reasons better when handed
  that truth in text. pyreplay stays offline — the bundle is a file;
  where it goes is the user's business.
- **How:** a serializer over existing data + a "copy bundle" button;
  size-capped, self-describing header (script, capsule info if #104
  exists).
- **Effort:** S.
- **Prior art:** crash reporters' minidumps, made narrative.

---

## Section 8 — Research-grade (flagged honestly as such)

### 116. Symbolic branch exploration
- **What:** for a chosen never-taken branch: attempt to solve the
  path condition ("what stdin reaches line 84?") via symbolic
  execution of the guarding expressions.
- **Why:** #77 answers why a line didn't run; this answers what WOULD
  make it run — test-input generation for the untested path.
- **How:** realistically, an optional bridge to CrossHair (Z3-based,
  exists today) fed with our dataflow; a from-scratch solver is a
  thesis, not a feature. Degrade to "not installed".
- **Effort:** XL (bridge: L).
- **Prior art:** CrossHair; KLEE; concolic testing (DART/SAGE).

### 117. Full deterministic record/replay
- **What:** #104 Tier 3 completed into rr-class fidelity: every
  nondeterminism source intercepted so any recorded run re-executes
  identically — enabling reverse-execution debugging on top of our
  replayer.
- **Why:** the end-state of the whole field: the recording IS the
  bug, forever. Kept here as the north star and marked honestly:
  CPython offers no cheap path to syscall-level capture; the
  pure-Python subset (#104 Tier 3) is the realistic 80%.
- **Effort:** XL.
- **Prior art:** rr (Mozilla), Pernosco, UndoDB — all C/C++-world;
  Python's equivalent does not exist, which is exactly why it's
  listed.

---

## Section 9 — The second pass (bug-taxonomy review, 2026-07-20)

A 10-category bug taxonomy and 20-tool observability inventory were
checked against this list; most of both were already covered
(FEATURES.md or #63–#117), but seven real gaps surfaced. Each entry
notes the section it thematically belongs to.

### 118. Console & logging lane (stdout/stderr/logging as events)
**Shipped 2026-08-01** — now catalog entry #118 in [FEATURES.md](FEATURES.md), with the full measured/displayed/why/use-case record.

### 119. Dynamic edges — what the run saw that the parse couldn't
**v1 shipped 2026-08-01** — now catalog entry #119 in [FEATURES.md](FEATURES.md): dark call edges (observed pairs with no static route) drawn dashed with counts, plus static ⚡ flags on `__import__`/`import_module` call sites. What remains: runtime-import reconciliation against the static import edges.
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

### 120. Boundary schemas — observed interfaces at the borders
**v1 shipped 2026-08-01** — now catalog entry #120 in [FEATURES.md](FEATURES.md): per-run observed interfaces with instability warnings and deviant-call jumps. What remains: cross-run diffing, declared-schema checks, map rows.

*(belongs with Section 2/3 — causality & instruments)*
- **What:** at function/module boundaries, record the *structural
  schema* of arguments and returns — keys, types, nesting, lengths,
  not values: "returns dict{id:int, items:list[dict{sku,qty}]} —
  14 calls, stable"; show it as the def's observed interface on map
  rows and in the replayer; diff schemas across runs (#63) and
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
  at fn granularity; declared-schema checks reuse the #73 evaluator.
- **Effort:** M–L.
- **Prior art:** consumer-driven contracts (Pact), pydantic — but
  observed rather than declared; MonkeyType's cousin for shapes.

### 121. NVTX bridge — Python meaning on the GPU timeline
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

### 122. Shadowing & collision audit
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

### 123. Float-hygiene probes
*(belongs with Section 1/3 — the lab & instruments; pairs with #79)*
- **What:** (a) flag float equality as it executes — the verdict
  machinery already sees the compare and the operand types; flag
  `== `/`!=` between floats statically too; (b) a harness probe:
  re-run a chosen reduction under #63 with permuted operand order
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

### 124. Event-loop starvation detector
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
(#63–#74, #104, #116) — pyreplay's role there is the instrument *under*
the gauntlet: when a gate goes red, it shows why; before properties
exist, it drafts them from observed behavior. Two real gaps surfaced,
both places where recording the execution adds something the
standalone gate lacks.

### 125. Mutation-survivor forensics
*(belongs with Section 1 — the reliability lab)*
**Shipped 2026-08-01** — now catalog entry #125 in [FEATURES.md](FEATURES.md): `--forensics` mode — survivors/tests/diffs read from mutmut as-is, diff applied to a patched shadow copy by unique-context match, nearest test traced twice at line level, #64 divergence report + the missing-assertion verdict; identical traces say possibly-equivalent, skips carry reasons. What remains: the unconsumed-values refinement (post-divergence alignment) and cosmic-ray.
- **What:** mutation testing's chore is the *surviving* mutant — a
  planted bug no test killed. Bridge to mutmut/cosmic-ray (used
  as-is): for each survivor, run the nearest test twice at fn/line
  granularity — original code vs mutant — align the two traces with
  the divergence finder (#64), and report the first behavioral
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
  (#63's runner) → #64 alignment → report. Honesty note (the
  equivalent-mutant problem): some mutants change nothing
  observable; when the traces never diverge, say exactly that —
  "no behavioral divergence found; possibly an equivalent mutant" —
  never invent a difference.
- **Effort:** M (needs #63 + #64; the bridge itself is thin).
- **Prior art:** mutmut, cosmic-ray; the equivalent-mutant
  literature. No tool today explains *why* a survivor survived.

### 126. Metamorphic relations harness
*(belongs with Section 1 — the reliability lab; sibling of #71)*
**Shipped 2026-08-01** — now catalog entry #126 in [FEATURES.md](FEATURES.md): `--relation "T => R"` (repeatable) + `--relation-trials`/`--relation-seed`, inputs from stdin or the #127 gen protocol, outputs read from the recorded console lane, violations keep both traces + compose the `--diverge` command; en route it fixed #64's state token to include console text. What remains: input shrinking rides #66 when it exists; violations as in-trace events.
- **What:** differential testing (#71) needs a second
  implementation; metamorphic testing needs only a *symmetry*: the
  true output may be unknown, but `f(perm(x)) == f(x)`,
  `dist(a,b) == dist(b,a)`, `f(2x) == 2·f(x)` must still hold.
  `--relation "f(sorted(x)) == f(x)"`-style declarations run under
  the N-run harness (#63) over generated inputs (#67); a violation
  keeps the input, shrinks it (#66), and traces both sides of the
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
  scrubber markers; #64 diffs the two runs of a broken relation.
- **Effort:** S–M on top of #63/#67.
- **Prior art:** metamorphic testing (T.Y. Chen et al., 1998) —
  standard in compiler and search-engine testing, almost never
  available to everyday Python.

## Section 11 — the library & representation pass (2026-08-01)

A permanent-shelf curriculum canon (computation → complexity →
algorithms → the machine → systems → networks → languages) and an
inventory of algorithm representations were checked against
FEATURES.md and this roadmap. Most of the curriculum's language and
systems floor is already instrumented: closure cells (#35), the MRO
panel (#39), aliasing vs. rebinding (#34), generator lifecycles (#33)
and the import-time badge (#37) cover the interpreter syllabus; #88 is
Lamport's happens-before by name; #78's proven→observed downgrade is
the computability boundary rendered as a banner; the event log itself
embodies the append-only-log-as-narrow-waist idea; #74 already owns
theory-from-trajectories. The machine layer stays out by constitution
— bridge, don't clone: #85 is the deepest honest rung inside CPython,
#121 the bridge outward.

Nine gaps surfaced, in two families: **instruments** that turn a law
into an experiment on your own code (#127–130), and **general views**
of code and execution (#131–135). One design rule binds the second
family: a view earns its place by generality — shape-recognized
(#23's doctrine) or bound by a single declared name — never authored
per algorithm.

### 127. The scaling bench (empirical asymptotics)
*(belongs with Section 1 — the reliability lab)*
**Shipped 2026-08-01** — now catalog entry #127 in [FEATURES.md](FEATURES.md): `--sweep`/`--gen`/`--predict`/`--sweep-seed` — ladder runs, event-count + traced-time fits with R², doubling-ratio table, scale-free claim scoring, log-log report (`sweep_*.html`), crashed/truncated rungs excluded by name. The gen protocol shipped MINIMAL (`gen(value, seed) → stdin bytes`; no `--gen` = the value itself) — full #67 (property/fuzz entry) remains unbuilt.
- **What:** `--sweep "n=1000,2000,4000,8000" --gen GEN.py` — run the
  target across a size ladder (the #67 generator protocol produces an
  input of size n), record per-size **event counts** (any
  granularity) and fn-mode wall times, fit the log–log slope, and
  report the observed growth exponent with R². A `--predict "n^2"`
  claim is scored against the measurement. The same harness with a
  non-size knob (`--sweep "alpha=3.0..5.0"`) measures hardness
  curves and phase transitions instead of growth.
- **Why:** nothing in #1–126 varies input size: #63 repeats one input,
  #67 randomizes inputs hunting failures, #71 races two
  implementations. "What is the observed exponent" is the question
  the whole algorithms shelf trains — and **event counts are the
  honest cost model**: exact, deterministic, immune to timing noise,
  valid at line granularity where wall time is forbidden. The
  doubling experiment separates n log n from n^1.2 where eyeballing
  cannot.
- **How:** a harness over #63's runner — per-rung child runs, event
  totals (already counted), least-squares on log–log, chart via the
  oscilloscope machinery plus a terminal table. Honesty: the banner
  states "counts are Python-level events, not machine operations —
  constants live in the C layer"; a bad fit is reported as a bad fit,
  never forced to a line.
- **Effort:** M.
- **Prior art:** Sedgewick's doubling-ratio experiments; McGeoch,
  *A Guide to Experimental Algorithmics*; SAT phase-transition
  studies (Mitchell–Selman–Levesque).

### 128. The prediction gate
*(belongs with Section 7 — the replayer as a medium)*
**Shipped 2026-08-01** — now catalog entry #128 in [FEATURES.md](FEATURES.md): 🔮 gate bar with three claim types (next line / variable value or unchanged / loop total from recorded verdicts), gated step controls with counted unscored skips, per-script localStorage ledger with hit rate by type + streak, JSON sidecar export. What remains: prediction stops inside tours — when #108 exists.
- **What:** a replayer mode in which the next state is hidden behind a
  curtain until you commit a claim — "this verdict is False", "this
  loop runs 7 times", "`total` becomes 42" — which is then scored
  against the recorded truth. The session ends with a prediction
  ledger (hit rate by claim type). Tours (#108) gain prediction
  stops: a walkthrough becomes an exercise with a grade.
- **Why:** passive replay teaches little; the mismatch between a
  committed prediction and the recorded truth is where understanding
  is generated. This is the feature that converts the replayer from a
  microscope into a laboratory — and a planted-bug hunt into a scored
  drill.
- **How:** renderer-only. Every claim type rides existing data:
  verdicts (#31), the change index (#28), controller iteration counts
  (#77). A "commit to reveal" curtain over the next-state panels;
  ledger in localStorage with sidecar export (the #107 pattern). Zero
  schema change.
- **Effort:** M.
- **Prior art:** predict–observe–explain (White & Gunstone, science
  education); the pre-registration discipline of experimental
  physics.

### 129. The graph lens on the map
*(belongs with Section 5 — the map)*
**Shipped 2026-08-01** — now catalog entry #129 in [FEATURES.md](FEATURES.md): lens "graph (structure)" — betweenness tint (Brandes, directed) + community borders (deterministic label propagation) on module boxes; walls panel gains the ⛓ betweenness ranking (static AND observed-call-pair graphs, each named), the 💥 percolation fragility curve (initial ranking, stated), and the degree line with the log-log caution.
- **What:** upgrade the map's analytics from degree to graph theory:
  **betweenness centrality** (Brandes) beside fan-in in the walls
  panel — the modules everything routes *through*, not merely *to*;
  **community detection** (label propagation), detected clusters
  outlined against declared package boundaries — "is the architecture
  real?" as a picture; **percolation** — remove the top-k central
  modules, plot reachability collapse: the dependency-fragility
  curve; and the degree distribution reported with a
  straight-line-on-log-log caution.
- **Why:** the map is a graph analyzed with a fraction of graph
  theory — #52 ranks by raw degree, #49 finds cycles; bridges,
  clusters and fragility are invisible. Betweenness routinely names a
  different (and truer) load-bearing wall than fan-in does.
- **How:** pure Python over data the mapper already holds (Brandes
  O(VE) is comfortable at map scale; label propagation is a page).
  Rendered as a lens beside heat/churn/risk in the #95 select. Every
  number names its graph — "static import graph" vs "observed call
  pairs" when heat is adopted; the dark-edge honesty clause carries
  over.
- **Effort:** M.
- **Prior art:** Brandes (2001); Raghavan et al., label propagation;
  Albert–Jeong–Barabási attack-tolerance studies; Newman, *Networks*.

### 130. Trace compressibility
*(belongs with Section 6 — scale & interchange)*
**Shipped 2026-08-01** — now catalog entry #130 in [FEATURES.md](FEATURES.md): ≤120 per-bucket gzip ratios recorded at write time (traces ≥50 events), thin strip under the density strip colored by bits/event over the trace's own range, click-to-jump buckets, totals + the upper-bound honesty in the tooltip verbatim.
- **What:** report the event stream's compression ratio — bits/event
  overall and per density-strip bucket — as a regularity measure; a
  marked change in compressibility marks a phase change in the run.
- **Why:** a tight loop is low-entropy; data-dependent wandering is
  high. The run's regularity is a real observable no panel currently
  shows — and the bytes are already gzipped (#101), so the
  measurement is nearly free.
- **How:** per-chunk ratios recorded at write time; a thin strip under
  the density strip. Honesty: compressed length is an upper bound on
  the entropy rate — the label says "compressibility", never bare
  "entropy".
- **Effort:** S.
- **Prior art:** Shannon (1948); compression-as-complexity
  (Cilibrasi–Vitányi, normalized compression distance).

### 131. CFG view — the code as a graph, the run as a path
*(sibling of #85 — code anatomy)*
**Shipped 2026-08-01** — now catalog entry #131 in [FEATURES.md](FEATURES.md): CONTROL FLOW section of the Anatomy panel — typed-edge block ladder, observed traversals ×N, current block as the walking token, ghost vs unreachable-by-construction kept distinct, whyline one click away. #86's BRANCH events remain the stated sub-line refinement.
- **What:** a per-function control-flow graph built from the ast
  (basic blocks; edges from if/while/for/try/match/break/continue/
  return). Static, it joins #85's anatomy panel. With a trace
  adopted it turns dynamic: edges weighted by observed traversal
  counts, the current event a token walking the graph, never-taken
  edges ghosted — with #77's "why" one click away.
- **Why:** control flow *is* a graph; source text hides it. The
  dynamic CFG is the picture of what the whyline already computes —
  controller structure joined with recorded verdict counts — and the
  natural home of branch-coverage truth. #86's BRANCH events refine
  it to sub-line precision when they land.
- **How:** stdlib CFG construction (a contained small-compiler
  exercise; the delicate edges are try/finally and loop-else — the
  whyline's controller-stamping pass is reusable ground). The
  renderer reuses the graph-view engine. Honesty:
  unreachable-by-construction and never-observed are distinguished,
  never conflated.
- **Effort:** M.
- **Prior art:** classic compiler-textbook CFG construction;
  staticfg / py2cfg (unmaintained); coverage.py's branch model —
  which counts, but never shows.

### 132. The observed state machine
*(sibling of #74 — mined behavior)*
**Shipped 2026-08-01** — now catalog entry #132 in [FEATURES.md](FEATURES.md): `--fsm EXPR` (rides the #72 watch machinery) + `--fsm-declare FILE` checker — State machine panel with dwell-sized nodes, ×N edges with first-occurrence jumps, current state lit, gap-crossing transitions dashed; undeclared transitions spliced as derived viol events (badge/pins/type:viol free via #73); `--runs` merges N runs into one machine in the runs report. The honesty clause verbatim under the diagram. What remains: the click-a-variable-row binding (renderer-mined from the change index, no re-trace).
- **What:** declare one state variable (`--fsm order.status`, or a
  click on a variable row) and the tool mines the transition diagram
  from the trace: nodes = observed values sized by dwell, edges =
  observed transitions weighted by count with first-occurrence jump
  links, current state lit during replay. #63 aggregates many runs
  into one machine. An optional declared-transitions file turns the
  view into a checker: a forbidden edge becomes a violation event.
- **Why:** state machines are how half of real systems are designed
  and almost never how they are observed. The mined diagram is
  executable documentation and a drift detector — the general
  instrument for every automata-shaped mental model in a codebase.
- **How:** the binding is a single declared name — one flag, no
  authored scenes. The change index already holds every value
  transition; the graph engine renders. Honesty, verbatim from the
  dark-edge clause: *observed machine ⊆ true machine — a missing edge
  is never evidence of absence.*
- **Effort:** M.
- **Prior art:** Synoptic / Perfume (Beschastnikh, Ernst et al. — FSM
  inference from logs); process mining (van der Aalst); Angluin's L*
  as the theory backdrop.

### 133. The recursion tree
*(belongs with Section 7 — the replayer as a medium)*
**Shipped 2026-08-01** — now catalog entry #133 in [FEATURES.md](FEATURES.md): the Call tree panel — nested collapsible frames with args + returns, cursor descending live, per-level calls × events line, generator resumes reattached, 4000-node render cap announced.
- **What:** a `tree` execution view: the run's call tree — not lanes,
  not a flame chart — each node a frame carrying its arguments and
  return value, subtrees collapsible, the replay cursor descending
  the tree live; per-level node counts and event totals annotated.
- **Why:** for divide-and-conquer the call tree IS the canonical
  object — the recurrence, drawn. Per-level totals make "work per
  level × number of levels" countable on screen, and pair with
  #127's measured exponent. The stack panel shows one path; this
  shows the whole tree.
- **How:** a pure projection of recorded call/return nesting — no
  schema change. Collapsible rendering with the existing windowing
  honesty for huge trees (caps announced).
- **Effort:** S.
- **Prior art:** the recursion-tree method of the classic algorithms
  texts; flame graphs as the aggregate cousin — this one keeps
  per-call identity.

### 134. The subproblem DAG
*(belongs with Section 2 — deeper causality)*
**Shipped 2026-08-01** — now catalog entry #134 in [FEATURES.md](FEATURES.md): `--memo NAME` — static subscript-site pass + per-event frame-state reconstruction evaluate every index at the moment it ran; DP-table grid layout for 2-int keys, causal fill animation, normal/base/pre edge classes (pre = amber ⚠ init-value read — rolling array or wrong order, fact stated, intent never guessed), frontiers counted (slices, call-bearing indexes, aliases). Built as the #75 container-element remainder SCOPED to the bound name; what remains with #75: cross-frame edges (a dependency routed through a call shows cells, not the edge) and the generic slice-closure crossing.
- **What:** bind a memo structure (`--memo dp`) and the view draws
  its entries as nodes appearing as they are written, with
  read→write dependency edges mined from the dataflow — the
  dependency DAG of the table, animated as it fills. The grid view
  shows fill *order*; this shows fill *causality*.
- **Why:** dynamic programming is shortest-paths-in-DAGs, and the DAG
  is the part nobody ever sees. It is also a bug detector, not just
  pedagogy: a read of a not-yet-written cell renders as a red edge —
  the wrong-evaluation-order bug, visible at the moment it happens.
- **How:** one binding flag; edges from the provenance machinery
  (#29/#75) restricted to subscripts of the bound name. The honest
  frontier note carries over: slice assignments and C-level writes
  are marked untracked, never guessed. Graph engine renders.
- **Effort:** M after #75's container-element remainder ships; L
  before it.
- **Prior art:** the DP-as-DAG chapter of the standard texts; program
  slicing (Weiser; Korel–Laski).

### 135. The motion layer
*(belongs with Section 7 — the replayer as a medium)*
**Shipped 2026-08-01** — now catalog entry #135 in [FEATURES.md](FEATURES.md): FLIP tweens at play speed over cells/bars/grid/dict/graph views (heuristic identity, labeled), inert at single-step, + presentation mode (P/🎬, chrome hidden, large type). The legend rides the play button and the presentation note verbatim.
- **What:** tweened transitions between consecutive events in the
  existing generic views — a swap's two bars glide past each other, a
  queue advances, a tree node descends into place — plus a
  presentation mode (chrome hidden, large type). Inert at
  single-step; active at play speeds.
- **Why:** state currently teleports between events, and at play
  speed the eye loses element identity exactly when
  watching-the-algorithm is the point. Motion is the honest rendering
  of a recorded change *as a change* — and it is generic by
  construction: it animates whatever the shape views already draw,
  for any code, with no per-algorithm authoring.
- **How:** renderer-only FLIP over the diff machinery, which already
  knows precisely which elements changed; identity by `id()` for
  objects, index/value heuristics for primitives — heuristic, and
  labeled as such. Honesty, stated once in the legend: *motion
  between events is interpolation; only the endpoints are recorded
  truth.* Composes with #111 (movie export) and #108 (tours).
- **Effort:** M.
- **Prior art:** the FLIP animation technique; Heer & Robertson,
  *Animated Transitions in Statistical Data Graphics* (2007).

### Notes recorded so they aren't lost (Section 11)
- **Guest clock** *(rides #72)* — when tracing an interpreter you
  wrote, declare one watch expression as the guest program counter:
  a second density strip in guest time, host events against guest
  steps — two floors of the interpretation tower on one screen.
  S once #72 exists (#72 shipped 2026-08-01 — this is now live bait).
- **Wire alignment** *(rides #84 + #105)* — import a packet-capture
  timeline as a lane aligned on the I/O lane's socket-call
  timestamps: the trace and the wire on one clock. A bridge, not a
  clone — capture remains tcpdump's job. M.
- **Descriptor blind spot** *(attach to #85)* — attribute lookup's
  descriptor priority resolves below the line: invisible to line
  events and to the MRO panel alike. #85 Tier 2 (instruction events)
  is the feature that would show a `__get__` hit.

### If you only build five — the learner's cut (Section 11)
1. **#128** — the prediction gate: the switch from microscope to
   laboratory; understanding is generated at the mismatch.
2. **#127** — the scaling bench: the observed exponent, measured in
   honest event counts; the doubling experiment as a command.
3. **#131** — the CFG path view: the code as the graph it is, the run
   as a walk on it — the whyline's knowledge, finally drawn.
4. **#85-static** — the anatomy floor: AST and bytecode, the deepest
   honest rung of the tower, already rated S.
5. **#74** — invariant mining: conserved quantities inferred from
   recorded trajectories — the trace-to-theory bridge everything
   else feeds.

## Section 12 — the atlas pass (2026-08-01)

The Representation Atlas (a separate study: one problem — sorting —
ten algorithms, 49 representations, 490 cells, each an artifact or a
reasoned refusal) doubled as an EXPERIMENT in generality: every
artifact is badged by how it was produced. The census is the finding:
**13 representations generated mechanically from canonical source, 6
from the event log, 30 requiring authored insight** — and the n/a
cells cluster exactly where generality dies (spreadsheets can't hold
unbounded control; circuits can't hold data-dependent comparisons;
cellular automata fit only local-rule algorithms). The 13 source-auto
grammars encode just TWO data sets — the syntax tree and the
control/data-flow graph — both already recorded here (#85, #131,
build_dataflow). The 30 authored rows are algorithm-pedagogy and stay
in the atlas: porting them would break the no-authored-scenes rule.
What remains for THIS tool is the log-auto family's one missing view
and two small completions:

### 136. The sequence diagram — lifelines from the log
*(belongs with Section 7 — the replayer as a medium)*
**Shipped 2026-08-01** — now catalog entry #136 in [FEATURES.md](FEATURES.md): the Sequence panel — window select (chapter / frame extent / flanking bookmarks / whole run), module-or-class lifelines caller-first, arrows in event order with the corner honesty, activation bars with exception red and open-at-window-end hollow, imports as module→module arrows, caps 12/400 announced. Rides the #133 projection; zero schema change.
- **What:** a `seq` view over a WINDOW of the trace (a chapter, a
  selection, or between two bookmarks — a whole run is too tall and
  the cap says so): lifelines = the modules (or classes, where the
  MRO machinery knows `self`) that act in the window; arrows = call
  events in order, labeled with the function name; activation bars =
  the call's extent (the #133 nesting, redrawn); returns close the
  bar, exceptions mark it. Threads/tasks come for free: a lane is a
  lifeline group. Time flows down in EVENT order — not wall time,
  stated in the corner. Click an arrow = jump to that call.
- **Why:** the classic onboarding question is "who talks to whom, in
  what order". The call tree aggregates it (identity, no sequence
  between siblings' subtrees at a glance); the lanes show
  interleaving (no interaction grammar). The sequence diagram is the
  missing third projection of the SAME call/return events — and the
  atlas proved the row log-auto on all ten algorithms.
- **How:** pure projection, renderer-only, zero schema change: the
  #133 builder already computes nesting; group frames by module (or
  class via the recorded MRO supplier), lay lifelines left-to-right
  by first appearance, draw arrows per call event in the window.
  Cap lifelines (~12) and arrows (~400), both announced; composes
  with chapters (#98: one diagram per test) and deep links (#106).
- **Effort:** M.
- **Prior art:** UML sequence diagrams; Jacobson interaction
  diagrams; the atlas's H4 row (generated from event log, 10/10).

### 137. The observed decision table
*(belongs with Section 2 — deeper causality; sibling of #77/#86)*
**Shipped 2026-08-01** — now catalog entry #137 in [FEATURES.md](FEATURES.md): DECISIONS — OBSERVED TRUTH in the Anatomy panel — guard rows from the CFG record (true-edge sources, exc/case-edge targets), ran/true/false counts with first-occurrence jumps, never-ran / never-true / never-false flags, never-ran rows hand off to the whyline. Whole-guard rows, said plainly; #86's sub-condition columns remain.
- **What:** per function, the branching truth summary AS A TABLE:
  one row per guard (the CFG already knows them) — ran N× · true
  T× · false F× — with never-true / never-false flagged and each
  cell a jump to its first occurrence. The atlas's G1 row, made
  OBSERVED: not the combinations that could happen, the ones that
  did. When #86's BRANCH events land, compound guards (`a and b`)
  gain sub-condition columns; until then whole-guard rows, said
  plainly.
- **Why:** the verdicts exist per event (#31) and the whyline
  answers one line at a time (#77); nothing shows a function's
  WHOLE branching behavior in one compact, jumpable table.
  Coverage tools count branches; none show the truth summary
  inline with the moments.
- **How:** pure aggregation of recorded cond events per guard line,
  rendered as a table in the Anatomy panel beside the CFG (same
  record resolution). Zero schema change.
- **Effort:** S.
- **Prior art:** decision tables (the atlas's G1, log-auto 8/10 —
  two reasoned refusals); coverage.py branch counts, which count
  but never show.

### 138. Classic grammar skins — flowchart and structogram
*(belongs with Section 7; presentation-only, explicitly optional)*
- **What:** alternate DRAWINGS of data already recorded, as a
  select in the Anatomy panel: #131's CFG rendered as a classic
  flowchart (diamonds, yes/no labels, orthogonal routing, rounded
  terminals) and #85's structured AST as a Nassi–Shneiderman
  structogram. The observed weights, ghost edges and current-block
  token carry over — the skin changes, the truth doesn't.
- **Why:** readability and teaching: these are the grammars people
  already know how to read; the ladder is denser but unfamiliar.
  No new information — added on the atlas's evidence that both are
  total functions of source (B1/B2, 10/10 auto), and worth building
  only when the classic look is wanted.
- **How:** renderer-only layout modes over the existing cfg/anatomy
  payloads.
- **Effort:** S–M per skin.
- **Prior art:** ISO 5807 flowcharts; Nassi & Shneiderman (1973);
  the atlas's B1/B2 rows.

## Deliberately still rejected

- **Per-algorithm authored scenes** — a view earns its place by
  generality: shape-recognized (#23's doctrine) or bound by a single
  declared name (#132, #134). One flag is a binding; an artwork per
  algorithm is a museum piece, and museums go stale while the shape
  engine keeps working on code nobody curated. The teaching fleet
  plus tours (#108) carry the pedagogy without bespoke renderers.
- **Viewer-side eval / edit-and-continue** — replay must never
  pretend to compute; recording-side #72/#73 cover the need honestly.
- **3D visualization** — aggregation and filtering, not rendering
  heroics (unchanged since the brief).
- **Rebuilding samplers/profilers** — py-spy and friends exist; we
  bridge (#105), not clone.
- **Auto-running composed commands from the map** — the ⌖ copy box is
  the interface on purpose: the funnel teaches; a button would
  obscure.

## If you only build five

(The previous five — 98, 101, 109, 118, 77 — all shipped on
2026-08-01, as did the five before them. Third edition:)

1. **#68** — schedule fuzzing: seeded interleaving perturbation ×
   the #63 harness turns "works on my machine" into a measured rate.
   The reliability lab's concurrency edge.
2. **#88** — happens-before arrows: lanes show interleaving; the
   arrows show CAUSATION — who woke whom, which put fed which get.
3. **#119** — dynamic edges: fn traces already know the caller→callee
   pairs the parse can't see; draw them and the map stops
   under-reporting exactly where it matters most.
4. **#95** — churn × complexity × heat: three axes the repo already
   has, joined into the strongest bug predictor known.
5. **#75** — the full backward slice: provenance's one hop, closed
   transitively — "how did this wrong value come to be" as a
   navigation mode.

## Good first features (S-effort, self-contained)

#72 · #73 · #85-static · #96 · #99 · #112 · #113 · #115 · #122 ·
#124.

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
