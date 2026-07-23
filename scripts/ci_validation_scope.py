#!/usr/bin/env python3
"""Select the smallest safe CI validation scope from changed repository paths."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


DEEP_CHECK_PATHS = frozenset(
    {
        "AGENTS.md",
        ".github/workflows/check.yml",
        "Makefile",
        "config/policy.yaml",
        "docs/translation-policy.md",
        "package-lock.json",
        "package.json",
        "pyproject.toml",
        "scripts/acceptance_evidence.py",
        "scripts/ci_validation_scope.py",
        "scripts/markdown_visibility.py",
        "scripts/papers.py",
        "scripts/pdf_metrics.py",
        "scripts/project_config.py",
        "scripts/reference_sections.py",
        "scripts/validate_source_pdf.py",
        "scripts/validate_listings.py",
        "scripts/validate_resources.py",
        "scripts/validate_translations.sh",
        "scripts/validation_policy.py",
    }
)
ACCEPTANCE_PATH = "config/acceptance.yaml"
ACCEPTANCE_SCHEMA_VERSION = 5
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_path(value: str) -> str:
    normalized = value.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def changed_paper_id(path: str) -> str | None:
    parts = PurePosixPath(path).parts
    if len(parts) < 4 or parts[0] != "papers":
        return None
    if parts[3] not in {"assets", "paper.yaml", "source.pdf", "translation.md"}:
        return None
    return parts[2]


def changed_acceptance_paper_ids(
    base: Any, head: Any
) -> tuple[bool, list[str]]:
    """Return whether a ledger diff is unsafe and its changed paper IDs."""

    if not isinstance(base, dict) or not isinstance(head, dict):
        return True, []
    expected_keys = {"schema_version", "review_snapshots", "entries"}
    if set(base) != expected_keys or set(head) != expected_keys:
        return True, []
    if (
        type(base["schema_version"]) is not int
        or type(head["schema_version"]) is not int
        or base["schema_version"] != ACCEPTANCE_SCHEMA_VERSION
        or head["schema_version"] != ACCEPTANCE_SCHEMA_VERSION
    ):
        return True, []
    if (
        not isinstance(base["review_snapshots"], dict)
        or not isinstance(head["review_snapshots"], dict)
        or base["review_snapshots"] != head["review_snapshots"]
    ):
        return True, []
    base_entries = base["entries"]
    head_entries = head["entries"]
    if not isinstance(base_entries, dict) or not isinstance(head_entries, dict):
        return True, []
    all_ids = set(base_entries) | set(head_entries)
    if any(not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id) for paper_id in all_ids):
        return True, []
    if any(
        not isinstance(entry, dict)
        for entry in list(base_entries.values()) + list(head_entries.values())
    ):
        return True, []
    return False, sorted(
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


def select_scope(
    changed_paths: list[str],
    *,
    force_deep: bool = False,
    acceptance_base: dict[str, Any] | None = None,
    acceptance_head: dict[str, Any] | None = None,
) -> tuple[bool, list[str], list[str]]:
    normalized = sorted(
        {
            path
            for value in changed_paths
            if (path := normalize_path(value))
        }
    )
    deep_paths = sorted(path for path in normalized if path in DEEP_CHECK_PATHS)
    paper_ids = sorted(
        {
            paper_id
            for path in normalized
            if (paper_id := changed_paper_id(path)) is not None
        }
    )
    if ACCEPTANCE_PATH in normalized:
        unsafe, acceptance_ids = changed_acceptance_paper_ids(
            acceptance_base, acceptance_head
        )
        paper_ids = sorted(set(paper_ids) | set(acceptance_ids))
        if unsafe:
            deep_paths = sorted(set(deep_paths) | {ACCEPTANCE_PATH})
    return force_deep or bool(deep_paths), paper_ids, deep_paths


def emit_github_output(deep_check: bool, paper_ids: list[str]) -> None:
    print(f"deep_check={'true' if deep_check else 'false'}")
    print("paper_ids<<__DB_PAPERS__")
    print("\n".join(paper_ids))
    print("__DB_PAPERS__")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force-deep",
        action="store_true",
        help="select the full repository gate when no trustworthy diff base exists",
    )
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

    changed_paths = sys.stdin.read().splitlines()
    normalized = {normalize_path(path) for path in changed_paths}
    acceptance_base = None
    acceptance_head = None
    acceptance_error = ""
    if ACCEPTANCE_PATH in normalized:
        if not args.base_sha:
            acceptance_error = "missing trusted --base-sha"
        else:
            try:
                acceptance_base = acceptance_at_revision(args.root, args.base_sha)
                acceptance_head = acceptance_at_revision(args.root, args.head_sha)
            except ValueError as exc:
                acceptance_error = str(exc)
    deep_check, paper_ids, deep_paths = select_scope(
        changed_paths,
        force_deep=args.force_deep,
        acceptance_base=acceptance_base,
        acceptance_head=acceptance_head,
    )
    if acceptance_error:
        print(
            f"CI acceptance diff is not safely locatable: {acceptance_error}; "
            "selecting deep-check",
            file=sys.stderr,
        )
    print(
        "CI validation scope: "
        f"deep_check={str(deep_check).lower()}, "
        f"paper_ids={','.join(paper_ids) or '-'}, "
        f"deep_paths={','.join(deep_paths) or '-'}",
        file=sys.stderr,
    )
    emit_github_output(deep_check, paper_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
