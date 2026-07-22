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
from urllib.parse import quote

WAIVER_CATEGORIES = frozenset({"abridgement", "listings", "resources"})
WAIVER_EVIDENCE_VERSION = 4
WAIVER_EVIDENCE_V1_PYPDF_VERSION = "6.14.2"
WAIVER_EVIDENCE_V1_PDF_METRICS_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FINDING_RE = re.compile(r"^[a-z0-9][a-z0-9._:/%+-]*$")


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


def _subject(value: str) -> str:
    value = value.strip().casefold()
    if not value:
        raise ValueError("waiver finding subject must not be empty")
    return quote(value, safe="._-/+").lower()


def _subjects(value: str) -> list[str]:
    subjects = [_subject(item) for item in value.split(",")]
    if not subjects:
        raise ValueError("waiver finding subject list must not be empty")
    return subjects


def _abridgement_candidate_v1(
    translated_cjk: int,
    source_words: int,
) -> str | None:
    """Reproduce the frozen evidence-v1 integer threshold semantics."""

    if translated_cjk * 100 < source_words * 50:
        severity = "high"
        threshold = "0.50"
    elif translated_cjk * 100 < source_words * 75:
        severity = "moderate"
        threshold = "0.75"
    else:
        return None
    return (
        f"{severity} mechanical abridgement risk: "
        f"CJK/source-word ratio={translated_cjk}/{source_words} "
        f"(<{threshold}; extractor=pypdf-{WAIVER_EVIDENCE_V1_PYPDF_VERSION}; "
        f"metric=v{WAIVER_EVIDENCE_V1_PDF_METRICS_VERSION})"
    )


