PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
MATHJAX_MODULE ?= node_modules/mathjax

.PHONY: python-path python-compile paper-new source-check \
	catalog catalog-check metadata-check normalize-headers normalize-headers-check \
	fix-math math-check math-audit-github math-audit-github-changed \
	math-audit-github-worktree math-audit-katex validate deep-validate paper-check \
	review-queue batch-start batch-check batch-state accept-preflight diff-check \
	test doctor doctor-accept check deep-check

python-path:
	@printf '%s\n' "$(PYTHON)"

python-compile:
	$(PYTHON) -m py_compile scripts/*.py

paper-new:
	@test -n "$(PAPER_ID)" || { echo "ERROR: PAPER_ID is required" >&2; exit 1; }
	@test -n "$(TITLE)" || { echo "ERROR: TITLE is required" >&2; exit 1; }
	@test -n "$(AREA)" || { echo "ERROR: AREA is required" >&2; exit 1; }
	@test -n "$(TOPICS)$(TOPIC)" || { echo "ERROR: TOPICS or TOPIC is required" >&2; exit 1; }
	@test -n "$(URL)" || { echo "ERROR: URL is required" >&2; exit 1; }
	$(PYTHON) scripts/papers.py new --id "$(PAPER_ID)" --title "$(TITLE)" \
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

catalog-check:
	$(PYTHON) scripts/papers.py catalog --check

metadata-check:
	$(PYTHON) scripts/papers.py validate

normalize-headers:
	$(PYTHON) scripts/normalize_translation_headers.py

normalize-headers-check:
	$(PYTHON) scripts/normalize_translation_headers.py --check

fix-math:
	@test -n "$(FILES)" || { echo "ERROR: FILES is required; safe fixes must have an explicit scope" >&2; exit 1; }
	$(PYTHON) scripts/fix_portable_math.py fix --safe $(FILES)

math-check:
	find papers -mindepth 3 -maxdepth 3 -name translation.md -exec $(PYTHON) scripts/validate_github_math.py {} +
	find papers -mindepth 3 -maxdepth 3 -name translation.md -exec $(PYTHON) scripts/verify_math_rendering.py --mathjax-module "$(MATHJAX_MODULE)" {} +
	find papers -mindepth 3 -maxdepth 3 -name translation.md -exec $(PYTHON) scripts/fix_portable_math.py check {} +

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

review-queue:
	$(PYTHON) scripts/papers.py review-queue

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

accept-preflight:
	@test -n "$(PAPER_ID)" || { echo "ERROR: PAPER_ID is required" >&2; exit 1; }
	@test -n "$(BASE)" || { echo "ERROR: BASE is required" >&2; exit 1; }
	@case "$(PAPER_ID)" in *[!a-z0-9-]*|-) \
		echo "ERROR: PAPER_ID must be a kebab-case identifier" >&2; exit 1;; esac
	@base=$$(git rev-parse --verify "$(BASE)^{commit}") || exit 1; \
	git merge-base --is-ancestor "$$base" HEAD || { \
		echo "ERROR: BASE is not an ancestor of HEAD: $$base" >&2; exit 1; \
	}; \
	for marker in config/.acceptance-transaction.yaml \
		config/.acceptance-transaction.cleanup.yaml; do \
		test ! -e "$$marker" || { \
			echo "ERROR: recover acceptance transaction first: $$marker" >&2; \
			exit 1; \
		}; \
	done; \
	statuses=$$($(PYTHON) scripts/papers.py status | \
		awk -F '\t' -v id="$(PAPER_ID)" '$$1 ~ ("/" id "$$") { print $$2 }'); \
	count=$$(printf '%s\n' "$$statuses" | sed '/^$$/d' | wc -l | tr -d ' '); \
	test "$$count" = 1 || { \
		echo "ERROR: PAPER_ID must resolve to exactly one status row (found $$count)" >&2; \
		exit 1; \
	}; \
	test "$$statuses" = draft || { \
		echo "ERROR: accept requires reading_status=draft (found $$statuses)" >&2; \
		exit 1; \
	}
	@if [ -n "$(BATCH_MANIFEST)" ]; then \
		$(PYTHON) scripts/batch_manifest.py check \
			--manifest "$(BATCH_MANIFEST)" \
			--paper-id "$(PAPER_ID)" \
			--expected-state reviewing \
			--expected-base-sha "$(BASE)"; \
	fi
	$(MAKE) doctor-accept
	$(MAKE) paper-check PAPER_ID="$(PAPER_ID)"

diff-check:
	bash scripts/check_diff.sh

test:
	$(PYTHON) -m unittest discover -s tests -v

doctor:
	PYTHON=$(PYTHON) bash scripts/doctor.sh

doctor-accept:
	REQUIRE_GITHUB=1 PYTHON=$(PYTHON) bash scripts/doctor.sh

check: test validate catalog-check normalize-headers-check math-check

deep-check: test deep-validate catalog-check normalize-headers-check math-check
