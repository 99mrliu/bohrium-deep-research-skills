# 运行记录(run-record):合成示例的端到端复现

> **合成示例声明**:`examples/synthetic-input/` 全部数据为虚构的教学数据
> (`case_id: "synthetic-qc-guard-001"`;DOI 均为 `10.99977/...` 占位号段;
> 标题均为 "Synthetic ...";PMID 为虚构号码),不对应任何真实文献。
> `examples/synthetic-output/` 是本目录脚本**真实运行**的产物。

本示例专门演示过程质量控制的全流程:检查点化运行 → 唯一模型判断点
(模糊重复对仲裁)→ `--resume` 断点续跑 → `--replay` 重放一致性 →
自查门全 PASS 交付。

## 环境与命令

仅需 Python 3(标准库)。设 `$B` 为本 bundle 根目录,工作/输出目录可在任意
可写位置(平台上下文中为 `/app/work` 与 `/app/output`):

```bash
# 0. 帮助(退出码 0)
python3 $B/scripts/qc_guard.py --help

# 1. 首次运行:流水线 + 自查门
python3 $B/scripts/qc_guard.py \
  --case $B/examples/synthetic-input/case.json \
  --task $B/examples/synthetic-input/task.md \
  --work /app/work --out /app/output
# 实测退出码 2(诚实 partial):仲裁队列有 1 对待决(pair:crossref#03--publisher#02,
# Jaccard=0.6250),且尚未执行 --replay(replay_stable 检查 FAIL)。

# 2. 唯一模型判断点:通读 work/arbitration_queue.json,将全部待决对
#    在"单次批量请求"中仲裁,写入 work/arbitration_decisions.json
#    (本示例的决定文件已存档于 examples/synthetic-output/work/)。
cp $B/examples/synthetic-output/work/arbitration_decisions.json /app/work/

# 3. 断点续跑:intake/normalize/coverage 因输入哈希未变被跳过(stage_skipped);
#    identity 检测到 decisions 文件出现(stale_detected)并连同 report 重跑
python3 $B/scripts/qc_guard.py \
  --case $B/examples/synthetic-input/case.json \
  --task $B/examples/synthetic-input/task.md \
  --work /app/work --out /app/output --resume
# 实测退出码 2(诚实 partial):仲裁已决,但 --replay 尚未执行。

# 4. 重放一致性:两个全新目录各完整运行一次(自动播种仲裁决定)并逐字节比对
python3 $B/scripts/qc_guard.py \
  --case $B/examples/synthetic-input/case.json \
  --task $B/examples/synthetic-input/task.md \
  --work /app/work --out /app/output --replay
# 实测退出码 0;work/replay_verdict.json: verdict=STABLE,比对 20 个产物文件,
# 差异文件 0 个;report 阶段随后自动刷新,自查门 7 项全部 PASS,status=success。

# 5. 幂等性:同一命令再次 --resume
python3 $B/scripts/qc_guard.py \
  --case $B/examples/synthetic-input/case.json \
  --task $B/examples/synthetic-input/task.md \
  --work /app/work --out /app/output --resume
# 实测退出码 0;账本显示全部 5 个阶段 stage_skipped;result.json 与
# qc_report.md 的 sha256 与运行前完全一致(输出不变)。
```

## 重放裁决

**STABLE**(`work/replay_verdict.json`:`differing_files: []`,
`compared_file_count: 20`)。另经独立验证:在两个全新临时目录中各自完整
运行(播种同一仲裁决定),`diff -r` 两个输出目录、逐文件 `cmp` 全部 work
中间产物,均逐字节一致。

## 关键观测事实

- 9 条原始记录(crossref 4 / europepmc 2 / publisher 3)合并为 6 条;
  出版方 DOI 大写 `10.99977/SYN.0002` 经规范化后与 Crossref 精确匹配
  (`doi_exact`);EuropePMC 与出版方一条无 DOI 记录经
  `title_year_first_author` 规则合并。
- 近重复对 `crossref#03 × publisher#02`(Jaccard=0.6250)**未**被自动合并,
  进入仲裁队列;模型仲裁为 `distinct` 后两记录保持独立。
- `result.json` 包含全部 5 个 `output_contract` 字段,
  `unresolved_contract_fields` 为空,`status="success"`。
- `qc_report.md` 自查门 7 项全部 PASS(首次运行时的 2 项 FAIL ——
  仲裁待决与重放未运行 —— 为流程中有意设计并已消解的中间态)。

## 产物清单

- `result.json`、`qc_report.md`、`arbitration_queue.json`、
  `merged_records.json`、`coverage_matrix.json`、`decision_log.json`
- `work/`: `run_plan.json`(预算感知运行计划)、`run_ledger.jsonl`
  (逻辑序号账本,含 skip/stale/replay 全事件)、
  `arbitration_decisions.json`(模型判断产物存档)、
  `replay_verdict.json`(STABLE 裁决)
