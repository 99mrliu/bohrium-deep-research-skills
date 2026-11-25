---
name: longdoc-streaming-translation-control
description: >-
  当科研翻译案例是长文（多章节、超单次响应容量）且核心风险是"分段漏译、重复翻译、上下文丢失、中断后无法续跑、预算失控"时使用本 Skill。
  Use when a scientific-translation case (/input/case.json + task.md + long source) requires streaming process control: semantic chunk planning that never splits a paragraph across chunks (token budget per chunk, headings/captions/formulas as atomic units), a resumable state ledger binding every translated chunk to its source hash (tamper-evident), context packages carrying the previous translated tail + next source head + locked glossary into each chunk translation, idempotent re-runs, budget accounting (64 model requests / 900 s envelope) with early partial delivery, and contract-driven result.json with case_id and every output_contract field plus honest partial status.
  不做的事：不在块边界切断段落、不重复计数已完成块、不用过期上下文续译、不在预算耗尽时静默丢弃剩余块。
---

# longdoc-streaming-translation-control（长文分段续译与断点续跑，Bundle D）

本 Skill 的重心是**过程控制**：长文翻译的失败大多是过程失败——漏块、重块、断点丢失、
预算失控。脚本把长文切成"段落原子"块、维护可续跑状态台账、为每块组装上下文包并记账
请求数与时间；Agent 只负责按上下文包逐块翻译。完整性由台账哈希保证，与 Bundle B 的
段级台账互补（D 管"批/流"，B 管"段/账"）。

## 何时使用 / 边界

**适用**：全文较长（多页/多章节）、超出单次响应容量或需多轮续译的案例。
**不适用**：三五行短文本（直接整段译，无需切块）；台账保证块级完整，不替代语义核验
（与 Bundle C 的审计或人工复核组合使用）。

## 运行契约

- 输入：`/input/case.json` + `/input/task.md` + 源文件。
- 中间产物（`/app/work/streamjob/`）：`source.md`、`plan.json`、`state.json`、`context/cNNN.md`、`chunks/cNNN.translated.json`。
- 交付（`/app/output/`）：`result.json`（`case_id` + 合同全部必填字段）、`bilingual.md`、`state_report.json`。
- 诚实 partial：中断或预算耗尽时，已完块照常交付，`status=partial` 并列出未译块清单；
  绝不静默丢弃。

## 精确命令工作流

```bash
# 0. 定向
cat /input/case.json /input/task.md; ls -la /input
export SKILL_DIR=$(dirname $(find /skills -maxdepth 3 -name SKILL.md -path '*longdoc-streaming*' 2>/dev/null | head -1))
S=$SKILL_DIR/scripts; W=/app/work/streamjob; O=/app/output; mkdir -p $W/context $W/chunks $O

# 1. 取源文 + 切块计划（段落原子：永不切断段落；默认每块 ≤1200 估计词元）
python3 $S/extract_source.py --input /input --out $W/source.md
python3 $S/plan_chunks.py --source $W/source.md --budget-tokens 1200 --out $W/plan.json

# 2. 初始化续跑台账（哈希绑定，防源文被改动后续译）
python3 $S/stream_state.py init --plan $W/plan.json --out $W/state.json

# 3. 逐块循环（Agent 每块 1 次请求；中断后从 list-pending 继续）：
for C in $(python3 $S/stream_state.py list-pending --state $W/state.json); do
  python3 $S/context_pack.py --plan $W/plan.json --state $W/state.json \
      --chunk $C --glossary $W/glossary.md --tail-chars 600 --head-chars 300 \
      --out $W/context/$C.md
  #   读 context 包 → 翻译该块全部单元 → 写 $W/chunks/$C.translated.json
  #   [{"unit_id":"u0007","source":"…","translation":"…"}]
  python3 $S/stream_state.py mark-done --state $W/state.json --plan $W/plan.json \
      --chunk $C --translations $W/chunks/$C.translated.json --requests 1 --seconds 25
done
#   预算告警：list-pending 输出剩余请求/秒；剩余不足时立即转 partial 交付。

# 4. 状态报告 + 组装交付
python3 $S/stream_state.py report --state $W/state.json --out $O/state_report.json
python3 $S/assemble_result.py --case /input/case.json --plan $W/plan.json \
    --state $W/state.json --translations-dir $W/chunks --out $O
```

`result.json`：完整译文为已完块按序拼接（未译块不填充、不伪造）；`bilingual` 按单元级
对照；`uncertainties` 列未译块与预算状态；`status`：全部块 done → `success`，否则 `partial`。

## 过程纪律

- 块内必须一次译完全部单元后 mark-done；部分单元缺失时 mark-done 拒绝（exit 1）。
- mark-done 校验源单元哈希与 plan 一致；源文被改动后必须重新 plan（新 job），
  禁止在旧台账上续跑。
- 重复 mark-done 同内容 = 幂等跳过，不重复计请求。
- 上下文包只携带：前块已译尾部、下块源文头部、锁定术语表节选、未决问题——
  不携带无关全文，控制每请求体积。
- 预算台账：每块如实登记 requests/seconds；剩余不足时优先交付已完成部分。

## 最小调用示例（合成示例，非正式案例结果）

`examples/make_synthetic.py` 生成一篇**合成的**长文（4 章节、30+ 段，含题注与公式）。
`run_example.sh` 跑通 计划→台账→上下文包→逐块翻译（合成译文）→中断/续跑→幂等重跑→
报告→组装，并断言：(a) 块不切断段落且不超预算；(b) 篡改源单元后 mark-done 拒绝；
(c) 中断后续跑只列未决块；(d) `result.json` 合同字段齐全。示意输出见 `examples/example_output/`。

## 预算、可靠性与限制

- 官方包线 64 请求 / 900 秒：块数 = f(源长/块预算)；每块恰 1 次翻译请求 +
  少量脚本调用；台账实时显示剩余额度。
- 稳定性：全部脚本幂等；`stream_state.py resume` 是唯一的续跑入口。
- 异常处理：源文无文字层 → plan 阶段退出并说明；某块反复失败 → 标 failed，
  交付其余块并列出。
- 限制：估计词元为启发式（chars/4），与真实模型计费不同，仅用于切块与预算提示；
  块间长程照应（全文术语一致性）依赖 glossary 与人工复核。
