# examples/ — 合成示例（非正式案例结果）

本目录全部内容均为**合成示例，非正式案例结果**，仅用于演示 zh-register-calibrator 的端到端闭环。

## 目录

- `input/case.json` — case_id = `EXAMPLE-NOT-A-TEST-CASE`，output_contract 含 5 键（case_id / deliverable / preserved_facts / evidence_map / change_log）
- `input/task.md` — 任务说明
- `input/materials/material_study.md` — 合成材料，含 L1 信号词（初步/preliminary/pilot/小样本/n=12），无因果设计信号
- `input/draft_bad.md` — 合成病稿，故意触发 R1–R7 各至少一条（R8 经 glossary.lock 与候选组触发）
- `work/glossary.lock`、`work/preserved_facts.json`、`work/evidence_map.json` — 工作目录输入
- `output/` — 以下全部为脚本真实运行生成：
  - `style_report.md` — 首轮 lint 报告（44 条：高 16 / 中 25 / 低 3，R1–R8 全覆盖）
  - `findings.json`、`lint_stats_initial.json` — 机器可读 findings 与统计
  - `draft_autofixed.md` + `fix_log.json` — --fix 产物（23 处，仅 R1/R2）
  - `deliverable.md` — 模型侧逐条处理 R3–R8 后的最终稿
  - `resolution_log.json` — 21 条处理记录（含 1 条驳回示例）
  - `verify_report.md` + `lint_stats.json` — 复检产物（高 0，VERIFY PASS）
  - `result.json` — 装配产物（契约 5 键齐全，status=success）

## 复现命令

```bash
cd <skill 根目录>
# 1) 首轮 lint
python3 scripts/register_lint.py --draft examples/input/draft_bad.md \
  --materials examples/input/materials/material_study.md --workdir examples/work \
  --report examples/output/style_report.md --findings-json examples/output/findings.json \
  --stats-json examples/output/lint_stats_initial.json
# 2) 自动修复
python3 scripts/register_lint.py --draft examples/input/draft_bad.md \
  --materials examples/input/materials/material_study.md --workdir examples/work \
  --fix --out examples/output/draft_autofixed.md --fix-log examples/output/fix_log.json
# 3) 模型处理 R3–R8 → deliverable.md + resolution_log.json（本示例已给出）
# 4) 复检
python3 scripts/register_lint.py --draft examples/output/deliverable.md \
  --materials examples/input/materials/material_study.md --workdir examples/work --verify
# 5) 装配
python3 scripts/assemble_result.py --case examples/input/case.json \
  --deliverable examples/output/deliverable.md --fix-log examples/output/fix_log.json \
  --resolution-log examples/output/resolution_log.json --lint-stats examples/output/lint_stats.json \
  --preserved-facts examples/work/preserved_facts.json --evidence-map examples/work/evidence_map.json \
  --sources examples/input/materials/material_study.md --out examples/output/result.json
```