def _candidate_findings_v1(category: str, candidate: str) -> list[str]:
    """Return stable rule-and-subject identities for one raw diagnostic.

    Source and translation hashes already bind the reviewed content.  Finding
    identities therefore retain the rule and affected object while excluding
    extractor-dependent ratios, token samples, and window lengths.  Unknown
    diagnostics fail closed so new validator rules cannot silently inherit an
    existing waiver.
    """

    if category == "abridgement":
        match = re.fullmatch(
            r"(high|moderate) mechanical abridgement risk: "
            r"CJK/source-word ratio=(\d+)/([1-9]\d*) "
            r"\(<(0\.50|0\.75); extractor=pypdf-"
            + re.escape(WAIVER_EVIDENCE_V1_PYPDF_VERSION)
            + r"; metric=v"
            + str(WAIVER_EVIDENCE_V1_PDF_METRICS_VERSION)
            + r"\)",
            candidate,
        )
        if match:
            severity, translated_cjk, source_words, threshold = match.groups()
            expected = _abridgement_candidate_v1(
                int(translated_cjk), int(source_words)
            )
            if expected == candidate and threshold == (
                "0.50" if severity == "high" else "0.75"
            ):
                return [f"abridgement:{severity}"]
        raise ValueError(f"unknown abridgement waiver candidate: {candidate}")

    if not candidate.startswith("RISK: "):
        raise ValueError(f"{category} waiver candidate must start with 'RISK: '")
    diagnostic = candidate.removeprefix("RISK: ")

    if category == "listings":
        match = re.fullmatch(r"Listing ([1-9]\d*) fenced payload (.+)", diagnostic)
        if not match:
            raise ValueError(f"unknown listings waiver candidate: {candidate}")
        listing_number, detail = match.groups()
        rules = (
            (r"is suspiciously short \(\d+ non-space chars\)", "suspiciously-short"),
            (
                r"has weak key-token overlap with source candidate \(.+\)",
                "weak-key-token-overlap",
            ),
            (
                r"omits all brace/semicolon tokens present in source candidate",
                "missing-brace-semicolon-tokens",
            ),
            (
                r"has weak distinctive-identifier overlap with source candidate "
                r"\([0-9]+(?:\.[0-9]+)?\)",
                "weak-distinctive-identifier-overlap",
            ),
            (r"shares no literals with source candidate", "no-shared-literals"),
            (
                r"is short relative to source code candidate \(\d+/\d+\)",
                "short-relative-to-source",
            ),
        )
        for pattern, rule in rules:
            if re.fullmatch(pattern, detail):
                return [f"listing:{listing_number}:{rule}"]
        raise ValueError(f"unknown listings waiver candidate: {candidate}")

    if category != "resources":
        raise ValueError(f"unknown waiver category: {category!r}")

    match = re.fullmatch(
        r"orphan asset is not referenced by translation\.md: (.+)", diagnostic
    )
    if match:
        return [f"orphan-asset:{_subject(match.group(1))}"]

    match = re.fullmatch(
        r"source reference identifier (\S+) was normalized to 1 as a "
        r"contiguous numeric-series OCR candidate",
        diagnostic,
    )
    if match:
        return [f"source-reference-ocr-normalization:{_subject(match.group(1))}:1"]

    match = re.fullmatch(
        r"source reference identifiers were normalized by ordered contiguous "
        r"OCR evidence: (.+)",
        diagnostic,
    )
    if match:
        findings: list[str] = []
        for mapping in match.group(1).split(", "):
            mapping_match = re.fullmatch(
                r"([A-Za-z0-9]{1,2})->([1-9]\d*)",
                mapping,
            )
            if mapping_match is None:
                raise ValueError(
                    f"unknown resources waiver candidate: {candidate}"
                )
            source_identifier, normalized_identifier = mapping_match.groups()
            findings.append(
                "source-reference-ocr-normalization:"
                f"{_subject(source_identifier)}:{normalized_identifier}"
            )
        return findings

    match = re.fullmatch(
        r"source reference identifiers were normalized by complete ordered "
        r"delimiter-OCR evidence: (.+)",
        diagnostic,
    )
    if match:
        findings = []
        for mapping in match.group(1).split(", "):
            mapping_match = re.fullmatch(
                r"([\[\]()<>A-Za-z0-9.]{1,5})->([1-9]\d*)",
                mapping,
            )
            if mapping_match is None:
                raise ValueError(
                    f"unknown resources waiver candidate: {candidate}"
                )
            source_identifier, normalized_identifier = mapping_match.groups()
            findings.append(
                "source-reference-ocr-normalization:"
                f"{_subject(source_identifier)}:{normalized_identifier}"
            )
        return findings

    grouped_rules = (
        (
            r"source has duplicate reference identifier candidates: (.+)",
            "duplicate-source-reference",
        ),
        (
            r"translation has unmatched reference identifiers: (.+)",
            "unmatched-translation-reference",
        ),
        (
            r"translation reference content is suspiciously short for: (.+)",
            "short-translation-reference",
        ),
        (
            r"translation reference has low source-token overlap for: (.+)",
            "low-token-overlap-reference",
        ),
        (
            r"source numbered top-level section headings have no "
            r"translation-side heading candidates: (.+)",
            "missing-section-heading",
        ),
        (
            r"source body citation identifiers have no "
            r"translation-side candidate: (.+)",
            "missing-inline-citation",
        ),
    )
    for pattern, rule in grouped_rules:
        match = re.fullmatch(pattern, diagnostic)
        if match:
            return [f"{rule}:{subject}" for subject in _subjects(match.group(1))]

    if re.fullmatch(r"reference entry-count candidate differs \(\d+/\d+\)", diagnostic):
        return ["reference-entry-count-differs"]
    if diagnostic == "non-numbered bibliography is empty in translation":
        return ["non-numbered-bibliography-empty"]
    if diagnostic == "non-numbered bibliography has very low translation-side coverage":
        return ["non-numbered-bibliography-low-coverage"]
    if diagnostic == "source Abstract heading has no translation-side heading candidate":
        return ["missing-abstract-heading"]
    if diagnostic == "source Conclusion/Summary heading has no translation-side heading candidate":
        return ["missing-conclusion-summary-heading"]

    match = re.fullmatch(
        r"source (Figure|Table|Algorithm) ([1-9]\d*) has no formal "
        r"translation-side payload candidate",
        diagnostic,
    )
    if match:
        kind, number = match.groups()
        return [f"missing-formal-payload:{kind.casefold()}:{number}"]

    match = re.fullmatch(
        r"Figure ([1-9]\d*) has \d+ image candidates; verify subfigures "
        r"versus duplicate representations",
        diagnostic,
    )
    if match:
        return [f"multiple-image-candidates:figure:{match.group(1)}"]

    match = re.fullmatch(
        r"source equation \(([1-9]\d*)\) has no translation-side "
        r"display/formula candidate",
        diagnostic,
    )
    if match:
        return [f"missing-display-equation:{match.group(1)}"]

    if re.fullmatch(
        r"source has more unnumbered code-like block candidates than "
        r"translation fenced blocks \(\d+/\d+\)",
        diagnostic,
    ):
        return ["unnumbered-code-block-coverage"]

    raise ValueError(f"unknown resources waiver candidate: {candidate}")


