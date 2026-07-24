"""Two worker threads over a shared counter -> per-thread lanes."""
import threading
shared = {"total": 0}
def worker(n):
    for _ in range(n):
        shared["total"] += 1
t1 = threading.Thread(target=worker, args=(3,), name="worker-A")
t2 = threading.Thread(target=worker, args=(3,), name="worker-B")
t1.start(); t2.start()
t1.join();  t2.join()
print(shared["total"])
