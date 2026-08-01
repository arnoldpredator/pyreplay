#!/usr/bin/env python3
"""pyreplay regression runner — asserts the honesty invariants.

    python3 checks.py            # run everything, green/red table
    python3 checks.py -k window  # only checks whose name contains "window"

Re-runs the tracer over the example suite plus purpose-built fixtures,
re-runs the mapper over tinyshop and (if present) asyncio, extracts the
embedded JSON from each generated HTML, and asserts the properties that
were won in the adversarial-review sessions. Data-level only — no
browser. Exit code 0 = all green.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
TMP = tempfile.mkdtemp(prefix="pyreplay-checks-")
PY = sys.executable

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


class Fail(Exception):
    pass


def expect(cond, msg):
    if not cond:
        raise Fail(msg)


def payload(html_path):
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()
    m = re.search(r'<script id="(?:trace|map)-data" '
                  r'type="application/json">(.*?)</script>', html, re.S)
    expect(m is not None, f"no embedded JSON in {html_path}")
    return json.loads(m.group(1).replace("<\\/", "</"))


def run_trace(script, *flags, stdin_text=None, name=None):
    out = os.path.join(TMP, (name or os.path.basename(script)) + ".html")
    cmd = [PY, os.path.join(HERE, "tracer.py"), "--out", out,
           *flags, script]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=TMP,
                       input=stdin_text, timeout=120)
    expect(os.path.exists(out),
           f"tracer produced no output ({r.stdout} {r.stderr})")
    return payload(out)


def run_map(target, *flags, name="map"):
    out = os.path.join(TMP, name + ".html")
    cmd = [PY, os.path.join(HERE, "mapper.py"), "--out", out,
           *flags, target]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=TMP,
                       timeout=120)
    expect(os.path.exists(out),
           f"mapper produced no output ({r.stdout} {r.stderr})")
    return payload(out)


def fixture(name, source):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(source)
    return path


def changes_of(events, var, fn=None):
    return [e for e in events
            if var in e.get("ch", {}) and (fn is None or e["fn"] == fn)]


# ---------------------------------------------------------------- tracer

@check("bubble: swap count and element diffing")
def _(events=None):
    p = run_trace(os.path.join(HERE, "bubble_sort.py"))
    ch = changes_of(p["events"], "nums", "bubble_sort")
    expect(len(ch) == 6, f"expected birth+5 swaps = 6 nums changes, "
           f"got {len(ch)}")
    last = ch[-1]["ch"]["nums"]
    expect([e["v"] for e in last["v"]] == ["1", "2", "4", "5"],
           f"final nums wrong: {last}")


@check("window/chi: change beyond the head is stamped")
def _():
    fx = fixture("fx_window.py", (
        "big = list(range(2000))\n"
        "big[1500] = -1\n"
        "big.append(7)\n"
        "big[5] = -2\n"))
    evs = run_trace(fx)["events"]
    ch = changes_of(evs, "big")
    expect(len(ch) >= 4, f"expected 4 big changes, got {len(ch)}")
    w = ch[1]["ch"]["big"]
    expect(w.get("off") == 1490 and w.get("chi") == [1500],
           f"1500-window wrong: off={w.get('off')} chi={w.get('chi')}")
    a = ch[2]["ch"]["big"]
    expect(a.get("chi") == [2000], f"append chi wrong: {a.get('chi')}")
    h = ch[3]["ch"]["big"]
    expect(h.get("chi") == [5] and not h.get("off"),
           "head-after-window must carry chi on an offset-free head")


@check("sets: na markers, removal-only suppression")
def _():
    fx = fixture("fx_set.py", (
        "s = set(range(50))\n"
        "s.remove(25)\n"
        "s.add(999)\n"))
    evs = run_trace(fx)["events"]
    ch = changes_of(evs, "s")
    rm = ch[1]["ch"]["s"]
    expect(rm.get("na") == 0 and rm["n"] == 49,
           f"removal-only must stamp na=0: {rm.get('na')} n={rm['n']}")
    ad = ch[2]["ch"]["s"]
    expect(ad.get("na") == 1 and ad["v"][0]["v"] == "999",
           "addition must stamp na=1 with the new element first")


@check("inner truncation: recursive partial recorded honestly")
def _():
    fx = fixture("fx_inner.py", (
        "adj = [[1] * 50, [0], [0]]\n"
        "adj[0][40] = 9\n"          # beyond row0's visible head
        "adj[0] = adj[0][:30]\n"))  # shrink to exactly the head size
    evs = run_trace(fx)["events"]
    ch = changes_of(evs, "adj")
    born = ch[0]["ch"]["adj"]["v"][0]
    expect(born["n"] == 50 and len(born["v"]) == 30,
           f"row0 must record n=50 with 30 shown: n={born['n']}")
    deep = ch[1]["ch"]["adj"]
    expect(deep.get("chi") == [0],
           f"hidden inner mutation must stamp chi=[0]: {deep.get('chi')}")
    # once fully visible, the encoding itself carries the change — the
    # tracer rightly stops shadowing and no chi is needed
    shrunk = ch[2]["ch"]["adj"]["v"][0]
    expect(shrunk["n"] == 30 and len(shrunk["v"]) == 30
           and "chi" not in ch[2]["ch"]["adj"],
           "fully-visible state must be plain (no chi)")


@check("objects: slots+attrs encoded, deep mutation detected, cycles safe")
def _():
    fx = fixture("fx_obj.py", (
        "class G:\n"
        "    __slots__ = ['n', 'adj']\n"
        "    def __init__(self):\n"
        "        self.n = 100\n"
        "        self.adj = [[i] for i in range(100)]\n"
        "class Loop:\n"
        "    def __init__(self):\n"
        "        self.me = self\n"
        "g = G()\n"
        "g.adj[50][0] = 999\n"
        "l = Loop()\n"))
    evs = run_trace(fx)["events"]
    ch = changes_of(evs, "g")
    expect(len(ch) >= 2, "deep mutation inside g.adj must be detected")
    enc = ch[0]["ch"]["g"]
    expect(enc["t"] == "obj" and [p[0] for p in enc["v"]] == ["n", "adj"],
           f"slots attrs wrong: {enc.get('v', [])[:1]}")
    lo = changes_of(evs, "l")[-1]["ch"]["l"]
    expect(lo["t"] == "obj" and lo["v"][0][1]["t"] == "o",
           "self-reference must degrade to opaque, not recurse")


@check("collapse honesty: call events diff attrs vs last observation")
def _():
    # a method-entry re-emission of an object seen before must stamp the
    # HONEST changed-attr list (`cha`, possibly empty) — not re-flag every
    # attribute because the frame is new. A mutation the tracer never saw
    # (scoped-out file) must land in cha on the next observed call.
    fixture("fx_poke.py", (
        "def poke(o):\n"
        "    o.state += 1\n"
        "def poke_and_read(o):\n"
        "    o.state += 1\n"
        "    return o.read()\n"))
    fx = fixture("fx_attrcall.py", (
        "from fx_poke import poke, poke_and_read\n"
        "class Box:\n"
        "    def __init__(self):\n"
        "        self.state = 0\n"
        "        self.k = 1\n"
        "    def read(self):\n"
        "        return self.state\n"
        "b = Box()\n"
        "b.read()\n"
        "poke_and_read(b)\n"
        "poke(b)\n"
        "b.read()\n"))
    evs = run_trace(fx, "--include", "fx_attrcall.py")["events"]
    init = [e for e in evs if e["e"] == "call" and e["fn"] == "__init__"]
    expect(init and "cha" not in init[0]["ch"].get("self", {}),
           "first-ever observation must carry NO cha (everything is new)")
    reads = [e for e in evs if e["e"] == "call" and e["fn"] == "read"
             and "self" in e["ch"]]
    expect(len(reads) == 3, f"expected 3 read() calls, got {len(reads)}")
    expect(reads[0]["ch"]["self"].get("cha") == [],
           f"1st read: object already observed, nothing moved — cha must "
           f"be [], got {reads[0]['ch']['self'].get('cha')!r}")
    expect(reads[1]["ch"]["self"].get("cha") == ["state"],
           f"read from a scoped-OUT frame: the unobserved mutation must "
           f"surface as cha=['state'], "
           f"got {reads[1]['ch']['self'].get('cha')!r}")
    expect(reads[2]["ch"]["self"].get("cha") == [],
           f"3rd read: the poke was already observed at the module line — "
           f"call must be quiet, got {reads[2]['ch']['self'].get('cha')!r}")


@check("aliasing: dict-in-list mutation stamps chi")
def _():
    fx = fixture("fx_alias.py", (
        "rows = [{'x': 0} for _ in range(100)]\n"
        "rows[50]['x'] = 999\n"))
    evs = run_trace(fx)["events"]
    ch = changes_of(evs, "rows")
    expect(len(ch) == 2 and ch[1]["ch"]["rows"].get("chi") == [50],
           f"aliased mutation lost or mis-stamped: "
           f"{[c['ch']['rows'].get('chi') for c in ch]}")


@check("bytearray: index writes visible")
def _():
    fx = fixture("fx_bytes.py", (
        "alive = bytearray(b'\\x01' * 50)\n"
        "alive[40] = 0\n"))
    evs = run_trace(fx)["events"]
    ch = changes_of(evs, "alive")
    w = ch[1]["ch"]["alive"]
    expect(w.get("chi") == [40] and w["c"] == "bytearray",
           f"bytearray write wrong: chi={w.get('chi')} c={w.get('c')}")


@check("exceptions: caught, soft, and propagation chain")
def _():
    p = run_trace(os.path.join(HERE, "example_exceptions.py"))
    exc = [e for e in p["events"] if e["e"] == "exc"]
    kinds = [(e["x"]["t"], e["fn"], e["x"]["soft"]) for e in exc]
    expect(kinds.count(("KeyError", "risky_lookup", False)) == 2,
           f"expected 2 caught KeyErrors: {kinds}")
    expect(("StopIteration", "main", True) in kinds,
           "exhausted next() must be a SOFT StopIteration")
    chain = [e["fn"] for e in exc if e["x"]["t"] == "ValueError"]
    expect(chain == ["parse_age", "main", "<module>"],
           f"propagation chain wrong: {chain}")
    expect("ValueError" in (p.get("error") or ""), "run error not recorded")


@check("verdicts: if / for / except / case")
def _():
    p = run_trace(os.path.join(HERE, "example_control.py"))
    evs = p["events"]
    conds = [(e["l"], e["cond"]) for e in evs if "cond" in e]
    fors = [c for l, c in conds if c.get("k") == "for" and l == 22]
    expect([c["r"] for c in fors] == [True, True, False] and
           fors[-1]["i"] == 2, f"for[3,1] verdicts wrong: {fors}")
    zero = [c for l, c in conds if c.get("k") == "for" and l == 25]
    expect(zero and zero[0]["r"] is False and zero[0]["i"] == 0,
           "0-iteration loop must say exhausted at 0")
    broke = [c for l, c in conds
             if c.get("k") == "for" and l == 28 and c["r"] is False]
    expect(not broke, "broken loop must NOT get an exhausted verdict")
    excs = [(c["x"], c["r"]) for l, c in conds if c.get("k") == "except"]
    expect(("TypeError", False) in excs and
           ("ZeroDivisionError", True) in excs,
           f"except verdicts wrong: {excs}")
    cases = [(c["x"], c["r"]) for l, c in conds if c.get("k") == "case"]
    expect(('"start"', False) in cases and ('"stop"', True) in cases,
           f"case verdicts wrong: {cases}")


@check("linevars: per-line variable inventory present")
def _():
    p = run_trace(os.path.join(HERE, "example_control.py"))
    lv = p["linevars"]["example_control.py"]
    expect("v" in lv.get("22", []) and "total" in lv.get("23", []),
           f"linevars for the loop wrong: {lv.get('22')}, {lv.get('23')}")


@check("line panel: attr mentions — bare use disables narrowing")
def _():
    # `r = s.G + o` narrows s to its mentioned attr; `probe(s) + s.G`
    # uses s BARE on the same line, so no narrowing (the viewer must
    # show the whole object); method mentions are recorded too (the
    # viewer decides what to do with non-state attrs).
    body = (
        "class S:\n"
        "    def __init__(self):\n"
        "        self.G = [1, 2]\n"
        "        self.kappa = 0.3\n"
        "    def step(self):\n"
        "        return 0\n"
        "def probe(x):\n"
        "    return 0\n"
        "s = S()\n"
        "o = [3]\n"
        "r = s.G + o\n"
        "q = probe(s) + len(s.G)\n"
        "w = s.step()\n")
    fx = fixture("fx_lattr.py", body)
    la = run_trace(fx)["lineattrs"]["fx_lattr.py"]
    lines = body.split("\n")
    lno = {frag: i + 1 for i, frag in enumerate(lines)}
    r_l = str(lno["r = s.G + o"])
    q_l = str(lno["q = probe(s) + len(s.G)"])
    w_l = str(lno["w = s.step()"])
    g_l = str(lno["        self.G = [1, 2]"])
    expect(la.get(r_l, {}).get("s") == ["G"],
           f"attr read must narrow: line {r_l} -> {la.get(r_l)!r}")
    expect("s" not in la.get(q_l, {}),
           f"bare use must disable narrowing: line {q_l} -> {la.get(q_l)!r}")
    expect(la.get(w_l, {}).get("s") == ["step"],
           f"method mention recorded: line {w_l} -> {la.get(w_l)!r}")
    expect(la.get(g_l, {}).get("self") == ["G"],
           f"attr TARGET recorded (pre-value matters): {la.get(g_l)!r}")


@check("provenance: static data-flow (target <- sources) per assignment")
def _():
    fx = fixture("fx_dataflow.py", (
        "def f(a, b):\n"
        "    c = a + b\n"
        "    d = c * 2\n"
        "    a, b = b, a\n"
        "    return d + b\n"
        "f(3, 4)\n"))
    df = run_trace(fx, name="dataflow")["dataflow"]["fx_dataflow.py"]
    expect(df.get("2", {}).get("c") == ["a", "b"],
           f"c = a+b should draw from a,b; got {df.get('2')}")
    expect(df.get("3", {}).get("d") == ["c"],
           f"d = c*2 should draw from c; got {df.get('3')}")
    # positional unpack: a, b = b, a  ->  a<-b, b<-a (the swap the panel needs)
    expect(df.get("4") == {"a": ["b"], "b": ["a"]},
           f"swap should be a<-b, b<-a; got {df.get('4')}")
    # data-flow is a LINE-level feature; fn granularity carries none
    expect(run_trace(fx, "--granularity", "fn", name="dataflow_fn")["dataflow"]
           == {}, "fn granularity must carry no dataflow")


@check("tinyshop: trace agrees with the source's semantics")
def _():
    with open(os.path.join(HERE, "tinyshop", "cart.py"),
              encoding="utf-8") as fh:
        bugged = "amount += line" not in fh.read()
    p = run_trace(os.path.join(HERE, "tinyshop", "main.py"),
                  name="tinyshop_main")
    hist = changes_of(p["events"], "self", "total")
    expect(len(hist) >= 4, "history writes missing")
    final = [e for e in p["events"] if "total" in e.get("ch", {})
             and e["fn"] == "main"]
    expect(bool(final), "main's total assignment not traced")
    got = float(final[-1]["ch"]["total"]["v"])
    expected = 48.45 if bugged else 527.70
    expect(abs(got - expected) < 1e-6,
           f"cart.py is {'bugged' if bugged else 'fixed'} but total is "
           f"{got} (expected ~{expected}) — trace and source disagree")


@check("fn granularity: calls only, paired, args, timestamps")
def _():
    fx = fixture("fx_fn.py", (
        "def inner(x):\n"
        "    s = 0\n"
        "    for i in range(50):\n"
        "        s += i\n"
        "    return s + x\n"
        "\n"
        "def outer():\n"
        "    return inner(3) + inner(4)\n"
        "\n"
        "outer()\n"))
    p = run_trace(fx, "--granularity", "fn")
    evs = p["events"]
    expect(p.get("granularity") == "fn", "granularity field missing")
    expect(all(e["e"] in ("call", "return", "exc") for e in evs),
           f"line events leaked into fn mode: "
           f"{ {e['e'] for e in evs} }")
    calls = [e for e in evs if e["e"] == "call"]
    rets = [e for e in evs if e["e"] == "return"]
    expect(len(calls) == 4 and len(rets) == 4,
           f"module+outer+2×inner = 4/4 expected, "
           f"got {len(calls)}/{len(rets)}")
    expect(all("ts" in e and e["ts"] >= 0 for e in evs),
           "every fn event needs a non-negative ts delta")
    ic = next(e for e in calls if e["fn"] == "inner")
    expect(ic["ch"].get("x", {}).get("v") == "3",
           f"shallow args missing on call: {ic['ch']}")
    # return events carry the (shallow) return value — this regressed
    # silently once, when 3b's generator marks restructured _record_fn
    rvals = {e["ret"]["v"] for e in rets if "ret" in e}
    expect(all("ret" in e for e in rets) and "1228" in rvals,
           f"fn returns must carry values: {rvals}")
    # line-granularity traces must NOT pretend to know time
    p2 = run_trace(fx, name="fx_fn_line")
    expect(p2.get("granularity") == "line" and
           all("ts" not in e for e in p2["events"]),
           "line traces must carry no timestamps")


@check("include/exclude: shared scoping in tracer and mapper")
def _():
    os.makedirs(os.path.join(TMP, "scopepkg"), exist_ok=True)
    fixture("scopepkg/a.py", "def fa():\n    return 1\n")
    fixture("scopepkg/b.py", "def fb():\n    return 2\n")
    m = fixture("scopepkg/m.py",
                "import a\nimport b\nprint(a.fa() + b.fb())\n")
    p = run_trace(m, "--include", "a.py", "--include", "m.py",
                  name="scope_trace")
    files = {e["f"] for e in p["events"]}
    expect(files == {"a.py", "m.py"},
           f"tracer scoping wrong: traced {files}")
    expect("b.py" not in p["sources"], "excluded source leaked in")
    mp = run_map(os.path.join(TMP, "scopepkg"), "--exclude", "b.py",
                 name="scope_map")
    ids = {mm["id"] for mm in mp["modules"]}
    expect(ids == {"a", "m"}, f"mapper scoping wrong: {ids}")


@check("time heat: fn traces yield labeled self/cum time")
def _():
    os.makedirs(os.path.join(TMP, "timelab"), exist_ok=True)
    prog = fixture("timelab/prog.py", (
        "import time\n"
        "\n"
        "def slow():\n"
        "    time.sleep(0.05)\n"
        "\n"
        "def fast():\n"
        "    return 1\n"
        "\n"
        "def main():\n"
        "    for _ in range(3):\n"
        "        fast()\n"
        "    slow()\n"
        "\n"
        "main()\n"))
    run_trace(prog, "--granularity", "fn", name="timelab_fn")
    tr = os.path.join(TMP, "timelab_fn.html")
    agg_path = os.path.join(TMP, "agg.json")
    p = run_map(os.path.join(TMP, "timelab"), "--trace", tr,
                "--heat-out", agg_path, name="map_timelab")
    h = p["heat"]
    expect(h["kind"] == "time", f"fn trace must yield time heat: {h['kind']}")
    fns = h["mods"]["prog"]["fns"]
    slow, fast = fns.get("slow", {}), fns.get("fast", {})
    expect(slow.get("tSelf", 0) >= 45000,
           f"slow() self time must include the sleep: {slow.get('tSelf')}")
    expect(fast.get("tCum", 0) < slow.get("tSelf", 1),
           "fast() must cost less than slow()")
    expect(fns.get("main", {}).get("tCum", 0) >= slow.get("tCum", 0),
           "main() cumulative must contain slow()")
    expect(h["script"] == "prog.py", "heat must carry the entry script")
    with open(agg_path, encoding="utf-8") as fh:
        agg = json.load(fh)
    expect(agg["kind"] == "time" and "prog" in agg["mods"],
           "--heat-out aggregate JSON wrong")
    # line trace over the same program must yield COUNT heat
    run_trace(prog, name="timelab_line")
    p2 = run_map(os.path.join(TMP, "timelab"), "--trace",
                 os.path.join(TMP, "timelab_line.html"),
                 name="map_timelab_counts")
    expect(p2["heat"]["kind"] == "counts",
           "line traces must yield count heat, never time")


@check("mro: supplier resolution and cooperative super chain")
def _():
    p = run_trace(os.path.join(HERE, "example_mro.py"))
    mros = [(e["fn"], e["mro"]["s"], e["mro"]["c"][0])
            for e in p["events"] if e.get("mro")]
    expect(("export", "Serializer", "Exporter") in mros,
           f"export must be found on Serializer via Exporter: {mros}")
    chain = [s for fn, s, c0 in mros if fn == "payload"]
    expect(chain == ["ZipMixin", "JsonMixin", "Serializer"],
           f"super() chain suppliers wrong: {chain}")
    exporter_chain = next(e["mro"]["c"] for e in p["events"]
                          if e.get("mro") and e["fn"] == "export")
    expect(exporter_chain[:4] == ["Exporter", "ZipMixin", "JsonMixin",
                                  "Serializer"],
           f"C3 chain wrong: {exporter_chain}")
    # fn granularity carries the same story
    p2 = run_trace(os.path.join(HERE, "example_mro.py"),
                   "--granularity", "fn", name="mro_fn")
    chain2 = [e["mro"]["s"] for e in p2["events"]
              if e.get("mro") and e["fn"] == "payload"]
    expect(chain2 == ["ZipMixin", "JsonMixin", "Serializer"],
           f"fn-mode mro wrong: {chain2}")


@check("per-attr cha: hidden attribute mutation names the attribute")
def _():
    fx = fixture("fx_cha.py", (
        "class G:\n"
        "    __slots__ = ['tag', 'adj']\n"
        "    def __init__(self):\n"
        "        self.tag = 'x'\n"
        "        self.adj = [[i] for i in range(100)]\n"
        "g = G()\n"
        "g.adj[50][0] = 999\n"))
    evs = run_trace(fx)["events"]
    ch = changes_of(evs, "g")
    expect(len(ch) >= 2, "deep obj mutation lost")
    expect(ch[1]["ch"]["g"].get("cha") == ["adj"],
           f"cha must name the mutated attr: {ch[1]['ch']['g'].get('cha')}")


@check("machinery: generator lifecycle, one instance identity")
def _():
    p = run_trace(os.path.join(HERE, "example_machinery.py"))
    gs = [(e["g"]["s"], e["g"]["i"]) for e in p["events"]
          if e.get("g") and e["fn"] == "squares"]
    states = [s for s, i in gs]
    expect(states == ["c", "y", "r", "y", "r", "y", "r", "e"],
           f"squares(3) lifecycle wrong: {states}")
    expect(len({i for s, i in gs}) == 1,
           "one generator must keep ONE instance identity")
    # a resume re-emits the frame's full live state
    resume = next(e for e in p["events"]
                  if e.get("g") and e["g"]["s"] == "r"
                  and e["fn"] == "squares")
    expect("i" in resume["ch"] and "n" in resume["ch"],
           f"resume must re-emit live locals: {list(resume['ch'])}")


@check("machinery: mutation vs rebinding, aliasing groups")
def _():
    p = run_trace(os.path.join(HERE, "example_machinery.py"))
    evs = p["events"]
    # b.append(3): both names flagged, marked as MUTATION, alias group
    mut = next(e for e in evs if e.get("mut") and "a" in e["mut"])
    expect(set(mut["mut"]) >= {"a", "b"},
           f"aliased mutation must mark both names: {mut['mut']}")
    expect(any(set(g) >= {"a", "b"} for g in mut.get("ali", [])),
           f"alias group missing: {mut.get('ali')}")
    # b = [9]: change WITHOUT mutation mark, alias group dissolves
    reb = next(e for e in evs
               if "b" in e.get("ch", {}) and e["l"] > mut["l"]
               and e["fn"] == "<module>" and "a" not in e["ch"])
    expect("b" not in (reb.get("mut") or []),
           "rebinding must NOT be marked as mutation")
    expect(not any(set(g) >= {"a", "b"} for g in reb.get("ali", [])),
           "alias group must dissolve after rebinding")


@check("machinery: closure cells and shared defaults")
def _():
    p = run_trace(os.path.join(HERE, "example_machinery.py"))
    evs = p["events"]
    mk = next(e for e in evs if e["e"] == "call"
              and e["fn"] == "make_counter")
    expect("count" in mk.get("cl", {}).get("c", []),
           f"make_counter must declare its cell var: {mk.get('cl')}")
    bump = next(e for e in evs if e["e"] == "call" and e["fn"] == "bump")
    expect("count" in bump.get("cl", {}).get("f", []),
           f"bump must declare its free var: {bump.get('cl')}")
    sticky = [e for e in evs if e["e"] == "call" and e["fn"] == "sticky"]
    expect(len(sticky) == 2, "two sticky calls expected")
    expect(sticky[1].get("da") == ["bucket"],
           f"second call must flag the shared default: {sticky[1].get('da')}")
    expect(sticky[0].get("da") == ["bucket"],
           "first call uses the shared default too (it IS the object)")


@check("asyncio tasks: lanes, interleaving, per-task stack balance")
def _():
    p = run_trace(os.path.join(HERE, "example_tasks.py"))
    evs = p["events"]
    tasks = {e.get("tk") for e in evs if e.get("tk")}
    expect({"producer", "consumer"} <= tasks,
           f"task lanes missing: {tasks}")
    # the tasks genuinely interleave (lane switches in event order)
    seq = [e["tk"] for e in evs if e.get("tk") in ("producer", "consumer")]
    switches = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    expect(switches >= 2, f"tasks must interleave: {switches} switches")
    # each lane's call/return events bracket like a real thread's —
    # and END balanced (a mis-laned return would leave depth > 0)
    for lane in ("producer", "consumer"):
        depth = 0
        for e in evs:
            if e.get("tk") != lane:
                continue
            if e["e"] == "call":
                depth += 1
            elif e["e"] == "return":
                depth -= 1
                expect(depth >= 0, f"{lane}: return without a call")
        expect(depth == 0,
               f"{lane}: {depth} frame(s) never returned in its lane")
    # a plain sync function called FROM a task joins the task's lane
    # (nested depth — not just the bare coroutine frame)
    mk = [e for e in evs if e["fn"] == "make_item"]
    expect(bool(mk) and all(e.get("tk") == "producer" for e in mk),
           f"sync helper must inherit the task lane: "
           f"{ {e.get('tk') for e in mk} }")
    # the coroutine keeps ONE frame identity across all its resumes
    for lane in ("producer", "consumer"):
        ids = {e["g"]["i"] for e in evs
               if e.get("tk") == lane and e.get("g") and e["fn"] == lane}
        expect(len(ids) == 1,
               f"{lane} must keep one frame identity, got {ids}")
    # a for loop suspended by await must keep counting its iterations
    prod_fors = [e["cond"]["i"] for e in evs
                 if e.get("tk") == "producer" and e.get("cond", {}).get("k")
                 == "for" and e["cond"]["r"]]
    expect(prod_fors == [1, 2, 3],
           f"loop counter must survive suspension: {prod_fors}")
    # fn granularity carries the same lanes
    p2 = run_trace(os.path.join(HERE, "example_tasks.py"),
                   "--granularity", "fn", name="tasks_fn")
    tasks2 = {e.get("tk") for e in p2["events"] if e.get("tk")}
    expect({"producer", "consumer"} <= tasks2,
           f"fn-mode task lanes missing: {tasks2}")
    # a trigger firing INSIDE a task reconstructs the live stack: the
    # task's own frames join its lane, the frames beneath it (module)
    # must stay unmarked — not dragged into the task's lane
    with open(os.path.join(HERE, "example_tasks.py"),
              encoding="utf-8") as fh:
        src = fh.read().splitlines()
    await_line = next(i + 1 for i, l in enumerate(src)
                      if "sleep(0.01)" in l)
    p3 = run_trace(os.path.join(HERE, "example_tasks.py"),
                   "--start-at", f"example_tasks.py:{await_line}",
                   name="tasks_trig")
    recon = [(e["fn"], e.get("tk")) for e in p3["events"][:4]
             if e["e"] == "call"]
    expect(("<module>", None) in recon and
           ("producer", "producer") in recon,
           f"trigger-in-task reconstruction mis-laned: {recon}")


@check("perfetto: B/E pairing, task lanes, real durations, refusal")
def _():
    os.makedirs(os.path.join(TMP, "pflab"), exist_ok=True)
    prog = fixture("pflab/prog.py", (
        "import time\n"
        "def slow():\n"
        "    time.sleep(0.05)\n"
        "def main():\n"
        "    slow()\n"
        "main()\n"))
    pf = os.path.join(TMP, "pf.json")
    run_trace(prog, "--granularity", "fn", "--export-perfetto", pf,
              name="pf_fn")
    with open(pf, encoding="utf-8") as fh:
        data = json.load(fh)
    tevs = data["traceEvents"]
    meta = {e["name"] for e in tevs if e["ph"] == "M"}
    expect({"process_name", "thread_name"} <= meta,
           f"lane/process metadata missing: {meta}")
    slices = [e for e in tevs if e["ph"] in ("B", "E")]
    ts = [e["ts"] for e in slices]
    expect(all(a <= b for a, b in zip(ts, ts[1:])),
           "timestamps must never go backwards")
    # stack discipline: every E closes the matching B, nothing dangles
    stacks = {}
    for e in slices:
        st = stacks.setdefault(e["tid"], [])
        if e["ph"] == "B":
            st.append(e["name"])
        else:
            expect(st and st[-1] == e["name"],
                   f"E '{e['name']}' does not close the open B "
                   f"({st[-1:] or 'empty'})")
            st.pop()
    expect(all(not st for st in stacks.values()), "unclosed B slices")
    # slow()'s slice really spans the sleep
    bi = next(i for i, e in enumerate(slices)
              if e["ph"] == "B" and e["name"] == "slow")
    ei = next(i for i in range(bi + 1, len(slices))
              if slices[i]["tid"] == slices[bi]["tid"])
    expect(slices[ei]["ph"] == "E" and
           slices[ei]["ts"] - slices[bi]["ts"] >= 45000,
           f"slow() slice must span the 50ms sleep: "
           f"{slices[ei]['ts'] - slices[bi]['ts']} µs")
    # tasks become named perfetto lanes — and the INTERESTING pairing
    # case (suspend/resume slices) must obey stack discipline too
    pf2 = os.path.join(TMP, "pf_tasks.json")
    run_trace(os.path.join(HERE, "example_tasks.py"),
              "--granularity", "fn", "--export-perfetto", pf2,
              name="pf_tasks")
    with open(pf2, encoding="utf-8") as fh:
        tevs2 = json.load(fh)["traceEvents"]
    lanes = {e["tid"]: e["args"]["name"] for e in tevs2
             if e["ph"] == "M" and e["name"] == "thread_name"}
    expect(any("producer" in l for l in lanes.values()) and
           any("consumer" in l for l in lanes.values()),
           f"task lanes missing from perfetto: {set(lanes.values())}")
    stacks2 = {}
    for e in tevs2:
        if e["ph"] not in ("B", "E"):
            continue
        st = stacks2.setdefault(e["tid"], [])
        if e["ph"] == "B":
            st.append(e["name"])
        else:
            expect(st and st[-1] == e["name"],
                   f"task-lane E '{e['name']}' mismatches open B "
                   f"({st[-1:] or 'empty'})")
            st.pop()
            expect("(unclosed)" not in e.get("args", {}),
                   "a completed run must not need artificial closes")
    expect(all(not st for st in stacks2.values()),
           "unclosed slices in the tasks export")
    prod_tid = next(t for t, l in lanes.items() if "producer" in l)
    bnames = [e["name"] for e in tevs2
              if e["ph"] == "B" and e["tid"] == prod_tid]
    expect(bnames.count("producer") == 4,
           f"producer = call + 3 resumes = 4 slices: {bnames}")
    expect(bnames.count("make_item") == 3,
           f"3 nested make_item slices expected in the lane: {bnames}")
    # line granularity must refuse UP FRONT (before tracing anything) —
    # its wall times would be fiction
    xj = os.path.join(TMP, "pf_refused.json")
    xo = os.path.join(TMP, "pf_refused.html")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--out", xo, "--export-perfetto", xj, prog],
                       capture_output=True, text=True, cwd=TMP, timeout=60)
    expect(r.returncode == 2 and "needs --granularity fn" in r.stdout
           and not os.path.exists(xj) and not os.path.exists(xo),
           "line-granularity export must be refused before running")


@check("monitoring backend: event-for-event parity with settrace")
def _():
    if not hasattr(sys, "monitoring"):
        return   # PEP 669 needs 3.12+ — skip silently on older Pythons
    fx = fixture("fx_backend.py", (
        "import time\n"
        "def slow():\n"
        "    time.sleep(0.01)\n"
        "def gen(n):\n"
        "    for i in range(n):\n"
        "        yield i * 2\n"
        "def boom():\n"
        "    raise ValueError('x')\n"
        "def main():\n"
        "    slow()\n"
        "    total = sum(gen(3))\n"
        "    try:\n"
        "        boom()\n"
        "    except ValueError:\n"
        "        pass\n"
        "    try:\n"
        "        next(iter([]))\n"
        "    except StopIteration:\n"
        "        pass\n"
        "    return total\n"
        "main()\n"))

    def skel(p):
        # everything semantic; timestamps and line numbers excluded
        return [(e["e"], e["fn"], (e.get("g") or {}).get("s"),
                 tuple(sorted(e.get("ch", {}))),
                 (e.get("ret") or {}).get("v"),
                 (e.get("x") or {}).get("t"),
                 (e.get("x") or {}).get("soft"))
                for e in p["events"]]

    p1 = run_trace(fx, "--granularity", "fn", name="be_settrace")
    p2 = run_trace(fx, "--granularity", "fn", "--backend", "monitoring",
                   name="be_monitoring")
    s1, s2 = skel(p1), skel(p2)
    diff = [f"  {a}  !=  {b}" for a, b in zip(s1, s2) if a != b]
    expect(s1 == s2,
           f"backends disagree ({len(s1)} vs {len(s2)} events):\n"
           + "\n".join(diff[:8]))
    expect(sum(e["ts"] for e in p2["events"]) >= 10000,
           "monitoring events must carry the real 10ms sleep")
    # line granularity keeps the settrace engine — refuse up front
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--backend", "monitoring", fx],
                       capture_output=True, text=True, cwd=TMP, timeout=60)
    expect(r.returncode == 2 and "settrace" in r.stdout,
           "monitoring at line granularity must be refused")


@check("monitoring backend: reraise / stop-iteration parity with settrace")
def _():
    # guards the fix for the RERAISE double-count and the STOP_ITERATION
    # under-count: exceptions crossing a finally / bare re-raise / new-exc-
    # in-except, generator .close()/.throw() teardown, yield-from and await
    # completion. Each is a place the monitoring backend once disagreed with
    # settrace by an exc event or a generator lifecycle scope.
    if not hasattr(sys, "monitoring"):
        return
    fx = fixture("fx_backend_exc.py", (
        "import asyncio\n"
        "def inner():\n"
        "    raise KeyError('k')\n"
        "def reraise_bare():\n"
        "    try: inner()\n"
        "    except KeyError: raise\n"
        "def reraise_finally():\n"
        "    try: inner()\n"
        "    finally: pass\n"
        "def new_in_except():\n"
        "    try: inner()\n"
        "    except KeyError: raise ValueError('v')\n"
        "def gen_close():\n"
        "    def g():\n"
        "        try:\n"
        "            yield 1\n"
        "            yield 2\n"
        "        finally: pass\n"
        "    it = g(); next(it); it.close()\n"
        "def gen_throw():\n"
        "    def g():\n"
        "        yield 1\n"
        "        yield 2\n"
        "    it = g(); next(it)\n"
        "    try: it.throw(RuntimeError('r'))\n"
        "    except RuntimeError: pass\n"
        "def sub():\n"
        "    yield 1\n"
        "    return 'end'\n"
        "def delegate():\n"
        "    r = yield from sub()\n"
        "    yield r\n"
        "async def coro():\n"
        "    await asyncio.sleep(0)\n"
        "    return 1\n"
        "def main():\n"
        "    for f in (reraise_bare, reraise_finally, new_in_except):\n"
        "        try: f()\n"
        "        except (KeyError, ValueError): pass\n"
        "    gen_close()\n"
        "    gen_throw()\n"
        "    list(delegate())\n"
        "    asyncio.run(coro())\n"
        "main()\n"))

    def skel(p):
        rows = []
        for e in p["events"]:
            # object reprs carry heap addresses that differ across processes
            v = re.sub(r"0x[0-9a-fA-F]+", "0x",
                       str((e.get("ret") or {}).get("v")))
            rows.append((e["e"], e["fn"], (e.get("g") or {}).get("s"),
                         tuple(sorted(e.get("ch", {}))), v,
                         (e.get("x") or {}).get("t"),
                         (e.get("x") or {}).get("soft")))
        return rows

    p1 = run_trace(fx, "--granularity", "fn", name="beexc_settrace")
    p2 = run_trace(fx, "--granularity", "fn", "--backend", "monitoring",
                   name="beexc_monitoring")
    s1, s2 = skel(p1), skel(p2)
    diff = [f"  set {a}\n  mon {b}" for a, b in zip(s1, s2) if a != b]
    expect(s1 == s2,
           f"reraise/stop-iteration parity broke ({len(s1)} vs {len(s2)} "
           f"events):\n" + "\n".join(diff[:8]))
    # concrete guard on the headline bug: an exception crossing a finally is
    # recorded ONCE per frame, not once per RERAISE the interpreter fires
    once = [e for e in p2["events"]
            if e["fn"] == "reraise_finally" and e["e"] == "exc"]
    expect(len(once) == 1,
           f"reraise_finally must record its exc once, got {len(once)}")


@check("module entry: -m runs a module, --root scopes it (#21)")
def _():
    # a package whose __main__ imports a sibling and calls it — the stand-in
    # for "run the test suite" without needing pytest installed in this env
    base = os.path.join(TMP, "m21")
    pkg = os.path.join(base, "proj")
    os.makedirs(pkg, exist_ok=True)
    open(os.path.join(pkg, "__init__.py"), "w").close()
    with open(os.path.join(pkg, "lib.py"), "w") as fh:
        fh.write("def work(n):\n    total = 0\n    for i in range(n):\n"
                 "        total += i\n    return total\n")
    # __main__ records its OWN argv (proves module-arg passthrough) then works
    argv_sentinel = os.path.join(base, "argv.txt")
    with open(os.path.join(pkg, "__main__.py"), "w") as fh:
        fh.write("import sys, json\nfrom proj.lib import work\n"
                 f"open({argv_sentinel!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
                 "print(work(5))\n")

    def run_m(*args, cwd=base):
        return subprocess.run([PY, os.path.join(HERE, "tracer.py"), *args],
                              capture_output=True, text=True, cwd=cwd,
                              timeout=60)

    # -m runs the module as __main__; --root keeps the scope on the project;
    # trailing args after the module name reach the module's own sys.argv
    out = os.path.join(TMP, "m21.html")
    r = run_m("--out", out, "--granularity", "fn", "--root", base,
              "-m", "proj", "alpha", "beta")
    expect(os.path.exists(out), f"-m proj produced no trace ({r.stdout}{r.stderr})")
    p = payload(out)
    fns = {e["fn"] for e in p["events"] if e["e"] == "call"}
    expect("work" in fns, f"-m must trace the project's own code, got {fns}")
    expect(p["script"] == "-m proj", f"entry label wrong: {p['script']!r}")
    expect(any(s.endswith("lib.py") for s in p["sources"]),
           "the project's lib.py must be captured under --root")
    with open(argv_sentinel) as fh:
        passed = json.load(fh)
    expect(passed == ["alpha", "beta"],
           f"args after the module name must reach its sys.argv, got {passed}")

    # -m + --export-perfetto must BOTH produce the html AND the perfetto json
    # (regression: script is None in -m mode — the export must not crash on it)
    pf = os.path.join(TMP, "m21.perfetto.json")
    rp = run_m("--out", os.path.join(TMP, "m21pf.html"), "--granularity", "fn",
               "--export-perfetto", pf, "--root", base, "-m", "proj")
    expect(rp.returncode == 0 and os.path.exists(pf),
           f"-m + --export-perfetto must write the json cleanly "
           f"(rc={rp.returncode}) {rp.stdout[-300:]}{rp.stderr[-300:]}")

    # --root DECOUPLES scope from the entry's own folder: an entry outside
    # root must NOT widen the trace to itself
    os.makedirs(os.path.join(base, "outside"), exist_ok=True)
    drive = os.path.join(base, "outside", "drive.py")
    with open(drive, "w") as fh:
        fh.write(f"import sys\nsys.path.insert(0, {base!r})\n"
                 "from proj.lib import work\nprint(work(4))\n")
    out2 = os.path.join(TMP, "m21b.html")
    run_m("--out", out2, "--granularity", "fn", "--root", pkg, drive)
    srcs = list(payload(out2)["sources"])
    expect(any(s.endswith("lib.py") for s in srcs)
           and not any("drive.py" in s for s in srcs),
           f"--root must scope to the pkg and exclude the out-of-root entry; {srcs}")

    # refusals (each exits 2, no trace): a bad top-level module, a bad
    # DOTTED submodule (top pkg exists, leaf doesn't), and a missing --root
    rb = run_m("-m", "no_such_module_zzz")
    expect(rb.returncode == 2 and "not importable" in rb.stdout,
           f"bad -m module must refuse, got rc={rb.returncode} {rb.stdout!r}")
    rsub = run_m("--root", base, "-m", "proj.does_not_exist")
    expect(rsub.returncode == 2 and "not importable" in rsub.stdout,
           f"bad -m submodule must refuse, got rc={rsub.returncode} {rsub.stdout!r}")
    rr = run_m("--root", os.path.join(base, "nope"), "-m", "proj")
    expect(rr.returncode == 2 and "directory" in rr.stdout,
           f"missing --root dir must refuse, got rc={rr.returncode} {rr.stdout!r}")


@check("trace doctor: -m defaults fn, dep hints, heartbeat")
def _():
    base = os.path.join(TMP, "doctor")
    pkg = os.path.join(base, "proj")
    os.makedirs(pkg, exist_ok=True)
    open(os.path.join(pkg, "__init__.py"), "w").close()
    with open(os.path.join(pkg, "lib.py"), "w") as fh:
        fh.write("def work(n):\n    return sum(range(n))\n")
    with open(os.path.join(pkg, "__main__.py"), "w") as fh:
        fh.write("from proj.lib import work\nprint(work(5))\n")

    def run_t(*args, env_extra=None):
        env = dict(os.environ, **(env_extra or {}))
        return subprocess.run([PY, os.path.join(HERE, "tracer.py"), *args],
                              capture_output=True, text=True, cwd=base,
                              env=env, timeout=60)

    def gran(out):
        return payload(out)["granularity"]

    # -m defaults to fn (announced); an explicit line + trigger stays line
    o1 = os.path.join(TMP, "doc1.html")
    r1 = run_t("--out", o1, "--root", base, "-m", "proj")
    expect("default to --granularity fn" in r1.stdout and gran(o1) == "fn",
           f"-m must default to fn, got {gran(o1)} / {r1.stdout[:200]!r}")
    o2 = os.path.join(TMP, "doc2.html")
    run_t("--out", o2, "--root", base, "--start-at", "lib.py:2", "-m", "proj")
    expect(gran(o2) == "line", "-m with --start-at must stay line-level")
    # script entries still default to line
    plain = os.path.join(base, "plain.py")
    with open(plain, "w") as fh:
        fh.write("x = 1\nprint(x)\n")
    o3 = os.path.join(TMP, "doc3.html")
    run_t("--out", o3, plain)
    expect(gran(o3) == "line", "script entries must keep the line default")

    # missing-import preflight BEFORE the run + pip hint AFTER the crash
    needs = os.path.join(base, "needs.py")
    with open(needs, "w") as fh:
        fh.write("import zzqx_not_installed\nprint('never')\n")
    r4 = run_t("--out", os.path.join(TMP, "doc4.html"), needs)
    expect("heads-up" in r4.stdout and "pip install zzqx_not_installed"
           in r4.stdout, f"preflight must name the pip line: {r4.stdout!r}")
    expect("hint:" in r4.stdout,
           "the import crash must print the install hint")

    # heartbeat: a slow run reports life on stderr at the tuned interval
    slow = os.path.join(base, "slow.py")
    with open(slow, "w") as fh:
        fh.write("import time\ntime.sleep(2.2)\nprint('done')\n")
    r5 = run_t("--out", os.path.join(TMP, "doc5.html"), slow,
               env_extra={"PYREPLAY_HEARTBEAT": "1"})
    expect("still tracing" in r5.stderr,
           f"heartbeat missing from stderr: {r5.stderr[:200]!r}")


@check("trace doctor: --doctor reports setup, runs nothing (#22)")
def _():
    base = os.path.join(TMP, "doccli")
    os.makedirs(os.path.join(base, "pkg"), exist_ok=True)
    open(os.path.join(base, "pkg", "__init__.py"), "w").close()
    with open(os.path.join(base, "pkg", "mod.py"), "w") as fh:
        fh.write("import zzqx_totally_absent\n")
    with open(os.path.join(base, "pyproject.toml"), "w") as fh:
        fh.write('[tool.pytest.ini_options]\naddopts = """\n'
                 '  -q\n  -n 2 --dist worksteal\n"""\n')
    marker = os.path.join(base, "RAN.txt")
    entry = os.path.join(base, "entry.py")
    with open(entry, "w") as fh:
        fh.write(f"open({marker!r}, 'w').write('x')\n")

    def run_d(*args):
        return subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                               "--doctor", *args],
                              capture_output=True, text=True, cwd=base,
                              timeout=60)

    # benign entry: codebase misses a dep (advisory), but NOTHING runs and
    # nothing is written; a packaged root gets the editable one-shot
    r = run_d("--root", base, entry)
    expect(r.returncode == 0, f"advisory-only doctor must exit 0: "
           f"rc={r.returncode} {r.stdout!r}")
    expect("zzqx_totally_absent" in r.stdout,
           "the codebase scan must name the missing dep")
    expect("pip install -e" in r.stdout,
           "a packaged root must get the editable install recipe")
    expect(not os.path.exists(marker), "--doctor must NOT run the target")
    expect(not any(f.startswith("trace_") for f in os.listdir(base)),
           "--doctor must not write a trace")

    # an entry that itself imports the missing module is a BLOCKER, exit 3
    bad = os.path.join(base, "bad_entry.py")
    with open(bad, "w") as fh:
        fh.write("import zzqx_totally_absent\n")
    rb = run_d("--root", base, bad)
    expect(rb.returncode == 3 and "BLOCKER" in rb.stdout,
           f"blocked entry must exit 3: rc={rb.returncode}")

    # -m pytest: the forced-xdist config (multi-line TOML addopts) is
    # flagged with the -n0 advice
    rp = run_d("--root", base, "-m", "pytest")
    expect("addopts" in rp.stdout and "-n0" in rp.stdout,
           f"forced xdist must be flagged with -n0 advice: {rp.stdout!r}")


