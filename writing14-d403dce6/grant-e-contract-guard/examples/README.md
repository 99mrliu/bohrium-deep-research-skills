# 示例说明（合成示例，非正式案例结果）

本目录只放合成输入：`case.json`（case_id=demo-001，`output_contract` 含
deliverables/status/sources/uncertainty/change_record 五字段）与一个
material_missing 异常描述文件。**本示例为合成示例，非正式案例结果。**

示例的真实运行产物在 bundle 之外：
`/Users/liuhengshen/Desktop/bhr_product/writing14/example-runs/grant-e-contract-guard/`
（下记 `$RUN`；脚本目录记 `$B/scripts`）。以下命令全部真实执行过，退出码与关键输出为真实记录。

## 0. 准备

```bash
mkdir -p $RUN/input $RUN/app/work $RUN/app/output
cp examples/case.json $RUN/input/case.json
cp examples/exception-material-missing.json $RUN/input/exception-material-missing.json
```

## 1. contract_probe：落保底 result.json 与 plan.json（退出码 0）

```bash
python3 $B/scripts/contract_probe.py --case $RUN/input/case.json \
    --output-dir $RUN/app/output --now 2026-11-24T21:30:00+08:00
# exit=0
```

关键输出：

```
case_id: demo-001
output_contract 字段（5 个）: change_record、deliverables、sources、status、uncertainty
写作要求摘要: 按七要素（立项依据、科学问题、研究目标、研究内容、技术路线、创新点、研究基础与可行性）撰写申请书章节稿；…
已写出保底 result.json（status=partial）: …/app/output/result.json
已写出 plan.json: …/app/output/plan.json
```

## 2. budget_ledger：init + 3 次 tick 到 75% 触发 warn

```bash
python3 $B/scripts/budget_ledger.py init --ledger $RUN/app/work/ledger.json \
    --budget-requests 64 --budget-seconds 900                    # exit=0
python3 $B/scripts/budget_ledger.py tick --ledger $RUN/app/work/ledger.json \
    --kind model_request --elapsed 30  --note "读 case.json 与材料清单"   # exit=0（level=ok，3.3%）
python3 $B/scripts/budget_ledger.py tick --ledger $RUN/app/work/ledger.json \
    --kind model_request --elapsed 300 --note "读文献 PDF（切片 1-8）"    # exit=0（level=ok，36.7%）
python3 $B/scripts/budget_ledger.py tick --ledger $RUN/app/work/ledger.json \
    --kind stage --elapsed 345 --note "本地整理笔记与来源台账"            # exit=2（level=warn，75.0%）
```

第 3 次 tick 真实输出（退出码 2 = warn）：

```
tick #3：kind=stage elapsed=345s note=本地整理笔记与来源台账
预算账本状态：level=warn
  请求：已用 2 / 64（3.1%），剩余 62
  耗时：已用 675 / 900 秒（75.0%），剩余 225 秒
  降级建议（degradation_advice）：
    1. 立即停止新增扩写与额外检索，不再发起非必要模型请求。
    …（共 6 条保底交付动作）
```

## 3. triage：处置 material_missing 异常（退出码 0）

```bash
python3 $B/scripts/triage.py --input $RUN/input/exception-material-missing.json \
    --out $RUN/app/work/triage-1.json                            # exit=0
```

关键输出（`triage-1.json` 节选）：

```json
{
  "disposition": "playbook_rule",
  "actions": [
    "在对应章节写入占位：【待申请人确认：请补充：申请人近三年论文清单（case.json 引用的 /input/applicant-prior-work.md 在输入目录中不存在）】",
    "把缺失项逐条写入缺口清单，禁止编造申请人成果",
    "继续完成其余有材料支撑的章节"
  ],
  "result_json_update": {"status_advice": "partial", …}
}
```

未知类型演示（`exception-unknown.json`，type=mystery_glitch）同样真实运行：
退出码 0，`disposition: conservative_default`，`status_advice: partial`。

## 4. checkpoint：两个快照 + 时间线（退出码 0）

```bash
python3 $B/scripts/checkpoint.py save --stage init --note "保底 result.json 已落盘" \
    --output-dir $RUN/app/output --store $RUN/app/work/checkpoints.jsonl \
    --now 2026-11-24T21:31:00+08:00                              # exit=0
# （模拟 Agent 就地改进 result.json：按 triage 建议填缺口与占位说明）
python3 $B/scripts/checkpoint.py save --stage post-triage \
    --note "三章成稿+material_missing 异常已处置" \
    --output-dir $RUN/app/output --store $RUN/app/work/checkpoints.jsonl \
    --now 2026-11-24T21:40:00+08:00                              # exit=0
python3 $B/scripts/checkpoint.py list --store $RUN/app/work/checkpoints.jsonl
# exit=0
```

真实输出：

```
检查点时间线（共 2 个）：
  #1  stage=init  note=保底 result.json 已落盘  文件：result.json、plan.json
  #2  stage=post-triage  note=三章成稿+material_missing 异常已处置  文件：result.json、plan.json
```

## 5. contract_probe --validate：通过（退出码 0）

```bash
python3 $B/scripts/contract_probe.py --validate --case $RUN/input/case.json \
    --output-dir $RUN/app/output                                 # exit=0
```

```
合同校验通过：case_id 一致；5 个合同字段齐全；status=partial 合法。
```

## 6. 陷阱（booby trap）：删一个合同字段，校验必须响（退出码 1）

手工把 `result.json` 的 `sources` 字段删掉后重跑校验，真实输出：

```
合同校验未通过（1 项问题）：
  1. 缺失合同字段：sources
# exit=1
```

修复方式（用快照恢复，证明断点恢复真实可用）：

```bash
python3 $B/scripts/checkpoint.py restore --stage post-triage \
    --output-dir $RUN/app/output --store $RUN/app/work/checkpoints.jsonl   # exit=0
python3 $B/scripts/contract_probe.py --validate --case $RUN/input/case.json \
    --output-dir $RUN/app/output                                 # exit=0（再次通过）
```

## 7. 预算超 100%：critical（退出码 3）

```bash
python3 $B/scripts/budget_ledger.py tick --ledger $RUN/app/work/ledger.json \
    --kind model_request --elapsed 300 --note "回检阶段（演示超支）"        # exit=3
```

真实输出节选：

```
预算账本状态：level=critical
  请求：已用 3 / 64（4.7%），剩余 61
  耗时：已用 975 / 900 秒（108.3%），剩余 -75 秒
  降级建议（degradation_advice）：…（共 6 条）
```

`budget_ledger.py status` 同样返回 critical、退出码 3。

## 8. 确定性核验

相同参数重跑 `contract_probe.py`，产出的 `result.json` 与第 4 步
`result.init.json` 快照 **字节一致**（`diff` 无输出）。脚本不读墙钟，
时间一律由 `--now`/`--elapsed` 传入。

## 退出码总表

| 脚本 | 0 | 非零 |
| --- | --- | --- |
| contract_probe.py | 探测成功 / 校验通过 | 1=校验不通过；2=输入或环境错误 |
| budget_ledger.py | 正常（<70%） | 2=warn（≥70%）；3=critical（≥90%）；1=错误 |
| checkpoint.py | 成功 | 1=阶段不存在/文件缺失等错误 |
| triage.py | 成功（含未知类型保守默认） | 1=输入或环境错误 |
