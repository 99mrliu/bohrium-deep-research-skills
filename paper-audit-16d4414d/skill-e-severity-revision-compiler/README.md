# severity-revision-compiler

论文逻辑与论证审查（Bohrium challenge-16d4414d）参赛 Skill —— **下游交付工程**方向。

把判断完的 findings 变成可交付审查报告：形式门禁（必填字段/枚举/三维定级依据/空话词表）、定级校准（≥4 条同级告警）、修复优先级队列（严重度×可修正性）、编译 report.md 与 result_fields.json。它不判断论文，它判断 finding 的交付形态。

## 组成

| 文件 | 作用 |
|-|-|
| `SKILL.md` | Skill 本体：触发条件、运行契约、执行协议、异常处理 |
| `scripts/compile_report.py` | 引擎：lint / priority / compile 三子命令，纯标准库（Python ≥3.8），确定性，零依赖 |
| `references/severity_rubric.md` | 定级决策树、三维依据、锚例、反失真规则 |
| `references/revision_patterns.md` | 七种操作类型模板、六类检查项建议侧重、反模式 |
| `examples/minimal/` | **合成示例**（非正式案例）：植入一条空话建议，演示拦截→修复→编译全流程 |
| `GITHUB_URL.txt` | 本作品公开仓库链接 |

## 快速验证（本地）

```sh
sh examples/minimal/run_example.sh
```

预期：lint 拦下空话建议（exit=7）；修复后放行；优先级队列 critical 排首；编译出按优先级排序的报告。产物真实生成于 `examples/minimal/outputs/`。

## 平台运行契约

输入 `/input/case.json`、`/input/task.md`、论文材料与审查 findings；工作区 `/app/work`；交付 `/app/output/report.md` + `result_fields.json`（含 `case_id`，并入 `result.json`）。lint/compile 双重门禁不过则不产出交付物。

## 限制

只管交付形态不管判断质量（错误判断通过门禁仍是错误判断）；空话词表覆盖中英常见表述，新空话需人工把关；优先级排序是严重度×可修正性的字典序，不含领域权重。
