---
name: querytrace-lineage-chain
description: >
  多数据库联合检索的多源查询编排与全链来源回溯。当案例材料包含 Crossref /
  EuropePMC / 出版商三个来源的原始响应（可能含引用图、组织方本地增量导入状态、
  组织方记录的查询台账），且任务要求审计“每个库实际执行了什么查询”并为每条
  记录建立可回链溯源时使用：从材料中提取各库真实查询式/参数/命中数/分页游标
  （以材料记录为准，未记录记 query_unrecorded，绝不臆造），做编排审计（各库
  查询是否机械复制同一条字符串的逐库 diff、items_returned×页数 vs total_hits
  的分页完整性、suspected_truncation、限流/配额痕迹分类），建立六段全链溯源
  账本（库→查询→响应文件+item 索引→逐字段 raw_pointer→去重判定→canonical
  贡献），两级精确聚类（DOI 小写化/PMID/PMCID 标识符精确 + 归一题名精确；
  模糊对一律进 unresolved 交模型仲裁，不臆断），四核验链完整性（字段可回链、
  item 全处置、台账页存在、同输入双跑重放 hash 一致），断链逐条写
  chain_gaps.jsonl 绝不静默修补，并做增量导入四类 diff（new/already_imported/
  updated/conflicting）。差异化能力：根治“查询记录靠脑补、合并结果无出处”的
  不可审计失败。边界：不联网执行真实检索（一切来自本地材料）、不做模糊去重与
  覆盖矩阵统计（那是方向 A/B 的职责）、不做全文质量评价、不预置案例答案、
  不编造 DOI/PMID/查询命中数。
---

# querytrace-lineage-chain — 多源查询编排与全链来源回溯

## 1. 适用场景与边界

**适用**：多数据库联合检索案例（`/input/case.json` + `task.md` + 三来源原始
响应材料）中需要交付：可辩护的查询台账、编排审计结论、逐字段可回链的溯源
账本、链完整性核验、增量导入 diff，以及按 output_contract 对齐的
`/app/output/result.json`。

**边界（不做什么）**：
- 全程离线：绝不声称执行任何真实联网查询；一切结论来自本地材料。某库查询
  未被材料记录时记 `query_unrecorded` 并写入 uncertainty，**绝不臆造查询串**。
- 不做模糊去重、不做覆盖矩阵统计（方向 A `identitymerge-dedup-engine`、
  方向 B `fieldatlas-coverage-audit` 的领域）；本 bundle 只做标识符精确与
  归一题名精确两级聚类，模糊对一律 `unresolved` 交模型仲裁。
- 不做全文质量评价、不绕服务限制、不预置案例答案、不编造文献元数据/DOI/
  PMID/查询命中数。
- 断链只报告不修补：核验发现的问题逐条写 `chain_gaps.jsonl`，由模型决定
  处置并留痕。

## 2. 运行环境

- 脚本全部 Python 3 标准库，位于本 skill 的 `scripts/` 下，每个脚本支持
  `--help`。
- 定位兜底（安装路径不确定时）：
  `find / -maxdepth 6 -name "query_log.py" -path "*querytrace*" 2>/dev/null`
  找到后以该目录为 `$SKILL`；SKILL.md 同理可搜 `"querytrace-lineage-chain"`。
- 退出码约定：**0=通过；2=输入/材料不足（诚实降级）；3=校验失败（断链/
  规则违反/输入非法）**。任何脚本顶层异常一律捕获汇总并以 exit 2 降级，
  绝不 crash 留 traceback。

## 3. 工作流程（编号步骤；64 请求 / 900s 预算适配）

预算原则：**步骤 0–2 先把脚手架落盘**（防超时零交付），重活全部脚本化，
模型只在 4 / 8 / 9 做判断与仲裁。任何一步中断后均可从该步幂等重跑。

0. **读案例（模型）**：通读 `/input/case.json` 与 `/input/task.md`。
1. **解析（脚本）**：`python3 $SKILL/scripts/parse_case.py --case /input/case.json
   --task /input/task.md --materials-dir /input --out /app/work/case_summary.json`
   —— 发现材料、嗅探归类（crossref/europepmc/publisher/recordlist/jsonl/csv/
   reference_graph/import_state/query_ledger/unknown），失败逐文件留痕。
