#!/usr/bin/env python3
"""Maintain the minimal ignored state file for one Codex paper batch."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

from project_config import load_yaml


MODES = {"draft-only", "review-and-repair/accept"}
STATES = {
    "queued",
    "translating",
    "draft-ready",
    "reviewing",
    "accepted",
    "rated",
    "blocked",
}
TRANSITIONS = {
    "queued": {"translating", "reviewing", "blocked"},
    "translating": {"draft-ready", "blocked"},
    "draft-ready": {"translating", "reviewing", "blocked"},
    "reviewing": {"draft-ready", "accepted", "blocked"},
    "accepted": {"rated", "blocked"},
    "rated": set(),
    "blocked": {"queued", "translating", "reviewing", "accepted"},
}
KEYS = {
    "schema_version",
    "mode",
    "branch",
    "worktree",
    "review_base_sha",
    "targets",
}
ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return result


def git_text(*args: str) -> str:
    return git(*args).stdout.strip()


def batch_context(require_clean: bool) -> tuple[Path, str, str]:
    root = Path(git_text("rev-parse", "--show-toplevel")).resolve()
    head = git_text("rev-parse", "HEAD")
    branch = git_text("symbolic-ref", "--quiet", "--short", "HEAD")
    primary_line = next(
        (
            line
            for line in git_text("worktree", "list", "--porcelain").splitlines()
            if line.startswith("worktree ")
        ),
        "",
    )
    if not primary_line:
        raise ValueError("git worktree list did not report a primary worktree")
    primary = Path(primary_line.removeprefix("worktree ")).resolve()
    if root == primary:
        raise ValueError(
            "batch work must run in an isolated linked worktree, not the primary worktree"
        )
    if not branch.startswith("codex/"):
        raise ValueError(f"batch branch must use codex/ (current: {branch})")
    if require_clean:
        dirty = git_text("status", "--porcelain=v1", "--untracked-files=all")
        if dirty:
            raise ValueError(
                f"batch must start clean (first change: {dirty.splitlines()[0]})"
            )
    for name in (
        ".acceptance-transaction.yaml",
        ".acceptance-transaction.cleanup.yaml",
    ):
        marker = root / "config" / name
        if marker.exists():
            raise ValueError(f"recover acceptance transaction first: {marker}")
    return root, branch, head


def manifest_path(root: Path, value: str) -> Path:
    raw = Path(value)
    path = (raw if raw.is_absolute() else root / raw).resolve()
    allowed = (root / "tmp/batches").resolve()
    if path.parent != allowed or path.suffix not in {".yaml", ".yml"}:
        raise ValueError(f"manifest must be a YAML file directly under {allowed}")
    return path


def full_sha(value: str) -> str:
    result = git_text("rev-parse", "--verify", f"{value}^{{commit}}")
    if not SHA_RE.fullmatch(result):
        raise ValueError(f"BASE did not resolve to a full commit SHA: {value}")
    return result


def paper_ids(root: Path, values: list[str]) -> list[str]:
    if not values or len(values) != len(set(values)):
        raise ValueError("paper IDs must be a non-empty unique list")
    for paper_id in values:
        matches = list((root / "papers").glob(f"*/{paper_id}/paper.yaml"))
        if not ID_RE.fullmatch(paper_id) or len(matches) != 1:
            raise ValueError(
                f"paper ID must be valid and resolve to one paper.yaml: {paper_id}"
            )
    return sorted(values)


def read_manifest(path: Path) -> dict:
    try:
        data = load_yaml(path)
    except ValueError as exc:
        raise ValueError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(data, dict) or set(data) != KEYS:
        raise ValueError(f"manifest must contain exactly: {sorted(KEYS)}")
    targets = data["targets"]
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != 1
        or not isinstance(data["mode"], str)
        or data["mode"] not in MODES
        or not isinstance(data["branch"], str)
        or not data["branch"].startswith("codex/")
        or not isinstance(data["worktree"], str)
        or not Path(data["worktree"]).is_absolute()
        or not isinstance(data["review_base_sha"], str)
        or not SHA_RE.fullmatch(data["review_base_sha"])
        or not isinstance(targets, dict)
        or not targets
    ):
        raise ValueError("manifest has invalid values")
    for paper_id, state in targets.items():
        if not isinstance(paper_id, str) or not ID_RE.fullmatch(paper_id):
            raise ValueError(f"invalid target paper ID: {paper_id!r}")
        if not isinstance(state, str) or state not in STATES:
            raise ValueError(f"invalid target state: {paper_id}={state!r}")
        if data["mode"] == "draft-only" and state in {"accepted", "rated"}:
            raise ValueError(f"draft-only batch cannot record {state}")
    return data


def write_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def check_manifest(
    data: dict,
    root: Path,
    branch: str,
    *,
    paper_id: str | None = None,
    expected_state: str | None = None,
    expected_base_sha: str | None = None,
) -> None:
    if Path(data["worktree"]).resolve() != root or data["branch"] != branch:
        raise ValueError("manifest belongs to another branch or worktree")
    base = full_sha(data["review_base_sha"])
    if expected_base_sha is not None:
        expected_base = full_sha(expected_base_sha)
        if base != expected_base:
            raise ValueError(
                "manifest review_base_sha does not match the expected batch "
                f"base: manifest={base}, expected={expected_base}"
            )
    if git("merge-base", "--is-ancestor", base, "HEAD", check=False).returncode:
        raise ValueError(f"review_base_sha is not an ancestor of HEAD: {base}")
    paper_ids(root, list(data["targets"]))
    if paper_id is not None:
        if paper_id not in data["targets"]:
            raise ValueError(f"paper is not in this batch: {paper_id}")
        if expected_state and data["targets"][paper_id] != expected_state:
            raise ValueError(
                f"{paper_id} is {data['targets'][paper_id]!r}; "
                f"expected {expected_state!r}"
            )


def command_init(args: argparse.Namespace) -> None:
    root, branch, head = batch_context(require_clean=True)
    path = manifest_path(root, args.manifest)
    if path.exists():
        raise ValueError(f"manifest already exists: {path}")
    base = full_sha(args.base_sha)
    if base != head:
        raise ValueError(f"batch must start at BASE: HEAD={head}, BASE={base}")
    targets = {paper_id: "queued" for paper_id in paper_ids(root, args.paper_id)}
    write_manifest(
        path,
        {
            "schema_version": 1,
            "mode": args.mode,
            "branch": branch,
            "worktree": str(root),
            "review_base_sha": base,
            "targets": targets,
        },
    )
    print(f"Batch manifest initialized: {path}")
    print(f"review_base_sha: {base}")


def command_check(args: argparse.Namespace) -> None:
    root, branch, _ = batch_context(require_clean=args.require_clean)
    path = manifest_path(root, args.manifest)
    data = read_manifest(path)
    check_manifest(
        data,
        root,
        branch,
        paper_id=args.paper_id,
        expected_state=args.expected_state,
        expected_base_sha=args.expected_base_sha,
    )
    print(f"Batch manifest valid: {path} ({len(data['targets'])} target(s))")


def command_set_state(args: argparse.Namespace) -> None:
    root, branch, _ = batch_context(require_clean=False)
    path = manifest_path(root, args.manifest)
    data = read_manifest(path)
    check_manifest(data, root, branch, paper_id=args.paper_id)
    old = data["targets"][args.paper_id]
    if args.state == old:
        print(f"Batch state unchanged: {args.paper_id}={old}")
        return
    if args.state not in TRANSITIONS[old]:
        raise ValueError(f"invalid state transition: {old} -> {args.state}")
    if data["mode"] == "draft-only" and args.state in {"accepted", "rated"}:
        raise ValueError(f"draft-only batch cannot enter {args.state}")
    data["targets"][args.paper_id] = args.state
    write_manifest(path, data)
    print(f"Batch state updated: {args.paper_id}: {old} -> {args.state}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init")
    init.add_argument("--manifest", required=True)
    init.add_argument("--mode", required=True, choices=sorted(MODES))
    init.add_argument("--base-sha", required=True)
    init.add_argument("--paper-id", action="append", required=True)
    init.set_defaults(func=command_init)
    check = subparsers.add_parser("check")
    check.add_argument("--manifest", required=True)
    check.add_argument("--paper-id")
    check.add_argument("--expected-state", choices=sorted(STATES))
    check.add_argument("--expected-base-sha")
    check.add_argument("--require-clean", action="store_true")
    check.set_defaults(func=command_check)
    state = subparsers.add_parser("set-state")
    state.add_argument("--manifest", required=True)
    state.add_argument("--paper-id", required=True)
    state.add_argument("--state", required=True, choices=sorted(STATES))
    state.set_defaults(func=command_set_state)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        args.func(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
