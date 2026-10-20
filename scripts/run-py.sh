#!/usr/bin/env bash
# run-py.sh <script.py> [args]: run one of the plugin's Python scripts through uv, for the hooks
# and the feedback skill. Exits 1 with no output when no Python is set up.
source "$(dirname "$0")/lib.sh"
py "$(dirname "$0")/$1" "${@:2}"
