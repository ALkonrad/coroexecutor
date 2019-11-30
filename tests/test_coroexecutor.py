import asyncio
from asyncio import run
import pytest
from coroexecutor import CoroutineExecutor


def test_basic():
    results = []

    async def f(dt):
        await asyncio.sleep(dt)
        results.append(1)

    async def main():
        async with CoroutineExecutor() as exe:
            t1 = exe.submit(f, 0.01)
            t2 = exe.submit(f, 0.05)

        assert t1.done()
        assert t2.done()
        assert not exe.tasks or all(t.done() for t in list(exe.tasks))

    run(main())
    assert results == [1, 1]


@pytest.mark.parametrize('exc_delay,expected_results', [
    (0.01, []),  # Failing task finishes first
    (0.06, [1]),  # Failing task finishes last
])
def test_exception_cancels_all_tasks(exc_delay, expected_results):
    results = []

    async def f(dt, error=False):
        await asyncio.sleep(dt)
        if error:
            raise Exception('oh noes')
        results.append(1)

    async def main():
        async with CoroutineExecutor() as exe:
            t1 = exe.submit(f, exc_delay, error=True)
            t2 = exe.submit(f, 0.05)

        assert t1.done()
        assert t2.done()
        assert not exe.tasks or all(t.done() for t in list(exe.tasks))

    with pytest.raises(Exception, match=r'oh noes'):
        run(main())

    assert results == expected_results


def test_no_new_tasks():
    got_to_here = []

    async def f(dt):
        await asyncio.sleep(dt)

    async def main():
        async with CoroutineExecutor() as exe:
            t1 = exe.submit(f, 0.01)
            t2 = exe.submit(f, 0.05)

        got_to_here.append(1)
        exe.submit(f, 0.02)

    with pytest.raises(RuntimeError):
        run(main())

    assert got_to_here


def test_reraise_unhandled():
    tasks = []

    async def f(dt):
        await asyncio.sleep(dt)

    async def main():
        async with CoroutineExecutor() as exe:
            t1 = exe.submit(f, 0.01)
            t2 = exe.submit(f, 0.05)
            tasks.extend([t1, t2])
            await asyncio.sleep(0.02)
            raise Exception('oh noes')

    with pytest.raises(Exception, match=r'oh noes'):
        run(main())

    t1, t2 = tasks
    assert t1.done() and not t1.cancelled()
    assert t2.done() and t2.cancelled()


def test_reraise_unhandled_nested():
    tasks = []

    async def f(dt):
        await asyncio.sleep(dt)

    async def main():
        async with CoroutineExecutor() as exe1:
            async with CoroutineExecutor() as exe2:
                async with CoroutineExecutor() as exe3:
                    t1 = exe3.submit(f, 0.01)
                    t2 = exe3.submit(f, 0.05)
                    tasks.extend([t1, t2])
                    await asyncio.sleep(0.02)
                    raise Exception('oh noes')

    with pytest.raises(Exception, match=r'oh noes'):
        run(main())

    t1, t2 = tasks
    assert t1.done() and not t1.cancelled()
    assert t2.done() and t2.cancelled()


def test_reraise_unhandled_nested2():
    tasks = []

    async def f(dt):
        await asyncio.sleep(dt)

    async def main():
        async with CoroutineExecutor() as exe1:
            t3 = exe1.submit(f, 0.01)
            t4 = exe1.submit(f, 0.10)
            async with CoroutineExecutor() as exe2:
                t1 = exe2.submit(f, 0.01)
                t2 = exe2.submit(f, 0.10)
                tasks.extend([t1, t2, t3, t4])
                await asyncio.sleep(0.05)
                raise Exception('oh noes')

    with pytest.raises(Exception, match=r'oh noes'):
        run(main())

    t1, t2, t3, t4 = tasks
    assert t1.done() and not t1.cancelled()
    assert t2.done() and t2.cancelled()

    assert t3.done() and not t3.cancelled()
    assert t4.done() and t4.cancelled()


def test_cancel_outer_task():
    tasks = []

    async def f(dt):
        await asyncio.sleep(dt)

    async def outer():
        async with CoroutineExecutor() as exe:
            t1 = exe.submit(f, 0.01)
            t2 = exe.submit(f, 0.05)
            tasks.extend([t1, t2])

    async def main():
        t = asyncio.create_task(outer())
        await asyncio.sleep(0.02)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    run(main())

    t1, t2 = tasks
    assert t1.done() and not t1.cancelled()
    assert t2.done() and t2.cancelled()


def test_cancel_inner_task():
    tasks = []

    async def f(dt):
        await asyncio.sleep(dt)

    async def outer():
        async with CoroutineExecutor() as exe:
            t1 = exe.submit(f, 0.05)
            t2 = exe.submit(f, 0.05)
            tasks.extend([t1, t2])

    async def main():
        t = asyncio.create_task(outer())
        await asyncio.sleep(0.02)
        t1, t2 = tasks
        t1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    run(main())

    t1, t2 = tasks
    assert t1.done() and t1.cancelled()
    assert t2.done() and t2.cancelled()


def test_timeout():
    tasks = []

    async def f(dt):
        await asyncio.sleep(dt)

    async def main():
        async with CoroutineExecutor(timeout=0.05) as exe:
            t1 = exe.submit(f, 0.01)
            t2 = exe.submit(f, 5)
            tasks.extend([t1, t2])

    with pytest.raises(asyncio.TimeoutError):
        run(main())

    t1, t2 = tasks
    assert t1.done() and not t1.cancelled()
    assert t2.done() and t2.cancelled()


def test_map():
    times = [0.01, 0.02, 0.03]

    async def f(dt):
        await asyncio.sleep(dt)
        return dt

    async def main():
        async with CoroutineExecutor() as exe:
            results = exe.map(f, times)
            assert [v async for v in results] == times

    run(main())


def test_map_error():
    times = [0.01, 0.02, 0.1, 0.2]
    results = []

    async def f(dt):
        await asyncio.sleep(dt)
        if dt == 0.1:
            raise Exception('oh noes')
        return dt

    async def main():
        async with CoroutineExecutor() as exe:
            async for r in exe.map(f, times):
                results.append(r)

    with pytest.raises(Exception):
        run(main())

    assert results == times[:2]


def test_map_timeout():
    times = [0.01, 0.02, 0.1, 0.2]
    results = []

    async def f(dt):
        await asyncio.sleep(dt)
        return dt

    async def main():
        async with CoroutineExecutor() as exe:
            async for r in exe.map(f, times, timeout=0.05):
                results.append(r)

    with pytest.raises(asyncio.TimeoutError):
        run(main())

    assert results == times[:2]


def test_map_outer_timeout():
    times = [0.01, 0.02, 0.1, 0.2]
    results = []

    async def f(dt):
        await asyncio.sleep(dt)
        return dt

    async def main():
        async with CoroutineExecutor(timeout=0.05) as exe:
            async for r in exe.map(f, times):
                results.append(r)

    with pytest.raises(asyncio.TimeoutError):
        run(main())

    assert results == times[:2]

