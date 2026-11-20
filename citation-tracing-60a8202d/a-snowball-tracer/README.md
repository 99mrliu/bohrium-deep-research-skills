# dir-aware-snowball-tracer

方向感知的多跳引文雪球追踪 Skill：从种子论文出发，后向沿参考文献、前向沿施引文献逐层扩展，带分支剪枝、停止判据与逐边数据源证据。对应赛题"引文追踪与关联文献发现"的**方向 1（前向/后向追踪）**。

## 文件清单

| 文件 | 作用 |
|-|-|
| `SKILL.md` | Skill 本体：用途、输入输出、调用方式、异常处理 |
| `rules/traversal_policy.md` | 方向定义、扩展/剪枝/停止规则、证据与诚实性规范 |
| `scripts/snowball_trace.py` | 主脚本（Python 3.8+，仅标准库，无安装步骤） |
| `scripts/verify_trace.py` | 独立自查脚本 |
| `templates/result_fields.md` | result.json 字段契约 |
| `examples/example_walkthrough.md` | 合成数据最小示例（示意，非正式案例结果） |

## 依赖与环境

- Python ≥ 3.8，仅标准库；无第三方依赖、无网络依赖（`--allow-net` 为可选 best-effort）。
- 输入契约：`/input/case.json`（含 case_id、种子标识、output_contract）＋本地语料文件。
- 输出契约：`/app/output/result.json`（镜像 output_contract 全字段）＋ `trace_graph.json` ＋ `evidence_table.md`。

## 一次完整使用

```bash
python3 scripts/snowball_trace.py --case /input/case.json --out /app/output --workdir /app/work
python3 scripts/verify_trace.py /app/output /app/work
```

## 适用场景与限制

- 适用：以种子论文为起点的后向出处追踪、前向后续工作追踪、多跳扩展、需要逐边证据的综述候选集构建。
- 限制：前向覆盖受本地语料引用记录的完整性约束；语料未收录的施引文献只能以"无记录"如实报告。不做关键词检索、不做全文语义理解、不做未授权抓取。

## 维护信息

- 版本：1.0（challenge-60a8202d 提交版）。去重键、剪枝阈值见 `rules/traversal_policy.md`，修改阈值通过命令行参数完成，无需改代码。
