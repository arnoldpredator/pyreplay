# pyreplay — user guide

## The static map (Phase 3)

```bash
python3 mapper.py path/to/codebase        # -> map_<name>.html
```

Parses every .py file with `ast` — **nothing is executed** — and draws
the codebase's geography: modules as boxes arranged by import depth,
arrows toward dependencies, function/class inventories inside each box
(click to expand), and toggleable dashed "call routes" showing which
modules statically call into which (with call-site counts). Drag to
pan, wheel to zoom, `fit` to frame everything. The search box
highlights any module or function by name — "where does sleep live?"
is one keystroke.

**Packages fold** (semantic zoom v2): modules group into package boxes.
Maps over 50 modules start folded — brian2's 309 modules arrive as 49
readable boxes. Click a box to unfold its members (they behave exactly
like normal module boxes inside); `fold pkgs` / `unfold` in the header
work the whole map. A folded box rolls up what it hides: module count,
loc, heat share (summed, same palette), ⚠N exceptions, parse errors.
Edges into hidden modules re-attach to the box and aggregate — thicker
line, tooltip lists the member-level imports. Search still sees inside:
matching a function that lives in a folded package lights the box.

**Import cycles** are found statically (strongly connected components)
and announced three ways: the stats bar counts them, folded boxes
hiding cycle edges carry a red **⭯N** pip, and the bottom note lists
every cycle — **click one to spotlight it** (members highlighted, its
edges red, everything else dimmed). The **cycles checkbox** in the
header paints *every* cyclic edge red at once; it's off by default
because a codebase whose core is one big SCC (nengo, brian2) would
otherwise drown in red — red should mean "look here", not "everywhere".

**Sibling edges hide inside open packages**: imports *between two
modules of the same package* are the densest noise on a big map, so an
unfolded package shows them as an honest **⇄N** count in its header
instead of drawing all N at once. They appear exactly when you care:
expand a member module (its own edges light up and ride above the
boxes), search, click a cycle, or flip the cycles toggle.
Cross-package edges always draw. And **hovering any box** — module
or package, folded or open — lights its arrows instantly while the
rest recede; no click needed (click keeps meaning fold/expand).

**Walls** (header button): the top-10 modules by fan-in — how many
modules import me (←N) vs how many I import (→M). This is how you find
a codebase's load-bearing walls: in brian2, `brian2/__init__` is
imported by 164 modules and `utils.logger` by 55. Click a row to
highlight it on the map.

**Mixed-language projects** (Python + C++/Cython/…): the mapper reads
only `.py` files — everything else is simply not on the map, and a
Python file that fails to parse (Python 2, templates) becomes a
red-dashed "parse error" box instead of killing the run. The Python
half of a hybrid codebase maps normally.

**Heat — the trace drawn onto the map** (the cockpit):

```bash
python3 tracer.py myapp/main.py                    # 1. record a run
python3 mapper.py myapp                            # 2. map + heat
```

**Auto-heat**: the mapper looks for the newest `trace_*.html` (working
dir + mapped root) whose traced files belong to the codebase being
mapped, and adopts it automatically — announced on stdout, never
guessed across codebases. `--trace FILE` picks one explicitly;
`--no-trace` disables the automation. So the funnel is: trace once,
and every later map of that codebase carries heat and complete ⌖
commands by itself.

Modules are tinted on a weather-radar scale by their ABSOLUTE share of
the run: 0% = no tint, ~5% = faint blue, then teal → green → yellow →
orange → hard red at 100% (legend in the bottom note; the exact value
is printed on every box). The bottom note SAYS what the heat measures:
**EVENT COUNTS** (from a line trace: share of executed lines) or
**TIME (self)** (from an fn trace: share of real wall time spent in
the module's own code — where the run's milliseconds actually lived).
Function rows then show "×calls · cumulative time" with self/cum in
the tooltip. `--heat-out agg.json` also writes the aggregate as plain
JSON.

