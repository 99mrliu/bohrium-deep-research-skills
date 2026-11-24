# 最小调用示例（合成示例，非正式案例结果）

> 本示例使用**合成数据**（手写的三行合成结果表），仅说明接口与流程，
> 不冒充平台正式案例的运行结果。

## 合成输入

`run_example.sh` 现场写入 `result.csv`：三个合成组（control / treat_a /
treat_b）的样本数与均值（合成数，单位标注 MPa 仅为演示单位标注机制）。

## 调用方式

```sh
sh examples/run_example.sh
```

依次执行 `chart_select.py` → `render_chart.py` → `figure_caption.py`。

## 示意输出（示例，非正式结果）

- `rec.json`：命中规则 R1（categorical compare）→ 推荐 `bar`。
- `fig1.png` + `fig1.figure.json`：确定性渲染的条形图（y 轴从零、轴含
  单位、200 dpi），规格文件记录渲染器版本、条形数、PNG 字节数。
- `fig1.caption.md`：审计图注，含图型、来源、条形数、单位与
  "synthetic demo data" 注意事项。

## 预期运行环境

Python 3.9+；渲染步骤需要 matplotlib（无头 Agg），其余脚本仅标准库。
产物写入 mktemp 目录。
