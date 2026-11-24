---
name: claim-citation-aligner
description: 引用与事实核验的"引用支持语义对齐"协议。当任务要求审查论文或科研材料中引用是否支持结论、识别"结论超出引文范围"的过度推断时使用。核心机制：把每个含引文的句子分解为原子子主张，构建"子主张 × 引文"对齐矩阵，逐格给出四态判定（supported / partially_supported / not_supported / undeterminable）与四维范围比对（人群、条件、因果强度、数量化）；配套 stdlib 脚本 citation_scan.py（正文引文标记与参考文献条目的机械对账：未解析标记、从未被引条目以退出码报警）与 matrix_check.py（矩阵完整性 + 摘录逐字性 + 判定词表校验，违例退出码 1）。判定规则见 references/verdict_rubric.md，分解协议见 references/decomposition_protocol.md。
---

# claim-citation-aligner：子主张×引文对齐矩阵审查

## 1. 定位与核心立场

本题的关键区分是"**引用存在**"与"**引用支持结论**"。基础 Agent 最常见的失败是看到句尾有 `[3]` 就默认支持。本 Skill 把引用支持判定做成一个**可机器对账的结构化过程**：

1. 每个含引文的句子先**分解为原子子主张**（一个句子可能含多个可独立真假的断言）；
2. 每个子主张 × 每个所引文献是一格矩阵，逐格判定四态并做**四维范围比对**；
3. 矩阵是交付物的一部分，由脚本校验完整性（每个引文标记至少一行、每个被引条目至少出现一次）、摘录逐字性（quote 必须是原文确切子串）与判定词表合法性——校验不过不能交付。

重心在**语义对齐质量**；但任务要求完整覆盖，第 5 节给出六类审查的最小执行要求，其中引用支持类 finding 必须全部来自矩阵格子，不允许矩阵之外的"印象式"判定。

## 2. 适用条件与不适用范围

适用：有明确正文引文标记（编号制 `[n]` 或作者-年份制）与参考文献列表的论文/综述/报告。材料可以是电子 PDF、扫描件（OCR 后）或纯文本。

不适用：论文润色、综述写作、数据分析建模；不替代作者对研究结论的判断。被引文献全文不可得时，判定依据限于条目元信息与宿主句语义范围的比对，且 verdict 只能是 `undeterminable` 或在明显范围错配时 `not_supported`/`partially_supported`，confidence ≤ medium（见判定规则 R5）。

## 3. 运行契约（Harbor）

- 输入 `/input/case.json`、`/input/task.md`；工作目录 `/app/work`；交付 `/app/output/`。
- `result.json` 含 `case_id` 与 case.json `output_contract`（或 `outputContract`/`outputs`）声明的**全部字段**——逐字段同名复制填充，无法填充的置 `null` 并在 `uncertainties` 说明，不得丢弃或捏造。
- 预算 64 次模型请求 / 900 秒 / 单次响应 ≤16384 token。脚本不占模型预算；每阶段落盘中途产物，可随时中断恢复；预算不足时诚实 partial（`status="partial"` + `unchecked_items`）。
- 禁止编造引文语义、被引文献内容、核验记录。读不到被引原文就明说"未核读原文"。

### 防御式输入解析

1. `case_id`：依次尝试 `case_id`/`id`/`caseId`；取不到用文件名并记入 `uncertainties`。
2. 材料路径：尝试 `paper`/`pdf`/`material`/`document`/`file`/`manuscript`（含一层嵌套）；否则在 `/input/` 按 `*.pdf → *.txt → *.md → *.html` 取第一个。
3. `task.md` 的具体审查面、finding 类型与证据要求**优先于本文件通用清单**。
4. 材料缺失 → `status="blocked"`，仍写出 result.json 与报告。

## 4. 工作流程

### 阶段 0：解析（脚本，0–1 次模型请求）

```bash
cd /app/work
python3 <SKILL_DIR>/scripts/ingest_pages.py <材料路径> pages.jsonl
```

pdftotext 优先（`-layout` 失败后原始模式），纯文本回退；扫描件用环境 OCR 工具；全部失败写 `ingest_meta.json` 的 `extract_status="failed"` 并转 blocked。

### 阶段 1：引文对账（脚本，0 次模型请求）

```bash
python3 <SKILL_DIR>/scripts/citation_scan.py --pages pages.jsonl --out citations.json
```

产出：参考文献条目表、正文每个引文标记的 `{mark, ref_ids, page, sentence, sentence_id}`、`unresolved_marks`（指向不存在条目的标记，如 `[9]` 但只有 6 条文献）、`uncited_refs`（从未被正文引用的条目）。`--strict` 时这两类非空即退出码 1；非 strict 模式只报告。未解析标记与从未被引条目分别进入 finding（规范问题，minor）。

### 阶段 2：子主张分解与矩阵填写（约 15–30 次模型请求）

