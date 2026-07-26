#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: audit_changed_math.sh BASE" >&2
  exit 2
fi

base=$1
PYTHON=${PYTHON:-python3}
audit_all=${AUDIT_ALL:-false}
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
files=()
profile_paths=(
  .github/workflows/github-math-audit.yml
  scripts/audit_changed_math.sh
  scripts/validate_github_math.py
  scripts/verify_math_rendering.py
)

if [[ "$audit_all" != "false" && "$audit_all" != "true" ]]; then
  echo "ERROR: AUDIT_ALL must be true or false" >&2
  exit 1
fi
if ! base=$(git rev-parse --verify "$base^{commit}" 2>/dev/null); then
  echo "ERROR: cannot resolve trusted audit base: $1" >&2
  exit 1
fi
if ! git merge-base "$base" HEAD >/dev/null 2>&1; then
  echo "ERROR: trusted audit base has no common ancestor with HEAD: $base" >&2
  exit 1
fi

if [[ "$audit_all" == "true" ]] ||
   ! git diff --quiet "$base...HEAD" -- "${profile_paths[@]}"; then
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

audit_args=(--github)
if [[ ${AUDIT_UNTRUSTED_DATA:-0} == 1 ]]; then
  audit_args+=(--unchecked-input)
fi
"$PYTHON" "$script_dir/verify_math_rendering.py" "${audit_args[@]}" "${files[@]}"
