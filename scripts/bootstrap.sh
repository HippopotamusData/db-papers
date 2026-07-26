#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap.sh [--site]

Without arguments, install the maintainer dependencies and run make doctor.
With --site, install only the dependencies required by make site-check.
EOF
}

profile=maintainer
case "${1:-}" in
  "")
    ;;
  --site)
    profile=site
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

if (( $# > 1 )); then
  usage >&2
  exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
root=$(cd -- "$script_dir/.." && pwd -P)
cd "$root"

if [[ -n "${BOOTSTRAP_PYTHON:-}" ]]; then
  python_candidates=("$BOOTSTRAP_PYTHON")
else
  python_candidates=(python3 python3.14 python3.13 python3.12 python3.11 python)
fi
bootstrap_python=
for candidate in "${python_candidates[@]}"; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c \
       'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'
  then
    bootstrap_python=$candidate
    break
  fi
done
if [[ -z "$bootstrap_python" ]]; then
  echo "ERROR: Python 3.11 or newer is required; set BOOTSTRAP_PYTHON" >&2
  exit 1
fi

venv_dir="$root/.venv"
venv_python="$venv_dir/bin/python"
if [[ -L "$venv_dir" ]]; then
  echo "ERROR: .venv must not be a symlink; each worktree owns its environment" >&2
  exit 1
fi
if [[ ! -x "$venv_python" ]]; then
  if [[ -e "$venv_dir" ]]; then
    echo "ERROR: existing .venv is incomplete; repair or remove it explicitly" >&2
    exit 1
  fi
  "$bootstrap_python" -m venv "$venv_dir"
fi

if [[ "$profile" == "maintainer" && -L "$root/node_modules" ]]; then
  echo \
    "ERROR: node_modules must not be a symlink; each worktree owns its dependencies" \
    >&2
  exit 1
fi

"$venv_python" -m pip install --upgrade "pip==26.1.2"

if [[ "$profile" == "site" ]]; then
  "$venv_python" -m pip install --group site
else
  "$venv_python" -m pip install --group dev
  if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm is required for the maintainer bootstrap" >&2
    exit 1
  fi
  npm ci
  make --no-print-directory doctor \
    PYTHON=.venv/bin/python \
    MATHJAX_MODULE=node_modules/mathjax
fi

printf '%s\n' \
  "BOOTSTRAP_RESULT status=passed profile=$profile worktree=$root"
