#!/usr/bin/env python3
"""pyreplay tracer — record a Python run and emit a self-contained HTML replayer.

Usage:
    python tracer.py <script.py> [script args...]
    python tracer.py --out mytrace.html --max-events 1000000 <script.py> [args...]

Output defaults to trace_<scriptname>.html in the current directory; if
that exists, trace_<scriptname>_2.html and so on — nothing is ever
overwritten. Use --out NAME.html to pick a name (that one DOES overwrite).
    python tracer.py --granularity fn --export-perfetto out.json <script.py>
    python tracer.py --backend monitoring <script.py>   # PEP 669 engine, 3.12+ (fn AND line)
    python tracer.py --start-at myfile.py:42 <script.py> [args...]
    python tracer.py --start-at myfile.py:42 --start-count 57 <script.py>
    python tracer.py --start-when "i == 56" <script.py> [args...]
    python tracer.py --trip nan <script.py>            # NaN/Inf tripwire
    python tracer.py --runs 50 <script.py>             # N-run statistics
    python tracer.py --diverge good.html bad.html      # first divergence
    python tracer.py -m pytest tests/                  # trace a test suite
    python tracer.py --root brian2 -m pytest           # pytest scoped to --root
    python tracer.py --root . -m pytest tests/ -q      # explicit test path

-m runs default to --granularity fn (call-level): line-level over a whole
suite is the runaway-slowness trap. Pass --granularity line (with --include
or --start-at scoping) for the microscope. Script entries are preflighted:
missing imports are announced with the pip line BEFORE the run, and a crash
at import prints the same hint after. Long runs print a heartbeat to stderr
every 30s (PYREPLAY_HEARTBEAT=seconds tunes it, 0 disables).

    python tracer.py --doctor --root pymdp -m pytest tests/   # runs NOTHING

--doctor prefixes any invocation and prints the setup report instead of
running: which python (venv or system, with the activate line), whether the
entry itself can work (blockers, exit 3), the codebase-wide missing-dep
shopping list with the install recipe (`pip install -e <root>` when the
root is a package), and pytest-config traps (forced xdist -> append -n0).

In-process (no CLI at all — a notebook cell, a server, a long script):

    from tracer import watch
    with watch():                        # bracket a block -> trace_watch.html
        result = solve(data)
    @watch()                             # or a function: its FIRST call is
    def handler(msg): ...                # recorded (once=False: every call)

--start-at works like a breakpoint that presses "record": nothing is
recorded until execution first reaches that line; from then on everything
is, starting with a reconstruction of the live call stack and variables.
--start-count N arms on the Nth hit instead of the first.
--start-when EXPR arms when EXPR (evaluated with the frame's variables)
is true — at the --start-at line if given, else checked on every line.

--trip nan marks the moment each variable first turns NaN/Inf (and each
return value that carries one out): amber ☢ markers over the scrubber,
a banner naming the FIRST birth — where the poison was born, not where
it finally crashed. Line granularity only; marks only what the encoded
values visibly show (beyond a cap or window = unknown = unmarked; the
inside of C objects, e.g. arrays, stays invisible).

--runs N: one run is an anecdote, N runs are an experiment. The target
executes N times (fn granularity by default; identical stdin each run),
every outcome is classified by exception type + crash site, and ONE
representative trace per outcome class is kept — first seen, not N
files. runs_<name>.html reports the counts, the wall-time distribution
per class (min/median/p95/max, tracer-inclusive — comparable to each
other, not to bare runtime) and links each class to its replayable
trace. Exit code 0 only if every run was clean, so `git bisect run`
can consume it directly. Ctrl-C reports the runs completed so far.
With BOTH outcomes present the report adds THE SUSPECTS (SBFL): every
line ranked by how exclusively failing runs execute it (Ochiai) — the
statistics do the boring half of debugging before you read anything.
Correlation, not causation, and the report says so; at fn granularity
the units are call/return/raise lines (line granularity gives
statement-level suspects).

Past 100k events a trace auto-CHUNKS (#101): the events move out of
the single JSON string into gzip+base64 chunks — files shrink 5-25x,
the browser never parses one giant string, and jumps resume from
KEYFRAMES (state snapshots every 64k events) instead of replaying the
run from the start. --chunked forces it on, --no-chunked off; a
missing chunk is announced loudly, in the file and in the viewer.
Needs DecompressionStream (Chrome 80+ / Firefox 113+ / Safari 16.4+).

--check EXPR turns any run into a yes/no experiment for `git bisect
run`: EXPR is watched per line like --start-when (state tests: "total
< 0") AND evaluated once over the run facts (error, exc, events,
output — the console text, hit, hits, tests_failed, truncated). Exit 1
the moment either says yes; 0 clean; 3 if the expression was never
evaluable anywhere (a typo must never look like a clean run). This
mode overrides the usual exit-0-on-target-crash behavior.

--watch EXPR (repeatable) records OBSERVABLES: the expression is
evaluated at every line event of every traced frame and recorded as a
synthetic variable ("watch:EXPR") with the same change detection, life
navigation and chart view real variables get — derived quantities
(lengths, sums, ratios) are often the real signal. Not evaluable in a
frame = nothing recorded there; a watch that was alive and stops being
evaluable records "(not evaluable here)" — the honest hole; a watch
never evaluable ANYWHERE warns at the end (a typo must never look like
data). Expressions run INSIDE your process — keep them pure. Line
granularity only; scope the per-line cost with --include.

--invariant EXPR (repeatable) is the contract you don't edit into the
code: checked at every line event where its names are in scope, and
every TRANSITION into falsehood becomes an amber VIOLATION event — the
run continues. Recovery re-arms (the tripwire pattern), so a contract
that stays broken records one entry, not a flood. The event carries
the values of the expression's names; the banner and terminal report
each invariant's verdict — violated N× with a jump, held everywhere it
was evaluable, or never evaluable (a typo must never look like a
clean contract). Line granularity only.

--black-box turns the tracer into a flight recorder: a ring buffer of
the LAST --max-events events (fn granularity by default), rotation
counted and announced in the banner; `kill -USR1 <pid>` dumps the
current window as a normal trace WITHOUT stopping the run, and the end
(or crash) writes the final window as usual. watch(ring=N) gives the
same in-process. Pay ~nothing forever; have the film when it matters.

--chaos-schedule SEED turns latent races into measured rates: seeded
micro-stalls and GIL yields injected at traced event boundaries,
switch-interval jitter, and (when asyncio runs) a seeded shuffle of
each loop tick's ready queue. Chaos biases WHICH legal interleavings
the run explores — it never edits your code — and the trace is
labeled PERTURBED. Same seed = same injected decision stream (the OS
still owns the schedule: biased exploration, not replay). Under
--runs N run i gets seed SEED+i-1, so "fails 4/20 under chaos, 0/20
without" becomes an afternoon's sentence. Timings under chaos are not
performance truth; --export-perfetto is refused.

Concurrent fn traces also compute their CRITICAL PATH (#89): the
longest dependency chain — through call nesting, #88 wake edges and
same-thread task switches — that determined total wall time. Speeding
up anything off it is wasted work. The viewer banner names it with
gold scrubber pins to walk; --export-perfetto adds a dedicated
"★ critical path" row plus a ★ on each critical slice. Gaps nobody
was running in are UNTRACKED EXTERNAL WAITS (sleep, network, OS) —
counted and attributed, never hidden. Ties are broken arbitrarily:
this is A critical path, not THE unique one.

Every run also records WHO WOKE WHOM (#88): thread started/joined and
asyncio task created (create_task, ensure_future, gather and TaskGroup
all funnel through it) land as first-class ⤳ wake events at the exact
moment they happen, attributed to the wake site. The viewer names the
edge and jumps to its other end; the Perfetto export draws real flow
arrows between the lanes. A start edge is recorded BEFORE the OS gets
the child thread — a started thread can live its whole life before
start() returns, and a wake must precede its consequences. v1 records
create/start/join; cancel edges and queue put→get correlation remain
on the roadmap.

Every fn or line trace also aggregates its BOUNDARY SCHEMAS (#120):
the structural shape of every function's observed arguments and
returns — types, keys, nesting, never values — shown on call/return
events in the viewer ("lookup(catalog: dict{...}, sku: str) → ⚠
dict{qty, price} 1x / NoneType 1x") with jump links to the deviant
calls, and a terminal summary of every unstable interface. Shapes are
honest to the recorded depth; observed, never declared.

Every run records its CONSOLE LANE: each stdout/stderr line the target
writes becomes an event tied to the frame that wrote it — a console
panel in the replayer follows the replay, click a line to land on its
moment (--no-console disables; caps announced; writes below the Python
layer bypass the tee, stated). Every trace also embeds its
REPRODUCIBILITY CAPSULE: the exact rerun command, cwd, python/platform,
PYTHONHASHSEED (with the random-order warning), curated env keys only,
and the stdin bytes the run actually CONSUMED (captured lazily — a
pipe that never closes cannot hang the start), downloadable from the
viewer's Reproduce box. And WHYLINE: click the line number of a line
that never ran — the viewer answers with the causal chain ("the guard
at line G ran 12x, 0x true — this branch was never chosen"), walked
upward one controller at a time; executed lines jump to their first
execution.

-m pytest runs get PER-TEST CHAPTERS: a tiny plugin is auto-injected
(-p _pyreplay_pytest_plugin) and every test becomes a named span —
colored bands over the scrubber (green passed / red failed), the
owning test shown while you scrub, TEST ▶/✓/✗ boundary events. With
both outcomes present the trace also carries the per-test SBFL join:
lines ranked by how exclusively FAILING tests executed them (Ochiai),
printed after the run and clickable in the banner — ranked suspects
from ONE suite run. Teardown-phase failures are not folded back into
an already-passed test's chapter (stated limit).

--diverge A.html B.html: where did two runs of the same code first part
ways? Reported twice, honestly: STATE divergence (the same line runs on
both sides but its values differ — usually nearer the cause; the
differing variables are named) and CONTROL divergence (a different line
runs — the symptom). Timestamps and memory addresses inside reprs are
canonicalized away first, so what remains differing is real. Prints
deep links that open both traces AT the divergence. Exit 0 identical,
1 diverged — pairs with --runs (compare a kept clean trace against a
kept failing one).

Traces every file inside the SCOPE ROOT — by default the entry script's
directory tree (your project). Pass --root DIR to set it explicitly; that is
what makes `-m pytest` useful — the entry (pytest) lives in site-packages, but
--root keeps the scope on your code. With `-m pytest` and no test path named,
--root doubles as pytest's discovery dir, so it can't crawl sibling projects
next to it. The stdlib, site-packages and this tracer
itself are never traced, so you can point it at the entry point of any codebase.
"""
import ast
import base64
import collections
import datetime
import dis
import fnmatch
import gzip
import io
import json
import os
import platform
import random
import re
import reprlib
import runpy
import shlex
import signal
import subprocess
import sys
import threading
import time
import weakref
import types

MAX_EVENTS = 200_000   # safety cap so a hot loop can't produce a 2 GB trace
CHUNK_AUTO = 100_000     # events; past this the trace auto-chunks (#101)
                         # (must sit BELOW the default event cap, or the
                         #  auto path could never fire on default runs)
CHUNK_EVENTS = 65_536    # events per gzip chunk
MAX_REPR = 120         # truncate huge values; the viewer shows reprs, not objects
SELF = os.path.realpath(__file__)

# reprlib truncates WHILE building the repr — repr() of a million-element
# list would build the whole string first and stall the trace.
_repr = reprlib.Repr()
_repr.maxstring = MAX_REPR
_repr.maxother = MAX_REPR
_repr.maxlist = _repr.maxtuple = _repr.maxset = _repr.maxfrozenset = 20
_repr.maxdict = 20
_repr.maxlong = MAX_REPR   # default 40 middle-truncates big ints — the
                           # viewer must be able to parse numbers faithfully


def scope_ok(rel, include, exclude):
    """Shared scoping vocabulary (tracer and mapper): glob patterns
    matched against the project-relative path and the bare filename."""
    base = os.path.basename(rel)
    if include and not any(fnmatch.fnmatch(rel, p) or
                           fnmatch.fnmatch(base, p) for p in include):
        return False
    if exclude and any(fnmatch.fnmatch(rel, p) or
                       fnmatch.fnmatch(base, p) for p in exclude):
        return False
    return True


class TraceLimitReached(BaseException):
    """Raised inside the target to abort the run once the event cap is hit.

    BaseException so the target's own `except Exception:` blocks don't
    swallow it.
    """


def safe_repr(value):
    """repr() that never raises and never explodes in size."""
    try:
        text = _repr.repr(value)
    except Exception:
        return f"<unrepr-able {type(value).__name__}>"
    return text if len(text) <= MAX_REPR else text[:MAX_REPR] + "…"


MAX_ITEMS = 30    # container elements recorded per level
MAX_DEPTH = 3     # nesting levels recorded before falling back to repr
FP_LIMIT = 4096   # max container size we shadow-copy for change detection
MAX_WINDOW = 60   # max elements encoded in a change-centered window


_SKIP_INSTANCE = (type, types.ModuleType, types.FunctionType,
                  types.BuiltinFunctionType, types.MethodType,
                  types.GeneratorType, types.CoroutineType,
                  types.FrameType, types.TracebackType)


