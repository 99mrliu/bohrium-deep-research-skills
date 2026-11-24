---
name: export-ingest-forensics
description: 系统性文献检索案例的摄入取证引擎。当案例提供多来源数据库导出文件（CSV/JSON/RIS/NBIB/TXT 混杂、编码不明、条目可能残缺）并要求全量题录筛选且结果可复核时使用。重心在上游数据真实性：格式嗅探、编码留痕、逐条来源坐标、隔离原因登记与摄入计数闭合审计，保证"没有一条输入被静默丢弃或改写"。不联网检索、不声称全局召回、不做模糊去重合并、不替代人工复核。
---

# export-ingest-forensics — 多源导出摄入取证与计数闭合

把"拿到一批导出文件"变成"每条记录有来源坐标、每个无法解析的条目有隔离原因、
每个数字都能首尾对账"的可复核起点。筛选结论的可信度首先取决于摄入层有没有
悄悄丢记录；本技能把这个环节做成自动硬门。

## 1 适用场景与红线

**适用**：案例材料含一个或多个文献导出文件（格式/编码混杂），要求全量题录筛选、
逐条可溯源、各环节计数闭合。

**红线**：
- 不联网检索：只在 `/input` 快照内工作，禁止声称实时数据库结果；
- 不静默丢弃：任何无法解析的条目进入 quarantine 并写明原因与摘录；
- 不改写原文：乱码只登记 `repair_notes`，修复决定留给下游与人工；
- 不做合并：`duplicate_hints` 只登记精确重复提示，合并属下游去重环节；
- 不伪造人工复核：quarantine 与缺失字段如实进入不确定性说明。

## 2 运行环境

- Python 3 标准库（json/csv/re/os/sys/argparse/io），无第三方依赖；
- 脚本位于 `$SKILL/scripts/`（评测器中通常为 `/skills/weekly-skill/scripts/`）；
- 退出码：0=正常；2=输入缺失（诚实降级）；3=审计 FAIL（阻断下游，须修复重跑）；
- 脚本幂等，同参数重跑覆盖同名产物。

## 3 端到端运行契约（平台案例）

1. 读 `/input/case.json` 与 `/input/task.md`，确认 case_id、研究问题、
   output_contract 字段清单（写 skill 时合同未知，运行时以合同为准）。
2. **尽早**在 `/app/output/result.json` 落骨架（status=in_progress、case_id、
   合同字段先置 null），之后每步增量填充，防超时零交付。
3. 材料盘点后执行第 4 节摄入管线；摄入审计 PASS 前不做纳排判断。
4. 后续纳排/去重/审计环节可结合案例要求用通用方法完成，但每条判定必须引用
   摄入层分配的 `record_id` 与来源坐标，保证链路可追。
5. 最终 result.json 填齐全部 output_contract 字段；无法填充的字段置 null 并在
   uncertainty 说明，不得删除字段。status 只能是 completed / partial / failed，
   partial 必须写明已完成与未完成部分。

## 4 摄入管线（编号步骤；[脚本]=确定性环节，[模型]=判断环节）

0. **[脚本] 摄入解析**：
   `python3 $SKILL/scripts/sniff_parse.py --input-dir /input --out /app/work/ingest`
   → `records_ingested.json`（规范记录+来源坐标+field_status+repair_notes）、
   `ingest_ledger.json`（每文件字节/行/编码/格式/计数）。
   若已知导出文件命名模式，用 `--glob` 过滤，避免误吞 task 说明文件。
1. **[脚本] 闭合审计**：
   `python3 $SKILL/scripts/ingest_audit.py --ingest-dir /app/work/ingest --out /app/work/ingest`
   → `ingest_audit.json` + `ingest_report.md`。exit 3 时按 FAIL 项修复
   （通常意味着上游产物被手工改动过——回到第 0 步重跑，而不是手改台账）。
2. **[模型] 异常研读**：读 ingest_report.md，把 quarantine 原因、mojibake 提示、
   非 UTF-8 文件、duplicate_hints 逐条转成 result.json 的 uncertainty 条目；
   确认是否影响筛选口径（如整批乱码 → 降级 partial 并说明）。
3. **[模型] 边界登记**：`field_status` 含 missing-abstract / missing-title 的记录
   在下游纳排中不得按"信息不足"直接排除，须转人工或标边界类型——把这条规则
   写进传给下游环节的说明。

## 5 输出合同映射（常见字段）

| 合同字段 | 来源产物 |
|---|---|
| case_id | case.json |
| status | 审计 PASS 且后续环节完成 → completed；摄入有未解异常 → partial |
| product | 摄入后的规范记录集说明（记录数、格式分布、来源文件清单） |
| evidence_matrix | ingest_ledger.json 每文件条目 + ingest_audit.json 各检查项 |
| sources | 输入导出文件清单（含字节数、编码、格式），只列快照内文件 |
| uncertainty | quarantine 清单及原因、mojibake 提示、duplicate_hints、非 UTF-8 文件 |
| change_records | 摄入参数（--glob 过滤）与重跑记录 |
| counts | totals（files/records_parsed/items_quarantined/duplicate_hints） |
| checks | ingest_audit 的 A1–A6 PASS/FAIL |

## 6 异常处理表

| 异常 | 处理 |
|---|---|
| /input 无候选导出文件 | sniff_parse exit 2；result.json status=failed 并说明材料缺失，终止 |
| 整文件无法识别格式 | plain-text 兜底：整文件隔离，原因 `unrecognized-format-plain-text` |
| JSON 单条损坏 | 只隔离该条（json-line-parse-error / json-entry-not-object），其余照常 |
| RIS 块无标题 | 隔离该块（ris-block-without-title），保留全部原始标签摘录 |
| 编码非 UTF-8 | 按 encoding_playbook 回退并留痕；lossy-replace 文件进 uncertainty |
| 字段疑似乱码 | 记 repair_notes，不改写；锚定环节以原文为准 |
| 审计 A1–A6 任一 FAIL | 阻断下游；重跑摄入；无法修平则 status=partial 并逐项说明 |

## 7 最小调用示例（合成数据）

`examples/minimal/exports/` 含三个**合成**导出文件（pubmed_export.csv、
scopus_export.json、wos_export.txt，内容为虚构题录，不对应真实检索结果）：

```bash
cd <bundle 根目录>
python3 scripts/run_example.py
```

期望：解析 11 条记录、隔离 2 条（JSON 损坏条目、无标题 RIS 块）、登记 3 条
精确重复提示（2 条按归一 DOI、1 条按归一标题）、1 条 mojibake 提示、
1 条 missing-abstract、1 条 missing-doi；审计 A1–A6 全 PASS，exit 0。
产物在 `examples/minimal/output/`（已随包附带，标明为合成示例输出），
逐步运行记录见 `examples/minimal/RUNLOG.md`。

## 8 自查方法

- 重跑 `run_example.py`，两次产物逐字节一致（确定性）；
- 手工抽 3 条记录，对照原导出文件核对 source_line 与字段值；
- 把某个导出文件删一行再跑，A1/A2 必须 FAIL——验证硬门有效；
- 确认 result.json 的 uncertainty 覆盖全部 quarantine 条目，无遗漏。
