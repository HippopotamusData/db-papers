PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: catalog catalog-check metadata-check normalize-headers normalize-headers-check normalize-math normalize-math-check validate deep-validate paper-check diff-check test doctor check deep-check

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

normalize-math:
	find papers -mindepth 3 -maxdepth 3 -name translation.md -exec $(PYTHON) scripts/normalize_portable_math.py {} +

normalize-math-check:
	find papers -mindepth 3 -maxdepth 3 -name translation.md -exec $(PYTHON) scripts/normalize_portable_math.py --check {} +

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

check: test validate catalog-check normalize-headers-check normalize-math-check

deep-check: test deep-validate catalog-check normalize-headers-check normalize-math-check
