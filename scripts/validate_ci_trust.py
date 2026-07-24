#!/usr/bin/env python3
"""Reject PR changes to code executed by the privileged math-audit workflow."""

from __future__ import annotations

import argparse
from pathlib import Path


TRUSTED_ROOT = Path(__file__).resolve().parents[1]
PROTECTED_PATHS = (
    Path(".github/workflows/github-math-audit.yml"),
    Path("scripts/audit_changed_math.sh"),
    Path("scripts/verify_math_rendering.py"),
    Path("scripts/validate_github_math.py"),
    Path("scripts/validate_ci_trust.py"),
)


def _read_regular(root: Path, relative: Path, errors: list[str]) -> bytes | None:
    path = root / relative
    current = path
    while current != root:
        if current.is_symlink():
            errors.append(f"{relative}: symlinks are not allowed in the trust boundary")
            return None
        current = current.parent
    if not path.is_file():
        errors.append(f"{relative}: protected file is missing or not regular")
        return None
    try:
        return path.read_bytes()
    except OSError as exc:
        errors.append(f"{relative}: cannot be read: {exc}")
        return None


def validate_ci_trust(root: Path) -> list[str]:
    """Compare candidate privileged-runtime files with the trusted base checkout."""

    candidate_root = root.resolve()
    errors: list[str] = []
    for relative in PROTECTED_PATHS:
        trusted = _read_regular(TRUSTED_ROOT, relative, errors)
        candidate = _read_regular(candidate_root, relative, errors)
        if trusted is not None and candidate is not None and candidate != trusted:
            errors.append(
                f"{relative}: protected privileged-runtime file differs from "
                "the trusted base"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="candidate repository worktree to inspect as untrusted data",
    )
    args = parser.parse_args()
    errors = validate_ci_trust(args.root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("CI trust boundary verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
