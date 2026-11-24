# 契约协议：output_contract 驱动的交付工程

本 bundle 的最高纲领：**审查质量一半在"审"，一半在"交"**。一切流程以
`/input/case.json` 中的 `output_contract` 为先验，先解析契约、先生成答题纸，
字段缺失即降级，绝不临时拼凑交付物。

## 1. 契约解析规则（contract_init.py 实现）

- `output_contract` 宽容解析，两种形态均接受：
  - 字段名列表：`["case_id","status","review_report","findings",...]`
  - dict：`{"case_id": "...", "findings": {...}}`（取 key 为字段名）
- 缺失或完全不识别：回退默认字段集
  `["case_id","status","review_report","findings","sources","uncertainty","change_log"]`，
  并在 `uncertainty` 中明确记录回退事实。
- `case_id` 缺失：不可降级，直接报错退出（退出码 2），因为最终 result.json
  必须含原 case_id，缺它整个交付无效。

## 2. 答题纸协议（work/answer_sheet.json）

答题纸是契约的"可填写实例"，每个契约字段一格：

```json
"contract_fields": {
  "<field>": {"status": "empty|partial|filled", "value": null, "null_reason": null}
}
```

- Agent 每完成一个字段，把 `status` 置为 `filled` 并填 `value`；
- 确实无法填的字段：保持 `value: null`，**必须**填 `null_reason`（诚实门依据）；
- 另有 `facet_coverage` 区：六分面各一格，Agent 核查后把 `status` 置为
  `checked_clean / issues_found / partially_checked / unable_to_check` 之一，
  并置 `"agent_filled": true`，否则 finalize 保守推导为 `unable_to_check`
  （不谎称 checked_clean，见 facet_coverage.md）。

## 3. 诚实门规则（finalize.py 终检）

终检按序执行，任何一条触发即 `status=partial` 并在降级原因中列明：

1. **null 无因**：任何契约字段值为 null 且 `null_reasons` 中无对应说明 →
   降 partial，记录"诚实门：契约字段 X 为 null 且无说明"。
2. **待复核未清**：adjudication 中存在 `downgraded`（pending_review）条目 →
   partial。pending 条目不凭空补结论，原样留痕。
3. **抽取错误**：任一输入文件有 `extract_error`（如缺 pdftotext）→ partial。
4. **recheck 提示未消化**：accepted 条目带豁免词表/类型-分面不一致提示 →
   partial，提示人工二次确认。
5. **未知契约字段置 null**：即使给了 null_reasons，也声明 partial 限度。

无触发 → `status=complete`。诚实门只降不升：Agent 不得在答题纸中
手工把 status 写成 complete 来绕过。

## 4. 原子写入与幂等要求

- 所有交付文件（result.json、review_report.md、answer_sheet.json、
  adjudication_report.json）一律"临时文件 + `os.replace` rename"写入，
  读者任何时刻看到的都是完整旧版或完整新版，绝无半写文件。
- **幂等**：finalize.py 可重复运行，同一 answer_sheet + adjudication 输入
  必得同一 findings 顺序与编号（F001… 按排序后位置分配，排序键 =
  (facet 序, severity 序, 锚点字符位置, original_text)），保证同一稿件
  重复运行 schema 与条目编号稳定，他人可逐条复验。
- result.json 可被他人逐条复验：每条 finding 的 `original_text` 在
  work/extracted_text.txt（空白归一化后）中可定位；`sources.input_files`
  带每个输入文件的 SHA-256，可核对稿件版本。

## 5. 交付物清单

| 文件 | 生成者 | 说明 |
| --- | --- | --- |
| work/answer_sheet.json | contract_init → Agent 填写 | 契约答题纸 |
| work/extracted_text.txt | contract_init | 抽取语料（锚点复验基准） |
| work/findings_candidate.json | Agent（scaffold 生成模板） | 候选问题清单 |
| work/adjudication_report.json | adjudicate check | 逐条处置 + 理由留痕 |
| /app/output/result.json | contract_init（保底）→ finalize（终稿） | 含 case_id 与契约全部字段 |
| /app/output/review_report.md | finalize | 可编辑审查报告 |
