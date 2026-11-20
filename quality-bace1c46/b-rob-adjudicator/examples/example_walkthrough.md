# 合成示例走查（示例，非正式案例结果）

> 以下文献为**虚构短文**，仅用于演示流水线各阶段产物形态。

## 输入：虚构文献 demo_rct.txt（节选）

```
A Randomized Trial of Fictivastatin in Hyperlipidemia

Methods: Patients were randomized to fictivastatin 20 mg or usual care.
The trial was open-label. The primary outcome was LDL cholesterol at 12
weeks (NCT09998888). Statistical analysis used t-tests with p<0.05.

Results: 240 patients were enrolled; 11 in the fictivastatin group and 26
in the usual-care group withdrew and were excluded from analysis. LDL at
12 weeks was significantly lower with fictivastatin (p=0.02).

Limitations: The primary endpoint was changed to LDL at 12 weeks after an
unblinded interim analysis. Data on adherence are not shown.

Funding: Funded by FictiPharma Inc. Two authors are employees of FictiPharma.
```

## 第 1–2 步：解析与领域选择

- extract：1 篇 fulltext（txt），doc_id=`demo_rct`。
- select_domains：命中 "randomized"、"open-label" → type=`rct`
  （type_hits 2 个，confident）；领域集 = 公共 3 域 + randomization /
  blinding / attrition。

## 第 3 步：双通道初评（各节选 2 条，含一处刻意分歧）

`channel_p/demo_rct.jsonl`：

```json
{"doc_id": "demo_rct", "domain": "randomization", "judgment": "insufficient", "quote": "", "locator": "", "rationale": "仅写 'Patients were randomized'，无序列生成细节。"}
{"doc_id": "demo_rct", "domain": "attrition", "judgment": "no_indication", "quote": "11 in the fictivastatin group and 26 in the usual-care group withdrew", "locator": "p1.¶3", "rationale": "已检索 Results 与 Limitations，失访数有报告。"}
```

`channel_n/demo_rct.jsonl`：

```json
{"doc_id": "demo_rct", "domain": "randomization", "judgment": "insufficient", "quote": "", "locator": "", "rationale": "未找到序列生成/分配隐藏描述。"}
{"doc_id": "demo_rct", "domain": "attrition", "judgment": "present", "quote": "11 in the fictivastatin group and 26 in the usual-care group withdrew and were excluded from analysis", "locator": "p1.¶3", "rationale": "组间失访明显不均衡（11 vs 26）且直接剔除出分析，仅完整病例分析。"}
```

## 第 4 步：裁决

- randomization：两通道一致 `insufficient` → R1，`source=agreement`。
- attrition：P=`no_indication`（有摘录） vs N=`present`（有摘录）→ 双方均有证据，
  触发 **R4 保守规则** → 取较高风险 `present`，标 `adjudicated_conservative=true`。

`adjudication_ledger.jsonl` 对应条目：

```json
{"doc_id": "demo_rct", "domain": "attrition", "type": "disagreement", "channel_p_judgment": "no_indication", "channel_n_judgment": "present", "rule_applied": "R4", "detail": "both quote-backed; conservative rule adopted higher-risk judgment present over no_indication"}
```

## 第 5 步：引用门控

两条摘录均为逐字子串 → `quote_verified=true`。若摘录被改写导致校验失败，
该域判定降级为 `insufficient` 并在 `verify_report.json.failures` 记录。

## 第 6–7 步：等级推导与 result.json 片段

映射：attrition 为核心领域且判 `present` → 命中 M1 → 整体 `high`。

```json
{
  "case_id": "demo-case",
  "status": "completed",
  "documents": [{
    "doc_id": "demo_rct", "doc_type": "rct", "grade": "fulltext",
    "domains": [
      {"domain": "attrition", "core": true, "judgment": "present",
       "quote": "11 in the fictivastatin group and 26 in the usual-care group withdrew and were excluded from analysis",
       "locator": "p1.¶3", "source": "adjudicated_R4",
       "adjudicated_conservative": true},
      {"domain": "randomization", "core": true, "judgment": "insufficient",
       "quote": "", "locator": "", "source": "agreement"}
    ],
    "overall_risk": "high",
    "overall_derivation": ["核心领域存在 present：attrition → high"]
  }]
}
```
