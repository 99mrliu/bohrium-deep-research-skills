# silenterror-auditor（challenge-9ec929fe 作品 C）

结果验证重心：静默错误猎手。`scan` 在计算前挖出缺失当 0、重复行、哨兵
值、混合类型、NULL 口径、主键重复等陷阱并试算影响；`audit` 把每个结论
数字登记为 claim 并从原始输入独立重算，MISMATCH 即 exit 1 阻断交付；
`diff` 对比两版结果。纯 Python 标准库。

## 使用

```bash
python3 scripts/secaudit.py scan /input/data.csv /input/lab.db --out /app/work/scan.json
# ... 主分析（任意工具）...
python3 scripts/secaudit.py audit --claims /app/work/claims.json --out /app/work/audit.json
python3 scripts/secaudit.py diff --a old_result.json --b new_result.json
```

## 合成示例

`bash examples/run_example.sh` —— 在埋有四类陷阱的人工合成数据上演示：
scan 发现 5 项风险 → naive claims 被 audit 阻断（exit 1）→ 修正版 8 条
claim 全部 CONFIRMED → diff 列出两版 8 处分歧。

详见 [SKILL.md](SKILL.md) 与 [references/silent_error_taxonomy.md](references/silent_error_taxonomy.md)。
