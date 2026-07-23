#!/usr/bin/env python3
"""Load and validate versioned policy, taxonomy, and acceptance records."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from acceptance_evidence import WAIVER_CATEGORIES, validate_waiver_records


POLICY_SCHEMA_VERSION = 1
ACCEPTANCE_SCHEMA_VERSION = 5
REVIEW_RECEIPT_SCHEMA_VERSION = 2
TAXONOMY_SCHEMA_VERSION = 1
MAX_REVIEW_FINDINGS = 8
MAX_REVIEW_FINDING_CHARS = 500
METADATA_FILE = "paper.yaml"
SOURCE_FILE = "source.pdf"
TRANSLATION_FILE = "translation.md"
TARGET_LANGUAGE = "zh-CN"
REQUIRE_COMPLETE_REFERENCES = True
ALLOW_WHOLE_PAGE_IMAGES_IN_READING_PATH = False
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STABLE_IDENTITY_RE = re.compile(r"^[a-z][a-z0-9-]*:\S+$")
SKIP_REASON_CODES = {
    "over-page-limit",
    "out-of-scope",
    "explicit-user-skip",
}
REVIEW_RECEIPT_V1_ACTIONS = frozenset(
    {
        "section-review",
        "full-translation-review",
        "repair-review",
    }
)
REVIEW_RECEIPT_V1_CHECKS = frozenset(
    {
        "front-matter",
        "section-structure",
        "technical-claims",
        "numbers-and-units",
        "formulas",
        "figures-and-tables",
        "algorithms-and-listings",
        "footnotes-and-end-matter",
        "conclusions-and-limitations",
        "references",
        "visual-layout",
    }
)
REVIEW_RECEIPT_V1_METADATA_KEYS = ("title", "authors", "year", "source_url")
REVIEW_RECEIPT_V1_IDENTITY_ASSURANCE = "self-attested"
REVIEW_RECEIPT_V1_REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "paper_id",
        "source_sha256",
        "translation_sha256",
        "assets_manifest_sha256",
        "translation_policy_sha256",
        "review_metadata_sha256",
        "review_gate_manifest_sha256",
        "review_action",
        "translator",
        "reviewer",
        "identity_assurance",
        "review_base_sha",
        "checks",
        "findings",
        "waivers",
        "fingerprint",
    }
)
REVIEW_RECEIPT_V2_ACTIONS = REVIEW_RECEIPT_V1_ACTIONS
REVIEW_RECEIPT_V2_CHECKS = REVIEW_RECEIPT_V1_CHECKS
REVIEW_RECEIPT_V2_METADATA_KEYS = REVIEW_RECEIPT_V1_METADATA_KEYS
REVIEW_RECEIPT_V2_IDENTITY_ASSURANCE = REVIEW_RECEIPT_V1_IDENTITY_ASSURANCE
REVIEW_RECEIPT_V2_REQUIRED_KEYS = frozenset(
    {
        *(
            REVIEW_RECEIPT_V1_REQUIRED_KEYS
            - {
                "translation_policy_sha256",
                "review_gate_manifest_sha256",
                "identity_assurance",
                "checks",
            }
        ),
        "review_head_sha",
        "authorial_voice",
    }
)
REVIEW_RECEIPT_ACTIONS_BY_SCHEMA = {
    1: REVIEW_RECEIPT_V1_ACTIONS,
    2: REVIEW_RECEIPT_V2_ACTIONS,
}
REVIEW_RECEIPT_CHECKS_BY_SCHEMA = {
    1: REVIEW_RECEIPT_V1_CHECKS,
    2: REVIEW_RECEIPT_V2_CHECKS,
}
REVIEW_RECEIPT_METADATA_KEYS_BY_SCHEMA = {
    1: REVIEW_RECEIPT_V1_METADATA_KEYS,
    2: REVIEW_RECEIPT_V2_METADATA_KEYS,
}
REVIEW_RECEIPT_IDENTITY_ASSURANCE_BY_SCHEMA = {
    1: REVIEW_RECEIPT_V1_IDENTITY_ASSURANCE,
    2: REVIEW_RECEIPT_V2_IDENTITY_ASSURANCE,
}
REVIEW_RECEIPT_REQUIRED_KEYS_BY_SCHEMA = {
    1: REVIEW_RECEIPT_V1_REQUIRED_KEYS,
    2: REVIEW_RECEIPT_V2_REQUIRED_KEYS,
}

# These aliases define the active schema used for new receipts. Historical
# receipt validation selects frozen rules by each receipt's own schema_version.
REVIEW_ACTIONS = set(REVIEW_RECEIPT_V2_ACTIONS)
REVIEW_IDENTITY_ASSURANCE = REVIEW_RECEIPT_V2_IDENTITY_ASSURANCE
REQUIRED_REVIEW_CHECKS = set(REVIEW_RECEIPT_V2_CHECKS)
REVIEW_METADATA_KEYS = REVIEW_RECEIPT_V2_METADATA_KEYS

RUNTIME_REVIEW_ACTIONS = set(REVIEW_ACTIONS)
REVIEW_GATE_STATIC_PATHS = (
    "AGENTS.md",
    "Makefile",
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "config/policy.yaml",
    "config/taxonomy.yaml",
    "docs/translation-policy.md",
    "docs/workflows/batch-translate.md",
    "docs/workflows/review.md",
)
ACCEPTANCE_WAIVERS = set(WAIVER_CATEGORIES)
MIGRATION_REVIEWERS = {
    "historical-v2-reviewer-unrecorded",
    "pending-v3-re-review",
}


class UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""

    def construct_mapping(
        self,
        node: yaml.nodes.MappingNode,
        deep: bool = False,
    ) -> dict[Any, Any]:
        self.flatten_mapping(node)
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as exc:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found an unhashable key",
                    key_node.start_mark,
                ) from exc
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def load_yaml_text(content: str, label: str) -> dict[str, Any]:
    try:
        value = yaml.load(content, Loader=UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"{label}: cannot read YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}: YAML root must be a mapping")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path}: must be a regular, non-symlink YAML file")
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{path}: cannot read YAML: {exc}") from exc
    return load_yaml_text(content, str(path))


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = expected - value.keys()
    unknown = value.keys() - expected
    messages: list[str] = []
    if missing:
        messages.append(f"missing keys: {', '.join(sorted(missing))}")
    if unknown:
        messages.append(f"unknown keys: {', '.join(sorted(unknown))}")
    if messages:
        raise ValueError(f"{label}: {'; '.join(messages)}")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def is_trimmed_single_line(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(
            unicodedata.category(character) in {"Cc", "Cs", "Zl", "Zp"}
            for character in value
        )
    )


def _nonempty_string(value: Any, label: str) -> str:
    if not is_trimmed_single_line(value):
        raise ValueError(
            f"{label} must be a trimmed, non-empty single-line string"
        )
    return value


def _schema_version(value: Any, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        raise ValueError(f"{label} must be integer {expected}, got {value!r}")


def load_project_policy(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    _exact_keys(data, {"schema_version", "default_max_source_pages", "papers"}, str(path))
    _schema_version(data["schema_version"], POLICY_SCHEMA_VERSION, f"{path}: schema_version")

    pages = data["default_max_source_pages"]
    if isinstance(pages, bool) or not isinstance(pages, int) or pages < 1:
        raise ValueError(f"{path}: default_max_source_pages must be a positive integer")

    papers = _mapping(data["papers"], f"{path}: papers")
    for paper_id, record in papers.items():
        if not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id):
            raise ValueError(f"{path}: invalid policy paper id: {paper_id!r}")
        record = _mapping(record, f"{path}: papers.{paper_id}")
        allowed = {"max_source_pages", "authorization", "skip_reason"}
        unknown = record.keys() - allowed
        if unknown:
            raise ValueError(
                f"{path}: papers.{paper_id}: unknown keys: {', '.join(sorted(unknown))}"
            )
        if not record:
            raise ValueError(f"{path}: papers.{paper_id} must not be empty")

        has_limit = "max_source_pages" in record
        has_authorization = "authorization" in record
        if has_limit != has_authorization:
            raise ValueError(
                f"{path}: papers.{paper_id} page-limit override requires max_source_pages and authorization"
            )
        if has_limit:
            override = record["max_source_pages"]
            if isinstance(override, bool) or not isinstance(override, int) or override <= pages:
                raise ValueError(
                    f"{path}: papers.{paper_id}.max_source_pages must exceed the default limit"
                )
            _nonempty_string(record["authorization"], f"{path}: papers.{paper_id}.authorization")

        if "skip_reason" in record:
            reason = record["skip_reason"]
            if not isinstance(reason, str) or reason not in SKIP_REASON_CODES:
                raise ValueError(
                    f"{path}: papers.{paper_id}.skip_reason must be one of "
                    + ", ".join(sorted(SKIP_REASON_CODES))
                )
    return data


def load_taxonomy(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    _exact_keys(data, {"schema_version", "areas", "topics"}, str(path))
    _schema_version(data["schema_version"], TAXONOMY_SCHEMA_VERSION, f"{path}: schema_version")
    areas = _mapping(data["areas"], f"{path}: areas")
    topics = _mapping(data["topics"], f"{path}: topics")
    if not areas or not topics:
        raise ValueError(f"{path}: areas and topics must be non-empty mappings")
    for area, details in areas.items():
        if not isinstance(area, str) or not SLUG_RE.fullmatch(area):
            raise ValueError(f"{path}: invalid area id: {area!r}")
        details = _mapping(details, f"{path}: areas.{area}")
        _exact_keys(details, {"label_zh", "description"}, f"{path}: areas.{area}")
        _nonempty_string(details["label_zh"], f"{path}: areas.{area}.label_zh")
        _nonempty_string(details["description"], f"{path}: areas.{area}.description")
    for topic, details in topics.items():
        if not isinstance(topic, str) or not SLUG_RE.fullmatch(topic):
            raise ValueError(f"{path}: invalid topic id: {topic!r}")
        details = _mapping(details, f"{path}: topics.{topic}")
        _exact_keys(details, {"label_zh", "description"}, f"{path}: topics.{topic}")
        _nonempty_string(details["label_zh"], f"{path}: topics.{topic}.label_zh")
        _nonempty_string(details["description"], f"{path}: topics.{topic}.description")
    return data


def configured_paths(root: Path) -> dict[str, Path]:
    return {
        "metadata": Path(METADATA_FILE),
        "source": Path(SOURCE_FILE),
        "translation": Path(TRANSLATION_FILE),
        "policy": root / "config/policy.yaml",
        "acceptance_ledger": root / "config/acceptance.yaml",
    }


def review_receipt_fingerprint(receipt: dict[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("fingerprint", None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


REVIEW_SNAPSHOT_KEYS = frozenset(
    {
        "translation_policy_sha256",
        "review_gate_manifest_sha256",
        "review_base_sha",
    }
)
LEDGER_V1_INHERITED_KEYS = frozenset(
    {
        "translation_policy_sha256",
        "review_gate_manifest_sha256",
        "review_base_sha",
        "identity_assurance",
        "checks",
    }
)


def review_snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(
        snapshot,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def materialize_acceptance_receipt(
    ledger: dict[str, Any], paper_id: str
) -> dict[str, Any]:
    entry = _mapping(ledger["entries"][paper_id], f"entries.{paper_id}")
    if entry.get("schema_version") != 1:
        return copy.deepcopy(entry)
    snapshot_id = entry.get("review_snapshot")
    if not isinstance(snapshot_id, str) or not SHA256_RE.fullmatch(snapshot_id):
        raise ValueError(
            f"entries.{paper_id}.review_snapshot must be a lowercase SHA-256 digest"
        )
    snapshots = _mapping(ledger["review_snapshots"], "review_snapshots")
    if snapshot_id not in snapshots:
        raise ValueError(
            f"entries.{paper_id}.review_snapshot does not exist: {snapshot_id}"
        )
    receipt = copy.deepcopy(entry)
    receipt.pop("review_snapshot")
    receipt.update(copy.deepcopy(snapshots[snapshot_id]))
    receipt["identity_assurance"] = REVIEW_RECEIPT_V1_IDENTITY_ASSURANCE
    receipt["checks"] = sorted(REVIEW_RECEIPT_V1_CHECKS)
    return receipt


def validate_review_receipt(receipt: Any, label: str) -> dict[str, Any]:
    receipt = _mapping(receipt, label)
    schema_version = receipt.get("schema_version")
    if (
        type(schema_version) is not int
        or schema_version not in REVIEW_RECEIPT_REQUIRED_KEYS_BY_SCHEMA
    ):
        supported = ", ".join(
            str(version)
            for version in sorted(REVIEW_RECEIPT_REQUIRED_KEYS_BY_SCHEMA)
        )
        raise ValueError(
            f"{label}.schema_version must be a supported integer version "
            f"({supported})"
        )
    required = REVIEW_RECEIPT_REQUIRED_KEYS_BY_SCHEMA[schema_version]
    _exact_keys(receipt, required, label)
    paper_id = receipt["paper_id"]
    if not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id):
        raise ValueError(f"{label}.paper_id must be kebab-case")
    digest_keys = [
        "source_sha256",
        "translation_sha256",
        "assets_manifest_sha256",
        "review_metadata_sha256",
        "fingerprint",
    ]
    if schema_version == 1:
        digest_keys.extend(
            [
                "translation_policy_sha256",
                "review_gate_manifest_sha256",
            ]
        )
    for key in digest_keys:
        if not isinstance(receipt[key], str) or not SHA256_RE.fullmatch(receipt[key]):
            raise ValueError(f"{label}.{key} must be a lowercase SHA-256 digest")
    review_action = receipt["review_action"]
    allowed_actions = REVIEW_RECEIPT_ACTIONS_BY_SCHEMA[schema_version]
    if not isinstance(review_action, str) or review_action not in allowed_actions:
        raise ValueError(
            f"{label}.review_action must be one of "
            + ", ".join(sorted(allowed_actions))
        )
    translator = receipt["translator"]
    reviewer = receipt["reviewer"]
    for key, value in (("translator", translator), ("reviewer", reviewer)):
        if (
            not isinstance(value, str)
            or value != value.strip()
            or not STABLE_IDENTITY_RE.fullmatch(value)
        ):
            raise ValueError(
                f"{label}.{key} must use a stable namespace:value identity"
            )
    if translator == reviewer:
        raise ValueError(f"{label}: translator and reviewer must be different")
    if reviewer in MIGRATION_REVIEWERS or translator in MIGRATION_REVIEWERS:
        raise ValueError(f"{label}: migration identity markers are not allowed")
    if schema_version == 1:
        identity_assurance = REVIEW_RECEIPT_IDENTITY_ASSURANCE_BY_SCHEMA[
            schema_version
        ]
        if receipt["identity_assurance"] != identity_assurance:
            raise ValueError(
                f"{label}.identity_assurance must be {identity_assurance!r}"
            )
    review_base_sha = receipt["review_base_sha"]
    if not isinstance(review_base_sha, str) or not GIT_SHA_RE.fullmatch(review_base_sha):
        raise ValueError(
            f"{label}.review_base_sha must be a 40-character lowercase Git SHA"
        )
    if schema_version >= 2:
        review_head_sha = receipt["review_head_sha"]
        if (
            not isinstance(review_head_sha, str)
            or not GIT_SHA_RE.fullmatch(review_head_sha)
        ):
            raise ValueError(
                f"{label}.review_head_sha must be a 40-character lowercase Git SHA"
            )
    if schema_version == 1:
        checks = receipt["checks"]
        required_checks = REVIEW_RECEIPT_CHECKS_BY_SCHEMA[schema_version]
        if (
            not isinstance(checks, list)
            or any(not isinstance(check, str) for check in checks)
            or checks != sorted(required_checks)
        ):
            raise ValueError(
                f"{label}.checks must contain the complete sorted review checklist"
            )
    findings = receipt["findings"]
    if (
        not isinstance(findings, list)
        or any(
            not isinstance(finding, str)
            or not finding.strip()
            or finding != finding.strip()
            for finding in findings
        )
        or len(findings) != len(set(findings))
        or (schema_version >= 2 and not findings)
    ):
        raise ValueError(
            f"{label}.findings must be a non-empty duplicate-free list of "
            "trimmed strings for new receipts"
        )
    if schema_version >= 2:
        if (
            len(findings) > MAX_REVIEW_FINDINGS
            or any(
                not is_trimmed_single_line(finding)
                or len(finding) > MAX_REVIEW_FINDING_CHARS
                for finding in findings
            )
        ):
            raise ValueError(
                f"{label}.findings must contain at most {MAX_REVIEW_FINDINGS} "
                "single-line items of at most "
                f"{MAX_REVIEW_FINDING_CHARS} characters each"
            )
        authorial_voice = _mapping(
            receipt["authorial_voice"], f"{label}.authorial_voice"
        )
        _exact_keys(
            authorial_voice,
            {
                "source_valid_items",
                "verified_items",
                "shared_subject_merges",
            },
            f"{label}.authorial_voice",
        )
        for key, value in authorial_voice.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(
                    f"{label}.authorial_voice.{key} must be a non-negative integer"
                )
        if authorial_voice["verified_items"] != authorial_voice["source_valid_items"]:
            raise ValueError(
                f"{label}.authorial_voice.verified_items must equal "
                "source_valid_items for an accepted review"
            )
        if (
            authorial_voice["shared_subject_merges"]
            > authorial_voice["verified_items"]
        ):
            raise ValueError(
                f"{label}.authorial_voice.shared_subject_merges cannot exceed "
                "verified_items"
            )
    receipt["waivers"] = validate_waiver_records(
        receipt["waivers"], f"{label}.waivers"
    )
    expected_fingerprint = review_receipt_fingerprint(receipt)
    if receipt["fingerprint"] != expected_fingerprint:
        raise ValueError(f"{label}.fingerprint does not match the receipt")
    return receipt


def validate_acceptance_ledger(data: dict[str, Any], label: str) -> dict[str, Any]:
    _exact_keys(data, {"schema_version", "review_snapshots", "entries"}, label)
    _schema_version(
        data["schema_version"], ACCEPTANCE_SCHEMA_VERSION, f"{label}: schema_version"
    )
    snapshots = _mapping(data["review_snapshots"], f"{label}: review_snapshots")
    for snapshot_id, snapshot in snapshots.items():
        if not isinstance(snapshot_id, str) or not SHA256_RE.fullmatch(snapshot_id):
            raise ValueError(
                f"{label}: review snapshot ids must be lowercase SHA-256 digests"
            )
        snapshot = _mapping(
            snapshot, f"{label}: review_snapshots.{snapshot_id}"
        )
        _exact_keys(snapshot, REVIEW_SNAPSHOT_KEYS, f"{label}: review_snapshots.{snapshot_id}")
        for key in ("translation_policy_sha256", "review_gate_manifest_sha256"):
            if not isinstance(snapshot[key], str) or not SHA256_RE.fullmatch(
                snapshot[key]
            ):
                raise ValueError(
                    f"{label}: review_snapshots.{snapshot_id}.{key} "
                    "must be a lowercase SHA-256 digest"
                )
        if (
            not isinstance(snapshot["review_base_sha"], str)
            or not GIT_SHA_RE.fullmatch(snapshot["review_base_sha"])
        ):
            raise ValueError(
                f"{label}: review_snapshots.{snapshot_id}.review_base_sha "
                "must be a 40-character lowercase Git SHA"
            )
        if snapshot_id != review_snapshot_fingerprint(snapshot):
            raise ValueError(
                f"{label}: review snapshot id does not match its content: "
                f"{snapshot_id}"
            )
    entries = _mapping(data["entries"], f"{label}: entries")
    referenced_snapshots: set[str] = set()
    for paper_id, entry in entries.items():
        if not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id):
            raise ValueError(f"{label}: invalid acceptance paper id: {paper_id!r}")
        entry = _mapping(entry, f"{label}: entries.{paper_id}")
        if entry.get("schema_version") == 1:
            expected = (
                REVIEW_RECEIPT_V1_REQUIRED_KEYS
                - LEDGER_V1_INHERITED_KEYS
            ) | {"review_snapshot"}
            _exact_keys(entry, expected, f"{label}: entries.{paper_id}")
            snapshot_id = entry["review_snapshot"]
            if (
                not isinstance(snapshot_id, str)
                or not SHA256_RE.fullmatch(snapshot_id)
                or snapshot_id not in snapshots
            ):
                raise ValueError(
                    f"{label}: entries.{paper_id}.review_snapshot must "
                    "reference a defined review snapshot"
                )
            referenced_snapshots.add(snapshot_id)
            receipt = materialize_acceptance_receipt(data, paper_id)
        else:
            receipt = entry
        receipt = validate_review_receipt(receipt, f"{label}: entries.{paper_id}")
        if receipt["paper_id"] != paper_id:
            raise ValueError(
                f"{label}: entries.{paper_id}.paper_id must match the entry id"
            )
    unused_snapshots = set(snapshots) - referenced_snapshots
    if unused_snapshots:
        raise ValueError(
            f"{label}: unused review snapshots: "
            + ", ".join(sorted(unused_snapshots))
        )
    return data


def load_acceptance_ledger(path: Path) -> dict[str, Any]:
    data = validate_acceptance_ledger(load_yaml(path), str(path))
    materialized = copy.deepcopy(data)
    materialized["entries"] = {
        paper_id: materialize_acceptance_receipt(data, paper_id)
        for paper_id in data["entries"]
    }
    return materialized


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def review_metadata_sha256(
    metadata: dict[str, Any],
    schema_version: int = REVIEW_RECEIPT_SCHEMA_VERSION,
) -> str:
    keys = REVIEW_RECEIPT_METADATA_KEYS_BY_SCHEMA.get(schema_version)
    if keys is None:
        raise ValueError(
            f"unsupported review receipt schema version: {schema_version!r}"
        )
    payload = {key: metadata.get(key) for key in keys}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _git_blob(root: Path, revision: str, relative: str) -> bytes:
    tree_entry = subprocess.run(
        ["git", "-C", os.fspath(root), "ls-tree", revision, "--", relative],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if tree_entry.returncode != 0 or not tree_entry.stdout:
        details = tree_entry.stderr.decode("utf-8", errors="replace").strip()
        suffix = f": {details}" if details else ""
        raise ValueError(
            f"review gate input is not available at {revision}: {relative}{suffix}"
        )
    mode = tree_entry.stdout.split(None, 1)[0]
    if mode == b"120000":
        raise ValueError(
            f"review gate input must not be a symlink at {revision}: {relative}"
        )
    blob = subprocess.run(
        ["git", "-C", os.fspath(root), "show", f"{revision}:{relative}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if blob.returncode != 0:
        details = blob.stderr.decode("utf-8", errors="replace").strip()
        suffix = f": {details}" if details else ""
        raise ValueError(
            f"cannot read review gate input at {revision}: {relative}{suffix}"
        )
    return blob.stdout


def _review_gate_relative_paths(root: Path, revision: str | None) -> list[str]:
    paths = set(REVIEW_GATE_STATIC_PATHS)
    if revision is None:
        scripts_dir = root / "scripts"
        if scripts_dir.is_symlink() or not scripts_dir.is_dir():
            raise ValueError(
                f"review gate scripts directory must be regular: {scripts_dir}"
            )
        for path in sorted(scripts_dir.rglob("*")):
            if path.suffix not in {".py", ".sh", ".cjs"}:
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError(
                    f"review gate input must be a regular file: {path}"
                )
            paths.add(path.relative_to(root).as_posix())
    else:
        result = subprocess.run(
            [
                "git",
                "-C",
                os.fspath(root),
                "ls-tree",
                "-r",
                "-z",
                "--name-only",
                revision,
                "--",
                "scripts",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            details = result.stderr.decode("utf-8", errors="replace").strip()
            suffix = f": {details}" if details else ""
            raise ValueError(
                f"cannot list review gate inputs at {revision}{suffix}"
            )
        paths.update(
            value.decode("utf-8")
            for value in result.stdout.split(b"\0")
            if value and Path(value.decode("utf-8")).suffix in {".py", ".sh", ".cjs"}
        )
    return sorted(paths)


def review_gate_manifest_sha256(
    root: Path, revision: str | None = None
) -> str:
    """Hash the canonical gate path/content manifest in worktree or Git."""

    digest = hashlib.sha256()
    for relative in _review_gate_relative_paths(root, revision):
        path = root / relative
        if revision is None:
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"review gate input must be a regular file: {path}")
            content = path.read_bytes()
        else:
            content = _git_blob(root, revision, relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _git_ignored_paths(paths: list[Path], cwd: Path) -> set[Path]:
    """Return Git-ignored candidates; copied test trees simply have none."""

    candidates = sorted({_lexical_absolute(path) for path in paths}, key=os.fspath)
    if not candidates:
        return set()
    payload = b"\0".join(os.fsencode(path) for path in candidates) + b"\0"
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(cwd), "check-ignore", "-z", "--stdin"],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return set()
    if result.returncode not in (0, 1):
        return set()
    return {
        _lexical_absolute(Path(os.fsdecode(value)))
        for value in result.stdout.split(b"\0")
        if value
    }


def assets_manifest(paper_dir: Path, root: Path | None = None) -> list[dict[str, str]]:
    """Return the canonical manifest for every non-ignored asset.

    The lexical path, entry kind, symlink target (when applicable), and content
    hash are all bound.  The deep resource validator separately rejects unsafe
    links; this manifest prevents an accepted same-path asset from drifting.
    """

    assets = paper_dir / "assets"
    if not assets.exists() and not assets.is_symlink():
        return []
    if assets.is_symlink() or not assets.is_dir():
        raise ValueError(f"{assets}: assets must be a real directory")
    paths = sorted(
        (
            path
            for path in assets.rglob("*")
            if path.is_symlink() or not path.is_dir()
        ),
        key=lambda path: path.relative_to(paper_dir).as_posix(),
    )
    ignored = _git_ignored_paths(paths, root or paper_dir)
    result: list[dict[str, str]] = []
    for path in paths:
        if _lexical_absolute(path) in ignored:
            continue
        relative = path.relative_to(paper_dir).as_posix()
        if path.is_symlink():
            if not path.is_file():
                raise ValueError(f"{path}: accepted asset symlink is broken or not a file")
            result.append(
                {
                    "path": relative,
                    "kind": "symlink",
                    "target": os.readlink(path),
                    "sha256": sha256_file(path),
                }
            )
        elif path.is_file():
            result.append(
                {
                    "path": relative,
                    "kind": "file",
                    "sha256": sha256_file(path),
                }
            )
        else:
            raise ValueError(f"{path}: accepted assets must be regular files")
    return result


def assets_manifest_sha256(paper_dir: Path, root: Path | None = None) -> str:
    payload = json.dumps(
        assets_manifest(paper_dir, root),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def effective_page_limit(policy: dict[str, Any], paper_id: str) -> int:
    paper_policy = policy["papers"].get(paper_id, {})
    return paper_policy.get("max_source_pages", policy["default_max_source_pages"])


def skip_reason(policy: dict[str, Any], paper_id: str) -> str:
    return policy["papers"].get(paper_id, {}).get("skip_reason", "")
