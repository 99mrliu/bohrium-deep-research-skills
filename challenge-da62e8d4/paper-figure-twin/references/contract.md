# 数据契约与比较语义

## 文件与权限

正式运行只接受 `/input/case.json` 和 `/input/task.md` 作为任务入口。`/input` 只读；脚本、命令和渲染器不得写入其中。临时方法输出、日志和中间文件放 `/app/work`，最终交付只放 `/app/output`。本仓库示例用显式 `--case`、`--spec`、`--work`、`--output` 参数演示同一契约；示例路径不冒充正式平台路径。

比较程序不会解析 PDF、执行 OCR、识别曲线、猜测缺失 anchor，或从 task.md 自动推断容差。人工操作者必须先从真实 PDF 页渲染出源图，人工采样 pixel points，并记录 figure/page/panel、刻度 anchor、映射及不确定性。组织方提供的合成图和候选方法不是论文作者代码，报告中必须区分。

## case.json

```json
{
  "case_id": "unique-case-id",
  "task": "/input/task.md",
  "spec": "/app/work/comparison_spec.json",
  "candidates": [
    {
      "id": "candidate_a",
      "label": "方法 A",
      "command": ["python3", "method_a.py", "--output", "{work}/a.json"],
      "output": "{work}/a.json",
      "cwd": "/app/work",
      "implementation_provenance": "组织方合成方法，非论文作者代码"
    }
  ],
  "timeout_seconds": 120,
  "output_contract": {
    "required_fields": ["case_id", "status", "sources", "summary", "comparison", "uncertainty", "change_records"]
  }
}
```

`command` 是字符串数组，不用 shell 拼接。占位符 `{work}`、`{output}`、`{case_dir}`、`{spec_dir}` 在参数内替换。每个候选必须真实执行且有独立 `id`、数值输出路径；失败、超时或输出不存在会使任务交付 partial。单个方法运行超时由 `timeout_seconds` 控制，正式总预算仍不得超过 900 秒。

## comparison spec

```json
{
  "version": 1,
  "figure": {
    "source_file": "paper_page.png",
    "source_locator": "paper.pdf#page=4&figure=2b",
    "figure": "Fig. 2",
    "page": 4,
    "panel": "b",
    "render_dpi": 200,
    "note": "由真实 PDF 第4页渲染；无预抽取文本层"
  },
  "axes": {
    "x": {"name": "time", "paper_unit": "s", "pixel_scale": "linear", "anchors": [{"pixel": 80, "value": 0}, {"pixel": 720, "value": 8}]},
    "y": {"name": "signal", "paper_unit": "mV", "pixel_scale": "linear", "anchors": [{"pixel": 400, "value": 0}, {"pixel": 60, "value": 2}]}
  },
  "tolerances": {"rmse": 0.05, "mae": 0.05, "max_error": 0.15, "unit": "mV", "declared_before_comparison": true, "source": "task.md 数值容差条款"},
  "series": [
    {
      "id": "paper_s1",
      "label": "Paper S1",
      "unit": "mV",
      "x_definition": "time_since_start_s",
      "points_file": "paper_points.json",
      "candidate_series": [
        {"candidate_id": "candidate_a", "series_id": "a_s1", "unit": "mV", "x_definition": "time_since_start_s"},
        {"candidate_id": "candidate_b", "series_id": "b_s1", "unit": "mV", "x_definition": "time_since_start_s"}
      ]
    }
  ]
}
```

`pixel_scale` 只有 `linear` 和 `log`。`log` 的 anchor value 和待转换坐标值必须大于 0；它描述数据值到 pixel 的对数映射，不表示对 pixel 坐标取对数。每轴至少两个不同 pixel 的 anchors，其对应数据值（log 时为 `log(value)`）必须不同。三点及以上 anchors 使用最小二乘拟合，并把逐 anchor 残差写入 mapping ledger；不隐藏非共线残差。

每个 series 的 `unit` 和 `x_definition` 必须与对应候选逐项完全一致。没有内置单位换算：未知换算不可猜，需先由上游在 ledger 中记录并执行明确换算。若 candidate 已经是相同 x definition 的原始网格，也在 paper overlap 内线性插值；不外推。

## paper_points.json

```json
{
  "series": [
    {
      "id": "paper_s1",
      "points": [
        {
          "pixel_x": 80.0,
          "pixel_y": 400.0,
          "source": {"figure": "Fig. 2", "page": 4, "panel": "b", "source_file": "paper_page.png", "locator": "manual click 1"},
          "uncertainty": {"pixel_x": 1.0, "pixel_y": 1.5, "method": "manual_pixel_click"},
          "value_status": "digitized"
        }
      ]
    }
  ]
}
```

