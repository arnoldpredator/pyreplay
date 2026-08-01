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
import base64
import collections
import gzip
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
    data = json.loads(m.group(1).replace("<\\/", "</"))
    ch = data.get("chunked")
    if ch:   # #101: events live in gzip+base64 chunk tags
        events = []
        tags = re.findall(r'<script id="trace-chunk-(\d+)" '
                          r'type="application/gzip-base64">(.*?)</script>',
                          html, re.S)
        for _, b64 in sorted(((int(k), s) for k, s in tags)):
            events.extend(json.loads(gzip.decompress(base64.b64decode(b64))))
        expect(len(events) == ch.get("total"),
               f"chunked trace incomplete: {len(events)}/{ch.get('total')}")
        data["events"] = events
    return data


def run_trace(script, *flags, stdin_text=None, name=None):
    out = os.path.join(TMP, (name or os.path.basename(script)) + ".html")
    cmd = [PY, os.path.join(HERE, "tracer.py"), "--out", out,
           *flags, script]
    # stdin is pinned either way: inherited descriptors made subprocess
    # behavior depend on HOW the suite was invoked (the ghost flake)
    kw = ({"input": stdin_text} if stdin_text is not None
          else {"stdin": subprocess.DEVNULL})
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=TMP,
                       timeout=120, **kw)
    expect(os.path.exists(out),
           f"tracer produced no output ({r.stdout} {r.stderr})")
    return payload(out)


def run_map(target, *flags, name="map"):
    out = os.path.join(TMP, name + ".html")
    cmd = [PY, os.path.join(HERE, "mapper.py"), "--out", out,
           *flags, target]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=120)
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
                       capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=TMP, timeout=60)
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
                       capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=TMP, timeout=60)
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
                              capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=cwd,
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
                              capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=base,
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
                              capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=base,
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
    r = subprocess.run([PY, host], capture_output=True, stdin=subprocess.DEVNULL, text=True,
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


@check("check: run predicates decide the exit code (#70)")
def _():
    fx = fixture("fx_bisect.py", (
        "total = 10\n"
        "for i in range(5):\n"
        "    total -= 4\n"
        "print('end', total)\n"))

    def run_check(expr, target=None):
        return subprocess.run(
            [PY, os.path.join(HERE, "tracer.py"), "--check", expr,
             "--out", os.path.join(TMP, "t_c70.html"), target or fx],
            capture_output=True, text=True, cwd=TMP,
            stdin=subprocess.DEVNULL, timeout=120)

    r = run_check("total < 0")
    expect(r.returncode == 1 and "HIT — first at event" in r.stdout,
           f"state hit must exit 1 with the moment: {r.stdout}")
    r = run_check("total < -999")
    expect(r.returncode == 0 and "clean (exit 0)" in r.stdout,
           f"never-true must exit 0: {r.stdout}")
    r = run_check("'end -10' in output")
    expect(r.returncode == 1,
           f"the console lane must be a queryable run fact: {r.stdout}")
    r = run_check("no_such_name > 3")
    expect(r.returncode == 3 and "never evaluable" in r.stdout,
           f"a typo must exit 3, never a silent 0: {r.stdout}")
    fx2 = fixture("fx_bisect2.py", "raise ValueError('boom')\n")
    r = run_check("error", target=fx2)
    expect(r.returncode == 1,
           f"--check 'error' must flag a crashing run: {r.stdout}")


@check("black-box: ring window, dropped honesty, live snapshot (#103)")
def _():
    fx = fixture("fx_ring.py", (
        "import os, signal\n"
        "def spin(n):\n"
        "    t = 0\n"
        "    for i in range(n):\n"
        "        t += i\n"
        "    return t\n"
        "for r_ in range(60):\n"
        "    spin(5)\n"
        "os.kill(os.getpid(), signal.SIGUSR1)\n"
        "for r_ in range(10):\n"
        "    spin(5)\n"
        "print('done')\n"))
    out = os.path.join(TMP, "t_ring.html")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--black-box", "--max-events", "50",
                        "--out", out, fx],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=120)
    expect("done" in r.stdout, f"the run must survive the snapshot: "
           f"{r.stdout} {r.stderr}")
    p = payload(out)
    expect(len(p["events"]) == 50 and p["ring"]["size"] == 50
           and p["ring"]["dropped"] > 0,
           f"ring window wrong: {len(p['events'])} {p.get('ring')}")
    snap = os.path.join(TMP, "t_ring_snap1.html")
    expect(os.path.exists(snap), "SIGUSR1 must dump a live snapshot")
    sp = payload(snap)
    expect(len(sp["events"]) <= 50 and "[SIGUSR1 snapshot]"
           in sp["script"] and sp["ring"]["dropped"]
           < p["ring"]["dropped"],
           f"snapshot must be the mid-run window: {sp['script']} "
           f"{sp.get('ring')}")
    with open(out, encoding="utf-8") as fh:
        expect("rotated out of the" in fh.read(),
               "the ring banner honesty note is missing")


@check("boundaries: observed interfaces, instability + jumps (#120)")
def _():
    fx = fixture("fx_shapes.py", (
        "def lookup(catalog, sku):\n"
        "    return catalog.get(sku)\n"
        "def total(items):\n"
        "    s = 0\n"
        "    for i in items:\n"
        "        s += i['qty']\n"
        "    return s\n"
        "cat = {'apple': {'qty': 3, 'price': 1.2}}\n"
        "print(total([cat['apple']]))\n"
        "print(lookup(cat, 'apple'))\n"
        "print(lookup(cat, 'mango'))\n"))
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--out", os.path.join(TMP, "t_shapes.html"), fx],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=120)
    expect("boundary instability" in r.stdout
           and "lookup — return:" in r.stdout,
           f"terminal instability summary missing: {r.stdout}")
    b = payload(os.path.join(TMP, "t_shapes.html"))["boundaries"]
    tot = b["fx_shapes.py:total"]
    expect(tot["args"]["items"] and
           list(tot["args"]["items"]) == ["list[dict{qty, price}]"]
           and list(tot["ret"]) == ["int"],
           f"stable shapes wrong: {tot}")
    lk = b["fx_shapes.py:lookup"]
    expect(sorted(lk["ret"]) == ["NoneType", "dict{qty, price}"]
           and lk["calls"] == 2,
           f"unstable return not observed: {lk}")
    ev_idx = lk["ret"]["NoneType"][1]
    evs = payload(os.path.join(TMP, "t_shapes.html"))["events"]
    expect(evs[ev_idx]["e"] == "return"
           and evs[ev_idx]["fn"] == "lookup",
           f"deviant jump target must be lookup's return: "
           f"{evs[ev_idx]}")
    expect(not any("genexpr" in k for k in b),
           "comprehension frames are machinery, not interfaces")


@check("capsule: rerun recipe embedded, stdin consumed lazily (#104)")
def _():
    fx = fixture("fx_caps.py", (
        "import sys\n"
        "first = input()\n"
        "rest = sys.stdin.read()\n"
        "print('got', first, len(rest))\n"))
    out = os.path.join(TMP, "t_caps.html")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--out", out, fx],
                       capture_output=True, text=True, cwd=TMP,
                       input="alpha\nbeta tail", timeout=120)
    expect(os.path.exists(out), f"capsule trace missing: {r.stderr}")
    c = payload(out)["capsule"]
    expect(c and c["cwd"] and c["python"] and c["platform"]
           and "tracer.py" in c["cmd"] and "fx_caps.py" in c["cmd"],
           f"capsule incomplete: {c}")
    got = base64.b64decode(c["stdin"] or b"")
    expect(got == b"alpha\nbeta tail" and c["stdinTrunc"] is False,
           f"capsule must hold exactly the consumed stdin: {got!r}")
    expect("hashseed" in c and "env" in c,
           "capsule must state hashseed and the curated env keys")
    # a run that never touches a non-EOF stdin must NOT block: closed
    # empty stdin here, plus the lazy tee means no read happens at all
    fx2 = fixture("fx_caps2.py", "x = 1\n")
    out2 = os.path.join(TMP, "t_caps2.html")
    r2 = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                         "--out", out2, fx2],
                        capture_output=True, text=True, cwd=TMP,
                        stdin=subprocess.DEVNULL, timeout=60)
    c2 = payload(out2)["capsule"]
    expect(c2["stdin"] is None,
           "no consumption must mean no stdin in the capsule")


@check("console lane: output lines become attributed events (#118)")
def _():
    fx = fixture("fx_lane.py", (
        "import sys\n"
        "def talk(n):\n"
        "    print('hello', n)\n"
        "    print('to stderr', file=sys.stderr)\n"
        "import logging\n"
        "logging.warning('via logging')\n"
        "talk(7)\n"
        "sys.stdout.write('unterminated')\n"))
    p = run_trace(fx, name="fx_lane")
    logs = [e for e in p["events"] if e.get("e") == "log"]
    expect([(e["s"], e["txt"]) for e in logs] == [
        ("err", "WARNING:root:via logging"),
        ("out", "hello 7"),
        ("err", "to stderr"),
        ("out", "unterminated")],
        f"console lane wrong: {[(e.get('s'), e.get('txt')) for e in logs]}")
    hello = logs[1]
    expect(hello["f"] == "fx_lane.py" and hello["l"] == 3
           and hello["fn"] == "talk",
           f"attribution wrong: {hello}")
    expect(p.get("logCapped") is None, "cap flag must be absent here")
    # fragmented print() writes joined into ONE line event
    expect(sum(1 for e in logs if "hello" in e["txt"]) == 1,
           "fragmented print writes must join into one line")
    p2 = run_trace(fx, "--no-console", name="fx_lane_off")
    expect(not any(e.get("e") == "log" for e in p2["events"]),
           "--no-console must record no console events")
    # fn granularity still carries the lane (the tee is independent)
    p3 = run_trace(fx, "--granularity", "fn", name="fx_lane_fn")
    expect(any(e.get("e") == "log" for e in p3["events"]),
           "the lane must work at fn granularity too")


