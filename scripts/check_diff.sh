#!/usr/bin/env bash

set -euo pipefail

git diff --check
git diff --cached --check

failures=0
while IFS= read -r -d '' path; do
  issues=$(git diff --no-index --check /dev/null "$path" 2>&1 || true)
  if [[ -n "$issues" ]]; then
    printf '%s\n' "$issues" >&2
    failures=$((failures + 1))
  fi
done < <(git ls-files --others --exclude-standard -z)

if (( failures > 0 )); then
  echo "Untracked-file whitespace validation failed with $failures file(s)." >&2
  exit 1
fi

echo "Tracked, staged, and untracked diff whitespace validation passed."
