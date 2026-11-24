# 最小调用示例（合成示例，非正式案例结果）

> 本示例使用**合成数据**（脚本现场生成的随机数据），仅说明接口与完整流程，
> 不冒充平台正式案例的运行结果。

## 合成输入

`run_example.sh` 现场生成 `/tmp/veritas-demo.*/lab.db`：表 `flowers`，150 行、
4 个数值列 + `species` 列（三类各 50 行），形态模仿公开 Iris 数据集，但
**`sepal_width` 一列被故意放大 1.1 倍**，模拟"上游快照被改动"的情形。

## 调用方式

```sh
sh examples/run_example.sh
```

等价于：

```
python <skill>/scripts/fingerprint.py --db <demo>/lab.db --out <demo>/fingerprint.json
python <skill>/scripts/verify_snapshot.py --fingerprint <demo>/fingerprint.json \
  --cards <skill>/references/reference_cards.json \
  --out <demo>/verdict.json --md <demo>/verdict.md
```

## 示意输出（示例，非正式结果）

- `fingerprint.json`：库文件 sha256、表 `flowers` 150 行、每列 min/max/mean/std
  与 `species` 的类别计数。
- `verdict.json` / `verdict.md`：候选评分中 iris 两张卡分数最高并区分变体；
  由于 `sepal_width` 统计量相对偏差约 10%（容差 1%），总体判定为 **DRIFT**，
  drift 清单逐列列出期望值、观测值与相对偏差；verdict.md 末尾列出同族变体卡。
- 按 `references/authenticity_rules.md`，此时下游分析必须进行，但报告须声明
  该列与参考卡不符、结论基于漂移快照，且不得把数据改回参考值。

## 预期运行环境

Python 3.9+，仅标准库；示例全程只读源库，产物写入 mktemp 目录。
