# pyreplay — the roadmap & contribution guide

Everything already built lives in **FEATURES.md** (the catalog, 122
entries, ordered the way you use the tool) and **TUTORIAL.md** (the
guide, same order). This file is the other half: **the features not
built yet** — numbered 1–17 below, 15 still open (a shipped one keeps
its number, struck through, so references stay stable) — and how to
contribute one. It's written so a stranger can pick an item and
implement it.

## Start here — how to contribute

New here and want to help? Three steps:

1. **Pick something.** The **Index** below lists the 15 open
   features. Bug reports, edge cases, and more `example_*.py`
   programs are just as welcome. Adding **another language** is the
   biggest prize — see "Support another language" and the event-log
   schema at the end of this file.
2. **Follow the constitution** (next section) — standard library
   only, the honesty contract, and `checks.py` green before and
   after. Match the style of whatever file you're editing.
3. **Open an issue** describing the plan before a large change, so
   the approach can be agreed first.

Everything you need is in this repo — no external docs, no chat
memory.

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
can hide an error that only sometimes shows up* — became the
reliability lab (catalog Part 14). The rest is reconstructed as
design lenses, not quotes:

- **The Hotz lens — machine truth, zero overhead.** Show the actual
  interpreter (bytecode, specializations), cost nothing when idle,
  attach to anything, never fake a number. → catalog #69/#49/#17,
  and #10 here.
- **The Torvalds lens — bisect it, diff it, no magic.** Every bug is
  a difference between a world that works and one that doesn't;
  build the tools that find the first divergence. → catalog
  #112/#114, and #3 here (shipped: catalog #118).
- **The Stroustrup lens — types, invariants, resources.** What holds
  always? What type flows here? Who owns this resource and who
  closed it? → catalog #65/#66/#67, and #5 here.

**Effort:** S = a focused day · M = several days · L = a week+, schema
touched · XL = multi-week / research-grade. **Payoff:** ★ nice ·
★★ strong · ★★★ changes what the tool is.

## Index

| # | Feature | Effort | Payoff |
|---|---------|--------|--------|
| ~~1~~ | ~~Random-input entry with seed capture~~ — **shipped**: catalog #117 (`--fuzz`) | M | ★★ |
| 2 | Inject exceptions/latency on purpose | L | ★★ |
| ~~3~~ | ~~Compare implementations on the same inputs~~ — **shipped**: catalog #118 (`--oracle`) | M | ★★ |
| 4 | Object-reference graph at an event | L | ★★ |
| 5 | I/O lane via audit hooks; resource-leak pairing | M | ★★ |
| 6 | Memory heat on the map (tracemalloc) | M | ★★ |
| 7 | Lock-wait attribution | L | ★★ |
| 8 | Multiprocessing children traced into lanes | XL | ★★★ |
| 9 | Live streaming replayer (--serve) | L | ★★ |
| 10 | Attach to a running process (PEP 768) | M | ★★★ |
| 11 | Schema spec + import/export bridges | M | ★★ |
| 12 | Two traces side by side, cursors synced | M | ★★ |
| 13 | Export a panel as video/GIF | M | ★★ |
| 14 | Hear the trace (sonification) | M | ★ |
| 15 | Symbolic "what input reaches this line" | XL | ★ |
| 16 | Full deterministic record/replay | XL | ★★ |
| 17 | NVTX bridge: Python names on the GPU timeline | M | ★★ |

## The features

### 1. Property/fuzz entry — SHIPPED
Now **catalog #117** (`--fuzz GEN.py`): seeded `gen(rng)` inputs
through the N-run harness, run i seeded base+i−1 and recorded;
first-per-class inputs saved beside their kept traces; the first
failure gets a line-level microscope trace and the composed
`--shrink` command. The Hypothesis `@given` bridge from the original
sketch remains unbuilt (the `gen(rng)` protocol carries it).

### 2. Fault injection (chaos engineering for one process)
- **What:** `--inject "shop.pay:raises=TimeoutError:on_call=3"` —
  force a chosen call site to raise / return a sentinel / stall, then
  watch (with the existing exception machinery) how the failure
  propagates and what catches it.
