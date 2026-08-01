"""Two threads move units between accounts with no lock. The invariant
(money is conserved) survives almost every natural schedule — the window
between reading a balance and writing it back is a few bytecodes wide.
--chaos-schedule stretches exactly such windows: what "never happens"
becomes a measured rate.

    python3 tracer.py --runs 12 --granularity line example_race.py
    python3 tracer.py --runs 12 --granularity line \
        --chaos-schedule 1 example_race.py

The failing runs raise RuntimeError at the conservation check; --diverge
a kept clean trace against a kept failing one to see the lost update.
"""
import threading

balance = {"a": 500, "b": 500}


def transfer(src, dst, amount, times):
    for _ in range(times):
        take = balance[src]
        give = balance[dst]
        balance[src] = take - amount
        balance[dst] = give + amount


t1 = threading.Thread(target=transfer, args=("a", "b", 1, 40))
t2 = threading.Thread(target=transfer, args=("b", "a", 1, 40))
t1.start()
t2.start()
t1.join()
t2.join()
total = balance["a"] + balance["b"]
if total != 1000:
    raise RuntimeError(f"conservation broken: {total} != 1000 — "
                       f"a lost update (the race fired)")
print("conserved:", total)
