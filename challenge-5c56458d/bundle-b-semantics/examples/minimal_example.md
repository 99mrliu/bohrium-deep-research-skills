# 最小调用示例（合成示例，非正式案例结果）

> 本示例使用**合成数据**（脚本现场生成），仅说明接口与流程，不冒充平台
> 正式案例的运行结果。

## 合成输入

`run_example.sh` 现场生成：

- `lab.db`：表 `assay`，120 行；`class` 为 1/2/3 编码列，`additive` 同时含
  0（真实未添加）与 NULL（缺失），并含近义列 `sample_status` /
  `experiment_status`。
- `task.md`：合成任务"按 class 分组统计 alcohol 的平均值与样本数，只看
  experiment_status 为 finished 的记录"。

## 调用方式

```sh
sh examples/run_example.sh
```

依次执行 `profile_fields.py` → `build_dictionary.py` → `resolve_caliber.py`。

## 示意输出（示例，非正式结果）

- `field_profile.json`：`class` 判定为 `numeric_coded_category` 并进入
  `numeric_code_traps`；`sample_id` 判定为 identifier。
- `data_dictionary.md`：`alcohol`/`class` 命中 semantics_pack（wine 语义与
  单位）；`sample_status`/`experiment_status` 进歧义队列。
- `caliber.md`：声明粒度"每个 class 一行"、聚合 AVG+COUNT、筛选
  experiment_status='finished'；告警不得对 `class` 本身做数值聚合；
  近义状态字段的取舍记入歧义队列。

## 预期运行环境

Python 3.9+，仅标准库；示例只读源库，产物写入 mktemp 目录。