- **Why:** error-handling paths are the least-executed, least-tested
  code in any codebase; injection is the only way to *see* them run.
  The propagation-chain view (catalog #114 in FEATURES) was built for exactly
  this moment.
- **How:** an import-time wrapper installed by the tracer around the
  named callable (we own the process bootstrap); every injection is
  recorded as a first-class INJECTED event so the trace never lies
  about what really happened.
- **Effort:** L.
- **Prior art:** Netflix chaos engineering, aerospace HALT testing —
  break it on the bench, not in the air.

### 3. Differential testing — SHIPPED
Now **catalog #118** (`--oracle REF.py`): both implementations on
the same input (piped stdin, or `--fuzz` seeded trials), stdouts
compared judge-style from the console lane; a mismatch keeps input
+ both traces and composes `--shrink --oracle` (ddmin under the
disagreement oracle, both sides microscoped on the minimal case).
One sketch line changed en route, honestly: `--diverge` is NOT
composed on a mismatch — it aligns two runs of the SAME code, and
these are two different programs; the minimized input is the
explanation there.

---

### 4. Heap topology view (the pointer graph)
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

### 5. The I/O lane (strace-lite) + resource pairing
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

### 6. Memory heat (calorimetry)
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

### 7. Lock-wait attribution
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

### 8. Multiprocessing lanes (recovers a "documented limit")
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
  (skew honestly labeled ±). Renderer scales via catalog #30.
- **Effort:** XL (bootstrap is fiddly, merge is careful work) —
  arguably the largest single unlock on this list for real codebases.
- **Prior art:** coverage.py's multiprocessing support; VizTracer's
  multiprocess tracing; Perfetto's multi-track model (already our
  export target).

### 9. Live mission control (`--serve`)
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

### 10. Attach to a running process (PEP 768)
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

### 11. Rosetta bridges (spec + import/export)
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

### 12. Dual synced replayers
- **What:** open two traces side by side with linked cursors —
  aligned by the catalog #112 divergence map when available, by manual anchor
  pairs otherwise; divergence point marked in both scrubbers.
- **Why:** before/after a fix, pass vs fail, brute vs fast (#3, shipped: catalog #118):
  humans diff by eye extremely well when the two films are locked in
  step.
- **How:** two iframes + postMessage cursor protocol + an alignment
  table; degrade to proportional sync with an honest "unaligned"
  badge.
- **Effort:** M (L with full alignment — build after catalog #112).
- **Prior art:** diff tools' two-pane discipline applied to
  executions.

### 13. Movie export
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

### 14. Sonification — hear the trace
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

### 15. Symbolic branch exploration
- **What:** for a chosen never-taken branch: attempt to solve the
  path condition ("what stdin reaches line 84?") via symbolic
  execution of the guarding expressions.
- **Why:** catalog #68 answers why a line didn't run; this answers what WOULD
  make it run — test-input generation for the untested path.
- **How:** realistically, an optional bridge to CrossHair (Z3-based,
  exists today) fed with our dataflow; a from-scratch solver is a
  thesis, not a feature. Degrade to "not installed".
- **Effort:** XL (bridge: L).
- **Prior art:** CrossHair; KLEE; concolic testing (DART/SAGE).

### 16. Full deterministic record/replay
- **What:** catalog #34 Tier 3 completed into rr-class fidelity: every
  nondeterminism source intercepted so any recorded run re-executes
  identically — enabling reverse-execution debugging on top of our
  replayer.
- **Why:** the end-state of the whole field: the recording IS the
  bug, forever. Kept here as the north star and marked honestly:
  CPython offers no cheap path to syscall-level capture; the
  pure-Python subset (catalog #34 Tier 3) is the realistic 80%.
- **Effort:** XL.
- **Prior art:** rr (Mozilla), Pernosco, UndoDB — all C/C++-world;
  Python's equivalent does not exist, which is exactly why it's
  listed.

---

### 17. NVTX bridge — Python meaning on the GPU timeline
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

## Deliberately still rejected

- **Per-algorithm authored scenes** — a view earns its place by
  generality: shape-recognized (catalog #56's doctrine) or bound by a single
  declared name (catalog #91, catalog #77). One flag is a binding; an artwork per
  algorithm is a museum piece, and museums go stale while the shape
  engine keeps working on code nobody curated. The teaching fleet
  plus tours (catalog #103) carry the pedagogy without bespoke renderers.
- **Viewer-side eval / edit-and-continue** — replay must never
  pretend to compute; recording-side catalog #63/catalog #89 cover the need honestly.
- **3D visualization** — aggregation and filtering, not rendering
  heroics (unchanged since the brief).
- **Rebuilding samplers/profilers** — py-spy and friends exist; we
  bridge (#11), not clone.
- **Auto-running composed commands from the map** — the ⌖ copy box is
  the interface on purpose: the funnel teaches; a button would
  obscure.

## If you only build five

The learner's cut of the open seventeen:

1. ~~**#1 property/fuzz entry**~~ — **shipped** (catalog #117): find
   the failing case while you sleep, keep the seed, shrink it.
2. ~~**#3 differential testing**~~ — **shipped** (catalog #118): the
   brute force is the specification, the loop closed end to end.
3. **#5 the I/O lane** — "what did this program touch?" answered
   from audit hooks, with unclosed resources named.
4. **#6 memory heat** — time-heat says where it computed;
   memory-heat says where it retained.
5. **#10 attach** — the one thing external samplers still have over
   pyreplay: joining a process already running.

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
