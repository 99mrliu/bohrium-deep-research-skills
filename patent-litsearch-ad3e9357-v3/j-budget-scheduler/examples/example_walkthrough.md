# 端到端示例（合成示例 / 示意输出）

> **合成示例声明**：本示例使用的 case、任务队列、花费事件全部来自
> `examples/fixtures/` 下的自造数据（各文件头部均有 `_notice` 声明），不对应任何
> 真实专利、真实案件或真实检索结论。下述输出为真实运行这些合成数据所得的示意输出，
> 数值可能因运行时刻的时间戳而略有差异。

目标：演示一条完整的"预算感知核验"流水线——从空账本到降级止损，再到成本报告。

## 准备

```bash
SKILL=/path/to/skill                 # 本 bundle 的 skill/ 目录
FIX=$SKILL/examples/fixtures
WORK=$(mktemp -d /tmp/budget-demo.XXXXXX)
mkdir -p "$WORK"
```

## 第 1 步：从空账本重算预算状态

```bash
python3 $SKILL/scripts/budget_ledger.py state \
  --ledger $WORK/ledger.jsonl --policy $FIX/scheduling_policy.json \
  --out $WORK/budget_state.json
```

示意输出：

```json
{"state_file": "…/budget_state.json", "remaining": {"requests": 64, "seconds": 900, "tokens": 16384}, "events": 0}
```

## 第 2 步：生成初始执行计划

```bash
python3 $SKILL/scripts/plan_schedule.py \
  --queue $FIX/task_queue.json --state $WORK/budget_state.json \
  --policy $FIX/scheduling_policy.json --out $WORK/plan.json
```

示意输出（`plan.json` 节选）：

```json
{
  "mode": "normal",
  "steps": [
    {"seq": 0, "id": "__checkpoint__", "kind": "checkpoint_write", "rule": "R0-checkpoint-first"},
    {"seq": 1, "id": "v01", "rule": "R1-mandatory-first", "deps": []},
    {"seq": 2, "id": "v02", "rule": "R1-mandatory-first", "deps": []},
    {"seq": 3, "id": "v03", "rule": "R2-priority-cost-ratio", "deps": ["v01"]},
    {"seq": 4, "id": "v05", "rule": "R1-mandatory-first", "deps": ["v02", "v03"]}
  ],
  "skipped": [
    {"id": "v12", "mandatory": false, "reason": "budget-insufficient: …"}
  ]
}
```

要点：第 0 步恒为检查点写入；`v05` 排在 `v02`、`v03` 之后（依赖序）；低优先级的
`v12` 因秒数预算不足被跳过并注明原因。

## 第 3 步：写入诚实部分骨架检查点

```bash
cat > $WORK/result_draft.json <<'JSON'
{"case_id": "SYNTH-AD3E9357-000", "status": "partial",
 "facsimile_forensics": null, "date_chronology": null, "claim_diff": null,
 "entity_resolution": null, "retrieval_queries": null, "legal_status": null,
 "family_links": null, "ocr_boundary_notes": null,
 "uncertainty": ["合成示例：骨架草稿，全部字段待核验"], "change_records": []}
JSON
echo '[]' > $WORK/completed.json
python3 - "$FIX/task_queue.json" > $WORK/pending.json <<'PY'
import json, sys
print(json.dumps([it["id"] for it in json.load(open(sys.argv[1]))["items"]]))
PY
python3 $SKILL/scripts/checkpoint.py write --workdir $WORK \
  --result $WORK/result_draft.json --completed $WORK/completed.json \
  --pending $WORK/pending.json --ledger $WORK/ledger.jsonl
```

## 第 4 步：模拟逐项执行并把实际花费入账

```bash
while IFS= read -r line; do
  python3 $SKILL/scripts/budget_ledger.py append --ledger $WORK/ledger.jsonl \
    --kind spend --payload "$line" > /dev/null
done < $FIX/spend_events.jsonl
python3 $SKILL/scripts/budget_ledger.py verify --ledger $WORK/ledger.jsonl
python3 $SKILL/scripts/budget_ledger.py state --ledger $WORK/ledger.jsonl \
  --policy $FIX/scheduling_policy.json --out $WORK/budget_state.json
# 记录已执行的步骤 id，供重规划与降级使用
python3 - "$FIX/spend_events.jsonl" > $WORK/completed.json <<'PY'
import json, sys
ids = [json.loads(l)["step_id"] for l in open(sys.argv[1]) if l.strip()]
print(json.dumps([i for i in ids if i.startswith("v")]))
PY
```

