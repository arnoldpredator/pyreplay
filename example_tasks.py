"""Two asyncio tasks interleaving over one shared list.

pyreplay treats tasks as PSEUDO-THREADS (#14): every event records the
task that drove it, and the viewer gives each task its own lane and
call stack — stepping through the trace shows the stacks alternating
as the event loop switches between them.

The shared list q is passed INTO both coroutines, so it appears in
each frame's variables: one object, two lanes. A task's frame re-emits
its full live state on every resume, so after sleeping through the
other task's mutations its q is shown current, never stale.
"""
import asyncio


def make_item(i):
    # a plain sync function called FROM a task: its frame joins the
    # task's lane, so the lane shows a real nested call stack
    return i * 10


async def producer(q):
    for i in range(3):
        q.append(make_item(i))
        await asyncio.sleep(0.01)     # suspend: the consumer runs
    return "produced 3"


async def consumer(q):
    got = []
    while len(got) < 3:
        if q:
            got.append(q.pop(0))
        await asyncio.sleep(0.005)    # suspend: the producer runs
    return got


async def main():
    q = []
    prod = asyncio.create_task(producer(q), name="producer")
    cons = asyncio.create_task(consumer(q), name="consumer")
    return await prod, await cons


if __name__ == "__main__":
    print(asyncio.run(main()))
