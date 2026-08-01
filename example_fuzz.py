"""A ledger with a planted boundary bug, carrying its own input model.

One file, two roles — the target AND the generator:

    python3 tracer.py --fuzz example_fuzz.py --runs 20 example_fuzz.py

Most random ledgers balance fine. A refund bigger than the running
total followed by an audit breaks the books — rare enough that a few
runs look reliable, common enough that a fuzz night finds it. When it
does: the seed is recorded, the failing input is saved, a line-level
microscope trace is written, and the harness prints the --shrink
command that minimizes the ledger to its failing core.

gen(rng) below is the roadmap-#1 protocol: take a seeded
random.Random, return the run's stdin (str/bytes) or its argv (list).
Loading this file as a generator executes nothing — the __main__
guard keeps the two roles apart.
"""
import sys


def gen(rng):
    lines = []
    for _ in range(rng.randint(4, 10)):
        kind = rng.choice(["order", "order", "order", "refund", "audit"])
        if kind == "audit":
            lines.append("audit")
        else:
            lines.append(f"{kind} {rng.randint(1, 60)}")
    return "\n".join(lines) + "\n"


def main():
    total = 0
    for line in sys.stdin:
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "order":
            total += int(parts[1])
        elif parts[0] == "refund":
            total -= int(parts[1])
        elif parts[0] == "audit":
            assert total >= 0, "books negative"
    print(f"final: {total}")


if __name__ == "__main__":
    main()
