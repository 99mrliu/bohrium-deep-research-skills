---
name: record-status-hygiene
description: >-
  文献状态卫生与版本归并技能，适用于"多数据库联合检索"类离线科研案例：对 Crossref /
  Europe PMC / 出版商 JSON·JSONL·CSV 记录、保留引用图与组织方本地 import_state 做
  记录级状态风险治理——识别撤回（retraction）、勘误（erratum/correction）、关注声明
  （expression of concern）、import_state 撤回条目，并将 preprint 与其期刊正式版
  （VoR）归并为一项研究。差异化能力：每条状态信号携带机器可读原因码与证据定位符
  （文件+jsonpath）；显式关系链接才允许自动配对，书目学回退一律进待审队列；
  import_state 声称已导入但响应缺席的标识符被隔离报告；查不到状态的记录标
  status_unverifiable 而非 clean，不进入候选池。边界：完全离线，绝不查询外部撤回
  数据库；状态证据只能来自材料内部显式字段/关系/引用图状态属性；不做通用 DOI
  去重、查询规划、覆盖率统计与相关性排序。
---

# 文献状态卫生与版本归并（Record Status Hygiene）

核心理念：**一个静默混入撤回论文的合并候选集、或把 preprint 与其 VoR 计作两项
独立研究的候选集，即使 DOI 去重完全成功，也仍然是错的。**
本技能在候选集定稿之前，对每一条记录做状态风险治理与版本归并。

## 适用场景与边界

**适用：**
- 案例提供离线数据库响应（Crossref works 信封 `message.items`、Europe PMC
  `resultList.result`、出版商 JSON/JSONL/CSV）、保留引用图（节点状态属性/撤回边）、
  组织方本地增量 import_state（含 withdrawn 条目）；
- 需要可复核的状态证据链：每条 severe/flagged 判定都能指回
  `文件::jsonpath` 定位符；
- 需要 preprint↔VoR 归并：候选集按研究计数，引用字段以 VoR 为准；
- 需要 import_state 对账：withdrawn 排除、absent-but-claimed 隔离、
  not-yet-imported 信息性披露。

**边界（重要）：**
- **不联网**。绝不调用真实 API，绝不查询外部撤回数据库（如 Retraction Watch、
  Crossmark 在线服务）；
- **状态证据只能来自材料内部**的显式字段（pubTypeList、status）、显式关系
  （Crossref relation/update-to）、引用图状态属性与 import_state 条目；
- **查不到状态 ≠ 干净**：无状态承载面的记录一律标 `status_unverifiable`，
  不进入候选池，列入待补证清单；
- 不做通用 DOI 去重/合并（那是上游）、不做查询规划、不做覆盖率统计、
  不做与研究问题的相关性排序（那是下游）；
- 只读输入材料，永不修改 `/input`。

## 运行环境

- 技能安装路径 `/skills/weekly-skill`；仅 **Python 3 标准库**；无网络、无随机数、
  产物无墙钟时间（确定性：同输入必得同输出，重跑幂等覆盖同名文件）。
- 若安装路径不确定，先定位脚本：

```bash
find / -maxdepth 6 -name "status_hygiene.py" 2>/dev/null
```

- 退出码：`0` 正常（success 或诚实 partial）；`1` selfcheck 失败（产物不可信）；
  `2` 诚实降级（无材料可扫描 / 裁定文件部分无效 / 内部异常，已写出部分结果）；
  `3` 输入无效（case.json 缺失/不可解析/非 JSON 对象）。`--help` 可用且退出 0。
- 所有脚本顶层均有 try/except：未预期异常被捕获后写出降级 result.json 并以
  退出码 2 收场，绝不 traceback 崩溃。

## 运行契约

输入在 `/input`（case.json + task.md + 材料文件），中间产物在 `/app/work`，
交付物在 `/app/output`：

