def build_roads():
    """String-keyed adjacency dict, undirected (both directions added)."""
    roads = {}
    for city in ["A", "B", "C", "D", "E"]:
        roads[city] = []
    for a, b in [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"), ("D", "E")]:
        roads[a].append(b)
        roads[b].append(a)
    return roads


def bfs(adj, start):
    """Index-based adjacency list + a plain-list queue (stdlib only)."""
    dist = [-1] * len(adj)
    dist[start] = 0
    queue = [start]
    head = 0
    while head < len(queue):
        u = queue[head]
        head += 1
        for v in adj[u]:
            if dist[v] == -1:
                dist[v] = dist[u] + 1
                queue.append(v)
    return dist


def cheapest_hops(prices):
    """Weighted adjacency as dict-of-dicts."""
    best = dict(prices["hub"])
    for stop, cost in prices["hub"].items():
        for dest, extra in prices.get(stop, {}).items():
            total = cost + extra
            if dest not in best or total < best[dest]:
                best[dest] = total
    return best


if __name__ == "__main__":
    roads = build_roads()

    edges = [[0, 1], [0, 2], [1, 3], [2, 3], [3, 4], [4, 5]]
    adj = [[] for _ in range(6)]
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)
    print(bfs(adj, 0))

    prices = {"hub": {"x": 5, "y": 2}, "x": {"z": 1}, "y": {"z": 9}}
    print(cheapest_hops(prices))
