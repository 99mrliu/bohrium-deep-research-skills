#!/bin/bash
# run_example.sh — deterministic end-to-end SYNTHETIC example for deliverable-forge.
#
# Simulates the /input, /app/work, /app/output three-part layout in a mktemp sandbox:
#   checklist -> (simulated model edits + result_parts) -> assemble
#   -> FORGE_NO_RENDER=1 render (deterministic branch) -> verify_delivery
#   -> fault injection (delete one part, re-assemble, expect exit!=0 + partial)
# Then diffs every product against expected/ (frozen by a real run).
#
# Regenerate expected/ from a real run with:  FORGE_EXAMPLE_FREEZE=1 ./run_example.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/../.." && pwd)"
SCRIPTS="$BUNDLE/scripts"
INPUT="$HERE/input"
EXPECTED="$HERE/expected"
NOTE="SYNTHETIC EXAMPLE — 合成示例，非正式案例结果"

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/forge-example.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT
WORK="$SANDBOX/app/work"
OUT="$SANDBOX/app/output"
mkdir -p "$WORK/result_parts" "$WORK/chapters" "$OUT/chapters"

echo "== [1/6] contract_checklist: case.json -> checklist.json =="
python3 "$SCRIPTS/contract_checklist.py" \
  --case "$INPUT/case.json" --out "$WORK/checklist.json" --note "$NOTE"

echo "== [2/6] simulate model edits + write result_parts =="
python3 - "$INPUT" "$WORK" "$OUT" <<'PYEOF'
"""Simulated agent: apply workorder edits and write result_parts (stdlib only)."""
import json, os, sys

inp, work, out = sys.argv[1], sys.argv[2], sys.argv[3]
chapters = ["ch01.md", "ch02.md", "ch03.md"]
PROTECTED = "《隔膜槽维护规程》"   # quoted title kept unchanged per workorder #1

for name in chapters:
    with open(os.path.join(inp, "chapters", name), encoding="utf-8") as f:
        text = f.read()
    # workorder #1: 隔膜 -> 隔板 everywhere except inside the quoted title
    text = (text.replace(PROTECTED, "\x00TITLE\x00")
                .replace("隔膜", "隔板")
                .replace("\x00TITLE\x00", PROTECTED))
    # workorder #2: ch03 unit fix
    if name == "ch03.md":
        text = text.replace("m3/h", "m³/h")
    for base in (os.path.join(work, "chapters"), os.path.join(out, "chapters")):
        with open(os.path.join(base, name), "w", encoding="utf-8") as f:
            f.write(text)

parts = os.path.join(work, "result_parts")

