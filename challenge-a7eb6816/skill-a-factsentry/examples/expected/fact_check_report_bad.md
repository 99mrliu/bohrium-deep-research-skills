# 事实核验报告（fact_check_report）

- 工具：fact_check 1.0.0（基于 ledger_extract 台账）
- 台账：`examples/expected/evidence_ledger.json`
- 改写稿：`examples/draft_bad.md`
- 失败判定阈值（--min-severity）：mandatory
- 结论：**FAIL**（退出码 3）

## 汇总

| 类别 | 条数 |
| --- | --- |
| unsupported_number（数字漂移/单位错配） | 2 |
| dropped_evidence（证据丢失） | 9 |
| strength_upgrade（论断强度升格） | 2 |
| **合计** | **13**（其中计入失败判定 12 条） |

核验覆盖面：改写稿数字 5 个；台账数字 10 个、图表引用 3 个、引用标记 3 个；论断句配对 5 组。

## 逐条发现

### 1. [unsupported_number] 数字漂移/单位错配（严重度：mandatory）

- 改写稿位置：`examples/draft_bad.md:5`
- 改写稿锚句：实验证实，该催化剂在 160 °C 下即可实现 99.8% 的 CO 转化率（图2），活性较纯 Co3O4 提升 2.3 倍，并可稳定运行 100 h
- 问题值：160 °C（单位：°C）
- 线索：源文中单位为「°C」的数值：180
- 修复建议：疑似数字漂移：请对照台账核对数值与单位。

### 2. [unsupported_number] 数字漂移/单位错配（严重度：mandatory）

- 改写稿位置：`examples/draft_bad.md:5`
- 改写稿锚句：实验证实，该催化剂在 160 °C 下即可实现 99.8% 的 CO 转化率（图2），活性较纯 Co3O4 提升 2.3 倍，并可稳定运行 100 h
- 问题值：99.8%（单位：%）
- 线索：源文中单位为「%」的数值：95.1、99.2
- 修复建议：疑似数字漂移：请对照台账核对数值与单位。

### 3. [dropped_evidence] 证据丢失（严重度：mandatory）

- 台账条目：`num-004`（number，位于 `examples/source.md:11`）
- 源文锚句：XRD 结果（图1）显示，Co3O4/CeO2 复合氧化物的平均晶粒尺寸为 4.5 nm，比表面积为 112 m2/g
- 丢失内容：112 m2/g
- 修复建议：该证据（112 m2/g）未在改写稿中出现；默认必须保留，请恢复，或在交付说明中写明删减理由（保留优先级见 references/retention_priority.md）。

### 4. [dropped_evidence] 证据丢失（严重度：mandatory）

- 台账条目：`num-005`（number，位于 `examples/source.md:11`）
- 源文锚句：在 180 °C、质量空速 36000 mL/(g·h) 条件下，CO 转化率达到 99.2%（图2）
- 丢失内容：180 °C
- 修复建议：该证据（180 °C）未在改写稿中出现；默认必须保留，请恢复，或在交付说明中写明删减理由（保留优先级见 references/retention_priority.md）。

### 5. [dropped_evidence] 证据丢失（严重度：mandatory）

- 台账条目：`num-006`（number，位于 `examples/source.md:11`）
- 源文锚句：在 180 °C、质量空速 36000 mL/(g·h) 条件下，CO 转化率达到 99.2%（图2）
- 丢失内容：36000 mL
- 修复建议：该证据（36000 mL）未在改写稿中出现；默认必须保留，请恢复，或在交付说明中写明删减理由（保留优先级见 references/retention_priority.md）。

### 6. [dropped_evidence] 证据丢失（严重度：mandatory）

- 台账条目：`num-010`（number，位于 `examples/source.md:11`）
- 源文锚句：连续运行 100 h 后，转化率保持在 95.1% 以上
- 丢失内容：95.1%
- 修复建议：该证据（95.1%）未在改写稿中出现；默认必须保留，请恢复，或在交付说明中写明删减理由（保留优先级见 references/retention_priority.md）。

### 7. [dropped_evidence] 证据丢失（严重度：mandatory）

- 台账条目：`num-007`（number，位于 `examples/source.md:11`）
- 源文锚句：在 180 °C、质量空速 36000 mL/(g·h) 条件下，CO 转化率达到 99.2%（图2）
- 丢失内容：99.2%
- 修复建议：该证据（99.2%）未在改写稿中出现；默认必须保留，请恢复，或在交付说明中写明删减理由（保留优先级见 references/retention_priority.md）。

### 8. [dropped_evidence] 证据丢失（严重度：mandatory）

- 台账条目：`num-001`（number，位于 `examples/source.md:11`）
- 源文锚句：平行实验 n=5，组间差异 p<0.05
- 丢失内容：n=5
- 修复建议：该证据（n=5）未在改写稿中出现；默认必须保留，请恢复，或在交付说明中写明删减理由（保留优先级见 references/retention_priority.md）。

### 9. [dropped_evidence] 证据丢失（严重度：mandatory）

- 台账条目：`num-002`（number，位于 `examples/source.md:11`）
- 源文锚句：平行实验 n=5，组间差异 p<0.05
- 丢失内容：p<0.05
- 修复建议：该证据（p<0.05）未在改写稿中出现；默认必须保留，请恢复，或在交付说明中写明删减理由（保留优先级见 references/retention_priority.md）。

### 10. [dropped_evidence] 证据丢失（严重度：mandatory）

- 台账条目：`tab-001`（figure_ref，位于 `examples/source.md:11`）
- 源文锚句：与纯 Co3O4 相比，复合催化剂的活性提升约 2.3 倍（表1）
- 丢失内容：表1
- 修复建议：该证据（表1）未在改写稿中出现；默认必须保留，请恢复，或在交付说明中写明删减理由（保留优先级见 references/retention_priority.md）。

### 11. [dropped_evidence] 证据丢失（严重度：recommended）

- 台账条目：`cit-002`（citation，位于 `examples/source.md:7`）
- 源文锚句：贵金属催化剂成本较高 [2]，过渡金属氧化物被认为是潜在替代方案 (Smith, 2021)
- 丢失内容：[2]
- 修复建议：该证据（[2]）未在改写稿中出现；默认必须保留，请恢复，或在交付说明中写明删减理由（保留优先级见 references/retention_priority.md）。

### 12. [strength_upgrade] 论断强度升格（严重度：mandatory）

- 改写稿位置：`examples/draft_bad.md:5`
- 改写稿锚句：研究还证实，CeO2 的引入促进了氧空位形成
- 源文位置：`examples/source.md:13`（配对相似度 0.524）
- 源文锚句：初步表明，CeO2 的引入促进了氧空位的形成
- 强度变化：提示/初步(1) → **证实(3)**
- 修复建议：论断强度由源文「初步表明」（提示/初步(1)）升格为「证实」（证实(3)）；建议改用与源文同级的表述。

### 13. [strength_upgrade] 论断强度升格（严重度：mandatory）

- 改写稿位置：`examples/draft_bad.md:5`
- 改写稿锚句：氧空位浓度的提高导致了催化剂活性的上升
- 源文位置：`examples/source.md:13`（配对相似度 0.364）
- 源文锚句：催化剂活性与氧空位浓度相关
- 强度变化：相关(1.5) → **因果断言(4)**
- 修复建议：论断强度由源文「相关」（相关(1.5)）升格为「导致」（因果断言(4)）；建议改用与源文同级的表述。
