#!/usr/bin/env python3
"""Prepare run-local reader text and shared checks in one Python process.

No persistent cache or acceptance state is written. The shell validator still
owns policy severity, source evidence, and final status.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from markdown_visibility import reader_visible_markdown
from normalize_translation_headers import normalize_text
from validate_narrative_voice import find_ambiguous_author_narration


def prepare(manifest: Path, output: Path, *, check_headers: bool = False) -> None:
    for row in manifest.read_text(encoding="utf-8").splitlines()[1:]:
        kind, directory, status, _limit, _reason, title, _severity = row.split("\x1f")
        if kind != "paper":
            raise ValueError("invalid validation manifest row")
        source = Path(directory) / "translation.md"
        if status not in {"draft", "translated"} or not source.is_file():
            continue
        paper_id = Path(directory).name
        try:
            raw = source.read_text(encoding="utf-8")
            visible = reader_visible_markdown(raw)
            (output / f"visible-{paper_id}.md").write_text(visible, encoding="utf-8")
            findings = find_ambiguous_author_narration(visible, already_visible=True)
            (output / f"narrative-{paper_id}.txt").write_text(
                "\n".join(f"line {number}: {line}" for number, line in findings),
                encoding="utf-8",
            )
            if check_headers and normalize_text(raw, title, visible=visible) != raw:
                (output / f"header-{paper_id}.error").write_text(
                    "non-canonical translation header", encoding="utf-8")
        except (OSError, ValueError) as exc:
            (output / f"prepare-{paper_id}.error").write_text(str(exc), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--check-headers", action="store_true")
    args = parser.parse_args()
    prepare(args.manifest, args.output, check_headers=args.check_headers)


if __name__ == "__main__":
    main()