- `result.json` 必须包含：`case_id`、`skill_name`、`status`、`artifacts`（各产物
  路径+sha256）、`sources`（各材料 sha256）、`uncertainty`、`change_records`、
  `counts`（records_scanned / severe / flagged / unverifiable / pairs_explicit /
  pairs_pending / import_inconsistent）、`checks`，以及 case.json `output_contract`
  声明的**每一个**顶层字段；
- 无法诚实填写的契约字段一律置 `null` 并列入 `unresolved_contract_fields`，
  **绝不编造**；存在 null 字段或任何声明的缺口时 `status` 降为 `partial`
  （退出码仍为 0）——诚实部分优于虚假完整。

## 工作流程

预算意识：重活全部脚本化；模型只做判读与裁定，不要把材料全文逐段读进上下文——
先看台账与报告，再有选择地抽查。

0. **（脚本化）读取 case**：`parse` 读取 case.json + task.md，按 case.json
   `materials` 引用（绝不假定固定文件名）发现并嗅探材料。
1. **（脚本化）解析+嗅探**：分类 crossref / europepmc / publisher(json|jsonl|csv) /
   reference_graph / import_state / unknown；每条记录归一化为
   `{record_id, source_db, source_path, jsonpath_locator, doi_norm, pmid, pmcid,
   title_norm, year, authors, pub_types, relations, raw_status_fields}`；
   每个字段区分 missing / unknown / not_provided。写 `work/normalized.jsonl` +
   `work/case_summary.json`。
2. **（脚本化）尽早搭骨架**：`finalize` 前所有中间产物落盘；即使流程中断，
   work 目录中已有诚实部分结果。
3. **（脚本化）提取状态信号**：`scan` 逐记录提取撤回/勘误/EoC/图状态/preprint
   信号，每条信号带原因码（见 `references/status-vocabulary.md`）与证据定位符，
   并派生"被撤回目标"等反向信号。写 `work/status_signals.jsonl`。
4. **（脚本化）preprint↔VoR 配对**：`pair` 先用显式关系链接
   （is-preprint-of / has-preprint）自动配对；书目学回退（标题+第一作者姓氏+
   年份±1）只进 `pending_review`，**绝不自动配对**。写 `work/version_pairs.json`。
5. **（脚本化）import_state 对账**：`reconcile` 将声称已导入但所有在场响应均
   缺席的标识符判 `import_inconsistent`（隔离该声明并报告）；import_state 标记
   withdrawn 的条目确保排除出候选池并注明原因；响应存在但 import_state 未知
   的记录记 `not_yet_imported`（信息性）。写 `work/reconcile.json`。
6. **（模型判断，一次性批量）**：模型阅读 `status_report` 初稿/台账摘要后，
   在**一次批量请求**内复核全部 flagged（及待审版本对），撰写
   `dispositions.json`：每条含 `record_id`、`disposition`（
   `exclude_as_retracted` / `keep_with_notice` / `keep_clean` /
   `merge_version_pair` / `split_not_same`）与**必填 rationale（≥10 字符）**；
   交由 `adjudicate` 校验模式并应用（无效条目被拒绝并如实报告，退出码 2）。
7. **（脚本化）定稿**：`finalize` 生成 `status_ledger.json`（逐记录
   status_class clean/flagged/severe/unverifiable + 信号 + 配对归属 + 最终处置）、
   `status_report.md`（severe/flagged 表格含证据定位符、unverifiable 清单、计数）、
   `candidate_pool.json`（状态清洗后候选，版本对已折叠）、`result.json`。
8. **（脚本化+模型复核）自查**：`selfcheck` 校验契约键齐全、每条 severe/flagged
   记录至少 1 个证据定位符、计数可重算、候选池无任何 severe 记录、无沉默丢弃；
   模型最后通读 `status_report.md` 与 `result.json`，在最终答复中如实转述全部
   uncertainty。

端到端等价命令（模型第 6 步的裁定文件经 `--dispositions` 传入）：