@check("whyline: guard map chains innermost-first (#77)")
def _():
    fx = fixture("fx_why.py", (
        "def f(x):\n"
        "    if x > 100:\n"
        "        return 'big'\n"
        "    return 'small'\n"
        "for i in range(3):\n"
        "    if i == 99:\n"
        "        print('never')\n"
        "try:\n"
        "    pass\n"
        "except ValueError:\n"
        "    print('caught')\n"
        "f(1)\n"))
    p = run_trace(fx, name="fx_why")
    g = p["guards"]["fx_why.py"]
    expect(g["3"] == [2, "then"] and g["4"] == [1, "def"],
           f"if/def guards wrong: {g.get('3')} {g.get('4')}")
    expect(g["7"] == [6, "then"] and g["6"] == [5, "loop"],
           f"nested loop/if guards wrong: {g.get('7')} {g.get('6')}")
    expect(g["11"] == [10, "except"],
           f"except guard wrong: {g.get('11')}")
    expect(g["2"] == [1, "def"],
           f"innermost-first violated at the if header: {g.get('2')}")
    # fn granularity: no guards (whyline needs line events, stated)
    p2 = run_trace(fx, "--granularity", "fn", name="fx_why_fn")
    expect(p2["guards"] == {}, "guards must be line-granularity only")
    # renderer wiring
    with open(os.path.join(TMP, "fx_why.html"), encoding="utf-8") as fh:
        html = fh.read()
    for needle in ("function whyline", "never ran", "renderConsole",
                   "unhandledrejection"):
        expect(needle in html, f"wiring missing: {needle!r}")


@check("chunked: gzip chunks round-trip, auto past 100k, honesty (#101)")
def _():
    # deterministic fixture (no functions/objects -> no 0x addresses):
    # two separate runs produce byte-identical events, so the chunked
    # and plain artifacts must decode to EXACTLY the same list
    fx = fixture("fx_chunk.py",
                 "a = 1\nb = [1, 2]\nb.append(a)\nc = 'x' * 3\n")
    plain = run_trace(fx, name="fx_chunk_plain")
    chunk = run_trace(fx, "--chunked", name="fx_chunk_gz")
    meta = chunk.get("chunked")
    expect(meta and meta["chunks"] == 1
           and meta["total"] == len(chunk["events"]),
           f"chunk meta wrong: {meta}")
    expect(plain["events"] == chunk["events"],
           "chunked events must decode identical to the plain run")
    with open(os.path.join(TMP, "fx_chunk_gz.html"),
              encoding="utf-8") as fh:
        html = fh.read()
    expect('id="trace-chunk-0" type="application/gzip-base64"' in html,
           "chunk tag missing from the artifact")
    for needle, why in [
        ("function loadChunks", "async chunk loader missing"),
        ("DecompressionStream", "browser decompression path missing"),
        ("is MISSING", "damaged-chunk honesty note missing"),
        ("function maybeKeyframe", "keyframe builder missing"),
        ("function cloneStacks", "keyframe snapshot missing"),
        ("window.PYREPLAY", "debug handle missing"),
    ]:
        expect(needle in html, f"chunked: {why} ({needle!r})")
    # a damaged file must refuse loudly, never truncate silently
    broken = re.sub(r'<script id="trace-chunk-0" '
                    r'type="application/gzip-base64">.*?</script>',
                    "", html, count=1, flags=re.S)
    bp = os.path.join(TMP, "fx_chunk_broken.html")
    with open(bp, "w", encoding="utf-8") as fh:
        fh.write(broken)
    try:
        payload(bp)
        loud = False
    except Fail as exc:                 # payload()'s own expect fired
        loud = "incomplete" in str(exc)
    except Exception:
        loud = True                     # any reader exception is loud
    expect(loud, "reading a chunk-damaged trace must fail loudly")
    # auto threshold: >100k events chunk WITHOUT the flag; --no-chunked
    # forces the old single-string format on the same run
    fx2 = fixture("fx_chunk_big.py",
                  "t = 0\nfor i in range(26000):\n"
                  "    t += i\n    t -= 1\n    t ^= 1\n")
    big = run_trace(fx2, name="fx_chunk_auto")
    expect(big.get("chunked") and big["chunked"]["chunks"] >= 2
           and len(big["events"]) > 100000,
           f"auto-chunking must fire past 100k events: "
           f"{big.get('chunked')} n={len(big['events'])}")
    off = run_trace(fx2, "--no-chunked", name="fx_chunk_off")
    expect(off.get("chunked") is None,
           "--no-chunked must force the single-string format")
    expect(len(off["events"]) == len(big["events"]),
           "both formats must hold the same run shape")


@check("chapters: pytest tests become spans + per-test SBFL join (#98)")
def _():
    # needs a python with pytest: try the checks interpreter, then the
    # repo's .venv — verifying a pytest integration without pytest is
    # not possible, so the absence is a loud, actionable failure
    pytest_py = None
    for cand in (PY, os.path.join(HERE, ".venv", "bin", "python3")):
        probe = subprocess.run([cand, "-c", "import pytest"],
                               capture_output=True, stdin=subprocess.DEVNULL)
        if probe.returncode == 0:
            pytest_py = cand
            break
    expect(pytest_py is not None,
           "#98 needs pytest in some python (checks interpreter or "
           "./.venv) — pip install pytest to verify this feature")
    suite = os.path.join(TMP, "chapsuite")
    os.makedirs(suite, exist_ok=True)
    with open(os.path.join(suite, "calc.py"), "w") as fh:
        fh.write("def add(a, b):\n    return a + b\n\n\n"
                 "def buggy_scale(x):\n    return x * 3\n")
    with open(os.path.join(suite, "test_mini.py"), "w") as fh:
        fh.write("from calc import add, buggy_scale\n\n\n"
                 "def test_add_small():\n    assert add(2, 3) == 5\n\n\n"
                 "def test_add_big():\n    assert add(10, 20) == 30\n\n\n"
                 "def test_scale():\n    assert buggy_scale(4) == 8\n")
    out = os.path.join(TMP, "t_chap.html")
    r = subprocess.run([pytest_py, os.path.join(HERE, "tracer.py"),
                        "--root", suite, "--out", out, "-m", "pytest",
                        os.path.join(suite, "test_mini.py"), "-q"],
                       capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=TMP,
                       timeout=180)
    expect(os.path.exists(out), f"suite trace missing: {r.stdout} "
           f"{r.stderr}")
    p = payload(out)
    chaps = [e for e in p["events"] if e.get("e") == "chap"]
    starts = [e for e in chaps if e["k"] == "s"]
    ends = [e for e in chaps if e["k"] == "e"]
    expect(len(starts) == 3 and len(ends) == 3,
           f"3 tests must yield 3 start/end pairs: {len(starts)}/"
           f"{len(ends)}")
    expect(all(e.get("f") == "test_mini.py"
               and isinstance(e.get("l"), int) for e in starts),
           f"chapter starts must carry the test file:line: {starts}")
    outcomes = sorted(e.get("o") for e in ends)
    expect(outcomes == ["failed", "passed", "passed"],
           f"outcomes wrong: {outcomes}")
    fail_end = next(e for e in ends if e["o"] == "failed")
    expect(fail_end["id"].endswith("::test_scale"),
           f"the failing nodeid must name test_scale: {fail_end['id']}")
    # spans well-formed: every end after its start
    idx = {e["id"]: i for i, e in enumerate(p["events"])
           if e.get("e") == "chap" and e["k"] == "s"}
    for i, e in enumerate(p["events"]):
        if e.get("e") == "chap" and e["k"] == "e":
            expect(idx.get(e["id"], 10**9) < i,
                   f"chapter end before start for {e['id']}")
    # the summary and the killer join
    ts = p["tests"]
    expect(ts["tests"] == 3 and ts["passed"] == 2 and ts["failed"] == 1,
           f"tests summary wrong: {ts}")
    s = p["testSuspicion"]
    expect(s is not None and s["pass"] == 2 and s["fail"] == 1,
           f"per-test suspicion contrast wrong: {s}")
    perfect = [row for row in s["top"] if row["score"] == 1.0]
    expect(any(row["f"] == "calc.py" and row["ep"] == 0
               and row["ef"] == 1 for row in perfect),
           f"buggy_scale's lines (calc.py, only the failing test) must "
           f"score 1.0: {s['top'][:5]}")
    for row in perfect:
        if row["ev"] is not None:
            e = p["events"][row["ev"]]
            expect(e.get("f") == row["f"] and e.get("l") == row["l"],
                   f"suspect jump target mismatch: {row} -> {e}")
    # non-pytest -m runs stay chapter-free (the plugin only rides pytest)
    expect("tests" not in payload(os.path.join(TMP, "fx_chart.html"))
           if os.path.exists(os.path.join(TMP, "fx_chart.html"))
           else True,
           "plain traces must not grow a tests summary")


@check("diverge: state vs control divergence, identical pair, exits (#64)")
def _():
    # env-controlled fixture: same control flow, different values ->
    # STATE diverges while CONTROL never does
    fx = fixture("fx_div.py", (
        "import os\n"
        "v = int(os.environ.get('DIV', '1'))\n"
        "acc = 0\n"
        "for i in range(3):\n"
        "    acc += v\n"
        "print(acc)\n"))
    outs = {}
    for tag, div in (("a", "1"), ("b", "2"), ("a2", "1")):
        outs[tag] = os.path.join(TMP, f"t_div_{tag}.html")
        env = dict(os.environ, DIV=div)
        r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                            "--out", outs[tag], fx],
                           capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=TMP,
                           env=env, timeout=120)
        expect(os.path.exists(outs[tag]), f"trace {tag} missing: {r.stderr}")

    def diverge(x, y):
        return subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                               "--diverge", outs[x], outs[y]],
                              capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=TMP,
                              timeout=60)

    r = diverge("a", "b")
    expect(r.returncode == 1, f"diverged pair must exit 1: {r.stdout}")
    expect("STATE diverges first" in r.stdout
           and "control flow never diverges" in r.stdout,
           f"state-only divergence misreported:\n{r.stdout}")
    expect("v:  1  vs  2" in r.stdout,
           f"the differing variable must be named with both values:\n"
           f"{r.stdout}")
    expect("#ev=" in r.stdout, "deep links missing from the report")
    r2 = diverge("a", "a2")
    expect(r2.returncode == 0 and "identical" in r2.stdout,
           f"identical runs must exit 0:\n{r2.stdout}")
    # control divergence: a value-dependent branch
    fx2 = fixture("fx_div2.py", (
        "import os\n"
        "v = int(os.environ.get('DIV', '1'))\n"
        "if v == 1:\n"
        "    x = 'low'\n"
        "else:\n"
        "    x = 'high'\n"
        "print(x)\n"))
    for tag, div in (("c", "1"), ("d", "2")):
        outs[tag] = os.path.join(TMP, f"t_div_{tag}.html")
        subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--out", outs[tag], fx2],
                       capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=TMP,
                       env=dict(os.environ, DIV=div), timeout=120)
    r3 = diverge("c", "d")
    expect(r3.returncode == 1
           and "control flow follows at event" in r3.stdout,
           f"branch divergence must show the control moment:\n{r3.stdout}")


