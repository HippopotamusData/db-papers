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
            "mode": "review-and-repair",
            "branch": "codex/sample-batch",
            "worktree": str(worktree),
            "base_sha": "a" * 40,
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

            value["schema_version"] = 1
            batch_manifest.write_manifest(path, value)
            with self.assertRaisesRegex(
                ValueError,
                "manifest must contain exactly",
            ):
                batch_manifest.read_manifest(path)

    def test_manifest_rejects_yaml_type_lookalikes_with_value_errors(self) -> None:
        invalid_values = (
            {"mode": ["draft-only"]},
            {"base_sha": ["a" * 40]},
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
        self.assertEqual(
            batch_manifest.MODES,
            {"draft-only", "review-and-repair"},
        )
        self.assertIn("blocked", batch_manifest.TRANSITIONS["reviewed"])
        self.assertIn("reviewed", batch_manifest.TRANSITIONS["blocked"])
        self.assertIn("rated", batch_manifest.TRANSITIONS["reviewed"])

    def test_draft_only_manifest_rejects_reviewed_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "batch.yaml"
            value = self.manifest(Path(temporary))
            value["mode"] = "draft-only"
            value["targets"]["sample-paper"] = "reviewed"
            batch_manifest.write_manifest(path, value)
            with self.assertRaisesRegex(ValueError, "draft-only batch"):
                batch_manifest.read_manifest(path)

    def test_manifest_base_must_match_expected_batch_base(self) -> None:
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
                    "manifest base_sha does not match the expected batch base",
                ):
                    batch_manifest.check_manifest(
                        data,
                        root,
                        "codex/sample-batch",
                        expected_base_sha="b" * 40,
                    )


if __name__ == "__main__":
    unittest.main()
