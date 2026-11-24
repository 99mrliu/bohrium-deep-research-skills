#!/usr/bin/env bash
# 合成示例端到端演示（非正式案例结果）：
#   init -> 台账 -> 两次模拟 checkpoint（含一次预算 82% 预警）
#   -> 对故意缺 risk_register 字段、缺风险要素的 result.json 跑 contract_guard
#   -> 缺项拦截与 partial 强制
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
WORK="$HERE/work"
OUT="$HERE/expected"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

RESULT="$OUT/result.json"
LOG="$OUT/checkpoint_log.jsonl"
LEDGER="$OUT/budget_ledger.jsonl"
GUARD="$OUT/guard_report.json"
rm -f "$RESULT" "$LOG" "$LEDGER" "$GUARD"

echo "=== 步骤0（T+30s 内）：契约读取 + checkpoint init ==="
python3 "$SKILL/scripts/checkpoint.py" init "$HERE/input/case.json" "$RESULT" \
  --log "$LOG" --requests-used 2

echo "=== 台账：材料通读 ==="
python3 "$SKILL/scripts/budget_ledger.py" add "$LEDGER" \
  --purpose "材料通读：literature_notes + lab_conditions（合成材料）" \
  --tokens 5200 --requests-left 54 --phase reading

echo "=== 起草：写合成草稿（故意缺『风险与备选』章节）与来源清单 ==="
cat > "$WORK/draft.md" <<'MD'
# 固态锂电池界面工程开题报告（合成示例草稿）

## 一、研究背景与缺口
固态锂电池以固态电解质取代易燃电解液，是高比能电池的重要方向。合成来源 [S1] 指出，
LLZO 与锂金属界面阻抗可达数百 Ω·cm²，润湿性差与孔洞是主因；[S3] 指出枝晶沿晶界穿透
导致短路，临界电流密度普遍低于 1 mA/cm²。现有研究的缺口在于：缓冲层减阻与枝晶抑制
往往分开研究，缺乏在同一界面上协同优化阻抗-稳定性的系统方案。

## 二、问题定义与研究目标
问题定义：如何在不牺牲临界电流密度的前提下，将 LLZO/锂界面阻抗稳定降至 10 Ω·cm² 量级。
研究目标：(1) 确定缓冲层成分-厚度窗口，界面阻抗 ≤ 10 Ω·cm²（量级依据 [S2]）；
(2) 对称电池 0.5 mA/cm² 下稳定循环 ≥ 500 小时；(3) 标定堆叠压力窗口（依据 [S4] 的 2–5 MPa）。

## 三、技术路线与阶段计划
技术路线：磁控溅射制备 Al/ZnO 缓冲层 → 阻抗谱与对称电池筛选 → 压力-电流协同优化 → 全电池验证。
阶段计划：第 1–6 月工艺摸索；第 7–12 月窗口优化并参加中期考核；第 13–18 月机理表征；
第 19–24 月全电池验证与论文撰写。

## 四、预期成果
预期成果：界面工程工艺包 1 套；学术论文 2 篇；发明专利申请 1 项；中期与结题数据集各 1 份。

## 五、引用证据
引用证据均来自合成来源 [S1]–[S5]，论断与来源编号在 fact_source_map 中一一对应。

## 六、可编辑交付
可编辑交付物：本报告 Markdown 源文件、fact_source_map 与 schedule 的 JSON 结构化版本。
MD
cat > "$WORK/sources.json" <<'JSON'
[
  {"source_id": "S1", "loc": "input/materials/literature_notes.md", "note": "界面阻抗量级与成因"},
  {"source_id": "S2", "loc": "input/materials/literature_notes.md", "note": "缓冲层降阻量级"},
  {"source_id": "S3", "loc": "input/materials/literature_notes.md", "note": "枝晶穿透与临界电流密度"},
  {"source_id": "S4", "loc": "input/materials/literature_notes.md", "note": "堆叠压力窗口"},
  {"source_id": "S5", "loc": "input/materials/literature_notes.md", "note": "硫化物电解质操作约束"}
]
JSON

echo "=== 检查点1：要素起草完成（risk_register 故意留空）==="
python3 "$SKILL/scripts/checkpoint.py" save "$RESULT" --log "$LOG" \
  --set-file proposal_draft="$WORK/draft.md" \
  --sources-file "$WORK/sources.json" \
  --set 'fact_source_map=[{"claim":"LLZO/锂界面阻抗可达数百 Ω·cm²","source_id":"S1"},{"claim":"缓冲层可将界面阻抗降至 10 Ω·cm² 量级","source_id":"S2"},{"claim":"临界电流密度普遍低于 1 mA/cm²","source_id":"S3"}]' \
  --set 'schedule=[{"phase":"工艺摸索","months":"1-6","milestone":"缓冲层成膜工艺稳定"},{"phase":"窗口优化","months":"7-12","milestone":"界面阻抗 ≤10 Ω·cm²，中期考核"},{"phase":"机理表征","months":"13-18","milestone":"失效机理报告"},{"phase":"全电池验证","months":"19-24","milestone":"全电池数据与论文初稿"}]' \
  --set 'expected_outcomes=[{"deliverable":"学术论文","metric":"2 篇"},{"deliverable":"发明专利","metric":"申请 1 项"}]' \
  --note "七要素中六要素成稿；风险与备选章节因预算紧张暂缓" \
  --requests-used 26 --tokens-used 30500 --completion 70 --level L2

echo "=== 台账：修订消耗累计达 82%（预期触发超限预警，退出码 2）==="
set +e
python3 "$SKILL/scripts/budget_ledger.py" add "$LEDGER" \
  --purpose "校验修订：引文抽验与指标核对（多轮）" \
  --tokens 15700 --requests-left 11 --phase revision
ADD_EXIT=$?
set -e
echo "ledger add exit=$ADD_EXIT（预期 2，预警已输出）"

echo "=== 检查点2：预算预警触发强制收尾 ==="
python3 "$SKILL/scripts/checkpoint.py" save "$RESULT" --log "$LOG" \
  --note "用量 82% 触发强制收尾：冻结改进；risk_register 未及填写，诚实保留空值" \
  --requests-used 53 --tokens-used 46200 --completion 75 --level L2

echo "=== 终检 contract_guard（预期 fail：缺 risk_register 字段 + 缺风险要素）==="
set +e
python3 "$SKILL/scripts/contract_guard.py" "$HERE/input/case.json" "$RESULT" "$GUARD"
GUARD_EXIT=$?
set -e
echo "contract_guard exit=$GUARD_EXIT（预期 1：拦截并强制 partial）"

echo "=== 台账汇总（预期再次输出强制收尾指令，退出码 2）==="
set +e
python3 "$SKILL/scripts/budget_ledger.py" report "$LEDGER"
REPORT_EXIT=$?
set -e
echo "ledger report exit=$REPORT_EXIT"

echo "=== 最终有效交付状态 ==="
python3 "$SKILL/scripts/checkpoint.py" status "$RESULT" --log "$LOG"

echo "示例运行完成：产物见 $OUT（result.json 为诚实 partial）"