@check("watch: in-process bracket, exception, cap survival, once (#24)")
def _():
    base = os.path.join(TMP, "watchlab")
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, "helper.py"), "w") as fh:
        fh.write("def triple(x):\n    y = x * 3\n    return y\n")
    host = os.path.join(base, "host.py")
    with open(host, "w") as fh:
        fh.write(f"""\
import sys
sys.path.insert(0, {HERE!r})
from tracer import watch
from helper import triple

with watch(out="t_block.html"):          # block lines + called fn
    a = 2
    b = triple(a)

try:                                      # exception: recorded + re-raised
    with watch(out="t_exc.html"):
        raise ValueError("boom")
except ValueError:
    pass

with watch(out="t_cap.html", max_events=5):   # cap: host must survive
    total = 0
    for i in range(200):
        total += i
open("SURVIVED.txt", "w").write(str(total))

with watch(out="t_outer.html"):           # nested inner is a no-op
    with watch(out="t_inner.html"):
        z = triple(3)

@watch()                                  # decorator: first call only
def deco(x):
    return x + 1
deco(1); deco(2)
""")
    # the whole point of #24: run with PLAIN python, not under tracer.py
    r = subprocess.run([PY, host], capture_output=True, text=True,
                       cwd=base, timeout=60)
    expect(r.returncode == 0,
           f"host must run to completion: {r.stderr[-300:]}")

    p1 = payload(os.path.join(base, "t_block.html"))
    fns = {e["fn"] for e in p1["events"]}
    expect("triple" in fns and "<module>" in fns,
           f"block must capture its own lines AND the called fn: {fns}")
    expect(p1["granularity"] == "line" and p1["dataflow"],
           "watch defaults to line granularity with provenance dataflow")
    expect(p1["script"].startswith("watch @ host.py:"),
           f"entry label wrong: {p1['script']!r}")

    p2 = payload(os.path.join(base, "t_exc.html"))
    expect(p2["error"] == "ValueError: boom",
           f"block exception must be recorded: {p2['error']!r}")

    p3 = payload(os.path.join(base, "t_cap.html"))
    survived = open(os.path.join(base, "SURVIVED.txt")).read()
    expect(p3["truncated"] and len(p3["events"]) <= 5
           and survived == "19900",
           f"cap must stop recording but NOT the host "
           f"(events={len(p3['events'])}, survived={survived!r})")

    expect(os.path.exists(os.path.join(base, "t_outer.html"))
           and not os.path.exists(os.path.join(base, "t_inner.html")),
           "nested watch must no-op; outer trace must still be written")

    wd = [f for f in os.listdir(base) if f.startswith("trace_watch")]
    expect(len(wd) == 1
           and payload(os.path.join(base, wd[0]))["script"]
           == "watch @ deco()",
           f"decorator must record the FIRST call only: {wd}")


