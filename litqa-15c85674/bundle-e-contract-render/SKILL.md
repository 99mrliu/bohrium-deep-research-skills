---
name: litqa-contract-render
description: 文献智能问答的"下游渲染工程"路线。当任务给出 /input/case.json（带段落编号的论文案例包与中文问题清单，常附 output_contract）并要求把结构化结果写入 /app/output/result.json 时使用。本 Skill 的重心在交付物工程：init 从 output_contract 机械提取交付所需的全部顶层字段并立即写含全部字段的占位骨架；模型只填"答题纸"（简单的 STATUS/ANSWER/CLAIM/UNANSWERED 行格式），从不手写 result.json；refresh 在每次改完答题纸后幂等重渲染，部分结果始终落盘；finalize 做严格终检（契约字段一个不缺、无占位残留、引文逐字、状态合法）后原子双写 result.json 与 answers.json，流水线不产出的契约字段由 extra_fields.json 显式并入。适用于交付契约严格、需过程可断点续作的文献问答。
---

# 契约渲染工程（litqa-contract-render）

版本：1.0.0　运行环境：Python 3.10+（仅标准库）、shell。零外部依赖。

**方法重心**：这一类任务的交付物是机器消费的结构化 JSON，但最常见的失败是
工程性的：契约字段漏一个、引文错一词、最后一刻手写 JSON 出 schema 错、
中途超时导致零产出。本 Skill 把"答案内容"与"交付物结构"彻底分离——
**模型只写答题纸（行格式文本），渲染器机械拼装 result.json**；
契约字段从 `output_contract` 实时提取，不凭记忆硬编码；
骨架从 init 起就含全部契约字段，任何时刻被叫停都有一份结构完整的部分结果。

## 1. 运行契约

- 输入：`/input/case.json`（含可选 `output_contract`）；工作目录 `/app/work/`；
  输出 `/app/output/result.json` 与 `/app/answers.json`（`--legacy`，同内容双写）。
- 基线字段：`case_id`、`paper_id`、`material_version`、`status`、`answers[]`
  （`question_id`、`answer`、`conditions[]`、`status`
  ∈ `answered|partial|insufficient_evidence|input_error`、`claims[]`
  （`claim_id`、`text`、`kind` ∈ `reported|inferred`、`evidence[]`
  （`paragraph_id` + 逐字 `quote`））、`unanswered_parts[]`）、`coverage`。
- 契约字段 = 基线 ∪ `output_contract` 声明的全部顶层字段；流水线不产出的字段
  （如 `sources`、`uncertainty`、`change_log`）必须经 `--extra` 提供，
  否则 finalize 失败（refresh 时降级为 WARN + 占位值）。
- **诚实 partial**：骨架自始落盘；占位值是字面量 `<待填>`，finalize 不允许残留；
  中断时的部分结果如实反映已完成题目。

## 2. 流程（每案例约 4–6 次工具调用）

```bash
mkdir -p /app/work /app/output
SRC=$(find /skills -maxdepth 3 -name render_contract.py -path '*/scripts/*' 2>/dev/null | head -1)
[ -z "$SRC" ] && SRC=$(find /app /opt -maxdepth 5 -name render_contract.py -path '*/scripts/*' 2>/dev/null | head -1)
cp -r "$(dirname "$SRC")" /app/work/scripts && ls /app/work/scripts

# 步骤 1：初始化（退出码 2 = 输入损坏，input_error 骨架已写，结束）
python3 /app/work/scripts/render_contract.py init --case /input/case.json --work /app/work --out /app/output
# 读 /app/work/contract.json：本次交付到底要哪些顶层字段。

# 步骤 2：通读 /input/case.json 全部段落，逐题填 /app/work/sheets/Q*.md
# （格式：STATUS:/ANSWER:/CONDITIONS:/CLAIM:/UNANSWERED: 行；答题规则与
#  证据纪律见 references/answering-sheet.md）。

# 步骤 3：每改完一题就 refresh——部分结果始终落盘
python3 /app/work/scripts/render_contract.py refresh --work /app/work \
    --out /app/output --legacy /app/answers.json

# 步骤 4：流水线不产出的契约字段写 /app/work/extra_fields.json，然后终检交付
python3 /app/work/scripts/render_contract.py finalize --work /app/work \
    --out /app/output --legacy /app/answers.json --extra /app/work/extra_fields.json
# finalize 失败：产物不覆盖（保留上次 refresh 的诚实部分结果），按 ERROR 修复重跑。
```

## 3. 渲染语义

- `claim_id` 由渲染器机械分配（`Q<n>-C<j>`）；`coverage` 默认如实为空，
  需要时把留痕内容并入 `extra_fields.json` 的契约字段中（或在答题纸中说明）。
- `status`（顶层）：所有问题 ∈ {answered, insufficient_evidence} → `completed`，
  否则 `partial`——由渲染器推导，不可在答题纸中 override。
- `extra_fields.json` 中契约未声明的键**不并入**（防止与内部字段串味），并给出 WARN。
- 所有写盘为临时文件 + 原子替换；finalize 失败时不触碰既有产物。

## 4. 已知限制

- 渲染器不做论断质量审核（引文逐字之外的语义判断在模型）；需要审核闭环时
  与对抗审核类方法互补使用。
- 答题纸行格式严格：CLAIM 行格式错误的条目会被静默丢弃——refresh 后
  目测一次各题 claims 数量。
- `output_contract` 缺省时退化为基线字段集。

## 5. 资源清单

| 路径 | 作用 |
|-|-|
| `scripts/render_contract.py` | init / refresh / finalize 三子命令 |
| `references/answering-sheet.md` | 答题纸行格式规范与填写示例 |
| `examples/synthetic-case.json` | 合成示例输入（虚构论文，含 9 字段 output_contract） |
| `examples/run-record.md` | 合成示例的端到端真实运行记录（含故障注入） |
| `examples/result.synthetic.json` | finalize 的真实输出（契约 9 字段齐全） |
| `GITHUB_URL.txt` | 本作品的 GitHub 公开链接 |
