def make_counter():
    count = 0

    def bump():
        nonlocal count
        count += 1
        return count
    return bump


def squares(n):
    for i in range(n):
        yield i * i


def sticky(item, bucket=[]):     # the classic shared-default trap
    bucket.append(item)
    return bucket


a = [1, 2]
b = a                  # alias: two names, ONE object
b.append(3)            # mutation: a "changes" too — same object
b = [9]                # rebinding: b points elsewhere, a untouched

counter = make_counter()
counter()
counter()

gen = squares(3)
first = next(gen)
second = next(gen)
rest = list(gen)       # drains the rest: resume, yield, resume, end

s1 = sticky("x")
s2 = sticky("y")       # bucket is the SAME list as the first call!
