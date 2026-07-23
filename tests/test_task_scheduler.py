from __future__ import annotations

import unittest

from core.task_scheduler import run_limited_tasks


class TaskSchedulerTests(unittest.TestCase):
    def test_one_task_error_does_not_stop_remaining_tasks(self) -> None:
        def run_one(index: int, value: int) -> str:
            if value == 2:
                raise RuntimeError("broken")
            return f"ok:{value}"

        def handle_error(index: int, value: int, exc: Exception) -> str:
            return f"fail:{value}:{exc}"

        results = list(
            run_limited_tasks(
                [1, 2, 3],
                max_workers=2,
                submit_one=run_one,
                should_stop=lambda: False,
                on_error=handle_error,
            )
        )

        self.assertCountEqual(results, ["ok:1", "fail:2:broken", "ok:3"])

    def test_error_is_raised_without_handler(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "broken"):
            list(
                run_limited_tasks(
                    [1],
                    max_workers=1,
                    submit_one=lambda index, value: (_ for _ in ()).throw(RuntimeError("broken")),
                    should_stop=lambda: False,
                )
            )


if __name__ == "__main__":
    unittest.main()
