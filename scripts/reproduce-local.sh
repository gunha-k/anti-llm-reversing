#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source scripts/activate.sh
python3 scripts/reproduce.py "${1:-standalone}" --jobs "${JOBS:-2}" --deps "$ROOT/.local/sysroot"