@check("trip: NaN/Inf births marked at kind changes, recovery re-arms (#79)")
def _():
    fx = fixture("fx_trip.py", (
        "def f():\n"
        "    return float('nan')\n"
        "a = 1.0\n"
        "a = a * 1e308 * 10\n"                        # inf birth
        "a = 2.0\n"                                    # recovery
        "a = a * 1e308 * 10\n"                        # relapse: marks again
        "a = a - a\n"                                  # inf -> nan: NEW birth
        "b = [0.0, float('inf') - float('inf')]\n"    # nan inside a container
        "c = f()\n"                                    # nan via return value
        "d = 5\n"))
    p = run_trace(fx, "--trip", "nan", name="fx_trip_on")
    expect(p["trip"] == "nan", "payload must carry the trip mode")
    seq = [(t["v"], t["k"]) for e in p["events"]
           for t in e.get("trip", [])]
    expect(seq == [("a", "inf"), ("a", "inf"), ("a", "nan"),
                   ("b", "nan"), ("<return>", "nan"), ("c", "nan")],
           f"trip sequence wrong: {seq}")
    p2 = run_trace(fx, name="fx_trip_off")
    expect(p2["trip"] is None
           and not any(e.get("trip") for e in p2["events"]),
           "no --trip flag must mean no trip marks (unmeasured = unmarked)")
    # sleeping generators keep their poison memory: a yield must not
    # re-mark on resume, only the true birth marks
    fx2 = fixture("fx_trip_gen.py", (
        "def g():\n"
        "    x = float('nan')\n"
        "    yield 1\n"
        "    x = x + 0\n"                   # still nan: NOT a new birth
        "    yield 2\n"
        "for _ in g():\n"
        "    pass\n"))
    p3 = run_trace(fx2, "--trip", "nan", name="fx_trip_gen")
    gseq = [(t["v"], t["k"]) for e in p3["events"]
            for t in e.get("trip", []) if e["fn"] == "g"]
    expect(gseq == [("x", "nan")],
           f"generator poison must mark ONCE across yields: {gseq}")


