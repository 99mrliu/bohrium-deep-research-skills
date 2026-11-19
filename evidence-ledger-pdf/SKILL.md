---
name: evidence-ledger-pdf
description: 深度研究的"证据回链"守门员——对案例提供的 PDF 逐篇本地解析（pdftotext，无预提取答案层），建立带页码与字符偏移的语料索引；所有证据条目必须保存逐字引用块（verbatim quote），每条综合结论必须通过归一化匹配在语料中找回其引用块后才允许标 verified；未通过的结论句强制降级为"无法核验"并出具回链率报告，从机制上消除"结论句找不到对应文献段落"。Use when a task provides research papers/PDFs and asks for a literature review, evidence synthesis or source-grounded conclusions where every claim must be traceable to an exact passage (证据回链, 引用核验, PDF 解析, 证据表, claim-evidence binding, quote verification).
---

# 证据回链核验器（evidence-ledger-pdf）

## 何时使用

案例附带一篇或多篇 PDF 文献（或其他材料文件），要求基于这些材料形成综述、筛选或综合结论时，使用本 Skill。典型平台场景：`/input/case.json` + `/input/task.md` + `/input/*.pdf`，结果写入 `/app/output`（含遵守 `output_contract` 的 `result.json`）。本 Skill 的核心增益在证据侧：每条结论强制绑定一段可在原文中逐字找回的引用，回链率可计算、可复核，冲突与空白都以"引用是否找回"为客观基础。

## 运行方式（三步）

```bash
# 1) 解析全部 PDF，建立带页码/偏移的语料索引（先产出 partial result.json）
python3 /skills/weekly-skill/scripts/run_case.py \
    --case /input/case.json --input-dir /input \
    --work /app/work --out /app/output

# 2) 逐条录入证据（Agent 从解析文本中复制逐字引用块，脚本负责定位与编号）：
python3 /skills/weekly-skill/scripts/ledger.py add \
    --ledger /app/output/evidence_ledger.json \
    --doc paper1.pdf --page 3 \
    --quote "the capacity retention reached 91.2% after 500 cycles" \
    --sq SQ-2 --field 效应方向与量级 \
    --note "图4b 对应结论"

# 3) 录入结论并强制过引用核验门，生成回链率报告：
python3 /skills/weekly-skill/scripts/claims.py add \
    --claims /app/output/claim_register.json \
    --claim "界面改性使循环寿命提升一倍以上" --strength inference \
    --evidence EV-0003,EV-0007
python3 /skills/weekly-skill/scripts/verify.py \
    --out /app/output            # 重算每条 claim 的 quote_check 与回链率
python3 /skills/weekly-skill/scripts/finalize.py \
    --case /input/case.json --work /app/work --out /app/output
```

## 流水线做了什么（每步都可重跑）

1. **语料解析（run_case.py → pdfindex）**：发现 input 目录全部 PDF；优先调用 `pdftotext -layout`（每页以 \f 分隔），不可用时回退 Python 纯文本读取；逐页建立 `{doc_id, page, char_start, char_end, sha256}` 索引写入 `corpus_index.json`，并保存每页纯文本快照到 `/app/work/corpus_pages/`（供后续步骤直接 grep，不再重复解析）。PDF 加密、损坏或解析为空时如实记 `parse_errors`，绝不假装解析成功。
2. **证据账本（ledger.py）**：每条证据 = 逐字引用块 + 文档 + 页码 + 绑定子问题 + 提取字段 + 录入方式。引用块必须通过"归一化精确匹配"在语料中定位（归一化 = Unicode NFKC + 折叠空白 + 去连字符断词）；定位失败的录入直接拒绝并要求修正——账本里没有"大概在这篇"的证据。
3. **结论登记与核验门（claims.py + verify.py）**：每条结论带强度标签（`fact`=材料直接陈述 / `inference`=跨证据推断 / `unknown=无法确定`）。核验门对每条结论的所有证据重跑引用定位，输出三态 `quote_check`：`verified`（全部引用找回）、`partial`（部分找回）、`quote_not_found`。`quote_not_found` 的结论强制移出正文结论区、降级为无法确定，并在 `backlink_report.json` 留痕。回链率 = verified 结论数 / 结论总数，与逐结论清单一并出具。
4. **综合与边界（finalize.py）**：生成 `synthesis.md`——正文每条结论句内联 ⟦EV-xxxx⟧ 锚点；冲突证据段只收录引用均已核验的冲突对；研究空白段要求每句空白判断附"检索/阅读范围"依据（哪些页、哪些关键词未见）。result.json 的 `status` 只有在核验门全部通过且六个评分面齐备时才写 `success`。

