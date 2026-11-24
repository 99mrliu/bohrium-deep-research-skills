# 空白-证据绑定规则（gap–evidence binding）

核心命题：**研究空白只能从证据分布里长出来**。任何一条被登记的空白，必须能回答
"查过哪些文献、凭什么说这里是空白"。`scripts/gap_register.py` 强制执行本规则。

## 1. 空白类型与出处

| gap_type | 来源 | 判定 |
| --- | --- | --- |
| `single_source` | theme 覆盖 | 某 theme 仅 1 篇可用文献覆盖，结论无法交叉验证（theme 取模型 `work/themes.json`；缺失时以 facet 共现粗聚类代替并标注来源） |
| `unresolved_conflict` | 模型论断清单 `work/claims.jsonl` | 同一 topic 下同时存在 direction=positive 与 direction=negative 的论断对；**并列登记，不调和、不取多数、不平均** |
| `facet_absent` | facet 覆盖矩阵 | `vocab/facets.json` 中某 facet 值被 0 篇可用文献覆盖 |

underpowered facet（恰好 1 篇覆盖）不单独成空白，但作为信号写入 facet_matrix 与
uncertainties。

## 2. 每条空白的必备字段

```json
{"gap_id": "G07",
 "gap_type": "single_source | unresolved_conflict | facet_absent",
 "description": "…",
 "docs_checked": ["D1", "D2", "…"],
 "binding_evidence": ["…"],
 "related_facets": ["…"]}
```

- `docs_checked`（已查文献清单）：为确立该空白实际检查过的文献。
  - facet_absent / single_source：**全部可用文献**（"查遍语料无一覆盖"才有意义）；
  - unresolved_conflict：提出该冲突论断的文献。
- `binding_evidence`（绑定证据）：可回链的机器凭据，如
  `facet_matrix.coverage[population:孕妇] = 0/5`、`claim:C1`、`theme:T2`、`sole_doc:D3`。
- 缺任一字段的空白不得进入 gap_register，更不得写进决策备忘录。

## 3. 禁止事项

- **禁止"有待进一步研究"式表述**：任何不指明 docs_checked 与 binding_evidence 的
  "未来方向""研究不足""尚待探索"一律视为无效空白，模型产出中此类句子必须改写为
  绑定形式或删除。
- 禁止从常识/语料外知识断言空白（"临床上尚无指南"之类）；空白结论仅在本案语料内
  有界成立，备忘录必须保留这一边界声明。
- 禁止调和冲突：unresolved_conflict 空白的两方向论断在备忘录中并列呈现，
  各自标注来源文献。
- 禁止把 metadata_only / failed 文献当作"覆盖证据"去消解空白；它们最多写入
  uncertainties 说明"未查证"。

## 4. 与选题评估的衔接

空白登记是选题评估的输入而非装饰：`appraise.py` 只为能绑定到 gap_register 条目的
选题出具"空白驱动"理由；绑定不到任何空白的选题，其新颖度解释力存疑，应在备忘录
第 3 节显式说明。
