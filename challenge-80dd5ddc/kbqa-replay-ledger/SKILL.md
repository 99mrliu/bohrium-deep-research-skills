---
name: kbqa-replay-ledger
description: 科研知识库问答的"过程质量控制与可复核交接"工作流——以哈希链 append-only 操作日志记录每一步扫描/检索/跳过/决定/核验（含操作对象的 SHA-256 版本坐标），用独立审计脚本核对日志完整性、输入全覆盖（没被日志触及的文件即未检查）与阶段齐备，用合同自检脚本在交付前重新核对 result.json 与 output_contract 逐字段一致并回验全部引文坐标，最后生成带交付物哈希清单的第三方重走包；任何一项审计不通过，result.json 只能是 partial。Use when a task over a scientific document library demands auditable process, replayable handover, honest partial results and verifiable deliverables (过程可复核, 操作日志, 证据回链, 交接, 自检, 诚实 partial, /input/case.json, result.json).
---

# 过程质量控制与可复核交接（kbqa-replay-ledger）

重心在**过程侧**：答案对不对由内容决定，过程信不信由日志决定。本 Skill
把"换一个人拿着记录能否重走一遍"做成机器可判的硬指标：哈希链日志 +
输入覆盖审计 + 合同自检 + 重走包。它包装而不是替代具体问答逻辑——问答
本身按题目要求做，本 Skill 负责让全过程可复核、失败可定位、交付可核验。

## 何时使用 / 不适用

适用：`/input/case.json` + `/input/task.md` + 资料库的整理/问答任务，
评分或场景要求过程可复核、跳过与失败留痕、诚实 partial、第三方交接。
不适用：一次性单文件问答且无任何复核要求的场景（开销大于收益）。

## 运行时合同

1. 先读 `/input/case.json`、`/input/task.md`：case_id、问题、output_contract。
2. 工作区 `/app/work`（journal.jsonl 在此）；交付 `/app/output`：
   result.json、audit_report.json、selfcheck_report.json、replay/。
3. 预算 64 次模型请求 / 900 秒：日志/审计/自检都是确定性脚本；
   **第 1 步即落骨架 result.json（status=partial）**，finalize 时且仅当
   两份审计报告全过才允许改 completed。

## 工作流（$SKILL=/skills/weekly-skill）

```bash
SKILL=/skills/weekly-skill

# 0) 初始化日志（任何实质操作之前）
python3 $SKILL/scripts/oplog.py init --work /app/work

# 1) 每个实质操作后追加日志（示例）：
python3 $SKILL/scripts/oplog.py append --work /app/work --op scan \
    --detail '{"files": 12, "unreadable": 1}'
python3 $SKILL/scripts/oplog.py append --work /app/work --op search \
    --detail '{"query": "界面阻抗 60", "hits": 2}'
python3 $SKILL/scripts/oplog.py append --work /app/work --op read \
    --file /input/reports/a.txt
#    跳过与失败同样必须记录：--op skip / --op error

# 2) 完成问答与产物后：封口 → 审计 → 自检 → 重走包
python3 $SKILL/scripts/oplog.py seal --work /app/work
python3 $SKILL/scripts/journal_audit.py --input /input --work /app/work --out /app/output
python3 $SKILL/scripts/selfcheck.py    --input /input --work /app/work --out /app/output
python3 $SKILL/scripts/replay_pack.py  --work /app/work --out /app/output
```

审计或自检不通过：修问题（补日志、补覆盖、修 result.json），改完重新
append（含一次新 seal）再审计；**不得为通过审计而删改历史日志**——哈希链
会让删改现形。日志格式与最低齐备性见 references/journal_contract.md。

## 与其他流程的组合

本 Skill 不规定怎么检索、怎么引证，只规定"每一步都要留痕、交付前必须
过两道机器闸门"。若任务要求逐字引文，引文坐标按 [Fxx|sha8|La-Lb]"引文"
形态写入 result.json，selfcheck.py 会自动回验；若另有索引文件
（kb_index.json / suff_index.json / catalog.json 任一），自检自动接入。

## 异常与失败处置

日志未 init 就 append → 脚本拒绝并提示；日志链断裂 → append 拒绝，
只能以断裂点为事实写 error 说明（不得重造历史）；文件不可读 → 记 skip
并继续；预算耗尽 → 立即 seal + 审计 + 以 partial 收尾，未完成项写
uncertainty。所有脚本 exit 0（oplog 对非法操作返回 2 但不崩溃）。

## 自查清单

按 references/handover_checklist.md 逐项核对：两份报告 pass=true、
重走包哈希可重算、result.json 状态与报告一致、坐标抽查可定位。

最小调用示例见 [examples/minimal_example.md](examples/minimal_example.md)
（**合成示例**，非正式案例结果）。
