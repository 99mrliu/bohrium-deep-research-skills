#!/usr/bin/env bash
# 合成示例（非正式测评）：演示 contract_deliver.py 全流程
#   scaffold -> fill 三轮 -> 故意留 confirmation_items 为 draft 跑 validate（FAIL 自动降级 partial）
#   -> 补全 final -> validate PASS -> render（本机无 pandoc/libreoffice，演示 PDF 降级诚实记录）
# 用法：bash examples/run_example.sh   （输出写入 examples/output/）
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_PY="$HERE/../scripts/contract_deliver.py"
CASE="$HERE/mock_case.json"
OUT="$HERE/output"
WORK="$HERE/work"
rm -rf "$OUT" "$WORK"
mkdir -p "$OUT" "$WORK"

echo "=== 1. scaffold：立即获得合法 partial（保底） ==="
python3 "$SKILL_PY" --case "$CASE" --out "$OUT" scaffold

echo "=== 2. 写 plan.json（成本用 case 单价重算：80*24+40*12+250*5+180*5=4550） ==="
cat > "$OUT/plan.json" <<'EOF'
{
  "assumptions_variables": [
    "假设：MAPbI3 结晶质量对退火温度敏感区间在 100-120°C（source.key_claim，合成示例论断）",
    "自变量：anneal_temperature_C（域内 100/110/120）；因变量：薄膜覆盖率、PL 强度",
    "控制变量：spin_coating_rpm=4000、anneal_time_min=10 固定"
  ],
  "controls": [
    "未退火对照（同批旋涂后直接表征）",
    "candidate v1 的 125°C 单点作为域内参照"
  ],
  "equipment_materials": [
    {"id": "EQ-GB", "name": "充氮手套箱", "source": "resource_contract.equipment[0]"},
    {"id": "EQ-HP", "name": "精密加热台", "source": "equipment_domain_note（内嵌，可用性待确认）"},
    {"id": "RE-MAI", "name": "MAI ≥99.99%", "source": "resource_contract.reagents[0]"},
    {"id": "RE-PBI2", "name": "PbI2 ≥99.99%", "source": "resource_contract.reagents[1]"}
  ],
  "schedule": {"est_days": 14, "basis": "6 次实验 × 4h/次；手套箱 3 档/周 → 2 周，window_days=30 内可行"},
  "parameters": {"anneal_temperature_C": [100, 110, 120], "spin_coating_rpm": 4000, "anneal_time_min": 10},
  "cost_items": [
    {"item": "手套箱", "unit_price": 80, "quantity": 24, "subtotal": 1920},
    {"item": "加热台", "unit_price": 40, "quantity": 12, "subtotal": 480},
    {"item": "MAI", "unit_price": 250, "quantity": 5, "subtotal": 1250},
    {"item": "PbI2", "unit_price": 180, "quantity": 5, "subtotal": 900}
  ],
  "total_cost": 4550,
  "risks": [
    "手套箱预约冲突 → 提前 7 天锁档，冲突时顺延并在 change_log 记录",
    "EQ-HP 为内嵌设备、可用性未确认 → 已列入 confirmation_items，确认前不排产",
    "湿气侵入 → 手套箱水氧 <1ppm 监控，超阈中止当次实验"
  ]
}
EOF

echo "=== 3. fill 第一轮：revised_plan / candidate_assessment（final） ==="
cat > "$WORK/revised_plan.json" <<'EOF'
{
  "hypothesis": "退火温度在 100-120°C 域内存在结晶质量峰值（source.key_claim，合成示例论断）",
  "variables": {"independent": ["anneal_temperature_C"], "dependent": ["薄膜覆盖率", "PL 强度"], "controlled": ["spin_coating_rpm=4000", "anneal_time_min=10"]},
  "controls": ["未退火对照", "125°C 单点参照（candidate v1）"],
  "equipment_materials": ["EQ-GB 充氮手套箱", "EQ-HP 精密加热台（内嵌设备，待确认）", "MAI/PbI2 各 1 包（5g）"],
  "schedule": {"est_days": 14, "basis": "6 次×4h，3 档/周，window_days=30 内"},
  "parameters": {"anneal_temperature_C": [100, 110, 120], "spin_coating_rpm": 4000, "anneal_time_min": 10},
  "cost": {"total_cost": 4550, "basis": "plan.json cost_items 重算，预算 cap 20000 内"},
  "risks": ["预约冲突顺延", "EQ-HP 可用性待确认", "湿气侵入中止阈值"]
}
EOF
cat > "$WORK/candidate_assessment.json" <<'EOF'
[
  {"version": "v1", "verdict": "部分采纳",
   "findings": ["成本算术错误：subtotal 之和 3200+1250+900=5350 != total_cost 7330（candidate_plans[0]）",
                "参数全部在域内；est_days=28 ≤ deadline 30，吞吐可行（10 档 × 4h = 40h 对 40h 用量）"]},
  {"version": "v2", "verdict": "否决",
   "findings": ["est_days=45 超 deadline_days=30；16 组合需 64h=16 档，3 档/周需约 6 周，超 window_days=30 的预约吞吐（candidate_plans[1]）",
                "成本算术正确（5120+2500+1800=9420）"]},
  {"version": "v3", "verdict": "否决",
   "findings": ["anneal_temperature_C=165 越出 parameter_domains 上限 150（candidate_plans[2]）",
                "依赖内嵌设备 EQ-HP，可用性未确认"]}
]
EOF
python3 "$SKILL_PY" --out "$OUT" fill --field revised_plan --file "$WORK/revised_plan.json" --finalize-field
python3 "$SKILL_PY" --out "$OUT" fill --field candidate_assessment --file "$WORK/candidate_assessment.json" --finalize-field

