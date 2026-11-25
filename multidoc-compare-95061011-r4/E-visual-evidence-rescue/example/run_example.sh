#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
TOOL="$ROOT/scripts/visual_evidence.py"
INPUT="$HERE/input"
WORK="$HERE/work"
OUTPUT="$HERE/output"
mkdir -p "$WORK" "$OUTPUT"

python3 "$TOOL" ingest \
  --workorder "$INPUT/comparison-workorder.json" \
  --input-root "$INPUT" --work "$WORK"

layout_path() {
  python3 -c 'import json, sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print(next(d["layout_text"] for d in data["documents"] if d["source_document_id"] == sys.argv[2]))' \
    "$WORK/ingest-manifest.json" "$1"
}

python3 "$TOOL" parse-layout \
  --input "$(layout_path DOC_A)" \
  --source-document-id DOC_A --paragraph-id DOC_A:caption-001 \
  --output "$WORK/parsed-regions/DOC_A.json"
python3 "$TOOL" parse-layout \
  --input "$(layout_path DOC_B)" \
  --source-document-id DOC_B --paragraph-id DOC_B:caption-001 \
  --output "$WORK/parsed-regions/DOC_B.json"
python3 "$TOOL" parse-layout \
  --input "$(layout_path DOC_GAMMA)" \
  --source-document-id DOC_GAMMA --paragraph-id DOC_GAMMA:p001 \
  --output "$WORK/parsed-regions/DOC_GAMMA.json"

python3 "$TOOL" validate --case "$INPUT/case.json" \
  --workorder "$INPUT/comparison-workorder.json" --manifest "$WORK/ingest-manifest.json"
python3 "$TOOL" render --case "$INPUT/case.json" \
  --workorder "$INPUT/comparison-workorder.json" --manifest "$WORK/ingest-manifest.json" --output "$OUTPUT"

printf '\nOutputs:\n%s\n%s\n%s\n' \
  "$OUTPUT/comparison-matrix.md" "$OUTPUT/source-regions.md" "$OUTPUT/result.json"