def _author_key_ocr_mappings_v2(
    category: str,
    candidate: str,
) -> list[tuple[str, str]] | None:
    if category != "resources" or not candidate.startswith("RISK: "):
        return None
    diagnostic = candidate.removeprefix("RISK: ")
    match = re.fullmatch(
        r"source author-key reference identifiers were normalized by unique "
        r"bibliography-content OCR evidence: (.+)",
        diagnostic,
    )
    if match is None:
        return None

    mappings: list[tuple[str, str]] = []
    source_identifiers: set[str] = set()
    normalized_identifiers: set[str] = set()
    for mapping in match.group(1).split(", "):
        mapping_match = re.fullmatch(
            r"([A-Za-z][A-Za-z0-9+_.:-]{0,63})->"
            r"([A-Za-z][A-Za-z0-9+_.:-]{0,63})",
            mapping,
        )
        if mapping_match is None:
            raise ValueError(f"unknown resources waiver candidate: {candidate}")
        source_identifier, normalized_identifier = mapping_match.groups()
        source_identity = source_identifier.casefold()
        normalized_identity = normalized_identifier.casefold()
        if (
            source_identity == normalized_identity
            or source_identity in source_identifiers
            or normalized_identity in normalized_identifiers
        ):
            raise ValueError(f"unknown resources waiver candidate: {candidate}")
        source_identifiers.add(source_identity)
        normalized_identifiers.add(normalized_identity)
        mappings.append((source_identifier, normalized_identifier))
    return mappings


def _candidate_findings_v2(category: str, candidate: str) -> list[str]:
    """Extend frozen v1 evidence with author-key OCR content matching."""

    mappings = _author_key_ocr_mappings_v2(category, candidate)
    if mappings is not None:
        return [
            "source-reference-ocr-normalization:"
            f"{_subject(source_identifier)}:{_subject(normalized_identifier)}"
            for source_identifier, normalized_identifier in mappings
        ]

    return _candidate_findings_v1(category, candidate)


def _numeric_reference_ocr_candidates_v3(identifier: str) -> set[int]:
    """Reproduce the frozen evidence-v3 short-marker OCR semantics."""

    if identifier.isdigit() and len(identifier) <= 2:
        return {int(identifier)}
    compact = identifier.casefold().strip("[]()<>").replace(".", "")
    if not compact or len(compact) > 5:
        return set()
    variants = {compact}
    removable_leading = frozenset({"r", "p", "v", "m", "w", "i", "l", "1"})
    removable_trailing = frozenset({"i", "l", "1"})
    if compact[0] in removable_leading:
        variants.add(compact[1:])
    if compact[-1] in removable_trailing:
        variants.add(compact[:-1])
    if (
        len(compact) >= 2
        and compact[0] in removable_leading
        and compact[-1] in removable_trailing
    ):
        variants.add(compact[1:-1])

    translation = str.maketrans({"i": "1", "l": "1", "o": "0", "s": "5"})
    candidates: set[int] = set()
    for variant in variants:
        normalized = variant.translate(translation)
        if normalized.isdigit() and int(normalized) > 0:
            candidates.add(int(normalized))
    return candidates


