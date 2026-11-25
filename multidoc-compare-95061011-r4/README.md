# 多文档比较与整合（challenge-95061011）：五个独立方向

本目录包含五份相互独立、零共享文件的 Skill bundle。每份都提供完整的 `SKILL.md`、`scripts/`、`references/`、`GITHUB_URL.txt` 和可运行的**合成示例**；示例不含正式案例答案。

| Bundle | Skill | 独立重心 |
|---|---|---|
| [A-workorder-synthesis](A-workorder-synthesis/) | `workorder-synthesis` | 工单自适应作答：按实际问题、动态字段和请求交付物组织证据，而非套用固定领域表格 |
| [B-evidence-intervals](B-evidence-intervals/) | `evidence-interval-reconciliation` | 证据区间协调：将结果、条件和定义分别锚定并重新绑定，保留偏移、哈希、派生操作数与缺失检索范围 |
| [C-estimand-stratifier](C-estimand-stratifier/) | `estimand-stratifier` | 目标量与操作分层：分别裁定 DESCRIBE、DIRECTION、RANK、TRANSFORM、POOL，而非一刀切阻断比较 |
| [D-conflict-mechanisms](D-conflict-mechanisms/) | `conflict-mechanism-atlas` | 结论适用范围与冲突机制：区分互补、真实冲突、表观冲突和证据不足，机制归因须区分直接检验与假设 |
| [E-visual-evidence-rescue](E-visual-evidence-rescue/) | `visual-evidence-rescue` | PDF 布局证据救援：恢复表格、多行单元格、图注和图面板中的数据，并保留物理页与区域定位 |

所有 bundle 均遵循同一平台契约：读取 `/input` 下真实工单与语料，在 `/app/work` 工作，向 `/app/output` 交付；`result.json` 保留 `case_id`、原始 `output_contract` 全部字段、来源、不确定性及变更记录，并诚实标注 `partial`。六维可比性检验先于定量合成，不合并不同数据集或染料。

各示例均为虚构合成数据。运行入口见每份 `SKILL.md`；本地执行已覆盖成功路径、动态契约、引用完整性和各自关键失败分支。
