# 最小示例（合成示例）

> **本示例全部数据为 `make_synthetic.py` 人工合成（seed=20240501），仅用于演示
> stats-run-gates 工作流，不代表任何真实实验。**

## 输入（由生成器现场产生，47 行 × 2 列）
- `synthetic_vinegar.csv`：表头 `group,yield_rate`（单位 %）；两组 control(n=24)/treatment(n=22)；
  故意埋入 2 个缺失 token（`NA`、空串）、1 行完全重复、2 个温和离群点。
- `synthetic_vinegar.db`：同内容 SQLite（**现场生成**，数值以 TEXT 存储，演示一致性核对）。
- `case.json` / `task.md`：契约与 SPEC 三案例一致（9 个 required_fields）。

## 调用
```bash
bash examples/run_example.sh
```
脚本依次：
1. (a) 好例：make_synthetic → `pipeline_e run` → `decide --confirm-all` → `finalize`
   → `gate_check`（G0–G7 PASS，exit 0）→ `contract_lint`（exit 0）
   → `run_manifest check`（exit 0）→ `replay_diff`（逐字节一致，exit 0）；
2. (b) 埋雷：`result_bad.json`（status="success" 非法值、删 hypothesis_test、case_id 改错）
   → 断言 `contract_lint` exit 1 且命中 `INVALID_STATUS` / `MISSING_FIELD` / `CASE_ID_MISMATCH`；
3. (c) 埋雷：report.md 中一个 p 值改成 `p = 0.0000`
   → 断言 `gate_check` exit 1 且命中 `G6 REPORT_NUMBER_DRIFT`；
4. 全部断言通过才 exit 0，并把真实产物归档到 `example_output/`。

## 示意输出（真实产物见 example_output/）
```
PIPELINE_RUN OK: status=complete, outcomes=['yield_rate'], decisions_pending=3
DECIDE OK: confirmed=['DEC-001', 'DEC-002', 'DEC-005'] overrides=[]
PIPELINE_FINALIZE OK: status=complete, outcomes=['yield_rate'], decisions_pending=0
GATE_CHECK PASS: G0-G7 全部通过
CONTRACT_LINT PASS: 9 个契约字段齐全，status=complete，引用闭合
MANIFEST_CHECK PASS: 5 inputs, 5 stage entries, 3 outputs 全部一致
REPLAY_DIFF PASS: 13 个产物除易变字段 [...] 外逐字节一致
CONTRACT_LINT FAIL: MISSING_FIELD / INVALID_STATUS / CASE_ID_MISMATCH（埋雷 b 被拦截）
GATE_CHECK FAIL: G6 REPORT_NUMBER_DRIFT（埋雷 c 被拦截）
```

## example_output/ 内容（均为真实跑出的文本产物）
- `result.json` / `report.md`：最终交付物；
- `manifest.json`：输入/阶段/交付物哈希登记；
- `stage_02_clean.json`：清洗账本（闭合律、缺失/重复/离群计数）；
- `stage_04_inference.json`：门控推断全记录（假设、检验、效应量、bootstrap CI、scipy 交叉校验）；
- `digest.md`：finalize 后的裁决状态（全部 CONFIRMED）；
- `checks.log`：上述 (a)(b)(c) 全部命令的真实输出。
