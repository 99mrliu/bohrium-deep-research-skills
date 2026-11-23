# 可比性裁定矩阵（case_id: SYNTH-EXAMPLE-001）

图例：✓ comparable ｜ ○ convertible ｜ △ subset_only ｜ ? undecidable ｜ ✗ blocked

## 总览：论文对 × 维度

| 论文对 | task | metric | units | material | pollutant | budget | 总裁定 |
|---|---|---|---|---|---|---|---|
| DOC-01 × DOC-02 | ✓ comparable | ✓ comparable | ✓ comparable | △ subset_only | ✗ blocked | △ subset_only | ✗ **blocked** |
| DOC-01 × DOC-03 | ✓ comparable | △ subset_only | △ subset_only | △ subset_only | ✓ comparable | ? undecidable | ? **undecidable** |
| DOC-02 × DOC-03 | ✓ comparable | △ subset_only | △ subset_only | △ subset_only | ✗ blocked | ? undecidable | ✗ **blocked** |

## 逐对裁定明细

### DOC-01 × DOC-02 — 总裁定：✗ blocked（最严维度：pollutant）

| 维度 | 裁定 | decision_id | A 取值（定位） | B 取值（定位） | 说明 |
|---|---|---|---|---|---|
| task | ✓ comparable | DEC-DOC-01--DOC-02-task | 染料光催化降解〔P2: “研究任务为染料废水的光催化降解”〕 | 染料光催化降解〔P2: “研究任务为染料的光催化降解”〕 | 规范化取值一致 |
| metric | ✓ comparable | DEC-DOC-01--DOC-02-metric | eta〔P4: “性能评价指标为降解率 η”〕 | eta〔P4: “以降解率 η 为评价指标”〕 | 规范化取值一致 |
| units | ✓ comparable | DEC-DOC-01--DOC-02-units | %〔P4: “η = 96%”〕 | %〔P4: “η = 88%”〕 | 规范化取值一致 |
| material | △ subset_only | DEC-DOC-01--DOC-02-material | g-C3N4〔P3: “催化剂材料为石墨相氮化碳 g-C3N4”〕 | N-TiO2〔P3: “催化剂为氮掺杂二氧化钛 N-TiO2”〕 | 取值不一致（不同材料体系的数值不可直接平均或排名；可在同污染物、同任务下做定性对照（如改性前后趋势）。） |
| pollutant | ✗ blocked | DEC-DOC-01--DOC-02-pollutant | RhB〔P2: “目标污染物为罗丹明 B（RhB）”〕 | MB〔P2: “目标污染物为亚甲基蓝（MB）”〕 | 取值不一致（不同污染物（如 RhB vs MB）的降解数据物理上不可合并：禁止均值、排名与'优于'断言。） |
| budget | △ subset_only | DEC-DOC-01--DOC-02-budget | 0.5 g/L〔P6: “催化剂投加量（budget）为 0.5 g/L”〕 | 1.0 g/L〔P6: “催化剂投加量为 1.0 g/L”〕 | 取值不一致且不在可换算表内（投加量或规模不同，定量合成需按剂量归一；默认仅发定性 permit，报告中必须注明口径差异。） |

### DOC-01 × DOC-03 — 总裁定：? undecidable（最严维度：budget）

| 维度 | 裁定 | decision_id | A 取值（定位） | B 取值（定位） | 说明 |
|---|---|---|---|---|---|
| task | ✓ comparable | DEC-DOC-01--DOC-03-task | 染料光催化降解〔P2: “研究任务为染料废水的光催化降解”〕 | 染料光催化降解〔P2: “研究任务为染料光催化降解”〕 | 规范化取值一致 |
| metric | △ subset_only | DEC-DOC-01--DOC-03-metric | eta〔P4: “性能评价指标为降解率 η”〕 | k〔P4: “速率常数 k = 0.031 min^-1”〕 | 取值不一致（不同指标（如降解率 η vs 速率常数 k）数值不可合并、不可排名，仅允许定性对照。） |
| units | △ subset_only | DEC-DOC-01--DOC-03-units | %〔P4: “η = 96%”〕 | min^-1〔P4: “0.031 min^-1”〕 | 取值不一致且不在可换算表内（单位不同先查 conversions：可换算 → convertible（permit 须附归一化说明）；不可换算（分属不同指标口径）→ subset_only。） |
| material | △ subset_only | DEC-DOC-01--DOC-03-material | g-C3N4〔P3: “催化剂材料为石墨相氮化碳 g-C3N4”〕 | g-C3N4-Ag〔P3: “复合材料 g-C3N4-Ag”〕 | 取值不一致（不同材料体系的数值不可直接平均或排名；可在同污染物、同任务下做定性对照（如改性前后趋势）。） |
| pollutant | ✓ comparable | DEC-DOC-01--DOC-03-pollutant | RhB〔P2: “目标污染物为罗丹明 B（RhB）”〕 | RhB〔P2: “目标污染物为罗丹明 B（RhB）”〕 | 规范化取值一致 |
| budget | ? undecidable | DEC-DOC-01--DOC-03-budget | 0.5 g/L〔P6: “催化剂投加量（budget）为 0.5 g/L”〕 | （未报告） | 维度未报告（B 侧缺失），无法裁定 |