@check("deep links: fragment state machinery wired into the artifact")
def _():
    # #106 is renderer-side (URL fragment -> viewer state), so the
    # data-level guard is structural: every generated trace must carry
    # the read path (applyHash at load + on hashchange) and the write
    # path (updateHash called from render). Behavior itself is verified
    # in the browser; this stops the wiring from silently vanishing.
    fx = fixture("fx_deeplink.py", "x = 1\nx = 2\n")
    run_trace(fx)                       # writes fx_deeplink.py.html in TMP
    with open(os.path.join(TMP, "fx_deeplink.py.html"),
              encoding="utf-8") as fh:
        html = fh.read()
    for needle, why in [
        ("function applyHash", "hash parser missing"),
        ("function updateHash", "hash writer missing"),
        ('addEventListener("hashchange"', "hashchange path missing"),
        ("applyHash(); render();", "load path must parse the hash first"),
        ("updateHash();", "render must publish state to the fragment"),
    ]:
        expect(needle in html, f"deep links: {why} ({needle!r})")


# ---------------------------------------------------------------- mapper

@check("map tinyshop: modules, imports, classes, bases")
def _():
    p = run_map(os.path.join(HERE, "tinyshop"), name="map_tinyshop")
    ids = {m["id"] for m in p["modules"]}
    expect(ids == {"main", "cart", "discounts"}, f"modules wrong: {ids}")
    edges = {(e["s"], e["d"]) for e in p["imports"]}
    expect(("main", "cart") in edges and ("cart", "discounts") in edges,
           f"import edges wrong: {edges}")
    cart = next(m for m in p["modules"] if m["id"] == "cart")
    cls = [d for d in cart["defs"] if d["k"] == "class"]
    expect(len(cls) == 1 and cls[0]["n"] == "Cart", "Cart class missing")


