---
name: ocr-rescue-postprocess
description: >-
  扫描版 PDF 经 OCR 后的证据门控后处理与质量校验。当案例 PDF 为扫描件、其 OCR 文本层
  出现典型混淆错误（0/O、1/l/I、rn/m、cl/d、vv/w、fi 连字丢失、希腊字母被拉丁化如
  α→a 等）时使用本 Skill。OCR 引擎本身不在本 Skill 范围内：先编排平台 ocr-tool（或
  外部 tesseract）产出原始 OCR 文本，本 Skill 是其下游的后处理质量门——只做白名单内
  高置信纠错并全程留痕，低置信片段标记为 [unreadable] 绝不猜测，最后输出前后对比的
  QC 报告。
---

# ocr-rescue-postprocess：扫描件 OCR 文本的证据门控后处理与校验

## 总览

```
扫描版 case PDF
   │  (编排: 平台 ocr-tool, 或外部 tesseract —— 不属于本 Skill)
   ▼
raw OCR text (按页 form feed 分隔)
   │  scripts/confusion_scan.py   数据驱动混淆扫描, 只产候选, 不改文本
   ▼
candidates.jsonl (page/line/col/span/suggestion/rule/confidence)
   │  scripts/postcorrect.py      证据门控: 仅应用 high + 词典可证; medium 需
   │                              --aggressive; low 永不改动; 垃圾串标记 [unreadable]
   ▼
corrected.txt + change_log.jsonl + review_list.json
   │  scripts/ocr_qc.py           前后可疑词元率对比 + 合同感知 result.json
   ▼
qc_report.json + result.json  →  交付到 /app/output
```

核心原则：**precision over recall —— 一处错误纠正比一个不修改的诚实标记危害更大**。
所有规则与词典见 `references/ocr-confusions.tsv`、`references/lexicon-en.txt`、
`references/method.md`。

## 运行契约

- 输入侧：`ls -R /input` 查看案例；`/input/case.json`（含 `case_id` 与
  `output_contract`）+ `task.md` + 案例 PDF。
- 工作区：`/app/work`（中间产物）。
- 输出侧：`/app/output`。`result.json` **必须**包含原始 `case_id`，并逐一回显
  `output_contract` 的每个字段：有产出则给出相对路径，无产出则留空并附
  explanation；status 必须诚实（ok / partial / failed + 原因）。
- 预算纪律：64 次请求 / 900 秒。**脚本优先**：先跑 `run_pipeline.py` 或三个脚本，
  只把剩余预算用于人工核对 review_list，不要把预算花在逐字阅读上。
- 本 Skill 全部为 Python 3 标准库实现，无需 pip；OCR 引擎（平台 ocr-tool /
  tesseract）仅在提取原始文本层时需要，缺失时的处置见“异常与限制”。

## 操作步骤

1. `ls -R /input`；读 `case.json` 与 `task.md`，记录 `case_id` 与
   `output_contract` 字段。
2. 若案例只有扫描 PDF：先用平台 ocr-tool（或检测到的 `tesseract`）提取文本层，
   按页以 form feed (`\f`) 分隔，存为 `/app/work/raw_ocr.txt`。若已有 OCR 文本层，
   直接使用。
3. 扫描候选（不改文本）：
   `python3 scripts/confusion_scan.py --input /app/work/raw_ocr.txt --out /app/work`
4. 门控纠错：
   `python3 scripts/postcorrect.py --input /app/work/raw_ocr.txt --candidates /app/work/candidates.jsonl --out /app/work`
   （默认 threshold=high；确需放宽时加 `--aggressive` 应用 medium；low 永不应用。）
5. QC 与结果组装：
   `python3 scripts/ocr_qc.py --raw /app/work/raw_ocr.txt --corrected /app/work/corrected.txt --candidates /app/work/candidates.jsonl --change-log /app/work/change_log.jsonl --review /app/work/review_list.json --case /input/case.json --out /app/output`
   也可用 `scripts/run_pipeline.py --input ... --case ... --out ...` 一键串联。
