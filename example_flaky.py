"""A set has no order — but code that ACCIDENTALLY depends on its
iteration order works fine... until the run where it doesn't. Python
randomizes string hashing per process, so this script passes or crashes
depending on nothing you wrote:

    python3 tracer.py --runs 20 example_flaky.py

Roughly a third of the runs crash. The report counts both outcomes,
gives each its wall-time distribution, and keeps ONE replayable trace
per outcome — open the failing one and step to the crash; open the
clean one and see the order that happened to work.
"""


def close_batch(tasks):
    done = []
    for t in tasks:              # set iteration: order is a hash accident
        done.append(t)
    return done


def finalize(log):
    # the audit entry must not lead the batch — a rule this code only
    # meets by luck, one hash seed at a time
    if log[0] == "audit":
        raise RuntimeError("audit closed before the batch it audits")
    return len(log)


tasks = {"ship", "bill", "audit"}
print("closed:", finalize(close_batch(tasks)))