@check("map heat: order, attribution, def-statement exclusion")
def _():
    tr = os.path.join(TMP, "tinyshop_main.html")
    if not os.path.exists(tr):
        run_trace(os.path.join(HERE, "tinyshop", "main.py"),
                  name="tinyshop_main")
    p = run_map(os.path.join(HERE, "tinyshop"), "--trace", tr,
                name="map_tinyshop_heat")
    h = p["heat"]["mods"]
    expect(set(h) == {"main", "cart", "discounts"}, f"heat mods: {set(h)}")
    expect(h["main"]["first"] < h["cart"]["first"] < h["discounts"]["first"],
           "execution order wrong")
    expect(h["cart"]["fns"].get("Cart.total", {}).get("n", 0) > 10,
           "Cart.total attribution missing")
    expect(p["heat"]["unmatched"] == 0, "events leaked outside the map")


def _map_invariants(p):
    """Structural facts of the map payload that hold by construction —
    the viewer depends on every one of them."""
    ids = {m["id"] for m in p["modules"]}
    expect(set(p["fan"]) == ids, "fan must cover every module id")
    si = sum(f["i"] for f in p["fan"].values())
    so = sum(f["o"] for f in p["fan"].values())
    expect(si == so == len(p["imports"]),
           f"fan totals must equal the edge count: {si}/{so}/"
           f"{len(p['imports'])}")
    seen = set()
    for c in p["cycles"]:
        expect(set(c) <= ids, f"cycle names unknown module: {c}")
        expect(not (set(c) & seen),
               "cycles must be DISJOINT SCCs, not overlapping rings")
        seen |= set(c)
    expect(all("pkg" in m for m in p["modules"]),
           "every module must carry its package field")