def _instance_attrs(value):
    """(name, value) pairs for plain class instances — their data lives
    in attributes. Covers both __dict__ and __slots__ classes. Returns
    None when the value isn't an attribute-bearing instance."""
    if isinstance(value, _SKIP_INSTANCE):
        return None
    cls = type(value)
    if cls.__module__ == "builtins":
        return None
    out, seen = [], set()
    d = getattr(value, "__dict__", None)
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(k, str) and not k.startswith("__"):
                out.append((k, v))
                seen.add(k)
    for klass in cls.__mro__:
        slots = getattr(klass, "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for s in slots:
            if isinstance(s, str) and not s.startswith("__") \
                    and s not in seen:
                try:
                    out.append((s, getattr(value, s)))
                    seen.add(s)
                except AttributeError:
                    pass   # slot declared but never assigned
    return out or None


def _shape_meta(value):
    """#83: array metadata at the Python boundary. The tracer honestly
    cannot see inside C extensions — but shape/dtype are readable
    without touching the data, and broadcasting bugs are visible
    exactly there. Guarded probes; anything odd records nothing."""
    meta = {}
    try:
        sh = getattr(value, "shape", None)
        if isinstance(sh, tuple) and 0 < len(sh) <= 8 \
                and all(isinstance(d, int) for d in sh):
            meta["sh"] = repr(sh)          # Python-style: (4,) not (4)
        elif sh is not None:
            s2 = str(sh)
            if 2 < len(s2) <= 48 and s2[0] in "([t":   # torch.Size([...])
                meta["sh"] = s2
    except Exception:
        pass
    if "sh" in meta:
        # dtype only WITH a shape: a lone .dtype is usually a module
        # or class attribute, not an array (the np-module trap)
        try:
            dt = getattr(value, "dtype", None)
            if dt is not None:
                s2 = str(dt)
                if 0 < len(s2) <= 32:
                    meta["dt"] = s2
        except Exception:
            pass
    return meta


def encode(value, depth=MAX_DEPTH, _objs=None):
    """Structured, size-capped encoding of any Python value.

    The viewer picks a semantic renderer by the "t" tag:
      p = primitive, s = string, o = opaque object (repr only),
      obj = class instance (attribute pairs),
      list / tuple / set / dict = containers ("n" is the REAL length;
      "v" holds at most MAX_ITEMS encoded elements).
    Works on any value from any program; anything weird degrades to "o".
    Objects are depth-TRANSPARENT (attributes are first-class data, not
    a nesting level); _objs carries the ids of instances currently being
    encoded so self-referential objects can't recurse forever.
    """
    try:
        cls = type(value).__name__
        if value is None or isinstance(value, (int, float, bool, complex)):
            return {"t": "p", "c": cls, "v": safe_repr(value)}
        if isinstance(value, str):
            v = value if len(value) <= MAX_REPR else value[:MAX_REPR] + "…"
            return {"t": "s", "c": cls, "v": v}
        if depth > 0:
            if isinstance(value, (bytes, bytearray)):
                # mutable byte buffers: render as int cells like a list,
                # so index assignments are visible (repr truncation hid them)
                return {"t": "list", "c": cls, "n": len(value),
                        "v": [{"t": "p", "c": "int", "v": str(b)}
                              for b in value[:MAX_ITEMS]]}
            if isinstance(value, (list, tuple)):
                return {"t": "list" if isinstance(value, list) else "tuple",
                        "c": cls, "n": len(value),
                        "v": [encode(x, depth - 1, _objs)
                              for x in value[:MAX_ITEMS]]}
            if isinstance(value, dict):
                pairs = []
                seen = {}
                for i, (k, v) in enumerate(value.items()):
                    if i >= MAX_ITEMS:
                        break
                    ks = safe_repr(k)
                    dup = seen.get(ks, 0) + 1
                    seen[ks] = dup
                    if dup > 1:   # truncated reprs may collide: disambiguate
                        ks = f"{ks} #{dup}"
                    pairs.append([ks, encode(v, depth - 1, _objs)])
                return {"t": "dict", "c": cls, "n": len(value), "v": pairs}
            if isinstance(value, (set, frozenset)):
                return {"t": "set", "c": cls, "n": len(value),
                        "v": [encode(x, depth - 1, _objs)
                              for x, _ in zip(value, range(MAX_ITEMS))]}
            try:
                # class instances: expose their attributes — that's where
                # OOP code keeps its data (self.adj_list, self.n, ...)
                attrs = _instance_attrs(value)
            except Exception:
                attrs = None
            if attrs is not None:
                oid = id(value)
                objs = _objs if _objs is not None else frozenset()
                if oid in objs:   # cycle: this instance is an ancestor
                    return {"t": "o", "c": cls, "v": safe_repr(value)}
                objs = objs | {oid}
                pairs = []
                for k, v in attrs[:MAX_ITEMS]:
                    pairs.append([k, encode(v, depth, objs)])
                enc = {"t": "obj", "c": cls, "n": len(attrs),
                       "v": pairs}
                enc.update(_shape_meta(value))   # #83: pandas-style
                return enc
        enc = {"t": "o", "c": cls, "v": safe_repr(value)}
        enc.update(_shape_meta(value))           # #83: numpy/torch
        return enc
    except Exception:
        return {"t": "o", "v": f"<unreadable {type(value).__name__}>"}


_MUTABLE = (list, dict, set)


def _copy_elem(x):
    """One-level copy of a mutable element so in-place mutation of it is
    detectable against the shadow (immutables pass through by reference)."""
    if isinstance(x, list):
        return list(x)
    if isinstance(x, dict):
        return dict(x)
    if isinstance(x, set):
        return set(x)
    return x


def _sample_has_mutable(items):
    """Check the first 32 elements for mutable containers. Sampling keeps
    the per-line cost tiny; a mutable element hiding past the sample in an
    otherwise-flat container is a documented blind spot."""
    for i, x in enumerate(items):
        if isinstance(x, _MUTABLE):
            return True
        if i >= 31:
            break
    return False


_FP_FAST_NONE = (int, float, str, bool, bytes, complex, type(None))


def fingerprint(value, _depth=2):
    """Shadow copy of a container, kept between events to detect changes
    beyond the encoded head. Flat containers of immutables use a C-level
    copy (fast path — no per-element Python work); containers holding
    mutable elements copy them one level deep so in-place mutation INSIDE
    an element is seen. Class instances fingerprint their attributes, so
    a mutation inside self.adj_list (beyond its encoded head) is still
    detected. None means "not tracked": small containers with small
    elements are fully covered by encode(), and containers over the
    FP_LIMIT total-cell budget fall back to head-only detection."""
    if isinstance(value, _FP_FAST_NONE):
        return None
    try:
        if isinstance(value, bytearray):
            if len(value) <= MAX_ITEMS or len(value) > FP_LIMIT:
                return None
            return bytes(value)   # immutable snapshot, C-level copy
        if isinstance(value, (list, tuple)):
            n = len(value)
            if n > FP_LIMIT:
                return None
            if n <= MAX_ITEMS and not any(
                    isinstance(x, _MUTABLE) and len(x) > MAX_ITEMS
                    for x in value):
                return None   # encode() head already covers everything
            if not _sample_has_mutable(value):
                return list(value)          # flat immutables: C-level copy
            out = []
            budget = FP_LIMIT
            for x in value:
                budget -= len(x) + 1 if isinstance(x, _MUTABLE) else 1
                if budget < 0:
                    return None
                out.append(_copy_elem(x))
            return out
        if isinstance(value, dict):
            n = len(value)
            if n > FP_LIMIT:
                return None
            if n <= MAX_ITEMS and not any(
                    isinstance(v, _MUTABLE) and len(v) > MAX_ITEMS
                    for v in value.values()):
                return None
            if not _sample_has_mutable(value.values()):
                return dict(value)          # flat immutables: C-level copy
            out = {}
            budget = FP_LIMIT
            for k, v in value.items():
                budget -= len(v) + 1 if isinstance(v, _MUTABLE) else 1
                if budget < 0:
                    return None
                out[k] = _copy_elem(v)
            return out
        if isinstance(value, (set, frozenset)):
            if len(value) <= MAX_ITEMS or len(value) > FP_LIMIT:
                return None
            return set(value)
        if _depth > 0:
            attrs = _instance_attrs(value)
            if attrs is not None:
                out = {}
                for k, v in attrs[:MAX_ITEMS]:
                    fv = fingerprint(v, _depth - 1)
                    if fv is not None:
                        out[k] = fv
                # tagged tuple: never confusable with a dict fingerprint,
                # so windowed_value safely ignores it (no window support
                # for attrs yet — the change is detected and flagged)
                return ("obj", out) if out else None
    except Exception:
        pass
    return None


def _changed_indices(old_fp, new_fp):
    """Index positions where two sequence fingerprints differ."""
    idxs = []
    shorter = min(len(old_fp), len(new_fp))
    for i in range(shorter):
        a, b = old_fp[i], new_fp[i]
        try:
            if a is not b and a != b:
                idxs.append(i)
        except Exception:
            idxs.append(i)  # incomparable (e.g. numpy) — assume changed
    if len(old_fp) != len(new_fp):
        idxs.extend(range(shorter, max(len(old_fp), len(new_fp))))
    return idxs


def encode_window(value, lo, hi, chi=None):
    """Encode value[lo:hi] with an "off" marker so the viewer can label
    real indices, plus "chi": the authoritative changed indices — window
    positions can't be compared across events, so the tracer must say
    which elements changed."""
    out = {"t": "tuple" if isinstance(value, tuple) else "list",
           "c": type(value).__name__, "n": len(value), "off": lo,
           "v": [encode(x, MAX_DEPTH - 1) for x in value[lo:hi]]}
    if chi:
        out["chi"] = chi
    return out


def windowed_value(value, enc, fp, old_fp):
    """Event payload for a changed variable. If the change lies beyond the
    encoded head of a large container, encode a region centered on the
    change (±10 elements) instead of mechanically showing the head."""
    if fp is None or old_fp is None or type(fp) is not type(old_fp):
        return enc
    try:
        if isinstance(fp, (list, bytes)):             # list / tuple / bytearray
            idxs = [i for i in _changed_indices(old_fp, fp)
                    if i < len(value)]
            if not idxs:
                return enc
            if max(idxs) < MAX_ITEMS:
                # change visible in the head — but still stamp the
                # authoritative indices (the PREVIOUS event may have been
                # a window elsewhere, which the viewer can't diff against).
                # Copy: enc is also stored in the snapshot; mutating it
                # would poison the next event's equality check.
                return {**enc, "chi": idxs}
            lo = max(0, min(idxs) - 10)
            hi = min(len(value), max(idxs) + 11)
            if hi - lo > MAX_WINDOW:   # scattered changes: cover the first
                hi = min(len(value), min(idxs) + MAX_WINDOW - 10)
            return encode_window(value, lo, hi,
                                 [i for i in idxs if lo <= i < hi])
        if isinstance(fp, dict):
            changed_keys = set()
            for k, v in fp.items():
                if k not in old_fp:
                    changed_keys.add(k)
                else:
                    try:
                        if old_fp[k] is not v and old_fp[k] != v:
                            changed_keys.add(k)
                    except Exception:
                        changed_keys.add(k)
            if not changed_keys:
                return enc
            pairs, fill = [], []
            seen = {}
            for k, v in value.items():
                ks = safe_repr(k)
                dup = seen.get(ks, 0) + 1
                seen[ks] = dup
                if dup > 1:      # truncated reprs may collide: disambiguate
                    ks = f"{ks} #{dup}"
                if k in changed_keys and len(pairs) < MAX_WINDOW:
                    pairs.append([ks, encode(v, MAX_DEPTH - 1)])
                elif len(fill) < MAX_ITEMS:
                    fill.append([ks, encode(v, MAX_DEPTH - 1)])
            fill = fill[:max(0, MAX_ITEMS - len(pairs))]
            return {"t": "dict", "c": type(value).__name__, "n": len(value),
                    "nc": len(pairs),   # first nc pairs are the changed ones
                    "v": pairs + fill}
        if isinstance(fp, tuple) and fp and fp[0] == "obj" \
                and isinstance(old_fp, tuple) and old_fp \
                and old_fp[0] == "obj":
            # object attribute shadows: name the attrs whose deep
            # contents changed, so the viewer can flash the exact row
            cha = []
            for k, v in fp[1].items():
                o = old_fp[1].get(k)
                try:
                    if o is None or (o is not v and o != v):
                        cha.append(k)
                except Exception:
                    cha.append(k)
            if cha:
                return {**enc, "cha": cha}
            return enc
        if isinstance(fp, set):
            added = fp - old_fp
            if not added:
                # removal-only change: stamp na=0 so the viewer suppresses
                # membership guessing against a partial old sample
                return {**enc, "na": 0}
            items = list(added)[:MAX_WINDOW]
            n_added = len(items)
            budget = max(0, MAX_ITEMS - len(items))
            for x in value:
                if budget <= 0:
                    break
                if x not in added:
                    items.append(x)
                    budget -= 1
            return {"t": "set", "c": type(value).__name__, "n": len(value),
                    "na": n_added,   # first na items are the newly added
                    "v": [encode(x, MAX_DEPTH - 1) for x in items]}
    except Exception:
        pass
    return enc


def _exc_info(arg):
    """Exception payload. Fires on every raise IN a frame — including
    exceptions an except block will catch, and C-level raises from calls
    made on the line (int("x"), d[missing], next(it)…). A propagating
    exception fires once per unwound frame: the trace shows the full
    path from raise to handler (or death)."""
    try:
        etype, evalue, _tb = arg
        msg = str(evalue)
        if len(msg) > MAX_REPR:
            msg = msg[:MAX_REPR] + "…"
        return {"t": getattr(etype, "__name__", str(etype)), "m": msg,
                # generator/iterator protocol: control flow, not error
                "soft": issubclass(etype, (StopIteration,
                                           StopAsyncIteration,
                                           GeneratorExit))}
    except Exception:
        return {"t": "Exception", "m": "?", "soft": False}


_GEN_FLAGS = 0x20 | 0x80 | 0x200   # generator | coroutine | async gen
try:
    _YIELD_OP = dis.opmap["YIELD_VALUE"]
except Exception:
    _YIELD_OP = -1


def _is_yield(frame):
    """At a generator frame's 'return' event: suspension (yield/await)
    leaves f_lasti sitting on a YIELD_VALUE opcode; a true return does
    not. This is how one sleeping frame stops looking like many calls."""
    try:
        return frame.f_code.co_code[frame.f_lasti] == _YIELD_OP
    except Exception:
        return False


_MRO_CACHE = {}


def _mro_info(frame):
    """For a method call: the class's MRO chain and which class actually
    SUPPLIED the executing code — "lookup started at Dog, passed Mammal,
    found speak on Animal". Cached per (class, code); only emitted when
    informative (inheritance actually involved)."""
    code = frame.f_code
    names = code.co_varnames
    if not names or names[0] not in ("self", "cls"):
        return None
    try:
        obj = frame.f_locals.get(names[0])
    except Exception:
        return None
    if obj is None:
        return None
    klass = obj if (names[0] == "cls" and isinstance(obj, type)) \
        else type(obj)
    key = (klass, code)
    if key in _MRO_CACHE:
        return _MRO_CACHE[key]
    info = None
    try:
        chain = klass.__mro__
        supplier = None
        for c in chain:
            for v in c.__dict__.values():
                fc = getattr(v, "__code__", None)
                if fc is None:
                    fc = getattr(getattr(v, "__func__", None),
                                 "__code__", None)
                if fc is None and isinstance(v, property):
                    for acc in (v.fget, v.fset, v.fdel):
                        if acc is not None and \
                                getattr(acc, "__code__", None) is code:
                            fc = code
                            break
                if fc is code:
                    supplier = c.__name__
                    break
            if supplier is not None:
                break
        # informative = the lookup involved real inheritance
        if supplier is not None and (len(chain) > 2
                                     or supplier != klass.__name__):
            info = {"c": [c.__name__ for c in chain[:10]], "s": supplier}
    except Exception:
        info = None
    _MRO_CACHE[key] = info
    return info


LOG_CAP = 20_000   # console lines recorded per run; cap announced


class _Ring(collections.deque):
    """#103: a bounded event store that counts what it rotated out —
    the flight recorder's honesty depends on knowing what was lost."""

    def __init__(self, maxlen):
        super().__init__(maxlen=maxlen)
        self.appended = 0

    def append(self, x):
        self.appended += 1
        super().append(x)

    @property
    def dropped(self):
        return self.appended - len(self)


class unevaluable:
    """#72: the honest hole in a watch's life — the expression HAD a
    value in this frame and then stopped being evaluable (a name left
    scope, an object died). Shown verbatim; never invented data."""

    def __repr__(self):
        return "(not evaluable here)"


_UNEVALUABLE = unevaluable()


class _Chaos:
    """#68: seeded schedule fuzzing. A pulse fires at a traced event
    boundary — a legal switch point anyway — so chaos only biases WHICH
    legal interleavings this run explores (PCT's insight: a few random
    perturbation points flush most races). Same seed = same injected
    decision stream; the OS still owns the schedule, so this is biased
    exploration, not deterministic replay. The trace says PERTURBED."""

    PULSE_P = 1 / 16       # a boundary perturbs at all
    BIG_P = 1 / 4          # ...and of those, a real stall vs a bare yield
    SWITCH_EVERY = 256     # re-roll sys.setswitchinterval this often

    def __init__(self, seed):
        self.seed = seed
        self._rng = random.Random(seed)   # own stream, never the target's
        self._lock = threading.Lock()
        self._n = 0
        self.delays = self.yields = self.switch_rolls = self.shuffles = 0
        self.asyncio_hooked = False
        self._unhook = None

    def interval(self):
        return self._rng.uniform(1e-5, 2e-3)

    def pulse(self):
        with self._lock:
            self._n += 1
            if self._n % self.SWITCH_EVERY == 0:
                sys.setswitchinterval(self._rng.uniform(1e-5, 2e-3))
                self.switch_rolls += 1
            if self._rng.random() >= self.PULSE_P:
                return
            stall = self._rng.random() < self.BIG_P
            dur = self._rng.uniform(50e-6, 500e-6) if stall else 0.0
            if stall:
                self.delays += 1
            else:
                self.yields += 1
        time.sleep(dur)   # outside the lock: stall THIS thread only

    def hook_asyncio(self):
        """Shuffle each loop tick's ready queue. Private API
        (loop._ready / loop._run_once) — probed, and its absence is
        reported rather than papered over."""
        try:
            import asyncio
            cls = type(asyncio.get_event_loop_policy())
            orig_new = cls.new_event_loop
            chaos = self

            def chaotic_new(pol):
                loop = orig_new(pol)
                chaos._wrap_loop(loop)
                return loop
            cls.new_event_loop = chaotic_new
            self._unhook = (cls, orig_new)
            self.asyncio_hooked = True
        except Exception:
            self.asyncio_hooked = False

    def _wrap_loop(self, loop):
        ready = getattr(loop, "_ready", None)
        orig = getattr(loop, "_run_once", None)
        if ready is None or orig is None:
            return          # exotic loop (uvloop): pulses still apply
        chaos = self

        def shuffled_run_once():
            r = loop._ready
            if len(r) > 1:
                items = list(r)
                with chaos._lock:
                    chaos._rng.shuffle(items)
                    chaos.shuffles += 1
                r.clear()
                r.extend(items)
            return orig()
        loop._run_once = shuffled_run_once

    def unhook(self):
        if self._unhook is not None:
            cls, orig = self._unhook
            cls.new_event_loop = orig
            self._unhook = None

    def report(self):
        return {"seed": self.seed, "delays": self.delays,
                "yields": self.yields, "switchRolls": self.switch_rolls,
                "shuffles": self.shuffles,
                "asyncioHooked": self.asyncio_hooked}


# the REAL streams — the tracer's own runtime prints (heartbeat,
# trigger-hit) go here so they are never recorded as target output
_RAW = {"out": sys.stdout, "err": sys.stderr}


class _ConsoleTee:
    """#118: forwards every write to the real stream and hands COMPLETE
    lines to the tracer (fragmented print() writes joined). The target
    sees the stream API it expects; recording can never break its IO.
    Stated limits: binary writes through .buffer bypass the lane, as
    does anything written below the Python layer (C extensions)."""

    def __init__(self, real, tr, tag):
        self._real = real
        self._tr = tr
        self._tag = tag
        self._buf = ""

    def write(self, s):
        n = self._real.write(s)
        try:
            self._buf += str(s)
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                self._tr.record_log(self._tag, line)
        except Exception:
            pass
        return n

    def writelines(self, lines):
        for s in lines:
            self.write(s)

    def flush(self):
        return self._real.flush()

    def tail(self):
        """An unterminated final line still counts — flush it."""
        if self._buf:
            try:
                self._tr.record_log(self._tag, self._buf)
            except Exception:
                pass
            self._buf = ""

    def __getattr__(self, name):   # encoding, isatty, fileno, buffer…
        return getattr(self._real, name)


class _StdinBufTee:
    """Binary layer of the stdin tee: sys.stdin.buffer reads recorded."""

    def __init__(self, real, sink):
        self._real = real
        self._sink = sink

    def _rec(self, b):
        if b:
            self._sink.feed(b)
        return b

    def read(self, *a):
        return self._rec(self._real.read(*a))

    def read1(self, *a):
        return self._rec(self._real.read1(*a))

    def readline(self, *a):
        return self._rec(self._real.readline(*a))

    def readlines(self, *a):
        ls = self._real.readlines(*a)
        for b in ls:
            self._rec(b)
        return ls

    def __iter__(self):
        return self

    def __next__(self):
        b = self._real.readline()
        if not b:
            raise StopIteration
        return self._rec(b)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _StdinSink:
    """Capped recorder of consumed stdin for the capsule (#104)."""

    def __init__(self, cap=65536):
        self.data = bytearray()
        self.total = 0
        self._cap = cap

    def feed(self, b):
        self.total += len(b)
        room = self._cap - len(self.data)
        if room > 0:
            self.data.extend(b[:room])


class _StdinTee:
    """#104: LAZY stdin capture — reads flow through on demand (no
    pre-buffering: a pipe that never closes can't hang the start),
    and the capsule keeps a copy of exactly what the run consumed —
    which is exactly what a rerun needs. input() and iteration go
    through readline; binary consumers get the wrapped .buffer."""

    def __init__(self, real, sink):
        self._real = real
        self._sink = sink
        rb = getattr(real, "buffer", None)
        if rb is not None:
            self.buffer = _StdinBufTee(rb, sink)

    def _rec(self, s):
        if s:
            try:
                enc = getattr(self._real, "encoding", None) or "utf-8"
                self._sink.feed(s.encode(enc, "replace"))
            except Exception:
                pass
        return s

    def read(self, *a):
        return self._rec(self._real.read(*a))

    def readline(self, *a):
        return self._rec(self._real.readline(*a))

    def readlines(self, *a):
        ls = self._real.readlines(*a)
        for s in ls:
            self._rec(s)
        return ls

    def __iter__(self):
        return self

    def __next__(self):
        s = self._real.readline()
        if not s:
            raise StopIteration
        return self._rec(s)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _poison_kind(enc):
    """Scan an ENCODED value for visible NaN/Inf leaves ("nan" beats
    "inf" when both appear). Working on the encoding — not the live
    object — keeps the cost bounded by the existing caps and the claim
    honest: only poison the artifact actually SHOWS is marked; anything
    beyond a window or item cap stays unknown = unmarked. Reprs like
    "np.float64(nan)" (numpy 2 scalars are float subclasses) are
    recognized by their suffix; exotic float-subclass reprs may not be —
    they stay unmarked, never mismarked."""
    if not isinstance(enc, dict):
        return None
    t = enc.get("t")
    if t == "p":
        v = enc.get("v")
        if not isinstance(v, str):
            return None
        if v in ("nan", "-nan") or v.endswith("(nan)") or v.endswith("(-nan)"):
            return "nan"
        if v in ("inf", "-inf") or v.endswith("(inf)") or v.endswith("(-inf)"):
            return "inf"
        if "complex" in (enc.get("c") or ""):
            if "nan" in v:
                return "nan"
            if "inf" in v:
                return "inf"
        return None
    if t in ("list", "tuple", "set"):
        kinds = [_poison_kind(x) for x in enc.get("v") or []]
    elif t in ("dict", "obj"):
        kinds = [_poison_kind(p[1]) for p in enc.get("v") or []
                 if isinstance(p, (list, tuple)) and len(p) == 2]
    else:
        return None
    if "nan" in kinds:
        return "nan"
    return "inf" if "inf" in kinds else None


class Tracer:
    """Callable trace hook: records call/line/return events + variable diffs."""

    def __init__(self, root, max_events=MAX_EVENTS, start_at=None,
                 start_when=None, start_count=1, include=None,
                 exclude=None, granularity="line", trip=None,
                 ring=None):
        self.root = os.path.realpath(root)
        self.max_events = max_events
        self.start_at = start_at        # (filename, lineno) trigger or None
        self.start_when = start_when    # compiled expression or None
        self.start_count = start_count  # arm on the Nth trigger hit
        self.include = include or []    # glob patterns (project-relative)
        self.exclude = exclude or []
        self.granularity = granularity  # "line" | "fn"
        self.trip = trip                # "nan" -> mark NaN/Inf births
        self._poisoned = {}   # id(frame) -> {var names currently NaN/Inf}
        self._log_count = 0
        self.log_capped = False
        self.check = None        # #70: compiled --check expression
        self.chaos = None        # #68: _Chaos instance when fuzzing
        self.watches = []        # #72: [(src, code)] observables
        self.watch_hits = {}     # #72: src -> successful evals
        self.invariants = []     # #73: [(src, code, names)] contracts
        self._inv_state = {}     # (frame id, src) -> held last time?
        self.inv_counts = {}     # src -> violations recorded
        self.inv_first = {}      # src -> event index of first violation
        self.inv_evals = {}      # src -> successful evaluations
        self.check_hit = False
        self.check_hits = 0
        self.check_evals = 0     # successful evaluations (typo honesty)
        self.check_first = None  # event index of the first hit
        self._hits = 0
        self._last_ts = time.perf_counter_ns() // 1000
        self._gen_ids = {}    # id(frame) -> generator instance number
        self._gen_next = 0
        self._func_cache = {} # code -> function object (or None)
        self._task_fn = None  # (_get_running_loop, current_task), lazy
        self._tk_pin = {}     # id(frame) -> lane pinned at trigger time
        self._tlabels = {}    # thread ident -> (thread obj, display name)
        self._tcounts = {}    # thread name -> how many threads used it
        self._tobj_labels = {}  # id(thread) -> label (#88; ident-reuse-proof)
        self._hb_objs = {}      # id(obj) -> thread/task woken by an hb
        #                         event — held so id() stays unambiguous
        #                         and task names can late-bind
        # False = watching but not recording
        self.armed = start_at is None and start_when is None
        # #103: ring mode — a bounded window that never truncates the
        # RUN, only its own memory; the cap machinery must stay silent
        self.ring = ring
        if ring:
            self.events = _Ring(ring)
            self.max_events = float("inf")
        else:
            self.events = []   # the event log — the backend/frontend contract
        self.sources = {}      # rel path -> file text, embedded for the viewer
        self._path_cache = {}  # raw co_filename -> rel path or None (= skip)
        self._snapshots = {}   # id(frame) -> {var: repr} for change detection
        # id(obj) -> (weakref|None, class name, attr encodings, attr
        # fingerprints): the last observation of each object ACROSS frames.
        # On a method-call event a promoted attribute counts as changed
        # only against this memory — not merely because the frame is new.
        # First observation = no entry = everything legitimately new
        # (shown in full). The weakref guards against id() reuse;
        # unweakrefable classes fall back to a class-name check and accept
        # the (value-identical) residual risk.
        self._objmem = {}
        self.truncated = False
        # CLI runs abort at the cap (no point running on once the trace is
        # full); in-process watch() must NOT kill its host — it uninstalls
        # the hook and lets the program run on untraced.
        self.abort_on_cap = True

    def _rel(self, filename):
        """Project-relative path for a frame's file, or None if out of scope."""
        try:
            return self._path_cache[filename]
        except KeyError:
            pass
        rel = None
        if filename and not filename.startswith("<"):
            path = os.path.realpath(filename)
            inside = path.startswith(self.root + os.sep)
            if inside and path != SELF and "site-packages" not in path:
                rel = os.path.relpath(path, self.root)
        if rel is not None and not scope_ok(rel, self.include,
                                            self.exclude):
            rel = None
        self._path_cache[filename] = rel
        return rel

    def __call__(self, frame, event, arg):
        if event == "call":
            # Returning None here tells Python: don't trace inside this
            # function. This is where stdlib/site-packages get filtered out.
            if self.truncated or self._rel(frame.f_code.co_filename) is None:
                return None
            if self.granularity == "fn":
                # keep return/exception events but silence the per-line
                # callbacks entirely — this is what makes big codebases
                # traceable (no line events, no locals encoding)
                frame.f_trace_lines = False
                self._record_fn(frame, "call", arg)
                return self
            if self.chaos is not None:
                self.chaos.pulse()
            if self.armed:
                self._record(frame, "call", arg)
            return self  # keep watching for the trigger even when not armed
        if self.granularity == "fn":
            if event in ("return", "exception") and not self.truncated:
                self._record_fn(frame, event, arg)
            return self
        if self.chaos is not None:
            # #68: every in-scope line/return/exception boundary is a
            # perturbation point, armed or not — chaos is about the RUN
            self.chaos.pulse()
        if self.check is not None and event == "line":
            # #70: the run-level predicate, watched on every in-scope
            # line (same contract as --start-when: not-evaluable-here
            # counts as False, never as an error)
            try:
                if eval(self.check, frame.f_globals, frame.f_locals):
                    if not self.check_hit:
                        self.check_first = len(self.events)
                    self.check_hit = True
                    self.check_hits += 1
                self.check_evals += 1
            except Exception:
                pass
        if not self.armed:
            if event == "line" and self._hits_trigger(frame):
                self._arm(frame)
                self._record(frame, "line", arg)
            return self
        if event in ("line", "return", "exception") and not self.truncated:
            self._record(frame, event, arg)
        if event == "return":
            self._snapshots.pop(id(frame), None)
        return self

    def chapter(self, kind, nodeid, outcome=None, f=None, l=None):
        """#98: a test boundary, reported by the injected pytest plugin.
        Chapter events ride the same stream (e="chap", k="s"|"e") so
        they scrub, filter and honor the cap like every other event."""
        if not self.armed or self.truncated \
                or len(self.events) >= self.max_events:
            return
        ev = {"e": "chap", "k": kind, "id": str(nodeid),
              "fn": str(nodeid), "ch": {}}
        if kind == "e" and outcome:
            ev["o"] = outcome
        if f:
            try:
                rel = self._rel(os.path.realpath(
                    os.path.join(os.getcwd(), f)))
            except Exception:
                rel = None
            if rel:
                ev["f"] = rel
                ev["l"] = int(l) if l else 1
                if rel not in self.sources:
                    try:
                        with open(os.path.join(self.root, rel),
                                  encoding="utf-8",
                                  errors="replace") as fh:
                            self.sources[rel] = fh.read()
                    except OSError:
                        self.sources[rel] = ""
        if self.granularity == "fn":
            now = time.perf_counter_ns() // 1000
            ev["ts"] = max(0, now - self._last_ts)
            self._last_ts = now
        tname = self._thread_label()
        if tname != "MainThread":
            ev["t"] = tname
        self.events.append(ev)

    def record_log(self, stream, text):
        """#118: one console LINE as a first-class event (e="log"),
        tied to the nearest in-scope frame up from the write. Levels
        are whatever the text says — the lane records, it never
        interprets. Cap announced via the banner."""
        if not self.armed or self.truncated \
                or len(self.events) >= self.max_events:
            return
        if self._log_count >= LOG_CAP:
            self.log_capped = True
            return
        self._log_count += 1
        if len(text) > 500:
            text = text[:500] + "…[line truncated]"
        ev = {"e": "log", "s": stream, "txt": text, "ch": {},
              "fn": "<io>"}
        f = sys._getframe(2)          # skip record_log + Tee.write
        depth = 0
        while f is not None and depth < 40:
            rel = self._rel(f.f_code.co_filename)
            if rel is not None:
                ev["f"] = rel
                ev["l"] = f.f_lineno
                ev["fn"] = f.f_code.co_name
                break
            f = f.f_back
            depth += 1
        if self.granularity == "fn":
            now = time.perf_counter_ns() // 1000
            ev["ts"] = max(0, now - self._last_ts)
            self._last_ts = now
        tname = self._thread_label()
        if tname != "MainThread":
            ev["t"] = tname
        tk = self._task_name()
        if tk is not None:
            ev["tk"] = tk
        self.events.append(ev)

    def record_hb(self, kind, dst_name, dst_obj=None):
        """#88: a happens-before edge — task created, thread started or
        joined — as a first-class event (e="hb") at the moment the wake
        action ran, attributed to the nearest in-scope frame. The
        event's own lane (t/tk) is where the action happened; "dst" is
        the OTHER lane. Direction by kind: create/tstart wake own→dst,
        tjoin means dst's end released own. A thread dst arrives as the
        Thread OBJECT (never its ident — the OS reuses idents the
        moment a thread dies) and is resolved to its lane label at
        write time (labels are assigned lazily — see resolve_hb)."""
        if not self.armed or self.truncated \
                or len(self.events) >= self.max_events:
            return
        ev = {"e": "hb", "hb": kind, "dst": str(dst_name), "ch": {},
              "fn": "<wake>"}
        if dst_obj is not None:
            self._hb_objs[id(dst_obj)] = dst_obj
            ev["_di"] = id(dst_obj)
        f = sys._getframe(2)          # skip record_hb + the hook wrapper
        depth = 0
        while f is not None and depth < 40:
            rel = self._rel(f.f_code.co_filename)
            if rel is not None:
                ev["f"] = rel
                ev["l"] = f.f_lineno
                ev["fn"] = f.f_code.co_name
                break
            f = f.f_back
            depth += 1
        if self.granularity == "fn":
            now = time.perf_counter_ns() // 1000
            ev["ts"] = max(0, now - self._last_ts)
            self._last_ts = now
        tname = self._thread_label()
        if tname != "MainThread":
            ev["t"] = tname
        tk = self._task_name()
        if tk is not None:
            ev["tk"] = tk
        self.events.append(ev)

    def resolve_hb(self):
        """#88: late-bind wake destinations. A thread's lane label
        exists only once it records an event, and a task can be RENAMED
        after creation (its lane key is the final name) — so hb events
        hold the woken OBJECT and bind the label here, at write time.
        A thread that never entered traced code keeps its raw name,
        honestly marked."""
        for e in self.events:
            di = e.pop("_di", None)
            if di is None:
                continue
            label = self._tobj_labels.get(di)
            if label is None:
                getn = getattr(self._hb_objs.get(di), "get_name", None)
                if getn is not None:      # a task: ask its FINAL name
                    try:
                        label = getn()
                    except Exception:
                        label = None
            e["dst"] = label if label is not None \
                else e["dst"] + " (never traced)"

    def _gen_mark(self, frame, event, yielding=None):
        """Generator/coroutine lifecycle: first call "c", resumption "r",
        suspension (yield/await) "y", true exhaustion "e" — one instance
        number ("i") ties every event of the sleeping frame together.
        yielding: the monitoring backend KNOWS (PY_YIELD vs PY_RETURN);
        settrace passes None and we infer it from the bytecode."""
        code = frame.f_code
        if not (code.co_flags & _GEN_FLAGS):
            return None
        kind = "c" if code.co_flags & 0x80 \
            else ("a" if code.co_flags & 0x200 else "g")
        fid = id(frame)
        if event == "call":
            inst = self._gen_ids.get(fid)
            if inst is not None:
                return {"s": "r", "i": inst, "k": kind}
            self._gen_next += 1
            self._gen_ids[fid] = self._gen_next
            return {"s": "c", "i": self._gen_next, "k": kind}
        inst = self._gen_ids.get(fid)
        if inst is None:
            return None
        if yielding if yielding is not None else _is_yield(frame):
            return {"s": "y", "i": inst, "k": kind}
        self._gen_ids.pop(fid, None)
        return {"s": "e", "i": inst, "k": kind}

    def _thread_label(self):
        """Stable display name for the current thread. Distinct threads
        that SHARE a user-assigned name get #2, #3… suffixes — the lane
        key is the label, and merging two live threads into one lane
        would silently interleave their stacks."""
        th = threading.current_thread()
        cached = self._tlabels.get(th.ident)
        if cached is not None and cached[0] is th:
            return cached[1]
        name = th.name
        n = self._tcounts.get(name, 0) + 1
        self._tcounts[name] = n
        label = name if n == 1 else f"{name} #{n}"
        self._tlabels[th.ident] = (th, label)
        # #88: idents are OS handles and get REUSED the moment a thread
        # dies — wake-edge resolution must key on the object instead
        self._tobj_labels[id(th)] = label
        return label

    def _current_task(self):
        """The asyncio task driving the current frame, or None. A task
        is a pseudo-thread: the viewer gives each one its own lane and
        call stack. Bound lazily so programs that never import asyncio
        pay one dict lookup per event; _get_running_loop (in asyncio's
        __all__) returns None instead of raising, so a sync program
        that merely imports asyncio doesn't pay a raised-and-caught
        RuntimeError on every event."""
        ct = self._task_fn
        if ct is None:
            mod = sys.modules.get("asyncio")
            if mod is None:
                return None
            get_loop = getattr(mod, "_get_running_loop", None)
            cur = getattr(mod, "current_task", None)
            if get_loop is None or cur is None:
                return None   # asyncio mid-import: retry next event
            self._task_fn = ct = (get_loop, cur)
        get_loop, cur = ct
        try:
            loop = get_loop()
            return None if loop is None else cur(loop)
        except Exception:
            return None

    def _task_name(self):
        task = self._current_task()
        if task is None:
            return None
        try:
            return task.get_name()
        except Exception:
            return None

    def _shared_defaults(self, frame):
        """The def f(x, acc=[]) trap: which arguments ARE the function's
        shared mutable default object right now. Function looked up via
        co_qualname (cached per code); nested functions are skipped."""
        code = frame.f_code
        func = self._func_cache.get(code, False)
        if func is False:
            func = None
            try:
                parts = code.co_qualname.split(".")
                if "<locals>" not in parts:
                    obj = frame.f_globals.get(parts[0])
                    for part in parts[1:]:
                        obj = getattr(obj, part, None)
                    if getattr(obj, "__code__", None) is code:
                        func = obj
            except Exception:
                func = None
            self._func_cache[code] = func
        if func is None or not getattr(func, "__defaults__", None):
            return None
        names = code.co_varnames[:code.co_argcount]
        defaults = func.__defaults__
        out = []
        for i, d in enumerate(defaults):
            if isinstance(d, (list, dict, set, bytearray)):
                pname = names[len(names) - len(defaults) + i]
                if frame.f_locals.get(pname) is d:
                    out.append(pname)
        return out or None

    def _record_fn(self, frame, event, arg, yielding=None):
        """fn-granularity recording: call/return/exception only, shallow
        args, µs timestamps (delta-encoded). No locals machinery — this
        path must stay nearly free. Both backends land here."""
        if self.chaos is not None:
            self.chaos.pulse()   # #68: fn boundaries, both backends
        if len(self.events) >= self.max_events:
            self.truncated = True
            if self.abort_on_cap:
                raise TraceLimitReached
            sys.settrace(None)          # watch(): stop recording,
            threading.settrace(None)    # let the host program run on
            return
        rel = self._rel(frame.f_code.co_filename)
        if rel is None:
            return
        if rel not in self.sources:
            try:
                with open(os.path.join(self.root, rel), encoding="utf-8",
                          errors="replace") as f:
                    self.sources[rel] = f.read()
            except OSError:
                self.sources[rel] = ""
        ev = {"e": "exc" if event == "exception" else event,
              "f": rel, "l": frame.f_lineno,
              "fn": frame.f_code.co_name, "ch": {}}
        if event == "call":
            code = frame.f_code
            for name in code.co_varnames[:code.co_argcount][:8]:
                if name in frame.f_locals:
                    ev["ch"][name] = encode(frame.f_locals[name], 1)
            mro = _mro_info(frame)
            if mro is not None:
                ev["mro"] = mro
            if code.co_freevars or code.co_cellvars:
                ev["cl"] = {"f": list(code.co_freevars),
                            "c": list(code.co_cellvars)}
            da = self._shared_defaults(frame)
            if da:
                ev["da"] = da
        if event in ("call", "return"):
            gm = self._gen_mark(frame, event, yielding)
            if gm is not None:
                ev["g"] = gm
        if event == "return":
            ev["ret"] = encode(arg, 1)
        elif event == "exception":
            ev["x"] = _exc_info(arg)
        # timestamps live ONLY in fn traces: at line granularity the
        # program runs ~100x slow and wall times would be fiction.
        # _last_ts is shared across threads without a lock (this path
        # must stay nearly free); a GIL switch inside these three lines
        # can produce a negative delta, so clamp — consumers rebuild
        # absolute time by cumulative sum and must never run backwards.
        now = time.perf_counter_ns() // 1000
        ev["ts"] = max(0, now - self._last_ts)
        self._last_ts = now
        tname = self._thread_label()
        if tname != "MainThread":
            ev["t"] = tname
        tk = self._task_name()
        if tk is not None:
            ev["tk"] = tk
        self.events.append(ev)

    def _hits_trigger(self, frame):
        if self.start_at:
            fname, lineno = self.start_at
            if frame.f_lineno != lineno:
                return False
            rel = self._rel(frame.f_code.co_filename)
            if rel is None or (rel != fname and os.path.basename(rel) != fname):
                return False
        if self.start_when:
            try:
                if not eval(self.start_when, frame.f_globals, frame.f_locals):
                    return False
            except Exception:
                return False  # e.g. the variable doesn't exist yet
        self._hits += 1
        return self._hits >= self.start_count

    def _arm(self, frame):
        """Trigger hit: start recording, first replaying the live call stack
        so the viewer opens with the correct stack and all current variables
        (each frame's full locals appear as its first 'changed' set)."""
        self.armed = True
        # If the trigger fired inside an asyncio task, only the frames of
        # the task's own coroutine chain belong to its lane — the frames
        # beneath it (module, asyncio.run caller) must NOT be stamped with
        # the task name, or the viewer would mis-lane them. The boundary
        # is the task's outermost coroutine frame; unknown = unmarked.
        task_frames = set()
        tkname = self._task_name()
        if tkname is not None:
            try:
                boundary = self._current_task().get_coro().cr_frame
                f = frame
                while f is not None:
                    task_frames.add(id(f))
                    if f is boundary:
                        break
                    f = f.f_back
                else:
                    task_frames = set()   # boundary not found: don't guess
            except Exception:
                task_frames = set()
        chain = []
        f = frame
        while f is not None:
            if self._rel(f.f_code.co_filename) is not None:
                chain.append(f)
            f = f.f_back
        for f in reversed(chain):
            # PIN each replayed frame's lane: all its later events must
            # land in the same lane, even when the boundary walk failed
            # and the guess is "no task" — a frame split across two
            # lanes would corrupt both lanes' stacks in the viewer
            if tkname is not None:
                self._tk_pin[id(f)] = \
                    tkname if id(f) in task_frames else None
            self._record(f, "call", None,
                         tk=tkname if id(f) in task_frames else None)
        print(f"pyreplay: trigger hit (occurrence #{self._hits}), "
              f"recording started", file=_RAW["out"], flush=True)

    def _record(self, frame, event, arg, tk="auto"):
        if len(self.events) >= self.max_events:
            self.truncated = True
            if self.abort_on_cap:
                # raising from the trace hook disables tracing and unwinds
                # the target — no point running on once the trace is full
                raise TraceLimitReached
            sys.settrace(None)          # watch(): stop recording,
            threading.settrace(None)    # let the host program run on
            return
        rel = self._rel(frame.f_code.co_filename)
        if rel is None:
            return
        if rel not in self.sources:
            try:
                with open(os.path.join(self.root, rel), encoding="utf-8",
                          errors="replace") as f:
                    self.sources[rel] = f.read()
            except OSError:
                self.sources[rel] = ""

        gm = self._gen_mark(frame, event) \
            if event in ("call", "return") else None

        # Variable-change detection: diff current locals against the last
        # snapshot of this same frame. Only the delta goes into the event.
        # Values are structured encodings; large containers additionally
        # keep a shadow copy (fingerprint) so changes beyond the encoded
        # head are detected and reported as a change-centered window.
        # The snapshot also carries id() so the diff can distinguish
        # MUTATION (same object changed — every alias changed too) from
        # REBINDING (the name points elsewhere), and spot aliases.
        old = self._snapshots.get(id(frame), {})
        if gm is not None and gm["s"] == "r":
            old = {}   # a resumed generator re-emits its full live state
        cur = {}
        changed = {}
        muts = []
        by_oid = {}
        items = frame.f_locals.items()
        if self.watches:
            # #72: watch expressions ride the SAME diff machinery as
            # real locals — change detection, life navigation, charts
            # and windows come free. Eval failure in a frame where the
            # watch was alive records the honest hole; never evaluable
            # here records nothing (the end-of-run warning catches a
            # watch that never evaluated ANYWHERE).
            items = list(items)
            for wsrc, wcode in self.watches:
                wkey = "watch:" + wsrc
                try:
                    items.append((wkey, eval(wcode, frame.f_globals,
                                             frame.f_locals)))
                    self.watch_hits[wsrc] = \
                        self.watch_hits.get(wsrc, 0) + 1
                except Exception:
                    if wkey in old:
                        items.append((wkey, _UNEVALUABLE))
        for name, value in items:
            if name.startswith("__"):
                continue
            enc = encode(value)
            fp = fingerprint(value)
            oid = None if isinstance(value, _FP_FAST_NONE + (tuple,
                                     frozenset)) else id(value)
            cur[name] = (enc, fp, oid)
            if oid is not None:
                by_oid.setdefault(oid, []).append(name)
            oldpair = old.get(name)
            try:
                same = (oldpair is not None
                        and oldpair[0] == enc and oldpair[1] == fp)
            except Exception:
                same = False    # incomparable fingerprints: report it
            if not same:
                changed[name] = windowed_value(
                    value, enc, fp, oldpair[1] if oldpair else None)
                if oldpair is not None and oid is not None \
                        and oldpair[2] == oid:
                    muts.append(name)
            if isinstance(enc, dict) and enc.get("t") == "obj" \
                    and oid is not None:
                # frame birth re-emits every attr as "changed"; diff the
                # object against its LAST OBSERVATION instead, and stamp
                # the honest changed-attr list (possibly EMPTY — "seen
                # before, nothing moved"). No memory = first observation
                # = no stamp = everything shown, honestly new. Encodings
                # are the comparable unit (they exist for every attr);
                # fingerprints supplement for deep-beyond-head changes.
                fps = fp[1] if (isinstance(fp, tuple) and fp
                                and fp[0] == "obj") else {}
                if event == "call" and oldpair is None \
                        and name in changed:
                    mem = self._objmem.get(oid)
                    if mem is not None and (
                            mem[0]() is not None if mem[0] is not None
                            else mem[1] == type(value).__name__):
                        cha = []
                        for ak, aenc in enc.get("v", []):
                            try:
                                moved = mem[2].get(ak) != aenc
                                if not moved:
                                    pf, nf = mem[3].get(ak), fps.get(ak)
                                    if pf is not None or nf is not None:
                                        moved = pf is not nf and pf != nf
                            except Exception:
                                moved = True
                            if moved:
                                cha.append(ak)
                        changed[name] = {**changed[name], "cha": cha}
                try:
                    wr = weakref.ref(value)
                except TypeError:
                    wr = None
                self._objmem[oid] = (wr, type(value).__name__,
                                     dict(enc.get("v", [])), fps)
        if len(self._objmem) > 8192:   # prune dead entries, bounded memory
            self._objmem = {k: m for k, m in self._objmem.items()
                            if m[0] is not None and m[0]() is not None}
        self._snapshots[id(frame)] = cur
        ali = [v for v in by_oid.values() if len(v) > 1]

        # NaN/Inf tripwire (--trip nan): mark the moment a variable's
        # poison KIND changes — clean -> nan/inf, and also inf -> nan
        # (an inf that collapses to nan IS a new birth; without the
        # kind memory the run's first NaN could hide inside an
        # already-inf variable). Stable poison re-marks nothing; a
        # recovery re-arms, so a relapse marks again.
        trips = []
        if self.trip:
            pmap = self._poisoned.setdefault(id(frame), {})
            for name, encv in changed.items():
                kind = _poison_kind(encv)
                if kind:
                    if pmap.get(name) != kind:
                        pmap[name] = kind
                        trips.append({"v": name, "k": kind})
                else:
                    pmap.pop(name, None)   # recovered — a relapse re-marks

        ev = {"e": "exc" if event == "exception" else event,
              "f": rel, "l": frame.f_lineno,
              "fn": frame.f_code.co_name, "ch": changed}
        if event == "return":
            ev["ret"] = encode(arg)
            if self.trip:
                # poison leaving THROUGH the return value — visible even
                # when the caller never assigns it (print(f(x)))
                rkind = _poison_kind(ev["ret"])
                if rkind and (gm is None or gm["s"] != "y"):
                    trips.append({"v": "<return>", "k": rkind})
            if gm is None or gm["s"] != "y":
                # true frame death (a yield keeps its poison memory — a
                # resumed generator's NaN is old news, not a new birth)
                self._poisoned.pop(id(frame), None)
        elif event == "exception":
            ev["x"] = _exc_info(arg)
        elif event == "call":
            mro = _mro_info(frame)
            if mro is not None:
                ev["mro"] = mro
            code = frame.f_code
            if code.co_freevars or code.co_cellvars:
                ev["cl"] = {"f": list(code.co_freevars),
                            "c": list(code.co_cellvars)}
            da = self._shared_defaults(frame)
            if da:
                ev["da"] = da
        if gm is not None:
            ev["g"] = gm
        if muts:
            ev["mut"] = muts
        if ali:
            ev["ali"] = ali
        if trips:
            ev["trip"] = trips
        tname = self._thread_label()
        if tname != "MainThread":
            ev["t"] = tname
        if tk == "auto":
            if self._tk_pin:
                fid = id(frame)
                tk = self._tk_pin[fid] if fid in self._tk_pin \
                    else self._task_name()
                # a pin dies with its frame (true return, not a yield) —
                # otherwise a recycled frame id would inherit the lane
                if event == "return" and fid in self._tk_pin \
                        and (gm is None or gm["s"] != "y"):
                    del self._tk_pin[fid]
            else:
                tk = self._task_name()
        if tk is not None:
            ev["tk"] = tk
        self.events.append(ev)
        if self.invariants and event == "line":
            self._check_invariants(frame, ev)

    def _record_br(self, frame, info, taken):
        """#86: one sub-line branch verdict — the column-precise truth
        of a ternary test, an and/or operand, or a comprehension's if,
        straight from the interpreter's BRANCH event."""
        if not self.armed or self.truncated \
                or len(self.events) >= self.max_events:
            return
        rel = self._rel(frame.f_code.co_filename)
        if rel is None:
            return
        _target, op, l0, c0, l1, c1 = info
        ev = {"e": "br", "f": rel, "l": l0, "fn": frame.f_code.co_name,
              "c0": c0, "c1": c1, "op": op, "r": bool(taken),
              "ch": {}}
        if l1 is not None and l1 != l0:
            ev["l1"] = l1
        tname = self._thread_label()
        if tname != "MainThread":
            ev["t"] = tname
        tk = (self._tk_pin.get(id(frame)) if self._tk_pin else None) \
            or self._task_name()
        if tk is not None:
            ev["tk"] = tk
        self.events.append(ev)

    def _check_invariants(self, frame, line_ev):
        """#73: contracts checked at every line event. A VIOLATION is
        the TRANSITION into falsehood — recovery re-arms, the #79 trip
        pattern — recorded as its own soft event carrying the values
        of the expression's names. Unevaluable here = the frame
        doesn't define the names = out of scope, never a violation."""
        for src, code, names in self.invariants:
            key = (id(frame), src)
            try:
                ok = bool(eval(code, frame.f_globals, frame.f_locals))
            except Exception:
                self._inv_state.pop(key, None)
                continue
            self.inv_evals[src] = self.inv_evals.get(src, 0) + 1
            if ok:
                self._inv_state[key] = True
                continue
            if self._inv_state.get(key) is False:
                continue          # still down — one event per entry
            self._inv_state[key] = False
            vals = {}
            for n in names:
                if n in frame.f_locals:
                    vals[n] = encode(frame.f_locals[n], 1)
                elif n in frame.f_globals:
                    vals[n] = encode(frame.f_globals[n], 1)
            vev = {"e": "viol", "inv": src, "f": line_ev["f"],
                   "l": line_ev["l"], "fn": line_ev["fn"], "ch": {},
                   "vals": vals}
            if "t" in line_ev:
                vev["t"] = line_ev["t"]
            if "tk" in line_ev:
                vev["tk"] = line_ev["tk"]
            self.inv_counts[src] = self.inv_counts.get(src, 0) + 1
            if src not in self.inv_first:
                self.inv_first[src] = len(self.events)
            self.events.append(vev)


MON = getattr(sys, "monitoring", None)   # PEP 669, Python 3.12+


def _install_hb_hooks(tracer):
    """#88: wrap the wake primitives — threading.Thread.start/join and
    the event loop's create_task (the funnel for asyncio.create_task,
    ensure_future, gather and TaskGroup) — so causality lands in the
    stream as hb events. Class-level patches; returns the undo list.
    v1 records create/start/join; cancel and queue put→get correlation
    are the roadmap remainder."""
    undo = []
    t_start = threading.Thread.start

    def start_hb(self, *a, **kw):
        # the edge is recorded BEFORE the OS gets the child: a started
        # thread can run its whole life before start() returns, and the
        # wake must precede its consequences in the stream
        try:
            tracer.record_hb("tstart", self.name, self)
        except Exception:
            pass
        return t_start(self, *a, **kw)
    threading.Thread.start = start_hb
    undo.append(lambda: setattr(threading.Thread, "start", t_start))

    t_join = threading.Thread.join

    def join_hb(self, *a, **kw):
        r = t_join(self, *a, **kw)
        try:
            if not self.is_alive():   # a timed-out join released nobody
                tracer.record_hb("tjoin", self.name, self)
        except Exception:
            pass
        return r
    threading.Thread.join = join_hb
    undo.append(lambda: setattr(threading.Thread, "join", t_join))

    try:
        import asyncio.base_events as _abe
        l_create = _abe.BaseEventLoop.create_task

        def create_hb(self, coro, **kw):
            task = l_create(self, coro, **kw)
            try:
                tracer.record_hb("create", task.get_name(), task)
            except Exception:
                pass
            return task
        _abe.BaseEventLoop.create_task = create_hb
        undo.append(lambda: setattr(_abe.BaseEventLoop, "create_task",
                                    l_create))
    except Exception:
        pass   # no asyncio here: thread edges still work
    return undo


class MonitoringBackend:
    """#19: sys.monitoring recorder (--backend monitoring, 3.12+).
    Same events, same schema, one difference under the hood: code that
    is out of scope returns DISABLE at its first event and never fires
    again — the stdlib costs ~nothing instead of one discarded callback
    per call, so fn granularity becomes nearly free. yield/resume/
    unwind arrive as FIRST-CLASS events here (settrace has to infer
    them from bytecode). PEP 669 guarantees callbacks don't trigger
    events for their own tool, so recording can't recurse into itself.
    settrace parity rules: a suspension is a return (PY_YIELD), a
    throw-resume is a call (PY_THROW), and an exception shows up once
    per frame it touches — at the raise, in every frame it unwinds,
    and in the frame that finally handles it."""

    def __init__(self, tracer, line_mode=False):
        self.t = tracer
        self.tool = None
        self.line_mode = line_mode   # #102: LINE via set_local_events
        self._armed = set()          # code ids already given local LINE
        self._brmaps = {}            # #86: code id -> offset -> branch
        self._mark = None   # (frame id, exc id) already recorded "exc"
        self._callbacks = None   # (event, fn) pairs, so stop() can detach

    def start(self):
        # PROFILER_ID is ours by right; fall back to the general-purpose
        # ids (3, 4) BEFORE the semantically reserved DEBUGGER(0)/
        # COVERAGE(1)/OPTIMIZER(5) slots, so a coexisting pdb or coverage
        # run — which has as much claim to those as we do — keeps its slot.
        for tid in (MON.PROFILER_ID, 3, 4, 0, 1, 5):
            if MON.get_tool(tid) is None:
                self.tool = tid
                break
        if self.tool is None:
            raise RuntimeError("no free sys.monitoring tool id")
        MON.use_tool_id(self.tool, "pyreplay")
        E = MON.events
        # RERAISE goes to _reraise (dedup), NOT _raise: the interpreter
        # re-fires RERAISE for one exception every time it crosses a
        # finally / non-matching except / with cleanup, and settrace
        # reports such a propagation only once per frame.
        self._callbacks = (
            (E.PY_START, self._start),
            (E.PY_RESUME, self._resume),
            (E.PY_THROW, self._throw),
            (E.PY_RETURN, self._return),
            (E.PY_YIELD, self._yield),
            (E.PY_UNWIND, self._unwind),
            (E.RAISE, self._raise),
            (E.RERAISE, self._reraise),
            (E.EXCEPTION_HANDLED, self._handled),
            (E.STOP_ITERATION, self._stopiter),
        )
        if self.line_mode:
            # #102: LINE is registered but NOT in the global mask — a
            # per-code set_local_events arms it only for in-scope code
            # objects (the whole trick: the stdlib never fires a line)
            # #86: BRANCH rides the same per-code arming — sub-line
            # verdicts at column precision, only where code is ours
            self._callbacks += ((E.LINE, self._line),
                                (E.BRANCH, self._branch))
        try:
            mask = 0
            for ev, fn in self._callbacks:
                MON.register_callback(self.tool, ev, fn)
                if not (self.line_mode and ev == E.LINE):
                    mask |= ev
            MON.set_events(self.tool, mask)
        except BaseException:
            self.stop()   # a half-built tool must not leak into the interp
            raise

    def stop(self):
        if self.tool is None:
            return
        try:
            MON.set_events(self.tool, 0)
        except Exception:
            pass
        # free_tool_id releases the NAME but leaves callbacks bound to the
        # id (PEP 669) — detach them by hand, or a later tool that reuses
        # the id would fire our callbacks against this dead Tracer.
        for ev, _ in (self._callbacks or ()):
            try:
                MON.register_callback(self.tool, ev, None)
            except Exception:
                pass
        try:
            MON.free_tool_id(self.tool)
        except Exception:
            pass
        self.tool = None
        self._callbacks = None

    def _skip(self, code):
        return self.t.truncated or self.t._rel(code.co_filename) is None

    def _arm(self, code):
        # #102: first entry into an in-scope code object switches its
        # LINE events on — locally, for this code object only
        if self.line_mode and id(code) not in self._armed:
            self._armed.add(id(code))
            try:
                MON.set_local_events(self.tool, code,
                                     MON.events.LINE
                                     | MON.events.BRANCH)
            except Exception:
                pass

    def _call_ev(self, frame):
        if self.line_mode:
            # through the DISPATCHER, not _record: triggers, --check,
            # chaos pulses and the snapshot pop are the dispatcher's —
            # parity with settrace by construction
            self.t(frame, "call", None)
        else:
            self.t._record_fn(frame, "call", None)

    def _exc_ev(self, frame, exc):
        if self.line_mode:
            self.t(frame, "exception", (type(exc), exc, None))
        else:
            self.t._record_fn(frame, "exception",
                              (type(exc), exc, None))

    def _line(self, code, line):
        # only armed (in-scope) code objects ever fire this
        self.t(sys._getframe(1), "line", None)

    # #86: conditional-branch instructions worth a verdict, with the
    # semantic each op gives to "took the jump". FOR_ITER is excluded
    # on purpose: iteration truth is the whole-line verdict's job.
    BR_OPS = {"POP_JUMP_IF_FALSE": "pjf", "POP_JUMP_IF_TRUE": "pjt",
              "POP_JUMP_IF_NONE": "pjn",
              "POP_JUMP_IF_NOT_NONE": "pjnn",
              "JUMP_IF_FALSE_OR_POP": "pjf",
              "JUMP_IF_TRUE_OR_POP": "pjt"}

    def _brmap(self, code):
        m = self._brmaps.get(id(code))
        if m is None:
            m = {}
            try:
                for ins in dis.get_instructions(code):
                    op = self.BR_OPS.get(ins.opname)
                    if op is None:
                        continue
                    pos = getattr(ins, "positions", None)
                    if pos is None or pos.lineno is None:
                        continue
                    m[ins.offset] = (ins.argval, op, pos.lineno,
                                     pos.col_offset, pos.end_lineno,
                                     pos.end_col_offset)
            except Exception:
                pass
            self._brmaps[id(code)] = m
        return m

    def _branch(self, code, off, dest):
        info = self._brmap(code).get(off)
        if info is None:
            return               # FOR_ITER and friends: not ours
        self.t._record_br(sys._getframe(1), info,
                          dest == info[0])

    def _start(self, code, off):
        if self._skip(code):
            return MON.DISABLE   # this location never fires again
        self._arm(code)
        self._call_ev(sys._getframe(1))

    def _resume(self, code, off):
        if self._skip(code):
            return MON.DISABLE
        self._arm(code)
        self._call_ev(sys._getframe(1))

    def _throw(self, code, off, exc):
        if not self._skip(code):   # throw events can't be DISABLEd
            self._arm(code)
            self._call_ev(sys._getframe(1))

    def _return(self, code, off, retval):
        if self._skip(code):
            return MON.DISABLE
        if self.line_mode:
            self.t(sys._getframe(1), "return", retval)
        else:
            self.t._record_fn(sys._getframe(1), "return", retval,
                              yielding=False)

    def _yield(self, code, off, retval):
        if self._skip(code):
            return MON.DISABLE
        if self.line_mode:
            self.t(sys._getframe(1), "return", retval)
        else:
            self.t._record_fn(sys._getframe(1), "return", retval,
                              yielding=True)

    def _raise(self, code, off, exc):
        # a genuinely NEW exception being raised here — always an event
        # (a distinct exc object; RAISE never fires twice for one raise)
        if self._skip(code):
            return
        frame = sys._getframe(1)
        self._mark = (id(frame), id(exc))
        self._exc_ev(frame, exc)

    def _reraise(self, code, off, exc):
        # the SAME exception re-raised as it propagates through cleanup
        # (finally / non-matching except / with / bare `raise`). Record it
        # once per (frame, exc) and dedup the rest — same guard _handled
        # and _unwind use — so one propagation isn't logged many times.
        if self._skip(code):
            return
        frame = sys._getframe(1)
        if self._mark != (id(frame), id(exc)):
            self._mark = (id(frame), id(exc))
            self._exc_ev(frame, exc)

    def _unwind(self, code, off, exc):
        # exceptional exit: settrace shows exception-then-return in
        # EVERY frame the exception kills — replicate exactly (the
        # raising frame already recorded its exc via _raise)
        if self._skip(code):
            return
        frame = sys._getframe(1)
        if self._mark != (id(frame), id(exc)):
            self._exc_ev(frame, exc)
        if self.line_mode:
            self.t(frame, "return", None)
        else:
            # yielding=None (not False): a generator killed while
            # suspended at a yield must be tagged by the same bytecode
            # inference settrace uses, or its lifecycle scope reads
            # "e" where settrace says "y".
            self.t._record_fn(frame, "return", None, yielding=None)

    def _stopiter(self, code, off, exc):
        # the IMPLICIT StopIteration that closes a `yield from` / `await`:
        # the interpreter swallows it as control flow, but settrace surfaces
        # it as a soft exc, so mirror that. Each occurrence is a DISTINCT
        # control-flow signal (asyncio reuses the exc object across awaits,
        # so we must NOT dedup on it), hence record like a fresh raise. An
        # EXPLICIT `raise StopIteration` arrives via _raise, so the for-loop
        # case never double-counts.
        if self._skip(code):
            return
        frame = sys._getframe(1)
        self._mark = (id(frame), id(exc))
        self._exc_ev(frame, exc)

    def _handled(self, code, off, exc):
        # the frame that CATCHES a propagated exception gets an exc
        # event under settrace; locally-caught ones already recorded
        if self._skip(code):
            return
        frame = sys._getframe(1)
        if self._mark != (id(frame), id(exc)):
            self._mark = (id(frame), id(exc))
            self._exc_ev(frame, exc)


def build_line_vars(source, filename="<unknown>"):
    """Static analysis: variable names mentioned on each source line, in
    order of appearance. The viewer uses this to show, on ANY line, the
    values the line is about to work with — before it executes."""
    out = {}
    try:
        # filename attributes compiler warnings to the real file
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return out
    per_line = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            per_line.setdefault(node.lineno, []).append(
                (node.col_offset, node.id))
    for line, pairs in per_line.items():
        names = []
        for _, name in sorted(pairs):
            if name not in names:
                names.append(name)
        out[line] = names[:8]
    return out


def build_line_attrs(source, filename="<unknown>"):
    """Static analysis: which ATTRIBUTES of each base name a line mentions
    (`r = s.G @ o` -> {L: {"s": ["G"]}}). A base that also appears BARE on
    the line (`probe(s) + s.G`) is omitted — the line works with the whole
    object, so the viewer must not narrow it. Chains record the first hop
    only (`s.a.b` -> "a"). The viewer uses this to show just the mentioned
    attribute rows of an object instead of its full dump; anything this
    pass cannot see (getattr, computed access) simply isn't recorded and
    the viewer falls back to the whole object — unknown = show all."""
    out = {}
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return out
    consumed = set()      # id() of Name nodes that are an Attribute's base
    attr_pairs = {}       # line -> [(col, base, attr)]
    bare = {}             # line -> {base names used on their own}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) \
                and isinstance(node.value, ast.Name):
            nm = node.value
            consumed.add(id(nm))
            attr_pairs.setdefault(nm.lineno, []).append(
                (nm.col_offset, nm.id, node.attr))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and id(node) not in consumed:
            bare.setdefault(node.lineno, set()).add(node.id)
    for line, pairs in attr_pairs.items():
        per_base = {}
        for _, base, attr in sorted(pairs):
            if base in bare.get(line, ()):
                continue
            lst = per_base.setdefault(base, [])
            if attr not in lst and len(lst) < 8:
                lst.append(attr)
        if per_base:
            out[line] = per_base
    return out


def build_dataflow(source, filename="<unknown>"):
    """Static data-flow: for each assignment line, which SOURCE names feed
    each TARGET name. `c = a + b` -> {L: {"c": ["a", "b"]}}. Powers the
    provenance panel — select a changed variable, see what produced it,
    each linked (by the viewer) to its OWN last change. Names only, no
    value-stack simulation, so it's cheap and version-proof; the dynamic
    trace supplies 'when each source last changed'. Attribute/subscript
    targets (obj.x, d[k]) yield no simple name and are skipped."""
    out = {}
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return out

    def names_in(node):
        seen, names = set(), []
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and n.id not in seen:
                seen.add(n.id)
                names.append(n.id)
        return names[:8]

    def targets(t):
        if isinstance(t, ast.Name):
            yield t.id
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                yield from targets(e)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            d = out.setdefault(node.lineno, {})
            # a, b = x, y  -> a<-x, b<-y positionally (precise for swaps);
            # everything else: each target draws from ALL right-hand names
            tg = node.targets[0] if len(node.targets) == 1 else None
            if (isinstance(tg, (ast.Tuple, ast.List))
                    and isinstance(node.value, (ast.Tuple, ast.List))
                    and len(tg.elts) == len(node.value.elts)):
                for tgt, val in zip(tg.elts, node.value.elts):
                    for tn in targets(tgt):
                        d[tn] = names_in(val)
            else:
                srcs = names_in(node.value)
                for t in node.targets:
                    for tn in targets(t):
                        d[tn] = srcs
        elif isinstance(node, ast.AugAssign):
            # x += y  ->  x <- [x, y]  (the old x is part of the new value)
            for tn in targets(node.target):
                srcs = names_in(node.value)
                out.setdefault(node.lineno, {})[tn] = (
                    [tn] + [s for s in srcs if s != tn])[:8]
        elif isinstance(node, ast.AnnAssign):
            if node.value is not None:
                for tn in targets(node.target):
                    out.setdefault(node.lineno, {})[tn] = \
                        names_in(node.value)
        elif isinstance(node, ast.NamedExpr):
            if isinstance(node.target, ast.Name):
                out.setdefault(node.lineno, {})[node.target.id] = \
                    names_in(node.value)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            # the loop variable draws from the iterable — the most
            # common chain link a backward slice (#75) has to cross
            for tn in targets(node.target):
                out.setdefault(node.lineno, {})[tn] = \
                    names_in(node.iter)
        elif isinstance(node, ast.Return):
            if node.value is not None:
                # "<return>" pseudo-target: #75 crosses call
                # boundaries by walking a return value back to the
                # return statement's own source names
                out.setdefault(node.lineno, {})["<return>"] = \
                    names_in(node.value)
    return out


def build_branch_map(source, filename="<unknown>"):
    """Static analysis of every branching construct: if/while tests,
    for-loop iterables, except clauses, match cases. Records the
    expression text and where the taken branch starts; the dynamic
    trace is matched against this to infer what execution decided."""
    out = {}
    try:
        # filename attributes compiler warnings to the real file
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return out

    def add(lineno, tend, expr_node, body, kind, loop_end=None):
        if not body:
            return
        body_line = body[0].lineno
        if body_line == lineno:
            return   # single-line body: next-line inference ambiguous
        expr = ""
        if expr_node is not None:
            try:
                expr = ast.get_source_segment(source, expr_node) or ""
            except Exception:
                expr = ""
        info = {"lineno": lineno, "tend": tend,
                "x": expr[:MAX_REPR], "body": body_line, "k": kind}
        if loop_end is not None:
            info["end"] = loop_end   # loop extent: detects fresh entry
        out[lineno] = info

    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While)):
            add(node.lineno, getattr(node.test, "end_lineno", node.lineno),
                node.test, node.body, "if")
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            add(node.lineno, getattr(node.iter, "end_lineno", node.lineno),
                node.iter, node.body, "for",
                getattr(node, "end_lineno", node.lineno))
        elif isinstance(node, ast.Try):
            for h in node.handlers:
                add(h.lineno,
                    getattr(h.type, "end_lineno", h.lineno)
                    if h.type is not None else h.lineno,
                    h.type, h.body, "except")
        elif isinstance(node, ast.Match):
            for c in node.cases:
                probe = c.guard if c.guard is not None else c.pattern
                add(c.pattern.lineno,
                    getattr(probe, "end_lineno", c.pattern.lineno),
                    c.pattern, c.body, "case")
    return out


