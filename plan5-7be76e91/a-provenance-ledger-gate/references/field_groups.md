# 七类字段定义与填写规范（field_groups）

> 评分"完整性"要求的七类字段在本 Skill 中的落地定义。每个候选方案在 result.json
> 中都必须给出这七组（缺失的组写空数组并在 uncertainty 中说明），另加
> `evidence_basis`（依据与风险）与 `confirmations`（确认项）。
> field_group 的合法取值即下列七组的英文键名（见 claim_schema.json 的 enum）。

## 1. assumptions（假设）

方案成立所依赖、但未在来源材料中明示的前提（如"细胞对血清敏感度在本批次一致"）。
- 填写：每条 {field, value, rationale}；来源能支撑的假设按 given 抽取并对账，
  纯推断一律 status=inferred，进入结果时标注"假设，未经证实"。

## 2. variables（变量）

实验中拟改变/观测的量：自变量、因变量、干扰变量。每条注明角色与取值范围。
- 观测指标的定义（如活力=台盼蓝排斥法）要有来源锚点。

## 3. controls（对照）

阴性/阳性/基线对照及其设置理由。无对照方案不得直接判"更好"，
只能在 uncertainty 中说明证据强度不足。

## 4. steps（步骤）

有序操作步骤，每步注明依赖的设备/耗材与预计耗时；步骤里出现的每个数字
（体积、时间、温度）都要么有来源锚点，要么标 inferred。

## 5. parameters（参数）

有限参数域内的具体取值（如 temperature_c=37）。**必须**过两道门：
claim_audit 逐字对账 + domain_check 域校验；域外或 unsupported 的参数整字段隔离。

## 6. resources（资源）

设备、耗材、价格、货期、预订窗口。价格/排期数字只能来自组织方契约材料，
并须在 result.json 中声明"契约是前瞻性情景给定，非真实报价/审批"。

## 7. interpretation_criteria（判读标准）

判定实验成败/方案优劣的阈值与判据（如"活力 ≥95% 判合格"）。
阈值数字必须与来源逐字一致；来源没有的阈值只能作为 inferred 建议。

## evidence_basis（依据与风险）

每方案一个数组，逐条列出：采用的结论 ← claim_audit verdict 为 supported 的锚点
（file + locator + quote + char_offset），以及被隔离字段与原因（verdict、detail）、
该依据缺口带来的风险。

## confirmations（确认项）

固定四个键：`safety` / `ethics` / `equipment_availability` / `expert`，
取值 `confirmed` / `pending` / `not_applicable` + 一句话说明。
**规则：没有来源材料或组织方文件明示确认的一律 pending；pending 项在
result.json 中只能写成"待确认"，不得写成已确认事实或可执行步骤。**
