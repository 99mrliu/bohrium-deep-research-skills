# 方向语义与反向索引恢复的可靠性说明

## 1. 方向语义约定

引用关系在本质上只有一个事实：「A 引用了 B」。为了支持双向遍历，
本 Skill 在图中以两类有向边表示同一事实的两个读法：

| 边方向 | 记法 | 语义字段 | 读法 | 遍历含义 |
|---|---|---|---|---|
| backward | `u --cites--> v` | `semantics: "cites"` | u 引用 v | 从 u 沿其参考文献向"过去"走 |
| forward | `u --cited_by--> v` | `semantics: "cited_by"` | u 被 v 引用 | 从 u 沿其施引文献向"未来"走 |

恒等式：backward 边 `u→v` 与 forward 边 `v→u` 表述同一事实。
verify_trace.py 据此校验：同一 (source, target) 不得同时带两个方向标签
（矛盾边）；每条 forward 边必须在图中有 backward 镜像。

## 2. 前向边的两种来源

1. **原生（native）**：数据源直接给出施引列表（如 OpenAlex 的 cited_by、
   通用 JSON 的 citations 字段）。`direction_restored: false`。
2. **反向索引恢复（restored）**：数据源只给各记录的参考文献列表时，
   refgraph.py 在建图末尾对全语料做一次反向索引——对每条 backward 边
   `u→v` 补一条 forward 边 `v→u`，标 `direction_restored: true`，
   其 locator 直接沿用触发它的那条参考文献条目的定位。

## 3. 恢复边的可靠性边界

- **断言强度**：恢复边断言的是"语料中存在一条 v 的参考文献条目指向 u"，
  而不是"权威施引索引收录了 v→u"。它精确等于语料事实，但不是独立证据。
- **覆盖度边界**：只有语料中出现的记录才能产生恢复边。未被任何语料记录
  引用的节点没有前向边；语料外的施引文献不可见。result.json 的
  uncertainty 会报告恢复边数量，提醒该边界。
- **重复与冲突**：若同一事实既有原生 forward 边又可被恢复，原生优先，
  不重复造边；locator 逐条合并，可回指多个来源。
- **stub 参与**：指向语料外目标的引用产生 stub 节点；stub 同样参与反向
  索引（stub 是被引方时会得到指向引用者的恢复边），但 stub 本身永不获得
  编造的元数据。

## 4. 复核方法

- 每条边（含恢复边）的 `sources` 给出 `{file, pointer}`：pointer 是 JSON
  路径或行号，可直接回到原始语料条目核对。
- 快速统计：`graph.json` 的 `stats.forward_edges_restored`；逐边检查
  `direction_restored` 字段。
- 机器门禁：verify_trace.py 的方向一致性检查保证"恢复边必有其源"
  （forward 必有 backward 镜像），矛盾边与孤儿边会以 error 级别报出。
