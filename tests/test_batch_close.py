from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import batch_close  # noqa: E402
from ci_validation_scope import ValidationPlan  # noqa: E402


class BatchCloseTests(unittest.TestCase):
    def snapshot(
        self,
        root: Path,
        *,
        mode: str = "review-and-repair",
        states: dict[str, str] | None = None,
        head: str = "b" * 40,
    ) -> batch_close.BatchSnapshot:
        return batch_close.BatchSnapshot(
            root=root,
            branch="codex/sample-batch",
            head=head,
            path=root / "tmp/batches/sample.yaml",
            data={
                "mode": mode,
                "branch": "codex/sample-batch",
                "worktree": str(root),
                "base_sha": "a" * 40,
                "targets": states or {
                    "paper-a": "reviewed",
                    "paper-b": "rated",
                },
            },
        )

    def test_final_states_match_batch_mode(self) -> None:
        for mode, states in (
            ("draft-only", {"paper-a": "draft-ready"}),
            (
                "review-and-repair",
                {"paper-a": "reviewed", "paper-b": "rated"},
            ),
        ):
            with self.subTest(mode=mode):
                batch_close.check_final_states(
                    self.snapshot(
                        Path("/tmp/worktree"),
                        mode=mode,
                        states=states,
                    ).data
                )

        for mode, state in (
            ("draft-only", "reviewed"),
            ("review-and-repair", "draft-ready"),
            ("review-and-repair", "blocked"),
        ):
            with self.subTest(mode=mode, state=state):
                with self.assertRaisesRegex(ValueError, "non-final"):
                    batch_close.check_final_states(
                        self.snapshot(
                            Path("/tmp/worktree"),
                            mode=mode,
                            states={"paper-a": state},
                        ).data
                    )

    def test_fast_gate_uses_same_clean_snapshot_and_terminal_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            before = self.snapshot(Path(temporary))
            commands: list[tuple[str, ...]] = []
            output = io.StringIO()
            with (
                patch.object(
                    batch_close,
                    "capture_snapshot",
                    side_effect=[before, before],
                ) as capture,
                patch.object(
                    batch_close,
                    "changed_paths",
                    return_value=["docs/workflows/batch-translate.md"],
                ),
                patch.object(
                    batch_close,
                    "select_validation_plan",
                    return_value=ValidationPlan(),
                ),
                redirect_stdout(output),
            ):
                batch_close.close_batch(
                    "tmp/batches/sample.yaml",
                    runner=lambda _root, command: commands.append(tuple(command)),
                )

        self.assertEqual(capture.call_count, 2)
        self.assertEqual(
            commands,
            [
                ("make", "--no-print-directory", "check"),
                ("make", "--no-print-directory", "diff-check"),
            ],
        )
        lines = output.getvalue().splitlines()
        self.assertEqual(
            lines[-1],
            "BATCH_CLOSE_RESULT "
            f"status=passed head={before.head} gate=check targets=2",
        )
        self.assertEqual(
            sum(line.startswith("BATCH_CLOSE_RESULT ") for line in lines),
            1,
        )

    def test_deep_plan_selects_controlled_deep_gate(self) -> None:
        before = self.snapshot(Path("/tmp/worktree"))
        commands: list[tuple[str, ...]] = []
        with (
            patch.object(
                batch_close,
                "capture_snapshot",
                side_effect=[before, before],
            ),
            patch.object(batch_close, "changed_paths", return_value=["Makefile"]),
            patch.object(
                batch_close,
                "select_validation_plan",
                return_value=ValidationPlan(deep_validate_all=True),
            ),
            redirect_stdout(io.StringIO()),
        ):
            batch_close.close_batch(
                "tmp/batches/sample.yaml",
                runner=lambda _root, command: commands.append(tuple(command)),
            )
        self.assertEqual(
            commands[0],
            (
                "make",
                "--no-print-directory",
                "deep-check",
                "DEEP_REASON=validator-semantics",
            ),
        )

    def test_gate_failure_stops_without_success_marker(self) -> None:
        before = self.snapshot(Path("/tmp/worktree"))
        calls = 0

        def fail_first(_root: Path, command: tuple[str, ...]) -> None:
            nonlocal calls
            calls += 1
            raise batch_close.GateFailure(command, 7)

        output = io.StringIO()
        with (
            patch.object(
                batch_close,
                "capture_snapshot",
                return_value=before,
            ),
            patch.object(batch_close, "changed_paths", return_value=[]),
            patch.object(
                batch_close,
                "select_validation_plan",
                return_value=ValidationPlan(),
            ),
            redirect_stdout(output),
            self.assertRaises(batch_close.GateFailure),
        ):
            batch_close.close_batch(
                "tmp/batches/sample.yaml",
                runner=fail_first,
            )
        self.assertEqual(calls, 1)
        self.assertNotIn("BATCH_CLOSE_RESULT", output.getvalue())

    def test_diff_gate_failure_also_prevents_success_marker(self) -> None:
        before = self.snapshot(Path("/tmp/worktree"))
        calls = 0

        def fail_second(_root: Path, command: tuple[str, ...]) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise batch_close.GateFailure(command, 9)

        output = io.StringIO()
        with (
            patch.object(
                batch_close,
                "capture_snapshot",
                return_value=before,
            ),
            patch.object(batch_close, "changed_paths", return_value=[]),
            patch.object(
                batch_close,
                "select_validation_plan",
                return_value=ValidationPlan(),
            ),
            redirect_stdout(output),
            self.assertRaises(batch_close.GateFailure),
        ):
            batch_close.close_batch(
                "tmp/batches/sample.yaml",
                runner=fail_second,
            )
        self.assertEqual(calls, 2)
        self.assertNotIn("BATCH_CLOSE_RESULT", output.getvalue())

    def test_run_gate_preserves_actual_child_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with (
                redirect_stdout(io.StringIO()),
                self.assertRaises(batch_close.GateFailure) as failure,
            ):
                batch_close.run_gate(
                    Path(temporary),
                    ("sh", "-c", "exit 7"),
                )
        self.assertEqual(failure.exception.returncode, 7)

    def test_snapshot_change_after_gates_prevents_success_marker(self) -> None:
        before = self.snapshot(Path("/tmp/worktree"))
        after = self.snapshot(Path("/tmp/worktree"), head="c" * 40)
        output = io.StringIO()
        with (
            patch.object(
                batch_close,
                "capture_snapshot",
                side_effect=[before, after],
            ),
            patch.object(batch_close, "changed_paths", return_value=[]),
            patch.object(
                batch_close,
                "select_validation_plan",
                return_value=ValidationPlan(),
            ),
            redirect_stdout(output),
            self.assertRaisesRegex(ValueError, "changed while gates ran"),
        ):
            batch_close.close_batch(
                "tmp/batches/sample.yaml",
                runner=lambda _root, _command: None,
            )
        self.assertNotIn("BATCH_CLOSE_RESULT", output.getvalue())

    def test_main_preserves_child_failure_code(self) -> None:
        with (
            patch.object(
                batch_close,
                "close_batch",
                side_effect=batch_close.GateFailure(("make", "check"), 7),
            ),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            self.assertEqual(
                batch_close.main(
                    ["--manifest", "tmp/batches/sample.yaml"]
                ),
                7,
            )


if __name__ == "__main__":
    unittest.main()