@check("runs: harness outcomes + one kept trace each + SBFL suspects (#63+#65)")
def _():
    # a counter file makes the "flake" fully deterministic: 6 runs share
    # the cwd, runs 3 and 6 (n=2, n=5) raise — 4 clean + 2 ValueError.
    fx = fixture("fx_nrun.py", (
        "import os\n"
        "n = 0\n"
        "if os.path.exists('ctr.txt'):\n"
        "    with open('ctr.txt') as fh:\n"
        "        n = int(fh.read())\n"
        "with open('ctr.txt', 'w') as fh:\n"
        "    fh.write(str(n + 1))\n"
        "if n % 3 == 2:\n"
        "    raise ValueError('flake')\n"
        "print('ok', n)\n"))
    ctr = os.path.join(TMP, "ctr.txt")
    if os.path.exists(ctr):
        os.remove(ctr)
    out = os.path.join(TMP, "runs_fx_nrun.html")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--runs", "6", "--out", out, fx],
                       capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=TMP,
                       timeout=180)
    expect(r.returncode == 1,
           f"a run set with failures must exit 1, got {r.returncode} "
           f"({r.stdout} {r.stderr})")
    expect(os.path.exists(out), "runs report missing")
    with open(out, encoding="utf-8") as fh:
        m = re.search(r'<script id="runs-data" '
                      r'type="application/json">(.*?)</script>',
                      fh.read(), re.S)
    expect(m is not None, "no embedded runs data")
    data = json.loads(m.group(1).replace("<\\/", "</"))
    per = data["perRun"]
    expect(len(per) == 6 and data["granularity"] == "fn",
           f"6 fn runs expected, got {len(per)} {data['granularity']}")
    clean = [p for p in per if p["cls"] == "clean"]
    fails = [p for p in per if p["cls"].startswith("ValueError at")]
    expect(len(clean) == 4 and len(fails) == 2,
           f"outcome split wrong: {[p['cls'] for p in per]}")
    expect([p["i"] for p in fails] == [3, 6],
           f"the deterministic flake fires on runs 3 and 6: {fails}")
    kept = [p["kept"] for p in per if p["kept"]]
    expect(len(kept) == 2, f"exactly one trace per class kept: {kept}")
    for k in kept:
        expect(os.path.exists(os.path.join(TMP, k)),
               f"kept representative missing on disk: {k}")
    on_disk = [f for f in os.listdir(TMP)
               if f.startswith("runs_fx_nrun_run")]
    expect(sorted(on_disk) == sorted(kept),
           f"non-representative traces must be deleted: {on_disk}")
    expect(fails[0]["note"], "first failing run must carry a stderr tail")
    # #65 SBFL: the raise line is executed ONLY by failing runs ->
    # perfect Ochiai score, deep-linked into a kept failing trace
    s = data["suspicion"]
    expect(s is not None and s["pass"] == 4 and s["fail"] == 2,
           f"suspicion needs the 4/2 contrast recorded: {s}")
    top = s["top"][0]
    expect(top["l"] == 9 and top["score"] == 1.0
           and top["ef"] == 2 and top["ep"] == 0,
           f"the raise line must be the perfect suspect: {top}")
    expect(top["rep"] in kept and top["ev"],
           f"top suspect must deep-link into a kept failing trace: {top}")
    expect(top["src"] and "raise ValueError" in top["src"],
           f"suspect must carry its source line: {top['src']!r}")
    # classification names the RAISE site (first hard exc), which is
    # also the top suspect's line — the two views must agree
    expect(fails[0]["cls"] == "ValueError at fx_nrun.py:9",
           f"class must name the raise site: {fails[0]['cls']}")
    # the all-clean path exits 0 and reports NO suspicion (no contrast)
    fx2 = fixture("fx_nrun_ok.py", "x = 1\nprint(x)\n")
    out2 = os.path.join(TMP, "runs_fx_ok.html")
    r2 = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                         "--runs", "2", "--out", out2, fx2],
                        capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=TMP,
                        timeout=120)
    expect(r2.returncode == 0,
           f"an all-clean run set must exit 0, got {r2.returncode}")
    with open(out2, encoding="utf-8") as fh:
        m2 = re.search(r'<script id="runs-data" '
                       r'type="application/json">(.*?)</script>',
                       fh.read(), re.S)
    expect(json.loads(m2.group(1).replace("<\\/", "</"))["suspicion"]
           is None,
           "no contrast (all clean) must mean NO suspicion ranking — "
           "never an invented one")


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


@check("oscilloscope: chart machinery wired into the artifact (#80)")
def _():
    # #80 is renderer-side (strip-chart + phase portrait over the change
    # index); the data-level guard is structural, like #106's: the
    # artifact must carry the series builder, both plotters, the numeric
    # eligibility test and the honesty strings (gap/cap/log notes).
    # Behavior is verified in the browser.
    fx = fixture("fx_chart.py", "x = 1\nx = 2\n")
    run_trace(fx, name="fx_chart")
    with open(os.path.join(TMP, "fx_chart.html"),
              encoding="utf-8") as fh:
        html = fh.read()
    for needle, why in [
        ("function renderChart", "strip-chart plotter missing"),
        ("function renderPhase", "phase-portrait plotter missing"),
        ("function numericAt", "series value reader missing"),
        ("function chartSeries", "series builder missing"),
        ("function numericScalar", "chart eligibility test missing"),
        ("non-numeric gap", "gap honesty note missing"),
        ("log needs all values > 0", "log honesty note missing"),
        (":chartvs", "phase partner pref missing"),
    ]:
        expect(needle in html, f"oscilloscope: {why} ({needle!r})")


@check("query bar: grammar + wiring in the artifact (#109)")
def _():
    # renderer-side; the structural guard covers the grammar table, the
    # honest unrecognized-token path, and the hit machinery. Behavior
    # (15 predicates, jumps, pins) is verified in the browser.
    fx = fixture("fx_query.py", "x = 1\nx = 2\n")
    run_trace(fx, name="fx_query")
    with open(os.path.join(TMP, "fx_query.html"),
              encoding="utf-8") as fh:
        html = fh.read()
    for needle, why in [
        ("function parseQuery", "query parser missing"),
        ("function runQuery", "query runner missing"),
        ("function jumpHit", "hit navigation missing"),
        ("unrecognized: ", "typo'd operators must be reported"),
        ('id="query"', "query input missing"),
        ("changed:", "changed: predicate missing"),
        ("srcLineAt", "bare-word source search missing"),
        ("qmark", "hit pins missing"),
    ]:
        expect(needle in html, f"query bar: {why} ({needle!r})")


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
                       capture_output=True, stdin=subprocess.DEVNULL, text=True, timeout=60)
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
                       capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=base, timeout=60)

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


@check("chaos: same seed = same decision stream; plain runs carry none (#68)")
def _():
    a = run_trace(os.path.join(HERE, "example_sort.py"),
                  "--chaos-schedule", "7", name="chaos_a")
    b = run_trace(os.path.join(HERE, "example_sort.py"),
                  "--chaos-schedule", "7", name="chaos_b")
    for p in (a, b):
        c = p.get("chaos")
        expect(c is not None, "chaos run carries no chaos block")
        expect(c["seed"] == 7, f"seed not recorded: {c}")
    expect((a["chaos"]["delays"], a["chaos"]["yields"],
            a["chaos"]["switchRolls"])
           == (b["chaos"]["delays"], b["chaos"]["yields"],
               b["chaos"]["switchRolls"]),
           f"same seed, different decision stream: {a['chaos']} "
           f"vs {b['chaos']}")
    expect(len(a["events"]) == len(b["events"]),
           "single-threaded same-seed chaos runs differ in event count")
    plain = run_trace(os.path.join(HERE, "example_sort.py"),
                      name="chaos_plain")
    expect(plain.get("chaos") is None,
           "an unperturbed trace carries a chaos block")


@check("chaos: asyncio ready queue really shuffled (#68)")
def _():
    p = run_trace(os.path.join(HERE, "example_tasks.py"),
                  "--chaos-schedule", "3", "--granularity", "fn",
                  name="chaos_tasks")
    c = p.get("chaos")
    expect(c is not None, "no chaos block on the asyncio run")
    expect(c["asyncioHooked"] is True,
           f"asyncio hook reported unavailable: {c}")
    expect(c["shuffles"] > 0, f"ready queue never shuffled: {c}")


@check("chaos x runs: derived seeds, PERTURBED report, kept capsule (#68+#63)")
def _():
    out = os.path.join(TMP, "runs_chaos.html")
    if os.path.exists(out):
        os.remove(out)
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--runs", "3", "--chaos-schedule", "50",
                        "--out", out,
                        os.path.join(HERE, "example_sort.py")],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=180)
    expect(r.returncode == 0,
           f"clean chaos run set must exit 0, got {r.returncode} "
           f"({r.stdout} {r.stderr})")
    expect(os.path.exists(out), "chaos runs report missing")
    with open(out, encoding="utf-8") as fh:
        m = re.search(r'<script id="runs-data" '
                      r'type="application/json">(.*?)</script>',
                      fh.read(), re.S)
    expect(m is not None, "no runs payload")
    rp = json.loads(m.group(1).replace("<\\/", "</"))
    expect(rp["chaos"] == 50, f"report must carry the seed base: "
           f"{rp.get('chaos')}")
    kept = payload(os.path.join(TMP, "runs_chaos_run1.html"))
    expect(kept["chaos"]["seed"] == 50,
           f"run 1 must run under seed base+0: {kept['chaos']}")
    expect("--chaos-schedule 50" in kept["capsule"]["cmd"],
           f"kept capsule must reproduce its own seed: "
           f"{kept['capsule']['cmd']}")


@check("chaos: --export-perfetto refused (perturbed time is not truth) (#68)")
def _():
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--chaos-schedule", "1", "--granularity", "fn",
                        "--export-perfetto", os.path.join(TMP, "cx.json"),
                        os.path.join(HERE, "example_sort.py")],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=60)
    expect(r.returncode == 2, f"expected refusal exit 2, got "
           f"{r.returncode}")
    expect("perturb" in (r.stdout + r.stderr).lower(),
           "refusal must say WHY (perturbed timings)")


@check("hb: thread start/join edges, causal order, reuse-proof labels (#88)")
def _():
    p = run_trace(os.path.join(HERE, "example_race.py"), name="hb_race")
    hbs = [e for e in p["events"] if e.get("e") == "hb"]
    starts = [e for e in hbs if e["hb"] == "tstart"]
    joins = [e for e in hbs if e["hb"] == "tjoin"]
    expect(len(starts) == 2 and len(joins) == 2,
           f"expected 2 starts + 2 joins, got "
           f"{[(e['hb'], e['dst']) for e in hbs]}")
    lanes = {e.get("t") for e in p["events"] if e.get("t")}
    expect({e["dst"] for e in starts} == lanes,
           f"start dsts {sorted(e['dst'] for e in starts)} must equal the "
           f"worker lanes {sorted(lanes)} — ident reuse would collapse them")
    expect({e["dst"] for e in joins} == lanes,
           "join dsts must cover both workers")
    expect(all("_di" not in e for e in hbs),
           "unresolved _di leaked into the payload")
    for s in starts:
        at = p["events"].index(s)
        first_dst = next(i for i, e in enumerate(p["events"])
                         if e.get("t") == s["dst"])
        expect(at < first_dst,
               f"a wake must precede its consequences: tstart {s['dst']} "
               f"at {at}, first dst event {first_dst}")
    q = run_trace(os.path.join(HERE, "example_sort.py"), name="hb_none")
    expect(not any(e.get("e") == "hb" for e in q["events"]),
           "a single-threaded run must record no wake edges")


