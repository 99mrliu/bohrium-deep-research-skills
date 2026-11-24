# 合并策略（merge-policy.md）

T1/T2（及经裁决的 T3）合并边构成连通分量，每个分量产出一条规范记录（canonical record）。
合并是**确定性**的：同一输入必得同一输出，可回放、可复查。

## 字段级来源优先级

默认优先级：**publisher > crossref > europepmc**。逐字段取值时，从分量成员中收集该字段的
全部非空候选值，按 (来源优先级名次, 记录 id) 升序排序，取第一名为规范值。

可在下方 `priority-json` 代码块中按字段覆盖（脚本启动时自动解析本文件；
解析失败或缺失时回退默认表）。键 `"default"` 必填语义上的兜底，其余键为字段名
（`doi, pmid, pmcid, title, year, authors, journal, volume, issue, pages, abstract, url`）。

```priority-json
{"default": ["publisher", "crossref", "europepmc"]}
```

## 溯源（provenance）

规范记录的每个字段都记录取值来源：

```json
{"db": "publisher", "artifact_id": "publisher_articles.json", "locator": "[0]"}
```

`locator` 为原始 artifact 内的定位符：Crossref 为 `message.items[i]`，EuropePMC 为
`resultList.result[i]`，publisher 数组为 `[i]`，JSONL 为 `line N`。

## 冲突记录（conflict_log.json）

同一字段在不同来源存在**不同的**非空值时，产生一条冲突记录：

```json
{
  "canonical_members": ["rec-0001", "rec-0007"],
  "field": "pages",
  "values": [{"db": "...", "artifact_id": "...", "locator": "...", "value": "..."}],
  "chosen": {"db": "publisher", "value": "..."},
  "rule": "source_priority:publisher>crossref>europepmc"
}
```

- 规则恒为来源优先级；同库多记录并列时以记录 id 升序为决胜（仍是确定性的）。
- `missing` / `unknown` / `not_provided` 状态的空值不参与冲突判定（空不算分歧）。
- 冲突不被"解决"抹除：被选中值进入规范记录，落选值永久保留在冲突日志中。

## 规范记录排序

规范记录按 **(规范化 DOI, 否则规范化标题)** 升序排列后赋 `canon-NNNN` 编号，
保证输出稳定、字节级可复现。

## 仲裁纪律

T3 模糊候选**绝不**进入合并边；只有 `--adjudications` 显式判 `merge` 的对才参与合并，
且决策行以 `T3_ADJUDICATED_MERGE` 标记并保留 rationale。无裁决时 T3 对双方各自成为
独立规范记录，`status=partial`，`uncertainty` 显式列出待仲裁对——绝不静默。
