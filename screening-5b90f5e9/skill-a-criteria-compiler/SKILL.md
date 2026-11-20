---
name: criteriaforge-screen-engine
description: 当案例要求按纳入/排除标准对题录做全量筛选（all-record screening）且每条判定需可复核时使用。方法链：解析案例→尽早落 result.json 骨架→记录归一化→保守精确去重→把纳入/排除标准编译为版本化可执行的 criteria_table.json→模型逐判据批量判定并锚定证据→脚本做证据子串校验门（失败 exit 3 强制重新锚定）→确定性合成纳入/排除/转人工→标准升版回溯重判→PRISMA 计数闭合与审计→终检。边界：只在给定材料快照内工作，不联网检索、不声称全局召回、不预置答案、不伪造人工复核；模糊去重与全文质量评价不属本方向。
---

# criteriaforge-screen-engine — 判据即代码的系统性文献筛选引擎

把纳入/排除标准编译成版本化、可执行、可回溯的判定规则表；筛选 = **模型逐判据判定 + 脚本确定性合成与校验**。

## 1 适用场景与边界

**适用**：案例给出固定研究问题、一批题录材料（json/jsonl/csv/ris/txt）、纳入/排除标准文本，要求对全部题录逐条给出 included / excluded / needs_human 判定，且每条判定要有理由码和指向标题/摘要真实片段的证据，检索、去重、纳排、冲突、审计各环节计数闭合、可被第三人独立复跑。

**不做什么（红线）**：
- 不联网检索：只在 `/input` 提供的有限快照内工作，禁止声称实时数据库检索或全局召回；
- 不预置答案：criteria_table、judgments、decisions 全部在运行时从案例材料生成；
- 不伪造人工复核：needs_human 队列如实保留并标注边界类型，绝不冒充"人工已复核"；
- 模糊去重不属本方向：只做归一 DOI/归一题名精确合并，疑似模糊重复只登记不合并；
- 全文质量评价不做：只有题录/摘要层面的纳排筛选，偏倚风险评估超出范围。

## 2 运行环境

- Python 3 标准库（json/re/sys/argparse/pathlib/html/unicodedata/collections/csv），无第三方依赖；
- 脚本在 `$SKILL/scripts/`；若 `$SKILL` 未设置，定位兜底：
  `find / -maxdepth 6 -name screen_engine.py -path "*criteria-compiler*" 2>/dev/null`
  取其上上级目录为 `$SKILL`（评测器中通常为 `/skills/weekly-skill`）；
- 退出码约定：**0=通过；2=输入不足（诚实降级）；3=校验失败**（锚定失败/计数不闭合/终检失败）；
- 所有脚本顶层 try/except 兜底，绝不 traceback-crash；全部脚本幂等，同参数重跑覆盖同名产物，可断点续跑；
- 路径默认值：`--input-dir /input`、`--work /app/work`、`--output-dir /app/output`，均可用参数覆盖。

## 3 工作流程（编号步骤；[脚本]=确定性脚本环节，[模型]=模型判断环节）

0. **[脚本] 盘点**：`parse_case.py --input-dir /input --work /app/work` → `case_summary.json`（case_id、research_question、criteria 片段、output_contract 字段、材料清单）。材料为零 → 直接填 result.json `status=failed` 并说明，终止。
1. **[模型] 读合同**：从 case.json / task.md 确认 output_contract 字段语义（以合同为准）。
2. **[脚本] 尽早落骨架**：`scaffold_result.py` → `/app/output/result.json`（status=in_progress），之后每步增量填充，防超时零交付。
3. **[脚本] 归一化**：`normalize_records.py` → `normalized.jsonl`（含 field_status 三级语义；HTML/编码容忍留痕）。
4. **[脚本] 保守精确去重**：`exact_dedup.py` → `dedup_ledger.jsonl` + `dedup_summary.json`（merge_exact/keep；suspected_pairs 只登记）。
5. **[脚本] 标准骨架**：`build_criteria_skeleton.py` → `criteria_table.json`（v1.0.0 空表）。
6. **[模型] 标准编译（一次请求批量完成）**：把案例标准文本编译进 criteria_table：每条 {criterion_id, type, statement, predicate（可判定检查点）, evidence_required, reason_code, boundary_notes}；填 eligible_languages；删掉下划线开头的说明字段。标准文本缺失时从 task.md 提取并在 result.json `change_records` 记录、标注需二次确认。
7. **[模型] 逐判据判定（尽量一次请求批量完成）**：读 normalized.jsonl + dedup_ledger（每个 study_group 只判 canonical 记录）+ criteria_table，按 `templates/judgments_format.md` 输出 `/app/work/judgments.jsonl`：每条记录×每条标准一行 {record_id, criterion_id, verdict, evidence_snippet, note}。evidence_snippet 必须从题录原文复制。
   **[脚本] 校验+合成**：`screen_engine.py`：先过证据锚定校验门——任一 snippet 归一后不是该记录 title/abstract 子串 → 写 `anchor_failures.json` 并 **exit 3**；模型必须按失败清单重新锚定、重跑，直到 exit 0。通过后确定性合成 `decisions.jsonl`（excluded/included/needs_human + primary_reason_code + 逐标准明细 + 边界类型）与 `screening_summary.json`。
