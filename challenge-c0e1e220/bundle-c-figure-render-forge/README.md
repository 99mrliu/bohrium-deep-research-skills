# bundle-c-figure-render-forge

Bohrium Playground challenge-c0e1e220（统计分析与结果解读）五份独立 Skill bundle 之 **Bundle C**。
重心：**下游渲染工程与图表证据**——按数据形态选图、双通道渲染（matplotlib PNG / 纯 Python 确定性 SVG）、
图注携带每组 n 与单位、图表机器可审计（5 违例码）。

## 文件清单

| 路径 | 用途 |
|---|---|
| `SKILL.md` | agent 面向的技能说明（8 必备章节） |
| `GITHUB_URL.txt` | GitHub 树 URL |
| `scripts/statcore_c.py` | 独立 stdlib 统计核心（t/F/χ²/正态分布函数、K²、Levene、t/Welch/MWU、ANOVA/Welch ANOVA/KW、Hedges g bootstrap、HL、η²/ω²/ε²、Holm） |
| `scripts/pipeline_c.py` | 一键 baseline：`run` / `decide` / `finalize` → result.json（9 字段+sources+reproducibility 等）+ report.md + digest.md |
| `scripts/figure_forge.py` | 重心 1：图形选择规则引擎 + 双通道渲染，产出 fig<N>.png/.svg + figures.md |
| `scripts/figure_audit.py` | 重心 2：机器审计（MISSING_FIGURE / BAD_SIGNATURE / CAPTION_NUMBER_MISMATCH / RULE_VIOLATION_BAR / MISSING_COVERAGE） |
| `references/` | figure-selection.md、caption-rules.md、dual-channel-rendering.md |
| `examples/` | make_synthetic.py、run_example.sh（好例+埋雷自断言）、minimal-example.md、example_output/（真实文本产物） |

## 快速验证

```bash
bash examples/run_example.sh    # 端到端：合成示例 + 审计 + 埋雷拦截，全过 exit 0
```

## 维护信息

- Python 3.9+；统计核心零第三方依赖；matplotlib 仅可选增强（try/except 降级 SVG）。
- 确定性：seed=20240501（bootstrap / 子样本 / 抖动全固定）；SVG 字节级可复现。
- 统计核心已对本机 scipy 1.18 交叉校验（t/F/χ² CDF 与逆函数、K²、Levene、t/Welch/MWU、ANOVA/KW，容差 ≤1e-8）。
- 维护者：见 GITHUB_URL.txt 指向的仓库。
