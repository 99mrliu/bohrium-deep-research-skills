# 筛选判定报告（screening_report.md）

> 本报告由脚本生成；所有计数来自 decision_ledger.jsonl 重算。

## 1. 资格标准（编译自 task.md，含原文引用）

| 标准 ID | 类型 | 定义 | task.md 原文依据 | 机器可判 | 状态 |
|---|---|---|---|---|---|
| I1 | inclusion | 研究设计为随机对照试验（RCT）；准随机/交替分配不满足。 | “研究设计必须为**随机对照试验（RCT）**” | 否（需判定） | 已确认 |
| I2 | inclusion | 研究对象为 ≥18 岁成人且诊断为慢性失眠。 | “研究对象必须为 **≥18 岁成人**且诊断为**慢性失眠**” | 否（需判定） | 已确认 |
| I3 | inclusion | 干预对比为 NX-3 对比安慰剂；仅活性对照而无安慰剂组者不满足。 | “干预对比必须为 **NX-3 对比安慰剂**” | 否（需判定） | 已确认 |
| I4 | inclusion | 结局指标包含入睡潜伏期（sleep latency / sleep onset latency）。 | “结局指标必须包含**入睡潜伏期（sleep latency / sleep onset latency）**” | 否（需判定） | 已确认 |
| E1 | exclusion | 发表年份超出 2015–2025。 | “发表年份须在 **2015–2025** 之间，超出者排除。” | 是（year_range） | 已确认 |
| E2 | exclusion | 文献类型为综述、社论或会议摘要。 | “文献类型为综述（review）、社论（editorial）或会议摘要者排除。” | 是（document_type） | 已确认 |

## 2. 纳入清单（含判定理由）

- **rec-0001** rank=1 — Synthetic peptide NX-3 versus placebo for sleep latency in adults with chronic insomnia: a randomized controlled trial（2021）
  - 依据标准：I1, I2, I3, I4
  - 证据（逐字引用）：“double-blind randomized controlled trial in 124 adults (aged 18-65) with chronic insomnia”
  - 理由：双盲 RCT，成人慢性失眠，NX-3 对比安慰剂，主结局为入睡潜伏期：四条纳入标准全部满足。
- **rec-0005** rank=2 — NX-3 versus placebo on sleep onset latency in adults with chronic insomnia: a multicenter randomized controlled trial（2022）
  - 依据标准：I1, I2, I3, I4
  - 证据（逐字引用）：“randomly assigned 240 adults with chronic insomnia to NX-3 or matching placebo”
  - 理由：多中心 RCT，成人慢性失眠，NX-3 对比匹配安慰剂，主结局 sleep onset latency。
- **rec-0012** rank=3 — Bedtime administration of NX-3 versus placebo and sleep latency in adults with chronic insomnia: a randomized controlled trial（2023）
  - 依据标准：I1, I2, I3, I4
  - 证据（逐字引用）：“110 adults with chronic insomnia took NX-3 or placebo at bedtime”
  - 理由：睡前给药 RCT，成人慢性失眠，NX-3 对比安慰剂，主结局 sleep latency。
- **rec-0006** rank=4 — Effects of NX-3 versus placebo on sleep latency in older adults with chronic insomnia: a randomized controlled trial（2020）
  - 依据标准：I1, I2, I3, I4
  - 证据（逐字引用）：“randomized controlled trial, 96 older adults (aged 60-80) with chronic insomnia received NX-3 or placebo”
  - 理由：老年成人 RCT，NX-3 对比安慰剂，结局含 sleep latency。
- **rec-0009** rank=5 — NX-3 versus placebo in adults with chronic insomnia and prolonged sleep latency: a randomized controlled trial.（2024）
  - 依据标准：I1, I2, I3, I4
  - 证据（逐字引用）：“randomized controlled trial of NX-3 versus placebo”
  - 理由：成人慢性失眠且基线睡眠潜伏期 >30 分钟，NX-3 对比安慰剂 RCT，主终点 sleep latency。
- **rec-0011** rank=6 — NX-3 versus placebo and sleep quality in adults with chronic insomnia: a randomized controlled trial（2023）
  - 依据标准：I4
  - 证据（逐字引用）：“Sleep onset latency was recorded as an exploratory secondary outcome”
  - 理由：I4 要求结局指标“包含”入睡潜伏期，未限定必须为主要结局；该研究以活动记录仪测量了 sleep onset latency，判纳入。

## 3. 排除原因矩阵

| 记录 | 标题（截断） | 排除标准 | 证据 | 判定者 |
|---|---|---|---|---|
| rec-0002 | NX-3 for pediatric insomnia: a randomized placebo-control... | I2 | children aged 6-12 years | model |
| rec-0003 | NX-3 in chronic insomnia: a randomized placebo-controlled... | E1 | year=2012, required range [2015, 2025] | script |
| rec-0004 | NX-3 versus placebo in patients aged 16 to 65 with chroni... | I2 | participants aged 16 to 65 years | model |
| rec-0007 | NX-3 versus zolpidem in adults with chronic insomnia: a r... | I3 | no placebo arm was included | model |
| rec-0008 | NX-3 versus placebo for chronic insomnia: a quasi-randomi... | I1 | allocated to NX-3 or placebo by alternation | model |
| rec-0010 | Synthetic peptide NX-3 for insomnia: a narrative review o... | E2 | doc_type='Narrative Review' matches exclude_types entry 'review' | script |

## 4. 边界队列与裁定

- **rec-0004** → exclude（依据 I2）：入组年龄自 16 岁起，包含未成年人，违反 I2（≥18 岁成人）；判排除。
- **rec-0008** → exclude（依据 I1）：按交替方式分配且未隐藏分组，不是真正的随机分配，不满足 I1（RCT）；判排除。
- **rec-0011** → include（依据 I4）：I4 要求结局指标“包含”入睡潜伏期，未限定必须为主要结局；该研究以活动记录仪测量了 sleep onset latency，判纳入。

## 5. 流量计数（重算值）

| 阶段 | 计数 |
|---|---|
| 识别（各源合计） | 14 |
| — crossref | 6 |
| — europepmc | 5 |
| — publisher | 3 |
| 去重移除 | 2 |
| 初筛 | 12 |
| 排除 | 6 |
| — E1（发表年份超出 2015–2025。） | 1 |
| — E2（文献类型为综述、社论或会议摘要。） | 1 |
| — I1（研究设计为随机对照试验（RCT）；准随机/交替分配不满足。） | 1 |
| — I2（研究对象为 ≥18 岁成人且诊断为慢性失眠。） | 2 |
| — I3（干预对比为 NX-3 对比安慰剂；仅活性对照而无安慰剂组者不满足。） | 1 |
| 边界待决 | 0 |
| 纳入 | 6 |

## 6. 局限与诚实声明

- 本技能只做题录级（标题/摘要/元数据）资格判定，**不做全文质量评价**；判定证据仅限记录内文本的逐字引用。
- 去重为最小确定性规则（DOI 精确 / 标题+年份+第一作者全同），仅用于喂流量计数，不做模糊合并。
