#!/usr/bin/env bash
# 合成示例（非正式案例、非预写答案）：契约工程全流程演示。
set -e
cd "$(dirname "$0")"
rm -rf demo
mkdir -p demo/input demo/output demo/work

cat > demo/input/case.json <<'EOF'
{"case_id": "synthetic-delivery-demo-001",
 "output_contract": {"fields": ["结果趋势", "异常点", "可能原因", "复核步骤",
                                "后续实验建议", "依据与风险", "确认项"]}}
EOF
echo "# 合成示例任务" > demo/input/task.md

S=../scripts
python3 $S/contract_engine.py scaffold --case demo/input/case.json --out demo/output/result.json

# 模拟 Agent 只填了两个字段，且一个缺定位 → lint 应失败 (L2+L3)
python3 $S/contract_engine.py set --out demo/output/result.json \
  --field "结果趋势" --value "载荷先升后降，峰值出现在位移 3.5mm 附近（traces.json::peak_stats）"
python3 $S/contract_engine.py set --out demo/output/result.json \
  --field "异常点" --value "有两个离群点"
echo "--- lint(预期 FAIL) ---"
python3 $S/contract_engine.py lint --case demo/input/case.json --out demo/output/result.json && echo UNEXPECTED || echo "lint failed as expected"

# 补齐全部字段（合成示例文本，均带定位）后 lint 应通过
python3 $S/contract_engine.py set --out demo/output/result.json \
  --field "异常点" --value "trace_013、trace_027 峰值超出 IQR×1.5（findings.json::peak_outlier_traces）"
python3 $S/contract_engine.py set --out demo/output/result.json \
  --field "可能原因" --value "候选1: 样品差异（支持: findings.json::peak_stats；排除: 无饱和签名）"
python3 $S/contract_engine.py set --out demo/output/result.json \
  --field "复核步骤" --value "重跑 run 脚本复算（findings.json）；回查 trace_013.txt 第 30-40 行"
python3 $S/contract_engine.py set --out demo/output/result.json \
  --field "后续实验建议" --value "对离群样加做平行重复（依据 findings.json::thresholds）"
python3 $S/contract_engine.py set --out demo/output/result.json \
  --field "依据与风险" --value "依据 findings.json 全部阈值字段；风险: 原型误识别（task.md）"
python3 $S/contract_engine.py set --out demo/output/result.json \
  --field "确认项" --value "单位约定需专家确认（task.md 未注明）"
python3 - <<'PY'
import json
p = "demo/output/result.json"
r = json.load(open(p))
r["status"] = "success"
r["limitations"] = []
r["sources"] = ["findings.json (合成示例)"]
r["change_records"].append("示例：全部字段补齐，置 success")
json.dump(r, open(p, "w"), ensure_ascii=False, indent=2)
PY
echo "--- lint(预期 PASS) ---"
python3 $S/contract_engine.py lint --case demo/input/case.json --out demo/output/result.json
python3 $S/render_report.py --result demo/output/result.json --outdir demo/output
ls -la demo/output