**The funnel handoff**: every module box has a small **⌖** in its
corner, and every function row is clickable — either composes the
exact microscope command (`--include` scoped, `--start-at` for a
specific def, entry script filled in from the trace) in a copy box at
the bottom right. With no trace loaded the ⌖ still tries hard, honestly:
a module with an `if __name__ == "__main__"` block gets a **complete**
command (it runs itself); a library module gets an entry **borrowed
from a runnable importer** — the map walks the import graph backwards
and picks the nearest module with a `__main__` guard that imports it
("entry borrowed from debug — it runs itself and imports this
module"). Only when nothing runnable reaches the module does the
`YOUR_SCRIPT.py` placeholder appear, and if pytest-style tests import
it, the note says so (run them under pytest once, re-map, and
auto-heat fills everything in). Entry paths are absolute, so commands
work from wherever your shell is. The map tells you WHERE; the ⌖ writes the HOW. Badges show **#1, #2…** execution
order and **⚠N** where hard exceptions fired; untouched modules fade —
one glance answers "which part of this codebase actually executes?". Expand a hot module
and every function shows **×N** (its event count this run); class
chips tint by their methods' heat. The `heat` checkbox toggles the
overlay. Note the honest details: importing a module executes its
top-level code, so "cold" modules still show a few events, and class
bodies run at import time — the map shows Python as it really is.

**Inside a module** (click its box): top-level functions listed, and
classes drawn as a grid of chips. Click a class chip and its whole
local ancestry lights up green with inheritance edges — in a monolith
("2000 lines of base classes + 50 exercise classes in one file") this
IS the architecture view. A panel shows the selected class's bases and
methods. Searching a method name highlights every class that defines
or overrides it — an instant override map.

**The call graph inside one file** (the function-world twin of that
class view): click a **function name** in an expanded module and it
focuses — **green** arrows fan out to every function it calls (those
rows light green), **amber dashed** arrows come in from every function
that calls it (amber). A green **▸** marks entry points (functions
called at module level — import time, or under `__main__` when run as a
script); a **↺** marks recursion. This turns a single 900-line script
from a dead list into its actual structure. Click the name again to
clear; click the **`:line`** number instead to get the scoped tracer
command. Like the map itself it's best-effort static — it catches
direct calls, not ones made through variables (`obj.method()` and
dispatch tables) — and the bottom note always reports how many calls
weren't statically resolvable. This is the wide, cheap end of the funnel: map
first, then aim the microscope.

# pyreplay tracer — user guide

Record a Python program's execution — every line, call, return, and
variable change — into a single self-contained HTML file you can replay
in any browser: step forward/back, play at chosen speed, scrub anywhere.

Files: `tracer.py` (recorder) + `replayer_template.html` (viewer shell,
must sit in the same folder as tracer.py). You never open the template
directly — only the generated `trace_*.html`.

---

## 1. Basic usage

```bash
python3 tracer.py path/to/your_script.py
```

- Runs the script exactly as `python3 your_script.py` would (its own
  `if __name__ == "__main__":` block fires; pass its arguments after
  the script path).
- Traces the script **plus every file it imports from its own directory
  tree**. The stdlib and site-packages are never traced.
- Output: `trace_<scriptname>.html` in the directory you ran from.
  Re-running never overwrites: you get `_2`, `_3`, … suffixes.
- `--out NAME.html` picks an explicit name (this one DOES overwrite).

If the script needs stdin (typical AtCoder style), pipe it:

```bash
python3 tracer.py solution.py < input.txt
```

If the terminal seems frozen, the script is waiting for input — the
tracer prints a hint when this is likely. Ctrl-C always stops the run
AND keeps everything traced so far. Check for stray runs with
`pgrep -af tracer.py`, kill one with `kill <PID>`.

## 2. The viewer

Open the generated HTML in a browser. Layout:

- **Left**: source code, current line highlighted, one tab per traced file.
- **Right**: current event (CALL/LINE/RETURN + return values), the live
  call stack (per thread), and all variables of the current frame.
  On every line, the Event panel shows the variables that line
  mentions, with their values as of BEFORE the line executes (the
  line's effect appears on the next event). Branching lines also show
  their expression and the verdict, inferred from the branch execution
  actually took (always correct): `if`/`while` → True/False;
  `for` → "item #N" / "exhausted after N iterations" / "exhausted —
  0 iterations" (the loop that silently never ran, made loud; a
  `break` honestly produces no exhausted verdict); `except Type:` →
  "caught here" / "not this handler"; `match` cases → "matched" /
  "no match". Sub-line branching (ternaries, and/or short-circuits)
  is not visible to line-level tracing. All variables are
  rendered **semantically by type**: lists/tuples as rows of indexed
  cells (tuples rounded, sets dashed), dicts as key→value rows, nested
  structures recursively. Hover any value to see its Python type (and
  real size for containers).
- **Change highlighting is surgical**: only the deepest thing that
  changed lights up — the one swapped cell, the one dict entry, the one
  leaf inside a nested structure. Sets highlight only truly-added
  elements (membership, not position).
- **Alternate views**: when a variable's shape allows it, a small
  dropdown appears next to its name — `grid` renders a list-of-lists as
  a 2D table (DP tables, boards, matrices), `bars` renders a numeric
  list as bar heights (sorting!), `graph` renders adjacency structures
  as actual nodes and arrows, and `edges` renders a list of [u, v]
  pairs as a graph. Change highlighting carries over: the updated grid
  cell, swapped bars, or just-added edge glow. Your choice is
  remembered per variable per script (browser localStorage).
- **Graph view** recognizes generic shapes with no algorithm
  knowledge: `{node: [neighbors]}` dicts, `{u: {v: weight}}` weighted
  dicts (weights shown on edges), index-based `adj[i] = [j, k]` lists,
  weighted index-based `adj[i] = [(nbr, w), ...]` lists (neighbor
  position auto-detected), and `[[u, v], ...]` edge lists (ambiguous
  with adjacency — both options are offered; you know which one your
  data is). Directed arrows; reciprocal pairs draw as two offset
  arrows; self-loops as arcs. Offered only up to 60 nodes — beyond
  that a node-link diagram is a hairball and the tool honestly
  declines.
- **Traversal overlay**: on a graph-viewed variable, a second dropdown
  ("tint: …") lists the frame's other variables. Pick one and the graph
  colors itself by it — a `visited` set turns member nodes green (new
  members flash), a distance array like `D` badges every node with its
  current value (just-changed values flash amber), a queue/path list
  highlights the nodes it contains, a dict does membership + value
  badges. This is how you watch BFS/DFS/Dijkstra actually traverse:
  graph view on `adj`, overlay on `dist` or `visited`, play.
- **Objects (OOP code)**: class instances are no longer opaque. Their
  attributes (both `__dict__` and `__slots__` classes) appear as
  first-class rows — `self.adj_list`, `g.N` — each with its own view
  selector, so a graph stored inside an object gets the graph offer
  right where it lives. Nested objects render as attribute tables.
- **Large containers**: normally the first 30 elements are shown with a
  "+K" remainder cell. When a change happens beyond that head, the view
  automatically becomes a window centered on the change (±10 elements)
  with REAL indices and "…before/+after" edge cells — change element
  1500 of a 2000-list and you see cells 1490–1510 with 1500 lit.
  Limits: containers up to ~4096 elements are change-tracked; beyond
  that (and for deep mutations inside dict values), changes past the
  head may go unseen — this is a documented cost/honesty trade-off.
- **Bottom**: scrubber to jump anywhere in the run.

Controls: `⏮ Start · ◀ Back · Step ▶ · Over ⤵ · Out ⤴ · ▶ Play ·
speed · End ⏭`. **Over** advances to the next event in the SAME
function (an entire nested call becomes one click); **Out** jumps to
the caller's next event. Keyboard: `←`/`→` step, `O` over, `U` out,
`Space` play/pause, `Home`/`End` jump, `C` collapse/expand,
`B` bookmark the current event (cyan marks above the scrubber,
persisted per trace), `[`/`]` jump between bookmarks. The **collapse** button in the Variables panel
shows only the variables changing at the current event — use it when a
function has many locals and changes happen off-screen. Collapsing also
hides the call stack (it has its own hide/show button too). **Drag the
divider** between code and sidebar to resize; double-click it to reset.
Speeds are events per second: crawl 0.5 · slow 1 (default) · normal 3 ·
fast 12 · turbo 66.

A banner at the top tells you when something needs knowing: the run
crashed (trace kept up to the crash), the event cap truncated the
recording, or recording started at a trigger.

**The interpreter's hidden machinery** (see example_machinery.py):
- **Generators/coroutines tell the truth**: a suspension shows as a
  purple **YIELD** badge ("⇢ yields 0"), waking up as **RESUME** with
  the frame's full live state re-shown — one sleeping frame, one
  identity (life navigation and step-over follow it across naps).
- **Mutation vs rebinding**: a changed variable wears **↺** (the
  OBJECT changed in place — every alias changed too) or **↦** (the
  NAME now points elsewhere; the old object is untouched). Variables
  that are the same object under different names share a **🔗** glyph
  (hover lists the aliases). This dissolves the "why did a change when
  I touched b" mystery.
- **Closure cells**: **⛓↑** = this variable lives in the enclosing
  frame (nonlocal); **⛓↓** = shared with inner functions defined here.
- **⚠def** = this argument IS the function's shared mutable default
  (`def f(x, acc=[])`) — it persists across calls.
- **⚙ import time** appears next to the badge while executing inside
  another module's import — the interpreter's two lives, distinct.
- Dunder calls get a hint: "invoked implicitly by Python — <".

**Method resolution made visible (OOP).** On every method call where
inheritance is involved, the Event panel shows the class chain with
the lookup story: classes that were searched and passed are struck
through, and the class that actually SUPPLIED the method is lit green
— "started at Exporter, passed ZipMixin and JsonMixin, found export on
Serializer". Cooperative `super()` chains show successive suppliers
walking the chain (see example_mro.py / trace_example_mro.html).

**The density strip** (above the scrubber, colored per FILE) shows the
shape of the whole trace before you scrub it: which file each region
of the run lived in, clickable to jump. Red band then green band =
"main ran, then cart took over".

**Every variable has a navigable life.** Each row in the Variables
panel shows ‹ 3/6 › — its change ordinal and total within this frame.
‹ and › jump to the previous/next event where it changed (recursion-
safe: each invocation's variables are tracked separately). Click the
count to unfold the **life strip**: one tick per change on the trace
axis — birth in green, current position in amber — every tick
clickable. The debugging move: click a red crash marker, then walk the
suspicious variable's history backward to the moment it went wrong.

**Exceptions are first-class events.** Every raise — including ones an
`except` block catches — appears as a red EXCEPTION badge with the
type and message, and the raising line turns red. An uncaught
exception shows its full propagation path: one EXCEPTION event per
frame it unwinds through, from the raise to the crash. Silently
caught exceptions (the classic "why is this None?") are no longer
silent. Red markers above the scrubber show every hard exception in
the run — click one to jump straight to it. Generator/iterator
control-flow raises (StopIteration etc.) are shown dimmed, not red.

## 3. Events and the cap — what you see and what you don't

An *event* is one line **execution**, not one line of code: a 3-line
loop running 1000 times = ~6000 events. The trace is a complete,
gapless film from the start of execution — nothing is ever sampled or
skipped in the middle. The default cap of 200,000 events stops the
*recording and the run* when reached (the movie stops; it never has
holes). Raise it if needed:

```bash
python3 tracer.py --max-events 1000000 script.py   # ~2M is the practical max
```

But for big executions, don't film everything — start filming at the
interesting part:

## 4. Triggers (conditional recording — the "red dot that starts the camera")

Nothing is recorded until the trigger fires; then everything is,
beginning with a reconstruction of the live call stack and all current
variables (they appear as the first events' "changed" set). Watching
for a trigger is ~100× cheaper than recording, so skipping millions of
events costs almost nothing.

```bash
# start at the first execution of line 30 of solution.py
python3 tracer.py --start-at solution.py:30 solution.py

# start at the 57th execution of that line
python3 tracer.py --start-at solution.py:30 --start-count 57 solution.py

# start the first moment a condition on your variables becomes true
python3 tracer.py --start-when "current_sum > 6000" solution.py

# combined: at line 13 only, when the condition holds, on its 2nd occurrence
python3 tracer.py --start-at solution.py:13 --start-when "d[k] > q[k]" --start-count 2 solution.py
```

Notes:
- The LAST argument is always the program to run (full path fine).
  `--start-at` takes just a filename:line label to match — it only
  differs from the script when the trigger lives in an imported file:
  `python3 tracer.py --start-at helpers.py:42 main.py`
- `--start-when` is a Python expression evaluated with the frame's
  variables. A variable that doesn't exist yet simply means "not yet".
  With `--start-at` it's checked only at that line (cheap); standalone
  it's checked at every line (slower but finds the moment anywhere).
- If the trigger never fires, the tracer tells you, and the viewer
  banner reminds you that pre-trigger execution is not in the trace.

## 4b. Big codebases: scoping and function granularity

```bash
# trace only these files (globs, project-relative or bare filename)
python3 tracer.py --include 'cart.py' --include 'pkg/*' main.py
python3 tracer.py --exclude 'tests/*' main.py      # mapper speaks the
python3 mapper.py --exclude 'b.py' myproject       # same vocabulary

# function granularity: calls/returns/exceptions only — no line events,
# no locals machinery. This is how you trace a 200k-line codebase.
python3 tracer.py --granularity fn main.py
```

On Python 3.12+, add `--backend monitoring` to fn mode: same trace,
same viewer, but recorded through PEP 669 `sys.monitoring` — code
outside your project is switched off at its first event and never
pays again, cutting tracing overhead ~3× (more on stdlib-heavy runs).
Suspensions and resumes arrive as first-class interpreter events
there, so it is also the future-proof engine.

fn traces carry **microsecond timestamps**: every return shows
"took 1.24 ms" in the viewer, and call events record shallow argument
values. Honesty rule: line-level traces have NO timestamps — under
line tracing the program runs ~100× slow, so wall times there would be
fiction. Time lives only where it's true. (Triggers --start-at/-when
need line events and can't combine with fn mode.)

## 4c. asyncio tasks and the Perfetto bridge

Tasks are **pseudo-threads**. When your program uses asyncio, every
event records which task drove it, and the viewer gives each task its
own lane with its own call stack — stepping through the trace shows
the stacks alternating as the event loop switches between tasks. The
badge area says `in task producer`; a task frame's Out button stays
put (its caller is the event loop, not your code). Name your tasks
(`asyncio.create_task(coro, name="worker-A")`) and the lanes inherit
the names; unnamed ones show as Task-1, Task-2…

A suspended coroutine is ONE sleeping frame: `await` shows as YIELD,
waking up as RESUME (same machinery as generators), the frame keeps
its identity and re-emits its full live state on every resume — after
sleeping through the other task's mutations, what you see is current,
never stale. (Re-emitted values are shown quietly, not highlighted:
"fresh info" is not "changed".) At fn granularity, durations tell the
whole truth: a yield says "slice took X", and the final return says
"last slice X · active Y across N slices". Try it:

```bash
python3 tracer.py example_tasks.py
```

**Perfetto export** hands an fn-granularity trace to a professional
million-event timeline (https://ui.perfetto.dev — the trace never
leaves your machine; the UI processes it locally):

```bash
python3 tracer.py --granularity fn --export-perfetto out.json main.py
# then open ui.perfetto.dev and drag out.json in
```

One timeline row per thread·task lane; call/return become begin/end
slice pairs with argument and return-value summaries; exceptions are
instant markers; an awaiting coroutine's slice closes at the yield and
reopens on resume, so suspension shows as a real gap in the row.
Honesty rule as always: line traces carry no timestamps, so
`--export-perfetto` refuses to run without `--granularity fn`.

**Who woke whom (the ⤳ arrows).** Every trace records the wake edges
as first-class events: thread started/joined, asyncio task created
(`create_task`, `ensure_future`, `gather` and `TaskGroup` all funnel
through the same door). In the replayer a **⤳ WAKE** badge names the
edge and offers a jump to its other end; in the Perfetto export the
edges become real flow arrows drawn between lanes. Threads can outrun
their own `start()` call — the edge is recorded before the OS gets the
child, so the wake always precedes its consequences in the stream.

## 4d. The reliability lab & the instruments (2026-08)

**Run it N times (`--runs`).** One run is an anecdote. `python3
tracer.py --runs 20 flaky.py` executes the target 20 times (fn
granularity by default, identical stdin each run), classifies every
outcome by exception type + crash site, and writes `runs_flaky.html`:
an outcome bar, wall-time distributions per class (min/median/p95/max —
labeled tracer-inclusive), and ONE kept, replayable trace per distinct
behavior. Exit code 0 only when every run is clean, so it drops
straight into `git bisect run`. Ctrl-C reports what completed.

**The suspects (SBFL).** When a run set contains both passing and
failing runs, the report grows THE SUSPECTS: every executed line
ranked by how exclusively the failing runs execute it (Ochiai), each
suspect deep-linked into a kept failing trace at that line. It is
correlation, not causation — the report says so — but the top of the
table is where to read first: the statistics do the boring half of
debugging before you open a single file.

**Find where two runs part ways (`--diverge`).** `python3 tracer.py
--diverge good.html bad.html` canonicalizes both event streams
(timestamps and memory addresses stripped) and reports the first
mismatch at two depths: STATE — the same line runs but its values
differ (usually the cause; the differing variables are named with both
values) — and CONTROL — a different line runs (the symptom). It prints
deep links that open both traces at the divergence. The natural
pipeline: `--runs`, then diverge a kept clean trace against a kept
failing one.

**Turn any question into an exit code (`--check`).** `python3
tracer.py --check "total < 0" script.py` watches the expression two
ways in one run: per line, against the frame's variables (like
`--start-when`), and once at end-of-run against the run FACTS —
`error`, `exc`, `events`, `output` (the console text), `hit`, `hits`,
`tests_failed`, `truncated`. Exit 1 the moment either says yes; 0
clean; **3** when the expression was never evaluable anywhere — a typo
must never look like a clean run. That is exactly the yes/no oracle
`git bisect run` wants: find the commit that introduced a warning with
`--check "'deprecated' in output"`, no test required; compose with
`--runs` and you can bisect a *rate* change in flaky behavior.

**Make the race fire (`--chaos-schedule SEED`).** A latent race
survives almost every natural schedule — the torn window is a few
bytecodes wide. Chaos injects seeded stalls and GIL yields at traced
event boundaries, jitters the thread switch interval, and (under
asyncio) shuffles each loop tick's ready queue: it biases *which*
legal interleavings you explore without touching your code, and the
trace is labeled **⚡ PERTURBED** (timings under chaos are not
performance truth; `--export-perfetto` is refused). With `--runs N`,
run i gets seed SEED+i−1 — diverse exploration, every child
reproducible from the seed in its own Reproduce box. The bundled
`example_race.py`: 12/12 clean naturally, 11/12 conservation-broken
under chaos — the race that "never happens", as a rate.

**Catch the first NaN at birth (`--trip nan`).** For numerical code
the crash site is thousands of operations downstream of the mistake.
`python3 tracer.py --trip nan sim.py` marks the event where each
variable's poison is BORN (clean→inf, clean→nan, inf→nan; recoveries
re-arm; returns carry poison out of frames): a banner names the first
birth, amber ☢ pins mark the scrubber, the poisoned row wears ☢ at
exactly its transition. Only what encoded values visibly show is
judged — beyond a cap or window is unknown, unmarked.

**The oscilloscope (chart view).** Any numeric variable's dropdown now
offers `chart`: its whole life as the step function it really is —
clickable change points, NaN/±Inf as edge ticks, non-numeric gaps
counted, crash/trip moments tick-aligned, honest log scale (refused
unless every value > 0). Pick a partner variable ("vs …") for a phase
portrait: the x-vs-y trajectory fading into the past. `example_prefix.py`'s
`running` vs `i` is the two-second demo.

**Deep links.** The address bar now follows the replay:
`trace_x.html#ev=8412&var=dist&view=graph&ov=seen`. Copy it into an
issue and the reader lands on that event with that view open. Works on
a fresh load and on an already-open trace (edit the hash). Every
moment any tool above names is therefore shareable.

## 4e. The replayer grows: chapters, console, query, whyline, schemas (2026-08)

**Per-test chapters.** `python3 tracer.py -m pytest tests/` now
dissects the suite: colored chapter spans over the scrubber (green
pass, red fail), every event labeled with its owning test, TEST ▶/✓/✗
badges in the stream. And the killer join: per-test coverage × per-test
outcomes = the SUSPECTS from a single suite run, ranked in the banner,
clickable straight to the guilty line inside the failing test's span.

**The console lane.** Every line the target prints to stdout/stderr
becomes an event tied to the frame that wrote it. The replayer's
Console panel fills as the replay advances — output appears when it
appeared, WARNING/ERROR colored from the recorded text — and clicking
a line jumps to the moment it was written, stack and variables live.
`--no-console` disables; caps are announced; writes below the Python
layer (raw `os.write`) bypass the tee, and the trace says so.

**The query bar.** Press `/` in any trace: `type:exc file:cart.py`,
`changed:total total<0`, `fn:lookup`, `after:5000 mut:items`, or a
bare word to match source text — terms AND-compose, hits become
magenta pins on the scrubber, Enter cycles through them. Value tests
look at recorded CHANGE moments (the facts, never interpolation), and
a typo'd prefix is reported as a typo, never a silent zero hits.

**The whyline.** Click the line *number* of a line that never ran and
the viewer answers why not: the innermost guard that controlled it,
with its recorded verdict counts — "ran 12× — 0× true — this branch
was never chosen" — walked upward one controller at a time, each step
jumpable to where execution actually arrived. Click an executed line's
number and you jump to its first execution. Line granularity (under fn
the panel says why it can't answer).

**Boundary schemas.** Every trace aggregates each function's observed
interface — the structural *shape* of arguments and returns (`dict{qty,
price}`, `list[dict{sku, qty}]`), never values. Stable interfaces show
their signature on call/return events; a wobbling one wears ⚠ with the
distribution ("dict 13× / NoneType 1×") and jump links to the deviant
calls, and the terminal summarizes every unstable interface after the
run. The wrong-shape payload gets caught at the border, not five
frames downstream.

## 4f. Recording for real life: the black box, the capsule, the chunks (2026-08)

**The flight recorder (`--black-box`).** Recording becomes a ring
buffer of the last `--max-events` events: the run is never truncated,
only the ring's own memory, and the banner counts what rotated out
("the film starts mid-run"). `kill -USR1 <pid>` dumps the current
window as a normal trace WITHOUT stopping the run; the end or a crash
writes the final window. In-process: `watch(ring=N)`. Pay ~nothing
forever; have the film when it matters.

**The reproducibility capsule.** Every trace embeds the run's
identity: exact command, cwd, python/platform, `PYTHONHASHSEED` (with
a random-order warning), curated env keys — and the stdin bytes the
run actually consumed, captured lazily so a never-closing pipe cannot
hang the start. The viewer's Reproduce box prints the rerun command
and offers `stdin.bin` for download: every trace is a specimen someone
else can rerun, not just a report.

**Chunked traces + keyframes.** Past 100k events the artifact
auto-chunks: events move into gzip+base64 blocks (files shrink 5–25×)
and the replayer seeks from state keyframes instead of replaying from
event zero. Invisible when healthy — a missing chunk is announced
loudly — and every reader (`--runs`, `--diverge`, map heat,
`checks.py`) understands the format. `--chunked`/`--no-chunked`
forces; replay needs `DecompressionStream` (Chrome 80+ / Firefox 113+
/ Safari 16.4+).

## 5. Recipes

```bash
# Whole small script, watch everything
python3 tracer.py test1.py

# AtCoder solution with sample input
python3 tracer.py solution.py < sample1.txt

# Long run, only care about the end phase
python3 tracer.py --start-at solution.py:32 solution.py < big.txt

# Hunt: "when does x ever go negative?"
python3 tracer.py --start-when "x < 0" script.py

# Compare two runs: trace, edit code, trace again → trace_x.html and
# trace_x_2.html, open both in two browser tabs

# Which commit broke it? A trace predicate as the bisect oracle
git bisect run python3 tracer.py --check "tests_failed > 0" -m pytest tests/

# Long-running process: keep only the last 200k events, snapshot live
python3 tracer.py --black-box --max-events 200000 server.py
kill -USR1 <pid>    # dumps the current window; the run continues
```

## 6. Field guide: studying a codebase you didn't write

The two layers have different prices. The **map is free** — nothing
runs, no dependencies needed. The **tracer executes the code**, so it
needs what any run needs: the project's dependencies and a valid entry
point. This recipe is the distilled path (battle-tested on PyTheus, a
quantum-optics research codebase):

```bash
# 0. Map first — free, and it does the recon for you
python3 mapper.py path/to/repo
```

Read three things off the map before running anything: the **walls**
(what everything depends on), the **▸ self-running modules** (built-in
entry points), and the bottom-note line **"⚠ not importable here:
numpy, …"** — the mapper statically collects every external import and
checks (without executing anything) which ones your current
environment can actually satisfy. That line is tomorrow's crash,
announced today.

```bash
# 1. Give the code its dependencies, in a venv
python3 -m venv .venv && source .venv/bin/activate
pip install -e path/to/repo      # pulls what the project declares
python3 mapper.py path/to/repo   # re-map INSIDE the venv: the ⚠ line
                                 # should now be gone
```

```bash
# 2. First run — the ⌖ writes it for you
```
Click ⌖ on any module: self-running modules get complete commands;
library modules get an entry **borrowed from a runnable importer**;
worst case you're told which pytest-style tests import it. Expect the
first run to fail honestly once or twice — each failure names the next
step: a missing dep (install it), a legacy dep (PyTheus needed
`pip install "setuptools<81"` for `pkg_resources`), or a **missing
data file** (authors' debug scripts often read inputs they never
committed — look for shipped examples/configs and copy one into
place).

```bash
# 3. The real trace + self-heating map
python3 tracer.py --granularity fn --backend monitoring /abs/path/entry.py
python3 mapper.py path/to/repo   # auto-heat adopts the newest trace
```
Long optimizations/simulations: the event cap (default 200k) is your
exit valve, and Ctrl-C keeps a valid partial trace.

```bash
# 4. Microscope the hot spot the heat exposed
```
Click the hot module's function row — the composed command scopes with
`--include` (patterns are relative to the TRACE root, i.e. the entry
script's folder) and `--start-at`, with a line-level cap. Then read
values, verdicts and mutations event by event.

## 6b. Current limits (by design, for now)

- One process; threads are traced, but `multiprocessing` children are not.
- Values are shown as truncated reprs (~120 chars, 20 container items).
- Line-level tracing slows the target ~100×: use triggers/caps for
  anything big. The funnel is mostly self-contained now: find WHERE
  cheaply with the static map, then a `--granularity fn` trace
  (near-free, `--backend monitoring` on 3.12+) whose **heat** overlay
  shows where the time and the exceptions concentrate — then let ⌖
  aim the line-level microscope at that one spot. External *samplers*
  like py-spy still add something pyreplay can't: attaching to an
  already-running process (we always launch the script ourselves).
