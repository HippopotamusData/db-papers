#!/usr/bin/env python3
"""Plan the smallest safe CI validation scope for a Git diff."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


ACCEPTANCE_PATH = "config/acceptance.yaml"
ACCEPTANCE_SCHEMA_VERSION = 5
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
READER_ONLY_METADATA_FIELDS = frozenset({"rating", "title_zh", "topics"})
MATH_PROFILE_PATHS = frozenset(
    {
        "package.json",
        "package-lock.json",
        "scripts/fix_portable_math.py",
        "scripts/render_mathjax.cjs",
        "scripts/validate_github_math.py",
        "scripts/verify_math_rendering.py",
    }
)
SITE_EXACT_PATHS = frozenset(
    {
        "Makefile",
        ACCEPTANCE_PATH,
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
    """Return whether a metadata change can affect paper/acceptance semantics."""

    if not isinstance(base, dict) or not isinstance(head, dict):
        return True
    changed_fields = {
        key for key in set(base) | set(head) if base.get(key) != head.get(key)
    }
    return bool(changed_fields - READER_ONLY_METADATA_FIELDS)


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
    base_snapshots = base["review_snapshots"]
    head_snapshots = head["review_snapshots"]
    if not isinstance(base_snapshots, dict) or not isinstance(
        head_snapshots, dict
    ):
        raise ValueError("acceptance review_snapshots must be mappings")
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
    changed_ids = sorted(
        paper_id
        for paper_id in all_ids
        if base_entries.get(paper_id) != head_entries.get(paper_id)
    )
    added_snapshots = set(head_snapshots) - set(base_snapshots)
    changed_snapshots = {
        snapshot_id
        for snapshot_id in set(base_snapshots) & set(head_snapshots)
        if base_snapshots[snapshot_id] != head_snapshots[snapshot_id]
    }
    if added_snapshots or changed_snapshots:
        raise ValueError(
            "acceptance review_snapshots may only remove newly unreferenced "
            "snapshots"
        )

    removed_snapshots = set(base_snapshots) - set(head_snapshots)
    if removed_snapshots:
        base_references: dict[Any, set[str]] = {}
        head_references: set[Any] = set()
        for paper_id, entry in base_entries.items():
            if "review_snapshot" in entry:
                snapshot_id = entry["review_snapshot"]
                if not isinstance(snapshot_id, str):
                    raise ValueError(
                        "acceptance entry review_snapshot must be a string"
                    )
                base_references.setdefault(snapshot_id, set()).add(paper_id)
        for entry in head_entries.values():
            if "review_snapshot" in entry:
                snapshot_id = entry["review_snapshot"]
                if not isinstance(snapshot_id, str):
                    raise ValueError(
                        "acceptance entry review_snapshot must be a string"
                    )
                head_references.add(snapshot_id)

        safely_pruned = True
        for snapshot_id in removed_snapshots:
            referencing_ids = base_references.get(snapshot_id, set())
            if not referencing_ids or snapshot_id in head_references:
                safely_pruned = False
                break
            for paper_id in referencing_ids:
                base_entry = base_entries[paper_id]
                head_entry = head_entries.get(paper_id)
                if (
                    type(base_entry.get("schema_version")) is not int
                    or base_entry["schema_version"] != 1
                    or head_entry is None
                    or type(head_entry.get("schema_version")) is not int
                    or head_entry["schema_version"] != 2
                    or "review_snapshot" in head_entry
                ):
                    safely_pruned = False
                    break
            if not safely_pruned:
                break
        if not safely_pruned:
            raise ValueError(
                "acceptance review_snapshots may only remove newly "
                "unreferenced snapshots"
            )
    return changed_ids


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


def acceptance_at_revision(root: Path, revision: str) -> dict[str, Any]:
    value = yaml_at_revision(root, revision, ACCEPTANCE_PATH)
    if value is INVALID:
        raise ValueError(f"cannot parse {ACCEPTANCE_PATH} at {revision}")
    if not isinstance(value, dict):
        raise ValueError(
            f"{ACCEPTANCE_PATH} at {revision} must be a mapping"
        )
    return value


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
    acceptance_base: dict[str, Any] | None = None,
    acceptance_head: dict[str, Any] | None = None,
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

    if ACCEPTANCE_PATH in normalized:
        if acceptance_base is None or acceptance_head is None:
            if not base_sha:
                raise ValueError(
                    "acceptance changes require a trusted --base-sha"
                )
            acceptance_base = acceptance_at_revision(root, base_sha)
            acceptance_head = acceptance_at_revision(root, head_sha)
        paper_ids.update(
            changed_acceptance_paper_ids(
                acceptance_base,
                acceptance_head,
            )
        )

    if "pyproject.toml" in normalized:
        if not base_sha:
            raise ValueError(
                "pyproject changes require a trusted --base-sha"
            )
        base_dev, base_site = pyproject_groups_at_revision(root, base_sha)
        head_dev, head_site = pyproject_groups_at_revision(root, head_sha)
        math_all = math_all or base_dev != head_dev
        site_changed = site_changed or base_site != head_site

    return ValidationPlan(
        paper_ids=tuple(sorted(paper_ids)),
        math_files=tuple(sorted(math_files)),
        math_all=math_all,
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
    print(f"site_changed={'true' if plan.site_changed else 'false'}")


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
        plan = select_validation_plan(
            changed_paths,
            root=args.root,
            base_sha=args.base_sha,
            head_sha=args.head_sha,
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
        "CI validation plan: "
        f"papers={','.join(plan.paper_ids) or '-'} "
        f"math={'all' if plan.math_all else ','.join(plan.math_files) or '-'} "
        f"site={'yes' if plan.site_changed else 'no'}",
        file=sys.stderr,
    )
    emit_github_output(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
