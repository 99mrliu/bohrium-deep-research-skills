---
name: replay-verification-pack
description: 文献证据驱动写作——可复核性工程（第三方一键重验包）。当任务评分关注"复得现"（论断清单、证据表、原文摘录和判定理由能被他人独立回查与重跑），或交付物需要被评审、合作者、另一个 Agent 独立复核时使用。本 Skill 的重心在"交付之后"：pack_manifest.py 把产物文件哈希、逐字摘录、关键数字、文献条目、契约键固化为一份核验清单，verify_pack.py 让复核方在不调用模型、不信任交付过程的前提下一条命令重验全部承诺。把"看起来完整的成稿"升级为"机器可重验的交付包"。
---

# 可复核性工程（Replay Verification Pack）

## 这个 Skill 解决什么问题

评分要求"论断编号、原文摘录、定位信息与强度理由能否被独立复核"——但通常交付的只有一份成稿，复核者要逐句回原文核对，成本高到事实上无人复核。本 Skill 把可复核性做成工程产物：交付时附一份**核验清单**（manifest），复核方运行一个脚本即可重算文件哈希、逐字重查摘录、重新命中数字、核对契约键，全程不需要模型、不需要信任交付方。哈希机制同时保证"打包后改动必被发现"。

## 何时使用

- 任务要求结果可核验、可回查（证据表、引用核验、论断清单类交付）；
- 交付物将被独立评审或多轮迭代（哈希让"哪版动过"一目了然）。

不适用：纯一次性阅读物；无任何来源承诺要核验的自由文本。

## 运行契约

- 输入：`/input/case.json`、`/input/task.md`、材料文件；工作区 `/app/work`；产物、`result.json`、manifest 与自检报告放 `/app/output`。
- `result.json` 含原样 `case_id` 与 `output_contract` 全部键；manifest 未覆盖的内容在 `limits` 如实声明（见 references/replay_protocol.md 第 5 节）。
- 预算意识：打包与自检是秒级脚本；先产出全键 partial，再补承诺项。

## 依赖

- Python ≥3.9 标准库，无网络依赖。
- 脚本：`scripts/pack_manifest.py`（生成核验清单）、`scripts/verify_pack.py`（独立重验）；协议：`references/replay_protocol.md`。

## 工作流（严格按序执行）

**步骤 0 — 读契约、备文本**
```bash
mkdir -p /app/work/text /app/output
```
读 case.json（case_id、output_contract 全部键）、task.md；把材料全文提取到 `/app/work/text/<source>.txt`（`\f` 分页，PDF 用 `pdftotext -layout`）。

**步骤 1 — 证据承诺登记（模型）**
写作过程中同步维护 `/app/work/evidence_pack.json`：
- `quotes`：每条逐字摘录 `{id, source, quote}`——quote 必须是来源文本的连续原文；
- `numbers`：每个关键数字 `{id, source, value, context}`；
- `refs`：每条文献 `{n, title, authors, year}`。
登记纪律：只登记**能兑现的**承诺；兑现不了的表述不进成稿。

**步骤 2 — 成稿与契约产物（模型）**
写 deliverable 与各契约键产物到 /app/output；按 output_contract 组装 result.json（含 case_id、status、sources、uncertainty、change_log、limits）。

**步骤 3 — 生成核验清单（脚本）**
```bash
python3 /skills/weekly-skill/scripts/pack_manifest.py --output-dir /app/output \
  --manifest /app/output/verification_manifest.json \
  --evidence /app/work/evidence_pack.json
```

**步骤 4 — 自检（脚本，模拟复核方）**
```bash
python3 /skills/weekly-skill/scripts/verify_pack.py --output-dir /app/output \
  --sources /app/work/text \
  --manifest /app/output/verification_manifest.json \
  --report /app/output/verify_report.md
```
- 任何 FAIL：修复对应承诺（重摘 quote、改正数字、补著录字段、补契约键），**然后重跑步骤 3**（产物变了哈希必须重算），直至退出码 0；
- verify_report.md 留在 /app/output 供评审直接查看。

**步骤 5 — 交付声明**
在 result.json 的 `limits` 写明 manifest 的覆盖范围：哪些承诺可机器复核（quotes/numbers/refs/hash/contract），哪些只能人工复核（证据完整性、语义支持关系）。打包后若再改 /app/output 任何文件，必须重跑步骤 3–4。

## 异常处理

- 来源文本提取失败：对应 quote/number 承诺不得登记，相关表述不进成稿，limits 说明；
- 复核方环境缺文件：verify_pack 对缺失项报 FAIL 而非跳过——交付方应保证 /app/output 自包含；
- manifest 与 result.json 的 case_id 不一致：CONTRACT 检查 FAIL，说明打包后改了 result.json，重跑步骤 3。

## 最小调用示例（合成示例，非正式案例结果）

`examples/input/` 含一个迷你可交付包（result.json、deliverable.md、evidence_pack.json）与 2 份合成来源文本。执行：
```bash
python3 scripts/pack_manifest.py --output-dir examples/input/pack \
  --manifest examples/input/pack/verification_manifest.json \
  --evidence examples/input/evidence_pack.json
python3 scripts/verify_pack.py --output-dir examples/input/pack \
  --sources examples/input/text \
  --manifest examples/input/pack/verification_manifest.json \
  --report /tmp/verify_report.md
```
全部承诺通过（退出码 0）。示例还演示了篡改检测：打包后改动 deliverable.md 再重验，HASH 检查 FAIL。真实输出见 `examples/minimal_example.md` 与 `examples/output/`。

## 限制与维护

- 复核覆盖"登记过的承诺为真"，不覆盖"承诺登记完整"与"语义支持正确"（协议第 5 节，须如实声明）；
- 规范化规则集中在 `verify_pack.py` 的 normalize()；检查类别集中在其 main()；协议变更同步 `references/replay_protocol.md`。
