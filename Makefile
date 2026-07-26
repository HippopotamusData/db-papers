PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
MATHJAX_MODULE ?= node_modules/mathjax
TEST_VERBOSE ?= 0

.DEFAULT_GOAL := help

.PHONY: help python-compile paper-new source-check \
	catalog normalize-headers \
	fix-math math-check math-check-files math-audit-github math-audit-github-changed \
	math-audit-github-worktree math-audit-katex validate deep-validate paper-check \
	batch-start batch-check batch-state diff-check \
	site-check site-serve test doctor check deep-check \
	_catalog-check _normalize-headers-check _site-prepare _site-build _deep-check

help:
	@printf '%s\n' \
		'DB Papers maintenance commands:' \
		'  make check                         fast repository submission gate' \
		'  make diff-check                    whitespace and untracked-translation gate' \
		'  make validate                      fast metadata and translation-structure checks' \
		'  make deep-validate                 full PDF, resource, and coverage audit' \
		'  make paper-check PAPER_ID=<id>     deep gate for one paper' \
		'  make source-check PAPER_ID=<id>    source identity and readability gate' \
		'  make catalog                       regenerate CATALOG.md' \
		'  make site-check                    build and verify the reader site' \
		'  make site-serve                    serve the reader site locally' \
		'  make deep-check DEEP_REASON=<reason>  full audit for semantic changes' \
		'    reasons: content-semantics, publication-semantics, validator-semantics, full-audit' \
		'  make math-check-files FILES="..."  scoped portable-math gate' \
		'  make paper-new ...                 create one minimal paper record' \
		'  make batch-start|batch-check|batch-state ...  temporary batch coordination' \
		'  make doctor                        verify the maintainer environment' \
		'' \
		'Use TEST_VERBOSE=1 with make test/check for verbose unittest output.'

python-compile:
	$(PYTHON) -m py_compile scripts/*.py

paper-new:
	@test -n "$(PAPER_ID)" || { echo "ERROR: PAPER_ID is required" >&2; exit 1; }
	@test -n "$(TITLE)" || { echo "ERROR: TITLE is required" >&2; exit 1; }
	@test -n "$(TITLE_ZH)" || { echo "ERROR: TITLE_ZH is required" >&2; exit 1; }
	@test -n "$(AREA)" || { echo "ERROR: AREA is required" >&2; exit 1; }
	@test -n "$(TOPICS)$(TOPIC)" || { echo "ERROR: TOPICS or TOPIC is required" >&2; exit 1; }
	@test -n "$(URL)" || { echo "ERROR: URL is required" >&2; exit 1; }
	$(PYTHON) scripts/papers.py new --id "$(PAPER_ID)" --title "$(TITLE)" \
		--title-zh "$(TITLE_ZH)" \
		--area "$(AREA)" \
		$(foreach topic,$(if $(strip $(TOPICS)),$(TOPICS),$(TOPIC)),--topic "$(topic)") \
		--url "$(URL)"

source-check:
	@test -n "$(PAPER_ID)" || { echo "ERROR: PAPER_ID is required" >&2; exit 1; }
	@case "$(PAPER_ID)" in *[!a-z0-9-]*|-) \
		echo "ERROR: PAPER_ID must be a kebab-case identifier" >&2; exit 1;; esac
	@metadata=$$(find papers -mindepth 3 -maxdepth 3 -path "*/$(PAPER_ID)/paper.yaml" -print); \
	count=$$(printf '%s\n' "$$metadata" | sed '/^$$/d' | wc -l | tr -d ' '); \
	test "$$count" = 1 || { \
		echo "ERROR: PAPER_ID must resolve to exactly one paper.yaml (found $$count)" >&2; \
		exit 1; \
	}; \
	pdf="$(SOURCE_PDF)"; \
	if [ -z "$$pdf" ]; then pdf="$${metadata%/paper.yaml}/source.pdf"; fi; \
	$(PYTHON) scripts/validate_source_pdf.py \
		--metadata "$$metadata" --pdf "$$pdf" --verbose

catalog:
	$(PYTHON) scripts/papers.py catalog

_catalog-check:
	$(PYTHON) scripts/papers.py catalog --check

normalize-headers:
	$(PYTHON) scripts/normalize_translation_headers.py

_normalize-headers-check:
	$(PYTHON) scripts/normalize_translation_headers.py --check

fix-math:
	@test -n "$(FILES)" || { echo "ERROR: FILES is required; safe fixes must have an explicit scope" >&2; exit 1; }
	$(PYTHON) scripts/fix_portable_math.py fix --safe $(FILES)

math-check:
	find papers -mindepth 3 -maxdepth 3 -name translation.md -exec $(PYTHON) scripts/verify_math_rendering.py --mathjax-module "$(MATHJAX_MODULE)" {} +
	find papers -mindepth 3 -maxdepth 3 -name translation.md -exec $(PYTHON) scripts/fix_portable_math.py check {} +

math-check-files:
	@test -n "$(FILES)" || { echo "ERROR: FILES is required for scoped math validation" >&2; exit 1; }
	@for file in $(FILES); do \
		case "$$file" in papers/*/*/translation.md) ;; \
			*) echo "ERROR: invalid translation path: $$file" >&2; exit 1;; \
		esac; \
		test -f "$$file" || { echo "ERROR: translation not found: $$file" >&2; exit 1; }; \
	done
	$(PYTHON) scripts/verify_math_rendering.py --mathjax-module "$(MATHJAX_MODULE)" $(FILES)
	$(PYTHON) scripts/fix_portable_math.py check $(FILES)