对每个含引文标记的句子（`citation_scan` 已给出清单与 sentence_id），按 `references/decomposition_protocol.md` 分解为原子子主张，逐格填写 `alignment_matrix.jsonl`（每行一格）：

```json
{"sentence_id": "p2.S4", "sub_claim_id": "p2.S4.c1", "sub_claim": "子主张原文或精确转述", "quote": "宿主句中支撑该子主张的逐字片段", "ref_id": 3, "verdict": "supported", "scope_check": {"population": "match", "condition": "match", "causal_strength": "narrower_in_source", "quantification": "unclear"}, "basis": "判定依据：引文条目语义范围 + 是否核读原文", "confidence": "medium"}
```

判定四态与范围比对的规则严格按 `references/verdict_rubric.md`；核心信号是**结论超出引文范围**（over-claim）：宿主句在人群、条件、因果强度或数量化任一维上宽于来源所示范围，至少判 `partially_supported`。

预算控制：引文标记数 >25 时，优先覆盖方法、结果、讨论章节的标记与所有多文献标记；未覆盖的 sentence_id 写入 `unchecked_items`，矩阵仍是部分的但如实。

### 阶段 2.5：矩阵机检（脚本，0 次模型请求）

```bash
python3 <SKILL_DIR>/scripts/matrix_check.py --pages pages.jsonl \
    --scan citations.json --matrix alignment_matrix.jsonl --out matrix_report.json
```

校验：行 schema 齐全；verdict/scope 词表合法；`quote` 是宿主句所在页文本的逐字子串（折叠空白）；每个 citing sentence 至少一行；每个被引 ref_id 至少出现一次；sub_claim 非空且与 quote 不雷同（防止整句复制充数）。任一违例退出码 1，逐条修复或降级后才能交付；报告写入运行日志。

### 阶段 3：六类审查补全与交付（约 10–15 次模型请求）

引用支持类 finding 从矩阵格子落：凡 `partially_supported`/`not_supported` 至少 minor，`not_supported` 且该子主张是论文核心结论时 major 以上。其余五类按常规要点审查（事实核验、方法设计、统计报告、论证链、学术规范），每条 finding 带 locator + 逐字 quote + basis + severity + suggestion + recheck。交付 `/app/output/`：`result.json`（schema 见第 6 节）、`review_report.md`、`run_log.jsonl`、`evidence/`（citations.json、alignment_matrix.jsonl、matrix_report.json 副本）。

## 5. 异常处理

| 情况 | 处置 |
|-|-|
| 参考文献节定位失败 | 引用清单基于正文标记重建；矩阵 ref_id 用标记文本；声明限制 |
| 引文标记与条目编号对不上（unresolved） | finding（规范问题 minor）；这些标记的格子 verdict=undeterminable |
| 作者-年份制与编号制混用 | 记录为规范问题；按多数制式对齐 |
| 被引文献全文不可得 | 按 R5 限定 verdict 与 confidence；basis 写明"未核读原文" |
| 引文严重歧义（同一条目对应多个可能来源） | 标 待复核，给出候选与复核路径 |
| matrix_check 不通过 | 修复后重跑；预算耗尽则在 result.json 标 partial 并附 matrix_report.json |

## 6. result.json Schema

```json
{
  "case_id": "来自 case.json",
  "skill": "claim-citation-aligner",
  "status": "completed | partial | blocked",
  "coverage": {"事实核验": "checked", "引用支持": "checked", "方法设计": "checked", "统计报告": "checked", "论证链": "checked", "学术规范": "checked"},
  "alignment_summary": {"citing_sentences": 0, "matrix_rows": 0, "supported": 0, "partially_supported": 0, "not_supported": 0, "undeterminable": 0, "matrix_check_passed": true},
  "findings": [
    {"id": "F-01", "category": "引用支持 | 事实核验 | 方法设计 | 统计报告 | 论证链 | 学术规范",
     "issue_type": "事实错误 | 证据不足 | 规范问题 | 建议性意见",
     "severity": "critical | major | minor | advisory",
     "location": {"locator": "p.2 ¶4", "page": 2, "quote": "逐字摘录"},
     "claim": "被审查的子主张", "verdict": "一句话判定",
     "basis": "依据；引用支持类必须回指 matrix 行 id",
     "suggestion": "修改建议", "confidence": "high | medium | low",
     "recheck": "复核路径", "needs_human_review": false}
  ],
  "unchecked_items": [], "uncertainties": [],
  "artifacts": {"report": "review_report.md", "matrix": "evidence/alignment_matrix.jsonl", "log": "run_log.jsonl"}
}
```

## 7. 参考资料

- `references/verdict_rubric.md`：四态判定规则 R1–R6、over-claim 四维分类、严重度映射。
- `references/decomposition_protocol.md`：子主张分解协议（原子性、可判定性、不漏不重）。
- `examples/`：**合成示例**——含一个典型 over-claim（小鼠研究引为人类结论）与未解析标记；演示 citation_scan 与 matrix_check 的报警。
