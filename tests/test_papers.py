from __future__ import annotations

import contextlib
import fcntl
import hashlib
import io
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import papers  # noqa: E402
from acceptance_evidence import build_waiver_records  # noqa: E402


REVIEWER = "reviewer@example.com"
REVIEW_BASE_SHA = "a" * 40


def resource_waivers() -> dict[str, dict[str, object]]:
    return build_waiver_records(
        {"resources": ["source Figure 1 has no formal payload candidate"]}
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PapersTests(unittest.TestCase):
    def make_root(self, status: str = "source_only") -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "config").mkdir()
        (root / "papers/query-processing/sample-paper").mkdir(parents=True)
        (root / "config/policy.yaml").write_text(
            "schema_version: 1\ndefault_max_source_pages: 60\npapers: {}\n",
            encoding="utf-8",
        )
        (root / "config/taxonomy.yaml").write_text(
            "schema_version: 1\nareas:\n  query-processing:\n    label_zh: 查询处理\n    description: 测试。\ntopics:\n  query-execution:\n    label_zh: 查询执行\n    description: 测试。\n  cloud-native:\n    label_zh: 云原生\n    description: 测试。\n",
            encoding="utf-8",
        )
        paper = root / "papers/query-processing/sample-paper"
        metadata = {
            "title": "Sample Paper",
            "authors": [],
            "year": None,
            "source_url": "https://example.com/paper",
            "topics": ["query-execution"],
            "reading_status": status,
        }
        (paper / "paper.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        (paper / "source.pdf").write_bytes(b"source evidence")
        entries = {}
        if status in {"draft", "translated"}:
            translation = (
                "---\npaper_id: sample-paper\ntitle: Sample Paper\nlanguage: zh-CN\nsource: source.pdf\n---\n\n"
                "# Sample Paper（中文译文）\n"
            )
            (paper / "translation.md").write_text(translation, encoding="utf-8")
            (paper / "assets").mkdir()
            (paper / "assets/figure.png").write_bytes(b"accepted image")
        if status == "translated":
            entries["sample-paper"] = {
                "source_sha256": sha256(paper / "source.pdf"),
                "translation_sha256": sha256(paper / "translation.md"),
                "assets_manifest_sha256": papers.assets_manifest_sha256(paper, root),
                "review_action": "section-review",
                "reviewer": REVIEWER,
                "review_base_sha": REVIEW_BASE_SHA,
                "waivers": resource_waivers(),
            }
        (root / "config/acceptance.yaml").write_text(
            yaml.safe_dump({"schema_version": 3, "entries": entries}, sort_keys=False), encoding="utf-8"
        )
        return root

    def globals_patch(self, root: Path):
        return patch.multiple(
            papers,
            ROOT=root,
            PAPERS=root / "papers",
            CATALOG=root / "CATALOG.md",
            validate_review_base_commit=lambda _root, _sha: None,
            current_git_head=lambda _root: "b" * 40,
        )

    def test_acceptance_hash_change_invalidates_translated(self) -> None:
        root = self.make_root("translated")
        with self.globals_patch(root):
            self.assertEqual(papers.validate(), 0)
            translation = root / "papers/query-processing/sample-paper/translation.md"
            translation.write_text(translation.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(papers.validate(), 1)
            self.assertIn("changed after acceptance", stderr.getvalue())

    def test_source_hash_change_invalidates_translated(self) -> None:
        root = self.make_root("translated")
        with self.globals_patch(root):
            source = root / "papers/query-processing/sample-paper/source.pdf"
            source.write_bytes(source.read_bytes() + b"changed")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(papers.validate(), 1)
            self.assertIn("source.pdf changed after acceptance", stderr.getvalue())

    def test_same_path_asset_change_invalidates_translated(self) -> None:
        root = self.make_root("translated")
        with self.globals_patch(root):
            asset = root / "papers/query-processing/sample-paper/assets/figure.png"
            asset.write_bytes(b"replacement image")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(papers.validate(), 1)
            self.assertIn("assets changed after acceptance", stderr.getvalue())

    def test_translated_paper_without_ledger_entry_is_rejected(self) -> None:
        root = self.make_root("translated")
        ledger_path = root / "config/acceptance.yaml"
        ledger_path.write_text("schema_version: 3\nentries: {}\n", encoding="utf-8")
        with self.globals_patch(root), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(papers.validate(), 1)

    def test_scoped_validation_ignores_unrelated_in_progress_translation(self) -> None:
        root = self.make_root("source_only")
        other = root / "papers/query-processing/other-paper"
        other.mkdir()
        (other / "paper.yaml").write_text(
            yaml.safe_dump(
                {
                    "title": "Other Paper",
                    "authors": [],
                    "year": None,
                    "source_url": "https://example.com/other",
                    "topics": ["query-execution"],
                    "reading_status": "draft",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (other / "source.pdf").write_bytes(b"source evidence")
        (other / "translation.md").write_text("in-progress", encoding="utf-8")
        with self.globals_patch(root):
            self.assertEqual(papers.validate("sample-paper"), 0)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(papers.validate(), 1)

    def test_scoped_validation_requires_exact_paper_id(self) -> None:
        root = self.make_root("source_only")
        with self.globals_patch(root), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(papers.validate("missing-paper"), 1)

    def test_accept_command_records_hashes_and_transitions_draft(self) -> None:
        root = self.make_root("draft")
        with self.globals_patch(root), patch.object(
            papers, "acceptance_preflight", return_value=(True, "", resource_waivers())
        ):
            result = papers.accept_record(
                "sample-paper",
                "section-review",
                [f"resources={resource_waivers()['resources']['fingerprint']}"],
                REVIEWER,
                REVIEW_BASE_SHA,
            )
        self.assertEqual(result, 0)
        metadata = yaml.safe_load(
            (root / "papers/query-processing/sample-paper/paper.yaml").read_text(encoding="utf-8")
        )
        ledger = yaml.safe_load((root / "config/acceptance.yaml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["reading_status"], "translated")
        self.assertEqual(
            ledger["entries"]["sample-paper"]["translation_sha256"],
            sha256(root / "papers/query-processing/sample-paper/translation.md"),
        )
        self.assertEqual(ledger["entries"]["sample-paper"]["reviewer"], REVIEWER)
        self.assertEqual(
            ledger["entries"]["sample-paper"]["assets_manifest_sha256"],
            papers.assets_manifest_sha256(
                root / "papers/query-processing/sample-paper", root
            ),
        )
        self.assertEqual(
            ledger["entries"]["sample-paper"]["waivers"], resource_waivers()
        )

    def test_accept_rejects_legacy_migration_as_runtime_action(self) -> None:
        root = self.make_root("draft")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        ledger_path = root / "config/acceptance.yaml"
        original_metadata = metadata_path.read_text(encoding="utf-8")
        original_ledger = ledger_path.read_text(encoding="utf-8")
        stderr = io.StringIO()
        with self.globals_patch(root), contextlib.redirect_stderr(stderr):
            result = papers.accept_record(
                "sample-paper", "legacy-migration", [], REVIEWER, REVIEW_BASE_SHA
            )
        self.assertEqual(result, 1)
        self.assertIn("runtime review action", stderr.getvalue())
        self.assertEqual(metadata_path.read_text(encoding="utf-8"), original_metadata)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)

    def test_accept_rejects_reserved_migration_reviewer(self) -> None:
        root = self.make_root("draft")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        ledger_path = root / "config/acceptance.yaml"
        original_metadata = metadata_path.read_text(encoding="utf-8")
        original_ledger = ledger_path.read_text(encoding="utf-8")
        stderr = io.StringIO()
        with self.globals_patch(root), contextlib.redirect_stderr(stderr):
            result = papers.accept_record(
                "sample-paper",
                "section-review",
                [],
                "pending-v3-re-review",
                REVIEW_BASE_SHA,
            )
        self.assertEqual(result, 1)
        self.assertIn("migration reviewer markers", stderr.getvalue())
        self.assertEqual(metadata_path.read_text(encoding="utf-8"), original_metadata)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)

    def test_review_base_must_exist_and_be_an_ancestor(self) -> None:
        current = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        papers.validate_review_base_commit(REPO_ROOT, current)
        with self.assertRaisesRegex(ValueError, "not an available Git commit"):
            papers.validate_review_base_commit(REPO_ROOT, "0" * 40)

    def test_validation_rechecks_recorded_review_base(self) -> None:
        root = self.make_root("translated")
        stderr = io.StringIO()
        with self.globals_patch(root), patch.object(
            papers,
            "validate_review_base_commit",
            side_effect=ValueError("not an ancestor"),
        ), contextlib.redirect_stderr(stderr):
            self.assertEqual(papers.validate(), 1)
        self.assertIn("invalid review_base_sha", stderr.getvalue())

    def test_acceptance_preflight_failure_rolls_back_ledger_and_status(self) -> None:
        root = self.make_root("draft")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        ledger_path = root / "config/acceptance.yaml"
        original_metadata = metadata_path.read_text(encoding="utf-8")
        original_ledger = ledger_path.read_text(encoding="utf-8")
        with self.globals_patch(root), patch.object(
            papers,
            "acceptance_preflight",
            return_value=(False, "ERROR: missing standard translator note", {}),
        ), contextlib.redirect_stderr(io.StringIO()):
            result = papers.accept_record(
                "sample-paper", "section-review", [], REVIEWER, REVIEW_BASE_SHA
            )
        self.assertEqual(result, 1)
        self.assertEqual(metadata_path.read_text(encoding="utf-8"), original_metadata)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)

    def test_preflight_runs_before_any_authoritative_write(self) -> None:
        root = self.make_root("draft")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        ledger_path = root / "config/acceptance.yaml"
        original_metadata = metadata_path.read_text(encoding="utf-8")
        original_ledger = ledger_path.read_text(encoding="utf-8")

        def verify_draft(_paper_id, _waivers):
            self.assertEqual(metadata_path.read_text(encoding="utf-8"), original_metadata)
            self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)
            return True, "", {}

        with self.globals_patch(root), patch.object(
            papers, "acceptance_preflight", side_effect=verify_draft
        ):
            self.assertEqual(
                papers.accept_record(
                    "sample-paper", "section-review", [], REVIEWER, REVIEW_BASE_SHA
                ),
                0,
            )

    def test_acceptance_preflight_forces_deep_validation(self) -> None:
        root = self.make_root("draft")
        environments: list[dict[str, str]] = []
        commands: list[list[str]] = []

        def succeed(command, **kwargs):
            commands.append(command)
            environments.append(kwargs["env"])
            return subprocess.CompletedProcess(command, 0, "", "")

        inherited = {
            "ACCEPTANCE_DISCOVERY": "poisoned",
            "ACCEPTANCE_EVIDENCE_FILE": "/poisoned",
            "ACCEPTANCE_RECORDED_WAIVERS": "poisoned",
            "ACCEPTANCE_TARGET_STATUS": "translated",
            "MATHJAX_MODULE": "/locked/mathjax",
        }
        with self.globals_patch(root), patch.dict(
            papers.os.environ, inherited
        ), patch.object(papers.subprocess, "run", side_effect=succeed):
            passed, output, records = papers.acceptance_preflight("sample-paper", {})
        self.assertTrue(passed)
        self.assertEqual(output, "")
        self.assertEqual(records, {})
        self.assertEqual(len(environments), 6)
        self.assertTrue(all(environment["DEEP_VALIDATION"] == "1" for environment in environments))
        self.assertEqual(
            sum("scripts/validate_translations.sh" in command for command in commands), 2
        )
        self.assertIn(
            [
                sys.executable,
                "scripts/normalize_translation_headers.py",
                "--check",
                "--paper-id",
                "sample-paper",
            ],
            commands,
        )
        self.assertTrue(
            any("scripts/verify_math_rendering.py" in command for command in commands)
        )
        internal_keys = {
            "ACCEPTANCE_DISCOVERY",
            "ACCEPTANCE_EVIDENCE_FILE",
            "ACCEPTANCE_PAPER_ID",
            "ACCEPTANCE_RECORDED_WAIVERS",
            "ACCEPTANCE_TARGET_STATUS",
        }
        self.assertTrue(
            all(not internal_keys.intersection(environment) for environment in environments)
        )
        discovery_command = next(
            command for command in commands if "--acceptance-discovery" in command
        )
        translated_command = next(
            command for command in commands if "--acceptance-target-status" in command
        )
        recorded_index = translated_command.index("--acceptance-recorded-waivers") + 1
        self.assertTrue(translated_command[recorded_index])
        self.assertNotIn("--acceptance-target-status", discovery_command)
        self.assertNotIn("--acceptance-discovery", translated_command)
        mathjax_command = next(
            command
            for command in commands
            if "--mathjax-module" in command
        )
        self.assertEqual(
            mathjax_command[-4:],
            [
                "scripts/verify_math_rendering.py",
                "--mathjax-module",
                "/locked/mathjax",
                "papers/query-processing/sample-paper/translation.md",
            ],
        )
        github_command = next(command for command in commands if "--github" in command)
        self.assertEqual(
            github_command[-3:],
            [
                "scripts/verify_math_rendering.py",
                "--github",
                "papers/query-processing/sample-paper/translation.md",
            ],
        )
        self.assertEqual(commands[-2:], [mathjax_command, github_command])

    def test_github_node_audit_failure_prevents_authoritative_write(self) -> None:
        root = self.make_root("draft")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        ledger_path = root / "config/acceptance.yaml"
        original_metadata = metadata_path.read_text(encoding="utf-8")
        original_ledger = ledger_path.read_text(encoding="utf-8")

        def fail_github(command, **_kwargs):
            if command[0] == "git":
                return subprocess.CompletedProcess(command, 1, b"", b"")
            return subprocess.CompletedProcess(
                command,
                1 if "--github" in command else 0,
                "GitHub did not create a math renderer" if "--github" in command else "",
                "",
            )

        with self.globals_patch(root), patch.object(
            papers.subprocess, "run", side_effect=fail_github
        ), contextlib.redirect_stderr(io.StringIO()):
            result = papers.accept_record(
                "sample-paper", "section-review", [], REVIEWER, REVIEW_BASE_SHA
            )
        self.assertEqual(result, 1)
        self.assertEqual(metadata_path.read_text(encoding="utf-8"), original_metadata)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)

    def test_acceptance_preflight_rejects_candidate_change_between_passes(self) -> None:
        root = self.make_root("draft")

        def change_candidate(command, **kwargs):
            if "scripts/validate_translations.sh" in command:
                evidence = Path(
                    command[command.index("--acceptance-evidence-file") + 1]
                )
                candidate = (
                    "source Figure 1 has no formal payload candidate"
                    if "--acceptance-discovery" in command
                    else "source Figure 2 has no formal payload candidate"
                )
                evidence.write_text(f"resources\t{candidate}\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")

        with self.globals_patch(root), patch.object(
            papers.subprocess, "run", side_effect=change_candidate
        ):
            passed, output, _records = papers.acceptance_preflight(
                "sample-paper",
                {"resources": resource_waivers()["resources"]["fingerprint"]},
            )
        self.assertFalse(passed)
        self.assertIn("waiver evidence changed:resources:", output)

    def test_acceptance_preflight_rejects_unreviewed_candidate_in_same_category(self) -> None:
        root = self.make_root("draft")
        reviewed = resource_waivers()["resources"]

        def add_same_category_candidate(command, **_kwargs):
            if "--acceptance-discovery" in command:
                evidence = Path(
                    command[command.index("--acceptance-evidence-file") + 1]
                )
                evidence.write_text(
                    "resources\tsource Figure 1 has no formal payload candidate\n"
                    "resources\tsource Figure 2 has no formal payload candidate\n",
                    encoding="utf-8",
                )
            return subprocess.CompletedProcess(command, 0, "", "")

        with self.globals_patch(root), patch.object(
            papers.subprocess, "run", side_effect=add_same_category_candidate
        ):
            passed, output, _records = papers.acceptance_preflight(
                "sample-paper", {"resources": reviewed["fingerprint"]}
            )
        self.assertFalse(passed)
        self.assertIn("approved waiver fingerprint changed: resources:", output)

    def test_accept_rejects_direct_refresh_of_translated_paper(self) -> None:
        root = self.make_root("translated")
        ledger_path = root / "config/acceptance.yaml"
        original_ledger = ledger_path.read_text(encoding="utf-8")
        with self.globals_patch(root), contextlib.redirect_stderr(io.StringIO()):
            result = papers.accept_record(
                "sample-paper", "section-review", [], REVIEWER, REVIEW_BASE_SHA
            )
        self.assertEqual(result, 1)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)

    def test_acceptance_write_failure_rolls_back_first_file(self) -> None:
        root = self.make_root("draft")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        ledger_path = root / "config/acceptance.yaml"
        original_metadata = metadata_path.read_text(encoding="utf-8")
        original_ledger = ledger_path.read_text(encoding="utf-8")
        real_atomic_write = papers.atomic_write_text
        failed = False

        def fail_metadata_once(path: Path, content: str) -> None:
            nonlocal failed
            if path == metadata_path and not failed:
                failed = True
                raise OSError("simulated metadata write failure")
            real_atomic_write(path, content)

        with self.globals_patch(root), patch.object(
            papers, "acceptance_preflight", return_value=(True, "", {})
        ), patch.object(
            papers, "atomic_write_text", side_effect=fail_metadata_once
        ), contextlib.redirect_stderr(io.StringIO()):
            result = papers.accept_record(
                "sample-paper", "section-review", [], REVIEWER, REVIEW_BASE_SHA
            )
        self.assertEqual(result, 1)
        self.assertEqual(metadata_path.read_text(encoding="utf-8"), original_metadata)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)

    def test_compare_and_swap_rejects_preflight_time_metadata_change(self) -> None:
        root = self.make_root("draft")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        ledger_path = root / "config/acceptance.yaml"
        original_ledger = ledger_path.read_text(encoding="utf-8")

        def mutate_during_preflight(_paper_id, _waivers):
            data = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
            data["authors"] = ["Concurrent Editor"]
            metadata_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            return True, "", {}

        with self.globals_patch(root), patch.object(
            papers, "acceptance_preflight", side_effect=mutate_during_preflight
        ), contextlib.redirect_stderr(io.StringIO()):
            result = papers.accept_record(
                "sample-paper", "section-review", [], REVIEWER, REVIEW_BASE_SHA
            )
        self.assertEqual(result, 1)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)
        self.assertIn("Concurrent Editor", metadata_path.read_text(encoding="utf-8"))

    def test_compare_and_swap_rejects_preflight_time_head_change(self) -> None:
        root = self.make_root("draft")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        ledger_path = root / "config/acceptance.yaml"
        original_metadata = metadata_path.read_text(encoding="utf-8")
        original_ledger = ledger_path.read_text(encoding="utf-8")
        heads = iter(["b" * 40, "c" * 40])

        with self.globals_patch(root), patch.object(
            papers, "current_git_head", side_effect=lambda _root: next(heads)
        ), patch.object(
            papers, "acceptance_preflight", return_value=(True, "", {})
        ), contextlib.redirect_stderr(io.StringIO()):
            result = papers.accept_record(
                "sample-paper", "section-review", [], REVIEWER, REVIEW_BASE_SHA
            )
        self.assertEqual(result, 1)
        self.assertEqual(metadata_path.read_text(encoding="utf-8"), original_metadata)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)

    def test_cross_process_flock_wraps_acceptance(self) -> None:
        root = self.make_root("draft")
        lock_modes: list[int] = []

        def record_lock(_descriptor, mode):
            lock_modes.append(mode)

        with self.globals_patch(root), patch.object(
            papers, "acceptance_preflight", return_value=(False, "stop", {})
        ), patch.object(papers.fcntl, "flock", side_effect=record_lock), contextlib.redirect_stderr(
            io.StringIO()
        ):
            self.assertEqual(
                papers.accept_record(
                    "sample-paper", "section-review", [], REVIEWER, REVIEW_BASE_SHA
                ),
                1,
            )
        self.assertEqual(lock_modes, [fcntl.LOCK_EX, fcntl.LOCK_UN])

    def test_keyboard_interrupt_after_first_write_rolls_back(self) -> None:
        root = self.make_root("draft")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        ledger_path = root / "config/acceptance.yaml"
        original_metadata = metadata_path.read_text(encoding="utf-8")
        original_ledger = ledger_path.read_text(encoding="utf-8")
        real_atomic_write = papers.atomic_write_text

        def interrupt_metadata(path: Path, content: str) -> None:
            if path == metadata_path:
                raise KeyboardInterrupt()
            real_atomic_write(path, content)

        with self.globals_patch(root), patch.object(
            papers, "acceptance_preflight", return_value=(True, "", {})
        ), patch.object(
            papers, "atomic_write_text", side_effect=interrupt_metadata
        ), contextlib.redirect_stderr(io.StringIO()):
            result = papers.accept_record(
                "sample-paper", "section-review", [], REVIEWER, REVIEW_BASE_SHA
            )
        self.assertEqual(result, 1)
        self.assertEqual(metadata_path.read_text(encoding="utf-8"), original_metadata)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)

    def test_sigterm_after_first_write_rolls_back(self) -> None:
        root = self.make_root("draft")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        ledger_path = root / "config/acceptance.yaml"
        original_metadata = metadata_path.read_text(encoding="utf-8")
        original_ledger = ledger_path.read_text(encoding="utf-8")
        real_atomic_write = papers.atomic_write_text

        def terminate_metadata(path: Path, content: str) -> None:
            if path == metadata_path:
                papers.signal.raise_signal(papers.signal.SIGTERM)
            real_atomic_write(path, content)

        with self.globals_patch(root), patch.object(
            papers, "acceptance_preflight", return_value=(True, "", {})
        ), patch.object(
            papers, "atomic_write_text", side_effect=terminate_metadata
        ), contextlib.redirect_stderr(io.StringIO()):
            result = papers.accept_record(
                "sample-paper", "section-review", [], REVIEWER, REVIEW_BASE_SHA
            )
        self.assertEqual(result, 1)
        self.assertEqual(metadata_path.read_text(encoding="utf-8"), original_metadata)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)

    def test_sigterm_handler_raises_transaction_exception_and_restores(self) -> None:
        previous = papers.signal.getsignal(papers.signal.SIGTERM)
        with papers.sigterm_as_exception():
            handler = papers.signal.getsignal(papers.signal.SIGTERM)
            with self.assertRaisesRegex(papers.AcceptanceInterrupted, "SIGTERM"):
                handler(papers.signal.SIGTERM, None)
        self.assertIs(papers.signal.getsignal(papers.signal.SIGTERM), previous)

    def test_catalog_omits_topic_index_and_contains_authoritative_link(self) -> None:
        root = self.make_root("source_only")
        with self.globals_patch(root):
            catalog = papers.build_catalog()
        self.assertNotIn("## 按主题浏览", catalog)
        self.assertIn("| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |", catalog)
        self.assertNotIn("| 论文 | 作者 |", catalog)
        self.assertIn("| — | source_only |", catalog)
        self.assertIn("[原文](https://example.com/paper)", catalog)
        self.assertIn("papers/query-processing/sample-paper/source.pdf", catalog)

    def test_catalog_uses_taxonomy_order_for_unordered_topics(self) -> None:
        root = self.make_root("source_only")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["topics"] = ["cloud-native", "query-execution"]
        metadata_path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        with self.globals_patch(root):
            catalog = papers.build_catalog()
        self.assertIn("查询执行、云原生", catalog)

    def test_valid_rating_is_accepted_and_catalog_shows_only_score(self) -> None:
        root = self.make_root("source_only")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["rating"] = {
            "score": 4.5,
            "influence_breadth": 4,
            "technical_value": 5,
            "practical_diffusion": 4,
            "durability": 5,
            "reader_payoff": 4,
        }
        metadata_path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        with self.globals_patch(root):
            self.assertEqual(papers.validate(), 0)
            catalog = papers.build_catalog()
        self.assertIn("| 4.5 | source_only |", catalog)
        self.assertNotIn("influence_breadth", catalog)
        self.assertNotIn("technical_value", catalog)

    def test_rating_score_must_match_weighted_dimensions(self) -> None:
        root = self.make_root("source_only")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["rating"] = {
            "score": 5.0,
            "influence_breadth": 4,
            "technical_value": 5,
            "practical_diffusion": 4,
            "durability": 5,
            "reader_payoff": 4,
        }
        metadata_path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        stderr = io.StringIO()
        with self.globals_patch(root), contextlib.redirect_stderr(stderr):
            self.assertEqual(papers.validate(), 1)
        self.assertIn("rating.score must equal the weighted score 4.5", stderr.getvalue())

    def test_five_point_rating_requires_landmark_gate(self) -> None:
        rating = {
            "score": 5.0,
            "influence_breadth": 4,
            "technical_value": 5,
            "practical_diffusion": 5,
            "durability": 5,
            "reader_payoff": 5,
        }
        self.assertEqual(papers.calculated_rating_score(rating), Decimal("4.5"))

    def test_catalog_links_accepted_paper_directly_to_translation(self) -> None:
        root = self.make_root("translated")
        with self.globals_patch(root):
            catalog = papers.build_catalog()
        self.assertIn("papers/query-processing/sample-paper/translation.md", catalog)

    def test_non_http_source_url_is_rejected(self) -> None:
        root = self.make_root("source_only")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["source_url"] = "ftp://example.com/paper.pdf"
        metadata_path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        with self.globals_patch(root), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(papers.validate(), 1)

    def test_skipped_status_requires_project_reason(self) -> None:
        root = self.make_root("source_only")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["reading_status"] = "skipped"
        metadata_path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        with self.globals_patch(root), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(papers.validate(), 1)

    def test_config_command_exposes_named_page_limit_exception(self) -> None:
        root = self.make_root("source_only")
        policy_path = root / "config/policy.yaml"
        policy_path.write_text(
            "schema_version: 1\ndefault_max_source_pages: 60\npapers:\n"
            "  sample-paper:\n"
            "    max_source_pages: 80\n"
            "    authorization: explicit test override\n",
            encoding="utf-8",
        )
        stdout = io.StringIO()
        with self.globals_patch(root), contextlib.redirect_stdout(stdout):
            self.assertEqual(papers.config_value("paper_page_limit", "sample-paper"), 0)
        self.assertEqual(stdout.getvalue().strip(), "80")

    def test_validation_manifest_batches_policy_and_acceptance_waivers(self) -> None:
        root = self.make_root("translated")
        stdout = io.StringIO()
        poisoned = {
            "ACCEPTANCE_PAPER_ID": "sample-paper",
            "ACCEPTANCE_TARGET_STATUS": "translated",
            "ACCEPTANCE_RECORDED_WAIVERS": papers.encode_waiver_records({}),
        }
        with self.globals_patch(root), patch.dict(
            papers.os.environ, poisoned
        ), contextlib.redirect_stdout(stdout):
            self.assertEqual(papers.validation_manifest("sample-paper"), 0)
        rows = [
            line.split(papers.VALIDATION_FIELD_SEPARATOR)
            for line in stdout.getvalue().splitlines()
        ]
        self.assertEqual(rows[0], ["config", "source.pdf", "translation.md", "true", "false"])
        self.assertEqual(
            rows[1][0:4],
            ["paper", "papers/query-processing/sample-paper", "translated", "60"],
        )
        self.assertEqual(papers.decode_waiver_records(rows[1][4]), resource_waivers())
        self.assertEqual(rows[1][6:], ["Sample Paper", "error"])

    def test_new_record_uses_safe_defaults_matching_template(self) -> None:
        root = self.make_root("source_only")
        with self.globals_patch(root):
            result = papers.new_record(
                "new-paper",
                "New Paper",
                "query-processing",
                ["query-execution"],
                "https://example.com/new",
            )
        self.assertEqual(result, 0)
        created = yaml.safe_load(
            (root / "papers/query-processing/new-paper/paper.yaml").read_text(encoding="utf-8")
        )
        template = yaml.safe_load((REPO_ROOT / "templates/paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual(created["authors"], template["authors"])
        self.assertEqual(created["year"], template["year"])
        self.assertEqual(created["reading_status"], template["reading_status"])


if __name__ == "__main__":
    unittest.main()