@check("hb: asyncio create edges late-bind renamed tasks (#88)")
def _():
    p = run_trace(os.path.join(HERE, "example_tasks.py"),
                  "--granularity", "fn", name="hb_tasks")
    creates = [e for e in p["events"] if e.get("e") == "hb"
               and e["hb"] == "create"]
    expect(len(creates) >= 3,
           f"expected >= 3 task-create edges, got {len(creates)}")
    tks = {e.get("tk") for e in p["events"] if e.get("tk")}
    named = {e["dst"] for e in creates}
    expect({"producer", "consumer"} <= tks,
           f"sanity: the named task lanes exist ({tks})")
    expect({"producer", "consumer"} <= named,
           f"renamed tasks must resolve to their FINAL lane names, "
           f"got {named}")


@check("hb: perfetto flows — wake arrows bound in pairs across lanes (#88)")
def _():
    out = os.path.join(TMP, "hb_flow.json")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--granularity", "fn", "--export-perfetto", out,
                        "--out", os.path.join(TMP, "hb_flow.html"),
                        os.path.join(HERE, "example_tasks.py")],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=120)
    expect(os.path.exists(out), f"no perfetto file ({r.stdout} {r.stderr})")
    with open(out, encoding="utf-8") as fh:
        te = json.load(fh)["traceEvents"]
    wakes = [e for e in te if e.get("cat") == "wake"]
    s = [e for e in wakes if e["ph"] == "s"]
    f = [e for e in wakes if e["ph"] == "f"]
    expect(len(s) >= 2 and len(s) == len(f),
           f"flow arrows must come in bound pairs: {len(s)} s / {len(f)} f")
    expect({e["id"] for e in s} == {e["id"] for e in f},
           "every flow start must meet its finish")
    expect(any(a["tid"] != b["tid"] for a in s for b in f
               if a["id"] == b["id"]),
           "at least one arrow must actually cross lanes")


@check("map dark edges: runtime-only routes drawn, statics excluded (#119)")
def _():
    # a plugin registry: core calls plugins.double through a dict — no
    # static route core→plugins exists; main reaches plugins only via
    # importlib, so main→plugins is dark too (and main gets the ⚡ flag)
    pkg = os.path.join(TMP, "dyndemo", "dyndemo")
    os.makedirs(pkg, exist_ok=True)
    with open(os.path.join(pkg, "__init__.py"), "w") as fh:
        fh.write("")
    with open(os.path.join(pkg, "core.py"), "w") as fh:
        fh.write("REGISTRY = {}\n\n\ndef register(name, fn):\n"
                 "    REGISTRY[name] = fn\n\n\ndef dispatch(name, x):\n"
                 "    return REGISTRY[name](x)\n")
    with open(os.path.join(pkg, "plugins.py"), "w") as fh:
        fh.write("from dyndemo import core\n\n\ndef double(x):\n"
                 "    return x * 2\n\n\ncore.register('double', double)\n")
    root = os.path.join(TMP, "dyndemo")
    main_py = os.path.join(root, "main.py")
    with open(main_py, "w") as fh:
        fh.write("import importlib\n\nfrom dyndemo import core\n\n"
                 "importlib.import_module('dyndemo.plugins')\n"
                 "print('answer:', core.dispatch('double', 21))\n")
    tr = os.path.join(root, "trace_dyn.html")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--granularity", "fn", "--root", root,
                        "--out", tr, main_py],
                       capture_output=True, text=True, cwd=root,
                       stdin=subprocess.DEVNULL, timeout=120)
    expect(os.path.exists(tr), f"no trace ({r.stdout} {r.stderr})")
    mp = run_map(root, "--trace", tr, name="map_dyn")
    h = mp.get("heat") or {}
    dark = {(d["a"], d["b"]): d["n"] for d in h.get("dark") or []}
    expect(("dyndemo.core", "dyndemo.plugins") in dark,
           f"registry dispatch must be a dark edge: {dark}")
    expect(("main", "dyndemo.plugins") in dark,
           f"a dynamic import is a dark edge too: {dark}")
    static = {(e["s"], e["d"]) for e in mp["imports"]}
    expect(all(p not in static for p in dark),
           "a dark edge must never duplicate a static route")
    flags = {m["id"]: m.get("dynimp", 0) for m in mp["modules"]}
    expect(flags.get("main", 0) == 1,
           f"main's importlib call site must be flagged: {flags}")
    expect(flags.get("dyndemo.core", 0) == 0,
           "core has no dynamic import — must not be flagged")


@check("map dark edges: absent when every observed route is static (#119)")
def _():
    tr = os.path.join(TMP, "trace_shop_dyn.html")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--granularity", "fn", "--out", tr,
                        os.path.join(HERE, "tinyshop", "main.py")],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=120)
    expect(os.path.exists(tr), f"no tinyshop trace ({r.stdout} {r.stderr})")
    mp = run_map(os.path.join(HERE, "tinyshop"), "--trace", tr,
                 name="map_shop_dyn")
    h = mp.get("heat") or {}
    expect(not (h.get("dark") or []),
           f"tinyshop's routes are all static — dark must be empty, "
           f"got {h.get('dark')}")
    expect(h.get("xmod"),
           "cross-module calls must still be OBSERVED (main→cart etc.) "
           "— only their darkness is denied")


@check("map crime scene: churn x complexity from git history (#95)")
def _():
    root = os.path.join(TMP, "crimedemo")
    os.makedirs(root, exist_ok=True)

    def g(*a):
        return subprocess.run(["git", "-C", root, "-c", "user.name=t",
                               "-c", "user.email=t@t"] + list(a),
                              capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60)
    g("init", "-q")
    with open(os.path.join(root, "busy.py"), "w") as fh:
        fh.write("def f(x):\n    if x > 0:\n        return 1\n"
                 "    for i in range(3):\n        x += i\n    return x\n")
    with open(os.path.join(root, "calm.py"), "w") as fh:
        fh.write("VALUE = 7\n")
    g("add", "-A")
    g("commit", "-qm", "one")
    with open(os.path.join(root, "busy.py"), "a") as fh:
        fh.write("Y = 1\n")
    g("add", "-A")
    g("commit", "-qm", "two")
    with open(os.path.join(root, "busy.py"), "a") as fh:
        fh.write("Z = 2\n")
    g("add", "-A")
    g("commit", "-qm", "three")
    mp = run_map(root, "--churn-since", "10 years ago", name="map_crime")
    ch = mp.get("churn")
    expect(ch is not None, "a git repo with commits must yield churn")
    expect(ch["commits"] == 3, f"3 commits expected, got {ch['commits']}")
    expect(ch["files"]["busy.py"]["c"] == 3
           and ch["files"]["calm.py"]["c"] == 1,
           f"per-file churn wrong: {ch['files']}")
    expect(ch["since"] == "10 years ago",
           "the window must be recorded — the legend names it")
    cx = {m["id"]: m["cx"] for m in mp["modules"]}
    expect(cx["busy"] >= 2 and cx["calm"] == 0,
           f"decision points wrong: {cx}")


@check("map crime scene: honestly absent without git history (#95)")
def _():
    root = os.path.join(TMP, "norepo")
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "solo.py"), "w") as fh:
        fh.write("x = 1\nif x:\n    print(x)\n")
    mp = run_map(root, name="map_norepo")
    expect(mp.get("churn") is None,
           "no readable history -> churn must be null, never guessed")
    expect(mp["modules"][0]["cx"] == 1,
           f"cx is AST-side and must survive without git: "
           f"{mp['modules'][0]}")


@check("slice dataflow: return, loop and walrus targets tracked (#75)")
def _():
    fx = fixture("fx_slice_df.py", (
        "def f(k):\n"
        "    m = k * 3\n"
        "    return m + 1\n"
        "total = 0\n"
        "for i in range(3):\n"
        "    total = total + i\n"
        "r = f(total)\n"
        "if (w := r + 1) > 5:\n"
        "    print(w)\n"))
    df = run_trace(fx, name="slice_df")["dataflow"]["fx_slice_df.py"]
    expect(df.get("3", {}).get("<return>") == ["m"],
           f"a return statement must expose its sources under "
           f"'<return>': {df.get('3')}")
    expect(df.get("5", {}).get("i") == ["range"],
           f"a loop variable draws from its iterable's names: "
           f"{df.get('5')}")
    expect(df.get("8", {}).get("w") == ["r"],
           f"a walrus target draws from its value: {df.get('8')}")


@check("slice: golden chain — the closure is exact on a known case (#75)")
def _():
    # mirrors the viewer's walk on a single-frame program where the
    # full closure is known by hand: d <- (c, a), c <- b, b <- a
    fx = fixture("fx_slice.py", (
        "a = 2\n"
        "b = a + 3\n"
        "c = b * b\n"
        "d = c + a\n"
        "print(d)\n"))
    p = run_trace(fx, name="slice_gold")
    evs, df = p["events"], p["dataflow"]["fx_slice.py"]

    def changes(name):
        return [i for i, e in enumerate(evs)
                if name in (e.get("ch") or {})]
    seed = changes("d")[-1]
    sl, frontier, queue, seen = set(), [], [("d", seed)], set()
    while queue:
        n, at = queue.pop(0)
        if (n, at) in seen:
            continue
        seen.add((n, at))
        sl.add(at)
        pj = at - 1          # single frame: every event is in it
        if pj < 0:
            frontier.append(n)
            continue
        srcs = df.get(str(evs[pj].get("l")), {}).get(n)
        if srcs is None:
            frontier.append(n)
            continue
        for s in srcs:
            prior = [j for j in changes(s) if j < at]
            if prior:
                queue.append((s, prior[-1]))
            else:
                frontier.append(s)
    expect(sl == {seed, changes("c")[-1], changes("b")[-1],
                  changes("a")[-1]},
           f"slice of d must be exactly the d/c/b/a chain, got {sl}")
    expect(not frontier,
           f"a fully name-tracked chain has no frontier: {frontier}")


