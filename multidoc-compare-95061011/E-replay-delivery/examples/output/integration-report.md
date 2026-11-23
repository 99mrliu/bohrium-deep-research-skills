# 多文档整合报告（由 render_all.py 从 JSONL 记录确定性渲染）

本报告由 work/cells.jsonl（18 条单元格记录）与 work/decisions.jsonl（3 条可比性判定）渲染；每个事实句级引用 cell_id，可回溯至 (document_id, paragraph_id)。请勿手工编辑。

## 分论文要点
- **DOC-01**：catalyst_dosage_mg = 50 mg（C-005，DOC-01/P-02）；degradation_efficiency_pct = 96 %（C-003，DOC-01/P-01）；material = g-C3N4（C-001，DOC-01/P-01）；pollutant = 罗丹明B (RhB)（C-002，DOC-01/P-01）；rate_constant_k = 0.035 min^-1（C-006，DOC-01/P-03）；reaction_time_min = 90 min（C-004，DOC-01/P-01）。
- **DOC-02**：catalyst_dosage_mg = 40 mg（C-011，DOC-02/P-02）；degradation_efficiency_pct = 88 %（C-009，DOC-02/P-01）；material = N-TiO2（C-007，DOC-02/P-01）；pollutant = 亚甲基蓝 (MB)（C-008，DOC-02/P-01）；rate_constant_k 未报告（C-012）；reaction_time_min = 120 min（C-010，DOC-02/P-01）。
- **DOC-03**：catalyst_dosage_mg 未报告（C-018）；degradation_efficiency_pct 未报告（C-015）；material = g-C3N4-Ag（C-013，DOC-03/P-01）；pollutant = 罗丹明B (RhB)（C-014，DOC-03/P-01）；rate_constant_k = 0.031 min^-1（C-016，DOC-03/P-02）；reaction_time_min 未报告（C-017）。

## 可比性与合成结论
- D-001 [blocked] degradation_efficiency_pct 跨论文定量合成：DOC-02 污染物不同（亚甲基蓝 vs 罗丹明B，C-008）且材料体系不同（C-007），DOC-03 未报告效率（C-015）；依据规则不得合并不同染料或不同数据集，效率指标禁止跨文定量合并，仅并列呈现
- D-002 [partial] rate_constant_k 跨论文比较：DOC-01 与 DOC-03 均报告 k 且均为 RhB/g-C3N4 基体系（C-006、C-016），可并列呈现；但禁止合并或平均不同数据集，且 DOC-02 未报告 k（C-012），DOC-03 的 k 无法换算为效率口径
- D-003 [partial] budget（catalyst_dosage_mg）维度完整性：DOC-01/DOC-02 已报告投加量（C-005、C-011），DOC-03 未报告（C-018），budget 维度不完整，投加量归一化比较不可行

## 不确定性与缺失边界
- DOC-02 的 材料(material) 维度不可比（首见 C-007：材料体系不同（N-TiO2 vs g-C3N4 基））
- DOC-02 的 污染物(pollutant) 维度不可比（首见 C-008：污染物不同：亚甲基蓝 vs 罗丹明B，禁止合并）
- DOC-02 的 任务(task) 维度存在未报告项（首见 C-012）
- DOC-02 的 指标(metric) 维度存在未报告项（首见 C-012）
- DOC-02 的 单位(units) 维度存在未报告项（首见 C-012）
- DOC-02 的 材料(material) 维度存在未报告项（首见 C-012）
- DOC-02 的 污染物(pollutant) 维度存在未报告项（首见 C-012）
- DOC-02 的 预算(budget) 维度存在未报告项（首见 C-012）
- DOC-03 的 任务(task) 维度存在未报告项（首见 C-018）
- DOC-03 的 指标(metric) 维度存在未报告项（首见 C-015）
- DOC-03 的 单位(units) 维度存在未报告项（首见 C-018）
- DOC-03 的 材料(material) 维度存在未报告项（首见 C-018）
- DOC-03 的 污染物(pollutant) 维度存在未报告项（首见 C-018）
- DOC-03 的 预算(budget) 维度存在未报告项（首见 C-018）
- DOC-03 的 指标(metric) 维度不可比（首见 C-016：仅报告速率常数 k；k 与效率%口径不同，不可并入效率合成）
- 判定 D-001（blocked）：degradation_efficiency_pct 跨论文定量合成 — DOC-02 污染物不同（亚甲基蓝 vs 罗丹明B，C-008）且材料体系不同（C-007），DOC-03 未报告效率（C-015）；依据规则不得合并不同染料或不同数据集，效率指标禁止跨文定量合并，仅并列呈现
- 判定 D-002（partial）：rate_constant_k 跨论文比较 — DOC-01 与 DOC-03 均报告 k 且均为 RhB/g-C3N4 基体系（C-006、C-016），可并列呈现；但禁止合并或平均不同数据集，且 DOC-02 未报告 k（C-012），DOC-03 的 k 无法换算为效率口径
- 判定 D-003（partial）：budget（catalyst_dosage_mg）维度完整性 — DOC-01/DOC-02 已报告投加量（C-005、C-011），DOC-03 未报告（C-018），budget 维度不完整，投加量归一化比较不可行

交付状态：partial
