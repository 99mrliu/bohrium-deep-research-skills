#!/usr/bin/env bash
# run_example.sh — 一键跑通合成示例迷你流水线（正例，预期全程 exit 0）。
# 步骤：三步流水线 → runlog 登记 → reconcile 轧账 → runlog verify → replay 自证。
# 负例（篡改/轧不平/漂移）由 scripts/selfcheck 独立断言，本脚本不覆盖。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
RUN="$HERE/run"

echo "== 0. 清理并重建运行目录: $RUN"
rm -rf "$RUN"
mkdir -p "$RUN/replay"
cd "$RUN"
LOG="runlog.jsonl"

echo "== 1. ingest：登记原始题录"
python3 "$SKILL/scripts/runlog.py" --log "$LOG" record \
  --step ingest --actor agent \
  --inputs ../input/records.json --outputs ../input/records.json \
  --note "合成示例：题录摄入，原样登记"

echo "== 2. step1 去重"
python3 "$HERE/pipeline/step1_dedupe.py" \
  --input ../input/records.json --output deduped.json
python3 "$SKILL/scripts/runlog.py" --log "$LOG" record \
  --step dedupe --actor agent \
  --inputs ../input/records.json --outputs deduped.json

echo "== 3. step2 题录级筛选"
python3 "$HERE/pipeline/step2_screen_count.py" \
  --input deduped.json --output screening.json --decisions decisions.jsonl
python3 "$SKILL/scripts/runlog.py" --log "$LOG" record \
  --step screen_ta --actor agent \
  --inputs deduped.json --outputs screening.json decisions.jsonl

echo "== 4. step3 全文级筛选 + 冻结纳入清单 + 生成 flow.json"
python3 "$HERE/pipeline/step3_freeze.py" \
  --records ../input/records.json --deduped deduped.json --decisions decisions.jsonl \
  --output-decisions decisions.jsonl --output-included included.json --output-flow flow.json
python3 "$SKILL/scripts/runlog.py" --log "$LOG" record \
  --step screen_ft --actor agent \
  --inputs decisions.jsonl --outputs decisions.jsonl included.json flow.json \
  --note "decisions.jsonl 被重写，verify 以本次登记为准"

echo "== 5. 计数轧账（含 decisions 对账）"
python3 "$SKILL/scripts/reconcile.py" --flow flow.json --decisions decisions.jsonl

echo "== 6. 与静态合规 flow.json 交叉轧账"
python3 "$SKILL/scripts/reconcile.py" --flow "$HERE/flow.json"

echo "== 7. runlog 完整性校验"
python3 "$SKILL/scripts/runlog.py" --log "$LOG" verify
python3 "$SKILL/scripts/runlog.py" --log "$LOG" status

echo "== 8. 生成 manifest 并确定性重放"
cat > manifest.json <<'EOF'
{
  "steps": [
    {"step_id": "dedupe",
     "cmd": "python3 ../../pipeline/step1_dedupe.py --input ../../input/records.json --output deduped.json",
     "outputs": ["deduped.json"]},
    {"step_id": "screen_ta",
     "cmd": "python3 ../../pipeline/step2_screen_count.py --input deduped.json --output screening.json --decisions decisions.jsonl",
     "outputs": ["screening.json", "decisions.jsonl"]},
    {"step_id": "screen_ft",
     "cmd": "python3 ../../pipeline/step3_freeze.py --records ../../input/records.json --deduped deduped.json --decisions decisions.jsonl --output-decisions decisions.jsonl --output-included included.json --output-flow flow.json",
     "outputs": ["decisions.jsonl", "included.json", "flow.json"]}
  ]
}
EOF
python3 "$SKILL/scripts/replay.py" --manifest manifest.json --workdir "$RUN/replay" --runlog "$LOG"

echo "== 完成：合成示例全流程通过（预期各步 exit 0，replay 输出 3 identical, 0 differ）"
