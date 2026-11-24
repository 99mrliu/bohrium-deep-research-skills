# 预算包线、检查点模式、账本模式与恢复语义

## 1. 预算包线(Budget Envelope)

平台约束:**至多 64 次模型请求 / 900 秒**。本技能的设计使流水线本身几乎
不消耗模型预算:

| 预算项 | 规划值 | 说明 |
|---|---|---|
| 脚本化阶段(intake/normalize/identity-机械部分/coverage/report) | 0 次模型请求 | 全部 5 阶段合并为 **1 条 bash 命令**执行;`--resume` 避免重复劳动 |
| 唯一模型判断点:模糊重复对仲裁 | **0 或 1 次** | identity 产出 `work/arbitration_queue.json`;若非空,代理将**全部**待决对放入**单次批量请求**仲裁,决定写入 `work/arbitration_decisions.json` 后 `--resume` 重跑 |
| 重放验证 `--replay` | 0 次 | 双跑为纯脚本执行 |
| 代理编排/契约核验/异常重试预留 | ≥ 60 次 / ≥ 800 s | 64 − 1(仲裁)− 少量读取确认 ≈ 60+ 次余量 |

预算数学:`64(上限) = 1(仲裁批量) + 63(预留)`;`900s ≈ 数秒(脚本流水线)
+ 数十秒(一次仲裁请求) + 全部余量`。脚本阶段确定性且毫秒~秒级,无超时风险。

## 2. 检查点模式(Checkpoint Schema)

每阶段完成后写入 `work/checkpoints/<stage>.json`:

```json
{
  "stage": "identity",
  "input_sha256": "<该阶段全部输入的清单哈希>",
  "output_sha256": "<该阶段实质输出的哈希>",
  "invariants_checked": [{"name": "...", "status": "ok|failed", "detail": {}}],
  "status": "ok | invariant_failed"
}
```

各阶段输入定义(哈希自这些实体重算):

- `intake`: `case.json`、`task.md`、case 声明的全部材料文件
- `normalize`: `work/materials_index.json`(内嵌逐材料 sha256)
- `identity`: `work/normalized_records.json` + `work/arbitration_decisions.json`(缺省记 `absent`)
- `coverage`: `work/merged_records.json`
- `report`: `coverage_matrix.json` + `merged_records.json` + `decision_log.json` +
  `arbitration_queue.json` + `replay_verdict.json`(缺省记 `absent`)+ `case.json`

## 3. 账本模式(Ledger Schema)

`work/run_ledger.jsonl`:每行一个 JSON 对象,一行对应一个阶段事件:

```json
{"seq": 7, "event": "stage_completed", "stage": "identity", "detail": {...}}
```

- `seq` 为**逻辑序号**(自 0 单调递增),**不携带墙钟时间**;
- `event ∈ {run_plan_written, stage_completed, stage_skipped, stale_detected,
  invariant_failed, gate_completed, replay_completed, input_error,
  honest_partial_on_error}`;
- 账本是 `result.json.change_records` 的来源,也是断点续跑的审计轨迹。

## 4. 恢复语义(--resume)

逐阶段重算输入哈希并与检查点比对:

- **一致且 `status == "ok"`** → 记 `stage_skipped`,直接沿用既有产物;
- **不一致** → 记 `stale_detected`,自该阶段起重跑;由于下游阶段的输入
  包含上游产物哈希,陈旧会**自然级联**,下游必然随之重跑,不会出现
  "新上游 + 旧下游"的混杂状态;
- 典型用法:模型完成仲裁 → 写入 `work/arbitration_decisions.json` →
  `--resume`:identity 输入哈希变化 → identity 及下游重跑,上游
  intake/normalize 被跳过。

## 5. 重放语义(--replay)

`--replay` 在 `work/replay/{a,b}/` 两个**全新** work/out 目录中各完整运行
一次流水线(若主 work 中存在仲裁决定文件则播种至两侧),随后对全部实质
产物(`out/*` 与 `work` 下中间产物、检查点、账本)做**逐字节 sha256 比对**,
产出 `work/replay_verdict.json`:

```json
{"verdict": "STABLE | DRIFT", "differing_files": [], "compared_file_count": 0,
 "case_sha256": "...", "note": "..."}
```

产物不含墙钟时间与绝对路径(账本用逻辑序号、路径一律相对),故 STABLE
是可达且必须达到的;出现 DRIFT 即表示存在非确定性来源,`replay_stable`
自查项 FAIL,状态降级为 partial。
