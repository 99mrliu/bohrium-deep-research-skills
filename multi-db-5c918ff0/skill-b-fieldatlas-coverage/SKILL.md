---
name: fieldatlas-coverage-audit
description: >
  多数据库联合检索案例的跨库字段标准化与覆盖缺口审计。当任务要求把
  Crossref / EuropePMC / 出版商等多来源原始记录归一到统一字段（字段卡片）、
  区分 missing / unknown / not_provided 三级缺失语义、产出库×字段覆盖矩阵、
  识别单库独有文献与系统性缺口字段、建立失败降级状态台账（零结果 / HTTP 错误 /
  限流 / schema 漂移 / 撤回标记 / 无法解析文件）、并与 organizer-local 增量
  导入状态对账（already_imported / new_candidates / conflicting_updates）时
  使用。差异化能力：以三来源字段映射表（含语义注释，如 Crossref issued vs
  published-print vs published-online 不等价、EuropePMC journalInfo 嵌套与
  authorString 解析规则）为唯一事实来源的字段标准化，覆盖结论全部可回链到
  source_path 与 raw_excerpt。边界：不联网、不做模糊去重（仅按标识符 + 归一
  题名+年份做最小必要聚类用于覆盖统计，模糊匹配属 identitymerge-dedup-engine
  方向）、不做查询编排与全链溯源（属 querytrace-lineage-chain 方向）、不做
  全文质量评价、不预置案例答案、不编造文献元数据。
---

# fieldatlas-coverage-audit — 跨库字段标准化与覆盖缺口审计

## 1. 适用场景与边界

**适用**：系统性综述类案例（`/input/case.json` + `task.md` + 本地科研材料）中
需要跨库覆盖审计的环节：把三个来源（Crossref works API、EuropePMC、出版商）
的真实响应记录归一为统一字段卡片，产出可辩护的库×字段覆盖矩阵、单库独有
文献表、系统性缺口字段表、失败降级台账与增量导入对账，并按要求组装
`/app/output/result.json`。

**边界**：
- **不联网**：全程离线，一切结论来自本地材料；不声称执行任何真实数据库查询。
- **不做模糊去重**：仅按标识符（DOI 小写 / PMID）或归一题名+年份做最小必要
  聚类用于覆盖统计；模糊相似度、作者重合度仲裁属 `identitymerge-dedup-engine`。
- **不做查询编排**：不构建/审计检索式、不做来源回溯账本；属
  `querytrace-lineage-chain`。
- **不做全文质量评价 / 偏倚评估**（下游环节）；**不预置案例答案**；不编造
  文献元数据、DOI、命中数。撤回记录单列入结果并标记，不静默剔除。
- 字段语义以 `references/field_map_*.md` 映射表为唯一事实来源；脚本实现与
  文档不一致时以文档为准并记入 change_records。

## 2. 运行环境

- 全部脚本 Python 3 标准库（argparse/json/re/csv/html，无第三方依赖），位于
  本 skill 的 `scripts/` 下。
- 定位兜底（安装路径不确定时）：
  `find / -maxdepth 5 -name "map_fields.py" -path "*fieldatlas*" 2>/dev/null`
  找到后以该目录的上一级为 `$SKILL`；SKILL.md 可按 `"fieldatlas-coverage-audit"` 搜索。
- 退出码约定：`0`=通过；`2`=输入/材料不足（诚实降级，stderr 说明原因）；
  `3`=校验失败（非法 JSON、违反规则）。每个脚本支持 `--help`。
- 工作区：`/app/work`（中间产物）、`/app/output`（result.json 等最终交付）。
- 脚本对未知 schema 鲁棒：嗅探失败降级 `unknown` 并逐文件留痕；单文件异常不
  中断流程；顶层 try/except 汇总 exit 2，绝不静默吞掉、绝不崩溃。

## 3. 工作流程（编号步骤，预算 64 请求 / 900s）

> 原则：步骤 0–2 立即脚手架落盘，重判断（语义裁决）留给模型，其余全部脚本化；
> 每步幂等可重跑，超时可断点续跑（已存在的产物直接复用，scaffold 不覆盖已填字段）。

0. **读案例**【模型】：通读 `/input/case.json` 与 `/input/task.md`，确认
   output_contract 与材料清单。
1. **解析嗅探**【脚本】：`python3 $SKILL/scripts/parse_case.py --case
   /input/case.json --task /input/task.md --out /app/work/case_summary.json`
   → 材料 sniff 归类（crossref/europepmc/publisher/recordlist/jsonl/csv/
   reference_graph/import_state/unknown）、研究问题（task.md 回退提取时置
   `needs_confirmation`）。exit 2 = 无可用材料，转第 7 步如实声明。
