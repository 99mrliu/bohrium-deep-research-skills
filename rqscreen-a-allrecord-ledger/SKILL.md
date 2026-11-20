---
name: rqscreen-allrecord-ledger
description: 科研检索快照的"全记录筛查台账"引擎——对 /input 中给定检索快照(检索导出、参考文献清单、PDF 等)逐条解析、精确+模糊去重(显式识别夹具标注的合成重复)、按纳排条款逐条给出 include/exclude/uncertain 处置与可复算依据、对组织方给定的真实署名文献清单逐篇做归属核验(匹配/存疑/缺失+元数据一致性),并原样登记夹具中标注的冲突意见记录而不替其裁决,最终按 case.json 的 output_contract 生成 result.json。Use when a task gives a finite literature snapshot / search export (search09, RIS, BibTeX, CSV, JSON) plus a research question and asks for all-record screening, deduplication, attributed-paper verification, or a traceable candidate set (全记录筛查, 去重, 纳排台账, 归属核验, PRISMA 计数, 有限快照).
---

# 全记录筛查台账引擎（rqscreen-allrecord-ledger）

## 何时使用

案例输入是**有限快照**（检索导出 JSON/CSV/RIS/BibTeX、参考文献清单、任务说明），要求围绕研究问题完成文献筛查、去重、候选集与归属核验。核心判断：本题素材是"给定的快照"，不是全网；所有证据必须来自 `/input` 中的真实文件，**禁止联网补查、禁止凭空补文献**。

## 运行方式（一条命令 + 一次判断 + 收尾）

```bash
# 1) 一条命令: 清点输入→解析全部记录→去重→自动生成筛查条款草案→筛查→归属核验
python3 /skills/weekly-skill/scripts/run_all.py \
    --case /input/case.json --input-dir /input \
    --work /app/work --out /app/output

# 2) 唯一需要判断的步骤: 打开 /app/work/criteria.auto.json,
#    对照 task.md 的研究问题核对条款(年份窗、纳入词、排除词、文献类型、子问题词表),
#    修订后另存为 /app/work/criteria.json,然后:
python3 /skills/weekly-skill/scripts/screen.py \
    --work /app/work --criteria /app/work/criteria.json --out /app/output

#    对规则判不准的少数记录(≤10 条),逐条写 overrides.json:
#    [{"rid":"s09-005","disposition":"include","reason":"冲突意见记录,作为争议证据纳入","sq":"SQ-1"}]
#    带上 --overrides 重跑 screen.py 即可。

# 3) 收尾: 汇总 result.json(按 output_contract 补齐字段、诚实状态)
python3 /skills/weekly-skill/scripts/finalize.py \
    --case /input/case.json --input-dir /input --work /app/work --out /app/output
```

非平台环境把路径换成实际目录。**预算意识**：全程只有第 2 步需要模型判断（约 1–3 次模型请求），其余全部确定性脚本，900 秒预算绰绰有余；先把第 1 步跑完并确认 partial 产物存在，再做任何精修。

## 流水线（每步可独立重跑，产物可第三方复核）

1. **清点解析（ingest.py）**：递归扫描输入目录，按扩展名解析 JSON/JSONL/CSV/TSV/RIS/BibTeX/MD；JSON 中深度优先寻找记录列表（优先 `records/results/items/papers` 等键）。每条记录统一 schema 并保留 `origin_file!origin_row` 溯源与全部原始键。无法解析的文件逐条记入 `ingest_report.json` 的 failures，绝不静默丢弃。
2. **去重（dedupe.py）**：判定链按序执行——非空 DOI 相同 → 归一化标题完全相同 → 标题 token Jaccard ≥ 0.85。每对归并在 `duplicates.jsonl` 中记录 kept/dropped、方法与相似度。记录自带 `synthetic_duplicate`/`duplicate_of` 标记时原样保留并在输出中注明"输入夹具标记"。
3. **筛查条款（criteria）**：`run_all.py` 从 research_question 抽取年份窗与高频术语生成草案；Agent 的职责是**核对与修订**，不是从零撰写。条款与模板见 `resources/criteria_template.md`。
4. **逐条筛查（screen.py）**：年份窗 → 文献类型排除 → 排除词 → 纳入词最低命中数，规则全部可复算；命中 `subquestion_map` 的记录自动标注所属子问题。台账每行含：rid、disposition、reason_codes、命中词、子问题标注、夹具标记、原文片段、来源文件行号。附 PRISMA 式计数。
5. **归属核验（attest.py）**：自动在输入中定位署名文献清单（含 `papers/refs/references` 列表的 JSON），逐篇核验：DOI 精确 → 标题模糊（Jaccard）；给出 matched/ambiguous/missing 与元数据一致性核对（年份/期刊/第一作者不一致逐项列出）。夹具标注的冲突意见记录只**登记**关联关系，不裁决谁对谁错。
6. **收尾（finalize.py）**：汇总所有产物，按 `output_contract` 逐字段填充（填不了的留空容器并在 uncertainty 说明）；`status` 三值诚实标注；任何中断前先把已有产物落盘。

## 输入 / 输出

- 输入：`case.json`（含 `case_id`、`research_question`、`output_contract`）、`task.md`、快照导出与清单文件（以实际文件内容为准）。
- 输出（`/app/output`）：`result.json`、`ledger.jsonl`（逐条台账）、`screening_summary.json`（PRISMA 计数+条款留档）、`candidates.json`（纳入集）、`attribution.json`（归属核验）；`/app/work`：`records.jsonl`、`deduped_records.jsonl`、`duplicates.jsonl`、`ingest_report.json`、`criteria.auto.json`。

## 依赖与异常处理

- 仅 Python 3 标准库；无网络依赖；快照缺失某类文件时对应步骤如实输出（如无清单则 attribution 标 `no_reference_list`）。
- 输入目录不存在或 case.json 缺失：finalize 输出 `status=blocked` 的 result.json 并指明缺哪个文件，不猜测。
- 某文件解析失败：记入 failures，继续处理其余文件；记录数为零时在 uncertainty 中说明。
- 条款为空（无任何纳入词）：screen.py 全量标 `uncertain` 并提示必须先修订 criteria.json，不会产出虚假 include。

## 不适用边界

- 不做全网检索与跨库召回（本方向只处理给定快照；检索规划见其他方案）。
- 不做单篇精读、不做全文翻译与写作。
- 不替冲突意见做学术裁决：只登记、定位、提示人工复核。

## 最小调用示例（示意输出，非正式案例结果）

```bash
python3 /skills/weekly-skill/scripts/run_all.py --case /input/case.json --input-dir /input --work /app/work --out /app/output
# ingest: 15 条记录 / dedupe: 移除 2 条(1 条夹具标注合成重复) / criteria.auto.json 已生成
# screen: 纳入 7 / 排除 4 / 待复核 2 / attribution: 9 篇清单文献 匹配 7 存疑 1 缺失 1
python3 /skills/weekly-skill/scripts/finalize.py --case /input/case.json --input-dir /input --work /app/work --out /app/output
# result.json: status=partial(1 篇缺失已写入 uncertainty)
```

## 复用与维护

- 条款模板、台账 schema 见 `resources/`；把 criteria.json 换成其他问题的条款即可复用整条流水线。
- 版本：v1.0（2026-11，Python ≥ 3.8，stdlib only）。维护：随案例格式扩展在 ingest.py 的 PARSERS 注册表加解析器。