2. **保底脚手架（脚本）**：`python3 $SKILL/scripts/scaffold_result.py --summary
   /app/work/case_summary.json --out /app/output/result.json` —— 全字段占位落盘。
3. **查询台账（脚本）**：`python3 $SKILL/scripts/query_log.py --summary
   /app/work/case_summary.json --work /app/work` → `query_ledger.jsonl` +
   `query_audit.json`（机械复制 diff / 分页完整性 / 限流痕迹）。
4. **审计裁读 + 排除仲裁（模型）**：读 `query_audit.json` 结论（截断/机械
   复制/未记录库）；按材料内容决定不相关条目，写
   `/app/work/exclusions.json`（`{"<record_uid>": "relevance_excluded"}`，
   record_uid 规范见 `references/lineage_schema.md` §2）。
5. **溯源账本（脚本）**：`python3 $SKILL/scripts/build_lineage.py --summary
   /app/work/case_summary.json --work /app/work --exclusions
   /app/work/exclusions.json` → `lineage.jsonl` + `canonical_records.json`
   （两级精确聚类 + unresolved 模糊对）。
6. **链核验 + 重放（脚本）**：`python3 $SKILL/scripts/verify_chain.py --summary
   /app/work/case_summary.json --work /app/work --exclusions
   /app/work/exclusions.json --report /app/output/lineage_report.md`
   —— 四核验（C1–C4，内含 build_lineage 双跑 hash 比对）；exit 3 = 有断链，
   断链逐条在 `chain_gaps.jsonl`。
7. **导入 diff（脚本）**：`python3 $SKILL/scripts/import_diff.py --summary
   /app/work/case_summary.json --work /app/work` → `import_diff.json`；
   无导入状态材料时 exit 2，诚实降级（把“无导入状态，diff 未执行”写入
   result.json.status 与 uncertainty）。
8. **仲裁（模型）**：处置 `unresolved_pairs`（只可确认/否决，确认即说明依据
   写入 change_records）、处置断链（只能补登记或如实承认，不得改账本掩饰）。
9. **组装 result.json（模型）**：按第 4 节映射填充；重跑 6 若曾修改账本。
10. **自查（脚本）**：`python3 $SKILL/scripts/selfcheck`，结果记入
    `result.json.checks`。

**超时断点续跑**：步骤 2 后任意时刻中断都有可交付 result.json；重入时从
最近成功步骤的下一编号继续（脚本幂等，重跑覆盖同名产物，不覆盖已存在
result.json 骨架除非 --force）。

## 4. 输出合同映射（result.json 字段来源）

| 字段 | 来源 |
|---|---|
| case_id | case_summary.json |
| skill_name | 固定 `querytrace-lineage-chain` |
| status | complete / partial / failed + 原因；离线、query_unrecorded、无导入状态、存在断链时 partial 并说明 |
| product | query_ledger.jsonl / query_audit.json / lineage.jsonl / canonical_records.json / chain_gaps.jsonl / import_diff.json / lineage_report.md 的路径清单 |
| sources | case_summary.materials（文件名+sniff+用途+路径） |
| uncertainty | query_unrecorded、unparsed_files、unresolved_pairs、截断/限流痕迹、task.md 取题确认项 |
| change_records | 脚手架初始化、exclusions 仲裁、unresolved 处置、断链处置 |
| counts | 材料数/来源库数/原始记录数/canonical 数/断链数/diff 四类计数 |
| checks | parse_case/query_log/build_lineage/verify_chain/import_diff/selfcheck 的 exit 码与摘要 |
| query_ledger / lineage / chain_gaps / import_diff | output_contract 常见扩展字段：对应产物路径+关键摘要 |

output_contract 中超出上表的字段：scaffold_result.py 已生成占位，按案例语义填充。

## 5. 异常处理

