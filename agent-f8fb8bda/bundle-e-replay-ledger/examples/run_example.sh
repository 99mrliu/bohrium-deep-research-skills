#!/usr/bin/env bash
# run_example.sh — dr-replay-ledger 合成示例（synthetic，无真实检索）
# 一键演示：journal 记账 6 笔 → 哈希链校验 → stats/replay → 埋雷篡改必被检出
#           → manifest build/verify → 产物被改必被检出 → resume 检查点与续跑自检。
# 每步打印 EXPECTED vs ACTUAL 退出码；产物保留在 examples/output_demo/。
set +e
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
SCRIPTS="$BUNDLE/scripts"
IN="$HERE/input_demo"
DEMO="$HERE/output_demo"
WORK="$DEMO/work"
OUT="$DEMO/output"
JOURNAL="$WORK/run_journal.jsonl"

PASS=0; FAIL=0
run_step() { # $1=期望退出码 $2=描述 其余=命令
  local expect="$1"; local desc="$2"; shift 2
  echo "----- $desc"
  "$@"
  local actual=$?
  if [ "$actual" -eq "$expect" ]; then
    echo "  [EXPECTED $expect / ACTUAL $actual] PASS"
    PASS=$((PASS+1))
  else
    echo "  [EXPECTED $expect / ACTUAL $actual] FAIL"
    FAIL=$((FAIL+1))
  fi
  echo
}

echo "===== 0. 准备合成产物目录（output_demo 重置） ====="
rm -rf "$DEMO"
mkdir -p "$WORK" "$OUT"
# 合成的阶段产物与最终 result.json（synthetic，无真实检索内容）
printf '%s\n' '{"subquestions": ["SQ1 X 的低温相稳定性?", "SQ2 Y 的低温相稳定性?", "SQ3 直接对比证据?"], "_notice": "合成示例 / synthetic"}' > "$WORK/subquestions.json"
printf '%s\n' '# 合成示例综合稿 / synthetic synthesis' '' '结论（虚构）：证据不足，status=partial。' > "$WORK/synthesis.md"
printf '%s\n' 'FAKE-PDF-BYTES synthetic demo payload（合成示例，非真实论文）' > "$WORK/paper_x.pdf"
printf '%s\n' '{"case_id": "synthetic-demo-0001", "status": "partial", "subquestions": [], "coverage": {}, "findings": [], "conflicts": [], "synthesis": "synthetic demo", "research_gaps": ["SQ3 无公开直接对比证据（检索 empty）"], "sources": [], "uncertainty": "合成示例：fetch_pdf 曾限流降级，SQ3 检索为空；详见 run_journal.jsonl", "_notice": "合成示例 / synthetic"}' > "$OUT/result.json"
PDF_DIGEST=$(shasum -a 256 "$WORK/paper_x.pdf" | cut -d' ' -f1)
RESULT_DIGEST=$(shasum -a 256 "$OUT/result.json" | cut -d' ' -f1)
EMPTY_DIGEST=$(printf '' | shasum -a 256 | cut -d' ' -f1)
SEARCH_DIGEST=$(printf 'synthetic search hits: 5 titles about material X low-T' | shasum -a 256 | cut -d' ' -f1)
TEXT_DIGEST=$(printf 'synthetic extracted text of paper_x' | shasum -a 256 | cut -d' ' -f1)
echo

echo "===== 1. journal：init + append 6 笔 ====="
run_step 0 "journal init（genesis）" \
  python3 "$SCRIPTS/journal.py" init --journal "$JOURNAL"
run_step 0 "append #1 web_search ok" \
  python3 "$SCRIPTS/journal.py" append --journal "$JOURNAL" \
    --tool web_search --args-json '{"query": "material X low temperature stability", "numResults": 8}' \
    --results-count 5 --results-digest "$SEARCH_DIGEST" \
    --status ok --note "合成示例：覆盖 SQ1"
run_step 0 "append #2 web_search empty（检索为空，非 failed）" \
  python3 "$SCRIPTS/journal.py" append --journal "$JOURNAL" \
    --tool web_search --args-json '{"query": "material X vs material Y direct comparison", "numResults": 8}' \
    --results-count 0 --results-digest "$EMPTY_DIGEST" \
    --status empty --note "合成示例：SQ3 无直接对比证据，转入 research_gaps"
run_step 0 "append #3 fetch_pdf failed（限流）" \
  python3 "$SCRIPTS/journal.py" append --journal "$JOURNAL" \
    --tool fetch_pdf --args-json '{"url": "https://example.invalid/paper_x.pdf"}' \
    --results-count 0 --results-digest "$EMPTY_DIGEST" \
    --status failed --note "合成示例：HTTP 429 限流；降级决策：退避 5s 后重试"
run_step 0 "append #4 fetch_pdf retry（退避后重试成功，原 failed 笔保留）" \
  python3 "$SCRIPTS/journal.py" append --journal "$JOURNAL" \
    --tool fetch_pdf --args-json '{"url": "https://example.invalid/paper_x.pdf", "retry_after_s": 5}' \
    --results-count 1 --results-digest "$PDF_DIGEST" \
    --status retry --note "合成示例：对 seq=3 同一 URL 的重试，本次成功取得 PDF"
