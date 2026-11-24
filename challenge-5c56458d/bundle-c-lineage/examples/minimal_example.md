# 最小调用示例（合成示例，非正式案例结果）

> 本示例使用**合成数据**（脚本现场生成），仅说明接口与流程，不冒充平台
> 正式案例的运行结果。

## 合成输入

`run_example.sh` 现场生成 `lab.db`：表 `measurements`（sample_id /
group_id / metric），61 行，含一条 `metric IS NULL` 与一条重复
`sample_id`；以及 `spec.json`：按 `group_id` 求 `COUNT(*)` 与
`AVG(metric)`，过滤 `metric IS NOT NULL`。

## 调用方式

```sh
sh examples/run_example.sh
```

## 示意输出（示例，非正式结果）

- `q1.csv`：control / treat_a / treat_b 三组的 n 与 mean_metric。
- `q1.lineage.jsonl`：每组一行，含该组全部贡献 sample_id（重复键 S000
  出现两次，如实保留，处置口径由分析者在 notes 中声明）。
- `q1.run.json`：逐字 SQL、spec 原文、耗时。
- `q1.recompute.json`：`status: PASS`，`aggregates_checked: 6`——每个导出
  数字都从原始行独立重算并比对通过。

## 预期运行环境

Python 3.9+，仅标准库；示例只读源库，产物写入 mktemp 目录。
