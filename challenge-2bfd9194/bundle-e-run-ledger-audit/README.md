# run-ledger-audit

科研资料库整理 skill，重心是**过程质量控制与可复跑审计**：每次复制走 WAL 两段式提交并留
journal，独立审计器逐项 PASS/FAIL，replay 脚本仅凭 journal 在空目录复放全部操作并与
library/ 逐字节比对。审计不过，status 绝不报 complete。

## 运行

```
python3 scripts/run_case.py all --input /input --work /app/work --out /app/output
```

一条命令跑完 init → preflight → scan → plan → apply → replay → verify → finalize。
分阶段命令与模型介入点见 SKILL.md §4/§5。

## 脚本

| 脚本 | 作用 |
|---|---|
| scripts/run_case.py | 八阶段编排器，防御式解析 case.json，异常全留痕 |
| scripts/journal_exec.py | WAL 引擎：begin→staging→哈希校验→os.replace→done；启动 reconcile |
| scripts/audit_run.py | 独立审计器（不 import 业务脚本），A–E 五项检查 |
| scripts/replay.py | 仅凭 journal 复放，产物与 library/ 比对写 REPLAY_DIFF.json |

## 输出（/app/output/）

result.json、library/、LIBRARY_MANIFEST.jsonl、PREFLIGHT.json、operations_journal.jsonl、
AUDIT_REPORT.json、REPLAY_DIFF.json、duplicates.json、version_chains.json、
skipped_and_conflicts.json（task.md 含问题时另有 QA_LOG.json）。replay 复放产物放
/app/work/replay，不进 output，避免双倍体积。

## 限制

- 仅 Python 3 标准库，无网络访问，不修改 /input，不复制 /input 之外的路径。
- 去重按内容 SHA-256：同内容别名默认不重复入库（manifest 记 duplicate_alias 回指 canonical）；
  若 task.md 要求保留全部副本，先改 work/plan.json 再 apply。
- 版本链 latest_by_mtime 仅是推断，版本取舍以 task.md 或行政备注为准。
- 桶归类是确定性规则（见 SKILL.md §6），特殊归类约定由 task.md 覆盖。

## 示例

examples/ 下是**合成示例**（非正式案例结果）：synthetic-input 为 12 个极小合成文本，
synthetic-output 为本地真实跑出的输出。复跑方法见 examples/README.md。
