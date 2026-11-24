# bundle-e-stats-run-gates（skill: stats-run-gates）

过程质量控制、契约强制与确定性复跑。面向 Bohrium Playground challenge-c0e1e220
（统计分析与结果解读）的独立 Skill bundle：在 64 请求 / 900 秒预算下，把三个主要失败
模式——丢工作、契约字段缺失、结果不可复跑——工程化为 **阶段门 + 契约 lint + 影子复跑**。

## 组成

| 文件 | 作用 |
|---|---|
| `scripts/statcore_e.py` | 纯标准库统计核心：不完全 Beta/Gamma 分布函数、D'Agostino K²、Levene、Student/Welch t、Mann-Whitney U、ANOVA/Welch ANOVA/Kruskal-Wallis、Hedges g、η²/ω²/ε²、bootstrap CI、Hodges-Lehmann、Holm |
| `scripts/pipeline_e.py` | 一键 baseline（run/decide/finalize）：五阶段确定性落盘，**先写契约骨架再填数**，崩溃留诚实 partial |
| `scripts/run_manifest.py` | manifest 构建/校验：输入 sha256 登记、环境、阶段状态表、seq 日志 |
| `scripts/gate_check.py` | G0–G7 阶段门（闭合律、骨架先行、数字可溯源、报告不漂移、裁决清零） |
| `scripts/contract_lint.py` | result.json vs case.json：MISSING_FIELD / INVALID_STATUS / CASE_ID_MISMATCH / DANGLING_REFERENCE 等 |
| `scripts/replay_diff.py` | 影子复跑：除声明的易变字段外全部产物逐字节 sha256 一致 |
| `references/` | stage-gates / contract-mapping / determinism / honest-partial 四篇方法学 |
| `examples/` | 合成示例（make_synthetic.py + run_example.sh 端到端自检 + 真实产物） |

## 快速验证

```bash
bash examples/run_example.sh   # 好例全门 PASS；埋雷例按预期 exit 1 并命中违例码
```

## 维护

- Python 3.9+，零第三方依赖；scipy 仅用于可选交叉校验（缺失自动跳过）。
- 全部 UTF-8 文本、无符号链接、无二进制。
- 与其他 bundle 零共享文件；统计核心独立编写。
- 维护者：99mrliu；问题请提交到 GITHUB_URL.txt 所列仓库。
