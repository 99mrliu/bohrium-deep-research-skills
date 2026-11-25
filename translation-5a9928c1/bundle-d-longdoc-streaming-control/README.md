# bundle-d-longdoc-streaming-control

重心：**长文分段续译的过程控制**。语义切块（段落原子、词元预算）、可续跑状态台账
（源文哈希绑定、篡改拒绝、幂等重跑）、逐块上下文包（前块已译尾部+下块源文头部+术语表）、
请求/时间预算记账（64/900 包线）、中断 partial 诚实交付。针对长文"漏块、重块、断点丢失、
预算失控"四类过程失败。

## 组成

- `SKILL.md` — Agent 调用契约与工作流（/input → /app/work → /app/output，result.json 含 case_id 与全部 output_contract 字段，诚实 partial）。
- `scripts/` — extract_source / plan_chunks / stream_state(init·mark-done·list-pending·report) / context_pack / assemble_result。纯 Python 3.10+ 标准库，幂等可续跑。
- `references/` — 切块规则、state 格式、预算规则。
- `examples/` — `make_synthetic.py` 合成长文生成器 + 一键自测 `run_example.sh`（19 项断言）。

## 本地自测

```bash
bash examples/run_example.sh
```

## 与 Bundle A/B/C/E 的关系

五个 bundle 相互独立、零共享文件，分别聚焦：A 术语治理 / B 段落对齐台账 /
C 数字公式引用不变量核验 / D 长文分段续译过程控制 / E 证据锚定与不确定性标注。