@check("map depth: packages, cycles, fan — mixed-language safe")
def _():
    d = os.path.join(TMP, "mixpkg")
    os.makedirs(os.path.join(d, "pkg", "sub"), exist_ok=True)
    os.makedirs(os.path.join(d, "nspkg"), exist_ok=True)
    os.makedirs(os.path.join(d, "shadow"), exist_ok=True)
    fixture("mixpkg/main.py", "import pkg.a\nimport pkg.sub.b\n")
    # an __init__ that IMPORTS, via a relative import
    fixture("mixpkg/pkg/__init__.py", "from . import a\n")
    fixture("mixpkg/pkg/a.py", "import pkg.sub.b\n")
    fixture("mixpkg/pkg/sub/__init__.py", "")
    # a level-2 relative import ("from .. import a")
    fixture("mixpkg/pkg/sub/b.py", "from .. import a as pa\nX = 1\n")
    # a relative import that climbs OUT of the mapped root: must
    # produce NO edge (re-anchoring would fabricate one)
    fixture("mixpkg/pkg/sub/esc.py", "from ....far import zzz\n")
    fixture("mixpkg/pkg/c1.py", "import pkg.c2\n")
    fixture("mixpkg/pkg/c2.py", "import pkg.c1\n")
    fixture("mixpkg/r1.py", "import r2\n")
    fixture("mixpkg/r2.py", "import r3\n")
    fixture("mixpkg/r3.py", "import r1\n")
    # interlocking rings t1<->t2, t2<->t3: ONE SCC of three — this is
    # what separates real Tarjan from naive ring enumeration
    fixture("mixpkg/t1.py", "import t2\n")
    fixture("mixpkg/t2.py", "import t1\nimport t3\n")
    fixture("mixpkg/t3.py", "import t2\n")
    # namespace package (PEP 420, no __init__.py): from-imports must
    # still resolve per name, and 'nspkg' must NOT be marked external
    fixture("mixpkg/nspkg/x.py", "from nspkg import y\n")
    fixture("mixpkg/nspkg/y.py", "Y = 1\n")
    # three spellings of the same dependency: ONE edge (set dedup)
    fixture("mixpkg/dup.py",
            "import pkg.a\nfrom pkg import a\nfrom pkg import a as a2\n")
    # foo.py shadowed by foo/ package: the package owns the id
    fixture("mixpkg/shadow.py", "import r1\n")
    fixture("mixpkg/shadow/__init__.py", "import r2\n")
    # external deps: one stdlib (importable), one that surely isn't —
    # the map must warn about missing deps BEFORE anyone runs a trace
    fixture("mixpkg/needs.py",
            "import os\nimport msvcrt\n"       # Windows-only stdlib
            "import zzz_surely_not_installed_xyz\n")
    # the mixed-language reality: these must be ignored / survived,
    # never crashed on (the projects we map carry C++ and Cython)
    fixture("mixpkg/native.cpp",
            "#include <vector>\nint main() { return 0; }\n")
    fixture("mixpkg/speed.pyx", "cdef int f(int x):\n    return x * 2\n")
    fixture("mixpkg/legacy.py", "print 'python 2'\n")
    p = run_map(d, name="map_mixpkg")
    _map_invariants(p)
    byid = {m["id"]: m for m in p["modules"]}
    # non-Python files never become modules; broken Python is flagged
    expect("native" not in byid and "speed" not in byid,
           "C++/Cython files must not appear as modules")
    expect(byid["legacy"]["err"] is True and len(p["errors"]) == 1,
           "the Python-2 file must be flagged as a parse error, not die")
    # pkg fields: __init__ belongs to its OWN box, members to theirs
    pk = {m: byid[m]["pkg"] for m in byid}
    expect(pk["main"] == "" and pk["pkg"] == "pkg" and
           pk["pkg.a"] == "pkg" and pk["pkg.sub"] == "pkg.sub" and
           pk["pkg.sub.b"] == "pkg.sub" and pk["r1"] == "" and
           pk["nspkg.x"] == "nspkg",
           f"pkg fields wrong: {pk}")
    # shadowed file: unique ids, package wins the plain name
    expect("shadow" in byid and "shadow (shadowed)" in byid and
           len(byid) == len(p["modules"]),
           "foo.py next to foo/ must get a distinct id, never merge")
    edges = {(e["s"], e["d"]) for e in p["imports"]}
    # relative imports anchor correctly (both levels)
    expect(("pkg", "pkg.a") in edges and
           ("pkg.sub.b", "pkg.a") in edges and
           ("pkg.sub.b", "pkg") in edges,
           f"relative-import edges wrong: {sorted(edges)}")
    # namespace-package from-import resolves; nothing marked external
    expect(("nspkg.x", "nspkg.y") in edges,
           "namespace-package from-import edge lost")
    expect("nspkg" not in p["external"] and "far" not in p["external"],
           f"internal/unknowable marked external: {p['external']}")
    # dependency preflight: the missing dep is flagged; stdlib never is
    # (msvcrt is stdlib-on-Windows — a platform guard, not a pip need)
    expect("zzz_surely_not_installed_xyz" in p["extMissing"] and
           "os" not in p["extMissing"] and
           "msvcrt" not in p["extMissing"],
           f"missing-dep detection wrong: {p['extMissing']}")
    # the escape-above-root import fabricates nothing
    expect(not any(s == "pkg.sub.esc" for s, _ in edges),
           "an import climbing out of the root must produce NO edge")
    # dedup: three spellings, one edge each to pkg and pkg.a
    dup_edges = [e for e in p["imports"] if e["s"] == "dup"]
    expect(sorted((e["s"], e["d"]) for e in dup_edges) ==
           [("dup", "pkg"), ("dup", "pkg.a")],
           f"import dedup broken: {dup_edges}")
    # cycles: exactly the four planted SCCs. The first spans TWO
    # packages and exists because pkg/__init__ imports a, a imports
    # sub.b, and sub.b's "from .. import a" points back at pkg — the
    # classic partially-initialized-package cycle. The interlocked
    # t-rings MERGE into one component (real Tarjan, not naive rings).
    expect(p["cycles"] == [["pkg", "pkg.a", "pkg.sub.b"],
                           ["pkg.c1", "pkg.c2"], ["r1", "r2", "r3"],
                           ["t1", "t2", "t3"]],
           f"cycles wrong: {p['cycles']}")
    fan = p["fan"]
    expect(fan["pkg.a"] == {"i": 4, "o": 1} and
           fan["pkg.sub.b"] == {"i": 2, "o": 2} and
           fan["main"] == {"i": 0, "o": 2} and
           fan["t2"] == {"i": 2, "o": 2} and
           fan["pkg.sub.esc"] == {"i": 0, "o": 0},
           f"fan wrong: a={fan['pkg.a']} b={fan['pkg.sub.b']} "
           f"t2={fan['t2']}")
    # --include keeps from-imports resolvable among the kept members
    p2 = run_map(d, "--include", "nspkg/*", name="map_mixpkg_inc")
    expect([(e["s"], e["d"]) for e in p2["imports"]] ==
           [("nspkg.x", "nspkg.y")],
           f"filtered map lost the from-import edge: {p2['imports']}")
    # flags AFTER the path are an error, never silently ignored
    r = subprocess.run([PY, os.path.join(HERE, "mapper.py"), d,
                        "--out", os.path.join(TMP, "never.html")],
                       capture_output=True, text=True, timeout=60)
    expect(r.returncode == 2 and
           not os.path.exists(os.path.join(TMP, "never.html")),
           "flags after the path must be rejected, not ignored")


