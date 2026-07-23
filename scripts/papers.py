#!/usr/bin/env python3
"""Validate minimal reading metadata, expose status rows, and generate the catalog."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from acceptance_evidence import (
    build_waiver_records,
    compare_waiver_records,
    decode_waiver_records,
    encode_waiver_records,
    read_observed_tsv,
)
from project_config import (
    ACCEPTANCE_WAIVERS,
    ALLOW_WHOLE_PAGE_IMAGES_IN_READING_PATH,
    GIT_SHA_RE,
    METADATA_FILE,
    REVIEW_IDENTITY_ASSURANCE,
    REQUIRED_REVIEW_CHECKS,
    REQUIRE_COMPLETE_REFERENCES,
    REVIEW_RECEIPT_SCHEMA_VERSION,
    RUNTIME_REVIEW_ACTIONS,
    SHA256_RE,
    SLUG_RE,
    SOURCE_FILE,
    TARGET_LANGUAGE,
    TRANSLATION_FILE,
    assets_manifest,
    assets_manifest_sha256,
    configured_paths,
    effective_page_limit,
    load_acceptance_ledger,
    load_project_policy,
    load_taxonomy,
    load_yaml,
    load_yaml_text,
    is_trimmed_single_line,
    review_receipt_fingerprint,
    review_gate_manifest_sha256,
    review_metadata_sha256,
    sha256_file,
    skip_reason as configured_skip_reason,
    validate_acceptance_ledger,
    validate_review_receipt,
)
from validation_policy import quality_issue_severity
from validate_github_math import math_like_code_span_issues


ROOT = Path(__file__).resolve().parents[1]
PAPERS = ROOT / "papers"
CATALOG = ROOT / "CATALOG.md"
REQUIRED_TOP_LEVEL_KEYS = {"title", "authors", "year", "source_url", "topics", "reading_status"}
OPTIONAL_TOP_LEVEL_KEYS = {"rating"}
READING_STATUSES = {"unavailable", "source_only", "draft", "translated", "skipped"}
RATING_DIMENSIONS = {
    "influence_breadth": Decimal("0.30"),
    "technical_value": Decimal("0.25"),
    "practical_diffusion": Decimal("0.20"),
    "durability": Decimal("0.15"),
    "reader_payoff": Decimal("0.10"),
}
RATING_KEYS = {"score", *RATING_DIMENSIONS}
VALID_RATING_SCORES = {Decimal(step) / 2 for step in range(2, 11)}
VALIDATION_FIELD_SEPARATOR = "\x1f"
VALIDATION_INTERNAL_ENV_KEYS = (
    "ACCEPTANCE_DISCOVERY",
    "ACCEPTANCE_EVIDENCE_FILE",
    "ACCEPTANCE_PAPER_ID",
    "ACCEPTANCE_RECORDED_WAIVERS",
    "ACCEPTANCE_TARGET_STATUS",
    "PAPER_ID",
    "SKIP_METADATA_VALIDATION",
)
ACCEPTANCE_JOURNAL_SCHEMA_VERSION = 1


class IndentedSafeDumper(yaml.SafeDumper):
    """Indent block lists so generated records match the documented template."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.dump(
        data,
        Dumper=IndentedSafeDumper,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )


