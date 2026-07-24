def pick(cmd):
    match cmd:
        case "start":
            return 1
        case "stop":
            return 2
        case _:
            return 0


def handle(x):
    try:
        return 10 / x
    except TypeError:
        return "type problem"
    except ZeroDivisionError:
        return "zero problem"


def main():
    total = 0
    for v in [3, 1]:
        total += v

    for v in []:
        total += 99        # never runs: the invisible-loop classic

    for v in [5, 6, 7]:
        if v == 6:
            break          # broken, not exhausted

    a = pick("stop")
    b = handle(0)
    return total, a, b


main()
