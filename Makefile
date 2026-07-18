PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
MATHJAX_MODULE ?= node_modules/mathjax

.PHONY: catalog catalog-check metadata-check normalize-headers normalize-headers-check fix-math math-check math-audit-github math-audit-github-changed math-audit-katex validate deep-validate paper-check review-queue diff-check test doctor doctor-accept check deep-check

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
