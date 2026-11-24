---
name: version-lineage-rebuilder
description: 科研资料库版本世系重建 Skill。当任务给出混杂的科研文件（多版本报告、扫描件新旧件、改名备份、行政版本备注）并要求"整理文件，也保留版本关系"时触发。核心机制是三级证据世系图谱：E1 行政版本备注解析（locator=文件#行号）> E2 内容哈希别名判定 > E3 规范化词干+mtime 候选边，无证据不连边；别名（同内容）与版本（同词干不同内容）严格区分；成环/多父不强行断环，记冲突由模型落盘裁定。适用于有版本备注、同名多版、改名备份混杂的资料整理；不适用于纯无版本关系的扁平入库（此时所有文件按孤儿正常入库，仍可用），也不替代模型回答 task.md 中的检索/问题。
---

# version-lineage-rebuilder：版本世系图谱重建

## 1. 解决什么问题

科研资料整理最容易断链的一环：**谁替代了谁**。典型失败：

- 把 `report_v1.txt / report_v2.txt / report_最终版.txt` 当成三个无关文件平铺入库，版本关系丢失；
- 反过来，把两个不同项目的同名 `notes.txt` 误判为同一文件的两个版本；
- 把同内容不同名的别名（`data_copy.txt` ↔ `实验数据备份.txt`）当成两个版本或重复入库两份；
- 行政备注里白纸黑字写着"scan_final.pdf 替代 scan_old.pdf"，却只按文件名猜，连错边或不敢连边；
- 版本关系成环或多父时，工具悄悄断环/选边，事后无法复核。

本 Skill 的核心主张：**版本关系必须有证据基础，无证据不连边；每条边都能回查依据。**

## 2. 适用 / 不适用

- 适用：含多版本稿件、新旧扫描件、改名备份、行政版本备注的资料库整理；需要交付可复核世系图的任务。
- 不适用：纯扁平入库（世系图会退化为全孤儿，流程仍正确但无增益）；需要内容级 diff 的任务（本 Skill 只到"谁替代谁+size/mtime 差"，不做行级 diff）。

## 3. 输入契约

- `/input/case.json`：防御式解析。`case_id` 递归尝试 `case_id|caseId|id|case`，取不到记 `unknown_case` 并写入 uncertainties；`output_contract` 递归尝试 `output_contract|contract|output_fields|required_fields|outputs|result_fields`，字段名镜像进 `result.json.contract_fields`（能映射的给交付物相对路径，映射不了的给 `{"value": null, "reason": ...}`）。
- `/input/task.md`：原文摘入 `work/task_excerpt.txt`。**task.md 中的约定优先于本文件的一切默认流程**（包括桶目录、备注文件指定、命名方式）。task.md 可用"备注文件：xxx"显式指定备注文件。
- 材料文件：`/input` 下除 case.json/task.md 外的全部条目，递归扫描；含 `SIMULATED-CORRUPT` 头标记或不可读的文件记入 skipped，绝不静默跳过、绝不崩溃。

## 4. 运行方式

**全 auto 一条命令（优先用这个）：**

```bash
python3 /skills/weekly-skill/scripts/run_case.py all --input /input --work /app/work --out /app/output
```

分阶段（排查时用；每阶段幂等，可单独重跑）：

```bash
python3 /skills/weekly-skill/scripts/run_case.py init    --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py scan    --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py lineage --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py plan    --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py apply   --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py verify  --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py finalize --input /input --work /app/work --out /app/output
```

## 5. 模型职责（只做这 3 件需要判断的事，全部落盘留痕）

1. **裁定世系冲突**：当 `version_graph.json.conflicts` 出现 `cycle`（成环）、`multi_parent`（多父）、`multi_sink`、`unresolved_admin_reference`（备注指认解析不到文件）时，阅读 `LINEAGE_REPORT.md` 与备注原文，在 `work/lineage_overrides.json` 写裁定：
   ```json
   {"drop_edges": [["<src_sha或路径或文件名>", "<dst>"]],
    "add_edges": [{"src": "...", "dst": "...", "reason": "裁定理由"}]}
   ```
   然后重跑 `all`（幂等，只改受影响的边）。**不要**手改 version_graph.json。
2. **回答 task.md 中的检索/问题**：若 task.md 含问题，模型必须作答，把答案+证据路径写入 `/app/output/QA_LOG.json`（`{"question","answer","evidence_paths":[...]}`），并在 result.json 的 uncertainties 之外保持 status 如实。引擎只负责整理与世系，不替你答题。
3. **核对 contract_fields 映射**：result.json 里 `{"value": null, "reason": ...}` 的契约字段，按 task.md 判断对应哪个交付物，无法对应的在 uncertainties 说明。**不得凭文件名猜作者/年份/项目号/仪器型号等元数据**——metadata.csv 等伴随表有什么算什么，没有就标未知。

## 6. 特色机制：三级证据世系图（判定规则）

证据等级严格降级，**高等级优先，无证据不连边**：

