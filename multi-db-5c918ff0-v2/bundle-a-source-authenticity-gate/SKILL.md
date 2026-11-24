---
name: source-authenticity-gate
description: >-
  上游数据真实性门控技能，适用于"多数据库联合检索"类离线科研案例：在任何归一化、去重、合并之前，
  先对 case 目录中的每一份材料工件（Crossref / Europe PMC / 出版商 JSON·JSONL·HTML 片段、保留引用图、
  组织方本地增量导入状态）做真实性认证——记录 sha256/大小/BOM/UTF-8/U+FFFD 探针，按内容形状嗅探分类，
  逐类型做信封与条目级模式认证（必填键、类型检查、total-results/hitCount 截断检测、HTML 标签残留、
  载荷内重复标识符），并做跨工件一致性核验（引用图悬挂边、导入状态条目的 not_verifiable/inconsistent
  判定），最终对每件工件给出 trusted / trusted_with_warnings / quarantined 的机器可读判定与原因码，
  仅放行可信工件的记录进入 gated_records.json 供下游消费。边界：本技能不做联网核验、不做文献相关性
  排序与主题筛选、不修改原始材料；unknown 工件被隔离但完整记录，绝不沉默丢弃；无法诚实填写的
  output_contract 字段一律置 null 并列入 unresolved_contract_fields。
---

# 上游数据真实性门控（Source Authenticity Gate）

核心理念：**任何下游步骤（归一化/去重/合并）都不得消费尚未通过真实性门控的记录。**
本技能在任何合并发生之前，对每一个输入工件先行认证。

## 何时使用

**适用：**
- 案例提供离线的数据库响应（Crossref/Europe PMC/出版商 API 的 JSON、JSONL 或 HTML 片段）、
  保留引用图（reference graph）、组织方本地增量导入状态（import state），需要先验真伪再合并；
- 需要可复核的溯源链：每条进入下游的记录都必须能指回其源工件与原始定位符（如 `message.items[3]`）；
- 需要对截断响应、缺字段条目、载荷内重复 DOI、HTML 残留、悬挂引用边、不可核验/不一致的
  导入声明给出**声明式**（而非沉默式）处理。

**不适用：**
- 需要联网调用真实 API 的检索（本技能完全离线）；
- 文献与研究问题的相关性判定、排序、主题筛选（属下游技能职责）；
- 对材料的修复/改写（门控只判定与隔离，不篡改原始证据）。

## 固定运行方式

技能安装路径为 `/skills/weekly-skill`。固定命令（在 `/app/work` 下执行亦可，脚本自足）：

```bash
python3 /skills/weekly-skill/scripts/source_gate.py \
  --case /input/case.json --task /input/task.md \
  --work /app/work --out /app/output
```

若安装路径不确定，先定位脚本：

```bash
find / -maxdepth 6 -name "source_gate.py" 2>/dev/null
```

仅 Python 3 标准库；无网络、无随机数、产物无墙钟时间。退出码：`0` 正常
（success 或诚实 partial）；`2` 诚实降级（内部异常，已写出 partial 结果）；`3` 输入无效
（case.json 缺失/不可解析）。`--help` 可用且退出 0。

**运行时契约**：输入在 `/input`（case.json + task.md + 材料文件），中间产物在 `/app/work`，
交付物在 `/app/output/result.json`——必须包含 `case_id`、`status`、`sources`（含 sha256）、
`uncertainty`、`change_records`、`artifacts`（每个输出文件的路径+sha256），以及 case.json 中
`output_contract` 声明的**每一个**顶层字段；无法诚实填写的字段置 `null` 并列入
`unresolved_contract_fields`，**绝不编造**。

## 完整工作流

预算意识：全程约 64 次请求 / 900 秒。重活全部脚本化；模型只做判读与收尾，不要把材料
全文逐段读进上下文——先看台账与报告，再有选择地抽查。

1. **（脚本化，STEP 0）** 脚本启动即先创建输出目录并写入 `result.json` 骨架
   （`status="partial"`、无任何推断值）——即使后续崩溃也留有诚实部分结果。
2. **（脚本化，Intake）** 读取 case.json 与 task.md；以排序顺序扫描 case 目录并解析
   case.json 中的 `materials` 引用来发现材料（绝不假定固定文件名）；对每个材料记录
   sha256 / size / BOM / UTF-8 合法性 / U+FFFD 计数。
3. **（脚本化，嗅探分类）** 按内容形状分类：crossref / europepmc / publisher（JSON 数组、
   JSONL、HTML 片段）/ reference_graph / import_state / unknown。unknown 被隔离但完整记录。
4. **（脚本化，模式认证）** 逐类型核验信封必填键、条目必填字段、字段类型、
   截断（`total-results` vs items 数、`hitCount` vs 结果数）、HTML 标签残留
   （剥离供检查、原始保留）、载荷内重复标识符。详见 `references/source-schemas.md`。
