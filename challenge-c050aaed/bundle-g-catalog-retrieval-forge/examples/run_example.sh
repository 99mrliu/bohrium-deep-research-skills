#!/usr/bin/env bash
# SYNTHETIC EXAMPLE runner for catalog-retrieval-forge.
# Executes catalog -> index -> query -> answer -> contract on the
# synthetic fixture and prints the produced artifacts. Safe to re-run:
# it removes only its own output directory first.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
K="$(dirname "$HERE")"
FIX="$HERE/fixture"
WORK="$HERE/out/work"
OUT="$HERE/out/output"
rm -rf "$HERE/out"
mkdir -p "$WORK" "$OUT"

echo "== 1. catalog (read-only; sidecar metadata + admin notes) =="
python3 "$K/scripts/catalogforge.py" catalog --root "$FIX/materials" \
    --meta "$FIX/materials/metadata.csv" \
    --notes "$FIX/materials/行政说明.txt" \
    --out "$OUT/catalog.jsonl"

echo "== 2. index (SQLite; FTS5 when available) =="
python3 "$K/scripts/catalogforge.py" index --catalog "$OUT/catalog.jsonl" \
    --db "$WORK/library.sqlite"
cp "$WORK/library.sqlite" "$OUT/library.sqlite" 2>/dev/null || \
    echo "(binary sqlite not copied into a text-only bundle at submission)"

echo "== 3. smoke query =="
python3 "$K/scripts/catalogforge.py" query --db "$WORK/library.sqlite" \
    --q "单原子 稳定性" --k 3 --out "$OUT/query_smoke.json" >/dev/null
python3 -c "import json;d=json.load(open('$OUT/query_smoke.json'));print('hits:',d['hit_count']);[print('-',h['path'],'|',h['matched_field']) for h in d['hits']]"

echo "== 4. answer questions (q3 must abstain honestly) =="
python3 "$K/scripts/catalogforge.py" answer --db "$WORK/library.sqlite" \
    --questions "$FIX/input/questions.json" --out "$OUT/answers.jsonl"
cat "$OUT/answers.jsonl"

echo "== 5. contract assembly against case.json output_contract =="
python3 "$K/scripts/catalogforge.py" contract --case "$FIX/input/case.json" \
    --map inventory="$OUT/catalog.jsonl" \
    --map answers="$OUT/answers.jsonl" \
    --map version_relations="$OUT/catalog.edges.json" \
    --out "$OUT/result.json" || true
python3 -c "import json;d=json.load(open('$OUT/result.json'));print('case_id:',d['case_id']);print('status:',d['status']);print('fields:',sorted(d.keys()))"

echo "SYNTHETIC EXAMPLE OK: artifacts under $OUT"
