"""In-process tracing: bracket a block with `with watch():` — no CLI."""
from tracer import watch

def analyze(nums):
    acc = 0
    with watch():                     # only this block is filmed
        for n in nums:
            acc += n * n
    return acc

print(analyze([3, 1, 4, 1, 5]))
