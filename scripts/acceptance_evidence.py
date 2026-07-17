#!/usr/bin/env python3
"""Build and compare item-level acceptance-waiver evidence."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


WAIVER_CATEGORIES = frozenset({"abridgement", "listings", "resources"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def normalize_candidates(candidates: Iterable[str]) -> list[str]:
    normalized: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, str):
            raise ValueError("waiver candidates must be strings")
        candidate = candidate.strip()
        if not candidate:
            raise ValueError("waiver candidates must not be empty")
        if any(separator in candidate for separator in ("\n", "\r", "\t")):
            raise ValueError("waiver candidates must be single-line, tab-free strings")
        normalized.add(candidate)
    return sorted(normalized)


def waiver_fingerprint(category: str, candidates: Iterable[str]) -> str:
    if category not in WAIVER_CATEGORIES:
        raise ValueError(f"unknown waiver category: {category!r}")
    normalized = normalize_candidates(candidates)
    if not normalized:
        raise ValueError(f"waiver category {category!r} must contain at least one candidate")
    payload = json.dumps(
        {"category": category, "candidates": normalized},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_waiver_records(observed: dict[str, Iterable[str]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for category in sorted(observed):
        if category not in WAIVER_CATEGORIES:
            raise ValueError(f"unknown waiver category: {category}")
        candidates = normalize_candidates(observed[category])
        if not candidates:
            continue
        records[category] = {
            "fingerprint": waiver_fingerprint(category, candidates),
            "candidates": candidates,
        }
    return records


def validate_waiver_records(value: Any, label: str = "waivers") -> dict[str, dict[str, Any]]:
    """Validate and return canonical item-level waiver evidence.

    A category-only waiver is intentionally not accepted.  The exact candidate
    strings and their deterministic fingerprint are part of the acceptance
    snapshot, so a later candidate change cannot be hidden by an old category.
    """

    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    unknown = [
        category
        for category in value
        if not isinstance(category, str) or category not in WAIVER_CATEGORIES
    ]
    if unknown:
        raise ValueError(
            f"{label} contains unknown categories: "
            + ", ".join(repr(category) for category in sorted(unknown, key=repr))
        )
    result: dict[str, dict[str, Any]] = {}
    for category in sorted(value):
        record = value[category]
        if not isinstance(record, dict):
            raise ValueError(f"{label}.{category} must be a mapping")
        missing = {"fingerprint", "candidates"} - record.keys()
        extra = record.keys() - {"fingerprint", "candidates"}
        if missing or extra:
            details: list[str] = []
            if missing:
                details.append(f"missing keys: {', '.join(sorted(missing))}")
            if extra:
                details.append(f"unknown keys: {', '.join(sorted(extra))}")
            raise ValueError(f"{label}.{category}: {'; '.join(details)}")
        candidates = record["candidates"]
        if not isinstance(candidates, list):
            raise ValueError(f"{label}.{category}.candidates must be a list")
        normalized = normalize_candidates(candidates)
        if candidates != normalized:
            raise ValueError(
                f"{label}.{category}.candidates must be sorted, unique, and trimmed"
            )
        if not normalized:
            raise ValueError(f"{label}.{category}.candidates must not be empty")
        fingerprint = record["fingerprint"]
        if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(fingerprint):
            raise ValueError(
                f"{label}.{category}.fingerprint must be a lowercase SHA-256 digest"
            )
        expected = waiver_fingerprint(category, normalized)
        if fingerprint != expected:
            raise ValueError(
                f"{label}.{category}.fingerprint does not match its candidates"
            )
        result[category] = {
            "fingerprint": fingerprint,
            "candidates": normalized,
        }
    return result


def read_observed_tsv(path: Path) -> dict[str, list[str]]:
    observed: dict[str, list[str]] = {}
    if not path.exists():
        return observed
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line:
            continue
        try:
            category, candidate = raw_line.split("\t", 1)
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: expected category<TAB>candidate") from exc
        category = category.strip()
        if not category:
            raise ValueError(f"{path}:{line_number}: waiver category must not be empty")
        if category not in WAIVER_CATEGORIES:
            raise ValueError(f"{path}:{line_number}: unknown waiver category: {category}")
        observed.setdefault(category, []).append(candidate)
    return observed


def encode_waiver_records(records: dict[str, Any]) -> str:
    records = validate_waiver_records(records)
    payload = json.dumps(
        records,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_waiver_records(encoded: str) -> dict[str, Any]:
    error = "recorded waiver evidence is not valid canonical URL-safe base64 JSON"
    if not isinstance(encoded, str) or not encoded:
        raise ValueError(error)
    try:
        decoded = base64.b64decode(encoded.encode("ascii"), altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(decoded).decode("ascii") != encoded:
            raise ValueError(error)
        value = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError, binascii.Error) as exc:
        raise ValueError(error) from exc
    return validate_waiver_records(value, "recorded waiver evidence")


def compare_waiver_records(
    recorded: dict[str, dict[str, Any]], observed: dict[str, dict[str, Any]]
) -> tuple[list[str], list[str]]:
    recorded = validate_waiver_records(recorded, "recorded waivers")
    observed = validate_waiver_records(observed, "observed waivers")
    reviewed: list[str] = []
    mismatches: list[str] = []
    for category in sorted(observed.keys() | recorded.keys()):
        expected = recorded.get(category)
        current = observed.get(category)
        if expected is None and current is not None:
            mismatches.append(
                f"missing:{category}:{current['fingerprint']}:{' | '.join(current['candidates'])}"
            )
        elif current is None and expected is not None:
            mismatches.append(f"unused:{category}:{expected.get('fingerprint', '')}")
        elif expected != current:
            mismatches.append(
                f"changed:{category}:{expected.get('fingerprint', '')}:"
                f"{current.get('fingerprint', '')}:{' | '.join(current.get('candidates', []))}"
            )
        else:
            reviewed.append(
                f"reviewed:{category}:{current['fingerprint']}:{len(current['candidates'])}"
            )
    return reviewed, mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--recorded", required=True)
    compare_parser.add_argument("--observed", required=True, type=Path)
    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--observed", required=True, type=Path)
    args = parser.parse_args()

    if args.command == "compare":
        try:
            recorded = decode_waiver_records(args.recorded)
            observed = build_waiver_records(read_observed_tsv(args.observed))
            reviewed, mismatches = compare_waiver_records(recorded, observed)
        except (OSError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        for item in reviewed:
            print(item)
        for item in mismatches:
            print(item)
        return 1 if mismatches else 0

    if args.command == "summarize":
        try:
            records = build_waiver_records(read_observed_tsv(args.observed))
        except (OSError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        for category, record in records.items():
            print(
                f"WAIVER-EVIDENCE: --waiver {category}={record['fingerprint']} "
                f"({len(record['candidates'])} candidate(s))"
            )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