```bash
python3 /skills/weekly-skill/scripts/status_hygiene.py run-all \
  --input /input --work /app/work --output /app/output \
  --dispositions /app/work/dispositions.json
```

也可逐子命令执行：`parse → scan → pair → reconcile → adjudicate → finalize →
selfcheck`，中间产物均在 `--work` 目录接力。

## 输出合同映射表

| output_contract 字段（示例） | 填充来源 |
|---|---|
| `status_ledger` | `status_ledger.json`（逐记录台账） |
| `candidate_pool` | `candidate_pool.json`（版本对已折叠，一项研究计一次） |
| `retraction_exclusions` | 台账中全部 severe 记录的 id + 原因码列表 |
| `version_pairs` | `version_pairs.json`（显式对 + 待审队列 + 归并规则） |
| `import_reconciliation` | `reconcile.json` 摘要（inconsistent / withdrawn_excluded / not_yet_imported） |
| `status_summary` | `counts` 对象 |
| 其它任何字段（如 `curator_comment`） | 无法诚实填写 → `null` + 列入 `unresolved_contract_fields` |

未知字段名一律走最后一行规则。字段名与上表不一致时按语义就近映射，映射不了
就诚实置 null。

## 异常处理表

| 异常 | 行为 | 退出码 |
|---|---|---|
| case.json 缺失/不可解析/非对象 | stderr 说明后终止 | 3 |
| 无任何材料 / normalized 记录为 0 时执行 scan | 拒绝出具"干净"结论，报错 | 2 |
| case.json 引用的材料磁盘缺失 | 该材料记入 `missing_materials` 与 uncertainty，继续 | 0 |
| 材料无法分类（unknown） | 不产出记录但如实登记 `unknown_materials`，绝不沉默丢弃 | 0 |
| 无 import_state 材料 | 对账空操作并显式声明"无导入状态可核对" | 0 |
| 无 reference_graph 材料 | 图类信号缺省，继续 | 0 |
| dispositions.json 缺失/非 JSON/模式错误 | 拒绝条目逐条报告；run-all 中继续用已应用子集并降级 | 2 |
| 未提供 --dispositions | flagged 记录保持 `pending_model_review`，status=partial | 0 |
| selfcheck 任一检查失败 | 打印 FAIL 明细；run-all 以 1 收场，产物标记不可信 | 1 |
| 未预期内部异常 | 顶层捕获，写出降级 result.json（status=degraded） | 2 |

## 合成最小示例

`examples/synthetic-input/`（case_id `synthetic-status-hyg-001`）含 11 条虚构记录，
埋设全部典型缺陷：撤回通告 + 被撤回原文（Crossref relation is-retraction-of +
update-to）、EuropePMC `Retraction of Publication`、出版商 `expression_of_concern`、
引用图 withdrawn 节点（与出版商 published 冲突）、preprint↔VoR 双向显式关系、
import_state 中 1 个 absent-but-claimed 标识符与 1 个 withdrawn 条目、1 条无任何
状态面的 unverifiable 记录。`examples/synthetic-output/` 为脚本真实运行的产物
（模型裁定步骤由人工手写 `dispositions.json` 代替），复现命令与真实退出码见
`examples/synthetic-output/run-record.md`。

## 诚实声明

- 本技能**不证明**任何记录"在真实世界中未被撤回"——离线材料之外的状态无从
  核验；`clean` 的语义仅为"材料内所有状态承载面均无不良信号"。
- `unverifiable` 记录被挡在候选池之外是**有意为之**的保守选择，其清单完整
  出现在报告与 result.json 的 uncertainty 中，供人工补证后回收。
- 排除、折叠、保留附注意等每一个改变候选集的动作都登记在
  `result.json.change_records` 中，无沉默丢弃。
- 示例数据全部虚构，仅演示接口形态，**不是官方赛题答案**。
