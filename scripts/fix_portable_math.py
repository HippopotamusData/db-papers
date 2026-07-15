#!/usr/bin/env python3
"""Apply explicitly requested, byte-bounded Markdown-math fixes.

The safe fixer only inserts an ASCII space before an already recognized inline
formula when the preceding character is unambiguously prose punctuation or a
non-ASCII prose character. It never changes TeX, delimiters, containers,
presentation markup, footnotes, links, images, code, or paper metadata.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path

from validate_github_math import (
    MARKDOWN,
    extract_math_fragments,
    nonportable_math_lines,
)


SAFE_ASCII_PREDECESSORS = frozenset(",;:!?)")
SAFE_CJK_PUNCTUATION = frozenset("，。；：、！？》）】」』”’")


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset)


def _can_insert_boundary_space(previous: str) -> bool:
    return (
        previous in SAFE_ASCII_PREDECESSORS
        or previous in SAFE_CJK_PUNCTUATION
        or "\u3400" <= previous <= "\u9fff"
        or "\U00020000" <= previous <= "\U0003134f"
    )


def _safe_edits(text: str) -> list[tuple[int, str]]:
    excluded_lines = nonportable_math_lines(text)
    edits: list[tuple[int, str]] = []
    for fragment in extract_math_fragments(text):
        if fragment.display:
            continue
        opening = fragment.offset - 1
        if opening <= 0 or _line_number(text, opening) in excluded_lines:
            continue
        previous = text[opening - 1]
        if previous not in {" ", "("} and _can_insert_boundary_space(previous):
            edits.append((opening, " "))
    return edits


def _apply_edits(text: str, edits: list[tuple[int, str]]) -> str:
    for offset, insertion in sorted(edits, reverse=True):
        text = text[:offset] + insertion + text[offset:]
    return text


def safe_fix_text(text: str) -> str:
    """Return only byte-bounded boundary insertions proven safe below."""

    return _apply_edits(text, _safe_edits(text))


def _payload_signature(text: str) -> list[tuple[str, bool]]:
    return [
        (fragment.text, fragment.display)
        for fragment in extract_math_fragments(text)
    ]


def _markdown_signature(text: str) -> list[tuple[str, int, str, str]]:
    signature: list[tuple[str, int, str, str]] = []
    for token in MARKDOWN.parse(text):
        signature.append((token.type, token.nesting, token.tag, token.markup))
        for child in token.children or []:
            signature.append((child.type, child.nesting, child.tag, child.markup))
    return signature


def _assert_safe(original: str, fixed: str, edits: list[tuple[int, str]]) -> None:
    if fixed != _apply_edits(original, edits):
        raise ValueError("safe fix changed bytes outside its declared insertions")
    if _payload_signature(original) != _payload_signature(fixed):
        raise ValueError("safe fix changed a TeX payload, formula order, or formula type")
    if _markdown_signature(original) != _markdown_signature(fixed):
        raise ValueError("safe fix changed the Markdown container structure")
    if nonportable_math_lines(original) != nonportable_math_lines(fixed):
        raise ValueError("safe fix changed a nonportable Markdown container")
    if safe_fix_text(fixed) != fixed:
        raise ValueError("safe fix is not idempotent")


def _stage_text(path: Path, text: str) -> Path:
    """Write a replacement beside its target without changing the target."""

    mode = stat.S_IMODE(path.stat().st_mode)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    staged = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(staged, mode)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged


def _commit_planned(planned: list[tuple[Path, str, str]]) -> None:
    """Stage all files, replace atomically, and roll back a partial batch."""

    staged: list[tuple[Path, str, str, Path]] = []
    replaced: list[tuple[Path, str, str]] = []
    try:
        for path, original, fixed in planned:
            if path.is_symlink() or not path.is_file():
                raise OSError(f"refusing to replace a symlink or non-regular file: {path}")
            staged.append((path, original, fixed, _stage_text(path, fixed)))
        for path, original, fixed, temporary in staged:
            if path.is_symlink() or path.read_text(encoding="utf-8") != original:
                raise OSError(f"target changed after planning: {path}")
            os.replace(temporary, path)
            replaced.append((path, original, fixed))
    except OSError as error:
        rollback_errors: list[str] = []
        for path, original, fixed in reversed(replaced):
            rollback_temporary: Path | None = None
            try:
                if path.read_text(encoding="utf-8") != fixed:
                    rollback_errors.append(
                        f"{path}: concurrent edit preserved; rollback incomplete"
                    )
                    continue
                rollback_temporary = _stage_text(path, original)
                os.replace(rollback_temporary, path)
            except OSError as rollback_error:
                rollback_errors.append(f"{path}: {rollback_error}")
            finally:
                if rollback_temporary is not None:
                    rollback_temporary.unlink(missing_ok=True)
        if rollback_errors:
            details = "; ".join(rollback_errors)
            raise OSError(f"{error}; rollback also failed: {details}") from error
        raise
    finally:
        for _, _, _, temporary in staged:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="report safe-fix candidates without writing")
    check.add_argument("paths", nargs="+", type=Path)
    fix = commands.add_parser("fix", help="apply explicitly requested safe fixes")
    fix.add_argument("--safe", action="store_true", required=True)
    fix.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    planned: list[tuple[Path, str, str]] = []
    try:
        for path in args.paths:
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"refusing a symlink or non-regular file: {path}")
            original = path.read_text(encoding="utf-8")
            edits = _safe_edits(original)
            fixed = _apply_edits(original, edits)
            _assert_safe(original, fixed, edits)
            if fixed != original:
                planned.append((path, original, fixed))
        if args.command == "fix":
            _commit_planned(planned)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"ERROR: portable math safe fix failed: {error}", file=sys.stderr)
        return 2

    if args.command == "check" and planned:
        for path, _, _ in planned:
            print(path)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
