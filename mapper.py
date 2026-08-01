#!/usr/bin/env python3
"""pyreplay mapper — static import/call map of a Python codebase.

Usage:
    python3 mapper.py <directory-or-file> [--out NAME.html]
    python3 mapper.py --trace a.html --trace b.html <dir>   # heat from BOTH

With no --trace, auto-heat aggregates EVERY matching trace_*.html it finds
for this codebase, so the color reflects several runs (a sim, some tests)
rather than one narrow workload. --trace FILE (repeatable) picks specific
ones; --no-trace disables it.

Parses every .py file with the ast module (nothing is executed), builds
the internal import graph, the definition inventory (functions, classes,
methods) and a best-effort static call graph, then writes a
self-contained zoomable HTML map (map_<name>.html, never overwriting).

This is the wide, cheap end of the diagnosis funnel: run it FIRST on an
unknown codebase to learn the geography, then aim tracer.py at the
region that matters.
"""
import ast
import base64
import gzip
import bisect
import fnmatch
import importlib.util
import json
import os
import re
import sys


def scope_ok(rel, include, exclude):
    """Same scoping vocabulary as the tracer: globs matched against the
    project-relative path and the bare filename."""
    base = os.path.basename(rel)
    if include and not any(fnmatch.fnmatch(rel, p) or
                           fnmatch.fnmatch(base, p) for p in include):
        return False
    if exclude and any(fnmatch.fnmatch(rel, p) or
                       fnmatch.fnmatch(base, p) for p in exclude):
        return False
    return True

SKIP_DIRS = {"__pycache__", ".git", ".hg", ".svn", ".venv", "venv", "env",
             "node_modules", "site-packages", ".tox", ".mypy_cache",
             ".pytest_cache", "build", "dist", ".idea", ".vscode", ".eggs"}


def find_py_files(root):
    if os.path.isfile(root):
        return [root]
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not d.startswith("."))
        for f in sorted(filenames):
            if f.endswith(".py"):
                out.append(os.path.join(dirpath, f))
    return out


def module_name(path, root_dir):
    rel = os.path.relpath(path, root_dir)
    parts = rel[:-3].split(os.sep)          # strip ".py"
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else "__root__"


