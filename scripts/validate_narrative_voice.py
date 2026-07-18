#!/usr/bin/env python3
"""Reject ambiguous bare-author narration in Chinese paper translations."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from markdown_visibility import reader_visible_markdown


AUTHOR_METADATA = re.compile(r"^(?:[-*]\s*)?(?:\*\*)?作者(?:单位|贡献)?[:：]")
QUALIFIED_AUTHOR = re.compile(
    r"(?:本文|该文|原|第一|第二|第三|通信|通讯|共同|部分|其他|一些|每个|多位|几位|"
    r"数据源|扩展|演示|所有者或)作者|(?:合|创|工)作者|的作者|作者版本"
)


def find_ambiguous_author_narration(text: str) -> list[tuple[int, str]]:
    text = reader_visible_markdown(text)
    findings: list[tuple[int, str]] = []
    in_fence = False
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or line.startswith("#") or AUTHOR_METADATA.match(line.strip()):
            continue
        unqualified = QUALIFIED_AUTHOR.sub("", line)
        if "作者" in unqualified:
            findings.append((line_number, line.strip()))
    return findings


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_narrative_voice.py TRANSLATION", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        findings = find_ambiguous_author_narration(path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not findings:
        return 0
    for line_number, line in findings:
        print(f"line {line_number}: {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
