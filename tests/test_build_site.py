from __future__ import annotations

import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site  # noqa: E402


class BuildSiteTests(unittest.TestCase):
    def make_repo(self, root: Path) -> None:
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
        accepted_metadata = {
            "title": "Accepted Paper",
            "title_zh": "已验收论文",
            "authors": ["Ada Example"],
            "year": 2024,
            "source_url": "https://example.com/accepted",
            "topics": ["query-execution"],
            "reading_status": "translated",
            "rating": {"score": 4.5},
        }
        draft_metadata = {
            "title": "Draft Paper",
            "title_zh": "草稿论文",
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

    def test_prepare_publishes_only_translated_records(self) -> None:
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
            self.assertIn(
                '<p class="paper-title-zh paper-title-zh--page">已验收论文</p>',
                accepted,
            )
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
            self.assertIn(
                '{ "开始" = [\n'
                '    { "首页" = "index.md" },\n'
                '    { "论文目录" = "catalog.md" },',
                generated_config,
            )
            self.assertIn('"查询处理" = "papers/query-processing/index.md"', generated_config)
            home = (output / "index.md").read_text(encoding="utf-8")
            self.assertIn("title: 数据库系统论文档案馆", home)
            self.assertIn(
                "提供论文原文和经过审校的中文译文。",
                home,
            )
            self.assertNotIn("便于查找、阅读和对照", home)
            self.assertNotIn("title: DB Papers", home)
            self.assertIn("数据库系统论文档案馆", home)
            self.assertNotIn("GitHub 仓库", home)
            self.assertNotIn("完整性与准确性检查", home)
            self.assertNotIn("发布边界", home)
            self.assertIn(
                "综合考虑影响广度、技术价值、实际应用、长期生命力和阅读回报",
                home,
            )
            self.assertIn("评分不评价译文质量", home)
            self.assertIn("无法精确体现论文对不同读者的全部价值", home)
            catalog = (output / "catalog.md").read_text(encoding="utf-8")
            self.assertIn("Accepted Paper", catalog)
            self.assertIn(
                '<p class="paper-card__title-zh">已验收论文</p>',
                catalog,
            )
            self.assertNotIn("<details", catalog)
            self.assertIn(
                'class="catalog-advanced__toggle" type="button"',
                catalog,
            )
            self.assertIn('aria-controls="catalog-advanced-fields"', catalog)
            self.assertIn('class="catalog-advanced__chevron"', catalog)
            self.assertIn("更多筛选与排序", catalog)
            self.assertIn('id="catalog-active-filters"', catalog)
            self.assertIn("accepted paper 已验收论文 ada example", catalog)
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

    def test_translated_record_requires_translation_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_repo(root)
            (
                root
                / "papers/query-processing/accepted-paper/translation.md"
            ).unlink()
            with self.assertRaisesRegex(
                ValueError,
                "translated paper must have a regular translation file",
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


class SiteAssetTests(unittest.TestCase):
    def test_theme_palette_cycles_system_light_and_dark(self) -> None:
        config = tomllib.loads(
            (ROOT / "zensical.toml").read_text(encoding="utf-8")
        )
        palette = config["project"]["theme"]["palette"]
        self.assertEqual(
            [entry["media"] for entry in palette],
            [
                "(prefers-color-scheme)",
                "(prefers-color-scheme: light)",
                "(prefers-color-scheme: dark)",
            ],
        )
        self.assertNotIn("scheme", palette[0])
        self.assertEqual(palette[1]["scheme"], "default")
        self.assertEqual(palette[2]["scheme"], "slate")
        self.assertEqual(
            [entry["toggle"]["name"] for entry in palette],
            ["切换到浅色模式", "切换到深色模式", "跟随系统主题"],
        )

    def test_home_area_cards_do_not_repeat_link_underlines(self) -> None:
        stylesheet = (
            ROOT / "site_assets/stylesheets/extra.css"
        ).read_text(encoding="utf-8")
        area_rule = stylesheet.split(".area-card {", 1)[1].split("}", 1)[0]
        self.assertIn("text-decoration: none !important;", area_rule)
        self.assertIn(".area-card:focus-visible", stylesheet)

    def test_mobile_full_width_stat_is_vertically_centered(self) -> None:
        stylesheet = (
            ROOT / "site_assets/stylesheets/extra.css"
        ).read_text(encoding="utf-8")
        stat_rule = stylesheet.split(
            ".stat-grid > div:last-child {", 1
        )[1].split("}", 1)[0]
        self.assertIn("align-items: center;", stat_rule)
        self.assertNotIn("align-items: baseline;", stat_rule)

    def test_browse_and_reader_content_use_centered_width_limits(self) -> None:
        stylesheet = (
            ROOT / "site_assets/stylesheets/extra.css"
        ).read_text(encoding="utf-8")
        self.assertIn("--dbp-browse-width: 64rem;", stylesheet)
        self.assertIn("--dbp-reader-width: 44rem;", stylesheet)
        self.assertIn(
            ".md-content__inner:not(:has(> .paper-meta)) {",
            stylesheet,
        )
        self.assertIn(
            "max-width: var(--dbp-browse-width);",
            stylesheet,
        )
        self.assertIn(
            "max-width: var(--dbp-reader-width);",
            stylesheet,
        )
        self.assertGreaterEqual(
            stylesheet.count("margin-inline: auto !important;"),
            2,
        )

    def test_header_title_uses_theme_default_behavior(self) -> None:
        navigation = (
            ROOT / "site_assets/javascripts/navigation.js"
        ).read_text(encoding="utf-8")
        self.assertIn("expandPrimaryNavigation", navigation)
        self.assertNotIn(".md-header__title", navigation)
        self.assertNotIn("window.scrollTo", navigation)
        self.assertNotIn("dbpHeaderLink", navigation)

    def test_search_enhancement_is_loaded(self) -> None:
        config = tomllib.loads(
            (ROOT / "zensical.toml").read_text(encoding="utf-8")
        )
        self.assertIn(
            "javascripts/search.js",
            config["project"]["extra_javascript"],
        )
        search = (ROOT / "site_assets/javascripts/search.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("搜索论文标题或正文", search)
        self.assertIn("当前显示", search)
        self.assertIn("dbp-search-group-toggle", search)


if __name__ == "__main__":
    unittest.main()
