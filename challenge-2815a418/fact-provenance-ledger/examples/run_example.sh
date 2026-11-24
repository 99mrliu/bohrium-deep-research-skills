#!/usr/bin/env bash
# run_example.sh — fact-provenance-ledger 端到端 quick path。
#
# 默认模式（合成示例，非正式案例结果）：
#   bash examples/run_example.sh
#     输入 examples/case/，中间产物 examples/work/，产物 examples/output/
#
# Harness 模式（评测运行时）：
#   SKILL=/skills/weekly-skill bash "$SKILL/examples/run_example.sh" --harness
#     输入 /input，工作目录 /app/work，产物 /app/output
#
# 仅依赖 Python 3 标准库；任一脚本失败不阻断，状态降级为 partial 并记录。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ "${1:-}" = "--harness" ]; then
  CASE_DIR=/input
  WORK=/app/work
  OUT=/app/output
else
  CASE_DIR="$SCRIPT_DIR/case"
  WORK="$SCRIPT_DIR/work"
  OUT="$SCRIPT_DIR/output"
fi
mkdir -p "$WORK" "$OUT"

BASELINE="$CASE_DIR/materials/manuscript-baseline.md"
DECISIONS="$WORK/decisions.json"
EDITS="$WORK/edits.json"
WHITELIST="$WORK/whitelist.txt"
[ -f "$DECISIONS" ] || DECISIONS="$SCRIPT_DIR/decisions.json"
[ -f "$EDITS" ] || EDITS="$SCRIPT_DIR/edits.json"
[ -f "$WHITELIST" ] || WHITELIST="$SCRIPT_DIR/whitelist.txt"
WL_ARG=""
[ -f "$WHITELIST" ] && WL_ARG="--whitelist $WHITELIST"

STATUS=partial
note() { NOTES+=("$1"); }
NOTES=()

echo "== [1/6] boot: 立即落一个合法的部分 result.json =="
python3 "$SKILL_DIR/scripts/make_result.py" \
  --case "$CASE_DIR/case.json" \
  --materials-dir "$CASE_DIR/materials" \
  --out "$OUT/result.json" \
  --status partial \
  --note "boot: partial result placeholder（机械阶段未完成，后续更新）" \
  || { echo "FATAL: make_result boot failed"; exit 2; }

echo "== [2/6] 编译事实台账 facts.jsonl =="
python3 "$SKILL_DIR/scripts/fact_ledger.py" \
  --materials "$CASE_DIR/materials" \
  --out "$WORK/facts.jsonl" \
  || note "fact_ledger 失败，落地守卫不可用"

echo "== [3/6] 锚点落稿 =="
if [ -f "$BASELINE" ]; then
  python3 "$SKILL_DIR/scripts/apply_edits.py" \
    --baseline "$BASELINE" \
    --edits "$EDITS" \
    --out "$OUT/revised-manuscript.md" \
    --changes "$OUT/change-locations.json" \
    --report "$WORK/apply_report.json" \
    || note "apply_edits 失败"
else
  note "基线缺失: $BASELINE"
  STATUS=unable_to_determine
fi

echo "== [4/6] 由 decisions.json 机械生成回复信草案与未到位证据清单 =="
python3 - "$DECISIONS" "$CASE_DIR/materials/reviewer-comments.md" \
              "$OUT/response-letter.md" "$OUT/evidence-checklist.json" <<'PYEOF' || note "回复信生成失败"
import json, re, sys
dec_path, rc_path, letter_path, checklist_path = sys.argv[1:5]
with open(dec_path, encoding="utf-8") as f:
    decisions = json.load(f)["decisions"]
with open(rc_path, encoding="utf-8") as f:
    rc = f.read()
lines_raw = [l.strip() for l in rc.splitlines() if l.strip()]

def quote_of(sub):
    for l in lines_raw:
        body = re.sub(r"^[-*]\s*", "", l)
        if body.startswith(sub + "：") or body.startswith(sub + ":"):
            return body.split("：", 1)[-1].split(":", 1)[-1].strip()
    return None

lines = ["# 审稿回复信（草案，意见按 reviewer-comments.md 摘要转述，非逐字审稿原文）",
         "", "尊敬的编辑与审稿人：", "",
         "感谢审阅。以下逐条回应（转述自意见摘要）。本回复不冒称逐字审稿要求，",
         "所有事实性表述均可回溯至事实台账 facts.jsonl。", ""]
