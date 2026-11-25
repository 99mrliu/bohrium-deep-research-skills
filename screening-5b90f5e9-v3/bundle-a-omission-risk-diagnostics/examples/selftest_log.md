# 自测日志（selftest log）

> 全部命令于 2026-11-25 在 macOS (arm64) / Python 3.12.14 上真实执行，exit code 为实测值。
> 输入输出均为**合成示例，非真实评测案例**。工作目录变量：
> `B=<bundle 根目录>`（即本文件上两级）。

## A. 合成示例端到端（happy path）

命令：`bash examples/run_example.sh`（内部逐步等价于下列 6 条）

| # | 命令（参数均为 `--input-dir examples/run/input --work examples/run/work --output-dir examples/run/output`） | exit code |
|---|---|---|
| A1 | `python3 scripts/scaffold_result.py ...` | 0 |
| A2 | `python3 scripts/mine_near_misses.py ...` | 0 |
| A3 | `python3 scripts/fragility_report.py ...` | 0 |
| A4 | `python3 scripts/facet_coverage.py ...` | 0 |
| A5 | `python3 scripts/omission_statement.py ...` | 0 |
| A6 | `python3 scripts/selfcheck.py ...` | 0 |

run_example.sh 整体退出码：0。selfcheck 输出三项全 pass：
`contract_fields_present`（10 字段齐备）、`evidence_anchor_authenticity`
（54 条证据 quote 全部锚定到题录真实片段）、`status_finalization`（status=completed）。

## B. 降级路径：judgments 缺失

构造：`mktemp -d` 临时目录，仅复制 case.json + records.json（不放 judgments.json），顺序执行 6 脚本。

| 脚本 | exit code | 实测行为 |
|---|---|---|
| scaffold_result.py | 0 | 骨架正常 |
| mine_near_misses.py | 2 | `near_misses`/`recheck_worklist` 置 null，uncertainty 记字段名与原因 |
| fragility_report.py | 2 | `fragility_report` 置 null + uncertainty |
| facet_coverage.py | 2 | `facet_coverage` 写 `{"status":"skipped"}` + uncertainty |
| omission_statement.py | 2 | 缺上游产物，置 null + uncertainty 提示先跑诊断脚本 |
| selfcheck.py | 2 | 合同校验 pass（null 字段均有 uncertainty 交代）；证据锚定校验标记 skipped；status 保持 partial |

result.json 最终 `status=partial`，uncertainty 5 条。

## C. 失败路径：证据 quote 被篡改

构造：复制完整输入后，用 python 将 R03 第一条证据 quote 改为
`"this phrase does not exist anywhere"`，顺序执行 6 脚本。

| 脚本 | exit code | 实测行为 |
|---|---|---|
| scaffold_result.py | 0 | 骨架正常 |
| mine_near_misses.py | 0 | 诊断不受篡改影响（只读 verdict/anchor 元数据） |
| fragility_report.py | 0 | 同上 |
| facet_coverage.py | 0 | 同上 |
| omission_statement.py | 0 | 同上 |
| selfcheck.py | 3 | `evidence_anchor_authenticity` fail：quote 未锚定到 abstract 原文；status 保持 partial |

## D. 边界：case.json 整体缺失

构造：空 input 目录执行 `scaffold_result.py`。
exit code **2**；写出最小 result.json（`status=failed`，uncertainty 说明合同不可知），stderr 一行提示。

## E. 幂等性验证

命令：happy path 连跑两遍，`run_example.sh` 第二次整体退出码 **0**；
对比两遍 `run/work/near_misses.json`：`identical = True`（诊断段内容稳定，
仅 change_records 时间戳追加，属设计行为）。

## F. 合规自查

| 检查 | 结果 |
|---|---|
| SKILL.md frontmatter YAML 合法性 | 通过（pyyaml 解析，name=omission-risk-diagnostics） |
| 文件总数 | 26（≤50） |
| 总大小 | 141,837 字节 ≈ 139 KB（≤2MB），单文件最大 20,708 字节 <500KB |
| 符号链接 | 无 |
| 非 UTF-8 / 二进制 | 无（全部 UTF-8 文本，逐文件解码校验通过） |
