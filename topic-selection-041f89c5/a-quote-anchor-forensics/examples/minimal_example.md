# 最小调用示例（合成示例，非正式案例结果）

本示例全部材料为**虚构的合成数据**，仅用于演示接口与流程，不构成任何真实文献结论。

## 输入

- `input/sources/paper1.txt`、`paper2.txt`、`paper3.txt`：3 段虚构文献文本；
- `input/ledger.jsonl`：5 条证据台账记录，其中 E3 故意写成"主动学习在所有数据集上都降成本"的错误转述（quote 在原文中不存在）。

## 调用

```bash
python3 scripts/anchor_audit.py \
    --sources examples/input/sources \
    --ledger examples/input/ledger.jsonl \
    --out examples/output
```

## 预期输出（真实运行产生，已目检）

- 退出码 1（存在未通过记录）；
- stdout：`{"total": 5, "PASS": 4, "FAIL": 1, "ERROR": 0, "all_passed": false}`；
- `output/source_registry.json`：3 个来源的字节数与 SHA-256；
- `output/audit_report.json` / `audit_report.md`：E3 被判 FAIL，问题为
  "quote 在来源全文中找不到逐字匹配（归一化后）"；E1/E2/E4/E5 为 PASS。

按技能纪律，E3 对应陈述必须回原文修复 quote 或从综述中删除；修复后重跑至全部 PASS 方可进入综合阶段。