- **E1 行政版本备注**（`basis=admin_note`）：扫描文件名含 `备注/notes/version/版本/行政/admin` 的文本（或 task.md 指定），逐行跑中英文句式正则（"X 替代 Y"、"X 作废，以 Y 为准"、"Y 已被 X 替换"、"X replaces/supersedes Y" 等，完整清单见 `references/admin_note_grammar.md`）。每条边记录 `locator=文件#行号` 与原文。E1 指认的文件对**即使词干不同也照连**（行政备注为准）；指认解析不到文件时记 `unresolved_admin_reference` 冲突，不猜。
- **E2 内容哈希相同 → 别名组**（aliases）：SHA-256 完全相同 = 同一内容的不同名字，**不是版本关系**。正本（文件名最短者）入库，别名只登记不复制。
- **E3 规范化词干分组**（`basis=stem_mtime`）：剥离 `_vN、_V N、最终版、定稿、副本、备份、.bak、~、尾日期 YYYYMMDD/YYYY-MM-DD、尾序号 (1)/(2)`（规则见 `references/stem_normalization_rules.md`）后词干相同 + 扩展名相同 + 内容不全同 → 候选版本组；组内按 mtime 排序，相邻连候选边，evidence 记 size_delta 与 mtime_delta。**备注类文件（notes/备注…）不参与 E3 分组**——这是防止两个项目各自的 notes.txt 被误判为版本的硬规则。
- **冲突处理**：E1 与 E3 方向矛盾时 E1 优先，被丢弃的候选边记入 conflicts（`e1_overrides_e3`，已自动解决，不降级）。环（DFS 检测）不强行断环，记 `cycle` 并降级 partial；多父记 `multi_parent` 降级 partial；二者都等模型按 §5.1 裁定。

边方向统一为 **旧 → 新（supersedes）**。链 = 弱连通分量 + 拓扑排序；链尾唯一无出边节点为 latest。

## 7. 落库策略与输出清单

落库：latest 以规范化名（词干+扩展名）入主目录桶；被替代版本保留原名进 `_versions/<链词干>/`；别名不重复入库；孤儿正常入库。缺省桶：`papers/ data/ scans/ supplementary/ drafts/ admin/ _unassigned/ _versions/`。复制不移动；目标被不同内容占用时自动 `__vN` 后缀并记录，绝不覆盖；重跑幂等收敛零新操作。

| 交付文件（/app/output/） | 内容 | 完成标准 |
|---|---|---|
| result.json | case_id、status、contract_fields 镜像、summary、limits、failures_and_recovery | status 与 audit 一致；全 PASS 且无未决冲突才 complete |
| library/ | 整理后资料库 | 与 LIBRARY_MANIFEST.jsonl 一一对应，哈希可复算 |
| LIBRARY_MANIFEST.jsonl | 每行一文件：sha256/size/mtime/stem + lineage 角色 | role ∈ latest/superseded/alias/orphan；alias 行 library_path=null 且带 alias_of |
| version_graph.json | 世系图：nodes/edges/aliases/chains/orphans/conflicts | 每条边有 basis 与 evidence；admin_note 边带 locator |
| LINEAGE_REPORT.md | 人读报告：每链一段、版本序列、逐边依据、latest 标注 | 与 version_graph.json 一致；每条边依据可查 |
| duplicates.json | 别名组（同内容不同名） | 与重算哈希组一致 |
| operations_journal.jsonl | 逐操作日志（copy/alias_record，含状态） | 已入库文件都有 copy 记录；重跑全为 already_committed_identical |
| skipped_and_conflicts.json | 跳过项 + 世系冲突 + 目标名冲突 | 所有 skipped 如实披露原因 |
| audit_report.json | 独立校验器 PASS/FAIL 逐项 | overall=PASS 才可报 complete |
| QA_LOG.json | task.md 问题的作答+证据路径 | 仅当 task.md 含检索/问题时由模型写 |

## 8. 异常处理与诚实状态

- 任何阶段异常：记入 `failures_and_recovery`，继续后续阶段，finalize 如实降级。**任何情况下都留下 result.json。**
- status 规则：audit 全 PASS 且无未决冲突 → `complete`；audit 有 FAIL 或有未决冲突（cycle/multi_parent/multi_sink/unresolved_admin_reference）或有阶段异常 → `partial` 并在 limits 列明；流程无法运行 → `blocked` 写明原因。已完成的不夸大，未完成的不写完成。
- 自动解决项（E1 覆盖 E3、`__vN` 改名、别名登记）不降级，但全部记录可查。

## 9. 自查方法

```bash
python3 /skills/weekly-skill/scripts/verify_lineage.py --input /input --out /app/output
```

校验器只读 /input 与 /app/output，独立重算哈希/词干/分组/边，回查 admin_note 边 locator 是否真实命中备注原文、链拓扑是否无未声明的环、manifest 与目录树是否一致。**overall=PASS 且 result.json.status=complete 才可收工**；否则按 §5 裁定后重跑。
