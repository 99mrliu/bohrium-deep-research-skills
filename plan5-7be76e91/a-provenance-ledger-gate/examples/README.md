# examples/ — 合成示例 / SYNTHETIC EXAMPLE，非正式案例结果

本目录全部为**虚构教学示例**：虚构细胞系 XJ-7、虚构供应商 SynthiaBio、虚构设备
CO2 培养箱 2 号、虚构契约 SYNTH-PRICE-001 / SYNTH-BOOK-002。不对应任何真实
评测案例、论文、报价或审批。

## 文件

- `mini-case.json` — 虚构案例：case_id、output_contract 示例键、parameter_domains（temperature_c 20–39 °C 等）、硬约束（预算 12000 CNY / 30 天）。
- `task.md` — 虚构任务说明。
- `sources/` — 3 个虚构来源文本：paper_excerpt.txt（虚构论文片段）、price_contract.txt（虚构价格契约）、booking_contract.txt（虚构预订契约）。
- `plans/` — 2 个虚构候选方案；`plan_b.json` 含**预埋陷阱**：temperature_c=41 超出参数域。
- `claims_good.json` — 正例：9 条 given 断言全部 supported。
- `claims_bad.json` — 负例（booby-trap）：1 条 conflict（quote 写 10% FBS 而 value 写 12）+ 1 条 unsupported（quote "倍增时间约 18 小时"不存在）；另含 1 条 inferred（temperature_c=41，留 domain_check 判域外）与 1 条 missing，仅记录不判负。
- `outputs/` — 以下命令序列真实跑出的产物（均含合成示例标注）。

## 调用命令序列（在本目录的父目录、即 bundle 根目录下执行）

```bash
NOTE="合成示例 / SYNTHETIC EXAMPLE，非正式案例结果"

# 1) 登记来源指纹 + 抽取文本
python3 scripts/source_registry.py --input-dir examples/sources \
    --out examples/outputs/registry.json --asof 2026-01-01 --note "$NOTE"
# 期望：exit 0

# 2) 正例对账：全部 supported
python3 scripts/claim_audit.py --claims examples/claims_good.json \
    --registry examples/outputs/registry.json \
    --out-json examples/outputs/audit_good.json \
    --out-md examples/outputs/audit_good.md --note "$NOTE"
# 期望：exit 0

# 3) 负例对账：精确命中预埋的 2 条缺陷
python3 scripts/claim_audit.py --claims examples/claims_bad.json \
    --registry examples/outputs/registry.json \
    --out-json examples/outputs/audit_bad.json \
    --out-md examples/outputs/audit_bad.md --note "$NOTE"
# 期望：exit 3，stdout 缺陷清单恰好 2 行：
#   DEFECT  conflict     PLAN-A  parameters.fbs_percent  ...
#   DEFECT  unsupported  PLAN-B  interpretation_criteria.doubling_time_hours  ...

# 4) 域校验正例（仅 plan_a）
python3 scripts/domain_check.py --case examples/mini-case.json \
    --plans examples/plans/plan_a.json \
    --out examples/outputs/domain_good.json --note "$NOTE"
# 期望：exit 0

# 5) 域校验负例（plan_a + plan_b）：命中预埋域外参数
python3 scripts/domain_check.py --case examples/mini-case.json \
    --plans examples/plans/plan_a.json examples/plans/plan_b.json \
    --out examples/outputs/domain_bad.json --note "$NOTE"
# 期望：exit 3，stdout 恰好 1 行：
#   VIOLATION  out_of_domain  PLAN-B  temperature_c  值 41 高于域上限 39

# 6) 端到端自查（含双跑逐字节一致性验证）
python3 scripts/selfcheck.py
# 期望：exit 0
```
