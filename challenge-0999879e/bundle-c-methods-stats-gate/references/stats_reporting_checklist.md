# 统计报告完备性清单（stats_reporting_checklist）

16 条。每条在 `gate_check.py` 中有同编号（C01–C16）的确定性判定规则；
登记状态只能是 `pass` / `fail_reporting`（方法可接受但报告不全）/
`fail_design`（方法本身有缺陷）/ `unable_to_check`（文本不足以判定）。

核心区分：**fail_design** 指即使补写报告也无法挽回的缺陷（如无对照却下因果
结论、多指标未校正）；**fail_reporting** 指方法学上可接受、仅文字报告缺失
（如只写 p<0.05 不写检验名称）。

## 方法设计（facet: 方法设计 / 统计设计）

- **C01 对照设置**：设有恰当对照组（空白/溶剂/阳性对照），组间比较以对照为
  基准。判定：全文无对照描述 + 存在因果结论 → `fail_design critical`；无对照
  且无因果结论 → `fail_reporting major` 待人工复核；有对照 → `pass`。
- **C02 抽样方式**：描述研究对象/样本来源与抽样（或分组纳入）方式。体外实验
  且文本未给样本来源细节 → `unable_to_check`（如实记录，不臆断）。
- **C03 指标选择**：主要结局指标预先定义且与结论对应。无指标定义句 →
  `fail_reporting minor`。
- **C10 多重比较校正**（统计设计）：多指标/多组逐一做显著性判断却无
  Bonferroni/FDR 等校正或理由 → `fail_design major`（假阳性风险不可控，
  补写报告无法挽回）；单指标场景 → `pass`（不适用）。
- **C11 随机化**：组间分配采用随机化并描述方式。声称 RCT 却无随机化 →
  `fail_design critical`；普通研究未描述 → `fail_reporting minor`。
- **C12 盲法**：描述是否采用盲法及其实施环节。文本完全未提及 →
  `unable_to_check`（缺失声明 ≠ 未实施，不记 fail）。
- **C13 重复与独立性**：说明生物学/技术重复次数，观察单位相互独立。未说明 →
  `fail_reporting minor`。
- **C14 数据剔除规则**：预先说明剔除/排除标准。未说明 → `fail_reporting minor`。

## 统计报告（facet: 统计报告）

- **C04 样本量与依据**：报告 n 并说明估算依据（功效分析/前期数据）。有 n 无
  依据 → `fail_reporting minor`；连 n 都没有 → `fail_reporting major`。
- **C05 检验适用条件**：说明正态性/方差齐性等核验。未说明 →
  `fail_reporting minor`。
- **C06 检验名称**：给出具体检验名称。报告了 p 值却无任何检验名称 →
  `fail_reporting major`（无法复现）。
- **C07 精确 p 值 vs 阈值**：报告精确 p 值；只有阈值式（p<0.05）→
  `fail_reporting major`。
- **C08 置信区间**：关键比较给出 95% CI。做了推断统计但无 CI →
  `fail_reporting minor`。
- **C09 效应量**：报告 Cohen's d / OR 等。做了推断统计但无效应量 →
  `fail_reporting major`（无法判断实际意义）。
- **C15 统计软件版本**：软件名称 + 版本号。缺版本 → `fail_reporting minor`；
  完全未报告 → `fail_reporting minor`。
- **C16 图表误差棒定义**：误差棒含义（SD/SEM/95%CI）有定义。未定义 →
  `fail_reporting minor`。

## 防误报规则（判定前必读）

- **R1 描述性研究豁免**：全文未做假设检验（无 p 值）时，C06/C07/C08/C09
  不记 fail，按 `pass（不适用）` 登记并注明依据。描述性研究无检验不算缺陷。
- **R2 学科惯例差异**：某些学科（如部分物理学分支、定性研究）不报告
  不报告效应量/CI 属惯例；规则检出后由人工在复核时降级为 `info`，初判先按 rubric
  给 minor，报告里必须标注"可能属学科惯例，建议人工确认"。
- **R3 缺失 ≠ 未做**：盲法、随机化等文本未提及时，凡不能从文本判定的，一律
  `unable_to_check`，禁止把"没写"直接记为"没做"（fail_design）。
- **R4 因果结论红线**：fail_design 的判定必须以"原文因果结论句"为证据锚点
  （如"证明/证实/有效"），无锚点只能记 fail_reporting 待复核。
- **R5 抽取失败即 unable**：某文件抽取失败（如缺 pdftotext）时，依赖该文件
  的条目全部 `unable_to_check`，并在 uncertainty 中如实记录 extract_error。
