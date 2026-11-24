# 七态来源核验状态机（verify_sources.py 的精确定义）

每条参考文献条目恰好落入一个状态。状态、触发条件与下游约束：

| 状态 | 触发条件 | 对下游审查的约束 | 退出码贡献 |
|-|-|-|-|
| `verified` | 在可信快照或 Crossref 在线记录中匹配（DOI 精确或规范化标题精确），且年份、首作者、标题相似度（≥0.40 token overlap）全部一致 | 引用支持判定可进入语义阶段；confidence 上限仍受"是否核读原文"约束 | 0 |
| `metadata_conflict` | 记录匹配但年份不一致、首作者不一致或标题相似度 <0.40 | 该条引用一律先按"事实错误/规范问题"出 finding；修正条目后再做语义判定 | 1 |
| `not_found_in_snapshot` | 快照存在且在线查询（若启用）均无匹配，但条目本身元数据可解析、DOI（若有）语法合法 | 标 待复核；引用支持判定 confidence ≤ low；basis 写明核查范围 | 0 |
| `suspected_fabricated` | 查无记录 **且**（DOI 语法无效 或 元数据无法解析） | 硬报警；finding 类别=学术规范，severity≥major，措辞用"疑似"；建议作者提供原文 | 1 |
| `retraction_flagged` | 可信记录状态为 retracted | 硬报警；finding 类别=学术规范，severity≥major；检查本稿结论对其依赖程度 | 1 |
| `version_mismatch` | 条目指向预印本而可信记录给出已发表版本 `version_of` | 硬报警；规范问题 finding；依赖其具体数值的主张标 待复核 直至核对正式版 | 1 |
| `not_checked` | 无快照且未启用/未能完成在线查询 | 不作任何真实性断言；报告中统一声明"来源真实性未核"；引用支持判定 confidence ≤ medium | 0 |

## 匹配规则（判定可复现的关键）

- **DOI 匹配**：规范化小写、去 `https://doi.org/` 前缀与尾随标点后的精确相等。
- **标题匹配**：NFKC 规范化、小写、去标点后的精确相等（快照内）；快照外不做模糊匹配定性，只做冲突检测（token overlap）。
- **年份冲突**：取条目中最后一个四位年份（出版年惯例在最后）与可信记录 `year` 比较。
- **首作者冲突**：取条目第一个大写字母开头的姓氏 token 与可信记录 `first_author` 比较（NFKC、小写）。

## 退出码语义

`verify_sources.py` 写出完整报告后：任一硬报警状态（`suspected_fabricated` / `metadata_conflict` / `retraction_flagged` / `version_mismatch`）计数 >0 时退出码为 1，否则为 0。退出码 1 的含义是"门禁发现必须进入审查报告的硬问题"，不是程序失败；程序自身失败（输入文件缺失、JSON 损坏）以非零退出码 + stderr 报错表示，二者在运行日志中区分记录。
