#!/usr/bin/env python3
"""Shared severity policy for incomplete translation-quality findings."""

from __future__ import annotations

import sys


def quality_issue_severity(reading_status: str) -> str:
    if reading_status == "draft":
        return "warning"
    if reading_status == "translated":
        return "error"
    raise ValueError(f"quality findings do not apply to reading_status={reading_status}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validation_policy.py READING_STATUS", file=sys.stderr)
        return 2
    try:
        print(quality_issue_severity(sys.argv[1]))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
