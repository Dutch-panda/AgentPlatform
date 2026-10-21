#!/bin/sh
set -eu
cd /app/workspace
PYTHON=/app/workspace/.venv/bin/python
"$PYTHON" -m pytest -q
"$PYTHON" - <<'PY'
import subprocess
import sys

result = subprocess.run(["/app/workspace/.venv/bin/python", 'compound_interest.py'],
                        check=True, capture_output=True, text=True)
assert result.stdout == 'Final balance: $1,647.01\nInterest earned: $647.01\n', result.stdout
result = subprocess.run(["/app/workspace/.venv/bin/python", '-c', 'import compound_interest'],
                        check=True, capture_output=True, text=True)
assert result.stdout == '', result.stdout
print('Example output and silent reusable import verified.')
PY