@check("watch: observables ride the diff machinery; typo warns (#72)")
def _():
    fx = fixture("fx_watch.py", (
        "nums = [5, 1, 4, 2]\n"
        "total = 0\n"
        "for i in range(len(nums)):\n"
        "    total += nums[i]\n"
        "nums.sort()\n"
        "print(total)\n"))
    out = os.path.join(TMP, "fx_watch.html")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"), "--out", out,
                        "--watch", "sum(nums)", "--watch", "nums[0]",
                        "--watch", "len(nozzle)", fx],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=120)
    p = payload(out)

    def wch(key):
        return [(i, e["ch"][key]) for i, e in enumerate(p["events"])
                if key in (e.get("ch") or {})]
    s = wch("watch:sum(nums)")
    expect(len(s) == 1 and s[0][1]["v"] == "12",
           f"sum(nums) is conserved: exactly one birth change of 12, "
           f"got {s}")
    n0 = wch("watch:nums[0]")
    expect(len(n0) == 2 and [c[1]["v"] for c in n0] == ["5", "1"],
           f"nums[0] changes at birth and at the sort: {n0}")
    expect(not wch("watch:len(nozzle)"),
           "a never-evaluable watch must record NOTHING")
    expect("never evaluable" in (r.stdout + r.stderr),
           "the typo watch must warn at the end")
    r2 = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                         "--watch", "x", "--granularity", "fn",
                         "--out", os.path.join(TMP, "wfn.html"), fx],
                        capture_output=True, text=True, cwd=TMP,
                        stdin=subprocess.DEVNULL, timeout=60)
    expect(r2.returncode == 2, "watch under fn granularity must refuse")


@check("invariant: entry-transitions only, values captured, verdicts (#73)")
def _():
    fx = fixture("fx_inv.py", (
        "balance = 10\n"
        "steps = [-4, -9, 5, -7, 2]\n"
        "for d in steps:\n"
        "    balance += d\n"
        "print(balance)\n"))
    out = os.path.join(TMP, "fx_inv.html")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"), "--out", out,
                        "--invariant", "balance >= 0",
                        "--invariant", "balance <= 100",
                        "--invariant", "quux > 0", fx],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=120)
    p = payload(out)
    viols = [e for e in p["events"] if e.get("e") == "viol"]
    expect(len(viols) == 2,
           f"two ENTRIES into violation (stay-broken is silent, "
           f"recovery re-arms), got {len(viols)}")
    expect([v["vals"]["balance"]["v"] for v in viols] == ["-3", "-5"],
           f"violations must carry the offending values: {viols}")
    expect(all(v["inv"] == "balance >= 0" for v in viols),
           "only the broken contract records")
    meta = {m["src"]: m for m in p["invariants"]}
    expect(meta["balance >= 0"]["n"] == 2
           and meta["balance <= 100"]["n"] == 0
           and meta["balance <= 100"]["evals"] > 0
           and meta["quux > 0"]["evals"] == 0,
           f"per-invariant verdicts wrong: {meta}")
    expect("VIOLATED 2x" in r.stdout and "held everywhere" in r.stdout
           and "never evaluable" in r.stdout,
           f"terminal must state all three verdicts ({r.stdout})")
    r2 = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                         "--invariant", "x > 0", "--granularity", "fn",
                         "--out", os.path.join(TMP, "ifn.html"), fx],
                        capture_output=True, text=True, cwd=TMP,
                        stdin=subprocess.DEVNULL, timeout=60)
    expect(r2.returncode == 2,
           "invariant under fn granularity must refuse")


@check("map import cost: startup autopsy from <module> frames (#99)")
def _():
    root = os.path.join(TMP, "impdemo")
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "slowmod.py"), "w") as fh:
        fh.write("import time\ntime.sleep(0.08)\nX = 1\n")
    with open(os.path.join(root, "fastmod.py"), "w") as fh:
        fh.write("Y = 2\n")
    main_py = os.path.join(root, "main.py")
    with open(main_py, "w") as fh:
        fh.write("import slowmod\nimport fastmod\n"
                 "print(slowmod.X + fastmod.Y)\n")
    tr = os.path.join(root, "tr99.html")
    subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                    "--granularity", "fn", "--root", root,
                    "--out", tr, main_py],
                   capture_output=True, text=True, cwd=root,
                   stdin=subprocess.DEVNULL, timeout=120)
    mp = run_map(root, "--trace", tr, name="map_imp")
    ic = (mp.get("heat") or {}).get("importCost") or {}
    expect(ic.get("slowmod", 0) >= 40000,
           f"a sleeping import must show its cost (>=40ms): {ic}")
    expect(0 < ic.get("fastmod", 10 ** 9) < ic["slowmod"],
           f"a trivial import must cost less than the sleeper: {ic}")
    # honesty: line traces carry no timestamps -> no import cost
    tr2 = os.path.join(root, "tr99_line.html")
    subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                    "--root", root, "--out", tr2, main_py],
                   capture_output=True, text=True, cwd=root,
                   stdin=subprocess.DEVNULL, timeout=120)
    mp2 = run_map(root, "--trace", tr2, name="map_imp_line")
    expect(not ((mp2.get("heat") or {}).get("importCost") or {}),
           "a line trace has no wall times — the autopsy must be "
           "absent, never fiction")


@check("critical path: the spine crosses lanes; sequential abstains (#89)")
def _():
    p = run_trace(os.path.join(HERE, "example_tasks.py"),
                  "--granularity", "fn", name="cp_tasks")
    c = p.get("critical")
    expect(c is not None, "a concurrent fn trace must carry its path")
    expect(c["lanes"] >= 3,
           f"the asyncio spine must cross task lanes: {c['lanes']}")
    expect(all(p["events"][i]["e"] == "call" for i in c["evs"]),
           "spine entries must be call events")
    expect(c["gapUs"] > 0,
           "asyncio.sleep must surface as untracked external waits")
    segs = c["segs"]
    expect(all(a[1] <= b[0] for a, b in zip(segs, segs[1:]))
           and all(s[0] < s[1] for s in segs),
           "spine segments must be ordered and non-overlapping")
    q = run_trace(os.path.join(HERE, "example_race.py"),
                  "--granularity", "fn", name="cp_race")
    expect(q["critical"] and q["critical"]["lanes"] >= 2,
           "thread workers must appear on the race's spine")
    s = run_trace(os.path.join(HERE, "example_sort.py"),
                  "--granularity", "fn", name="cp_sort")
    expect(s.get("critical") is None,
           "a single-lane run has no critical path to claim")
    out = os.path.join(TMP, "cp89.json")
    subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                    "--granularity", "fn", "--export-perfetto", out,
                    "--out", os.path.join(TMP, "cp89.html"),
                    os.path.join(HERE, "example_tasks.py")],
                   capture_output=True, text=True, cwd=TMP,
                   stdin=subprocess.DEVNULL, timeout=120)
    with open(out, encoding="utf-8") as fh:
        te = json.load(fh)["traceEvents"]
    kt = [e for e in te if e.get("tid") == 9999]
    expect(any(e["ph"] == "M" and "critical" in e["args"]["name"]
               for e in kt), "the ★ critical path row must exist")
    bs = sum(1 for e in kt if e["ph"] == "B")
    es = sum(1 for e in kt if e["ph"] == "E")
    expect(bs > 0 and bs == es,
           f"★ row segments must be balanced B/E pairs: {bs}/{es}")


@check("anatomy: AST + dis records, innermost spans, fn-honesty (#85)")
def _():
    src = fixture("an85.py", (
        "def outer(a, b):\n"
        "    def inner(x):\n"
        "        return x * 2\n"
        "    if a < b:\n"
        "        a, b = b, a\n"
        "    return inner(a)\n"
        "\n"
        "print(outer(3, 5))\n"))
    p = run_trace(src)
    an = (p.get("anatomy") or {}).get("an85.py")
    expect(an and an.get("py"), "line traces must carry anatomy + version")
    recs = {r["q"]: r for r in an["recs"]}
    expect({"<module>", "outer", "outer.<locals>.inner"} <= set(recs),
           f"module + defs with real qualnames expected: {set(recs)}")
    o = recs["outer"]
    expect(o["l0"] == 1 and o["l1"] == 6, f"outer span wrong: {o}")
    ops = [r[1] for r in o["dis"]]
    expect("COMPARE_OP" in ops,
           "a < b must compile to COMPARE_OP in outer's listing")
    expect(any(r[4] for r in o["dis"]),
           "jump targets must be flagged for the » marker")
    expect(all(r[3] is None or o["l0"] <= r[3] <= o["l1"]
               for r in o["dis"]),
           "every instruction's line must sit inside its record's span")
    # innermost pick: line 3 belongs to inner, not outer or <module>
    inner = [r for r in an["recs"] if r["l0"] <= 3 <= r["l1"]]
    best = min(inner, key=lambda r: r["l1"] - r["l0"])
    expect(best["q"] == "outer.<locals>.inner",
           f"innermost record for line 3 must be inner: {best['q']}")
    expect(best["ast"][0].startswith("FunctionDef"),
           f"record AST root must be its def node: {best['ast'][0]}")
    # honesty: fn granularity has no current line — no anatomy fiction
    q = run_trace(src, "--granularity", "fn", name="an85_fn")
    expect(not q.get("anatomy"),
           "fn traces must not carry anatomy (no line to dissect)")


@check("cfg: typed edges, exact observed weights, dead code (#131)")
def _():
    src = fixture("cfg131.py", (
        "def classify(xs):\n"
        "    total = 0\n"
        "    for x in xs:\n"
        "        if x < 0:\n"
        "            continue\n"
        "        if x > 100:\n"
        "            break\n"
        "        total += x\n"
        "    else:\n"
        "        total += 1\n"
        "    return total\n"
        "\n"
        "def dead_tail(a):\n"
        "    return a\n"
        "    a += 1\n"
        "\n"
        "def pick(flag):\n"
        "    if flag:\n"
        "        return 1\n"
        "    return 0\n"
        "\n"
        "print(classify([4, -1, 7, 2]), classify([50, 200, 9]),\n"
        "      dead_tail(1), pick(True))\n"))
    p = run_trace(src)
    recs = {r["q"]: r for r in p["cfg"]["cfg131.py"]["recs"]}
    c = recs["classify"]
    kinds = {k for _, _, k in c["edges"]}
    expect({"seq", "true", "false", "loop", "continue", "break",
            "return"} <= kinds, f"edge grammar incomplete: {kinds}")
    ln2b = {}
    for bi, lines in enumerate(c["blocks"]):
        for ln in lines:
            ln2b.setdefault(ln, bi)
    w = c.get("w") or {}

    def wof(a, b, k=None):
        for s, d, kk in c["edges"]:
            if s == ln2b[a] and d == ln2b[b] and (k is None or kk == k):
                return w.get(f"{s}-{d}", 0)
        raise Fail(f"no edge L{a}->L{b} ({k})")
    # hand-traced: [4,-1,7,2] exhausts into the else; [50,200,9] breaks
    expect(wof(5, 3, "continue") == 1, "continue must be observed once")
    expect(wof(7, 11, "break") == 1, "break must skip the for-else once")
    expect(wof(3, 10, "false") == 1,
           "for-else entered exactly once (the broken run skips it)")
    expect(wof(8, 3, "loop") == 4, "four normal iterations loop back")
    expect(wof(4, 5, "true") == 1 and wof(4, 6, "false") == 5,
           "if x<0 verdict counts must be 1/5")
    expect((c.get("h") or {}).get(str(c["entry"])) == 2,
           "classify entered twice")
    expect(recs["dead_tail"]["unreach"],
           "code after return must be unreachable by construction")
    pk = recs["pick"]
    ghost = [f"{s}-{d}" for s, d, k in pk["edges"] if k == "false"]
    expect(ghost and all((pk.get("w") or {}).get(g, 0) == 0
                         for g in ghost),
           "pick(True) only: the false edge exists and carries no "
           "weight — ghosted, never conflated with unreachable")
    expect(not recs["pick"]["unreach"],
           "pick's untaken branch is reachable — ghost, not unreach")
    q = run_trace(src, "--granularity", "fn", name="cfg131_fn")
    expect(not q.get("cfg"),
           "fn traces carry no CFG weights (no line events to walk)")


