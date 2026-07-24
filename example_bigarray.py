"""Writes far past the display head -> the honest windowing view."""
data = [0] * 2000
for k in (5, 250, 1500, 1900):
    data[k] = k * k                   # data[1500] change -> window ~1490..1510
print(sum(data))
