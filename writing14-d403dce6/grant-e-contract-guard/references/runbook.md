# 运行手册（runbook）：从启动到交付

每步注明调用哪个脚本、读什么、写什么。脚本路径以 Skill 安装目录 `/skills/weekly-skill` 为准（下记 `$SKILL/scripts/…`）。

## 阶段 0：启动与保底（目标：60 秒内落合法 result.json）

1. 读 `/input/case.json`、`/input/task.md`；若存在 `/input/organizer-workorder.json`、`environment/resources.yaml` 一并读。
2. 列材料清单：`/input` 下全部文件，逐个标注可读性。
3. **落保底**：
   ```
   python3 $SKILL/scripts/contract_probe.py --case /input/case.json \
       --output-dir /app/output --now <当前时间ISO8601>
   ```
   写出 `/app/output/result.json`（status=partial、全部合同字段诚实占位）与 `plan.json`。
4. 建账本：
   ```
   python3 $SKILL/scripts/budget_ledger.py init --ledger /app/work/ledger.json \
       --budget-requests 64 --budget-seconds 900
   ```
5. 存第一个检查点：
   ```
   python3 $SKILL/scripts/checkpoint.py save --stage init --note "保底 result.json 已落盘" \
       --output-dir /app/output --store /app/work/checkpoints.jsonl --now <当前时间>
   ```

## 阶段 1：读材料（预算 ≈20% 请求 / 25% 耗时）

6. 逐个读材料（PDF 用 `pdftotext`），要点落盘到 `/app/work/notes.md`；每条论断登记来源台账骨架 `/app/output/sources.md`。
7. 每次模型请求后记账：`budget_ledger.py tick --kind model_request --elapsed <秒> --note "读材料：…"`；本地处理记 `--kind stage`。
8. 遇异常：写异常描述 JSON，跑 `triage.py --input <文件> --out /app/work/triage-<n>.json`，按输出动作执行（占位 + 缺口 + uncertainty）。

## 阶段 2：成稿（≈45% / 40%）

9. 按 `plan.json` 的要素清单逐章写 `/app/output/proposal_draft.md`；每完成一节：
   - 就地更新 `result.json`（`deliverables`、`change_record` 等字段追加）；
   - `checkpoint.py save --stage <节名>` 留快照；
   - `budget_ledger.py tick` 记账。
10. 同步维护 `/app/output/element_mapping.md`（章节稿 ↔ 要素/案例要求对照）。

## 阶段 3：回检（≈20% / 20%）

11. 逐项回检：合同字段齐全、四态标注（已完成／外部工作／拟开展／待确认）、引用可溯源、无占位遗漏。
12. 任一维度 ≥70%（warn，退出码 2）：停止非必要扩写；≥90%（critical，退出码 3）：立即按 `budget_policy.md` 第 4 条保底交付。

## 阶段 4：交付

13. 最终校验：
    ```
    python3 $SKILL/scripts/contract_probe.py --validate --case /input/case.json \
        --output-dir /app/output
    ```
    退出码 0 才可交付；退出码 1 按列出的问题逐条修复后重跑。
14. 最后检查点：`checkpoint.py save --stage final --note "交付前快照"`。

## 断点续跑

- 被截断后重启：先 `checkpoint.py list --store /app/work/checkpoints.jsonl` 看时间线；
- `/app/output/result.json` 损坏或丢失时：`checkpoint.py restore --stage <最近阶段>`（实际复制 `result.<stage>.json` 回 `result.json`）；
- 用 `budget_ledger.py status` 恢复预算视图（账本持久化在 `/app/work/ledger.json`）；
- 从时间线上最近完成阶段的下一步继续，**不重复已完成工作**（幂等：脚本重复运行产出一致，合同字段以案例为准、口径不变）。
