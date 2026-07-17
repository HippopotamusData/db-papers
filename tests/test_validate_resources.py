from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_resources import source_coverage_findings, validate_images  # noqa: E402


class ResourceValidationTests(unittest.TestCase):
    def test_duplicate_and_orphan_assets_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            Image.new("RGB", (2, 2), "white").save(assets / "used.png")
            Image.new("RGB", (2, 2), "white").save(assets / "orphan.png")
            text = "![图 1](assets/used.png)\n![重复图 1](assets/used.png)\n"
            errors, risks = validate_images(paper, text, allow_whole_page=False)
            self.assertTrue(any("duplicate image references" in issue for issue in errors))
            self.assertTrue(any("orphan asset" in issue for issue in risks))

    def test_image_link_cannot_escape_paper_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            errors, _risks = validate_images(
                paper, "![bad](../other/assets/image.png)", allow_whole_page=False
            )
            self.assertTrue(any("safe assets/" in issue for issue in errors))

    def test_symlink_target_cannot_escape_paper_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paper = root / "paper"
            assets = paper / "assets"
            assets.mkdir(parents=True)
            outside = root / "outside.png"
            Image.new("RGB", (2, 2), "white").save(outside)
            (assets / "escape.png").symlink_to(outside)
            errors, _risks = validate_images(
                paper, "![图 1](assets/escape.png)", allow_whole_page=False
            )
            self.assertTrue(any("resolves outside" in issue for issue in errors))

    def test_corrupt_image_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            (assets / "broken.png").write_bytes(b"not an image")
            errors, _risks = validate_images(
                paper, "![图 1](assets/broken.png)", allow_whole_page=False
            )
            self.assertTrue(any("not decodable" in issue for issue in errors))

    def test_algorithm_duplicate_representation_is_an_error(self) -> None:
        source = "Algorithm 1: Parse a row"
        translation = "**算法 1：解析一行。**\n\n```text\nparse(row)\n```\n\n![算法 1](assets/algorithm-01.png)\n"
        errors, _risks = source_coverage_findings(source, translation, False)
        self.assertIn("Algorithm 1 has 2 formal representations", errors)

    def test_algorithm_caption_with_one_image_is_not_a_duplicate(self) -> None:
        source = "Algorithm 1: Parse a row"
        translation = "**算法 1：解析一行。**\n\n![算法 1](assets/algorithm-01.png)\n"
        errors, _risks = source_coverage_findings(source, translation, False)
        self.assertFalse(any("formal representations" in issue for issue in errors))

    def test_image_before_caption_is_a_formal_figure_representation(self) -> None:
        source = "Figure 1: Architecture"
        translation = "![架构](assets/figure-1.png)\n\n**图 1：系统架构。**\n"
        _errors, risks = source_coverage_findings(source, translation, False)
        self.assertFalse(any("formal translation-side payload" in issue for issue in risks))

    def test_code_backed_figure_is_a_formal_representation(self) -> None:
        source = "Figure 2: Email program"
        translation = "**图 2：邮件程序。**\n\n```python\nprint('mail')\n```\n"
        errors, risks = source_coverage_findings(source, translation, False)
        self.assertFalse(errors)
        self.assertFalse(any("formal translation-side payload" in issue for issue in risks))

    def test_figure_image_takes_precedence_over_code_transcription(self) -> None:
        source = "Figure 2: Email program"
        translation = (
            "![图 2：邮件程序](assets/figure-2.png)\n\n"
            "图 2：带编号标注的邮件程序。\n\n"
            "```python\nprint('mail')\n```\n"
        )
        errors, risks = source_coverage_findings(source, translation, False)
        self.assertFalse(errors)
        self.assertFalse(any("Figure 2 has" in issue for issue in risks))

    def test_prose_cross_reference_before_next_image_is_not_a_caption(self) -> None:
        source = "Figure 7: Scale up\nFigure 8: Network"
        translation = (
            "![纵向扩展](assets/figure-7.png)\n\n"
            "**图 7：纵向扩展。**\n\n"
            "图 7 按 CPU 数绘制结果，并由图 8 解释网络瓶颈。\n\n"
            "![网络](assets/figure-8.png)\n\n"
            "**图 8：网络带宽。**\n"
        )
        errors, risks = source_coverage_findings(source, translation, False)
        self.assertFalse(any("formal representations" in issue for issue in errors))
        self.assertFalse(any("formal translation-side payload" in issue for issue in risks))

    def test_table_cross_reference_does_not_reuse_previous_table_payload(self) -> None:
        source = "Table 1: Grammar\nTable 2: Results"
        translation = (
            "**表 1：文法。**\n\n| A |\n| --- |\n| x |\n\n"
            "表 2 给出了结果。\n\n"
            "**表 2：结果。**\n\n| B |\n| --- |\n| y |\n"
        )
        errors, risks = source_coverage_findings(source, translation, False)
        self.assertFalse(any("formal representations" in issue for issue in errors))
        self.assertFalse(any("formal translation-side payload" in issue for issue in risks))

    def test_markdown_table_and_table_image_are_duplicate_representations(self) -> None:
        source = "Table 1: Results"
        translation = (
            "**表 1：结果。**\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
            "![表 1：结果](assets/table-01.png)\n"
        )
        errors, _risks = source_coverage_findings(source, translation, False)
        self.assertIn("Table 1 has 2 formal representations", errors)

    def test_multiple_figure_images_are_a_review_candidate(self) -> None:
        source = "Figure 1: Results"
        translation = (
            "![图 1a](assets/figure-01a.png)\n"
            "![图 1b](assets/figure-01b.png)\n"
        )
        _errors, risks = source_coverage_findings(source, translation, False)
        self.assertTrue(any("verify subfigures" in issue for issue in risks))

    def test_cross_reference_inside_another_image_alt_is_not_a_duplicate(self) -> None:
        source = "Figure 2: Records\nFigure 3: Encoding"
        translation = (
            "![图 2：样例记录](assets/figure-02.png)\n"
            "![图 3：图 2 样例的列式编码](assets/figure-03.png)\n"
        )
        _errors, risks = source_coverage_findings(source, translation, False)
        self.assertFalse(any("Figure 2 has" in issue for issue in risks))

    def test_prose_cross_references_do_not_satisfy_resource_coverage(self) -> None:
        source = (
            "Figure 1: Architecture\n"
            "Table 2: Results\n"
            "Algorithm 3 Parse a row\n"
        )
        translation = "图 1 展示架构。\n表 2 汇总结果。\n算法 3 解析一行。\n"
        _errors, risks = source_coverage_findings(source, translation, False)
        self.assertTrue(any("Figure 1" in issue and "formal" in issue for issue in risks))
        self.assertTrue(any("Table 2" in issue and "formal" in issue for issue in risks))
        self.assertTrue(any("Algorithm 3" in issue and "formal" in issue for issue in risks))

    def test_two_column_layout_captions_after_long_spacing_are_detected(self) -> None:
        source = (
            "left column" + (" " * 4000) + "Figure 7: Architecture\n"
            "left column" + (" " * 4000) + "Table 8: Results\n"
            "left column" + (" " * 4000) + "Algorithm 9: Probe rows\n"
        )
        _errors, risks = source_coverage_findings(source, "正文没有资源。\n", False)
        self.assertTrue(any("Figure 7" in issue for issue in risks))
        self.assertTrue(any("Table 8" in issue for issue in risks))
        self.assertTrue(any("Algorithm 9" in issue for issue in risks))

    def test_page_start_form_feed_captions_are_detected(self) -> None:
        source = (
            "\fFigure 5: Architecture\n"
            "\fTable 7: Results\n"
            "\fAlgorithm 9: Probe rows\n"
        )
        _errors, risks = source_coverage_findings(source, "正文没有资源。\n", False)
        self.assertTrue(any("Figure 5" in issue for issue in risks))
        self.assertTrue(any("Table 7" in issue for issue in risks))
        self.assertTrue(any("Algorithm 9" in issue for issue in risks))

    def test_caption_payloads_and_numbered_images_satisfy_resource_coverage(self) -> None:
        source = (
            "Figure 1: Architecture\n"
            "Table 2: Results\n"
            "Algorithm 3 Parse a row\n"
        )
        translation = (
            "图 1：架构\n\n![架构](assets/architecture.png)\n\n"
            "表 2：结果\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
            "Algorithm 3 Parse a row\n\n```text\nparse(row)\n```\n"
        )
        _errors, risks = source_coverage_findings(source, translation, False)
        self.assertFalse(any("formal translation-side payload" in issue for issue in risks))

    def test_missing_numbered_reference_is_an_error(self) -> None:
        source = "REFERENCES\n[1] First paper.\n[2] Second paper.\n"
        translation = "## 参考文献\n\n- [1] First paper.\n"
        errors, _risks = source_coverage_findings(source, translation, True)
        self.assertIn("missing numbered references: 2", errors)

    def test_contiguous_numeric_reference_series_normalizes_one_ocr_i(self) -> None:
        source = (
            "REFERENCES\n"
            "[i] Alice Author. First database paper. Journal 1.\n"
            "[2] Bob Author. Second database paper. Journal 2.\n"
            "[3] Carol Author. Third database paper. Journal 3.\n"
        )
        translation = (
            "## 参考文献\n\n"
            "- [1] Alice Author. First database paper. Journal 1.\n"
            "- [2] Bob Author. Second database paper. Journal 2.\n"
            "- [3] Carol Author. Third database paper. Journal 3.\n"
        )
        errors, risks = source_coverage_findings(source, translation, True)
        self.assertFalse(errors)
        self.assertEqual(
            risks,
            [
                "source reference identifier i was normalized to 1 as a contiguous numeric-series OCR candidate"
            ],
        )

    def test_mixed_author_keys_do_not_trigger_reference_ocr_normalization(self) -> None:
        source = (
            "REFERENCES\n"
            "[i] Alice Author. Indexed database paper. Journal 1.\n"
            "[BMG93] Bob Author. Named-key database paper. Journal 2.\n"
        )
        translation = (
            "## 参考文献\n\n"
            "- [1] Alice Author. Indexed database paper. Journal 1.\n"
            "- [BMG93] Bob Author. Named-key database paper. Journal 2.\n"
        )
        errors, risks = source_coverage_findings(source, translation, True)
        self.assertIn("missing numbered references: i", errors)
        self.assertFalse(any("normalized" in issue for issue in risks))

    def test_alphanumeric_and_decimal_references_are_matched(self) -> None:
        source = (
            "REFERENCES\n"
            "[BMG93] A. Author. Database systems in 1993. Journal 12.\n"
            "2. B. Author. Another database paper in 2001. Venue 4.\n"
        )
        translation = (
            "## 参考文献\n\n"
            "- [BMG93] A. Author. Database systems in 1993. Journal 12.\n"
            "2. B. Author. Another database paper in 2001. Venue 4.\n"
        )
        errors, _risks = source_coverage_findings(source, translation, True)
        self.assertFalse(any("missing numbered references" in issue for issue in errors))

    def test_duplicate_translation_reference_is_an_error(self) -> None:
        source = "REFERENCES\n[BMG93] A complete database systems citation.\n"
        translation = (
            "## 参考文献\n\n"
            "- [BMG93] A complete database systems citation.\n"
            "- [BMG93] Duplicate citation.\n"
        )
        errors, _risks = source_coverage_findings(source, translation, True)
        self.assertTrue(any("duplicate translation reference" in issue for issue in errors))

    def test_short_reference_content_is_a_review_candidate(self) -> None:
        source = (
            "REFERENCES\n"
            "[1] Alice Example and Bob Example. A long database systems paper title. "
            "Proceedings of the Database Conference, 2020.\n"
        )
        translation = "## 参考文献\n\n- [1] Alice.\n"
        _errors, risks = source_coverage_findings(source, translation, True)
        self.assertTrue(any("suspiciously short" in issue for issue in risks))

    def test_low_coverage_unnumbered_bibliography_is_a_risk(self) -> None:
        source = (
            "BIBLIOGRAPHY\n"
            "Alice Author. A complete database systems paper. Database Journal 2020.\n"
            "Bob Author. A second complete database systems paper. Systems Venue 2021.\n"
        )
        translation = "## 参考文献\n\n见原文。\n"
        errors, risks = source_coverage_findings(source, translation, True)
        self.assertFalse(errors)
        self.assertTrue(any("non-numbered bibliography" in issue for issue in risks))

    def test_latex_tag_is_an_equation_number_candidate(self) -> None:
        source = "score = left + right                                      (5)\n"
        translation = "$$\nscore = left + right \\tag{5}\n$$\n"
        _errors, risks = source_coverage_findings(source, translation, False)
        self.assertFalse(any("equation (5)" in issue for issue in risks))

    def test_equation_cross_reference_is_not_a_formula_candidate(self) -> None:
        source = "score = left + right                                      (5)\n"
        translation = "计算过程见公式 (5)。\n"
        _errors, risks = source_coverage_findings(source, translation, False)
        self.assertTrue(any("equation (5)" in issue for issue in risks))

    def test_missing_structural_headings_are_review_candidates(self) -> None:
        source = (
            "ABSTRACT\nText\n"
            "1 INTRODUCTION\nText\n"
            "2 METHODS\nText\n"
            "3 CONCLUSIONS\nText\n"
        )
        translation = "## 1 引言\n正文。\n## 3 结论\n正文。\n"
        _errors, risks = source_coverage_findings(source, translation, False)
        self.assertTrue(any("Abstract heading" in issue for issue in risks))
        self.assertFalse(any("Conclusion/Summary" in issue for issue in risks))
        self.assertTrue(any(issue.endswith("candidates: 2") for issue in risks))

    def test_numeric_ocr_rows_do_not_form_a_heading_sequence(self) -> None:
        for source in (
            "150000 THROUGHPUT\nText\n",
            "16 SIMD\n64 LANES\nText\n",
            "2 METHODS\n1 INTRODUCTION\nText\n",
        ):
            with self.subTest(source=source):
                _errors, risks = source_coverage_findings(source, "正文。\n", False)
                self.assertFalse(any("numbered top-level" in issue for issue in risks))

    def test_heading_sequence_stops_at_first_gap_and_before_references(self) -> None:
        source = (
            "1 INTRODUCTION\nText\n"
            "2 METHODS\nText\n"
            "5000 THROUGHPUT\n"
            "REFERENCES\n"
            "3 RESULTS\n"
        )
        translation = "## 1 引言\n正文。\n"
        _errors, risks = source_coverage_findings(source, translation, False)
        heading_risks = [issue for issue in risks if "numbered top-level" in issue]
        self.assertEqual(len(heading_risks), 1)
        self.assertTrue(heading_risks[0].endswith("candidates: 2"))

    @unittest.skipUnless(shutil.which("git"), "git is required for ignore tests")
    def test_ignored_orphan_is_suppressed_but_reference_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(
                ["git", "init", "-q", str(root)], check=True, stdout=subprocess.DEVNULL
            )
            paper = root / "paper"
            assets = paper / "assets"
            assets.mkdir(parents=True)
            (root / ".gitignore").write_text("paper/assets/qa.png\n", encoding="utf-8")
            Image.new("RGB", (2, 2), "white").save(assets / "qa.png")

            errors, risks = validate_images(paper, "", allow_whole_page=False)
            self.assertFalse(errors)
            self.assertFalse(any("qa.png" in issue for issue in risks))

            errors, _risks = validate_images(
                paper, "![图 1](assets/qa.png)", allow_whole_page=False
            )
            self.assertTrue(any("git-ignored asset" in issue for issue in errors))


if __name__ == "__main__":
    unittest.main()