def _branch_result(info, line):
    """Which branch did execution take? None = still inside the test
    expression (multi-line conditions fire several line events)."""
    if line == info["body"]:
        return True
    if info["lineno"] <= line <= info["tend"]:
        return None
    return False


def build_guards(text, rel):
    """#77 whyline: for every line, the INNERMOST control structure
    that decides whether it runs — {"line": [controller_line, kind]}
    with kind in then/else/loop/loopelse/except/case/def. The chain
    ("why didn't this run?") emerges by walking the map upward.
    Parent extents are stamped first, bodies re-stamped on recursion,
    so the innermost controller wins by construction."""
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return {}
    guards = {}

    def stamp(node, ctl):
        ln = getattr(node, "lineno", None)
        if ln is None or ctl is None:
            return
        end = getattr(node, "end_lineno", None) or ln
        for k in range(ln, end + 1):
            guards[k] = ctl

    def visit(stmts, ctl):
        for node in stmts:
            stamp(node, ctl)
            if isinstance(node, ast.If):
                visit(node.body, [node.lineno, "then"])
                visit(node.orelse, [node.lineno, "else"])
            elif isinstance(node, ast.While):
                visit(node.body, [node.lineno, "loop"])
                visit(node.orelse, [node.lineno, "loopelse"])
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                visit(node.body, [node.lineno, "loop"])
                visit(node.orelse, [node.lineno, "loopelse"])
            elif isinstance(node, (ast.Try,
                                   getattr(ast, "TryStar", ast.Try))):
                visit(node.body, ctl)
                for h in node.handlers:
                    visit(h.body, [h.lineno, "except"])
                visit(node.orelse, ctl)
                visit(node.finalbody, ctl)
            elif isinstance(node, (ast.FunctionDef,
                                   ast.AsyncFunctionDef)):
                visit(node.body, [node.lineno, "def"])
            elif isinstance(node, ast.ClassDef):
                visit(node.body, ctl)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                visit(node.body, ctl)
            elif hasattr(ast, "Match") and isinstance(node, ast.Match):
                for case_ in node.cases:
                    visit(case_.body, [node.lineno, "case"])

    visit(tree.body, None)
    return {str(k): v for k, v in guards.items()}


def build_shadows(text, rel):
    """#122 static tier: per-def name masking — locals that shadow a
    builtin, a module-level name, or an enclosing function's local.
    Scope-collision bugs read correctly and RESOLVE wrongly; the
    badge marks the name at the moment the frame actually holds it.
    Records keyed by span; the renderer picks the innermost."""
    import builtins as _bi
    BUILTINS = set(dir(_bi))
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return None

    def name_targets(node, out, line):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                out.setdefault(sub.id, line)

    def bound_names(fn_node):
        """Names bound in this def's own scope: args, assignments,
        loop/with/except targets, local imports, nested def/class
        names, walrus targets. Nested defs are their own scope and
        are not descended into."""
        out = {}
        a = fn_node.args
        for arg in (a.posonlyargs + a.args + a.kwonlyargs +
                    ([a.vararg] if a.vararg else []) +
                    ([a.kwarg] if a.kwarg else [])):
            out.setdefault(arg.arg, fn_node.lineno)

        def stmts(body):
            for st in body:
                if isinstance(st, (ast.FunctionDef,
                                   ast.AsyncFunctionDef, ast.ClassDef)):
                    out.setdefault(st.name, st.lineno)
                    continue                 # a different scope
                if isinstance(st, ast.Assign):
                    for t in st.targets:
                        name_targets(t, out, st.lineno)
                elif isinstance(st, (ast.AugAssign, ast.AnnAssign)):
                    name_targets(st.target, out, st.lineno)
                elif isinstance(st, (ast.For, ast.AsyncFor)):
                    name_targets(st.target, out, st.lineno)
                elif isinstance(st, (ast.Import, ast.ImportFrom)):
                    for al in st.names:
                        nm = (al.asname or al.name).split(".")[0]
                        if nm != "*":
                            out.setdefault(nm, st.lineno)
                elif isinstance(st, (ast.With, ast.AsyncWith)):
                    for it in st.items:
                        if it.optional_vars is not None:
                            name_targets(it.optional_vars, out,
                                         st.lineno)
                if isinstance(st, ast.ExceptHandler) and st.name:
                    out.setdefault(st.name, st.lineno)
                # walrus binds in the enclosing function scope; other
                # expression subtrees can hide one too
                for sub in ast.walk(st):
                    if isinstance(sub, ast.NamedExpr) and \
                            isinstance(sub.target, ast.Name):
                        out.setdefault(sub.target.id,
                                       getattr(sub, "lineno",
                                               st.lineno))
                for ch in ast.iter_child_nodes(st):
                    body2 = getattr(ch, "body", None)
                    if isinstance(body2, list) and not isinstance(
                            ch, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                        stmts([ch] if isinstance(ch, ast.ExceptHandler)
                              else body2)
                        for extra in ("orelse", "finalbody",
                                      "handlers"):
                            more = getattr(ch, extra, None)
                            if isinstance(more, list):
                                stmts(more)
                if hasattr(st, "body") and isinstance(st.body, list):
                    stmts(st.body)
                for extra in ("orelse", "finalbody", "handlers"):
                    more = getattr(st, extra, None)
                    if isinstance(more, list):
                        stmts(more)
        stmts(fn_node.body)
        return out

    mod_names = {}
    for st in tree.body:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef,
                           ast.ClassDef)):
            mod_names.setdefault(st.name, st.lineno)
        elif isinstance(st, ast.Assign):
            for t in st.targets:
                name_targets(t, mod_names, st.lineno)
        elif isinstance(st, (ast.AugAssign, ast.AnnAssign, ast.For,
                             ast.AsyncFor)):
            name_targets(st.target, mod_names, st.lineno)
        elif isinstance(st, (ast.Import, ast.ImportFrom)):
            for al in st.names:
                nm = (al.asname or al.name).split(".")[0]
                if nm != "*":
                    mod_names.setdefault(nm, st.lineno)
    recs = []

    def visit(node, enclosing):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = bound_names(ch)
                sh = {}
                for nm in sorted(names):
                    if nm in ("self", "cls", "_"):
                        continue
                    hit = None
                    for enc_names, _l0 in reversed(enclosing):
                        if nm in enc_names:
                            hit = ["enclosing", "L%d" % enc_names[nm]]
                            break
                    if hit is None and nm in mod_names \
                            and nm != ch.name:
                        hit = ["global", "L%d" % mod_names[nm]]
                    if hit is None and nm in BUILTINS:
                        hit = ["builtin", ""]
                    if hit is not None:
                        sh[nm] = hit
                if sh:
                    recs.append({"l0": ch.lineno,
                                 "l1": ch.end_lineno or ch.lineno,
                                 "fn": ch.name, "sh": sh})
                visit(ch, enclosing + [(names, ch.lineno)])
            else:
                visit(ch, enclosing)

    visit(tree, [])
    return {"recs": recs} if recs else None


ANATOMY_AST_CAP = 800    # nodes per record; truncation announced in-tree

_AST_OPS = {
    "Add": "+", "Sub": "-", "Mult": "*", "Div": "/", "FloorDiv": "//",
    "Mod": "%", "Pow": "**", "LShift": "<<", "RShift": ">>",
    "BitOr": "|", "BitXor": "^", "BitAnd": "&", "MatMult": "@",
    "And": "and", "Or": "or", "Not": "not", "Invert": "~",
    "UAdd": "+", "USub": "-", "Eq": "==", "NotEq": "!=", "Lt": "<",
    "LtE": "<=", "Gt": ">", "GtE": ">=", "Is": "is", "IsNot": "is not",
    "In": "in", "NotIn": "not in",
}


def _ast_label(node):
    """One human line per AST node: the type plus its salient detail."""
    t = type(node).__name__
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                         ast.ClassDef)):
        return t + " " + node.name
    if isinstance(node, ast.Name):
        return t + " " + node.id
    if isinstance(node, ast.Attribute):
        return t + " ." + node.attr
    if isinstance(node, ast.Constant):
        r = repr(node.value)
        return t + " " + (r[:24] + "…" if len(r) > 24 else r)
    if isinstance(node, (ast.BinOp, ast.UnaryOp)):
        return t + " " + _AST_OPS.get(type(node.op).__name__, "")
    if isinstance(node, ast.BoolOp):
        return t + " " + _AST_OPS.get(type(node.op).__name__, "")
    if isinstance(node, ast.Compare):
        return t + " " + " ".join(_AST_OPS.get(type(o).__name__, "?")
                                  for o in node.ops)
    if isinstance(node, ast.AugAssign):
        return t + " " + _AST_OPS.get(type(node.op).__name__, "") + "="
    if isinstance(node, ast.arg):
        return t + " " + node.arg
    if isinstance(node, ast.keyword):
        return t + " " + (node.arg or "**")
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return t + " " + ", ".join(a.name for a in node.names)
    if isinstance(node, ast.ExceptHandler) and node.name:
        return t + " as " + node.name
    return t


