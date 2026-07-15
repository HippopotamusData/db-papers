#!/usr/bin/env python3
"""Validate minimal reading metadata, expose status rows, and generate the catalog."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from project_config import (
    ACCEPTANCE_WAIVERS,
    ALLOW_WHOLE_PAGE_IMAGES_IN_READING_PATH,
    METADATA_FILE,
    REQUIRE_COMPLETE_REFERENCES,
    RUNTIME_REVIEW_ACTIONS,
    SLUG_RE,
    SOURCE_FILE,
    TARGET_LANGUAGE,
    TRANSLATION_FILE,
    configured_paths,
    effective_page_limit,
    load_acceptance_ledger,
    load_project_policy,
    load_taxonomy,
    load_yaml,
    sha256_file,
    skip_reason as configured_skip_reason,
)
from validation_policy import quality_issue_severity


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
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary_name).replace(path)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def records() -> list[tuple[Path, dict[str, Any]]]:
    result: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(PAPERS.glob(f"*/*/{METADATA_FILE}")):
        result.append((path, load_yaml(path)))
    return result


def add_error(errors: list[str], path: Path, message: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {message}")


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


def validate_rating(errors: list[str], path: Path, rating: Any) -> None:
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


def parse_translation_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("translation.md must start with YAML frontmatter")
    try:
        frontmatter, _body = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise ValueError("translation.md frontmatter is not closed") from exc
    value = yaml.safe_load(frontmatter)
    if not isinstance(value, dict):
        raise ValueError("translation.md frontmatter must be a mapping")
    return value


def validate(paper_id: str | None = None) -> int:
    errors: list[str] = []
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
            validate_rating(errors, path, data["rating"])

        slug = path.parent.name
        area = path.parent.parent.name
        if area not in areas:
            add_error(errors, path, f"paper area is not registered: {area}")
        if not SLUG_RE.fullmatch(slug):
            add_error(errors, path, f"paper directory must be a kebab-case id: {slug}")
        if not isinstance(data.get("title"), str) or not data["title"].strip():
            add_error(errors, path, "title must be a non-empty string")
        authors = data.get("authors")
        if not isinstance(authors, list) or any(
            not isinstance(author, str) or not author.strip() for author in authors
        ):
            add_error(errors, path, "authors must be a list of non-empty strings")
        year = data.get("year")
        if year is not None and (not isinstance(year, int) or not 1800 <= year <= 2100):
            add_error(errors, path, "year must be null or an integer between 1800 and 2100")
        if not isinstance(data.get("source_url"), str) or not data["source_url"].strip():
            add_error(errors, path, "source_url must be a non-empty string")
        else:
            parsed_url = urlparse(data["source_url"])
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                add_error(errors, path, "source_url must use an absolute HTTP(S) URL")

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
            if source.is_file() != expect_source:
                add_error(
                    errors,
                    path,
                    f"reading_status={reading_status} requires {source_name}={expect_source}",
                )
            if translation.is_file() != expect_translation:
                add_error(
                    errors,
                    path,
                    f"reading_status={reading_status} requires {translation_name}={expect_translation}",
                )

        if translation.is_file():
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

        ledger_entry = acceptance["entries"].get(slug)
        if reading_status == "translated":
            if not ledger_entry:
                add_error(errors, path, "reading_status=translated requires an acceptance-ledger entry")
            elif source.is_file() and translation.is_file():
                current_source_hash = sha256_file(source)
                current_translation_hash = sha256_file(translation)
                if ledger_entry["source_sha256"] != current_source_hash:
                    add_error(errors, path, "source.pdf changed after acceptance; set status to draft and review again")
                if ledger_entry["translation_sha256"] != current_translation_hash:
                    add_error(errors, path, "translation.md changed after acceptance; set status to draft and review again")
        elif ledger_entry and reading_status not in {"draft"}:
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
            "> 本文件由 `python3 scripts/papers.py catalog` 从各论文的 `paper.yaml` 生成，"
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
            lines.append(f"| {details['label_zh']} (`{area}`) | {area_counts[area]} |")

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
                f"### {details['label_zh']} (`{area}`，{len(area_records)} 篇)",
                "",
                "| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |",
                "| --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        for path, data in area_records:
            topic_labels = "、".join(
                taxonomy["topics"][topic]["label_zh"]
                for topic in sorted(data["topics"], key=topic_order.__getitem__)
            )
            reading_target = catalog_reading_target(path, data, source_name, translation_name)
            title = data["title"].replace("|", "\\|")
            year = data["year"] if data["year"] is not None else "—"
            rating = catalog_rating(data)
            lines.append(
                f"| [{title}]({reading_target}) | {topic_labels} | "
                f"{year} | {rating} | {data['reading_status']} | [原文]({data['source_url']}) |"
            )

    lines.extend(["", "## 元数据完整性", "", "| 字段 | 已确认 | 待补证据 |", "| --- | ---: | ---: |"])
    for label, known in completeness.items():
        lines.append(f"| {label} | {known} | {len(loaded) - known} |")
    return "\n".join(lines) + "\n"


def catalog(check: bool) -> int:
    content = build_catalog()
    if check:
        if not CATALOG.exists() or CATALOG.read_text(encoding="utf-8") != content:
            print("ERROR: CATALOG.md is stale; run `python3 scripts/papers.py catalog`.", file=sys.stderr)
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
    parsed_url = urlparse(url.strip())
    if not title.strip() or parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        print("ERROR: --title and --url must be non-empty.", file=sys.stderr)
        return 1

    target = PAPERS / area / paper_id
    existing = sorted(PAPERS.glob(f"*/{paper_id}"))
    if existing:
        print(f"ERROR: paper id already exists: {existing[0].relative_to(ROOT)}", file=sys.stderr)
        return 1

    data = {
        "title": title.strip(),
        "authors": [],
        "year": None,
        "source_url": url.strip(),
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
        entry = acceptance["entries"].get(paper_id)
        print("\t".join(entry.get("waivers", [])) if entry else "")
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


def validation_manifest(paper_id: str | None) -> int:
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
        entry = acceptance["entries"].get(slug)
        waivers = "\t".join(entry.get("waivers", [])) if entry else ""
        severity = (
            quality_issue_severity(reading_status)
            if reading_status in {"draft", "translated"}
            else ""
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
        ]
        if not emit(fields):
            return 1
    return 0


def acceptance_preflight(paper_id: str) -> tuple[bool, str]:
    env = os.environ.copy()
    env.update(
        {
            "PAPER_ID": paper_id,
            "PYTHON": sys.executable,
            "SKIP_METADATA_VALIDATION": "1",
            "DEEP_VALIDATION": "1",
        }
    )
    commands = [
        [sys.executable, "scripts/papers.py", "validate"],
        [sys.executable, "scripts/normalize_translation_headers.py", "--check"],
        ["bash", "scripts/validate_translations.sh"],
    ]
    output: list[str] = []
    for command in commands:
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
        if completed.returncode != 0:
            return False, "\n".join(output)
    return True, "\n".join(output)


def accept_record(paper_id: str, review_action: str, waivers: list[str]) -> int:
    try:
        paths = configured_paths(ROOT)
        ledger = load_acceptance_ledger(paths["acceptance_ledger"])
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    matches = sorted(PAPERS.glob(f"*/{paper_id}/{paths['metadata'].name}"))
    if len(matches) != 1:
        print(f"ERROR: paper id must resolve exactly once: {paper_id}", file=sys.stderr)
        return 1
    metadata_path = matches[0]
    data = load_yaml(metadata_path)
    if data.get("reading_status") != "draft":
        print(
            "ERROR: acceptance requires reading_status=draft; changed or re-reviewed translated papers must transition to draft first",
            file=sys.stderr,
        )
        return 1
    source = metadata_path.parent / paths["source"].name
    translation = metadata_path.parent / paths["translation"].name
    if not source.is_file() or not translation.is_file():
        print("ERROR: acceptance requires source.pdf and translation.md", file=sys.stderr)
        return 1
    if review_action not in RUNTIME_REVIEW_ACTIONS:
        print(
            "ERROR: runtime review action must be one of: "
            + ", ".join(sorted(RUNTIME_REVIEW_ACTIONS)),
            file=sys.stderr,
        )
        return 1
    normalized_waivers = list(dict.fromkeys(item.strip() for item in waivers if item.strip()))
    unknown_waivers = set(normalized_waivers) - ACCEPTANCE_WAIVERS
    if unknown_waivers:
        print(
            "ERROR: unknown acceptance waivers: " + ", ".join(sorted(unknown_waivers)),
            file=sys.stderr,
        )
        return 1

    original_ledger = paths["acceptance_ledger"].read_text(encoding="utf-8")
    original_metadata = metadata_path.read_text(encoding="utf-8")
    ledger["entries"][paper_id] = {
        "source_sha256": sha256_file(source),
        "translation_sha256": sha256_file(translation),
        "review_action": review_action,
    }
    if normalized_waivers:
        ledger["entries"][paper_id]["waivers"] = normalized_waivers
    data["reading_status"] = "translated"

    try:
        atomic_write_text(paths["acceptance_ledger"], dump_yaml(ledger))
        atomic_write_text(metadata_path, dump_yaml(data))
        accepted, details = acceptance_preflight(paper_id)
        if not accepted:
            raise ValueError(f"acceptance preflight failed\n{details}".rstrip())
        recorded = load_acceptance_ledger(paths["acceptance_ledger"])["entries"].get(paper_id)
        if not recorded or recorded["source_sha256"] != sha256_file(source):
            raise ValueError("source.pdf changed during acceptance preflight")
        if recorded["translation_sha256"] != sha256_file(translation):
            raise ValueError("translation.md changed during acceptance preflight")
    except (OSError, ValueError) as exc:
        rollback_errors: list[str] = []
        for path, content in (
            (paths["acceptance_ledger"], original_ledger),
            (metadata_path, original_metadata),
        ):
            try:
                atomic_write_text(path, content)
            except OSError as rollback_exc:
                rollback_errors.append(f"{path}: {rollback_exc}")
        print(f"ERROR: {exc}", file=sys.stderr)
        if rollback_errors:
            print("ERROR: rollback failed: " + "; ".join(rollback_errors), file=sys.stderr)
        else:
            print("Acceptance changes were rolled back.", file=sys.stderr)
        return 1
    print(f"Accepted {paper_id}; hashes recorded in {paths['acceptance_ledger'].relative_to(ROOT)}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate minimal paper metadata")
    validate_parser.add_argument("--paper-id", help="validate only one paper record")
    subparsers.add_parser("status", help="print tab-separated rows for deep validation")
    config_parser = subparsers.add_parser("config", help="print a validated project config value")
    config_parser.add_argument("--key", required=True)
    config_parser.add_argument("--paper-id")
    manifest_parser = subparsers.add_parser(
        "validation-manifest", help="print one batched snapshot for deep translation validation"
    )
    manifest_parser.add_argument("--paper-id")
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
    accept_parser = subparsers.add_parser("accept", help="record hashes after manual review and set translated")
    accept_parser.add_argument("--id", required=True, dest="paper_id")
    accept_parser.add_argument(
        "--review-action", required=True, choices=sorted(RUNTIME_REVIEW_ACTIONS)
    )
    accept_parser.add_argument("--waiver", action="append", default=[], choices=sorted(ACCEPTANCE_WAIVERS))
    args = parser.parse_args()

    if args.command == "validate":
        return validate(args.paper_id)
    if args.command == "status":
        return status_rows()
    if args.command == "config":
        return config_value(args.key, args.paper_id)
    if args.command == "validation-manifest":
        return validation_manifest(args.paper_id)
    if args.command == "catalog":
        return catalog(args.check)
    if args.command == "accept":
        return accept_record(args.paper_id, args.review_action, args.waiver)
    return new_record(args.id, args.title, args.area, args.topics, args.url)


if __name__ == "__main__":
    raise SystemExit(main())
