---
name: run-ledger-audit
description: 面向科研资料库整理的"运行台账审计"skill。触发条件：需要把 /input 混杂资料整理进 /app/output/library，并要求整理过程本身可复核、可复跑（谁动了什么文件、何时、结果哈希是否一致）。核心机制：WAL 两段式提交 journal（begin→staging→哈希校验→os.replace→done）、启动 reconcile 清理崩溃残留、独立审计器逐项 PASS/FAIL、仅凭 journal 的 replay 复放比对。适用：需要强过程证据、可第三方复跑的整理任务。不适用：纯内容取证/全文抽取、元数据著录规范化、大规模索引检索（那些是其他方向）；也不处理 /input 之外路径的复制。
---

# run-ledger-audit：过程质量控制与可复跑审计

## 1. 解决什么问题

资料整理任务里最常见的失败不是"没整理"，而是**无法证明整理做对了**：

- 复制中断留下半截文件，后续步骤在坏数据上继续，无人察觉；
- 日志只有"完成"两个字，第三方无法核对每个文件的来龙去脉；
- 同名冲突被静默覆盖，旧版本永远丢失；
- 重跑脚本结果漂移，这次和上次产物对不上；
- `result.json` 写了 `complete`，但没有任何逐项证据支撑。

本 skill 的主张：**整理动作做对不算完，第三方仅凭日志与清单能独立复跑并逐条核对才算完。**
因此运行本身被设计成证据：每一次复制都是 WAL 两阶段提交并留 journal；独立审计器（不 import
任何业务脚本）只读输入与输出重新核算；replay 脚本仅凭 journal 在空目录复放全部操作并与
library/ 逐字节比对。**审计不过，status 绝不报 complete。**

## 2. 适用 / 不适用

适用：需要可复核、可复放过程证据的资料库整理；有中断恢复风险的批量复制；需要向第三方
（评审、合作者）证明"产物与记录一致"的场景。

不适用：深度内容取证与引用核对、元数据 schema 著录、全文索引与检索系统构建；不会复制
/app/input 之外的路径（case.json 引用外部路径会记入 skipped 并留 uncertainty）。

## 3. 输入契约（防御式解析）

- `/input/case.json`：`case_id` 递归尝试 `case_id|caseId|id|case`，取不到记 `unknown_case`
  并写入 uncertainties；`output_contract` 递归查找
  `output_contract|contract|output_fields|required_fields|outputs|result_fields`，全部字段名
  镜像进 `result.json.contract_fields`（字段 → 交付物相对路径；映射不了给
  `{"value": null, "reason": ...}`，绝不硬编）。
- `/input/task.md`：原文摘入 `/app/work/task_excerpt.txt`。**task.md 中的约定优先于本文件
  的一切默认流程**（类别桶、去重策略、版本取舍都先看 task.md）。若 task.md 含检索/问题
  （含 `?`/`？` 的行），init 会自动生成 `QA_LOG.json` 骨架，模型必须作答（见 §5）。
- 材料文件：/input 下除 case.json/task.md 外的全部条目。扫描时 PermissionError /
  UnicodeError / OSError 一律记入 skipped 继续，绝不静默跳过、绝不崩溃。文件名比较用 NFC。

## 4. 运行方式

**全 auto（首选，一条命令跑完全部八个阶段）：**

```
python3 /skills/weekly-skill/scripts/run_case.py all --input /input --work /app/work --out /app/output
```

分阶段（需要人工介入或排障时）：

```
python3 /skills/weekly-skill/scripts/run_case.py init      --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py preflight --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py scan      --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py plan      --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py apply     --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py replay    --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py verify    --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_case.py finalize  --input /input --work /app/work --out /app/output
```

各阶段产物：init→result.json 首版；preflight→PREFLIGHT.json；scan→duplicates.json +
version_chains.json；plan→work/plan.json；apply→library/ + LIBRARY_MANIFEST.jsonl +
operations_journal.jsonl + skipped_and_conflicts.json；replay→REPLAY_DIFF.json（复放产物在
/app/work/replay，不进 output）；verify→AUDIT_REPORT.json；finalize→result.json 定稿。

## 5. 模型职责（只做这 3 件需要判断的事，全部落盘留痕）

1. **读 task.md 裁定归类与版本取舍**：默认桶是
   `papers/ data/ scans/ supplementary/ drafts/ admin/ _unassigned/`。若 task.md 另有约定，
   在 plan 之后、apply 之前编辑 `/app/work/plan.json`（改 `dst` 即可），再跑 apply。
   apply 不会覆盖你的改动（它只按 plan 执行）。
2. **作答 QA_LOG.json**：task.md 含检索/问题时，把答案与证据路径（library 内相对路径）填进
   QA_LOG.json 的 `answer`/`evidence_paths`，然后重跑一次 `finalize` 刷新 status。
   答案必须有证据文件支撑；不得凭文件名猜作者/年份/项目号/仪器型号。
3. **处置审计 FAIL 项**：AUDIT_REPORT.json 有 FAIL 时，按 references/audit_checklist.md
   的处置表修复（通常是重跑 apply 让 reconcile 收尾，或补跑缺失阶段），修完重跑
   verify + finalize。修不了就保持 partial 并写清 limits，**不得把未完成写成完成**。

