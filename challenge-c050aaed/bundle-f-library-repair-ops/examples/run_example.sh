#!/usr/bin/env bash
# SYNTHETIC EXAMPLE runner for library-repair-ops.
# Executes survey -> plan -> apply -> verify -> rollback on the synthetic
# fixture and prints the produced artifacts. Safe to re-run: it removes
# only its own output directory first.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
K="$(dirname "$HERE")"
FIX="$HERE/fixture"
WORK="$HERE/out/work"
OUT="$HERE/out/output"
rm -rf "$HERE/out"
mkdir -p "$WORK" "$OUT"

echo "== 1. survey (read-only) =="
python3 "$K/scripts/librepair.py" survey --root "$FIX/materials" \
    --out "$WORK/manifest.json"

echo "== 2. plan (admin notes override heuristics) =="
python3 "$K/scripts/librepair.py" plan --manifest "$WORK/manifest.json" \
    --notes "$FIX/materials/行政说明.txt" --out "$WORK/plan.json"

echo "== 3. apply (copy-only, journaled) =="
python3 "$K/scripts/librepair.py" apply --plan "$WORK/plan.json" \
    --root "$FIX/materials" --dest "$OUT/organized_library" \
    --journal "$WORK/journal.jsonl"

echo "== 4. verify (re-hash + journal chain + lost-source check) =="
python3 "$K/scripts/librepair.py" verify --dest "$OUT/organized_library" \
    --journal "$WORK/journal.jsonl" --manifest "$WORK/manifest.json" \
    --out "$OUT/verify_report.json"

cp "$WORK/manifest.json" "$WORK/plan.json" "$WORK/journal.jsonl" "$OUT/"

echo "== organized layout =="
find "$OUT/organized_library" -type f | sort

echo "== journal (first 3 entries) =="
head -3 "$OUT/journal.jsonl"

echo "== verify_report =="
cat "$OUT/verify_report.json"

echo "== 5. rollback drill (then re-apply to leave a complete example) =="
python3 "$K/scripts/librepair.py" rollback --dest "$OUT/organized_library" \
    --journal "$WORK/journal.jsonl"
python3 "$K/scripts/librepair.py" apply --plan "$WORK/plan.json" \
    --root "$FIX/materials" --dest "$OUT/organized_library" \
    --journal "$WORK/journal2.jsonl"
python3 "$K/scripts/librepair.py" verify --dest "$OUT/organized_library" \
    --journal "$WORK/journal2.jsonl" --manifest "$WORK/manifest.json" \
    --out "$OUT/verify_report.json"

echo "SYNTHETIC EXAMPLE OK: artifacts under $OUT"
