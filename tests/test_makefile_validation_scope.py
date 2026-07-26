from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("make"), "make is required for Makefile tests")
class MakefileValidationScopeTests(unittest.TestCase):
    def dry_run(self, target: str, **environment: str) -> str:
        result = subprocess.run(
            ["make", "--dry-run", target],
            cwd=ROOT,
            env={**os.environ, **environment},
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout

    def test_global_validation_clears_ambient_scope_and_metadata_skip(self) -> None:
        for target in ("validate", "deep-validate", "check", "deep-check"):
            with self.subTest(target=target):
                environment = {
                    "PAPER_ID": "ambient-paper",
                    "SKIP_METADATA_VALIDATION": "1",
                }
                if target == "deep-check":
                    environment["DEEP_REASON"] = "full-audit"
                output = self.dry_run(
                    target,
                    **environment,
                )
                validation_command = next(
                    line
                    for line in output.splitlines()
                    if "scripts/validate_translations.sh" in line
                )
                self.assertIn("-u PAPER_ID", validation_command)
                self.assertIn("-u SKIP_METADATA_VALIDATION", validation_command)
                self.assertNotIn("PAPER_ID=ambient-paper", validation_command)

    def test_paper_check_keeps_explicit_single_paper_scope(self) -> None:
        output = self.dry_run(
            "paper-check",
            PAPER_ID="sample-paper",
            SKIP_METADATA_VALIDATION="1",
        )
        validation_command = next(
            line
            for line in output.splitlines()
            if "scripts/validate_translations.sh" in line
        )
        self.assertIn("-u PAPER_ID", validation_command)
        self.assertIn("-u SKIP_METADATA_VALIDATION", validation_command)
        self.assertIn('--paper-id "sample-paper"', validation_command)

    def test_validation_script_rejects_ambient_scope_interfaces(self) -> None:
        for variable, value in (
            ("PAPER_ID", "ambient-paper"),
            ("SKIP_METADATA_VALIDATION", "1"),
        ):
            with self.subTest(variable=variable):
                result = subprocess.run(
                    ["bash", "scripts/validate_translations.sh"],
                    cwd=ROOT,
                    env={**os.environ, variable: value},
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    f"{variable} is an internal preflight option",
                    result.stderr,
                )

    def test_metadata_skip_cli_is_not_supported(self) -> None:
        result = subprocess.run(
            [
                "env",
                "-u",
                "PAPER_ID",
                "-u",
                "SKIP_METADATA_VALIDATION",
                "bash",
                "scripts/validate_translations.sh",
                "--paper-id",
                "sample-paper",
                "--skip-metadata-validation",
            ],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown validation option", result.stderr)

    def test_resource_legacy_replay_is_selected_only_by_manifest_review_grade(
        self,
    ) -> None:
        script = (ROOT / "scripts/validate_translations.sh").read_text(
            encoding="utf-8"
        )
        routing = (
            'if [[ "$review_grade" == "true" ]]; then\n'
            "      resource_args+=(--require-inline-citations)\n"
            "    else\n"
            "      resource_args+=(--legacy-accepted-resource-structure)\n"
            "    fi"
        )
        self.assertIn(routing, script)

    def test_source_identity_scan_is_reserved_for_deep_or_scoped_validation(
        self,
    ) -> None:
        script = (ROOT / "scripts/validate_translations.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'if [[ "$deep_validation" == "1" || -n "$target_paper_id" ]]; then\n'
            '  source_args=(--root "$ROOT")',
            script,
        )

    def test_math_check_uses_one_static_parse_before_rendering(self) -> None:
        output = self.dry_run("math-check")
        self.assertIn("scripts/verify_math_rendering.py", output)
        self.assertIn("scripts/fix_portable_math.py check", output)
        self.assertNotIn("scripts/validate_github_math.py", output)

    def test_check_omits_repository_wide_math_rendering(self) -> None:
        output = self.dry_run("check")
        self.assertNotIn("scripts/verify_math_rendering.py", output)
        self.assertNotIn("scripts/fix_portable_math.py check", output)

    def test_scoped_math_check_requires_explicit_translation_files(self) -> None:
        result = subprocess.run(
            ["make", "math-check-files"],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FILES is required", result.stderr)

        translation = (
            "papers/query-processing/"
            "access-path-selection-relational-database-management-system/"
            "translation.md"
        )
        output = self.dry_run("math-check-files", FILES=translation)
        self.assertIn(
            f'scripts/verify_math_rendering.py --mathjax-module '
            f'"node_modules/mathjax" {translation}',
            output,
        )
        self.assertIn(f"scripts/fix_portable_math.py check {translation}", output)

    def test_deep_check_requires_a_controlled_reason(self) -> None:
        environment = os.environ.copy()
        for variable in (
            "DEEP_REASON",
            "MAKEFLAGS",
            "MAKEOVERRIDES",
            "MFLAGS",
        ):
            environment.pop(variable, None)
        result = subprocess.run(
            ["make", "deep-check"],
            cwd=ROOT,
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("deep-check requires DEEP_REASON", result.stderr)

        output = self.dry_run(
            "deep-check",
            DEEP_REASON="validator-semantics",
        )
        self.assertIn("DEEP_VALIDATION=1", output)
        self.assertIn("scripts/verify_math_rendering.py", output)

    def test_translation_validator_reserves_math_profile_for_deep_or_draft_scope(
        self,
    ) -> None:
        script = (ROOT / "scripts/validate_translations.sh").read_text(
            encoding="utf-8"
        )
        marker = (
            'if [[ "$deep_validation" == "1" || -n "$target_paper_id" '
            '|| "$reading_status" == "draft" ]]; then'
        )
        math_call = 'scripts/validate_github_math.py "${github_math_args[@]}"'
        self.assertIn(marker, script)
        self.assertIn(math_call, script)


if __name__ == "__main__":
    unittest.main()
