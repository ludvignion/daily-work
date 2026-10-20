#!/usr/bin/env bash
# Install uv if it is missing, with its official installer, then a Python for it. Run by
# /daily-work:init after the person agrees. Telemetry and content logging run on this Python.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

if ! uv_bin >/dev/null; then
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" ;;
    *) curl -LsSf https://astral.sh/uv/install.sh | sh ;;
  esac
fi
u=$(uv_bin) || { echo "refused: uv did not install; see https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
"$u" python find --managed-python >/dev/null 2>&1 || "$u" python install --quiet
echo "python: $(py -c 'import platform; print(platform.python_version())') through uv"