run_step 0 "append #5 pdftotext ok" \
  python3 "$SCRIPTS/journal.py" append --journal "$JOURNAL" \
    --tool pdftotext --args-json '{"path": "work/paper_x.pdf"}' \
    --results-count 1 --results-digest "$TEXT_DIGEST" \
    --status ok --note "合成示例：正文提取成功"
run_step 0 "append #6 finalize ok" \
  python3 "$SCRIPTS/journal.py" append --journal "$JOURNAL" \
    --tool finalize --args-json '{"out": "output/result.json"}' \
    --results-count 1 --results-digest "$RESULT_DIGEST" \
    --status ok --note "合成示例：status=partial，限度已写入 uncertainty"
echo

echo "===== 2. 账本终检：verify / stats / replay ====="
run_step 0 "journal verify（哈希链完整）" \
  python3 "$SCRIPTS/journal.py" verify --journal "$JOURNAL"
run_step 0 "journal stats（empty 与 failed 分开计数）" \
  python3 "$SCRIPTS/journal.py" stats --journal "$JOURNAL"
python3 "$SCRIPTS/journal.py" replay --journal "$JOURNAL" > "$OUT/replay_plan.json"
echo "----- replay 清单已写入 $OUT/replay_plan.json（退出码 $?）"
echo

echo "===== 3. 埋雷变例 A：篡改 journal 某行 results_count，verify 必须 exit 1 ====="
cp "$JOURNAL" "$DEMO/tampered_journal.jsonl"
python3 - "$DEMO/tampered_journal.jsonl" <<'EOF'
import json, sys
path = sys.argv[1]
lines = open(path, encoding="utf-8").read().splitlines()
e = json.loads(lines[2])          # seq=1 的 web_search ok 笔
e["results_count"] = 99           # 篡改返回计数
lines[2] = json.dumps(e, ensure_ascii=False)
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("已篡改 seq=1 的 results_count: 5 -> 99")
EOF
run_step 1 "journal verify（被改账本，须 exit 1 并指出断链 seq）" \
  python3 "$SCRIPTS/journal.py" verify --journal "$DEMO/tampered_journal.jsonl"

echo "===== 4. manifest：build → verify → 改动产物 → verify 必须 exit 1 ====="
# 注：演示中 --skill-dir 取 scripts/。真实评测用 /skills/weekly-skill；
# 此处若用 bundle 根，examples/output_demo 位于清单根内会把产物重复登记为 skill 文件。
run_step 0 "manifest build（输入=input_demo，产物=output，skill=scripts/）" \
  python3 "$SCRIPTS/manifest.py" build --input-dir "$IN" --out "$OUT" --skill-dir "$SCRIPTS" --checkpoints "$WORK/checkpoints/stages.json"
run_step 0 "manifest verify（一致）" \
  python3 "$SCRIPTS/manifest.py" verify --manifest "$OUT/run_manifest.json"
cp "$OUT/result.json" "$DEMO/result.json.bak"
printf '%s\n' '{"case_id": "synthetic-demo-0001", "status": "complete", "_tampered": true}' > "$OUT/result.json"
run_step 1 "manifest verify（result.json 被改，须 exit 1 并点名文件）" \
  python3 "$SCRIPTS/manifest.py" verify --manifest "$OUT/run_manifest.json"
cp "$DEMO/result.json.bak" "$OUT/result.json"   # 还原，保持 output_demo 终态自洽
run_step 0 "manifest verify（还原后再次通过）" \
  python3 "$SCRIPTS/manifest.py" verify --manifest "$OUT/run_manifest.json"

echo "===== 5. resume：mark-done / status / verify-resume，改产物必须 exit 1 ====="
run_step 0 "resume mark-done decompose" \
  python3 "$SCRIPTS/resume.py" mark-done --stage decompose --out "$WORK" --file subquestions.json
run_step 0 "resume mark-done synthesis（声明两个产物文件）" \
  python3 "$SCRIPTS/resume.py" mark-done --stage synthesis --out "$WORK" --file synthesis.md --file paper_x.pdf
run_step 0 "resume status" \
  python3 "$SCRIPTS/resume.py" status --out "$WORK"
run_step 0 "resume verify-resume（一致，可续跑）" \
  python3 "$SCRIPTS/resume.py" verify-resume --out "$WORK"
printf '%s\n' 'tampered synthesis（合成示例：演示产物被改）' > "$WORK/synthesis.md"
run_step 1 "resume verify-resume（synthesis.md 被改，须 exit 1 并点名阶段）" \
  python3 "$SCRIPTS/resume.py" verify-resume --out "$WORK"
printf '%s\n' '# 合成示例综合稿 / synthetic synthesis' '' '结论（虚构）：证据不足，status=partial。' > "$WORK/synthesis.md"
run_step 0 "resume verify-resume（还原后通过）" \
  python3 "$SCRIPTS/resume.py" verify-resume --out "$WORK"

echo "===== 汇总 ====="
cp "$JOURNAL" "$OUT/run_journal.jsonl"
echo "PASS=$PASS FAIL=$FAIL"
echo "产物保留于：$DEMO"
[ "$FAIL" -eq 0 ]
