# bundle-b-paragraph-alignment-ledger

重心：**段落完整性与段号一一对应**。语义分段（标题/正文/题注/公式/列表独立成块）、
跨栏断词与换行修复留痕、内容哈希覆盖台账（拒未知 ID/拒重复/拒错位）、
段落级双语对齐导出。针对本题"段落全"评分点：不漏段、不重复、不错位、段号可回溯。

## 组成

- `SKILL.md` — Agent 调用契约与工作流（/input → /app/work → /app/output，result.json 含 case_id 与全部 output_contract 字段，诚实 partial）。
- `scripts/` — segment_docs(run·repair-report) / coverage(init·apply·list-pending·report) / align_export。纯 Python 3.10+ 标准库，幂等可续跑。
- `references/` — 段号约定、覆盖规则、合同字段映射。
- `examples/` — **合成**两栏摘录与一键自测 `run_example.sh`（13 项断言：分段与修复留痕、拒绝未知/错位回填、全绿导出、缺段 partial）。

## 本地自测

```bash
bash examples/run_example.sh
```

## 与 Bundle A/C/D/E 的关系

五个 bundle 相互独立、零共享文件，分别聚焦：A 术语治理 / B 段落对齐台账 /
C 数字公式引用不变量核验 / D 长文分段续译过程控制 / E 证据锚定与不确定性标注。
