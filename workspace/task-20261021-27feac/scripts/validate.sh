#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
.venv/bin/python -m compileall -q local_notes tests
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
