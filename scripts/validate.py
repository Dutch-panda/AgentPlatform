"""Run platform unit tests from any working directory."""

from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    raise SystemExit(subprocess.call(
        [sys.executable, "-m", "pytest", *sys.argv[1:]],
        cwd=Path(__file__).resolve().parent.parent,
    ))