def build_anatomy(text, rel):
    """#85 Tier 0+1 (static): per-function AST tree + bytecode listing.
    Records = <module> plus every def/async def, keyed by line span; the
    renderer picks the INNERMOST record containing the current line.
    Bytecode comes from compiling the source fresh — the instructions as
    CPython compiles them, NOT the adaptive/specialized forms the run
    may have quickened into (that would need the live code objects;
    stated in the panel). Nothing here executes the code."""
    try:
        tree = ast.parse(text, filename=rel)
        code = compile(tree, rel, "exec")
    except SyntaxError:
        return None

    # -- AST side: one nested tree per record, capped with an announced
    #    marker node (label, l0, c0, l1, children) — cols are 0-based.
    def encode(node, budget):
        lab = _ast_label(node)
        ln = getattr(node, "lineno", None)
        l1 = getattr(node, "end_lineno", None)
        col = getattr(node, "col_offset", None)
        kids = []
        for ch in ast.iter_child_nodes(node):
            if type(ch).__name__ in ("Load", "Store", "Del",
                                     "expr_context") \
                    or isinstance(ch, (ast.operator, ast.boolop,
                                       ast.unaryop, ast.cmpop)):
                continue      # operator detail already lives in the label
            if budget[0] <= 0:
                kids.append(["… (AST truncated at %d nodes)"
                             % ANATOMY_AST_CAP, None, None, None, []])
                break
            budget[0] -= 1
            kids.append(encode(ch, budget))
        return [lab, ln, col, l1, kids]

    # -- bytecode side: every code object reachable from the module,
    #    keyed by (name, firstlineno) for the join below.
    def walk_codes(co, out):
        out[(co.co_name, co.co_firstlineno)] = co
        for c in co.co_consts:
            if hasattr(c, "co_code"):
                walk_codes(c, out)
        return out
    codes = walk_codes(code, {})

    def listing(co):
        rows = []
        for ins in dis.get_instructions(co):
            pos = getattr(ins, "positions", None)
            line = (pos.lineno if pos and pos.lineno else None)
            rows.append([ins.offset, ins.opname, str(ins.argrepr or ""),
                         line, 1 if ins.is_jump_target else 0])
        return rows

    recs = []

    def add_rec(name, qual, l0, l1, ast_node, co_key):
        budget = [ANATOMY_AST_CAP]
        co = codes.get(co_key)
        recs.append({
            "q": qual, "l0": l0, "l1": l1,
            "ast": encode(ast_node, budget),
            "dis": listing(co) if co is not None else None,
        })

    def visit(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = prefix + ch.name
                add_rec(ch.name, qual, ch.lineno,
                        ch.end_lineno or ch.lineno, ch,
                        (ch.name, ch.lineno))
                visit(ch, qual + ".<locals>.")
            elif isinstance(ch, ast.ClassDef):
                visit(ch, prefix + ch.name + ".")
            else:
                visit(ch, prefix)

    nlines = text.count("\n") + 1
    add_rec("<module>", "<module>", 1, nlines, tree, (code.co_name, 1))
    visit(tree, "")
    return {"recs": recs,
            "py": "%d.%d.%d" % sys.version_info[:3]}


def build_cfg(text, rel):
    """#131 static half: per-record control-flow graph — the code as
    the graph it is. One node per statement, coalesced into basic
    blocks; typed edges (seq/true/false/loop/break/continue/exc/case/
    nomatch/return/raise); ENTRY = the record's header, EXIT = a
    pseudo-block. Records mirror build_anatomy's: <module> plus every
    def. Honest simplifications, stated in the panel: exception edges
    are drawn from the try HEADER (any line in the region may raise),
    and a finally's interception of returns is not drawn."""
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return None
    Try = (ast.Try, getattr(ast, "TryStar", ast.Try))
    recs = []

    def make_record(qual, header_line, l0, l1, body):
        nodes = []                      # node id -> line (None = EXIT)
        edges = []                      # (src, dst, kind) node-level

        def new_node(line):
            nodes.append(line)
            return len(nodes) - 1

        entry = new_node(header_line)
        ret_exits = []                  # (node, "return"/"raise")

        def build(stmts, loops, prev):
            # prev = dangling (node, kind) exits awaiting their target;
            # returns the dangling exits of this statement list
            for st in stmts:
                n = new_node(st.lineno)
                for m, k in prev:
                    edges.append((m, n, k))
                if isinstance(st, ast.If):
                    p_body = build(st.body, loops, [(n, "true")])
                    if st.orelse:
                        p_else = build(st.orelse, loops, [(n, "false")])
                        prev = p_body + p_else
                    else:
                        prev = p_body + [(n, "false")]
                elif isinstance(st, (ast.While, ast.For, ast.AsyncFor)):
                    lp = {"header": n, "breaks": []}
                    body_exits = build(st.body, loops + [lp],
                                       [(n, "true")])
                    for m, _ in body_exits:      # fallthrough loops back
                        edges.append((m, n, "loop"))
                    brk = [(b, "break") for b in lp["breaks"]]
                    if st.orelse:
                        prev = build(st.orelse, loops,
                                     [(n, "false")]) + brk
                    else:
                        prev = [(n, "false")] + brk
                elif isinstance(st, Try):
                    body_exits = build(st.body, loops, [(n, "seq")])
                    handler_exits = []
                    for h in st.handlers:
                        hn = new_node(h.lineno)
                        edges.append((n, hn, "exc"))
                        handler_exits += build(h.body, loops,
                                               [(hn, "seq")])
                    if st.orelse:
                        body_exits = build(st.orelse, loops, body_exits)
                    prev = body_exits + handler_exits
                    if st.finalbody:
                        prev = build(st.finalbody, loops, prev)
                elif isinstance(st, (ast.With, ast.AsyncWith)):
                    prev = build(st.body, loops, [(n, "seq")])
                elif hasattr(ast, "Match") and isinstance(st, ast.Match):
                    case_exits = []
                    for c in st.cases:
                        cn = new_node(c.pattern.lineno)
                        edges.append((n, cn, "case"))
                        case_exits += build(c.body, loops, [(cn, "seq")])
                    prev = case_exits + [(n, "nomatch")]
                elif isinstance(st, ast.Return):
                    ret_exits.append((n, "return"))
                    prev = []
                elif isinstance(st, ast.Raise):
                    ret_exits.append((n, "raise"))
                    prev = []
                elif isinstance(st, ast.Break):
                    if loops:
                        loops[-1]["breaks"].append(n)
                    prev = []
                elif isinstance(st, ast.Continue):
                    if loops:
                        edges.append((n, loops[-1]["header"],
                                      "continue"))
                    prev = []
                else:
                    # simple statements — and def/class, whose bodies
                    # are their own records
                    prev = [(n, "seq")]
            return prev

        exits = build(body, [], [(entry, "seq")])
        xid = new_node(None)
        for m, k in exits:
            edges.append((m, xid, "return" if k == "seq" else k))
        for m, k in ret_exits:
            edges.append((m, xid, k))

        # ---- coalesce straight seq chains into basic blocks
        succ = collections.defaultdict(list)
        pred = collections.defaultdict(list)
        for s, d, k in edges:
            succ[s].append((d, k))
            pred[d].append((s, k))

        def mergeable(m):
            return (m not in (entry, xid) and len(pred[m]) == 1
                    and pred[m][0][1] == "seq"
                    and len(succ[pred[m][0][0]]) == 1)

        blk_of, blocks = {}, []
        for L in range(len(nodes)):
            if mergeable(L):
                continue
            chain, cur = [L], L
            while (len(succ[cur]) == 1 and succ[cur][0][1] == "seq"
                   and mergeable(succ[cur][0][0])):
                cur = succ[cur][0][0]
                chain.append(cur)
            bid = len(blocks)
            for m in chain:
                blk_of[m] = bid
            blocks.append(chain)
        bedges = sorted({(blk_of[s], blk_of[d], k) for s, d, k in edges
                         if blk_of[s] != blk_of[d] or k != "seq"})
        seen = {blk_of[entry]}
        queue = [blk_of[entry]]
        while queue:
            b = queue.pop()
            for s, d, _ in bedges:
                if s == b and d not in seen:
                    seen.add(d)
                    queue.append(d)
        recs.append({
            "q": qual, "l0": l0, "l1": l1,
            "blocks": [[nodes[m] for m in chain
                        if nodes[m] is not None] for chain in blocks],
            "edges": [list(e) for e in bedges],
            "entry": blk_of[entry], "exit": blk_of[xid],
            "unreach": sorted(b for b in range(len(blocks))
                              if b not in seen),
        })

    def visit(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = prefix + ch.name
                make_record(qual, ch.lineno, ch.lineno,
                            ch.end_lineno or ch.lineno, ch.body)
                visit(ch, qual + ".<locals>.")
            elif isinstance(ch, ast.ClassDef):
                visit(ch, prefix + ch.name + ".")
            else:
                visit(ch, prefix)

    nlines = text.count("\n") + 1
    make_record("<module>", 1, 1, nlines, tree.body)
    visit(tree, "")
    return {"recs": recs}


def _cfg_weights(events, cfg):
    """#131 dynamic half: observed block→block traversal counts ("w")
    and block entry counts ("h") folded into each CFG record — the
    run as a path on the code's graph. Frames are walked with the
    annotate_conditionals stack pattern (generator suspend/resume
    included) so every transition is attributed to the frame that
    made it, never to an interleaved caller."""
    l2b, by_l0, mod_rec, spans = {}, {}, {}, {}
    for rel, c in (cfg or {}).items():
        if not c:
            continue
        maps = []
        for ri, r in enumerate(c["recs"]):
            m = {}
            for bi, lines in enumerate(r["blocks"]):
                for ln in lines:
                    m.setdefault(ln, bi)
            maps.append(m)
            if r["q"] == "<module>":
                mod_rec[rel] = ri
            else:
                by_l0.setdefault(rel, {})[
                    (r["q"].rsplit(".", 1)[-1], r["l0"])] = ri
        l2b[rel] = maps
        spans[rel] = sorted(
            ((r["l0"], r["l1"], ri) for ri, r in enumerate(c["recs"])
             if r["q"] != "<module>"), key=lambda s: s[1] - s[0])
    W, H = {}, {}
    stacks, gen_saved = {}, {}
    for ev in events:
        e = ev.get("e")
        stack = stacks.setdefault(ev.get("t", "main"), [])
        if e == "call":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "r" \
                    and gm.get("i") in gen_saved:
                stack.append(gen_saved.pop(gm["i"]))
                continue
            rel, fn, ln = ev.get("f"), ev.get("fn"), ev.get("l")
            ridx = None
            if rel in l2b:
                if fn == "<module>":
                    ridx = mod_rec.get(rel)
                else:
                    ridx = by_l0.get(rel, {}).get((fn, ln))
                    if ridx is None:      # decorated: call line ≠ l0
                        for l0, l1, ri in spans.get(rel, ()):
                            if l0 <= ln <= l1 and cfg[rel]["recs"][ri][
                                    "q"].rsplit(".", 1)[-1] == fn:
                                ridx = ri
                                break
            stack.append({"rec": (rel, ridx), "prev": None})
            continue
        if not stack:
            continue
        fr = stack[-1]
        rel, ridx = fr.get("rec", (None, None))
        if e == "return":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "y":
                gen_saved[gm["i"]] = fr      # suspended, not dead
            elif ridx is not None and fr["prev"] is not None:
                rec = cfg[rel]["recs"][ridx]
                key = (rel, ridx)
                pair = (fr["prev"], rec["exit"])
                W.setdefault(key, {})[pair] = \
                    W.get(key, {}).get(pair, 0) + 1
                H.setdefault(key, {})[rec["exit"]] = \
                    H.get(key, {}).get(rec["exit"], 0) + 1
            stack.pop()
            continue
        if e == "line" and ridx is not None:
            b = l2b[rel][ridx].get(ev["l"])
            if b is not None:
                key = (rel, ridx)
                pb = fr["prev"]
                if pb != b:
                    H.setdefault(key, {})[b] = \
                        H.get(key, {}).get(b, 0) + 1
                    if pb is not None:
                        W.setdefault(key, {})[(pb, b)] = \
                            W.get(key, {}).get((pb, b), 0) + 1
                fr["prev"] = b
    for (rel, ridx), wmap in W.items():
        cfg[rel]["recs"][ridx]["w"] = {
            "%d-%d" % p: n for p, n in sorted(wmap.items())}
    for (rel, ridx), hmap in H.items():
        cfg[rel]["recs"][ridx]["h"] = {
            str(b): n for b, n in sorted(hmap.items())}


def annotate_conditionals(events, sources):
    """Post-processing: walk the event stream with per-thread frame
    stacks; each event on an if/while line becomes 'pending' and is
    resolved by the NEXT event in the same frame — the taken branch
    reveals the condition's result. Generic: works for any code, and is
    always correct because it observes what actually happened."""
    maps = {rel: build_branch_map(text, rel)
            for rel, text in sources.items()}
    stacks = {}
    gen_saved = {}   # generator instance -> saved frame state (suspended)
    for ev in events:
        stack = stacks.setdefault(ev.get("t", "main"), [])
        if ev["e"] == "call":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "r" \
                    and gm.get("i") in gen_saved:
                # a RESUME re-enters the sleeping frame: restore its
                # state so loop counters survive the suspension
                stack.append(gen_saved.pop(gm["i"]))
            else:
                stack.append({"pending": None, "prev": None, "fc": {}})
            continue
        if not stack:
            continue
        frame = stack[-1]
        pend = frame["pending"]
        if pend is not None:
            ev0, info, fresh = pend
            res = _branch_result(info, ev["l"])
            if res is not None:
                cond = {"x": info["x"], "r": res}
                kind = info.get("k", "if")
                if kind != "if":
                    cond["k"] = kind
                if kind == "for":
                    # iteration counter, reset on exhaustion or fresh entry
                    line = info["lineno"]
                    if res:
                        cnt = 1 if fresh else frame["fc"].get(line, 0) + 1
                        frame["fc"][line] = cnt
                        cond["i"] = cnt
                    else:
                        cond["i"] = 0 if fresh else frame["fc"].get(line, 0)
                        frame["fc"][line] = 0
                ev0["cond"] = cond
                frame["pending"] = None
        if ev["e"] == "line":
            info = maps.get(ev["f"], {}).get(ev["l"])
            if info is not None:
                fresh = True
                if info.get("k") == "for" and frame["prev"] is not None:
                    # looping back if the previous event in this frame
                    # was inside the loop's own extent
                    fresh = not (info["lineno"] <= frame["prev"]
                                 <= info.get("end", info["lineno"]))
                frame["pending"] = (ev, info, fresh)
        elif ev["e"] == "return":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "y":
                gen_saved[gm["i"]] = frame   # suspended, not dead
            stack.pop()
            continue
        frame["prev"] = ev["l"]


def _critical_path(events):
    """#89: the chain that determined total wall time. Every µs of the
    run is attributed to the INNERMOST slice open anywhere in the
    process at that instant — under the GIL one thread computes at a
    time, so this spine IS the computation's critical chain, crossing
    lanes exactly where awaits, wakes and joins handed control over.
    Instants where NOTHING traced was open are UNTRACKED EXTERNAL
    WAITS (sleep, network, OS, untraced library code) — counted,
    never hidden. Needs >= 2 lanes: a sequential run's critical path
    is the whole run, a claim with no content. True multi-core DAG
    analysis (parallel threads genuinely overlapping) is the stated
    remainder."""
    open_list = []   # [call_idx, lane, still_open] in call order
    by_lane = {}     # lane -> stack of indexes into open_list
    segs = []        # [t0, t1, call_idx] — the spine, merged
    lanes_seen = set()
    abs_t = 0
    gaps = 0
    for i, e in enumerate(events):
        dt = e.get("ts", 0)
        if dt:
            top = None
            for k in range(len(open_list) - 1, -1, -1):
                if open_list[k][2]:
                    top = open_list[k]
                    break
            if top is None:
                gaps += dt
            elif segs and segs[-1][2] == top[0] \
                    and segs[-1][1] == abs_t:
                segs[-1][1] = abs_t + dt
            else:
                segs.append([abs_t, abs_t + dt, top[0]])
            abs_t += dt
        k = e.get("e")
        lane = (e.get("t", "main"), e.get("tk"))
        if k == "call":
            by_lane.setdefault(lane, []).append(len(open_list))
            open_list.append([i, lane, True])
            lanes_seen.add(lane)
        elif k == "return":
            st = by_lane.get(lane)
            if st:
                open_list[st.pop()][2] = False
    if not segs or len(lanes_seen) < 2:
        return None
    evs, seen = [], set()
    for _t0, _t1, ci in segs:
        if ci not in seen:
            seen.add(ci)
            evs.append(ci)
    return {"evs": evs,
            "segs": segs,
            "n": len(evs),
            "lanes": len({(events[ci].get("t", "main"),
                           events[ci].get("tk")) for ci in evs}),
            "spanUs": abs_t,
            "gapUs": gaps}


def export_perfetto(events, script, path):
    """#15: Chrome Trace Event Format for Perfetto (ui.perfetto.dev) or
    chrome://tracing — B/E slice pairs from call/return events, absolute
    µs timestamps rebuilt from the delta-encoded ts, one timeline row
    (tid) per thread·task lane. fn granularity only: line traces carry
    no timestamps (the #6 honesty rule — wall times under line tracing
    would be fiction). A coroutine's slice CLOSES at the yield and a new
    one opens on resume, so time spent suspended shows as a real gap in
    the row. Exceptions become instant markers ("i"), one per unwound
    frame. Returns (slices, lanes, stray, unclosed) for the report."""
    tevs = [{"ph": "M", "name": "process_name", "pid": 1, "tid": 0,
             "args": {"name": "pyreplay: " + script}}]
    lanes = {}     # lane label -> tid
    open_b = {}    # tid -> (name, call idx, start ts) of open B slices
    stray = 0      # returns whose call predates the trace: skipped
    hb_flows = []  # #88: wake edges, bound to slices in a second pass
    crit = _critical_path(events)          # #89: gold in the export
    critset = set(crit["evs"]) if crit else set()
    acc = 0

    def brief(enc):
        """One-line display string from a structured encoding."""
        if not isinstance(enc, dict):
            return "?"
        if enc.get("t") in ("p", "s", "o"):
            return str(enc.get("v", ""))
        return f"<{enc.get('c') or enc.get('t')} · {enc.get('n', '?')} items>"

    for i, ev in enumerate(events):
        acc += ev.get("ts", 0)
        lane = ev.get("t", "main")
        if ev.get("tk"):
            lane += " · task " + ev["tk"]
        tid = lanes.get(lane)
        if tid is None:
            tid = lanes[lane] = len(lanes) + 1
            tevs.append({"ph": "M", "name": "thread_name", "pid": 1,
                         "tid": tid, "args": {"name": lane}})
        kind = ev["e"]
        if kind == "call":
            e = {"ph": "B", "name": ev["fn"], "cat": ev["f"], "ts": acc,
                 "pid": 1, "tid": tid,
                 "args": {k: brief(v) for k, v in ev.get("ch", {}).items()}}
            if (ev.get("g") or {}).get("s") == "r":
                e["args"]["(resumed)"] = "suspended frame woke up here"
            if i in critset:
                e["args"]["(critical)"] = "★ on the critical path"
            tevs.append(e)
            open_b.setdefault(tid, []).append((ev["fn"], i, acc))
        elif kind == "return":
            st = open_b.get(tid)
            if not st:
                stray += 1
                continue
            bname, bci, b0 = st.pop()
            e = {"ph": "E", "name": bname, "ts": acc, "pid": 1,
                 "tid": tid}
            if (ev.get("g") or {}).get("s") == "y":
                e["args"] = {"(suspended)": "yield/await — resumes later",
                             "yields": brief(ev.get("ret"))}
            elif "ret" in ev:
                e["args"] = {"returns": brief(ev["ret"])}
            tevs.append(e)
        elif kind == "exc":
            x = ev.get("x") or {}
            tevs.append({"ph": "i", "s": "t", "name": x.get("t", "exception"),
                         "cat": "exception", "ts": acc, "pid": 1, "tid": tid,
                         "args": {"msg": x.get("m", ""),
                                  "soft": bool(x.get("soft")),
                                  "where": f"{ev['f']}:{ev['l']}"}})
        elif kind == "log":
            # #118: console lines land on the timeline as instants —
            # in Perfetto too, the output meets its moment
            tevs.append({"ph": "i", "s": "t",
                         "name": ("stderr: " if ev.get("s") == "err"
                                  else "stdout: ") + ev.get("txt", ""),
                         "cat": "console", "ts": acc, "pid": 1,
                         "tid": tid})
        elif kind == "chap":
            # #98: test boundaries as instants (a B/E span would fight
            # the call slices for nesting on the same row)
            mark = ("TEST ▶ " if ev.get("k") == "s"
                    else f"TEST {ev.get('o', 'end')} — ")
            tevs.append({"ph": "i", "s": "t", "name": mark + ev.get("id", ""),
                         "cat": "test", "ts": acc, "pid": 1, "tid": tid})
        elif kind == "hb":
            # #88: the wake is an instant; the causality is a FLOW —
            # Perfetto draws the arrow between the two lanes
            hbk = ev.get("hb")
            label = {"tstart": "started thread", "tjoin": "joined thread",
                     "create": "created task"}.get(hbk, hbk)
            tevs.append({"ph": "i", "s": "t",
                         "name": "⤳ " + label + " " + ev.get("dst", "?"),
                         "cat": "wake", "ts": acc, "pid": 1, "tid": tid})
            if hbk == "create":
                dst_lane = (ev.get("t", "main") + " · task "
                            + ev.get("dst", "?"))
            else:
                dst_lane = ev.get("dst", "?")
            hb_flows.append({"kind": hbk, "ts": acc, "tid": tid,
                             "dst_lane": dst_lane})
        elif kind == "line":
            # a line event means a line-granularity stream: it carries
            # no time, and exporting it would be fiction — refuse here
            # too, not only at the CLI
            raise ValueError(f"export_perfetto needs an fn-granularity "
                             f"event stream, got a {kind!r} event")
    unclosed = 0
    for tid, st in open_b.items():
        while st:   # frames still live when the trace ended: close at
            unclosed += 1   # the final timestamp, and say so
            bname, bci, b0 = st.pop()
            tevs.append({"ph": "E", "name": bname, "ts": acc, "pid": 1,
                         "tid": tid,
                         "args": {"(unclosed)": "frame still live when "
                                                "the trace ended"}})
    # #88 second pass: bind each wake edge to real slices. A create/
    # tstart arrow runs from the wake instant to the woken lane's FIRST
    # slice after it; a tjoin arrow runs from the joined lane's LAST
    # slice end to the join instant. A lane that never sliced gets the
    # instant only — no invented arrow.
    fid = 0
    for fl in hb_flows:
        dst_tid = lanes.get(fl["dst_lane"])
        if dst_tid is None:
            continue
        if fl["kind"] == "tjoin":
            src = None
            for e in tevs:
                if e.get("tid") == dst_tid and e["ph"] == "E" \
                        and e["ts"] <= fl["ts"]:
                    src = e
            if src is None:
                continue
            fid += 1
            tevs.append({"ph": "s", "id": fid, "name": "wake",
                         "cat": "wake", "ts": src["ts"], "pid": 1,
                         "tid": dst_tid})
            tevs.append({"ph": "f", "id": fid, "name": "wake",
                         "cat": "wake", "bp": "e", "ts": fl["ts"],
                         "pid": 1, "tid": fl["tid"]})
        else:
            dst = None
            for e in tevs:
                if e.get("tid") == dst_tid and e["ph"] == "B" \
                        and e["ts"] >= fl["ts"]:
                    dst = e
                    break
            if dst is None:
                continue
            fid += 1
            tevs.append({"ph": "s", "id": fid, "name": "wake",
                         "cat": "wake", "ts": fl["ts"], "pid": 1,
                         "tid": fl["tid"]})
            tevs.append({"ph": "f", "id": fid, "name": "wake",
                         "cat": "wake", "bp": "e", "ts": dst["ts"],
                         "pid": 1, "tid": dst_tid})
    if crit:
        # #89: the critical path as its OWN row — the run's spine read
        # left to right, segment-exact; gaps in the row are the
        # untracked external waits. Critical slices also wear ★ in args.
        KTID = 9999
        tevs.append({"ph": "M", "name": "thread_name", "pid": 1,
                     "tid": KTID, "args": {"name": "★ critical path"}})
        for t0, t1, ci in crit["segs"]:
            nm = events[ci].get("fn", "?")
            tevs.append({"ph": "B", "name": nm, "cat": "critical",
                         "ts": t0, "pid": 1, "tid": KTID})
            tevs.append({"ph": "E", "name": nm, "cat": "critical",
                         "ts": t1, "pid": 1, "tid": KTID})
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"traceEvents": tevs,
                   "otherData": {"tool": "pyreplay", "script": script}}, f)
    return (sum(1 for e in tevs if e["ph"] == "B"), len(lanes),
            stray, unclosed)


def _venv_hint():
    """One-line hint when running on the system python while a project
    .venv sits right here — the single most common cause of 'module not
    found' crashes under the tracer."""
    if sys.prefix != sys.base_prefix:
        return ""   # already inside a venv
    for d in (os.getcwd(), os.path.dirname(SELF)):
        if os.path.exists(os.path.join(d, ".venv", "bin", "python")):
            return (" — note: you're on the SYSTEM python and a .venv "
                    "exists here; if your packages live there, run "
                    "`source .venv/bin/activate` first")
    return ""


def _top_imports(tree):
    """Top-level module names imported by an ast tree (absolute only —
    relative imports resolve inside the codebase by construction)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module \
                and not node.level:
            names.add(node.module.split(".")[0])
    return names


def _probe_missing(names, root):
    """Which of these module names can't THIS python find, probed with
    root+cwd on the path the way a traced run resolves them? Local
    packages under root therefore count as present; stdlib is skipped."""
    import importlib.util
    stdlib = getattr(sys, "stdlib_module_names", ())
    missing = []
    saved, sys.path = sys.path, [root, os.path.realpath(os.getcwd())] \
        + sys.path
    try:
        for n in sorted(names):
            if n in stdlib:
                continue
            try:
                if importlib.util.find_spec(n) is None:
                    missing.append(n)
            except BaseException:
                missing.append(n)
    finally:
        sys.path = saved
    return missing


def _missing_imports(script, root):
    """Preflight a script entry: which top-level imports of the ENTRY file
    can't be found by THIS python (probed with root+cwd on the path, the
    way the run will resolve them)? Advisory — an import wrapped in
    try/except may be fine — but it turns the classic 'trace crashed at
    import numpy with 0 events' surprise into a warning BEFORE the run."""
    try:
        with open(script, encoding="utf-8", errors="replace") as fh:
            tree = ast.parse(fh.read(), filename=script)
    except (OSError, SyntaxError):
        return []
    return _probe_missing(_top_imports(tree), root)


def _scan_codebase_imports(root, cap=3000):
    """Every top-level import across the root's .py files (dot-dirs,
    __pycache__ and node_modules skipped) — the full shopping list a run
    inside this codebase MAY need. Returns (names, files_scanned)."""
    names, scanned = set(), 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".")
                       and d not in ("__pycache__", "node_modules")]
        for f in filenames:
            if not f.endswith(".py"):
                continue
            if scanned >= cap:
                return names, scanned
            scanned += 1
            try:
                with open(os.path.join(dirpath, f), encoding="utf-8",
                          errors="replace") as fh:
                    names |= _top_imports(ast.parse(fh.read()))
            except (OSError, SyntaxError):
                continue
    return names, scanned


def _pytest_config_notes(root):
    """pytest config landmines in the root: addopts lines (verbatim) and
    the xdist trap — forced worker subprocesses are invisible to the
    tracer, so any -n / --dist in the config needs -n0 on the command."""
    notes = []
    for fname in ("pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini"):
        try:
            with open(os.path.join(root, fname), encoding="utf-8",
                      errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if "addopts" in line:
                block = line.strip()
                # TOML multi-line strings: addopts = """ ...lines... """
                for q in ('"""', "'''"):
                    if line.count(q) == 1:
                        j = i + 1
                        while j < len(lines) and q not in lines[j]:
                            block += " " + lines[j].strip()
                            j += 1
                        if j < len(lines):
                            block += " " + lines[j].strip()
                        i = j
                        break
                notes.append(f"pytest config — {fname} sets: "
                             + block[:160])
                if " -n" in block or "--dist" in block or "xdist" in block:
                    notes.append("⚠ that forces pytest-xdist WORKER "
                                 "subprocesses, which the tracer cannot "
                                 "see — append -n0 to your command")
            i += 1
    return notes


def _doctor(module, script, root, entry_label, module_ok):
    """--doctor: diagnose the environment for this exact invocation and
    print the setup recipe INSTEAD of running anything. Hard blockers
    (the entry itself can't work) exit 3; codebase-wide missing deps
    are advisory — a run only needs the ones it actually imports. The
    proactive half of the trace doctor; the reactive hints fire on
    real runs."""
    print(f"pyreplay doctor — {entry_label}   (scope root: {root})")
    in_venv = sys.prefix != sys.base_prefix
    print(f"  python: {sys.executable} "
          + ("(venv)" if in_venv else "(SYSTEM interpreter)"))
    if _venv_hint():
        print("  ⚠ a .venv exists here but is NOT active — your packages "
              "probably live there:")
        print("      source .venv/bin/activate")
    blockers = 0
    if module is not None and not module_ok:
        blockers += 1
        print(f"  ⚠ BLOCKER: the entry module is not importable: {module}")
        print(f"      pip install {module.split('.')[0]}")
    if script is not None:
        miss = _missing_imports(script, root)
        if miss:
            blockers += 1
            print("  ⚠ BLOCKER: the entry script imports missing "
                  "module(s): " + ", ".join(miss))
            print("      pip install " + " ".join(miss))
    names, scanned = _scan_codebase_imports(root)
    missing = _probe_missing(names, root)
    if missing:
        print(f"  codebase deps ({scanned} files scanned): {len(missing)} "
              "not importable here — " + ", ".join(missing[:12])
              + (" …" if len(missing) > 12 else ""))
        if any(os.path.exists(os.path.join(root, f))
               for f in ("pyproject.toml", "setup.py", "setup.cfg")):
            print("    → the root is a pip package; one-shot setup "
                  "(installs it plus its declared deps):")
            print(f"      pip install -e '{root}'")
        else:
            print("      pip install " + " ".join(missing))
        print("    (advisory: only the ones your run actually imports "
              "matter)")
    else:
        print(f"  codebase deps ({scanned} files scanned): "
              "all importable ✓")
    if module == "pytest":
        for note in _pytest_config_notes(root):
            print("  " + note)
    if blockers:
        print(f"  verdict: {blockers} blocker(s) — fix the lines above, "
              "then re-run without --doctor to trace")
        return 3
    print("  verdict: ready — drop --doctor and trace")
    return 0


def _write_trace(tr, out, granularity, entry_label, error,
                 trigger_desc=None, extra=None, chunked=None,
                 fsm=None, memo=None, starve_ms=None,
                 reduce_name=None):
    """Build the payload and write the self-contained replayer HTML —
    shared by the CLI run and the in-process watch() bracket, so both
    honor the same contract (line-only linevars/dataflow, the </ escape,
    honest truncation notes)."""
    fsm_data = None
    if fsm is not None and granularity == "line":
        # #132 runs FIRST: it may splice derived viol events into the
        # stream, and every later pass must see the final indices
        fsm_data = _build_fsm(tr.events, fsm[0], fsm[1])
    if granularity == "line":
        annotate_conditionals(tr.events, tr.sources)
    cfg = {}
    if granularity == "line":
        cfg = {rel: build_cfg(text, rel)
               for rel, text in tr.sources.items()}
        _cfg_weights(tr.events, cfg)
    payload = {
        "script": entry_label,
        "granularity": granularity,
        "sources": tr.sources,
        "linevars": {rel: build_line_vars(text, rel)
                     for rel, text in tr.sources.items()}
                    if granularity == "line" else {},
        "lineattrs": {rel: build_line_attrs(text, rel)
                      for rel, text in tr.sources.items()}
                     if granularity == "line" else {},
        "dataflow": {rel: build_dataflow(text, rel)
                     for rel, text in tr.sources.items()}
                    if granularity == "line" else {},
        "guards": {rel: build_guards(text, rel)
                   for rel, text in tr.sources.items()}
                  if granularity == "line" else {},
        "anatomy": {rel: build_anatomy(text, rel)
                    for rel, text in tr.sources.items()}
                   if granularity == "line" else {},
        # #122: per-def name-masking audit (static; badge at replay)
        "shadows": {rel: build_shadows(text, rel)
                    for rel, text in tr.sources.items()}
                   if granularity == "line" else {},
        "cfg": cfg,
        "events": tr.events,
        "truncated": tr.truncated,
        "error": error,
        "startAt": trigger_desc,
        "trip": getattr(tr, "trip", None),
        # #74: this run's own mined invariants — support = this run's
        # observations only; --runs --mine multiplies the evidence
        "mined": mine_invariants([{"events": tr.events}]),
        "fsm": fsm_data,   # #132, or null without --fsm
        # #78: state-recurrence findings (line granularity only)
        "nonterm": (_detect_nonterm(tr.events, tr.sources)
                    if granularity == "line" else []),
        # #134: the subproblem DAG of the bound memo, or null
        "memo": (_build_memo(tr.events, tr.sources, memo)
                 if memo is not None and granularity == "line"
                 else None),
        # #82: observed type histogram per name — instability visible
        "typeflow": _typeflow(tr.events),
        # #123a: float == / != where it executed + static literal sites
        "floatEq": (_float_probe(tr.events, tr.sources)
                    if granularity == "line" else None),
        # #123b: the bound reduction's ordering wobble, or null
        "reduce": (_reduction_probe(tr.events, reduce_name)
                   if reduce_name is not None
                   and granularity == "line" else None),
        # #124: loop starvation (fn only — line events carry no wall
        # timestamps, so the detector would have nothing true to say)
        "starve": (_detect_starvation(tr.events,
                                      (starve_ms or 100) * 1000)
                   if granularity == "fn" else None),
    }
    if granularity != "fn" and starve_ms is not None:
        print("--starve-ms: refused at line granularity — line events "
              "carry no wall timestamps; re-run with --granularity fn")
    if reduce_name is not None and granularity != "line":
        print("--probe-reduction: refused at fn granularity — the "
              "probe reads recorded VALUES; re-run at line "
              "granularity")
    tf = payload.get("typeflow") or {}
    unstable = [(k, v) for k, v in tf.items()
                if k != "__capped__" and len(v["ty"]) >= 2]
    if unstable:
        unstable.sort(key=lambda kv: (-len(kv[1]["ty"]),
                                      -kv[1]["n"]))
        print(f"⚠τ type instability: {len(unstable)} name(s) held "
              f"more than one type — this is what the code DID:")
        for k, v in unstable[:5]:
            f2, fn2, nm2 = k.split("|", 2)
            parts = " · ".join(
                f"{t} {c[0]}×" for t, c in
                sorted(v["ty"].items(), key=lambda x: -x[1][0]))
            print(f"    {fn2}(): {nm2} — {parts}  ({f2})")
        if len(unstable) > 5:
            print(f"    … {len(unstable) - 5} more (⚠τ on their "
                  f"rows in the replayer)")
    fe = payload.get("floatEq")
    if fe and fe["dyn"]:
        i0, names0 = fe["dyn"][0]
        print(f"≈ float equality executed {len(fe['dyn'])}"
              f"{'+' if fe['capped'] else ''}× — first at event "
              f"{i0 + 1} ({tr.events[i0].get('f')}:"
              f"{tr.events[i0].get('l')}, {', '.join(names0)} held "
              f"float) — the classic silent trap; == on floats "
              f"compares bit patterns, not mathematics")
    rd = payload.get("reduce")
    if rd is not None:
        if rd.get("refused"):
            print(f"≈ reduction probe [{rd['name']}]: refused — "
                  f"{rd['refused']}")
        else:
            print(f"≈ reduction probe [{rd['name']}] "
                  f"({rd['n']} numbers, last full value in "
                  f"{rd['fn']}()):")
            print(f"    as recorded   {rd['asRec']!r}")
            print(f"    sorted asc    {rd['sortAsc']!r} · desc "
                  f"{rd['sortDesc']!r}")
            print(f"    {rd['perms']} permutations  "
                  f"[{rd['permMin']!r}, {rd['permMax']!r}]")
            print(f"    math.fsum     {rd['fsum']!r} · exact "
                  f"rational {rd['exact']!r}")
            if rd["spread"] == 0.0:
                print("    verdict: every ordering agrees to the "
                      "bit — well-conditioned at this data")
            else:
                print(f"    verdict: orderings disagree by "
                      f"{rd['spread']:.3g} — the accumulation is "
                      f"ill-conditioned at this data (evidence of "
                      f"sensitivity, not proof of error)")
    st = payload["starve"]
    if st and st["inc"]:
        w = st["inc"][0]
        print(f"⏳ loop starvation: {len(st['inc'])} incident(s) ≥ "
              f"{st['thresholdMs']:g} ms — worst: task {w['tk']} held "
              f"the loop {w['us']/1000:.0f} ms inside {w['fn']}() "
              f"while {', '.join(w['starved'][:3])} waited")
    if extra:
        payload.update(extra)
    # #130: per-bucket compressibility — gzip bits/event as a
    # regularity measure. A tight loop is low-entropy; data-dependent
    # wandering is high; a marked change marks a phase change in the
    # run. The label is "compressibility", never bare "entropy":
    # compressed length is an UPPER BOUND on the entropy rate.
    n_ev = len(tr.events)
    if n_ev >= 50:
        nbuck = min(120, n_ev)
        per_b = n_ev / nbuck
        buckets = []
        for b in range(nbuck):
            lo = int(b * per_b)
            hi = min(n_ev, int((b + 1) * per_b))
            raw = json.dumps(tr.events[lo:hi],
                             separators=(",", ":")).encode("utf-8")
            comp = gzip.compress(raw, 6)
            buckets.append([hi - lo, len(raw), len(comp)])
        payload["compress"] = {"buckets": buckets, "gzip": 6}
    template_path = os.path.join(os.path.dirname(SELF),
                                 "replayer_template.html")
    with open(template_path, encoding="utf-8") as f:
        template = f.read()
    # #101: past the auto threshold (or on --chunked) the events array
    # moves out of the single JSON string into gzip+base64 chunk tags —
    # the browser never parses one giant string, and the file shrinks.
    n_ev = len(tr.events)
    if chunked is None:
        chunked = n_ev > CHUNK_AUTO
    chunk_html = ""
    if chunked and n_ev:
        b64s = []
        for i in range(0, n_ev, CHUNK_EVENTS):
            raw = json.dumps(tr.events[i:i + CHUNK_EVENTS],
                             separators=(",", ":")).encode("utf-8")
            b64s.append(base64.b64encode(
                gzip.compress(raw, 6)).decode("ascii"))
        payload["events"] = []
        payload["chunked"] = {"chunks": len(b64s), "total": n_ev,
                              "per": CHUNK_EVENTS}
        chunk_html = "\n".join(
            f'<script id="trace-chunk-{k}" '
            f'type="application/gzip-base64">{b64}</script>'
            for k, b64 in enumerate(b64s))
    # "</" would terminate the <script> tag early if a repr contains it
    # (base64 never contains "<", so chunks need no escaping)
    data = json.dumps(payload).replace("</", "<\\/")
    html = template.replace("__TRACE_DATA__", data)
    html = html.replace("<!-- __TRACE_CHUNKS__ -->", chunk_html)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"{len(tr.events)} events from {len(tr.sources)} file(s) -> {out}"
          + (f" ({len(b64s)} gzip chunks)" if chunked and n_ev else ""))
    if error:
        print(f"note: script ended with {error} "
              f"(trace captured up to that point)")
        if error.startswith("ModuleNotFoundError") and "'" in error:
            miss = error.split("'")[1].split(".")[0]
            print(f"hint: that module isn't installed in THIS python — "
                  f"pip install {miss}" + _venv_hint())
    if tr.truncated:
        if tr.abort_on_cap:
            print(f"note: event cap ({tr.max_events}) reached — run "
                  f"aborted there, trace holds everything up to that "
                  f"point (raise it with --max-events)")
        else:
            print(f"note: event cap ({tr.max_events}) reached — recording "
                  f"stopped there; the program ran on untraced "
                  f"(raise it with max_events=)")
    if trigger_desc and not tr.armed:
        print(f"note: trigger ({trigger_desc}) never fired — nothing "
              f"recorded. Check the file name / line / condition.")


_watch_active = False