class ModuleScan(ast.NodeVisitor):
    """One file: imports (resolved against the codebase), definitions,
    and statically-resolvable calls. Method calls on objects are not
    resolvable without running the code — they are counted honestly."""

    def __init__(self, mod, is_pkg, internal):
        self.mod = mod
        self.is_pkg = is_pkg
        self.internal = internal
        self.imports = set()     # internal module ids this module imports
        self.external = set()    # external top-level package names
        self.aliases = {}        # local name -> ("mod", id) | ("func", id, name)
        self.defs = []
        self.calls = []          # (src_def|None, dst_mod|None, dst_name|None)
        self.unresolved = 0      # calls static analysis cannot attribute
        self._scope = []
        self._bound = [set()]    # names bound per scope ([0] = module),
                                 # so a nested def can't be mistaken for a
                                 # top-level function of the same name

    def _resolve(self, dotted):
        parts = dotted.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            if cand in self.internal:
                return cand
        return None

    # ---- imports ----
    def visit_Import(self, node):
        for a in node.names:
            tgt = self._resolve(a.name)
            if tgt is not None:
                self.imports.add(tgt)
                if a.asname:
                    self.aliases[a.asname] = ("mod", tgt)
                else:
                    top = self._resolve(a.name.split(".")[0])
                    if top is not None:
                        self.aliases[a.name.split(".")[0]] = ("mod", top)
            else:
                self.external.add(a.name.split(".")[0])

    def visit_ImportFrom(self, node):
        if node.level:   # relative import: anchor at the current package
            base = self.mod.split(".") if self.is_pkg \
                else self.mod.split(".")[:-1]
            if base == ["__root__"]:
                base = []
            up = node.level - 1
            if up > len(base):
                return   # climbs OUT of the mapped root — the target is
                         # unknowable; re-anchoring it at the root would
                         # fabricate an edge that does not exist
            base = base[:len(base) - up]
            target = ".".join(base + (node.module.split(".")
                                      if node.module else []))
            if not target:
                # "from . import x" at the mapped root: names ARE modules
                prefix = ".".join(base)
                for a in node.names:
                    cand = (prefix + "." if prefix else "") + a.name
                    tgt = self._resolve(cand)
                    if tgt is not None:
                        self.imports.add(tgt)
                        self.aliases[a.asname or a.name] = ("mod", tgt)
                return
        else:
            target = node.module or ""
        tgt = self._resolve(target) if target else None
        if tgt is None:
            if target:
                # the package part may be unresolvable while the full
                # dotted name IS internal: namespace packages (PEP 420,
                # no __init__.py) and --include filters that drop the
                # __init__ but keep members — resolve per name before
                # declaring anything external
                hit = False
                for a in node.names:
                    sub = self._resolve(target + "." + a.name)
                    if sub is not None:
                        self.imports.add(sub)
                        self.aliases[a.asname or a.name] = ("mod", sub)
                        hit = True
                if not hit:
                    self.external.add(target.split(".")[0])
            return
        self.imports.add(tgt)
        for a in node.names:
            sub = tgt + "." + a.name
            if sub in self.internal:      # "from pkg import submodule"
                self.imports.add(sub)
                self.aliases[a.asname or a.name] = ("mod", sub)
            else:
                self.aliases[a.asname or a.name] = ("func", tgt, a.name)

    # ---- definitions ----
    def _def(self, node, kind):
        name = ".".join(self._scope + [node.name]) if self._scope \
            else node.name
        loc = getattr(node, "end_lineno", node.lineno) - node.lineno + 1
        self.defs.append({"n": name, "l": node.lineno, "loc": loc,
                          "k": kind})
        if self._bound:
            self._bound[-1].add(node.name)   # the def binds its name here
        # decorators, argument defaults and annotations execute at
        # DEFINITION time in the ENCLOSING scope — NOT in the body. Visit
        # them before pushing the function's own scope so their calls
        # (@app.route(...), x=get_logger(), field(default_factory=...))
        # are attributed to where they really run, not to this function.
        for dec in node.decorator_list:
            self.visit(dec)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)
        self._scope.append(node.name)
        self._bound.append(set())
        for stmt in node.body:
            self.visit(stmt)
        self._bound.pop()
        self._scope.pop()

    def visit_FunctionDef(self, node):
        self._def(node, "def")

    def visit_AsyncFunctionDef(self, node):
        self._def(node, "def")

    def _base_label(self, b):
        """Readable label for a base class expression; resolves imported
        names to "module.Class" where the import is internal."""
        if isinstance(b, ast.Subscript):     # Generic[T] etc.
            b = b.value
        if isinstance(b, ast.Name):
            a = self.aliases.get(b.id)
            if a is not None and a[0] == "func":
                return a[1] + "." + a[2]
            return b.id
        if isinstance(b, ast.Attribute):
            chain, cur = [], b
            while isinstance(cur, ast.Attribute):
                chain.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                chain.append(cur.id)
                return ".".join(reversed(chain))
        return None

    def visit_ClassDef(self, node):
        name = ".".join(self._scope + [node.name]) if self._scope \
            else node.name
        loc = getattr(node, "end_lineno", node.lineno) - node.lineno + 1
        entry = {"n": name, "l": node.lineno, "loc": loc, "k": "class"}
        bases = [lbl for lbl in (self._base_label(b) for b in node.bases)
                 if lbl]
        if bases:
            entry["bases"] = bases
        self.defs.append(entry)
        if self._bound:
            self._bound[-1].add(node.name)
        # base classes, keywords and decorators run at definition time in
        # the ENCLOSING scope; only the body runs in the class scope
        for dec in node.decorator_list:
            self.visit(dec)
        for b in node.bases:
            self.visit(b)
        for kw in node.keywords:
            self.visit(kw)
        self._scope.append(node.name)
        self._bound.append(set())
        for stmt in node.body:
            self.visit(stmt)
        self._bound.pop()
        self._scope.pop()

    # ---- calls ----
    def visit_Call(self, node):
        src = ".".join(self._scope) if self._scope else None
        f = node.func
        if isinstance(f, ast.Name):
            a = self.aliases.get(f.id)
            if a is not None and a[0] == "func":
                self.calls.append((src, a[1], a[2]))
            elif a is not None and a[0] == "mod":
                self.calls.append((src, a[1], None))
            elif any(f.id in s for s in self._bound[1:]):
                # a nested/local def of this name shadows any top-level
                # function of the same name: the call is to the local one,
                # so don't (mis)resolve it as a module-function edge
                self.unresolved += 1
            else:
                # maybe a local def — resolved after the scan; else builtin
                self.calls.append((src, None, f.id))
        elif isinstance(f, ast.Attribute):
            chain = []
            cur = f
            while isinstance(cur, ast.Attribute):
                chain.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                chain.append(cur.id)
                chain.reverse()
                a = self.aliases.get(chain[0])
                if a is not None and a[0] == "mod":
                    dotted = a[1] + "." + ".".join(chain[1:])
                    tgt = self._resolve(dotted)
                    if tgt is not None and len(dotted) > len(tgt):
                        self.calls.append((src, tgt, dotted[len(tgt) + 1:]))
                    elif tgt is not None:
                        self.calls.append((src, tgt, None))
                    else:
                        self.calls.append((src, a[1], ".".join(chain[1:])))
                else:
                    self.unresolved += 1   # obj.method(): needs runtime
            else:
                self.unresolved += 1
        else:
            self.unresolved += 1
        self.generic_visit(node)


