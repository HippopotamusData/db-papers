#!/usr/bin/env bash

set -uo pipefail

failures=0
PYTHON=${PYTHON:-python3}

require_command() {
  local command_name=$1
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "ERROR: missing required command: $command_name" >&2
    failures=$((failures + 1))
    return
  fi
  echo "$command_name: $(command -v "$command_name")"
}

for command_name in make rg pdfinfo pdftotext pdftoppm perl sed awk find sort mktemp; do
  require_command "$command_name"
done

if [[ "$PYTHON" == */* ]]; then
  if [[ -x "$PYTHON" ]]; then
    echo "python: $PYTHON"
  else
    echo "ERROR: configured Python is not executable: $PYTHON" >&2
    failures=$((failures + 1))
  fi
elif command -v "$PYTHON" >/dev/null 2>&1; then
  echo "python: $(command -v "$PYTHON")"
else
  echo "ERROR: configured Python is unavailable: $PYTHON" >&2
  failures=$((failures + 1))
fi

if [[ -x "$PYTHON" ]] || command -v "$PYTHON" >/dev/null 2>&1; then
  "$PYTHON" --version
fi
command -v make >/dev/null 2>&1 && make --version 2>&1 | head -n 1
command -v rg >/dev/null 2>&1 && rg --version 2>&1 | head -n 1
command -v pdfinfo >/dev/null 2>&1 && pdfinfo -v 2>&1 | head -n 1
command -v pdftotext >/dev/null 2>&1 && pdftotext -v 2>&1 | head -n 1
command -v pdftoppm >/dev/null 2>&1 && pdftoppm -v 2>&1 | head -n 1
command -v perl >/dev/null 2>&1 && perl -v 2>&1 | sed -n '2p'

if command -v make >/dev/null 2>&1; then
  make_banner=$(make --version 2>&1 | head -n 1)
  if [[ ! "$make_banner" =~ ^GNU[[:space:]]Make[[:space:]] ]]; then
    echo "ERROR: GNU Make 3.81 or newer is required" >&2
    failures=$((failures + 1))
  else
    make_version=${make_banner##* }
    if ! awk -v version="$make_version" 'BEGIN {
      split(version, p, "."); exit !((p[1] + 0) > 3 || ((p[1] + 0) == 3 && (p[2] + 0) >= 81))
    }'; then
      echo "ERROR: GNU Make 3.81 or newer is required (found $make_version)" >&2
      failures=$((failures + 1))
    fi
  fi
fi

if command -v rg >/dev/null 2>&1 && ! printf 'feature-smoke\n' | rg -q 'feature-smoke'; then
  echo "ERROR: rg does not support the required quiet search operation" >&2
  failures=$((failures + 1))
fi

if command -v perl >/dev/null 2>&1 && ! perl -e 'exit($] >= 5.030 ? 0 : 1)'; then
  echo "ERROR: Perl 5.30 or newer is required" >&2
  failures=$((failures + 1))
fi

if [[ -x "$PYTHON" ]] || command -v "$PYTHON" >/dev/null 2>&1; then
  "$PYTHON" - <<'PY' || failures=$((failures + 1))
import sys

if sys.version_info < (3, 11):
    raise SystemExit("ERROR: Python 3.11 or newer is required")

import PIL
import yaml


def major_minor(version: str) -> tuple[int, int]:
    values = version.split(".")
    return int(values[0]), int(values[1]) if len(values) > 1 else 0


if not ((6, 0) <= major_minor(yaml.__version__) < (7, 0)):
    raise SystemExit(f"ERROR: PyYAML >=6.0,<7 is required (found {yaml.__version__})")
if not ((10, 0) <= major_minor(PIL.__version__) < (13, 0)):
    raise SystemExit(f"ERROR: Pillow >=10,<13 is required (found {PIL.__version__})")

print(f"PyYAML: {yaml.__version__}")
print(f"Pillow: {PIL.__version__}")
PY
fi

if (( failures > 0 )); then
  echo "Environment check failed with $failures problem(s)." >&2
  exit 1
fi

echo "Environment check passed."
