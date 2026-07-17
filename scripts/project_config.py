#!/usr/bin/env python3
"""Load and validate versioned policy, taxonomy, and acceptance records."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from acceptance_evidence import WAIVER_CATEGORIES, validate_waiver_records


POLICY_SCHEMA_VERSION = 1
ACCEPTANCE_SCHEMA_VERSION = 3
TAXONOMY_SCHEMA_VERSION = 1
METADATA_FILE = "paper.yaml"
SOURCE_FILE = "source.pdf"
TRANSLATION_FILE = "translation.md"
TARGET_LANGUAGE = "zh-CN"
REQUIRE_COMPLETE_REFERENCES = True
ALLOW_WHOLE_PAGE_IMAGES_IN_READING_PATH = False
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKIP_REASON_CODES = {
    "over-page-limit",
    "out-of-scope",
    "explicit-user-skip",
}
REVIEW_ACTIONS = {
    "section-review",
    "full-translation-review",
    "repair-review",
}
RUNTIME_REVIEW_ACTIONS = REVIEW_ACTIONS
ACCEPTANCE_WAIVERS = set(WAIVER_CATEGORIES)
MIGRATION_REVIEWERS = {
    "historical-v2-reviewer-unrecorded",
    "pending-v3-re-review",
}
HISTORICAL_V2_ENTRY_FINGERPRINTS = {
    "a-relational-model-of-data-for-large-shared-data-banks": "2d46e99beec81d1a3eab08e90d17242bd991f4f5b928fd7e5560eb29544d0a8f",
    "alibaba-hologres-a-cloud-native-service-for-hybrid-serving-analytical-processing": "c1a8dba51408092650562a0cb3fb3a21f9352e36152c89fd8305ce9b0a768f77",
    "analyticdb-v-hybrid-analytical-engine-query-fusion": "23287da042bc206c05b5d4ffb5d2cf22ea58f626d9d7a36f1cf12d553ba5e931",
    "are-we-ready-for-learned-cardinality-estimation": "035d8012cd2846bcfc7c3d343bf27271cb5f4057b15b0602f7d5a3385e8d21af",
    "aurora-new-model-architecture-data-stream-management": "4848b2c566a7f9f30e37036a98b5be4921b39f6a6125eef04be95cbf5da1bc35",
    "automated-sql-query-generation-systematic-testing-database-engines": "ddab30c1e5db1e4e665a3d8946370a496bd16c226408095b0f468d6e4ab7a94b",
    "balsa-learning-a-query-optimizer-without-expert-demonstrations": "0ba0ad82a4bbdf44349ff5caae030dcfc8a3f2c4e9d0fb91f243bd9eea582bc7",
    "bao-making-learned-query-optimization-practical": "a680cce473a95a74fcd92e165c40936e50b794b992383d737597a139026ef21e",
    "bringing-cloud-native-storage-to-sap-iq": "b597b6e545a1c1e536066afd76fd3bfd690f38fdfb042415f5240d5858c5e8ef",
    "calvin-fast-distributed-transactions-partitioned-database-systems": "2ec511509b8cc3d182989d577488245cc422aaad5d2afdd6ad0133fde6ae5b03",
    "can-foundation-models-wrangle-your-data": "103c9588265e12be044da21ad80b1c669f3a762872d85333d1542da03eded62b",
    "case-for-learned-index-structures": "5fe641687c8c4553a0a4a76af13a506b9ce1875999ca0752ddc5fa556cfc93c8",
    "cql-continuous-query-language": "9966894caaea64801bad9e98e27c8c4e9fb08f6a7adbd15286b31c50a81bfbe3",
    "dataflow-model-balancing-correctness-latency-cost": "082ed25155ca5e00493e6526f5b45146a3f83c0f23ede7d06e91350432b2dbec",
    "delta-lake-high-performance-acid-table-storage-cloud-object-stores": "2a86dc97066d5bb127e3537e312aca637a86e4555b3dbaacaa32f7a30bf13e9d",
    "design-and-implementation-of-ingres": "3448303e3983c7e00c6a1dbdc09fc14867e6639d87168f5a50d1c54b68baa631",
    "diskann-fast-accurate-billion-point-nearest-neighbor-search": "576aad4dacbf87e6927a025a2b0926d17316a81201a9f9280cc7b5330f6bc355",
    "dremel-interactive-analysis-of-web-scale-datasets": "d07286a12e12ce49e80ddb7b72e2f3131ba28eaf960d913f6e90a18ee602729a",
    "dynamo-amazon-highly-available-key-value-store": "c9db2de62b7446652aee027378cfae9319faa101b3fae3968b5e1f6545116059",
    "f1-query-declarative-querying-at-scale": "bfb8aa6f0ce6dc8ccdc82696fef4358a4ffe95d2949fe6b4a5e2a24aa0edf846",
    "foundationdb-a-distributed-unbundled-transactional-key-value-store": "a5b7bb1266fbab85b7949c100ba3bbb87a76a905b42b4c8602214a57ae13689d",
    "how-good-are-query-optimizers-really": "1acc172a29d18a2e58614df2d28ccaa817af8b8f2fb561c3d0af252325d9cce4",
    "improving-unnesting-of-complex-queries": "1ef6ebe119a7dc7f731a42084b8517c65ad3d578348dd919c92810a56bf7d89a",
    "instant-loading-main-memory-databases": "4890ae8101ac70288a5f72c6c80e3f09b3f83cc92aa6080b9f353b95a439ae86",
    "lakehouse-new-generation-open-platforms": "aadb52fe01f95363734cf216296b7a8ca23382c36ab5cee8e20233674b7ac1ab",
    "language-models-enable-structured-views-heterogeneous-data-lakes": "a8e01bd005c22dbd03fb19e500c5f8814d2e9c958b069180c5165fc7f0533963",
    "learned-cardinalities-estimating-correlated-joins-deep-learning": "6a93eb0a1df9bc475d7ba9b3981b8b187284861b3cf4ccfdf0b47c5b400ecdfd",
    "mainlining-databases-fast-transactional-workloads-universal-columnar-data-file-formats": "97da2514a25a94569fcab6312c11135b876c2b1d3500bd4ff991a508388dd5cc",
    "mesa-geo-replicated-near-real-time-scalable-data-warehousing": "7aaa8c22cfa8380a93215757cf4265e55283a3ab1af053b57ab527eafa640b4d",
    "milvus-purpose-built-vector-data-management-system": "b7c3b4c4cb8aa510af66fde1dee3bd5b913315353050ced3cb656656e33220c2",
    "neo-a-learned-query-optimizer": "5da1a0a8f7a4b68e133910d239b017b620677595b2d1ff7766d025b071af28a7",
    "neurocard-one-cardinality-estimator-for-all-tables": "8e862c28226883edb3fa2af99926fb72fc18fd4149c6a6a08a917ee3031306d4",
    "notions-consistency-predicate-locks-database-system": "fc2965da890b467ff24fbdc59447c9ab8e41036c33e13ea2a3d89b21b4eb0651",
    "optimistic-methods-concurrency-control": "a22b668be4a2961590a24db10bfa9adef6e66a0d99653fcec2c803aa56c7d4bd",
    "optimizing-queries-partitioned-tables-mpp": "b1bba6534956d9d6b609e8aa66a2e1be2c45dff0e87178dc34842e780487fcb9",
    "palimpzest-optimizing-ai-powered-analytics-declarative-query-processing": "d6258a98bc2ba609e1e051f97b9b199bfbbfc8184406d46523653598cad42cd9",
    "pattern-defeating-quicksort": "c80c5cba09844186cf4421fbe93f88eba8b6a7a1671b8b687ace11fb42f760f7",
    "pax-cache-friendly-hybrid-storage": "f65ae0bf6c363c0faddc0a50f005176d6df449731c00439aaecd2d118d9bf359",
    "presto-sql-on-everything": "438676f3ee951ba0cf5fe8269171d5ec9983de47dd4903c735ba4dbea440f373",
    "qagen-generating-query-aware-test-databases": "6076f2dae4e3126e68e5b8ef15bf7c48cb0842208f662700f05accafbf6cf976",
    "resilient-distributed-datasets-a-fault-tolerant-abstraction-for-in-memory-cluster-computing": "2aa6a07773de186258683bc7192fa5f0c9c584c769903c15aa32ce94a4e21616",
    "saha-string-adaptive-hash-table-analytical-databases": "8f646e6c4137f339fd984965694088340546e5807727bc5d5600a28fd589611a",
    "speculative-distributed-csv-data-parsing-big-data-analytics": "2256999cdb2207ad4f84d1772a902901c0bce07c87b64602c6b656ad8c30286a",
    "the-vertica-analytic-database-c-store-7-years-later": "4e5f65b9d182a9956603cbcb44d295585e1af8ae2465f9729b69dc0cbaa9366b",
    "tile-row-store": "c96f2388c6528b4318260bec6efbfd2b77e7d5282c9838083ab344056dadb5bc",
    "towards-practical-vectorized-analytical-query-engines": "7c281b6ed14a75c3547785fb0ecf00a21204c18c0b2e7bcb96ba9b1770832524",
    "ubiquitous-b-tree": "e3957d011dac169184b130e4df3b465cdae02db14483d3e8bdbe2a99d9725198",
    "vbase-unifying-vector-search-relational-queries": "9a2183188fb1c2b04a094ea9514118059cd31ae026d3b7bc345a47518330e7c8",
    "velox-metas-unified-execution-engine": "73542abeec0fa03a7368cfbd7e709d2b1b405a583b477355be42e9e49f3b0bb2",
    "wisckey-ssd-conscious-storage": "46b90ac2b632ad88d3d558fba9319df99963e768d7f5b245a7d6fe6c10bc5134",
    "x-engine-an-optimized-storage-engine-for-large-scale-e-commerce-transaction-processing": "15d5d1c3a9e555cf8e7ebc08db842f10bcb975a15ace83f9dc07e4514829aee1",
}


def load_yaml_text(content: str, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f"{label}: cannot read YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}: YAML root must be a mapping")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
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


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
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


def acceptance_entry_fingerprint(entry: dict[str, Any]) -> str:
    payload = json.dumps(
        entry,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_acceptance_ledger(data: dict[str, Any], label: str) -> dict[str, Any]:
    _exact_keys(data, {"schema_version", "entries"}, label)
    _schema_version(
        data["schema_version"], ACCEPTANCE_SCHEMA_VERSION, f"{label}: schema_version"
    )
    entries = _mapping(data["entries"], f"{label}: entries")
    for paper_id, entry in entries.items():
        if not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id):
            raise ValueError(f"{label}: invalid acceptance paper id: {paper_id!r}")
        entry = _mapping(entry, f"{label}: entries.{paper_id}")
        required = {
            "source_sha256",
            "translation_sha256",
            "assets_manifest_sha256",
            "review_action",
            "reviewer",
            "review_base_sha",
        }
        allowed = required | {"waivers"}
        missing = required - entry.keys()
        unknown = entry.keys() - allowed
        messages: list[str] = []
        if missing:
            messages.append(f"missing keys: {', '.join(sorted(missing))}")
        if unknown:
            messages.append(f"unknown keys: {', '.join(sorted(unknown))}")
        if messages:
            raise ValueError(f"{label}: entries.{paper_id}: {'; '.join(messages)}")
        for key in ("source_sha256", "translation_sha256", "assets_manifest_sha256"):
            if not isinstance(entry[key], str) or not SHA256_RE.fullmatch(entry[key]):
                raise ValueError(f"{label}: entries.{paper_id}.{key} must be a lowercase SHA-256 digest")
        review_action = entry["review_action"]
        if not isinstance(review_action, str) or review_action not in REVIEW_ACTIONS:
            raise ValueError(
                f"{label}: entries.{paper_id}.review_action must be one of "
                + ", ".join(sorted(REVIEW_ACTIONS))
            )
        reviewer = entry["reviewer"]
        _nonempty_string(reviewer, f"{label}: entries.{paper_id}.reviewer")
        if reviewer != reviewer.strip():
            raise ValueError(f"{label}: entries.{paper_id}.reviewer must be trimmed")
        if reviewer == "pending-v3-re-review":
            raise ValueError(
                f"{label}: entries.{paper_id}.reviewer pending-v3-re-review is no longer valid"
            )
        review_base_sha = entry["review_base_sha"]
        if not isinstance(review_base_sha, str) or not GIT_SHA_RE.fullmatch(review_base_sha):
            raise ValueError(
                f"{label}: entries.{paper_id}.review_base_sha must be a 40-character lowercase Git SHA"
            )
        validate_waiver_records(
            entry.get("waivers", {}), f"{label}: entries.{paper_id}.waivers"
        )
        if reviewer == "historical-v2-reviewer-unrecorded":
            expected = HISTORICAL_V2_ENTRY_FINGERPRINTS.get(paper_id)
            actual = acceptance_entry_fingerprint(entry)
            if expected is None or actual != expected:
                raise ValueError(
                    f"{label}: entries.{paper_id}: historical migration evidence is not frozen"
                )
    return data


def load_acceptance_ledger(path: Path) -> dict[str, Any]:
    return validate_acceptance_ledger(load_yaml(path), str(path))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
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
