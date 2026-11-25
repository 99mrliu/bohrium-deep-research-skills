# 运行记录(run-record):合成示例的端到端复现

> **合成示例声明**:`examples/synthetic-input/` 全部数据为虚构教学数据
> (`case_id: "synthetic-import-gov-001"`;DOI 均为 `10.99988/...` 占位
> 号段;PMID、作者、期刊均虚构),不对应任何真实文献。
> `examples/synthetic-output/` 是本 bundle 脚本**真实运行**的产物;
> `work/change_dispositions.json` 为手工编写,模拟工作流第 5 步的
> 模型单次批量处置。

本示例演示:方言 a 状态对账 → 六路分类(含 field 级 before→after)→
水印推进提案(publisher HELD)→ 模型批量处置 → 治理状态折叠 → 自查门。

## 环境与命令

仅需 Python 3(标准库)。设 `$B` 为本 bundle 根目录:

```bash
# 0. 帮助(实测退出码 0)
python3 $B/scripts/import_governor.py --help

# 1. 分阶段运行(可选演示;实测退出码均为 0)
python3 $B/scripts/import_governor.py parse --input $B/examples/synthetic-input --work /app/work
python3 $B/scripts/import_governor.py diff --work /app/work
python3 $B/scripts/import_governor.py watermark --work /app/work

# 2. 模型判断点(唯一,单次批量):通读 work/import_diff.json 中
#    changed/withdrawn/unverifiable_withdrawal/inconsistent_state 条目,
#    写 work/change_dispositions.json(本目录存档为手工样例)
cp $B/examples/synthetic-output/work/change_dispositions.json /app/work/

# 3. 端到端全流程(在 /private/tmp 下实测,退出码 0,status=success)
cd /private/tmp
python3 $B/scripts/import_governor.py run-all \
  --input $B/examples/synthetic-input \
  --work /app/work --output /app/output \
  --dispositions /app/work/change_dispositions.json

# 4. 独立自查(实测退出码 0,7/7 PASS)
python3 $B/scripts/import_governor.py selfcheck \
  --input $B/examples/synthetic-input --work /app/work --output /app/output
```

## 实测结果(真实执行观测)

- **分类与工程化真值完全一致**:并集 13 = 7 unchanged + 1 changed +
  2 new + 1 withdrawn + 1 unverifiable_withdrawal + 1 inconsistent_state
  (上一状态 11 条,当前响应 10 条)。
- changed 条目 `10.99988/gov.0004` 给出 field 级 before→after:
  `year: 2020→2021`、`venue: journal of bio-adhesion letters →
  journal of bionic interface mechanics`。
- 水印提案:crossref `advance`(cursor 取响应 next-cursor,
  offset 20→26)、europepmc `advance`(cursorMark 取响应
  nextCursorMark)、publisher **`hold`(`response_absent`)**;
  `requires_approval=true`,`applied=false`。
- 治理状态折叠:gov.0004 `accept_change` 采纳新值;pmid:39000009
  `exclude_withdrawn` 移出(11+2−1=12 条记录);gov.0090 `escalate`
  保留待人工;pub:JBA-1042 `keep_previous` 标注待核验;2 条 new 自动
  纳入。水印保持原值(`watermark_status: held_pending_approval`)。
- selfcheck 7/7 PASS:契约键、分类分区(13=13=13)、计数守恒、
  重跑确定性(import_diff.json 8440 字节字节一致)、水印不回退、
  输入 import_state 哈希未被修改、材料哈希登记。
- `result.json`:`status="success"`,5 个 output_contract 字段全部
  填充,`unresolved_contract_fields` 为空;`uncertainty` 如实列出
  unverifiable_withdrawal、watermark_unapproved、escalated_pending_human。

## 确定性与降级路径实测

```bash
# 全新目录重跑同一命令(退出码 0):result.json / delta_report.md /
# final_governed_state.json / import_diff.json / proposed_next_state.json /
# previous_state.json / current_state.json 全部 cmp 字节一致。
# 同一 work 目录连续两次 diff:import_diff.json 字节一致。

# 缺 case.json(退出码 3,result.json status=input_error)
python3 $B/scripts/import_governor.py run-all --input <无case.json目录> ...

# 缺 import_state 材料(退出码 0):baseline_established=true,
# 全部 10 条当前记录分类 new,水印动作记 initialize。

# import_state 为未知方言(退出码 2):sniff_report 记录失败原因,
# status=partial,不猜结构。

# run-all 不给 --dispositions(退出码 2):diff/提案/报告照常,
# final_governed_state.json 不生成,uncertainty 含
# change_dispositions_pending。
```

## 产物清单

- `result.json`、`delta_report.md`、`final_governed_state.json`
- `work/`:`previous_state.json`(方言 a 规范化)、`current_state.json`
  (当前响应快照 + 逐源游标信号)、`import_diff.json`(六路分类 +
  证据定位)、`proposed_next_state.json`(水印提案,未写回)、
  `change_dispositions.json`(模型处置,手工样例)、
  `sniff_report.json`、`selfcheck.json`
