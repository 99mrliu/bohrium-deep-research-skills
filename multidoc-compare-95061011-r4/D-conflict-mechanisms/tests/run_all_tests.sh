#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
bash "$ROOT/examples/run_example.sh"
python3 -m unittest discover -s "$ROOT/tests" -p 'test_*.py' -v
bash "$ROOT/tests/negative_speculation.sh"
python3 - "$ROOT" <<'PY'
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
files = [p for p in root.rglob("*") if p.is_file()]
assert all(not p.is_symlink() for p in root.rglob("*")), "symlink found"
assert len(files) <= 50, f"too many files: {len(files)}"
for path in files:
    assert path.stat().st_size <= 500_000, f"oversize file: {path}"
    if "__pycache__" not in path.parts and not path.name.endswith(".pyc"):
        path.read_text(encoding="utf-8")
text_files = [p for p in files if "__pycache__" not in p.parts and not p.name.endswith(".pyc")]
assert sum(p.stat().st_size for p in text_files) <= 2_000_000, "bundle text exceeds 2 MB"
print(f"Bundle constraints passed: {len(text_files)} UTF-8 text files, {sum(p.stat().st_size for p in text_files)} bytes, no symlinks.")
PY
