# challenge-e97137c9 文献综述生成 — 五方向独立 Skill bundles

本题（https://play.bohrium.com/challenge/challenge-e97137c9）要求制作可被 Agent 调用的
"文献综述生成" Skill。本目录提交五个重心截然不同的独立 bundle，相互零共享文件，
各自含完整 SKILL.md、scripts/、rules|vocab|schemas/、templates/ 与可运行合成示例。

| 目录 | Skill | 重心 |
|-|-|-|
| a-source-truth-gate | source-truth-gate | 上游数据真实性：来源取证、身份核验、近重复裁定、T1/T2/T3 信任分层 + 引用门控 |
| b-budget-orchestrator | contract-first-budget-orchestrator | 过程质量控制：output_contract 先行映射、64 次请求预算编排、checkpoint/中断恢复、一致性校验 |
| c-quant-evidence-synth | quant-evidence-synth | 定量证据：数值+单位抽取、单位归一化、跨文献数值冲突检测、草稿数字回链门控 |
| d-audit-render-forge | audit-render-forge | 下游渲染工程：论断→证据→摘录→锚点的自包含 HTML 审计包、CSV 证据矩阵、手写 schema 校验闸口 |
| e-bounded-topic-appraiser | bounded-topic-appraiser | 决策端点：facet 覆盖扫描、空白-证据绑定、候选选题三维评分与有界决策备忘录 |

运行契约（每个 bundle 一致）：输入 `/input/case.json` + `/input/task.md`，工作 `/app/work`，
交付 `/app/output/`（result.json 含 case_id 与 output_contract 全部字段、status、sources、
uncertainties、change_log）；仅依赖 Python 3 标准库，有 pdftotext 时自动用于 PDF。

每个 bundle 的最小示例（合成数据，标注 simulated）：

```bash
python3 <bundle>/examples/make_example.py /tmp/<bundle>-demo
```
