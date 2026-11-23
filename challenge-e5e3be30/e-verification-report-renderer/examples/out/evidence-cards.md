# 证据卡片集（DEMO-E-001 合成示例）

共 3 条论断的判定卡片。判定四级枚举：supported（支持）/ partially_supported（部分支持）/ contradicted（反驳）/ insufficient_evidence（证据不足）。

## 证据卡片 C1

| 项目 | 内容 |
| --- | --- |
| 论断原文 | CsPbBr3 纳米晶在甲苯中的光致发光量子产率达到 87%。 |
| 判定 | **supported**（支持） |
| 判定理由 | 摘要逐字报告甲苯中量子产率达 87%，与论断一致；第二条证据补充发光峰位以加强定位。 |
| 不确定性 | （无） |

### 逐字证据（2 条）

| # | 引用（逐字） | 页码 | 段落 | 来源 |
| --- | --- | --- | --- | --- |
| 1 | “The photoluminescence quantum yield of the CsPbBr3 nanocrystals reached 87% in toluene” | 第 1 页 | Abstract | paper.txt p.1 |
| 2 | “the sample's emission peak was centered at 515 nm” | 第 2 页 | 3. Optical Characterization | paper.txt p.2（原文为弯引号 sample’s，演示归一化匹配） |

---

## 证据卡片 C2

| 项目 | 内容 |
| --- | --- |
| 论断原文 | 该合成反应全程在室温（25 °C）下进行，无需加热。 |
| 判定 | **contradicted**（反驳） |
| 判定理由 | 方法部分明确记载加热至 120 °C 并保温 30 分钟，与“室温、无需加热”的论断直接矛盾。 |
| 不确定性 | （无） |

### 逐字证据（1 条）

| # | 引用（逐字） | 页码 | 段落 | 来源 |
| --- | --- | --- | --- | --- |
| 1 | “The reaction mixture was heated to 120 °C and maintained at this temperature for 30 minutes” | 第 2 页 | 2. Methods | paper.txt p.2 |

---

## 证据卡片 C3

| 项目 | 内容 |
| --- | --- |
| 论断原文 | 储存 30 天后该纳米晶材料保持稳定，未发生团聚。 |
| 判定 | **partially_supported**（部分支持） |
| 判定理由 | 4.1 节的光学观测支持论断；但 4.3 节 TEM 观测到显著团聚，两处表述直接冲突，故判部分支持并并列双方原话。 |
| 不确定性 | 光学测量与电镜观察结论相反，可能因样品制备或观测条件差异导致，需作者澄清。 |

### 逐字证据（1 条）

| # | 引用（逐字） | 页码 | 段落 | 来源 |
| --- | --- | --- | --- | --- |
| 1 | “No aggregation was observed after 30 days of storage under ambient conditions” | 第 3 页 | 4.1 Shelf Storage | paper.txt p.3 |

### 冲突证据并列（双方原话，不作取舍）

冲突 1：同一篇论文内部两处表述冲突（光学 vs 电镜）

| 立场 | 引用（逐字） | 页码 | 来源 |
| --- | --- | --- | --- |
| 甲方 | “No aggregation was observed after 30 days of storage under ambient conditions” | 第 3 页 | paper.txt p.3 §4.1 |
| 乙方 | “TEM images revealed significant aggregation of the nanocrystals after 30 days of storage” | 第 3 页 | paper.txt p.3 §4.3 |

---