5. **（脚本化，跨工件一致性）** 引用图每条边的端点须能在某材料的标识符宇宙中解析
   （悬挂边报告但不致命）；导入状态每条 "db X id Y" 声明须与对应源响应核对——源工件缺失
   记 `not_verifiable`（声明缺口），id 不存在记 `inconsistent`（隔离该条目）。
6. **（脚本化，判定与门控）** 每件工件得 trusted / trusted_with_warnings / quarantined 及
   原因码（`references/reason-codes.md`）；仅可信（含带警告）工件的记录进入
   `gated_records.json`，附 `source_artifact` 与原始定位符。
7. **（脚本化，写出）** 依次写 `authenticity_ledger.json`、`gated_records.json`、
   `authenticity_report.md`，最后定稿 `result.json`（含全部契约字段、artifacts 的
   路径+sha256）。中间产物 `intake_manifest.json` 写入 `--work`。
8. **（模型判断）** 阅读 `authenticity_report.md` 与 `result.json`：确认判定符合预期、
   uncertainty 完整声明了隔离/缺口/不一致；若有 quarantined 工件，评估是否影响案例目标，
   并在最终答复中如实转述（不要自行把隔离记录"捞回"下游）。
9. **（模型判断）** 若 task.md 提出了门控之外的要求（如候选集排序），明确声明：
   本技能只交付已通过门控的记录集与证据链，相关性排序需下游技能完成。

## 输出契约

`--out` 目录下固定四个文件：

| 文件 | 内容 |
|---|---|
| `authenticity_ledger.json` | 逐工件判定：分类、verdict、全部检查（code/severity/locator/detail）、sha256、编码探针、记录数与放行数、导入条目逐条 verdict、汇总统计 |
| `gated_records.json` | 放行记录（`record_id`、`source_artifact`、`source_type`、jsonpath 式 `locator`、规范化的 `identifiers`、title/year/container）+ `excluded_items` + 被隔离工件清单及原因码 |
| `authenticity_report.md` | 人类可复核报告：判定表、检查明细、跨工件一致性、门控结论、不确定性声明 |
| `result.json` | 交付主文件，见"运行时契约" |

`result.json.status` 语义见下节；`artifacts` 列出全部输出文件的相对路径与 sha256
（`result.json` 自身的 sha256 置 null 以避免自引用，可通过重跑验证）。

## 状态语义

- **success**：全部工件可信（trusted / trusted_with_warnings 且无隔离）、task.md 可读、
  所有契约字段均被诚实填写。带警告可信不算降级——警告已在 ledger/report 中声明。
- **partial**：流程完整跑完但存在以下任一诚实缺口——有工件被 quarantined；task.md 缺失；
  存在无法填写的契约字段（置 null 并列入 `unresolved_contract_fields`）。退出码仍为 0。
- **input_error**：case.json 缺失/不可读/非 JSON 对象。退出码 3。
- **诚实降级**：任何未预期内部异常被顶层捕获，写出 partial 结果并在 uncertainty 中说明，
  退出码 2，绝不 traceback 崩溃。

## 规则边界和维护

- 门控**只读**输入材料，永不修改 `/input`；重跑幂等（覆盖同名输出）。
- 隔离是声明式的：被隔离工件及其记录数出现在 `result.json.uncertainty`、`gated_records.json`
  的 `quarantined_artifacts` 与报告中，绝不沉默丢弃。
- 原因码集合以 `references/reason-codes.md` 为准；新增检查必须同时登记原因码与严重级别。
- 判定规则是确定性的纯函数：同一份输入必得同一份输出（含 run_id——它由输入内容哈希派生）。
- 维护时修改 `scripts/source_gate.py` 后必须重跑 `examples/` 合成用例并刷新
  `examples/synthetic-output/`。

## 确定性与自查

交付前执行 5 步自查：

1. `python3 scripts/source_gate.py --help` 退出 0；
2. 对 `examples/synthetic-input/` 端到端运行退出 0，`result.json` 为合法 JSON 且含
   `case_id` 与全部契约字段（`curator_comment` 应为 null 且列入 unresolved）；
3. 换一组临时 `--work`/`--out` 重跑，`diff` 实质性产物（ledger/gated/report）逐字节一致
   （产物中无绝对路径、无时间戳）；
4. 三处埋点缺陷全部被捕获：europepmc `COUNT_MISMATCH`、import_state `IMPORT_INCONSISTENT`、
   reference_graph `DANGLING_EDGE`；
5. 确认 `result.json.artifacts` 的 sha256 与磁盘文件一致（`shasum -a 256` 抽验）。

## 示例

`examples/` 为**合成教学数据**（case_id `synthetic-source-gate-001`，全部论文/DOI/数据库
均为虚构，DOI 形如 `10.99999/synth.xxx`），用于演示门控形态与缺陷捕获，**不是官方赛题答案**。
`examples/synthetic-output/` 为脚本真实运行的产物，复现命令见
`examples/synthetic-output/run-record.md`。
