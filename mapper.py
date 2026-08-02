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
import subprocess
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

# #95: decision-point node types — a cyclomatic-ISH count, honestly
# labeled "decision points", never "McCabe"
_CX_NODES = (ast.If, ast.While, ast.For, ast.AsyncFor, ast.IfExp,
             ast.ExceptHandler, ast.Assert, ast.comprehension)


def _complexity(tree):
    """#95: decision points per module — ifs, loops, handlers, ternaries,
    asserts, per-comprehension clauses, boolean-op branches and match
    cases. A cheap, stdlib, explainable complexity score."""
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, _CX_NODES):
            n += 1
            if isinstance(node, ast.comprehension):
                n += len(node.ifs)
        elif isinstance(node, ast.BoolOp):
            n += len(node.values) - 1
        elif isinstance(node, ast.Match):
            n += len(node.cases)
    return n


def _fmt_us(us):
    if us < 1000:
        return f"{us:.0f} µs"
    if us < 1_000_000:
        return f"{us / 1000:.1f} ms"
    return f"{us / 1e6:.2f} s"


def _gather_churn(root_dir, since):
    """#95: per-file change counts from `git log --numstat` over the
    window, scoped to the mapped subtree. Returns None when there is no
    git history to read (not a repo, no git, git errors) — the crime
    lens degrades to absent, it never guesses."""
    def _git(*args):
        return subprocess.run(["git", "-C", root_dir] + list(args),
                              capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL)
    try:
        top = _git("rev-parse", "--show-toplevel")
        if top.returncode != 0:
            return None
        toplevel = top.stdout.strip()
        log = _git("log", "--numstat", "--no-renames", "--format=%H",
                   "--since=" + since, "--", ".")
        if log.returncode != 0:
            return None
    except Exception:
        return None
    files, commits = {}, 0
    hash_re = re.compile(r"^[0-9a-f]{40}$")
    stat_re = re.compile(r"^(\d+|-)\t(\d+|-)\t(.+)$")
    for line in log.stdout.splitlines():
        if hash_re.match(line):
            commits += 1
            continue
        m = stat_re.match(line)
        if m is None:
            continue
        rel = os.path.relpath(os.path.join(toplevel, m.group(3)),
                              root_dir)
        if rel.startswith(".."):
            continue   # touched outside the mapped subtree
        rec = files.setdefault(rel, {"c": 0, "ch": 0})
        rec["c"] += 1
        if m.group(1) != "-":
            rec["ch"] += int(m.group(1)) + int(m.group(2))
    if commits == 0:
        return None   # a repo with no history in the window: say absent
    return {"since": since, "commits": commits, "files": files}


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
        self.dunder_all = None   # #100: literal __all__, or None
        self.dynimp = 0          # #119: __import__/import_module call
        #                          sites — targets unknown until traced
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

    def visit_Assign(self, node):
        # #100: a LITERAL module-level __all__ declares the intended
        # surface; anything computed stays None (honest absence)
        if not self._scope:
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__" \
                        and isinstance(node.value, (ast.List, ast.Tuple)):
                    vals = []
                    for el in node.value.elts:
                        if isinstance(el, ast.Constant) \
                                and isinstance(el.value, str):
                            vals.append(el.value)
                        else:
                            vals = None
                            break
                    if vals is not None:
                        self.dunder_all = vals
        self.generic_visit(node)

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
        # #119: a dynamic import is the parse's declared blind spot —
        # flag the SITE now; the target only exists once a run is traced
        if (isinstance(f, ast.Name) and f.id == "__import__") or \
                (isinstance(f, ast.Attribute)
                 and f.attr == "import_module"):
            self.dynimp += 1
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
                elif chain[0] == "self" and len(chain) == 2:
                    # #94: self.method() resolves against the enclosing
                    # class's own defs post-scan (same class only —
                    # inherited methods still need runtime, stated)
                    self.calls.append((src, "@self", chain[1]))
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
            if pl.get("inject"):
                # roadmap #2: same rule — injected faults bend the
                # control flow on purpose; that heat is not the code's
                print("auto-heat: skipped " + os.path.basename(p)
                      + " (PERTURBED — fault-injection run; --trace "
                      "it explicitly if you really want that heat)")
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
    if data.get("inject"):
        print("note: " + os.path.basename(trace_path) + " is a "
              "PERTURBED fault-injection run — its heat includes "
              "paths the faults forced, not natural behavior")
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
    stacks = {}          # per-thread frames: [mod_id, def_key, t0,
    #                      child, is_module_frame]
    xstacks = {}         # #119: per-(thread, task) module stacks
    xmod = {}            # "callerId|calleeId" -> observed call count
    imp_cost = {}        # #99: mid -> µs inside its <module> frames
    abs_ts = 0
    for i, ev in enumerate(events):
        mod = mod_for(ev.get("f", ""))
        # ---- #119: cross-module call pairs the run OBSERVED. Per
        # (thread, task) lane so asyncio interleaving can't fake an
        # edge; unmatched callees still push (None) so nesting stays
        # balanced. Direct caller only — a foreign frame in between
        # means the direct call was foreign, not a module edge.
        if ev.get("e") in ("call", "return"):
            lane = (ev.get("t", "main"), ev.get("tk"))
            xst = xstacks.setdefault(lane, [])
            if ev["e"] == "call":
                top = xst[-1] if xst else None
                mid = mod["id"] if mod else None
                if top is not None and mid is not None and top != mid:
                    key = top + "|" + mid
                    xmod[key] = xmod.get(key, 0) + 1
                xst.append(mid)
            elif xst:
                xst.pop()
        # ---- time attribution (fn traces): stack replay over ALL
        # events, matched or not, so nesting stays balanced
        if kind == "time":
            abs_ts += ev.get("ts", 0)
            th = ev.get("t", "main")
            st = stacks.setdefault(th, [])
            if ev["e"] == "call":
                st.append([mod["id"] if mod else None, None, abs_ts, 0.0,
                           ev.get("fn") == "<module>"])
            elif ev["e"] == "return" and st:
                mid, dk, t0, child, is_mod = st.pop()
                dur = abs_ts - t0
                if st:
                    st[-1][3] += dur
                if is_mod and mid is not None:
                    # #99: time inside a <module> frame IS import cost
                    # (cumulative — a slow import's children are the
                    # point, not an accounting detail)
                    imp_cost[mid] = imp_cost.get(mid, 0) + dur
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
    # #6 remainder: --memory traces carry a per-file byte distribution
    # (in-scope bytes at the largest sampled snapshot). Map the rel
    # paths onto modules with the same matcher the events use; bytes in
    # files outside this map are COUNTED, never guessed onto a module.
    mem = None
    m_ = data.get("memory")
    if m_ and m_.get("perFile"):
        per_mod, outside = {}, 0
        for f, b in m_["perFile"].items():
            mm = mod_for(f)
            if mm is not None:
                per_mod[mm["id"]] = per_mod.get(mm["id"], 0) + b
            else:
                outside += b
        if per_mod or outside:
            mem = {"perMod": per_mod,
                   "at": m_.get("perFileAt") or 0,
                   "peak": m_.get("peak", 0), "outside": outside,
                   "from": os.path.basename(trace_path)}
    return {"trace": os.path.basename(trace_path), "events": len(events),
            "unmatched": unmatched, "mods": heat, "kind": kind,
            "xmod": xmod, "importCost": imp_cost, "script": script,
            "memory": mem, "total": max(1, total)}


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
    xmod = {}
    for h in heats:   # #119: observed pairs sum across workloads too
        for k, n in h.get("xmod", {}).items():
            xmod[k] = xmod.get(k, 0) + n
    imp_cost = {}
    for h in heats:   # #99: import cost sums across adopted runs
        for k, us in h.get("importCost", {}).items():
            imp_cost[k] = imp_cost.get(k, 0) + us
    # #6 remainder: a byte distribution is ONE moment of ONE run —
    # summing snapshots from different runs would paint a state that
    # never existed. Adopt the run with the largest in-scope snapshot
    # whole; its "from" names which trace the palette speaks for.
    mem = None
    for h in heats:
        hm = h.get("memory")
        if hm and (mem is None or hm.get("at", 0) > mem.get("at", 0)):
            mem = hm
    return {"trace": f"{len(heats)} traces: "
            + ", ".join(h["trace"] for h in heats),
            "events": sum(h["events"] for h in heats),
            "unmatched": sum(h["unmatched"] for h in heats),
            "mods": mods, "kind": kind, "script": heats[0]["script"],
            "xmod": xmod, "importCost": imp_cost, "memory": mem,
            "total": max(1, total)}


