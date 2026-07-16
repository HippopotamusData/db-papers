PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
MATHJAX_MODULE ?= node_modules/mathjax

.PHONY: catalog catalog-check metadata-check normalize-headers normalize-headers-check fix-math math-check math-audit-github math-audit-github-changed math-audit-katex validate deep-validate paper-check diff-check test doctor check deep-check

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
	PYTHON=$(PYTHON) bash scripts/validate_translations.sh

deep-validate:
	DEEP_VALIDATION=1 PYTHON=$(PYTHON) bash scripts/validate_translations.sh

paper-check:
	@test -n "$(PAPER_ID)" || { echo "ERROR: PAPER_ID is required" >&2; exit 1; }
	PAPER_ID="$(PAPER_ID)" DEEP_VALIDATION=1 PYTHON=$(PYTHON) bash scripts/validate_translations.sh

diff-check:
	bash scripts/check_diff.sh

test:
	$(PYTHON) -m unittest discover -s tests -v

doctor:
	PYTHON=$(PYTHON) bash scripts/doctor.sh

check: test validate catalog-check normalize-headers-check math-check

deep-check: test deep-validate catalog-check normalize-headers-check math-check