每个点必须明确 `value_status: digitized`。`paper-reported` 数值不能伪装为 pixel 点；如任务另需引用论文表格，应另表记录且不得进入 pixel RMSE。每个点需 source locator 和 uncertainty；uncertainty 至少含 `pixel_x`、`pixel_y` 和 `method: manual_pixel_click`。点转换后若不在有限数轴范围内则失败。源图缺失、source locator 不一致、anchor 缺失都不可比较。

## candidate 输出（JSON）

顶层可为 `{"series": [...]}`，也可直接是 series 数组。每项：

```json
{"id":"a_s1","unit":"mV","x_definition":"time_since_start_s","points":[{"x":0.0,"y":0.0}],"source":{"method":"method_a","run_id":"optional"}}
```

CSV 需要表头 `series_id,x,y,unit,x_definition`，每个数据点的 unit/x_definition 均须与表头声明一致。额外列会保留在 ledger 的输入统计之外但不参与误差。候选点必须有限，同 series 内 x 严格递增且无重复。

## 动态 output_contract 与 result 装盒

不能只实现示例的 `required_fields`。脚本独立解析并平铺以下常见形式；合同声明的字段名可以是 `case_id/status/sources/uncertainty/change_records` 等标准字段，不能因此拒绝合同。

1. **List**：`["summary", "comparison", {"name":"custom_field"}]`。对象项可用 `name/field/key/id`，`required:false` 表示可选。
2. **直接 mapping**：`{"summary":{"type":"string"}, "custom_field":{"type":"object"}}`；每个 key 是一个顶层字段，`required:false` 同样表示可选。
3. **fields / required_fields**：值为上述 list 或 mapping；两者同时出现时合并去重。单独的 `required` list 也可读。
4. **JSON Schema**：读取 `properties`；有 `required` 字符串数组时只强制其中字段（即使某字段未在 properties 声明也保留），没有 `required` 时把所有 properties 当成交付字段。单一的 `{"schema": ...}` 或 `{"output_contract": ...}` 包装也可读。

`result.json` 顶层**始终**包含 `case_id`、`status`、`sources`、`uncertainty`、`change_records`，并逐个包含当前 case 合同字段，不能把它们藏在 `result.output_contract` 或固定模板中。工具额外字段限 `artifacts/comparison/mapping/report/errors/reproduction_verdict`；`summary` 只有合同要求才输出。partial/unable 也走同一装盒函数：能够读取 case 时仍平铺全部合同字段，未生成文件对应的 comparison/mapping/report 为 null。

脚本内生的标准字段和 `reproduction_verdict` 来自真实运行。未知的自定义字段只从 `spec.contract_values[field]` 获取 case-specific、有证据的值，例如：

```json
{
  "contract_values": {
    "custom_delivery": {
      "value": "example evidence-backed value",
      "evidence_path": "comparison.json"
    }
  }
}
```

没有值或值为 null 时，字段仍须存在，但只能是结构化说明：

```json
{"status":"unavailable", "reason":"No evidence-backed value ... spec.contract_values.", "evidence_required":true}
```

这表示交付不全，整体必须 `status=partial` 并退出 1，即使数值计算已完成；不得把 unavailable 改写成看似有内容的科学结论。所有生成的路径字段相对 output，不能写绝对产物路径；命令 argv 则按真实执行情况保存。

## 最终产物

完整科学比较的目录固定包含：

- `comparison.json`：机器可读的逐 pair 指标、overlap、容差、科学判定、任务状态和 candidate/paper 对齐点。
- `mapping.json`：源图定位、轴 anchors、拟合映射、anchor 残差、每个 paper pixel 的 source/uncertainty/转换值，以及 candidate series 的来源与对齐元数据。
- `report.md`：材料与环境、候选命令及退出码、参数、数值表、SVG/PNG 链接、误差归因与限制；图不替代表。
- `result.json`：上述动态平铺合同以及实际交付信息。
- 每对 series 的 `<pair>_overlay.svg`、`<pair>_error.svg`、`<pair>_overlay.png`、`<pair>_error.png`，以及 `side_by_side.svg`、`side_by_side.png`。

### 两层判定与退出码

| 条件 | result.status | reproduction_verdict | 退出码 |
|---|---|---|---:|
| 材料/执行/交付完整，所有 pair 在容差内 | success | pass | 0 |
| 材料/执行/交付完整，至少一个 pair 数值超差 | success | fail | 2 |
| 缺材料、anchor、重叠，或运行/渲染/动态合同交付不全 | partial | not_comparable；若科学比较实际完整，可为 pass/fail | 1 |
| case 完全无法读取 | unable | not_comparable | 1 |

`refused` 是平台允许的状态，但本工具没有政策拒绝分支。数值超差是科学 `reproduction_verdict=fail`，不是任务 `status=fail`，也不写入任务执行 `errors`。正式运行在 output 可写时尽力生成同样动态的 partial/unable result，而不伪造完整产物。
