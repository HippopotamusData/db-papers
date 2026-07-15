# DB Papers agent contract

## Outcome

Maintain a reader-first archive of database papers, complete Chinese translations, and direct reading-value ratings. Keep per-paper metadata minimal, use verifiable evidence, and never invent missing facts.

## Sources of truth

Use this order when facts conflict:

1. The user's current scope and explicit overrides.
2. The paper's `source.pdf` for paper content.
3. The paper directory for its ID and primary area.
4. The paper's `paper.yaml` for title, authors, year, source URL, topics, reading status, and an optional rating.
5. Versioned values under `config/`; `scripts/project_config.py` defines their schemas and controlled codes.
6. Active documents under `docs/`; use Git history for superseded policy and detailed review history.

## Task routing

Before acting, read only the document or documents listed for the task:

| Task | Required documents |
| --- | --- |
| Add or recover a source paper | `docs/workflows/ingest.md` |
| Classify or enrich reading metadata | `docs/workflows/metadata.md` |
| Score a paper's reading value | `docs/workflows/rating.md` |
| Create or repair a translation | `docs/workflows/translate.md`, `docs/translation-policy.md` |
| Coordinate a Codex translation batch with direct subagents | `docs/workflows/batch-translate.md`, `docs/translation-policy.md` |
| Audit, repair, or accept a translation | `docs/workflows/review.md`, `docs/translation-policy.md` |
| Change required metadata fields | `docs/workflows/maintain.md`, `docs/workflows/metadata.md` |
| Change rating structure | `docs/workflows/maintain.md`, `docs/workflows/rating.md` |
| Change taxonomy, scripts, generated catalog, or maintainer environment | `docs/workflows/maintain.md` |

## Global invariants

- One paper lives at `papers/<primary-area>/<paper-id>/`; the path supplies the paper ID and primary area.
- `paper.yaml` follows the contract in `docs/workflows/metadata.md`; topics are an unordered set drawn only from `config/taxonomy.yaml`.
- File names are fixed: `source.pdf`, `translation.md`, and optional `assets/`.
- Do not infer missing authors, publication years, paper content, experimental results, or citations.
- Ratings follow `docs/workflows/rating.md` and measure the paper, not its translation or availability.
- Full processing of a newly added paper includes rating after translation acceptance; do not call the paper complete while its rating is missing unless the evidence gap is reported as a blocker.
- Do not translate a missing PDF or a PDF over the configured page limit without an explicit user override.
- Do not regenerate an accepted translation merely to change wording; make evidence-backed, scoped repairs.
- Preserve complete references, formulas, tables, algorithms, code, and semantically necessary figures. Whole-page screenshots and QA residue do not belong in the reading path.
- Preserve unrelated user changes and ignored review artifacts.

## Autonomy

For audit/review, explanation, diagnosis, rule design, or planning requests, inspect relevant files and report without modifying papers. Full processing of a newly added paper carries standing authorization to write its evidence-backed `rating` after acceptance; rating an existing paper outside that lifecycle still requires an explicitly named scope. Only `review-and-repair`, `accept`, or another explicit change authorization may edit a reviewed paper or its status. For change, build, fix, translate, rate, or archive requests, make in-scope local edits and run non-destructive validation. Ask before external publication, destructive cleanup, acquiring paid material, or materially expanding scope.

## Commands

```bash
make validate       # fast metadata, status/file, hash, and translation-structure checks
make deep-validate  # full PDF, listing, image, reference, and coverage audit
make paper-check PAPER_ID=<paper-id>  # scoped deep gate for one paper during a parallel batch
make catalog        # regenerate CATALOG.md from paper.yaml files
make check          # fast submission gate and generated-file check
make deep-check     # full repository audit; reserve for validator/policy changes or an explicit audit
make diff-check     # whitespace gate including untracked translation files
```

Before finishing an integrated repository change, run `make check` and `make diff-check`. In a Codex translation batch, translation and review subagents use `make paper-check` while the root agent owns shared state, per-round checkpoints, and final integration. Paper acceptance always runs the deep validator for that paper, so ordinary translation batches do not run `make deep-check`. Reserve `make deep-check` for validator changes, project-wide translation-policy changes that may affect historical papers, or an explicit full-repository audit. If a required tool or source is unavailable, state the exact unrun check and why.

## Completion report

Lead with the outcome. Include applicable changed paper IDs or project files, final ratings, validation results, and unresolved evidence gaps. Use `translated` only when acceptance hashes match; choose every other status from the lifecycle table in `docs/workflows/metadata.md`.
