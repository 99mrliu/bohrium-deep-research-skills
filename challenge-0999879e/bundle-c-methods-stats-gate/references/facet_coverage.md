# 六分面覆盖（facet_coverage）

状态值统一为：`checked_clean` / `issues_found` / `partially_checked` /
`unable_to_check`。

本 bundle 深查面 = **方法设计** + **统计报告**；其余四分面只做最低检查点
并如实登记，不越界深查、不凭空补结论。

## 深查面

### 方法设计（issues_found 触发条件：任一 fail_design）
- 对照设置（C01）、抽样（C02）、指标选择（C03）、多重比较（C10）、随机化
  （C11）、盲法（C12）、重复与独立性（C13）、剔除规则（C14）。
- 由 `gate_check.py run` 逐条判定；任一 fail_design → 本分面 `issues_found`。

### 统计报告（深查面，同上）
- 样本量与依据（C04）、检验适用条件（C05）、检验名称（C06）、精确 p（C07）、
  CI（C08）、效应量（C09）、软件版本（C15）、误差棒（C16）。
- 任一 fail（含 fail_reporting）→ 本分面 `issues_found`。

## 轮查面（最低检查点）

### 事实核验
- 最低检查点：扫描占位/待核实标记（`[?]`、`待核实`、`citation needed`、
  `TODO`）。无标记 → `checked_clean`；有标记 → `issues_found`（逐条核验不属
  本 bundle）。事实主张真伪核验本身 → `partially_checked` 都不记，本 bundle
  明确不评估真伪，只查占位。

### 引用支持
- 最低检查点：识别参考文献节并计数条目。有节且 ≥1 条 → `checked_clean`；
  无节 → `unable_to_check`。引文-主张逐条对应 → 不属本 bundle，不评估。

### 论证链
- 最低检查点：结论节存在性登记。存在 → `partially_checked`（深查交其他
  bundle/人工）；不存在 → `partially_checked` 并注明结构缺失。

### 学术规范
- 最低检查点：伦理/知情同意、数据可得性、利益冲突、基金声明的模式检出。
  至少一类 → `checked_clean`；全无 → `issues_found`（提示补声明，不定性为
  学术不端）。
