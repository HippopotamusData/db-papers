#!/usr/bin/env python3
"""Locate changed papers that need a scoped CI validation gate."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


ACCEPTANCE_PATH = "config/acceptance.yaml"
ACCEPTANCE_SCHEMA_VERSION = 5
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_path(value: str) -> str:
    normalized = value.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def decode_changed_paths(payload: bytes) -> list[str]:
    """Decode Git's NUL-delimited path output without losing special characters."""

    return [os.fsdecode(value) for value in payload.split(b"\0") if value]


def changed_paper_id(path: str) -> str | None:
    parts = PurePosixPath(path).parts
    if len(parts) < 4 or parts[0] != "papers":
        return None
    if parts[3] not in {"assets", "paper.yaml", "source.pdf", "translation.md"}:
        return None
    return parts[2]


def changed_acceptance_paper_ids(base: Any, head: Any) -> list[str]:
    """Return changed acceptance entry IDs or reject an ambiguous ledger."""

    if not isinstance(base, dict) or not isinstance(head, dict):
        raise ValueError("base and head acceptance ledgers must be mappings")
    expected_keys = {"schema_version", "review_snapshots", "entries"}
    if set(base) != expected_keys or set(head) != expected_keys:
        raise ValueError("acceptance ledger has unexpected top-level keys")
    if (
        type(base["schema_version"]) is not int
        or type(head["schema_version"]) is not int
        or base["schema_version"] != ACCEPTANCE_SCHEMA_VERSION
        or head["schema_version"] != ACCEPTANCE_SCHEMA_VERSION
    ):
        raise ValueError(
            f"acceptance ledger schema_version must be {ACCEPTANCE_SCHEMA_VERSION}"
        )
    if (
        not isinstance(base["review_snapshots"], dict)
        or not isinstance(head["review_snapshots"], dict)
        or base["review_snapshots"] != head["review_snapshots"]
    ):
        raise ValueError("acceptance review_snapshots changed or are invalid")
    base_entries = base["entries"]
    head_entries = head["entries"]
    if not isinstance(base_entries, dict) or not isinstance(head_entries, dict):
        raise ValueError("acceptance entries must be mappings")
    all_ids = set(base_entries) | set(head_entries)
    if any(
        not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id)
        for paper_id in all_ids
    ):
        raise ValueError("acceptance entry IDs must be canonical paper slugs")
    if any(
        not isinstance(entry, dict)
        for entry in list(base_entries.values()) + list(head_entries.values())
    ):
        raise ValueError("acceptance entries must be mappings")
    return sorted(
        paper_id
        for paper_id in all_ids
        if base_entries.get(paper_id) != head_entries.get(paper_id)
    )


def acceptance_at_revision(root: Path, revision: str) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "-C", os.fspath(root), "show", f"{revision}:{ACCEPTANCE_PATH}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.strip()
        suffix = f": {details}" if details else ""
        raise ValueError(
            f"cannot read {ACCEPTANCE_PATH} at {revision}{suffix}"
        )
    try:
        value = yaml.safe_load(result.stdout)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"cannot parse {ACCEPTANCE_PATH} at {revision}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(
            f"{ACCEPTANCE_PATH} at {revision} must be a mapping"
        )
    return value


def select_paper_ids(
    changed_paths: list[str],
    *,
    acceptance_base: dict[str, Any] | None = None,
    acceptance_head: dict[str, Any] | None = None,
) -> list[str]:
    normalized = sorted(
        {
            path
            for value in changed_paths
            if (path := normalize_path(value))
        }
    )
    paper_ids = sorted(
        {
            paper_id
            for path in normalized
            if (paper_id := changed_paper_id(path)) is not None
        }
    )
    if ACCEPTANCE_PATH in normalized:
        acceptance_ids = changed_acceptance_paper_ids(
            acceptance_base,
            acceptance_head,
        )
        paper_ids = sorted(set(paper_ids) | set(acceptance_ids))
    return paper_ids


def emit_github_output(paper_ids: list[str]) -> None:
    print("paper_ids<<__DB_PAPERS__")
    print("\n".join(paper_ids))
    print("__DB_PAPERS__")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-sha",
        help="trusted Git diff base used to compare acceptance entries",
    )
    parser.add_argument(
        "--head-sha",
        default="HEAD",
        help="Git revision containing the proposed acceptance ledger",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    changed_paths = decode_changed_paths(sys.stdin.buffer.read())
    normalized = {normalize_path(path) for path in changed_paths}
    acceptance_base = None
    acceptance_head = None
    if ACCEPTANCE_PATH in normalized:
        if not args.base_sha:
            print(
                "ERROR: acceptance changes require a trusted --base-sha",
                file=sys.stderr,
            )
            return 1
        try:
            acceptance_base = acceptance_at_revision(args.root, args.base_sha)
            acceptance_head = acceptance_at_revision(args.root, args.head_sha)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    try:
        paper_ids = select_paper_ids(
            changed_paths,
            acceptance_base=acceptance_base,
            acceptance_head=acceptance_head,
        )
    except ValueError as exc:
        print(
            f"ERROR: cannot safely locate changed acceptance entries: {exc}",
            file=sys.stderr,
        )
        return 1
    print(
        f"CI changed paper IDs: {','.join(paper_ids) or '-'}",
        file=sys.stderr,
    )
    emit_github_output(paper_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
