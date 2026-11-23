# 可比性裁定报告（模板，case_id: SYNTH-EXAMPLE-001）

> **叙述绑定规范**：本节之后每个跨论文比较句必须引用 [DEC-…] 或 [PERMIT-…]；无 PERMIT 不得写任何定量比较/排名/“优于”结论；定性对照若带口径警告必须复述该警告。

## 1. 语料与任务

语料论文：DOC-01, DOC-02, DOC-03。裁定维度：task, metric, units, material, pollutant, budget（扩展键见裁定矩阵）。

## 2. 任务级总裁定

- DOC-01 × DOC-02：**blocked**（最严维度：pollutant）[DEC-DOC-01--DOC-02-__overall__]
- DOC-01 × DOC-03：**undecidable**（最严维度：budget）[DEC-DOC-01--DOC-03-__overall__]
- DOC-02 × DOC-03：**blocked**（最严维度：pollutant）[DEC-DOC-02--DOC-03-__overall__]

## 3. 许可内合成

- [PERMIT-REQ-PERMIT-01] DOC-01 与 DOC-03 针对相同污染物（RhB）的相同任务（染料光催化降解），允许做定性对照：在相同底物与光源条件下，Ag 负载改性（g-C3N4 → g-C3N4-Ag）的表现差异可作定性讨论；材料维度仅 subset_only，报告必须注明口径差异，不做数值合并。（DOC-01×DOC-03 / material: 仅 subset_only——取值不一致（不同材料体系的数值不可直接平均或排名；可在同污染物、同任务下做定性对照（如改性前后趋势）。） （报告必须注明口径差异）[DEC-DOC-01--DOC-03-material]）

## 4. 被阻断的合成

- [REQ-BLOCK-01] 请求“对 DOC-01 与 DOC-02 的降解率 η 求均值并排名，断言 DOC-01 优于 DOC-02。”被阻断：维度 material 裁定 subset_only（'g-C3N4' vs 'N-TiO2'）[DEC-DOC-01--DOC-02-material]
- [REQ-BLOCK-01] 请求“对 DOC-01 与 DOC-02 的降解率 η 求均值并排名，断言 DOC-01 优于 DOC-02。”被阻断：维度 pollutant 裁定 blocked（'RhB' vs 'MB'）[DEC-DOC-01--DOC-02-pollutant]
- [REQ-BLOCK-01] 请求“对 DOC-01 与 DOC-02 的降解率 η 求均值并排名，断言 DOC-01 优于 DOC-02。”被阻断：维度 budget 裁定 subset_only（'0.5 g/L' vs '1.0 g/L'）[DEC-DOC-01--DOC-02-budget]

## 5. 不可比与未报告项（必须保留，不得删除）

- DOC-01 × DOC-02：阻断/受限维度 = budget, material, pollutant[DEC-DOC-01--DOC-02-__overall__]
- DOC-01 × DOC-03：阻断/受限维度 = budget, material, metric, units[DEC-DOC-01--DOC-03-__overall__]
- DOC-02 × DOC-03：阻断/受限维度 = budget, material, metric, pollutant, units[DEC-DOC-02--DOC-03-__overall__]
