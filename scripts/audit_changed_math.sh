#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: audit_changed_math.sh BASE" >&2
  exit 2
fi

base=$1
PYTHON=${PYTHON:-python3}
files=()
profile_paths=(
  .github/workflows/check.yml
  Makefile
  docs/portable-math-maintainers.md
  docs/translation-policy.md
  package-lock.json
  package.json
  pyproject.toml
  scripts/audit_changed_math.sh
  scripts/fix_portable_math.py
  scripts/render_mathjax.cjs
  scripts/validate_github_math.py
  scripts/verify_math_rendering.py
)

if ! git diff --quiet "$base...HEAD" -- "${profile_paths[@]}"; then
  while IFS= read -r -d '' path; do
    files+=("$path")
  done < <(
    find papers -mindepth 3 -maxdepth 3 -name translation.md -print0
  )
else
  while IFS= read -r -d '' path; do
    files+=("$path")
  done < <(
    git diff --name-only --diff-filter=ACMR -z "$base...HEAD" -- \
      'papers/*/*/translation.md'
  )
fi

if (( ${#files[@]} == 0 )); then
  echo "No changed translations require a GitHub math audit."
  exit 0
fi

"$PYTHON" scripts/verify_math_rendering.py --github "${files[@]}"
