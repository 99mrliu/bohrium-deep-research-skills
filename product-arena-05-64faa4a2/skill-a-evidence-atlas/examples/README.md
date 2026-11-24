# examples — 合成示例（合成示例，非正式案例结果）

> 本目录全部为**人工编造的合成材料与产物**，仅用于演示 evidence-atlas 流水线，
> 不对应评测中的任何正式案例。

## 输入（case/）

- `config.yaml`：训练配置（learning_rate、epochs、batch_size、划分比例、seed 等）。
- `train.log`：训练日志，其中 `learning_rate=0.001` 与 `config.yaml` 的
  `learning_rate: 0.0003` **故意冲突**，演示冲突检测。
- `draft.md`：待修章节草稿，其中 dropout 比率 `0.5` 是**材料中不存在的编造数值**；
  其余数值（0.0003、0.0001、50、32、0.8、0.1、42）均可在材料中定位。
- `README.md`：材料说明。

## 调用

```bash
bash examples/run_example.sh
```

等价于：

```bash
python3 scripts/atlas_scan.py --input examples/case --out examples/expected
python3 scripts/ledger_check.py examples/case/draft.md examples/expected/atlas.json \
    --out examples/expected
```

## 预期输出（expected/）

- `atlas.json`：台账。文件清单含 sha256 与解析状态；参数候选含
  `learning_rate=0.0003`（config.yaml:5）等条目；`conflicts` 中列出
  `learning_rate` 在 config.yaml 与 train.log 之间的取值冲突。
- `atlas.md`：人读摘要（文件清单表 + 参数候选表 + 冲突清单 + 未解析清单）。
- `ledger_report.md` / `ledger_report.json`：校验报告。
  - `0.5`（dropout）判为 **UNSOURCED**，脚本退出码为 1，并给出
    "删除或标注 [待确认]"建议；
  - `0.0003`、`0.0001`、`50`、`32`、`0.8`、`0.1`、`42` 判为 **BOUND**；
  - `ResNet-18` 中的 `18` 被左边界规则排除，不产生误报。
