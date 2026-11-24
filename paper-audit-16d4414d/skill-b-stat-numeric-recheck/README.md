# stat-numeric-recheck

论文逻辑与论证审查（Bohrium challenge-16d4414d）参赛 Skill —— **统计数值确定性机审**方向。

凡能从论文文本自身重算的数值主张，交给确定性引擎重算：p 值 vs 显著性措辞、百分比 vs 分子分母、CI 连贯性、不可能值、跨章节数值口径、效应方向 vs 数值顺序（C1–C6）。工具只产出候选，判断留给 Agent；交付前过逐字 quote 关卡。

## 组成

| 文件 | 作用 |
|-|-|
| `SKILL.md` | Skill 本体：触发条件、运行契约、执行协议、异常处理 |
| `scripts/statscan.py` | 引擎：scan / check / verify 三子命令，纯标准库（Python ≥3.8），确定性，零依赖 |
| `references/checks.md` | C1–C6 判定式、容差、误报护栏、确认要点、严重度映射 |
| `examples/minimal/` | **合成示例**（非正式案例）：植入六处数值缺陷的合成短文，端到端演示 |
| `GITHUB_URL.txt` | 本作品公开仓库链接 |

## 快速验证（本地）

```sh
sh examples/minimal/run_example.sh
```

预期：7 条候选命中全部六类缺陷；verify 退出码 4 拦下一条非逐字 quote。产物真实生成于 `examples/minimal/outputs/work/`。

## 平台运行契约

输入 `/input/case.json`、`/input/task.md`、论文材料；工作区 `/app/work`；交付 `/app/output/result.json`（含原 `case_id` 与 `output_contract` 全部字段、诚实 status、provenance、uncertainty）。零候选是有效结果（写入通过项）；截断/无文本层列入未检查项，不编造。

## 限制

只做"文本内可重算"的一致性，不做原始数据重分析（本题排除项）；拼写数字、表格内复杂结构、非英文数值格式覆盖有限；C5 需语义确认，误报边界见 references/checks.md。