class watch:
    """In-process microscope (#24): bracket ONE block or function with the
    tracer, inside a program you did NOT launch under the CLI — a notebook
    cell, a server handler, a long-running script.

        from tracer import watch

        with watch():                    # bracket a block
            result = solve(data)

        @watch()                         # or a function — the FIRST call
        def handler(msg): ...            # is recorded (once=True default;
                                         # once=False records every call)

    Writes the same self-contained trace_watch*.html the CLI writes
    (default name never overwrites; an explicit out= does). Line
    granularity by default — the bracket makes the region small by
    construction; granularity="fn" gives the call-level overview. Scope
    root defaults to the calling file's folder (pass root="/path/to/
    project" in notebooks, whose cells live in temp files). If the block
    raises, the trace is written and the exception RE-RAISED, with the
    error recorded in the trace. If max_events fills, recording stops but
    the host program RUNS ON (the CLI aborts instead). One watch at a
    time: a nested watch records nothing and says so. Threads started
    inside the block are traced; threads already running are not."""

    def __init__(self, out=None, granularity="line", root=None,
                 include=None, exclude=None, max_events=MAX_EVENTS,
                 once=True, trip=None, ring=None):
        if callable(out):
            raise TypeError("use @watch() with parentheses, not @watch")
        if granularity not in ("line", "fn"):
            raise ValueError("granularity must be 'line' or 'fn'")
        if trip and granularity == "fn":
            raise ValueError("trip='nan' needs line granularity "
                             "(variable values live in line events)")
        self.out = out
        self.trip = trip
        self.ring = ring
        self.granularity = granularity
        self.root = root
        self.include = include
        self.exclude = exclude
        self.max_events = max_events
        self.once = once
        self._label = None    # decorator pre-sets; __enter__ derives else
        self._tr = None
        self._caller = None
        self._prev = None
        self._fired = False

    def __enter__(self):
        global _watch_active
        if _watch_active:
            print("pyreplay: a watch() is already active — this nested "
                  "watch records nothing", flush=True)
            return self
        caller = sys._getframe(1)
        fname = caller.f_code.co_filename
        real_file = bool(fname) and not fname.startswith("<")
        root = self.root or (os.path.dirname(os.path.realpath(fname))
                             if real_file else os.getcwd())
        if self._label is None:
            self._label = (f"watch @ {os.path.basename(fname)}:"
                           f"{caller.f_lineno}" if real_file
                           else "watch @ <interactive>")
        self._tr = Tracer(root, self.max_events, include=self.include,
                          exclude=self.exclude,
                          granularity=self.granularity, trip=self.trip,
                          ring=self.ring)
        self._tr.abort_on_cap = False   # never kill the host program
        _watch_active = True
        self._caller = caller
        self._prev = sys.gettrace()     # restore any debugger afterwards
        threading.settrace(self._tr)
        sys.settrace(self._tr)
        # the caller's frame predates the hook (settrace only fires on NEW
        # calls) — register it by hand so the block's OWN lines are
        # recorded, not just the calls it makes
        lt = self._tr(caller, "call", None)
        if lt:
            caller.f_trace = lt
        return self

    def __exit__(self, etype, exc, tb):
        global _watch_active
        if self._tr is None:            # nested no-op
            return False
        sys.settrace(self._prev)
        threading.settrace(None)
        try:
            self._caller.f_trace = None
        except Exception:
            pass
        _watch_active = False
        error = f"{etype.__name__}: {exc}" if etype is not None else None
        out = self.out
        if out is None:                 # default: unique, never overwrite
            out = "trace_watch.html"
            n = 2
            while os.path.exists(out):
                out = f"trace_watch_{n}.html"
                n += 1
        out = os.path.abspath(out)
        ring_extra = None
        if self.ring:
            ring_extra = {"size": self.ring,
                          "dropped": self._tr.events.dropped}
            self._tr.events = list(self._tr.events)
        capsule = {   # #104: the in-process bracket's capsule — the
            # HOST command is the reproduction recipe here
            "cmd": " ".join(shlex.quote(a) for a in
                            [os.path.basename(sys.executable)]
                            + sys.argv),
            "argv": sys.argv[:],
            "cwd": os.getcwd(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "hashseed": os.environ.get("PYTHONHASHSEED") or "random",
            "env": {k: os.environ[k] for k in
                    ("VIRTUAL_ENV", "PYTHONPATH")
                    if k in os.environ},
            "when": datetime.datetime.now().isoformat(
                timespec="seconds"),
            "stdin": None, "stdinTrunc": False,
        }
        _write_trace(self._tr, out, self.granularity, self._label, error,
                     extra={"capsule": capsule, "ring": ring_extra})
        self.out = out
        self._tr = None
        return False                    # never swallow the block's raise

    def __call__(self, fn):
        import functools
        src = fn.__code__.co_filename
        droot = self.root or (os.path.dirname(os.path.realpath(src))
                              if src and not src.startswith("<")
                              else os.getcwd())

        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if self.once and self._fired:
                return fn(*a, **kw)     # recorded once; full speed after
            self._fired = True
            w = watch(out=self.out, granularity=self.granularity,
                      root=droot, include=self.include,
                      exclude=self.exclude, max_events=self.max_events)
            w._label = f"watch @ {fn.__name__}()"
            with w:
                return fn(*a, **kw)
        return wrapper


def _extract_payload(html_path):
    """Read the embedded JSON back out of a generated trace — including
    #101 chunked artifacts, whose events live in gzip+base64 chunk tags
    (the same contract checks.py and the mapper rely on)."""
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()
    m = re.search(r'<script id="trace-data" '
                  r'type="application/json">(.*?)</script>', html, re.S)
    if m is None:
        raise ValueError("no embedded trace data")
    data = json.loads(m.group(1).replace("<\\/", "</"))
    ch = data.get("chunked")
    if ch:
        events = []
        tags = re.findall(r'<script id="trace-chunk-(\d+)" '
                          r'type="application/gzip-base64">(.*?)</script>',
                          html, re.S)
        for _, b64 in sorted(((int(k), s) for k, s in tags)):
            events.extend(json.loads(
                gzip.decompress(base64.b64decode(b64))))
        if len(events) != ch.get("total"):
            raise ValueError(f"chunked trace incomplete: {len(events)} "
                             f"of {ch.get('total')} events")
        data["events"] = events
    return data


def _ochiai_rank(cov_fail, cov_pass, n_fail, cap=15):
    """#65: Ochiai suspiciousness — ef / sqrt(n_fail * (ef + ep)) — for
    every unit at least one FAILING run/test touched. Ranked descending;
    ties stay visibly equal (then sorted by unit for stability)."""
    scored = []
    for u, ef in cov_fail.items():
        ep = cov_pass.get(u, 0)
        scored.append((ef / ((n_fail * (ef + ep)) ** 0.5), ef, ep, u))
    scored.sort(key=lambda s: (-s[0], s[3]))
    return scored[:cap]


def _chapter_suspicion(events, granularity):
    """#98's killer join: per-TEST coverage from one suite trace ×
    chapter outcomes -> the #65 suspicion ranking without N runs.
    Returns (summary, suspicion) — either may be None: no chapters ->
    (None, None); chapters but no pass/fail contrast -> (summary, None).
    Skipped tests contribute no coverage (they measured nothing)."""
    spans, open_ = [], {}
    for i, e in enumerate(events):
        if e.get("e") != "chap":
            continue
        if e.get("k") == "s":
            open_[e.get("id")] = i
        else:
            s = open_.pop(e.get("id"), None)
            if s is not None:
                spans.append((e.get("id"), e.get("o", "passed"), s, i))
    if not spans:
        return None, None
    counts = {"passed": 0, "failed": 0, "skipped": 0, "other": 0}
    for _, o, _, _ in spans:
        counts[o if o in counts else "other"] += 1
    n_pass = counts["passed"]
    n_fail = counts["failed"] + counts["other"]   # errors fail too
    summary = {"tests": len(spans), **counts,
               "failedIds": [nid for nid, o, _, _ in spans
                             if o not in ("passed", "skipped")][:20]}
    if not (n_pass and n_fail):
        return summary, None
    cov_fail, cov_pass = {}, {}
    fail_spans = []
    for nid, o, s, t in spans:
        if o == "skipped":
            continue
        cov = {(e["f"], e["l"]) for e in events[s:t]
               if e.get("f") and e.get("l") and e.get("e") != "chap"}
        if o == "passed":
            bucket = cov_pass
        else:
            bucket = cov_fail
            fail_spans.append((s, t))
        for u in cov:
            bucket[u] = bucket.get(u, 0) + 1
    rows = []
    for score, ef, ep, (f, l) in _ochiai_rank(cov_fail, cov_pass,
                                              n_fail):
        ev_idx = None
        for s, t in fail_spans:
            for k in range(s, t):
                e = events[k]
                if e.get("f") == f and e.get("l") == l:
                    ev_idx = k
                    break
            if ev_idx is not None:
                break
        rows.append({"f": f, "l": l, "score": round(score, 3),
                     "ef": ef, "ep": ep, "ev": ev_idx})
    return summary, {"unit": "line" if granularity == "line"
                     else "boundary",
                     "pass": n_pass, "fail": n_fail, "top": rows}


def _shape_of(enc, depth=2):
    """#120: the STRUCTURAL shape of an encoded value — types, keys,
    nesting; never the values. Honest to the recorded depth: what the
    encoder truncated shows as an ellipsis, not a guess."""
    if not isinstance(enc, dict):
        return "?"
    t = enc.get("t")
    if t == "p":
        return enc.get("c") or "num"
    if t == "s":
        return "str"
    if t == "o":
        return enc.get("c") or "object"
    if t in ("list", "tuple", "set"):
        if depth <= 0 or not enc.get("v"):
            inner = "…" if enc.get("n") else ""
        else:
            kinds = sorted({_shape_of(x, depth - 1)
                            for x in enc["v"][:8]})
            inner = "|".join(kinds)
        return f"{t}[{inner}]"
    if t == "dict":
        pairs = [p for p in (enc.get("v") or [])[:6]
                 if isinstance(p, (list, tuple)) and len(p) == 2]
        keys = [str(p[0]).strip("'\"") for p in pairs]
        if depth > 0 and keys and len(keys) <= 5 \
                and all(len(k) <= 14 for k in keys):
            more = "…" if (enc.get("n") or 0) > len(pairs) else ""
            return "dict{" + ", ".join(keys) + more + "}"
        return f"dict{{{enc.get('n', '?')} keys}}"
    if t == "obj":
        return (enc.get("c") or "obj") + "{…}"
    return t or "?"


def _boundaries(events):
    """#120: aggregate each function's OBSERVED interface — the shape
    every argument and return actually had, with counts and the first
    event index per shape (the jump target for a deviant call). Yields
    are excluded: a generator's yields are its own story, not its
    return contract."""
    out = {}
    for i, e in enumerate(events):
        fn = e.get("fn")
        if fn in (None, "<module>", "<genexpr>", "<listcomp>",
                  "<dictcomp>", "<setcomp>") \
                or e.get("e") not in ("call", "return"):
            continue          # comprehension frames are machinery,
                              # their .0 iterator is not an interface
        if e.get("e") == "call" and (e.get("g") or {}).get("s") == "r":
            continue                      # a resume is not a new call
        key = f"{e.get('f')}:{fn}"
        b = out.setdefault(key, {"calls": 0, "args": {}, "ret": {},
                                 "l": e.get("l")})
        if e.get("e") == "call":
            b["calls"] += 1
            for name, enc in (e.get("ch") or {}).items():
                sh = _shape_of(enc)
                d = b["args"].setdefault(name, {})
                if sh not in d:
                    d[sh] = [0, i]
                d[sh][0] += 1
        else:
            if (e.get("g") or {}).get("s") == "y" or "ret" not in e:
                continue
            sh = _shape_of(e["ret"])
            d = b["ret"]
            if sh not in d:
                d[sh] = [0, i]
            d[sh][0] += 1
    return {k: v for k, v in out.items() if v["calls"]}


def _run_harness(orig_argv, n_runs, out, entry_label, granularity,
                 module, script, chaos_seed=None, mine=False):
    """#63: one run is an anecdote; N runs are an experiment. Execute the
    target N times (each a fresh child tracer with identical stdin),
    classify every outcome (exception type + crash site), keep ONE
    representative trace per class — first seen, not N files — and write
    a self-contained report. Exit 0 only if every run was clean."""
    stem = (module.replace(".", "_") if module is not None
            else os.path.splitext(os.path.basename(script))[0])
    if out is None:
        out = f"runs_{stem}.html"
        k = 2
        while os.path.exists(out):
            out = f"runs_{stem}_{k}.html"
            k += 1
    out = os.path.abspath(out)
    rep_base = os.path.splitext(out)[0]

    # children: same flags, minus the harness's own, plus an explicit
    # granularity (the parent resolved the default; a child would
    # re-default a script entry to line) and their own --out. The walk
    # mirrors the real parser — every value-taking flag is known, and
    # stripping stops at -m or the script, so a --out (or --runs) in the
    # TARGET's own argv is the target's business. --runs especially must
    # never reach a child: that child would fork a harness of its own.
    valued = {"--out", "--root", "--export-perfetto", "--include",
              "--exclude", "--granularity", "--max-events", "--start-at",
              "--start-count", "--start-when", "--backend", "--trip",
              "--runs", "--check", "--chaos-schedule", "--fsm",
              "--fsm-declare", "--memo", "--starve-ms", "--probe-reduction"}
    # --chaos-schedule is stripped and re-issued per child with a
    # DERIVED seed (base+i-1): N runs under one seed would explore one
    # biased stream N times; N seeds explore N different ones, and any
    # failing child remains reproducible from its own recorded seed.
    strip = {"--runs", "--out", "--granularity", "--chaos-schedule",
             "--mine"}
    child_flags, i = [], 0
    while i < len(orig_argv):
        tok = orig_argv[i]
        if tok == "-m" or not tok.startswith("--"):
            child_flags.extend(orig_argv[i:])   # theirs from here on
            break
        step = 2 if tok in valued and i + 1 < len(orig_argv) else 1
        if tok not in strip:
            child_flags.extend(orig_argv[i:i + step])
        i += step
    child_flags = ["--granularity", granularity] + child_flags

    # the measurement protocol: every run gets the SAME stdin bytes.
    # Probe before blocking — a daemon/CI stdin that never closes must
    # not hang run 0 (found the hard way: this exact hang was the
    # suite's ghost flake) — and ANNOUNCE before any blocking read, so
    # a slow pipe is never mistaken for a freeze.
    stdin_bytes = b""
    if not sys.stdin.isatty():
        try:
            import select
            ready, _, _ = select.select([sys.stdin], [], [], 0.5)
        except Exception:
            ready = [sys.stdin]      # no select (exotic platform): read
        if ready:
            print("pyreplay: reading stdin to EOF (the N-run protocol "
                  "feeds every run the same bytes)…", flush=True)
            try:
                stdin_bytes = sys.stdin.buffer.read()
            except Exception:
                stdin_bytes = b""
        else:
            print("pyreplay: stdin open but quiet after 0.5s — the "
                  "runs get EMPTY stdin (pipe input explicitly, or "
                  "close the descriptor)", flush=True)

    shown = " ".join([os.path.basename(sys.executable),
                      os.path.basename(SELF)] + child_flags)
    print(f"pyreplay: {n_runs} runs of {entry_label} ({granularity} "
          f"granularity), identical stdin each run", flush=True)
    if chaos_seed is not None:
        print(f"pyreplay: schedule chaos — seed base {chaos_seed}, run i "
              f"gets seed {chaos_seed}+i-1; every run is PERTURBED on "
              f"purpose (a failing run reruns with its own seed)",
              flush=True)
    per_run, seen_cls, interrupted = [], set(), False
    # #65 SBFL: per-run coverage survives the trace deletion — the set
    # of (file, line) pairs each run touched, split by outcome
    cov_fail, cov_pass = {}, {}
    n_fail_cov = n_pass_cov = 0
    mine_acc = {}        # #74: fingerprints survive the trace deletion
    fsm_acc = None       # #132: N runs merged into ONE machine
    try:
        for i in range(1, n_runs + 1):
            tr_path = f"{rep_base}_run{i}.html"
            cmd = [sys.executable, SELF, "--out", tr_path] \
                + (["--chaos-schedule", str(chaos_seed + i - 1)]
                   if chaos_seed is not None else []) + child_flags
            t0 = time.perf_counter()
            r = subprocess.run(cmd, input=stdin_bytes,
                               capture_output=True)
            ms = (time.perf_counter() - t0) * 1000.0
            cls, ev_count, note = f"no trace (exit {r.returncode})", 0, None
            cov = None
            if os.path.exists(tr_path):
                try:
                    data = _extract_payload(tr_path)
                    ev_count = len(data.get("events", []))
                    cov = {(e["f"], e["l"]) for e in data.get("events", [])
                           if e.get("f") and e.get("l")}
                    if mine:      # #74: fingerprints before deletion
                        _mine_collect(data, mine_acc, i)
                    if data.get("fsm"):   # #132: merge machines
                        f = data["fsm"]
                        if fsm_acc is None:
                            fsm_acc = {"expr": f["expr"],
                                       "declared": bool(f["declared"]),
                                       "states": {}, "edges": {},
                                       "runs": 0, "viol": 0}
                        fsm_acc["runs"] += 1
                        fsm_acc["viol"] += f.get("viol", 0)
                        for s in f["states"]:
                            st = fsm_acc["states"].setdefault(
                                s["v"], {"dwell": 0, "runs": 0})
                            st["dwell"] += s["dwell"]
                            st["runs"] += 1
                        names = [s["v"] for s in f["states"]]
                        for e in f["edges"]:
                            key = names[e["a"]] + " -> " + names[e["b"]]
                            me = fsm_acc["edges"].setdefault(
                                key, {"n": 0, "runs": 0,
                                      "forbidden": e["forbidden"],
                                      "gap": False})
                            me["n"] += e["n"]
                            me["runs"] += 1
                            me["gap"] = me["gap"] or e["gap"]
                    err = data.get("error")
                    if err is None and r.returncode == 0:
                        cls = "clean"
                    elif err is None:
                        cls = f"exit {r.returncode}"
                    else:
                        # FIRST hard exc = the raise site (the last one
                        # is merely where it escaped the top frame)
                        site = ""
                        for e in data.get("events", []):
                            if e.get("e") == "exc" and e.get("x") \
                                    and not e["x"].get("soft"):
                                site = f" at {e['f']}:{e['l']}"
                                break
                        cls = err.split(":")[0].strip() + site
                except Exception as exc:
                    cls = f"unreadable trace ({type(exc).__name__})"
                    cov = None
            if cov is not None:
                bucket = cov_pass if cls == "clean" else cov_fail
                if cls == "clean":
                    n_pass_cov += 1
                else:
                    n_fail_cov += 1
                for u in cov:
                    bucket[u] = bucket.get(u, 0) + 1
            first = cls not in seen_cls
            seen_cls.add(cls)
            if first and cls != "clean":
                # a crashing target's diagnostics usually land on stdout
                # (the runner folds the traceback into the trace itself);
                # prefer stderr when it has anything, else stdout
                tail = r.stderr.decode(errors="replace").strip() \
                    or r.stdout.decode(errors="replace").strip()
                note = "\n".join(tail.splitlines()[-4:]) or None
            kept = None
            if first and os.path.exists(tr_path):
                kept = os.path.basename(tr_path)
            elif os.path.exists(tr_path):
                os.remove(tr_path)
            per_run.append({"i": i, "cls": cls,
                            "ms": round(ms, 1), "ev": ev_count,
                            "kept": kept, "note": note})
            print(f"  run {i}/{n_runs}: {cls} ({ms:.0f} ms, "
                  f"{ev_count} events)", flush=True)
    except KeyboardInterrupt:
        interrupted = True
        print(f"pyreplay: interrupted — reporting the {len(per_run)} "
              f"completed runs", flush=True)
    if not per_run:
        print("error: no runs completed — nothing to report")
        return 2

    # #65 SBFL (Ochiai): score every unit at least one FAILING run
    # touched — ef / sqrt(totalFail * (ef + ep)). Needs contrast: with
    # no passing or no failing runs there is no signal, and the report
    # says nothing rather than inventing a ranking.
    suspicion = None
    if n_fail_cov and n_pass_cov:
        scored = _ochiai_rank(cov_fail, cov_pass, n_fail_cov)
        # sources + a jump target per suspect, from the kept traces
        sources, fail_pls = {}, []
        outdir = os.path.dirname(out)
        for r_ in per_run:
            if not r_["kept"]:
                continue
            rep_path = os.path.join(outdir, r_["kept"])
            try:
                pl = _extract_payload(rep_path)
            except Exception:
                continue   # unreadable rep: suspects lose links, not truth
            for relf, text in (pl.get("sources") or {}).items():
                sources.setdefault(relf, text)
            if r_["cls"] != "clean":
                fail_pls.append((r_["kept"], pl.get("events", [])))
        rows = []
        for score, ef, ep, (f, l) in scored:
            src = None
            text = sources.get(f)
            if text:
                ls = text.splitlines()
                if 0 < l <= len(ls):
                    src = ls[l - 1].strip()[:90]
            rep = ev = None
            for name, evs in fail_pls:
                for k, e in enumerate(evs):
                    if e.get("f") == f and e.get("l") == l:
                        rep, ev = name, k + 1
                        break
                if rep:
                    break
            rows.append({"f": f, "l": l, "score": round(score, 3),
                         "ef": ef, "ep": ep, "src": src,
                         "rep": rep, "ev": ev})
        suspicion = {"unit": "line" if granularity == "line"
                     else "boundary",
                     "pass": n_pass_cov, "fail": n_fail_cov,
                     "top": rows}

    mined = (_mine_derive(mine_acc, min_support=2) if mine else None)
    payload = {"script": entry_label, "requested": n_runs,
               "granularity": granularity,
               "python": sys.version.split()[0],
               "cmd": shown,   # child_flags already ends with the target
               "chaos": chaos_seed,   # #68: seed base, or null
               "interrupted": interrupted,
               "suspicion": suspicion,
               "mined": mined,        # #74, or null without --mine
               "fsm": fsm_acc,        # #132, or null without --fsm
               "perRun": per_run}
    template_path = os.path.join(os.path.dirname(SELF),
                                 "runs_template.html")
    with open(template_path, encoding="utf-8") as f:
        template = f.read()
    data = json.dumps(payload).replace("</", "<\\/")
    with open(out, "w", encoding="utf-8") as f:
        f.write(template.replace("__RUNS_DATA__", data))

    counts = {}
    for r_ in per_run:
        counts[r_["cls"]] = counts.get(r_["cls"], 0) + 1
    for cls, cnt in sorted(counts.items(), key=lambda kv: -kv[1]):
        rep = next((r_["kept"] for r_ in per_run
                    if r_["cls"] == cls and r_["kept"]), None)
        print(f"  {cnt:4d}x {cls}" + (f"  -> {rep}" if rep else ""))
    if suspicion and suspicion["top"]:
        u = "lines" if suspicion["unit"] == "line" \
            else "call/return/raise lines (fn granularity)"
        print(f"  suspicion — Ochiai over {u}, "
              f"{suspicion['pass']} pass / {suspicion['fail']} fail "
              f"(correlation, not causation):")
        for row in suspicion["top"][:5]:
            print(f"    {row['score']:.2f}  {row['f']}:{row['l']}"
                  + (f"  {row['src']}" if row["src"] else ""))
    if mined is not None:
        _mine_print(mined, len(per_run))
    if fsm_acc:
        print(f"\nobserved machine [{fsm_acc['expr']}] across "
              f"{fsm_acc['runs']} run(s) — observed ⊆ true; a missing "
              f"edge is never evidence of absence:")
        for key, e in sorted(fsm_acc["edges"].items(),
                             key=lambda kv: -kv[1]["n"]):
            print(f"    {key}   ×{e['n']} in {e['runs']} run(s)"
                  + ("   ⚠ NOT DECLARED" if e["forbidden"] else "")
                  + ("   (crossed an unobservable gap)"
                     if e["gap"] else ""))
        if fsm_acc["viol"]:
            print(f"  ⚠ {fsm_acc['viol']} undeclared transition(s) — "
                  f"each is a viol event in its kept trace")
    print(f"report -> {out}")
    return 0 if set(counts) == {"clean"} else 1


# ---- #132: the observed state machine -----------------------------------
# One declared name (--fsm EXPR) rides the #72 watch machinery — the
# change stream IS the transition log. The post-pass mines the machine
# from it: nodes = observed values sized by dwell, edges = observed
# transitions with counts and first-occurrence jumps. Honesty, verbatim
# where the machine is drawn: observed machine ⊆ true machine — a
# missing edge is never evidence of absence.

def _fsm_label(enc):
    """A state's display label from its encoding — primitives verbatim,
    containers by shape (a state variable should be small; the panel
    says so when it isn't)."""
    if not isinstance(enc, dict):
        return "?"
    if enc.get("c") == "unevaluable":
        return None                       # a hole, not a state
    if enc.get("t") in ("p", "s"):        # scalar / string: the value
        v = str(enc.get("v"))
        return v if len(v) <= 40 else v[:38] + "…"
    if enc.get("n") is not None:
        return (enc.get("c") or enc.get("t")) + "[" + str(enc["n"]) + "]"
    return enc.get("c") or enc.get("t") or "?"


def _parse_fsm_declare(path):
    """Declared-transitions file: one 'A -> B' per line (values as the
    replayer displays them), '#' comments. Returns a set of pairs."""
    declared = set()
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            a, sep, b = line.partition("->")
            if not sep or not a.strip() or not b.strip():
                raise SystemExit(
                    f"error: --fsm-declare {path}:{lineno}: expected "
                    f"'FROM -> TO' (values as displayed), got: {line!r}")
            declared.add((a.strip(), b.strip()))
    return declared


def _build_fsm(events, expr, declared):
    """Mine the machine from the recorded change stream, in global
    stream order (the observed interleaving is the truth). When a
    declared set exists, undeclared transitions become viol events
    SPLICED after the observing event — labeled as derived, and the
    #73 machinery (badge, pins, type:viol) renders them for free."""
    wkey = "watch:" + expr

    def walk():
        cur, gap = None, False
        for i, ev in enumerate(events):
            ch = ev.get("ch") or {}
            if wkey not in ch:
                continue
            lab = _fsm_label(ch[wkey])
            if lab is None:               # unobservable stretch begins
                gap = True
                continue
            if cur is None:
                yield (i, None, lab, False)
                cur, gap = lab, False
            elif lab != cur:
                yield (i, cur, lab, gap)
                cur, gap = lab, False
            else:
                gap = False
        return

    if declared:
        inserts = []
        for i, a, b, _gap in walk():
            if a is not None and (a, b) not in declared:
                src = events[i]
                inserts.append((i, {
                    "e": "viol", "f": src.get("f"), "l": src.get("l"),
                    "fn": src.get("fn"),
                    **({"t": src["t"]} if src.get("t") else {}),
                    **({"tk": src["tk"]} if src.get("tk") else {}),
                    "inv": f"fsm: {a} -> {b} not declared "
                           f"(derived from --fsm-declare)",
                    "vals": {expr: (src.get("ch") or {}).get(wkey)},
                }))
        for i, ev in reversed(inserts):
            events.insert(i + 1, ev)

    states, order = {}, []
    edges = {}
    obs = []
    for i, a, b, gap in walk():
        if b not in states:
            states[b] = {"v": b, "dwell": 0, "first": i}
            order.append(b)
        obs.append([i, order.index(b)])
        if a is not None:
            key = (a, b)
            e = edges.setdefault(key, {"n": 0, "first": i, "gap": False})
            e["n"] += 1
            e["gap"] = e["gap"] or gap
    for k, (i, si) in enumerate(obs):
        end = obs[k + 1][0] if k + 1 < len(obs) else len(events)
        states[order[si]]["dwell"] += end - i
    n_viol = 0
    edge_list = []
    for (a, b), e in sorted(edges.items(),
                            key=lambda kv: (-kv[1]["n"], kv[0])):
        forb = bool(declared) and (a, b) not in declared
        if forb:
            n_viol += e["n"]
        edge_list.append({"a": order.index(a), "b": order.index(b),
                          "n": e["n"], "first": e["first"],
                          "gap": e["gap"], "forbidden": forb})
    return {"expr": expr,
            "declared": sorted(list(x) for x in declared)
            if declared else None,
            "states": [states[v] for v in order],
            "edges": edge_list, "obs": obs, "viol": n_viol}


# ---- #125: mutation-survivor forensics ----------------------------------
# Mutation testing's chore is the SURVIVING mutant — a planted bug no
# test killed. The bridge uses mutmut AS-IS (never rebuilt): it reads
# the survivor list (`mutmut results`), the nearest tests
# (mutants/mutmut-stats.json, mutmut's own coverage mapping) and the
# mutation diff (`mutmut show ID`). The two traced runs happen on a
# PATCHED SHADOW COPY of the project — real files, real line numbers,
# identical structure except the mutation — so #64's alignment lands
# exactly on the behavioral difference, and identical traces can
# honestly mean "possibly an equivalent mutant" instead of trampoline
# noise. Stated plainly in the report.

def _apply_unified_diff(path, diff_text):
    """Apply mutmut's function-scoped diff by UNIQUE context match —
    its hunk numbers are function-relative, so positions are useless;
    the old block (context + removals) must appear exactly once in
    the file, or the caller refuses the survivor honestly."""
    with open(path, encoding="utf-8") as fh:
        lines = [ln.rstrip("\n") for ln in fh.read().splitlines()]
    old_block, new_block = [], []
    for raw in diff_text.splitlines():
        if raw.startswith(("---", "+++", "@@", "#")) or not raw:
            continue
        if raw.startswith("-"):
            old_block.append(raw[1:])
        elif raw.startswith("+"):
            new_block.append(raw[1:])
        else:
            old_block.append(raw[1:])
            new_block.append(raw[1:])
    if not old_block:
        return False
    hits = [i for i in range(len(lines) - len(old_block) + 1)
            if lines[i:i + len(old_block)] == old_block]
    if len(hits) != 1:
        return False        # absent or ambiguous: never guess
    i = hits[0]
    lines[i:i + len(old_block)] = new_block
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return True


def _forensics_harness(ids):
    import importlib.util
    import shutil
    import tempfile
    root = os.getcwd()
    mut_dir = os.path.join(root, "mutants")
    stats_path = os.path.join(mut_dir, "mutmut-stats.json")
    if not os.path.isdir(mut_dir) or not os.path.exists(stats_path):
        print("error: no mutants/ here — run `mutmut run` first (the "
              "bridge reads mutmut's own artifacts; it never mutates "
              "code itself)")
        return 2
    if importlib.util.find_spec("mutmut") is None:
        print("error: mutmut is not importable in THIS python — run "
              "the tracer with the interpreter that has it "
              "(e.g. .venv/bin/python tracer.py --forensics)"
              + _venv_hint())
        return 2
    with open(stats_path, encoding="utf-8") as fh:
        stats = json.load(fh)
    tests_by_fn = stats.get("tests_by_mangled_function_name", {})
    if not ids:
        r = subprocess.run([sys.executable, "-m", "mutmut", "results"],
                           capture_output=True, text=True, cwd=root,
                           stdin=subprocess.DEVNULL, timeout=120)
        ids = [ln.split(":")[0].strip()
               for ln in r.stdout.splitlines()
               if ln.strip().endswith(": survived")]
        if not ids:
            print("no survivors — every mutant was killed. The suite "
                  "held; nothing to explain.")
            return 0
        if len(ids) > 5:
            print(f"pyreplay forensics: {len(ids)} survivors — "
                  f"examining the first 5 (name specific ids for "
                  f"the rest)", flush=True)
            ids = ids[:5]
    n_div = n_eq = n_skip = 0
    for sid in ids:
        mangled = sid.rsplit("__mutmut_", 1)[0]
        tests = tests_by_fn.get(mangled, [])
        print(f"\n⛏ survivor {sid}", flush=True)
        r = subprocess.run([sys.executable, "-m", "mutmut", "show",
                            sid], capture_output=True, text=True,
                           cwd=root, stdin=subprocess.DEVNULL,
                           timeout=120)
        diff = "\n".join(ln for ln in r.stdout.splitlines()
                          if not ln.startswith("#"))
        for ln in diff.splitlines():
            print("    " + ln)
        m = re.search(r"^--- (\S+)", diff, re.M)
        if not m or not tests:
            reason = ("mutmut recorded no covering test for it"
                      if not tests else "no diff header")
            print(f"  SKIPPED: {reason} — run the suite by hand and "
                  f"--diverge the traces yourself")
            n_skip += 1
            continue
        target_rel = m.group(1)
        test_id = tests[0]
        print(f"  nearest test (mutmut's own mapping): {test_id}"
              + (f"  (+{len(tests) - 1} more)"
                 if len(tests) > 1 else ""))
        shadow = tempfile.mkdtemp(prefix="pyreplay-forensics-")
        shutil.copytree(root, shadow, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(
                            "mutants", ".git", "__pycache__",
                            "trace_*.html", "forensics_*.html",
                            ".venv", "*.egg-info"))
        safe = sid.replace(".", "_")
        p_orig = os.path.join(root, f"forensics_{safe}_orig.html")
        p_mut = os.path.join(root, f"forensics_{safe}_mut.html")

        def run(outp):
            cmd = [sys.executable, SELF, "--granularity", "line",
                   "--root", shadow, "--out", outp,
                   "-m", "pytest", test_id, "-q"]
            subprocess.run(cmd, capture_output=True, cwd=shadow,
                           stdin=subprocess.DEVNULL, timeout=600)
            return os.path.exists(outp)
        ok = run(p_orig)
        if not _apply_unified_diff(os.path.join(shadow, target_rel),
                                   diff):
            print("  SKIPPED: mutmut's diff did not apply cleanly to "
                  "a shadow copy — trace the trampoline by hand "
                  "(MUTANT_UNDER_TEST=" + sid + ")")
            n_skip += 1
            shutil.rmtree(shadow, ignore_errors=True)
            continue
        ok = run(p_mut) and ok
        shutil.rmtree(shadow, ignore_errors=True)
        if not ok:
            print("  SKIPPED: a traced run produced no artifact")
            n_skip += 1
            continue
        rc = _diverge(p_orig, p_mut)
        if rc == 1:
            n_div += 1
            print("  ⚖ the traces DIVERGE and every assertion still "
                  "passed — the divergence above is the assertion "
                  "you forgot to write.")
        else:
            n_eq += 1
            print("  no behavioral divergence found on this test; "
                  "possibly an equivalent mutant — or the difference "
                  "only shows under a test mutmut didn't map. Never "
                  "invented, either way.")
    print(f"\nforensics: {n_div} divergence(s) located · {n_eq} "
          f"possibly-equivalent · {n_skip} skipped. Traced on a "
          f"patched shadow copy — real files, real line numbers.")
    return 0 if (n_div or n_eq) else 1


# ---- #82: type-flow — the types every name actually held. The sneaky
# None, the str that is sometimes bytes: type instability is where
# dynamic code rots. Observations are the RECORDED CHANGES of each
# name (per file+function); this is what the code DID, not what it
# promised. Offline aggregation over existing encodings — zero
# recording cost.

TYPEFLOW_CAP = 2000


def _typeflow(events):
    agg = {}
    for i, ev in enumerate(events):
        f, fn = ev.get("f"), ev.get("fn")
        if f is None or fn is None:
            continue
        for nm, enc in (ev.get("ch") or {}).items():
            if not isinstance(enc, dict):
                continue
            ty = enc.get("c") or enc.get("t") or "?"
            key = f + "|" + fn + "|" + nm
            rec = agg.setdefault(key, {"n": 0, "ty": {}})
            rec["n"] += 1
            slot = rec["ty"].setdefault(ty, [0, i])
            slot[0] += 1
    if len(agg) > TYPEFLOW_CAP:
        keep = sorted(agg.items(), key=lambda kv: -kv[1]["n"])
        agg = dict(keep[:TYPEFLOW_CAP])
        agg["__capped__"] = {"n": len(keep) - TYPEFLOW_CAP, "ty": {}}
    return agg


# ---- #123: float hygiene — the equality trap and the ordering wobble.
# (a) float == / != flagged where it EXECUTED: the verdict machinery
# already records every guard; a compare whose participating recorded
# value is a float at that moment is the classic silent trap. Static
# tier flags float literals inside == / != — provable from source.
# (b) --probe-reduction NAME: the recorded floats of one bound list,
# re-summed under permuted orderings beside math.fsum and the EXACT
# rational sum (floats are exact binary rationals — Fraction sums
# them without error). A spread is evidence of sensitivity, never
# proof of error, and the report says so.

FLOATEQ_CAP = 200


def _float_probe(events, sources):
    static = {}
    for rel, text in sources.items():
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            continue
        rows = []
        lines = text.split("\n")
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and any(
                    isinstance(op, (ast.Eq, ast.NotEq))
                    for op in node.ops):
                operands = [node.left] + list(node.comparators)
                if any(isinstance(o, ast.Constant)
                       and isinstance(o.value, float)
                       for o in operands):
                    rows.append([node.lineno,
                                 (lines[node.lineno - 1] or "")
                                 .strip()[:60]])
        if rows:
            static[rel] = rows

    # dynamic tier: which names sit inside == / != on each guard line
    cmp_names = {}   # (rel, line) -> set of names, or None = no eq
    def names_of(rel, line, expr):
        key = (rel, line)
        if key in cmp_names:
            return cmp_names[key]
        got = None
        try:
            t = ast.parse(expr, mode="eval")
            got = set()
            for node in ast.walk(t):
                if isinstance(node, ast.Compare) and any(
                        isinstance(op, (ast.Eq, ast.NotEq))
                        for op in node.ops):
                    for o in [node.left] + list(node.comparators):
                        for sub in ast.walk(o):
                            if isinstance(sub, ast.Name):
                                got.add(sub.id)
            if not got:
                got = None
        except SyntaxError:
            got = None       # truncated/odd expr: no claim
        cmp_names[key] = got
        return got

    dyn = []
    stacks, gen_saved = {}, {}
    for i, ev in enumerate(events):
        e = ev.get("e")
        stack = stacks.setdefault(ev.get("t", "main"), [])
        if e == "call":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "r" \
                    and gm.get("i") in gen_saved:
                stack.append(gen_saved.pop(gm["i"]))
            else:
                stack.append({})
        elif e == "return":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "y" and stack:
                gen_saved[gm["i"]] = stack[-1]
            if stack:
                stack.pop()
            continue
        if not stack:
            continue
        frame = stack[-1]
        for nm, enc in (ev.get("ch") or {}).items():
            if isinstance(enc, dict) and enc.get("t") == "p":
                frame[nm] = enc.get("c")
        cond = ev.get("cond")
        if cond is None or ("==" not in cond.get("x", "")
                            and "!=" not in cond.get("x", "")):
            continue
        names = names_of(ev.get("f"), ev.get("l"), cond["x"])
        if not names:
            continue
        floats = sorted(nm for nm in names
                        if frame.get(nm) == "float")
        if floats and len(dyn) < FLOATEQ_CAP:
            dyn.append([i, floats])
    if not static and not dyn:
        return None
    return {"static": static, "dyn": dyn,
            "capped": len(dyn) >= FLOATEQ_CAP}


def _reduction_probe(events, name):
    import math
    import random as _rnd
    from fractions import Fraction
    last = None
    last_fn = None
    for ev in events:
        enc = (ev.get("ch") or {}).get(name)
        if isinstance(enc, dict):
            last = enc
            last_fn = ev.get("fn")
    if last is None:
        return {"name": name, "refused":
                "never recorded — bind a variable that changes"}
    if last.get("t") not in ("list", "tuple"):
        return {"name": name, "refused":
                "not a sequence (%s) — a reduction probe needs the "
                "operand list" % (last.get("c") or last.get("t"))}
    if last.get("n") != len(last.get("v") or []):
        return {"name": name, "refused":
                "windowed (%d of %d elements recorded) — permuting a "
                "window would claim the whole"
                % (len(last.get("v") or []), last.get("n") or 0)}
    vals = []
    for el in last["v"]:
        if not (isinstance(el, dict) and el.get("t") == "p"
                and el.get("c") in ("int", "float")):
            return {"name": name, "refused":
                    "non-numeric element — only int/float sums are "
                    "probed"}
        v = float(el["v"])
        if math.isnan(v):
            return {"name": name, "refused":
                    "contains NaN — ordering experiments are "
                    "meaningless past a NaN (see --trip nan)"}
        vals.append(v)
    if len(vals) < 3:
        return {"name": name, "refused":
                "%d element(s) — nothing to permute" % len(vals)}
    def fold(seq):
        acc = 0.0
        for v in seq:
            acc += v
        return acc
    as_rec = fold(vals)
    fs = math.fsum(vals)
    exact = float(sum(Fraction(v) for v in vals))
    asc = fold(sorted(vals))
    desc = fold(sorted(vals, reverse=True))
    rng = _rnd.Random(1234)
    sums = []
    for _ in range(20):
        p = vals[:]
        rng.shuffle(p)
        sums.append(fold(p))
    allsums = [as_rec, asc, desc] + sums
    spread = max(allsums) - min(allsums)
    return {"name": name, "fn": last_fn, "n": len(vals),
            "asRec": as_rec, "fsum": fs, "exact": exact,
            "sortAsc": asc, "sortDesc": desc,
            "permMin": min(sums), "permMax": max(sums),
            "perms": 20, "spread": spread}


# ---- #124: event-loop starvation — long synchronous stretches ----------
# A blocked loop is the "program frozen" bug class and is invisible in
# source. At fn granularity every inter-event delta is recorded; a
# contiguous same-task stretch whose deltas sum past the threshold
# held the loop that long, and the largest single delta names the
# frame the time actually sat in. Only stretches with OTHER tasks
# alive count — with nobody waiting, nobody starved.

def _detect_starvation(events, threshold_us):
    task_span = {}   # (thread, task) -> [birth_i, last_i]
    for i, ev in enumerate(events):
        tk = ev.get("tk")
        if tk is None:
            continue
        key = (ev.get("t") or "main", tk)
        if key not in task_span:
            task_span[key] = [i, i]
        else:
            task_span[key][1] = i
    if not task_span:
        return None          # no asyncio lanes recorded — not applicable
    # a created-but-not-yet-run task is already waiting: its birth is
    # the #88 create event, not its first own event (only tasks that
    # eventually ran traced code count — a wrapper task that never
    # did cannot claim starvation)
    for i, ev in enumerate(events):
        if ev.get("e") == "hb" and ev.get("hb") == "create":
            key = (ev.get("t") or "main", ev.get("dst"))
            if key in task_span and i < task_span[key][0]:
                task_span[key][0] = i
    by_thread = {}
    for i, ev in enumerate(events):
        by_thread.setdefault(ev.get("t") or "main", []).append(i)
    incidents = []
    for thread, idxs in by_thread.items():
        run = []             # consecutive indices sharing one task
        run_tk = None

        def close():
            if run_tk is None or len(run) < 1:
                return
            dur = sum(events[j].get("ts") or 0 for j in run[1:])
            if dur < threshold_us:
                return
            starved = sorted(
                tk for (t2, tk), (a, b) in task_span.items()
                if t2 == thread and tk != run_tk
                and a < run[-1] and b > run[0])
            if not starved:
                return       # nobody was waiting: not starvation
            # the largest single delta names the culprit frame: walk
            # the run with a stack; the frame OPEN under that delta
            # is where the wall time sat
            gi, gus = run[0], -1
            for j in run[1:]:
                d = events[j].get("ts") or 0
                if d > gus:
                    gi, gus = j, d
            stack = []
            culprit = events[run[0]].get("fn")
            for j in run:
                ev = events[j]
                if j == gi:
                    culprit = stack[-1] if stack else ev.get("fn")
                if ev["e"] == "call":
                    stack.append(ev.get("fn"))
                elif ev["e"] == "return" and stack:
                    stack.pop()
            incidents.append({
                "tk": run_tk, "t": thread,
                "i0": run[0], "i1": run[-1], "us": dur,
                "gi": gi, "gus": gus, "fn": culprit,
                "f": events[gi].get("f"), "l": events[gi].get("l"),
                "starved": starved})

        for i in idxs:
            ev = events[i]
            tk = ev.get("tk")
            if tk != run_tk:
                close()
                run, run_tk = [], tk
            run.append(i)
            # a coroutine yield RELEASES the loop: the synchronous
            # stretch ends here. Generator yields (k=="g") return to
            # their caller, not the loop, and do not break it. A
            # mid-chain await splits a stretch by microseconds — a
            # real block is one delta and cannot be split.
            g = ev.get("g")
            if ev.get("e") == "return" and g and g.get("s") == "y" \
                    and g.get("k") in ("c", "a"):
                close()
                run, run_tk = [], None
        close()
    incidents.sort(key=lambda x: -x["us"])
    return {"thresholdMs": threshold_us / 1000, "inc": incidents}


# ---- #78: the nontermination detector (state recurrence) ----------------
# Poincaré's framing: a closed system that returns to a previous state
# must repeat forever. At every loop-head event the frame's recorded
# state is fingerprinted; an exact repeat is a cycle. "PROVEN" is
# claimed only when the recorder could actually see the whole system:
# a while-loop whose extent is statically free of calls/attributes/
# await/yield (C calls are INVISIBLE to settrace — time.time() in the
# condition would fake purity), every fingerprinted encoding complete
# (windowed containers can collide), and nothing else active in the
# window (no calls, no I/O, no other lanes, no exceptions). Anything
# less downgrades to "state recurring at line level", with the
# reasons named. The trace itself usually ends at the event cap —
# that is the expected way to catch a hang.

def build_loop_purity(text, rel):
    """Per loop-head line: can the recorder SEE this loop's whole
    state? {"line": {"kind": "while"|"for", "end": last_line,
    "reasons": [static impurity strings]}}."""
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return {}
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.While, ast.For, ast.AsyncFor)):
            continue
        reasons = []
        kind = "while" if isinstance(node, ast.While) else "for"
        if kind == "for":
            reasons.append("a for-loop's iterator is state the "
                           "recorder cannot fingerprint")
        seen = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                seen.add("calls in the loop body (C calls are "
                         "invisible to the recorder)")
            elif isinstance(sub, ast.Attribute):
                seen.add("attribute access (properties/descriptors "
                         "may read external state)")
            elif isinstance(sub, (ast.Await, ast.Yield,
                                  ast.YieldFrom)):
                seen.add("suspension points (await/yield)")
            elif isinstance(sub, ast.Global):
                seen.add("global declarations (writes escape the "
                         "frame)")
        reasons.extend(sorted(seen))
        out[str(node.lineno)] = {
            "kind": kind,
            "end": node.end_lineno or node.lineno,
            "reasons": reasons,
        }
    return out


