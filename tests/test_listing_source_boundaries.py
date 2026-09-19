from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_listings import listing_findings, source_listing_evidence, source_listing_windows  # noqa: E402


def columns(left: list[str], right: list[str]) -> str:
    count = max(len(left), len(right))
    left = left + [""] * (count - len(left))
    right = right + [""] * (count - len(right))
    return "\n".join(a.ljust(80) + b for a, b in zip(left, right))


class ListingSourceBoundaryTests(unittest.TestCase):
    def test_top_caption_excludes_surrounding_prose_and_next_listing(self) -> None:
        source = (
            "The SELECT operator uses customer histories; unrelated prose.\n\n"
            "Listing 1: A wrapped description\ncontinued on another line.\n"
            "CREATE TABLE alpha (quantity INT);\n"
            "SELECT quantity FROM alpha WHERE quantity > 17;\n\n"
            "The optimizer may return values from unrelated histories; see below.\n"
            "Listing 2: Another example\nSELECT value FROM beta WHERE value > 99;\n"
        )
        windows = source_listing_windows(source)
        self.assertEqual(windows[1], "CREATE TABLE alpha (quantity INT);\n"
                         "SELECT quantity FROM alpha WHERE quantity > 17;")
        self.assertEqual(windows[2], "SELECT value FROM beta WHERE value > 99;")

    def test_neighboring_top_caption_does_not_reuse_previous_payload(self) -> None:
        windows = source_listing_windows(
            "Listing 1: First\nSELECT amount FROM first_table;\n"
            "Listing 2: Second caption\nwrapped description.\n"
            "SELECT price FROM second_table;\n"
        )
        self.assertEqual(windows[2], "SELECT price FROM second_table;")

    def test_bottom_caption_keeps_numbered_wraps_and_blank_numbered_lines(self) -> None:
        windows = source_listing_windows(
            "1 Table accounts, columns = [account_id,\n"
            "      account_balance]\n2\n3 SELECT account_id FROM accounts;\n\n"
            "Listing 1: Example prompt\n\n"
            "1 SELECT other_value FROM another_table;\n\n"
            "Listing 2: Another prompt\n"
        )
        self.assertEqual(windows[1], "Table accounts, columns = [account_id,\n"
                         "      account_balance]\n\nSELECT account_id FROM accounts;")
        self.assertEqual(windows[2], "SELECT other_value FROM another_table;")

    def test_top_numbered_payload_does_not_swallow_indented_prose(self) -> None:
        windows = source_listing_windows(
            "Listing 1: A loop\n1 for (int i = 0; i < 17; ++i) {\n2\n"
            "3   output[i] = input[i];\n4 }\n\n"
            "    The loop above returns data from the input; it is discussed here.\n"
        )
        self.assertNotIn("discussed", windows[1])
        self.assertIn("output[i]", windows[1])

    def test_two_columns_do_not_mix_distinct_listings_or_prose(self) -> None:
        prose = ["This paragraph describes unrelated data from another system."] * 6
        source = columns(
            prose + ["Listing 1: Left query", "SELECT alpha FROM left_table;", ""],
            prose + ["Listing 2: Right query", "SELECT beta FROM right_table;", ""],
        )
        windows = source_listing_windows(source)
        self.assertEqual(windows[1], "SELECT alpha FROM left_table;")
        self.assertEqual(windows[2], "SELECT beta FROM right_table;")

    def test_page_boundary_does_not_supply_previous_page_code(self) -> None:
        windows = source_listing_windows("SELECT alpha FROM first_table;\fListing 1: Empty\n")
        self.assertEqual(windows[1], "")

    def test_empty_boundary_stays_an_explicit_review_risk(self) -> None:
        errors, risks = listing_findings(
            "Listing 1: Source payload is not extractable\n",
            "清单 1：示例\n\n```sql\nSELECT quantity FROM accounts;\n```\n",
        )
        self.assertEqual(errors, [])
        self.assertTrue(any("boundary could not be identified" in risk for risk in risks))

    def test_prose_reference_does_not_erase_formal_payload(self) -> None:
        windows = source_listing_windows(
            "Listing 1: Query\nSELECT balance FROM accounts;\n\n"
            "Listing 1. The optimizer produces the wrong result.\n"
            "This paragraph explains why.\n"
        )
        self.assertEqual(windows[1], "SELECT balance FROM accounts;")

    def test_xml_and_bare_last_sql_line_work_with_bottom_captions(self) -> None:
        windows = source_listing_windows(
            '<query>\n  <column id="17" />\n</query>\n\n'
            'Listing 1: XML message\n\n'
            'SELECT account_id\nFROM accounts\nGROUP BY\n  account_id\n\n'
            'Listing 2: SQL query\n'
        )
        self.assertIn('<column id="17" />', windows[1])
        self.assertEqual(windows[2], 'SELECT account_id\nFROM accounts\nGROUP BY\n  account_id')

    def test_unindented_sql_clauses_stay_inside_payload(self) -> None:
        code = (
            "SELECT customer_id FROM accounts\n"
            "JOIN balances\nON accounts.customer_id = balances.customer_id\n"
            "WHERE active = true\nAND balance > 9999\n"
            "OR region = 'west'\nORDER BY customer_id;"
        )
        self.assertEqual(source_listing_windows("Listing 1: Query\n" + code)[1], code)

    def test_sql_keywords_accept_mixed_case_without_truncating(self) -> None:
        code = (
            "SELECT customer_id FROM accounts\n"
            "where active = true\nand balance > 9999\n"
            "Or region = 'west'\nORDER BY customer_id;"
        )
        self.assertEqual(source_listing_windows("Listing 1: Query\n" + code)[1], code)

    def test_clause_words_in_prose_cannot_select_a_source_payload(self) -> None:
        source = (
            "Other aggregate functions are useful.\n"
            "and the optimizer transforms them.\n"
            "from this we derive the following example.\n\n"
            "Listing 1: An aggregate query\n"
            "for composable aggregate functions.\n"
            "SELECT SUM(amount) FROM accounts;\n"
        )
        self.assertEqual(source_listing_windows(source)[1], "SELECT SUM(amount) FROM accounts;")

    def test_bottom_caption_wrap_and_body_cannot_replace_numbered_code(self) -> None:
        for tail in (
            "from both storage optimizations such as file clustering, as\nwell as runtime optimization.",
            "from parent stream RDDs, which themselves could source\nevents from an external queue.",
        ):
            with self.subTest(tail=tail):
                source = (
                    "1 CREATE TABLE records (id INT,\n2   amount INT);\n\n"
                    "Listing 1: A table declaration\n" + tail
                )
                self.assertEqual(source_listing_windows(source)[1],
                                 "CREATE TABLE records (id INT,\namount INT);")

    def test_cross_page_continuation_is_explicitly_partial(self) -> None:
        source = (
            "Listing 1: Query\nCREATE TABLE accounts (balance INT);\n"
            "INSERT INTO accounts VALUES (17);\n\nPublication footer.\f"
            "12 Author Name\n\nSELECT balance FROM accounts;\n\nDiscussion follows."
        )
        windows, partial = source_listing_evidence(source)
        self.assertEqual(partial, {1})
        self.assertNotIn("SELECT", windows[1])
        errors, risks = listing_findings(
            source, "清单 1：查询\n\n```sql\n" + windows[1] + "\n```"
        )
        self.assertEqual(errors, [])
        self.assertTrue(any("page/column boundary" in risk for risk in risks))

    def test_partial_boundary_does_not_relax_missing_translation_payload(self) -> None:
        source = (
            "Listing 1: Query\nCREATE TABLE accounts (balance INT);\f"
            "SELECT balance FROM accounts;\n"
        )
        errors, _risks = listing_findings(source, "正文没有清单。")
        self.assertIn("Listing 1 has no labeled fenced payload", errors)

    def test_numbered_cpp_continuation_is_partial(self) -> None:
        source = (
            "Listing 1: A class\n1 class Sum {\n2 public:\n3 Sum()\f"
            "4 {}\n5 int size() { return 17; }\n6 };\n"
        )
        self.assertEqual(source_listing_evidence(source)[1], {1})

    def test_next_page_code_with_its_own_bottom_caption_is_not_continuation(self) -> None:
        source = (
            "Listing 1: First query\nSELECT balance FROM accounts;\f"
            "SELECT price FROM products;\n\nListing 2: Independent query\n"
        )
        windows, partial = source_listing_evidence(source)
        self.assertEqual(partial, set())
        self.assertIn("products", windows[2])

    def test_page_header_is_not_continuation_evidence(self) -> None:
        source = (
            "Listing 1: Query\nSELECT balance FROM accounts;\f"
            "12 Author Name\n\nThis page discusses the results."
        )
        self.assertEqual(source_listing_evidence(source)[1], set())

    def test_real_omission_still_warns_without_neighbor_contamination(self) -> None:
        source = (
            "Listing 1: A substantial query\n"
            "SELECT customer_id, customer_name, order_amount FROM customer_orders\n"
            "    WHERE order_amount > 500 AND customer_region = 'west';\n"
        )
        errors, risks = listing_findings(
            source, "清单 1：查询\n\n```sql\nSELECT x, y FROM unrelated_table;\n```\n"
        )
        self.assertEqual(errors, [])
        self.assertTrue(any("distinctive-identifier overlap" in risk for risk in risks))
        self.assertTrue(any("no literals" in risk for risk in risks))


if __name__ == "__main__":
    unittest.main()
