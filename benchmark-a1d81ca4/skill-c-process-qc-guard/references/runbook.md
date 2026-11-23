# 标准运行手册（Runbook）

适用：Bohrium Playground 文献阅读评测环境（`/input` → `/app/work` → `/app/output`）。本手册约束"包住干活过程"的质量控制动作；具体作答由 agent 完成并写入约定工作文件（T1 写 `answers.json`，T2 写 `items.json`）。

## 一、900 秒预算分配建议

| 阶段 | 占比 | 时间 | 请求数 | 动作 |
|---|---|---|---|---|
| 预检 | ≈7% | ≤60 秒 | ≤2 | 跑 `init_run.py`：清点输入、探测工具、写 manifest，**立即落 result.json 安全网骨架** |
| 读材料与起草 | ≤60% | ≤540 秒 | ≤38 | 读 task.md/材料；T1 逐问作答、T2 起草 4 道题卡；写入 answers.json/items.json |
| 核验与探针 | ≥20% | ≥180 秒 | ≥14 | 跑 `probe_failures.py`，逐条修复命中；高危不清零不交付 |
| 门禁与交付 | ≥10% | ≥90 秒 | ≥10 | 跑 `rerun_consistency.py` 与 `checkpoint.py status/export`，刷新 result.json |

纪律：每个阶段结束立即 `checkpoint.py save`；每完成一次实质修改就更新工作文件，保证"任何时刻中断都有可提交的诚实 partial"。

## 二、中断恢复流程

1. 重跑 `init_run.py`（幂等：不覆盖已有工作文件与正式 result.json，只刷新预检字段）。
2. `checkpoint.py status` 看完成矩阵与"下次中断可从哪续"；`checkpoint.py resume` 校验依赖哈希。
3. 若出现 STALE：受影响产物按提示重跑该阶段，`checkpoint.py save` 刷新后继续。
4. 从中断阶段继续，禁止跳过后续 probe 与 consistency 门禁。

## 三、三次重复运行的一致性声明模板

> 本次交付基于 `run_manifest.json` 锁定的输入集（各文件 sha256 见清单）。
> 机器阶段（预检、检查点、探针、导出）经 `rerun_consistency.py` 复跑，判定 **STABLE**，产物逐字节一致。
> 三次重复运行间 `result.json` 契约字段逐字节一致（diff 为空）；如存在措辞微差，属模型起草的非确定性，语义与证据锚点保持一致。
> 全部契约字段可追溯至：输入哈希（manifest）→ 阶段检查点（checkpoints/*.json）→ 导出记录（change_records）。
> 已知局限：<列明未作答字段、降级原因与 uncertainty>。

## 四、两类工单要点

- **T1 阅读问答/解析/翻译/抽取**：逐问写入 `answers.json` 的 `items[]`（id/question/answer/evidence/confidence/uncertainty），材料未给出的信息标"未报告"，绝不编造。
- **T2 benchmark-DRAFT 出题**（task.md 含"出题/题卡/benchmark/DRAFT/草拟/4 道/四道"）：起草 4 道题卡写入 `items.json`，每题含任务、材料范围、参考答案、评分规则、证据锚点、难度、授权七要素；探针同样适用（占位符、空证据为常见命中）。