def _numeric_reference_recovery_v3(
    category: str,
    candidate: str,
) -> tuple[int, list[tuple[str, str]]] | None:
    if category != "resources" or not candidate.startswith("RISK: "):
        return None
    diagnostic = candidate.removeprefix("RISK: ")
    match = re.fullmatch(
        r"source numeric references 1-([1-9]\d*) were recovered by complete "
        r"ordered two-column bibliography-content evidence; parsed markers: "
        r"(.+)",
        diagnostic,
    )
    if match is None:
        return None

    entry_count = int(match.group(1))
    if entry_count < 10:
        raise ValueError(f"unknown resources waiver candidate: {candidate}")
    mappings: list[tuple[str, str]] = []
    source_identifiers: set[str] = set()
    target_identifiers: set[str] = set()
    for mapping in match.group(2).split(", "):
        mapping_match = re.fullmatch(
            r"([\[\]()<>A-Za-z0-9.]{1,5})->([1-9]\d*)",
            mapping,
        )
        if mapping_match is None:
            raise ValueError(f"unknown resources waiver candidate: {candidate}")
        source_identifier, target_identifier = mapping_match.groups()
        source_identity = source_identifier.casefold()
        target_number = int(target_identifier)
        if (
            source_identity in source_identifiers
            or target_identifier in target_identifiers
            or target_number > entry_count
            or target_number not in _numeric_reference_ocr_candidates_v3(
                source_identifier
            )
        ):
            raise ValueError(f"unknown resources waiver candidate: {candidate}")
        source_identifiers.add(source_identity)
        target_identifiers.add(target_identifier)
        mappings.append((source_identifier, target_identifier))
    if len(mappings) < 3:
        raise ValueError(f"unknown resources waiver candidate: {candidate}")
    return entry_count, mappings


def _candidate_findings_v3(category: str, candidate: str) -> list[str]:
    """Extend frozen v2 evidence with complete numeric content recovery."""

    recovery = _numeric_reference_recovery_v3(category, candidate)
    if recovery is not None:
        entry_count, mappings = recovery
        findings = [
            f"source-reference-content-recovery:{index}"
            for index in range(1, entry_count + 1)
        ]
        findings.extend(
            "source-reference-marker-content-mapping:"
            f"{_subject(source_identifier)}:{target_identifier}"
            for source_identifier, target_identifier in mappings
        )
        return findings

    return _candidate_findings_v2(category, candidate)


def _candidate_findings_v4(category: str, candidate: str) -> list[str]:
    """Extend frozen v3 evidence with hierarchical equation numbers."""

    if category == "resources" and candidate.startswith("RISK: "):
        diagnostic = candidate.removeprefix("RISK: ")
        match = re.fullmatch(
            r"source equation \(([1-9]\d*(?:\.\d+)*)\) has no "
            r"translation-side display/formula candidate",
            diagnostic,
        )
        if match:
            return [f"missing-display-equation:{match.group(1)}"]

    return _candidate_findings_v3(category, candidate)


WAIVER_FINDING_PARSERS = {
    1: _candidate_findings_v1,
    2: _candidate_findings_v2,
    3: _candidate_findings_v3,
    4: _candidate_findings_v4,
}


def candidate_findings(
    category: str,
    candidate: str,
    *,
    evidence_version: int = WAIVER_EVIDENCE_VERSION,
) -> list[str]:
    parser = WAIVER_FINDING_PARSERS.get(evidence_version)
    if parser is None:
        raise ValueError(
            f"unsupported waiver evidence_version: {evidence_version!r}"
        )
    return parser(category, candidate)