# ---- #129: the graph lens — graph theory over the map's own graphs ------
# The map IS a graph analyzed with a fraction of graph theory: fan
# counts degree, Tarjan finds cycles — bridges, clusters and fragility
# stay invisible. These four instruments close that gap, pure stdlib,
# comfortable at map scale (Brandes is O(V·E) per source). Every number
# names its graph: "static import graph" vs "observed call pairs".

def _brandes(nodes, edges):
    """Betweenness centrality, unweighted, DIRECTED (an import points
    somewhere on purpose). Returns {node: score} for nodes > 0."""
    adj = {v: [] for v in nodes}
    for a, b in edges:
        if a != b and a in adj and b in adj:
            adj[a].append(b)
    cb = {v: 0.0 for v in nodes}
    for s in nodes:
        stack = []
        pred = {v: [] for v in nodes}
        sigma = {v: 0 for v in nodes}
        sigma[s] = 1
        dist = {v: -1 for v in nodes}
        dist[s] = 0
        queue = [s]
        qi = 0
        while qi < len(queue):
            v = queue[qi]
            qi += 1
            stack.append(v)
            for w in adj[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = {v: 0.0 for v in nodes}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                cb[w] += delta[w]
    return {v: round(c, 2) for v, c in sorted(cb.items()) if c > 0}


def _label_prop(ids, und):
    """Community detection by label propagation — deterministic: fixed
    sweep order, most-frequent neighbor label, ties to the smallest.
    Returns {module: community index}; singletons carry no community."""
    label = {v: v for v in ids}
    order = sorted(ids)
    for _ in range(50):
        changed = False
        for v in order:
            if not und[v]:
                continue
            counts = {}
            for w in und[v]:
                counts[label[w]] = counts.get(label[w], 0) + 1
            best = sorted(counts.items(),
                          key=lambda kv: (-kv[1], kv[0]))[0][0]
            if best != label[v]:
                label[v] = best
                changed = True
        if not changed:
            break
    groups = {}
    for v, lb in label.items():
        groups.setdefault(lb, []).append(v)
    out = {}
    k = 0
    for lb, members in sorted(groups.items(),
                              key=lambda kv: (-len(kv[1]), kv[0])):
        if len(members) < 2:
            continue
        for v in members:
            out[v] = k
        k += 1
    return out


def _percolate(ids, und, between):
    """Attack-tolerance curve (Albert–Jeong–Barabási): remove the
    top-k most-between modules (INITIAL ranking — stated in the
    panel), track the giant weakly-connected component's share of the
    ORIGINAL module count. A cliff = a load-bearing wall, measured."""
    n = len(ids)
    if n < 3 or not between:
        return None
    targets = [v for v, _ in sorted(between.items(),
                                    key=lambda kv: (-kv[1], kv[0]))]
    targets = targets[:min(10, n - 2)]
    removed = set()

    def giant():
        seen = set()
        best = 0
        for v in ids:
            if v in removed or v in seen:
                continue
            comp = 0
            todo = [v]
            seen.add(v)
            while todo:
                u = todo.pop()
                comp += 1
                for w in und[u]:
                    if w not in removed and w not in seen:
                        seen.add(w)
                        todo.append(w)
            best = max(best, comp)
        return best
    curve = [{"k": 0, "removed": None, "giant": round(giant() / n, 3)}]
    for i, t in enumerate(targets, 1):
        removed.add(t)
        curve.append({"k": i, "removed": t,
                      "giant": round(giant() / n, 3)})
    return curve


def _graph_lens(modules, imports, heat):
    ids = [m["id"] for m in modules]
    if len(ids) < 2:
        return None
    idset = set(ids)
    static = [(e["s"], e["d"]) for e in imports
              if e["s"] in idset and e["d"] in idset]
    res = {"staticEdges": len(static),
           "between": _brandes(ids, static)}
    if heat and heat.get("xmod"):
        obs = []
        for key in heat["xmod"]:
            a, _, b = key.partition("|")
            if a in idset and b in idset:
                obs.append((a, b))
        if obs:
            res["betweenObs"] = _brandes(ids, obs)
            res["obsEdges"] = len(obs)
    und = {v: set() for v in ids}
    for a, b in static:
        if a != b:
            und[a].add(b)
            und[b].add(a)
    res["community"] = _label_prop(ids, und)
    res["percolation"] = _percolate(ids, und, res["between"])
    degs = {}
    for v in ids:
        d = len(und[v])
        degs[str(d)] = degs.get(str(d), 0) + 1
    res["degrees"] = degs
    return res


# ---- #97: dead-code evidence ---------------------------------------
# The join IS the feature: static unreference (#94's def→def graph +
# the importable surface) × dynamic never-ran (every adopted trace).
# Tier A: no static reference at all. Tier B: importable surface or
# method of a live class — never called statically. Tier C: called
# statically somewhere, never ran in any adopted trace (workload-
# relative). A def that RAN is alive whatever the static graph says —
# that is dynamic dispatch, not dead code. Dunders are skipped (the
# interpreter calls them implicitly). Evidence, never proof:
# reflection, plugins and decorators can hide callers.

# ---- #100: API-surface honesty (encapsulation leaks) ---------------
# The gap between the intended interface and the real one, measured.
# L1: an outside module imports an _underscore module (privacy owner
# = the underscore component's parent package). L2: an outsider does
# `from m import _name` (owner = m's parent package; top-level
# modules own their own privacy). L3: m declares a literal __all__
# and an outsider imports a public name NOT in it. Intra-package
# reaches are the convention working as intended — not counted.
# Star imports bypass the name audit and are counted, never ignored.

LEAK_CAP = 100


# ---- #122: shadowing & collision audit (static tier, module level).
# Three masks the parse can prove: a module-level assignment that
# rebinds an earlier import; a module-level binding named like a
# builtin; and a TOP-LEVEL file named like a stdlib module — the
# import horror that breaks codebases at import time (only top-level
# files can shadow stdlib for scripts run from that directory; a
# package-internal email.py cannot under absolute imports).

def _module_shadows(tree, mod, is_top_level):
    import builtins as _bi
    BUILTINS = set(dir(_bi))
    sh = []
    bound = {}
    for st in tree.body:
        if isinstance(st, (ast.Import, ast.ImportFrom)):
            kind = "import"
            names = [(al.asname or al.name).split(".")[0]
                     for al in st.names if al.name != "*"]
        elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            kind = "def"
            names = [st.name]
        elif isinstance(st, ast.Assign):
            kind = "assign"
            names = [n.id for t in st.targets for n in ast.walk(t)
                     if isinstance(n, ast.Name)]
        elif isinstance(st, (ast.AugAssign, ast.AnnAssign,
                             ast.For, ast.AsyncFor)):
            kind = "assign"
            names = [n.id for n in ast.walk(st.target)
                     if isinstance(n, ast.Name)]
        else:
            continue
        for nm in names:
            prev = bound.get(nm)
            if prev and prev[0] == "import" and kind != "import":
                sh.append(["import-rebound", nm,
                           "imported L%d, rebound L%d"
                           % (prev[1], st.lineno)])
            if nm in BUILTINS and prev is None:
                sh.append(["builtin", nm, "L%d" % st.lineno])
            if prev is None:
                bound[nm] = (kind, st.lineno)
    if is_top_level and mod.split(".")[0] in \
            getattr(sys, "stdlib_module_names", ()):
        sh.insert(0, ["stdlib-filename", mod.split(".")[0],
                      "a top-level %s.py shadows the stdlib module "
                      "for anything run from this directory"
                      % mod.split(".")[0]])
    return sh


# ---- #96: layering rules — the declared architecture, enforced.
# An optional .pyreplay-layers file names the layers and their order;
# the map paints violating import edges red and --check-layers exits
# non-zero for CI. Grammar (comments with #, blank lines ignored):
#   layers: ui -> logic -> data     # order = permission: a layer may
#                                   # import DOWNWARD, never upward
#   layer ui: main, cli.*           # membership by fnmatch on the
#   layer logic: cart, discounts    # dotted module id
#   layer data: store*
#   forbid cli.* -> store*          # extra explicit ban (module globs)
# A malformed file REFUSES to enforce (partial rules would pretend
# the architecture is safe); modules matching no layer are counted,
# never guessed into one.

def _load_layers(root_dir, override=None):
    path = override or os.path.join(root_dir, ".pyreplay-layers")
    if not os.path.exists(path):
        return None
    chains, members, forbids, errors = [], {}, [], []
    order = []   # layer declaration order (first match wins)
    with open(path, encoding="utf-8") as fh:
        for ln, raw in enumerate(fh, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("layers:"):
                names = [p.strip() for p in
                         line[len("layers:"):].split("->")]
                if len(names) < 2 or not all(names):
                    errors.append(f"line {ln}: a chain needs at least "
                                  f"two layer names: {raw.strip()!r}")
                else:
                    chains.append(names)
            elif line.startswith("layer "):
                head, _, rest = line[len("layer "):].partition(":")
                name = head.strip()
                pats = [p.strip() for p in rest.split(",") if p.strip()]
                if not name or not pats:
                    errors.append(f"line {ln}: expected 'layer NAME: "
                                  f"glob, …': {raw.strip()!r}")
                elif name in members:
                    errors.append(f"line {ln}: layer {name!r} declared "
                                  f"twice")
                else:
                    members[name] = pats
                    order.append(name)
            elif line.startswith("forbid "):
                parts = [p.strip() for p in
                         line[len("forbid "):].split("->")]
                if len(parts) != 2 or not all(parts):
                    errors.append(f"line {ln}: expected 'forbid GLOB "
                                  f"-> GLOB': {raw.strip()!r}")
                else:
                    forbids.append(parts)
            else:
                errors.append(f"line {ln}: unrecognized: {raw.strip()!r}")
    for chain in chains:
        for name in chain:
            if name not in members:
                errors.append(f"chain names undeclared layer {name!r} "
                              f"(add a 'layer {name}: …' line)")
    return {"file": os.path.basename(path), "chains": chains,
            "members": members, "order": order, "forbids": forbids,
            "errors": errors}


def _layer_violations(rules, imports, internal):
    """Classify every internal import edge against the declared
    architecture. Violation = importing UPWARD in a chain (a layer may
    use what is below it, never what is above), or an explicit forbid.
    Modules matching no layer are unconstrained and counted."""
    import fnmatch
    assign = {}
    for mod in internal:
        for name in rules["order"]:
            if any(fnmatch.fnmatchcase(mod, pat)
                   for pat in rules["members"][name]):
                assign[mod] = name
                break
    rank = {}   # (chain_idx, layer) -> position; 0 = top
    for ci, chain in enumerate(rules["chains"]):
        for pos, name in enumerate(chain):
            rank.setdefault(name, {})[ci] = pos
    viol = []
    seen = set()
    for e in imports:
        s, d = e["s"], e["d"]
        if d not in internal or (s, d) in seen:
            continue
        seen.add((s, d))
        ls, ld = assign.get(s), assign.get(d)
        rule = None
        if ls and ld and ls != ld:
            for ci, chain in enumerate(rules["chains"]):
                ps = rank.get(ls, {}).get(ci)
                pd = rank.get(ld, {}).get(ci)
                if ps is not None and pd is not None and pd < ps:
                    rule = (f"{ls} may not import {ld} — the chain "
                            f"says {' -> '.join(chain)}")
                    break
        if rule is None:
            for fa, fb in rules["forbids"]:
                if fnmatch.fnmatchcase(s, fa) and \
                        fnmatch.fnmatchcase(d, fb):
                    rule = f"forbidden: {fa} -> {fb}"
                    break
        if rule is not None:
            viol.append({"s": s, "d": d, "ls": ls, "ld": ld,
                         "rule": rule})
    unassigned = sorted(m for m in internal if m not in assign)
    return {"assign": assign, "viol": viol, "unassigned": unassigned}


def _api_leaks(imports, name_imports, all_decls, star_imports):
    def inside(importer, pkg):
        return pkg is not None and (
            importer == pkg or importer.startswith(pkg + "."))
    mod_leaks, name_leaks = {}, {}
    leak_edges = set()
    for e in imports:
        s, d = e["s"], e["d"]
        parts = d.split(".")
        for k in range(1, len(parts)):
            if parts[k].startswith("_"):
                owner = ".".join(parts[:k])
                if not inside(s, owner):
                    mod_leaks.setdefault(d, set()).add(s)
                    leak_edges.add((s, d))
                break
    for s, d, n in name_imports:
        if s == d:
            continue
        owner = d.rsplit(".", 1)[0] if "." in d else None
        if inside(s, owner):
            continue
        if n.startswith("_"):
            name_leaks.setdefault((d, n, "private"), set()).add(s)
            leak_edges.add((s, d))
        elif d in all_decls and n not in all_decls[d]:
            name_leaks.setdefault((d, n, "undeclared"), set()).add(s)
            leak_edges.add((s, d))
    ml = sorted(({"d": d, "srcs": sorted(v)}
                 for d, v in mod_leaks.items()),
                key=lambda x: (-len(x["srcs"]), x["d"]))
    nl = sorted(({"d": d, "n": n, "kind": kind, "srcs": sorted(v)}
                 for (d, n, kind), v in name_leaks.items()),
                key=lambda x: (-len(x["srcs"]), x["d"], x["n"]))
    total = len(ml) + len(nl)
    return {"modLeaks": ml[:LEAK_CAP], "nameLeaks": nl[:LEAK_CAP],
            "edges": sorted(list(e) for e in leak_edges),
            "declared": sorted(all_decls),
            "stars": star_imports, "total": total,
            "capped": total > 2 * LEAK_CAP}


DEAD_CAP = 500


def _dead_code(modules, callgraph, imported_fns, heat, n_runs):
    called = set()
    if callgraph:
        for s, d, n, k in callgraph["edges"]:
            dm, _, dn = d.partition(":")
            called.add((dm, dn))
    hm = (heat or {}).get("mods", {})

    def ran(mid, name):
        fh = (hm.get(mid) or {}).get("fns", {}).get(name)
        return bool(fh and (fh.get("n", 0) or fh.get("calls", 0)))
    live_cls = set()
    for m in modules:
        for d in m["defs"]:
            if d.get("k") == "class":
                key = (m["id"], d["n"])
                if key in called or key in imported_fns:
                    live_cls.add(key)
    cands = []
    counts = {"A": 0, "B": 0, "C": 0}
    for m in modules:
        if m.get("err"):
            continue
        for d in m["defs"]:
            name = d["n"]
            leaf = name.rsplit(".", 1)[-1]
            if leaf.startswith("__") and leaf.endswith("__"):
                continue
            key = (m["id"], name)
            if d.get("k") == "class":
                # a class BODY runs at import time — that is not
                # liveness. A class is alive statically (called/
                # imported) or through a method that ran.
                if key in live_cls or any(
                        ran(m["id"], d2["n"]) for d2 in m["defs"]
                        if d2["n"].startswith(name + ".")):
                    continue
            elif ran(m["id"], name):
                continue                  # it ran: alive, full stop
            in_called = key in called
            meth_live = "." in name and (
                m["id"], name.split(".")[0]) in live_cls
            if in_called:
                if not n_runs:
                    continue              # no dynamic evidence yet
                tier = "C"
            elif key in imported_fns or meth_live:
                tier = "B"
            else:
                tier = "A"
            counts[tier] += 1
            cands.append({"m": m["id"], "n": name, "l": d["l"],
                          "k": d.get("k", "def"), "tier": tier})
    cands.sort(key=lambda c: (c["tier"], c["m"], c["l"]))
    return {"cands": cands[:DEAD_CAP], "counts": counts,
            "runs": n_runs, "capped": len(cands) > DEAD_CAP}


def main(argv):
    out = None
    traces = []
    no_trace = False
    no_churn = False
    churn_since = "12 months ago"   # #95: git's --since vocabulary
    heat_out = None
    include, exclude = [], []
    layers_file = None
    check_layers = False
    while argv[:1] and argv[0] in ("--out", "--trace", "--no-trace",
                                   "--include", "--exclude", "--heat-out",
                                   "--churn-since", "--no-churn",
                                   "--layers", "--check-layers"):
        if argv[0] == "--no-trace":   # boolean: refuses auto-heat
            no_trace = True
            argv = argv[1:]
            continue
        if argv[0] == "--no-churn":   # boolean: skip git history
            no_churn = True
            argv = argv[1:]
            continue
        if argv[0] == "--check-layers":   # #96: CI gate
            check_layers = True
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
        elif argv[0] == "--churn-since":
            churn_since = argv[1]
        elif argv[0] == "--layers":
            layers_file = argv[1]
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
    imported_fns = set()   # #97: (module, name) importable surface
    name_imports = []      # #100: (importer, module, name) triples
    all_decls = {}         # #100: module -> literal __all__
    star_imports = 0       # #100: audits nothing, counted honestly
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
        all_defs = {d["n"] for d in scan.defs}
        for src_def, dmod, dname in scan.calls:
            if dmod is None:
                if dname in top_defs:
                    calls_raw.append((emit_id, src_def, emit_id, dname,
                                      "direct"))
                else:
                    unresolved += 1     # builtin / external call
            elif dmod == "@self":
                cls = (src_def or "").split(".")[0]
                if cls and f"{cls}.{dname}" in all_defs:
                    calls_raw.append((emit_id, src_def, emit_id,
                                      f"{cls}.{dname}", "self"))
                else:
                    unresolved += 1     # inherited/dynamic: runtime's
            else:
                calls_raw.append((emit_id, src_def, dmod, dname,
                                  "direct"))
        unresolved += scan.unresolved
        for a in scan.aliases.values():   # #97: importable surface
            if a[0] == "func":
                imported_fns.add((a[1], a[2]))
                if a[2] == "*":
                    star_imports += 1     # #100: bypasses the audit
                else:
                    name_imports.append((emit_id, a[1], a[2]))
        if scan.dunder_all is not None:
            all_decls[emit_id] = scan.dunder_all
        for e in scan.external:
            ext_counts[e] = ext_counts.get(e, 0) + 1
        for d in sorted(scan.imports):
            if d != mod:
                imports.append({"s": emit_id, "d": d})
        shadows = _module_shadows(tree, mod, "." not in mod)
        entry = {"id": emit_id,
                 "dynimp": scan.dynimp,
                 "shadows": shadows,   # #122, [] when clean
                 "cx": _complexity(tree),   # #95: decision points
                 "path": os.path.relpath(path, root_dir),
                 "pkg": parent_pkg(mod, path),
                 "loc": len(src.splitlines()),
                 "defs": scan.defs, "err": False}
        if has_main_guard(tree):
            entry["run"] = True   # module can run itself (__main__ guard)
        modules.append(entry)

    # aggregate calls per module pair, sample function-level detail
    agg = {}
    for smod, sdef, dmod, dname, _kind in calls_raw:
        key = (smod, dmod)
        a = agg.setdefault(key, {"n": 0, "fns": []})
        a["n"] += 1
        if len(a["fns"]) < 8:
            a["fns"].append((sdef or "<module>") + " → " +
                            (dname or "<module>"))
    calls = [{"s": s, "d": d, "n": v["n"], "fns": v["fns"]}
             for (s, d), v in sorted(agg.items())]

    # #94: the project-wide FUNCTION call graph — the same recorded
    # call sites, kept at def→def resolution instead of module counts.
    # resolved = the target name is among the target module's defs;
    # guessed = internal module, name unknown there (re-export or
    # attribute the parse can't confirm); module-only routes and the
    # per-module unresolved counter stay what they always were.
    CG_CAP = 4000
    def_names = {m["id"]: {d["n"] for d in m["defs"]} for m in modules}
    cg_edges = {}
    cg_res = cg_guess = cg_modonly = 0
    for smod, sdef, dmod, dname, kind in calls_raw:
        if dname is None:
            cg_modonly += 1
            continue
        if dmod in def_names and dname in def_names[dmod]:
            ekind = kind
            cg_res += 1
        elif dmod in def_names:
            ekind = "guessed"
            cg_guess += 1
        else:
            cg_modonly += 1
            continue
        key = (f"{smod}:{sdef or '<module>'}", f"{dmod}:{dname}",
               ekind)
        cg_edges[key] = cg_edges.get(key, 0) + 1
    fanin = {}
    for (s, d, k), n in cg_edges.items():
        smod2 = s.split(":", 1)[0]
        dmod2 = d.split(":", 1)[0]
        if smod2 != dmod2 and k != "guessed":
            f = fanin.setdefault(d, {"n": 0, "mods": set()})
            f["n"] += n
            f["mods"].add(smod2)
    edge_list = sorted(cg_edges.items(), key=lambda kv: -kv[1])
    callgraph = {
        "edges": [[s, d, n, k] for (s, d, k), n in
                  edge_list[:CG_CAP]],
        "total": len(cg_edges), "resolved": cg_res,
        "guessed": cg_guess, "modOnly": cg_modonly,
        "fanin": [[d, f["n"], len(f["mods"])] for d, f in
                  sorted(fanin.items(),
                         key=lambda kv: (-kv[1]["n"], kv[0]))[:12]],
    }

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
    for smod, sdef, dmod, dname, _kind in calls_raw:
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
    n_runs = 0
    if traces:
        try:
            heat = aggregate_heat([load_heat(t, modules) for t in traces])
            n_runs = len(traces)
            if auto and not heat["mods"]:
                # matched by filenames but no event landed on this map:
                # an auto guess must never ship empty heat
                print("auto-heat: no events matched this map — dropped")
                heat = None
                n_runs = 0
            else:
                print(f"heat[{heat['kind']}]: {heat['events']} events from "
                      f"{heat['trace']}, {len(heat['mods'])} modules "
                      f"touched, {heat['unmatched']} events outside "
                      f"this map")
                if heat.get("memory"):
                    hm = heat["memory"]

                    def _hb(n):
                        for u in ("B", "KB", "MB"):
                            if abs(n) < 1024:
                                return (f"{n:.0f} {u}" if u == "B"
                                        else f"{n:.1f} {u}")
                            n /= 1024
                        return f"{n:.1f} GB"
                    print(f"memory palette: {_hb(hm.get('at', 0))} "
                          f"in-scope across {len(hm['perMod'])} "
                          f"module(s) from {hm['from']}"
                          + (f", {_hb(hm['outside'])} outside this map"
                             if hm.get("outside") else "")
                          + " — lens → memory (bytes)")
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

    if heat and heat.get("importCost"):
        # #99: the startup autopsy — the data was in every fn trace
        # all along; this is a lens, not a recorder
        ic = heat["importCost"]
        top = sorted(ic.items(), key=lambda kv: -kv[1])[:3]
        print("startup autopsy: " + _fmt_us(sum(ic.values()))
              + " inside <module> frames (import time) — top: "
              + ", ".join(f"{m} {_fmt_us(us)}" for m, us in top))

    churn = None if no_churn else _gather_churn(root_dir, churn_since)
    if churn:
        # #95: the crime scene — churn × complexity, the strongest bug
        # predictor known. Terminal gets the top offenders; the map
        # gets the lens.
        by_path2 = {m["path"]: m for m in modules}
        max_c = max((f["c"] for f in churn["files"].values()),
                    default=0) or 1
        max_x = max((m.get("cx", 0) for m in modules), default=0) or 1
        scored = []
        for p, f in churn["files"].items():
            m = by_path2.get(p)
            if m is None:
                continue   # touched in history, not on this map now
            s = ((f["c"] / max_c) * (m.get("cx", 0) / max_x)) ** 0.5
            scored.append((s, f["c"], m.get("cx", 0), m["id"]))
        scored.sort(reverse=True)
        print(f"crime scene: {churn['commits']} commit(s) since "
              f"\"{churn_since}\" touched this subtree; churn × "
              f"complexity, top offenders:")
        for s, c, x, mid in scored[:3]:
            print(f"    {s:.2f}  {mid}  ({c} commit(s) · {x} decision "
                  f"points)")
    elif not no_churn:
        print("crime scene: no git history readable here — the churn "
              "lens stays absent (map from inside the repo to get it)")

    if heat and heat.get("xmod"):
        # #119 dark edges: runtime caller→callee pairs with NO static
        # route (neither an import nor a resolvable call) — the map's
        # documented blind spot, drawn instead of merely counted.
        # Honesty: observed in the adopted run(s) only; the absence of
        # a dark edge is never evidence of absence.
        static_pairs = {(e["s"], e["d"]) for e in imports}
        static_pairs |= {(c["s"], c["d"]) for c in calls}
        dark = []
        for key, n in sorted(heat["xmod"].items(), key=lambda kv:
                             (-kv[1], kv[0])):
            a, _, b = key.partition("|")
            if (a, b) not in static_pairs:
                dark.append({"a": a, "b": b, "n": n})
        heat["darkTotal"] = len(dark)
        heat["dark"] = dark[:200]   # cap; darkTotal states the truth
        if dark:
            print(f"dark edges: the run saw {len(dark)} caller→callee "
                  f"pair(s) the parse couldn't — drawn dashed on the map")

    apileaks = _api_leaks(imports, name_imports, all_decls,
                          star_imports)
    if apileaks["modLeaks"] or apileaks["nameLeaks"]:
        print("encapsulation leaks — intended vs real interface "
              "(intra-package reaches not counted):")
        for L in apileaks["modLeaks"][:4]:
            print(f"    {len(L['srcs'])} outside module(s) reach into "
                  f"{L['d']}: {', '.join(L['srcs'][:4])}"
                  + (" …" if len(L["srcs"]) > 4 else ""))
        for L in apileaks["nameLeaks"][:4]:
            what = ("private name" if L["kind"] == "private"
                    else "name outside __all__")
            print(f"    {L['d']}.{L['n']} ({what}) ← "
                  f"{', '.join(L['srcs'][:4])}"
                  + (" …" if len(L["srcs"]) > 4 else ""))
        if apileaks["stars"]:
            print(f"    ({apileaks['stars']} star-import(s) bypass "
                  f"the name audit)")

    dead = _dead_code(modules, callgraph, imported_fns, heat, n_runs)
    if dead["cands"]:
        c = dead["counts"]
        print(f"dead-code evidence: {c['A']} with no static reference "
              f"· {c['B']} importable-surface-only · {c['C']} never "
              f"ran in {n_runs} adopted run(s) — evidence, not proof "
              f"(reflection/plugins/decorators can hide callers):")
        for cd in dead["cands"][:10]:
            print(f"    [{cd['tier']}] {cd['m']}.{cd['n']}  "
                  f"(:{cd['l']}, {cd['k']})")
        if len(dead["cands"]) > 10:
            print(f"    … +{len(dead['cands']) - 10} more on the map")

    graphlens = _graph_lens(modules, imports, heat)
    if graphlens:
        topb = sorted(graphlens["between"].items(),
                      key=lambda kv: (-kv[1], kv[0]))[:3]
        if topb:
            print("graph lens: betweenness (static import graph) — "
                  + ", ".join(f"{v} {c:g}" for v, c in topb)
                  + " route the most import paths")
        ncomm = len(set(graphlens["community"].values()))
        if ncomm:
            print(f"graph lens: {ncomm} detected communities (label "
                  f"propagation) — compare them against the package "
                  f"boxes on the map")

    # #122: the shadowing audit — counts to the terminal, pips on the map
    n_shadow = sum(len(m.get("shadows") or []) for m in modules)
    if n_shadow:
        worst = sorted((m for m in modules if m.get("shadows")),
                       key=lambda m: -len(m["shadows"]))[:4]
        print(f"shadowing audit: {n_shadow} mask(s) — "
              + ", ".join(f"{m['id']} ({len(m['shadows'])})"
                          for m in worst)
              + " — 👥 pips on the map; stdlib-filename cases listed "
                "first")
        for m in modules:
            for kind, nm, det in (m.get("shadows") or []):
                if kind == "stdlib-filename":
                    print(f"    ⚠ {m['id']}: {det}")

    # #96: the declared architecture, checked against every internal
    # import edge — a malformed rules file refuses to enforce
    layers = None
    rules = _load_layers(root_dir, layers_file)
    if rules is not None:
        if rules["errors"]:
            print(f"layers: {rules['file']} has "
                  f"{len(rules['errors'])} problem(s) — NOT enforced "
                  f"(partial rules would pretend the architecture is "
                  f"safe):")
            for msg in rules["errors"][:8]:
                print(f"    {msg}")
            layers = {"file": rules["file"], "errors": rules["errors"],
                      "viol": [], "assign": {}, "unassigned": [],
                      "chains": rules["chains"]}
        else:
            checked = _layer_violations(rules, imports, internal)
            layers = {"file": rules["file"], "errors": [],
                      "chains": rules["chains"],
                      "assign": checked["assign"],
                      "viol": checked["viol"],
                      "unassigned": checked["unassigned"]}
            chain_txt = "; ".join(" -> ".join(c)
                                  for c in rules["chains"])
            print(f"layers ({rules['file']}): {chain_txt or '(no chain)'}"
                  f" · {len(checked['assign'])} module(s) assigned, "
                  f"{len(checked['unassigned'])} outside every layer")
            for v in checked["viol"][:8]:
                print(f"    VIOLATION: {v['s']} imports {v['d']} — "
                      f"{v['rule']}")
            if len(checked["viol"]) > 8:
                print(f"    … {len(checked['viol']) - 8} more")
            if not checked["viol"]:
                print("    no violations — the architecture holds")

    payload = {
        "root": name,
        "rootPath": root,
        "layers": layers,         # #96: declared architecture audit
        "modules": modules,
        "imports": imports,
        "graphlens": graphlens,   # #129, or null on tiny maps
        "cycles": cycles,
        "fan": fan,
        "calls": calls,
        "intra": intra,
        "external": dict(sorted(ext_counts.items(),
                                key=lambda kv: (-kv[1], kv[0]))[:20]),
        "extMissing": ext_missing,
        "unresolvedCalls": unresolved,
        "callgraph": callgraph,   # #94: def→def, resolved/guessed
        "dead": dead,             # #97: the join, tiered, capped
        "apileaks": apileaks,     # #100: the leak audit
        "errors": errors,
        "heat": heat,
        "churn": churn,   # #95: git history lens, or null (no repo)
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
    if check_layers:
        if layers is None:
            print("--check-layers: no .pyreplay-layers file found — "
                  "nothing to check")
            return 2
        if layers["errors"]:
            return 2      # a broken rules file must fail the gate
        if layers["viol"]:
            print(f"--check-layers: {len(layers['viol'])} "
                  f"violation(s) — exit 4")
            return 4
        print("--check-layers: architecture holds — exit 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