@check("call tree: projection counts, generator reattachment (#133)")
def _():
    src = fixture("tree133.py", (
        "def fib(n):\n"
        "    if n < 2:\n"
        "        return n\n"
        "    return fib(n - 1) + fib(n - 2)\n"
        "\n"
        "def gen():\n"
        "    yield 1\n"
        "    yield 2\n"
        "\n"
        "g = gen()\n"
        "next(g); next(g)\n"
        "print(fib(5))\n"))
    p = run_trace(src)
    # mirror of the viewer's buildTree: node per call, resumes REATTACH
    nodes, stacks, saved = [], {}, {}
    for ev in p["events"]:
        lane = (ev.get("t") or "main", ev.get("tk") or "")
        st = stacks.setdefault(lane, [])
        if ev["e"] == "call":
            gm = ev.get("g")
            if gm and gm.get("s") == "r" and gm.get("i") in saved:
                nid = saved.pop(gm["i"])
                nodes[nid]["resumes"] += 1
                st.append(nid)
                continue
            nodes.append({"fn": ev["fn"], "depth": len(st),
                          "resumes": 0, "ret": None})
            st.append(len(nodes) - 1)
            continue
        if not st:
            continue
        if ev["e"] == "return":
            gm = ev.get("g")
            if gm and gm.get("s") == "y":
                saved[gm["i"]] = st[-1]
            else:
                nodes[st[-1]]["ret"] = ev.get("ret")
            st.pop()
    fibs = [n for n in nodes if n["fn"] == "fib"]
    expect(len(fibs) == 15, f"fib(5) must project 15 nodes: {len(fibs)}")
    depths = collections.Counter(n["depth"] for n in fibs)
    expect(depths == collections.Counter({1: 1, 2: 2, 3: 4, 4: 6, 5: 2}),
           f"the recurrence's level counts are wrong: {dict(depths)}")
    expect(all(n["ret"] is not None for n in fibs),
           "every fib frame returned — every node must carry its value")
    gens = [n for n in nodes if n["fn"] == "gen"]
    expect(len(gens) == 1,
           "a resumed generator must stay ONE node, never phantom calls")
    expect(gens[0]["resumes"] == 1 and gens[0]["ret"] is None,
           f"gen: one resume, still suspended (never exhausted): {gens}")
    expect(all("n" in e.get("ch", {}) for e in p["events"]
               if e["e"] == "call" and e["fn"] == "fib"),
           "arguments must ride every call event (the tree's labels)")


@check("motion layer: honesty legend + play-only gating (#135)")
def _():
    with open(os.path.join(HERE, "replayer_template.html"),
              encoding="utf-8") as fh:
        tpl = fh.read()
    expect(tpl.count("only the endpoints are recorded truth") >= 2,
           "the interpolation legend must appear on the play control "
           "AND in presentation mode — motion may never pose as data")
    expect("motionOn ? motionSnap()" in tpl,
           "tweens must be gated on play — single-step stays inert")
    expect("motionOn = false" in tpl and "motionOn = true" in tpl,
           "stop()/play() must arm and disarm the motion layer")
    expect("body.presenting" in tpl and 'id="presnote"' in tpl,
           "presentation mode: chrome-hiding CSS + the on-screen note")
    for probe in ("data-mkey", "el.animate"):
        expect(probe in tpl, f"FLIP machinery missing: {probe}")


@check("sweep: exponent fit, claim verdicts, gen protocol, honesty (#127)")
def _():
    quad = fixture("quad127.py", (
        "import sys\n"
        "def cmp(a, b):\n"
        "    return a < b\n"
        "def work(n):\n"
        "    t = 0\n"
        "    for i in range(n):\n"
        "        for j in range(n):\n"
        "            t += cmp(i, j)\n"
        "    return t\n"
        "n = int(sys.stdin.readline())\n"
        "if n > 20:\n"
        "    raise ValueError('too big')\n"
        "print(work(n))\n"))

    def sweep(*flags, name):
        out = os.path.join(TMP, name + ".html")
        r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                            "--out", out, *flags, quad],
                           capture_output=True, text=True, cwd=TMP,
                           stdin=subprocess.DEVNULL, timeout=300)
        data = None
        if os.path.exists(out):
            with open(out, encoding="utf-8") as fh:
                m = re.search(r'<script id="sweep-data" type="application/'
                              r'json">(.*?)</script>', fh.read(), re.S)
            data = (json.loads(m.group(1).replace("<\\/", "</"))
                    if m else None)
        return r, data
    r, d = sweep("--sweep", "n=4,8,16", "--predict", "n^2", name="sw2")
    expect(d is not None, f"sweep report missing ({r.stdout} {r.stderr})")
    expect(all(g["status"] == "ok" for g in d["rungs"]),
           f"all rungs must be clean: {[g['status'] for g in d['rungs']]}")
    expect(abs(d["fitE"]["slope"] - 2.0) < 0.2 and d["fitE"]["r2"] > 0.99,
           f"a quadratic must fit n^2 in EVENTS: {d['fitE']}")
    expect(d["claim"]["verdict"] is True,
           f"claim n^2 must be CONSISTENT: {d['claim']}")
    expect(r.returncode == 0, "clean fit exits 0")
    r3, d3 = sweep("--sweep", "n=4,8,16", "--predict", "n^3", name="sw3")
    expect(d3["claim"]["verdict"] is False,
           f"claim n^3 must be rejected on quadratic data: {d3['claim']}")
    # gen protocol: gen(v, seed) DOUBLES the size — if the protocol were
    # ignored, counts would match the default-stdin run
    gen = fixture("gen127.py", (
        "def gen(n, seed):\n"
        "    assert isinstance(seed, int)\n"
        "    return str(n * 2) + chr(10)\n"))
    rg, dg = sweep("--sweep", "n=4,8", "--gen", gen, name="swg")
    base = {g["v"]: g["events"] for g in d["rungs"]}
    expect(dg["rungs"][0]["events"] > base[4] * 3,
           "gen(v,seed) must drive the input (doubled size ≈ 4× events)")
    # honesty: a crashing rung is excluded, named, and the fit survives
    rc, dc = sweep("--sweep", "n=4,8,32", name="swc")
    st = [g["status"] for g in dc["rungs"]]
    expect(st[2].startswith("crashed: ValueError"),
           f"the n=32 rung must be excluded as crashed: {st}")
    expect(dc["fitE"] is not None,
           "two clean rungs still fit (partial ladder, stated)")
    # a claim that is not just n and log() is refused, never evaluated
    rbad, _ = sweep("--sweep", "n=4,8",
                    "--predict", "__import__('os').getcwd()", name="swb")
    expect(rbad.returncode == 2 and "--predict" in rbad.stdout,
           f"malicious claim must be refused: {rbad.returncode} "
           f"{rbad.stdout[:120]}")


@check("prediction gate: loop-claim truth mirror + gate contract (#128)")
def _():
    p = run_trace(os.path.join(HERE, "bubble_sort.py"), name="gate128")
    events = p["events"]
    # frame ids, the viewer's way: call pushes, return pops, per lane
    fids, stacks, nxt = [], {}, [0]
    for ev in events:
        st = stacks.setdefault(ev.get("t", "main"), [])
        if ev["e"] == "call":
            st.append(nxt[0])
            nxt[0] += 1
        fids.append(st[-1] if st else -1)
        if ev["e"] == "return" and st:
            st.pop()

    def loop_total(i0):
        # mirror of the viewer's gateCommitLoop scan
        fid, line = fids[i0], events[i0]["l"]
        trues = 0
        for j in range(i0, len(events)):
            if fids[j] != fid:
                continue
            e2 = events[j]
            c = e2.get("cond")
            if e2["l"] == line and c and c.get("k") in ("for", "while"):
                if c["r"] is False:
                    return c.get("i", trues) if c["k"] == "for" else trues
                trues += 1
            if e2["e"] == "return":
                break
        return None
    entries = {}   # line -> totals at each FRESH entry (i == 1)
    for i, ev in enumerate(events):
        c = ev.get("cond")
        if c and c.get("k") == "for" and c.get("r") and c.get("i") == 1:
            entries.setdefault(ev["l"], []).append(loop_total(i))
    # bubble_sort([5,2,4,1]): outer for runs 4x; inner entries run 3,2,1
    # (the 4th outer pass enters range(-1+4-... n-1-i = 0) -> i=1 never
    # fires, so only three fresh inner entries exist)
    expect(entries.get(3) == [4],
           f"outer for total must be 4: {entries.get(3)}")
    expect(entries.get(4) == [3, 2, 1],
           f"inner for totals must be 3,2,1: {entries.get(4)}")
    with open(os.path.join(HERE, "replayer_template.html"),
              encoding="utf-8") as fh:
        tpl = fh.read()
    expect(tpl.count("#128: claims before steps") == 2,
           "BOTH forward-step paths (button + ArrowRight) must be "
           "gate-guarded")
    for probe in ('id="gatebar"', "pyreplay-gate:", "step unscored",
                  "pyreplay-predictions.json",
                  "only committed claims count"):
        expect(probe in tpl, f"gate contract missing: {probe}")


