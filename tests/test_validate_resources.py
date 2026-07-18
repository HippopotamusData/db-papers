from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_resources  # noqa: E402
from validate_resources import source_coverage_findings, validate_images  # noqa: E402


def save_nonuniform_image(path: Path, size: tuple[int, int] = (32, 16)) -> None:
    image = Image.new("RGB", size, "white")
    for index in range(min(64, size[0] * size[1])):
        image.putpixel((index % size[0], index // size[0]), (0, 0, 0))
    image.save(path)


class ResourceValidationTests(unittest.TestCase):
    def test_duplicate_and_orphan_assets_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            save_nonuniform_image(assets / "used.png")
            save_nonuniform_image(assets / "orphan.png")
            text = "![图 1](assets/used.png)\n![重复图 1](assets/used.png)\n"
            errors, risks = validate_images(paper, text, allow_whole_page=False)
            self.assertTrue(any("duplicate image references" in issue for issue in errors))
            self.assertTrue(any("orphan asset" in issue for issue in risks))

    def test_markdown_image_literals_in_code_or_escaped_text_are_not_links(
        self,
    ) -> None:
        translations = (
            "    ![图 1](assets/literal.png)\n",
            "```markdown\n![图 1](assets/literal.png)\n```\n",
            "`![图 1](assets/literal.png)`\n",
            "\\![图 1](assets/literal.png)\n",
        )
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            save_nonuniform_image(assets / "literal.png")
            for translation in translations:
                with self.subTest(translation=translation):
                    self.assertEqual(
                        validate_resources.image_links(translation),
                        [],
                    )
                    representations = (
                        validate_resources.formal_resource_representations(
                            translation
                        )
                    )
                    self.assertNotIn(1, representations["figure"])
                    _errors, coverage_risks = source_coverage_findings(
                        "Figure 1: Architecture\n",
                        translation,
                        require_references=False,
                    )
                    self.assertTrue(
                        any(
                            "Figure 1" in issue
                            and "formal translation-side payload" in issue
                            for issue in coverage_risks
                        )
                    )
                    image_errors, image_risks = validate_images(
                        paper,
                        translation,
                        allow_whole_page=False,
                    )
                    self.assertFalse(image_errors)
                    self.assertTrue(
                        any("orphan asset" in issue for issue in image_risks)
                    )

    def test_inline_comment_before_real_image_keeps_image_token(self) -> None:
        translation = (
            "visible <!-- hidden --> ![图 1](assets/visible.png)\n"
        )
        self.assertEqual(
            validate_resources.image_links(translation),
            [("图 1", "assets/visible.png")],
        )
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            save_nonuniform_image(assets / "visible.png")
            errors, risks = validate_images(
                paper,
                translation,
                allow_whole_page=False,
            )
            self.assertFalse(errors)
            self.assertFalse(any("orphan asset" in issue for issue in risks))

    def test_unclosed_comment_images_are_hidden_from_every_resource_gate(
        self,
    ) -> None:
        translation = (
            "![图 1](assets/visible.png)\n"
            "visible <!-- hidden\n"
            "![hidden](assets/hidden.png)\n"
        )
        self.assertEqual(
            validate_resources.image_links(translation),
            [("图 1", "assets/visible.png")],
        )
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            save_nonuniform_image(assets / "visible.png")
            save_nonuniform_image(assets / "hidden.png")
            errors, risks = validate_images(
                paper,
                translation,
                allow_whole_page=False,
            )
            self.assertFalse(errors)
            self.assertTrue(
                any("assets/hidden.png" in issue for issue in risks)
            )

    def test_image_target_aliases_are_canonical_and_cannot_evade_duplicates(
        self,
    ) -> None:
        translation = (
            "![图 1](assets/a.png)\n"
            "![图 2](assets/./a.png)\n"
        )
        self.assertEqual(
            validate_resources.image_links(translation),
            [("图 1", "assets/a.png"), ("图 2", "assets/a.png")],
        )
        representations = validate_resources.formal_resource_representations(
            translation
        )
        self.assertNotIn(1, representations["figure"])
        self.assertNotIn(2, representations["figure"])
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            save_nonuniform_image(assets / "a.png")
            errors, _risks = validate_images(
                paper,
                translation,
                allow_whole_page=False,
            )
            self.assertTrue(
                any("duplicate image references" in issue for issue in errors)
            )

    def test_angle_image_target_with_space_maps_to_local_asset(self) -> None:
        translation = "![图 1](<assets/a b.png>)\n"
        self.assertEqual(
            validate_resources.image_links(translation),
            [("图 1", "assets/a b.png")],
        )
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            save_nonuniform_image(assets / "a b.png")
            errors, risks = validate_images(
                paper,
                translation,
                allow_whole_page=False,
            )
            self.assertFalse(errors)
            self.assertFalse(risks)

    def test_hardlink_aliases_cannot_reuse_one_asset_for_two_figures(
        self,
    ) -> None:
        translation = (
            "![图 1](assets/a.png)\n"
            "![图 2](assets/alias.png)\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            save_nonuniform_image(assets / "a.png")
            (assets / "alias.png").hardlink_to(assets / "a.png")
            errors, _risks = validate_images(
                paper,
                translation,
                allow_whole_page=False,
            )
            self.assertTrue(
                any(
                    "resolve to the same asset file" in issue
                    for issue in errors
                )
            )

    def test_percent_encoded_nul_is_a_structured_image_error(self) -> None:
        errors, _risks = validate_images(
            Path("/nonexistent"),
            "![图 1](assets/a%00.png)\n",
            allow_whole_page=False,
        )
        self.assertTrue(
            any("forbidden NUL byte" in issue for issue in errors)
        )

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

    def test_tiny_and_single_color_images_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            Image.new("RGB", (1, 1), "white").save(assets / "tiny.png")
            Image.new("RGB", (32, 32), "white").save(assets / "blank.png")
            text = (
                "![图 1](assets/tiny.png)\n"
                "![图 2](assets/blank.png)\n"
            )
            errors, _risks = validate_images(paper, text, allow_whole_page=False)
            self.assertTrue(
                any("too small" in issue and "tiny.png" in issue for issue in errors)
            )
            self.assertTrue(
                any("one pixel color" in issue and "blank.png" in issue for issue in errors)
            )

    def test_fully_transparent_image_with_hidden_rgb_variation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
            image.putpixel((0, 0), (255, 0, 0, 0))
            image.save(assets / "transparent.png")
            errors, _risks = validate_images(
                paper,
                "![图 1](assets/transparent.png)",
                allow_whole_page=False,
            )
            self.assertTrue(
                any(
                    "too few visible pixels" in issue
                    and "transparent.png" in issue
                    for issue in errors
                )
            )

    def test_single_changed_pixel_is_not_a_useful_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            image = Image.new("RGB", (32, 32), "white")
            image.putpixel((0, 0), (0, 0, 0))
            image.save(assets / "one-pixel.png")
            errors, _risks = validate_images(
                paper,
                "![图 1](assets/one-pixel.png)",
                allow_whole_page=False,
            )
            self.assertTrue(
                any("too little visible variation" in issue for issue in errors)
            )

    def test_large_nearly_blank_image_requires_proportional_variation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            image = Image.new("RGB", (1024, 1024), "white")
            for index in range(64):
                image.putpixel((index, 0), (0, 0, 0))
            image.save(assets / "near-blank.png")
            errors, _risks = validate_images(
                paper,
                "![图 1](assets/near-blank.png)",
                allow_whole_page=False,
            )
            self.assertTrue(
                any(
                    "too little visible variation" in issue
                    and "near-blank.png" in issue
                    and "minimum=1049" in issue
                    for issue in errors
                )
            )

    def test_narrow_nonuniform_image_is_allowed_when_area_is_sufficient(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            save_nonuniform_image(assets / "narrow.png", size=(4, 80))
            errors, _risks = validate_images(
                paper, "![图 1](assets/narrow.png)", allow_whole_page=False
            )
            self.assertFalse(errors)

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

    def test_multiline_paragraph_image_is_not_guessed_as_caption_payload(
        self,
    ) -> None:
        source = "Figure 1: First\nFigure 2: Second"
        translation = (
            "**图 1：第一幅。**\n"
            "**图 2：第二幅。**\n"
            "![plain](assets/a.png)\n"
        )
        representations = validate_resources.formal_resource_representations(
            translation
        )
        self.assertNotIn(1, representations["figure"])
        self.assertNotIn(2, representations["figure"])
        _errors, risks = source_coverage_findings(
            source,
            translation,
            False,
        )
        self.assertTrue(any("Figure 1" in issue for issue in risks))
        self.assertTrue(any("Figure 2" in issue for issue in risks))

    def test_one_payload_cannot_serve_multiple_resource_owners(self) -> None:
        cases = (
            (
                "Figure 1: First\nFigure 2: Second",
                "**图 1：第一幅。**\n\n"
                "![plain](assets/a.png)\n\n"
                "**图 2：第二幅。**\n",
                (("figure", 1), ("figure", 2)),
            ),
            (
                "Table 1: First\nTable 2: Second",
                "**表 1：第一张。**\n\n"
                "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
                "**表 2：第二张。**\n",
                (("table", 1), ("table", 2)),
            ),
            (
                "Algorithm 1: First\nAlgorithm 2: Second",
                "**算法 1：第一个。**\n\n"
                "```text\nprobe first row\n```\n\n"
                "**算法 2：第二个。**\n",
                (("algorithm", 1), ("algorithm", 2)),
            ),
            (
                "Algorithm 1: First\nFigure 1: Second",
                "**算法 1：第一个。**\n\n"
                "```text\nprobe first row\n```\n\n"
                "**图 1：第二幅。**\n",
                (("algorithm", 1), ("figure", 1)),
            ),
        )
        for source, translation, owners in cases:
            with self.subTest(owners=owners):
                representations = (
                    validate_resources.formal_resource_representations(
                        translation
                    )
                )
                for kind, number in owners:
                    self.assertNotIn(number, representations[kind])
                _errors, risks = source_coverage_findings(
                    source,
                    translation,
                    False,
                )
                for kind, number in owners:
                    label = {
                        "figure": "Figure",
                        "table": "Table",
                        "algorithm": "Algorithm",
                    }[kind]
                    self.assertTrue(
                        any(f"{label} {number}" in issue for issue in risks)
                    )

    def test_receiptless_legacy_mode_replays_frozen_payload_pairing(
        self,
    ) -> None:
        source = "Figure 1: First\nFigure 2: Second\n"
        translation = (
            "**图 1：第一幅。**\n\n"
            "![plain](assets/shared.png)\n\n"
            "**图 2：第二幅。**\n"
        )
        _current_errors, current_risks = source_coverage_findings(
            source,
            translation,
            require_references=False,
        )
        self.assertTrue(any("Figure 1" in issue for issue in current_risks))
        self.assertTrue(any("Figure 2" in issue for issue in current_risks))

        legacy_errors, legacy_risks = source_coverage_findings(
            source,
            translation,
            require_references=False,
            legacy_resource_structure=True,
        )
        self.assertFalse(legacy_errors)
        self.assertFalse(
            any(
                "formal translation-side payload" in issue
                for issue in legacy_risks
            )
        )

    def test_legacy_resource_replay_cannot_disable_review_grade_citation_gate(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "cannot be combined with review-grade",
        ):
            source_coverage_findings(
                "REFERENCES\n[1] A. Smith, Paper, 2020.\n",
                "## 参考文献\n- [1] A. Smith, Paper, 2020.\n",
                require_references=True,
                require_inline_citations=True,
                legacy_resource_structure=True,
            )

    def test_code_backed_figure_is_a_formal_representation(self) -> None:
        source = "Figure 2: Email program"
        translation = "**图 2：邮件程序。**\n\n```python\nprint('mail')\n```\n"
        errors, risks = source_coverage_findings(source, translation, False)
        self.assertFalse(errors)
        self.assertFalse(any("formal translation-side payload" in issue for issue in risks))

    def test_empty_or_one_token_fence_is_not_a_formal_representation(self) -> None:
        source = "Algorithm 1: Parse a row"
        for translation in (
            "**算法 1：解析一行。**\n\n```text\n```\n",
            "```text\n```\n\n**算法 1：解析一行。**\n",
            "**算法 1：解析一行。**\n\n```text\nx\n```\n",
            "**算法 1：解析一行。**\n\n```text\nplaceholder\n```\n",
        ):
            with self.subTest(translation=translation):
                _errors, risks = source_coverage_findings(source, translation, False)
                self.assertTrue(
                    any(
                        "Algorithm 1" in issue
                        and "formal translation-side payload" in issue
                        for issue in risks
                    )
                )

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
            "**表 1：文法。**\n\n| A | Meaning |\n| --- | --- |\n| x | first |\n\n"
            "表 2 给出了结果。\n\n"
            "**表 2：结果。**\n\n| B | Meaning |\n| --- | --- |\n| y | second |\n"
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

    def test_table_literals_inside_code_blocks_are_not_formal_tables(
        self,
    ) -> None:
        translations = (
            (
                "```markdown\n"
                "**表 1：结果。**\n\n"
                "| A | B |\n"
                "| --- | --- |\n"
                "| 1 | 2 |\n"
                "```\n"
            ),
            (
                "    **表 1：结果。**\n"
                "\n"
                "    | A | B |\n"
                "    | --- | --- |\n"
                "    | 1 | 2 |\n"
            ),
            (
                "**表 1：结果。**\n"
                "\n"
                "    | A | B |\n"
                "    | --- | --- |\n"
                "    | 1 | 2 |\n"
            ),
        )
        for translation in translations:
            with self.subTest(translation=translation):
                representations = (
                    validate_resources.formal_resource_representations(
                        translation
                    )
                )
                self.assertNotIn(1, representations["table"])
                _errors, risks = source_coverage_findings(
                    "Table 1: Results\n",
                    translation,
                    require_references=False,
                )
                self.assertTrue(
                    any(
                        "Table 1" in issue
                        and "formal translation-side payload" in issue
                        for issue in risks
                    )
                )

    def test_markdown_table_requires_a_nonempty_data_row(self) -> None:
        source = "Table 1: Results"
        for translation in (
            "**表 1：结果。**\n\n| A | B |\n| --- | --- |\n",
            "**表 1：结果。**\n\n| A | B |\n| --- | --- |\n|   |   |\n",
            "**表 1：结果。**\n\n| A |\n| --- |\n| x |\n",
            "| A | B |\n| --- | --- |\n\n**表 1：结果。**\n",
        ):
            with self.subTest(translation=translation):
                _errors, risks = source_coverage_findings(source, translation, False)
                self.assertTrue(
                    any(
                        "Table 1" in issue
                        and "formal translation-side payload" in issue
                        for issue in risks
                    )
                )

    def test_gfm_table_without_outer_pipes_is_formal(self) -> None:
        source = "Table 2: Results"
        translation = (
            "**表 2：结果。**\n\n"
            "A | B\n"
            "--- | ---\n"
            "1 | 2\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            False,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("formal translation-side payload" in issue for issue in risks)
        )

    def test_escaped_pipe_inside_table_cell_is_not_a_column_separator(self) -> None:
        source = "Table 1: Algebra"
        translation = (
            "**表 1：代数。**\n\n"
            "| Operator | Equivalence |\n"
            "| --- | --- |\n"
            "| Join | `{LT} \\| {RT}` |\n"
        )
        errors, risks = source_coverage_findings(source, translation, False)
        self.assertFalse(errors)
        self.assertFalse(
            any("formal translation-side payload" in issue for issue in risks)
        )

    def test_unescaped_pipe_inside_table_cell_breaks_the_formal_table(self) -> None:
        source = "Table 1: Algebra"
        translation = (
            "**表 1：代数。**\n\n"
            "| Operator | Equivalence |\n"
            "| --- | --- |\n"
            "| Join | `{LT} | {RT}` |\n"
        )
        _errors, risks = source_coverage_findings(source, translation, False)
        self.assertTrue(
            any("formal translation-side payload" in issue for issue in risks)
        )

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

    def test_truncated_reference_page_range_is_an_error(self) -> None:
        source = (
            "REFERENCES\n"
            "[58] Sharov et al. Take me to your leader. 2015. 1490-1501.\n"
        )
        translation = (
            "## 参考文献\n\n"
            "- [58] Sharov et al. Take me to your leader. 2015. 1490-.\n"
        )
        errors, _risks = source_coverage_findings(source, translation, True)
        self.assertIn(
            "translation references have a truncated numeric range: 58",
            errors,
        )

    def test_whitespace_split_reference_url_is_an_error(self) -> None:
        source = (
            "REFERENCES\n"
            "[1] Example. https://example.com/product/widget.\n"
            "[2] Example. https://example.com/about-aws/new-release.\n"
        )
        translations = (
            "## 参考文献\n\n"
            "- [1] Example. https://example.com/product/ widget.\n"
            "- [2] Example. https://example.com/about- aws/new-release.\n",
            "## 参考文献\n\n"
            "- [1] Example. http://example. com/product/widget.\n"
            "- [2] Example. https://example.com/about-aws/new-release.\n",
        )
        for translation in translations:
            with self.subTest(translation=translation):
                errors, _risks = source_coverage_findings(
                    source, translation, True
                )
                self.assertTrue(
                    any("whitespace-split URL" in issue for issue in errors)
                )

    def test_complete_or_citation_terminated_reference_url_is_allowed(self) -> None:
        source = (
            "REFERENCES\n"
            "[1] Example. https://example.com/. 2020.\n"
            "[2] Example. https://example.com/deep/path/ accessed 2021.\n"
            "[3] Example. https://example.com/deep/path.\n"
        )
        translation = (
            "## 参考文献\n\n"
            "- [1] Example. https://example.com/ 2020.\n"
            "- [2] Example. https://example.com/deep/path/ accessed 2021.\n"
            "- [3] Example. <https://example.com/deep/path>. 2022.\n"
        )
        errors, _risks = source_coverage_findings(source, translation, True)
        self.assertFalse(
            any("whitespace-split URL" in issue for issue in errors)
        )

    def test_hidden_html_comments_cannot_satisfy_source_coverage(self) -> None:
        source = (
            "ABSTRACT\n"
            "Figure 1: Architecture\n"
            "Table 2: Results\n"
            "Algorithm 3: Probe\n"
            "1 INTRODUCTION\n"
            "2 CONCLUSION\n"
            "REFERENCES\n"
            "[1] First paper, 2020.\n"
        )
        translation = (
            "<!--\n"
            "## 摘要\n"
            "图 1：架构\n![图 1](assets/fake.png)\n"
            "表 2：结果\n| A | B |\n| --- | --- |\n| 1 | 2 |\n"
            "算法 3：探测\n```text\nprobe row\n```\n"
            "## 1 引言\n## 2 结论\n"
            "## 参考文献\n- [1] First paper, 2020.\n"
            "-->\n"
        )
        errors, risks = source_coverage_findings(source, translation, True)
        self.assertIn(
            "source has a References section but translation has no reference heading",
            errors,
        )
        for resource in ("Figure 1", "Table 2", "Algorithm 3"):
            self.assertTrue(
                any(resource in issue for issue in risks),
                resource,
            )
        self.assertTrue(any("Abstract heading" in issue for issue in risks))
        self.assertTrue(any("Conclusion/Summary" in issue for issue in risks))

    def test_raw_html_blocks_cannot_satisfy_resource_coverage(self) -> None:
        source = "Figure 1: Architecture\nTable 2: Results\n"
        translation = (
            "<!-- hidden --> ![图 1](assets/figure.png)\n"
            "<!-- hidden --> ![表 2](assets/table.png)\n"
        )
        _errors, coverage_risks = source_coverage_findings(
            source,
            translation,
            require_references=False,
        )
        for resource in ("Figure 1", "Table 2"):
            self.assertTrue(
                any(
                    resource in issue
                    and "formal translation-side payload" in issue
                    for issue in coverage_risks
                ),
                resource,
            )

        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            assets = paper / "assets"
            assets.mkdir()
            save_nonuniform_image(assets / "figure.png")
            save_nonuniform_image(assets / "table.png")
            errors, image_risks = validate_images(
                paper,
                translation,
                allow_whole_page=False,
            )
            self.assertFalse(errors)
            self.assertEqual(
                sum("orphan asset" in issue for issue in image_risks),
                2,
            )

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

    def test_clean_long_numeric_reference_series_needs_no_ocr_waiver(self) -> None:
        entries = [
            (str(index), f"Author, A. Database paper {index}. Journal.")
            for index in range(1, 11)
        ]
        normalized, risks = validate_resources._normalize_source_reference_ocr(
            entries
        )
        self.assertEqual(normalized, entries)
        self.assertEqual(risks, [])

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
        source = (
            "REFERENCES\n"
            "[BMG93] A. Author. A complete database systems citation, 1993.\n"
        )
        translation = (
            "## 参考文献\n\n"
            "- [BMG93] A. Author. A complete database systems citation, 1993.\n"
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

    def test_final_reference_stops_before_unrelated_next_page_appendix(self) -> None:
        source = (
            "REFERENCES\n"
            "[31] J. Lee and M. Grund. High-performance processing. 2013.\n"
            "\fAPPENDIX\n"
            + ("unrelated table and appendix material " * 200)
            + "\fADDITIONAL APPENDIX MATERIAL\n"
            + "1.19MB, a 41% reduction from the baseline.\n"
        )
        translation = (
            "## 参考文献\n"
            "- [31] J. Lee and M. Grund. High-performance processing. 2013.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("suspiciously short" in issue for issue in risks)
        )

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

    def test_bilingual_structural_headings_are_candidates(self) -> None:
        source = (
            "ABSTRACT\nText\n"
            "1 INTRODUCTION\nText\n"
            "2 CONCLUSIONS\nText\n"
        )
        for translation in (
            "## 摘要（Abstract）\n正文。\n## 2. 结论（Conclusions）\n正文。\n",
            "## Abstract (摘要)\nText.\n## 2 Conclusions (结论)\nText.\n",
        ):
            with self.subTest(translation=translation):
                _errors, risks = source_coverage_findings(source, translation, False)
                self.assertFalse(any("Abstract heading" in issue for issue in risks))
                self.assertFalse(
                    any("Conclusion/Summary" in issue for issue in risks)
                )

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

    def test_missing_inline_citations_are_review_candidates(self) -> None:
        source = (
            "INTRODUCTION\nPrior systems [1], [2] and later work [3] are relevant.\n"
            "REFERENCES\n"
            "[1] Alpha, A. First paper.\n"
            "[2] Beta, B. Second paper.\n"
            "[3] Gamma, C. Third paper.\n"
        )
        translation = (
            "## 引言\n已有系统 [1] 和后续工作 [3] 与此相关。\n"
            "## 参考文献\n"
            "- [1] Alpha, A. First paper.\n"
            "- [2] Beta, B. Second paper.\n"
            "- [3] Gamma, C. Third paper.\n"
        )
        _errors, risks = source_coverage_findings(
            source,
            translation,
            True,
            require_inline_citations=True,
        )
        self.assertIn(
            "source body citation identifiers have no translation-side candidate: 2",
            risks,
        )

    def test_citation_in_trailing_footnote_counts_but_bibliography_does_not(self) -> None:
        source = (
            "INTRODUCTION\nPrior systems [1] and the footnote source [2] matter.\n"
            "REFERENCES\n"
            "[1] Alpha, A. First paper, 2020.\n"
            "[2] Beta, B. Footnote paper, 2021.\n"
        )
        translation = (
            "## 引言\n已有系统 [1] 与脚注来源[^1] 都很重要。\n"
            "## 参考文献\n"
            "- [1] Alpha, A. First paper, 2020.\n"
            "- [2] Beta, B. Footnote paper, 2021.\n"
            "\n[^1]: 参见 [2]。\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("body citation identifiers" in issue for issue in risks)
        )

    def test_two_column_same_line_reference_cannot_escape_both_gates(self) -> None:
        source = (
            "INTRODUCTION\nPrior systems [1] and [2] are relevant.\n"
            "REFERENCES\n"
            "[1] Alpha, A. First paper, 2020.        "
            "[2] Beta, B. Second paper, 2021.\n"
        )
        translation = (
            "## 引言\n已有系统 [1] 与此相关。\n"
            "## 参考文献\n"
            "- [1] Alpha, A. First paper, 2020.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            True,
            require_inline_citations=True,
        )
        self.assertIn("missing numbered references: 2", errors)
        self.assertIn(
            "source body citation identifiers have no translation-side candidate: 2",
            risks,
        )

    def test_review_grade_parser_does_not_rebind_legacy_reference_evidence(self) -> None:
        source = (
            "INTRODUCTION\nPrior systems [1] and [2] are relevant.\n"
            "REFERENCES\n"
            "[1] Alpha, A. First paper, 2020.        "
            "[2] Beta, B. Second paper, 2021.\n"
        )
        translation = (
            "## 引言\n已有系统 [1] 与此相关。\n"
            "## 参考文献\n"
            "- [1] Alpha, A. First paper, 2020.\n"
        )
        legacy_errors, legacy_risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=False,
        )
        self.assertFalse(
            any("missing numbered references: 2" in issue for issue in legacy_errors)
        )
        self.assertFalse(
            any("body citation identifiers" in issue for issue in legacy_risks)
        )

        review_errors, review_risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertIn("missing numbered references: 2", review_errors)
        self.assertIn(
            "source body citation identifiers have no translation-side candidate: 2",
            review_risks,
        )

    def test_crowded_second_column_reference_is_parsed_without_spacing(self) -> None:
        source = (
            "INTRODUCTION\nPrior systems [1] and [29] are relevant.\n"
            "REFERENCES\n"
            "[1] A. Alpha, “First paper,” 2020. "
            "[29] D. Abadi, “Second-column paper,” 2021.\n"
        )
        translation = (
            "## 引言\n已有系统 [1] 和 [29] 与此相关。\n"
            "## 参考文献\n"
            "- [1] A. Alpha, “First paper,” 2020.\n"
            "- [29] D. Abadi, “Second-column paper,” 2021.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("entry-count candidate differs" in issue for issue in risks)
        )

    def test_crowded_corporate_reference_uses_bibliographic_cue(self) -> None:
        source = (
            "INTRODUCTION\nPrior systems [1] and [41] are relevant.\n"
            "REFERENCES\n"
            "[1] A. Alpha, “First paper with a deliberately long left-column "
            "venue description,” 2020. "
            "[41] Pig. Apache Pig. Retrieved in 2017 from http://pig.apache.org/\n"
        )
        translation = (
            "## 引言\n已有系统 [1] 和 [41] 与此相关。\n"
            "## 参考文献\n"
            "- [1] A. Alpha, “First paper,” 2020.\n"
            "- [41] Pig. Apache Pig. Retrieved in 2017 from http://pig.apache.org/\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("entry-count candidate differs" in issue for issue in risks)
        )

    def test_left_body_citation_is_not_a_crowded_corporate_reference(self) -> None:
        source = (
            "INTRODUCTION\nPrior systems [5] and [6] are relevant.\n"
            "REFERENCES\n"
            "[5] A. Alpha, “First paper,” 2020.\n"
            "Calcite compares prior work [6]              "
            "In Proceedings of the 2020 Conference.\n"
            "[6] B. Beta, “Second paper,” 2021.\n"
        )
        translation = (
            "## 引言\n已有系统 [5] 和 [6] 与此相关。\n"
            "## 参考文献\n"
            "- [5] A. Alpha, “First paper,” 2020.\n"
            "- [6] B. Beta, “Second paper,” 2021.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("duplicate reference identifier candidates" in issue for issue in risks)
        )

    def test_right_column_references_before_heading_are_recovered_not_citations(self) -> None:
        source = (
            "Prior work [1] is relevant.\n"
            "Summary text from the left column.                         "
            "[17] V. Leis, A. Gubichev, and T. Neumann, “First title,” 2015.\n"
            "More summary text from the left column.                    "
            "[18] B. Radke and A. Kemper, “Second title,” 2018.\n"
            "R E F E R E N C E S\n"
            "[1] A. Alpha, “Base paper,” 2010.\n"
        )
        translation = (
            "## 正文\n已有工作 [1] 与此相关。\n"
            "## 参考文献\n"
            "- [1] A. Alpha, “Base paper,” 2010.\n"
            "- [17] V. Leis, A. Gubichev, and T. Neumann, “First title,” 2015.\n"
            "- [18] B. Radke and A. Kemper, “Second title,” 2018.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("body citation identifiers" in issue for issue in risks)
        )
        self.assertFalse(
            any("entry-count candidate differs" in issue for issue in risks)
        )

    def test_preheading_hyphenated_diacritic_initial_is_recovered(self) -> None:
        source = (
            "Prior work [1] is relevant.\n"
            "Left-column conclusion text.                              "
            "[19] A. Lakshman and P. Malik. Cassandra. Journal, 2010.\n"
            "More left-column text.                                    "
            "[20] P.-A\u030a. Larson, E. Hanson, and S. Price. "
            "Columnar Storage. Journal, 2012.\n"
            "R E F E R E N C E S\n"
            "[1] A. Alpha, “Base paper,” 2010.\n"
        )
        translation = (
            "## 正文\n已有工作 [1] 与此相关。\n"
            "## 参考文献\n"
            "- [1] A. Alpha, “Base paper,” 2010.\n"
            "- [19] A. Lakshman and P. Malik. Cassandra. Journal, 2010.\n"
            "- [20] P.-A. Larson, E. Hanson, and S. Price. "
            "Columnar Storage. Journal, 2012.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("unmatched reference identifiers" in issue for issue in risks),
            risks,
        )
        self.assertFalse(
            any("entry-count candidate differs" in issue for issue in risks),
            risks,
        )

    def test_preheading_corporate_entries_fill_author_sequence_gaps(self) -> None:
        source = (
            "Prior work [1] is relevant.\n"
            "Left conclusion.                              "
            "[34] S. Melnik. Dremel. PVLDB, 2010.\n"
            "More conclusion.                             "
            "[35] Microsoft Analytics Platform System.\n"
            "More conclusion.                             "
            "[36] Microsoft Azure Blob Storage.\n"
            "More conclusion.                             "
            "[37] Microsoft Azure SQL DW.\n"
            "More conclusion.                             "
            "[38] G. Moerkotte. Small aggregates. VLDB, 1998.\n"
            "More conclusion.                             "
            "[39] MongoDB. mongodb.com.\n"
            "R E F E R E N C E S\n"
            "[1] A. Alpha, “Base paper,” 2010.\n"
            "                                                  "
            "[40] J. Mullin. Optimal semijoins. IEEE, 1990.\n"
        )
        translation = (
            "## 正文\n已有工作 [1] 与此相关。\n"
            "## 参考文献\n"
            "- [1] A. Alpha, “Base paper,” 2010.\n"
            "- [34] S. Melnik. Dremel. PVLDB, 2010.\n"
            "- [35] Microsoft Analytics Platform System.\n"
            "- [36] Microsoft Azure Blob Storage.\n"
            "- [37] Microsoft Azure SQL DW.\n"
            "- [38] G. Moerkotte. Small aggregates. VLDB, 1998.\n"
            "- [39] MongoDB. mongodb.com.\n"
            "- [40] J. Mullin. Optimal semijoins. IEEE, 1990.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("unmatched reference identifiers" in issue for issue in risks),
            risks,
        )
        self.assertFalse(
            any("entry-count candidate differs" in issue for issue in risks),
            risks,
        )

    def test_preheading_lowercase_web_reference_fills_numeric_gap(self) -> None:
        source = (
            "Prior work [8], [9], and [10] is relevant.\n"
            "Left conclusion.                              "
            "[8] A. Alpha. First paper. Journal, 2020.\n"
            "More conclusion.                             "
            "[9] Cloudera impala. http://example.com/, March 2013.\n"
            "More conclusion.                             "
            "[10] B. Beta. Second paper. Journal, 2021.\n"
            "R E F E R E N C E S\n"
            "[1] C. Gamma. Base paper. Journal, 2010.\n"
        )
        translation = (
            "## 正文\n已有工作 [8]、[9] 和 [10] 与此相关。\n"
            "## 参考文献\n"
            "- [1] C. Gamma. Base paper. Journal, 2010.\n"
            "- [8] A. Alpha. First paper. Journal, 2020.\n"
            "- [9] Cloudera impala. http://example.com/, March 2013.\n"
            "- [10] B. Beta. Second paper. Journal, 2021.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("unmatched reference identifiers" in issue for issue in risks),
            risks,
        )
        self.assertFalse(
            any("entry-count candidate differs" in issue for issue in risks),
            risks,
        )

    def test_preheading_right_column_author_keys_are_recovered_not_body_text(
        self,
    ) -> None:
        source = (
            "INTRODUCTION\n"
            "Prior systems [AHO74] and [KNUT73] are relevant.\n"
            "Left body text.                                  "
            "AHO74 AHO, A., AND ULLMAN, J. Algorithms, 1974.\n"
            "More left body text.                             "
            "KNUT73 KNUTH, D. Sorting and searching, 1973.\n"
            "REFERENCES\n"
            "BAYE72 BAYER, R., AND MCCREIGHT, C. Indexes, 1972.\n"
        )
        translation = (
            "## 正文\n这里省略了全部正文引用。\n"
            "## 参考文献\n"
            "- [AHO74] AHO, A., AND ULLMAN, J. Algorithms, 1974.\n"
            "- [KNUT73] KNUTH, D. Sorting and searching, 1973.\n"
            "- [BAYE72] BAYER, R., AND MCCREIGHT, C. Indexes, 1972.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertIn(
            "source body citation identifiers have no translation-side candidate: "
            "aho74, knut73",
            risks,
        )

    def test_preheading_author_keys_do_not_depend_on_column_32_or_digits(
        self,
    ) -> None:
        cases = (
            (
                "AHO74",
                "KNUT73",
                "AHO, A., AND ULLMAN, J. Algorithms.",
                "KNUTH, D. Sorting and searching.",
            ),
            (
                "CODD",
                "STONE",
                "CODD, E. Relational model.",
                "STONEBRAKER, M. Ingres.",
            ),
        )
        for first_key, second_key, first_entry, second_entry in cases:
            with self.subTest(first_key=first_key):
                source = (
                    "INTRODUCTION\n"
                    f"Prior systems [{first_key}] and [{second_key}] matter.\n"
                    + "left body".ljust(31)
                    + f"{first_key} {first_entry}\n"
                    + "more body".ljust(31)
                    + f"{second_key} {second_entry}\n"
                    + "REFERENCES\n"
                    + "[1] Smith, J. Base paper, 2020.\n"
                )
                translation = (
                    "## 正文\n这里省略了两个正文引用。\n"
                    "## 参考文献\n"
                    f"- [{first_key}] {first_entry}\n"
                    f"- [{second_key}] {second_entry}\n"
                    "- [1] Smith, J. Base paper, 2020.\n"
                )
                errors, risks = source_coverage_findings(
                    source,
                    translation,
                    require_references=True,
                    require_inline_citations=True,
                )
                self.assertFalse(errors)
                self.assertTrue(
                    any(
                        first_key.casefold() in issue
                        and second_key.casefold() in issue
                        and "body citation identifiers" in issue
                        for issue in risks
                    )
                )

    def test_preheading_author_keys_do_not_require_same_line_year_or_venue(
        self,
    ) -> None:
        source = (
            "INTRODUCTION\n"
            "Prior systems [AHO74] and [KNUT73] are relevant.\n"
            "Left body text.                                  "
            "AHO74 AHO, A., AND ULLMAN, J. Algorithms.\n"
            "Continuation of left body.                       "
            "Journal of Computing, 1974.\n"
            "More left body text.                             "
            "KNUT73 KNUTH, D. Sorting and searching.\n"
            "Another left continuation.                      "
            "Addison-Wesley.\n"
            "REFERENCES\n"
            "BAYE72 BAYER, R., AND MCCREIGHT, C. Indexes, 1972.\n"
        )
        translation = (
            "## 正文\n这里省略了全部正文引用。\n"
            "## 参考文献\n"
            "- [AHO74] AHO, A., AND ULLMAN, J. Algorithms. "
            "Journal of Computing, 1974.\n"
            "- [KNUT73] KNUTH, D. Sorting and searching. Addison-Wesley.\n"
            "- [BAYE72] BAYER, R., AND MCCREIGHT, C. Indexes, 1972.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertIn(
            "source body citation identifiers have no translation-side candidate: "
            "aho74, knut73",
            risks,
        )

    def test_letter_spaced_two_column_reference_heading_is_selected(self) -> None:
        source = (
            "INTRODUCTION\nPrior systems [1], [2] are relevant.\n"
            "R EFERENCES                                      right-column text\n"
            "[1] Alpha, A. First paper.\n"
            "[2] Beta, B. Second paper.\n"
        )
        translation = (
            "## 引言\n已有系统 [1] 与此相关。\n"
            "## 参考文献\n"
            "- [1] Alpha, A. First paper.\n"
            "- [2] Beta, B. Second paper.\n"
        )
        _errors, risks = source_coverage_findings(
            source,
            translation,
            True,
            require_inline_citations=True,
        )
        self.assertIn(
            "source body citation identifiers have no translation-side candidate: 2",
            risks,
        )

    def test_cited_general_references_recovers_ordered_ocr_identifiers(
        self,
    ) -> None:
        source_markers = (
            "<l>",
            "<2>",
            "<3>",
            "<4>",
            "<5>",
            "<6>",
            "<7>",
            "<8>",
            "CS>",
            "<lO>",
            "(11)",
            "(12)",
            "<13>",
            "(19)",
        )
        source_entries: list[str] = []
        for index, marker in enumerate(source_markers, start=1):
            source_entries.append(
                f"{marker} Surname{index}, A. Database paper. Journal, 19{index:02d}."
            )
            if index == 6:
                source_entries.append(
                    "Traiger,          1.1.        Views, operators, and database systems."
                )
            elif index == 14:
                source_entries.append(
                    "AFIPS             1975        NCC, proceedings of the conference."
                )
        source = (
            "INTRODUCTION\n"
            "Prior work <l>, <2>, <3>, <4>, <5>, <6>, <7>, <a>, <9>, "
            "<lo>, <11>, <12>, <13>, and <14> is relevant.\n"
            "level 3 subquery           references          a level 1 value\n"
            "left-column conclusion                    "
            "Cited and General References\n"
            + "\n".join(source_entries)
            + "\n"
        )
        translation = (
            "## 正文\n"
            + "、".join(f"[{index}]" for index in range(1, 15))
            + " 与本文相关。\n"
            "## 参考文献\n"
            + "\n".join(
                f"- [{index}] Surname{index}, A. Database paper. Journal, 19{index:02d}."
                for index in range(1, 15)
            )
            + "\n"
        )
        heading, _section, _body = (
            validate_resources._review_source_reference_parts(source)
        )
        self.assertIsNotNone(heading)
        assert heading is not None
        self.assertEqual(
            heading.group("heading"),
            "Cited and General References",
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertIn(
            "source reference identifiers were normalized by complete "
            "ordered delimiter-OCR evidence: l->1, cs->9, lo->10, 19->14",
            risks,
        )
        self.assertFalse(
            any(
                phrase in issue
                for issue in risks
                for phrase in (
                    "entry-count candidate differs",
                    "unmatched reference identifiers",
                    "body citation identifiers",
                )
            )
        )

    def test_complete_two_column_delimiter_ocr_series_is_recovered(
        self,
    ) -> None:
        damaged = {
            1: "[II",
            2: "PI",
            3: "r31",
            4: "[41",
            5: "151",
            6: "VI",
            7: "171",
            8: "PI",
            9: "PI",
            10: "[IO]",
            11: "[ll]",
            16: "Ml",
            17: "II71",
            18: "WI",
            19: "[I91",
            20: "PO1",
            21: "WI",
            27: "1271",
            32: "1321",
            39: "(391",
            41: "[4l]",
            42: "1421",
            46: "1461",
            50: "[SO]",
            51: "[Sl]",
            52: "[.52]",
            58: "I.581",
        }

        def entry(index: int) -> str:
            marker = damaged.get(index, f"[{index}]")
            return (
                f"{marker} Surname, A. Database paper {index}. "
                f"Journal, 19{index:02d}."
            )

        lines = [entry(index) for index in range(1, 23)]
        for offset in range(20):
            left_index = 23 + offset
            right_index = 43 + offset
            left = entry(left_index) if left_index <= 42 else ""
            right = entry(right_index) if right_index <= 61 else ""
            lines.append(f"{left:<80}{right}")

        entries = validate_resources._reference_entries("\n".join(lines))
        normalized, risks = (
            validate_resources._normalize_source_reference_ocr(entries)
        )
        self.assertEqual(len(entries), 61)
        self.assertEqual(
            {identifier for identifier, _body in normalized},
            {str(index) for index in range(1, 62)},
        )
        self.assertTrue(
            any("complete ordered delimiter-OCR evidence" in issue for issue in risks)
        )

    def test_parenthesized_roman_list_item_is_not_reference_entry(self) -> None:
        source = (
            "5. CONCLUSIONS                                  6. REFERENCES\n"
            "Compilation benefits from (i) SIMD alignment,\n"
            "(ii) avoiding branch mispredictions and (iii) parallel access.\n"
            "                                                   "
            "[1] Alpha, A. Database paper. Journal, 2010.\n"
            "                                                   "
            "(2) Beta, B. Query paper. Conference, 2011.\n"
        )
        translation = (
            "## 结论\n"
            "编译受益于（i）SIMD 对齐、（ii）避免分支预测错误以及"
            "（iii）并行访问。\n"
            "## 参考文献\n"
            "- [1] Alpha, A. Database paper. Journal, 2010.\n"
            "- [2] Beta, B. Query paper. Conference, 2011.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=False,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("ii" in issue.casefold() for issue in risks),
            risks,
        )
        self.assertFalse(
            any("entry-count candidate differs" in issue for issue in risks),
            risks,
        )

    def test_parenthesized_plan_nodes_do_not_split_reference_entries(
        self,
    ) -> None:
        entries = validate_resources._reference_entries(
            "[1] Alpha, A. Database paper. Journal, 2010.        (14) S\n"
            "(11) sigma                                        "
            "[2] Beta, B. Query paper. Conference, 2011.\n"
            "(6) R                                             "
            "[3] Gamma, C. Storage paper. Journal, 2012.\n"
        )
        self.assertEqual(
            [identifier for identifier, _body in entries],
            ["1", "2", "3"],
        )

    def test_parenthesized_year_is_reference_continuation_not_entry(
        self,
    ) -> None:
        entries = validate_resources._reference_entries(
            "[1] Alpha, A. Adaptive query execution.\n"
            "(1999) Proceedings of the database conference.\n"
            "[2] Beta, B. Streaming query processing.\n"
            "(2002) Proceedings of the systems conference.\n"
        )
        self.assertEqual(
            [identifier for identifier, _body in entries],
            ["1", "2"],
        )

    def test_lowercase_references_in_body_is_not_a_heading(self) -> None:
        source = (
            "The level 3 subquery           references          a level 1 value.\n"
            "No bibliography follows this sentence.\n"
        )
        heading, section, body = (
            validate_resources._review_source_reference_parts(source)
        )
        self.assertIsNone(heading)
        self.assertEqual(section, "")
        self.assertEqual(body, source)

    def test_right_column_heading_and_author_key_entries_outrank_toc(self) -> None:
        source = (
            "CONTENTS\n"
            "REFERENCES                                      body column\n"
            "Introduction text.\n"
            "[KNUT73] provides a survey of the basics.\n"
            "Summary text.                                  REFERENCES\n"
            "more left text                                 "
            "AHO74        AHO, A., AND ULLMAN, J. Algorithms, 1974.\n"
            "BAYE72       BAYER, R., AND MCCREIGHT, C. Indexes, 1972.    "
            "KNUT73       KNUTH, D. Sorting and searching, 1973.\n"
        )
        translation = (
            "## 正文\n[KNUT73] 对基础知识做了综述。\n"
            "## 参考文献\n"
            "- [AHO74] AHO, A., AND ULLMAN, J. Algorithms, 1974.\n"
            "- [BAYE72] BAYER, R., AND MCCREIGHT, C. Indexes, 1972.\n"
            "- [KNUT73] KNUTH, D. Sorting and searching, 1973.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertFalse(
            any("unmatched reference identifiers" in issue for issue in risks)
        )
        self.assertFalse(
            any("entry-count candidate differs" in issue for issue in risks)
        )

    def test_left_column_body_on_reference_heading_line_remains_citation_evidence(
        self,
    ) -> None:
        source = (
            "INTRODUCTION\n"
            "A database claim is supported here [1].                  REFERENCES\n"
            "[1] A. Smith, “Database paper,” Journal 7, 2020.\n"
        )
        translation = (
            "## 引言\n这里省略了正文引用。\n"
            "## 参考文献\n"
            "- [1] A. Smith, “Database paper,” Journal 7, 2020.\n"
        )
        errors, risks = source_coverage_findings(
            source,
            translation,
            require_references=True,
            require_inline_citations=True,
        )
        self.assertFalse(errors)
        self.assertIn(
            "source body citation identifiers have no translation-side candidate: 1",
            risks,
        )

    def test_author_conjunction_continuation_is_not_an_author_key_entry(
        self,
    ) -> None:
        entries = validate_resources._reference_entries(
            "BAYE72 BAYER, R., AND MCCREIGHT, C. Indexes, 1972.\n"
            "A., AND SNYDER, L. More bibliographic details.\n"
        )
        self.assertEqual([identifier for identifier, _body in entries], ["baye72"])

    def test_author_key_body_is_not_reparsed_as_damaged_marker(self) -> None:
        entries = validate_resources._reference_entries(
            "KARL76    KARLTON, P. Balanced trees.         "
            "WIRT76    WIRTH, N. Algorithms and data structures.\n"
        )
        self.assertEqual(
            [identifier for identifier, _body in entries],
            ["karl76", "wirt76"],
        )

    def test_dotted_coauthor_initials_do_not_split_numeric_reference(self) -> None:
        entries = validate_resources._reference_entries(
            "[i]    K.P. Eswaran,     J.N. Gray,        R.A. Lorie, "
            "I.L. Traiger, On the Notions of Consistency and Predicate Locks, "
            "Technical Report RJ1487, 1974.\n"
            "[2] Information Management System Virtual Storage. IBM, 1975.\n"
            "[3] UNIVAC Data Management System. Sperry Rand, 1973.\n"
        )
        normalized, risks = validate_resources._normalize_source_reference_ocr(
            entries
        )
        self.assertEqual(
            [identifier for identifier, _body in normalized],
            ["1", "2", "3"],
        )
        self.assertEqual(len(risks), 1)

    def test_inline_citation_ranges_are_expanded(self) -> None:
        source = (
            "INTRODUCTION\nPrior systems [1]-[3] are relevant.\n"
            "REFERENCES\n"
            "[1] Alpha, A. First paper.\n"
            "[2] Beta, B. Second paper.\n"
            "[3] Gamma, C. Third paper.\n"
        )
        translation = (
            "## 引言\n已有系统 [1] 与 [3] 相关。\n"
            "## 参考文献\n"
            "- [1] Alpha, A. First paper.\n"
            "- [2] Beta, B. Second paper.\n"
            "- [3] Gamma, C. Third paper.\n"
        )
        _errors, risks = source_coverage_findings(
            source,
            translation,
            True,
            require_inline_citations=True,
        )
        self.assertIn(
            "source body citation identifiers have no translation-side candidate: 2",
            risks,
        )

    def test_mixed_inline_citation_groups_expand_each_item(self) -> None:
        reference_ids = {str(value) for value in range(1, 8)}
        cases = {
            "[1, 3-5]": {"1", "3", "4", "5"},
            "[1,2,5–7]": {"1", "2", "5", "6", "7"},
            "[1; 3—5]": {"1", "3", "4", "5"},
            "[1-3, 5]": {"1", "2", "3", "5"},
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(
                    validate_resources._citation_identifiers(
                        text,
                        reference_ids,
                    ),
                    expected,
                )

    def test_author_key_citation_groups_expand_each_item(self) -> None:
        reference_ids = {"aho74", "knut73", "baye72"}
        for text in ("[AHO74, KNUT73]", "[AHO74; KNUT73]"):
            with self.subTest(text=text):
                self.assertEqual(
                    validate_resources._citation_identifiers(
                        text,
                        reference_ids,
                    ),
                    {"aho74", "knut73"},
                )

    def test_reference_entries_are_not_body_citations(self) -> None:
        source = (
            "INTRODUCTION\nNo inline citations here.\n"
            "REFERENCES\n"
            "[1] Alpha, A. First paper, 2020.\n"
        )
        translation = (
            "## 引言\n这里没有正文引用。\n"
            "## 参考文献\n"
            "- [1] Alpha, A. First paper, 2020.\n"
        )
        _errors, risks = source_coverage_findings(
            source,
            translation,
            True,
            require_inline_citations=True,
        )
        self.assertFalse(
            any("body citation identifiers" in issue for issue in risks)
        )

    def test_inline_citation_gate_is_opt_in(self) -> None:
        source = (
            "INTRODUCTION\nPrior systems [1] are relevant.\n"
            "REFERENCES\n"
            "[1] Alpha, A. First paper.\n"
        )
        translation = (
            "## 引言\n已有系统与此相关。\n"
            "## 参考文献\n"
            "- [1] Alpha, A. First paper.\n"
        )
        _errors, risks = source_coverage_findings(source, translation, True)
        self.assertFalse(
            any("body citation identifiers" in issue for issue in risks)
        )

    def test_cli_reports_ambiguous_reference_evidence_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paper = Path(temporary)
            (paper / "translation.md").write_text("## 参考文献\n", encoding="utf-8")
            source = paper / "source.txt"
            source.write_text("REFERENCES\n", encoding="utf-8")
            output = io.StringIO()
            with (
                mock.patch.object(
                    validate_resources,
                    "validate_paper",
                    side_effect=ValueError("multiple candidates"),
                ),
                mock.patch.object(
                    sys,
                    "argv",
                    ["validate_resources.py", str(paper), str(source)],
                ),
                contextlib.redirect_stdout(output),
            ):
                return_code = validate_resources.main()
            self.assertEqual(return_code, 2)
            self.assertIn(
                "ERROR: reference-section evidence is ambiguous: multiple candidates",
                output.getvalue(),
            )
            self.assertNotIn("Traceback", output.getvalue())

    def test_review_heading_scan_handles_extreme_layout_padding(self) -> None:
        source = (
            "Body text before the bibliography.\n"
            + "left column text"
            + (" " * 1043)
            + "REFERENCES\n"
            + "[1] Smith, J. A real database paper. Journal, 2020.\n"
            + "[2] Jones, A. Another database paper. Conference, 2021.\n"
        )
        heading, section, body = validate_resources._review_source_reference_parts(
            source
        )
        self.assertIsNotNone(heading)
        self.assertIn("[1] Smith", section)
        self.assertIn("Body text before", body)

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
            save_nonuniform_image(assets / "qa.png")

            errors, risks = validate_images(paper, "", allow_whole_page=False)
            self.assertFalse(errors)
            self.assertFalse(any("qa.png" in issue for issue in risks))

            errors, _risks = validate_images(
                paper, "![图 1](assets/qa.png)", allow_whole_page=False
            )
            self.assertTrue(any("git-ignored asset" in issue for issue in errors))


if __name__ == "__main__":
    unittest.main()
