from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_listings import listing_findings, listing_issues  # noqa: E402


class ListingValidationTests(unittest.TestCase):
    def test_page_start_form_feed_caption_is_detected(self) -> None:
        errors, _risks = listing_findings(
            "\fListing 4: Probe a row\nint probe() { return 1; }\n",
            "正文没有清单。\n",
        )
        self.assertIn("Listing 4 has no labeled fenced payload", errors)

    def setUp(self) -> None:
        fixtures = ROOT / "tests/fixtures/listings"
        self.source = (fixtures / "source-listing.txt").read_text(encoding="utf-8")

    def test_complete_listing_payload_passes(self) -> None:
        translation = (ROOT / "tests/fixtures/listings/translation-complete.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(listing_issues(self.source, translation), [])

    def test_adjacent_placeholder_block_is_not_accepted(self) -> None:
        translation = (ROOT / "tests/fixtures/listings/translation-placeholder.md").read_text(
            encoding="utf-8"
        )
        issues = listing_issues(self.source, translation)
        self.assertTrue(any("suspiciously short" in issue or "key-token overlap" in issue for issue in issues))
        errors, risks = listing_findings(self.source, translation)
        self.assertEqual(errors, [])
        self.assertTrue(risks)

    def test_caption_without_fenced_payload_fails(self) -> None:
        issues = listing_issues(self.source, "**清单 1：探测。**\n\n只有过程摘要。\n")
        self.assertIn("Listing 1 has no labeled fenced payload", issues)
        errors, risks = listing_findings(
            self.source, "**清单 1：探测。**\n\n只有过程摘要。\n"
        )
        self.assertTrue(errors)
        self.assertEqual(risks, [])

    def test_hidden_html_comment_cannot_supply_listing_payload(self) -> None:
        translation = (
            "<!--\n"
            "**清单 1：探测。**\n\n"
            "```sql\nSELECT key FROM table WHERE value > 1;\n```\n"
            "-->\n"
        )
        errors, _risks = listing_findings(self.source, translation)
        self.assertIn("Listing 1 has no labeled fenced payload", errors)

    def test_unrelated_same_language_listing_is_a_review_risk(self) -> None:
        source = (
            "SELECT customer_id, order_total FROM customer_orders "
            "WHERE order_total > 100;\n\n"
            "Listing 1: High-value customer orders\n"
        )
        translation = (
            "**清单 1：高价值客户订单。**\n\n"
            "```sql\nSELECT x, y FROM unrelated_rows WHERE y > 1;\n```\n"
        )
        errors, risks = listing_findings(source, translation)
        self.assertEqual(errors, [])
        self.assertTrue(any("distinctive-identifier overlap" in issue for issue in risks))

    def test_listing_code_and_screenshot_are_duplicate_representations(self) -> None:
        translation = (
            (ROOT / "tests/fixtures/listings/translation-complete.md").read_text(encoding="utf-8")
            + "\n![清单 1](assets/listing-01.png)\n"
        )
        errors, _risks = listing_findings(self.source, translation)
        self.assertIn("Listing 1 has 2 formal representations", errors)

    def test_two_column_layout_caption_after_long_spacing_is_detected(self) -> None:
        source = "left-column text" + (" " * 4000) + "Listing 1: Probe rows\n"
        errors, _risks = listing_findings(source, "正文没有清单。\n")
        self.assertIn("Listing 1 has no labeled fenced payload", errors)


if __name__ == "__main__":
    unittest.main()
