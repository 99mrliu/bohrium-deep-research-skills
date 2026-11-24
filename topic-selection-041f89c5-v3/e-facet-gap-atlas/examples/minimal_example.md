# 最小示例（合成，非正式测试案例结果）

## 输入

`examples/input/records_good.jsonl`：6 篇虚构文献的类型化记录
（虚构领域：钠离子电池正极；2 任务 × 3 方法族，故意留 2 个空格、
若干指标缺口与 2 对指标集不相交记录）。
`examples/input/records_bad.jsonl`：埋了 3 处违例（缺 comparability_class 字段、
venue_kind=blog 越枚举、year=1805 越界）。

## 运行

```bash
bash examples/run_example.sh
```

## 实跑结果（示例产物，标注为合成示例）

1. `validate records_good.jsonl`：**exit 0**；
2. `validate records_bad.jsonl`：**exit 1**，准确报出 3 处违例
   （`output/validate_bad.json`）；
3. `gap records_good.jsonl`：`output/atlas/` 中——
   - 覆盖矩阵打出 **2 个空白格**（合成工艺优化×机器学习、
     容量保持率预测×高通量实验），均标注"输入文献集内未见（非全局空白）"；
   - **5 条指标覆盖缺口**（如 R2 缺报容量保持率与首效）；
   - **2 对无法直接比较的记录**（R1 vs R2、R4 vs R6，指标集不相交，附原因）。

关键观察点：空白、缺口、不可比对关系全部从记录表查询算出；把任何一条
"未见"写成全局新颖性断言都违反本技能的口径红线。
