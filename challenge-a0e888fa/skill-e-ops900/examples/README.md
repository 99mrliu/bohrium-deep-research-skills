# 最小调用示例（合成数据，非正式案例）

`greenhouse.csv`（7 行）：合成田间试验汇总表——`g/m2` 与 `kg/m2` 混写、
`-999`/`ND` 缺失码、大小写近似重复行（`t4`）、越界值（25.0 > 界 15）。
`rules.json` 为配套填写完成的管道配置。数据为人工编造。

## 真实运行过的命令（`$SK` = 本技能根目录，在技能根目录下执行）

```bash
python3 $SK/scripts/timewatch.py start --workdir work
python3 $SK/scripts/pipeline.py --rules examples/rules.json \
    --workdir work --outdir out          # 七道工序一次跑完
python3 $SK/scripts/pipeline.py --rules examples/rules.json \
    --workdir work --outdir out --resume # 续跑演示：全部工序 skip (checkpoint)
python3 $SK/scripts/digest.py out        # <2KB 紧凑摘要
python3 $SK/scripts/timewatch.py status --workdir work
# 最后把 cleaned_table/quality_report/notes 回填 result.json（expected 已含回填版）
```

## 真实运行产物（`expected/`）

| 文件 | 关键内容 |
|---|---|
| `cleaned.csv` | 6 行：5100 g/m2 → 5.1 kg/m2（Decimal 精确换算，无浮点噪声） |
| `ledger.csv` | 8 条台账；`-999` 被标记录入缺失后**不再**被误判越界 |
| `quality_report.json` | 数字全部由产物重算：missing 2、换算 2、去重 1、越界 1 |
| `review_queue.csv` | 空（本示例无键冲突/未知单位） |
| `result.json` | 回填后的最终交付物，`status: success` |
| `digest.txt` | digest.py 的真实输出（Agent 每轮只读这个，不看整表） |

要点：整个机械流程一次命令完成；`--resume` 幂等续跑（实测 7 个工序全部
命中检查点跳过）；模型只需读 digest.txt 级别的紧凑摘要。
