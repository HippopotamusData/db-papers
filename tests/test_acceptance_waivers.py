from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/acceptance_waivers.sh"


class AcceptanceWaiverTests(unittest.TestCase):
    def compare(self, recorded: str, observed: str) -> tuple[int, list[str]]:
        completed = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; compare_acceptance_waivers "$2" "$3"',
                "waiver-test",
                str(HELPER),
                recorded,
                observed,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        return completed.returncode, completed.stdout.splitlines()

    def test_clean_paper_with_waiver_is_rejected(self) -> None:
        self.assertEqual(self.compare("resources", ""), (1, ["unused:resources"]))

    def test_matching_candidate_and_waiver_pass(self) -> None:
        self.assertEqual(self.compare("resources", "resources"), (0, []))

    def test_unrelated_waiver_reports_missing_and_unused(self) -> None:
        self.assertEqual(
            self.compare("listings", "resources"),
            (1, ["missing:resources", "unused:listings"]),
        )

    def test_deterministic_error_cannot_consume_waiver(self) -> None:
        # Deterministic errors are never added to the observed waivable candidates.
        self.assertEqual(self.compare("listings", ""), (1, ["unused:listings"]))


if __name__ == "__main__":
    unittest.main()
