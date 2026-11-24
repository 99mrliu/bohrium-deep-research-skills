# 论文质量审查报告

- case_id: `synthetic-e-001`
- status: **partial**
- accepted findings: 3；pending_review: 1；rejected: 1
- 降级原因: 存在 1 条 pending_review 待人工复核；存在命中豁免词表/类型-分面不一致的 recheck 提示

## 稿件版本（SHA-256）

- `manuscript.md` sha256=`0b572afc54b519f3cdb44d7a5fdb53e46278d455a16b6914ef99639f498c9f6a`
- `task.md` sha256=`b734479b7f7eba5dc1da5e30f1252361ba99df7102c0cbd510860a6def378736`

## 分面覆盖

| 分面 | 状态 | 说明 |
| --- | --- | --- |
| 事实核验 | issues_found | 摘要 312 与正文 318 样本量不一致，已产出 finding |
| 引用支持 | partially_checked | 2 条引用格式完整；无法联网核对文献内容真实性 |
| 方法设计 | checked_clean | RCT 设计、纳入标准、干预方案、统计方法均已交代 |
| 统计报告 | issues_found | 候选清单中相关条目因 severity 非法被 rejected，已留痕；p 值精确报告 |
| 论证链 | checked_clean | 引言-方法-结果-结论首尾呼应，局限性有讨论 |
| 学术规范 | issues_found | 缺数据可用性声明；'按期刊惯例'表述属惯例不判缺陷 |

## Findings（按分面分组、组内按严重度排序；编号稳定）

### 事实核验

#### F001 [major/事实错误] 摘要与正文样本量不一致
- 定位: `manuscript.md` § 摘要（anchor: 共纳入 312 名受试者）
- 原文: > 共纳入 312 名受试者
- 判定依据: 摘要称共纳入 312 名受试者，而正文 2.1 节写最终纳入 318 名受试者，同一数值两处不一致，读者无法确定真实样本量。
- 修改建议: 核对原始记录后统一两处数字；若 312 为完成分析人数，应在摘要中区分'纳入'与'完成分析'。

### 学术规范

#### F002 [minor/规范问题] 以期刊惯例为由从简报告
- 定位: `manuscript.md` § 2.2 干预方案（anchor: 本研究按目标期刊惯例报告了主要结局指标。）
- 原文: > 本研究按目标期刊惯例报告了主要结局指标。
- 判定依据: （演示用误报：把'按目标期刊惯例'表述误判为规范问题，用于演示豁免词表 recheck 提示；按 false_positive_suppression.md，此类惯例声明不判缺陷，recheck 后应撤回。）
- 修改建议: （演示用）
- ⚠ recheck: 命中豁免词表 按目标期刊惯例：疑似学科/期刊惯例被误判为缺陷，请人工 recheck（见 references/false_positive_suppression.md）

#### F003 [minor/报告不全] 缺少数据可用性声明
- 定位: `manuscript.md` § 文末（anchor: [2] 李某, 等. 久坐行为与睡眠健康的相关性研究. 中华健康管理杂志. 2022.）
- 原文: > [2] 李某, 等. 久坐行为与睡眠健康的相关性研究. 中华健康管理杂志. 2022.
- 判定依据: 全文检索确认稿件至参考文献结束均无数据可用性声明（Data Availability Statement），多数期刊要求 RCT 提供。
- 修改建议: 在参考文献前补充数据可用性声明，说明数据获取途径或不可公开的原因。

## Pending Review（待人工复核，不凭空补结论）

- [#2] 本研究共纳入 500 名受试者并采用双盲设计：锚点复验失败：original_text（空白归一化后）未在 /input 抽取文本中复验到，疑似编造或转述，降级 pending_review；处置：pending_review（不凭空补结论，待人工复核）

## Rejected（机器复核驳回，留痕）

- [#3] 组间差异有统计学意义（p = 0.032）：severity 非法值 'high'（合法值: critical/major/minor/info）

## 不确定性记录

- pending_review [#2]: 锚点复验失败：original_text（空白归一化后）未在 /input 抽取文本中复验到，疑似编造或转述，降级 pending_review；处置：pending_review（不凭空补结论，待人工复核）
