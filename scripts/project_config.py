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
ACCEPTANCE_SCHEMA_VERSION = 4
REVIEW_RECEIPT_SCHEMA_VERSION = 1
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
REVIEW_RECEIPT_ACTIONS_BY_SCHEMA = {
    1: REVIEW_RECEIPT_V1_ACTIONS,
}
REVIEW_RECEIPT_CHECKS_BY_SCHEMA = {
    1: REVIEW_RECEIPT_V1_CHECKS,
}
REVIEW_RECEIPT_METADATA_KEYS_BY_SCHEMA = {
    1: REVIEW_RECEIPT_V1_METADATA_KEYS,
}
REVIEW_RECEIPT_IDENTITY_ASSURANCE_BY_SCHEMA = {
    1: REVIEW_RECEIPT_V1_IDENTITY_ASSURANCE,
}
REVIEW_RECEIPT_REQUIRED_KEYS_BY_SCHEMA = {
    1: REVIEW_RECEIPT_V1_REQUIRED_KEYS,
}

# These aliases define the active schema used for new receipts. Historical
# receipt validation selects frozen rules by each receipt's own schema_version.
REVIEW_ACTIONS = set(REVIEW_RECEIPT_V1_ACTIONS)
REVIEW_IDENTITY_ASSURANCE = REVIEW_RECEIPT_V1_IDENTITY_ASSURANCE
REQUIRED_REVIEW_CHECKS = set(REVIEW_RECEIPT_V1_CHECKS)
REVIEW_METADATA_KEYS = REVIEW_RECEIPT_V1_METADATA_KEYS

