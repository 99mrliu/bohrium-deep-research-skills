# 检索式静态审计（lint）规则表

`scripts/query_lint.py` 实现的全部规则。每条 finding 含
`rule_id / severity / concept / term / source / message / suggestion`。
lint 只做静态审计与建议，**不自动改写检索式**；召回类问题交给
`coverage_check.py` 的已知项召回诊断驱动修订。

| 规则 | 严重级 | 触发条件 | 风险 | 修改建议 |
|---|---|---|---|---|
| QL001 | info | 多词 term 出现在 crossref `query.bibliographic` 序列化中 | Crossref 无短语语义，词序约束丢失，"molecular property" 退化为无序词集合 | Crossref 结果在客户端做短语级后置过滤；以 Europe PMC / arXiv 短语查询为准，Crossref 仅作补充召回 |
| QL002 | error | 序列化查询串顶层 `AND` 分段内含 `OR` 且未加括号 | AND/OR 优先级歧义，块结构被破坏，召回/噪声双双失控 | 给每个 OR 组显式加括号：`(a OR b) AND (c OR d)` |
| QL003 | warn；若为块内唯一 term 则 error | 单词 term 命中过宽词表（model/data/study/analysis/method/system/property/learning/prediction/network…） | 高噪声：过宽单词几乎不限定任何文献，块形同虚设 | 替换为更具体的多词短语；或与块内其他 term 合并为短语；唯一 term 时该块必须重写 |
| QL004 | error | term 含 `*` 或 `?`，目标源为 crossref 或 arXiv | 这些源不支持通配符，查询被静默降级或报错 | 用枚举同义词（OR 组）替代截断符；只有 Europe PMC 支持词尾 `*`（如 `neural*`） |
| QL005 | warn | 同一概念块内两个 term 仅大小写不同（如 `Gnn` 与 `GNN`） | 三个源均大小写不敏感，重复 term 徒增审计与维护成本 | 保留一种写法（推荐保留权威大小写，如 `GNN`） |
| QL006 | error | 概念块无任何 term | 块间 AND 语义下整体召回为 0 | 删除该块或补充至少一个 term；并检查概念解析是否漏抽 |
| QL007 | warn | term 自带双引号（如 `"molecular property"`） | `query_build` 会再套一层引号，产生 `""…""` 双重引用 | 概念块中存裸 term，引号由 `query_build` 按方言添加 |

## 设计说明

- **严重级语义**：`error` = 会实质改变检索语义或使召回为 0，必须修复；
  `warn` = 噪声/冗余风险，建议修复；`info` = 方言固有限制的提示，需流程级对策
  （如 Crossref 后置过滤）。
- **确定性**：所有规则只依赖概念块文本与已序列化查询串，无随机、无外部调用，
  同样输入必然产生同样 findings。
- **与 coverage_check 的分工**：lint 发现"形式上"的问题（语法、方言兼容性、宽度）；
  `coverage_check` 发现"实证上"的问题（已知相关文献实际被哪个块挡掉）。两者互补，
  lint 全绿不代表召回达标，反之亦然。