def findings_for_candidates(
    category: str,
    candidates: Iterable[str],
    *,
    evidence_version: int = WAIVER_EVIDENCE_VERSION,
) -> list[str]:
    findings: dict[str, str] = {}
    author_key_targets: dict[str, str] = {}
    author_key_sources: dict[str, str] = {}
    for candidate in normalize_candidates(candidates):
        author_key_mappings = (
            _author_key_ocr_mappings_v2(category, candidate)
            if evidence_version in {2, 3, 4}
            else None
        )
        for source_identifier, normalized_identifier in author_key_mappings or []:
            source_identity = source_identifier.casefold()
            normalized_identity = normalized_identifier.casefold()
            previous_target = author_key_targets.get(source_identity)
            previous_source = author_key_sources.get(normalized_identity)
            if (
                previous_target is not None
                and previous_target != normalized_identity
            ) or (
                previous_source is not None
                and previous_source != source_identity
            ):
                raise ValueError(
                    "author-key OCR waiver candidates must form one global "
                    "one-to-one mapping"
                )
            author_key_targets[source_identity] = normalized_identity
            author_key_sources[normalized_identity] = source_identity
        for finding in candidate_findings(
            category,
            candidate,
            evidence_version=evidence_version,
        ):
            if not FINDING_RE.fullmatch(finding):
                raise ValueError(f"invalid waiver finding identity: {finding!r}")
            previous = findings.get(finding)
            if previous is not None:
                raise ValueError(
                    f"duplicate waiver finding {finding!r} from diagnostics "
                    f"{previous!r} and {candidate!r}"
                )
            findings[finding] = candidate
    return sorted(findings)


