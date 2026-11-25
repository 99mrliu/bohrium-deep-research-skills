#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$HERE/../validation/evidence-anchor/output"
WORK="$HERE/../validation/evidence-anchor/work"
mkdir -p "$OUT" "$WORK"
python3 "$HERE/scripts/evidence_pipeline.py" --input "$HERE/examples" --work "$WORK" --output "$OUT" --claims "$HERE/examples/claims.json"
python3 - "$OUT/result.json" "$OUT/figure.png" "$OUT/figure.pdf" <<'PY'
import json,sys
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text())
assert r['case_id']=='SYN-EVIDENCE-001' and r['status']=='success',r
assert Path(sys.argv[2]).read_bytes()[:8]==b'\x89PNG\r\n\x1a\n'
assert Path(sys.argv[3]).read_bytes()[:4]==b'%PDF'
print('synthetic example verified:',r['case_id'],r['status'])
PY
