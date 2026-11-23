---
name: litqa-input-fidelity
description: 文献智能问答的"上游数据真实性"路线。当任务给出 /input/case.json（带段落编号的论文案例包与中文问题清单）并要求把结构化结果写入 /app/output/result.json 时使用。本 Skill 的重心不在答题技巧，而在输入侧：对案例包做宽容解析与逐段完整性审计（重复编号、空文本、编码损伤、疑似截断），为每段计算 SHA-256 版本坐标并归类（摘要/正文/表格/图注/参考文献），用"读取留痕"机械推导诚实的 coverage 字段，最后对拟交付结果做引文逐字机器校验。输入损坏时立即写 input_error 骨架，绝不编造。适用于一切以给定材料为准的文献问答、证据溯源与阅读核对任务。
---

# 上游数据真实性（litqa-input-fidelity）

版本：1.0.0　运行环境：Python 3.10+（仅标准库）、shell。零外部依赖。

**方法重心**：同类 Skill 把力气花在"怎么答"，本 Skill 先把"材料本身是否可信、
是否被如实读取"钉死。其主张是：答案质量的上限由输入侧决定——段落清单里若有重复编号、
空段、编码损伤或截断，下游再努力也会产出幻觉引文；coverage 若由模型自述，
必然与真实读取行为脱节。因此本 Skill 用确定性脚本完成四件事：
**宽容解析 → 完整性审计 → 读取留痕 → 引文逐字校验**，模型的全部预算只花在读与答上。

## 1. 运行契约

- 输入：`/input/case.json`（案例包：案例/论文标识、材料版本、段落清单、任务说明、问题清单，
  可能附带 `output_contract`）。平台把本 Skill 装入 `/skills/literature-qa`（或
  `/skills/weekly-skill`），引导时先定位脚本再复制到 `/app/work/scripts`（见第 3 节）。
- 工作目录：`/app/work/`（中间产物）；输出目录：`/app/output/`。
- 主输出：`/app/output/result.json`，**同时**写一份内容相同的 `/app/answers.json`
  （旧契约兼容）。两个文件都必须真实落盘。
- `result.json` 必须包含：`case_id`、`paper_id`、`material_version`（与输入一致）、
  `answers[]`（覆盖全部 `question_id`，每项含 `answer`、`conditions[]`、
  `status`（`answered|partial|insufficient_evidence|input_error`）、
  `claims[]`（每项 `claim_id`、`text`、`kind`（`reported|inferred`）、
  `evidence[]`（每条 `paragraph_id` + 逐字 `quote`））、`unanswered_parts[]`）、
  `coverage`（`read_sections`、`unread_sections[]` 含原因）。
  若 case.json 给出 `output_contract` 的额外顶层字段，逐一照抄进 result.json。
- **诚实 partial**：任何阶段失败都必须留有一份如实反映当前状态的 result.json，
  未作答的问题如实标注，绝不留空文件、绝不编造。

## 2. 流水线（每案例约 6–9 次工具调用）

```bash
mkdir -p /app/work /app/output
# 引导：定位脚本（平台安装路径可能不同，找到后复制到工作目录）
SRC=$(find /skills -maxdepth 3 -name source_ledger.py -path '*/scripts/*' 2>/dev/null | head -1)
[ -z "$SRC" ] && SRC=$(find /app /opt -maxdepth 5 -name source_ledger.py -path '*/scripts/*' 2>/dev/null | head -1)
cp -r "$(dirname "$SRC")" /app/work/scripts && ls /app/work/scripts

# 步骤 1：解析 + 完整性审计 + 骨架落盘（退出码 2 = 输入损坏，骨架已写 input_error，结束）
python3 /app/work/scripts/source_ledger.py audit \
    --case /input/case.json --work /app/work --out /app/output

# 步骤 2：读材料清单与归一化文本
#   先看 /app/work/inventory.md：哪些段被标记了 duplicate_id / empty /
#   encoding_damage / possible_truncation；有标记的段落作答时必须在
#   unanswered_parts 或 conditions 中如实说明该段不可信。
#   再读 /app/work/case_norm.json 全部段落（含表格、图注、参考文献）。

# 步骤 3：作答期间随手留痕（幂等，可多次调用）
python3 /app/work/scripts/source_ledger.py mark --work /app/work --read "P1,P2,P3,P5"

# 步骤 4：写答案（模型手写 result.json 草稿，规则见 references/answering-rules.md），
#   用留痕机械生成 coverage 并合入草稿
python3 /app/work/scripts/source_ledger.py coverage --work /app/work \
    --reason "经问题相关性判断后未读取"
#   把 /app/work/coverage.json 的内容原样并入 result.json 的 coverage 字段。

# 步骤 5：机器校验，ERROR 必须修到归零
python3 /app/work/scripts/source_ledger.py check \
    --case-norm /app/work/case_norm.json --result /app/output/result.json
#   通过后将同一内容复制到 /app/answers.json。
```

## 3. 上游审计决定下游处置（本 Skill 的核心规则）

| 审计标记 | 含义 | 作答时的硬性处置 |
|-|-|-|
| `duplicate_id` | 段落编号重复，引文坐标歧义 | 引用该编号时在 claim 中注明歧义并给 SHA-8 消歧 |
| `empty` | 段落无文本 | 不得引用；列入 `coverage.unread_sections`，原因写"原文为空" |
| `encoding_damage` | 含控制字符/替换符 | 不得截取含损伤字符的引文；在 `unanswered_parts` 说明 |
| `possible_truncation` | 段尾无终止标点，疑似截断 | 涉该段数值的结论降为 `partial`，说明"段尾疑似不完整" |

- `coverage` 一律由 `coverage` 子命令从留痕生成，**禁止模型自述**——
  平台会结合运行记录核验，自述与行为不符即失分。
- 未读取的段落必须出现在 `unread_sections` 并给真实原因；全部读取则为空列表。
- "材料未报告 X"是有效回答：先把清单中全部段落读过（全部留痕），
  再写 `status=insufficient_evidence`，`answer` 说明"已核对全部 N 段，材料未报告 X"。

## 4. 异常处理

- 案例包缺失/非 UTF-8/非法 JSON/缺字段：`audit` 退出码 2，已自动写
  `input_error` 骨架到 `--out`。确认文件存在后如实结束，**不得**凭记忆补写内容。
- `check` 报 ERROR：逐条修复（引文不在原段就换引文或改论断），直到 0 ERROR；
  预算不足时保留已通过的题目，其余如实标 `partial` 并写原因。
- 段落编号体系不是 P\d+：脚本不假设编号格式，原样保留；作答与引文沿用原编号。

## 5. 已知限制

- 完整性审计是启发式：能发现结构性损伤，不能判断"内容是否被篡改"。
- 归类启发式仅用于材料清单展示，不影响作答正确性。
- 不解析 PDF、不做图像识别、不联网检索——输入只有 case.json 给定的文本。

## 6. 资源清单

| 路径 | 作用 |
|-|-|
| `scripts/source_ledger.py` | audit / mark / coverage / check 四子命令，全部逻辑所在 |
| `references/input-fidelity.md` | 方法论证、字段变体表、审计标记语义详解 |
| `references/answering-rules.md` | 作答与证据规则（论断、条件、不确定性、冲突） |
| `examples/synthetic-case.json` | 合成示例输入（虚构论文，非正式案例） |
| `examples/run-record.md` | 上述示例的本地端到端真实运行记录（标注为合成示例） |
| `GITHUB_URL.txt` | 本作品的 GitHub 公开链接 |
