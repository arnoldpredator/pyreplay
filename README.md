# pyreplay

**See what Python is actually doing.** A zero-dependency tracer and static
mapper that turn a Python run — or a whole codebase — into an explorable,
self-contained HTML page. It's built for a problem that keeps growing: an
LLM can generate a whole project in seconds, but quickly grasping what that
code *actually does*, and how it all fits together, is not easy. pyreplay
makes that first pass fast — record a run and replay it step by step, or
map the whole codebase at a glance. It won't fix your bugs (that's what a
professional IDE is for) — it's the fast first look, especially at code an
LLM wrote.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)

<!-- ⬇ Drop a screen recording here — a 15-second GIF of stepping through a
     trace, then zooming a codebase map, sells this faster than any paragraph.
     Record one, save it as docs/demo.gif, and uncomment:
![pyreplay demo](docs/demo.gif)
-->

## What you get

Two tools that share one JSON event-log format:

- **`tracer.py`** — records a run (every line / call / return, and *which*
  variables changed) into a self-contained `trace_*.html` you step through
  like a video. Semantic views per data structure (a list is a row of cells,
  a graph is nodes and edges), asyncio tasks shown as parallel lanes, and
  Perfetto timeline export. Every trace also records the console (click a
  printed line → the moment that wrote it) and embeds a reproducibility
  capsule: the exact command, environment facts and consumed stdin needed
  to run it again.
- **`mapper.py`** — reads a codebase with `ast` (**nothing is executed**) into
  a zoomable `map_*.html`: modules laid out by import depth, packages that
  fold, import cycles drawn in red, and the "load-bearing walls" ranked by how
  many modules import them. Overlay a trace to see which parts actually ran.

## Quickstart — no install, standard library only

```bash
python3 tracer.py your_script.py      # -> trace_your_script.html
python3 mapper.py path/to/project     # -> map_project.html

python3 tracer.py --runs 20 flaky.py            # run it 20x: outcome stats,
                                                #    one kept trace per behavior
python3 tracer.py --diverge good.html bad.html  # first event where two runs
                                                #    part ways (cause, then symptom)
python3 tracer.py --trip nan sim.py             # where the first NaN was BORN
python3 tracer.py --check "total < 0" app.py    # any question about a run as an
                                                #    exit code -> git bisect's oracle
python3 tracer.py --black-box server.py         # flight recorder: ring of the LAST
                                                #    N events; kill -USR1 = live snapshot
```

Open the HTML in any browser. No server, no build step, no dependencies.
Full guide in [TUTORIAL.md](TUTORIAL.md); every feature explained with a
screenshot in [FEATURES.md](FEATURES.md).

## How is this different from Python Tutor / VizTracer?

- **Python Tutor** visualizes small snippets in a sandbox. pyreplay traces real
  scripts on your own machine and scales up to whole codebases through the
  static map and semantic zoom.
- **VizTracer** is profiling-first — a timeline of *when* calls happened.
  pyreplay is understanding-first — it shows *values*: which element of a list
  changed, whether a name was rebound or the object mutated in place, what a
  branch decided and why.
- **The honesty contract.** pyreplay marks *only* what it actually knows
  changed. Partial or unknown state is left unmarked, never guessed; every cap
  and truncation is announced on screen. If it can't be sure, it says so.

## Architecture — and how to add another language

Three decoupled layers:

```
  tracer  (Python: sys.settrace / sys.monitoring)
     │
     ▼
  JSON event log   ◀── the contract. language-neutral.
     │
     ▼
  HTML renderer  (vanilla JS, no framework)
```

The event log is the whole point: the renderer doesn't care what produced it.
You can add support for another language **without touching the viewer** —
emit the same JSON from a C++ / Rust / JS tracer and the existing replayer
plays it back. The static map has a matching seam (swap `ast` for a parser of
your target language). Both are laid out in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Tests

```bash
python3 checks.py     # 68 data-level checks — should print all green
```

Every feature is pinned by a check. Run it before and after any change; a
green suite is the contract that keeps contributions honest.

## Contributing

Bug reports, edge cases, more example programs, and **other languages** are
all very welcome. **[CONTRIBUTING.md](CONTRIBUTING.md) is the place to start** — one file
with the roadmap of what to build (49 unbuilt features plus a "good first"
list), the ground rules, and the event-log schema a new-language backend emits.

## License

[MIT](LICENSE).

---

*Requires Python 3.10+ (developed on 3.12). The faster `--backend monitoring`
recorder uses [PEP 669](https://peps.python.org/pep-0669/) and needs 3.12+.*