@check("map intra: single-file function call graph")
def _():
    d = os.path.join(TMP, "intralab")
    os.makedirs(d, exist_ok=True)
    # one file, only functions — exactly the "el gordo" shape
    fixture("intralab/solo.py", (
        "def helper(x):\n"
        "    return x + 1\n"
        "def walk(n):\n"                 # recursion
        "    if n <= 0:\n"
        "        return 0\n"
        "    return walk(n - 1)\n"
        "def build():\n"                 # calls helper (twice) + walk
        "    a = helper(1)\n"
        "    b = helper(a)\n"
        "    return b + walk(3)\n"
        "def unused():\n"                # calls nothing internal
        "    return 42\n"
        "class Maker:\n"                 # a method calling a function:
        "    def make(self):\n"          # caller is a class, not drawable
        "        return helper(9)\n"
        "def outer():\n"                 # nested-fn call attributes to outer
        "    def inner():\n"
        "        return build()\n"
        "    return inner()\n"
        "def main():\n"
        "    return build()\n"
        "main()\n"))                     # module-level entry point
    p = run_map(d, name="map_intra")
    intra = p["intra"]["solo"]
    edges = {tuple(e) for e in intra["edges"]}
    # function → function edges, deduped (helper appears once despite 2 calls)
    expect(("build", "helper") in edges and ("build", "walk") in edges and
           ("main", "build") in edges and ("add_hyperlink", "x") not in edges,
           f"expected core edges missing: {sorted(edges)}")
    # a nested function's call is attributed to its top-level owner
    expect(("outer", "build") in edges,
           f"nested-fn call must attribute to the outer top func: {edges}")
    # recursion is recorded as a self-edge (drawn as a marker, not an arrow)
    expect(("walk", "walk") in edges, "recursion self-edge missing")
    # a class method calling a function is NOT a function-row edge
    expect(not any(a == "Maker" or a == "make" for a, _ in edges),
           f"class-method call leaked into function edges: {edges}")
    # calling a class (Maker()) is not a function→function edge either
    expect(not any(b == "Maker" for _, b in edges),
           "constructing a class must not be a function-call edge")
    # module-level call marks the entry point
    expect(intra["entries"] == ["main"],
           f"entry point wrong: {intra['entries']}")
    # a function with no internal relationships still exists as a node,
    # just absent from edges/entries
    expect(not any("unused" in e for e in edges) and
           "unused" not in intra["entries"],
           "a relationship-free function must not fabricate edges")
    # every edge/entry endpoint must be a top-level function name — a
    # regression that emitted "Class.method" or a class would slip past
    # the name-specific asserts above, so pin the invariant directly
    funcnames = {dd["n"] for dd in
                 next(m for m in p["modules"] if m["id"] == "solo")["defs"]
                 if dd["k"] == "def" and "." not in dd["n"]}
    expect(all(a in funcnames and b in funcnames for a, b in edges) and
           all(e in funcnames for e in intra["entries"]),
           "every intra endpoint must be a top-level function")

    # the honesty-critical cases the adversarial review surfaced:
    # decorators-with-args, default-arg calls, name shadowing, nested
    # class methods must NOT fabricate function-body edges
    fixture("intralab/tricky.py", (
        "def deco(path):\n"
        "    def wrap(fn):\n"
        "        return fn\n"
        "    return wrap\n"
        "def provider():\n"
        "    return 1\n"
        "def real_work():\n"
        "    return 2\n"
        "@deco('/home')\n"                # decorator runs at module load
        "def index(v=provider()):\n"      # default runs at module load
        "    return real_work()\n"
        "def build():\n"
        "    return 0\n"
        "def outer():\n"
        "    def build():\n"              # shadows the top-level build
        "        return 99\n"
        "    return build()\n"            # calls the LOCAL build
        "class C:\n"
        "    def m(self):\n"
        "        return real_work()\n"
        "def host():\n"
        "    class Local:\n"              # nested class inside a function
        "        def m(self):\n"
        "            return real_work()\n"
        "    return Local\n"))
    p3 = run_map(d, name="map_intra_tricky")
    tk = p3["intra"]["tricky"]
    te = {tuple(e) for e in tk["edges"]}
    expect(te == {("index", "real_work")},
           f"only the real body edge should survive: {sorted(te)}")
    expect(sorted(tk["entries"]) == ["deco", "provider"],
           f"decorator + default calls must be entries: {tk['entries']}")
    expect(("index", "deco") not in te and ("index", "provider") not in te,
           "a decorator/default call must never be a function-body edge")
    expect(("outer", "build") not in te,
           "a nested def shadowing a name must not fabricate an edge")
    expect(not any("." in a or a in ("C", "host") for a, _ in te),
           f"class/nested-class methods must not leak edges: {sorted(te)}")

    # multi-file maps still get intra where internal calls exist
    p2 = run_map(os.path.join(HERE, "tinyshop"), name="map_intra_ts")
    expect("intra" in p2, "intra field must always be present")