def parent_pkg(mod, path):
    """The package box a module belongs to: its containing package —
    except a package's own __init__, which belongs to ITSELF (the
    __init__ file lives inside the box it names). Top level = ""."""
    if os.path.basename(path) == "__init__.py":
        return mod
    head, _, _ = mod.rpartition(".")
    return head


def find_cycles(module_ids, imports):
    """Import cycles = strongly connected components (size ≥ 2) of the
    internal import graph. Iterative Tarjan — no recursion-limit risk
    on big codebases; members and components sorted for stable output."""
    adj = {m: [] for m in module_ids}
    for e in imports:
        if e["s"] in adj and e["d"] in adj:
            adj[e["s"]].append(e["d"])
    index, low, onstack = {}, {}, set()
    stack, sccs, counter = [], [], 0
    for root in sorted(adj):
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        onstack.add(root)
        work = [(root, iter(adj[root]))]
        while work:
            node, it = work[-1]
            pushed = False
            for child in it:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    onstack.add(child)
                    work.append((child, iter(adj[child])))
                    pushed = True
                    break
                if child in onstack:
                    low[node] = min(low[node], index[child])
            if pushed:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    onstack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                if len(comp) > 1:
                    sccs.append(sorted(comp))
    return sorted(sccs)


def has_main_guard(tree):
    """True when the module can RUN ITSELF: a top-level
    `if __name__ == "__main__":` block — statically visible, so the
    funnel handoff can emit a complete command with no trace needed."""
    for node in tree.body:
        if isinstance(node, ast.If):
            t = node.test
            if (isinstance(t, ast.Compare) and len(t.ops) == 1
                    and isinstance(t.ops[0], ast.Eq)
                    and any(isinstance(x, ast.Name) and x.id == "__name__"
                            for x in [t.left] + list(t.comparators))):
                return True
    return False


