# 关闭判据与覆盖度规则（closure-rules.md）

本文件是 `scripts/close_obligations.py` / `coverage.py` / `contract_gate.py` 机检逻辑的人读版本。机检为准，人读为辅。

## 1. 状态机

```
open
 ├─ answered_with_evidence   有证据地回答
 ├─ not_reported_confirmed   已确认未报告（合法结论，但须附检索范围）
 ├─ conflict_preserved       存在冲突/口径不一致，保留双方证据，不得合并
 └─ out_of_scope             超出工单/题目范围（须说明理由）
```

任何义务不得静默消失：不关闭就是 `open`，`open` 必须显式豁免或写入 `result.json` 的 `uncertainty`（门禁逐项核对）。

## 2. 各状态的关闭判据（机检项）

| status | 必填字段 | 机检内容 |
|---|---|---|
| `answered_with_evidence` | `value`、`source_document_id`、`paragraph_id`、`quote` | (doc, paragraph) 必须存在于语料段落索引；`quote` 必须是该段落 text 的逐字子串；field_cell 义务的证据文档必须等于该义务管辖文档；comparability 义务证据文档必须属于 `doc_pair` |
| `not_reported_confirmed` | `search_scope`（paragraph_id 列表）、`note`（≥10 字符） | `search_scope` 非空；每个 id 必须存在于管辖文档内；`note` 须说明检索范围与“已检索相关段落无果”的结论 |
| `conflict_preserved` | 双方证据：`source_*` 与 `secondary_source_*` 两组 (document, paragraph, quote)、`value` 或 `note`（≥10 字符） | 两组 quote 均逐字核验；这是“冲突”而非“回答”，数值不得合并 |
| `out_of_scope` | `note`（≥10 字符） | note 说明为何该义务不适用于本案 |

附加规则：
- 任何 closure 中的 `obligation_id` 必须存在于台账，否则报错（防止凭空造义务）。
- 同一义务重复关闭时后写覆盖先写（脚本给出警告）。
- 任一校验失败：整体不写回、非零退出。宁可不合并，不接受半合格证据。

## 3. 可比性维度的判定约定（comparability 义务的 value）

- `comparable`：两文档在该维度上口径一致（如都报去除率、都报 min-1、同污染物同光源任务）。
- `not_comparable`：口径不一致或未报告导致无法比较。**典型判 not_comparable**：不同污染物（如 RhB vs MB，v2 明令不得合并不同染料）、不同数据集、指标口径不同（去除率 vs 速率常数）、材料体系不同、一方未报告。
- `partially_comparable`：部分可比（如同族材料但负载改性）。
- 判断前先看字段义务是否已关闭：一方 `not_reported_confirmed` 的维度，其 comparability 通常也只能判 `not_comparable` 或附证据说明。

## 4. 覆盖度指标定义（coverage.json）

- `total / closed / open / closure_rate`：义务总数、非 open 数、open 数、关闭率。
- `by_dimension`：按 `dim:<维度>`（comparability）、`field:<字段>`（field_cell）、`question` 分组，各组 total/closed/closure_rate/open_ids。
- `by_document`：field_cell 计入其文档；comparability 同时计入两个文档。
- `open_obligations`：全部 open 的 obligation_id 列表——这是门禁第 7 项的核对输入。

比较矩阵 `comparison-matrix.md` 的单元格渲染规则：`answered_with_evidence` → `value unit 〔doc#para〕`；`not_reported_confirmed` → “未报告（已确认）”；`conflict_preserved` → “冲突保留：…”；`out_of_scope` → “范围外”；`open` → `⚠ OPEN`。矩阵是台账的渲染视图，**不是手工产物**。

## 5. 豁免规则

- 豁免只针对 `open` 义务；已关闭义务没有豁免概念。
- 豁免方式唯一：把 obligation_id 逐字写进 `result.json` 的 `uncertainty`（建议结构 `{"obligation_id": ..., "reason": ...}`），门禁做逐字核对。
- `out_of_scope` 不是豁免手段的替代品：能拿到证据的不许 out_of_scope；确属工单范围外的才可用。

## 6. 交付门禁检查项（contract_gate.py）

1. `result.json` 是合法 JSON 对象；
2. `case_id` 存在且与 `case.json` 一致（原样复制）；
3. `case.json` 的 `output_contract` 全部字段作为顶层键出现（支持 list[str] / list[dict] / dict 三种形态）；无 output_contract 时退化为 `{case_id, status, sources, uncertainty}`；
4. `status ∈ {success, partial, failed}`；
5. `sources`、`uncertainty` 键存在；
6. `status=partial` ⇒ `uncertainty` 非空（写明缺失边界）；
7. 台账中每个 open 的 obligation_id 必须逐字出现在 `uncertainty` 中。

任一失败 ⇒ `GATE FAIL`，退出码 1；全部通过 ⇒ `GATE PASS`，退出码 0。

## 7. 段落索引构建（语料无预提取答案层时）

语料可能是真实 PDF。流程：`pdftotext -layout in.pdf /app/work/<doc>.txt`（失败则 `pdftoppm -r 200` 渲染 + OCR），再按空行/小节切分为段落，写成

```json
{"document_id": "DOC-01", "paragraph_id": "DOC-01-p1", "text": "……"}
```

每行一条的 `<document_id>.jsonl`，放进 `/app/work/corpus/`。最小切分脚本示例（python3 标准库）：

```python
import json, sys
doc_id, txt_in, jsonl_out = sys.argv[1], sys.argv[2], sys.argv[3]
paras = [p.strip() for p in open(txt_in, encoding="utf-8").read().split("\n\n") if p.strip()]
with open(jsonl_out, "w", encoding="utf-8") as f:
    for i, t in enumerate(paras, 1):
        f.write(json.dumps({"document_id": doc_id, "paragraph_id": "%s-p%d" % (doc_id, i), "text": t}, ensure_ascii=False) + "\n")
```

若语料本身已自带 paragraph_id 的 jsonl（如本 bundle 的 examples/corpus），直接使用。
