# extraction-schema.md — extractions.jsonl 行格式与抽取规则

本文件定义模型需要写的**唯一**工件 `/app/work/extractions.jsonl` 的格式。
每行一个 JSON 对象；以 `#` 开头的行和空行被跳过；解析失败的行被拒绝并记录
（`MALFORMED_JSON`），不影响其余行。所有示例均来自 SYNTHETIC 合成示例，非真实论文。

## 1. 操作总览

| op | 必填字段 | 可选字段 | 证据要求 |
|---|---|---|---|
| `node` | `id`, `type`, `label` | `aliases`, `qualifiers`, `evidence` | ≥1 条（强制） |
| `edge` | `id`, `source`, `target`, `relation` | `qualifiers`, `evidence` | ≥1 条（强制） |
| `merge` | `keep`, `drop`, `key`, `reason` | `evidence` | 可选，有则校验 |
| `nonmerge` | `a`, `b`, `reason` | `key`, `evidence` | 可选，有则校验 |
| `unreported` | `item` | `context`, `evidence` | 可选，有则校验 |
| `note` | `text` | `evidence` | 可选，有则校验 |

## 2. 证据对象（evidence）

```json
{"source_id": "S1", "paragraph_id": "s1p07", "quote": "a PCE of 21.1%"}
```

- `source_id` / `paragraph_id` 必须在语料中真实存在（组织者的 JATS 段落 ID；本包没有
  PDF 页码，绝不编造页码）。
- `quote` 必须是该段落 `text` 的**精确子串**（逐字，含大小写与标点）。`verify` 阶段
  机械校验；渲染阶段 `evidence_index.json` 再校验一次。
- 一条 node/edge 可挂多条证据（跨篇时鼓励）。

## 3. 实体类型（entity types）

建议封闭集合（未知类型不会被拒绝，但会在图中排到最后一列）：

`researcher`（研究者）/ `material`（材料）/ `method`（方法）/ `task`（任务）/
`metric`（指标）/ `condition`（条件）/ `sample`（样品/器件实例）/ `dataset`（数据集）/
`claim`（数值或论断性主张）/ `note`（其他）。

要点：
- **物理样品/器件**（"champion device"）与**材料类别**（"MAPbI3"）是不同的节点类型；
  同一通用材料术语跨篇 ≠ 同一物理样品。
- 数值主张建为 `claim` 节点，`qualifiers` 里带 `{"value": "...", "metric": "..."}`，
  并用 `concerns`（→metric）、`under`（→condition）、`about`（→sample）三类边定位；
  这样不同条件下的冲突数值自然成为不同 claim 节点，被保留而非合并。

## 4. 关系词汇表（relation vocabulary）

| relation | 方向（source → target） | 说明 |
|---|---|---|
| `uses` | sample/method → material | 样品或方法使用了某材料 |
| `fabricated-by` | sample/material → method | 由某方法制备 |
| `measures` | method → metric | 方法测量某指标 |
| `about` | claim → sample | 主张关于哪个样品 |
| `concerns` | claim → metric | 主张关于哪个指标（数值进 claim 的 qualifiers.value） |
| `under` | claim → condition | 主张成立的实验条件 |
| `outperforms` | claim → claim | 同条件下一条主张优于另一条 |
| `supports` | claim → claim | 证据主张支持解释性主张 |
| `contradicts` | claim → claim | 直接矛盾（慎用；数值不同但条件不同 ≠ 矛盾，应各自保留） |
| `degrades-into` | material → material | 降解/转化为 |
| `reviews-cites` | claim → 任意 | **综述转述/二手引用**：明确区别于直接证据（连得对） |
| `aliases` | — | 不要用边表示别名；用 `merge` 操作 |

## 5. 合并纪律（对得齐）

- `merge`：跨篇别名合并。`keep` 保留、`drop` 被并入（其证据、别名、边全部转移），
  必须给出归一化键 `key`（大小写折叠 + 去连字符/空格）与一句话 `reason`。
  例（SYNTHETIC）：S1 "methylammonium lead iodide (MAPbI3)" 与 S2 "MAPbI3" →
  `{"op":"merge","keep":"N01","drop":"N02","key":"mapbi3","reason":"..."}`。
- `nonmerge`：同名不同物的显式记录。例（SYNTHETIC）：两篇都出现 "TiO2"，但 S1 是
  致密电子传输层、S2 是介孔支架 → 显式 `nonmerge`，键 `tio2`，理由引用原文。
- 不同条件/样品/数值绝不合并成一条结论；冲突数值各自是独立 claim，
  构建阶段自动以 `resolution="preserved"` 记入 conflicts。
- 拿不准的合并：不要合，写 `note` 说明。

## 6. 未报告与备注

- `unreported`：文中明确未测/未报的项（如滞后指数），`context` 写明情况，
  证据指向"未测量"的原句。
- `note`：归属提醒（如 case.json 根元数据只属于 primary）、综述转述提醒等。

## 7. 校验拒绝原因码

`MALFORMED_JSON` / `UNKNOWN_OP` / `MISSING_FIELD` / `EMPTY_EVIDENCE` /
`ADDRESS_NOT_FOUND`（段落不存在）/ `QUOTE_NOT_SUBSTRING`（引文非精确子串）/
`DUPLICATE_ID` / `DANGLING_ENDPOINT`（引用了未定义节点）。
被拒绝的行进入 `verification_report.json` 的 `rejected` 列表；修复方式：改写该行后
重跑 `verify` 及后续阶段即可（幂等）。
