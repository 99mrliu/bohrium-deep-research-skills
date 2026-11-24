# quote-anchor-forensics

上游数据真实性取向的科研选题证据取证 Skill：每条进入综述的证据必须带逐字引文锚点，由脚本机检其真实存在于所指来源后方可使用。详见 [SKILL.md](SKILL.md)。

## 文件

- `SKILL.md`：技能说明与运行时契约（/input → /app/work → /app/output，result.json 含 case_id 与全部 output_contract 字段）；
- `scripts/anchor_audit.py`：证据锚点取证核验器（纯 Python 3.8+ 标准库，无第三方依赖）；
- `references/evidence_ledger_format.md`：证据台账格式与写作纪律；
- `references/verification_policy.md`：核验判定规则与 FAIL 修复手册；
- `examples/`：合成示例（虚构材料），运行方式见 `examples/minimal_example.md`。

## 依赖与安装

Python 3.8+，标准库即可，无安装步骤。

## 快速自检

```bash
python3 scripts/anchor_audit.py --sources examples/input/sources \
    --ledger examples/input/ledger.jsonl --out /tmp/anchor_audit_demo
# 预期退出码 1（示例故意含 1 条 FAIL 记录），查看 /tmp/anchor_audit_demo/audit_report.md
```
