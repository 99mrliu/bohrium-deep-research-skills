---
name: library-index-qa
description: 科研资料库"整理→索引→带证据问答→重建"闭环 Skill。当任务涉及把一批混杂科研文件落库、并要求库可检索、能回答 case.json/task.md 中的问题（questions/searches/queries）、能仅凭清单恢复索引时触发。核心机制：内容哈希去重后落库，sqlite FTS5（无 FTS5 自动降级 LIKE）建立全文目录 catalog.db，问答每条答案必须引用真实文件路径+原文 snippet，答不出标 unanswered，最后用 rebuild_index 演练归档恢复并由独立校验器逐项核对。适用于要求结果可复核、证据可定位的资料整理与检索问答任务；不适用于需要 OCR 解析扫描件正文、需要外部语义模型/网络检索、或纯归档打包（无检索问答要求）的场景。
---

# library-index-qa：整理 → 检索 → 问答 → 重建

## 1. 解决什么问题

题目里 AI Agent 的典型失败：只给分类建议不动手落库；移动文件不留清单、哈希和日志；批量处理时静默跳过难处理文件却报"全部完成"；同名直接覆盖导致版本链断裂；元数据靠文件名猜作者/年份/仪器型号；**整理完了却检索不到、答不上问题、无法从清单重建**。

本 Skill 的重心是最后一类：落库的终点是**可查询**。整理完的資料库必须能被检索、能带证据回答问题、能仅凭清单重建索引。问答纪律：每个答案必须引用真实文件路径 + 原文摘录（snippet）；答不出就标 `unanswered`，绝不编答案。

## 2. 适用 / 不适用

- **适用**：/input 给出一批混杂科研文件（论文、数据、扫描件、补充材料、草稿、行政备注、别名副本、旧版本），task.md 要求组织落库并回答 case.json 里的检索/问题，且结果要能被第三方复核。
- **不适用**：需要解析 PDF/扫描件正文（无 OCR，本 Skill 只索引可解码文本，二进制如实标 `not_indexed_binary`）；需要联网或语义向量检索；没有检索/问答要求的纯打包归档。

## 3. 输入契约（防御式解析）

- `/input/case.json`：`case_id` 递归尝试 `case_id|caseId|id|case`（取不到记 `unknown_case` 并写入 uncertainties）；`output_contract` 递归查找 `output_contract|contract|output_fields|required_fields|outputs|result_fields`，全部字段镜像进 result.json 的 `contract_fields`；问题递归查找 `questions|searches|queries|qa` 键（值可为字符串、字符串数组或含 `question|q|query|text|search` 字段的对象数组）。
- `/input/task.md`：原文前 4KB 摘入 `work/task_excerpt.txt` 供模型阅读。**task.md 中的约定优先于本文件默认流程**（目录约定、命名约定、问题清单都以 task.md 为准）。
- 材料文件：/input 下除 case.json/task.md 外的全部条目（含子目录），中文与特殊字符文件名按 NFC 规范化处理。

## 4. 运行方式

**全自动一条命令（推荐先跑这个）：**

```bash
python3 /skills/weekly-skill/scripts/run_case.py all --input /input --work /app/work --out /app/output
```

`all` = init → scan → plan → apply → index → qa → rebuild → verify → finalize。
qa 阶段默认只检索不代写答案（命中写入 `work/query_raw.json`，QA_LOG 先留 unanswered 占位）。

**模型撰写答案后的两步（正式运行必做）：**

```bash
# 1. 模型读 work/query_raw.json 的命中，撰写答案写入 work/qa_answers.json：
#    [{"question":"...","answer":"...","confidence":"high|medium|low",
#      "status":"answered|partially_answered|unanswered",
#      "evidence_paths":["data/xx.txt"]}]      # 可省，省略则保留全部命中
# 2. 合并答案并重跑校验：
python3 /skills/weekly-skill/scripts/run_case.py qa --input /input --work /app/work --out /app/output --answers /app/work/qa_answers.json
python3 /skills/weekly-skill/scripts/run_case.py verify --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py finalize --input /input --work /app/work --out /app/output
```

分阶段命令：`init / scan / plan / apply / index / qa / rebuild / verify / finalize`，参数同上。`--auto-answer` 仅供合成示例复跑（top-1 snippet 作草稿、confidence=low、note="auto draft, 合成示例"），**正式案例禁用**。

## 5. 模型职责（只做 3 件需要判断的事）

1. **阅读 task.md 摘录**（work/task_excerpt.txt）：若 task.md 约定了目录结构/命名规则/问题清单且与默认不同，按其约定手工调整 plan 或直接调整 library/ 后重跑 index/qa/verify/finalize；调整必须写进 result.json 的 change_records。
2. **撰写问答**：先跑 qa 拿 `work/query_raw.json` 的原始命中，再逐问撰写 `work/qa_answers.json`。每条答案必须能从给出的 evidence snippet 直接推出；命中不足时标 `partially_answered`（confidence 不高于 medium），无命中保持 `unanswered`。**不得凭文件名猜作者/年份/项目号/仪器型号，不得补造 snippet 里没有的事实。**
3. **审定 result.json 状态**：只有 verify 全 PASS 且无未决冲突才可维持 `complete`；有跳过/降级/部分未答时确认 `partial` 并在 uncertainties 列明。