RUNTIME_REVIEW_ACTIONS = set(REVIEW_ACTIONS)
REVIEW_GATE_STATIC_PATHS = (
    "Makefile",
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "config/policy.yaml",
    "config/taxonomy.yaml",
    "docs/workflows/batch-translate.md",
    "docs/workflows/review.md",
)
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
LEGACY_V3_ENTRY_FINGERPRINTS = {
    "access-path-selection-relational-database-management-system": "bb054d9352a7655e50942fbb167809b93b947cce794c1224a5ea468f87bd03a8",
    "adaptive-execution-compiled-queries": "2f314f6113945763b2b9c4621de3f973b08d8b51c4ce66e19c849948adb0f5a6",
    "adaptive-optimization-very-large-join-queries": "8a5c0b1c2e31c2abdad928c85a26e8b7608f29e0c851ba1a1748158cb180790a",
    "amazon-redshift-and-the-case-for-simpler-data-warehouses": "e61df684e9a39c076034248daf30ed7e32719b70398aef8db1e8213b58b987d4",
    "analyticdb-real-time-olap-database-system-at-alibaba-cloud": "f9a2ab125bc593e6c89c57526296a47abcd729b493782ada1ca8ce0f329cbc33",
    "apache-calcite-a-foundational-framework-for-optimized-query-processing-over-heterogeneous-data-sources": "c29dd2530f39dd14c10a8ec2e86ce719dda75bcedb66f1bfddb20069532cabda",
    "apache-flink-stream-and-batch-processing-in-a-single-engine": "21427d163102cbef4f8ad05ab791c7e958445348a1444e93eda4cc9dca1e9cbd",
    "big-metadata-when-metadata-is-big-data": "a39ce47823bac941c9bdef14e0d9127cf2b89cebccefc7ca4068ffa46fec538f",
    "bigtable-distributed-storage-system-structured-data": "584d1af7094aa28f424fec3eeaef8f83e1c5c5daf0a7c93454c4bc0712f6e422",
    "bipie-fast-selection-aggregation-encoded-data-operator-specialization": "a89883f62ab5d4e22f1c06b085244e652713f8f2c8a6b6aa7d2366d667593d50",
    "bird-can-llm-already-serve-as-a-database-interface": "4f0582f65ab5d6afe879bad2535718a550bd20117bc5e1504c93937404ee286f",
    "building-an-elastic-query-engine-on-disaggregated-storage": "74b0e4efc7405e85f692fc3065b21c8e470db43c2958e6d41e81c430664d60db",
    "c-store-column-oriented-dbms": "b7bcdbc11703eec7f7cead52321d6c9daf6bd8390c69bd359ec0cdedaa4a9ac0",
    "cascades-framework-query-optimization": "e9a604637ecd504c850c788618b07e05b4ed7167a7f97e0768d03b1d17d4a2d1",
    "ceph-a-scalable-high-performance-distributed-file-system": "8e5fd161e3beff98105faca38b9c04b4583b7377771c5f1200f7301657d5969a",
    "cfs-a-distributed-file-system-for-large-scale-container-platforms": "36f34a809cd6e172ba7997c9832ef62f84f9731002523bd1dcf2cd2cb5a1c228",
    "cockroachdb-the-resilient-geo-distributed-sql-database": "5968a33a97a480f2d119939db34b3bfe6eab5e2a293ab077fd39fd80927ff53f",
    "compiled-and-vectorized-queries-afraid-to-ask": "281410070b2f3689ee749412f7757125023fc397e7d82b2cdb3d90cf8ff445f5",
    "complete-story-of-joins-hyper": "26c96cf189983d48ce1f6ef067bd9947f1eb6d11678c49cbe7a0796cd5737b8b",
    "critique-ansi-sql-isolation-levels": "ec652d2f4526aa5e3507c5790903d853c52e1135f40426176ab51ede29440a03",
    "data-blocks-hybrid-oltp-olap-compressed-storage-vectorization-compilation": "212d40ae1c57df8d7a4155b5c803d0b3d08b88689787cfdc51a2d20efab55460",
    "data-warehousing-in-the-cloud-amazon-redshift-vs-microsoft-azure-sql": "d5f9d78338930da4c3f2d89463c514d510999240d1469006b294553257b778e0",
    "db2-with-blu-acceleration-so-much-more-than-just-a-column-store": "bc78b572bd60029d924888a0049e2c773b3dc0c8fecc35908399faf09381dc47",
    "dbaiops-reasoning-llm-database-operation-maintenance-knowledge-graphs": "87406b1f3979a77a843552e25705304431009c8bd3c891a0556033c828437a68",
    "dbtoaster-higher-order-delta-processing": "4bfa93bf240218100dc1991a54a4e8c71720b5eef96adbeaa8d95a4920cc922a",
    "deepdb-learn-from-data-not-from-queries": "44323f13400b7da4809b7d3d5b7e4756bffbcebaab851af1a84f82379b527677",
    "design-of-postgres": "9bb2b3439e8ab9019d1c749203a874a518bb1820bd090b763f413ff760cdd69b",
    "detecting-optimization-bugs-non-optimizing-reference-engine": "58b98ff4c658279ab0768dd5976fb47c586a703955a0ac61be52562217abf86a",
    "druid-a-real-time-analytical-data-store": "83eb2ae2248a3a192b9dc087819aeafbf89fea9bbc3104491254c297058e93eb",
    "duckdb-embeddable-analytical-database": "bd1dea3462569f118edbd200c7674b10b9dac9b0923a99f7e954ded4e5a544dd",
    "efficiently-compiling-efficient-query-plans-modern-hardware": "fb158733e73c3c62499bd5ada87aef311f3a6529888160588648f7c0f52d4959",
    "exploiting-upper-lower-bounds-top-down-query-optimization": "1189b7b3edd089e3fb79c39681d3b78a5021c6553ae7d86fc5e8e9da2780fc65",
    "expression-templates-revisited": "5199b037693979672c1d93cb66262c6cce8bfdf053bd2dc01d92150630cc7040",
    "facebook-tectonic-filesystem-efficiency-from-exascale": "4fa9be9cb99f11b0f69bb74c155cb50b252e317ed96656368980773a6030fe23",
    "generating-code-holistic-query-evaluation": "5fba80e3f23bbb69408db31c510918f0b7201ce2378cd99dd9a7e2b66e04f68a",
    "granularity-locks-degrees-consistency-shared-database": "5b876d3c07251f3dff14cc484c84312fa7581874f48b5a1fb06507a4cba205bd",
    "hawq-a-massively-parallel-processing-sql-engine-in-hadoop": "a05885db80fd1def0bf30bbd0ddf526456209fb2c4dc6c884854dfd40bf28dbf",
    "hnsw-efficient-and-robust-approximate-nearest-neighbor-search": "f79ff6083db04294ba6d7e972bce7a3e66b85bac248be14220df9b08fc8c6a24",
    "impala-a-modern-open-source-sql-engine-for-hadoop": "73f52ec10e35470572538cc94e103b602557a14dfbc817d0563b48264d2b75f3",
    "interleaved-multi-vectorizing": "c0b7a91761fbbd07370f6a02a35fba976658b849e11a7d740369995219a05d1f",
    "kudu-storage-for-fast-analytics-on-fast-data": "baacb88d5739e66ce1b80857942e4cfadb9171a858a3134b93225ca70b665a7a",
    "llvm-compilation-framework-lifelong-program-analysis-transformation": "7ce57ccd1ef3d2ec790e08eec1b7be3aae0c1dcd45801f8d5ad2f253acf14017",
    "log-structured-merge-tree": "bba6ecc8ffb3e8c09e7841ef4c41779c485ad88bdeab30c5df02a8482b39488b",
    "low-latency-compilation-sql-queries-machine-code": "ea3eb7ab54702a078e65cb358e704980b078966c6e4568d034950d5377feb710",
    "memsql-query-optimizer": "f5a52887ceebc4c903220dc077f40e15cf4ee7aa7f86a9fadf949660655ee4d7",
    "merge-path-visually-intuitive-parallel-merging": "27fca471d8bdd9a4618072d98b08a97d90c2a0ed64d873552d3ed7243d04f1fc",
    "monetdb-x100-hyper-pipelining-query-execution": "f330ed274236038697ca549f94efd525cc0092a3ac89ffc9b3232741b9f050cf",
    "morsel-driven-parallelism": "7a2c9e90c38d44997212e4c26acf602ab45d60a789a2499237fb96d382d3e5af",
    "napa-powering-scalable-data-warehousing-with-robust-query-performance-at-google": "2bf56429a747e4dee83f74a20c5b6d4c03ca21e24c191bca5f8926896909fddd",
    "optimization-common-table-expressions-mpp": "16e718ea09371a245700a85daed85b017bc9a7208c957265f6b20b3e0ef30fb9",
    "optimizing-queries-using-materialized-views": "7d2594316c8322724ee5bcb820ec0a7ffd5dddfac6449430a05251df1d450609",
    "orca-modular-query-optimizer-architecture-big-data": "24a876f52862452f26f94b99cd618331a49d05e269d89212b0f4126da7f7dc28",
    "overview-query-optimization-relational-systems": "930e2dec85f8a5fee9a706c8618fe535b4110f22764997f20cf13426625bc8fa",
    "permutable-compiled-queries-dynamically-adapting-without-recompiling": "f02eeb28a27da20f98b838fb1d78dd896c0f60124add92726e5f7342c3d9efab",
    "photon-fast-query-engine-lakehouse-systems": "b3a4fe7f7fb918241b79f22f2df871a90a9e8ceb792758068d1d117df3bb6864",
    "pinot-realtime-olap-for-530-million-users": "9266e6ec284ced70ae765c09c0d81397c4a6992668f177555cde5ca2378fc232",
    "procella-unifying-serving-and-analytical-data-at-youtube": "0b9a6723a78b129d869207bd281723bbf6315f5d2530bed4f7863f2efac1452e",
    "push-vs-pull-loop-fusion": "13f27ec3ba3c5b6f10e17b8057af9a3a03d1f1fa68cecc1ad6b19d77a6463d48",
    "quantifying-tpch-choke-points": "15d66007b5322a1f784553c05144369a03c9e768976ec57234f00b2093deaf13",
    "relaxed-operator-fusion-in-memory-databases": "e5ee1f29195082d7367bf5c058ddeab5e28e169b86e9d347c67b237bbded7e87",
    "rethinking-simd-vectorization-in-memory-databases": "d01a9f5c6d744674fbe6bab1e80c81ede8402b073cc82763a0f2f80b86c2eac1",
    "runtime-code-generation-cloudera-impala": "9f9691cada78044f59fb41bc785105ea8e1e9d3e70824eb436bb5cd3d95965b2",
    "snappydata-unified-cluster-for-streaming-transactions-and-interactive-analytics": "9c646b743c32b680b3ac8bcf127dab6a8dd937e279ffd7a34dff07766e2fd68d",
    "spann-highly-efficient-billion-scale-approximate-nearest-neighbor-search": "3f23bdd0dfbb13516f3d4c99fbf74e493270c5a2181ae9f00d5d0ebb5c957bcb",
    "spanner-googles-globally-distributed-database": "0ebc1bedbab1e8ce2d373f04d9cedf8c6b6e8d8a3af2d55feea9cf2946eee8e0",
    "spark-sql-relational-data-processing-in-spark": "935b20929888ecbc54b22e8c1b57282efb786b9d06bf358451c07f84ddf3ab9a",
    "speedy-transactions-multicore-in-memory-databases": "1336d21b42fc406dd17c068466f13bcb98d27511b848409efe81add577699bcd",
    "starling-scalable-query-engine-cloud-function-services": "f291ae55cd0ba9dcb9b3ded2783f2c0d45a9fd4d4c0c6c3f0852db8becfefca5",
    "system-r-relational-approach-to-database-management": "d7ab9dc56161724c5deb2bbe4a2edddda4ea9b76fb1f9fc2fc95b91c9c9d1eb0",
    "text-to-sql-empowered-by-large-language-models-benchmark-evaluation": "1e1f992351ec7d5df9e6c3f87b306174f7c37dbbac6cae76e116a07f0a9ea4b8",
    "the-snowflake-elastic-data-warehouse": "d25982d8e0245d0be9cd7b6d5445ff21a16d1c2887a9b4b9cdb26670a3c413aa",
    "unnesting-arbitrary-queries": "49e4ccbe7f3033cde1fdbb4b100f61e754b6dd9fb543d2ec19f6b705f84d55b0",
    "vectorization-vs-compilation-query-execution": "860b7996459c1ca2a5f88a8fef9c86e35f800d988e3d29af8639ff4133c518e5",
    "vldb-2009-tutorial-column-stores": "14fd0cae969f8b75db536f70420b15750fcac679b9bc682ab59a2b90fdb0eb81",
    "volcano-optimizer-generator": "81586032f9d260e17763cf8e9cbef0f8d2eced96596760b98bb94103f68ee886",
    "what-serverless-computing-is-and-should-become": "a66224a517bbbbb1c239f13c720733acefbb69e5b4725cb1bea80061ce43286d",
    "winmagic-subquery-elimination-window-aggregation": "96d009c9ca1cfb2c70e7db3628ef086433132ed997fe83db1d17027ce4c759fa",
}
LEGACY_RECEIPTLESS_ENTRY_FINGERPRINTS = {
    **HISTORICAL_V2_ENTRY_FINGERPRINTS,
    **LEGACY_V3_ENTRY_FINGERPRINTS,
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
    for key in (
        "source_sha256",
        "translation_sha256",
        "assets_manifest_sha256",
        "translation_policy_sha256",
        "review_metadata_sha256",
        "review_gate_manifest_sha256",
        "fingerprint",
    ):
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
    ):
        raise ValueError(
            f"{label}.findings must be a duplicate-free list of trimmed strings"
        )
    receipt["waivers"] = validate_waiver_records(
        receipt["waivers"], f"{label}.waivers"
    )
    expected_fingerprint = review_receipt_fingerprint(receipt)
    if receipt["fingerprint"] != expected_fingerprint:
        raise ValueError(f"{label}.fingerprint does not match the receipt")
    return receipt


