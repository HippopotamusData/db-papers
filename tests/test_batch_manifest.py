from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import batch_manifest  # noqa: E402


class BatchManifestTests(unittest.TestCase):
    def manifest(self, worktree: Path) -> dict:
        return {
            "schema_version": 1,
            "mode": "review-and-repair/accept",
            "branch": "codex/sample-batch",
            "worktree": str(worktree),
            "review_base_sha": "a" * 40,
            "targets": {"sample-paper": "queued"},
        }

    def test_manifest_round_trip_and_strict_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "batch.yaml"
            value = self.manifest(Path(temporary))
            batch_manifest.write_manifest(path, value)
            self.assertEqual(batch_manifest.read_manifest(path), value)

            path.write_text(
                path.read_text(encoding="utf-8")
                + "mode: draft-only\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate key 'mode'"):
                batch_manifest.read_manifest(path)

    def test_manifest_rejects_yaml_type_lookalikes_with_value_errors(self) -> None:
        invalid_values = (
            {"schema_version": True},
            {"mode": ["draft-only"]},
            {"targets": {"sample-paper": ["queued"]}},
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "batch.yaml"
            for update in invalid_values:
                with self.subTest(update=update):
                    value = self.manifest(Path(temporary))
                    value.update(update)
                    batch_manifest.write_manifest(path, value)
                    with self.assertRaises(ValueError):
                        batch_manifest.read_manifest(path)

    def test_rating_blocker_has_a_recoverable_state_path(self) -> None:
        self.assertIn("blocked", batch_manifest.TRANSITIONS["accepted"])
        self.assertIn("accepted", batch_manifest.TRANSITIONS["blocked"])
        self.assertIn("rated", batch_manifest.TRANSITIONS["accepted"])

    def test_draft_only_manifest_rejects_accepted_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "batch.yaml"
            value = self.manifest(Path(temporary))
            value["mode"] = "draft-only"
            value["targets"]["sample-paper"] = "accepted"
            batch_manifest.write_manifest(path, value)
            with self.assertRaisesRegex(ValueError, "draft-only batch"):
                batch_manifest.read_manifest(path)

    def test_manifest_base_must_match_accept_preflight_base(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            data = self.manifest(root)
            with patch.object(
                batch_manifest,
                "full_sha",
                side_effect=lambda value: value,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "does not match the expected batch base",
                ):
                    batch_manifest.check_manifest(
                        data,
                        root,
                        "codex/sample-batch",
                        expected_base_sha="b" * 40,
                    )


if __name__ == "__main__":
    unittest.main()
