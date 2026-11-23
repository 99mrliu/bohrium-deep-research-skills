#!/usr/bin/env bash
# ============================================================================
# run_example.sh — 合成示例端到端演示（SYNTHETIC EXAMPLE，非正式案例结果）
#
# 演示流水线：paper.txt → extract_pages.py → pages.jsonl
#             手工构造 sample_result.json（quote 摘自 paper.txt 原文）
#             → quote_audit.py → fidelity-report.json（预期 exit 0）
#             → num_drift.py → num-drift.json（预期 exit 1，因 C2/C4 设计为漂移场景）
#             附保真门演示：捏造 quote 的坏结果应被 quote_audit.py 拦截（exit 1）
#
# 用法：bash examples/run_example.sh    （在 skill 根目录或任意目录运行均可）
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$HERE/.." && pwd)"
OUT="$HERE/out"
mkdir -p "$OUT"
cd "$OUT"

PY=python3
EXTRACT="$SKILL_ROOT/scripts/extract_pages.py"
AUDIT="$SKILL_ROOT/scripts/quote_audit.py"
NUMDRIFT="$SKILL_ROOT/scripts/num_drift.py"

echo "== 步骤 1：抽取分页文本 =="
$PY "$EXTRACT" --input "$HERE/paper.txt" --output pages.jsonl || {
  echo "extract_pages 失败"; exit 1; }

echo
echo "== 步骤 2：手工构造 sample result.json（quote 摘自 paper.txt 原文；"
echo "           C2 的 quote 用直引号替代原文弯引号，演示归一化）=="
cat > sample_result.json <<'JSON'
{
  "case_id": "SYNTH-EXAMPLE-001",
  "claims": [
    {"claim_id": "C1", "claim_text": "NFO-700 在 280 °C、2.0 MPa 条件下 CO2 转化率达到 78%。"},
    {"claim_id": "C2", "claim_text": "在 350 °C 下 NFO-700 的 CO2 转化率超过 90%。"},
    {"claim_id": "C3", "claim_text": "NFO-700 在含 SO2 的工业烟气中可保持稳定活性。"},
    {"claim_id": "C4", "claim_text": "NFO-700 将 CO2 转化率从 62% 提升至 78.2%，提高了 16 个百分点。"}
  ],
  "verdicts": [
    {"claim_id": "C1", "verdict": "supported",
     "rationale": "原文第 2 页明确报告 280 °C、2.0 MPa 下转化率达 78%。"},
    {"claim_id": "C2", "verdict": "contradicted",
     "rationale": "原文第 3 页报告 350 °C 时转化率下降至 54%，与'超过 90%'直接冲突。"},
    {"claim_id": "C3", "verdict": "insufficient_evidence",
     "rationale": "原文第 3 页明确写'未考察含硫气氛'，属未报告，不能判反驳。"},
    {"claim_id": "C4", "verdict": "partially_supported",
     "rationale": "'62%→78%、提高 16 个百分点'有原文支持，但论断写成 78.2% 系数值漂移。"}
  ],
  "evidence": [
    {"claim_id": "C1", "page": 2, "section": "3.1 催化活性",
     "quote": "在 280 °C、2.0 MPa 条件下，NFO-700 的 CO2 转化率达到 78%，"},
    {"claim_id": "C2", "page": 3, "section": "3.2 热稳定性",
     "quote": "当温度升至 350 °C 时，因\"活性相烧结\"，转化率下降至 54%。"},
    {"claim_id": "C3", "page": 3, "section": "3.3 限制",
     "quote": "未考察含硫气氛（如 SO2）对催化剂结构与活性的影响。"},
    {"claim_id": "C4", "page": 2, "section": "3.1 催化活性",
     "quote": "NFO-700 的 CO2 转化率达到 78%，较商业 Ni/Al2O3 基准（62%）提高 16 个百分点"}
  ],
  "sources": [
    {"type": "paper", "file": "paper.txt", "note": "合成示例论文（虚构）", "pages_used": [2, 3]}
  ],
  "uncertainty": [
    "全部材料为合成示例，不构成真实科研结论。",
    "C4 的 78.2% 在原文中不存在（原文为 78%），已由 num_drift.py 标记。"
  ],
  "status": "success",
  "change_records": [
    {"step": 1, "action": "写入骨架 result.json（status=partial 占位）"},
    {"step": 2, "action": "填充四条论断的判定与证据 quote"},
    {"step": 3, "action": "quote_audit.py 保真门通过后将 status 覆写为 success"}
  ]
}
JSON

echo
echo "== 步骤 3：保真门 quote_audit.py（预期 exit 0）=="
if $PY "$AUDIT" --result sample_result.json --pages pages.jsonl \
    --output fidelity-report.json; then
  echo ">> 保真门通过（exit 0）"
else
  rc=$?
  echo ">> 保真门未通过（exit $rc），示例异常，请检查"; exit 1
fi

echo
echo "== 步骤 4：数值漂移 num_drift.py（C2/C4 为设计的漂移场景，预期 exit 1）=="
$PY "$NUMDRIFT" --claims "$HERE/claims.json" --result sample_result.json \
    --output num-drift.json
rc=$?
echo ">> num_drift 退出码 = $rc（1 = 检出漂移，属预期）"

echo
echo "== 步骤 5：保真门拦截演示 —— 捏造 quote 应被判 not_found（预期 exit 1）=="
cat > sample_result_bad.json <<'JSON'
{
  "case_id": "SYNTH-EXAMPLE-001",
  "evidence": [
    {"claim_id": "C9", "page": 2,
     "quote": "NFO-700 的 CO2 转化率高达 99%，创下该领域历史新高。"}
  ]
}
JSON
$PY "$AUDIT" --result sample_result_bad.json --pages pages.jsonl \
    --output fidelity-report-bad.json
rc=$?
if [ "$rc" -eq 1 ]; then
  echo ">> 拦截成功：捏造 quote 被判 not_found，quote_audit exit 1（符合预期）"
else
  echo ">> 异常：捏造 quote 未被拦截（exit $rc）"; exit 1
fi

echo
echo "== 全部演示完成。产物：$OUT =="
ls -1 pages.jsonl fidelity-report.json num-drift.json sample_result.json fidelity-report-bad.json
exit 0