def _enc_complete(enc):
    if not isinstance(enc, dict):
        return True
    if enc.get("n") is not None:
        v = enc.get("v")
        if not isinstance(v, list) or len(v) < enc["n"]:
            return False
        return all(_enc_complete(x) for x in v)
    return True


def _nt_bump(d, reason):
    d[reason] = d.get(reason, 0) + 1


def _detect_nonterm(events, sources):
    """The post-pass: fingerprint the frame at every loop-head event,
    report the FIRST recurrence per head. Returns a list of findings,
    strongest (proven, then longest period) first."""
    purity = {rel: build_loop_purity(text, rel)
              for rel, text in sources.items()}
    stacks, gen_saved = {}, {}
    fid_next = [0]
    seen = {}        # (fid, rel, line) -> {fp: (ev_idx, hits)}
    hits = {}        # (fid, rel, line) -> head hit count
    findings = []
    done = set()     # heads already reported
    for i, ev in enumerate(events):
        e = ev.get("e")
        stack = stacks.setdefault(ev.get("t", "main"), [])
        if e == "call":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "r" \
                    and gm.get("i") in gen_saved:
                stack.append(gen_saved.pop(gm["i"]))
                continue
            if stack:
                imp = stack[-1]["impure"]
                imp["a traced function ran inside the window"] = \
                    imp.get("a traced function ran inside the window",
                            0) + 1
            stack.append({"id": fid_next[0], "vars": {},
                          "impure": {}})
            fid_next[0] += 1
            continue
        if not stack:
            continue
        fr = stack[-1]
        if e == "return":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "y":
                gen_saved[gm["i"]] = fr
            stack.pop()
            continue
        for nm, enc in (ev.get("ch") or {}).items():
            fr["vars"][nm] = json.dumps(enc, sort_keys=True)
            if not _enc_complete(enc):
                _nt_bump(fr["impure"], "state beyond the recorded "
                         "window (a truncated encoding can collide)")
        if e in ("log",):
            _nt_bump(fr["impure"], "console I/O inside the loop window")
        if e in ("hb", "viol"):
            _nt_bump(fr["impure"], "other machinery active in the window")
        if e == "exc":
            _nt_bump(fr["impure"], "an exception unwound in the window")
        if e != "line":
            continue
        rel, line = ev.get("f"), str(ev.get("l"))
        info = purity.get(rel, {}).get(line)
        if info is None:
            continue
        key = (fr["id"], rel, line)
        if key in done:
            continue
        fp = hash(tuple(sorted(fr["vars"].items())))
        table = seen.setdefault(key, {})
        hits[key] = hits.get(key, 0) + 1
        if fp in table:
            first_i, first_hit, imp0 = table[fp]
            reasons = list(info["reasons"]) + sorted(
                r for r, c in fr["impure"].items()
                if c > imp0.get(r, 0))
            lanes = [t for t, st in stacks.items() if st]
            if len(lanes) > 1 or len(stacks) > 1:
                reasons.append("other lanes were active")
            findings.append({
                "f": rel, "head": int(line),
                "kind": info["kind"],
                "first": first_i, "again": i,
                "period": i - first_i,
                "iters": hits[key] - first_hit,
                "proven": not reasons,
                "reasons": reasons,
            })
            done.add(key)
        else:
            if len(table) < 20000:   # per-head cap; never near it
                table[fp] = (i, hits[key], dict(fr["impure"]))
    findings.sort(key=lambda g: (not g["proven"], -g["period"]))
    return findings


# ---- #66: automatic input shrinking (ddmin) -----------------------------
# A 2 MB input that crashes is a chore; the 3-line core that still
# crashes is a diagnosis. --shrink minimizes the piped stdin against
# an oracle: with --check EXPR, "the check hits" (child exit 1); with
# none, "the target crashes with the SAME exception type as the full
# input" (ddmin must preserve THE failure, never swap it for another).
# Classic Zeller ddmin over lines / whitespace tokens / bytes, with a
# per-attempt cap announced when it bites; the minimal input is
# written to a file and auto-traced at line level.

def _ddmin(units, fails, cap):
    """Zeller & Hildebrandt 2002, complement-only variant. Returns
    (minimal units, attempts, capped)."""
    attempts = [0]

    def test(u):
        attempts[0] += 1
        return fails(u)
    n = 2
    while len(units) >= 2:
        if attempts[0] >= cap:
            return units, attempts[0], True
        chunk = max(1, len(units) // n)
        reduced = False
        i = 0
        while i < len(units):
            if attempts[0] >= cap:
                return units, attempts[0], True
            comp = units[:i] + units[i + chunk:]
            if comp and test(comp):
                units = comp
                n = max(n - 1, 2)
                reduced = True
                break
            i += chunk
        if not reduced:
            if n >= len(units):
                break
            n = min(n * 2, len(units))
    # final single-unit pass: try dropping each remaining unit once
    i = 0
    while i < len(units) and len(units) > 1:
        if attempts[0] >= cap:
            return units, attempts[0], True
        comp = units[:i] + units[i + 1:]
        if test(comp):
            units = comp
        else:
            i += 1
    return units, attempts[0], False


def _shrink_harness(orig_argv, model, cap, check_active, entry_label,
                    granularity, module, script):
    stem = (module.replace(".", "_") if module is not None
            else os.path.splitext(os.path.basename(script))[0])
    valued = {"--out", "--root", "--export-perfetto", "--include",
              "--exclude", "--granularity", "--max-events",
              "--start-at", "--start-count", "--start-when",
              "--backend", "--trip", "--runs", "--check",
              "--chaos-schedule", "--sweep", "--gen", "--predict",
              "--sweep-seed", "--fsm", "--fsm-declare", "--memo", "--starve-ms", "--probe-reduction",
              "--relation", "--relation-trials", "--relation-seed",
              "--shrink-model", "--shrink-cap"}
    strip = {"--shrink", "--shrink-model", "--shrink-cap", "--out"}
    child_flags, i = [], 0
    while i < len(orig_argv):
        tok = orig_argv[i]
        if tok == "-m" or not tok.startswith("--"):
            child_flags.extend(orig_argv[i:])
            break
        step = 2 if tok in valued and i + 1 < len(orig_argv) else 1
        if tok not in strip:
            child_flags.extend(orig_argv[i:i + step])
        i += step
    child_flags = ["--granularity", granularity] + child_flags

    data = b""
    if not sys.stdin.isatty():
        try:
            import select
            ready, _, _ = select.select([sys.stdin], [], [], 0.5)
        except Exception:
            ready = [sys.stdin]
        if ready:
            print("pyreplay: reading stdin to EOF (the input to "
                  "shrink)…", flush=True)
            try:
                data = sys.stdin.buffer.read()
            except Exception:
                data = b""
    if not data:
        print("error: --shrink needs a piped stdin — the input IS "
              "the thing being minimized")
        return 2

    if model == "lines":
        units = data.decode(errors="replace").splitlines(keepends=True)
        join = "".join
    elif model == "tokens":
        units = data.decode(errors="replace").split()
        join = " ".join
    else:                                  # bytes
        units = [data[i:i + 1] for i in range(len(data))]
        join = b"".join

    tmp_out = os.path.abspath(f".shrink_{stem}_probe.html")

    def run_probe(u):
        payload_in = join(u)
        b = payload_in.encode() if isinstance(payload_in, str) \
            else payload_in
        cmd = [sys.executable, SELF, "--out", tmp_out] + child_flags
        r = subprocess.run(cmd, input=b, capture_output=True)
        err = None
        if os.path.exists(tmp_out):
            try:
                err = _extract_payload(tmp_out).get("error")
            except Exception:
                err = "unreadable"
            finally:
                try:
                    os.remove(tmp_out)
                except OSError:
                    pass
        return r.returncode, err

    rc0, err0 = run_probe(units)
    if check_active:
        oracle_desc = "the --check expression hits (child exit 1)"
        if rc0 != 1:
            print(f"error: the full input does not hit the check "
                  f"(child exit {rc0}) — the failure must reproduce "
                  f"BEFORE it can be shrunk")
            return 2

        def fails(u):
            return run_probe(u)[0] == 1
    else:
        if not err0:
            print("error: the full input does not crash the target — "
                  "give --shrink an oracle (--check EXPR) or a "
                  "crashing input")
            return 2
        kind0 = err0.split(":")[0].strip()
        oracle_desc = (f"the target crashes with {kind0} — the SAME "
                       f"failure, never a different one")

        def fails(u):
            _rc, err = run_probe(u)
            return bool(err) and err.split(":")[0].strip() == kind0

    n0 = len(units)
    print(f"pyreplay shrink: {entry_label} · {n0} {model} · oracle: "
          f"{oracle_desc} · cap {cap} attempts", flush=True)
    minimal, attempts, capped = _ddmin(units, fails, cap)
    out_txt = join(minimal)
    out_bytes = (out_txt.encode() if isinstance(out_txt, str)
                 else out_txt)
    shrunk_path = os.path.abspath(f"shrunk_{stem}.txt")
    with open(shrunk_path, "wb") as fh:
        fh.write(out_bytes)
    trace_path = os.path.abspath(f"trace_shrunk_{stem}.html")
    cmd = [sys.executable, SELF, "--out", trace_path,
           "--granularity", "line"] + child_flags[2:]
    subprocess.run(cmd, input=out_bytes, capture_output=True)
    print(f"  {n0} → {len(minimal)} {model} "
          f"({len(data)} → {len(out_bytes)} bytes) in {attempts} "
          f"attempt(s)"
          + (f" — CAP REACHED: this is the best so far, not a local "
             f"minimum (raise --shrink-cap)" if capped else
             " — 1-minimal: removing any single "
             + model.rstrip('s') + " un-fails it"), flush=True)
    print(f"  minimal input -> {os.path.basename(shrunk_path)}")
    print(f"  line-level trace of the minimal case -> "
          f"{os.path.basename(trace_path)}")
    print(f"  rerun: python3 {os.path.basename(SELF)} "
          + " ".join(shlex.quote(t) for t in child_flags[2:])
          + f" < {os.path.basename(shrunk_path)}")
    return 0


# ---- #126: the metamorphic relations harness ----------------------------
# The oracle problem's cheapest instrument: the right answer may be
# unknown, but its SYMMETRIES are not. --relation "T => R" declares an
# input transform T (an expression over x, the original stdin text)
# and an output relation R (over out0 = the original run's stdout and
# out = the transformed run's, both read from the recorded console
# lane — the faithful channel; tracer chatter never enters it). Each
# trial runs the target twice and checks R. A violation keeps BOTH
# traces and composes the --diverge command — the funnel hands you
# the microscope, it never auto-runs it.

def _parse_relation(spec):
    t_src, sep, r_src = spec.partition("=>")
    if not sep or not t_src.strip() or not r_src.strip():
        raise SystemExit(
            'error: --relation expects "TRANSFORM => RELATION", e.g. '
            "\"' '.join(reversed(x.split())) => out == out0\" — "
            "x is the original stdin text, out0/out the two stdouts")
    t_src, r_src = t_src.strip(), r_src.strip()
    try:
        t_code = compile(t_src, "<relation-T>", "eval")
        r_code = compile(r_src, "<relation-R>", "eval")
    except SyntaxError as exc:
        raise SystemExit(f"error: --relation is not a valid pair of "
                         f"expressions: {exc}")
    return {"t": t_src, "r": r_src, "tc": t_code, "rc": r_code}


def _rel_ns(extra):
    def num(s):
        return float(str(s).strip().split()[0]) if str(s).strip() \
            else 0.0

    def nums(s):
        return [float(t) for t in str(s).split()]
    ns = {"num": num, "nums": nums, "abs": abs, "min": min,
          "max": max, "len": len, "round": round, "sorted": sorted,
          "sum": sum, "reversed": reversed, "str": str, "int": int,
          "float": float, "list": list, "zip": zip,
          "enumerate": enumerate}
    ns.update(extra)
    return ns


def _relation_harness(orig_argv, relations, gen_file, trials, seed,
                      entry_label, granularity, module, script):
    """Run the target twice per (relation, trial) — original input vs
    transformed input — and check the declared output relation. Exit
    0 iff every relation held on every trial (git-bisect-ready)."""
    genfn = None
    if gen_file:
        ns = runpy.run_path(os.path.realpath(gen_file))
        genfn = ns.get("gen")
        if not callable(genfn):
            print("error: --gen file must define gen(value, seed) -> "
                  "str|bytes (the trial's stdin)")
            return 2
    stem = (module.replace(".", "_") if module is not None
            else os.path.splitext(os.path.basename(script))[0])

    valued = {"--out", "--root", "--export-perfetto", "--include",
              "--exclude", "--granularity", "--max-events",
              "--start-at", "--start-count", "--start-when",
              "--backend", "--trip", "--runs", "--check",
              "--chaos-schedule", "--sweep", "--gen", "--predict",
              "--sweep-seed", "--fsm", "--fsm-declare", "--memo", "--starve-ms", "--probe-reduction",
              "--relation", "--relation-trials", "--relation-seed"}
    strip = {"--relation", "--relation-trials", "--relation-seed",
             "--gen", "--out", "--granularity"}
    child_flags, i = [], 0
    while i < len(orig_argv):
        tok = orig_argv[i]
        if tok == "-m" or not tok.startswith("--"):
            child_flags.extend(orig_argv[i:])
            break
        step = 2 if tok in valued and i + 1 < len(orig_argv) else 1
        if tok not in strip:
            child_flags.extend(orig_argv[i:i + step])
        i += step
    child_flags = ["--granularity", granularity] + child_flags

    base_input = None
    if genfn is None:
        # the piped stdin is the one trial input (the #63 protocol:
        # probe before blocking, announce before reading)
        base_input = b""
        if not sys.stdin.isatty():
            try:
                import select
                ready, _, _ = select.select([sys.stdin], [], [], 0.5)
            except Exception:
                ready = [sys.stdin]
            if ready:
                print("pyreplay: reading stdin to EOF (each relation "
                      "runs the target on it, then on its "
                      "transform)…", flush=True)
                try:
                    base_input = sys.stdin.buffer.read()
                except Exception:
                    base_input = b""
            else:
                print("pyreplay: stdin open but quiet after 0.5s — "
                      "trials get EMPTY stdin (pipe input, or use "
                      "--gen)", flush=True)

    print(f"pyreplay relations: {entry_label} · "
          f"{len(relations)} relation(s) × {trials} trial(s) · "
          f"{granularity} granularity"
          + (f" · gen {os.path.basename(gen_file)} seed {seed}"
             if genfn else " · input = the piped stdin"), flush=True)

    def run_child(stdin_bytes, out_path):
        cmd = [sys.executable, SELF, "--out", out_path] + child_flags
        subprocess.run(cmd, input=stdin_bytes, capture_output=True)
        if not os.path.exists(out_path):
            return "", "no trace written", None
        try:
            data = _extract_payload(out_path)
        except Exception as exc:
            return "", f"unreadable trace ({type(exc).__name__})", None
        out = "\n".join(ev.get("txt", "")
                        for ev in data.get("events", [])
                        if ev.get("e") == "log"
                        and ev.get("s") == "out").strip()
        return out, data.get("error"), data

    n_viol = 0
    hashseed = os.environ.get("PYTHONHASHSEED", "random") or "random"
    for rel_i, rel in enumerate(relations, 1):
        for t in range(1, trials + 1):
            if genfn is not None:
                try:
                    raw = genfn(t, seed)
                except Exception as exc:
                    print(f"  relation {rel_i} trial {t}: gen() "
                          f"raised {type(exc).__name__}: {exc} — "
                          f"counted as a violation")
                    n_viol += 1
                    continue
                x_bytes = raw.encode() if isinstance(raw, str) else raw
            else:
                x_bytes = base_input
            x_text = x_bytes.decode(errors="replace")
            try:
                tg = _rel_ns({"x": x_text})
                tg["__builtins__"] = {}
                tx = eval(rel["tc"], tg)
            except Exception as exc:
                print(f"error: relation {rel_i} transform raised "
                      f"{type(exc).__name__}: {exc} — fix the "
                      f"expression (x is the stdin TEXT)")
                return 2
            tx_bytes = (tx if isinstance(tx, bytes)
                        else str(tx).encode())
            base = f"relation_{stem}_r{rel_i}_t{t}"
            p_orig = os.path.abspath(base + "_orig.html")
            p_x = os.path.abspath(base + "_xform.html")
            out0, err0, _d0 = run_child(x_bytes, p_orig)
            out1, err1, _d1 = run_child(tx_bytes, p_x)
            note = ""
            if err0 or err1:
                verdict = False
                note = (f"crashed — original: {err0 or 'clean'} · "
                        f"transformed: {err1 or 'clean'}")
            else:
                try:
                    rg = _rel_ns({"x": x_text, "tx": str(tx),
                                  "out0": out0, "out": out1})
                    rg["__builtins__"] = {}
                    verdict = bool(eval(rel["rc"], rg))
                except Exception as exc:
                    print(f"error: relation {rel_i} check raised "
                          f"{type(exc).__name__}: {exc} — out0/out "
                          f"are the two stdout TEXTS")
                    return 2
            if verdict:
                for pth in (p_orig, p_x):
                    try:
                        os.remove(pth)
                    except OSError:
                        pass
                print(f"  relation {rel_i} trial {t}: held",
                      flush=True)
            else:
                n_viol += 1
                print(f"  relation {rel_i} trial {t}: ⚖ VIOLATED "
                      f"[{rel['t']} => {rel['r']}]"
                      + (f" — {note}" if note else ""), flush=True)
                print(f"    out0: {out0[:80]!r}")
                print(f"    out : {out1[:80]!r}")
                print(f"    kept: {os.path.basename(p_orig)} + "
                      f"{os.path.basename(p_x)}")
                print(f"    next: python3 {os.path.basename(SELF)} "
                      f"--diverge {os.path.basename(p_orig)} "
                      f"{os.path.basename(p_x)}")
    if n_viol:
        print(f"\n{n_viol} violation(s). The symmetry is the oracle: "
              f"a broken relation is a bug OR nondeterminism"
              + (f" — PYTHONHASHSEED is {hashseed}; pin it (or "
                 f"--runs first) before trusting the verdict"
                 if hashseed == "random" else "")
              + ". Input shrinking (#66) is unbuilt — shrink by "
                "hand or with a smaller --gen value.")
        return 1
    print(f"\nall relations held on every trial — an observation "
          f"over {trials} trial(s), never a proof.")
    return 0


# ---- #134: the subproblem DAG -------------------------------------------
# Bind ONE memo structure (--memo dp) and the dependency DAG of its
# table is mined from the trace: a static pass finds every subscript
# READ and WRITE of the bound name with its index expressions; the
# dynamic pass reconstructs frame state per event and evaluates those
# indexes at the moment each site ran — read cells → written cell,
# edge by edge, as the table fills. This is the #75 container-element
# remainder RESTRICTED to the bound name (the generic slice-closure
# crossing stays open, stated in CONTRIBUTING). Honest frontiers:
# slice/starred/call-bearing/unevaluable indexes are counted as
# untracked, never guessed; a read of a cell before its first tracked
# write is the wrong-evaluation-order signature and is flagged, with
# the aliasing caveat stated in-panel.

def build_memo_sites(text, rel, name):
    """Per line: subscript chains of NAME read and written, index
    expressions compiled for reconstruction-time eval. Calls inside
    an index are refused (no eval side effects — that chain becomes
    an untracked site)."""
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return {}

    def chain_of(node):
        # dp[i][j] -> Subscript(Subscript(Name dp, i), j) -> [i, j]
        idxs = []
        while isinstance(node, ast.Subscript):
            idxs.append(node.slice)
            node = node.value
        if isinstance(node, ast.Name) and node.id == name:
            return list(reversed(idxs))
        return None

    def compile_chain(idxs):
        codes = []
        for ix in idxs:
            if isinstance(ix, ast.Slice):
                return None               # slice: cells untracked
            for sub in ast.walk(ix):
                if isinstance(sub, (ast.Call, ast.Starred,
                                    ast.NamedExpr)):
                    return None           # no eval side effects, ever
            try:
                codes.append(compile(ast.Expression(body=ix), "<memo>",
                                     "eval"))
            except (SyntaxError, TypeError, ValueError):
                return None
        return codes

    sites = {}

    def site(line):
        return sites.setdefault(line, {"w": [], "r": [], "untracked": 0,
                                       "bulk": False})

    class V(ast.NodeVisitor):
        def visit_Subscript(self, node):
            idxs = chain_of(node)
            if idxs is not None:
                codes = compile_chain(idxs)
                st = site(node.lineno)
                kind = ("w" if isinstance(node.ctx, (ast.Store, ast.Del))
                        else "r")
                if codes is None:
                    st["untracked"] += 1
                else:
                    st[kind].append(codes)
                # the chain's own inner subscripts are plumbing, but an
                # INDEX may itself read the memo (dp[dp[0]]): walk it
                for ix in idxs:
                    self.visit(ix)
                return
            self.generic_visit(node)

        def visit_Assign(self, node):
            # dp = ... (whole-name rebind): a BULK write moment
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    site(node.lineno)["bulk"] = True
            self.generic_visit(node)

    V().visit(tree)
    return {str(k): v for k, v in sites.items()
            if v["w"] or v["r"] or v["untracked"] or v["bulk"]}


def _memo_parse(enc):
    """Encoded value -> a hashable index value (int/float/str/bool/
    None, or a tuple of those). Anything else -> unusable."""
    if not isinstance(enc, dict):
        return None, False
    t = enc.get("t")
    if t == "p":
        c, v = enc.get("c"), enc.get("v")
        try:
            if c == "int":
                return int(v), True
            if c == "float":
                return float(v), True
            if c == "bool":
                return v == "True", True
            if c == "NoneType":
                return None, True
        except (TypeError, ValueError):
            return None, False
        return None, False
    if t == "s":
        return enc.get("v"), True
    if t == "tuple" and enc.get("n") == len(enc.get("v") or []):
        out = []
        for item in enc["v"]:
            val, ok = _memo_parse(item)
            if not ok:
                return None, False
            out.append(val)
        return tuple(out), True
    return None, False


def _memo_eval(codes, ns):
    """Evaluate one compiled index chain against the reconstructed
    namespace. Any failure -> None (untracked, never guessed)."""
    out = []
    for code in codes:
        try:
            v = eval(code, {"__builtins__": {}}, dict(ns))
        except Exception:
            return None
        if isinstance(v, tuple):
            if not all(isinstance(x, (int, float, str, bool,
                                      type(None))) for x in v):
                return None
        elif not isinstance(v, (int, float, str, bool, type(None))):
            return None
        out.append(v)
    return out


def _build_memo(events, sources, name):
    """The dynamic half: reconstruct frame namespaces (scalars and
    scalar-tuples only) event by event; at each site line, evaluate
    the index chains against the state BEFORE the line ran (exactly
    what the interpreter used) and grow the DAG."""
    sites_by_file = {rel: build_memo_sites(text, rel, name)
                     for rel, text in sources.items()}
    cells, order = {}, []
    fills = []
    untracked = 0
    bulk_ev = None
    bulk_evs = []
    raw_edges = []
    stacks, gen_saved = {}, {}

    def keyfmt(vals):
        return ",".join(repr(v) for v in vals)

    def cell(k):
        if k not in cells:
            cells[k] = {"first": None, "writes": 0, "idx": len(order)}
            order.append(k)
        return cells[k]

    for i, ev in enumerate(events):
        e = ev.get("e")
        stack = stacks.setdefault(ev.get("t", "main"), [])
        if e == "call":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "r" \
                    and gm.get("i") in gen_saved:
                stack.append(gen_saved.pop(gm["i"]))
                continue
            ns = {}
            for nm, enc in (ev.get("ch") or {}).items():
                val, ok = _memo_parse(enc)
                if ok:
                    ns[nm] = val
            stack.append({"ns": ns})
            continue
        if not stack:
            continue
        fr = stack[-1]
        if e == "return":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "y":
                gen_saved[gm["i"]] = fr
            stack.pop()
            continue
        # ch of event X = the PREVIOUS statement's effects, already
        # part of the state BEFORE line X runs — absorb FIRST, then
        # evaluate this line's sites against the fresh namespace
        for nm, enc in (ev.get("ch") or {}).items():
            val, ok = _memo_parse(enc)
            if ok:
                fr["ns"][nm] = val
            else:
                fr["ns"].pop(nm, None)
            if nm == name and not fr.get("prev_w"):
                # the memo changed and the statement that changed it
                # had no tracked write: append/extend/alias — a bulk
                # moment (reads of never-tracked cells attribute here)
                bulk_ev = i
                bulk_evs.append(i)
        if e == "line":
            st = sites_by_file.get(ev.get("f"), {}).get(
                str(ev.get("l")))
            if st is not None:
                if st["bulk"]:
                    bulk_ev = i
                    bulk_evs.append(i)
                untracked += st["untracked"]
                rkeys = []
                for codes in st["r"]:
                    k = _memo_eval(codes, fr["ns"])
                    if k is None:
                        untracked += 1
                    else:
                        rkeys.append(keyfmt(k))
                for codes in st["w"]:
                    k = _memo_eval(codes, fr["ns"])
                    if k is None:
                        untracked += 1
                        bulk_ev = i   # an untracked write is bulk-like
                        bulk_evs.append(i)
                        continue
                    wk = keyfmt(k)
                    c = cell(wk)
                    if c["first"] is None:
                        c["first"] = i
                    c["writes"] += 1
                    fills.append([i, c["idx"]])
                    for rk in rkeys:
                        if rk != wk:  # aug self-reads are not edges
                            raw_edges.append((rk, wk, i))
                for rk in rkeys:
                    cell(rk)          # a read names the cell, even
                                      # unwritten (the frontier shows)
            fr["prev_w"] = bool(st and st["w"])

    edge_map = {}
    for rk, wk, ev_i in raw_edges:
        a, b = cells[rk], cells[wk]
        # Three honest classes. normal: read after the cell's first
        # tracked write. base (gray dashed): a never-computed cell
        # read after a bulk init — the legitimate base-case read
        # (knapsack's zeros). pre (amber ⚠): the read saw the
        # INITIALIZATION value of a cell that is computed later —
        # physically identical whether it's a rolling array doing it
        # on purpose or a forward recurrence in the wrong evaluation
        # order; the tool states the fact, never guesses the intent.
        base = pre = False
        if a["first"] is not None and ev_i < a["first"]:
            pre = True
        elif a["first"] is None:
            if any(bv <= ev_i for bv in bulk_evs):
                base = True
            else:
                pre = True        # read of nothing at all — suspect
        key = (a["idx"], b["idx"])
        em = edge_map.setdefault(key, {"n": 0, "first": ev_i,
                                       "pre": False, "base": False})
        em["n"] += 1
        em["pre"] = em["pre"] or pre
        em["base"] = em["base"] or base
    edge_list = [{"a": a, "b": b, "n": em["n"], "first": em["first"],
                  "pre": em["pre"], "base": em["base"]}
                 for (a, b), em in sorted(edge_map.items(),
                                          key=lambda kv: kv[1]["first"])]
    cell_list = [{"k": k, "first": cells[k]["first"],
                  "writes": cells[k]["writes"]} for k in order]
    return {"name": name, "cells": cell_list, "edges": edge_list,
            "fills": fills, "untracked": untracked,
            "preReads": sum(1 for e in edge_list if e["pre"]),
            "bulk": bulk_ev}


# ---- #74: invariant mining (Daikon-lite) --------------------------------
# A small template library checked OFFLINE against recorded traces:
# candidates instantiated per variable/pair at function entry/exit and
# over each frame's value sequence, killed on the first counterexample,
# survivors ranked by support (evaluable observations). "Held in N
# observations" is an observation, never a proof — the label says so
# everywhere the facts appear. Noise control: constants imply and
# suppress weaker facts, pairs live among numeric ARGS only, containers
# are judged only when fully recorded (window honesty), NaN kills order
# facts for that observation.

def _mine_num(enc):
    if not isinstance(enc, dict) or enc.get("t") != "p":
        return None
    if enc.get("c") not in ("int", "float"):
        return None
    try:
        x = float(enc.get("v"))
    except (TypeError, ValueError):
        return None
    return None if x != x else x          # NaN: no order facts


def _mine_items(enc):
    """Fully-recorded ordered container -> list of numeric items (or
    None when truncated / non-numeric / unordered kind)."""
    if not isinstance(enc, dict) or enc.get("t") not in ("list", "tuple"):
        return None
    v = enc.get("v")
    if not isinstance(v, list) or enc.get("n") != len(v):
        return None                        # window: judged only if FULL
    out = []
    for it in v:
        x = _mine_num(it)
        if x is None:
            return None
        out.append(x)
    return out


class _VarFacts:
    """Per (function, site, variable): everything the templates need,
    updated per observation, killed monotonically (a dead fact never
    revives)."""

    __slots__ = ("count", "types", "values", "vmin", "over_c",
                 "lens", "sorted_ok", "sortable")

    def __init__(self):
        self.count = 0
        self.types = set()
        self.values = set()
        self.over_c = False       # too many distinct values for == C
        self.vmin = None
        self.lens = set()
        self.sorted_ok = True
        self.sortable = 0         # observations where sortedness judged

    def see(self, enc):
        self.count += 1
        if isinstance(enc, dict):
            self.types.add(enc.get("c") or enc.get("t") or "?")
        if not self.over_c:
            key = json.dumps(enc, sort_keys=True, default=str)
            self.values.add(key)
            if len(self.values) > 6:
                self.over_c = True
                self.values.clear()
        x = _mine_num(enc)
        if x is not None:
            self.vmin = x if self.vmin is None else min(self.vmin, x)
        if isinstance(enc, dict) and enc.get("n") is not None:
            self.lens.add(enc["n"])
        items = _mine_items(enc)
        if items is not None and len(items) >= 2:
            self.sortable += 1
            if any(a > b for a, b in zip(items, items[1:])):
                self.sorted_ok = False

    _MACHINERY = {"function", "type", "module",
                  "builtin_function_or_method", "method"}

    def facts(self, label, site):
        out = []
        # def-bindings, classes, imports: machinery, not data — a fact
        # about them is spam, not insight
        if self.count == 0 or self.types <= self._MACHINERY:
            return out
        if not self.over_c and len(self.values) == 1:
            try:
                enc = json.loads(next(iter(self.values)))
            except Exception:
                enc = None
            shown = (enc.get("v") if isinstance(enc, dict)
                     and enc.get("t") == "p"
                     else "one recorded value")
            if isinstance(shown, str) and len(shown) > 24:
                shown = shown[:22] + "…"
            out.append((f"{label} == {shown}{site}", self.count))
            return out                     # == C implies the rest
        if len(self.types) == 1:
            out.append((f"{label}: type {next(iter(self.types))} "
                        f"constant{site}", self.count))
        if self.vmin is not None:
            if self.vmin > 0:
                out.append((f"{label} > 0{site}", self.count))
            elif self.vmin >= 0:
                out.append((f"{label} >= 0{site}", self.count))
        if len(self.lens) == 1 and self.lens != {0}:
            out.append((f"len({label}) == {next(iter(self.lens))}"
                        f"{site}", self.count))
        return out


class _PairFacts:
    __slots__ = ("count", "always_eq", "always_le", "always_ge")

    def __init__(self):
        self.count = 0
        self.always_eq = self.always_le = self.always_ge = True

    def see(self, a, b):
        self.count += 1
        if a != b:
            self.always_eq = False
        if a > b:
            self.always_le = False
        if a < b:
            self.always_ge = False

    def fact(self, na, nb, site):
        if self.count < 2:
            return None
        if self.always_eq:
            return (f"{na} == {nb}{site}", self.count)
        if self.always_le:
            return (f"{na} <= {nb}{site}", self.count)
        if self.always_ge:
            return (f"{na} >= {nb}{site}", self.count)
        return None


def _mine_collect(payload, acc, run_id):
    """Walk one payload's events (the annotate_conditionals frame-stack
    pattern) and feed every entry/exit/lifetime observation into acc,
    keyed by file:function."""
    stacks, gen_saved = {}, {}
    for ev in payload.get("events", []):
        e = ev.get("e")
        stack = stacks.setdefault(ev.get("t", "main"), [])
        if e == "call":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "r" \
                    and gm.get("i") in gen_saved:
                stack.append(gen_saved.pop(gm["i"]))
                continue
            key = f"{ev.get('f')}:{ev.get('fn')}"
            fr = {"key": key, "vars": {}, "seq": {}}
            a = acc.setdefault(key, {
                "frames": 0, "runs": set(),
                "entry": {}, "exit": {}, "ret": _VarFacts(),
                "pairs": {}, "life": {}})
            a["frames"] += 1
            a["runs"].add(run_id)
            args = ev.get("ch") or {}
            nums = {}
            for name, enc in args.items():
                a["entry"].setdefault(name, _VarFacts()).see(enc)
                fr["vars"][name] = enc
                x = _mine_num(enc)
                if x is not None:
                    nums[name] = x
                    fr["seq"][name] = [x]
            names = sorted(nums)
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    a["pairs"].setdefault(
                        (names[i], names[j]), _PairFacts()).see(
                        nums[names[i]], nums[names[j]])
            stack.append(fr)
            continue
        if not stack:
            continue
        fr = stack[-1]
        for name, enc in (ev.get("ch") or {}).items():
            fr["vars"][name] = enc
            x = _mine_num(enc)
            if x is not None:
                fr["seq"].setdefault(name, []).append(x)
        if e == "return":
            gm = ev.get("g")
            if gm is not None and gm.get("s") == "y":
                gen_saved[gm["i"]] = fr     # suspended, not an exit
                stack.pop()
                continue
            a = acc.get(fr["key"])
            if a is not None:
                for name, enc in fr["vars"].items():
                    a["exit"].setdefault(name, _VarFacts()).see(enc)
                if "ret" in ev:
                    a["ret"].see(ev.get("ret"))
                for name, seq in fr["seq"].items():
                    if len(seq) < 3:
                        continue
                    lf = a["life"].setdefault(
                        name, {"nondec": True, "noninc": True,
                               "count": 0})
                    lf["count"] += 1
                    if any(x > y for x, y in zip(seq, seq[1:])):
                        lf["nondec"] = False
                    if any(x < y for x, y in zip(seq, seq[1:])):
                        lf["noninc"] = False
            stack.pop()


def _mine_derive(acc, min_support=1):
    """Surviving facts per function, ranked by support. min_support
    guards the multi-run report against single-anecdote spam."""
    out = {}
    for key, a in sorted(acc.items()):
        facts = []
        for name, vf in sorted(a["entry"].items()):
            facts += vf.facts(name, " at entry")
        exit_only = {n: vf for n, vf in a["exit"].items()}
        for name, vf in sorted(exit_only.items()):
            for s, sup in vf.facts(name, " at exit"):
                # a var constant at entry AND exit reads once, at entry
                if not any(s.replace(" at exit", " at entry") == s0
                           for s0, _ in facts):
                    facts.append((s, sup))
            if vf.sortable and vf.sorted_ok:
                facts.append((f"{name} sorted (ascending) at return",
                              vf.sortable))
        for s, sup in a["ret"].facts("return", ""):
            facts.append((s, sup))
        if a["ret"].sortable and a["ret"].sorted_ok:
            facts.append(("return value sorted (ascending)",
                          a["ret"].sortable))
        for (na, nb), pf in sorted(a["pairs"].items()):
            f = pf.fact(na, nb, " at entry")
            if f:
                facts.append(f)
        for name, lf in sorted(a["life"].items()):
            if lf["nondec"] and lf["noninc"]:
                continue                    # constant: entry facts own it
            if lf["nondec"]:
                facts.append((f"{name} monotonically nondecreasing "
                              f"(per call)", lf["count"]))
            elif lf["noninc"]:
                facts.append((f"{name} monotonically nonincreasing "
                              f"(per call)", lf["count"]))
        facts = [(s, sup) for s, sup in facts if sup >= min_support]
        if facts:
            facts.sort(key=lambda f: (-f[1], f[0]))
            out[key] = {"frames": a["frames"],
                        "runs": len(a["runs"]),
                        "facts": [{"s": s, "sup": sup}
                                  for s, sup in facts]}
    return out


def mine_invariants(payloads, min_support=1):
    """#74 entry point: mine one or many payloads. Returns
    {file:fn -> {frames, runs, facts:[{s, sup}]}}."""
    acc = {}
    for i, p in enumerate(payloads):
        _mine_collect(p, acc, i)
    return _mine_derive(acc, min_support)


def _mine_print(mined, n_runs):
    print(f"\nmined invariants — held in EVERY evaluable observation "
          f"across {n_runs} run(s); an observation, NEVER a proof:")
    if not mined:
        print("  (nothing survived — too few observations, or nothing "
              "held everywhere)")
        return
    for key, m in mined.items():
        print(f"  {key} — {m['frames']} call(s) / {m['runs']} run(s):")
        for f in m["facts"]:
            print(f"    {f['s']}   [held {f['sup']}x]")


def _parse_sweep(spec):
    """#127: 'n=1000,2000,4000' or 'alpha=3.0..5.0:5' -> (name, values).
    A comma list is taken verbatim; lo..hi:K is K evenly spaced points.
    Integral values stay ints (sizes); the rest stay floats (knobs)."""
    name, _, vals = spec.partition("=")
    name, vals = name.strip(), vals.strip()
    if not name or not vals:
        raise SystemExit("error: --sweep expects NAME=v1,v2,... "
                         "or NAME=lo..hi:K")
    try:
        if ".." in vals:
            rng, _, k = vals.partition(":")
            lo, _, hi = rng.partition("..")
            k = int(k or 8)
            if k < 2:
                raise ValueError("K must be >= 2")
            lo, hi = float(lo), float(hi)
            xs = [lo + (hi - lo) * i / (k - 1) for i in range(k)]
        else:
            xs = [float(v) for v in vals.split(",")]
    except ValueError as exc:
        raise SystemExit(f"error: --sweep values unreadable: {exc}")
    if len(xs) < 2:
        raise SystemExit("error: --sweep needs at least 2 points "
                         "(one point has no slope)")
    return name, [int(v) if float(v).is_integer() else v for v in xs]


def _safe_curve(expr):
    """#127 --predict: compile a claim like 'n^2', 'n*log(n)', 'n^1.5'
    into a callable — names n and log only, ^ means power, nothing
    else evaluates. Never touches user data; refuses anything fancier."""
    src = expr.replace("^", "**")
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as exc:
        raise SystemExit(f"error: --predict is not an expression: {exc}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in ("n", "log"):
                raise SystemExit(f"error: --predict knows only n and "
                                 f"log(), not {node.id!r}")
        elif isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name)
                    and node.func.id == "log"):
                raise SystemExit("error: --predict allows only log(...) "
                                 "calls")
        elif not isinstance(node, (ast.Expression, ast.BinOp,
                                   ast.UnaryOp, ast.Constant,
                                   ast.operator, ast.unaryop, ast.Load)):
            raise SystemExit(f"error: --predict does not allow "
                             f"{type(node).__name__}")
    code = compile(tree, "<predict>", "eval")
    import math as _math
    return lambda v: eval(code, {"__builtins__": {}},
                          {"n": v, "log": _math.log})