## 输入 / 输出

- 输入：`case.json`（含 `case_id`、`output_contract`）、`task.md`、PDF 等材料文件（以实际文件为准）。
- 输出（`/app/output`）：`result.json`（遵守 `output_contract` + 原始 `case_id`，含诚实 `status`/`sources`/`uncertainty`）、`corpus_index.json`、`evidence_ledger.json`、`claim_register.json`、`backlink_report.json`（回链率与逐结论核验结果）、`synthesis.md`、`parse_report.json`、`run_manifest.json`。

## 依赖与异常处理

- 依赖 Python 3 标准库；`pdftotext` 可用时优先（poppler），缺失自动回退并记录。
- PDF 解析失败/加密/为空：进入 `parse_errors` 与 `uncertainty`，相应文档的所有结论最高只能标 `partial`。
- 证据引用块在语料中定位不到：录入被拒绝（ledger add 返回定位失败与最相近片段），不允许含糊入库。
- 结论引用了不存在的证据号：核验门报错并拒绝 finalize 成功状态。
- 无任何 PDF 材料：脚本不虚构语料，result.json 直接 `blocked` 并说明缺什么。
- result.json 从第 1 步起存在；任何中断都留下已解析的语料索引与部分账本。

## 不适用边界

- 不做翻译、润色或逐句精读评述；不审查文献方法学质量（相邻课题）。
- 只覆盖输入材料实际包含的文献；超出材料范围的结论必须标 `unknown` 并说明"未检索/未提供"。
- 不预制答案；账本与结论全部由本次解析与录入产生。

## 复跑方法

在任意机器上重跑第 1、3 步命令：语料索引由 PDF 重建（哈希一致即证明材料未变），核验门重算的回链率与提交的 backlink_report.json 一致即证明结论-引用绑定未被事后修改。

## 最小调用示例（示意输出，非正式案例结果）

```bash
python3 /skills/weekly-skill/scripts/run_case.py --case /input/case.json \
  --input-dir /input --work /app/work --out /app/output
# {"ok": true, "pdfs": 2, "pages": 18, "parse_errors": []}      ← 示例值
python3 /skills/weekly-skill/scripts/ledger.py add --ledger /app/output/evidence_ledger.json \
  --doc paper1.pdf --page 3 --quote "capacity retention reached 91.2%" \
  --sq SQ-2 --field 效应方向与量级
# {"ok": true, "evidence_id": "EV-0001", "locate": "hit@paper1.pdf:p3+108"}  ← 示例值
python3 /skills/weekly-skill/scripts/claims.py add --claims /app/output/claim_register.json \
  --claim "界面改性显著提升循环寿命" --strength inference --evidence EV-0001
# {"ok": true, "claim_id": "CL-001"}                            ← 示例值
python3 /skills/weekly-skill/scripts/verify.py --out /app/output
# {"ok": true, "claims": 1, "verified": 1, "backlink_rate": 1.0} ← 示例值
python3 /skills/weekly-skill/scripts/finalize.py --case /input/case.json \
  --work /app/work --out /app/output
```

以上输出为接口示意；正式运行以平台 3 个固定案例的实际解析与核验为准。
