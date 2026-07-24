# DB Papers agent contract

## Outcome

Maintain a reader-first archive of database papers, complete Chinese translations, and direct reading-value ratings. Keep per-paper metadata minimal, use verifiable evidence, and never invent missing facts.

## Evidence and canonical storage

Do not confuse the place where a value is stored with the evidence that justifies
it. Resolve conflicts only within the same information type:

| Information | Evidence source | Canonical storage |
| --- | --- | --- |
| Paper content, numbers, formulas, and citations | The acquired original paper | `source.pdf` |
| Paper ID and primary area | The scoped ingest/classification decision | Directory path |
| Title, authors, year, and source URL | Paper first page or a reliable original-paper entry | `paper.yaml` |
| Assigned topics | The paper's core question plus `config/taxonomy.yaml` definitions | `paper.yaml` |
| Reading status | Lifecycle rules plus current files, policy, and acceptance state | `paper.yaml` |
| Rating | `source.pdf` and the evidence required by the rating workflow | `paper.yaml` |
| Page policy, per-paper exceptions, and skip reasons | Project policy and explicit user authorization | `config/policy.yaml` |
| Controlled areas and topics | Maintainer-approved taxonomy definitions | `config/taxonomy.yaml` |
| Current accepted hashes, review evidence, action, and waivers | Independent PDF review plus the acceptance gates | `config/acceptance.yaml` |
| Config schemas and controlled codes | Maintainer-approved executable contract | `scripts/project_config.py` |
| Operation scope and write authority | The user's current request | The current request and the Autonomy section below |
| Current procedures | Maintainer-approved workflow | Active documents under `docs/` |
| Superseded policy and detailed review history | Prior committed states | Git history |

User scope controls what may be changed; it does not override facts stated by the paper.

## Task routing

Before acting, read only the document or documents listed for the task:

| Task | Required documents |
| --- | --- |
| Add or recover a source paper | `docs/workflows/ingest.md`, `docs/workflows/metadata.md` |
| Classify or enrich reading metadata | `docs/workflows/metadata.md` |
| Score a paper's reading value | `docs/workflows/rating.md` |
| Create or repair a translation draft | `docs/workflows/translate.md`, `docs/workflows/metadata.md`, `docs/translation-policy.md` |
| Complete one newly added paper end to end | `docs/workflows/ingest.md`, `docs/workflows/metadata.md`, `docs/workflows/translate.md`, `docs/workflows/review.md`, `docs/workflows/rating.md`, `docs/translation-policy.md` |
| Record a page-limit exception or a policy skip | `docs/workflows/maintain.md`, `docs/workflows/metadata.md` |
| Coordinate a Codex translation or authorized historical-repair batch with direct subagents | `docs/workflows/batch-translate.md`, `docs/workflows/review.md`, `docs/translation-policy.md` |
| Audit/review a translation (read-only by default) | `docs/workflows/review.md`, `docs/translation-policy.md` |
| Review-and-repair or accept a translation (explicit write authorization) | `docs/workflows/review.md`, `docs/translation-policy.md` |
| Change required metadata fields | `docs/workflows/maintain.md`, `docs/workflows/metadata.md` |
| Change rating structure | `docs/workflows/maintain.md`, `docs/workflows/rating.md` |
| Repair portable-math syntax in named translations | `docs/portable-math-maintainers.md` |
| Change formula rules, validators, or safe fixers | `docs/workflows/maintain.md`, `docs/portable-math-maintainers.md` |
| Change taxonomy, scripts, generated catalog, or maintainer environment | `docs/workflows/maintain.md` |

## Global invariants

- One paper lives at `papers/<primary-area>/<paper-id>/`; the path supplies the paper ID and primary area.
- `paper.yaml` follows the contract in `docs/workflows/metadata.md`; topics are an unordered set drawn only from `config/taxonomy.yaml`.
- File names are fixed: `source.pdf`, `translation.md`, and optional `assets/`.
- Do not infer missing authors, publication years, paper content, experimental results, or citations.
- Ratings follow `docs/workflows/rating.md` and measure the paper, not its translation or availability.
- Full processing of a newly added paper includes rating after translation acceptance; do not call the paper complete while its rating is missing unless the evidence gap is reported as a blocker.
- Do not translate a missing PDF or a PDF over the configured page limit without an explicit user override. Translation work detects and stops on this condition; maintain owns the matching policy record and `source_only <-> skipped` transition.
- Do not regenerate an accepted translation merely to change wording; make evidence-backed, scoped repairs.
- Default review scope is newly added papers, changed accepted content, and papers named by concrete new evidence. Do not start a repository-wide content re-review or bulk historical rewrite unless the user's current request explicitly authorizes that scope.
- Preserve complete references, formulas, tables, algorithms, code, and semantically necessary figures. Whole-page screenshots and QA residue do not belong in the reading path.
- Preserve unrelated user changes and ignored review artifacts.

## Autonomy

For audit/review, explanation, diagnosis, rule design, or planning, inspect and report without modifying papers. Full processing of a newly added paper may write its evidence-backed `rating` after acceptance; rating an existing paper still requires an explicitly named scope.

Only `review-and-repair`, `accept`, or another explicit change authorization may edit a reviewed paper or its status. Repository-wide non-destructive checks do not authorize repository-wide content review or edits. Repair only papers identified by concrete findings within the authorized scope, and ask before expanding to a historical re-review.

For change, build, fix, translate, rate, or archive requests, make in-scope local edits and run non-destructive validation. Ask before external publication, destructive cleanup, paid acquisition, or material scope expansion.

## Commands

```bash
make validate       # fast metadata, status/file, hash, and translation-structure checks
make deep-validate  # full PDF, listing, image, reference, and coverage audit
make source-check PAPER_ID=<paper-id>  # source identity and readability gate
make paper-check PAPER_ID=<paper-id>  # scoped deep gate for one paper during a parallel batch
make review-queue   # risk-first queue for deeper PDF re-review
make catalog        # regenerate CATALOG.md from paper.yaml files
make check          # fast submission gate and generated-file check
make deep-check     # check superset with full repository audit
make diff-check     # whitespace gate including untracked translation files
```

Before finishing an ordinary integrated change, run `make check` and `make diff-check`. For validator changes, project-wide translation-policy changes, or an explicit full audit, run `make deep-check` **instead of** `make check`, then run `make diff-check`.

In a Codex translation batch, the translator runs `make paper-check`. An independent reviewer performs the PDF review and emits a content-bound receipt; receipt generation captures one fresh single-paper check. Accept performs one final translated-grade check before writing. The root agent owns accept, shared state, checkpoints, and integration. Ordinary translation batches do not run `make deep-check`.

A full mechanical check does not authorize a repository-wide content review or rewrite. Report the affected paper IDs and keep repairs within the authorized scope. If a required tool or source is unavailable, state exactly which check was not run and why.

## Completion report

Lead with the outcome. Include applicable changed paper IDs or project files, final ratings, validation results, and unresolved evidence gaps. Use `translated` only when acceptance hashes match; choose every other status from the lifecycle table in `docs/workflows/metadata.md`.
