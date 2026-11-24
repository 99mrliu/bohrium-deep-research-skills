# 最小调用示例（合成数据，非正式案例）

`demo_table.csv` 是一份**合成**演示表：模拟"已发表汇总表转写件"被注入存储/编码
故障——双重编码 mojibake、分号分隔符、混合行尾（CRLF/LF）、NBSP、全角数字、
哨兵码（-999、ND）、科学计数法文本。数据为人工编造，不对应任何真实案例。

## 真实运行过的命令（`$SK` = 本技能根目录）

```bash
# 第 1 轮：诊断 → 审批 → 修复 → 核验
python3 $SK/scripts/byte_scan.py demo_table.csv --out work/diag1
# （人工/Agent 审批 suggested_repair_map.json，全部置 approved=true 并写理由）
python3 $SK/scripts/repair_apply.py demo_table.csv \
    --map work/repair_map1.json --out work/repair1
python3 $SK/scripts/roundtrip_check.py --original demo_table.csv \
    --map work/repair_map1.json --recovered work/repair1/recovered.csv \
    --out work/verify1        # 退出码 0 = PASS

# 第 2 轮：对恢复表再诊断（mojibake 修复后才暴露的全角字符）
python3 $SK/scripts/byte_scan.py work/repair1/recovered.csv --out work/diag2
python3 $SK/scripts/repair_apply.py work/repair1/recovered.csv \
    --map work/repair_map2.json --out work/repair2
python3 $SK/scripts/roundtrip_check.py --original work/repair1/recovered.csv \
    --map work/repair_map2.json --recovered work/repair2/recovered.csv \
    --out work/verify2        # 退出码 0 = PASS
```

## 真实运行产物（`expected/`，由上述命令实际生成）

| 文件 | 内容 |
|---|---|
| `fault_report_round1.md` | 第 1 轮诊断：mojibake(score 0.99)、混合行尾、分号分隔符、NBSP、哨兵码计数 |
| `repair_map_round1.approved.json` | 第 1 轮经审批修复图（4 项全批准，含审批理由） |
| `repair_log_round1.json` | 修复留痕：9 行 mojibake 修复、行尾规范化、分号→逗号重序列化、NBSP 移除 |
| `roundtrip_verdict_round1.json` | PASS：输入哈希一致、独立重算一致、NBSP 清除、mojibake 字节级往返成立 |
| `fault_report_round2.md` | 第 2 轮诊断：暴露 1 格全角数字；哨兵码仅计数（语义层处置，不插补） |
| `recovered_final.csv` | 最终恢复表：规范 CSV（逗号/LF/UTF-8）、中文表头还原、全角转半角 |
| `roundtrip_verdict_round2.json` | PASS |

要点：哨兵码 `-999`、`ND` 与科学计数法 `1.2e-3` 在存储层**原样保留**——其语义
（未检测/低于检出限/录入缺失/真值 0）由数据字典与工单裁决，本层绝不插补。