示意输出：12 条合成花费事件入账后，`budget_state.json` 显示
`remaining.seconds ≈ 66`，`below_threshold = ["seconds"]`——秒数跌破阈值（120）。

## 第 5 步：重规划 → 自动转入降级

```bash
python3 $SKILL/scripts/plan_schedule.py \
  --queue $FIX/task_queue.json --state $WORK/budget_state.json \
  --policy $FIX/scheduling_policy.json --completed $WORK/completed.json \
  --out $WORK/plan2.json
# 计划事件入账（含跳过清单，供成本报告归集）
python3 - "$WORK/plan2.json" > $WORK/plan_event.json <<'PY'
import json, sys
plan = json.load(open(sys.argv[1]))
print(json.dumps({"plan_file": "plan2.json", "mode": plan["mode"],
                  "steps": len(plan["steps"]),
                  "skipped": plan.get("skipped", [])}, ensure_ascii=False))
PY
python3 $SKILL/scripts/budget_ledger.py append --ledger $WORK/ledger.jsonl \
  --kind plan --payload "$(cat $WORK/plan_event.json)"
```

示意输出：`{"mode": "degrade", "reason": "R3", "below": ["seconds"], …}`——
计划仅剩两步：检查点写入 + 降级写入；`skipped` 恰好只有尚未执行的 `v12`。

## 第 6 步：生成降级计划与降级报告

```bash
python3 $SKILL/scripts/degrade_plan.py \
  --state $WORK/budget_state.json --contract $FIX/case_fixture.json \
  --queue $FIX/task_queue.json --completed $WORK/completed.json \
  --out-plan $WORK/degrade_plan.json --report $WORK/degradation_report.json
python3 $SKILL/scripts/budget_ledger.py append --ledger $WORK/ledger.jsonl \
  --kind degrade --payload "{\"trigger\": \"R3-degrade-threshold\", \"report\": \"degradation_report.json\"}"
```

示意输出（`degradation_report.json` 节选）：

```json
{
  "dropped_verifications": [
    {"id": "v12", "mandatory": false,
     "reason": "degrade-mode: 剩余预算不足（remaining={…'seconds': 66…}）",
     "consequence": "该项核验未执行；关联契约字段 [legal_status] 将置 null 并记录 uncertainty"}
  ],
  "contract_null_fields": ["family_links", "legal_status", "ocr_boundary_notes", "retrieval_queries"],
  "contract_mandatory_filled": ["claim_diff", "date_chronology", "entity_resolution", "facsimile_forensics"]
}
```

被放弃项恰好是尚未执行的 `v12`；四个非强制契约字段全部置 null 并登记 uncertainty。

## 第 7 步：断点续跑（检查点恢复）

```bash
# 模拟中断后恢复：以最新账本 + 已完成列表更新检查点，再恢复
echo '["v12"]' > $WORK/pending.json
# 先把 checkpoint 事件入账，再写检查点：检查点会锚定包含该事件的账本链头，
# 若先写检查点再入账，链头前移将导致 restore --ledger 校验失败。
python3 $SKILL/scripts/budget_ledger.py append --ledger $WORK/ledger.jsonl \
  --kind checkpoint --payload '{"checkpoint_file": "checkpoint.json", "note": "合成示例：降级前最终检查点"}'
python3 $SKILL/scripts/checkpoint.py write --workdir $WORK \
  --result $WORK/result_draft.json --completed $WORK/completed.json \
  --pending $WORK/pending.json --ledger $WORK/ledger.jsonl
python3 $SKILL/scripts/checkpoint.py restore --workdir $WORK --ledger $WORK/ledger.jsonl
```

恢复出的 `restored_state.json` 中 `pending == ["v12"]`，与写入时完全一致；
若手工改动 `checkpoint.json` 中任何一个字段，`restore` 立即以退出码 1 拒绝。

## 第 8 步：结束成本报告

```bash
python3 $SKILL/scripts/cost_report.py --ledger $WORK/ledger.jsonl \
  --out $WORK/cost_report.json --md $WORK/cost_report.md
cat $WORK/cost_report.md
```

示意输出（节选）：

```markdown
## 预算利用率
| 维度 | 已用 | 预算 | 利用率 |
| 模型请求数 | 54 | 64 | 84.38% |
| 秒 | 834 | 900 | 92.67% |
| token 数 | 7200 | 16384 | 43.95% |
## 被跳过项及原因
- `v12`：degrade-mode: 剩余预算不足…
```

中文摘要末尾给出可直接摘录进 result.json `change_records` / `uncertainty` 的表述。

## 第 9 步：自检

```bash
python3 $SKILL/scripts/selfcheck.py   # 期望：SELFCHECK OK，退出码 0
```
