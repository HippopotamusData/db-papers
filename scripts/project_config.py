#!/usr/bin/env python3
"""Load and validate the versioned project, paper-policy, and acceptance files."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml


PROJECT_SCHEMA_VERSION = 2
PAPER_POLICY_SCHEMA_VERSION = 1
ACCEPTANCE_SCHEMA_VERSION = 1
TAXONOMY_SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKIP_REASON_CODES = {
    "over-page-limit",
    "out-of-scope",
    "explicit-user-skip",
}
ACCEPTANCE_BASE_DISPOSITION_CODES = {
    "section-review-complete",
    "new-full-translation-reviewed",
    "priority-repair-reviewed",
    "legacy-accepted-status-migrated",
}


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: cannot read YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


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


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _schema_version(value: Any, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        raise ValueError(f"{label} must be integer {expected}, got {value!r}")


def load_project_config(root: Path) -> dict[str, Any]:
    path = root / "config/project.yaml"
    data = load_yaml(path)
    _exact_keys(data, {"schema_version", "project", "translation_policy", "records"}, str(path))
    _schema_version(data["schema_version"], PROJECT_SCHEMA_VERSION, f"{path}: schema_version")

    project = _mapping(data["project"], f"{path}: project")
    _exact_keys(
        project,
        {
            "target_language",
            "canonical_metadata",
            "source_pdf",
            "translation_file",
        },
        f"{path}: project",
    )
    for key in ("target_language",):
        _nonempty_string(project[key], f"{path}: project.{key}")
    fixed_names = {
        "canonical_metadata": "paper.yaml",
        "source_pdf": "source.pdf",
        "translation_file": "translation.md",
    }
    for key, expected in fixed_names.items():
        value = _nonempty_string(project[key], f"{path}: project.{key}")
        if value != expected:
            raise ValueError(f"{path}: project.{key} must be {expected!r}")

    policy = _mapping(data["translation_policy"], f"{path}: translation_policy")
    _exact_keys(
        policy,
        {
            "max_source_pages",
            "require_complete_references",
            "allow_whole_page_images_in_reading_path",
        },
        f"{path}: translation_policy",
    )
    pages = policy["max_source_pages"]
    if isinstance(pages, bool) or not isinstance(pages, int) or pages < 1:
        raise ValueError(f"{path}: translation_policy.max_source_pages must be a positive integer")
    _boolean(policy["require_complete_references"], f"{path}: translation_policy.require_complete_references")
    _boolean(
        policy["allow_whole_page_images_in_reading_path"],
        f"{path}: translation_policy.allow_whole_page_images_in_reading_path",
    )

    records = _mapping(data["records"], f"{path}: records")
    _exact_keys(records, {"paper_policy", "acceptance_ledger"}, f"{path}: records")
    for key in ("paper_policy", "acceptance_ledger"):
        relative = Path(_nonempty_string(records[key], f"{path}: records.{key}"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"{path}: records.{key} must be a repository-relative path")
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
        _exact_keys(details, {"label_zh"}, f"{path}: topics.{topic}")
        _nonempty_string(details["label_zh"], f"{path}: topics.{topic}.label_zh")
    return data


def configured_paths(root: Path, config: dict[str, Any]) -> dict[str, Path]:
    project = config["project"]
    records = config["records"]
    return {
        "metadata": Path(project["canonical_metadata"]),
        "source": Path(project["source_pdf"]),
        "translation": Path(project["translation_file"]),
        "paper_policy": root / records["paper_policy"],
        "acceptance_ledger": root / records["acceptance_ledger"],
    }


def load_paper_policy(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    _exact_keys(data, {"schema_version", "page_limit_exceptions", "skipped_reasons"}, str(path))
    _schema_version(
        data["schema_version"], PAPER_POLICY_SCHEMA_VERSION, f"{path}: schema_version"
    )
    exceptions = _mapping(data["page_limit_exceptions"], f"{path}: page_limit_exceptions")
    for paper_id, record in exceptions.items():
        if not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id):
            raise ValueError(f"{path}: invalid page-limit paper id: {paper_id!r}")
        record = _mapping(record, f"{path}: page_limit_exceptions.{paper_id}")
        _exact_keys(record, {"max_pages", "reason"}, f"{path}: page_limit_exceptions.{paper_id}")
        max_pages = record["max_pages"]
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
            raise ValueError(f"{path}: page_limit_exceptions.{paper_id}.max_pages must be a positive integer")
        _nonempty_string(record["reason"], f"{path}: page_limit_exceptions.{paper_id}.reason")

    reasons = _mapping(data["skipped_reasons"], f"{path}: skipped_reasons")
    for paper_id, reason in reasons.items():
        if not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id):
            raise ValueError(f"{path}: invalid skipped paper id: {paper_id!r}")
        if reason not in SKIP_REASON_CODES:
            raise ValueError(
                f"{path}: skipped_reasons.{paper_id} must be one of {', '.join(sorted(SKIP_REASON_CODES))}"
            )
    return data


def load_acceptance_ledger(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    _exact_keys(data, {"schema_version", "entries"}, str(path))
    _schema_version(
        data["schema_version"], ACCEPTANCE_SCHEMA_VERSION, f"{path}: schema_version"
    )
    entries = _mapping(data["entries"], f"{path}: entries")
    for paper_id, entry in entries.items():
        if not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id):
            raise ValueError(f"{path}: invalid acceptance paper id: {paper_id!r}")
        entry = _mapping(entry, f"{path}: entries.{paper_id}")
        _exact_keys(
            entry,
            {"source_sha256", "translation_sha256", "accepted_version", "risk_disposition"},
            f"{path}: entries.{paper_id}",
        )
        for key in ("source_sha256", "translation_sha256"):
            if not isinstance(entry[key], str) or not SHA256_RE.fullmatch(entry[key]):
                raise ValueError(f"{path}: entries.{paper_id}.{key} must be a lowercase SHA-256 digest")
        _nonempty_string(entry["accepted_version"], f"{path}: entries.{paper_id}.accepted_version")
        dispositions = entry["risk_disposition"]
        if (
            not isinstance(dispositions, list)
            or not dispositions
            or any(not isinstance(item, str) or not item.strip() for item in dispositions)
        ):
            raise ValueError(
                f"{path}: entries.{paper_id}.risk_disposition must be a non-empty string list"
            )
        if len(dispositions) != len(set(dispositions)):
            raise ValueError(f"{path}: entries.{paper_id}.risk_disposition contains duplicates")
        if not ACCEPTANCE_BASE_DISPOSITION_CODES.intersection(dispositions):
            raise ValueError(
                f"{path}: entries.{paper_id}.risk_disposition requires one controlled base acceptance code"
            )
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def effective_page_limit(
    project_config: dict[str, Any], paper_policy: dict[str, Any], paper_id: str
) -> int:
    exception = paper_policy["page_limit_exceptions"].get(paper_id)
    if exception:
        return exception["max_pages"]
    return project_config["translation_policy"]["max_source_pages"]
