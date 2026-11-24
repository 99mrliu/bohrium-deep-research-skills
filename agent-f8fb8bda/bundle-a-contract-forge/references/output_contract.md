# 交付契约参考：字段语义、诚实状态与 change records

本文件是 dr-contract-forge 的契约语义细则。脚本（contract_check.py）只判定存在性与一致性，**语义达标由 agent 负责**；本文件定义"什么算填好"。

## 1. 契约字段的动态读取原则

- 契约字段一律来自 case.json 的 `output_contract`，逐案例不同，**禁止硬编码字段名**。
- `contract_init.py` 已把字段展开为点路径清单（`contract.json` 的 `output_contract.fields[]`），每项含 `path` 与 `declaration`（原始声明文本）。填写前重读该清单，以 `declaration` 为准理解每个字段的要求。
- 字段值可能是对象（展开为子路径）、数组或字符串；骨架中全部以 `"PENDING"` 占位，回填时按声明文本赋予正确类型。

## 2. 常见字段形态的填写规范

| 声明形态 | 应填内容 | 算"非占位"的最低标准 |
|---|---|---|
| 报告/正文（字符串） | 完整综述正文（Markdown），覆盖 task 问题、引用 `[E-编号]` 回链 | 非空、非 PENDING、含实质性段落而非一句话搪塞 |
| 矩阵/表格（数组） | 每行一条记录，键名遵循声明中的 schema | 数组元素为对象且键齐全；completed 下非空 |
| 日志（对象或数组） | 检索/处理过程记录：query、source、hits、kept 等 | 与 `search_coverage` 一致，不得事后编造命中数 |
| 局限性（数组） | 逐项的边界声明 | 每项指明"哪条结论 + 在什么边界内成立/不成立" |

注意脚本 F2 的机械判定：存在、非 `"PENDING"`、`completed` 下非空、`partial` 下空值须被 `limitations` 逐字段提及。语义质量（是否真有内容）靠 agent 自律与评测检验。

## 3. 六要点区块语义

- `problem_decomposition`：子问题数组。每条是一句可检索的问句，最好标注服务的契约字段。合取覆盖原问题，相互正交。
- `search_coverage`：检索记录数组。每条含来源、查询串、命中数、采用数；覆盖每个子问题；与 `sources` 能对上号。
- `evidence_linkage`：证据条目数组。每条：`id`（`E-01` 起编号）、`source_id`（指向 sources）、`claim`（该证据支持的主张）、`locator`（精确到页/段/表）。
- `conflict_evidence`：冲突主题数组。每条列主题、对立双方证据 id、以及处置（采纳哪方、为何，或标注未决）。没有冲突也要显式写"未发现实质冲突"并说明检索为何足以支撑此判断——completed 下区块不得为空。
- `synthesis`：综合结论文本。凡引用证据写 `[E-编号]`；编号必须存在于 `evidence_linkage`（F6 机械检查）。也可在对象形态中带 `evidence_ids` 列表，同样受 F6 约束。
- `research_gaps`：研究空白数组。每条说明"缺什么证据 + 为什么现有材料回答不了"。

## 4. 诚实状态规则

| status | 判定条件 | 写法要求 |
|---|---|---|
| `completed` | 全部契约字段填实、六要点区块非空、sources 非空 | `limitations` 仍应写明结论适用边界；`uncertainty` 保留真实不确定项 |
| `partial` | 有任何契约字段留空，或检索/综合未覆盖全部子问题 | `limitations` **逐字段**写原因（脚本 F2 按字段名匹配）；`uncertainty` 非空；说明"已覆盖什么、缺什么、为何缺" |
| `blocked` | case.json 不可用、材料缺失或环境故障导致无法开展 | 必须有 `blocked_reason`：缺什么、停在哪一步、如何恢复 |

铁律：不得为过门控填无依据内容；降级顺序是 completed → partial → blocked，永远诚实向下，绝不虚假向上。

## 5. Change records 怎么记

两层记录，互为补充：

1. **文件级**：`checkpoint.py save <stage>` 在每阶段结束时快照，`manifest.json` 记录每文件 SHA-256。这是回滚依据。
2. **语义级**：在 `result.json` 顶层维护 `change_log` 数组（非契约字段，允许添加），每次重大修改追加一条：
   ```json
   {"stage": "s4-synthesis", "action": "rewrite", "field": "synthesis",
    "note": "按 F6 违例移除不存在的 [E-09]，改为引用 [E-03]"}
   ```
   条目含阶段、动作（fill/rewrite/remove）、涉及字段、一句原因。评审可据此追溯"哪些结论是后来改的"。

`budget_ledger.json` 的 `usage` 数组同步记账：每阶段结束追加 `{"stage","requests","seconds","note"}`。
