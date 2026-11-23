# 适用边界、失败模式与维护

## 适用边界

- 本 Skill 聚焦**两篇独立论文**之间的实体身份裁决与图谱证据绑定；
  语义抽取（提及、别名、关系）由调用方 Agent 完成，本包只提供确定性裁决、
  核验、构图与查询，不臆造任何实体或数值。
- 规范化是字符串级（大小写、连字符、希腊字母、空白、少量单位别名），
  不做词形还原、不做跨语言对齐、不做单位换算；换算不确定的单位按
  `unit_conflict` 保守阻断。
- 数值比较是近精确相等；任何真实差异都构成阻断，宁可 KEEP_DISTINCT 也不错并。

## 已知失败模式与处置

| 情形 | 行为 |
|-|-|
| `/app/work/mentions.json` 缺失 | 立即产出 `status=partial` 的 result.json，注明人工接管位置 |
| 段落抽取为空 | `status=partial`，图谱为空，不编造内容 |
| 引文非逐字 / 段落或来源缺失 | 元素剔除，记入 verification-report.json，运行继续 |
| 证据携带 page 字段 | 判核验失败（本包无 PDF 页码，禁止页码声称） |
| 同名测量值跨篇不同 | KEEP_DISTINCT（提及层）或 conflicts.json 记录（合并节点测量层），分别保留 |
| 通用术语无强身份键 | 至多 UNDECIDED |
| 查询无结果 / 路径不存在 | 如实标注 no_result / no_path（KEEP_DISTINCT 后无路径属预期） |
| output_contract 键无自然映射 | 保留 null 并在 uncertainties 说明 |

## 不做的事

- 不从图像像素、补充附件、底层实验数据推断数值（输入本就不提供）；
- 不把自建页码称作原 PDF 页码；
- 不把不同论文的条件、样本、数值合成一个结论；
- 不强迫每个别名合并，也不允许“同名即合并”。

## 维护信息

- 运行环境：Python3（>=3.7），仅标准库；全部文件 UTF-8 文本。
- 自检：`python3 scripts/selftest.py`（正向端到端 + 7 组负向守门）。
- 规则变更流程：先改 `references/identity-policy.md`，再改
  `scripts/identity_gate.py`，并在 `scripts/selftest.py` 增加对应测试。
- 示例数据为人工合成文本，仅演示接口与流程，不冒充正式案例结果。
