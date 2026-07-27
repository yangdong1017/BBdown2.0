from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import TypeVar


T = TypeVar("T")
R = TypeVar("R")


def run_limited_tasks(
    items: Iterable[T],
    *,
    max_workers: int,
    submit_one: Callable[[int, T], R],
    should_stop: Callable[[], bool],
    on_error: Callable[[int, T, Exception], R] | None = None,
    start_index: int = 0,
) -> Iterator[R]:
    worker_count = max(1, int(max_workers))
    iterator = enumerate(items, start=start_index)
    running: dict[Future[R], tuple[int, T]] = {}

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        def submit_next() -> bool:
            if should_stop():
                return False
            try:
                index, item = next(iterator)
            except StopIteration:
                return False
            future = pool.submit(submit_one, index, item)
            running[future] = (index, item)
            return True

        for _ in range(worker_count):
            if not submit_next():
                break

        while running:
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                index, item = running.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    if on_error is None:
                        raise
                    result = on_error(index, item, exc)
                yield result
                if not should_stop():
                    submit_next()
