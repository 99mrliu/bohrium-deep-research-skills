---
name: idempotent-rerun-controller
description: 科研资料库整理的"过程质量控制"技能。当任务要求在大批量混杂文献文件上真实完成归档、改名、去重并保证可回滚、可续跑、重跑一致时使用；重心在过程质量：任何变更先落成带哈希的计划（plan），apply 逐条 journaling 且可断点续跑，verify 复核覆盖率与哈希，certify 用输出树指纹证明两次运行逐字节一致并签发幂等证书，undo 可按日志完整回滚。输入只读、不删除、冲突不覆盖。不负责单篇精读、全文翻译与文献检索发现。
---

# idempotent-rerun-controller：先计划后动手，重跑必须逐字节一致

## 1. 核心思想

批量整理的质量不在"做了多少"，而在**过程是否可证**：中断后能否续跑、重跑结果
是否一致、做错了能否回滚。本 Skill 把整理流程做成一个可证明正确的事务管线：

1. **计划先行（plan）**：任何文件变更必须先存在于 `ops_plan.json` 中，计划本身
   带 `plan_hash`（内容寻址）。apply 只执行计划内的操作，计划外一律不动。
2. **逐条 journaling + 断点续跑（apply）**：每条操作完成才写日志；进程在任意
   两条操作之间被杀死，重跑 apply 自动跳过已核验完成的操作，从断点继续。
   示例中用 `--stop-after` 注入崩溃点演示续跑。
3. **幂等证书（certify）**：对输出树计算指纹（全部文件的 相对路径+SHA-256
   排序后再哈希），连续两次完整 plan→apply 后指纹必须逐字节一致，签发
   `idempotency_certificate.json`；不一致即失败并说明差异。
4. **可回滚（undo）**：按日志逆序移除所有已落地文件并清理空目录，输出树回到
   整理前状态，回滚本身也写日志。

## 2. 适用边界

- 适用：要求真实移动/复制归档、改名、去重并给出可复核过程证据的批量整理任务。
- 不适用：精读、翻译、润色、检索发现；OCR；损坏/无权限文件的内容判读
  （如实进 skipped，跳过也进计划与日志）。

## 3. 运行时契约（Harbor）

- 安装路径 `/skills/weekly-skill`；脚本 `python3 /skills/weekly-skill/scripts/xxx.py`。
- 输入 `/input/case.json`、`/input/task.md` 与材料目录；防御式解析见
  `references/case_contract.md`。
- 工作目录 `/app/work`；交付 `/app/output/`：`result.json`（含原 `case_id` 与
  `output_contract` 全部字段、诚实 status）、`library/`、`operations.jsonl`、
  `ops_plan.json`、`verify_report.json`、`idempotency_certificate.json`。
- status：`complete` / `partial`（有跳过或证书未签发，列限度）/ `blocked`。
- 依赖：Python 3 标准库；`pdftotext` 缺失时降级登记。
- 预算：脚本零模型请求；模型 1–3 次（决策/版本关系/回答）。第一步永远是 init。

## 4. 工作流程

设 `S=/skills/weekly-skill/scripts`。协议细则见 `references/idempotency_protocol.md`。

```bash
python3 $S/run_case.py init   --input /input --work /app/work --out /app/output   # 盘点+保底 partial
# 模型写 /app/work/decisions.json（assignments / version_relations / answers）
python3 $S/run_case.py plan   --work /app/work --out /app/output                  # 生成带 plan_hash 的计划
python3 $S/run_case.py apply  --work /app/work --out /app/output                  # 逐条执行+日志；可续跑
python3 $S/run_case.py verify --work /app/work --out /app/output                  # 哈希+覆盖率复核
python3 $S/run_case.py certify --work /app/work --out /app/output                 # 二次执行+指纹对比，签发幂等证书
python3 $S/run_case.py finalize --work /app/work --out /app/output                # 终版 result.json
# 需要回滚时：
python3 $S/run_case.py undo   --work /app/work --out /app/output
```

## 5. 异常处理

| 情况 | 处置 |
|---|---|
| 进程中断 | 重跑 apply 自动续跑；日志中已核验操作转 `verified_skip` |
| 目标重名不同内容 | 自动 `-n` 后缀，记 `conflict_renamed`，不覆盖 |
| 损坏/无文本层/无权限文件 | 计划中即标记 skipped（含恢复建议），不产生文件操作 |
| verify 失败 | 修复 decisions 后重跑 plan/apply/verify（续跑安全）；两轮仍失败如实 partial |
| certify 指纹不一致 | 证书 `granted=false`，差异写入证书与 uncertainties，status=partial |
| undo 后验证 | 输出 library 为空树，undo_log 记录移除的每个路径 |

## 6. 最小调用示例（合成示例）

```bash
cd examples && python3 make_fixture.py && bash run_example.sh
```

示例演示完整过程质量链路：init → 预写决策 → plan → **注入崩溃**（apply 执行
3 条后强制停止）→ 续跑 apply → verify → certify（幂等证书）→ finalize →
undo 演示回滚。输出摘录见 `sample_output.md`。**合成示例，非正式案例结果。**

## 7. 自查清单

- [ ] `idempotency_certificate.json` 的 `granted=true` 且两次指纹一致。
- [ ] operations.jsonl 覆盖全部输入文件（操作或显式跳过）。
- [ ] undo 演示后输出树为空，且重新 apply 能完整重建。
- [ ] result.json status 与证书、skipped 一致，无粉饰。