| 异常 | 处置 |
|---|---|
| 零材料 / case+task 均缺 | parse_case exit 2；result.json 记 failed 原因，不伪造产物 |
| 某库查询未记录 | 台账记 `query_unrecorded=true` 并写入 uncertainty；**不臆造** |
| 分页不吻合（Σ items_returned < total_hits） | 审计记 `suspected_truncation` + 估算缺失区间；写入 uncertainty |
| 各库查询逐字相同 | 审计 `mechanical_copy_confirmed`，提示应按库方言分别构造（参照 `references/db_capability_notes.md`） |
| 坏 JSON / 未知 schema | 嗅探降级 `unknown` 并逐文件留痕（unparsed_files），继续处理其余文件 |
| item 无法解析 | 丢弃原因码 `unparsed`，账本留痕 |
| 撤回痕迹 | 丢弃原因码 `withdrawn`（结构化字段与 pubType 信号） |
| 模糊相似对 | 一律 `unresolved_pairs`，交模型仲裁；**不臆断** |
| 标识符冲突（导入状态内矛盾版本） | import_diff 归 `conflicting`，列版本数；不擅断取舍 |
| 断链（指针失效/值不符/item 未处置/页缺失/重放不一致） | verify_chain exit 3，逐条写 chain_gaps.jsonl；**不得静默修补** |
| 无导入状态材料 | import_diff exit 2 诚实降级，如实声明 |
| 超时 | 步骤 2 已保底骨架；任意中断点有可交付 result.json + 已完成产物 |

## 6. 自查方法（selfcheck）

```bash
python3 $SKILL/scripts/selfcheck    # 或 chmod +x 后直接执行
```

跑 `examples/` 下合成示例（**示例数据，非真实案例**）。断言：正例全链路
exit 0（已知重复对并入同一 canonical、Tier1/Tier2 依据正确、每字段
raw_pointer 可解析、丢弃 item 均有合法原因码、分页截断被识别、publisher
记 query_unrecorded、重放 hash 一致）；负例（人为删掉 raw_pointer →
verify_chain exit 3 且 chain_gaps.jsonl 含断链）；降级例（无导入状态 →
import_diff exit 2）；健壮例（坏 JSON → 降级 unknown 留痕不 crash）；并对
全部脚本 py_compile。任一断言失败 exit 3。

## 7. 最小调用示例

```bash
SKILL=$(dirname $(dirname $(find / -maxdepth 6 -name "query_log.py" -path "*querytrace*" 2>/dev/null | head -1)))
mkdir -p /app/work /app/output
python3 $SKILL/scripts/parse_case.py --case /input/case.json --task /input/task.md \
    --materials-dir /input --out /app/work/case_summary.json
python3 $SKILL/scripts/scaffold_result.py --summary /app/work/case_summary.json \
    --out /app/output/result.json
python3 $SKILL/scripts/query_log.py --summary /app/work/case_summary.json --work /app/work
# （模型写出 /app/work/exclusions.json 后；无排除可省略 --exclusions）
python3 $SKILL/scripts/build_lineage.py --summary /app/work/case_summary.json \
    --work /app/work --exclusions /app/work/exclusions.json
python3 $SKILL/scripts/verify_chain.py --summary /app/work/case_summary.json \
    --work /app/work --exclusions /app/work/exclusions.json \
    --report /app/output/lineage_report.md --import-diff /app/work/import_diff.json
python3 $SKILL/scripts/import_diff.py --summary /app/work/case_summary.json --work /app/work
python3 $SKILL/scripts/selfcheck
```

（上述产物均为按案例材料生成的运行时输出；`examples/lineage_report.example.md`
为合成示例数据的渲染结果，属示例输出，非真实案例结果。）

## 附录 A：exclusions.json（模型仲裁输入）

```json
{"crossref:raw_crossref_page1.json:item[3]": "relevance_excluded"}
```

record_uid 规范：`{source_db}:{response_file}:item[{index}]`（见
`references/lineage_schema.md` §2）；原因码合法集：duplicate_of /
relevance_excluded / unparsed / withdrawn（§5）。
