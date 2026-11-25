---
name: retrieval-coverage-ledger
description: 文献筛选任务的上游数据真实性与来源/遗漏审计引擎。对有限检索快照建立台账：逐条记录归因到实际查询（显式来源字段 > 词面重叠推断 > 诚实未归因登记）、逐查询产出、全记录恰好一次的会计恒等式（违规确定性修复并留痕）、保守的重复/版本登记（夹具标注仅作 provenance），以及显式遗漏说明（有限快照、无实时库、不可声称全局召回）。当任务要求来源可追溯、遗漏可说明、筛选结果可核验时使用。
---

# retrieval-coverage-ledger

## 用途与重心

本 Skill 的重心是**上游数据真实性与来源/遗漏审计**。筛选标签只是副产品；真正的交付物是一套建立在检索快照之上的台账系统：哪条实际查询命中了哪条记录（来源可追溯）、每条查询的产出是多少（per-query yield）、每条输入记录是否在 keep/pending/exclude 中恰好出现一次（会计恒等式）、哪些记录是同一工作的重复导出（保守登记）、以及这个有限快照**不可能包含什么**（遗漏说明）。模型只在一次批量调用中给出判定，其余全部由确定性脚本保证并留痕。

## 适用条件

- 输入为 `/input/case.json`（固定研究问题、**实际查询输入**、约 9 条真实署名文献的有限快照；部分案例含已用 `fixture_note` 等字段标注的合成重复导出/冲突意见夹具——仅可作 provenance 引用，绝不可当作 ground truth）与 `/input/task.md`。
- 要求**全记录筛选**：每条输入记录恰好计入一个分桶一次；无法归因的记录进入未归因登记，不得静默丢弃。
- 平台运行契约：在 `/app/work` 下工作，最终结果写入 `/app/output/result.json`，必须含回显的 `case_id` 与 `output_contract` 声明的全部字段，以及诚实的 `status`、`uncertainty`、`change_records`。

## 运行契约与预算纪律（64 次模型请求 / 900 秒）

按以下四步执行，模型调用 ≤2 次，任何一步失败都跳到第 3 步的退化路径交付诚实 partial：

1. **建账（脚本，无模型调用）**
   `python3 /skills/weekly-skill/scripts/coverage_engine.py map --case /input/case.json --out /app/work/coverage.json`
   读取 coverage.json：`attributions` 是逐条来源归因（explicit/inferred），`per_query_yield` 是逐查询产出，`unattributed_register` 与 `missing_metadata` 直接进入遗漏说明。
2. **批量判定（1 次模型调用）**：对 coverage.json 中全部 record_id 一次性输出 `{"decisions":[{"record_id","bucket"∈{keep,pending,exclude},"rationale","quote"}]}`，存为 `/app/work/decisions.json`。`quote` 必须是该记录标题/摘要的**逐字子串**；判不了的一律 `pending`，不得编造。9 条规模禁止逐条调用模型。
3. **入账（脚本）**
   `python3 /skills/weekly-skill/scripts/coverage_engine.py account --case /input/case.json --coverage /app/work/coverage.json --decisions /app/work/decisions.json --out /app/output/result.json`
   脚本强制会计恒等式（未知 id 拒入 `rejected_register`、缺失 id 补 pending、重复判定取首次、非法 quote 置 null，全部记入 `change_records`），构建重复/版本登记与遗漏说明，并逐字段镜像 output_contract。**退化路径**：省略 `--decisions`，全部记录 pending，`status.state=partial`，仍是合法交付。
4. **交付校验（脚本）**
   `python3 /skills/weekly-skill/scripts/coverage_engine.py validate --case /input/case.json --result /app/output/result.json`
   FAIL 则按打印清单修复后重跑第 3 步；PASS 才视为可交付。

## 输入与输出

- 输入：`/input/case.json`、`/input/task.md`；中间物：`/app/work/coverage.json`、`/app/work/decisions.json`。
- 输出：`/app/output/result.json`，含 `case_id`、`screened_records`（bucket/rationale/quote/逐条 attribution）、`query_coverage`（逐查询产出 + 未归因登记）、`duplicate_register`（merged 组与 fixture_declared 条目）、`rejected_register`、`omission_statement`（有限快照免责声明、缺失元数据、疑似重复复核队列）、`summary`、`status`、`uncertainty`、`change_records`，以及契约声明的每个其他字段（可回显则回显，可生成则生成，否则显式 null + `status.incomplete`）。

## 异常处理

- case.json 无法解析 → 脚本以非零退出并说明；候选池定位是宽容的（命名键优先，否则取最大的含 title 的顶层列表）。
- 决策文件缺失 → 全 pending 的诚实 partial；决策含未知 id → 拒入 `rejected_register` 并留痕，不影响真实记录。
- 记录无来源字段且与所有查询零重叠 → 未归因登记（诚实暴露，不丢弃）；元数据缺失 → 逐条进入遗漏说明。
- 夹具标注（fixture_note）逐字引用为 provenance；模糊疑似重复对只进复核队列，绝不自动合并。

## 方法说明与限制

- 归因优先级与推断诚实规则、合并阈值、遗漏说明模板、会计恒等式修复规则详见 `references/coverage-playbook.md`；同一输入必得同一输出，可独立复核。
- 局限：inferred 归因是词面重叠启发式，`matched_tokens` 即审计线索，语义误差写入 `uncertainty`；快照之外的召回无法声称（无实时数据库）；契约字段名按案例原文镜像，不做语义猜测。
- 自查方法：validate PASS；`summary.accounting_identity_holds=true`；抽查若干 `screened_records[].quote` 确为原文子串；`duplicate_register` 无未知 id；示例见 `examples/minimal/`（合成示例，不冒充正式案例结果）。
