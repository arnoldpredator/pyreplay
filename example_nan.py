"""One careless gain births an Inf; one subtraction births a NaN; the
final report is garbage — and nothing ever crashed. The classic
scientific-code failure: the poison is born thousands of operations
before anyone notices, and the traceback (if you even get one) points
at the WRONG place.

    python3 tracer.py --trip nan example_nan.py

The banner names the first birth (amplify's return value turning inf);
the amber ☢ marks over the scrubber trace the spread; each poisoned
variable wears the glyph at the exact event it turned.
"""


def amplify(reading, gain):
    return reading * gain            # 1e308 * 10 -> inf: born HERE


def detrend(values):
    mean = sum(values) / len(values)     # one inf poisons the mean
    return [v - mean for v in values]    # inf - inf -> the first NaN


def report(values):
    total = 0.0
    for v in values:
        total += v                   # nan swallows the running sum
    return total / len(values)


readings = [1.5, 2.25, 1e308, 4.0]   # one glitched sensor sample
amplified = [amplify(r, 10.0) for r in readings]
clean = detrend(amplified)
mean = report(clean)
print("mean signal:", mean)          # nan — no exception, just a lie
