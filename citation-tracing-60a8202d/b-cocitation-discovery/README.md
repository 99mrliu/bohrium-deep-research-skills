# cocitation-parallel-discovery

共被引／文献耦合的平行工作发现 Skill：找不直接引用种子但同属一个方法脉络的文献，逐候选保留可复核的关联证据。对应赛题"引文追踪与关联文献发现"的**方向 2（关联文献发现）**。

## 文件清单

| 文件 | 作用 |
|-|-|
| `SKILL.md` | Skill 本体 |
| `rules/signal_spec.md` | 信号定义、入选门槛、抗噪声原则、参数指引 |
| `scripts/codiscover.py` | 主脚本（Python 3.8+，仅标准库） |
| `scripts/verify_discovery.py` | 独立自查脚本 |
| `templates/result_fields.md` | result.json 字段契约 |
| `examples/example_walkthrough.md` | 合成数据最小示例（示意） |

## 依赖

Python ≥ 3.8，仅标准库，无网络依赖。输入 `/input/case.json`＋本地语料；输出 `/app/output/result.json`（镜像 output_contract）＋ `evidence_table.md`。

## 使用

```bash
python3 scripts/codiscover.py --case /input/case.json --out /app/output --workdir /app/work
python3 scripts/verify_discovery.py /app/output /app/work
```

## 适用场景与限制

- 适用：平行工作发现、方法脉络扩展、综述候选集补充、需要"关联依据"的推荐解释。
- 限制：共被引信号依赖本地语料的施引记录覆盖；覆盖不足时退化为以耦合为主，并如实说明。不做直接引文追踪、不做身份合并、不做全文语义。

## 维护信息

版本 1.0（challenge-60a8202d 提交版）。阈值与权重见 `rules/signal_spec.md`，通过命令行参数调整。
