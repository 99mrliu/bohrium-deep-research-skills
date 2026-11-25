# bundle-c-fidelity-invariants-audit

重心：**数字、单位、公式、引用、否定与限定的守恒核验**。从源文与译文两侧确定性抽取
保真不变量（quantity/statistic/citation/ref/negation/qualifier），逐段句对齐比对，
输出 missing/changed/added/negation_lost/qualifier_lost 与人工确认清单。
针对本题"关系准"评分点。

## 组成

- `SKILL.md` — Agent 调用契约与工作流（/input → /app/work → /app/output，result.json 含 case_id 与全部 output_contract 字段，诚实 partial）。
- `scripts/` — extract_source / segment_docs / extract_invariants / audit_invariants / assemble_result。纯 Python 3.10+ 标准库。
- `references/` — 不变量分类与归一化、否定限定守恒规则、合同字段映射。
- `examples/` — **合成**临床摘要与好/坏两份合成译文，一键自测 `run_example.sh`（10 项断言：六类不变量抽取、planted errors 全部检出、好译文零硬差异、partial 诚实状态）。

## 本地自测

```bash
bash examples/run_example.sh
```

## 与 Bundle A/B/D/E 的关系

五个 bundle 相互独立、零共享文件，分别聚焦：A 术语治理 / B 段落对齐台账 /
C 数字公式引用不变量核验 / D 长文分段续译过程控制 / E 证据锚定与不确定性标注。