math-audit-github:
	@if [ -n "$(FILES)" ]; then \
		$(PYTHON) scripts/verify_math_rendering.py --github $(FILES); \
	else \
		find papers -mindepth 3 -maxdepth 3 -name translation.md -exec $(PYTHON) scripts/verify_math_rendering.py --github {} +; \
	fi

math-audit-github-changed:
	@test -n "$(BASE)" || { echo "ERROR: BASE is required" >&2; exit 1; }
	PYTHON=$(PYTHON) bash scripts/audit_changed_math.sh "$(BASE)"

math-audit-github-worktree:
	@test -n "$(BASE)" || { echo "ERROR: BASE is required" >&2; exit 1; }
	@base=$$(git rev-parse --verify "$(BASE)^{commit}") || exit 1; \
	git merge-base --is-ancestor "$$base" HEAD || { \
		echo "ERROR: BASE is not an ancestor of HEAD: $$base" >&2; exit 1; \
	}; \
	files=$$({ \
		git diff --name-only --diff-filter=ACMR "$$base" -- \
			'papers/*/*/translation.md'; \
		git ls-files --others --exclude-standard -- \
			'papers/*/*/translation.md'; \
	} | LC_ALL=C sort -u); \
	if [ -z "$$files" ]; then \
		echo "No changed worktree translations require a GitHub math audit."; \
	else \
		$(PYTHON) scripts/verify_math_rendering.py --github $$files; \
	fi

math-audit-katex:
	@test -n "$(KATEX_MODULE)" || { echo "ERROR: KATEX_MODULE is required" >&2; exit 1; }
	find papers -mindepth 3 -maxdepth 3 -name translation.md -exec $(PYTHON) scripts/verify_math_rendering.py --katex-module "$(KATEX_MODULE)" {} +

validate:
	env -u PAPER_ID -u SKIP_METADATA_VALIDATION PYTHON=$(PYTHON) bash scripts/validate_translations.sh

deep-validate:
	env -u PAPER_ID -u SKIP_METADATA_VALIDATION DEEP_VALIDATION=1 PYTHON=$(PYTHON) bash scripts/validate_translations.sh

paper-check:
	@test -n "$(PAPER_ID)" || { echo "ERROR: PAPER_ID is required" >&2; exit 1; }
	env -u PAPER_ID -u SKIP_METADATA_VALIDATION DEEP_VALIDATION=1 PYTHON=$(PYTHON) bash scripts/validate_translations.sh --paper-id "$(PAPER_ID)"

batch-start:
	@test -n "$(BATCH_MANIFEST)" || { echo "ERROR: BATCH_MANIFEST is required" >&2; exit 1; }
	@test -n "$(MODE)" || { echo "ERROR: MODE is required" >&2; exit 1; }
	@test -n "$(BASE)" || { echo "ERROR: BASE is required" >&2; exit 1; }
	@test -n "$(PAPER_IDS)" || { echo "ERROR: PAPER_IDS is required" >&2; exit 1; }
	$(PYTHON) scripts/batch_manifest.py init \
		--manifest "$(BATCH_MANIFEST)" \
		--mode "$(MODE)" \
		--base-sha "$(BASE)" \
		$(foreach paper,$(PAPER_IDS),--paper-id "$(paper)")

batch-check:
	@test -n "$(BATCH_MANIFEST)" || { echo "ERROR: BATCH_MANIFEST is required" >&2; exit 1; }
	$(PYTHON) scripts/batch_manifest.py check \
		--manifest "$(BATCH_MANIFEST)" \
		$(if $(strip $(PAPER_ID)),--paper-id "$(PAPER_ID)") \
		$(if $(strip $(EXPECTED_STATE)),--expected-state "$(EXPECTED_STATE)") \
		$(if $(strip $(BASE)),--expected-base-sha "$(BASE)")

batch-state:
	@test -n "$(BATCH_MANIFEST)" || { echo "ERROR: BATCH_MANIFEST is required" >&2; exit 1; }
	@test -n "$(PAPER_ID)" || { echo "ERROR: PAPER_ID is required" >&2; exit 1; }
	@test -n "$(STATE)" || { echo "ERROR: STATE is required" >&2; exit 1; }
	$(PYTHON) scripts/batch_manifest.py set-state \
		--manifest "$(BATCH_MANIFEST)" \
		--paper-id "$(PAPER_ID)" \
		--state "$(STATE)"

diff-check:
	bash scripts/check_diff.sh

_site-prepare:
	$(PYTHON) scripts/build_site.py prepare

_site-build: _site-prepare
	$(PYTHON) -m zensical build --clean --config-file site.generated.toml

site-check: _site-build
	$(PYTHON) scripts/build_site.py check

site-serve: _site-prepare
	$(PYTHON) -m zensical serve --config-file site.generated.toml

test:
	$(PYTHON) -m unittest discover -s tests $(if $(filter 1 true yes,$(TEST_VERBOSE)),-v)

doctor:
	PYTHON=$(PYTHON) bash scripts/doctor.sh

check: test validate _catalog-check _normalize-headers-check

deep-check:
	@case "$(DEEP_REASON)" in \
		content-semantics|publication-semantics|validator-semantics|full-audit) ;; \
		*) \
			echo "ERROR: deep-check requires DEEP_REASON=" \
				"{content-semantics,publication-semantics,validator-semantics,full-audit}" >&2; \
			exit 1;; \
	esac
	@printf '%s\n' "Deep validation reason: $(DEEP_REASON)"
	@$(MAKE) --no-print-directory _deep-check

_deep-check: test deep-validate _catalog-check _normalize-headers-check math-check
