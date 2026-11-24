# 最小调用示例（合成数据，非正式案例）

合成水质汇总表 `measurements.csv`（10 行），注入语义层问题：μg/L 与 mg/L 混写、
`ND`/`<0.01`/`-999` 三类缺失码、大小写+尾随空格的近似重复行（`w-06 `）、
越界值（总磷 25 > 物理界 5）、真值 0（浊度 0）。`dictionary.md` 与
`workorder.md` 为配套合成材料。数据为人工编造，不对应任何真实案例。

## 真实运行过的命令（`$SK` = 本技能根目录，在技能根目录下执行）

```bash
python3 $SK/scripts/field_survey.py examples/measurements.csv \
    --dict examples/dictionary.md --out work/survey
# 对照 dictionary.md 与 workorder.md 填写 decisions.json（本目录已附填好的版本）
python3 $SK/scripts/adjudicate.py --decisions examples/decisions.json --validate
python3 $SK/scripts/adjudicate.py --decisions examples/decisions.json \
    --run --out work/run
```

## 真实运行产物（`expected/`）

| 文件 | 关键内容 |
|---|---|
| `survey_report.md` | 字段画像：哨兵计数、`sample_id` 归一化后 9/10 唯一（1 个重复组） |
| `cleaned.csv` | 9 行：μg/L→mg/L 换算 1 格（7900→7.9），近似重复行已去重 |
| `ledger.csv` | 7 条逐格台账：单位换算+单位列联动、3 条缺失分类标记（原值保留）、越界标记（保留不剔除）、去重丢弃（整行 JSON 存档） |
| `review_queue.csv` | 空——本示例全部可裁定；真实案例中键冲突/未知单位会进入此队列 |
| `field_summary.json` / `digest.md` | 质量摘要：行 10→9，缺失分类 3、换算 1、越界 1、IQR 诊断 1 |

要点：`ND`/`-999` **原值保留只标记**（不填补）；`<0.01` 字面值保留；
`0` 按真值 0 处理；NTU 行声明 `convert_only` 后不产生换算噪声。