2. **保底脚手架**【脚本】：`python3 $SKILL/scripts/scaffold_result.py --summary
   /app/work/case_summary.json --out /app/output/result.json` → 全合同字段占位
   落盘，**此后任何中断都有可交付 result.json**。
3. **字段标准化**【脚本】：`python3 $SKILL/scripts/map_fields.py --summary
   /app/work/case_summary.json --out /app/work/field_cards.jsonl --report
   /app/work/map_report.json` → 字段卡片（status/value/source_path/raw_excerpt
   四元组）、作者两种格式统一、DOI 小写、HTML 剥离、解析告警与 drift 留痕、
   库间对账基数（返回/解析/丢弃逐条原因）。exit 2 = 无任何可映射记录。
4. **状态台账**【脚本】：`python3 $SKILL/scripts/status_ledger.py --summary
   /app/work/case_summary.json --map-report /app/work/map_report.json --cards
   /app/work/field_cards.jsonl --out /app/work/status_ledger.json
   --uncertainty-out /app/work/uncertainty_draft.json` → 分类：empty_result /
   http_error / timeout / rate_limited / schema_drift / withdrawn_retracted /
   unparsed_file / parse_drop，每类带处置（partial / uncertainty / manual_review）。
5. **增量对账**【脚本，可选】：`python3 $SKILL/scripts/import_reconcile.py
   --summary /app/work/case_summary.json --cards /app/work/field_cards.jsonl
   --out /app/work/import_reconcile.json` → 三类清单（材料无导入状态时 exit 2，
   诚实降级，result.json 记“材料不含导入状态”）。
6. **覆盖矩阵与报告**【脚本】：`python3 $SKILL/scripts/coverage_matrix.py
   --cards /app/work/field_cards.jsonl --map-report /app/work/map_report.json
   --ledger /app/work/status_ledger.json --summary /app/work/case_summary.json
   --out /app/work/coverage_matrix.json --md /app/work/coverage_report.md`
   → 矩阵、单库独有、系统性缺口、撤回单列、对账表，按模板渲染
   `templates/coverage_report.md`。
7. **组装 result.json**【模型判断 + 脚本回填】：按第 4 节映射表填充合同字段；
   将 `uncertainty_draft.json` 逐条审读（合并去重、确认是否需要人工确认项）
   写入 `uncertainty`；`status.state` 裁决：全部主链完成且无 partial 类台账条目
   → `complete`，否则 `partial` + 原因（库不可用/限流/解析丢失等）；写
   `checks`（各脚本 exit 码与摘要）与 `change_records`。重语义判断清单：
   ① 研究问题是否采信（needs_confirmation 时）；② 撤回记录是否纳入分析集
   （默认单列不纳入，人工确认）；③ 导入冲突以何者为准；④ output_contract
   与默认映射不一致时的取舍（写入 change_records）。
8. **自查**【脚本】：`python3 $SKILL/scripts/selfcheck`（见第 6 节），结果记入
   `result.json.checks.selfcheck`。

**超时断点续跑**：步骤 1–6 均为幂等文件产物；超时后从第一个缺失产物重新执行
对应步骤即可（parse_case/scaffold 会增量补键，map_fields 全量重写卡片属安全
重跑）。预算分配建议：模型请求主要用于第 0、7 步语义裁决，其余为零请求脚本步。

## 4. 输出合同映射表（result.json 字段来源）

| 字段 | 来源 |
|---|---|
| case_id | case_summary.json |
| skill_name | 固定 `fieldatlas-coverage-audit` |
| status | 模型裁决（complete/partial/failed + 原因）；存在 partial 类台账条目或脚本 exit 2 降级时不得为 complete |
| coverage_matrix | coverage_matrix.json 的 matrix（库×字段×四态计数） |
| single_source_unique | coverage_matrix.json 的 single_source_unique |
| systematic_gaps | coverage_matrix.json 的 systematic_gaps |
| status_ledger | status_ledger.json（entries + summary + disposition 词表） |
| import_reconcile | import_reconcile.json 三类清单；材料无导入状态时填 `null` 并在 uncertainty 说明 |
| sources | case_summary.materials（文件 + sniff + 用途定位） |
| uncertainty | uncertainty_draft.json（模型审读合并）+ needs_confirmation 项 |
| change_records | 脚手架初始化、字段裁决、合同取舍、版本变更 |
| checks | 各脚本 exit 码与摘要 + selfcheck 结果 |

output_contract 中超出上表的字段：scaffold_result.py 已生成占位，按案例语义
填充；与默认映射冲突时以案例 output_contract 为准并写入 change_records。
撤回记录同时在 `retracted_records`（若合同未含此键则并入 status_ledger 或
uncertainty，注明取舍）。

