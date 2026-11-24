# metric-schema.md — 响应指标注册表规范

`metric_registry.json` 的 schema（`schema_version: "1.0"`）与填写规则。
由 `scripts/metric_registry.py` 生成；Agent 也可手工准备 `--spec` JSON 输入。

## 1. 顶层结构

```json
{
  "schema_version": "1.0",
  "generated_by": "metric_registry.py",
  "spec_source": "--spec | case.json:response_metrics | inferred-from-csv",
  "factors": ["temp_C", "time_h"],
  "metrics": [ /* 见 §2 */ ],
  "validation": {
    "status": "ok | degraded | empty | error",
    "n_checks": 0,
    "n_failed": 0,
    "checks": [ /* 见 §4 */ ],
    "uncertainties": [ "人类可读的诚实声明，必须原样进入 result.json 的 uncertainty" ]
  }
}
```

## 2. metrics[] 条目（必填语义）

| 字段 | 类型 | 规则 |
|---|---|---|
| `name` | string | 响应指标列名，必须与历史 CSV 列名完全一致（大小写敏感） |
| `unit` | string 或 null | SI 或领域通用单位（如 `%`, `degC`, `MPa`）。**未知就写 null，禁止猜测**；null 时一切跨来源数值比较不可信 |
| `method` | string 或 null | 测量方法与仪器口径（如 "HPLC 面积归一化法"）。方法不同则数据不可直接合并 |
| `direction` | enum | `maximize` / `minimize` / `target`。缺省 `maximize` 并记 uncertainty；`target` 时应同时给 `target` 值 |
| `acceptable_fluctuation` | object 或 null | 测量重复性可接受波动，如 `{"type":"absolute","value":1.5,"unit":"percentage_point"}` 或 `{"type":"relative","value":0.03}`。缺失记 uncertainty：后续不得把小于测量噪声的差异当成"改进" |
| `target` | number（可选） | direction=target 时的目标值 |

## 3. 规格来源优先级

1. `--spec metrics.json`（Agent 从案例材料中人工抽取，最可信）；
2. `case.json` 的 `response_metrics` 字段；
3. 从 CSV 推断：不在 `--factors` 列表中、且多数单元格为数值的列视为响应指标，
   此时 unit/method/acceptable_fluctuation 全部为未知并产生 uncertainty，
   `validation.status` 至少为 `degraded`。

## 4. 一致性校验（checks）

| check | 触发 fail 的条件 | 后果 |
|---|---|---|
| `csv_readable` | CSV 不存在/不可解析 | 全部列校验跳过，status=degraded 或更差 |
| `spec` | 条目缺 name/unit/method，direction 非法，缺 acceptable_fluctuation | 逐条记 uncertainty |
| `column_present` | 指标列不在 CSV 表头 | 该指标无证据来源；result.json 对应字段须降级 |
| `numeric` | 指标列存在非数值/缺失单元格 | 记录数量；拟合脚本会跳过坏行 |
| `factor_present` | 声明的因子列不在 CSV 表头 | 该因子不可用于建模 |

`status` 汇总：`ok`（0 fail）、`degraded`（有 fail 但仍有可用指标）、
`empty`（无指标）、`error`（脚本内部异常，已兜底，不会 traceback）。

## 5. 填写纪律（写给 Agent）

- **先注册，后比较**：任何"这个条件比那个好"的陈述之前，确认两个数的
  unit/method 一致、差异 > acceptable_fluctuation；
- 单位换算必须写明换算关系并进 `sources`；拿不准的换算视同单位缺失；
- 材料（PDF/文本）中口径信息不全时，宁可在 uncertainty 里写"未声明"，
  也不要用常识补齐——补齐的口径是幻觉的高发区；
- 注册表的 `validation.uncertainties` 必须原样汇总进 result.json 的
  `uncertainty` 字段，不得润色删除。