def validate_acceptance_ledger(data: dict[str, Any], label: str) -> dict[str, Any]:
    _exact_keys(
        data,
        {
            "schema_version",
            "retired_legacy_entry_fingerprints",
            "entries",
        },
        label,
    )
    _schema_version(
        data["schema_version"], ACCEPTANCE_SCHEMA_VERSION, f"{label}: schema_version"
    )
    retired = _mapping(
        data["retired_legacy_entry_fingerprints"],
        f"{label}: retired_legacy_entry_fingerprints",
    )
    for paper_id, fingerprint in retired.items():
        if not isinstance(paper_id, str) or not SLUG_RE.fullmatch(paper_id):
            raise ValueError(
                f"{label}: invalid retired legacy paper id: {paper_id!r}"
            )
        if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(fingerprint):
            raise ValueError(
                f"{label}: retired_legacy_entry_fingerprints.{paper_id} "
                "must be a lowercase SHA-256 digest"
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
        allowed = required | {"waivers", "review_receipt"}
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
        if "review_receipt" in entry:
            receipt = validate_review_receipt(
                entry["review_receipt"],
                f"{label}: entries.{paper_id}.review_receipt",
            )
            parent_matches = {
                "source_sha256": "source_sha256",
                "translation_sha256": "translation_sha256",
                "assets_manifest_sha256": "assets_manifest_sha256",
                "review_action": "review_action",
                "reviewer": "reviewer",
                "review_base_sha": "review_base_sha",
            }
            for receipt_key, entry_key in parent_matches.items():
                if receipt[receipt_key] != entry[entry_key]:
                    raise ValueError(
                        f"{label}: entries.{paper_id}.review_receipt.{receipt_key} "
                        f"must match {entry_key}"
                    )
            if receipt["paper_id"] != paper_id:
                raise ValueError(
                    f"{label}: entries.{paper_id}.review_receipt.paper_id must match the entry id"
                )
            if receipt["waivers"] != entry.get("waivers", {}):
                raise ValueError(
                    f"{label}: entries.{paper_id}.review_receipt.waivers "
                    "must match the entry waivers"
                )
        else:
            expected = LEGACY_RECEIPTLESS_ENTRY_FINGERPRINTS.get(paper_id)
            actual = acceptance_entry_fingerprint(entry)
            if expected is None or actual != expected:
                raise ValueError(
                    f"{label}: entries.{paper_id}: receiptless legacy evidence "
                    "is not frozen"
                )
        if reviewer == "historical-v2-reviewer-unrecorded":
            expected = HISTORICAL_V2_ENTRY_FINGERPRINTS.get(paper_id)
            actual = acceptance_entry_fingerprint(entry)
            if expected is None or actual != expected:
                raise ValueError(
                    f"{label}: entries.{paper_id}: historical migration evidence is not frozen"
                )
    return data


def validate_repository_legacy_freeze(
    data: dict[str, Any],
    label: str,
) -> None:
    """Require the immutable universe to partition into active and retired debt."""

    entries = data["entries"]
    retired = data["retired_legacy_entry_fingerprints"]
    retired_ids = set(retired)
    unknown_retired = retired_ids - set(LEGACY_RECEIPTLESS_ENTRY_FINGERPRINTS)
    changed_retired = {
        paper_id
        for paper_id, fingerprint in retired.items()
        if LEGACY_RECEIPTLESS_ENTRY_FINGERPRINTS.get(paper_id) != fingerprint
    }
    retired_without_receipt = {
        paper_id
        for paper_id in retired_ids
        if paper_id not in entries
        or "review_receipt" not in entries[paper_id]
    }
    retirement_errors: list[str] = []
    if unknown_retired:
        retirement_errors.append(
            "unknown retired legacy entries: "
            + ", ".join(sorted(unknown_retired))
        )
    if changed_retired:
        retirement_errors.append(
            "changed retired legacy fingerprints: "
            + ", ".join(sorted(changed_retired))
        )
    if retired_without_receipt:
        retirement_errors.append(
            "retired legacy entries without review receipts: "
            + ", ".join(sorted(retired_without_receipt))
        )
    if retirement_errors:
        raise ValueError(f"{label}: {'; '.join(retirement_errors)}")

    receiptless_ids = {
        paper_id
        for paper_id, entry in entries.items()
        if "review_receipt" not in entry
    }
    frozen_ids = set(LEGACY_RECEIPTLESS_ENTRY_FINGERPRINTS) - retired_ids
    if receiptless_ids != frozen_ids:
        missing = receiptless_ids - frozen_ids
        surplus = frozen_ids - receiptless_ids
        details: list[str] = []
        if missing:
            details.append(
                "unfrozen receiptless entries: " + ", ".join(sorted(missing))
            )
        if surplus:
            details.append(
                "surplus legacy allowlist entries: " + ", ".join(sorted(surplus))
            )
        raise ValueError(f"{label}: {'; '.join(details)}")

    historical_ids = {
        paper_id
        for paper_id, entry in entries.items()
        if entry["reviewer"] == "historical-v2-reviewer-unrecorded"
    }
    frozen_historical_ids = (
        set(HISTORICAL_V2_ENTRY_FINGERPRINTS) - retired_ids
    )
    if historical_ids != frozen_historical_ids:
        missing = historical_ids - frozen_historical_ids
        surplus = frozen_historical_ids - historical_ids
        details = []
        if missing:
            details.append(
                "unfrozen historical entries: " + ", ".join(sorted(missing))
            )
        if surplus:
            details.append(
                "surplus historical allowlist entries: "
                + ", ".join(sorted(surplus))
            )
        raise ValueError(f"{label}: {'; '.join(details)}")


def load_acceptance_ledger(path: Path) -> dict[str, Any]:
    data = validate_acceptance_ledger(load_yaml(path), str(path))
    repository_ledger = Path(__file__).resolve().parents[1] / "config/acceptance.yaml"
    if path.resolve() == repository_ledger.resolve():
        validate_repository_legacy_freeze(data, str(path))
    return data


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


def review_gate_manifest_sha256(root: Path) -> str:
    paths = [root / relative for relative in REVIEW_GATE_STATIC_PATHS]
    scripts_dir = root / "scripts"
    paths.extend(
        path
        for path in sorted(scripts_dir.iterdir())
        if path.is_file() and path.suffix in {".py", ".sh", ".cjs"}
    )
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda candidate: candidate.relative_to(root).as_posix()):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"review gate input must be a regular file: {path}")
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
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
