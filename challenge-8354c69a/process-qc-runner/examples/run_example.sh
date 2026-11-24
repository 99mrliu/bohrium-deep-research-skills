#!/usr/bin/env bash
# 合成示例（非正式案例、非预写答案）：过程质量控制演示。
# 剧情：阶段B 首次因输入缺失失败 -> 修复 -> 续跑时阶段A 被 SKIP（幂等恢复）。
set -e
cd "$(dirname "$0")"
rm -rf demo
mkdir -p demo/input demo/work demo/output

cat > demo/input/case.json <<'EOF'
{"case_id": "synthetic-qc-demo-001",
 "output_contract": {"fields": ["结果趋势", "复核步骤"]}}
EOF
printf 'x,y\n1,2\n2,4\n3,9\n' > demo/input/data.csv

S=../scripts
python3 $S/result_kit.py scaffold --case demo/input/case.json --out demo/output/result.json
python3 $S/budget.py init --work demo/work --requests 64 --seconds 900

# plan: A 统计 -> B 需要 stats.json 存在（首次会失败，因为 A 还没写出它？不——
# 让 A 正常产出，B 依赖一个故意缺失的文件 needed.txt，制造失败）
cat > demo/work/plan.json <<EOF
{"stages": [
  {"id": "A_stats",
   "cmd": "python3 -c \"import csv,json;rows=list(csv.reader(open('demo/input/data.csv')))[1:];ys=[float(r[1]) for r in rows];json.dump({'n':len(ys),'mean':sum(ys)/len(ys)},open('demo/work/stats.json','w'))\"",
   "inputs": ["demo/input/data.csv"], "outputs": ["demo/work/stats.json"],
   "timeout_s": 30},
  {"id": "B_needs_file",
   "cmd": "test -f demo/work/needed.txt && python3 -c \"print('B ok')\"",
   "inputs": ["demo/work/needed.txt"], "outputs": [],
   "timeout_s": 30},
  {"id": "C_checkpoint",
   "cmd": "python3 $S/result_kit.py checkpoint --out demo/output/result.json --stage C --set '结果趋势=y 随 x 单调上升(demo/input/data.csv)' --set '复核步骤=重跑 qc_runner 比对 manifest(demo/work/qc/manifest.json)' --status success --source demo/work/stats.json",
   "inputs": ["demo/work/stats.json", "demo/output/result.json"],
   "outputs": ["demo/output/result.json"], "timeout_s": 30}
]}
EOF

echo "=== 第一次运行（预期 B 失败，停在断点）==="
python3 $S/qc_runner.py run --plan demo/work/plan.json --work demo/work && echo UNEXPECTED || echo "-> failed as expected"

echo "=== 修复（补上 needed.txt）后原命令续跑（预期 A 被 SKIP）==="
echo "fixed" > demo/work/needed.txt
python3 $S/qc_runner.py run --plan demo/work/plan.json --work demo/work

python3 $S/budget.py tick --work demo/work
python3 $S/budget.py tick --work demo/work
python3 $S/budget.py report --work demo/work
echo "=== status / verify ==="
python3 $S/qc_runner.py status --work demo/work
python3 $S/result_kit.py verify --case demo/input/case.json --out demo/output/result.json

echo "=== 第三次运行（预期全部 SKIP，幂等）==="
python3 $S/qc_runner.py run --plan demo/work/plan.json --work demo/work