def atomic_write_text(path: Path, content: str) -> None:
    """Replace one text file atomically; callers coordinate multi-file rollback."""
    temporary_name: str | None = None
    existing_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            if existing_mode is not None:
                os.fchmod(handle.fileno(), existing_mode)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary_name).replace(path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def _acceptance_journal_path(root: Path) -> Path:
    return root / "config/.acceptance-transaction.yaml"


def _acceptance_cleanup_marker_path(root: Path) -> Path:
    return root / "config/.acceptance-transaction.cleanup.yaml"


def _acceptance_transaction_markers(root: Path) -> list[Path]:
    return [
        path
        for path in (
            _acceptance_journal_path(root),
            _acceptance_cleanup_marker_path(root),
        )
        if path.exists() or path.is_symlink()
    ]


def _unfinished_acceptance_marker(root: Path) -> Path | None:
    markers = _acceptance_transaction_markers(root)
    if len(markers) > 1:
        rendered = ", ".join(path.relative_to(root).as_posix() for path in markers)
        raise ValueError(
            "multiple acceptance transaction markers exist; refusing to choose "
            f"between them: {rendered}"
        )
    return markers[0] if markers else None


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _acceptance_journal_fingerprint(journal: dict[str, Any]) -> str:
    payload = dict(journal)
    payload.pop("fingerprint", None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_acceptance_journal(
    *,
    paper_id: str,
    ledger_path: Path,
    original_ledger: str,
    accepted_ledger: str,
    metadata_path: Path,
    original_metadata: str,
    accepted_metadata: str,
    source: Path,
    source_sha256: str,
    translation: Path,
    translation_sha256: str,
    assets_manifest_sha256_value: str,
    policy_path: Path,
    policy_sha256: str,
    review_gate_sha256: str,
    git_head: str,
) -> dict[str, Any]:
    journal: dict[str, Any] = {
        "schema_version": ACCEPTANCE_JOURNAL_SCHEMA_VERSION,
        "paper_id": paper_id,
        "files": {
            ledger_path.relative_to(ROOT).as_posix(): {
                "original": original_ledger,
                "accepted": accepted_ledger,
            },
            metadata_path.relative_to(ROOT).as_posix(): {
                "original": original_metadata,
                "accepted": accepted_metadata,
            },
        },
        "context": {
            "source_path": source.relative_to(ROOT).as_posix(),
            "source_sha256": source_sha256,
            "translation_path": translation.relative_to(ROOT).as_posix(),
            "translation_sha256": translation_sha256,
            "assets_manifest_sha256": assets_manifest_sha256_value,
            "translation_policy_path": policy_path.relative_to(ROOT).as_posix(),
            "translation_policy_sha256": policy_sha256,
            "review_gate_manifest_sha256": review_gate_sha256,
            "git_head": git_head,
        },
    }
    journal["fingerprint"] = _acceptance_journal_fingerprint(journal)
    return journal


def _validate_acceptance_journal(
    journal: Any,
    *,
    root: Path,
    label: str,
) -> dict[str, Any]:
    if not isinstance(journal, dict):
        raise ValueError(f"{label}: YAML root must be a mapping")
    expected_keys = {
        "schema_version",
        "paper_id",
        "files",
        "context",
        "fingerprint",
    }
    if set(journal) != expected_keys:
        missing = expected_keys - journal.keys()
        unknown = journal.keys() - expected_keys
        details: list[str] = []
        if missing:
            details.append("missing keys: " + ", ".join(sorted(missing)))
        if unknown:
            details.append("unknown keys: " + ", ".join(sorted(unknown)))
        raise ValueError(f"{label}: {'; '.join(details)}")
    if (
        type(journal["schema_version"]) is not int
        or journal["schema_version"] != ACCEPTANCE_JOURNAL_SCHEMA_VERSION
    ):
        raise ValueError(
            f"{label}.schema_version must be integer "
            f"{ACCEPTANCE_JOURNAL_SCHEMA_VERSION}"
        )
    paper_id = journal["paper_id"]
    if not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id):
        raise ValueError(f"{label}.paper_id must be kebab-case")
    files = journal["files"]
    if not isinstance(files, dict):
        raise ValueError(f"{label}.files must be a mapping")
    metadata_matches = sorted(
        root.glob(f"papers/*/{paper_id}/{METADATA_FILE}")
    )
    if len(metadata_matches) != 1:
        raise ValueError(
            f"{label}: paper id must resolve exactly once: {paper_id}"
        )
    expected_paths = {
        (root / "config/acceptance.yaml").relative_to(root).as_posix(),
        metadata_matches[0].relative_to(root).as_posix(),
    }
    if set(files) != expected_paths:
        raise ValueError(
            f"{label}.files must contain exactly the acceptance ledger "
            "and the paper metadata"
        )
    for relative_path, record in files.items():
        if not isinstance(record, dict) or set(record) != {"original", "accepted"}:
            raise ValueError(
                f"{label}.files.{relative_path} must contain only "
                "original and accepted"
            )
        for state in ("original", "accepted"):
            if not isinstance(record[state], str):
                raise ValueError(
                    f"{label}.files.{relative_path}.{state} must be text"
                )
        if record["original"] == record["accepted"]:
            raise ValueError(
                f"{label}.files.{relative_path} must describe a real change"
            )
    context = journal["context"]
    expected_context_keys = {
        "source_path",
        "source_sha256",
        "translation_path",
        "translation_sha256",
        "assets_manifest_sha256",
        "translation_policy_path",
        "translation_policy_sha256",
        "review_gate_manifest_sha256",
        "git_head",
    }
    if not isinstance(context, dict) or set(context) != expected_context_keys:
        raise ValueError(
            f"{label}.context must contain exactly the acceptance input snapshot"
        )
    paper_dir = metadata_matches[0].parent
    expected_context_paths = {
        "source_path": (paper_dir / SOURCE_FILE).relative_to(root).as_posix(),
        "translation_path": (paper_dir / TRANSLATION_FILE)
        .relative_to(root)
        .as_posix(),
        "translation_policy_path": "docs/translation-policy.md",
    }
    for key, expected in expected_context_paths.items():
        if context[key] != expected:
            raise ValueError(f"{label}.context.{key} must be {expected!r}")
    for key in (
        "source_sha256",
        "translation_sha256",
        "assets_manifest_sha256",
        "translation_policy_sha256",
        "review_gate_manifest_sha256",
    ):
        if not isinstance(context[key], str) or not SHA256_RE.fullmatch(context[key]):
            raise ValueError(f"{label}.context.{key} must be lowercase SHA-256")
    if not isinstance(context["git_head"], str) or not GIT_SHA_RE.fullmatch(
        context["git_head"]
    ):
        raise ValueError(f"{label}.context.git_head must be a lowercase Git SHA")
    fingerprint = journal["fingerprint"]
    if (
        not isinstance(fingerprint, str)
        or fingerprint != _acceptance_journal_fingerprint(journal)
    ):
        raise ValueError(f"{label}.fingerprint does not match the journal")
    return journal


def _write_acceptance_journal(journal: dict[str, Any]) -> Path:
    journal_path = _acceptance_journal_path(ROOT)
    if _acceptance_transaction_markers(ROOT):
        raise ValueError(
            "an unfinished acceptance transaction already exists; "
            "run recover-acceptance first"
        )
    atomic_write_text(journal_path, dump_yaml(journal))
    recorded = _validate_acceptance_journal(
        load_yaml_text(journal_path.read_text(encoding="utf-8"), str(journal_path)),
        root=ROOT,
        label=str(journal_path),
    )
    if recorded != journal:
        raise ValueError("acceptance transaction journal failed verification")
    return journal_path


def _remove_acceptance_journal(
    marker_path: Path,
    expected_content: str,
) -> None:
    """Durably retire a journal without losing the only recovery record.

    The active journal is first renamed to a cleanup marker and that rename is
    directory-synced.  Only then may the cleanup marker be unlinked.  If the
    first sync fails, recovery can consume the marker.  If only the final sync
    fails after a successful unlink, the requested transaction state is already
    complete; a crash can at worst resurrect the durable cleanup marker.
    """

    journal_path = _acceptance_journal_path(ROOT)
    cleanup_path = _acceptance_cleanup_marker_path(ROOT)
    if marker_path == journal_path:
        if cleanup_path.exists() or cleanup_path.is_symlink():
            raise OSError(
                f"cleanup marker already exists at {cleanup_path.relative_to(ROOT)}"
            )
        marker_path.replace(cleanup_path)
        marker_path = cleanup_path
    elif marker_path != cleanup_path:
        raise OSError(f"unexpected acceptance transaction marker: {marker_path}")

    if marker_path.read_text(encoding="utf-8") != expected_content:
        raise OSError("transaction marker changed concurrently; refusing to remove it")

    # This is the recovery anchor: failure leaves the marker visible and usable.
    _fsync_directory(marker_path.parent)
    if marker_path.read_text(encoding="utf-8") != expected_content:
        raise OSError("transaction marker changed concurrently; refusing to remove it")

    marker_path.unlink()
    try:
        _fsync_directory(marker_path.parent)
    except OSError as exc:
        print(
            "WARNING: acceptance transaction state is complete, but cleanup "
            "directory sync failed after the durable marker was removed; a "
            f"stale cleanup marker may reappear after a crash: {exc}",
            file=sys.stderr,
        )


def records() -> list[tuple[Path, dict[str, Any]]]:
    result: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(PAPERS.glob(f"*/*/{METADATA_FILE}")):
        result.append((path, load_yaml(path)))
    return result


def add_error(errors: list[str], path: Path, message: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {message}")


def is_absolute_http_url(value: Any) -> bool:
    if not is_trimmed_single_line(value):
        return False
    if any(
        character.isspace()
        or ord(character) < 0x20
        or character in "<>\\"
        for character in value
    ):
        return False
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        parsed.port
        username = parsed.username
        password = parsed.password
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(hostname)
        and username is None
        and password is None
    )


def is_regular_non_symlink(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def file_contract_matches(path: Path, expected: bool) -> bool:
    if expected:
        return is_regular_non_symlink(path)
    return not path.exists() and not path.is_symlink()


def calculated_rating_score(rating: dict[str, Any]) -> Decimal:
    raw_score = sum(
        Decimal(rating[dimension]) * weight
        for dimension, weight in RATING_DIMENSIONS.items()
    )
    rounded = (raw_score * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2
    qualifies_for_five = (
        rating["influence_breadth"] == 5
        and rating["technical_value"] >= 4
        and rating["durability"] >= 4
        and min(rating[dimension] for dimension in RATING_DIMENSIONS) >= 3
    )
    if rounded == Decimal("5") and not qualifies_for_five:
        return Decimal("4.5")
    return rounded


def validate_rating(
    errors: list[str],
    path: Path,
    rating: Any,
    year: Any,
    *,
    current_year: int | None = None,
) -> None:
    if not isinstance(rating, dict):
        add_error(errors, path, "rating must be a mapping")
        return

    missing = RATING_KEYS - rating.keys()
    unknown = rating.keys() - RATING_KEYS
    if missing:
        add_error(errors, path, f"rating missing keys: {', '.join(sorted(missing))}")
    if unknown:
        add_error(errors, path, f"rating unknown keys: {', '.join(sorted(unknown))}")

    dimensions_valid = True
    for dimension in RATING_DIMENSIONS:
        value = rating.get(dimension)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            add_error(errors, path, f"rating.{dimension} must be an integer between 1 and 5")
            dimensions_valid = False

    score = rating.get("score")
    try:
        normalized_score = Decimal(str(score))
    except (InvalidOperation, ValueError):
        normalized_score = None
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or normalized_score not in VALID_RATING_SCORES
    ):
        add_error(errors, path, "rating.score must be between 1.0 and 5.0 in 0.5 increments")
        return

    if dimensions_valid and not missing:
        expected = calculated_rating_score(rating)
        if normalized_score != expected:
            add_error(
                errors,
                path,
                f"rating.score must equal the weighted score {expected:.1f}",
            )
        effective_year = date.today().year if current_year is None else current_year
        if (
            type(year) is int
            and effective_year - year < 5
            and rating["durability"] > 4
        ):
            add_error(
                errors,
                path,
                "rating.durability must not exceed 4 for papers published "
                "less than five years ago",
            )


def parse_translation_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("translation.md must start with YAML frontmatter")
    try:
        frontmatter, _body = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise ValueError("translation.md frontmatter is not closed") from exc
    return load_yaml_text(frontmatter, f"{path}: frontmatter")


def validate(paper_id: str | None = None) -> int:
    errors: list[str] = []
    transaction_markers = _acceptance_transaction_markers(ROOT)
    if transaction_markers:
        rendered_markers = ", ".join(
            path.relative_to(ROOT).as_posix() for path in transaction_markers
        )
        print(
            "ERROR: unfinished acceptance transaction marker exists at "
            f"{rendered_markers}; run "
            "`scripts/papers.py recover-acceptance --mode commit` or "
            "`--mode rollback`",
            file=sys.stderr,
        )
        return 1
    try:
        taxonomy = load_taxonomy(ROOT / "config/taxonomy.yaml")
        paths = configured_paths(ROOT)
        policy = load_project_policy(paths["policy"])
        acceptance = load_acceptance_ledger(paths["acceptance_ledger"])
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    areas = set(taxonomy["areas"])
    allowed_topics = set(taxonomy["topics"])
    target_language = TARGET_LANGUAGE
    metadata_name = paths["metadata"].name
    source_name = paths["source"].name
    translation_name = paths["translation"].name

    if paper_id is not None and not SLUG_RE.fullmatch(paper_id):
        print(f"ERROR: paper id must be kebab-case: {paper_id}", file=sys.stderr)
        return 1

    acceptance_entries = acceptance["entries"]
    review_bases = {
        receipt["review_base_sha"]
        for configured_id, receipt in acceptance_entries.items()
        if paper_id is None or configured_id == paper_id
    }
    for review_base_sha in sorted(review_bases):
        try:
            validate_review_base_commit(ROOT, review_base_sha)
        except (OSError, ValueError) as exc:
            errors.append(
                f"{paths['acceptance_ledger'].relative_to(ROOT)}: "
                f"invalid review_base_sha {review_base_sha}: {exc}"
            )
    review_heads = {
        receipt["review_head_sha"]
        for configured_id, receipt in acceptance_entries.items()
        if receipt["schema_version"] >= 2
        and (paper_id is None or configured_id == paper_id)
    }
    for review_head_sha in sorted(review_heads):
        try:
            validate_review_base_commit(ROOT, review_head_sha)
        except (OSError, ValueError) as exc:
            errors.append(
                f"{paths['acceptance_ledger'].relative_to(ROOT)}: "
                f"invalid review_head_sha {review_head_sha}: {exc}"
            )

    if paper_id is None:
        for path in sorted(PAPERS.glob("**/metadata.md")):
            add_error(errors, path, f"legacy metadata.md is not allowed; use {metadata_name}")

        paper_areas = {path.name for path in PAPERS.iterdir() if path.is_dir()}
        for unknown_area in sorted(paper_areas - areas):
            errors.append(f"papers/{unknown_area}: directory is not a registered area")

    metadata_paths = sorted(PAPERS.glob(f"*/*/{metadata_name}"))
    if paper_id is not None:
        metadata_paths = [path for path in metadata_paths if path.parent.name == paper_id]
        if len(metadata_paths) != 1:
            print(f"ERROR: paper id must resolve exactly once: {paper_id}", file=sys.stderr)
            return 1

    loaded: list[tuple[Path, dict[str, Any]]] = []
    for path in metadata_paths:
        try:
            data = load_yaml(path)
        except ValueError as exc:
            add_error(errors, path, str(exc))
            continue
        loaded.append((path, data))

        missing = REQUIRED_TOP_LEVEL_KEYS - data.keys()
        unknown = data.keys() - REQUIRED_TOP_LEVEL_KEYS - OPTIONAL_TOP_LEVEL_KEYS
        if missing:
            add_error(errors, path, f"missing keys: {', '.join(sorted(missing))}")
        if unknown:
            add_error(errors, path, f"unknown keys: {', '.join(sorted(unknown))}")
        if "rating" in data:
            validate_rating(errors, path, data["rating"], data.get("year"))

        slug = path.parent.name
        area = path.parent.parent.name
        if area not in areas:
            add_error(errors, path, f"paper area is not registered: {area}")
        if not SLUG_RE.fullmatch(slug):
            add_error(errors, path, f"paper directory must be a kebab-case id: {slug}")
        if not is_trimmed_single_line(data.get("title")):
            add_error(errors, path, "title must be a trimmed, non-empty single-line string")
        authors = data.get("authors")
        if not isinstance(authors, list) or any(
            not is_trimmed_single_line(author) for author in authors
        ):
            add_error(
                errors,
                path,
                "authors must be a list of trimmed, non-empty single-line strings",
            )
        elif len(authors) != len(set(authors)):
            add_error(errors, path, "authors contains duplicates")
        year = data.get("year")
        if year is not None and (type(year) is not int or not 1800 <= year <= 2100):
            add_error(errors, path, "year must be null or an integer between 1800 and 2100")
        if not is_absolute_http_url(data.get("source_url")):
            add_error(
                errors,
                path,
                "source_url must be a safe absolute HTTP(S) URL on one line",
            )

        topics = data.get("topics")
        if not isinstance(topics, list) or not topics:
            add_error(errors, path, "topics must contain at least one value")
        elif any(not isinstance(topic, str) for topic in topics):
            add_error(errors, path, "topics must contain strings")
        elif len(topics) != len(set(topics)):
            add_error(errors, path, "topics contains duplicates")
        elif invalid_topics := sorted(set(topics) - allowed_topics):
            add_error(errors, path, f"unregistered topics: {', '.join(invalid_topics)}")

        reading_status = data.get("reading_status")
        if reading_status not in READING_STATUSES:
            add_error(errors, path, f"invalid reading_status: {reading_status}")

        source = path.parent / source_name
        translation = path.parent / translation_name
        expected_files = {
            "unavailable": (False, False),
            "source_only": (True, False),
            "draft": (True, True),
            "translated": (True, True),
            "skipped": (True, False),
        }
        if reading_status in expected_files:
            expect_source, expect_translation = expected_files[reading_status]
            if not file_contract_matches(source, expect_source):
                add_error(
                    errors,
                    path,
                    f"reading_status={reading_status} requires "
                    f"{source_name}={expect_source} as a regular non-symlink file",
                )
            if not file_contract_matches(translation, expect_translation):
                add_error(
                    errors,
                    path,
                    f"reading_status={reading_status} requires "
                    f"{translation_name}={expect_translation} as a regular "
                    "non-symlink file",
                )

        if is_regular_non_symlink(translation):
            try:
                frontmatter = parse_translation_frontmatter(translation)
            except (OSError, ValueError, yaml.YAMLError) as exc:
                add_error(errors, translation, str(exc))
            else:
                expected_frontmatter = {
                    "paper_id": slug,
                    "title": data.get("title"),
                    "language": target_language,
                    "source": source_name,
                }
                if frontmatter != expected_frontmatter:
                    add_error(
                        errors,
                        translation,
                        "frontmatter must contain only canonical paper_id, title, language, and source",
                    )

        paper_skip_reason = configured_skip_reason(policy, slug)
        if reading_status == "skipped" and not paper_skip_reason:
            add_error(errors, path, "reading_status=skipped requires a project-level skipped reason")
        if reading_status != "skipped" and paper_skip_reason:
            add_error(errors, path, "project-level skipped reason exists but reading_status is not skipped")

        receipt = acceptance["entries"].get(slug)
        if reading_status == "translated":
            if not receipt:
                add_error(errors, path, "reading_status=translated requires an acceptance-ledger entry")
            elif is_regular_non_symlink(source) and is_regular_non_symlink(translation):
                current_source_hash = sha256_file(source)
                current_translation_hash = sha256_file(translation)
                current_assets_hash = assets_manifest_sha256(path.parent, ROOT)
                if receipt["source_sha256"] != current_source_hash:
                    add_error(errors, path, "source.pdf changed after acceptance; set status to draft and review again")
                if receipt["translation_sha256"] != current_translation_hash:
                    add_error(errors, path, "translation.md changed after acceptance; set status to draft and review again")
                if receipt["assets_manifest_sha256"] != current_assets_hash:
                    add_error(
                        errors,
                        path,
                        "assets changed after acceptance; set status to draft and review again",
                    )
                if (
                    receipt["review_metadata_sha256"]
                    != review_metadata_sha256(
                        data,
                        receipt["schema_version"],
                    )
                ):
                    add_error(
                        errors,
                        path,
                        "title/authors/year/source_url changed after review; "
                        "set status to draft and review again",
                    )
        elif receipt and reading_status not in {"draft"}:
            add_error(errors, path, "acceptance-ledger entry is only allowed for translated or re-reviewing draft papers")

    if paper_id is None:
        ids = [path.parent.name for path, _data in loaded]
        for duplicate, count in Counter(ids).items():
            if count > 1:
                errors.append(f"duplicate paper id: {duplicate}")

        known_ids = set(ids)
        for configured_id in sorted(policy["papers"]):
            if configured_id not in known_ids:
                errors.append(
                    f"{paths['policy'].relative_to(ROOT)}: unknown paper id: {configured_id}"
                )
        for configured_id in sorted(acceptance["entries"]):
            if configured_id not in known_ids:
                errors.append(
                    f"{paths['acceptance_ledger'].relative_to(ROOT)}: unknown paper id: {configured_id}"
                )

        paper_dirs = sorted(path for path in PAPERS.glob("*/*") if path.is_dir())
        metadata_dirs = {path.parent for path, _data in loaded}
        for directory in paper_dirs:
            if directory not in metadata_dirs:
                errors.append(f"{directory.relative_to(ROOT)}: paper directory is missing {metadata_name}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"Validation failed with {len(errors)} error(s).", file=sys.stderr)
        return 1

    counts = Counter(data["reading_status"] for _path, data in loaded)
    summary = ", ".join(f"{status}={counts[status]}" for status in sorted(counts))
    print(f"Metadata validation passed: {len(loaded)} papers ({summary}).")
    return 0


def status_rows() -> int:
    for path, data in records():
        print(f"{path.parent.relative_to(ROOT)}\t{data['reading_status']}")
    return 0


def review_queue(limit: int | None = None) -> int:
    """Print a deterministic risk-first queue for deeper PDF review."""

    paths = configured_paths(ROOT)
    acceptance = load_acceptance_ledger(paths["acceptance_ledger"])["entries"]
    queue: list[tuple[int, str, list[str]]] = []
    for metadata_path, data in records():
        if data.get("reading_status") != "translated":
            continue
        paper_id = metadata_path.parent.name
        receipt = acceptance[paper_id]
        score = 0
        reasons: list[str] = []
        if receipt["schema_version"] == 1 and not receipt["findings"]:
            score += 40
            reasons.append("legacy-empty-findings")
        waivers = receipt.get("waivers", {})
        waiver_weights = {"abridgement": 30, "listings": 20, "resources": 10}
        for category, weight in waiver_weights.items():
            if category in waivers:
                score += weight
                findings = len(waivers[category].get("findings", []))
                score += min(findings, 20)
                reasons.append(f"{category}-waiver:{findings}")
        asset_count = len(assets_manifest(metadata_path.parent, ROOT))
        if asset_count:
            score += min(asset_count, 10)
            reasons.append(f"assets:{asset_count}")
        rating = data.get("rating")
        if isinstance(rating, dict) and rating.get("score") in {4.5, 5.0}:
            score += 5
            reasons.append(f"high-reading-value:{rating['score']}")
        translation_path = metadata_path.parent / TRANSLATION_FILE
        if translation_path.is_file():
            math_code_spans = len(
                math_like_code_span_issues(
                    translation_path.read_text(encoding="utf-8")
                )
            )
            if math_code_spans:
                score += 15 + min(math_code_spans, 20)
                reasons.append(f"math-like-code-spans:{math_code_spans}")
        queue.append((score, paper_id, reasons))
    queue.sort(key=lambda item: (-item[0], item[1]))
    print("priority\tpaper_id\treasons")
    selected = queue if limit is None else queue[:limit]
    for score, paper_id, reasons in selected:
        print(f"{score}\t{paper_id}\t{','.join(reasons)}")
    return 0


def catalog_reading_target(
    path: Path, data: dict[str, Any], source_name: str, translation_name: str
) -> str:
    relative_dir = path.parent.relative_to(ROOT).as_posix()
    if data["reading_status"] in {"draft", "translated"}:
        return f"{relative_dir}/{translation_name}"
    if data["reading_status"] in {"source_only", "skipped"}:
        return f"{relative_dir}/{source_name}"
    return f"{relative_dir}/"


def catalog_rating(data: dict[str, Any]) -> str:
    rating = data.get("rating")
    if not isinstance(rating, dict):
        return "—"
    score = rating.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return "—"
    return f"{score:.1f}"


def markdown_link_label(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("|", "\\|")
    )


def markdown_link_destination(value: str) -> str:
    return f"<{value.replace('<', '%3C').replace('>', '%3E')}>"


def build_catalog() -> str:
    paths = configured_paths(ROOT)
    source_name = paths["source"].name
    translation_name = paths["translation"].name
    taxonomy = load_taxonomy(ROOT / "config/taxonomy.yaml")
    loaded = records()
    area_counts = Counter(path.parent.parent.name for path, _data in loaded)
    status_counts = Counter(data["reading_status"] for _path, data in loaded)
    completeness = {
        "作者": sum(bool(data["authors"]) for _path, data in loaded),
        "发表年份": sum(data["year"] is not None for _path, data in loaded),
    }

    lines = [
        "# 论文目录",
        "",
        (
            "> 本文件由 `make catalog` 从各论文的 `paper.yaml` 生成，"
            "请勿手工编辑。"
        ),
        "",
        "## 总览",
        "",
        f"- 论文记录：{len(loaded)}",
        f"- 已验收译文：{status_counts['translated']}",
        f"- 译文草稿：{status_counts['draft']}",
        f"- 仅有原文：{status_counts['source_only']}",
        f"- 已跳过：{status_counts['skipped']}",
        f"- 原文不可用：{status_counts['unavailable']}",
        "",
        "## 领域分布",
        "",
        "| 一级领域 | 数量 |",
        "| --- | ---: |",
    ]
    for area, details in taxonomy["areas"].items():
        if area_counts[area]:
            area_label = markdown_link_label(details["label_zh"])
            lines.append(f"| {area_label} (`{area}`) | {area_counts[area]} |")

    lines.extend(["", "## 按领域浏览"])
    area_order = {area: index for index, area in enumerate(taxonomy["areas"])}
    topic_order = {topic: index for index, topic in enumerate(taxonomy["topics"])}
    loaded.sort(
        key=lambda item: (
            area_order[item[0].parent.parent.name],
            item[1]["title"].casefold(),
        )
    )
    for area, details in taxonomy["areas"].items():
        area_records = [
            (path, data)
            for path, data in loaded
            if path.parent.parent.name == area
        ]
        if not area_records:
            continue

        lines.extend(
            [
                "",
                f"### {markdown_link_label(details['label_zh'])} "
                f"(`{area}`，{len(area_records)} 篇)",
                "",
                "| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |",
                "| --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        for path, data in area_records:
            topic_labels = "、".join(
                markdown_link_label(
                    taxonomy["topics"][topic]["label_zh"]
                )
                for topic in sorted(data["topics"], key=topic_order.__getitem__)
            )
            reading_target = catalog_reading_target(path, data, source_name, translation_name)
            title = markdown_link_label(data["title"])
            year = data["year"] if data["year"] is not None else "—"
            rating = catalog_rating(data)
            lines.append(
                f"| [{title}]({reading_target}) | {topic_labels} | "
                f"{year} | {rating} | {data['reading_status']} | "
                f"[原文]({markdown_link_destination(data['source_url'])}) |"
            )

    lines.extend(["", "## 元数据完整性", "", "| 字段 | 已确认 | 待补证据 |", "| --- | ---: | ---: |"])
    for label, known in completeness.items():
        lines.append(f"| {label} | {known} | {len(loaded) - known} |")
    return "\n".join(lines) + "\n"


def catalog(check: bool) -> int:
    content = build_catalog()
    if check:
        if not CATALOG.exists() or CATALOG.read_text(encoding="utf-8") != content:
            print("ERROR: CATALOG.md is stale; run `make catalog`.", file=sys.stderr)
            return 1
        print("Catalog is current.")
        return 0
    CATALOG.write_text(content, encoding="utf-8")
    print(f"Wrote {CATALOG.relative_to(ROOT)}.")
    return 0


def new_record(paper_id: str, title: str, area: str, topics: list[str], url: str) -> int:
    taxonomy = load_taxonomy(ROOT / "config/taxonomy.yaml")
    metadata_name = METADATA_FILE
    if not SLUG_RE.fullmatch(paper_id):
        print("ERROR: --id must be a lowercase kebab-case slug.", file=sys.stderr)
        return 1
    if area not in taxonomy["areas"]:
        print(f"ERROR: unregistered area: {area}", file=sys.stderr)
        return 1
    unknown_topics = sorted(set(topics) - taxonomy["topics"].keys())
    if unknown_topics:
        print(f"ERROR: unregistered topics: {', '.join(unknown_topics)}", file=sys.stderr)
        return 1
    if len(topics) != len(set(topics)):
        print("ERROR: duplicate --topic values are not allowed.", file=sys.stderr)
        return 1
    topic_order = {topic: index for index, topic in enumerate(taxonomy["topics"])}
    if (
        not is_trimmed_single_line(title)
        or not is_absolute_http_url(url)
    ):
        print(
            "ERROR: --title and --url must be trimmed single-line values, "
            "and --url must be absolute HTTP(S).",
            file=sys.stderr,
        )
        return 1

    target = PAPERS / area / paper_id
    existing = sorted(PAPERS.glob(f"*/{paper_id}"))
    if existing:
        print(f"ERROR: paper id already exists: {existing[0].relative_to(ROOT)}", file=sys.stderr)
        return 1

    data = {
        "title": title,
        "authors": [],
        "year": None,
        "source_url": url,
        "topics": sorted(topics, key=topic_order.__getitem__),
        "reading_status": "unavailable",
    }
    target.mkdir(parents=True)
    (target / metadata_name).write_text(
        dump_yaml(data),
        encoding="utf-8",
    )
    print(f"Created {target.relative_to(ROOT)}/{metadata_name}; add source.pdf and update reading_status when ready.")
    return 0


def config_value(key: str, paper_id: str | None) -> int:
    try:
        paths = configured_paths(ROOT)
        policy = load_project_policy(paths["policy"])
        acceptance = load_acceptance_ledger(paths["acceptance_ledger"])
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    values: dict[str, Any] = {
        "max_source_pages": policy["default_max_source_pages"],
        "require_complete_references": REQUIRE_COMPLETE_REFERENCES,
        "allow_whole_page_images_in_reading_path": ALLOW_WHOLE_PAGE_IMAGES_IN_READING_PATH,
        "source_pdf": SOURCE_FILE,
        "translation_file": TRANSLATION_FILE,
    }
    if key == "paper_page_limit":
        if not paper_id:
            print("ERROR: --paper-id is required for paper_page_limit", file=sys.stderr)
            return 1
        print(effective_page_limit(policy, paper_id))
        return 0
    if key == "skip_reason":
        if not paper_id:
            print("ERROR: --paper-id is required for skip_reason", file=sys.stderr)
            return 1
        print(configured_skip_reason(policy, paper_id))
        return 0
    if key == "acceptance_waivers":
        if not paper_id:
            print("ERROR: --paper-id is required for acceptance_waivers", file=sys.stderr)
            return 1
        receipt = acceptance["entries"].get(paper_id)
        print(encode_waiver_records(receipt.get("waivers", {}) if receipt else {}))
        return 0
    if key == "paper_title":
        if not paper_id:
            print("ERROR: --paper-id is required for paper_title", file=sys.stderr)
            return 1
        matches = sorted(PAPERS.glob(f"*/{paper_id}/{paths['metadata'].name}"))
        if len(matches) != 1:
            print(f"ERROR: paper id must resolve exactly once: {paper_id}", file=sys.stderr)
            return 1
        title = load_yaml(matches[0]).get("title")
        if not isinstance(title, str) or not title.strip():
            print(f"ERROR: paper has no valid title: {paper_id}", file=sys.stderr)
            return 1
        print(title)
        return 0
    if key not in values:
        print(f"ERROR: unsupported config key: {key}", file=sys.stderr)
        return 1
    value = values[key]
    print(str(value).lower() if isinstance(value, bool) else value)
    return 0


def validation_manifest(
    paper_id: str | None,
    *,
    preflight_paper_id: str | None = None,
    preflight_target_status: str = "",
    preflight_waivers: str = "",
) -> int:
    """Emit one validated, delimiter-safe snapshot for the shell deep validator."""

    try:
        paths = configured_paths(ROOT)
        policy = load_project_policy(paths["policy"])
        acceptance = load_acceptance_ledger(paths["acceptance_ledger"])
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    def emit(fields: list[str]) -> bool:
        for field in fields:
            if VALIDATION_FIELD_SEPARATOR in field or "\n" in field or "\r" in field:
                print("ERROR: validation manifest field contains a record delimiter", file=sys.stderr)
                return False
        print(VALIDATION_FIELD_SEPARATOR.join(fields))
        return True

    if not emit(
        [
            "config",
            paths["source"].name,
            paths["translation"].name,
            str(REQUIRE_COMPLETE_REFERENCES).lower(),
            str(ALLOW_WHOLE_PAGE_IMAGES_IN_READING_PATH).lower(),
        ]
    ):
        return 1

    metadata_name = paths["metadata"].name
    preflight_paper_id = preflight_paper_id or ""
    if preflight_paper_id and paper_id != preflight_paper_id:
        print(
            "ERROR: acceptance preflight paper id must match the scoped --paper-id",
            file=sys.stderr,
        )
        return 1
    if (preflight_target_status or preflight_waivers) and not preflight_paper_id:
        print(
            "ERROR: acceptance preflight overrides require an exact paper id",
            file=sys.stderr,
        )
        return 1
    if preflight_target_status not in {"", "translated"}:
        print("ERROR: acceptance target status must be translated", file=sys.stderr)
        return 1
    if preflight_target_status and not preflight_waivers:
        print(
            "ERROR: translated acceptance preflight requires recorded waiver evidence",
            file=sys.stderr,
        )
        return 1
    if preflight_waivers:
        try:
            preflight_waivers = encode_waiver_records(
                decode_waiver_records(preflight_waivers)
            )
        except ValueError as exc:
            print(f"ERROR: invalid acceptance recorded waivers: {exc}", file=sys.stderr)
            return 1
    for path in sorted(PAPERS.glob(f"*/*/{metadata_name}")):
        slug = path.parent.name
        if paper_id and slug != paper_id:
            continue
        try:
            data = load_yaml(path)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        reading_status = data.get("reading_status")
        title = data.get("title")
        if not isinstance(reading_status, str) or not isinstance(title, str):
            print(
                f"ERROR: {path}: validation manifest requires valid title and reading_status",
                file=sys.stderr,
            )
            return 1
        receipt = acceptance["entries"].get(slug)
        waivers = encode_waiver_records(
            receipt.get("waivers", {}) if receipt else {}
        )
        if slug == preflight_paper_id:
            if preflight_target_status:
                reading_status = preflight_target_status
            waivers = preflight_waivers or encode_waiver_records({})
        severity = (
            quality_issue_severity(reading_status)
            if reading_status in {"draft", "translated"}
            else ""
        )
        review_grade = bool(
            reading_status == "draft"
            or slug == preflight_paper_id
            or receipt
        )
        fields = [
            "paper",
            path.parent.relative_to(ROOT).as_posix(),
            reading_status,
            str(effective_page_limit(policy, slug)),
            waivers,
            configured_skip_reason(policy, slug),
            title,
            severity,
            str(review_grade).lower(),
        ]
        if not emit(fields):
            return 1
    return 0


class AcceptanceInterrupted(RuntimeError):
    """Raised when SIGTERM requests a rollback-safe acceptance stop."""


def _acceptance_lock_path(root: Path) -> Path:
    common_dir = subprocess.run(
        [
            "git",
            "-C",
            os.fspath(root),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    identity = (
        Path(common_dir.stdout.strip()).resolve()
        if common_dir.returncode == 0 and common_dir.stdout.strip()
        else root.resolve()
    )
    root_key = hashlib.sha256(os.fsencode(identity)).hexdigest()[:24]
    return Path(tempfile.gettempdir()) / f"db-papers-acceptance-{root_key}.lock"


@contextlib.contextmanager
def acceptance_lock(root: Path):
    """Serialize acceptance writers across every worktree of one repository."""

    lock_path = _acceptance_lock_path(root)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def sigterm_as_exception():
    """Convert SIGTERM into an exception and restore the caller's handler."""

    def handle_sigterm(_signum, _frame) -> None:
        raise AcceptanceInterrupted("acceptance interrupted by SIGTERM")

    try:
        previous = signal.signal(signal.SIGTERM, handle_sigterm)
    except ValueError:
        # Signal handlers can only be installed by the main thread.  The CLI is
        # always on that thread; tests embedding this function still get all
        # lock, CAS, and KeyboardInterrupt protections.
        yield
        return
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _run_preflight_command(
    command: list[str], env: dict[str, str], output: list[str]
) -> bool:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    details = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    if details:
        output.append(details)
    return completed.returncode == 0


def validate_review_base_commit(root: Path, review_base_sha: str) -> None:
    """Require the recorded review baseline to be a real ancestor commit."""

    commit = subprocess.run(
        ["git", "-C", os.fspath(root), "cat-file", "-e", f"{review_base_sha}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        details = commit.stderr.strip()
        suffix = f": {details}" if details else ""
        raise ValueError(f"review_base_sha is not an available Git commit{suffix}")
    ancestor = subprocess.run(
        ["git", "-C", os.fspath(root), "merge-base", "--is-ancestor", review_base_sha, "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if ancestor.returncode == 1:
        raise ValueError("review_base_sha must be an ancestor of the current HEAD")
    if ancestor.returncode != 0:
        details = ancestor.stderr.strip()
        suffix = f": {details}" if details else ""
        raise ValueError(f"cannot verify review_base_sha ancestry{suffix}")


def current_git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", os.fspath(root), "rev-parse", "--verify", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    head = result.stdout.strip()
    if result.returncode != 0 or not GIT_SHA_RE.fullmatch(head):
        details = result.stderr.strip()
        suffix = f": {details}" if details else ""
        raise ValueError(f"cannot resolve current Git HEAD{suffix}")
    return head


def _capture_review_snapshot(paper_id: str) -> dict[str, Any]:
    """Capture every mutable input that must stay stable while the deep gate runs."""

    if not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id):
        raise ValueError(f"paper id must be kebab-case: {paper_id}")
    matches = sorted(PAPERS.glob(f"*/{paper_id}/{METADATA_FILE}"))
    if len(matches) != 1:
        raise ValueError(f"paper id must resolve exactly once: {paper_id}")
    metadata_path = matches[0]
    metadata_text = metadata_path.read_text(encoding="utf-8")
    metadata = load_yaml_text(metadata_text, str(metadata_path))
    if metadata.get("reading_status") != "draft":
        raise ValueError("review receipt requires reading_status=draft")
    paper_dir = metadata_path.parent
    source = paper_dir / SOURCE_FILE
    translation = paper_dir / TRANSLATION_FILE
    policy_path = ROOT / "docs/translation-policy.md"
    if not source.is_file() or not translation.is_file():
        raise ValueError("review receipt requires source.pdf and translation.md")
    if not policy_path.is_file():
        raise ValueError("review receipt requires docs/translation-policy.md")
    review_head_sha = current_git_head(ROOT)
    review_gate_sha = review_gate_manifest_sha256(ROOT)
    committed_review_gate_sha = review_gate_manifest_sha256(
        ROOT, review_head_sha
    )
    if review_gate_sha != committed_review_gate_sha:
        raise ValueError(
            "review gate inputs differ from review_head_sha; commit the gate "
            "implementation and workflow before generating a receipt"
        )
    return {
        "metadata_path": metadata_path,
        "metadata_text": metadata_text,
        "source_sha256": sha256_file(source),
        "translation_sha256": sha256_file(translation),
        "assets_manifest_sha256": assets_manifest_sha256(paper_dir, ROOT),
        "translation_policy_sha256": sha256_file(policy_path),
        "review_metadata_sha256": review_metadata_sha256(metadata),
        "review_gate_manifest_sha256": review_gate_sha,
        "review_head_sha": review_head_sha,
    }


def _build_review_receipt_from_snapshot(
    paper_id: str,
    review_action: str,
    translator: str,
    reviewer: str,
    review_base_sha: str,
    checks: list[str],
    findings: list[str],
    authorial_voice: dict[str, int],
    waiver_records: dict[str, dict[str, Any]],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": REVIEW_RECEIPT_SCHEMA_VERSION,
        "paper_id": paper_id,
        "source_sha256": snapshot["source_sha256"],
        "translation_sha256": snapshot["translation_sha256"],
        "assets_manifest_sha256": snapshot["assets_manifest_sha256"],
        "review_metadata_sha256": snapshot["review_metadata_sha256"],
        "review_action": review_action,
        "translator": translator,
        "reviewer": reviewer,
        "review_base_sha": review_base_sha,
        "review_head_sha": snapshot["review_head_sha"],
        "findings": sorted(findings),
        "authorial_voice": authorial_voice,
        "waivers": waiver_records,
    }
    receipt["fingerprint"] = review_receipt_fingerprint(receipt)
    return validate_review_receipt(receipt, f"review receipt for {paper_id}")


def _validate_review_checklist(checks: list[str]) -> None:
    if not isinstance(checks, list) or any(
        not isinstance(check, str) for check in checks
    ):
        raise ValueError("review receipt checks must be a list of strings")
    if set(checks) == REQUIRED_REVIEW_CHECKS and len(checks) == len(set(checks)):
        return
    missing = sorted(REQUIRED_REVIEW_CHECKS - set(checks))
    unexpected = sorted(set(checks) - REQUIRED_REVIEW_CHECKS)
    details: list[str] = []
    if missing:
        details.append("missing: " + ", ".join(missing))
    if unexpected:
        details.append("unexpected: " + ", ".join(unexpected))
    raise ValueError(
        "review receipt requires every checklist item exactly once"
        + (f" ({'; '.join(details)})" if details else "")
    )


def _parse_waiver_approvals(waivers: list[str]) -> dict[str, str]:
    approved: dict[str, str] = {}
    for raw_waiver in waivers:
        if not isinstance(raw_waiver, str):
            raise ValueError("acceptance waiver approvals must be strings")
        category, separator, fingerprint = raw_waiver.strip().partition("=")
        if not separator or category not in ACCEPTANCE_WAIVERS:
            raise ValueError(
                "acceptance waivers must use category=<reviewed-fingerprint> for: "
                + ", ".join(sorted(ACCEPTANCE_WAIVERS))
            )
        if not SHA256_RE.fullmatch(fingerprint):
            raise ValueError(
                f"acceptance waiver fingerprint for {category} must be lowercase SHA-256"
            )
        if category in approved:
            raise ValueError(f"duplicate acceptance waiver approval: {category}")
        approved[category] = fingerprint
    return approved


def _assert_waiver_approvals_match(
    approved: dict[str, str],
    waiver_records: dict[str, dict[str, Any]],
) -> None:
    observed = {
        category: record["fingerprint"]
        for category, record in waiver_records.items()
    }
    if observed == approved:
        return
    missing = observed.keys() - approved.keys()
    unused = approved.keys() - observed.keys()
    changed = {
        category
        for category in observed.keys() & approved.keys()
        if observed[category] != approved[category]
    }
    details: list[str] = []
    if missing:
        details.append(
            "unapproved waiver candidates: "
            + ", ".join(
                f"{category}={observed[category]}" for category in sorted(missing)
            )
        )
    if unused:
        details.append(
            "requested waivers have no current candidates: "
            + ", ".join(sorted(unused))
        )
    details.extend(
        "approved waiver fingerprint changed: "
        f"{category}:{approved[category]}:{observed[category]}"
        for category in sorted(changed)
    )
    raise ValueError("; ".join(details))


def build_review_receipt(
    paper_id: str,
    review_action: str,
    translator: str,
    reviewer: str,
    review_base_sha: str,
    checks: list[str],
    findings: list[str],
    authorial_voice: dict[str, int],
    waiver_records: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a content-bound reviewer attestation without mutating the repository."""

    _validate_review_checklist(checks)
    validate_review_base_commit(ROOT, review_base_sha)
    snapshot = _capture_review_snapshot(paper_id)
    return _build_review_receipt_from_snapshot(
        paper_id,
        review_action,
        translator,
        reviewer,
        review_base_sha,
        checks,
        findings,
        authorial_voice,
        waiver_records or {},
        snapshot,
    )


def emit_review_receipt(
    paper_id: str,
    review_action: str,
    translator: str,
    reviewer: str,
    review_base_sha: str,
    checks: list[str],
    findings: list[str],
    authorial_voice: dict[str, int],
    waivers: list[str],
) -> int:
    """Run the scoped deep gate and emit a pure-YAML content-bound receipt."""

    if not findings:
        print(
            "ERROR: new review receipts require at least one --finding with "
            "the review disposition",
            file=sys.stderr,
        )
        return 1
    try:
        approved_waivers = _parse_waiver_approvals(waivers)
        before_snapshot = _capture_review_snapshot(paper_id)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    environment = os.environ.copy()
    for internal_key in VALIDATION_INTERNAL_ENV_KEYS:
        environment.pop(internal_key, None)
    environment["PYTHON"] = sys.executable
    environment["DEEP_VALIDATION"] = "1"
    with tempfile.TemporaryDirectory(
        prefix="db-papers-review-receipt-evidence-"
    ) as temporary:
        evidence_file = Path(temporary) / "observed.tsv"
        evidence_file.write_text("", encoding="utf-8")
        completed = subprocess.run(
            [
                "bash",
                "scripts/validate_translations.sh",
                "--paper-id",
                paper_id,
                "--acceptance-discovery",
                "--acceptance-evidence-file",
                os.fspath(evidence_file),
                "--acceptance-paper-id",
                paper_id,
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        waiver_records: dict[str, dict[str, Any]] = {}
        evidence_error: OSError | ValueError | None = None
        if completed.returncode == 0:
            try:
                waiver_records = build_waiver_records(
                    read_observed_tsv(evidence_file)
                )
                _assert_waiver_approvals_match(
                    approved_waivers, waiver_records
                )
            except (OSError, ValueError) as exc:
                evidence_error = exc
    if completed.returncode != 0:
        details = "\n".join(
            part.strip()
            for part in (completed.stdout, completed.stderr)
            if part.strip()
        )
        print("ERROR: paper-check failed before review receipt", file=sys.stderr)
        if details:
            print(details, file=sys.stderr)
        return 1
    if evidence_error is not None:
        print(
            f"ERROR: review waiver evidence failed: {evidence_error}",
            file=sys.stderr,
        )
        return 1
    try:
        after_snapshot = _capture_review_snapshot(paper_id)
        if after_snapshot != before_snapshot:
            raise ValueError(
                "review snapshot changed while paper-check was running; "
                "repeat the review receipt step on stable inputs"
            )
        _validate_review_checklist(checks)
        validate_review_base_commit(ROOT, review_base_sha)
        receipt = _build_review_receipt_from_snapshot(
            paper_id,
            review_action,
            translator,
            reviewer,
            review_base_sha,
            checks,
            findings,
            authorial_voice,
            waiver_records,
            after_snapshot,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(dump_yaml(receipt), end="")
    return 0


def acceptance_preflight(
    paper_id: str, approved_waivers: dict[str, str]
) -> tuple[bool, str, dict[str, dict[str, Any]]]:
    """Run discovery and translated-grade gates before mutating authoritative state.

    ``validate_translations.sh`` writes exact candidates to the TSV named by
    ``ACCEPTANCE_EVIDENCE_FILE``.  The discovery pass runs while the paper is
    still a draft.  The second pass receives the resulting item-level evidence
    through ``ACCEPTANCE_RECORDED_WAIVERS`` and is forced to translated severity.
    This two-pass protocol lets mechanical candidates be reviewed without ever
    temporarily claiming the paper is accepted.
    """

    matches = sorted(PAPERS.glob(f"*/{paper_id}/{TRANSLATION_FILE}"))
    if len(matches) != 1:
        return False, f"ERROR: paper id must resolve exactly once: {paper_id}", {}
    translation = matches[0]
    output: list[str] = []
    base_env = os.environ.copy()
    for internal_key in VALIDATION_INTERNAL_ENV_KEYS:
        base_env.pop(internal_key, None)
    base_env.update(
        {
            "PYTHON": sys.executable,
            "DEEP_VALIDATION": "1",
        }
    )
    initial_commands = [
        [sys.executable, "scripts/papers.py", "validate", "--paper-id", paper_id],
        [
            sys.executable,
            "scripts/normalize_translation_headers.py",
            "--check",
            "--paper-id",
            paper_id,
        ],
    ]
    for command in initial_commands:
        if not _run_preflight_command(command, base_env, output):
            return False, "\n".join(output), {}

    with tempfile.TemporaryDirectory(prefix="db-papers-acceptance-evidence-") as temporary:
        evidence_root = Path(temporary)
        discovery_file = evidence_root / "discovery.tsv"
        translated_file = evidence_root / "translated.tsv"
        discovery_file.write_text("", encoding="utf-8")
        translated_file.write_text("", encoding="utf-8")

        discovery_env = base_env.copy()
        discovery_command = [
            "bash",
            "scripts/validate_translations.sh",
            "--paper-id",
            paper_id,
            "--acceptance-discovery",
            "--acceptance-evidence-file",
            os.fspath(discovery_file),
            "--acceptance-paper-id",
            paper_id,
        ]
        if not _run_preflight_command(
            discovery_command, discovery_env, output
        ):
            return False, "\n".join(output), {}

        try:
            waiver_records = build_waiver_records(read_observed_tsv(discovery_file))
        except (OSError, ValueError) as exc:
            output.append(f"ERROR: cannot read acceptance evidence: {exc}")
            return False, "\n".join(output), {}
        observed_fingerprints = {
            category: record["fingerprint"] for category, record in waiver_records.items()
        }
        if observed_fingerprints != approved_waivers:
            missing = observed_fingerprints.keys() - approved_waivers.keys()
            unused = approved_waivers.keys() - observed_fingerprints.keys()
            changed = {
                category
                for category in observed_fingerprints.keys() & approved_waivers.keys()
                if observed_fingerprints[category] != approved_waivers[category]
            }
            if missing:
                output.append(
                    "ERROR: unapproved waiver candidates: "
                    + ", ".join(
                        f"{category}={observed_fingerprints[category]}"
                        for category in sorted(missing)
                    )
                )
            if unused:
                output.append(
                    "ERROR: requested waivers have no current candidates: "
                    + ", ".join(sorted(unused))
                )
            for category in sorted(changed):
                output.append(
                    "ERROR: approved waiver fingerprint changed: "
                    f"{category}:{approved_waivers[category]}:"
                    f"{observed_fingerprints[category]}"
                )
            return False, "\n".join(output), waiver_records

        translated_env = base_env.copy()
        translated_command = [
            "bash",
            "scripts/validate_translations.sh",
            "--paper-id",
            paper_id,
            "--acceptance-evidence-file",
            os.fspath(translated_file),
            "--acceptance-paper-id",
            paper_id,
            "--acceptance-target-status",
            "translated",
            "--acceptance-recorded-waivers",
            encode_waiver_records(waiver_records),
        ]
        if not _run_preflight_command(
            translated_command, translated_env, output
        ):
            return False, "\n".join(output), waiver_records
        try:
            translated_records = build_waiver_records(read_observed_tsv(translated_file))
            _reviewed, mismatches = compare_waiver_records(
                waiver_records, translated_records
            )
        except (OSError, ValueError) as exc:
            output.append(f"ERROR: cannot verify translated acceptance evidence: {exc}")
            return False, "\n".join(output), waiver_records
        if waiver_records != translated_records and not mismatches:
            output.append(
                "ERROR: raw waiver diagnostics changed between acceptance passes "
                "while semantic findings stayed constant"
            )
            return False, "\n".join(output), waiver_records
        if mismatches:
            output.extend(f"ERROR: waiver evidence {item}" for item in mismatches)
            return False, "\n".join(output), waiver_records

        mathjax_module = os.fspath(ROOT / "node_modules/mathjax")
        mathjax_command = [
            sys.executable,
            "scripts/verify_math_rendering.py",
            "--mathjax-module",
            mathjax_module,
            translation.relative_to(ROOT).as_posix(),
        ]
        if not _run_preflight_command(mathjax_command, translated_env, output):
            return False, "\n".join(output), waiver_records

        github_command = [
            sys.executable,
            "scripts/verify_math_rendering.py",
            "--github",
            translation.relative_to(ROOT).as_posix(),
        ]
        if not _run_preflight_command(github_command, translated_env, output):
            return False, "\n".join(output), waiver_records

    return True, "\n".join(output), waiver_records


def _assert_acceptance_snapshot(
    *,
    ledger_path: Path,
    expected_ledger: str,
    metadata_path: Path,
    expected_metadata: str,
    source: Path,
    source_sha256: str,
    translation: Path,
    translation_sha256: str,
    assets_sha256: str,
    policy_path: Path,
    policy_sha256: str,
    review_gate_sha256: str,
    receipt_path: Path,
    expected_receipt: str,
    expected_head_sha: str,
) -> None:
    if current_git_head(ROOT) != expected_head_sha:
        raise ValueError("Git HEAD changed during acceptance")
    if ledger_path.read_text(encoding="utf-8") != expected_ledger:
        raise ValueError("acceptance ledger changed concurrently")
    if metadata_path.read_text(encoding="utf-8") != expected_metadata:
        raise ValueError("paper.yaml changed concurrently")
    if sha256_file(source) != source_sha256:
        raise ValueError("source.pdf changed during acceptance")
    if sha256_file(translation) != translation_sha256:
        raise ValueError("translation.md changed during acceptance")
    if assets_manifest_sha256(metadata_path.parent, ROOT) != assets_sha256:
        raise ValueError("assets changed during acceptance")
    if sha256_file(policy_path) != policy_sha256:
        raise ValueError("translation policy changed during acceptance")
    if review_gate_manifest_sha256(ROOT) != review_gate_sha256:
        raise ValueError("review gate changed during acceptance")
    if receipt_path.read_text(encoding="utf-8") != expected_receipt:
        raise ValueError("review receipt changed during acceptance")


def _rollback_attempted_writes(
    attempted: list[tuple[Path, str, str]]
) -> list[str]:
    errors: list[str] = []
    for path, original, expected_write in reversed(attempted):
        try:
            current = path.read_text(encoding="utf-8")
            if current == original:
                continue
            if current != expected_write:
                errors.append(f"{path}: changed concurrently; refusing to overwrite")
                continue
            atomic_write_text(path, original)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    return errors


def _accept_record_locked(
    paper_id: str,
    review_receipt_path: Path,
) -> int:
    journal_path = _acceptance_journal_path(ROOT)
    if _acceptance_transaction_markers(ROOT):
        raise ValueError(
            "an unfinished acceptance transaction already exists; "
            "run recover-acceptance first"
        )
    paths = configured_paths(ROOT)
    ledger_path = paths["acceptance_ledger"]
    matches = sorted(PAPERS.glob(f"*/{paper_id}/{paths['metadata'].name}"))
    if len(matches) != 1:
        raise ValueError(f"paper id must resolve exactly once: {paper_id}")
    metadata_path = matches[0]
    original_ledger = ledger_path.read_text(encoding="utf-8")
    ledger = validate_acceptance_ledger(
        load_yaml_text(original_ledger, str(ledger_path)), str(ledger_path)
    )
    original_metadata = metadata_path.read_text(encoding="utf-8")
    data = load_yaml_text(original_metadata, str(metadata_path))
    if data.get("reading_status") != "draft":
        raise ValueError(
            "acceptance requires reading_status=draft; changed or re-reviewed "
            "translated papers must transition to draft first"
        )
    source = metadata_path.parent / paths["source"].name
    translation = metadata_path.parent / paths["translation"].name
    policy_path = ROOT / "docs/translation-policy.md"
    if not source.is_file() or not translation.is_file():
        raise ValueError("acceptance requires source.pdf and translation.md")
    original_receipt = review_receipt_path.read_text(encoding="utf-8")
    receipt = validate_review_receipt(
        load_yaml_text(original_receipt, str(review_receipt_path)),
        str(review_receipt_path),
    )
    if receipt["schema_version"] != REVIEW_RECEIPT_SCHEMA_VERSION:
        raise ValueError(
            "accept requires a receipt generated with the current review "
            f"schema v{REVIEW_RECEIPT_SCHEMA_VERSION}"
        )
    if receipt["paper_id"] != paper_id:
        raise ValueError("review receipt paper_id does not match --id")
    validate_review_base_commit(ROOT, receipt["review_base_sha"])
    approved_waivers = {
        category: record["fingerprint"]
        for category, record in receipt["waivers"].items()
    }
    expected_head_sha = current_git_head(ROOT)
    if receipt["review_head_sha"] != expected_head_sha:
        raise ValueError(
            "review receipt review_head_sha does not match the current Git HEAD"
        )

    source_hash = sha256_file(source)
    translation_hash = sha256_file(translation)
    assets_hash = assets_manifest_sha256(metadata_path.parent, ROOT)
    policy_hash = sha256_file(policy_path)
    review_gate_hash = review_gate_manifest_sha256(ROOT)
    current_receipt_values = {
        "source_sha256": source_hash,
        "translation_sha256": translation_hash,
        "assets_manifest_sha256": assets_hash,
        "review_metadata_sha256": review_metadata_sha256(
            data,
            receipt["schema_version"],
        ),
    }
    for key, current_value in current_receipt_values.items():
        if receipt[key] != current_value:
            raise ValueError(
                f"review receipt {key} does not match the current review snapshot"
            )
    committed_gate_hash = review_gate_manifest_sha256(
        ROOT, receipt["review_head_sha"]
    )
    if review_gate_hash != committed_gate_hash:
        raise ValueError(
            "current review gate and translation policy cannot be reproduced "
            "from review_head_sha"
        )

    accepted, details, waiver_records = acceptance_preflight(paper_id, approved_waivers)
    if not accepted:
        raise ValueError(f"acceptance preflight failed\n{details}".rstrip())
    if waiver_records != receipt["waivers"]:
        raise ValueError(
            "review receipt waiver evidence does not match the current validator output"
        )

    _assert_acceptance_snapshot(
        ledger_path=ledger_path,
        expected_ledger=original_ledger,
        metadata_path=metadata_path,
        expected_metadata=original_metadata,
        source=source,
        source_sha256=source_hash,
        translation=translation,
        translation_sha256=translation_hash,
        assets_sha256=assets_hash,
        policy_path=policy_path,
        policy_sha256=policy_hash,
        review_gate_sha256=review_gate_hash,
        receipt_path=review_receipt_path,
        expected_receipt=original_receipt,
        expected_head_sha=expected_head_sha,
    )

    ledger["entries"][paper_id] = receipt
    referenced_snapshots = {
        entry["review_snapshot"]
        for entry in ledger["entries"].values()
        if entry.get("schema_version") == 1
    }
    ledger["review_snapshots"] = {
        snapshot_id: snapshot
        for snapshot_id, snapshot in ledger["review_snapshots"].items()
        if snapshot_id in referenced_snapshots
    }
    data["reading_status"] = "translated"
    accepted_ledger = dump_yaml(ledger)
    accepted_metadata = dump_yaml(data)
    journal = _build_acceptance_journal(
        paper_id=paper_id,
        ledger_path=ledger_path,
        original_ledger=original_ledger,
        accepted_ledger=accepted_ledger,
        metadata_path=metadata_path,
        original_metadata=original_metadata,
        accepted_metadata=accepted_metadata,
        source=source,
        source_sha256=source_hash,
        translation=translation,
        translation_sha256=translation_hash,
        assets_manifest_sha256_value=assets_hash,
        policy_path=policy_path,
        policy_sha256=policy_hash,
        review_gate_sha256=review_gate_hash,
        git_head=expected_head_sha,
    )
    expected_journal_text = dump_yaml(journal)
    attempted: list[tuple[Path, str, str]] = []
    journal_written = False

    try:
        journal_path = _write_acceptance_journal(journal)
        journal_written = True
        attempted.append((ledger_path, original_ledger, accepted_ledger))
        atomic_write_text(ledger_path, accepted_ledger)
        _assert_acceptance_snapshot(
            ledger_path=ledger_path,
            expected_ledger=accepted_ledger,
            metadata_path=metadata_path,
            expected_metadata=original_metadata,
            source=source,
            source_sha256=source_hash,
            translation=translation,
            translation_sha256=translation_hash,
            assets_sha256=assets_hash,
            policy_path=policy_path,
            policy_sha256=policy_hash,
            review_gate_sha256=review_gate_hash,
            receipt_path=review_receipt_path,
            expected_receipt=original_receipt,
            expected_head_sha=expected_head_sha,
        )
        attempted.append((metadata_path, original_metadata, accepted_metadata))
        atomic_write_text(metadata_path, accepted_metadata)
        _assert_acceptance_snapshot(
            ledger_path=ledger_path,
            expected_ledger=accepted_ledger,
            metadata_path=metadata_path,
            expected_metadata=accepted_metadata,
            source=source,
            source_sha256=source_hash,
            translation=translation,
            translation_sha256=translation_hash,
            assets_sha256=assets_hash,
            policy_path=policy_path,
            policy_sha256=policy_hash,
            review_gate_sha256=review_gate_hash,
            receipt_path=review_receipt_path,
            expected_receipt=original_receipt,
            expected_head_sha=expected_head_sha,
        )
        recorded = load_acceptance_ledger(ledger_path)["entries"].get(paper_id)
        if recorded != ledger["entries"][paper_id]:
            raise ValueError("acceptance ledger failed post-write verification")
        _assert_acceptance_snapshot(
            ledger_path=ledger_path,
            expected_ledger=accepted_ledger,
            metadata_path=metadata_path,
            expected_metadata=accepted_metadata,
            source=source,
            source_sha256=source_hash,
            translation=translation,
            translation_sha256=translation_hash,
            assets_sha256=assets_hash,
            policy_path=policy_path,
            policy_sha256=policy_hash,
            review_gate_sha256=review_gate_hash,
            receipt_path=review_receipt_path,
            expected_receipt=original_receipt,
            expected_head_sha=expected_head_sha,
        )
        if journal_path.read_text(encoding="utf-8") != expected_journal_text:
            raise ValueError("acceptance transaction journal changed concurrently")
    except BaseException:
        rollback_errors = _rollback_attempted_writes(attempted)
        if rollback_errors:
            print("ERROR: rollback failed: " + "; ".join(rollback_errors), file=sys.stderr)
        elif attempted:
            print("Acceptance changes were rolled back.", file=sys.stderr)
        if journal_written and not rollback_errors:
            try:
                if journal_path.read_text(encoding="utf-8") != expected_journal_text:
                    raise OSError(
                        "journal changed concurrently; refusing to remove it"
                    )
                _remove_acceptance_journal(
                    journal_path,
                    expected_journal_text,
                )
            except OSError as cleanup_error:
                markers = _acceptance_transaction_markers(ROOT)
                recovery = (
                    "; recovery marker retained at "
                    + ", ".join(
                        path.relative_to(ROOT).as_posix() for path in markers
                    )
                    + "; run recover-acceptance --mode rollback"
                    if markers
                    else "; no recovery marker remains, so do not run recovery"
                )
                print(
                    "ERROR: rollback completed but transaction cleanup failed"
                    f"{recovery}: {cleanup_error}",
                    file=sys.stderr,
                )
        raise

    try:
        _remove_acceptance_journal(journal_path, expected_journal_text)
    except OSError as exc:
        markers = _acceptance_transaction_markers(ROOT)
        if markers:
            rendered_markers = ", ".join(
                path.relative_to(ROOT).as_posix() for path in markers
            )
            recovery = (
                f"recovery marker retained at {rendered_markers}; run "
                "recover-acceptance --mode commit"
            )
        else:
            recovery = (
                "no recovery marker remains; the authoritative files are in "
                "the accepted state, so do not run recovery"
            )
        raise ValueError(
            "acceptance files were written, but transaction cleanup failed; "
            f"{recovery}: {exc}"
        ) from exc

    print(f"Accepted {paper_id}; hashes recorded in {ledger_path.relative_to(ROOT)}.")
    return 0


def accept_record(
    paper_id: str,
    review_receipt_path: Path,
) -> int:
    try:
        with sigterm_as_exception(), acceptance_lock(ROOT):
            return _accept_record_locked(paper_id, review_receipt_path)
    except (AcceptanceInterrupted, KeyboardInterrupt, OSError, ValueError) as exc:
        details = str(exc).strip() or f"acceptance interrupted by {type(exc).__name__}"
        print(f"ERROR: {details}", file=sys.stderr)
        return 1


def _assert_recovery_file_states(
    files: dict[str, dict[str, str]],
    expected: dict[str, str],
) -> None:
    """Refuse to continue after either authoritative file changes."""

    for relative_path in files:
        current = (ROOT / relative_path).read_text(encoding="utf-8")
        if current != expected[relative_path]:
            raise ValueError(
                f"{relative_path} changed while acceptance recovery was running; "
                "refusing to overwrite"
            )


def _assert_recovery_context(context: dict[str, str]) -> None:
    """Recheck every content-bound input before recovery can be committed."""

    context_checks = {
        "git HEAD": (
            current_git_head(ROOT),
            context["git_head"],
        ),
        "source.pdf": (
            sha256_file(ROOT / context["source_path"]),
            context["source_sha256"],
        ),
        "translation.md": (
            sha256_file(ROOT / context["translation_path"]),
            context["translation_sha256"],
        ),
        "assets": (
            assets_manifest_sha256(
                (ROOT / context["translation_path"]).parent,
                ROOT,
            ),
            context["assets_manifest_sha256"],
        ),
        "translation policy": (
            sha256_file(ROOT / context["translation_policy_path"]),
            context["translation_policy_sha256"],
        ),
        "review gate": (
            review_gate_manifest_sha256(ROOT),
            context["review_gate_manifest_sha256"],
        ),
    }
    mismatched = [
        label
        for label, (current, expected) in context_checks.items()
        if current != expected
    ]
    if mismatched:
        raise ValueError(
            "acceptance inputs changed after the interrupted transaction: "
            + ", ".join(mismatched)
            + "; use mode=rollback"
        )


def _recover_acceptance_locked(mode: str) -> int:
    journal_path = _unfinished_acceptance_marker(ROOT)
    if journal_path is None:
        raise ValueError("no unfinished acceptance transaction exists")
    if not journal_path.is_file():
        raise ValueError(
            f"acceptance transaction marker is not a file: {journal_path}"
        )
    journal_text = journal_path.read_text(encoding="utf-8")
    journal = _validate_acceptance_journal(
        load_yaml_text(journal_text, str(journal_path)),
        root=ROOT,
        label=str(journal_path),
    )
    target_state = "accepted" if mode == "commit" else "original"
    files = journal["files"]
    context = journal["context"]
    current_contents: dict[str, str] = {}
    for relative_path, record in files.items():
        path = ROOT / relative_path
        current = path.read_text(encoding="utf-8")
        if current not in {record["original"], record["accepted"]}:
            raise ValueError(
                f"{relative_path} changed outside the unfinished transaction; "
                "refusing recovery"
            )
        current_contents[relative_path] = current

    if mode == "commit":
        _assert_recovery_context(context)
        ledger_relative = "config/acceptance.yaml"
        accepted_ledger = validate_acceptance_ledger(
            load_yaml_text(
                files[ledger_relative]["accepted"],
                f"{journal_path}: accepted ledger",
            ),
            f"{journal_path}: accepted ledger",
        )
        accepted_entry = accepted_ledger["entries"].get(journal["paper_id"])
        if not accepted_entry:
            raise ValueError(
                "transaction target lacks a content-bound acceptance entry"
            )
        receipt = accepted_entry
        bound_values = {
            "source_sha256": context["source_sha256"],
            "translation_sha256": context["translation_sha256"],
            "assets_manifest_sha256": context["assets_manifest_sha256"],
        }
        if receipt["schema_version"] == 1:
            bound_values.update(
                {
                    "translation_policy_sha256": context[
                        "translation_policy_sha256"
                    ],
                    "review_gate_manifest_sha256": context[
                        "review_gate_manifest_sha256"
                    ],
                }
            )
        elif receipt["review_head_sha"] != context["git_head"]:
            raise ValueError(
                "transaction target review_head_sha does not match its context"
            )
        for key, expected in bound_values.items():
            value = receipt.get(key)
            if value != expected:
                raise ValueError(
                    f"transaction target {key} does not match its context"
                )
        if (
            receipt["schema_version"] >= 2
            and review_gate_manifest_sha256(ROOT, receipt["review_head_sha"])
            != context["review_gate_manifest_sha256"]
        ):
            raise ValueError(
                "transaction target review gate cannot be reconstructed from "
                "review_head_sha"
            )

    ordered_paths = list(files)
    if mode == "rollback":
        ordered_paths.reverse()
    for relative_path in ordered_paths:
        _assert_recovery_file_states(files, current_contents)
        target = files[relative_path][target_state]
        if current_contents[relative_path] != target:
            atomic_write_text(ROOT / relative_path, target)
            current_contents[relative_path] = target

    expected_target_contents = {
        relative_path: record[target_state]
        for relative_path, record in files.items()
    }
    _assert_recovery_file_states(files, expected_target_contents)
    if mode == "commit":
        _assert_recovery_context(context)
        metadata_relative = next(
            relative_path
            for relative_path in files
            if relative_path != "config/acceptance.yaml"
        )
        metadata = load_yaml_text(
            files[metadata_relative]["accepted"],
            f"{journal_path}: accepted metadata",
        )
        if metadata.get("reading_status") != "translated":
            raise ValueError(
                "transaction target metadata is not reading_status=translated"
            )
        accepted_entry = load_acceptance_ledger(
            ROOT / "config/acceptance.yaml"
        )["entries"].get(journal["paper_id"])
        if not accepted_entry:
            raise ValueError("recovered acceptance entry failed validation")
        if (
            accepted_entry["review_metadata_sha256"]
            != review_metadata_sha256(
                metadata,
                accepted_entry["schema_version"],
            )
        ):
            raise ValueError(
                "transaction target metadata does not match its review receipt"
            )
    _assert_recovery_file_states(files, expected_target_contents)
    if mode == "commit":
        _assert_recovery_context(context)
    if journal_path.read_text(encoding="utf-8") != journal_text:
        raise ValueError("acceptance transaction journal changed during recovery")
    _remove_acceptance_journal(journal_path, journal_text)
    print(
        f"Recovered acceptance transaction for {journal['paper_id']} "
        f"using mode={mode}."
    )
    return 0


def recover_acceptance(mode: str) -> int:
    try:
        with sigterm_as_exception(), acceptance_lock(ROOT):
            return _recover_acceptance_locked(mode)
    except (AcceptanceInterrupted, KeyboardInterrupt, OSError, ValueError) as exc:
        details = str(exc).strip() or f"recovery interrupted by {type(exc).__name__}"
        print(f"ERROR: {details}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate minimal paper metadata")
    validate_parser.add_argument("--paper-id", help="validate only one paper record")
    subparsers.add_parser("status", help="print tab-separated rows for deep validation")
    queue_parser = subparsers.add_parser(
        "review-queue", help="print the deterministic risk-first deep-review queue"
    )
    queue_parser.add_argument("--limit", type=int)
    config_parser = subparsers.add_parser("config", help="print a validated project config value")
    config_parser.add_argument("--key", required=True)
    config_parser.add_argument("--paper-id")
    manifest_parser = subparsers.add_parser(
        "validation-manifest", help="print one batched snapshot for deep translation validation"
    )
    manifest_parser.add_argument("--paper-id")
    manifest_parser.add_argument("--acceptance-paper-id", help=argparse.SUPPRESS)
    manifest_parser.add_argument(
        "--acceptance-target-status", default="", help=argparse.SUPPRESS
    )
    manifest_parser.add_argument(
        "--acceptance-recorded-waivers", default="", help=argparse.SUPPRESS
    )
    catalog_parser = subparsers.add_parser("catalog", help="generate CATALOG.md")
    catalog_parser.add_argument("--check", action="store_true", help="fail if CATALOG.md is stale")
    new_parser = subparsers.add_parser("new", help="create a minimal unavailable paper record")
    new_parser.add_argument("--id", required=True, help="globally unique kebab-case paper id")
    new_parser.add_argument("--title", required=True, help="official paper title")
    new_parser.add_argument("--area", required=True, help="registered directory area")
    new_parser.add_argument(
        "--topic",
        action="append",
        required=True,
        dest="topics",
        help="registered topic; repeat as needed",
    )
    new_parser.add_argument("--url", required=True, help="authoritative source URL")
    receipt_parser = subparsers.add_parser(
        "review-receipt",
        help="run the scoped deep gate and emit a content-bound review receipt",
    )
    receipt_parser.add_argument("--id", required=True, dest="paper_id")
    receipt_parser.add_argument(
        "--review-action", required=True, choices=sorted(RUNTIME_REVIEW_ACTIONS)
    )
    receipt_parser.add_argument(
        "--translator",
        required=True,
        help="stable namespace:value identity of the translator or repairer",
    )
    receipt_parser.add_argument(
        "--reviewer",
        required=True,
        help="stable namespace:value identity of the independent PDF reviewer",
    )
    receipt_parser.add_argument(
        "--review-base-sha",
        required=True,
        help="40-character fixed baseline commit against which the review was performed",
    )
    receipt_parser.add_argument(
        "--check",
        action="append",
        default=[],
        choices=sorted(REQUIRED_REVIEW_CHECKS),
        help="attest one required review dimension; every dimension is required exactly once",
    )
    receipt_parser.add_argument(
        "--finding",
        action="append",
        required=True,
        help="record one repaired or verified finding; repeat as needed",
    )
    receipt_parser.add_argument(
        "--authorial-voice-source-items",
        required=True,
        type=int,
        help="valid source authorial I/we/my/our/us items after exclusions",
    )
    receipt_parser.add_argument(
        "--authorial-voice-verified-items",
        required=True,
        type=int,
        help="source authorial items verified in the final translation",
    )
    receipt_parser.add_argument(
        "--authorial-voice-shared-subject-merges",
        required=True,
        type=int,
        help="verified source items represented by an explicit shared Chinese subject",
    )
    receipt_parser.add_argument(
        "--waiver",
        action="append",
        default=[],
        metavar="CATEGORY=FINGERPRINT",
        help="attest one exact reviewed paper-check candidate-group fingerprint",
    )
    accept_parser = subparsers.add_parser("accept", help="record hashes after manual review and set translated")
    accept_parser.add_argument("--id", required=True, dest="paper_id")
    accept_parser.add_argument(
        "--review-receipt",
        required=True,
        type=Path,
        help="YAML receipt emitted by the independent reviewer",
    )
    recover_parser = subparsers.add_parser(
        "recover-acceptance",
        help="finish or roll back an interrupted two-file acceptance transaction",
    )
    recover_parser.add_argument(
        "--mode",
        required=True,
        choices=("commit", "rollback"),
    )
    args = parser.parse_args()

    if args.command == "validate":
        return validate(args.paper_id)
    if args.command == "status":
        return status_rows()
    if args.command == "review-queue":
        if args.limit is not None and args.limit < 1:
            parser.error("--limit must be positive")
        return review_queue(args.limit)
    if args.command == "config":
        return config_value(args.key, args.paper_id)
    if args.command == "validation-manifest":
        return validation_manifest(
            args.paper_id,
            preflight_paper_id=args.acceptance_paper_id,
            preflight_target_status=args.acceptance_target_status,
            preflight_waivers=args.acceptance_recorded_waivers,
        )
    if args.command == "catalog":
        return catalog(args.check)
    if args.command == "review-receipt":
        return emit_review_receipt(
            args.paper_id,
            args.review_action,
            args.translator,
            args.reviewer,
            args.review_base_sha,
            args.check,
            args.finding,
            {
                "source_valid_items": args.authorial_voice_source_items,
                "verified_items": args.authorial_voice_verified_items,
                "shared_subject_merges": args.authorial_voice_shared_subject_merges,
            },
            args.waiver,
        )
    if args.command == "accept":
        return accept_record(args.paper_id, args.review_receipt)
    if args.command == "recover-acceptance":
        return recover_acceptance(args.mode)
    return new_record(args.id, args.title, args.area, args.topics, args.url)


if __name__ == "__main__":
    raise SystemExit(main())
