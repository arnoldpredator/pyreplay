# pyreplay — user guide

Two tools, one contract. `tracer.py` records a real execution of your
program into a self-contained `trace_*.html` you replay in any
browser; `mapper.py` reads a codebase with `ast` — nothing executes —
into a `map_*.html` that later adopts traces as a heat overlay. Both
files must sit next to their templates (`replayer_template.html`,
`map_template.html`); you never open a template directly, only the
generated files.

This guide is ordered the way you use the tool — the funnel, wide
and cheap first: map the codebase (free, nothing executes), record a
run, heat the map and let it aim you, then descend into the
replayer's depth as the questions get harder. Part numbers match the
feature catalog (FEATURES.md).

## The philosophy — an observatory, not a lens

Most debugging tools are one lens: a profiler shows time, a debugger
shows one moment, a log shows what you thought to print. pyreplay is
built as an **observatory with a funnel doctrine**: many instruments
that compose, ordered wide-and-cheap first, narrow-and-expensive
last. One full descent through it looks like this:

**`--fuzz` finds a failure** (seeded, reproducible) → **`--shrink`
cuts the input to the tiny core that still fails** → **an oracle
judges the output** (`--oracle` against a reference implementation,
or a `--relation` symmetry when no reference exists) → **a violation
hands you `--diverge`, which pins the FIRST event where two runs
part ways** (the cause, before the symptom) → **the provenance panel
and the whyline explain where that wrong value came from** →
**the map shows where it all lives in the architecture** (heat,
walls, dark edges) → **the memory palette shows what it retained**
(`--memory`, lens → memory (bytes)).

Every arrow is a real handoff: the finishing stage prints the exact
next command — scoped, seeded, ready to paste, and deliberately
never auto-run. You stay the scientist; the tool hands you the next
instrument and teaches the funnel by doing so. Underneath all of it
sits one contract that makes the composition trustworthy: **the
display marks only what was actually recorded.** Partial state stays
unmarked rather than guessed, and every cap, window and truncation
announces itself on screen. You can only stack seven instruments
into one investigation if you can trust every single cell — so that
trust is the load-bearing feature.

---

## Part 1 — The static map

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

