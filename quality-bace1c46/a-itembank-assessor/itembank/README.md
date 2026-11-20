# 条目库说明（itembank/）

本目录为「量表驱动的研究设计分型条目化评价」提供结构化检查条目。
每个文件按设计类型分组；`common.md` 的通用条目适用于所有设计类型，
类型文件（`rct.md` 等）仅在脚本分型（或模型修正分型）为对应类型时启用。

## 条目格式（机器可解析，脚本依赖此格式，勿改动字段名）

```
## [条目ID] 条目标题
- 维度: 研究设计 | 样本与抽样 | 测量与结局 | 统计分析 | 报告完整性
- 问题: 一句话评价问题
- 所需证据: 判 met 需要在原文中找到什么样的表述
- 不可评价: 何种情况必须判 not_assessable（弃权条件）
- 核心: 是 | 否        （核心条目参与分级阈值的 not_met/na 计数）
- 关键词: kw1, kw2, …   （match_evidence.py 据此抽取候选句，中英文均可）
```

- 条目 ID 规则：`C-` 通用，`R-` RCT，`H-` 队列，`K-` 病例对照，
  `X-` 横断面，`D-` 诊断准确性，`S-` 系统综述/Meta。
- 判断四态见 `rules/evidence_rules.md`；分级阈值见 `rules/grading_thresholds.md`。
- 新增条目：在对应文件追加同格式小节即可，无需改代码；
  新增设计类型：新增 `<type>.md` 并在 `scripts/match_evidence.py` 的
  `TYPE_FILE_MAP` 与 `scripts/classify_design.py` 的 `SIGNALS` 中登记。