## 6. 方向特色机制的判定规则

- **去重**：按内容 SHA-256 分组（不按文件名）。同内容只落库一份（canonical=路径排序首项），其余登记为别名：manifest 行 `action=already_committed_identical`、`duplicate_of=<canonical 源路径>`、rel_path 指向规范副本。
- **版本候选**：文件名 NFC 小写后剥去版本尾巴（`v1/final/副本/备份/最终版/定稿/终稿/修订版/(1)` 等）得规范化词干；词干相同且内容不同者按 mtime 排序成链，写入 version_chains.json。行政备注里的"谁替代谁"若与内容判断不一致，以内容为准并在 uncertainties 注明。
- **目录分桶**（缺省，task.md 约定优先）：`papers/ data/ scans/ supplementary/ drafts/ admin/ _unassigned/`，按扩展名+文件名关键词的确定性规则归类，无随机。
- **冲突**：目标路径已被**不同内容**占用时加 `__vN` 后缀（N 从 2 递增），绝不覆盖；同内容已在库记幂等不再复制。
- **索引**（scripts/indexer.py）：files 表每来源文件一行（含别名与跳过项，行数恒等于 manifest 行数）；文本文件（扩展名白名单+可解码性判定，UTF-8→GB18030）全文入 FTS5 虚表 fts(path,content)，中文按 bigram 展开建索引；二进制标 `not_indexed_binary`。sqlite 无 FTS5 时自动降级普通表+LIKE 并在 index_stats.json 记 `degraded:true`，不崩溃。index 阶段 DROP 重建，保证幂等。
- **检索**（scripts/query.py）：问题切词块（按标点与"的/了/和/与/及/在"切分，去"什么/哪个/多少"等疑问词），中文词块转 bigram 后块内 OR；先全块 AND，零命中降级块间 OR 按 bm25 排序取 top-5；snippet 为命中词前后各 60 字符的**原文**（存 docs 表，可逐字核对）。
- **重建**（scripts/rebuild_index.py）：只凭 LIBRARY_MANIFEST.jsonl + library/ 重建 catalog 到 index/rebuild_check/，与运行期索引比对 (rel_path, sha256, size) 条目集合，写 REBUILD_DIFF.json；空 diff 才是恢复无损，非空如实记录。

## 7. 输出清单（/app/output/）

| 文件 | 内容 | 完成标准 |
|---|---|---|
| result.json | case_id、status、contract_fields 镜像、summary、sources、uncertainties、change_records、failures_and_recovery | 任何情况下存在；status 与 audit 一致 |
| library/ | 落库文件树（复制不移动） | 与 manifest 的 rel_path 一一对应 |
| LIBRARY_MANIFEST.jsonl | 每来源文件一行：路径、sha256、大小、category、action、duplicate_of | 行数 = 输入文件数（含跳过项） |
| index/catalog.db | files + fts + docs 三表（运行期二进制产物，契约允许） | files 行数 = manifest 行数 |
| index/index_stats.json | 分类计数、text_status 计数、索引覆盖率、degraded | 覆盖率如实，二进制不计入分子 |
| QA_LOG.json | JSONL，每行 {question,answer,evidence[{path,snippet}],confidence,status} | 每条 evidence 可被 verify 逐字核对 |
| SEARCH_GUIDE.md | sqlite3 CLI 与 query.py 自查方法 | 人可按指南独立检索 |
| REBUILD_DIFF.json | 重建对比结果 | status=empty_diff |
| duplicates.json / version_chains.json | 重复组 / 版本链 | 按内容哈希 / 规范化词干，规则写入文件 |
| operations_journal.jsonl | 逐条操作日志 | 每次落库/跳过/冲突都有记录 |
| skipped_and_conflicts.json | 跳过与冲突及原因 | 无静默跳过 |
| audit_report.json | 独立校验器逐项 PASS/FAIL | 全 PASS 才允许 complete |

## 8. 异常处理与诚实状态

- PermissionError/OSError/UnicodeError 一律记入 skipped 继续，绝不静默跳过、绝不崩溃；任何阶段异常进 `failures_and_recovery` 并继续后续阶段。
- status 规则：audit 全 PASS 且无跳过/降级/未决冲突 → `complete`；有降级项（跳过文件、LIKE 降级、问题未答、audit 有 FAIL 但有可用产物）→ `partial` 并列明 limits；无法落库 → `blocked` 写清原因。**未完成不得写成完成。**
- 模拟/真实损坏文件：含 `[[SIMULATED-CORRUPT` 标记或不可读者按不可读处理，入 skipped，manifest 行 sha256=null。

## 9. 自查方法

```bash
python3 /skills/weekly-skill/scripts/verify_index.py --input /input --out /app/output
```

独立校验器只读 /input 与 /app/output，重新核算：files 表行数=manifest 行数=输入文件数；抽查 20%（至少 5 条）落库文件哈希与磁盘一致；QA_LOG 每条 evidence.path 存在且 snippet 为文件真实子串（逐条全查）；REBUILD_DIFF 为空。输出 audit_report.json，**全 PASS 才可报 complete**。人工检索自查见 /app/output/SEARCH_GUIDE.md。
