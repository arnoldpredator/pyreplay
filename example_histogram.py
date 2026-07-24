def tally(dice_rolls):
    counts = [0] * 7   # counts[v] = how many times value v was rolled
    for roll in dice_rolls:
        counts[roll] += 1
    return counts


if __name__ == "__main__":
    rolls = [3, 6, 3, 2, 5, 3, 6, 1, 4, 6, 2, 3]
    print(tally(rolls))
