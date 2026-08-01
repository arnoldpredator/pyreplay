#!/usr/bin/env python3
"""pyreplay tracer — record a Python run and emit a self-contained HTML replayer.

Usage:
    python tracer.py <script.py> [script args...]
    python tracer.py --out mytrace.html --max-events 1000000 <script.py> [args...]

Output defaults to trace_<scriptname>.html in the current directory; if
that exists, trace_<scriptname>_2.html and so on — nothing is ever
overwritten. Use --out NAME.html to pick a name (that one DOES overwrite).
    python tracer.py --granularity fn --export-perfetto out.json <script.py>
    python tracer.py --granularity fn --backend monitoring <script.py>  # 3.12+
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
import datetime
import dis
import fnmatch
import gzip
import io
import json
import os
import platform
import re
import reprlib
import runpy
import shlex
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
                return {"t": "obj", "c": cls, "n": len(attrs), "v": pairs}
        return {"t": "o", "c": cls, "v": safe_repr(value)}
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
                 exclude=None, granularity="line", trip=None):
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
        self._hits = 0
        self._last_ts = time.perf_counter_ns() // 1000
        self._gen_ids = {}    # id(frame) -> generator instance number
        self._gen_next = 0
        self._func_cache = {} # code -> function object (or None)
        self._task_fn = None  # (_get_running_loop, current_task), lazy
        self._tk_pin = {}     # id(frame) -> lane pinned at trigger time
        self._tlabels = {}    # thread ident -> (thread obj, display name)
        self._tcounts = {}    # thread name -> how many threads used it
        # False = watching but not recording
        self.armed = start_at is None and start_when is None
        self.events = []       # the event log — the backend/frontend contract
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
            if self.armed:
                self._record(frame, "call", arg)
            return self  # keep watching for the trigger even when not armed
        if self.granularity == "fn":
            if event in ("return", "exception") and not self.truncated:
                self._record_fn(frame, event, arg)
            return self
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
        for name, value in frame.f_locals.items():
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


MON = getattr(sys, "monitoring", None)   # PEP 669, Python 3.12+


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

    def __init__(self, tracer):
        self.t = tracer
        self.tool = None
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
        try:
            mask = 0
            for ev, fn in self._callbacks:
                MON.register_callback(self.tool, ev, fn)
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

    def _start(self, code, off):
        if self._skip(code):
            return MON.DISABLE   # this location never fires again
        self.t._record_fn(sys._getframe(1), "call", None)

    def _resume(self, code, off):
        if self._skip(code):
            return MON.DISABLE
        self.t._record_fn(sys._getframe(1), "call", None)

    def _throw(self, code, off, exc):
        if not self._skip(code):   # throw events can't be DISABLEd
            self.t._record_fn(sys._getframe(1), "call", None)

    def _return(self, code, off, retval):
        if self._skip(code):
            return MON.DISABLE
        self.t._record_fn(sys._getframe(1), "return", retval,
                          yielding=False)

    def _yield(self, code, off, retval):
        if self._skip(code):
            return MON.DISABLE
        self.t._record_fn(sys._getframe(1), "return", retval,
                          yielding=True)

    def _raise(self, code, off, exc):
        # a genuinely NEW exception being raised here — always an event
        # (a distinct exc object; RAISE never fires twice for one raise)
        if self._skip(code):
            return
        frame = sys._getframe(1)
        self._mark = (id(frame), id(exc))
        self.t._record_fn(frame, "exception", (type(exc), exc, None))

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
            self.t._record_fn(frame, "exception", (type(exc), exc, None))

    def _unwind(self, code, off, exc):
        # exceptional exit: settrace shows exception-then-return in
        # EVERY frame the exception kills — replicate exactly (the
        # raising frame already recorded its exc via _raise)
        if self._skip(code):
            return
        frame = sys._getframe(1)
        if self._mark != (id(frame), id(exc)):
            self.t._record_fn(frame, "exception", (type(exc), exc, None))
        # yielding=None (not False): a generator killed while suspended at
        # a yield must be tagged by the same bytecode inference settrace
        # uses, or its lifecycle scope reads "e" where settrace says "y".
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
        self.t._record_fn(frame, "exception", (type(exc), exc, None))

    def _handled(self, code, off, exc):
        # the frame that CATCHES a propagated exception gets an exc
        # event under settrace; locally-caught ones already recorded
        if self._skip(code):
            return
        frame = sys._getframe(1)
        if self._mark != (id(frame), id(exc)):
            self._mark = (id(frame), id(exc))
            self.t._record_fn(frame, "exception", (type(exc), exc, None))


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
    open_b = {}    # tid -> names of B slices not yet closed by an E
    stray = 0      # returns whose call predates the trace: skipped
    acc = 0

    def brief(enc):
        """One-line display string from a structured encoding."""
        if not isinstance(enc, dict):
            return "?"
        if enc.get("t") in ("p", "s", "o"):
            return str(enc.get("v", ""))
        return f"<{enc.get('c') or enc.get('t')} · {enc.get('n', '?')} items>"

    for ev in events:
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
            tevs.append(e)
            open_b.setdefault(tid, []).append(ev["fn"])
        elif kind == "return":
            st = open_b.get(tid)
            if not st:
                stray += 1
                continue
            e = {"ph": "E", "name": st.pop(), "ts": acc, "pid": 1,
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
            tevs.append({"ph": "E", "name": st.pop(), "ts": acc, "pid": 1,
                         "tid": tid,
                         "args": {"(unclosed)": "frame still live when "
                                                "the trace ended"}})
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
                 trigger_desc=None, extra=None, chunked=None):
    """Build the payload and write the self-contained replayer HTML —
    shared by the CLI run and the in-process watch() bracket, so both
    honor the same contract (line-only linevars/dataflow, the </ escape,
    honest truncation notes)."""
    if granularity == "line":
        annotate_conditionals(tr.events, tr.sources)
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
        "events": tr.events,
        "truncated": tr.truncated,
        "error": error,
        "startAt": trigger_desc,
        "trip": getattr(tr, "trip", None),
    }
    if extra:
        payload.update(extra)
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
                 once=True, trip=None):
        if callable(out):
            raise TypeError("use @watch() with parentheses, not @watch")
        if granularity not in ("line", "fn"):
            raise ValueError("granularity must be 'line' or 'fn'")
        if trip and granularity == "fn":
            raise ValueError("trip='nan' needs line granularity "
                             "(variable values live in line events)")
        self.out = out
        self.trip = trip
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
                          granularity=self.granularity, trip=self.trip)
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
                     extra={"capsule": capsule})
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


def _run_harness(orig_argv, n_runs, out, entry_label, granularity,
                 module, script):
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
              "--runs"}
    strip = {"--runs", "--out", "--granularity"}
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

    # the measurement protocol: every run gets the SAME stdin bytes
    stdin_bytes = b""
    if not sys.stdin.isatty():
        try:
            stdin_bytes = sys.stdin.buffer.read()
        except Exception:
            stdin_bytes = b""

    shown = " ".join([os.path.basename(sys.executable),
                      os.path.basename(SELF)] + child_flags)
    print(f"pyreplay: {n_runs} runs of {entry_label} ({granularity} "
          f"granularity), identical stdin each run", flush=True)
    per_run, seen_cls, interrupted = [], set(), False
    # #65 SBFL: per-run coverage survives the trace deletion — the set
    # of (file, line) pairs each run touched, split by outcome
    cov_fail, cov_pass = {}, {}
    n_fail_cov = n_pass_cov = 0
    try:
        for i in range(1, n_runs + 1):
            tr_path = f"{rep_base}_run{i}.html"
            cmd = [sys.executable, SELF, "--out", tr_path] + child_flags
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

    payload = {"script": entry_label, "requested": n_runs,
               "granularity": granularity,
               "python": sys.version.split()[0],
               "cmd": shown,   # child_flags already ends with the target
               "interrupted": interrupted,
               "suspicion": suspicion,
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
    print(f"report -> {out}")
    return 0 if set(counts) == {"clean"} else 1


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
        core = {k: e.get(k) for k in ("ch", "ret", "x") if k in e}
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
    chunked_opt = None   # #101: None = auto by size
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
        if (module is not None or runs_n) and not (start_at or start_when):
            granularity = "fn"
            if not doctor:
                what = "-m runs" if module is not None else "--runs"
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
    if runs_n and perfetto:
        print("error: --runs keeps one trace per OUTCOME, not per run — "
              "a single --export-perfetto file would be ambiguous. Run "
              "the export on a kept representative afterwards.")
        return 2
    if backend == "monitoring":
        if MON is None:
            print("error: --backend monitoring needs Python 3.12+ "
                  "(PEP 669 sys.monitoring)")
            return 2
        if granularity != "fn":
            print("error: --backend monitoring records call-level events "
                  "only — combine it with --granularity fn (line-level "
                  "tracing keeps the classic settrace engine)")
            return 2
    if perfetto and granularity != "fn":
        print("error: --export-perfetto needs --granularity fn — "
              "line traces carry no timestamps (wall times under "
              "line tracing would be fiction)")
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
                            granularity, module, script)

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
                    include, exclude, granularity, trip=trip)
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

    error = None
    mon = None
    if backend == "monitoring":
        mon = MonitoringBackend(tracer)
        mon.start()   # process-wide: covers every thread by itself
    else:
        threading.settrace(tracer)  # threads started by the target too
        sys.settrace(tracer)
    if _chap_plug is not None:
        _chap_plug._ACTIVE_TRACER = tracer   # #98 handoff
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
    extra = {"capsule": capsule,
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
    _write_trace(tracer, out, granularity, entry_label, error,
                 trigger_desc, extra=extra, chunked=chunked_opt)
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