echo "=== 4. fill 第二轮：validation / sources / uncertainty（final） ==="
cat > "$WORK/validation.json" <<'EOF'
[
  {"check": "成本算术", "method": "sum(unit_price*quantity) 复算", "data": "80*24+40*12+250*5+180*5=4550", "conclusion": "plan.json total_cost=4550 一致；candidate v1 的 7330 系算术错误（应为 5350）"},
  {"check": "参数域", "method": "逐项对 parameter_domains", "data": "100/110/120 ∈ [80,150] step5；4000 ∈ enum；10 ∈ [5,60]", "conclusion": "修订方案全部合规"},
  {"check": "时间可行性", "method": "预约吞吐对账", "data": "6 档 × 4h = 24h；3 档/周 → 2 周", "conclusion": "est_days=14 ≤ 30 可行"},
  {"check": "机械复核", "method": "contract_deliver.py validate", "data": "validation_report.json", "conclusion": "以脚本输出为准"}
]
EOF
cat > "$WORK/sources.json" <<'EOF'
[
  {"value": "手套箱 80 CNY/h", "source": "resource_contract.equipment[0].price_per_hour（前瞻合同，非已确认报价）"},
  {"value": "MAI 250 CNY/g、PbI2 180 CNY/g", "source": "resource_contract.reagents（前瞻合同）"},
  {"value": "加热台 40 CNY/h", "source": "equipment_domain_note 内嵌 JSON（可用性待确认）"},
  {"value": "温度域 80-150 step5、转速枚举、时间域 5-60", "source": "parameter_domains"},
  {"value": "100-120°C 敏感区间", "source": "source.key_claim（合成示例论断，未经本方案验证）"},
  {"value": "6 次实验设计", "source": "假设（3 温度 × 2 重复）"}
]
EOF
cat > "$WORK/uncertainty.json" <<'EOF'
[
  "source.key_claim 为合成示例论断，100-120°C 峰值假设未经本方案验证",
  "EQ-HP 加热台为 equipment_domain_note 内嵌设备，可用性与前瞻价格均未确认",
  "est_days=14 按 3 档/周满排估计，实际排期可能顺延"
]
EOF
python3 "$SKILL_PY" --out "$OUT" fill --field validation --file "$WORK/validation.json" --finalize-field
python3 "$SKILL_PY" --out "$OUT" fill --field sources --file "$WORK/sources.json" --finalize-field
python3 "$SKILL_PY" --out "$OUT" fill --field uncertainty --file "$WORK/uncertainty.json" --finalize-field

echo "=== 5. fill 第三轮：change_log（final）+ confirmation_items（故意留 draft） ==="
cat > "$WORK/change_log.json" <<'EOF'
["起草：以 candidate v1 为底，纠正其 total_cost 算术错误（7330→5350 的量级来源），温度收窄至 100-120°C 域内三点"]
EOF
cat > "$WORK/confirmation_items.json" <<'EOF'
[
  "EQ-HP 精密加热台（equipment_domain_note 内嵌设备）是否在合同内可用？确认前不排产",
  "resource_contract 全部价格与预约信息为组织方前瞻约定，需委托方书面确认后方可作为执行依据",
  "MAI/PbI2 各 1 包（5g）是否覆盖 6 次实验用量？不足需追加采购（预算内）"
]
EOF
python3 "$SKILL_PY" --out "$OUT" fill --field change_log --file "$WORK/change_log.json" --finalize-field
python3 "$SKILL_PY" --out "$OUT" fill --field confirmation_items --file "$WORK/confirmation_items.json"
echo "    （confirmation_items 故意不加 --finalize-field，保持 draft）"

echo "=== 6. validate 第 1 次：预期 FAIL，status 自动降级 partial ==="
python3 "$SKILL_PY" --case "$CASE" --out "$OUT" validate
cp "$OUT/validation_report.json" "$OUT/validation_report_fail.json"
echo "    result.status 现在为：$(python3 -c "import json;print(json.load(open('$OUT/result.json'))['status'])")"

echo "=== 7. 补全：confirmation_items 标记 final，validate 第 2 次预期 PASS ==="
python3 "$SKILL_PY" --out "$OUT" fill --field confirmation_items --file "$WORK/confirmation_items.json" --finalize-field
python3 "$SKILL_PY" --case "$CASE" --out "$OUT" validate
cp "$OUT/validation_report.json" "$OUT/validation_report_pass.json"

echo "=== 8. render：plan.md（+ PDF 探测/降级记录） ==="
python3 "$SKILL_PY" --case "$CASE" --out "$OUT" render

echo "=== 9. 给示例输出加注'合成示例输出，非正式测评结果' ==="
python3 - "$OUT" <<'PYEOF'
import json, sys, os
out = sys.argv[1]
note = "合成示例输出，非正式测评结果"
for fn in ("result.json", "validation_report.json", "validation_report_fail.json",
           "validation_report_pass.json", "plan.json"):
    p = os.path.join(out, fn)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        d2 = {"_example_note": note}
        d2.update(d)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d2, f, ensure_ascii=False, indent=2)
            f.write("\n")
for fn in ("plan.md", "plan_skeleton.md"):
    p = os.path.join(out, fn)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            body = f.read()
        with open(p, "w", encoding="utf-8") as f:
            f.write("> %s\n\n%s" % (note, body))
PYEOF

echo "=== 完成。产物： ==="
ls -1 "$OUT"
