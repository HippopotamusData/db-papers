#!/usr/bin/env python3
"""Plan the smallest safe CI validation scope for a Git diff."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


READER_ONLY_METADATA_FIELDS = frozenset({"rating", "title_zh", "topics"})
MATH_PROFILE_PATHS = frozenset(
    {
        "Makefile",
        "package.json",
        "package-lock.json",
        "scripts/fix_portable_math.py",
        "scripts/render_mathjax.cjs",
        "scripts/validate_github_math.py",
        "scripts/verify_math_rendering.py",
    }
)
DEEP_VALIDATION_PATHS = frozenset(
    {
        "Makefile",
        "config/policy.yaml",
        "scripts/markdown_visibility.py",
        "scripts/papers.py",
        "scripts/pdf_metrics.py",
        "scripts/project_config.py",
        "scripts/reference_sections.py",
        "scripts/validate_github_math.py",
        "scripts/validate_listings.py",
        "scripts/validate_narrative_voice.py",
        "scripts/validate_resources.py",
        "scripts/validate_source_pdf.py",
        "scripts/validate_translations.sh",
        "scripts/validation_policy.py",
    }
)
SITE_EXACT_PATHS = frozenset(
    {
        "Makefile",
        "config/taxonomy.yaml",
        "scripts/build_site.py",
        "scripts/project_config.py",
        "zensical.toml",
        ".github/workflows/pages.yml",
    }
)
MISSING = object()
INVALID = object()


@dataclass(frozen=True)
class ValidationPlan:
    """Independent validation domains selected by a trusted Git diff."""

    paper_ids: tuple[str, ...] = ()
    math_files: tuple[str, ...] = ()
    math_all: bool = False
    deep_validate_all: bool = False
    site_changed: bool = False


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


def paper_metadata_requires_scoped_gate(base: Any, head: Any) -> bool:
    """Return whether a metadata change can affect paper publication semantics."""

    if not isinstance(base, dict) or not isinstance(head, dict):
        return True
    changed_fields = {
        key for key in set(base) | set(head) if base.get(key) != head.get(key)
    }
    return bool(changed_fields - READER_ONLY_METADATA_FIELDS)


def file_at_revision(
    root: Path,
    revision: str,
    path: str,
    *,
    missing_ok: bool = False,
) -> str | object:
    result = subprocess.run(
        ["git", "-C", os.fspath(root), "show", f"{revision}:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if missing_ok:
            return MISSING
        details = result.stderr.strip()
        suffix = f": {details}" if details else ""
        raise ValueError(f"cannot read {path} at {revision}{suffix}")
    return result.stdout


def yaml_at_revision(
    root: Path,
    revision: str,
    path: str,
    *,
    missing_ok: bool = False,
) -> Any:
    payload = file_at_revision(
        root,
        revision,
        path,
        missing_ok=missing_ok,
    )
    if payload is MISSING:
        return MISSING
    try:
        return yaml.safe_load(payload)
    except yaml.YAMLError:
        return INVALID


def pyproject_groups_at_revision(
    root: Path,
    revision: str,
) -> tuple[Any, Any]:
    payload = file_at_revision(
        root,
        revision,
        "pyproject.toml",
        missing_ok=True,
    )
    if payload is MISSING:
        return MISSING, MISSING
    try:
        parsed = tomllib.loads(payload)
    except (tomllib.TOMLDecodeError, TypeError):
        return INVALID, INVALID
    groups = parsed.get("dependency-groups")
    if not isinstance(groups, dict):
        return INVALID, INVALID
    return groups.get("dev", MISSING), groups.get("site", MISSING)


def select_paper_ids(
    changed_paths: list[str],
) -> list[str]:
    normalized = sorted(
        {
            path
            for value in changed_paths
            if (path := normalize_path(value))
        }
    )
    return sorted(
        {
            paper_id
            for path in normalized
            if (paper_id := changed_paper_id(path)) is not None
        }
    )


def is_site_path(path: str) -> bool:
    if path in SITE_EXACT_PATHS:
        return True
    if path.startswith("site_assets/"):
        return True
    return changed_paper_id(path) is not None


def select_validation_plan(
    changed_paths: list[str],
    *,
    root: Path,
    base_sha: str | None = None,
    head_sha: str = "HEAD",
) -> ValidationPlan:
    """Map changed paths and field-level diffs to independent validation gates."""

    normalized = sorted(
        {
            path
            for value in changed_paths
            if (path := normalize_path(value))
        }
    )
    paper_ids: set[str] = set()
    math_files: set[str] = set()
    math_all = any(path in MATH_PROFILE_PATHS for path in normalized)
    deep_validate_all = any(
        path in DEEP_VALIDATION_PATHS for path in normalized
    )
    site_changed = any(is_site_path(path) for path in normalized)

    for path in normalized:
        paper_id = changed_paper_id(path)
        if paper_id is None:
            continue
        if path.endswith("/paper.yaml"):
            if not base_sha:
                raise ValueError(
                    "paper metadata changes require a trusted --base-sha"
                )
            base = yaml_at_revision(
                root,
                base_sha,
                path,
                missing_ok=True,
            )
            head = yaml_at_revision(
                root,
                head_sha,
                path,
                missing_ok=True,
            )
            if (
                base is MISSING
                or base is INVALID
                or head is MISSING
                or head is INVALID
                or paper_metadata_requires_scoped_gate(base, head)
            ):
                paper_ids.add(paper_id)
        else:
            paper_ids.add(paper_id)
        if path.endswith("/translation.md"):
            math_files.add(path)

    if "pyproject.toml" in normalized:
        if not base_sha:
            raise ValueError(
                "pyproject changes require a trusted --base-sha"
            )
        base_dev, base_site = pyproject_groups_at_revision(root, base_sha)
        head_dev, head_site = pyproject_groups_at_revision(root, head_sha)
        math_all = math_all or base_dev != head_dev
        deep_validate_all = deep_validate_all or base_dev != head_dev
        site_changed = site_changed or base_site != head_site

    return ValidationPlan(
        paper_ids=tuple(sorted(paper_ids)),
        math_files=tuple(sorted(math_files)),
        math_all=math_all,
        deep_validate_all=deep_validate_all,
        site_changed=site_changed,
    )


def _emit_multiline_output(name: str, values: tuple[str, ...]) -> None:
    print(f"{name}<<__DB_PAPERS__")
    print("\n".join(values))
    print("__DB_PAPERS__")


def emit_github_output(plan: ValidationPlan | list[str]) -> None:
    if isinstance(plan, list):
        plan = ValidationPlan(paper_ids=tuple(plan))
    _emit_multiline_output("paper_ids", plan.paper_ids)
    _emit_multiline_output("math_files", plan.math_files)
    print(f"math_all={'true' if plan.math_all else 'false'}")
    print(
        "deep_validate_all="
        f"{'true' if plan.deep_validate_all else 'false'}"
    )
    print(f"site_changed={'true' if plan.site_changed else 'false'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-sha",
        help="trusted Git diff base used for field-level comparisons",
    )
    parser.add_argument(
        "--head-sha",
        default="HEAD",
        help="Git revision containing the proposed changes",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    changed_paths = decode_changed_paths(sys.stdin.buffer.read())
    try:
        plan = select_validation_plan(
            changed_paths,
            root=args.root,
            base_sha=args.base_sha,
            head_sha=args.head_sha,
        )
    except ValueError as exc:
        print(
            f"ERROR: cannot safely determine validation scope: {exc}",
            file=sys.stderr,
        )
        return 1
    print(
        "CI validation plan: "
        f"papers={','.join(plan.paper_ids) or '-'} "
        f"math={'all' if plan.math_all else ','.join(plan.math_files) or '-'} "
        f"deep={'yes' if plan.deep_validate_all else 'no'} "
        f"site={'yes' if plan.site_changed else 'no'}",
        file=sys.stderr,
    )
    emit_github_output(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