6. 人工只核对 `review_list.json` 中的 deferred 项与 `qc_report.json` 的
   remaining_candidates；确认 `result.json` 的 `case_id` 与合同字段齐全后交付。

## 输出物说明

| 文件 | 生产者 | 内容 |
|---|---|---|
| candidates.jsonl | confusion_scan.py | 全部候选：page/line/col/span/suggestion/rule/confidence/reason；未做任何修改 |
| corrected.txt | postcorrect.py | 纠错后文本，分页 form feed 保留 |
| change_log.jsonl | postcorrect.py | 每一处已应用编辑：line, before, after, rule, confidence |
| review_list.json | postcorrect.py | 被暂缓/拒绝的候选及原因（precision-first 的证据） |
| qc_report.json | ocr_qc.py | 前后可疑词元率、按规则计数、剩余候选、逐行热度 |
| result.json | ocr_qc.py | case_id、合同字段回显、工具可用性 sources、uncertainty、change_record、status |

## 方法要点

- **数据驱动**：混淆模式全部在 `references/ocr-confusions.tsv`（35 条：
  char_in_word / seq_in_word / ligature_insert / space_merge / greek_latin /
  unreadable / standalone_confusable 七类），改表即改行为，无需动代码。
- **词典即证据**：候选只有在“原词不在词典且建议在词典中”时才成立
  （希腊字母与 unreadable 标记除外，二者由上下文门控）。这自动保护
  barn/kernel 等真 rn 词、C12/Fe2O3 等化学式。
- **门控分级**：high → 默认应用；medium → 仅 `--aggressive` 或
  `--threshold medium`；low → 永不改动，只进 review_list；多重词典命中 →
  自动降级 low 并标注 ambiguous。
- **绝不猜测**：符号乱码（如 `#7@z~`）标记为 `[unreadable]`，原串记入
  change_log，正文不保留也不臆造内容。
- **可度量**：QC 以前后可疑词元率（digit-in-word / 符号乱码 / 孤立 l·I·O /
  非词典词）量化收益。

## 异常与限制

| 情形 | 行为 |
|---|---|
| 无可用 OCR 引擎（无平台 ocr-tool、无 tesseract） | 本 Skill 不做 OCR；在 result.json 的 sources 中如实记录缺失，状态 partial，只交付合同说明并建议移交上游 OCR |
| 输入为空 / 无词元（疑似纯图像无文本层） | confusion_scan.py 退出码 3，stderr 说明；result.json 记 empty + explanation |
| CJK 文本混淆（形似汉字、全半角） | 本词典与规则面向英文科学文本；CJK 混淆在 result.json warnings 中标记，建议换用 CJK 词典，不强行纠错 |
| 严重退化扫描 | 候选变多但门控不变：更多 [unreadable]、更长 review_list，绝不放宽 low 门槛 |
| 纯图像表格 / 公式区 | 表格结构不在本 Skill 范围（不做版面分析）；表格内符号乱码只会被标记 |
| URL / 邮箱 / 化学式 | 含 @ # 等字符可能误中 unreadable 规则；化学式由大写+数字守卫排除，其余进 review_list 人工定夺 |

退出码约定（三个脚本一致）：0 = 正常；2 = 输入/用法错误（文件缺失、TSV 表头
不符等）；3 = 运行时失败（空输入、写出失败等）。

## 最小示例（合成数据）

`examples/minimal/` 内含 3 页**人工合成**的 OCR 文本（15 处人工植入错误），
以及真实运行三个脚本得到的全部输出。复现：

```bash
cd skill
python3 scripts/run_pipeline.py \
  --input examples/minimal/inputs/raw_ocr.txt \
  --case examples/minimal/inputs/case.json \
  --out examples/minimal/outputs
```

预期：16 个候选（13 high / 2 medium / 1 low）；默认门控应用 13 处（含 1 处
[unreadable] 标记），3 处进入 review_list；可疑词元率 0.1067 → 0.0201。
细节见 `examples/minimal/README.md`。**免责**：示例文本为演示而手写，不来自
真实扫描件。
