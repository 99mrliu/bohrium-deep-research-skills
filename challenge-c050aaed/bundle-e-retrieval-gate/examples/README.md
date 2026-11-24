# Synthetic example — retrieval gate end to end

SYNTHETIC fixture data only (all files carry `"synthetic": true` or equivalent
labels). The "source files" named in `files_inventory.json`
(`papers/efficient_transformers_survey.pdf`, `notes/continual_learning_zh.txt`)
are not shipped; only their synthetic metadata is. `output/` is a pre-built
delivery whose `result.json` claims `status: "complete"` — the gate verifies
that claim.

Contents: 6 annotations + 4 notes (mixed English/Chinese) + 2-file inventory,
`smoke.json` (2 known-item queries + 1 negative control), a fake `case.json`
whose `output_contract` is `["inventory","notes","index","verification"]`, and
the pre-built `output/` dir.

All commands run from this `examples/` directory; `BUNDLE` is the bundle root:

```
BUNDLE=/path/to/bundle-e-retrieval-gate
cd "$BUNDLE/examples"
```

## 1. Build the index (byte-identical to the shipped output/index.json)

```
python3 "$BUNDLE/scripts/build_index.py" \
  --annotations annotations.jsonl --notes notes.jsonl \
  --inventory files_inventory.json --out /tmp/work_index.json
cmp /tmp/work_index.json output/index.json && echo IDENTICAL
```

## 2. Retrieval

```
# English theme query
python3 "$BUNDLE/scripts/query.py" --index output/index.json \
  --q "sparse attention" --log query_log.jsonl

# Chinese query — matched via CJK bigrams, finds note-002 at rank 1
python3 "$BUNDLE/scripts/query.py" --index output/index.json \
  --q "增量学习" --log query_log.jsonl

# No-hit query — structured report with diagnosis + suggestions
python3 "$BUNDLE/scripts/query.py" --index output/index.json \
  --q "quantum zebra teleportation" --log query_log.jsonl

# Facet elimination — the --file facet is named as the eliminator
python3 "$BUNDLE/scripts/query.py" --index output/index.json \
  --q "sparse" --file "notes/continual_learning_zh.txt" --log query_log.jsonl

# Low-recall marking — best score 1 < threshold 2.0 -> low_confidence
python3 "$BUNDLE/scripts/query.py" --index output/index.json --q "softmax"

# Tag and time retrieval
python3 "$BUNDLE/scripts/query.py" --index output/index.json --tag "增量学习"
python3 "$BUNDLE/scripts/query.py" --index output/index.json --since 2026-11-21
```

## 3. Gate — pass case

```
python3 "$BUNDLE/scripts/gate.py" \
  --case case.json --output-dir output --index output/index.json \
  --smoke-queries smoke.json --out output/gate_report.json
echo "exit: $?"   # 0
```

## 4. Gate — seeded contract violation (exit 3, result forced partial)

```
rm -rf /tmp/out_bad && cp -R output /tmp/out_bad
python3 - <<'EOF'
import json
r = json.load(open('/tmp/out_bad/result.json', encoding='utf-8'))
del r['index']                      # remove a field the output_contract names
json.dump(r, open('/tmp/out_bad/result.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
EOF
python3 "$BUNDLE/scripts/gate.py" \
  --case case.json --output-dir /tmp/out_bad --index output/index.json \
  --smoke-queries smoke.json --out /tmp/out_bad/gate_report.json
echo "exit: $?"   # 3 — and /tmp/out_bad/result.json now says status: partial
```

## 5. Gate — tampered index (exit 3, caught two ways)

```
rm -rf /tmp/out_tamper && cp -R output /tmp/out_tamper
python3 - <<'EOF'
data = open('/tmp/out_tamper/index.json', 'rb').read()
i = data.rfind(b': 1')             # flip one tf digit; JSON stays valid
open('/tmp/out_tamper/index.json', 'wb').write(data[:i] + b': 2' + data[i+3:])
EOF
python3 "$BUNDLE/scripts/gate.py" \
  --case case.json --output-dir /tmp/out_tamper --index /tmp/out_tamper/index.json \
  --smoke-queries smoke.json --out /tmp/out_tamper/gate_report.json
echo "exit: $?"   # 3 — artifact_integrity (sha256) AND replay_determinism fail
```

Real observed output for every command above: see `EXPECTED.md`.
