# d-grade-engine

文献研究质量评估的**等级推导与校准**技能 bundle。核心立场：绝不输出孤立等级标签——所有域级/总评等级均由版本化量表（`references/thresholds.json`）中的显式阈值规则派生，并携带推导链；证据不足（弃权）沿聚合链传播，绝不参与平均。

## 内容

- `SKILL.md` — 技能说明（中文）：输入契约、工作流、预算、异常处理、result.json 契约。
- `references/grading_scale.md` — 人类可读量表：5 维度、4 等级、域映射、总评阶梯、弃权传播理由、完整演算示例。
- `references/thresholds.json` — 同一量表的机器可读版本（scale_version 1.0.0），脚本唯一阈值来源。
- `scripts/derive.py` — 维度判定 → 域级 + 总评（含推导链、弃权传播、非法行拒绝）。
- `scripts/second_rater.py` — 双人判定比对：一致率 + Cohen's kappa（纯标准库）+ 分歧/未配对清单。
- `scripts/build_result.py` — 组装 result.json + grade_report.md（契约镜像、status 规则、诚实 partial）。
- `examples/` — 完全虚构的合成示例，含真实运行输出摘录（弃权传播、kappa=0.7059）。

## 快速开始

```bash
python3 scripts/derive.py --verdicts examples/input/verdicts.jsonl --workdir /tmp/w
python3 scripts/second_rater.py --rater-a examples/input/verdicts.jsonl --rater-b examples/input/verdicts_b.jsonl --workdir /tmp/w
python3 scripts/build_result.py --workdir /tmp/w --output-dir /tmp/o --case examples/input/case.json
```

Python 3 标准库，零依赖，离线运行。退出码：0 正常 / 1 运行期错误 / 2 用法或输入文件错误。