def waiver_fingerprint(
    category: str,
    candidates: Iterable[str],
    *,
    evidence_version: int = WAIVER_EVIDENCE_VERSION,
) -> str:
    if category not in WAIVER_CATEGORIES:
        raise ValueError(f"unknown waiver category: {category!r}")
    findings = findings_for_candidates(
        category,
        candidates,
        evidence_version=evidence_version,
    )
    if not findings:
        raise ValueError(f"waiver category {category!r} must contain at least one candidate")
    payload = json.dumps(
        {
            "category": category,
            "evidence_version": evidence_version,
            "findings": findings,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_waiver_records(
    observed: dict[str, Iterable[str]],
    *,
    evidence_versions: dict[str, int] | None = None,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    evidence_versions = evidence_versions or {}
    for category in sorted(observed):
        if category not in WAIVER_CATEGORIES:
            raise ValueError(f"unknown waiver category: {category}")
        candidates = normalize_candidates(observed[category])
        if not candidates:
            continue
        evidence_version = evidence_versions.get(
            category, WAIVER_EVIDENCE_VERSION
        )
        if (
            type(evidence_version) is not int
            or evidence_version not in WAIVER_FINDING_PARSERS
        ):
            raise ValueError(
                f"unsupported waiver evidence_version: {evidence_version!r}"
            )
        records[category] = {
            "evidence_version": evidence_version,
            "fingerprint": waiver_fingerprint(
                category,
                candidates,
                evidence_version=evidence_version,
            ),
            "findings": findings_for_candidates(
                category,
                candidates,
                evidence_version=evidence_version,
            ),
            "candidates": candidates,
        }
    return records


def validate_waiver_records(value: Any, label: str = "waivers") -> dict[str, dict[str, Any]]:
    """Validate and return canonical item-level waiver evidence.

    A category-only waiver is intentionally not accepted.  The versioned,
    exact finding set is fingerprinted, while raw diagnostics remain available
    for audit without making extractor-dependent measurements authoritative.
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
        required = {"evidence_version", "fingerprint", "findings", "candidates"}
        missing = required - record.keys()
        extra = record.keys() - required
        if missing or extra:
            details: list[str] = []
            if missing:
                details.append(f"missing keys: {', '.join(sorted(missing))}")
            if extra:
                details.append(f"unknown keys: {', '.join(sorted(extra))}")
            raise ValueError(f"{label}.{category}: {'; '.join(details)}")
        evidence_version = record["evidence_version"]
        if (
            type(evidence_version) is not int
            or evidence_version not in WAIVER_FINDING_PARSERS
        ):
            raise ValueError(
                f"{label}.{category}.evidence_version must be a supported integer: "
                + ", ".join(str(version) for version in sorted(WAIVER_FINDING_PARSERS))
            )
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
        findings = record["findings"]
        if not isinstance(findings, list) or not all(
            isinstance(finding, str) for finding in findings
        ):
            raise ValueError(f"{label}.{category}.findings must be a list of strings")
        derived_findings = findings_for_candidates(
            category,
            normalized,
            evidence_version=evidence_version,
        )
        if findings != derived_findings:
            raise ValueError(
                f"{label}.{category}.findings must exactly match sorted diagnostic identities"
            )
        fingerprint = record["fingerprint"]
        if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(fingerprint):
            raise ValueError(
                f"{label}.{category}.fingerprint must be a lowercase SHA-256 digest"
            )
        expected = waiver_fingerprint(
            category,
            normalized,
            evidence_version=evidence_version,
        )
        if fingerprint != expected:
            raise ValueError(
                f"{label}.{category}.fingerprint does not match its candidates"
            )
        result[category] = {
            "evidence_version": evidence_version,
            "fingerprint": fingerprint,
            "findings": findings,
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


def build_observed_waiver_records_for_compare(
    recorded: dict[str, dict[str, Any]],
    observed: dict[str, Iterable[str]],
) -> dict[str, dict[str, Any]]:
    """Build current observations without silently widening old waivers.

    Existing diagnostics are first replayed with the evidence parser recorded
    by the acceptance receipt.  If, and only if, that parser does not recognize
    a current diagnostic, retry the whole category with the current parser so
    comparison reports an explicit evidence-version/fingerprint change.  Other
    failures remain hard validation errors.
    """

    recorded = validate_waiver_records(recorded, "recorded waivers")
    records: dict[str, dict[str, Any]] = {}
    for category in sorted(observed):
        candidates = normalize_candidates(observed[category])
        if not candidates:
            continue
        recorded_version = recorded.get(category, {}).get(
            "evidence_version", WAIVER_EVIDENCE_VERSION
        )
        try:
            category_record = build_waiver_records(
                {category: candidates},
                evidence_versions={category: recorded_version},
            )
        except ValueError as exc:
            unknown_prefix = f"unknown {category} waiver candidate: "
            if (
                recorded_version == WAIVER_EVIDENCE_VERSION
                or not str(exc).startswith(unknown_prefix)
            ):
                raise
            category_record = build_waiver_records(
                {category: candidates},
                evidence_versions={category: WAIVER_EVIDENCE_VERSION},
            )
        records.update(category_record)
    return records


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
            # A newer validator may retire a conservative risk.  The recorded
            # waiver remains historical review provenance and does not make
            # otherwise unchanged accepted content invalid.
            continue
        elif expected["evidence_version"] != current["evidence_version"]:
            mismatches.append(
                f"changed:{category}:{expected.get('fingerprint', '')}:"
                f"{current.get('fingerprint', '')}:{' | '.join(current.get('candidates', []))}"
            )
        elif not set(current["findings"]).issubset(expected["findings"]):
            mismatches.append(
                f"changed:{category}:{expected.get('fingerprint', '')}:"
                f"{current.get('fingerprint', '')}:{' | '.join(current.get('candidates', []))}"
            )
        else:
            reviewed.append(
                f"reviewed:{category}:{current['fingerprint']}:{len(current['findings'])}"
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
            observed = build_observed_waiver_records_for_compare(
                recorded,
                read_observed_tsv(args.observed),
            )
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
                f"({len(record['findings'])} finding(s))"
            )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
