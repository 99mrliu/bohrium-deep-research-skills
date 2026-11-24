# 合成示例（非正式案例结果）

> 本目录全部内容为**合成示例，非正式案例结果**，仅用于演示
> stagegate-qc-runner 的端到端流程。`output/` 下的文件是脚本真实运行的产物。

## 目录

- `input/case.json`：合成案例（case_id=`EXAMPLE-NOT-A-TEST-CASE`，
  output_contract 含 case_id / deliverable / preserved_facts / evidence_map /
  change_log 五键）
- `input/task.md`：合成任务
- `input/materials/material-01.md`：合成材料
- `output/`：真实运行生成的产物（workplan、worklog、notes、初稿、骨架版与终版
  result.json、selfcheck_report、delivery_manifest 等）

## 完整命令序列（两分钟复现）

```bash
cd <本 bundle 根目录>
export STAGEGATE_INPUT_DIR=$PWD/examples/input
export STAGEGATE_WORK_DIR=$PWD/examples/output
export STAGEGATE_OUTPUT_DIR=$PWD/examples/output

# 1) 初始化：立即生成 workplan + 骨架 result.json（全字段+PENDING）+ deliverable 占位
python3 scripts/gate.py init

# 2) 人为负例：产物未建先 check → 观察 FAIL（退出码 1）
python3 scripts/gate.py check intake

# 3) 补齐 intake 产物后 check → GO
mkdir -p examples/output/notes
# …编写 notes/material_inventory.md（内容见 output/notes/）…
python3 scripts/gate.py check intake

# 4) outline / draft / audit：写产物 → check
python3 scripts/gate.py check outline
python3 scripts/gate.py check draft
python3 scripts/gate.py check audit

# 5) 量规自评
python3 scripts/gate.py selfcheck

# 6) 人为负例：deliverable 里故意留 TODO → deliver 出口清单 FAIL（退出码 2）
#    修复后重跑 deliver → GO，生成终版 result.json 与 delivery_manifest.json
python3 scripts/gate.py deliver
```

## output/ 中值得看的文件

- `result.json`：终版（五键齐全、case_id 逐字节一致、status/sources/uncertainty）
- `result_skeleton_snapshot.json`：init 后立即生成的骨架版快照（全字段 + PENDING），
  演示"先交付后优化"
- `worklog.jsonl`：全程留痕，包含两次人为 FAIL（intake 产物缺失、deliverable
  残留 TODO）及修复后 GO 的完整记录
- `delivery_manifest.json`：输出文件清单 + sha256 + 出口检查结果
- `selfcheck_report.md`：机器判定项评分 + 需模型自答清单
