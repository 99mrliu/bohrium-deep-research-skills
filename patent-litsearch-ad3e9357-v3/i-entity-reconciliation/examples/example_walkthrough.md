# Example Walkthrough — 合成示例 / 示意输出

> **合成示例**:本页所有数据均来自 `examples/fixtures/` 下的合成夹具(非真实专利/论文)。
> 下列 JSON 为对真实运行输出做删减后的**示意输出**(省略重复字段,以 `…` 标注)。

## 场景

两条合成专利记录、一篇合成对比论文:

- `rec_IX1001.txt` — Applicant: `Acme, Inc.`;Inventors: `Zhang Wei; Priya Nair`
- `rec_IX1002.txt` — Applicant: `Globex Ltd.`;Inventors: `Wei Zhang; Sara Kim`
- `paper_PX2001.txt` — Authors: `Wei Zhang; P. Nair`;Affiliation: `ACME Incorporated Research Lab`

实体清单:`entities_patent.json`(6 条)、`entities_paper.json`(3 条);
策略:`match_policy.json`(high=0.9, low=0.2)。

## 命令

```bash
W=$(mktemp -d)
python3 scripts/name_norm.py --suffix-table references/legal_suffix_table.json \
  --input examples/fixtures/entities_patent.json --output $W/entities_patent_norm.json
python3 scripts/name_norm.py --suffix-table references/legal_suffix_table.json \
  --input examples/fixtures/entities_paper.json  --output $W/entities_paper_norm.json
python3 scripts/entity_match.py \
  --left $W/entities_patent_norm.json --right $W/entities_paper_norm.json \
  --policy examples/fixtures/match_policy.json --output $W/match_report.json
python3 scripts/cross_ledger.py \
  --left $W/entities_patent_norm.json --right $W/entities_paper_norm.json \
  --left-sources examples/fixtures/rec_IX1001.txt examples/fixtures/rec_IX1002.txt \
  --right-sources examples/fixtures/paper_PX2001.txt \
  --policy examples/fixtures/match_policy.json --output $W/ledger.json
```

控制台摘要(示意):

```
normalized 6 name(s) -> .../entities_patent_norm.json
normalized 3 name(s) -> .../entities_paper_norm.json
auto=1 candidate_groups=3 non_match=2 pairs_scored=4 -> .../match_report.json
ledger rows=6 auto=1 candidate=3 non_match=2 -> .../ledger.json
```

## 第 1 步:规范化留痕(示意输出)

`entities_patent_norm.json` 节选:

```json
{
  "raw": "Acme, Inc.",
  "normalized": "acme inc",
  "applied_rules": [
    {"rule": "R2", "raw": "Acme, Inc.", "normalized": "acme, inc."},
    {"rule": "R3", "raw": "acme, inc.", "normalized": "acme inc"}
  ],
  "kind": "org", "basis": "legal suffix canonical 'inc' present",
  "tokens": ["acme", "inc"], "core": "acme", "canonical_suffix": "inc", …
}
```

`entities_paper_norm.json` 节选:

```json
{
  "raw": "ACME Incorporated Research Lab",
  "normalized": "acme inc research lab",
  "applied_rules": [
    {"rule": "R2", "raw": "ACME Incorporated Research Lab", "normalized": "acme incorporated research lab"},
    {"rule": "R4", "raw": "acme incorporated research lab", "normalized": "acme inc research lab"}
  ],
  "kind": "org", "canonical_suffix": "inc", "core": "acme research lab", …
}
```

## 第 2 步:三档匹配(示意输出)

`match_report.json` 要点:

- **auto(1 对)**:`Wei Zhang`(IX1002 发明人)≡ `Wei Zhang`(PX2001 作者),score=1.0
  (exact_norm 饱和),五维特征全 1.0。
- **candidate(3 组)**:
  1. `Acme, Inc.` ↔ `ACME Incorporated Research Lab`,score=0.2
     (core_containment=1.0, token_jaccard=0.5)——实验室 ≠ 公司本体,留人审;
  2. `Zhang Wei` ↔ `Wei Zhang`,score=0.25,flags=`["order_variant"]`——
     语序变体,**强制 candidate,绝不 auto**;
  3. `Priya Nair` ↔ `P. Nair`,score=0.2333
     (initial_surname=1.0, token_jaccard≈0.333)——首字母形式,留人审。
- **non_match(2 条)**:`Globex Ltd.`、`Sara Kim`(论文侧无对应实体)。

```json
"candidate_pairs": [
  {"left": {"raw": "Zhang Wei", "kind": "person", …},
   "alternatives": [
     {"right": {"raw": "Wei Zhang", …}, "score": 0.25,
      "features": {"exact_norm": 0.0, "core_eq": 0.0, "core_containment": 1.0,
                   "token_jaccard": 1.0, "initial_surname": 0.0},
      "flags": ["order_variant"]}]},
  …
],
"statistics": {"left_count": 6, "right_count": 3, "pairs_scored": 4,
               "auto_count": 1, "candidate_left_count": 3, "non_match_count": 2}
```

## 第 3 步:跨源重叠对账表(示意输出)

`ledger.json` 每个专利实体一行。auto 行(锚点 sha256 等以实际运行为准):

```json
{
  "entity_id": "IX1002-INV-1", "entity_raw": "Wei Zhang", "role": "inventor",
  "band": "auto", "confidence": "auto",
  "matched_counterpart_raw": "Wei Zhang", "score": 1.0,
  "flags": [], "requires_review": false,
  "anchors": {
    "left":  {"path": ".../rec_IX1002.txt", "sha256": "…", "span": [156, 165], "quote": "Wei Zhang"},
    "right": {"path": ".../paper_PX2001.txt", "sha256": "…", "span": [139, 148], "quote": "Wei Zhang"}
  }
}
```

candidate 行(order-variant,注意 `requires_review` 与全量 `alternatives`):

```json
{
  "entity_id": "IX1001-INV-1", "entity_raw": "Zhang Wei",
  "band": "candidate", "requires_review": true,
  "matched_counterpart_raw": "Wei Zhang", "score": 0.25,
  "flags": ["order_variant"],
  "alternatives": [{"counterpart_raw": "Wei Zhang", "score": 0.25,
                    "features": {…}, "flags": ["order_variant"]}],
  "anchors": {
    "left":  {"path": ".../rec_IX1001.txt", "span": [173, 182], "quote": "Zhang Wei", "sha256": "…"},
    "right": {"path": ".../paper_PX2001.txt", "span": [139, 148], "quote": "Wei Zhang", "sha256": "…"}
  }
}
```

non-match 行(缺失一侧保持 `null`,绝不推断):

```json
{
  "entity_id": "IX1002-APP", "entity_raw": "Globex Ltd.",
  "band": "non_match", "matched_counterpart_raw": null,
  "score": null, "features": null,
  "anchors": {"left": {"path": ".../rec_IX1002.txt", "span": [133, 144],
                       "quote": "Globex Ltd.", "sha256": "…"},
              "right": null}
}
```

## 验证锚点

任一锚点满足:重新计算 `sha256(文件字节)` 相等,且源文件文本的 `span` 切片逐字等于
`quote`。`scripts/selfcheck.py` 内置正向断言与"伪造 quote 必失败"的反向断言。
