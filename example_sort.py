def selection_sort(heights):
    n = len(heights)
    for i in range(n):
        smallest = i
        for j in range(i + 1, n):
            if heights[j] < heights[smallest]:
                smallest = j
        heights[i], heights[smallest] = heights[smallest], heights[i]
    return heights


if __name__ == "__main__":
    print(selection_sort([7, 3, 9, 1, 6, 2, 8, 4]))
