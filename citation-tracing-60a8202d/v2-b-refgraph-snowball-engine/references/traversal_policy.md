# 遍历策略全文：扩展、剪枝与停止

本文档是 `scripts/snowball.py` 所实现遍历策略的完整文字版，供复核与调参参考。

## 1. 记号

- 图为 refgraph.py 产出的有向引用图。边分两类：
  - backward（reference 边）：`u --cites--> v`，即 u 引用 v；
  - forward（citation 边）：`u --cited_by--> v`，即 u 被 v 引用。
- 种子集合 S（layer 0）：由 case.json 多字段 + task.md DOI 正则解析得到，
  全部解析尝试记录于 result.json 的 `seed.parse_attempts`。
- 关键词集合 K：task.md 分词（长度≥4 的英文词）、去停用词、按词频取前 12。
  节点的相关性得分 = K 中以其为子串出现于"标题+作者+期刊"文本的关键词数。

## 2. 扩展规则（方向感知分层 BFS）

- 遍历按层推进，depth 从 1 到 `--max-depth`（默认 3）。
- 第 d 层的前沿是第 d-1 层新加入的节点。对每个前沿节点，**同层内两个方向
  都扩展**：
  - 后向分支：沿该节点的 references（backward 边的 target）；
  - 前向分支：沿该节点的 citations（forward 边的 target，含反向索引恢复边）。
- 已访问节点不重复入层；同一层内被多个父节点同时触达的候选合并为一个节点，
  证据（父节点、方向、边 locator）逐条保留在 evidence_records。
- 每个节点入层时记录：layer、到达方向集合、关键词得分、是否 stub、是否经典。

## 3. 剪枝流水线

候选按以下顺序过闸；**每个决策（保留或剪除）都写入 pruning_log**，
含节点、层深、父节点、方向、原因与细节。

### 3.1 年份下限（`--year-min`，默认不启用）

- year 已知且 < year-min → 剪除，原因 `year_below_min`。
- **奠基经典例外**：`cited_by_count ≥ --classic-citedby`（默认 1000）的节点
  豁免，记 `classic_exception`（action=kept）。year 未知的节点不做年份剪枝。

### 3.2 关键词相关性

- K 非空且得分 = 0 → 剪除，原因 `keyword_irrelevant`。
- 豁免：stub 节点（无文本可判，记 `kept_stub`，保留以待人工复核）与经典节点。
- task.md 缺失时 K 为空，本闸整体停用并在 uncertainty 声明。

### 3.3 分支上限（`--max-branch`，默认 40）

- 对每个（父节点 × 方向）分组独立计数。
- 组内排序：关键词得分降序 → 年份降序 → 节点 id 升序（确定性）。
- 非经典节点保留前 max-branch 个，溢出者剪除，原因 `branch_cap`。
- **经典节点永远豁免**于分支上限；在名额已满时被保留会记
  `classic_exception`（kept beyond branch cap）。

### 3.4 全局节点预算（`--max-nodes`，默认 250）

- 加入新节点前检查 `|已访问| + |本层已接纳| ≥ max-nodes`：超出则剪除，
  原因 `node_budget`，并置预算耗尽标志（见 §4）。

## 4. 停止判据（写入 stop_log）

按优先级记录最先触发者：

1. `no_seed`：种子解析失败，depth 0 即停（status=failed）。
2. `node_budget`：全局节点预算耗尽，当前层收尾后立即停止；
   uncertainty 声明"更深层未探索"。
3. `zero_growth_layer`：某一层零新增节点——自然收敛，正常停止。
4. `depth_limit`：到达 `--max-depth`。

## 5. 诚实性与状态判定

- 无种子 → `failed`；种子有节点但零扩展 → `partial`；存在解析失败的语料
  文件 → 至多 `partial`；其余 → `ok`。
- 反向恢复边、stub 节点、被剪节点（遗漏说明）都会写入 uncertainty。
- output_contract 中本管线无法填充的字段镜像为 null 并记
  `field_not_produced`，绝不丢字段、绝不编造。

## 6. 调参建议

- 语料覆盖率高、噪声大：收紧 `--max-branch`（20–40）、启用 `--year-min`。
- 语料稀疏或种子很新：放宽 `--max-branch`，不加 `--year-min`，
  提高 `--max-depth` 至 4–5 并观察是否出现 `zero_growth_layer`。
- 900 秒预算内三命令管线远可完成；失败时先保留 honest partial，再调参重跑。