@check("mining: survivors, kills, window honesty, support math (#74)")
def _():
    src = fixture("mine74.py", (
        "def scale(xs, k, cap):\n"
        "    out = []\n"
        "    total = 0\n"
        "    for x in xs:\n"
        "        total += x * k\n"
        "        out.append(x * k)\n"
        "    return sorted(out)\n"
        "\n"
        "def big():\n"
        "    return list(range(200))\n"
        "\n"
        "for trial in range(4):\n"
        "    scale([3, 1, 2], trial + 1, 100)\n"
        "scale([5, 4, 9, 2, 8], -1, 100)\n"
        "big()\n"))
    p = run_trace(src)
    mined = p.get("mined") or {}
    m = mined.get("mine74.py:scale")
    expect(m and m["frames"] == 5, f"five scale observations: {m}")
    facts = {f["s"]: f["sup"] for f in m["facts"]}
    expect(facts.get("cap == 100 at entry") == 5,
           f"constant arg must survive with full support: {facts}")
    expect(facts.get("cap >= k at entry") == 5,
           "the pair template must survive (100 >= every k)")
    expect("k > 0 at entry" not in facts,
           "the k=-1 call must KILL the sign fact — first "
           "counterexample is fatal")
    expect(facts.get("k: type int constant at entry") == 5,
           "the type fact survives the sign kill")
    expect(facts.get("return value sorted (ascending)") == 5,
           "sorted(out) at return must be mined")
    expect("total monotonically nondecreasing (per call)" not in facts,
           "k=-1 makes total decrease — monotone must die")
    expect(not any("scale ==" in s for key in mined
                   for s in [f["s"] for f in mined[key]["facts"]]),
           "function objects are machinery — never mined as data")
    mb = mined.get("mine74.py:big")
    expect(mb is None or not any("sorted" in f["s"] for f in mb["facts"]),
           "a WINDOWED container (200 > recorded window) must never "
           "claim sortedness — judged only when fully recorded")
    # --mine mode: same trace twice -> support doubles; sidecar written
    tr = os.path.join(TMP, "mine74.py.html")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--mine", tr, tr],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=120)
    expect("cap == 100 at entry   [held 10x]" in r.stdout,
           f"support must SUM across mined traces: {r.stdout[-400:]}")
    side = os.path.join(TMP, "mined_mine74.py.json")
    expect(os.path.exists(side), "the JSON sidecar must be written")
    with open(side, encoding="utf-8") as fh:
        sj = json.load(fh)
    expect(sj["mine74.py:scale"]["runs"] == 2,
           "the sidecar counts contributing traces as runs")
    # --runs N --mine: fingerprints survive trace deletion into report
    rout = os.path.join(TMP, "runs_mine74.html")
    r2 = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                         "--runs", "2", "--mine",
                         "--granularity", "line", "--out", rout, src],
                        capture_output=True, text=True, cwd=TMP,
                        stdin=subprocess.DEVNULL, timeout=300)
    with open(rout, encoding="utf-8") as fh:
        mm = re.search(r'<script id="runs-data" type="application/'
                       r'json">(.*?)</script>', fh.read(), re.S)
    rd = json.loads(mm.group(1).replace("<\\/", "</"))
    rm = (rd.get("mined") or {}).get("mine74.py:scale")
    expect(rm and rm["runs"] == 2 and rm["frames"] == 10,
           f"--runs 2 --mine must aggregate 10 calls / 2 runs: {rm}")


@check("graph lens: betweenness, communities, percolation exact (#129)")
def _():
    # two triangles bridged through br: a1→br→b1 is the only corridor
    root = os.path.join(TMP, "glens")
    os.makedirs(root, exist_ok=True)
    files = {"a1.py": "import a2\nimport a3\nimport br\n",
             "a2.py": "import a3\n", "a3.py": "",
             "br.py": "import b1\n",
             "b1.py": "import b2\nimport b3\n",
             "b2.py": "", "b3.py": ""}
    for name, text in files.items():
        with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    mp = run_map(root, name="map_glens")
    g = mp.get("graphlens")
    expect(g, "a 7-module map must carry the graph lens")
    # Brandes, hand-computed: b1 sits on 4 shortest paths, br on 3
    expect(g["between"].get("b1") == 4.0 and g["between"].get("br") == 3.0,
           f"betweenness must be exact (b1=4, br=3): {g['between']}")
    c = g["community"]
    expect(len(set(c.values())) == 2,
           f"two triangles = two communities: {c}")
    expect(c["a1"] == c["a2"] and c["b1"] == c["b2"]
           and c["a1"] != c["b1"],
           f"clusters must separate across the bridge: {c}")
    p = g["percolation"]
    expect(p[0]["giant"] == 1.0 and p[0]["k"] == 0,
           f"intact map is fully connected: {p[0]}")
    expect(p[1]["removed"] == "b1" and p[1]["giant"] == round(4 / 7, 3),
           f"removing the top-between module must shatter the giant "
           f"component to 4/7: {p[1]}")
    expect(g["degrees"] == {"1": 2, "2": 3, "3": 2},
           f"degree histogram wrong: {g['degrees']}")
    # honesty + surfaces pinned in the template
    with open(os.path.join(HERE, "map_template.html"),
              encoding="utf-8") as fh:
        tpl = fh.read()
    for probe in ('value="graph"', ".mod.comm0 rect", "initial ranking",
                  "static import graph", "proves nothing"):
        expect(probe in tpl, f"graph-lens contract missing: {probe}")
    # a one-module map has no graph to analyze — null, never fiction
    solo = os.path.join(TMP, "glens_solo")
    os.makedirs(solo, exist_ok=True)
    with open(os.path.join(solo, "only.py"), "w", encoding="utf-8") as fh:
        fh.write("x = 1\n")
    mp2 = run_map(solo, name="map_glens_solo")
    expect(mp2.get("graphlens") is None,
           "a single module carries no graph lens (nothing to rank)")


@check("fsm: mined machine, forbidden splice, gap honesty (#132)")
def _():
    src = fixture("fsm132.py", (
        "class Order:\n"
        "    def __init__(self):\n"
        "        self.status = 'new'\n"
        "def advance(order, to):\n"
        "    order.status = to\n"
        "def process(order):\n"
        "    advance(order, 'paid')\n"
        "    advance(order, 'shipped')\n"
        "    advance(order, 'delivered')\n"
        "    advance(order, 'paid')\n"
        "    advance(order, 'cancelled')\n"
        "order = Order()\n"
        "process(order)\n"
        "print(order.status)\n"))
    dec = fixture("fsm132.txt", (
        "# the whiteboard lifecycle\n"
        "new -> paid\n"
        "paid -> shipped\n"
        "shipped -> delivered\n"
        "paid -> cancelled\n"))
    p = run_trace(src, "--fsm", "order.status", "--fsm-declare", dec)
    f = p["fsm"]
    names = [s["v"] for s in f["states"]]
    expect(names == ["new", "paid", "shipped", "delivered", "cancelled"],
           f"states in first-seen order: {names}")
    expect(all(s["dwell"] > 0 for s in f["states"]),
           "every state must carry dwell")
    ed = {(names[e["a"]], names[e["b"]]):
          (e["n"], e["forbidden"]) for e in f["edges"]}
    expect(ed == {("new", "paid"): (1, False),
                  ("paid", "shipped"): (1, False),
                  ("shipped", "delivered"): (1, False),
                  ("delivered", "paid"): (1, True),
                  ("paid", "cancelled"): (1, False)},
           f"the machine must be exact, refund edge forbidden: {ed}")
    viols = [i for i, e in enumerate(p["events"]) if e["e"] == "viol"]
    expect(len(viols) == 1 and f["viol"] == 1,
           f"exactly one derived viol event: {viols}")
    ve = p["events"][viols[0]]
    expect("not declared" in ve["inv"] and ve.get("fn"),
           f"the viol names the edge and its frame: {ve}")
    prev = p["events"][viols[0] - 1]
    expect("watch:order.status" in (prev.get("ch") or {}),
           "the viol must sit right after the observing event")
    obs_idx = [o[0] for o in f["obs"]]
    expect(obs_idx == sorted(obs_idx) and f["obs"][0][1] == 0,
           "observations strictly ordered, first state first")
    # without a declare file: mined only — nothing forbidden, no viols
    q = run_trace(src, "--fsm", "order.status", name="fsm132_free")
    expect(q["fsm"]["viol"] == 0
           and not any(e["forbidden"] for e in q["fsm"]["edges"])
           and not any(e["e"] == "viol" for e in q["events"]),
           "no declaration = a mined machine, never a checker")
    # gap honesty: a state that DIES and returns changed crosses a gap
    src2 = fixture("fsm132_gap.py", (
        "class Box:\n"
        "    pass\n"
        "b = Box()\n"
        "b.state = 'on'\n"
        "b.state = 'off'\n"
        "del b\n"
        "x = 1\n"
        "b = Box()\n"
        "b.state = 'on'\n"
        "print(b.state)\n"))
    g = run_trace(src2, "--fsm", "b.state", name="fsm132_gap")
    ge = {(g["fsm"]["states"][e["a"]]["v"],
           g["fsm"]["states"][e["b"]]["v"]): e["gap"]
          for e in g["fsm"]["edges"]}
    expect(ge.get(("on", "off")) is False and ge.get(("off", "on")),
           f"the transition across the del must wear the gap flag: {ge}")
    # gates: one name only; declare needs fsm; fn granularity refused
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--fsm", "a", "--fsm", "b", src],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=60)
    expect(r.returncode == 2 and "ONE declared name" in r.stdout,
           "--fsm binds one name")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--fsm-declare", dec, src],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=60)
    expect(r.returncode == 2, "--fsm-declare without --fsm refused")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--granularity", "fn", "--fsm", "order.status",
                        src], capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=60)
    expect(r.returncode == 2 and "LINE event" in r.stdout,
           "--fsm at fn granularity refused with the reason")
    # #63 aggregation: two runs, one machine, counts doubled
    rout = os.path.join(TMP, "runs_fsm132.html")
    subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                    "--runs", "2", "--granularity", "line",
                    "--fsm", "order.status", "--fsm-declare", dec,
                    "--out", rout, src],
                   capture_output=True, text=True, cwd=TMP,
                   stdin=subprocess.DEVNULL, timeout=300)
    with open(rout, encoding="utf-8") as fh:
        mm = re.search(r'<script id="runs-data" type="application/'
                       r'json">(.*?)</script>', fh.read(), re.S)
    rf = json.loads(mm.group(1).replace("<\\/", "</")).get("fsm")
    expect(rf and rf["runs"] == 2
           and rf["edges"]["delivered -> paid"]["n"] == 2
           and rf["edges"]["delivered -> paid"]["forbidden"],
           f"two runs must merge into ONE machine, counts summed: {rf}")