def find_matching_traces(root_dir, modules, cap=6):
    """Auto-heat: when no --trace is given, find ALL trace_*.html (cwd +
    mapped root) whose traced files belong to THIS codebase — newest
    first, up to `cap` — and adopt them TOGETHER. Aggregating several runs
    paints a fuller, less workload-biased picture than any single trace
    (one unit test over-weights import; a sim over-weights its own path).
    Overridable with --trace FILE (repeatable), refusable with --no-trace.
    Matching is by traced source paths against the map's module paths
    (suffix-aware, but a bare filename like main.py never matches across
    codebases)."""
    cands = []
    for d in {os.getcwd(), root_dir}:
        try:
            for f in os.listdir(d):
                if f.startswith("trace_") and f.endswith(".html"):
                    p = os.path.join(d, f)
                    try:
                        if os.path.getsize(p) < 256 * 1024 * 1024:
                            cands.append((os.path.getmtime(p), p))
                    except OSError:
                        pass
        except OSError:
            pass
    paths = {m["path"] for m in modules}
    # only aggregate genuinely BROAD runs: a --include microscope (1-2
    # modules) or a near-empty dud would swamp the color if summed in, so
    # require a trace to touch a meaningful slice of the map (~5%, floor 2).
    min_mods = max(2, len(modules) // 20)
    matches = []
    for _, p in sorted(cands, reverse=True)[:12]:   # newest first, bounded
        try:
            with open(p, encoding="utf-8") as fh:
                html = fh.read()
            m = re.search(r'<script id="trace-data" '
                          r'type="application/json">(.*?)</script>',
                          html, re.S)
            if m is None:
                continue   # not a trace (a map, or something else)
            pl = json.loads(m.group(1).replace("<\\/", "</"))
            if pl.get("chaos"):
                # #68: a schedule-chaos run is PERTURBED on purpose —
                # auto-adoption must never mix its heat into the picture
                print("auto-heat: skipped " + os.path.basename(p)
                      + " (PERTURBED — schedule-chaos run; --trace it "
                      "explicitly if you really want fuzzed heat)")
                continue
            srcs = set(pl.get("sources", {}))
            if not srcs:
                continue
            hits = sum(1 for s in srcs
                       if s in paths
                       or any(s.endswith("/" + q) for q in paths)
                       or ("/" in s and any(q.endswith("/" + s)
                                            for q in paths)))
            if hits >= min_mods and hits * 2 >= len(srcs):
                matches.append(p)
                if len(matches) >= cap:
                    break
        except Exception:
            continue
    return matches


def load_heat(trace_path, modules):
    """Aggregate a trace_*.html's event log onto the map's modules:
    events per module, execution order, hard exceptions, and events per
    def (attributed by line range, so overrides in different classes
    are distinguished). fn-granularity traces additionally carry µs
    timestamps, so they yield TIME heat (self/cumulative per function
    via a stack replay); line traces yield COUNT heat — the payload
    says which ("kind"), because they mean different things.
    This is the dynamic layer drawn onto the static map — the cockpit."""
    with open(trace_path, encoding="utf-8") as fh:
        html = fh.read()
    m = re.search(r'<script id="trace-data" '
                  r'type="application/json">(.*?)</script>', html, re.S)
    if m is None:
        raise ValueError("not a pyreplay trace file")
    data = json.loads(m.group(1).replace("<\\/", "</"))
    ch = data.get("chunked")
    if ch:   # #101: events live in gzip+base64 chunk tags
        events = []
        tags = re.findall(r'<script id="trace-chunk-(\d+)" '
                          r'type="application/gzip-base64">(.*?)</script>',
                          html, re.S)
        for _, b64 in sorted(((int(k), s) for k, s in tags)):
            events.extend(json.loads(gzip.decompress(base64.b64decode(b64))))
        if len(events) != ch.get("total"):
            raise ValueError(f"chunked trace incomplete: "
                             f"{len(events)}/{ch.get('total')}")
        data["events"] = events
    events = data.get("events", [])
    if data.get("chaos"):
        # explicit --trace of a chaos run: obeyed, but never silently
        print("note: " + os.path.basename(trace_path) + " is a PERTURBED "
              "schedule-chaos run — its heat reflects the fuzzed "
              "schedule, not natural timing")
    kind = "time" if data.get("granularity") == "fn" else "counts"
    script = data.get("script")

    by_path = {mod["path"]: mod for mod in modules}
    fcache = {}

    def mod_for(f):
        if f not in fcache:
            hit = by_path.get(f)
            if hit is None:
                cands = [mod for p, mod in by_path.items()
                         if p.endswith("/" + f) or f.endswith("/" + p)]
                hit = cands[0] if len(cands) == 1 else None
            fcache[f] = hit
        return fcache[f]

    intervals = {}
    for mod in modules:
        ds = sorted(mod["defs"], key=lambda d: d["l"])
        intervals[mod["id"]] = (ds, [d["l"] for d in ds])

    heat, unmatched = {}, 0
    stacks = {}          # per-thread frames: [mod_id, def_key, t0, child]
    abs_ts = 0
    for i, ev in enumerate(events):
        mod = mod_for(ev.get("f", ""))
        # ---- time attribution (fn traces): stack replay over ALL
        # events, matched or not, so nesting stays balanced
        if kind == "time":
            abs_ts += ev.get("ts", 0)
            th = ev.get("t", "main")
            st = stacks.setdefault(th, [])
            if ev["e"] == "call":
                st.append([mod["id"] if mod else None, None, abs_ts, 0.0])
            elif ev["e"] == "return" and st:
                mid, dk, t0, child = st.pop()
                dur = abs_ts - t0
                if st:
                    st[-1][3] += dur
                self_t = max(0, dur - child)
                if mid is not None and mid in heat:
                    hh = heat[mid]
                    hh["tSelf"] = hh.get("tSelf", 0) + self_t
                    if dk:
                        fh = hh["fns"].setdefault(dk, {"n": 0, "calls": 0})
                        fh["tSelf"] = fh.get("tSelf", 0) + self_t
                        fh["tCum"] = fh.get("tCum", 0) + dur
        if mod is None:
            unmatched += 1
            continue
        h = heat.setdefault(mod["id"],
                            {"n": 0, "calls": 0, "exc": 0, "first": i,
                             "fns": {}})
        h["n"] += 1
        if ev["e"] == "call":
            h["calls"] += 1
        if ev["e"] == "exc" and not ev.get("x", {}).get("soft"):
            h["exc"] += 1
        ds, starts = intervals[mod["id"]]
        line = ev.get("l", 0)
        fn = ev.get("fn", "")
        k = bisect.bisect_right(starts, line) - 1
        scanned = 0
        while k >= 0 and scanned < 120:
            d = ds[k]
            # containment by line range AND the runtime frame name must
            # match — a "def foo():" statement executing at import time
            # is module-level code, not foo running
            if (d["l"] <= line <= d["l"] + d["loc"] - 1
                    and (d["n"] == fn or d["n"].endswith("." + fn))):
                fh2 = h["fns"].setdefault(d["n"], {"n": 0, "calls": 0})
                fh2["n"] += 1
                if ev["e"] == "call" and d["l"] == line:
                    fh2["calls"] += 1
                    if kind == "time":
                        stacks[ev.get("t", "main")][-1][1] = d["n"]
                break
            k -= 1
            scanned += 1
    total = abs_ts if kind == "time" else len(events)
    return {"trace": os.path.basename(trace_path), "events": len(events),
            "unmatched": unmatched, "mods": heat, "kind": kind,
            "script": script, "total": max(1, total)}


def aggregate_heat(heats):
    """Merge several per-trace heat dicts into one so the color reflects
    MANY workloads instead of one — sum events, self-time, exceptions and
    per-def stats per module across all runs. This is the reliability fix:
    no single narrow run defines the map. A single trace passes through
    unchanged (order badges and the T-button entry stay meaningful)."""
    if len(heats) == 1:
        return heats[0]
    kind = "time" if all(h["kind"] == "time" for h in heats) else "counts"
    mods = {}
    for h in heats:
        for mid, hh in h["mods"].items():
            agg = mods.setdefault(mid, {"n": 0, "calls": 0, "exc": 0,
                                        "first": 10 ** 12, "fns": {},
                                        "tSelf": 0})
            for k in ("n", "calls", "exc", "tSelf"):
                agg[k] += hh.get(k, 0)
            agg["first"] = min(agg["first"], hh.get("first", 10 ** 12))
            for dk, fh in hh.get("fns", {}).items():
                afh = agg["fns"].setdefault(dk, {"n": 0, "calls": 0,
                                                 "tSelf": 0, "tCum": 0})
                for k in ("n", "calls", "tSelf", "tCum"):
                    afh[k] += fh.get(k, 0)
    # % share denominator must match the per-module value: total wall-time
    # for TIME heat, total events for COUNT heat (a mixed set degrades to
    # counts, the only field both kinds carry)
    total = (sum(h["total"] for h in heats) if kind == "time"
             else sum(h["events"] for h in heats))
    return {"trace": f"{len(heats)} traces: "
            + ", ".join(h["trace"] for h in heats),
            "events": sum(h["events"] for h in heats),
            "unmatched": sum(h["unmatched"] for h in heats),
            "mods": mods, "kind": kind, "script": heats[0]["script"],
            "total": max(1, total)}


def main(argv):
    out = None
    traces = []
    no_trace = False
    heat_out = None
    include, exclude = [], []
    while argv[:1] and argv[0] in ("--out", "--trace", "--no-trace",
                                   "--include", "--exclude", "--heat-out"):
        if argv[0] == "--no-trace":   # boolean: refuses auto-heat
            no_trace = True
            argv = argv[1:]
            continue
        if len(argv) < 3:
            print(__doc__)
            return 2
        if argv[0] == "--out":
            out = argv[1]
        elif argv[0] == "--trace":
            traces.append(argv[1])
        elif argv[0] == "--heat-out":
            heat_out = argv[1]
        elif argv[0] == "--include":
            include.append(argv[1])
        else:
            exclude.append(argv[1])
        argv = argv[2:]
    if not argv:
        print(__doc__)
        return 2
    if len(argv) > 1:
        print(f"error: unexpected arguments after the path: "
              f"{' '.join(argv[1:])} — flags go BEFORE the path")
        return 2
    root = os.path.realpath(argv[0])
    if not os.path.exists(root):
        print(f"error: no such path: {argv[0]}")
        return 2
    root_dir = root if os.path.isdir(root) else os.path.dirname(root)
    files = find_py_files(root)
    if include or exclude:
        files = [p for p in files
                 if scope_ok(os.path.relpath(p, root_dir),
                             include, exclude)]
    if not files:
        print("error: no .py files found (check --include/--exclude)")
        return 2

    # a module id can be claimed by two files (foo.py next to
    # foo/__init__.py): the package wins, exactly like Python's
    # importer, and the shadowed file is labeled as such — two boxes
    # silently sharing one id would merge their stats
    owner = {}
    for p in files:
        mod = module_name(p, root_dir)
        if mod not in owner or p.endswith("__init__.py"):
            owner[mod] = p
    internal = set(owner)
    modules, imports, calls_raw, errors = [], [], [], []
    ext_counts = {}
    unresolved = 0

    for path in files:
        mod = module_name(path, root_dir)
        emit_id = mod if owner[mod] == path else mod + " (shadowed)"
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                src = fh.read()
            # filename makes compiler warnings (SyntaxWarning: invalid
            # escape sequence …) name the real file instead of <unknown>
            tree = ast.parse(src, filename=path)
        except SyntaxError as exc:
            rel = os.path.relpath(path, root_dir)
            errors.append({"path": rel, "msg": str(exc)})
            modules.append({"id": emit_id, "path": rel,
                            "pkg": parent_pkg(mod, path),
                            "loc": 0, "defs": [], "err": True})
            continue
        scan = ModuleScan(mod, path.endswith("__init__.py"), internal)
        scan.visit(tree)
        # local-name calls: resolve against this module's own top defs
        top_defs = {d["n"].split(".")[0] for d in scan.defs}
        for src_def, dmod, dname in scan.calls:
            if dmod is None:
                if dname in top_defs:
                    calls_raw.append((emit_id, src_def, emit_id, dname))
                else:
                    unresolved += 1     # builtin / external call
            else:
                calls_raw.append((emit_id, src_def, dmod, dname))
        unresolved += scan.unresolved
        for e in scan.external:
            ext_counts[e] = ext_counts.get(e, 0) + 1
        for d in sorted(scan.imports):
            if d != mod:
                imports.append({"s": emit_id, "d": d})
        entry = {"id": emit_id,
                 "path": os.path.relpath(path, root_dir),
                 "pkg": parent_pkg(mod, path),
                 "loc": len(src.splitlines()),
                 "defs": scan.defs, "err": False}
        if has_main_guard(tree):
            entry["run"] = True   # module can run itself (__main__ guard)
        modules.append(entry)

    # aggregate calls per module pair, sample function-level detail
    agg = {}
    for smod, sdef, dmod, dname in calls_raw:
        if smod == dmod:
            key = (smod, dmod)
        else:
            key = (smod, dmod)
        a = agg.setdefault(key, {"n": 0, "fns": []})
        a["n"] += 1
        if len(a["fns"]) < 8:
            a["fns"].append((sdef or "<module>") + " → " +
                            (dname or "<module>"))
    calls = [{"s": s, "d": d, "n": v["n"], "fns": v["fns"]}
             for (s, d), v in sorted(agg.items())]

    # intra-module call graph: which top-level function calls which,
    # WITHIN one file. This is the function-world twin of the class
    # inheritance view — it gives a single big file the structure the
    # import graph gives a multi-file project. Callers and callees are
    # top-level function names in the same module; a call made from
    # module level ("<module>") marks that function as an entry point.
    funcs_of, kind_of = {}, {}
    for m in modules:
        funcs_of[m["id"]] = {d["n"] for d in m["defs"]
                             if d["k"] == "def" and "." not in d["n"]}
        kind_of[m["id"]] = {d["n"]: d["k"] for d in m["defs"]}
    INTRA_CAP = 1000
    intra_tmp = {}
    for smod, sdef, dmod, dname in calls_raw:
        if smod != dmod or dname not in funcs_of.get(smod, ()):
            continue   # cross-file, or callee is a class/not a top func
        if sdef:
            parts = sdef.split(".")
            # a call inside a class body/method is not a plain function
            # edge — exclude it whether the class is top-level OR nested
            # inside a function (a method only runs when it's invoked)
            if any(kind_of[smod].get(".".join(parts[:i + 1])) == "class"
                   for i in range(len(parts))):
                continue
            caller = parts[0]
        else:
            caller = "<module>"
        rec = intra_tmp.setdefault(smod, {"edges": set(), "entries": set()})
        if caller == "<module>":
            rec["entries"].add(dname)          # called at module level
        elif caller in funcs_of[smod]:
            rec["edges"].add((caller, dname))  # function → function
    intra = {}
    for mid, rec in intra_tmp.items():
        edges = sorted(rec["edges"])
        intra[mid] = {"edges": [list(e) for e in edges[:INTRA_CAP]],
                      "entries": sorted(rec["entries"]),
                      "trunc": len(edges) > INTRA_CAP}

    name = os.path.basename(root.rstrip(os.sep)) or "map"
    if out is None:
        out = f"map_{name}.html"
        n = 2
        while os.path.exists(out):
            out = f"map_{name}_{n}.html"
            n += 1

    heat = None
    auto = False
    if not traces and not no_trace:
        traces = find_matching_traces(root_dir, modules)
        if traces:
            auto = True
            print("auto-heat: aggregating " + str(len(traces))
                  + " matching trace(s) — "
                  + ", ".join(os.path.basename(t) for t in traces)
                  + " (--trace FILE to choose, --no-trace to disable)")
    if traces:
        try:
            heat = aggregate_heat([load_heat(t, modules) for t in traces])
            if auto and not heat["mods"]:
                # matched by filenames but no event landed on this map:
                # an auto guess must never ship empty heat
                print("auto-heat: no events matched this map — dropped")
                heat = None
            else:
                print(f"heat[{heat['kind']}]: {heat['events']} events from "
                      f"{heat['trace']}, {len(heat['mods'])} modules "
                      f"touched, {heat['unmatched']} events outside "
                      f"this map")
                if heat_out:
                    with open(heat_out, "w", encoding="utf-8") as fh:
                        json.dump(heat, fh, indent=1)
                    print(f"aggregate written -> {heat_out}")
        except Exception as exc:
            print(f"warning: could not read trace(s) ({exc}) — no heat")

    # the load-bearing walls: how many modules import me (fan-in) and
    # how many I import (fan-out) — imports are unique per (s, d) pair
    fan = {m["id"]: {"i": 0, "o": 0} for m in modules}
    for e in imports:
        if e["s"] in fan and e["d"] in fan:
            fan[e["s"]]["o"] += 1
            fan[e["d"]]["i"] += 1

    cycles = find_cycles({m["id"] for m in modules}, imports)

    # which external deps are actually IMPORTABLE here? find_spec only
    # consults the import finders — no target code executes. This is
    # the "you will crash at import numpy" warning BEFORE any run.
    # (Checked against the environment the mapper runs in — map from
    # inside the venv you'll trace in.)
    ext_missing = []
    stdlib_names = getattr(sys, "stdlib_module_names", ())
    for ext_name in sorted(ext_counts):
        if ext_name in stdlib_names:
            continue   # stdlib — a "missing" one (msvcrt on Linux) is a
                       # platform guard in the code, not a pip install
        try:
            if importlib.util.find_spec(ext_name) is None:
                ext_missing.append(ext_name)
        except Exception:
            pass   # unresolvable finder result: unknown, never claimed

    payload = {
        "root": name,
        "rootPath": root,
        "modules": modules,
        "imports": imports,
        "cycles": cycles,
        "fan": fan,
        "calls": calls,
        "intra": intra,
        "external": dict(sorted(ext_counts.items(),
                                key=lambda kv: (-kv[1], kv[0]))[:20]),
        "extMissing": ext_missing,
        "unresolvedCalls": unresolved,
        "errors": errors,
        "heat": heat,
    }
    template = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                            "map_template.html")
    with open(template, encoding="utf-8") as fh:
        html = fh.read()
    data = json.dumps(payload).replace("</", "<\\/")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html.replace("__MAP_DATA__", data))

    print(f"{len(modules)} modules, {sum(len(m['defs']) for m in modules)} "
          f"defs, {len(imports)} internal imports, {len(calls)} call "
          f"routes, {len(cycles)} import cycle(s) -> {out}")
    if ext_missing:
        print(f"note: {len(ext_missing)} external dep(s) NOT importable "
              f"in this environment: {', '.join(ext_missing[:10])}"
              f"{'…' if len(ext_missing) > 10 else ''} — a traced run "
              f"will crash at their import (pip install them first)")
    if errors:
        print(f"note: {len(errors)} file(s) failed to parse "
              f"(shown on the map)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