## 5. 异常处理表

| 异常 | 处置 |
|---|---|
| 零结果（某查询/来源） | status_ledger 记 empty_result → uncertainty；不推断文献不存在 |
| 库不可用（HTTP 错误/超时） | status_ledger 记 http_error/timeout → 该库降级 partial，status 注明，覆盖结论为下限性质 |
| 限流/配额 | status_ledger 记 rate_limited → 同 partial；不绕服务限制 |
| 字段缺失 | 按三级语义判定（§0 伪代码）：missing / unknown / not_provided 分开计数，绝不补造值 |
| 字段结构漂移 | drift 日志逐条留痕 + uncertainty；按映射表降级判定，必要时人工核对原始载荷 |
| 撤回/更正标记 | 单列入结果并置 status 标记，manual_review 确认是否纳入，不静默剔除 |
| 标识符冲突（导入对账） | conflicting_updates 单列字段 diff，人工裁决，不自动覆盖本地库 |
| 无法解析文件 | 逐名列入 unparsed_files / status_ledger(unparsed_file)；为唯一证据时该字段按缺口处理并人工确认 |
| 研究问题缺失 | parse_case 回退 task.md 提取并置 needs_confirmation；两处皆无 → exit 2，result.json 记 failed 原因 |
| 条款冲突（合同 vs 默认字段） | 以案例 output_contract 为准，取舍写入 change_records |
| 超时 | 步骤 2 已保底骨架；步骤 1–6 幂等可续跑 |

## 6. 自查方法（selfcheck）

```bash
python3 $SKILL/scripts/selfcheck    # 或 chmod +x 后直接执行
```

跑 `examples/` 下**合成示例数据**（README 已声明全部虚构，非真实案例）：
正例全链路 exit 0 并断言——覆盖矩阵数值正确、单库独有文献识别正确、系统性
缺口识别正确（license）、三级缺失语义正确（EuropePMC `authorString` 空串 →
authors=unknown；Crossref 无 abstract 键 → not_provided；journalInfo.journal
缺失 → container=missing + drift 留痕）、导入对账三类正确（already=1/new=7/
conflict=1）、retracted 标记被单列、与回归基线 coverage_matrix.example.json
一致；负例断言——空材料 → parse_case exit 2、坏 JSON 不崩溃且 sniff=unknown
逐名留痕、无导入状态 → import_reconcile exit 2；全部脚本 py_compile 通过。
任一断言失败 selfcheck 以 exit 3 结束。

## 7. 最小调用示例（示例输出，非真实案例结果）

```bash
SKILL=$(dirname $(dirname $(find / -maxdepth 5 -name "map_fields.py" -path "*fieldatlas*" 2>/dev/null | head -1)))
mkdir -p /app/work /app/output
python3 $SKILL/scripts/parse_case.py --case /input/case.json --task /input/task.md \
    --out /app/work/case_summary.json
python3 $SKILL/scripts/scaffold_result.py --summary /app/work/case_summary.json \
    --out /app/output/result.json
python3 $SKILL/scripts/map_fields.py --summary /app/work/case_summary.json \
    --out /app/work/field_cards.jsonl --report /app/work/map_report.json
python3 $SKILL/scripts/status_ledger.py --summary /app/work/case_summary.json \
    --map-report /app/work/map_report.json --cards /app/work/field_cards.jsonl \
    --out /app/work/status_ledger.json --uncertainty-out /app/work/uncertainty_draft.json
python3 $SKILL/scripts/import_reconcile.py --summary /app/work/case_summary.json \
    --cards /app/work/field_cards.jsonl --out /app/work/import_reconcile.json
python3 $SKILL/scripts/coverage_matrix.py --cards /app/work/field_cards.jsonl \
    --map-report /app/work/map_report.json --ledger /app/work/status_ledger.json \
    --summary /app/work/case_summary.json \
    --out /app/work/coverage_matrix.json --md /app/work/coverage_report.md
python3 $SKILL/scripts/selfcheck
```

典型产物（examples 合成数据上的示例输出，非真实案例结果）：19 条原始记录 →
9 篇论文；单库独有 2 篇（Crossref-only 1、EuropePMC-only 1）；系统性缺口字段
`[license]`；撤回标记 1 条单列；导入对账 already=1 / new=7 / conflict=1
（issue 1 vs 2）。字段级样例：EuropePMC 记录 `authorString: ""` →
`{status: unknown, source_path: "authorString", raw_excerpt: ""}`；Crossref 记录
→ `abstract: {status: not_provided}`（载荷级动态判定）。
