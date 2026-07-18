#!/usr/bin/env python3
"""Select the smallest safe CI validation scope from changed repository paths."""

from __future__ import annotations

import argparse
import sys
from pathlib import PurePosixPath


DEEP_CHECK_PATHS = frozenset(
    {
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
        "scripts/validate_listings.py",
        "scripts/validate_resources.py",
        "scripts/validate_translations.sh",
    }
)


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


def select_scope(
    changed_paths: list[str], *, force_deep: bool = False
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
    args = parser.parse_args()

    deep_check, paper_ids, deep_paths = select_scope(
        sys.stdin.read().splitlines(),
        force_deep=args.force_deep,
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
