---
name: provenance-anchor
description: 论文质量审查/事实核验技能——先建保真台账（SHA-256+抽取状态）再对每条 finding 的原文引用做确定性锚定复验，复验失败自动降级 pending_review；适用于需要可机器复核证据链的稿件审查与事实核验，不适用于润色、翻译、查重。
---

# provenance-anchor：锚定保真的论文质量审查

## 核心思想

审查结论必须锚定在可机器复验的原文证据上。工作分两阶段：

1. **先建保真台账**：对每个输入文件计算 SHA-256、记录抽取方式/字符数/抽取状态，
   并在第一次脚本调用就写出保底 partial result.json。
2. **再逐条锚定**：每条 finding 的 `original_text` 经空白归一化后必须在抽取文本
   全集中作为子串命中；命不中（或为空、或超 300 字）自动降级 `pending_review`
   并留痕。用工程手段杜绝"凭空结论"与"漏查静默跳过"。

## 适用边界

- **适用**：论文/报告质量审查、事实核验、需要"每条结论可复核、稿件版本可锚定
  （SHA-256）、partial 要标明限度"的场景。
- **不适用**：语言润色、翻译、查重/AI 率检测（无对应工具链，登记 unable_to_check）。
- DOCX 不抽取正文（记 `needs_office_tool`）；PDF 依赖 `pdftotext`，缺失则如实记
  `extract_error`。禁止编造文献主张、页码、DOI、结论、分数。

## 运行时契约

- 安装路径 `/skills/weekly-skill`；脚本以 `python3 /skills/weekly-skill/scripts/xxx.py` 调用。
- 输入 `/input/case.json`、`/input/task.md` 与材料文件（PDF/DOCX/MD/TXT/TeX）。
  case.json schema 未知：output_contract 宽容处理（list 取元素、dict 取键、
  缺失回退默认字段集 `["case_id","status","review_report","findings","sources","uncertainty","change_log"]`
  并在 uncertainty 说明）。
- 工作目录 `/app/work`；最终 `/app/output/result.json`（含原 case_id 与契约全部字段）
  + `/app/output/review_report.md`。
- 仅 Python 3 标准库；文本统一 `utf-8, errors=replace`；预算内第一次调用即出保底 partial。

## 分步工作流

设 `SKILL=/skills/weekly-skill`（本地验证时替换为本 bundle 绝对路径）。

### 第 1 步：保真台账 + 保底 partial（最先执行）

```bash
python3 $SKILL/scripts/source_inventory.py --input-dir /input --work-dir /app/work --out-dir /app/output
```

产物：`/app/work/inventory.json`、`/app/work/extracted/*.txt`、保底
`/app/output/result.json`（status=partial，契约字段 null + null_reasons）。

### 第 2 步：生成 finding 草稿模板

```bash
python3 $SKILL/scripts/anchor_verify.py scaffold --work-dir /app/work
```

### 第 3 步：Agent 撰写两个 JSON（人工/模型步骤，非脚本）

- 编辑 `/app/work/findings_draft.json`：逐条 finding，填
  `id/facet/severity/location/original_text/claim/basis`。
  `original_text` 必须**从 `/app/work/extracted/` 复制、逐字、≤300 字**
  （纪律见 references/false_quote_policy.md）。
- 新建 `/app/work/answers.json`：
  ```json
  {"status": "complete",
   "summary": "总体结论一段",
   "facet_status": {"事实核验": {"status": "issues_found", "notes": "..."},
                    "引用支持": {"status": "...", "notes": "..."},
                    "方法设计": {"status": "...", "notes": "..."},
                    "统计报告": {"status": "...", "notes": "..."},
                    "论证链":   {"status": "...", "notes": "..."},
                    "学术规范": {"status": "...", "notes": "..."}},
   "uncertainty": ["..."], "change_log": ["..."]}
  ```
  六分面中本技能深查"事实核验的证据保真"；其余五面按
  references/facet_coverage.md 最低检查点轮查并登记
  （checked_clean / issues_found / partially_checked / unable_to_check）。

### 第 4 步：锚定复验

```bash
python3 $SKILL/scripts/anchor_verify.py verify --work-dir /app/work
```

产物 `/app/work/anchor_report.json`：verified / not_found（含
`downgrade_to=pending_review` 与理由）。

### 第 5 步：组装最终结果

```bash
python3 $SKILL/scripts/build_result.py --work-dir /app/work --out-dir /app/output
```

产物：`/app/output/result.json`（契约字段齐全、诚实门、原子写入）与
`/app/output/review_report.md`。

### 可选：自检测试（演示引错原文被降级）

```bash
python3 $SKILL/scripts/anchor_verify.py --selftest
```

## 输出 schema

result.json：output_contract 全部字段（默认七字段）+
`null_reasons`（dict，字段名→原因）+ `facet_coverage`（六分面登记）+
`anchor_summary`（total/verified/not_found/downgraded_ids）+ `generated_at`。
finding 条目：`id, facet, severity, location, original_text, claim, basis,
status(confirmed/pending_review), anchor(verified/not_found), matched_file?,
downgrade_reason?`。

## 异常处置

| 异常 | 处置 |
| --- | --- |
| case.json 缺失/非法/output_contract 结构未知 | 回退默认字段集，uncertainty 留痕 |
| PDF 无 pdftotext 或抽取为空 | 记 extract_error + 原因，写入 uncertainty，不猜内容 |
| DOCX | 记 needs_office_tool，待外部抽取后复检 |
| finding 引文锚定失败/为空/>300字 | 自动降级 pending_review + downgrade_reason |
| answers.json 缺失 | 六分面全登记 unable_to_check，status=partial |
| 契约字段为 null 且无 null_reasons | 诚实门触发，status 强制 partial |
| 脚本失败 | 退出码非 0，原因打 stderr；保底 result.json 已在第 1 步落盘 |

## 文件清单

- `scripts/source_inventory.py`：台账 + 保底 partial
- `scripts/anchor_verify.py`：scaffold / verify / --selftest
- `scripts/build_result.py`：组装 + 诚实门 + 报告渲染
- `references/provenance_spec.md`：台账字段与锚定规则
- `references/facet_coverage.md`：六分面最低检查点
- `references/false_quote_policy.md`：引原文纪律
- `examples/`：合成示例（输入 + 真实跑出的输出 + findings/answers 示例）