@check("map auto-heat: trace discovery, --no-trace, __main__ flag")
def _():
    d = os.path.join(TMP, "autolab")
    os.makedirs(d, exist_ok=True)
    fixture("autolab/engine.py", "def spin():\n    return 42\n")
    fixture("autolab/app.py", (
        "import engine\n"
        "def go():\n"
        "    return engine.spin()\n"
        "if __name__ == '__main__':\n"
        "    print(go())\n"))
    # an unrelated codebase, to prove mismatched traces are refused
    d2 = os.path.join(TMP, "autolab_other")
    os.makedirs(d2, exist_ok=True)
    fixture("autolab_other/other.py", "X = 1\n")
    # the trace must be NAMED like the tracer names them (trace_*.html)
    run_trace(os.path.join(d, "app.py"), name="trace_autolab")
    p = run_map(d, name="map_autolab")
    expect(p["heat"] is not None and p["heat"]["script"] == "app.py",
           "the newest matching trace must be auto-adopted")
    byid = {m["id"]: m for m in p["modules"]}
    # __main__ guard flag: app runs itself, engine does not
    expect(byid["app"].get("run") is True and "run" not in byid["engine"],
           f"__main__ flag wrong: app={byid['app'].get('run')} "
           f"engine={byid['engine'].get('run')}")
    # --no-trace refuses the automation
    p2 = run_map(d, "--no-trace", name="map_autolab_off")
    expect(p2["heat"] is None, "--no-trace must disable auto-heat")
    # a trace from ANOTHER codebase must never be adopted
    p3 = run_map(d2, name="map_autolab_other")
    expect(p3["heat"] is None,
           "an unrelated trace must not be adopted as heat")


@check("map heat: multi-trace aggregation combines workloads")
def _():
    # two DIFFERENT workloads of one codebase: run_a exercises pkg.alpha,
    # run_b exercises pkg.beta — neither touches the other's module
    base = os.path.join(TMP, "aggmap")
    pkg = os.path.join(base, "pkg")
    os.makedirs(pkg, exist_ok=True)
    open(os.path.join(pkg, "__init__.py"), "w").close()
    with open(os.path.join(pkg, "alpha.py"), "w") as fh:
        fh.write("def leaf(x):\n    return x + 1\ndef work(n):\n    t = 0\n"
                 "    for _ in range(n):\n        t = leaf(t)\n    return t\n")
    with open(os.path.join(pkg, "beta.py"), "w") as fh:
        fh.write("def leaf(x):\n    return x * 2\ndef work(n):\n    t = 1\n"
                 "    for _ in range(n):\n        t = leaf(t) % 1000\n"
                 "    return t\n")
    for r, mod in (("run_a", "alpha"), ("run_b", "beta")):
        with open(os.path.join(base, r + ".py"), "w") as fh:
            fh.write(f"from pkg.{mod} import work\nprint(work(40))\n")
    ta, tb = os.path.join(TMP, "trace_aggA.html"), os.path.join(TMP, "trace_aggB.html")
    for out, r in ((ta, "run_a"), (tb, "run_b")):
        subprocess.run([PY, os.path.join(HERE, "tracer.py"), "--out", out,
                        "--granularity", "fn", "--root", base,
                        os.path.join(base, r + ".py")],
                       capture_output=True, text=True, cwd=base, timeout=60)

    a = run_map(base, "--trace", ta, name="map_aggA")["heat"]
    b = run_map(base, "--trace", tb, name="map_aggB")["heat"]
    ab = run_map(base, "--trace", ta, "--trace", tb, name="map_aggAB")["heat"]
    # each single trace touches only its own module
    expect("pkg.alpha" in a["mods"] and "pkg.beta" not in a["mods"],
           f"trace A should touch alpha only, got {sorted(a['mods'])}")
    expect("pkg.beta" in b["mods"] and "pkg.alpha" not in b["mods"],
           f"trace B should touch beta only, got {sorted(b['mods'])}")
    # the aggregate touches BOTH — the whole point (no single run defines it)
    expect("pkg.alpha" in ab["mods"] and "pkg.beta" in ab["mods"],
           f"aggregate must combine both workloads, got {sorted(ab['mods'])}")
    # events and per-module totals are summed, not replaced
    expect(ab["events"] == a["events"] + b["events"],
           "aggregate events must be the sum of the traces")
    expect(ab["mods"]["pkg.alpha"]["n"] == a["mods"]["pkg.alpha"]["n"],
           "aggregate must preserve each module's summed event total")


@check("map asyncio: known real-world structure")
def _():
    target = "/usr/lib/python3.12/asyncio"
    if not os.path.isdir(target):
        return   # not on this machine: skip silently
    p = run_map(target, name="map_asyncio")
    expect(len(p["modules"]) >= 25, f"only {len(p['modules'])} modules")
    edges = {(e["s"], e["d"]) for e in p["imports"]}
    for known in [("base_events", "events"), ("tasks", "futures"),
                  ("selector_events", "base_events")]:
        expect(known in edges, f"missing known edge {known}")
    expect(sum(len(m["defs"]) for m in p["modules"]) > 800,
           "def inventory suspiciously small")
    # milestone-5 fields hold their invariants on a real codebase too,
    # and 'events' is asyncio's known load-bearing wall
    _map_invariants(p)
    expect(p["fan"]["events"]["i"] >= 5,
           f"events must rank as a wall: {p['fan']['events']}")


# ---------------------------------------------------------------- runner

def main():
    pat = None
    if len(sys.argv) >= 3 and sys.argv[1] == "-k":
        pat = sys.argv[2].lower()
    todo = [(n, f) for n, f in CHECKS if pat is None or pat in n.lower()]
    width = max(len(n) for n, _ in todo)
    failed = 0
    for name, fn in todo:
        try:
            fn()
            print(f"  \033[32mPASS\033[0m  {name}")
        except Fail as exc:
            failed += 1
            print(f"  \033[31mFAIL\033[0m  {name}")
            print(f"        {exc}")
        except Exception as exc:
            failed += 1
            print(f"  \033[31mERROR\033[0m {name}")
            print(f"        {type(exc).__name__}: {exc}")
    print()
    print(f"{len(todo) - failed}/{len(todo)} green"
          + (f" — {failed} RED" if failed else " — all invariants hold"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
