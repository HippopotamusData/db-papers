from __future__ import annotations

import contextlib
import io
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


class PapersTests(unittest.TestCase):
    def make_root(self, status: str = "source_only") -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "config").mkdir()
        paper = root / "papers/query-processing/sample-paper"
        paper.mkdir(parents=True)
        (root / "config/policy.yaml").write_text(
            "schema_version: 1\n"
            "default_max_source_pages: 60\n"
            "papers: {}\n",
            encoding="utf-8",
        )
        (root / "config/taxonomy.yaml").write_text(
            "schema_version: 1\n"
            "areas:\n"
            "  query-processing:\n"
            "    label_zh: 查询处理\n"
            "    description: 测试。\n"
            "topics:\n"
            "  query-execution:\n"
            "    label_zh: 查询执行\n"
            "    description: 测试。\n"
            "  cloud-native:\n"
            "    label_zh: 云原生\n"
            "    description: 测试。\n",
            encoding="utf-8",
        )
        metadata = {
            "title": "Sample Paper",
            "title_zh": "示例论文",
            "authors": [],
            "year": None,
            "source_url": "https://example.com/paper",
            "topics": ["query-execution"],
            "reading_status": status,
        }
        (paper / "paper.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        (paper / "source.pdf").write_bytes(b"source evidence")
        if status in {"draft", "translated"}:
            translation = (
                "---\n"
                "paper_id: sample-paper\n"
                "title: Sample Paper\n"
                "language: zh-CN\n"
                "source: source.pdf\n"
                "---\n\n"
                "# Sample Paper（中文译文）\n"
            )
            (paper / "translation.md").write_text(
                translation,
                encoding="utf-8",
            )
            (paper / "assets").mkdir()
            (paper / "assets/figure.png").write_bytes(b"image")
        return root

    def globals_patch(self, root: Path):
        return patch.multiple(
            papers,
            ROOT=root,
            PAPERS=root / "papers",
            CATALOG=root / "CATALOG.md",
        )

    def test_translated_paper_validates_without_management_ledger(self) -> None:
        root = self.make_root("translated")
        with self.globals_patch(root):
            self.assertEqual(papers.validate(), 0)

    def test_translated_validation_has_no_stored_version_state(self) -> None:
        root = self.make_root("translated")
        paper = root / "papers/query-processing/sample-paper"
        source = paper / "source.pdf"
        translation = paper / "translation.md"
        source.write_bytes(source.read_bytes() + b" changed")
        translation.write_text(
            translation.read_text(encoding="utf-8") + "\n修订。\n",
            encoding="utf-8",
        )
        (paper / "assets/figure.png").write_bytes(b"replacement")
        with self.globals_patch(root):
            self.assertEqual(papers.validate(), 0)

    def test_scoped_validation_ignores_unrelated_in_progress_translation(
        self,
    ) -> None:
        root = self.make_root("source_only")
        other = root / "papers/query-processing/other-paper"
        other.mkdir()
        (other / "paper.yaml").write_text(
            yaml.safe_dump(
                {
                    "title": "Other Paper",
                    "title_zh": "其他论文",
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
        (other / "translation.md").write_text(
            "in-progress",
            encoding="utf-8",
        )
        with self.globals_patch(root):
            self.assertEqual(papers.validate("sample-paper"), 0)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(papers.validate(), 1)

    def test_scoped_validation_requires_exact_paper_id(self) -> None:
        root = self.make_root()
        with self.globals_patch(root), contextlib.redirect_stderr(
            io.StringIO()
        ):
            self.assertEqual(papers.validate("missing-paper"), 1)

    def test_source_and_translation_symlinks_are_rejected(self) -> None:
        root = self.make_root("draft")
        paper = root / "papers/query-processing/sample-paper"
        source = paper / "source.pdf"
        translation = paper / "translation.md"
        external_source = root / "external-source.pdf"
        external_translation = root / "external-translation.md"
        source.replace(external_source)
        translation.replace(external_translation)
        source.symlink_to(external_source)
        translation.symlink_to(external_translation)
        stderr = io.StringIO()
        with self.globals_patch(root), contextlib.redirect_stderr(stderr):
            self.assertEqual(papers.validate(), 1)
        self.assertIn(
            "source.pdf=True as a regular non-symlink",
            stderr.getvalue(),
        )
        self.assertIn(
            "translation.md=True as a regular non-symlink",
            stderr.getvalue(),
        )

    def test_unavailable_rejects_a_broken_source_symlink(self) -> None:
        root = self.make_root("source_only")
        paper = root / "papers/query-processing/sample-paper"
        metadata_path = paper / "paper.yaml"
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["reading_status"] = "unavailable"
        metadata_path.write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        source = paper / "source.pdf"
        source.unlink()
        source.symlink_to("missing.pdf")
        stderr = io.StringIO()
        with self.globals_patch(root), contextlib.redirect_stderr(stderr):
            self.assertEqual(papers.validate(), 1)
        self.assertIn(
            "source.pdf=False as a regular non-symlink",
            stderr.getvalue(),
        )

    def test_catalog_omits_topic_index_and_separates_source_links(self) -> None:
        root = self.make_root()
        with self.globals_patch(root):
            catalog = papers.build_catalog()
        self.assertNotIn("## 按主题浏览", catalog)
        self.assertIn(
            "| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 原文 | 官方链接 |",
            catalog,
        )
        self.assertNotIn("| 论文 | 作者 |", catalog)
        self.assertIn("| — | source_only |", catalog)
        self.assertIn(
            "[原文](papers/query-processing/sample-paper/source.pdf)",
            catalog,
        )
        self.assertIn(
            "[官方链接](<https://example.com/paper>)",
            catalog,
        )
        self.assertNotIn("示例论文", catalog)

    def test_catalog_uses_taxonomy_order_for_unordered_topics(self) -> None:
        root = self.make_root()
        metadata_path = (
            root / "papers/query-processing/sample-paper/paper.yaml"
        )
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["topics"] = ["cloud-native", "query-execution"]
        metadata_path.write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        with self.globals_patch(root):
            catalog = papers.build_catalog()
        self.assertIn("查询执行、云原生", catalog)

    def test_valid_rating_is_accepted_and_catalog_shows_only_score(self) -> None:
        root = self.make_root()
        metadata_path = (
            root / "papers/query-processing/sample-paper/paper.yaml"
        )
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["rating"] = {
            "score": 4.5,
            "influence_breadth": 4,
            "technical_value": 5,
            "practical_diffusion": 4,
            "durability": 5,
            "reader_payoff": 4,
        }
        metadata_path.write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        with self.globals_patch(root):
            self.assertEqual(papers.validate(), 0)
            catalog = papers.build_catalog()
        self.assertIn("| 4.5 | source_only |", catalog)
        self.assertNotIn("influence_breadth", catalog)

    def test_rating_score_must_match_weighted_dimensions(self) -> None:
        root = self.make_root()
        metadata_path = (
            root / "papers/query-processing/sample-paper/paper.yaml"
        )
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["rating"] = {
            "score": 5.0,
            "influence_breadth": 4,
            "technical_value": 5,
            "practical_diffusion": 4,
            "durability": 5,
            "reader_payoff": 4,
        }
        metadata_path.write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        stderr = io.StringIO()
        with self.globals_patch(root), contextlib.redirect_stderr(stderr):
            self.assertEqual(papers.validate(), 1)
        self.assertIn(
            "rating.score must equal the weighted score 4.5",
            stderr.getvalue(),
        )

    def test_five_point_rating_requires_landmark_gate(self) -> None:
        rating = {
            "score": 5.0,
            "influence_breadth": 4,
            "technical_value": 5,
            "practical_diffusion": 5,
            "durability": 5,
            "reader_payoff": 5,
        }
        self.assertEqual(
            papers.calculated_rating_score(rating),
            Decimal("4.5"),
        )

    def test_catalog_links_translated_paper_directly_to_translation(self) -> None:
        root = self.make_root("translated")
        with self.globals_patch(root):
            catalog = papers.build_catalog()
        self.assertIn(
            "papers/query-processing/sample-paper/translation.md",
            catalog,
        )

    def test_non_http_source_url_is_rejected(self) -> None:
        root = self.make_root()
        metadata_path = (
            root / "papers/query-processing/sample-paper/paper.yaml"
        )
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["source_url"] = "ftp://example.com/paper.pdf"
        metadata_path.write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        with self.globals_patch(root), contextlib.redirect_stderr(
            io.StringIO()
        ):
            self.assertEqual(papers.validate(), 1)

    def test_skipped_status_requires_project_reason(self) -> None:
        root = self.make_root()
        metadata_path = (
            root / "papers/query-processing/sample-paper/paper.yaml"
        )
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["reading_status"] = "skipped"
        metadata_path.write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        with self.globals_patch(root), contextlib.redirect_stderr(
            io.StringIO()
        ):
            self.assertEqual(papers.validate(), 1)

    def test_config_command_exposes_named_page_limit_exception(self) -> None:
        root = self.make_root()
        (root / "config/policy.yaml").write_text(
            "schema_version: 1\n"
            "default_max_source_pages: 60\n"
            "papers:\n"
            "  sample-paper:\n"
            "    max_source_pages: 80\n"
            "    authorization: explicit test override\n",
            encoding="utf-8",
        )
        stdout = io.StringIO()
        with self.globals_patch(root), contextlib.redirect_stdout(stdout):
            self.assertEqual(
                papers.config_value("paper_page_limit", "sample-paper"),
                0,
            )
        self.assertEqual(stdout.getvalue().strip(), "80")

    def test_validation_manifest_contains_only_current_paper_state(self) -> None:
        root = self.make_root("translated")
        stdout = io.StringIO()
        with self.globals_patch(root), contextlib.redirect_stdout(stdout):
            self.assertEqual(
                papers.validation_manifest("sample-paper"),
                0,
            )
        rows = [
            line.split(papers.VALIDATION_FIELD_SEPARATOR)
            for line in stdout.getvalue().splitlines()
        ]
        self.assertEqual(
            rows,
            [
                [
                    "config",
                    "source.pdf",
                    "translation.md",
                    "true",
                    "false",
                ],
                [
                    "paper",
                    "papers/query-processing/sample-paper",
                    "translated",
                    "60",
                    "",
                    "Sample Paper",
                    "error",
                ],
            ],
        )

    def test_new_record_uses_safe_defaults_matching_template(self) -> None:
        root = self.make_root()
        with self.globals_patch(root):
            result = papers.new_record(
                "new-paper",
                "New Paper",
                "新论文",
                "query-processing",
                ["query-execution"],
                "https://example.com/new",
            )
        self.assertEqual(result, 0)
        created = yaml.safe_load(
            (
                root / "papers/query-processing/new-paper/paper.yaml"
            ).read_text(encoding="utf-8")
        )
        template = yaml.safe_load(
            (REPO_ROOT / "templates/paper.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(created["authors"], template["authors"])
        self.assertEqual(created["title_zh"], "新论文")
        self.assertEqual(created["year"], template["year"])
        self.assertEqual(
            created["reading_status"],
            template["reading_status"],
        )


if __name__ == "__main__":
    unittest.main()
