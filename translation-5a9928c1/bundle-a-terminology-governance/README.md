# bundle-a-terminology-governance

重心：**术语全生命周期治理**（抽取 → 决议 → 哈希锁定 → 执行 → 全篇一致性审计 → 安全回填）。
针对本题"术语稳"评分点：同一术语在标题、摘要、正文、图注、结论中是否始终同一译名，
且术语表被脚本**真正执行**而不是写在提示里。

## 组成

- `SKILL.md` — Agent 调用契约与工作流（/input → /app/work → /app/output，result.json 含 case_id 与全部 output_contract 字段，诚实 partial）。
- `scripts/` — extract_source / term_extract / termbase(init·decide·lock·verify-lock·export-glossary) / consistency_audit(--apply-lock) / assemble_result。纯 Python 3.10+ 标准库，幂等可重跑。
- `references/` — termbase 结构、一致性执行规则、合同字段映射。
- `examples/` — **合成**材料学摘要（含区带标记）与一键自测 `run_example.sh`（14 项断言：定义模式命中、锁定/防篡改、禁用变体检出与回填、合同字段齐全）。

## 本地自测

```bash
bash examples/run_example.sh
```

## 与 Bundle B–E 的关系

五个 bundle 相互独立、零共享文件，分别聚焦：A 术语治理 / B 段落对齐台账 /
C 数字公式引用不变量核验 / D 长文分段续译过程控制 / E 证据锚定与不确定性标注。
每个 bundle 都是可独立完成完整翻译交付的 Skill，仅重心不同。
