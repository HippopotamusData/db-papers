#!/usr/bin/env python3
"""Normalize deterministic Markdown-math portability hazards.

This tool only performs semantics-preserving syntax rewrites: portable display
delimiters, safe inline opening boundaries, and named TeX replacements for
characters that GitHub's Markdown pass otherwise consumes or HTML-escapes.
Ambiguous prose, unsafe closing boundaries, table-cell pipes, and unsupported
custom commands remain validator errors for manual repair.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from validate_github_math import FENCE_OPEN_RE, extract_math_fragments


SAME_LINE_DISPLAY_RE = re.compile(
    r"^(?P<prefix>(?: {0,3}>[ \t]?)* {0,3})\$\$(?P<body>\S(?:.*\S)?)\$\$[ \t]*(?P<newline>\r?\n)?$"
)
TEX_REPLACEMENTS = {
    r"\!": r"\negthinspace{}",
    r"\#": r'\char"0023{}',
    r"\%": r'\char"0025{}',
    r"\,": r"\thinspace{}",
    r"\;": r"\thickspace{}",
    r"\_": r'\char"005F{}',
    r"\{": r"\lbrace{}",
    r"\|": r"\Vert{}",
    r"\}": r"\rbrace{}",
    "<": r"\lt{}",
    ">": r"\gt{}",
    "*": r"\ast{}",
}


def _fence_close(line: str, quote: str, marker: str, minimum: int) -> bool:
    if not line.startswith(quote):
        return False
    remainder = line[len(quote) :]
    match = re.match(r"^( {0,3})(`+|~+)[ \t]*(?:\r?\n)?$", remainder)
    return bool(
        match
        and match.group(2)[0] == marker
        and len(match.group(2)) >= minimum
    )


def _portable_display_blocks(text: str) -> str:
    output: list[str] = []
    fence_marker: str | None = None
    fence_length = 0
    fence_quote = ""
    math_fence = False

    for line in text.splitlines(keepends=True):
        if fence_marker is not None:
            if _fence_close(line, fence_quote, fence_marker, fence_length):
                if math_fence:
                    newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
                    output.append(f"{fence_quote}$$" + newline)
                else:
                    output.append(line)
                fence_marker = None
                fence_length = 0
                fence_quote = ""
                math_fence = False
            else:
                output.append(line)
            continue

        opening = FENCE_OPEN_RE.match(line)
        if opening:
            run = opening.group("run")
            info = opening.group("info").strip()
            valid = not (run[0] == "`" and "`" in info)
            language = info.split(maxsplit=1)[0].lower() if info else ""
            if valid:
                fence_marker = run[0]
                fence_length = len(run)
                fence_quote = opening.group("quote")
                math_fence = language in {"math", "latex", "tex"}
                if math_fence:
                    newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
                    output.append(f"{fence_quote}$$" + newline)
                else:
                    output.append(line)
                continue

        same_line = SAME_LINE_DISPLAY_RE.match(line)
        if same_line:
            prefix = same_line.group("prefix")
            newline = same_line.group("newline") or ""
            output.extend(
                [
                    f"{prefix}$$" + newline,
                    f"{prefix}{same_line.group('body')}" + newline,
                    f"{prefix}$$" + newline,
                ]
            )
        else:
            output.append(line)
    converted = "".join(output)

    # GitHub treats list-indented $$ blocks as list/code content instead of
    # display math. Outdent them; blockquote prefixes remain supported.
    outdented: list[str] = []
    display_indent = ""
    for line in converted.splitlines(keepends=True):
        delimiter = re.match(
            r"^(?P<prefix>(?: {0,3}>[ \t]?)*)(?P<indent> {1,3})\$\$[ \t]*(?:\r?\n)?$",
            line,
        )
        if delimiter and ">" not in delimiter.group("prefix"):
            indent = delimiter.group("indent")
            if not display_indent:
                display_indent = indent
            elif indent == display_indent:
                display_indent = ""
            outdented.append(line[len(indent) :])
            continue
        if display_indent and line.startswith(display_indent):
            outdented.append(line[len(display_indent) :])
        else:
            outdented.append(line)
    return "".join(outdented)


def _normalize_tex(payload: str) -> str:
    output: list[str] = []
    cursor = 0
    while cursor < len(payload):
        replacement = None
        for source, target in TEX_REPLACEMENTS.items():
            if payload.startswith(source, cursor):
                replacement = (source, target)
                break
        if replacement is None and payload[cursor] == "_":
            previous = payload[cursor - 1] if cursor else ""
            if cursor and not (previous.isascii() and previous.isalnum()):
                output.append(r"\relax_")
            else:
                output.append("_")
            cursor += 1
        elif replacement is None:
            output.append(payload[cursor])
            cursor += 1
        else:
            source, target = replacement
            output.append(target)
            cursor += len(source)
    normalized = "".join(output)
    return re.sub(
        r"select",
        lambda match: match.group()[:5] + "{}" + match.group()[5:],
        normalized,
        flags=re.IGNORECASE,
    )


def _ordinary_math_containers(text: str) -> str:
    """Move formulas out of GitHub containers that suppress math rendering."""

    lines = text.splitlines(keepends=True)
    footnotes: dict[str, tuple[int, str]] = {}
    for index, line in enumerate(lines):
        match = re.match(r"^\[\^([^]]+)\]:\s*(.*\$.*)(\r?\n)?$", line)
        if match:
            footnotes[match.group(1)] = (index, match.group(2))

    for footnote_id, (definition_index, note) in footnotes.items():
        marker = f"[^{footnote_id}]"
        for index, line in enumerate(lines):
            if index == definition_index or marker not in line:
                continue
            lines[index] = line.replace(marker, f"（注：{note}）", 1)
            lines[definition_index] = ""
            break

    for index, line in enumerate(lines):
        newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        body = line[: -len(newline)] if newline else line
        stripped = body.strip()
        if (
            stripped.startswith("*")
            and not stripped.startswith("**")
            and stripped.endswith("*")
            and not stripped.endswith("**")
            and "$" in stripped
        ):
            start = body.index("*")
            end = body.rfind("*")
            lines[index] = body[:start] + body[start + 1 : end] + body[end + 1 :] + newline
    return "".join(lines)


def normalize_text(text: str) -> str:
    text = _ordinary_math_containers(text)
    text = _portable_display_blocks(text)
    edits: list[tuple[int, int, str]] = []
    for fragment in extract_math_fragments(text):
        normalized = _normalize_tex(fragment.text)
        if normalized != fragment.text:
            edits.append(
                (fragment.offset, fragment.offset + len(fragment.text), normalized)
            )
        if not fragment.display:
            opening = fragment.offset - 1
            if opening > 0 and text[opening - 1] not in {" ", "("}:
                edits.append((opening, opening, " "))

    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    args = parser.parse_args()

    changed: list[Path] = []
    try:
        for path in args.paths:
            original = path.read_text(encoding="utf-8")
            normalized = normalize_text(original)
            if normalized == original:
                continue
            changed.append(path)
            if not args.check:
                path.write_text(normalized, encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"ERROR: portable math normalization failed: {error}", file=sys.stderr)
        return 2

    if args.check and changed:
        for path in changed:
            print(path)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
