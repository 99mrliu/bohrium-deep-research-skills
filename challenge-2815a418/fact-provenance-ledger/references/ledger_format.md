# 台账 schema 与 ground_guard 判定规则（ledger_format）

## facts.jsonl schema

每行一个 JSON 对象：

```json
{
  "id": "F0001",
  "kind": "number | term | citation | claim",
  "surface": "88.2%",
  "unit": "%",
  "source": {
    "file": "materials/manuscript-baseline.md",
    "heading": "Results",
    "paragraph_index": 4,
    "quote": "……首圈库仑效率达 88.2%，循环 200 周后……"
  }
}
```

约束：
- `surface` 必须能在 `source.quote` 中逐字找到（claim 的 surface 即整段截断文本）。
- `unit` 可空（null）。`mAh g-1` 这类单位的 `-1` 是单位一部分，不会被识别成数字。
- 数字形态覆盖：`92–95`（区间，端点 92/95 另立条目）、`88.2%`、`1.5×10^-3`、`1.5e-3`、普通整数/小数。
- case.json 形状的 JSON（含 case_id / output_contract / result 字段）自动排除，不入台账。
- `paragraph_index` 从 1 开始，按空行分段；`heading` 为该段之前最近的 markdown 标题，无则 null。

## ground_guard 判定规则

对草稿全文（先剥离 `<!-- CHG-xx begin/end -->` 标记）：

1. **数字 token**：与台账中所有 number 事实的 surface（含区间端点）做字符串匹配（`88.2%` 与台账 `88.2%` 命中；单写 `88.2` 也命中，因匹配时剥尾部 `%`）。不命中且不在白名单 → `material_external`。
2. **引号论断**（“…”/「…」/"…"，4–120 字符）：必须是台账某条 quote 或 claim surface 的**子串**，否则 → `material_external`。
3. **默认豁免**（不计违规）：第 N 条/款/节、图 N、表 N、Figure N、Table N、Reviewer N、审稿人 N、意见 N、CHG-xx、F0001 编号、案例 id 形态（SYNTH-… 等）。

输出 ground_report.json：

```json
{
  "drafts": ["..."],
  "facts": "facts.jsonl",
  "tokens_checked": 57,
  "material_external_count": 2,
  "status": "pass | violations_found",
  "issues": [{"file": "...", "token": "97.5%", "type": "material_external",
              "detail": "数字不在 facts.jsonl 且不在白名单", "context": "……"}]
}
```

`--strict` 时 material_external_count > 0 即 exit 1。

## 白名单写法

每行一条，`#` 开头为注释：

```
# 字面字符串
CHG-01
2024-05-01
# 正则（re: 前缀）
re:^\d{4}-\d{2}-\d{2}$
re:^第[一二三四五六七八九十]+轮$
```

适用对象：日期、轮次编号、与案例编号相关的合法 token。**不得**用白名单豁免材料外的实验数值——那属于伪造。
