#!/usr/bin/env python3
"""Run the final local gate for one clean, committed paper batch."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import batch_manifest
from ci_validation_scope import decode_changed_paths, select_validation_plan


FINAL_STATES = {
    "draft-only": frozenset({"draft-ready"}),
    "review-and-repair": frozenset({"reviewed", "rated"}),
}


@dataclass(frozen=True)
class BatchSnapshot:
    root: Path
    branch: str
    head: str
    path: Path
    data: dict


class GateFailure(RuntimeError):
    def __init__(self, command: Sequence[str], returncode: int) -> None:
        self.command = tuple(command)
        self.returncode = returncode
        super().__init__(
            f"{shlex.join(self.command)} failed with exit code {returncode}"
        )


def check_final_states(data: dict) -> None:
    allowed = FINAL_STATES[data["mode"]]
    unfinished = [
        f"{paper_id}={state}"
        for paper_id, state in sorted(data["targets"].items())
        if state not in allowed
    ]
    if unfinished:
        raise ValueError(
            f"{data['mode']} batch has non-final target state(s): "
            + ", ".join(unfinished)
        )


def capture_snapshot(manifest: str) -> BatchSnapshot:
    root, branch, head = batch_manifest.batch_context(require_clean=True)
    path = batch_manifest.manifest_path(root, manifest)
    data = batch_manifest.read_manifest(path)
    batch_manifest.check_manifest(data, root, branch)
    check_final_states(data)
    return BatchSnapshot(root, branch, head, path, data)


def changed_paths(root: Path, base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", f"{base}..{head}"],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = os.fsdecode(result.stderr).strip()
        suffix = f": {detail}" if detail else ""
        raise ValueError(f"cannot determine batch diff{suffix}")
    return decode_changed_paths(result.stdout)


def run_gate(root: Path, command: Sequence[str]) -> None:
    print(f"$ {shlex.join(command)}", flush=True)
    environment = os.environ.copy()
    for name in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL"):
        environment.pop(name, None)
    try:
        result = subprocess.run(
            list(command),
            cwd=root,
            env=environment,
            check=False,
        )
    except OSError as exc:
        raise ValueError(f"cannot run {command[0]}: {exc}") from exc
    if result.returncode:
        raise GateFailure(command, result.returncode)


def close_batch(
    manifest: str,
    *,
    runner: Callable[[Path, Sequence[str]], None] | None = None,
) -> None:
    before = capture_snapshot(manifest)
    paths = changed_paths(
        before.root,
        before.data["base_sha"],
        before.head,
    )
    plan = select_validation_plan(
        paths,
        root=before.root,
        base_sha=before.data["base_sha"],
        head_sha=before.head,
    )
    gate = "deep-check" if plan.deep_validate_all else "check"
    commands: list[list[str]] = [["make", "--no-print-directory", gate]]
    if plan.deep_validate_all:
        commands[0].append("DEEP_REASON=validator-semantics")
    commands.append(["make", "--no-print-directory", "diff-check"])

    selected_runner = runner or run_gate
    for command in commands:
        selected_runner(before.root, command)

    after = capture_snapshot(manifest)
    if after != before:
        raise ValueError(
            "batch HEAD, worktree, branch, or manifest changed while gates ran"
        )

    print(
        "BATCH_CLOSE_RESULT "
        f"status=passed head={before.head} gate={gate} "
        f"targets={len(before.data['targets'])}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        close_batch(args.manifest)
    except GateFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.returncode if 0 < exc.returncode < 256 else 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
