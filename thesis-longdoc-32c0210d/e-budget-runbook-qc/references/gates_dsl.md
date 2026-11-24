# gates_dsl.md — 验收断言 DSL（qc_gates.py 编译规则）

qc_gates.py 把 workorder 每条 item 的 `acceptance` 自然语言文本编译为下列
机械断言之一；编译不出则落入 `manual` 门，由模型显式判定并记录理由。

## 1. 可编译门

### absent "X" ["Y" ...] — 缺失断言
- **触发**：acceptance 含 `不再出现` / `不得出现` / `不出现` / `禁止出现` / `无残留`，
  且能从文本中提取引号词（英文 `"..."` 或中文 `“...”`）。
- **语义**：对 target 指定的全部 .md 章节做字面 grep，每个词命中数必须为 0。
- **PASS**：所有词 0 命中。**FAIL**：detail 列出 `文件:行号 (词)` 残留清单。
- **示例**：`全部章节中不再出现"隔膜"` → absent ["隔膜"]。

### present "X" ["Y" ...] — 存在断言
- **触发**：acceptance 含 `应包含` / `须包含` / `必须包含` / `至少包含` / `包含` / `出现`，
  且能提取引号词，且不匹配 absent（absent 优先判定）。
- **语义**：每个词在 target 章节中至少出现 1 次。
- **示例**：`摘要中应包含"隔板"定义` → present ["隔板"]。

### figure_ref_integrity — 图表引用完整性断言
- **触发**：acceptance 匹配 `图|表` 后 6 字内出现 `引用|完整`，或含 `图文一致` / `图表引用`。
- **语义**：收集全部章节中所有 `图N` / `表N` 提及；图题/表题 = 行首形如
  `图1 xxx`、`表2：xxx`、`图3: xxx` 的行。每个被提及的编号都必须存在对应图题/表题行。
- **PASS**：提及集 ⊆ 图题/表题集。**FAIL**：detail 列出缺图题/表题的编号。
- **示例**：`图表引用完整：所有图N/表N引用均有对应图题/表题` → figure_ref_integrity。

## 2. manual 门（编译 fallback）

以下情况编译不出，verdict=MANUAL，等待模型判定：

1. acceptance 不含任何可识别触发词；
2. 含**除外/限定条款**：匹配 `除……外` / `除……以外`
   （如"除引用标题外不再出现X"——机械 grep 无法区分引用标题，强行判会误杀）；
3. 触发词存在但提取不到引号词（断言对象不明确）。

模型判定方式（必须给理由，理由会写入 gates_report.json）：

```
python3 /skills/weekly-skill/scripts/qc_gates.py manual \
  --workdir /app/work --item 3 --verdict PASS \
  --reason "人工核查: 引用标题'隔膜泵研究'为题名原样保留, 正文已无残留"
```

manual 门判定后重算总门。预算收紧时，所有 manual 门应在**一次模型响应**内批量判完。

## 3. target 解析

- `target: "全部章节"` 或不含 `.md` → 章节目录下全部 .md（按文件名排序）。
- `target` 中含具体文件名（含 `.md`）→ 只验这些文件；匹配不到则回退全部章节。

## 4. 总门

| overall | 条件 | suggestion |
|-|-|-|
| PASS | 全部 item PASS | complete（允许 checkpoint finalize） |
| MANUAL_PENDING | 无 FAIL 但有 MANUAL | partial（先判 manual 门） |
| FAIL | 任一 FAIL | partial，failed_items 列出未过项 |

checkpoint.py finalize 会读取 gates_report.json：overall≠PASS 时拒绝置 complete，
保证 result.json 的 status 永远诚实。
