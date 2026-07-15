from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_narrative_voice import find_ambiguous_author_narration  # noqa: E402


class NarrativeVoiceValidationTests(unittest.TestCase):
    def test_bare_author_research_narration_is_rejected(self) -> None:
        text = (
            "作者提出一种方法。\n"
            "据作者所知，这是首次实现。\n"
            "作者在测试中使用该配置。\n"
            "在作者实现中，该配置更快。\n"
            "因此作者改用另一种方法。\n"
        )
        self.assertEqual(
            [item[0] for item in find_ambiguous_author_narration(text)],
            [1, 2, 3, 4, 5],
        )

    def test_qualified_third_party_and_explicit_current_authors_are_allowed(self) -> None:
        text = (
            "该文作者提出另一种方法。\n"
            "本文作者感谢匿名审稿人。\n"
            "其他作者也提出过类似看法。\n"
            "该系统由多位作者共同开发。\n"
            "每个作者都对应一条数据记录。\n"
            "数据源作者需要暴露所有类型。\n"
            "内容创作者可以查看报表。\n"
            "数字众包工作者可以处理任务。\n"
            "这是论文的作者数量。\n"
            "原文声明作者版本不可再分发。\n"
        )
        self.assertEqual(find_ambiguous_author_narration(text), [])

    def test_metadata_headings_and_code_fences_are_ignored(self) -> None:
        text = "## 作者\n作者：Alice\n作者单位：Example University\n```text\n作者提出\n```\n"
        self.assertEqual(find_ambiguous_author_narration(text), [])


if __name__ == "__main__":
    unittest.main()
