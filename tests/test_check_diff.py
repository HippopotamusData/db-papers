from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_DIFF = REPO_ROOT / "scripts/check_diff.sh"


class DiffCheckTests(unittest.TestCase):
    def make_repo(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True
        )
        (root / "tracked.txt").write_text("clean\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-q", "-m", "initial"], check=True
        )
        return root

    def run_check(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(CHECK_DIFF)],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_untracked_file_whitespace_is_checked(self) -> None:
        root = self.make_repo()
        untracked = root / "translation.md"
        untracked.write_text("clean\n", encoding="utf-8")
        self.assertEqual(self.run_check(root).returncode, 0)

        untracked.write_text("bad  \n", encoding="utf-8")
        result = self.run_check(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("trailing whitespace", result.stderr)


if __name__ == "__main__":
    unittest.main()
