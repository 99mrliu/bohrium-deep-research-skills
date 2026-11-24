# 基准协议：缺陷类型、评分定义与协议校准

## 基准构成（全部为合成文本，非正式案例）

| 论文 | 植入缺陷 | 考察面 |
|-|-|-|
| p1 | P1-D1 显著无统计；P1-D2 试点+小样本配"证明…一半"；P1-D3 摘要"确定性方案" | 结论超出数据 |
| p2 | P2-D1 摘要 98% vs 结果 87%；P2-D2 摘要 60% vs 结果约 29%；P2-D3 承诺动力学模型未交付 | 跨章一致性 |
| p3 | 无（干净对照） | 误报率 |

key.json 的 `expect` 字段写明每条缺陷的标准判断，用于校准协议，不是唯一
表述——finding 的 quote 或 basis 含 `quote_contains` 片段即命中。

## 评分定义

- 命中（hit）：一条 finding 匹配一条缺陷，一对一配对。
- 召回 recall = 命中缺陷数 / 缺陷总数；p3 无缺陷时：零 finding 记 1.0，
  有 finding 记 0.0 且全部计 false_alarm。
- 精确 precision = 命中数 / finding 总数。
- verbatim_violations：quote 非基准论文逐字子串的 finding——机制性拦截
  "凭印象引用"。
- 稳定性：同一论文相邻两次运行的 hits 与 false_alarms 完全一致 → STABLE，
  否则 DRIFT。DRIFT 说明审查流程不可复跑，需找出随机环节。

## 协议校准方法（recall 不达标时）

1. 对 missed 的每条缺陷读 key.json 的 expect：属于哪一型（超出数据/跨章
   不一致/承诺未交付/因果越界/显著无统计）。
2. 定位漏检原因：该型缺陷在你的审查流程里没有对应检查动作 → 补动作；
   有动作但阈值过宽 → 调阈值；quote 没写对导致没匹配 → 修 quote 习惯。
3. 对 false_alarm 归因：把哪类合法文本（对照组/假设/转述/背景句）误当
   缺陷 → 把该型写进反误报规则。
4. 修完重跑一轮；仍不达标如实写进 provenance——诚实记录优于满分记录。

## finding schema（基准与真实案例同一套）

```json
{
  "id": "F01",
  "type": "事实错误 | 证据不足 | 规范问题 | 建议 | 待复核",
  "severity": "critical | major | minor | info",
  "sentence_id": "S0003",
  "quote": "所引句子的逐字子串",
  "basis": "判断依据 + 定级三问（主结论/可修正/可复现）",
  "suggestion": "改哪句、补什么证据、强度降到什么措辞（≥15 字）"
}
```

## 在 result.json provenance 中报告基准成绩

```
provenance.bench = {
  "p1": {"recall": ..., "precision": ..., "false_alarms": ...},
  "p2": {...}, "p3": {...},
  "stability": "STABLE|DRIFT",
  "engine": "bench/1.0.0"
}
```

这组数字是"加载本 Skill 的审查有多少可信度"的可复核证据；它与平台
固定案例的评分无因果关系，不得表述为对正式成绩的预测。