def _fit_loglog(xs, ys):
    """Least squares on (log x, log y): slope = the observed exponent,
    R² = how much of the variance a pure power law explains. Returns
    None when the data can't be fit (fewer than 2 positive points)."""
    import math
    pts = [(math.log(x), math.log(y))
           for x, y in zip(xs, ys) if x > 0 and y > 0]
    n = len(pts)
    if n < 2:
        return None
    sx = sum(p[0] for p in pts)
    sy = sum(p[1] for p in pts)
    sxx = sum(p[0] * p[0] for p in pts)
    sxy = sum(p[0] * p[1] for p in pts)
    den = n * sxx - sx * sx
    if den == 0:
        return None
    b = (n * sxy - sx * sy) / den
    a = (sy - b * sx) / n
    mean = sy / n
    ss_tot = sum((y - mean) ** 2 for _, y in pts)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in pts)
    return {"slope": b, "intercept": a,
            "r2": 1.0 - ss_res / ss_tot if ss_tot else 1.0}


def _claim_r2(curve, xs, ys):
    """Score a --predict claim scale-free: fit only the constant factor
    (intercept in log space), then R² of the claim's shape against the
    data. 1.0 = the claim's curve IS the data's shape. Returns
    {"r2", "scale"} or None when unscorable."""
    import math
    pts = []
    for x, y in zip(xs, ys):
        try:
            c = curve(x)
        except Exception:
            return None
        if y <= 0 or c <= 0:
            return None
        pts.append((math.log(c), math.log(y)))
    if len(pts) < 2:
        return None
    off = sum(y - c for c, y in pts) / len(pts)
    mean = sum(y for _, y in pts) / len(pts)
    ss_tot = sum((y - mean) ** 2 for _, y in pts)
    ss_res = sum((y - (c + off)) ** 2 for c, y in pts)
    return {"r2": 1.0 - ss_res / ss_tot if ss_tot else 1.0,
            "scale": math.exp(off)}


def _sweep_harness(orig_argv, sweep_spec, gen_file, predict_src,
                   sweep_seed, out, entry_label, granularity, module,
                   script):
    """#127: the scaling bench — run the target across a value ladder,
    measure EVENT COUNTS (the honest cost model: exact, deterministic,
    immune to timing noise) plus traced wall time where time is true
    (fn granularity), fit the log–log slope, and score any --predict
    claim against the measurement. Inputs come from the minimal #67
    protocol: GEN.py's gen(value, seed) returns the target's stdin
    (str or bytes); with no --gen the value itself, one per line, IS
    the stdin. Rung traces are deleted after measurement — each rung
    prints its reproduce command instead."""
    try:
        knob, values = _parse_sweep(sweep_spec)
        curve = _safe_curve(predict_src) if predict_src else None
    except SystemExit as exc:
        print(exc)
        return 2
    genfn = None
    if gen_file:
        ns = runpy.run_path(os.path.realpath(gen_file))
        genfn = ns.get("gen")
        if not callable(genfn):
            print("error: --gen file must define gen(value, seed) -> "
                  "str|bytes (the bytes become the target's stdin)")
            return 2
    stem = (module.replace(".", "_") if module is not None
            else os.path.splitext(os.path.basename(script))[0])
    if out is None:
        out = f"sweep_{stem}.html"
        k = 2
        while os.path.exists(out):
            out = f"sweep_{stem}_{k}.html"
            k += 1
    out = os.path.abspath(out)

    # child argv: the #63 stripper walk — harness flags never reach a
    # child (a child sweeping would ladder forever)
    valued = {"--out", "--root", "--export-perfetto", "--include",
              "--exclude", "--granularity", "--max-events", "--start-at",
              "--start-count", "--start-when", "--backend", "--trip",
              "--runs", "--check", "--chaos-schedule", "--sweep",
              "--gen", "--predict", "--sweep-seed", "--fsm",
              "--fsm-declare", "--memo", "--starve-ms", "--probe-reduction"}
    strip = {"--sweep", "--gen", "--predict", "--sweep-seed", "--out",
             "--granularity"}
    child_flags, i = [], 0
    while i < len(orig_argv):
        tok = orig_argv[i]
        if tok == "-m" or not tok.startswith("--"):
            child_flags.extend(orig_argv[i:])
            break
        step = 2 if tok in valued and i + 1 < len(orig_argv) else 1
        if tok not in strip:
            child_flags.extend(orig_argv[i:i + step])
        i += step
    child_flags = ["--granularity", granularity] + child_flags

    print(f"pyreplay sweep: {entry_label} · {knob} = "
          f"{', '.join(str(v) for v in values)} · {granularity} "
          f"granularity · seed {sweep_seed}"
          + ("" if gen_file else
             f" · no --gen: stdin per rung is the value itself"),
          flush=True)
    rungs, interrupted = [], False
    try:
        for v in values:
            if genfn is not None:
                try:
                    payload_in = genfn(v, sweep_seed)
                except Exception as exc:
                    rungs.append({"v": v, "status":
                                  f"gen() raised {type(exc).__name__}: "
                                  f"{exc}", "events": None, "us": None,
                                  "cmd": ""})
                    continue
                if isinstance(payload_in, str):
                    stdin_bytes = payload_in.encode()
                elif isinstance(payload_in, bytes):
                    stdin_bytes = payload_in
                else:
                    rungs.append({"v": v, "status":
                                  "gen() must return str|bytes, got "
                                  + type(payload_in).__name__,
                                  "events": None, "us": None, "cmd": ""})
                    continue
            else:
                stdin_bytes = (str(v) + "\n").encode()
            rung_path = os.path.splitext(out)[0] + f"_rung_{v}.html"
            cmd = [sys.executable, SELF, "--out", rung_path] + child_flags
            shown = " ".join([os.path.basename(sys.executable),
                              os.path.basename(SELF)] + child_flags)
            r = subprocess.run(cmd, input=stdin_bytes,
                               capture_output=True)
            rung = {"v": v, "events": None, "us": None, "status": "ok",
                    "cmd": f"echo-your-input | {shown}"}
            if not os.path.exists(rung_path):
                rung["status"] = f"no trace (exit {r.returncode})"
            else:
                try:
                    data = _extract_payload(rung_path)
                    rung["events"] = len(data.get("events", []))
                    ts = sum(e.get("ts", 0)
                             for e in data.get("events", []))
                    rung["us"] = ts if ts > 0 else None
                    if data.get("error"):
                        rung["status"] = ("crashed: "
                                          + data["error"].split(":")[0])
                    elif data.get("truncated"):
                        rung["status"] = ("truncated at the event cap "
                                          "— raise --max-events")
                except Exception as exc:
                    rung["status"] = (f"unreadable trace "
                                      f"({type(exc).__name__})")
                finally:
                    try:
                        os.remove(rung_path)
                    except OSError:
                        pass
            rungs.append(rung)
            e_txt = (f"{rung['events']:,}" if rung["events"] is not None
                     else "—")
            t_txt = (f"{rung['us'] / 1000:.1f} ms"
                     if rung["us"] else "—")
            print(f"  {knob}={v}: {e_txt} events · {t_txt}"
                  + ("" if rung["status"] == "ok"
                     else f" · {rung['status']}"), flush=True)
    except KeyboardInterrupt:
        interrupted = True
        print(f"\npyreplay: interrupted — {len(rungs)} of "
              f"{len(values)} rungs measured", flush=True)

    good = [r for r in rungs if r["status"] == "ok"
            and r["events"] and r["events"] > 0]
    xs = [r["v"] for r in good]
    fit_e = _fit_loglog(xs, [r["events"] for r in good])
    have_t = [r for r in good if r["us"]]
    fit_t = _fit_loglog([r["v"] for r in have_t],
                        [r["us"] for r in have_t])
    is_size = knob == "n" and all(
        isinstance(r["v"], int) for r in rungs)
    claim = None
    if curve is not None:
        sc = _claim_r2(curve, xs, [r["events"] for r in good])
        claim = {"src": predict_src,
                 "r2": sc["r2"] if sc else None,
                 "verdict": bool(sc and sc["r2"] >= 0.985)}
        if sc and xs:
            import math
            lo, hi = min(xs), max(xs)
            samples = []
            for i in range(41):
                x = (math.exp(math.log(lo) + (math.log(hi)
                     - math.log(lo)) * i / 40) if is_size and lo > 0
                     else lo + (hi - lo) * i / 40)
                try:
                    samples.append([x, sc["scale"] * curve(x)])
                except Exception:
                    pass
            claim["samples"] = samples

    # ---- terminal: the doubling table Sedgewick taught
    print(f"\n{knob:>10} | {'events':>12} | ratio | {'time':>10} | ratio")
    prev = None
    for r in rungs:
        e_txt = f"{r['events']:,}" if r["events"] is not None else "—"
        t_txt = f"{r['us'] / 1000:.1f} ms" if r["us"] else "—"
        re_ = rt_ = "  —"
        if prev and prev["events"] and r["events"]:
            re_ = f"{r['events'] / prev['events']:5.2f}"
        if prev and prev.get("us") and r.get("us"):
            rt_ = f"{r['us'] / prev['us']:5.2f}"
        print(f"{r['v']!s:>10} | {e_txt:>12} | {re_} | {t_txt:>10} | "
              f"{rt_}" + ("" if r["status"] == "ok"
                          else f"   ({r['status']})"))
        prev = r if r["status"] == "ok" else None
    excl = [r for r in rungs if r["status"] != "ok"]
    if excl:
        print(f"  ({len(excl)} rung(s) excluded from the fit — reasons "
              f"above; a partial ladder still fits IF >= 2 rungs stand)")
    if fit_e:
        bad = fit_e["r2"] < 0.98
        print(f"\nobserved exponent (events): {knob}^"
              f"{fit_e['slope']:.2f}  (R² {fit_e['r2']:.4f})"
              + ("  — a POOR power-law fit: this range is not a clean "
                 "power law, and the tool will not force one"
                 if bad else ""))
    if fit_t:
        print(f"observed exponent (time):   {knob}^"
              f"{fit_t['slope']:.2f}  (R² {fit_t['r2']:.4f})"
              + ("" if granularity == "fn" else ""))
    elif granularity == "line":
        print("time: line traces carry no timestamps (time under line "
              "tracing would be fiction) — events are the cost model")
    if not is_size:
        print(f"note: {knob} is a knob, not a size — the exponent is "
              f"reported for the curious, but a hardness curve (the "
              f"chart) is the honest reading")
    if claim:
        if claim["r2"] is None:
            print(f"claim {predict_src}: not scorable on this data")
        else:
            print(f"claim {predict_src}: shape R² {claim['r2']:.4f} — "
                  + ("CONSISTENT with the measurement"
                     if claim["verdict"] else "the data disagrees"
                     + (f" (measured {knob}^{fit_e['slope']:.2f})"
                        if fit_e else "")))
    print("\nhonesty: counts are Python-level EVENTS, not machine "
          "operations — constants live in the C layer; the exponent "
          "is an observation over this range, never a proof.")

    payload = {"target": entry_label, "knob": knob,
               "granularity": granularity, "seed": sweep_seed,
               "gen": os.path.basename(gen_file) if gen_file else None,
               "rungs": rungs, "fitE": fit_e, "fitT": fit_t,
               "claim": claim, "isSize": is_size,
               "interrupted": interrupted}
    template_path = os.path.join(os.path.dirname(SELF),
                                 "sweep_template.html")
    with open(template_path, encoding="utf-8") as f:
        template = f.read()
    html = template.replace("__SWEEP_DATA__",
                            json.dumps(payload).replace("</", "<\\/"))
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"report -> {out}")
    if fit_e is None:
        return 1
    return 0


_ADDR = re.compile(r"0x[0-9a-fA-F]+")


def _brief_enc(enc, cap=48):
    """One-line human summary of an encoded value for the diverge report."""
    if not isinstance(enc, dict):
        return "?"
    t = enc.get("t")
    if t in ("p", "s", "o"):
        s = str(enc.get("v"))
    elif t in ("list", "tuple", "set"):
        inner = ", ".join(_brief_enc(x, 12) for x in (enc.get("v") or [])[:6])
        s = ("[%s]" if t == "list" else "(%s)" if t == "tuple"
             else "{%s}") % inner
        if enc.get("n", 0) > 6:
            s += f" +{enc['n'] - 6}"
    elif t in ("dict", "obj"):
        inner = ", ".join(f"{p[0]}: {_brief_enc(p[1], 10)}"
                          for p in (enc.get("v") or [])[:4]
                          if isinstance(p, (list, tuple)) and len(p) == 2)
        s = "{%s}" % inner
        if enc.get("n", 0) > 4:
            s += f" +{enc['n'] - 4}"
    else:
        s = "?"
    return s if len(s) <= cap else s[:cap - 1] + "…"


def _diverge(path_a, path_b):
    """#64 v1: the first event where two traces of the same code part
    ways — reported twice, honestly. STATE divergence (same control
    path, different values: usually nearer the cause) and CONTROL
    divergence (a different line runs: the symptom). Canonicalization
    strips what differs between any two healthy runs — timestamps, and
    memory addresses inside reprs — so what remains differing is real.
    v1 aligns by identical prefix; runs that differ from event 1
    (different inputs, say) are reported as exactly that."""
    try:
        pa, pb = _extract_payload(path_a), _extract_payload(path_b)
    except Exception as exc:
        print(f"error: not a pair of pyreplay traces ({exc})")
        return 2
    if pa.get("granularity") != pb.get("granularity"):
        print(f"error: different granularities ({pa.get('granularity')} "
              f"vs {pb.get('granularity')}) — retrace one side; tokens "
              f"are not comparable across granularities")
        return 2
    if pa.get("script") != pb.get("script"):
        print(f"note: different entries ({pa.get('script')} vs "
              f"{pb.get('script')}) — comparing anyway")
    ea, eb = pa.get("events", []), pb.get("events", [])
    na, nb = os.path.basename(path_a), os.path.basename(path_b)

    def ctrl_tok(e):
        return (e.get("e"), e.get("f"), e.get("l"), e.get("fn"),
                (e.get("g") or {}).get("s"), e.get("t"), e.get("tk"))

    def state_tok(e):
        # txt/s joined 2026-08-01: the console lane (#118) is recorded
        # state too — two runs whose only difference is what they
        # PRINTED must diverge here, not read as identical (found by
        # #126: a broken relation's kept pair differed only in output)
        core = {k: e.get(k) for k in ("ch", "ret", "x", "txt", "s")
                if k in e}
        return _ADDR.sub("0xADDR", json.dumps(core, sort_keys=True))

    def first_mismatch(xs, ys):
        n = min(len(xs), len(ys))
        for i in range(n):
            if xs[i] != ys[i]:
                return i
        return None if len(xs) == len(ys) else n

    ca, cb = [ctrl_tok(e) for e in ea], [ctrl_tok(e) for e in eb]
    kc = first_mismatch(ca, cb)
    ks = first_mismatch([(c, state_tok(e)) for c, e in zip(ca, ea)],
                        [(c, state_tok(e)) for c, e in zip(cb, eb)])
    print(f"pyreplay diverge: {na} ({len(ea)} events) vs {nb} "
          f"({len(eb)} events) · {pa.get('granularity')} granularity")
    if ks is None:
        print("  identical: state and control flow agree event for "
              "event (timestamps and memory addresses excluded).")
        return 0

    def where(evs, i):
        if i >= len(evs):
            return "(run already over)"
        e = evs[i]
        gm = (e.get("g") or {}).get("s")
        kind = {"c": "call(gen)", "r": "resume", "y": "yield",
                "e": "exhaust"}.get(gm, e.get("e"))
        w = f"{kind} {e.get('f')}:{e.get('l')} in {e.get('fn')}"
        if e.get("x"):
            w += f" [{e['x'].get('t')}]"
        return w

    def src_line(p, evs, i):
        if i >= len(evs):
            return None
        e = evs[i]
        text = (p.get("sources") or {}).get(e.get("f"))
        if not text:
            return None
        lines = text.splitlines()
        return lines[e["l"] - 1].strip() if 0 < e["l"] <= len(lines) \
            else None

    print(f"  identical for the first {ks} event"
          f"{'s' if ks != 1 else ''}.")
    if ks == kc:
        print(f"  CONTROL and state diverge together at event {ks + 1}:")
    else:
        print(f"  STATE diverges first, at event {ks + 1} "
              f"(the same line runs on both sides — its values differ):")
    for name, evs, p in ((na, ea, pa), (nb, eb, pb)):
        line = src_line(p, evs, ks)
        print(f"    {name}: {where(evs, ks)}"
              + (f"  |  {line}" if line else ""))
    if ks < len(ea) and ks < len(eb) and ca[ks] == cb[ks]:
        cha, chb = ea[ks].get("ch") or {}, eb[ks].get("ch") or {}

        def canon(v):
            return _ADDR.sub("0xADDR", json.dumps(v, sort_keys=True))

        for nm in sorted(set(cha) | set(chb)):
            if canon(cha.get(nm)) != canon(chb.get(nm)):
                print(f"      {nm}:  {_brief_enc(cha.get(nm))}  vs  "
                      f"{_brief_enc(chb.get(nm))}")
    if kc is not None and kc != ks:
        print(f"  control flow follows at event {kc + 1}:")
        for name, evs, p in ((na, ea, pa), (nb, eb, pb)):
            line = src_line(p, evs, kc)
            print(f"    {name}: {where(evs, kc)}"
                  + (f"  |  {line}" if line else ""))
    elif kc is None:
        print(f"  control flow never diverges — both sides run the same "
              f"{min(len(ea), len(eb))} events through different values.")
    print(f"  open both at the divergence (deep links, #106):")
    print(f"    {os.path.abspath(path_a)}#ev={ks + 1}")
    print(f"    {os.path.abspath(path_b)}#ev={ks + 1}")
    return 1