checklist = []
for d in decisions:
    sub = d["sub_request"]
    q = quote_of(sub)
    lines.append("## %s" % sub)
    if q:
        lines.append("审稿意见（摘要转述）：「%s」" % q)
    else:
        lines.append("审稿意见（摘要转述）：%s" % d.get("summary", ""))
    st = d.get("evidence_status")
    if d.get("action") == "edit":
        lines.append("处置：已按决策修改基线（见修订稿 CHG 标记与 change-locations.json）。")
    elif st == "infeasible":
        lines.append("处置：该意见要求补做真实实验，本环境无法执行，绝不伪造数据。"
                     "建议后续由原作者补测后更新；此项列入未到位证据清单。")
    else:
        lines.append("处置：仅回复，未改稿。")
    lines.append("理由：%s" % d.get("reason", ""))
    lines.append("")
    if st in ("absent", "infeasible"):
        checklist.append({"sub_request": sub, "evidence_status": st,
                          "summary": d.get("summary", ""),
                          "reason": d.get("reason", "")})
lines += ["## 界限声明", "",
          "- 意见按摘要转述，非逐字审稿原文；",
          "- 未补做任何真实实验；",
          "- 本修订为基线摘要上的草案，不代表原作者已改稿或编辑部已接收。"]
with open(letter_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
with open(checklist_path, "w", encoding="utf-8") as f:
    json.dump({"evidence_checklist": checklist,
               "note": "absent=材料中找不到；infeasible=本环境无法补做"},
              f, ensure_ascii=False, indent=2)
print("letter & checklist generated: %d checklist items" % len(checklist))
PYEOF

echo "== [5/6] 落地守卫 =="
GUARD_RC=0
if [ -f "$WORK/facts.jsonl" ]; then
  # shellcheck disable=SC2086
  python3 "$SKILL_DIR/scripts/ground_guard.py" \
    --facts "$WORK/facts.jsonl" \
    --draft "$OUT/revised-manuscript.md" \
    --draft "$OUT/response-letter.md" \
    --out "$OUT/ground_report.json" $WL_ARG || GUARD_RC=$?
  [ "$GUARD_RC" != "0" ] && note "ground_guard 非零退出: $GUARD_RC"
fi

echo "== [6/6] 定稿 result.json =="
HAS_INFEASIBLE=$(python3 -c "
import json,sys
try:
    d=json.load(open('$OUT/evidence-checklist.json',encoding='utf-8'))
    print('yes' if any(i.get('evidence_status')=='infeasible' for i in d.get('evidence_checklist',[])) else 'no')
except Exception:
    print('no')" 2>/dev/null || echo no)
[ "$HAS_INFEASIBLE" = "yes" ] && STATUS=partial
PENDING=$(python3 -c "
import json
try:
    print(json.load(open('$WORK/apply_report.json',encoding='utf-8')).get('pending_review',0))
except Exception:
    print(0)" 2>/dev/null || echo 0)
[ "$PENDING" != "0" ] && STATUS=partial

MAKE_ARGS=(
  --case "$CASE_DIR/case.json"
  --out "$OUT/result.json"
  --status "$STATUS"
  --source "$WORK/facts.jsonl"
  --source "$OUT/ground_report.json"
  --change-record "$OUT/change-locations.json"
)
for n in "${NOTES[@]:-}"; do [ -n "$n" ] && MAKE_ARGS+=(--note "$n"); done
# output_contract 全字段映射（字段名以 case.json 为准）
while IFS= read -r field; do
  case "$field" in
    revised_manuscript) MAKE_ARGS+=(--artifact "revised_manuscript=$OUT/revised-manuscript.md");;
    response_letter)    MAKE_ARGS+=(--artifact "response_letter=$OUT/response-letter.md");;
    change_locations)   MAKE_ARGS+=(--artifact "change_locations=$OUT/change-locations.json");;
    evidence_checklist) MAKE_ARGS+=(--artifact "evidence_checklist=$OUT/evidence-checklist.json");;
  esac
done < <(python3 -c "
import json
print('\n'.join((json.load(open('$CASE_DIR/case.json',encoding='utf-8')).get('output_contract') or {}).keys()))")
[ "$HAS_INFEASIBLE" = "yes" ] && MAKE_ARGS+=(--uncertainty "存在 infeasible 子要求（需真实补实验），本环境无法完成")
[ "$PENDING" != "0" ] && MAKE_ARGS+=(--uncertainty "$PENDING 条编辑锚点未命中/不唯一，进 pending_review")
[ "$GUARD_RC" != "0" ] && MAKE_ARGS+=(--uncertainty "ground_guard 发现材料外事实，见 ground_report.json")

python3 "$SKILL_DIR/scripts/make_result.py" "${MAKE_ARGS[@]}" || { echo "FATAL: make_result final failed"; exit 2; }

echo "DONE. status=$STATUS 产物目录: $OUT"
