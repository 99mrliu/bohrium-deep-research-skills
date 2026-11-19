---
name: kbqa-library-cartography
description: 科研知识库问答的"编目驱动"工作流——先对混乱文档库做确定性修复：哈希盘点、精确/近似去重、别名归并、版本链重建（行政版本备注优先）、权限审计与修复台账全部机器留痕；问答阶段只允许从编目中标为"当前版本且可读"的条目取证，每条答案回链到编目坐标，使整库的组织结果与问答记录可被第三方复跑核对。Use when a task asks to repair/organize a messy scientific document library with duplicates, aliases, version notes, metadata and permission issues, and answer questions over the organized library (资料管理, 编目, 版本谱系, 去重, 别名, 修复台账, 元数据, /input/case.json, result.json).
---

# 编目驱动的资料修复与问答（kbqa-library-cartography）

## 何时使用

平台给出 `/input/case.json` + `/input/task.md`，其中是一个**待修复的科研文档库**：文件跨目录、多格式、含重复副本与历史版本、可能有别名（同一文献不同文件名）与行政版本备注（如"以 v3 为准"），可能附元数据文件；任务要求整理库并回答检索/问答问题。结果写入 `/app/output`，`result.json` 必须含 `case_id`、`output_contract` 全部字段，以及诚实的 `status` / `sources` / `uncertainty` / `change_log`。

本 Skill 的增益在库侧：所有整理结论（重复组、别名组、版本链、跳过与冲突）都由确定性脚本从文件字节与文本内容推导，任何人用同一输入可复跑出同一编目；问答建立在修复后的编目之上，天然排除"引用了已被废止版本"的错误。

## 运行方式（五步）

```bash
SKILL=/skills/weekly-skill

# 1) 盘点：逐文件哈希、类型、权限、文本抽取状态（先落 partial result.json 检查点）
python3 $SKILL/scripts/lib_inventory.py --input /input --work /app/work --out /app/output

# 2) 谱系：精确去重 + 近似去重 + 别名归并 + 版本链重建（读行政版本备注）
python3 $SKILL/scripts/lib_lineage.py --work /app/work --out /app/output

# 3) 编目：合并盘点、谱系与元数据，产出交付级 catalog.json 与修复台账
python3 $SKILL/scripts/lib_catalog.py --input /input --work /app/work --out /app/output

# 4) 问答：只对 catalog 中 current_version=true 且 readable=true 的条目检索取证；
#    每条答案的引用坐标为 catalog 的 entry_id + 行号（见 resources/catalog_schema.md）。

# 5) 收尾：按 output_contract 组装 result.json（status/uncertainty/change_log 诚实填写）
python3 $SKILL/scripts/lib_finalize.py --case /input/case.json --work /app/work --out /app/output
```

## 六维编目要求

`catalog.json` 必须覆盖：文件类型（type 分布）、元数据字段（来自元数据文件与文件名解析，缺字段记 null 不编造）、目录层级（原始路径树与修复后归档树）、重复文件（exact/near 重复组与保留决策）、版本差异（版本链、当前版本标记、差异说明）、权限与来源（readable 标志、skipped 清单与原因）。任一维度无数据时写空结构并在 `uncertainty` 说明，不得省略维度。

## 修复纪律（硬规则）

1. **绝不删除输入文件**；修复只产出台账与编目，物理整理（如需移动）只记方案不执行，除非任务说明明确要求。
2. 版本链排序优先级：行政版本备注（显式"以X为准"）> 文件名版本号（v1/v2/2023）> 修改时间。三者冲突时全部记录，当前版本按优先级取最高者，冲突写入 `version_conflicts`。
3. 别名归并只合并**内容证据**支持的组（同哈希或近似度 ≥0.85）；仅名字相似不合并。
4. 近似去重阈值 0.6（shingle Jaccard）；0.6–0.85 的组标记为"相关但非副本"，合并到版本链而非别名组。
5. 无法判断的记录写 `status=undecidable` 与原因，不猜。

## 问答取证规则

- 检索只在 `current_version=true` 且 `readable=true` 的编目条目上进行；若任务明确要求查历史版本，必须同时声明所引版本与当前版本的关系。
- 答案引用格式：`[E03|sha8|L12-L14]"逐字引文"`，E03 为 catalog entry_id。
- 问题在库中无证据时写"库中无依据"，并引用编目说明缺什么（缺哪类文件/字段）。
- 两个编目条目对同一事实给出不同值时，并列引用两者，注明所属版本链，不擅自取舍。

## 预算与异常

预算约 64 次请求、900 秒。第 1–3 步是确定性脚本；模型预算用于读题、复核谱系脚本报告（特别是 `needs_review` 组）、取证与作答。预算过半立即跑第 5 步交付 partial。

异常：目录为空→catalog 空结构 + partial；版本备注与内容矛盾→记录冲突、以实际内容为准；元数据文件不可解析→记 skipped 并继续；PDF 无文本层→记 `text_unavailable`，该条目只入编目不参与问答。

## 自查清单

1. catalog.json 六维齐全？每个文件都恰好属于一个组（独立/重复组/版本链/别名组）？
2. 每组保留决策都有确定性依据（哈希/相似度/备注）且写入台账？
3. 所有 skipped/conflict 都有原因与恢复建议？
4. 问答引用全部指向 current_version 条目？
5. result.json 契约字段齐全、status 诚实？

最小调用示例见 [examples/minimal_example.md](examples/minimal_example.md)（虚构示意，非正式案例结果）。
