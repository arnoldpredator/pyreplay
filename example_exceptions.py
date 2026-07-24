def parse_age(text):
    return int(text)


def risky_lookup(d, keys):
    found = []
    for k in keys:
        try:
            found.append(d[k])
        except KeyError:
            found.append(None)
    return found


def squares(n):
    for i in range(n):
        yield i * i


def main():
    data = {"a": 1, "b": 2}
    got = risky_lookup(data, ["a", "zz", "b", "nope"])

    it = squares(2)
    first = next(it)
    second = next(it)
    try:
        third = next(it)          # exhausted: soft StopIteration
    except StopIteration:
        third = None

    age = parse_age("42")
    boom = parse_age("not a number")   # uncaught: crashes the program
    return got, age, boom


main()
