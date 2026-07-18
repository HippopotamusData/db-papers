#!/usr/bin/env python3
"""Normalize reader-visible translation headers without touching article prose."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

from markdown_visibility import reader_visible_markdown


ROOT = Path(__file__).resolve().parents[1]
TRANSLATOR_NOTE = (
    "本文依据同目录的 `source.pdf` 翻译。"
    "章节、图表、公式、算法、代码与参考文献按原文结构保留。"
)
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def load_mapping(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return value


def prose_line_indices(lines: list[str]) -> list[int]:
    """Return line indexes outside CommonMark fenced code blocks."""

    result: list[int] = []
    fence_character: str | None = None
    fence_length = 0
    for index, line in enumerate(lines):
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            continue
        if fence_character is None:
            result.append(index)
    return result


def normalize_text(text: str, title: str) -> str:
    """Return a canonical H1 and translator-note block, preserving all other text."""
    lines = text.splitlines()
    visible_lines = reader_visible_markdown(text).splitlines()
    prose_indices = prose_line_indices(visible_lines)
    h1_indices = [
        index for index in prose_indices if visible_lines[index].startswith("# ")
    ]
    if len(h1_indices) != 1:
        raise ValueError(f"expected exactly one H1, found {len(h1_indices)}")

    note_indices = [
        index for index in prose_indices if visible_lines[index] == "## 译者说明"
    ]
    if len(note_indices) > 1:
        raise ValueError(f"expected at most one translator-note heading, found {len(note_indices)}")

    if note_indices:
        note_start = note_indices[0]
        first_content = note_start + 1
        while (
            first_content < len(visible_lines)
            and not visible_lines[first_content].strip()
        ):
            first_content += 1
        if (
            first_content < len(visible_lines)
            and visible_lines[first_content] == TRANSLATOR_NOTE
        ):
            # A canonical block has a known one-line body. Delete only that
            # block: author/affiliation lines may legitimately follow it before
            # the next H2 and must survive a second normalization pass.
            note_end = first_content + 1
            while (
                note_end < len(visible_lines)
                and not visible_lines[note_end].strip()
            ):
                note_end += 1
        else:
            # Legacy notes have free-form bodies; their boundary is the next H2.
            note_end = next(
                (
                    index
                    for index in prose_indices
                    if index > note_start
                    if visible_lines[index].startswith("## ")
                ),
                len(lines),
            )
        del lines[note_start:note_end]

    visible_lines = reader_visible_markdown("\n".join(lines)).splitlines()
    h1_index = next(
        index
        for index in prose_line_indices(visible_lines)
        if visible_lines[index].startswith("# ")
    )
    lines[h1_index] = f"# {title}（中文译文）"

    remainder = lines[h1_index + 1 :]
    while remainder and not remainder[0].strip():
        remainder.pop(0)
    canonical_block = [
        lines[h1_index],
        "",
        "## 译者说明",
        "",
        TRANSLATOR_NOTE,
        "",
    ]
    normalized = lines[:h1_index] + canonical_block + remainder
    return "\n".join(normalized).rstrip() + "\n"


def normalize_all(
    root: Path, *, check: bool = False, paper_id: str | None = None
) -> list[Path]:
    changed: list[Path] = []
    updates: list[tuple[Path, str]] = []
    metadata_paths = sorted((root / "papers").glob("*/*/paper.yaml"))
    if paper_id is not None:
        metadata_paths = [
            path for path in metadata_paths if path.parent.name == paper_id
        ]
        if len(metadata_paths) != 1:
            raise ValueError(f"paper id must resolve exactly once: {paper_id}")
    for metadata_path in metadata_paths:
        translation = metadata_path.parent / "translation.md"
        if not translation.is_file():
            continue
        metadata = load_mapping(metadata_path)
        title = metadata.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"{metadata_path}: title must be a non-empty string")
        current = translation.read_text(encoding="utf-8")
        normalized = normalize_text(current, title.strip())
        if normalized != current:
            changed.append(translation)
            updates.append((translation, normalized))
    if not check:
        for translation, normalized in updates:
            translation.write_text(normalized, encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--paper-id", help="limit normalization to one exact paper id")
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        changed = normalize_all(root, check=args.check, paper_id=args.paper_id)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}")
        return 2
    if args.check and changed:
        for path in changed:
            print(f"ERROR: non-canonical translation header: {path.relative_to(root)}")
        return 1
    action = "would normalize" if args.check else "normalized"
    print(f"Translation headers {action}: {len(changed)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