def main(argv):
    if argv[:1] == ["--diverge"]:
        # a mode, not a flag: compares two existing traces, runs nothing
        if len(argv) != 3:
            print("usage: tracer.py --diverge A.html B.html")
            return 2
        return _diverge(argv[1], argv[2])
    if argv[:1] == ["--forensics"]:
        # #125, a mode: explain mutmut's survivors — runs from the
        # project root where `mutmut run` was executed
        return _forensics_harness(argv[1:])
    if argv[:1] == ["--mine"]:
        # #74, a mode: mine invariants across EXISTING traces — offline,
        # nothing runs. Support multiplies across the files you give it.
        if len(argv) < 2:
            print("usage: tracer.py --mine trace_a.html [trace_b.html …]")
            return 2
        payloads = []
        for path in argv[1:]:
            try:
                payloads.append(_extract_payload(path))
            except Exception as exc:
                print(f"error: unreadable trace {path}: "
                      f"{type(exc).__name__}: {exc}")
                return 2
        mined = mine_invariants(payloads,
                                min_support=2 if len(payloads) > 1 else 1)
        _mine_print(mined, len(payloads))
        side = os.path.splitext(os.path.basename(argv[1]))[0]
        side = f"mined_{side}.json"
        with open(side, "w", encoding="utf-8") as fh:
            json.dump(mined, fh, indent=1)
        print(f"sidecar -> {side}")
        return 0
    orig_argv = list(argv)   # the N-run harness re-issues these to children
    out = None
    max_events = MAX_EVENTS
    start_at = None
    start_when = None
    start_when_src = None
    start_count = 1
    include, exclude = [], []
    granularity = None   # resolved per entry mode after parsing
    perfetto = None
    backend = "settrace"
    root_opt = None
    module = None
    module_argv = []
    doctor = False
    trip = None
    runs_n = None
    black_box = False    # #103: ring-buffer flight recorder
    chaos_seed = None    # #68: schedule-fuzzing seed
    sweep_spec = None    # #127: scaling bench "n=1000,2000,4000"
    gen_file = None      # #127: minimal #67 protocol — gen(v, seed)
    predict_src = None   # #127: claimed growth, e.g. "n^2"
    sweep_seed = 1234
    mine_flag = False    # #74: --runs N --mine (multi-run mining)
    fsm_expr = None      # #132: the ONE declared state name
    fsm_declared = None  # #132: declared transitions, or None
    memo_name = None     # #134: the ONE bound memo structure
    relations = []       # #126: [{"t","r","tc","rc"}] declared symmetries
    rel_trials = None    # #126: trials per relation (default by gen)
    rel_seed = 1234
    shrink_flag = False  # #66: ddmin the piped stdin
    shrink_model = "lines"
    shrink_cap = 200
    watch_list = []      # #72: [(src, code)] watch expressions
    inv_list = []        # #73: [(src, code, names)] invariants
    check = None         # #70: compiled --check expression
    check_src = None
    chunked_opt = None   # #101: None = auto by size
    starve_ms = None     # #124: loop-starvation threshold (fn only)
    reduce_name = None   # #123: the ONE probed reduction operand list
    console = True       # #118: console lane on by default
    _chap_plug = None   # #98: the imported pytest chapter plugin
    while argv and (argv[0].startswith("--") or argv[0] == "-m"):
        if argv[0] == "-m" and len(argv) >= 2:
            # -m MODULE runs a module as __main__ (e.g. -m pytest tests/).
            # Everything after MODULE is the module's OWN argv, so stop
            # parsing tracer flags here — pytest's -x/--tb are not ours.
            module = argv[1]
            module_argv = argv[2:]
            argv = []
            break
        if argv[0] == "--doctor":
            doctor = True
            argv = argv[1:]
            continue
        if argv[0] == "--backend" and len(argv) >= 2:
            if argv[1] not in ("settrace", "monitoring"):
                print("error: --backend expects 'settrace' or 'monitoring'")
                return 2
            backend, argv = argv[1], argv[2:]
            continue
        if argv[0] == "--out" and len(argv) >= 2:
            out, argv = argv[1], argv[2:]
        elif argv[0] == "--root" and len(argv) >= 2:
            root_opt, argv = argv[1], argv[2:]
        elif argv[0] == "--export-perfetto" and len(argv) >= 2:
            perfetto, argv = argv[1], argv[2:]
        elif argv[0] == "--include" and len(argv) >= 2:
            include.append(argv[1])
            argv = argv[2:]
        elif argv[0] == "--exclude" and len(argv) >= 2:
            exclude.append(argv[1])
            argv = argv[2:]
        elif argv[0] == "--granularity" and len(argv) >= 2:
            if argv[1] not in ("line", "fn"):
                print("error: --granularity expects 'line' or 'fn'")
                return 2
            granularity, argv = argv[1], argv[2:]
        elif argv[0] == "--max-events" and len(argv) >= 2:
            if not argv[1].isdigit() or int(argv[1]) < 1:
                print("error: --max-events expects a positive integer")
                return 2
            max_events, argv = int(argv[1]), argv[2:]
        elif argv[0] == "--trip" and len(argv) >= 2:
            if argv[1] != "nan":
                print("error: --trip expects 'nan' (NaN/Inf tripwire)")
                return 2
            trip, argv = argv[1], argv[2:]
        elif argv[0] == "--invariant" and len(argv) >= 2:
            try:
                inv_code = compile(argv[1], "<invariant>", "eval")
                inv_names = sorted({n.id for n in ast.walk(
                    ast.parse(argv[1], mode="eval"))
                    if isinstance(n, ast.Name)})[:8]
            except SyntaxError as exc:
                print(f"error: --invariant is not a valid expression: "
                      f"{exc}")
                return 2
            inv_list.append((argv[1], inv_code, inv_names))
            argv = argv[2:]
        elif argv[0] == "--watch" and len(argv) >= 2:
            try:
                watch_list.append((argv[1],
                                   compile(argv[1], "<watch>", "eval")))
            except SyntaxError as exc:
                print(f"error: --watch is not a valid expression: {exc}")
                return 2
            argv = argv[2:]
        elif argv[0] == "--check" and len(argv) >= 2:
            try:
                check = compile(argv[1], "<check>", "eval")
            except SyntaxError as exc:
                print(f"error: --check is not a valid expression: {exc}")
                return 2
            check_src, argv = argv[1], argv[2:]
        elif argv[0] == "--black-box":
            black_box = True
            argv = argv[1:]
        elif argv[0] == "--chaos-schedule" and len(argv) >= 2:
            try:
                chaos_seed = int(argv[1])
            except ValueError:
                print("error: --chaos-schedule expects an integer seed "
                      "(same seed = same injected decision stream)")
                return 2
            argv = argv[2:]
        elif argv[0] == "--no-console":
            console = False
            argv = argv[1:]
        elif argv[0] == "--chunked":
            chunked_opt = True
            argv = argv[1:]
        elif argv[0] == "--no-chunked":
            chunked_opt = False
            argv = argv[1:]
        elif argv[0] == "--runs" and len(argv) >= 2:
            if not argv[1].isdigit() or int(argv[1]) < 2:
                print("error: --runs expects an integer >= 2 "
                      "(one run is an anecdote)")
                return 2
            runs_n, argv = int(argv[1]), argv[2:]
        elif argv[0] == "--sweep" and len(argv) >= 2:
            sweep_spec, argv = argv[1], argv[2:]
        elif argv[0] == "--gen" and len(argv) >= 2:
            if not os.path.isfile(argv[1]):
                print(f"error: --gen file not found: {argv[1]}")
                return 2
            gen_file, argv = argv[1], argv[2:]
        elif argv[0] == "--predict" and len(argv) >= 2:
            predict_src, argv = argv[1], argv[2:]
        elif argv[0] == "--sweep-seed" and len(argv) >= 2:
            try:
                sweep_seed = int(argv[1])
            except ValueError:
                print("error: --sweep-seed expects an integer")
                return 2
            argv = argv[2:]
        elif argv[0] == "--mine":
            mine_flag = True
            argv = argv[1:]
        elif argv[0] == "--fsm" and len(argv) >= 2:
            if fsm_expr is not None:
                print("error: --fsm binds ONE declared name — the "
                      "machine of one state variable, not a dashboard")
                return 2
            fsm_expr = argv[1]
            try:
                compile(fsm_expr, "<fsm>", "eval")
            except SyntaxError as exc:
                print(f"error: --fsm is not a valid expression: {exc}")
                return 2
            argv = argv[2:]
        elif argv[0] == "--fsm-declare" and len(argv) >= 2:
            if not os.path.isfile(argv[1]):
                print(f"error: --fsm-declare file not found: {argv[1]}")
                return 2
            try:
                fsm_declared = _parse_fsm_declare(argv[1])
            except SystemExit as exc:
                print(exc)
                return 2
            argv = argv[2:]
        elif argv[0] == "--probe-reduction" and len(argv) >= 2:
            if not argv[1].isidentifier():
                print("error: --probe-reduction expects one variable "
                      "name (the list being summed)")
                return 2
            reduce_name, argv = argv[1], argv[2:]
        elif argv[0] == "--starve-ms" and len(argv) >= 2:
            if not argv[1].isdigit() or int(argv[1]) < 1:
                print("error: --starve-ms expects a positive integer "
                      "(milliseconds)")
                return 2
            starve_ms, argv = int(argv[1]), argv[2:]
        elif argv[0] == "--memo" and len(argv) >= 2:
            if memo_name is not None:
                print("error: --memo binds ONE structure — the DAG of "
                      "one table, not a dashboard")
                return 2
            if not argv[1].isidentifier():
                print("error: --memo expects a plain name (the local/"
                      "global holding the table) — dotted paths are "
                      "not bound yet")
                return 2
            memo_name = argv[1]
            argv = argv[2:]
        elif argv[0] == "--relation" and len(argv) >= 2:
            try:
                relations.append(_parse_relation(argv[1]))
            except SystemExit as exc:
                print(exc)
                return 2
            argv = argv[2:]
        elif argv[0] == "--relation-trials" and len(argv) >= 2:
            if not argv[1].isdigit() or int(argv[1]) < 1:
                print("error: --relation-trials expects a positive "
                      "integer")
                return 2
            rel_trials, argv = int(argv[1]), argv[2:]
        elif argv[0] == "--relation-seed" and len(argv) >= 2:
            try:
                rel_seed = int(argv[1])
            except ValueError:
                print("error: --relation-seed expects an integer")
                return 2
            argv = argv[2:]
        elif argv[0] == "--shrink":
            shrink_flag = True
            argv = argv[1:]
        elif argv[0] == "--shrink-model" and len(argv) >= 2:
            if argv[1] not in ("lines", "tokens", "bytes"):
                print("error: --shrink-model is lines | tokens | bytes")
                return 2
            shrink_model, argv = argv[1], argv[2:]
        elif argv[0] == "--shrink-cap" and len(argv) >= 2:
            if not argv[1].isdigit() or int(argv[1]) < 1:
                print("error: --shrink-cap expects a positive integer")
                return 2
            shrink_cap, argv = int(argv[1]), argv[2:]
        elif argv[0] == "--start-at" and len(argv) >= 2:
            fname, _, lineno = argv[1].rpartition(":")
            if not fname or not lineno.isdigit():
                print("error: --start-at expects file.py:LINENO")
                return 2
            start_at, argv = (fname, int(lineno)), argv[2:]
        elif argv[0] == "--start-count" and len(argv) >= 2:
            if not argv[1].isdigit() or int(argv[1]) < 1:
                print("error: --start-count expects a positive integer")
                return 2
            start_count, argv = int(argv[1]), argv[2:]
        elif argv[0] == "--start-when" and len(argv) >= 2:
            try:
                start_when = compile(argv[1], "<start-when>", "eval")
            except SyntaxError as exc:
                print(f"error: --start-when is not a valid expression: {exc}")
                return 2
            start_when_src, argv = argv[1], argv[2:]
        else:
            print(__doc__)
            return 2
    if not argv and module is None:
        print(__doc__)
        return 2
    if start_count > 1 and not (start_at or start_when):
        print("error: --start-count needs --start-at and/or --start-when")
        return 2
    if granularity is None:
        # -m runs (a test suite, a module) default to fn: line-level over
        # a whole suite is the runaway-slowness trap — ~100x overhead on
        # everything the suite touches, recorded or not. An explicit
        # --granularity always wins; --start-at/--start-when need line
        # events, so triggers keep the line default even under -m.
        # --runs also defaults to fn: the harness pays every cost N times.
        if (module is not None or runs_n or black_box or sweep_spec
                or relations or shrink_flag) \
                and not (start_at or start_when):
            granularity = "fn"
            if not doctor:
                what = ("-m runs" if module is not None
                        else "--runs" if runs_n
                        else "--sweep" if sweep_spec
                        else "--relation" if relations
                        else "--shrink" if shrink_flag
                        else "--black-box")
                print(f"pyreplay: {what} default to --granularity fn "
                      "(call-level overview) — pass --granularity line "
                      "plus --include/--start-at scoping for the line "
                      "microscope", flush=True)
        else:
            granularity = "line"
    if granularity == "fn" and (start_at or start_when):
        print("error: --start-at/--start-when need line events; "
              "they can't combine with --granularity fn")
        return 2
    if trip and granularity == "fn":
        print("error: --trip nan reads variable values, which only line "
              "events record — drop --granularity fn (or scope the cost "
              "with --include instead)")
        return 2
    if watch_list and granularity == "fn":
        print("error: --watch evaluates per LINE event — drop "
              "--granularity fn (and scope the cost with --include)")
        return 2
    if inv_list and granularity == "fn":
        print("error: --invariant is checked per LINE event — drop "
              "--granularity fn (and scope the cost with --include)")
        return 2
    if runs_n and perfetto:
        print("error: --runs keeps one trace per OUTCOME, not per run — "
              "a single --export-perfetto file would be ambiguous. Run "
              "the export on a kept representative afterwards.")
        return 2
    if predict_src and not sweep_spec:
        print("error: --predict belongs to --sweep — add "
              '--sweep "n=..." (the ladder to score it on)')
        return 2
    if gen_file and not sweep_spec and not relations:
        print("error: --gen feeds --sweep (a size ladder) or "
              "--relation (metamorphic trials) — add one of them")
        return 2
    if mine_flag and not runs_n:
        print("error: --mine rides --runs (mine N runs together), or "
              "stands alone as a mode: tracer.py --mine a.html b.html "
              "— single traces mine themselves automatically.")
        return 2
    if fsm_declared is not None and fsm_expr is None:
        print("error: --fsm-declare needs --fsm EXPR (the state "
              "variable whose transitions the file declares)")
        return 2
    if fsm_expr is not None and granularity == "fn":
        print("error: --fsm observes the state per LINE event — drop "
              "--granularity fn (and scope the cost with --include)")
        return 2
    if memo_name is not None and granularity == "fn":
        print("error: --memo reconstructs indexes from LINE events — "
              "drop --granularity fn (and scope the cost with "
              "--include)")
        return 2
    if fsm_expr is not None:
        # ride the #72 watch machinery: the change stream IS the log
        if not any(src == fsm_expr for src, _ in watch_list):
            watch_list.append((fsm_expr,
                               compile(fsm_expr, "<fsm>", "eval")))
    if sweep_spec and runs_n:
        print("error: --sweep and --runs are different experiments — "
              "a ladder of sizes vs repetitions of one input. Run them "
              "separately.")
        return 2
    if sweep_spec and (perfetto or black_box):
        print("error: --sweep measures event counts and traced time — "
              "it cannot combine with --export-perfetto or --black-box "
              "(a ring buffer would corrupt the counts)")
        return 2
    if sweep_spec and chaos_seed is not None:
        print("error: --sweep under --chaos-schedule would measure the "
              "chaos, not the algorithm — run the bench unperturbed")
        return 2
    if shrink_flag and (runs_n or sweep_spec or relations):
        print("error: --shrink is its own experiment — run it without "
              "--runs/--sweep/--relation")
        return 2
    if (shrink_model != "lines" or shrink_cap != 200) \
            and not shrink_flag:
        print("error: --shrink-model/--shrink-cap belong to --shrink")
        return 2
    if relations and (runs_n or sweep_spec):
        print("error: --relation is its own experiment — run it "
              "without --runs/--sweep (they answer different "
              "questions)")
        return 2
    if relations and not console:
        print("error: --relation reads the target's output from the "
              "recorded console lane — drop --no-console")
        return 2
    if (rel_trials is not None or gen_file) and not relations \
            and not sweep_spec:
        if rel_trials is not None:
            print("error: --relation-trials belongs to --relation")
            return 2
    if backend == "monitoring":
        if MON is None:
            print("error: --backend monitoring needs Python 3.12+ "
                  "(PEP 669 sys.monitoring)")
            return 2
        # #102: line mode rides PEP 669 too — LINE events armed
        # per-code via set_local_events, so out-of-scope code costs
        # one PY_START DISABLE instead of a callback per line
    if perfetto and granularity != "fn":
        print("error: --export-perfetto needs --granularity fn — "
              "line traces carry no timestamps (wall times under "
              "line tracing would be fiction)")
        return 2
    if chaos_seed is not None and perfetto:
        print("error: --chaos-schedule perturbs the schedule on purpose "
              "— a Perfetto timeline of a perturbed run would read as "
              "timing truth. Export from an unperturbed run instead.")
        return 2

    if module is not None:
        # -m mode: the entry is a module, not a file on disk. Scope defaults
        # to the current directory (the project you're standing in) so the
        # suite's own package is traced; --root overrides it.
        script = None
        entry_label = "-m " + module
        root = os.path.realpath(root_opt or os.getcwd())
        import importlib.util
        # look for the FULL module the way the run will: root + cwd on the
        # front of the path (so a LOCAL package resolves, not just
        # site-packages ones). The full name — not just the top package —
        # so `-m pkg.missing` is refused, not run to an empty trace.
        saved, sys.path = sys.path, [root, os.path.realpath(os.getcwd())] \
            + sys.path
        try:
            found = importlib.util.find_spec(module) is not None
        except BaseException:
            found = False
        finally:
            sys.path = saved
        if not found and not doctor:
            print(f"error: -m module not importable here: {module} — is it "
                  f"installed, or on the path from --root/cwd? "
                  f"(pip install it first, or check --root — or prefix "
                  f"the command with --doctor for the full setup report)")
            return 2
    else:
        script = os.path.realpath(argv[0])
        if not os.path.isfile(script):
            print(f"error: no such file: {argv[0]}")
            return 2
        entry_label = os.path.basename(script)
        root = os.path.realpath(root_opt) if root_opt else os.path.dirname(
            script)
    if not os.path.isdir(root):
        print(f"error: --root must be an existing directory: {root_opt}")
        return 2

    if doctor:
        # report and stop — nothing runs, nothing is written
        return _doctor(module, script, root, entry_label,
                       found if module is not None else True)

    if runs_n:
        return _run_harness(orig_argv, runs_n, out, entry_label,
                            granularity, module, script, chaos_seed,
                            mine=mine_flag)

    if sweep_spec:
        return _sweep_harness(orig_argv, sweep_spec, gen_file,
                              predict_src, sweep_seed, out, entry_label,
                              granularity, module, script)

    if shrink_flag:
        return _shrink_harness(orig_argv, shrink_model, shrink_cap,
                               check is not None, entry_label,
                               granularity, module, script)

    if relations:
        return _relation_harness(
            orig_argv, relations, gen_file,
            rel_trials if rel_trials is not None
            else (3 if gen_file else 1),
            rel_seed, entry_label, granularity, module, script)

    if out is None:  # default: unique name per entry, never overwrite
        stem = (module.replace(".", "_") if module is not None
                else os.path.splitext(os.path.basename(script))[0])
        out = f"trace_{stem}.html"
        n = 2
        while os.path.exists(out):
            out = f"trace_{stem}_{n}.html"
            n += 1
    # anchor outputs to the LAUNCH cwd now, before the target runs — a
    # traced program (pytest especially) may os.chdir(), and a relative
    # path would otherwise land the trace somewhere else or lose it.
    out = os.path.abspath(out)
    if perfetto:
        perfetto = os.path.abspath(perfetto)

    # #104 Tier-1: the reproducibility capsule — everything that lets
    # anyone (future-you included) make this run happen again. Piped
    # stdin is buffered ONCE and replayed to the target, so the capsule
    # can carry a copy (first 64 KB; truncation stated); interactive
    # stdin is not captured. Env: only the curated keys — never a full
    # dump (secrets live in env).
    capsule = {
        "cmd": "python3 tracer.py " + " ".join(
            shlex.quote(a) for a in orig_argv),
        "argv": orig_argv,
        "cwd": os.getcwd(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "hashseed": os.environ.get("PYTHONHASHSEED") or "random",
        "env": {k: os.environ[k] for k in
                ("VIRTUAL_ENV", "PYTHONPATH", "PYREPLAY_HEARTBEAT")
                if k in os.environ},
        "when": datetime.datetime.now().isoformat(timespec="seconds"),
        "stdin": None, "stdinTrunc": False,
    }
    prev_stdin = None
    stdin_sink = None
    if not sys.stdin.isatty():
        # lazy tee: never pre-read (a pipe that never closes must not
        # hang the start); the capsule gets what the run CONSUMED
        stdin_sink = _StdinSink()
        prev_stdin = sys.stdin
        sys.stdin = _StdinTee(prev_stdin, stdin_sink)

    tracer = Tracer(root, max_events, start_at, start_when, start_count,
                    include, exclude, granularity, trip=trip,
                    ring=max_events if black_box else None)
    tracer.check = check
    if watch_list:
        tracer.watches = watch_list
        print(f"pyreplay: {len(watch_list)} watch expression(s) "
              "evaluated at every line event of every traced frame — "
              "they run INSIDE your process (keep them pure); scope "
              "the cost with --include", flush=True)
    if inv_list:
        tracer.invariants = inv_list
        print(f"pyreplay: {len(inv_list)} invariant(s) checked at "
              "every line event where their names are in scope — "
              "violations become events, the run continues", flush=True)
    old_switch = None
    if chaos_seed is not None:
        tracer.chaos = _Chaos(chaos_seed)
        old_switch = sys.getswitchinterval()
        sys.setswitchinterval(tracer.chaos.interval())
        tracer.chaos.hook_asyncio()
        print(f"pyreplay: CHAOS — schedule fuzzing, seed {chaos_seed}: "
              "seeded stalls/yields at traced boundaries + "
              "switch-interval jitter"
              + (" + asyncio ready-queue shuffle"
                 if tracer.chaos.asyncio_hooked
                 else " (asyncio hook unavailable)")
              + "; this run is PERTURBED on purpose", flush=True)
    if black_box:
        print(f"pyreplay: flight recorder — keeping the LAST "
              f"{max_events} events (window = --max-events); kill "
              f"-USR1 this pid for a mid-run snapshot", flush=True)
    old_argv, old_path = sys.argv, sys.path[:]
    if module is not None:
        # pytest discovers tests from its positional paths, or the CWD if it
        # was given none. When --root scopes the trace to a subtree but no
        # test target was named, point pytest at the root too — otherwise
        # `--root brian2 -m pytest` traces brian2 yet pytest still crawls the
        # whole cwd (nonsensical when sibling projects live beside it). A test
        # path or a node id (file::test) the user DID pass is left untouched.
        if module == "pytest" and not any(
                os.path.exists(a) or "::" in a for a in module_argv):
            module_argv = module_argv + [root]
        if module == "pytest":
            # #98: inject the chapter-reporting plugin — every test
            # becomes a named span. -p accepts a module name, so the
            # tracer's own directory must be importable. Importing it
            # HERE claims the sys.modules entry pytest will reuse; the
            # tracer handle rides on the module object itself (runpy
            # swaps __main__ during the run, so globals can't carry it).
            plug_dir = os.path.dirname(SELF)
            if plug_dir not in sys.path:
                sys.path.insert(0, plug_dir)
            try:
                import _pyreplay_pytest_plugin as _chap_plug
                module_argv = ["-p", "_pyreplay_pytest_plugin"] \
                    + module_argv
            except ImportError:
                _chap_plug = None
                print("pyreplay: chapter plugin not importable — the "
                      "suite runs untagged (no per-test chapters)",
                      flush=True)
        # mimic `python -m MODULE ...`: run_module(alter_sys) fixes argv[0];
        # put the scope root AND cwd on sys.path so both the project package
        # and pytest's conftest/discovery resolve.
        sys.argv = [module] + module_argv
        for p in (root, os.path.realpath(os.getcwd())):
            if p not in sys.path:
                sys.path.insert(0, p)
    else:
        sys.argv = [script] + argv[1:]
        sys.path.insert(0, root)
    if script is not None:
        miss = _missing_imports(script, root)
        if miss:
            print("pyreplay: heads-up — this entry imports module(s) not "
                  "importable here: " + ", ".join(miss) + "; the run will "
                  "likely crash at import. Install them in THIS python: "
                  "pip install " + " ".join(miss) + _venv_hint(), flush=True)
    print(f"pyreplay: tracing {entry_label} — output follows; Ctrl-C stops "
          f"it and keeps the partial trace", flush=True)
    if module is None and sys.stdin.isatty():
        print("pyreplay: if nothing happens, the script is probably waiting "
              "for stdin — type its input (end with Ctrl-D) or pipe a file: "
              f"python3 tracer.py {argv[0]} < input.txt", flush=True)

    # heartbeat: long traces used to look FROZEN — say we're alive, with a
    # number that moves. stderr, so a piped target stdout stays clean.
    # PYREPLAY_HEARTBEAT=seconds tunes the interval; 0 disables it.
    try:
        hb_every = float(os.environ.get("PYREPLAY_HEARTBEAT", "30"))
    except ValueError:
        hb_every = 30.0
    hb_stop = threading.Event()
    if hb_every > 0:
        hb_t0 = time.time()

        def _beat():
            while not hb_stop.wait(hb_every):
                print(f"pyreplay: still tracing — "
                      f"{int(time.time() - hb_t0)}s, "
                      f"{len(tracer.events):,} events recorded "
                      f"(Ctrl-C stops and keeps the partial)",
                      file=_RAW["err"], flush=True)
        threading.Thread(target=_beat, daemon=True).start()

    # #88: hooks go in AFTER the tracer's own heartbeat thread started —
    # the tracer's machinery must never appear as a wake edge
    hb_undo = _install_hb_hooks(tracer)
    error = None
    mon = None
    if backend == "monitoring":
        mon = MonitoringBackend(tracer,
                                line_mode=(granularity == "line"))
        mon.start()   # process-wide: covers every thread by itself
    else:
        threading.settrace(tracer)  # threads started by the target too
        sys.settrace(tracer)
    if _chap_plug is not None:
        _chap_plug._ACTIVE_TRACER = tracer   # #98 handoff
    old_usr1 = None
    snap_n = 0
    if black_box and hasattr(signal, "SIGUSR1"):
        def _snap_dump(signum, frm):
            # #103: dump the ring as a normal trace WITHOUT stopping —
            # the tracer's own prints must bypass the console tee
            nonlocal snap_n
            snap_n += 1
            tracer.resolve_hb()   # #88: bind labels known so far
            shim = types.SimpleNamespace(
                events=list(tracer.events), sources=dict(tracer.sources),
                truncated=False, abort_on_cap=True,
                max_events=tracer.ring, armed=tracer.armed,
                trip=tracer.trip)
            spath = f"{os.path.splitext(out)[0]}_snap{snap_n}.html"
            saved_out = sys.stdout
            sys.stdout = _RAW["out"]
            try:
                _write_trace(shim, spath, granularity,
                             entry_label + " [SIGUSR1 snapshot]", None,
                             extra={"ring": {"size": tracer.ring,
                                             "dropped":
                                             tracer.events.dropped},
                                    "chaos": tracer.chaos.report()
                                    if tracer.chaos else None,
                                    "capsule": capsule})
                print(f"pyreplay: snapshot -> {spath}",
                      file=_RAW["err"], flush=True)
            except Exception as exc:
                print(f"pyreplay: snapshot failed: {exc}",
                      file=_RAW["err"], flush=True)
            finally:
                sys.stdout = saved_out
        old_usr1 = signal.signal(signal.SIGUSR1, _snap_dump)

    tees = None
    if console:
        # #118: the console lane — every stdout/stderr LINE the target
        # writes becomes an event tied to its emitting frame. Output
        # still reaches the real terminal; --no-console disables.
        sys.stdout = _ConsoleTee(sys.stdout, tracer, "out")
        sys.stderr = _ConsoleTee(sys.stderr, tracer, "err")
        tees = (sys.stdout, sys.stderr)
    try:
        # run_path/run_module execute the entry as __main__, so a script's
        # own `if __name__ == "__main__":` block — or a module like pytest —
        # runs exactly as `python <script>` / `python -m <module>` would.
        if module is not None:
            runpy.run_module(module, run_name="__main__", alter_sys=True)
        else:
            runpy.run_path(script, run_name="__main__")
    except TraceLimitReached:
        pass  # cap reached; the recorded trace is intact
    except SystemExit as exc:
        if exc.code not in (None, 0):
            error = f"SystemExit: {exc.code}"
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        hb_stop.set()
        if _chap_plug is not None:
            _chap_plug._ACTIVE_TRACER = None
        if mon is not None:
            mon.stop()
        else:
            sys.settrace(None)
            threading.settrace(None)
        sys.argv = old_argv
        sys.path[:] = old_path
        if prev_stdin is not None:
            sys.stdin = prev_stdin
        if tees is not None:
            tees[0].tail()
            tees[1].tail()
            sys.stdout = tees[0]._real
            sys.stderr = tees[1]._real
        if old_usr1 is not None:
            signal.signal(signal.SIGUSR1, old_usr1)
        if tracer.chaos is not None:
            tracer.chaos.unhook()
        if old_switch is not None:
            sys.setswitchinterval(old_switch)
        for u in hb_undo:
            u()

    ring_info = None
    if black_box:
        ring_info = {"size": tracer.ring,
                     "dropped": tracer.events.dropped}
        tracer.events = list(tracer.events)   # deques don't slice/dump

    trigger_desc = None
    if start_at or start_when:
        parts = []
        if start_at:
            parts.append(f"{start_at[0]}:{start_at[1]}")
        if start_when_src:
            parts.append(f"when {start_when_src}")
        if start_count > 1:
            parts.append(f"hit #{start_count}")
        trigger_desc = ", ".join(parts)

    # #98: chapters recorded by the pytest plugin -> summary + the
    # per-test SBFL join, embedded in the trace and echoed to stdout
    if stdin_sink is not None and stdin_sink.total:
        capsule["stdin"] = base64.b64encode(
            bytes(stdin_sink.data)).decode("ascii")
        capsule["stdinTrunc"] = stdin_sink.total > len(stdin_sink.data)
    tracer.resolve_hb()   # #88: idents -> lane labels
    for wsrc, _unused in watch_list:
        if not tracer.watch_hits.get(wsrc):
            print(f"pyreplay: watch [{wsrc}] was never evaluable "
                  f"anywhere — probably a typo (it recorded nothing; "
                  f"a wrong name must never look like data)", flush=True)
    for isrc, _c, _n in inv_list:
        nviol = tracer.inv_counts.get(isrc, 0)
        if not tracer.inv_evals.get(isrc):
            print(f"pyreplay: invariant [{isrc}] was never evaluable "
                  f"anywhere — probably a typo (it was checked "
                  f"nowhere)", flush=True)
        elif nviol:
            print(f"invariant [{isrc}]: VIOLATED {nviol}x — first at "
                  f"event {tracer.inv_first[isrc] + 1}", flush=True)
        else:
            print(f"invariant [{isrc}]: held everywhere it was "
                  f"evaluable", flush=True)
    bounds = _boundaries(tracer.events)
    extra = {"capsule": capsule,
             "ring": ring_info,
             "chaos": tracer.chaos.report() if tracer.chaos else None,
             "critical": _critical_path(tracer.events)
             if granularity == "fn" else None,
             "invariants": [{"src": s,
                             "n": tracer.inv_counts.get(s, 0),
                             "first": tracer.inv_first.get(s),
                             "evals": tracer.inv_evals.get(s, 0)}
                            for s, _c, _n in inv_list] or None,
             "boundaries": bounds or None,
             "logCapped": tracer.log_capped or None}
    tsum, tsusp = _chapter_suspicion(tracer.events, granularity)
    if tsum:
        extra.update({"tests": tsum, "testSuspicion": tsusp})
        line = (f"tests: {tsum['tests']} — {tsum['passed']} passed"
                + (f", {tsum['failed']} failed" if tsum["failed"] else "")
                + (f", {tsum['other']} errored" if tsum["other"] else "")
                + (f", {tsum['skipped']} skipped"
                   if tsum["skipped"] else ""))
        print(line)
        if tsusp and tsusp["top"]:
            u = "lines" if tsusp["unit"] == "line" \
                else "call/return/raise lines (fn granularity)"
            print(f"suspicion — Ochiai over {u}, {tsusp['pass']} passing "
                  f"/ {tsusp['fail']} failing tests "
                  f"(correlation, not causation):")
            for row in tsusp["top"][:5]:
                src = None
                text = tracer.sources.get(row["f"])
                if text:
                    ls = text.splitlines()
                    if 0 < row["l"] <= len(ls):
                        src = ls[row["l"] - 1].strip()[:80]
                print(f"    {row['score']:.2f}  {row['f']}:{row['l']}"
                      + (f"  {src}" if src else ""))
    if backend == "monitoring" and granularity == "line":
        # #102 honesty: PEP 709 inlines comprehensions; PEP 669 fires
        # LINE once per line transition — iteration variables inside a
        # comprehension are not re-observed by this engine
        comp_lines = 0
        for text in tracer.sources.values():
            try:
                t2 = ast.parse(text)
            except SyntaxError:
                continue
            comp_lines += sum(1 for nd in ast.walk(t2)
                              if isinstance(nd, (ast.ListComp,
                                                 ast.SetComp,
                                                 ast.DictComp,
                                                 ast.GeneratorExp)))
        extra = dict(extra or {})
        extra["engine"] = "monitoring"
        extra["monComp"] = comp_lines
        if comp_lines:
            print(f"engine note: {comp_lines} comprehension(s) in "
                  f"scope — under sys.monitoring an inlined "
                  f"comprehension runs within ONE line event; its "
                  f"per-iteration variables are not re-observed "
                  f"(settrace shows every iteration)")
    _write_trace(tracer, out, granularity, entry_label, error,
                 trigger_desc, extra=extra, chunked=chunked_opt,
                 fsm=(fsm_expr, fsm_declared) if fsm_expr else None,
                 memo=memo_name, starve_ms=starve_ms,
                 reduce_name=reduce_name)
    unstable = []
    for key, b in (bounds or {}).items():
        spots = [(n, d) for n, d in b["args"].items() if len(d) > 1]
        if len(b["ret"]) > 1:
            spots.append(("return", b["ret"]))
        for n, d in spots:
            dist = " / ".join(f"{sh} {c}x" for sh, (c, _)
                              in sorted(d.items(), key=lambda kv:
                                        -kv[1][0]))
            unstable.append(f"  {key} — {n}: {dist}")
    if unstable:
        print(f"boundary instability — {len(unstable)} unstable "
              f"interface(s) (shapes observed, not declared):")
        for line in unstable[:8]:
            print(line)
    if check is not None:
        # #70: the end-of-run facts — an expression over these (or a
        # per-line state test above, or both) decides the exit code,
        # which is exactly what `git bisect run` consumes
        ns = {"error": error,
              "exc": (error or "").split(":")[0],
              "events": len(tracer.events),
              "output": "\n".join(e.get("txt", "") for e in tracer.events
                                  if e.get("e") == "log"),
              "hit": tracer.check_hit,
              "hits": tracer.check_hits,
              "tests_failed": (tsum or {}).get("failed", 0)
              + (tsum or {}).get("other", 0),
              "truncated": tracer.truncated}
        end_res = None
        try:
            end_res = bool(eval(check, {"__builtins__": {}}, ns))
        except Exception:
            end_res = None      # a state-only expression: line hits decide
        if tracer.check_hit or end_res:
            where = (f" — first at event {tracer.check_first + 1}"
                     if tracer.check_hit and tracer.check_first is not None
                     else "")
            print(f"check [{check_src}]: HIT{where} (exit 1)")
            return 1
        if end_res is None and tracer.check_evals == 0:
            print(f"check [{check_src}]: never evaluable — neither as "
                  f"per-line state nor over the run facts (error/exc/"
                  f"events/output/hit/hits/tests_failed/truncated). "
                  f"Probably a typo (exit 3).")
            return 3
        print(f"check [{check_src}]: clean (exit 0)")
        return 0
    if perfetto:
        slices, nlanes, stray, unclosed = export_perfetto(
            tracer.events, entry_label, perfetto)
        print(f"perfetto: {slices} slices on {nlanes} lane(s) -> {perfetto}"
              f" — open it at https://ui.perfetto.dev")
        if stray:
            print(f"note: {stray} return(s) had no recorded call "
                  f"(frame predates the trace) — skipped")
        if unclosed:
            print(f"note: {unclosed} frame(s) still live at trace end — "
                  f"their slices were closed at the final timestamp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