**The project call graph (#16).** The map now resolves calls at
FUNCTION level across the whole codebase: from-imports, module
attributes, and `self.method()` within its own class become
`module:def → module:def` edges, each labeled resolved or guessed
(name not found in the target module), with everything the parse
cannot attribute counted and named as the trace's job. The walls
panel ranks the **load-bearing functions** by cross-module fan-in —
on nengo that crowns `ValidationError` (←135 sites from 26 modules)
and `Signal` (←133), invisible in module counts. Click a row to
spotlight its module.

**The graph lens (#15) — graph theory over the map's own graphs.**
The lens select gains *graph (structure)*, available on any map of
two or more modules: boxes tint violet by **betweenness centrality**
(Brandes — the modules import paths route THROUGH; fan-in counts
doors, this counts corridors) and wear their detected **community's**
border color (label propagation) — compare the borders against the
package boxes and "is the architecture real?" becomes a picture. The
walls panel gains the ⛓ betweenness ranking beside fan-in (they
routinely crown different walls: on nengo, fan-in picks
`nengo.exceptions`, betweenness picks `nengo.base` and
`nengo.simulator`), a second ranking on the observed call-pair graph
when a trace is adopted (each list names its graph), the 💥
**dependency-fragility curve** (remove the top-k most-between
modules, initial ranking — watch the giant component collapse; a
cliff is a wall the fan counts missed), and the degree distribution
with its caution: this few points prove no power law.

---

## Part 2 — Record a run

The tracer records a Python program's execution — every line, call,
return, and variable change — into a single self-contained HTML file
you can replay in any browser: step forward/back, play at chosen
speed, scrub anywhere.

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

### Events and the cap — what you see and what you don't

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

### Triggers — the red dot that starts the camera

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

### Big codebases: scoping and function granularity

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

**The PEP 669 line engine.** On 3.12+, `--backend monitoring` now
traces lines too: in-scope code objects get LINE events armed
per-code, out-of-scope code costs one disabled event instead of a
callback per line — on codebases where most executed Python is not
yours, total overhead roughly halves. The trace is event-for-event
identical to the settrace engine with one stated exception, bannered
when it applies: an inlined comprehension (PEP 709) runs within a
single line event, so its per-iteration variables are not
re-observed — switch back to the default engine to watch a
comprehension iterate.

### Recording for real life

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

## Part 3 — The cockpit: heat & the funnel

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

**Dark edges (#39) — the blind spot, drawn.** When the map adopts a
trace, every cross-module call the run actually made is diffed against
the static routes. Pairs with no static route — dispatch tables,
callbacks, plugin registries, `importlib` — appear as dashed **⚡ dark
edges** with call counts, on their own toggle; the banner counts them,
and modules containing `__import__`/`import_module` call sites wear a
⚡ flag up front ("target unknown until a run is traced"). The old
honesty note about unresolvable calls becomes a picture — with its own
honesty rule attached: the absence of a dark edge is never evidence of
absence, only the adopted runs' testimony.

**The startup autopsy (#40).** With an fn trace adopted, the walls
panel grows a **⚙ startup autopsy**: the time inside each module's
`<module>` frame — its import cost, cumulative on purpose — ranked
with click-to-spotlight rows and the total in the banner. Slow CLI
startup is pure import cost and nobody knows whose; the data was in
every fn trace all along. Line traces carry no wall times, so the
autopsy is honestly absent there.

## Part 4 — Read the replay

Open the generated HTML in a browser. Layout:
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

**The density strip** (above the scrubber, colored per FILE) shows the
shape of the whole trace before you scrub it: which file each region
of the run lived in, clickable to jump. Red band then green band =
"main ran, then cart took over".

**The compressibility strip.** Under the density strip, every trace
of ≥50 events wears a second, thinner strip: gzip bits/event per
bucket — the run's regularity, measured. Dark = a tight loop (low
entropy), bright = data-dependent wandering, and a marked change in
brightness is a phase change in the run, findable by eye before you
know what to look for. Hover for exact bits/event and ratio, click
to jump. The tooltip's rule, verbatim: gzip length is an upper bound
on the entropy rate — the strip says "compressibility", never bare
"entropy".

**Per-test chapters.** `python3 tracer.py -m pytest tests/` now
dissects the suite: colored chapter spans over the scrubber (green
pass, red fail), every event labeled with its owning test, TEST ▶/✓/✗
badges in the stream. And the killer join: per-test coverage × per-test
outcomes = the SUSPECTS from a single suite run, ranked in the banner,
clickable straight to the guilty line inside the failing test's span.

**Deep links.** The address bar now follows the replay:
`trace_x.html#ev=8412&var=dist&view=graph&ov=seen`. Copy it into an
issue and the reader lands on that event with that view open. Works on
a fresh load and on an already-open trace (edit the hash). Every
moment any tool above names is therefore shareable.

**The query bar.** Press `/` in any trace: `type:exc file:cart.py`,
`changed:total total<0`, `fn:lookup`, `after:5000 mut:items`, or a
bare word to match source text — terms AND-compose, hits become
magenta pins on the scrubber, Enter cycles through them. Value tests
look at recorded CHANGE moments (the facts, never interpolation), and
a typo'd prefix is reported as a typo, never a silent zero hits.

## Part 5 — Variables & data structures

Every value is rendered semantically by its shape, and only the
deepest thing that changed lights up:
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
- **Graph-shaped data and the ✂ mark**: object attributes are
  deliberately depth-transparent, so a node whose attribute holds
  nodes holding more nodes could multiply the caps above into
  megabyte values. One total budget (~8 KB) now spans each recorded
  value: where it runs out, descent stops and the spot shows its repr
  with a **✂** (hover it for the rule). A ✂ on the value itself means
  "somewhere inside, structure was withheld". Primitives are never
  cut, values that fit are untouched, and the fix when you care about
  a cut region is free: step to an event where that inner object is a
  variable of its own — a fresh value gets a fresh budget.

**Every variable has a navigable life.** Each row in the Variables
panel shows ‹ 3/6 › — its change ordinal and total within this frame.
‹ and › jump to the previous/next event where it changed (recursion-
safe: each invocation's variables are tracked separately). Click the
count to unfold the **life strip**: one tick per change on the trace
axis — birth in green, current position in amber — every tick
clickable. The debugging move: click a red crash marker, then walk the
suspicious variable's history backward to the moment it went wrong.

**The records table.** A list of dicts with uniform keys (or of
same-length tuples) gains a **table** option in its view select: one
column per key, the changed cell highlighted alone at each event,
window honesty inherited. Column headers sort — display only: the row
numbers keep the data's true order and the note under the table says
so. Query rows, CSV rows, API responses: read them as the table they
are, while the diff machinery keeps working per cell.

**The oscilloscope (chart view).** Any numeric variable's dropdown now
offers `chart`: its whole life as the step function it really is —
clickable change points, NaN/±Inf as edge ticks, non-numeric gaps
counted, crash/trip moments tick-aligned, honest log scale (refused
unless every value > 0). Pick a partner variable ("vs …") for a phase
portrait: the x-vs-y trajectory fading into the past. `example_prefix.py`'s
`running` vs `i` is the two-second demo.

**Watch expressions (`--watch`).** `--watch "sum(nums)"` evaluates the
expression at every line event, at *record* time where Python is
alive, and stores it as a synthetic variable — change highlighting,
life navigation and the chart view come free. A conserved quantity
changes once at birth and never again; that silence is the signal.
Frames where it isn't evaluable record nothing; a watch that dies
mid-frame records "(not evaluable here)"; one that never evaluates
anywhere warns at the end. They run inside your process — keep them
pure, and scope the per-line cost with `--include`.

**Shapes and dtypes.** Arrays are C-opaque to the tracer — but their
`.shape` and `.dtype` are read at every Python boundary and ride the
encodings: teal ⤢ chips on every numpy/torch/pandas value, and when a
name's own metadata transitions, the badge tells the story —
SHAPE-CHANGE (3, 4) → (4, 3) at the exact event of the silent
transpose, DTYPE-CHANGE float64 → float32 at the astype. Broadcasting
bugs live exactly there, and now they look like something.

**Type flow.** Every name's observed types are tallied across its
changes: a row that ever held more than one type wears **⚠τ**, the
tooltip shows the histogram, and a click lands on the first moment of
the rarest type — the sneaky None found where it was born, not where
it exploded. The terminal ranks the unstable names after every run.

## Part 6 — Control flow: what decided

Every branching line shows its expression and the recorded verdict
(see the Event panel notes in Part 2). The instruments below build
on those verdicts.

**The ghost branch.** Flip 👻 in the badges menu and every verdict
moment shows what did NOT happen: the untaken arm dims under a
hatched wash for exactly that one step — the else skipped, the loop
body that never ran (`for v in []:` finally *looks* like what it is),
the handler that didn't match. Nested code inside the untaken arm
dims with it. It clears the instant you step on.

**The whyline.** Click the line *number* of a line that never ran and
the viewer answers why not: the innermost guard that controlled it,
with its recorded verdict counts — "ran 12× — 0× true — this branch
was never chosen" — walked upward one controller at a time, each step
jumpable to where execution actually arrived. Click an executed line's
number and you jump to its first execution. Line granularity (under fn
the panel says why it can't answer).

**The anatomy panel.** Open **Anatomy** in the side bar of any
line-granularity trace and the current line is dissected into the
layer above it and the layer below it: SYNTAX — the enclosing
function's AST tree, the current line's path pre-opened and its nodes
lit (`If → Compare > → Subscript`); INSTRUCTIONS — the function's
`dis` listing scrolled to the current line's rows, `»` marking jump
targets. The interpreter stops being magic: a compare is two loads
and a COMPARE_OP, a tuple swap is a pack and an unpack. The header
is honest about what you're reading — "as compiled, not adaptive",
with the CPython version: the specialized opcodes the adaptive
interpreter may have quickened at run time are not these rows. Under
fn granularity the panel says why it can't answer (no current line).

**The CFG.** Below the instructions, the same panel draws the
function as the graph it is: blocks laddered in line order, edges
typed and colored (true/false drops, loop and continue back arcs,
break and exception arcs), and the run drawn onto it — every observed
edge solid with its ×N traversal count, the current block lit as the
replay advances. Never-observed edges are dashed ghosts; blocks with
no static path from entry are red-dashed "unreachable by
construction" — the graph never conflates the two. Click any block:
if it ran, you jump to its first execution; if it never ran, the
whyline answers with the guards that said no. The for-else you were
never sure about, the break that skips it: drawn, with counts.
Prefer the classic look? The select on the CONTROL FLOW header
switches the same graph to a **flowchart** skin — diamonds, yes/no
labels, rounded terminals — and the select on SYNTAX turns the tree
into a **Nassi–Shneiderman structogram**: if splits into T|F columns,
loops band their bodies, every guard wears its recorded T×/F× counts,
and lines that never ran are dimmed. Skins only: the same recorded
blocks, edges and verdicts underneath — the note under each says so.

**The decision table.** Under the CFG, the same panel condenses the
function's branching into DECISIONS — OBSERVED TRUTH: one row per
guard — every if/elif/while/for, every except clause, every case
pattern — with how often it ran, how often it went true, how often
false, each count a click to its first occurrence. The flags do the
reading for you: a `for` over an empty list wears **never true** (the
invisible loop), a loop that always `break`s wears **never false**
(never exhausted), a case that nothing matched wears **never ran** —
and clicking that row asks the whyline why not. It reads
whole guards only: the sub-conditions of `a and b` are not separated
(the monitoring engine records them — see the sub-line verdicts below), and for-rows count
entered/exhausted rather than true/false.

**Sub-line verdicts.** Under the monitoring engine (Part 2), the parts of a line get
their own truth: every ternary test, every `and`/`or` operand, every
comprehension `if` records a BRANCH event at its exact columns.
Stepping onto one shows the sub-expression underlined in its verdict
color; the DECISIONS table grows ↳ sub-rows per guard — and when an
operand was evaluated fewer times than its guard ran, that difference
IS the short-circuit, measured. Under the default engine these events
simply don't exist, and the table says so instead of pretending.

## Part 7 — Causality: where values come from

**The backward slice (✂).** The provenance row's "← from a, b" is one
hop; the **✂ slice** button beside it iterates to closure — every
recorded event that contributed to the clicked value, drawn as green
pins on the scrubber, with ←/→ walking the slice instead of the
stream and Esc exiting. The walk crosses call boundaries through
return values into the callee's own chain; what name-flow can't
cross — attribute/subscript writes, in-place mutation, caller
arguments — becomes a listed **frontier stop**, never a silent gap.
A 10k-event trace collapses to the dozen events that made one value.

**Forward taint.** The slice's twin: pick a value — a config field,
an input, a constant you're about to change — press **⇢ taint** on
its row, and every recorded event it influenced lights the strip:
violet where the data flowed (assignments, and `y = f(x)` through the
call), pink where a *decision* read it, hollow where a tainted
decision merely chose which line ran. That last distinction is the
honest one: control influence is displayed, never propagated as data.
Overwrite the name from clean sources and the taint dies — the kill
is part of the answer to "what would changing this touch?".

**The subproblem DAG (`--memo`).** Dynamic programming is
shortest-paths-in-DAGs, and the DAG is the part nobody ever sees.
Bind the table — `--memo dp` — and the **Subproblem DAG** panel draws
it: cells laid out as the DP table itself (2-integer keys) filling
CAUSALLY as you replay — unwritten cells dim, the just-written cell
lit, read→write dependency arrows appearing statement by statement.
The grid view shows fill order; this shows fill causality. Edge
colors carry the honesty: amber ⚠ means the read saw a cell's
*initialization* value, not a computed one — a rolling array does
that on purpose, a forward recurrence doing it is usually the wrong
evaluation order; the tool states the fact and never guesses intent.
Gray dashed = legitimate base-case reads of bulk-initialized cells.
Frontiers (slice writes, call-bearing indexes, aliased writes,
dependencies routed through calls) are counted and stated, never
guessed.

## Part 8 — The interpreter's hidden machinery

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

## Part 9 — Truth & alarms

**Exceptions are first-class events.** Every raise — including ones an
`except` block catches — appears as a red EXCEPTION badge with the
type and message, and the raising line turns red. An uncaught
exception shows its full propagation path: one EXCEPTION event per
frame it unwinds through, from the raise to the crash. Silently
caught exceptions (the classic "why is this None?") are no longer
silent. Red markers above the scrubber show every hard exception in
the run — click one to jump straight to it. Generator/iterator
control-flow raises (StopIteration etc.) are shown dimmed, not red.

**The console lane.** Every line the target prints to stdout/stderr
becomes an event tied to the frame that wrote it. The replayer's
Console panel fills as the replay advances — output appears when it
appeared, WARNING/ERROR colored from the recorded text — and clicking
a line jumps to the moment it was written, stack and variables live.
`--no-console` disables; caps are announced; writes below the Python
layer (raw `os.write`) bypass the tee, and the trace says so.

**Catch the first NaN at birth (`--trip nan`).** For numerical code
the crash site is thousands of operations downstream of the mistake.
`python3 tracer.py --trip nan sim.py` marks the event where each
variable's poison is BORN (clean→inf, clean→nan, inf→nan; recoveries
re-arm; returns carry poison out of frames): a banner names the first
birth, amber ☢ pins mark the scrubber, the poisoned row wears ☢ at
exactly its transition. Only what encoded values visibly show is
judged — beyond a cap or window is unknown, unmarked.

**Float hygiene.** Every line trace flags float `==`/`!=` at the
moments it executed — the guard's operand held a float right there,
says the pink pin — plus the statically provable float-literal sites.
And `--probe-reduction values` runs the physicist's experiment on the
recorded list: the sum as your program ordered it, sorted both ways,
twenty seeded permutations, `math.fsum`, and the exact rational sum
(floats are exact binary rationals — `Fraction` adds them without
error). The spread is the conditioning of your data, measured —
evidence of sensitivity, never proof of error, and refusals come with
reasons (windowed lists, NaN, fn granularity).

**Continuous invariants (`--invariant`).** The contract you don't
edit into the code: `--invariant "balance >= 0"` is checked at every
line event where its names are in scope, and each *entry* into
falsehood becomes an amber ⚖ event carrying the offending values —
the run continues, recovery re-arms, a stay-broken contract records
once. The banner gives every invariant its verdict: violated N× with
a jump, held everywhere it was evaluable, or never evaluable (the
typo case). Compose with `--check` and `git bisect` finds the commit
that first broke the contract.

**Invariant mining (⚗).** Every line trace now mines itself: a
template library (constants, types, signs, lengths, sorted-at-return,
per-call monotonicity, order pairs among numeric arguments) is checked
against everything the trace recorded — a candidate dies on its first
counterexample, survivors appear with their support on the function's
call/return events: `cap == 100 at entry 5× · cap >= k 5× · return
value sorted (ascending) 5×`. That is executable documentation — what
the code *actually* guaranteed in these observations — and a bug
detector: mine your clean runs (`--runs 20 --mine`, mined section in
the runs report), and the run that breaks a mined fact is your
suspect; `--diverge` the pair. `tracer.py --mine a.html b.html` mines
existing traces offline (support sums; JSON sidecar). The honesty
label rides every surface: held in N observations — an observation,
never a proof. Noise is controlled by design: constants suppress what
they imply, machinery objects are never mined, windowed containers
are never judged.

**The observed state machine (`--fsm`).** Declare ONE state variable —
`--fsm "order.status"` — and the trace mines its transition diagram:
the **State machine** panel draws states sized by dwell, edges
weighted ×N (click = jump to the first occurrence), and lights the
current state as the replay advances. Add `--fsm-declare
lifecycle.txt` (`FROM -> TO` lines) and the diagram becomes a
checker: every transition you never declared turns red AND lands in
the stream as a derived viol event — amber badge, scrubber pins,
`type:viol` in the query bar. `--runs N` merges all runs into one
machine in the runs report. The rule under the diagram, verbatim:
observed machine ⊆ true machine — a missing edge is never evidence
of absence. The refund path nobody drew on the whiteboard shows up
as one red arrow with a pin at the exact moment it happened.

**Boundary schemas.** Every trace aggregates each function's observed
interface — the structural *shape* of arguments and returns (`dict{qty,
price}`, `list[dict{sku, qty}]`), never values. Stable interfaces show
their signature on call/return events; a wobbling one wears ⚠ with the
distribution ("dict 13× / NoneType 1×") and jump links to the deviant
calls, and the terminal summarizes every unstable interface after the
run. The wrong-shape payload gets caught at the border, not five
frames downstream.

**The nontermination detector.** Poincaré's rule, applied: a closed
system that returns to a previous state must repeat forever. Every
line trace fingerprints the frame at each loop head; an exact repeat
raises the banner — "⟳ PROVEN CYCLE: iteration state at event 23
identical to event 8, period 15 events · 5 iterations", with jumps
to both ends. PROVEN holds itself to a hard standard: a while-loop
statically free of calls/attributes (C calls are invisible to the
recorder), complete encodings, a quiet window; anything else says
"state recurring at line level" and names every reason — for-loops
always carry the iterator caveat. Run the suspect with --max-events:
the cap catches the hang and the trace holds the cycle.

## Part 10 — Concurrency & time

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

**The critical path (★).** A concurrent fn trace names the chain that
determined its wall time: every microsecond is attributed to the
innermost slice open anywhere in the process — under the GIL, that
spine *is* the computation's critical path, crossing lanes exactly
where awaits and joins handed control over. The banner gives the
verdict ("16 slices across 4 lanes determined the 62.3 ms run —
28.5 ms of it untracked external waits"), gold scrubber pins walk it,
and the Perfetto export gains a dedicated ★ row with the spine read
left to right. Speeding up anything off the path is wasted work — and
instants where nothing traced ran are counted as waits, never hidden.

**Who woke whom (the ⤳ arrows).** Every trace records the wake edges
as first-class events: thread started/joined, asyncio task created
(`create_task`, `ensure_future`, `gather` and `TaskGroup` all funnel
through the same door). In the replayer a **⤳ WAKE** badge names the
edge and offers a jump to its other end; in the Perfetto export the
edges become real flow arrows drawn between lanes. Threads can outrun
their own `start()` call — the edge is recorded before the OS gets the
child, so the wake always precedes its consequences in the stream.

**Loop starvation.** In an asyncio fn trace, any synchronous stretch
that held the event loop past 100 ms (asyncio's own slow-callback
threshold; `--starve-ms N` tunes it) raises the ⏳ banner: which task,
how long, inside which function — the largest recorded delta names the
frame the time actually sat in — and which tasks were waiting,
including ones created but never yet scheduled. Awaited time never
flags: a coroutine yield releases the loop and ends the stretch. Teal
pins mark each incident on the strip; the fix is usually
`await asyncio.to_thread(...)`, and the banner clearing proves it.

## Part 11 — The run at a glance

**The call tree.** The stack panel shows one path; the **Call tree**
panel shows them all — the run's whole recursion as nested collapsible
nodes, each frame carrying its arguments and its return value
(`fib(n=3) → 2`), the current frame lit and its ancestors auto-opened
as the replay descends. The level line above it makes "work per level
× number of levels" countable on screen (`L4 6× / 24 ev`), ⤷ jumps to
any call's moment, and honesty holds at the edges: a frame that never
returned is marked, a suspended generator says so (resumes re-enter
their original node — no phantom calls), and the 4000-node render cap
announces itself. Works at both granularities — on an fn-level trace
of a real codebase it is the whole run's shape in one panel.

**The sequence diagram.** The **Sequence** panel answers the classic
onboarding question — who talks to whom, in what order — from the
same call/return events: lifelines are the modules acting in a
window (or the class, where the recorded MRO knew `self`), arrows
are the window's calls top to bottom in event order (the corner
reminds you: not wall time), and activation bars redraw the call
nesting — returns close them, red means an exception passed through,
hollow means still open at the window's end. Pick the window in the
select: the current test's chapter, the current frame's extent, the
span between your flanking bookmarks, or the whole run — with the
caps (12 lifelines, 400 arrows) announcing what a too-wide window
would hide. Imports draw as `<module>` → `<module>` arrows, because
a module body IS a call the tracer recorded; self-calls loop; a call
arriving from outside the window's actors enters as a dot ("found
message"). Click any arrow to jump. On tinyshop at fn granularity
the whole-run diagram — entry → main → cart → discounts, `add ×4`,
then the 2-per-item pricing conversation — is the architecture
diagram nobody drew.

**Motion & presentation.** Press ▶ Play and changes *glide*: a swap's
two cells slide past each other, a queue advances, graph nodes drift
to their new places — FLIP tweens over the diff the views already
draw, with heuristic identity (value+occurrence for primitives, key
for dict rows, node label for graphs). Single-step never tweens: at
step speed the highlight is the change. The honesty rule rides the
play button itself: motion between events is interpolation — only
the endpoints are recorded truth. `P` (or 🎬) enters presentation
mode — chrome hidden, large type, code and data side by side for a
projector — Esc exits.

## Part 12 — The trace as a notebook

**Notes.** Press **N** at any moment and write what you're thinking
— "HERE the total goes negative, why?" — Enter pins it. The Notes
panel lists every note jumpable, cream pins mark them on the strip,
and they persist per trace in your browser. **export sidecar** writes
them to a JSON file that travels WITH the trace: a teammate imports
it and your investigation is already pinned to the moments (notes
outside the trace's range are skipped, never clamped, and a
mismatched event count warns honestly).

**Guided tours.** Open **Tour**, park at a moment worth teaching,
set the view you want the learner to see, write one line of
narration, press *add stop* — repeat, export the sidecar, and hand
someone a lesson they can replay: each stop restores the exact event
AND view through the deep link, the narration bar walks them
stop-by-stop, and a 🔮 prediction stop arms the gate so they commit a
claim before stepping — a walkthrough with a grade. Try the bundled
one: trace `bubble_sort.py`, import
`tours/pyreplay-tour_bubble_sort.py.json`, press ▶ play.

**The explain bundle.** Park the cursor on the interesting moment
and press **⧉ explain**: ±25 events become a plain-text file — source
lines, every changed value, verdicts, provenance arrows, the rerun
command — downloaded and on your clipboard. Paste it into an issue, a
review, or an AI assistant: whoever reads it gets the recorded truth,
not a retelling. The header says exactly what it is, the cap
announces itself, and nothing is ever recomputed.

**The prediction gate (🔮).** Passive replay teaches little — the
gate makes you commit first. Arm it and the step controls ask for a
claim before they reveal: which line executes next (Enter commits,
the step scores it), what a variable will show (or that it won't
change), how many times the loop you're standing on runs (scored
from the recorded verdicts on the spot). Every verdict states both
sides — "✗ claimed L6 — recorded L5" — and the mismatch is the
lesson. The ledger tracks hit rate by claim type and your streak,
per script; skipped steps are counted too; export downloads the
JSON. Free navigation is never locked — only committed claims
count. Try it on a planted-bug trace: the drill turns a bug hunt
into a score.

## Part 13 — Architecture audits

**Layering rules.** Drop a `.pyreplay-layers` file at the root and
the map becomes the architecture's guardian: `layers: ui -> logic ->
data` declares the order (a layer may import downward, never upward),
`layer NAME: glob, …` assigns modules, `forbid A -> B` adds explicit
bans. Violating imports turn solid red with the broken rule in the
tooltip, the banner counts them, and the walls panel lists each one.
Modules outside every layer are counted as unconstrained — never
guessed. A malformed file refuses to enforce (and says so): partial
rules would pretend the architecture is safe. In CI,
`python3 mapper.py --check-layers .` exits 0 when the architecture
holds, 4 on violations, 2 on a broken rules file.

**API-surface honesty (#107).** Every package has two interfaces: the
one it declares (`__all__`, public names) and the one outsiders
actually use. The map now measures the gap: the walls panel's 🔓
audit lists every outside reach into `_private` modules, every
`from m import _name` across a package boundary, and every import of
a name a literal `__all__` didn't declare — and the 🔓 header toggle
paints those import edges dashed red. Intra-package reaches don't
count (that's the convention working), a computed `__all__` makes no
claims, and star imports are counted as bypassing the audit.
"Please don't import private stuff" becomes a number that can go
down.

**The shadowing badge.** A local named `list`, `id`, or like a
module-level variable silently masks the outer name — the code reads
fine and resolves wrongly. Every line trace carries a static per-def
audit: rows that shadow a builtin, a module global (named with its
line), or an enclosing function's local wear **👥**, on exactly the
frames that hold both names. Reading a closure variable is not
flagged — only binding is. The map runs the module-level tier: rebound
imports, module-level builtin masks, and the classic import horror — a
top-level `random.py` — with 👥 pips on the boxes and the stdlib case
shouted in the terminal.

**Dead-code evidence (#109).** Every map now joins two kinds of
evidence about every def: does anything reference it statically
(#16's call graph + the importable surface), and did it ever run
(every adopted trace)? Candidates come tiered — [A] no static
reference at all, [B] importable surface or live-class method
(obj.method dispatch hides here), [C] statically called but never
ran in any adopted run — as a ranked terminal list and 👻 rows on
the map's expanded modules. What ran is alive no matter what the
graph says, class bodies executing at import time don't count as
liveness, and the clause rides every surface: evidence, not proof —
reflection, plugins and decorators can hide callers. Deleting code
becomes a decision instead of a bet.

**The crime scene (#110) — history as the third axis.** On any mapped
git repo the header grows a **lens** select: *churn × cx* tints every
module by √(change-frequency × decision-points) over a window the
banner names (default 12 months; `--churn-since` takes git's own
vocabulary), and *risk* multiplies runtime heat in — changes often,
is complex AND carries the run, the strongest bug predictor known.
Scores are normalized to the repo's own maxima, so the brightest box
is *this* codebase's top offender; the terminal prints the top three
with the raw numbers. No git history readable → the lens stays
absent. pyreplay mapped on itself puts `tracer` at 0.93 — no
surprises, which is exactly the point.

## Part 14 — The reliability lab

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

**Find the failing input (`--fuzz GEN.py`).** Every instrument above
assumes you already have a failing case; this one finds it while you
sleep. Write `gen(rng)` in a file — take the seeded `random.Random`
it hands you, return the run's stdin (str/bytes) or its argv (a
list) — and `python3 tracer.py --fuzz gen.py --runs 50 target.py`
feeds every run its own generated input, run i seeded base+i−1
(`--fuzz-seed` pins the base; every input reproducible forever).
Outcomes classify as usual, the suspects fire when both classes
appear, and each class's FIRST input is saved beside its kept trace
— clean included, the known-good for diffing. On the first failure
the harness prints the seed, writes a line-level microscope trace of
exactly that input, and composes the `--shrink` command that
minimizes it: fuzz finds, shrink distills, diverge explains. It
stacks with `--chaos-schedule` (inputs × schedules, both seeds
recorded) and with `--check` (fail on a property, not just a crash).
The bundled `example_fuzz.py` carries its own `gen`: twenty runs, 7×
"books negative", and the composed shrink cuts the failing ledger to
its 2-line core.

**The differential oracle (`--oracle REF.py`).** When the right
answer is expensive to state, a slow correct program states it —
the AtCoder stress-test workflow, automated. `python3 tracer.py
--oracle brute.py --fuzz gen.py --runs 30 fast.py` runs both
implementations on the same seeded inputs (or pipe one input, one
trial) and compares stdouts judge-style: trailing whitespace and
trailing blank lines ignored, both read from the recorded console
lane. A mismatch prints both outputs, keeps the input and BOTH
traces, and composes the `--shrink --oracle` command — shrinking
under the disagreement oracle: ddmin keeps cutting while the two
still disagree, then microscopes BOTH sides on the minimal case at
line level. Crashes are verdicts: same exception type on both sides
counts as agreement at a domain edge (and says so); a crashed
reference is named loudly, because a broken spec can't certify
anything. The verdict never picks a side — a mismatch is a bug in
ONE of them. The four `strategy_*.py` RSQ solutions in this repo are
the born demo: the brute force certifies the Fenwick tree in one
command, and a planted off-by-one is caught 3/3.

**Fault injection (`--inject`).** Error-handling paths are the
least-executed code you own; injection is the only way to watch
them run. `python3 tracer.py --inject
"discounts.bulk_discount:raises=TimeoutError:on_call=2"
tinyshop/main.py` forces the second call of that function to raise
(or `returns=0` for a sentinel, `stall=250` for a slow dependency)
— the wrapper arms the moment the module is imported, the injection
is recorded as a first-class event at the call site, and the forced
raise rides the normal exception machinery, so what catches it (or
doesn't) is ordinary recorded truth. The banner says 💉 PERTURBED
with the performed/armed arithmetic, the moment wears a red badge
and pins, `type:inj` finds it, and a target name that never
resolved is reported loudly — a typo must never look like a
survived fault. Try `returns=0`: the run "succeeds" with a wrong
grand total, which is the quieter failure mode and the better
lesson. Repeat the flag for multiple faults; add `--runs 10` for
the catch rate.

**What did it touch? (`--io`).** `python3 tracer.py --io main.py`
opens the I/O lane: every file opened, host contacted, subprocess
spawned, `exec`/`eval` run and import your own code wrote becomes an
event tied to the frame that caused it, recorded through
`sys.addaudithook` (stdlib, works in `fn` mode too). Opened files
are paired with their closes, and any handle still open at exit is
named as a leak at its exact site — the resource question answered,
not guessed. The banner sums it up (⇄ with per-kind counts and the
leak verdict), a color-coded strip pins every operation with
unclosed files glowing red, and `type:io` filters the lane. It only
records what your code caused — a library opening a socket on your
behalf is attributed to the line that triggered it, while the dozens
of transitive stdlib imports stay out of the way. Honesty: audit
hooks see the Python layer, not raw C syscalls, and endpoints are
captured but payloads stay external (bridge mitmproxy for those).

**Where memory went (`--memory`).** Time-heat shows where the code
ran; memory-heat shows where it held on. `python3 tracer.py --memory
main.py` samples `tracemalloc` through the run and draws a growth
strip-chart under the scrubber — the filled area is current traced
bytes, the line above is the peak (a high-water mark) — so a leak
shows as a rising floor while it grows, not at the OOM kill. A
coarser snapshot attributes bytes to the modules holding them
(printed at exit; in-scope only, so the tracer's own buffer is
excluded). Read the honesty on the banner: it's recorded under
tracemalloc's ~2× overhead, the process totals include the tracer's
event buffer, and it sees Python-level allocations only — a
numpy/torch tensor allocated in C reads ~zero here while RSS climbs
(that's Memray's job). Works at `fn` granularity too. And the bytes
land on the map: build it with `--trace` of a `--memory` run and
switch the lens to **memory (bytes)** (or open `map.html#lens=memory`)
— modules tint by share of the largest in-scope snapshot, with byte
badges and the between-snapshots caveat in every tooltip. Several
runs adopted together keep the largest snapshot whole and name the
trace it came from — one distribution is one moment of one run, so
snapshots are never mixed into a state that never existed.

**Input shrinking (`--shrink`).** A huge input that crashes is a
chore; the tiny core that still crashes is a diagnosis. Pipe the
input and `--shrink` runs Zeller's ddmin over it — lines by default,
`--shrink-model tokens|bytes` otherwise — re-testing each candidate
in a real child run. The oracle is honest by construction: with
`--check` it's "the check hits"; without, it's "the target crashes
with the SAME exception type" — never a different failure quietly
substituted. You get the minimal input file, a line-level trace of
the minimal case, and the rerun command; the attempt cap announces
itself when it bites. 78 ledger lines shrink to `refund 999` +
`audit` in fifteen probes.

**Metamorphic relations (`--relation`).** When you can't say what the
right answer IS, you still know its symmetries: `sum` doesn't care
about order, a distance is symmetric, doubling every input doubles
the total. Declare the symmetry —
`--relation "' '.join(reversed(x.split())) => out == out0"` — and
each trial runs the target twice (original stdin, transformed stdin;
`--gen` generates trials) and checks the relation over the two
recorded outputs (`out0`/`out`, read from the console lane; `num()`/
`nums()` parse them). A violation prints both outputs, KEEPS both
traces and composes the exact `--diverge` command that lands on the
line where the symmetry broke. Exit 0 iff everything held —
git-bisect-ready. Honesty: a violation under hash randomization may
be nondeterminism (the report says to pin PYTHONHASHSEED or measure
with --runs first), and held trials are an observation, never a
proof. Conservation laws as tests — no oracle required.

**Mutation-survivor forensics (`--forensics`).** Run `mutmut run` in
your project, then point the tracer at the survivors — the mutants no
test killed. For each one, the bridge reads mutmut's own artifacts
(survivor list, nearest covering test, the diff), applies the diff to
a patched shadow copy, traces the test twice at line level, and hands
the pair to the divergence finder. The verdict writes itself: "STATE
diverges at event 17: base: 1 vs 2 … every assertion still passed —
the divergence above is the assertion you forgot to write." Identical
traces get the other honest answer: possibly an equivalent mutant,
never an invented difference. Needs mutmut importable in the python
you run the tracer with (`.venv/bin/python tracer.py --forensics`).

**The scaling bench (`--sweep`).** The doubling experiment as one
command: `--sweep "n=8,16,32,64" --predict "n^2" algo.py` runs the
target once per rung, measures EVENT COUNTS (exact, deterministic —
the honest cost model; timing noise can't touch them) plus traced
wall time at fn granularity, fits the log–log slope and reports the
observed exponent with R², consecutive-rung ratios, and a verdict on
your claim. Input per rung comes from the minimal generator protocol —
`--gen GEN.py` with `gen(value, seed) → str|bytes` becomes the
target's stdin; without `--gen` the value itself is the stdin (the
competitive-programming default). The `sweep_*.html` report draws the
log-log charts: a power law is a straight line, and your claim is the
dashed curve over the measured points. Honesty throughout: counts are
Python-level events, not machine operations; crashed or cap-truncated
rungs are excluded BY NAME; a poor fit is never forced to a line. Try
mergesort at both granularities: fn measures n^1.0 (calls ARE linear),
line measures `n*log(n)` CONSISTENT — the bench tells you which cost
you counted.

## Recipes

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

## Field guide: studying a codebase you didn't write

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

## Current limits (by design, for now)

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