## 6. 特色机制判定规则

- **PREFLIGHT**：盘点文件数/字节/目录深度分布/不可读清单；`shutil.disk_usage` 取磁盘余量；
  风险清单含 >100MB 大文件、深度 >8、特殊字符名（非 NFC、控制字符、`:*?"<>|`、结尾空格/点）。
  **磁盘余量 < 总量×1.2 → status=blocked 并写明原因，不执行后续整理。**
- **WAL 两段式提交**：每次复制 = append begin（含 sha256_src）→ 复制到 work/staging →
  重算 staging 哈希，一致才 `os.replace` 原子改名 → 重算最终哈希 → append done
  （含 sha256_dst）。任何失败 append failed。journal 每行带单调 seq 与 UTC ISO 时间，
  格式见 references/journal_format.md。
- **reconcile**：apply 启动时先扫 journal，begin 无 done/failed/reconciled 闭合 → 删除
  staging 残留并 append reconciled。中断后重跑永远从干净状态继续。
- **去重**：按内容 SHA-256 分组；同内容别名不重复入库，manifest 记
  `duplicate_alias` 并回指 canonical 的 dst。
- **版本链**：规范化词干（剥离 `_vN/_final/最终版/定稿/日期/副本` 等后缀）相同但内容不同
  → 版本候选链，写入 version_chains.json；`latest_by_mtime` 仅为推断，取舍以 task.md 或
  行政备注为准。
- **冲突**：目标已被不同内容占用 → 自动 `__vN` 后缀并记入 skipped_and_conflicts.json，
  绝不覆盖。
- **幂等**：目标已存在且哈希一致 → `already_committed_identical`，不复制、不追加 journal；
  重跑收敛零操作。
- **审计不过不报完成**：finalize 仅在 AUDIT 全 PASS 且 REPLAY_DIFF.equal=true 且无未作答
  QA 时报 complete；否则 partial 并列 limits；无法运行报 blocked。

## 7. 输出清单（/app/output/）

| 文件 | 内容 | 完成标准 |
|---|---|---|
| result.json | case_id、status、contract_fields 镜像、sources、uncertainties、change_records、failures_and_recovery、summary | status 与 AUDIT/REPLAY 证据一致；contract 字段全部有镜像 |
| library/ | 整理后资料库（类别桶子目录） | 每个文件都能回指 journal done 且哈希一致 |
| LIBRARY_MANIFEST.jsonl | 每行一个 input 文件的去向（src/dst/sha256/action/journal_done_seq） | input 每文件有且仅有一条记录 |
| PREFLIGHT.json | 输入盘点、磁盘余量、风险清单、阻断原因 | 磁盘不足时 status=blocked 且有原因 |
| operations_journal.jsonl | WAL 台账（begin/done/failed/reconciled，带 seq+ts） | 每条 begin 有闭合；无坏行 |
| AUDIT_REPORT.json | 独立审计 A–E 逐项 PASS/FAIL | 全 PASS 才可 complete |
| REPLAY_DIFF.json | 仅凭 journal 复放产物与 library/ 的比对 | equal=true |
| duplicates.json | 内容哈希重复组（canonical/aliases） | 组内文件真实存在 |
| version_chains.json | 词干版本候选链 | 成员真实存在，取舍依据已注明 |
| skipped_and_conflicts.json | 跳过项（含原因）与冲突改名记录 | 无静默跳过，每条有 reason |
| QA_LOG.json | task.md 检索/问题的作答与证据路径（仅在有问题时生成） | 每问有 answer+evidence_paths |

## 8. 异常处理与诚实状态规则

- 每个阶段的异常都捕获进 `failures_and_recovery` 并继续后续阶段；**任何情况下
  result.json 都存在**（init 在数秒内写出首版）。
- status 判定（finalize 统一收口）：AUDIT 全 PASS + REPLAY equal + QA 已答 + 无 failed
  未恢复 → `complete`；有降级项 → `partial` 并在 limits 逐条列明；preflight 阻断或无法
  运行 → `blocked` 并写明原因。
- 模拟损坏/不可读文件不进入 library，记 `skipped_simulated_corrupt` / `skipped_unreadable`，
  在 manifest 与 skipped_and_conflicts.json 中都留痕。
- 禁止出现"全部完成"而无逐条证据的表述；journal、manifest、library 三者必须互相印证。

## 9. 自查方法

```
python3 /skills/weekly-skill/scripts/audit_run.py --input /input --out /app/output
python3 /skills/weekly-skill/scripts/replay.py --journal /app/output/operations_journal.jsonl \
    --input /input --out /app/work/replay --library /app/output/library \
    --diff-out /app/output/REPLAY_DIFF.json
```

AUDIT_REPORT.json `overall=PASS` 且 REPLAY_DIFF.json `equal=true` 且 QA_LOG 无 pending，
才允许把 result.json 写成 `complete`；否则保持 `partial` 并说明 limits。审计器与 replay
都是独立脚本（不 import 业务代码），可作为第三方核对工具直接交给评审复跑。
