# 示例走查（example_walkthrough）

> **合成示例，非真实评测案例。** 本目录所有文献、检索式、重复导出与冲突意见均为虚构演示数据，
> 仅用于端到端演示守门链路。所有命令均在本 bundle 根目录真实执行，exit code 见 `selftest_log.md`。

## 目录角色（模拟运行时拓扑）

| 运行时 | 本示例 | 内容 |
|---|---|---|
| `/input` | `examples/input/` | `case.json`（含 `output_contract.fields` 五字段 + `case_id` + 5 条合成题录，含标注的重复导出夹具 R03 与冲突双人意见夹具 R05）、`task.md` |
| `/app/work` | `examples/work/` | 合成中间产物 `decisions.json` / `dedup_report.json` / `conflict_resolutions.json`（模拟模型实质筛选的输出），以及守门链路生成的 `contract_spec.json` / `fill_ledger.json` |
| `/app/output` | `examples/output/` | 真实跑出的 `result.json`（status=partial）与 `validation_report.json` |
| 负例 | `examples/negative/output/` | 故意删除合同字段 `conflict_resolutions` 的 `result.json` 与被拦截的校验报告 |

## 逐步走查

1. **合同探测**：`contract_probe.py --input examples/input --work examples/work` → exit 0。
   从 case.json 的 `output_contract.fields`（对象列表形态 D 包在形态 A 里）提取 5 个字段，
   `warnings` 留痕合同形态；`case_id=search09-synthetic-demo`。
2. **零分钟骨架**：`scaffold_result.py --work examples/work --output examples/output` → exit 0。
   落 `result.json`（status=in_progress，5 个业务字段占位 null，sources/uncertainty/change_records 空容器）
   与 `fill_ledger.json`（业务字段全 pending）。此刻即被杀也有合法交付物。
3. **增量填充**（模拟模型每完成一块实质工作就记账）：
   - `decisions` / `dedup_report` / `conflict_resolutions`：`mark --state filled --source <产物路径> --value <JSON>` → exit 0；
   - `screening_summary`：`mark --state filled --value <内联 JSON>` → exit 0；
   - **演示拦截**：`mark --field limits --state null_with_reason`（不带 reason）→ **exit 3**，静默空字段被拒绝；
   - `limits`：`mark --state null_with_reason --reason "有限快照、无实时库……"` → exit 0；
   - `uncertainty` / `sources`：filled → exit 0。
4. **终态定级**：按 `references/status_honesty_rules.md` §3 第 1 条（存在 null_with_reason 字段），
   必须降级为 `partial`：`mark --field status --value '"partial"'` → exit 0。
5. **校验门**：`validate_result.py --work examples/work --output examples/output` → exit 0，
   V1–V7 全 PASS（partial 有非空 uncertainty，放行）。
6. **台账终检**：`fill_ledger.py report --strict` → exit 0（filled=9 / null_with_reason=1 / pending=0）。

## 负例（校验门拦截演示）

`examples/negative/output/result.json` 由正例复制后**故意删除合同字段 `conflict_resolutions`**，
模拟"交付前删字段"违规：

```
validate_result.py --result examples/negative/output/result.json \
  --report examples/negative/output/validation_report.json
→ [FAIL] V2_FIELDS_PRESENT: 缺失合同字段: ['conflict_resolutions']
→ verdict=FAIL, exit 3（交付被拦截）
```

## 幂等性验证

整链（probe → scaffold → mark → validate）原样重跑一遍：四步 exit 全 0；
业务字段内容逐键比较与重跑前完全一致（`change_records` 仅追加一条审计记录，台账重复 mark 只刷新时间戳）。
