from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_resources import (  # noqa: E402
    formal_resource_representations,
    markdown_table_risks,
    source_coverage_findings,
)


TABLE = "| Key | Value |\n| --- | --- |\n| a | b |"
ALGORITHM = "```text\nread current row\nreturn next row\n```"


class ResourcePayloadMatchingTests(unittest.TestCase):
    def test_chapter_qualified_resource_numbers_remain_distinct(self) -> None:
        source = "Figure 2.1. First\nFigure 2.2. Second\nFigure 3: Third\n"
        text = (
            "![图 2.1：第一幅](assets/a.png)\n\n图 2.1：第一幅。\n\n"
            "![第二幅](assets/b.png)\n\n### 图 2.2：第二幅。\n\n"
            "![图 3：第三幅](assets/c.png)"
        )
        self.assertEqual(set(formal_resource_representations(text)["figure"]), {"2.1", "2.2", 3})
        errors, risks = source_coverage_findings(source, text, False)
        self.assertEqual(errors, [])
        self.assertFalse(any("payload candidate" in risk or "image candidates" in risk for risk in risks))
        _errors, risks = source_coverage_findings(source + "Figure 2.10\n", text, False)
        self.assertTrue(any("Figure 2.10 has no formal" in risk for risk in risks))

    def test_duplicate_decimal_resources_still_report_duplicates(self) -> None:
        source = "Table 2.1: Results\n"
        text = f"### 表 2.1：结果\n\n{TABLE}\n\n正文。\n\n### 表 2.1：结果\n\n{TABLE}"
        errors, _risks = source_coverage_findings(source, text, False)
        self.assertIn("Table 2.1 has 2 formal representations", errors)
        _errors, risks = source_coverage_findings(
            "Figure 2.1: First\n", "![图2.1](assets/a.png)\n\n![图2.1](assets/b.png)", False
        )
        self.assertTrue(any("Figure 2.1 has 2 image candidates" in risk for risk in risks))

    def test_decimal_support_does_not_turn_bare_integer_mentions_into_captions(self) -> None:
        _errors, risks = source_coverage_findings(
            "Table 50\nFigure 11\nTable 2.1: Actual caption\n", "没有表格。", False
        )
        self.assertFalse(any("Table 50" in risk or "Figure 11" in risk for risk in risks))
        self.assertTrue(any("Table 2.1 has no formal" in risk for risk in risks))

    def test_table_width_warning_detects_raw_pipe_even_inside_code_span(self) -> None:
        text = "| Type | Description |\n| --- | --- |\n| union | `str | float` |"
        risks = markdown_table_risks(text)
        self.assertEqual(len(risks), 1)
        self.assertIn("line 3", risks[0])
        self.assertIn("3 cells", risks[0])
        self.assertEqual(markdown_table_risks(text.replace("str | float", r"str \| float")), [])

    def test_table_width_warning_ignores_comments_code_and_non_tables(self) -> None:
        broken = "| A | B |\n| --- | --- |\n| 1 | 2 | 3 |"
        for text in (
            "", "ordinary | prose", "| A | B |\n\n| 1 | 2 | 3 |",
            "<!--\n" + broken + "\n-->",
            "```markdown\n" + broken + "\n```",
            "\n".join("    " + line for line in broken.splitlines()),
            TABLE + "\n\n| unrelated | text | here |",
        ):
            with self.subTest(text=text):
                self.assertEqual(markdown_table_risks(text), [])

    def test_consecutive_preceding_and_following_captions_keep_distinct_payloads(self) -> None:
        for kind, label, payload in (
            ("table", "表", TABLE), ("algorithm", "算法", ALGORITHM),
        ):
            for before in (True, False):
                parts = []
                for number in (1, 2, 3):
                    caption = f"**{label} {number}：描述。**"
                    parts.extend((caption, payload) if before else (payload, caption))
                with self.subTest(kind=kind, before=before):
                    found = formal_resource_representations("\n\n".join(parts))[kind]
                    self.assertEqual(set(found), {1, 2, 3})
                    self.assertEqual(len(set.union(*found.values())), 3)

    def test_heading_and_emphasis_caption_formats(self) -> None:
        for kind, label, payload in (
            ("table", "表", TABLE), ("algorithm", "算法", ALGORITHM),
        ):
            for caption in (
                f"### {label} 1：描述", f"*{label} 1：描述*",
                f"**{label} 1**：描述", f"### **{label} 1**：描述",
            ):
                with self.subTest(kind=kind, caption=caption):
                    found = formal_resource_representations(caption + "\n\n" + payload)
                    self.assertEqual(set(found[kind]), {1})

    def test_narrative_image_alt_does_not_claim_referenced_figure(self) -> None:
        text = (
            "![图2超图上的26个遍历步骤](assets/figure-3.png)\n\n"
            "**图 3：算法在图 2 上的执行轨迹。**"
        )
        self.assertEqual(formal_resource_representations(text)["figure"], {
            3: {"image:assets/figure-3.png"},
        })
        for alt in ("图 3", "图3：执行轨迹", "Figure 3: Trace"):
            with self.subTest(alt=alt):
                self.assertEqual(
                    set(formal_resource_representations(f"![{alt}](assets/a.png)")["figure"]),
                    {3},
                )

    def test_code_figure_before_next_image_keeps_its_own_caption(self) -> None:
        text = (
            ALGORITHM + "\n\n**图 1：程序。**\n\n"
            "![下一幅图](assets/figure-2.png)\n\n**图 2：示意图。**"
        )
        found = formal_resource_representations(text)["figure"]
        self.assertEqual(set(found), {1, 2})
        self.assertTrue(next(iter(found[1])).startswith("fence-line:"))
        self.assertEqual(found[2], {"image:assets/figure-2.png"})

    def test_missing_ambiguous_or_hidden_payloads_remain_missing(self) -> None:
        cases = (
            "", "### 表 1：没有载荷", "### 算法 1：没有载荷",
            "<!-- ### 表 1：隐藏 -->\n\n" + TABLE,
            "```markdown\n### 表 1：代码样例\n" + TABLE + "\n```",
            "`表 1：代码跨度`\n\n" + TABLE,
            "表 1 展示结果。\n\n" + TABLE,
            "### 表 1：第一表\n\n" + TABLE + "\n\n### 表 2：第二表",
        )
        for text in cases:
            with self.subTest(text=text):
                found = formal_resource_representations(text)
                self.assertEqual(found["table"], {})
                self.assertEqual(found["algorithm"], {})

    def test_duplicate_real_payloads_are_still_reported(self) -> None:
        for label, source, payload in (
            ("表", "Table 1: Results", TABLE),
            ("算法", "Algorithm 1: Read rows", ALGORITHM),
        ):
            text = f"### {label} 1：描述\n\n{payload}\n\n分隔正文。\n\n### {label} 1：描述\n\n{payload}"
            errors, _risks = source_coverage_findings(source, text, False)
            self.assertTrue(any("has 2 formal representations" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
