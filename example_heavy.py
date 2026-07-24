"""A stdlib-heavy loop: monitoring switches off out-of-project frames."""
import json, statistics
def summarize(rows):
    blob = json.dumps(rows)
    back = json.loads(blob)
    return statistics.mean(r["v"] for r in back)
total = 0.0
for i in range(4000):
    total += summarize([{"v": j} for j in range(20)])
print(round(total, 2))
