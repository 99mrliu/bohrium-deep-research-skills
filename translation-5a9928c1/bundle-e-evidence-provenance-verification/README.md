# bundle-e-evidence-provenance-verification

重心：**可核验性**。每段译文绑定原文引文+偏移并由脚本机器核验（防篡改、防错锚）、
源文覆盖缺口检测（防漏译）、译法依据留痕（literal/termbase/convention/uncertain）、
不确定性登记册与诚实状态推导（success/partial/failed）、人工确认清单。
针对本题"可核验"评分点。

## 组成

- `SKILL.md` — Agent 调用契约与工作流（/input → /app/work → /app/output，result.json 含 case_id 与全部 output_contract 字段，诚实 partial）。
- `scripts/` — extract_source / anchor_evidence / uncertainty_register / verification_report / assemble_result。纯 Python 3.10+ 标准库。
- `references/` — 证据结构、不确定性规则、合同字段映射。
- `examples/` — **合成** ML 摘录与一键自测 `run_example.sh`（12 项断言：篡改引文检出、覆盖缺口检出、全绿 success、诚实 partial）。

## 本地自测

```bash
bash examples/run_example.sh
```

## 与 Bundle A/B/C/D 的关系

五个 bundle 相互独立、零共享文件，分别聚焦：A 术语治理 / B 段落对齐台账 /
C 数字公式引用不变量核验 / D 长文分段续译过程控制 / E 证据锚定与不确定性标注。
