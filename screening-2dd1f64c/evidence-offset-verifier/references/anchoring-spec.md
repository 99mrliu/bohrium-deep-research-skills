# 证据锚定规范（anchoring spec）

本规范定义 evidence-offset-verifier 的锚点对象、匹配与偏移映射规则、拒绝与降级策略、理由卡片模板，以及批量判定调用的置信度指引。实现见 `scripts/evidence_engine.py`，二者语义一致；如有出入以本规范为准。

## 1. 锚点对象 schema

```json
{
  "field": "title | abstract",
  "start": 49,
  "end": 118,
  "surface_form": "源字段 [start:end] 的逐字切片",
  "match_type": "exact | whitespace-normalized"
}
```

- 偏移为 Python 语义下的字符偏移（半开区间 `[start:end)`，作用于该记录自身 `title` 或 `abstract` 字符串）。
- 不变式：**`record[field][start:end] == surface_form`**。validate 子命令逐条重算此不变式；任何不满足者即判定为编造或错引证据，validate FAIL（退出码 1）。
- `match_type` 记录定位方式，仅作审计信息；两种方式的锚点都参与同一不变式。

## 2. 匹配规则与偏移映射

定位顺序固定（确定性）：**先 title 后 abstract；每个字段内先精确匹配，后白空白归一化回退**。

1. **精确匹配**：`text.find(quote)`，命中则 `start=idx, end=idx+len(quote)`。
2. **白空白归一化回退**：把源文本与引文中的连续空白（空格/换行/制表等）各自折叠为单个空格后在归一化文本中查找；命中时通过归一化索引→原始索引的映射表还原原始偏移：
   - 映射表 `norm_to_orig[i]` = 产生归一化字符 i 的原始字符下标（被折叠的空白段只保留其首字符位置）；
   - `start = norm_to_orig[nidx]`，`end = norm_to_orig[nidx + len(norm_quote) - 1] + 1`；
   - `surface_form` 恒为**原始文本**的切片（保留原始空白），不是归一化形式。
   该回退只容忍空白差异（跨行复制、多余空格），**不容忍任何字符级改写**——改一个字即定位失败。
3. 空引文、纯空白引文、非字符串引文：直接视为定位失败，不参与匹配。

## 3. 拒绝与降级策略（反编造理由）

筛选结论的可信度完全系于证据可被第三方重算。一条无法核验的"证据"比没有证据更糟——它制造已核验的假象。因此：

- 定位失败的引文进入 `rejected_register`，条目含：`decision_index`、`record_id`、原始 `quote`、`reason: "evidence anchor failed verification"`，以及 **difflib 最近邻匹配**（候选为匹配块附近与引文等长的实际子串，输出 `field`、`ratio`、真实 `substring`），使 Agent 能在一次修复调用内把引文改成逐字形式。
- 对应决定**无条件降级为 `pending`**，`reason` 记录降级原因，事件写入 `change_records`。证据核验失败的决定绝不保留 keep/exclude 标签——这是本 Skill 的核心不变式。
- `record_id` 不在候选池的决定、同一记录的重复决定：同样进入拒绝登记（reason 分别为 record_id 未命中、重复决定），不影响首条有效决定。
- 无决定的记录：`pending` + `verification: "not_judged"`（`--decisions` 缺省时的退化路径同此），这是诚实占位而非判定。
- `verification_rate = anchors_verified / (anchors_verified + anchors_rejected)`，仅统计**已发出的决定**；无决定时定义为 0.0。`status.state=complete` 要求 rate==1.0、无未判定记录、无未填契约字段，否则 `partial` 并逐项说明。

## 4. 理由卡片模板（rationale_cards.md）

按排序结果（label 层级 keep<pending<exclude → confidence 降序 → record_id）逐记录一张：

```
## <rank>. <record_id> — <label> (confidence <0..1>, relevance <direct|indirect|none>)
- **Title**: <记录标题>
- **Criterion hit**: <判据命中短句>
- **Evidence anchor**: <field> [<start>:<end>] (<match_type> match), verification: verified
  > …<源字段 ±40 字符上文>**<surface_form>**<±40 字符下文>…
- **Verification status**: verified | rejected — <降级原因> | not_judged
```

引文以加粗嵌入源字段上下文中渲染，±40 字符窗口让读者无需翻原文件即可抽读核对语境；被拒绝或未判定的记录以相应状态行替代锚点行。

## 5. 批量判定调用的置信度指引

- `confidence` 是**证据支持度**的自评，不是标签的把握：引文直接陈述与方法/任务相关结论 → 0.8–0.95；需一步推断（如正向反应预测之于逆合成）→ 0.4–0.7 且 relevance 取 indirect；仅凭关键词共现 → ≤0.3，优先考虑 pending。
- `criterion_hit` 用一句短话写明命中/未命中哪条筛选判据，与引文分工：引文管"原文说了什么"，判据句管"为什么据此归类"。
- 引文优先选自摘要中的方法/结论句；标题引文仅用于摘要缺失或标题本身即结论的情况。
- 禁止为提高 verification_rate 而改写引文凑匹配（修复调用只允许把错引改成逐字原文）；禁止把 `fixture_note` 的内容当作判定依据——它是输入夹具的 provenance 标注。

## 6. 限制

- 证据来源**仅限标题与摘要**，无全文可得；基于题录的证据可能高估或低估相关性（尤其 indirect），此限制写入 result.json 的 `uncertainty`。
- 脚本核验"引文是否逐字存在及偏移是否正确"这一机械事实；判据语义是否合理不在脚本保证范围内。
- `fixture_note` / `fixture` 等字段仅作 provenance 引用，绝不作为 ground truth。
- 候选快照为有限集合，不声明快照之外的召回。
