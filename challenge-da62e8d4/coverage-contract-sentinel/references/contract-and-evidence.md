# 数据格式与人工复核清单

## 合同提取

`case.json` 含 `case_id` 和 `output_contract`。接受以下顶层形状；嵌套属性不会误当顶层字段：

```json
["dataset_summary", "method_comparison"]
```

```json
{"fields": [{"name": "dataset_summary"}, {"key": "method_comparison"}]}
```

```json
{"type": "object", "required": ["dataset_summary"], "properties": {"dataset_summary": {"type": "object"}, "method_comparison": {"type": "object"}}}
```

上例 JSON Schema 只要求 `dataset_summary`。若交付合同给 properties 却省略 required，为避免漏交，本工具把全部 properties 视为必需。直接 field mapping 默认所有 key 必需，单项 `required: false` 可排除。合同可以声明 `case_id`、`status`、`sources`、`uncertainty`、`change_records`、`delivery`；它们由工具的标准顶层字段满足并从答案字段集合中排除，不会冲突或漏交。`output_contract` 是保留名。合法 JSON Schema 本身并不保证科学交付完整，所以仍须逐问登记。

标准字段从 init 到 final 始终平铺，其结构和生成规则固定为：

- `status`: 仅 `success/partial/unable/refused`，分别允许表达成功、部分完成、无法完成、拒绝；科学状态确定性地映射为 `complete -> success`、`degraded -> partial`、`unavailable -> unable`，不会被 coverage 或 contract PASS 改写。
- `sources`: evidence 列表的交付投影，每项仅取稳定 `id` 以及 `path/hash/locator/kind`，`hash` 是已登记真实文件的 SHA256，不接收虚构来源。
- `uncertainty`: `{scientific_notes, unavailable_reasons, coverage_gaps}`；不可用字段的完整 reason/missing_materials/next_steps 被保留，coverage_gaps 与 delivery 中同次诊断一致。
- `change_records`: 按 1 开始的 `sequence` 记录真实 `init/register/finalize` 操作、`recorded_at`、操作 `details` 和 `atomic_state`。后者保存该次原子写入的 finalized、三个 delivery 轴和顶层 status；failed finalize 也如实记录。

## requirements payload

由 agent 阅读 task.md 后手工/语义拆分，复合问句每个小问至少一条；每个要求的产物列出稳定名称。

```json
{"requirements": [{
  "id": "q1-parameter",
  "question": "原文给出了什么参数、单位、适用条件？",
  "fields": ["dataset_summary"],
  "required_artifacts": ["paper_parameter_trace"],
  "evidence_ids": ["paper-p7-table2"]
}]}
```

answers/result 中的字段记录为：

```json
{"answer_fragment": {"value": 42, "unit": "K", "scope": "原文指定体系"}, "evidence_ids": ["paper-p7-table2"]}
```

不可用时不得伪造数值：

```json
{
  "unavailable": {
    "reason": "组织方未提供原始数据仓库，无法判断合成输入是否与作者数据一致。",
    "missing_materials": ["原始数据仓库及版本定位"],
    "next_steps": ["取得仓库后登记 attribution/environment/run/comparison 证据并更新字段。"]
  },
  "evidence_ids": ["case-attribution"]
}
```

## evidence payload

```json
{"evidence": [{
  "id": "paper-p7-table2",
  "kind": "paper",
  "path": "sources/article.pdf",
  "locator": {"page": 7, "table": "Table 2", "row": "model A", "column": "T"},
  "fields": ["dataset_summary"],
  "artifacts": ["paper_parameter_trace"],
  "note": "agent 已阅读原文：42 K 对应指定体系，不是全局结论。"
}, {
  "id": "candidate-a-run",
  "kind": "run",
  "path": "logs/candidate-a.log",
  "command": "已执行命令的原文；审计脚本不会执行它",
  "locator": {"lines": "1-28", "exit_code_line": 28},
  "fields": ["method_comparison"],
  "artifacts": ["candidate_a_log"]
}]}
```

路径基于 `--base-dir`；工具读取真实文件并计算 SHA256，不接受把哈希当文件替代。locator 所有叶节点必须非空。论文可以是真实 PDF，也可以是为可访问性生成的文本摘录；摘录 locator 仍须保留原 PDF 页码/段/表/图。register evidence 可暂时 `fields: []`，但矩阵会立即报 `evidence_without_fields` 和 `orphan_evidence`，不能 complete。

## 科学复核（机检之外）

- 读原文，确认 locator 的页、段、表、图确实是所引值，核对单位、误差、条件和分母；kind=paper 不是语义支持。
- 两个候选分别保留 environment/parameter/run。记录命令、日志行段、退出状态；失败候选同样保留，科学状态不得 complete。
- 在结果前固定 abs/rel 容差和比较指标。比较值、差异、是否满足事前容差、数值/物理/实现差异归因都要在 answer/comparison 产物出现。
- 组织方合成输入明确标注 synthetic；原始仓库缺失、无法执行、单候选失败或只完成部分问题均降级。不要用 `coverage_status` 反向抬升 `scientific_status`。
- available/unavailable 只表达本字段的交付状态，不得把 unavailable 改写成成功。所有字段可因具体原因 unavailable，但合同 PASS 仍仅是诚实交付，不是完成任务。

## final 规则与退出码

final 要求顶层精确为 `case_id + status + sources + uncertainty + change_records + 合同答案字段 + delivery`；合同显式声明标准字段时不重复计数，但缺失任何标准字段仍 FAIL。status 必须和科学状态映射一致，sources/uncertainty 必须与本次真实 evidence 和诊断一致，change_records 必须连续且含原子状态。每个 answered field 至少一条带同字段标签的真实证据，answer fragment 递归排除空容器、空泛串，unavailable 必须有具体 reason 和缺失项/下一步。文件哈希或 locator 失效也会 FAIL。coverage complete 额外要求：已 finalize、无 unavailable、八个查漏数组全空。

成功 finalize 返回 0，即使科学 degraded / coverage partial；只要合同机检失败就返回 2 并保留 FAIL 结果。输入格式错误、缺真实文件、无输出目录等也返回 2，此前产物不被清空。工具永远只登记运行，不执行候选命令。