def wjson(fname, obj):
    with open(os.path.join(parts, fname), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

def wtext(fname, text):
    with open(os.path.join(parts, fname), "w", encoding="utf-8") as f:
        f.write(text)

wjson("edited_chapters.json", {n: "chapters/" + n for n in chapters})
wtext("change_record.md", """# 变更记录（合成示例）

1. 工单 #1 术语统一：ch01/ch02/ch03 正文中“隔膜”→“隔板”共 8 处；
   引用标题《隔膜槽维护规程》按验收判据保留不变。
2. 工单 #2 单位统一：ch03.md 中“m3/h”→“m³/h”共 2 处。

交付物（均已真实落盘）：
/app/output/chapters/ch01.md、/app/output/chapters/ch02.md、/app/output/chapters/ch03.md。
""")
wtext("consistency_report.md", """# 一致性检查报告（合成示例）

- 术语：编辑后全文仅引用标题《隔膜槽维护规程》含“隔膜”，符合验收判据。
- 单位：ch03.md 中已无“m3/h”，统一为“m³/h”。
- 跨章引用：ch01 提及的维护规程标题与 ch03 无冲突；未发现编号或图表引用。
""")
wtext("uncertainty.md", """# 不确定性（合成示例）

- “隔膜→隔板共 8 处”按整词替换统计，若存在跨行断词未覆盖。
- 章节为合成示例，数值均为虚构，未与任何外部来源核对。
""")
wjson("artifacts.json", ["chapters/ch01.md", "chapters/ch02.md", "chapters/ch03.md"])
wjson("_meta.json", {"case_id": "synthetic-32c0210d-demo", "status": "complete"})
wjson("sources.json", ["input/case.json", "input/organizer-edit-workorder.json",
                       "input/chapters/ch01.md", "input/chapters/ch02.md",
                       "input/chapters/ch03.md"])
print("simulated edits applied; result_parts written:",
      sorted(os.listdir(parts)))
PYEOF

echo "== [3/6] assemble_result: six gates + atomic write =="
python3 "$SCRIPTS/assemble_result.py" \
  --case "$INPUT/case.json" --parts-dir "$WORK/result_parts" \
  --output-dir "$OUT" --output "$OUT/result.json" --note "$NOTE"

echo "== [4/6] render_preview: FORGE_NO_RENDER=1 (deterministic branch) =="
FORGE_NO_RENDER=1 python3 "$SCRIPTS/render_preview.py" \
  --chapters-dir "$OUT/chapters" --out-dir "$OUT/preview" \
  --result "$OUT/result.json" --report "$WORK/render_report.json" \
  --note "$NOTE" --title "M-3 电解槽（合成示例）edited chapters"

echo "== [5/6] verify_delivery: final checks + manifest =="
python3 "$SCRIPTS/verify_delivery.py" \
  --case "$INPUT/case.json" --result "$OUT/result.json" \
  --output-dir "$OUT" --work-dir "$WORK" \
  --manifest "$OUT/manifest.json" --note "$NOTE"

echo "== [6/6] fault injection: delete one result part, re-assemble =="
cp "$WORK/result_parts/consistency_report.md" "$WORK/consistency_report.md.bak"
rm "$WORK/result_parts/consistency_report.md"
set +e
python3 "$SCRIPTS/assemble_result.py" \
  --case "$INPUT/case.json" --parts-dir "$WORK/result_parts" \
  --output-dir "$OUT" --output "$WORK/result-partial.json" --note "$NOTE"
RC=$?
set -e
mv "$WORK/consistency_report.md.bak" "$WORK/result_parts/consistency_report.md"
echo "fault-injection assemble exit code: $RC (expect non-zero)"
if [ "$RC" -eq 0 ]; then
  echo "FAIL: fault injection should have exited non-zero" >&2
  exit 1
fi

# ---- freeze or compare ------------------------------------------------------
if [ "${FORGE_EXAMPLE_FREEZE:-0}" = "1" ]; then
  mkdir -p "$EXPECTED"
  cp "$WORK/checklist.json"        "$EXPECTED/checklist.json"
  cp "$OUT/result.json"            "$EXPECTED/result.json"
  cp "$WORK/render_report.json"    "$EXPECTED/render_report.json"
  cp "$OUT/manifest.json"          "$EXPECTED/manifest.json"
  cp "$WORK/result-partial.json"   "$EXPECTED/assemble-partial-on-missing-part.json"
  echo "FROZEN: expected/ regenerated from this real run"
  exit 0
fi

OK=1
compare() {
  if diff -u "$EXPECTED/$1" "$2" > /dev/null 2>&1; then
    echo "MATCH   $1"
  else
    echo "MISMATCH $1" >&2
    diff -u "$EXPECTED/$1" "$2" | head -40 >&2 || true
    OK=0
  fi
}
compare checklist.json                       "$WORK/checklist.json"
compare result.json                          "$OUT/result.json"
compare render_report.json                   "$WORK/render_report.json"
compare manifest.json                        "$OUT/manifest.json"
compare assemble-partial-on-missing-part.json "$WORK/result-partial.json"

if [ "$OK" -eq 1 ]; then
  echo "EXAMPLE PASS: all products match expected/"
else
  echo "EXAMPLE FAIL: see mismatches above (or re-freeze with FORGE_EXAMPLE_FREEZE=1)" >&2
  exit 1
fi
