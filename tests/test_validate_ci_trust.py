from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_ci_trust import PROTECTED_PATHS, validate_ci_trust


REPO_ROOT = Path(__file__).resolve().parents[1]
MATH_WORKFLOW = Path(".github/workflows/github-math-audit.yml")


class ValidateCiTrustTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.candidate_root = Path(self.temp_dir.name) / "candidate"
        for relative in PROTECTED_PATHS:
            destination = self.candidate_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / relative, destination)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def assert_violation(self, expected: str) -> None:
        errors = validate_ci_trust(self.candidate_root)
        self.assertTrue(
            any(expected in error for error in errors),
            f"expected {expected!r} in {errors!r}",
        )

    def test_current_trusted_runtime_passes(self) -> None:
        self.assertEqual(validate_ci_trust(self.candidate_root), [])

    def test_rejects_any_protected_file_change(self) -> None:
        for relative in PROTECTED_PATHS:
            with self.subTest(relative=relative):
                path = self.candidate_root / relative
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                self.assert_violation(str(relative))
                path.write_bytes(original)

    def test_rejects_missing_or_symlinked_protected_file(self) -> None:
        relative = Path("scripts/validate_github_math.py")
        path = self.candidate_root / relative
        path.unlink()
        self.assert_violation("missing or not regular")
        path.symlink_to(REPO_ROOT / relative)
        self.assert_violation("symlinks are not allowed")

    def test_unprivileged_workflow_is_outside_this_policy(self) -> None:
        path = self.candidate_root / ".github/workflows/check.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("name: candidate-check\n", encoding="utf-8")
        self.assertEqual(validate_ci_trust(self.candidate_root), [])

    def test_trusted_workflow_keeps_minimum_security_invariants(self) -> None:
        text = (REPO_ROOT / MATH_WORKFLOW).read_text(encoding="utf-8")
        self.assertIn("  pull_request_target:\n", text)
        self.assertIn("permissions:\n  contents: read\n", text)
        self.assertIn("persist-credentials: false", text)
        self.assertNotIn("ref: ${{ github.event.pull_request.head.sha }}", text)
        self.assertIn('AUDIT_UNTRUSTED_DATA: "1"', text)
        self.assertIn(
            '"$GITHUB_WORKSPACE/scripts/audit_changed_math.sh"', text
        )
        actions = re.findall(r"uses: (actions/[^@]+)@([0-9a-f]+)", text)
        self.assertTrue(actions)
        self.assertTrue(all(len(revision) == 40 for _action, revision in actions))

    def test_trusted_runtime_uses_only_inline_pinned_dependencies(self) -> None:
        text = (REPO_ROOT / MATH_WORKFLOW).read_text(encoding="utf-8")
        self.assertNotIn("--group dev", text)
        self.assertNotIn("cache-dependency-path", text)
        self.assertIn("--only-binary=:all:", text)
        self.assertIn("--no-deps", text)
        for requirement in (
            "pip==26.1.2",
            "markdown-it-py==4.2.0",
            "mdurl==0.1.2",
        ):
            self.assertIn(requirement, text)

    def test_trusted_audit_enables_unchecked_data_mode(self) -> None:
        text = (REPO_ROOT / "scripts/audit_changed_math.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("audit_args+=(--unchecked-input)", text)


if __name__ == "__main__":
    unittest.main()