@check("compressibility: the phase change is measurable (#130)")
def _():
    src = fixture("phases130.py", (
        "import hashlib\n"
        "def tight(n):\n"
        "    total = 0\n"
        "    for i in range(n):\n"
        "        total += i\n"
        "    return total\n"
        "def wander(n):\n"
        "    blob = []\n"
        "    for i in range(n):\n"
        "        h = hashlib.sha256(str(i).encode()).hexdigest()\n"
        "        blob.append(h[: (i * 7) % 40 + 3])\n"
        "    return len(blob)\n"
        "print(tight(220))\n"
        "print(wander(220))\n"))
    p = run_trace(src)
    C = p.get("compress")
    expect(C and C["buckets"], "a 1000-event trace must carry the strip")
    expect(sum(b[0] for b in C["buckets"]) == len(p["events"]),
           "the buckets must cover every event exactly once")
    expect(all(b[2] < b[1] for b in C["buckets"]),
           "gzip of event JSON must always shrink it")
    bits = [c * 8 / n for n, _, c in C["buckets"]]
    half = len(bits) // 2
    a = sum(bits[:half]) / half
    b = sum(bits[half:]) / (len(bits) - half)
    expect(b > a * 1.5,
           f"the wandering half must cost visibly more bits/event "
           f"than the tight loop ({a:.0f} vs {b:.0f})")
    # a tiny trace has no strip — 120 buckets of 0.3 events is noise
    q = run_trace(os.path.join(HERE, "bubble_sort.py"),
                  name="c130_tiny")
    expect(q.get("compress") is None,
           "under 50 events the strip is honestly absent")
    with open(os.path.join(HERE, "replayer_template.html"),
              encoding="utf-8") as fh:
        tpl = fh.read()
    expect("upper bound on the entropy rate" in tpl.lower()
           and 'id = "compress"' in tpl.replace("cbox.id = ", 'id = '),
           "the strip must exist and call itself an upper bound — "
           "compressibility, never bare entropy")


@check("memo DAG: exact edges, pre/base honesty, frontiers (#134)")
def _():
    src = fixture("memo134.py", (
        "def count_paths(n, m):\n"
        "    dp = [[0] * m for _ in range(n)]\n"
        "    for j in range(m):\n"
        "        dp[0][j] = 1\n"
        "    for i in range(n):\n"
        "        dp[i][0] = 1\n"
        "    for i in range(1, n):\n"
        "        for j in range(1, m):\n"
        "            dp[i][j] = dp[i - 1][j] + dp[i][j - 1]\n"
        "    return dp[n - 1][m - 1]\n"
        "print(count_paths(4, 5))\n"))
    p = run_trace(src, "--memo", "dp")
    M = p["memo"]
    names = [c["k"] for c in M["cells"]]
    expect(len(names) == 20 and len(M["edges"]) == 24,
           f"4x5 grid: 20 cells, 24 edges: {len(names)}/"
           f"{len(M['edges'])}")
    expect(M["preReads"] == 0 and M["untracked"] == 0,
           f"a clean forward DP has no pre-write reads and no "
           f"frontiers: {M['preReads']}/{M['untracked']}")
    deps = sorted(names[e["a"]] for e in M["edges"]
                  if names[e["b"]] == "1,1")
    expect(deps == ["0,1", "1,0"],
           f"dp[1][1] must depend on left+above exactly: {deps}")
    expect(len(M["fills"]) == 21,
           f"20 first-writes + dp[0][0] rewritten = 21: "
           f"{len(M['fills'])}")
    expect(M["bulk"] is not None,
           "the [[0]*m...] init is a recorded bulk moment")
    # the wrong-order recurrence: pre-write reads flagged, base split
    bug = fixture("memo134b.py", (
        "def countdown(n):\n"
        "    dp = [0] * n\n"
        "    for i in range(n - 1):\n"
        "        dp[i] = dp[i + 1] + 1\n"
        "    return dp[0]\n"
        "print(countdown(4))\n"))
    pb = run_trace(bug, "--memo", "dp", name="memo134b")
    nb = [c["k"] for c in pb["memo"]["cells"]]
    kinds = {(nb[e["a"]], nb[e["b"]]): ("pre" if e["pre"] else
             "base" if e["base"] else "ok")
             for e in pb["memo"]["edges"]}
    expect(kinds == {("1", "0"): "pre", ("2", "1"): "pre",
                     ("3", "2"): "base"},
           f"reads of later-computed cells are PRE, of never-computed "
           f"bulk cells BASE: {kinds}")
    # rolling knapsack: round-1 reads of later-written cells are PRE
    # ON PURPOSE — the tool states the fact, never guesses intent
    knap = fixture("memo134k.py", (
        "def knapsack(items, cap):\n"
        "    dp = [0] * (cap + 1)\n"
        "    for w, v in items:\n"
        "        for j in range(cap, w - 1, -1):\n"
        "            dp[j] = max(dp[j], dp[j - w] + v)\n"
        "    return dp[cap]\n"
        "print(knapsack([(2, 3), (3, 4), (4, 5)], 5))\n"))
    pk = run_trace(knap, "--memo", "dp", name="memo134k")
    expect(pk["memo"]["preReads"] == 2
           and any(e["base"] for e in pk["memo"]["edges"])
           and pk["memo"]["untracked"] == 0,
           f"rolling arrays wear PRE (amber, stated), bases dashed: "
           f"{pk['memo']['preReads']}")
    # a dependency routed through a CALL is the stated #75 remainder:
    # dict-memo fib shows its cells but no cross-frame edges
    fib = fixture("memo134f.py", (
        "memo = {}\n"
        "def fib(n):\n"
        "    if n < 2:\n"
        "        return n\n"
        "    if n in memo:\n"
        "        return memo[n]\n"
        "    memo[n] = fib(n - 1) + fib(n - 2)\n"
        "    return memo[n]\n"
        "print(fib(6))\n"))
    pf = run_trace(fib, "--memo", "memo", name="memo134f")
    fk = [c["k"] for c in pf["memo"]["cells"]]
    expect({"2", "3", "4", "5", "6"} <= set(fk),
           f"dict-memo cells must appear: {fk}")
    expect(len(pf["memo"]["edges"]) == 0,
           "cross-frame dependencies (through fib's calls) are the "
           "stated #75 remainder — never guessed as edges")
    # slice writes are counted frontiers, never guessed
    sl = fixture("memo134s.py", (
        "dp = [0] * 6\n"
        "dp[1:3] = [9, 9]\n"
        "dp[4] = dp[3] + 1\n"
        "print(dp)\n"))
    ps = run_trace(sl, "--memo", "dp", name="memo134s")
    expect(ps["memo"]["untracked"] >= 1,
           "a slice write is an untracked frontier, counted")
    # gates
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--memo", "a.b", src],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=60)
    expect(r.returncode == 2 and "plain name" in r.stdout,
           "dotted --memo refused with the reason")
    r = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--granularity", "fn", "--memo", "dp", src],
                       capture_output=True, text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=60)
    expect(r.returncode == 2 and "LINE" in r.stdout,
           "--memo at fn granularity refused")


@check("relations: the symmetry oracle, kept pairs, diverge (#126)")
def _():
    sumpy = fixture("rel126_sum.py", (
        "import sys\n"
        "nums = [int(t) for t in sys.stdin.read().split()]\n"
        "print(sum(nums))\n"))
    firstpy = fixture("rel126_first.py", (
        "import sys\n"
        "nums = [int(t) for t in sys.stdin.read().split()]\n"
        "print(nums[0] if nums else 0)\n"))
    gen = fixture("rel126_gen.py", (
        "import random\n"
        "def gen(n, seed):\n"
        "    rng = random.Random(seed * 1000 + n)\n"
        "    return ' '.join(str(rng.randint(-50, 99))\n"
        "                    for _ in range(6)) + chr(10)\n"))
    perm = "' '.join(reversed(x.split())) => out == out0"

    def rel(*args, **kw):
        return subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                               *args], capture_output=True, text=True,
                              cwd=TMP, timeout=600,
                              **(kw or {"stdin": subprocess.DEVNULL}))
    r = rel("--relation", perm, "--gen", gen, sumpy)
    expect(r.returncode == 0 and r.stdout.count(": held") == 3,
           f"sum is permutation-invariant: 3 trials must hold "
           f"({r.stdout[-200:]})")
    expect(not [f for f in os.listdir(TMP)
                if f.startswith("relation_rel126_sum")],
           "held trials must leave no kept traces behind")
    # homogeneity, with a GENEXP transform (pins the eval-globals fix:
    # helper names must be visible inside generator-expression bodies)
    r = rel("--relation", "' '.join(str(2 * int(t)) for t in "
            "x.split()) => num(out) == 2 * num(out0)",
            "--gen", gen, sumpy)
    expect(r.returncode == 0 and r.stdout.count(": held") == 3,
           f"sum is homogeneous — and genexp transforms must "
           f"evaluate: {r.stdout[-200:]}")
    # the asymmetric target: violations, kept pairs, composed command
    r = rel("--relation", perm, "--gen", gen, firstpy)
    expect(r.returncode == 1 and r.stdout.count("VIOLATED") == 3,
           f"first-token is order-dependent — all trials violate: "
           f"{r.stdout[-300:]}")
    expect("--diverge" in r.stdout and "kept:" in r.stdout,
           "each violation must keep the pair and compose the "
           "--diverge command")
    po = os.path.join(TMP, "relation_rel126_first_r1_t1_orig.html")
    px = os.path.join(TMP, "relation_rel126_first_r1_t1_xform.html")
    expect(os.path.exists(po) and os.path.exists(px),
           "the violated pair must exist on disk")
    # the composed command WORKS: #64 now sees console text as state
    d = subprocess.run([PY, os.path.join(HERE, "tracer.py"),
                        "--diverge", po, px], capture_output=True,
                       text=True, cwd=TMP,
                       stdin=subprocess.DEVNULL, timeout=120)
    expect("STATE diverges" in d.stdout and "log" in d.stdout,
           f"the pair differs ONLY in printed output — diverge must "
           f"see the console lane as state: {d.stdout[-300:]}")
    expect("PYTHONHASHSEED" in r.stdout or
           os.environ.get("PYTHONHASHSEED", "random") != "random",
           "a violation under hash randomization must carry the "
           "nondeterminism caveat")
    # gates
    b = rel("--relation", "no arrow here", sumpy)
    expect(b.returncode == 2 and "TRANSFORM => RELATION" in b.stdout,
           "a spec without => is refused with the grammar")
    b = rel("--relation", perm, "--no-console", sumpy)
    expect(b.returncode == 2 and "console lane" in b.stdout,
           "--no-console starves the output channel — refused")
    b = rel("--relation", perm, "--runs", "3", sumpy)
    expect(b.returncode == 2, "--relation with --runs refused")
    b = rel("--relation-trials", "3", sumpy)
    expect(b.returncode == 2, "--relation-trials needs --relation")


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