### DOC-02 × DOC-03 — 总裁定：✗ blocked（最严维度：pollutant）

| 维度 | 裁定 | decision_id | A 取值（定位） | B 取值（定位） | 说明 |
|---|---|---|---|---|---|
| task | ✓ comparable | DEC-DOC-02--DOC-03-task | 染料光催化降解〔P2: “研究任务为染料的光催化降解”〕 | 染料光催化降解〔P2: “研究任务为染料光催化降解”〕 | 规范化取值一致 |
| metric | △ subset_only | DEC-DOC-02--DOC-03-metric | eta〔P4: “以降解率 η 为评价指标”〕 | k〔P4: “速率常数 k = 0.031 min^-1”〕 | 取值不一致（不同指标（如降解率 η vs 速率常数 k）数值不可合并、不可排名，仅允许定性对照。） |
| units | △ subset_only | DEC-DOC-02--DOC-03-units | %〔P4: “η = 88%”〕 | min^-1〔P4: “0.031 min^-1”〕 | 取值不一致且不在可换算表内（单位不同先查 conversions：可换算 → convertible（permit 须附归一化说明）；不可换算（分属不同指标口径）→ subset_only。） |
| material | △ subset_only | DEC-DOC-02--DOC-03-material | N-TiO2〔P3: “催化剂为氮掺杂二氧化钛 N-TiO2”〕 | g-C3N4-Ag〔P3: “复合材料 g-C3N4-Ag”〕 | 取值不一致（不同材料体系的数值不可直接平均或排名；可在同污染物、同任务下做定性对照（如改性前后趋势）。） |
| pollutant | ✗ blocked | DEC-DOC-02--DOC-03-pollutant | MB〔P2: “目标污染物为亚甲基蓝（MB）”〕 | RhB〔P2: “目标污染物为罗丹明 B（RhB）”〕 | 取值不一致（不同污染物（如 RhB vs MB）的降解数据物理上不可合并：禁止均值、排名与'优于'断言。） |
| budget | ? undecidable | DEC-DOC-02--DOC-03-budget | 1.0 g/L〔P6: “催化剂投加量为 1.0 g/L”〕 | （未报告） | 维度未报告（B 侧缺失），无法裁定 |

## 阻断明细表（所有非 comparable 裁定）

| decision_id | 论文对 | 维度 | verdict | A 取值 | B 取值 | 双方 quote 定位 |
|---|---|---|---|---|---|---|
| DEC-DOC-01--DOC-02-material | DOC-01 × DOC-02 | material | △ subset_only | g-C3N4 | N-TiO2 | A:P3 / B:P3 |
| DEC-DOC-01--DOC-02-pollutant | DOC-01 × DOC-02 | pollutant | ✗ blocked | RhB | MB | A:P2 / B:P2 |
| DEC-DOC-01--DOC-02-budget | DOC-01 × DOC-02 | budget | △ subset_only | 0.5 g/L | 1.0 g/L | A:P6 / B:P6 |
| DEC-DOC-01--DOC-03-metric | DOC-01 × DOC-03 | metric | △ subset_only | eta | k | A:P4 / B:P4 |
| DEC-DOC-01--DOC-03-units | DOC-01 × DOC-03 | units | △ subset_only | % | min^-1 | A:P4 / B:P4 |
| DEC-DOC-01--DOC-03-material | DOC-01 × DOC-03 | material | △ subset_only | g-C3N4 | g-C3N4-Ag | A:P3 / B:P3 |
| DEC-DOC-01--DOC-03-budget | DOC-01 × DOC-03 | budget | ? undecidable | 0.5 g/L | （未报告） | A:P6 / B:— |
| DEC-DOC-02--DOC-03-metric | DOC-02 × DOC-03 | metric | △ subset_only | eta | k | A:P4 / B:P4 |
| DEC-DOC-02--DOC-03-units | DOC-02 × DOC-03 | units | △ subset_only | % | min^-1 | A:P4 / B:P4 |
| DEC-DOC-02--DOC-03-material | DOC-02 × DOC-03 | material | △ subset_only | N-TiO2 | g-C3N4-Ag | A:P3 / B:P3 |
| DEC-DOC-02--DOC-03-pollutant | DOC-02 × DOC-03 | pollutant | ✗ blocked | MB | RhB | A:P2 / B:P2 |
| DEC-DOC-02--DOC-03-budget | DOC-02 × DOC-03 | budget | ? undecidable | 1.0 g/L | （未报告） | A:P6 / B:— |
