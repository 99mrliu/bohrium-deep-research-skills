---
name: rqfind-snapshot-search
description: 有限文献快照上的"本地索引 + 受控术语扩展 + 可解释排序"检索引擎——对 /input 中的检索导出快照建立纯本地倒排索引（拉丁截尾 + CJK 二元组、字段加权），支持布尔/短语/分面（年份、文献类型）查询，每条候选输出按字段分解的命中词与文件行号定位，用受控预算的变体表做同义/缩写/拼写/连字符扩展以提升召回而不发散，并对组织方给定的署名文献清单做 top-k 排序审计；0 命中时如实输出 snapshot_empty 判定，绝不补造文献。Use when a task provides a finite local snapshot (search09 export, RIS/BibTeX/CSV/JSON) and requires traceable ranked retrieval, keyword/term expansion, facet filtering, per-record relevance evidence, or honest empty-result reporting (快照检索, 术语扩展, 相关性排序, 分面过滤, 排序审计, 空结果判定).
---

# 快照内检索排序引擎（rqfind-c-snapshot-search）

## 何时使用

案例输入是**有限快照**（检索导出、参考清单等本地文件），需要在快照内做检索、排序与证据定位。核心判断：不联网、不臆测快照外的世界；召回靠索引 + 受控术语扩展；排序的每一分都可复算。

## 运行方式

```bash
# 1) 一条命令: 建索引 → 从 case.json 派生初始查询组检索 → 排序审计
python3 /skills/weekly-skill/scripts/run_all.py \
    --case /input/case.json --input-dir /input --work /app/work --out /app/output

# 2) 视结果追加: 术语扩展(受控预算) → 对拆解出的每个子问题各执行一次检索
python3 /skills/weekly-skill/scripts/expand.py --terms "passivation,grain boundary,efficiency"
python3 /skills/weekly-skill/scripts/search.py --work /app/work \
    --query "grain boundary passivation" --query-zh "晶界 钝化" \
    --year-from 2022 --year-to 2025 --exclude-type "review,perspective" \
    --label "Q2-grain-boundary" --out /app/output

# 3) 排序审计(自动以署名清单为键,无清单则如实标 no_reference_list)与收尾
python3 /skills/weekly-skill/scripts/rankcheck.py \
    --work /app/work --out /app/output --search-dir /app/output --input-dir /input
python3 /skills/weekly-skill/scripts/finalize.py \
    --case /input/case.json --input-dir /input --work /app/work --out /app/output
```

**预算意识**：全部步骤为确定性脚本（0 次模型请求）；模型只用于第 2 步决定"还需要补哪些查询"（1–2 次请求）。先把第 1 步跑完保存 partial 产物。

## 方法与产物（每步可独立复算）

1. **建索引（index.py）**：递归解析 JSON/JSONL/CSV/TSV/MD/TXT 中的记录（记录列表自动探测），分词=拉丁保守截尾 + CJK 二元组，title/keywords/abstract 字段加权；输出 `index.json`（postings）与 `docstats.json`（df、文档元数据）。解析失败的文件逐条入 `index_report.json`，不静默丢弃。
2. **受控扩展（expand.py）**：`resources/variant_table.tsv` 人工词表优先，拼写/连字符/缩写规则次之；每词变体数有硬预算（默认 4），未命中不扩展——防止同义词发散把查询带离主题。
3. **检索（search.py）**：`+`必须/`-`排除/引号短语/OR 加权；年份与类型为硬过滤；打分=字段加权词频×IDF（公式与参数见 `resources/scoring.md`，可复算）。每条候选输出：score、matched_terms（按字段）、facet_check、夹具标记（conflicting_opinion/synthetic_duplicate 原样保留）、origin（文件!行号）。
4. **排序审计（rankcheck.py）**：自动在输入中定位署名文献清单，计算各查询的清单文献命中率@top-5；某查询 0 命中 → `verdict=snapshot_empty`（如实说明"快照无法覆盖该查询"），**不补造文献**。
5. **收尾（finalize.py）**：合并各查询结果按分去重排序，按 `output_contract` 生成 `result.json`（含 status/uncertainty/sources）；0 命中与索引缺失都会反映为 partial/blocked。

## 输入 / 输出

- 输入：`case.json`（research_question、constraints、output_contract）、快照导出文件。
- 输出（`/app/output`）：`result.json`、`search_<label>.json`（每组查询逐条候选+依据）、`rank_audit.json`；`/app/work`：`index.json`、`docstats.json`、`index_report.json`。

## 依赖与异常处理

- 仅 Python 3 标准库；无网络。输入目录不存在 → run_all 报错退出，finalize 输出 `status=blocked`。
- 快照记录数为 0 → index 正常完成（0 文档），search 返回 0 命中 + snapshot_empty，finalize 标 partial 并在 uncertainty 说明。
- 同一 rid 重复出现时自动加 `#dup` 后缀，防止静默覆盖；夹具标记不参与打分。

## 不适用边界

- 不做问题拆解（属规划方向）、不做全记录去重与纳排台账（属筛查方向）；本方向消费快照并产出排序候选。
- 索引不含全文语义向量；需要语义级模糊匹配时应在 uncertainty 中如实标注局限。

## 最小调用示例（示意输出，非正式案例结果）

```bash
python3 .../run_all.py --case /input/case.json --input-dir /input --work /app/work --out /app/output
# [index.py] rc=0 {"ok": true, "docs": 15, "vocab": 412, "failures": 0}
# [search.py] rc=0 {"ok": true, "label": "Q1-main", "returned": 7, ...}
# [rankcheck.py] rc=0 {"ok": true, "searches": 1, "empty_verdicts": 0}
python3 .../search.py --work /app/work --query "+perovskite passivation -photocatalysis" \
  --label Q2 --out /app/output --year-from 2022 --year-to 2025
python3 .../finalize.py --case /input/case.json --input-dir /input --work /app/work --out /app/output
# {"ok": true, "status": "complete", "candidates": 9, ...}
```

## 复用与维护

- 换课题：改 `--terms`、查询与分面即可；词表可在 `resources/variant_table.tsv` 增补（每行规范词+变体）。
- 版本：v1.0（2026-11，Python ≥ 3.8，stdlib only）。
