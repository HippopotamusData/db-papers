from __future__ import annotations

import contextlib
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PapersTests(unittest.TestCase):
    def make_root(self, status: str = "source_only") -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "config").mkdir()
        (root / "papers/query-processing/sample-paper").mkdir(parents=True)
        (root / "config/project.yaml").write_text(
            (REPO_ROOT / "config/project.yaml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        (root / "config/taxonomy.yaml").write_text(
            "schema_version: 1\nareas:\n  query-processing:\n    label_zh: 查询处理\n    description: 测试。\ntopics:\n  query-execution:\n    label_zh: 查询执行\n",
            encoding="utf-8",
        )
        (root / "config/paper-policy.yaml").write_text(
            "schema_version: 1\npage_limit_exceptions: {}\nskipped_reasons: {}\n", encoding="utf-8"
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
        if status == "translated":
            entries["sample-paper"] = {
                "source_sha256": sha256(paper / "source.pdf"),
                "translation_sha256": sha256(paper / "translation.md"),
                "accepted_version": "test-v1",
                "risk_disposition": ["section-review-complete"],
            }
        (root / "config/acceptance.yaml").write_text(
            yaml.safe_dump({"schema_version": 1, "entries": entries}, sort_keys=False), encoding="utf-8"
        )
        return root

    def globals_patch(self, root: Path):
        return patch.multiple(
            papers,
            ROOT=root,
            PAPERS=root / "papers",
            CATALOG=root / "CATALOG.md",
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

    def test_translated_paper_without_ledger_entry_is_rejected(self) -> None:
        root = self.make_root("translated")
        ledger_path = root / "config/acceptance.yaml"
        ledger_path.write_text("schema_version: 1\nentries: {}\n", encoding="utf-8")
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
            papers, "acceptance_preflight", return_value=(True, "")
        ):
            result = papers.accept_record(
                "sample-paper", "test-review-v2", ["section-review-complete"]
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

    def test_acceptance_preflight_failure_rolls_back_ledger_and_status(self) -> None:
        root = self.make_root("draft")
        metadata_path = root / "papers/query-processing/sample-paper/paper.yaml"
        ledger_path = root / "config/acceptance.yaml"
        original_metadata = metadata_path.read_text(encoding="utf-8")
        original_ledger = ledger_path.read_text(encoding="utf-8")
        with self.globals_patch(root), patch.object(
            papers,
            "acceptance_preflight",
            return_value=(False, "ERROR: missing standard translator note"),
        ), contextlib.redirect_stderr(io.StringIO()):
            result = papers.accept_record(
                "sample-paper", "test-review-v2", ["section-review-complete"]
            )
        self.assertEqual(result, 1)
        self.assertEqual(metadata_path.read_text(encoding="utf-8"), original_metadata)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)

    def test_acceptance_preflight_forces_deep_validation(self) -> None:
        root = self.make_root("draft")
        environments: list[dict[str, str]] = []

        def succeed(command, **kwargs):
            environments.append(kwargs["env"])
            return subprocess.CompletedProcess(command, 0, "", "")

        with self.globals_patch(root), patch.object(papers.subprocess, "run", side_effect=succeed):
            passed, output = papers.acceptance_preflight("sample-paper")
        self.assertTrue(passed)
        self.assertEqual(output, "")
        self.assertEqual(len(environments), 3)
        self.assertTrue(all(environment["DEEP_VALIDATION"] == "1" for environment in environments))

    def test_accept_rejects_direct_refresh_of_translated_paper(self) -> None:
        root = self.make_root("translated")
        ledger_path = root / "config/acceptance.yaml"
        original_ledger = ledger_path.read_text(encoding="utf-8")
        with self.globals_patch(root), contextlib.redirect_stderr(io.StringIO()):
            result = papers.accept_record(
                "sample-paper", "bypass", ["section-review-complete"]
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
            papers, "atomic_write_text", side_effect=fail_metadata_once
        ), contextlib.redirect_stderr(io.StringIO()):
            result = papers.accept_record(
                "sample-paper", "test-review-v2", ["section-review-complete"]
            )
        self.assertEqual(result, 1)
        self.assertEqual(metadata_path.read_text(encoding="utf-8"), original_metadata)
        self.assertEqual(ledger_path.read_text(encoding="utf-8"), original_ledger)

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
        policy_path = root / "config/paper-policy.yaml"
        policy_path.write_text(
            "schema_version: 1\npage_limit_exceptions:\n"
            "  sample-paper:\n    max_pages: 80\n    reason: explicit test override\n"
            "skipped_reasons: {}\n",
            encoding="utf-8",
        )
        stdout = io.StringIO()
        with self.globals_patch(root), contextlib.redirect_stdout(stdout):
            self.assertEqual(papers.config_value("paper_page_limit", "sample-paper"), 0)
        self.assertEqual(stdout.getvalue().strip(), "80")

    def test_validation_manifest_batches_config_and_paper_policy(self) -> None:
        root = self.make_root("translated")
        stdout = io.StringIO()
        with self.globals_patch(root), contextlib.redirect_stdout(stdout):
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
        self.assertEqual(rows[1][4], "section-review-complete")
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
