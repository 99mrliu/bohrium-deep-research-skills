# 最小调用示例（合成示例，非正式案例结果）

本示例的全部输入为虚构合成数据，仅用于演示接口与流程，不冒充正式案例结果。
`examples/output/` 下的产物是上述合成输入在本地真实执行脚本得到的真实输出。

## 输入（examples/input/）

- `evidence_registry.json`：合成证据登记（2 条论断、2 条证据摘录、
  2 条虚构文献；E1 强度 moderate，E2 强度 low）；
- `draft_bad.md`：刻意植入 4 类硬伤的草稿——数字错位（1.8 写成
  1.6）、相关性证据写成因果（"导致"）、引文悬空（[3] 无登记）、
  占位符残留（TODO），另有强措辞越级（"已证实"+moderate 证据）；
- `draft_good.md`：修复后的草稿。

## 调用

```bash
python3 scripts/draft_lint.py --draft examples/input/draft_bad.md \
  --registry examples/input/evidence_registry.json \
  --out /tmp/lint-bad.json --report /tmp/lint-bad.md
python3 scripts/gate_check.py --lint /tmp/lint-bad.json \
  --policy references/gate_policy.json --report /tmp/gate-bad.md
# 对 draft_good.md 同样跑一遍
```

## 输出（examples/output/，本地真实运行所得）

- `lint-bad.json` / `lint-bad.md`：5 个 error（NUM-UNTRACE、
  OVERCLAIM、CAUSAL-SLIP、CITE-ORPHAN、PLACEHOLDER），lint 退出码 1；
- `gate-bad.md`：门禁 **FAIL**，阻断项 5 条并给出逐行修复清单，
  退出码 1；
- `lint-good.json` / `gate-good.md`：0 error 0 warning，门禁 **PASS**。

该对照演示了门禁的拦截能力：draft_bad 的五类问题在不调用任何模型
的情况下被确定性拦截，修复后同一流水线放行。
