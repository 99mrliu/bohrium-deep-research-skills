# 证据记录结构（Bundle E）

```json
{
  "id": "p003",
  "source": "<原文段>",
  "translation": "<译文>",
  "evidence": {
    "quote": "<源文本的精确逐字子串>",
    "start": 63,
    "basis": "literal | termbase | convention | uncertain",
    "note": "译法依据（术语表条目 / 领域惯例 / 存疑点）"
  },
  "uncertainty": {"type": "unreadable", "detail": "…"}
}
```

## 核验规则

- `verified`：`source[start:start+len(quote)] == quote`。
- `offset_mismatch`：声明偏移处不匹配，但 quote 在源文本他处存在 → 多半是错锚或陈旧。
- `quote_not_found`：quote 在源文本中不存在 → 引文被改动或手误，必须修正。
- 未声明 start 时按首次出现定位（同时记录 resolved_start）。

## 覆盖分析

- 全部 verified 引文的区间并集 vs 源文本长度：缺口（gap）= 未被任何引文覆盖的非空白
  文本 → 潜在漏译，exit 2。
- 区间重叠 → overlapping（同一段被两条证据覆盖，提示重复）。

## basis 取值

| basis | 含义 | 例子 |
|-|-|-|
| literal | 直译/标题/题注 | 章节名、图题 |
| termbase | 术语表驱动 | 锁定译名首次出现给全称 |
| convention | 领域惯例 | regret 保留英文、half-life 译半衰期 |
| uncertain | 存疑译法 | 缩写义项不定；须人工确认 |
