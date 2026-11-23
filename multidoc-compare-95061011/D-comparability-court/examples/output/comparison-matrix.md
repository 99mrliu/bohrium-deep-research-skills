# 许可内比较矩阵（case_id: SYNTH-EXAMPLE-001）

只有获得 PERMIT 的合成请求才在本矩阵中展开数值/定性视图；被 BLOCK 的请求只登记阻断理由，绝不给出被阻断的数值结论。

## [PERMIT-REQ-PERMIT-01] qualitative_contrast_rhb_degradation（qualitative）

断言：DOC-01 与 DOC-03 针对相同污染物（RhB）的相同任务（染料光催化降解），允许做定性对照：在相同底物与光源条件下，Ag 负载改性（g-C3N4 → g-C3N4-Ag）的表现差异可作定性讨论；材料维度仅 subset_only，报告必须注明口径差异，不做数值合并。

| 论文 | task | pollutant | material |
|---|---|---|---|
| DOC-01 | 染料光催化降解〔P2〕 | RhB〔P2〕 | g-C3N4〔P3〕 |
| DOC-03 | 染料光催化降解〔P2〕 | RhB〔P2〕 | g-C3N4-Ag〔P3〕 |

- 口径警告：DOC-01×DOC-03 / material: 仅 subset_only——取值不一致（不同材料体系的数值不可直接平均或排名；可在同污染物、同任务下做定性对照（如改性前后趋势）。） （报告必须注明口径差异）[DEC-DOC-01--DOC-03-material]

## 被阻断的合成请求（仅登记，不给结论）

### [REQ-BLOCK-01] degradation_rate_eta（quantitative）— BLOCK

被阻断断言：对 DOC-01 与 DOC-02 的降解率 η 求均值并排名，断言 DOC-01 优于 DOC-02。

- 阻断维度 material（subset_only）：'g-C3N4' vs 'N-TiO2' [DEC-DOC-01--DOC-02-material]
- 阻断维度 pollutant（blocked）：'RhB' vs 'MB' [DEC-DOC-01--DOC-02-pollutant]
- 阻断维度 budget（subset_only）：'0.5 g/L' vs '1.0 g/L' [DEC-DOC-01--DOC-02-budget]