8. **[模型+脚本] 标准升版回溯（条件触发）**：筛选中发现标准歧义需细化 → 按 `rules/criteria_versioning.md` 升版本、写 changelog、留存旧版 → `rejudge_plan.py --old <旧版> --new <新版>` 列出受影响 record_id → [模型] 强制重判这些记录 → 重跑 screen_engine。**禁止口头改标准不回改表**。
9. **[脚本] 计数闭合**：`prisma_check.py`：identified = duplicates_removed + screened；screened = included + excluded + needs_human；不闭合 exit 3 并打印差额；输出 PRISMA 风格流量与逐步审计 `audit_summary.json`（每步 input/output 条目数、operator=system/model、依据文件路径）。
10. **[模型] 填充 result.json**：按第 4 节映射把产物汇总进合同字段（一次请求）。
11. **[脚本] 终检**：`selfcheck.py` → 全 PASS（exit 0）才视为交付完成；FAIL 项逐一修复重跑。

## 4 输出合同映射

output_contract 在写 skill 时未知，运行时从 case.json/task.md 读取并逐字段填充。常见字段映射：

| 合同字段 | 来源产物 |
|---|---|
| case_id | case_summary.json 的 case_id |
| skill_name | 固定 "criteriaforge-screen-engine" |
| status | completed / partial / failed（见第 5 节） |
| product | 主交付物说明 + decisions.jsonl 中逐记录结论（group_id、decision、primary_reason_code、boundary_types） |
| evidence_matrix | decisions.jsonl 的 per_criterion 明细（record×criterion 的 verdict + evidence_snippet 原文片段） |
| sources | 使用的输入材料文件清单（case_summary.records_files）+ 各产物路径；只列快照内文件，不虚构外部来源 |
| uncertainty | dedup_summary.suspected_pairs + 全部 needs_human 记录及其边界类型 + 解析警告 |
| change_records | criteria_table 的 changelog + 升版重判记录（rejudge_plan）+ 标准来源二次确认记录 |
| counts | audit_summary.prisma_flow（identified/duplicates_removed/screened/included/excluded/needs_human） |
| checks | audit_summary.closure_checks + selfcheck 各项 PASS/FAIL |

合同有额外字段时按语义填充并以合同为准；无法填充的字段填 null 并在 uncertainty 说明，**不得删除合同字段**。

## 5 异常处理表

| 异常 | 处理 |
|---|---|
| 材料文件为零 | result.json status=failed，说明原因，终止（parse_case 已警告） |
| 摘要为空/缺失 | 引擎强制 needs_human / EX-NO-ABSTRACT，boundary_types=["no_abstract"]，不自动排除 |
| 语言不符 eligible_languages | 引擎强制 needs_human / EX-LANGUAGE，boundary_types=["language_mismatch"] |
| 人群/干预部分重叠 | 模型判 uncertain + BND-PARTIAL-OVERLAP → needs_human |
| 编码乱码 | normalize 阶段 errors=replace 留痕 encoding_notes，继续降级处理 |
| 标准文本缺失 | 从 task.md 提取片段编译，change_records 记录"来源为 task.md，需二次确认" |
| 证据校验反复失败（≥3 轮仍 exit 3） | 未判定记录保留在 anchor_failures 清单，status=partial，uncertainty 说明 |
| 计数不闭合 | prisma_check exit 3 打印差额；排查后重跑；无法闭合则 status=partial |
| 合成重复导出（如 search09 式） | 仅精确合并；冲突标注记入 uncertainty，不擅自仲裁 |

## 6 最小调用示例

见 `examples/`：**全部为合成示例，非真实评测案例**。`example_walkthrough.md` 给出端到端命令与示意输出；`selftest_log.md` 记录真实自测的每步命令与 exit code。

```bash
SKILL=/skills/weekly-skill   # 或用第 2 节 find 兜底定位
python3 $SKILL/scripts/parse_case.py --input-dir /input --work /app/work
python3 $SKILL/scripts/scaffold_result.py --work /app/work --output-dir /app/output
python3 $SKILL/scripts/normalize_records.py --work /app/work
python3 $SKILL/scripts/exact_dedup.py --work /app/work
python3 $SKILL/scripts/build_criteria_skeleton.py --work /app/work
# [模型] 填充 criteria_table.json、产出 judgments.jsonl
python3 $SKILL/scripts/screen_engine.py --work /app/work
python3 $SKILL/scripts/prisma_check.py --work /app/work
# [模型] 填充 /app/output/result.json
python3 $SKILL/scripts/selfcheck.py --work /app/work --output-dir /app/output
```

## 7 维护信息

- 版本：v1.0.0
- 作者：bohrium-deep-research-skills 项目组（Bundle A: 判据即代码方向）
- 日期：2026-11-20
- 变更：首版。规则见 rules/，模板见 templates/，合成示例见 examples/。
