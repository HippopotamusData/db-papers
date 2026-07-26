#!/usr/bin/env python3
"""Load and validate project policy, taxonomy, and common paper paths."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml


POLICY_SCHEMA_VERSION = 1
TAXONOMY_SCHEMA_VERSION = 1
METADATA_FILE = "paper.yaml"
SOURCE_FILE = "source.pdf"
TRANSLATION_FILE = "translation.md"
TARGET_LANGUAGE = "zh-CN"
REQUIRE_COMPLETE_REFERENCES = True
ALLOW_WHOLE_PAGE_IMAGES_IN_READING_PATH = False
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKIP_REASON_CODES = {
    "over-page-limit",
    "out-of-scope",
    "explicit-user-skip",
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
    }


def effective_page_limit(policy: dict[str, Any], paper_id: str) -> int:
    paper_policy = policy["papers"].get(paper_id, {})
    return paper_policy.get("max_source_pages", policy["default_max_source_pages"])


def skip_reason(policy: dict[str, Any], paper_id: str) -> str:
    return policy["papers"].get(paper_id, {}).get("skip_reason", "")
