def prefix_sums(daily_sales):
    total_so_far = [0] * len(daily_sales)
    running = 0
    for i in range(len(daily_sales)):
        running += daily_sales[i]
        total_so_far[i] = running
    return total_so_far


if __name__ == "__main__":
    print(prefix_sums([3, 1, 4, 1, 5, 9, 2, 6]))
