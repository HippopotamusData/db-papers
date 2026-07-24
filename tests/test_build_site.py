from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site  # noqa: E402


class BuildSiteTests(unittest.TestCase):
    def make_repo(self, root: Path, *, accepted: bool = True) -> None:
        (root / "config").mkdir()
        (root / "papers/query-processing/accepted-paper/assets").mkdir(
            parents=True
        )
        (root / "papers/query-processing/draft-paper").mkdir(parents=True)
        (root / "site_assets/stylesheets").mkdir(parents=True)
        (root / "site_assets/javascripts").mkdir(parents=True)
        (root / "zensical.toml").write_text(
            "[project]\nsite_name = \"Test\"\n\n[project.theme]\n",
            encoding="utf-8",
        )
        (root / "config/taxonomy.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "areas": {
                        "query-processing": {
                            "label_zh": "查询处理",
                            "description": "查询优化与执行。",
                        }
                    },
                    "topics": {
                        "query-execution": {
                            "label_zh": "查询执行",
                            "description": "执行机制。",
                        }
                    },
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (root / "config/acceptance.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "entries": {"accepted-paper": {}} if accepted else {},
                }
            ),
            encoding="utf-8",
        )
        accepted_metadata = {
            "title": "Accepted Paper",
            "authors": ["Ada Example"],
            "year": 2024,
            "source_url": "https://example.com/accepted",
            "topics": ["query-execution"],
            "reading_status": "translated",
            "rating": {"score": 4.5},
        }
        draft_metadata = {
            "title": "Draft Paper",
            "authors": ["Grace Example"],
            "year": 2025,
            "source_url": "https://example.com/draft",
            "topics": ["query-execution"],
            "reading_status": "draft",
        }
        for paper_id, metadata in (
            ("accepted-paper", accepted_metadata),
            ("draft-paper", draft_metadata),
        ):
            paper_dir = root / "papers/query-processing" / paper_id
            (paper_dir / "paper.yaml").write_text(
                yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        (root / "papers/query-processing/accepted-paper/translation.md").write_text(
            """---
paper_id: accepted-paper
title: Accepted Paper
language: zh-CN
source: source.pdf
---

# Accepted Paper（中文译文）

正文与公式 $x + y$。

![figure](assets/figure.png)
""",
            encoding="utf-8",
        )
        (root / "papers/query-processing/draft-paper/translation.md").write_text(
            "# unaccepted draft\n",
            encoding="utf-8",
        )
        (root / "papers/query-processing/accepted-paper/source.pdf").write_bytes(
            b"not published"
        )
        (root / "papers/query-processing/draft-paper/source.pdf").write_bytes(
            b"not published"
        )
        (root / "papers/query-processing/accepted-paper/assets/figure.png").write_bytes(
            b"image"
        )
        (root / "site_assets/stylesheets/extra.css").write_text(
            "body { color: black; }\n",
            encoding="utf-8",
        )
        (root / "site_assets/javascripts/catalog.js").write_text(
            "void 0;\n",
            encoding="utf-8",
        )

    def test_prepare_publishes_only_accepted_translations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            output = root / "site_src"
            summary = build_site.prepare_site(root, output)
            self.assertEqual(summary["records"], 2)
            self.assertEqual(summary["translated_pages"], 1)
            accepted = (
                output
                / "papers/query-processing/accepted-paper/index.md"
            ).read_text(encoding="utf-8")
            self.assertIn(
                '<a class="md-button md-button--primary" href="source.pdf"',
                accepted,
            )
            self.assertIn(">阅读原文</a>", accepted)
            self.assertIn('href="https://example.com/accepted"', accepted)
            self.assertIn(">官方链接</a>", accepted)
            self.assertNotIn("<dt>作者</dt>", accepted)
            self.assertIn("<dt>主题</dt>", accepted)
            self.assertIn("Accepted Paper（中文译文）", accepted)
            self.assertNotIn("source: source.pdf", accepted)
            self.assertTrue(
                (
                    output
                    / "papers/query-processing/accepted-paper/assets/figure.png"
                ).is_file()
            )
            self.assertFalse(
                (output / "papers/query-processing/draft-paper/index.md").exists()
            )
            self.assertEqual(
                {
                    path.relative_to(output).as_posix()
                    for path in output.rglob("source.pdf")
                },
                {
                    "papers/query-processing/accepted-paper/source.pdf",
                    "papers/query-processing/draft-paper/source.pdf",
                },
            )
            generated_config = (root / "site.generated.toml").read_text(
                encoding="utf-8"
            )
            self.assertIn('{ "开始" = [', generated_config)
            self.assertIn('{ "论文领域" = [', generated_config)
            self.assertNotIn('"首页" = "index.md"', generated_config)
            self.assertIn('"查询处理" = "papers/query-processing/index.md"', generated_config)
            home = (output / "index.md").read_text(encoding="utf-8")
            self.assertIn("title: 数据库系统论文档案馆", home)
            self.assertNotIn("title: DB Papers", home)
            self.assertIn("数据库系统论文档案馆", home)
            self.assertIn("同时提供经过审校的中文译文与论文原文", home)
            self.assertNotIn("GitHub 仓库", home)
            self.assertNotIn("完整性与准确性检查", home)
            self.assertNotIn("发布边界", home)
            self.assertNotIn("阅读价值评分", home)
            catalog = (output / "catalog.md").read_text(encoding="utf-8")
            self.assertIn("Accepted Paper", catalog)
            self.assertIn("Draft Paper", catalog)
            self.assertEqual(catalog.count(">阅读原文</a>"), 2)
            self.assertIn(
                'href="papers/query-processing/accepted-paper/source.pdf"',
                catalog,
            )
            self.assertIn(
                'href="papers/query-processing/draft-paper/source.pdf"',
                catalog,
            )
            self.assertIn(
                '<h3><a href="papers/query-processing/accepted-paper/">'
                "Accepted Paper</a></h3>",
                catalog,
            )
            self.assertIn(
                '<h3><a href="papers/query-processing/draft-paper/source.pdf"'
                ' target="_blank" rel="noopener noreferrer">'
                "Draft Paper</a></h3>",
                catalog,
            )
            self.assertNotIn("https://example.com/draft", catalog)
            self.assertNotIn("阅读中文译文", catalog)
            self.assertNotIn("访问权威原文", catalog)

    def test_translated_record_requires_acceptance_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root, accepted=False)
            with self.assertRaisesRegex(
                ValueError, "translated paper has no acceptance entry"
            ):
                build_site.prepare_site(root, root / "site_src")

    def test_site_source_output_must_stay_inside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            with tempfile.TemporaryDirectory() as outside:
                with self.assertRaisesRegex(
                    ValueError, "dedicated directory inside the repo"
                ):
                    build_site.prepare_site(root, Path(outside) / "site")


if __name__ == "__main__":
    unittest.main()
