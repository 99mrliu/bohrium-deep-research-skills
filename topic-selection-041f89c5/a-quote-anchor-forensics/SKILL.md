---
name: quote-anchor-forensics
description: 上游数据真实性取向的科研选题证据取证技能。当任务是在 /input 给定 case.json（含 case_id 与 output_contract）、task.md 与一批科研材料（文献记录、论文文本或 PDF、提案文本），要求围绕固定研究问题完成文献整理、证据提取、选题或创新性评估，并在 /app/output 交付结构化 result.json 时使用。核心立场：证据进入综述之前先过取证关——每条可用证据必须带逐字引文锚点，由 scripts/anchor_audit.py 机检引文真实存在于所指来源（NFKC+空白折叠归一化后子串匹配、SHA-256 来源登记、元数据抽查），核验不过的证据一律不得进入证据矩阵与结论。不适用：无来源材料的纯观点咨询、任务明确允许二手转述的场景。
---

# quote-anchor-forensics：先取证，后综述

## 核心主张

选题评估最致命的失真不是漏文献，而是**证据本身是假的或记错的**：引文并非原文、张冠李戴、凭印象复述结论。基础 Agent 的典型失败是输出一段流畅综述，其中每个"事实"都无法回到原文。本技能把证据准入改成取证流程：**任何陈述只有挂上通过机检的逐字引文锚点，才有资格进入证据矩阵**；核验失败的材料要么修复锚点，要么降级为"不可用作证据"并如实登记。宁可结论变薄，不让假证据混入。

## 运行时契约（必须先读）

1. 输入在 `/input`：`task.md`（任务说明）、`case.json`（含 `case_id`、`output_contract`，可能还有文献清单与提案）、材料文件（PDF/TXT/JSON/CSV）。**逐文件读真实内容**，不依据文件名或标签猜测；PDF 用运行环境实际可用的解析工具从原始 PDF 提取，不假设有预提取文本层。
2. 若存在 `/input/environment/resources.yaml`，先读它确认可用工具。
3. 一切中间产物写入 `/app/work`，最终交付写入 `/app/output`。
4. `/app/output/result.json` 必须包含 `case_id`（与 case.json 逐字一致）与 `output_contract` 声明的**全部原始字段**，字段名逐字照抄，不增删改名。
5. 预算：约 64 次模型请求、900 秒、单次响应 16384 token。**第一阶段就写出 result.json 骨架**（契约字段先置 null、`status:"in_progress"`），每完成一个阶段回填一次，保证任何时刻中断都有合法半成品。
6. 诚实状态：`status` 只能是 `success` / `partial` / `failed`，与事实相符；材料缺失、无法判定、运行失败分别说明；partial 必须写明缺什么、为什么。
7. 禁止伪造：文献不存在就写不存在，引文核验不过就不得引用，不依据错误的领域标签补造数据。

## 工作流程（六阶段，每阶段结束回填一次 result.json）

### 阶段 0：取证登记与契约骨架

1. `ls -laR /input`，全部文件登记到 `/app/work/inventory.md`（文件名、字节数、格式、可解析性初判）。
2. 读 `case.json` 摘出 `case_id` 与 `output_contract` 全部字段；读 `task.md` 逐句标出交付要求。
3. 写 `/app/output/result.json` 骨架（契约字段=null，`status:"in_progress"`）。
4. 把可用作文献证据的文本材料汇集到 `/app/work/sources/`（PDF 提取为 txt 后放入，保留原始文件名映射），运行：

   ```
   python3 /skills/weekly-skill/scripts/anchor_audit.py \
       --sources /app/work/sources --ledger /dev/stdin --out /app/work/registry < /dev/null
   ```

   只为先生成 `source_registry.json`（来源 SHA-256 登记册）；台账为空属正常。

### 阶段 1：研究问题结构化

按 `references/evidence_ledger_format.md` 第 1 节，把研究问题拆成：研究对象、关键变量、比较基线、预期结论方向、可证伪条件，写入 `/app/work/question_frame.md`。任务文本缺的要素标 `未指定`，不脑补。

### 阶段 2：检索与筛选留痕

- 证据第一来源 = `/input` 文献集；若运行环境确有联网检索通道且 task.md 允许，登记完整检索式与时间窗；否则在结论中写明"覆盖边界 = 输入文献集"，**严禁写成"该领域尚无人研究"**。
- 每条候选记录判定 纳入/排除/待定，排除写明理由，记入 `/app/work/screening_log.md`。

### 阶段 3：证据台账与锚点机检（本技能核心）

1. 对每篇纳入文献，把综述要用到的每条证据写成台账记录（格式见 `references/evidence_ledger_format.md`）：`claim`（你打算在综述里说的话）、`source_file`、`quote`（**从来源文件复制粘贴的逐字片段**，不得凭记忆改写）、`locator`（页码/小节）、可选 `check_fields`（标题、年份等元数据抽查）。
2. 写入 `/app/work/evidence_ledger.jsonl`，运行：

   ```
   python3 /skills/weekly-skill/scripts/anchor_audit.py \
       --sources /app/work/sources \
       --ledger /app/work/evidence_ledger.jsonl \
       --out /app/work/audit
   ```

3. 读 `audit_report.json`：**FAIL/ERROR 的记录必须处理**——quote 找不到就回原文重新复制（常见原因：转述冒充引文、跨段拼接、记错出处）；修复后重跑，直至全部 PASS 或把该记录标记为不可用并从证据矩阵剔除。判定规则细节见 `references/verification_policy.md`。

### 阶段 4：综合结论（只引用通过核验的证据）

在 `/app/work/synthesis.md` 完成四项交付，每条结论引用台账记录 ID（只有 PASS 记录可被引用）：

1. 已有工作比较：谁做到哪一步、真正相近的工作、不可比的工作及原因；
2. 创新点识别：对提案每条创新陈述判 `已被覆盖/部分覆盖/未见覆盖/无法判定`，附台账 ID；"未见覆盖"必须同句写明检索范围边界；
3. 可行性判断：数据、算力/实验条件、时间窗、方法成熟度四类前提，每条标 `[来源:台账ID]` 或 `[假设]`；
4. 研究空白与不确定性：冲突证据双方均列出并说明取舍。

### 阶段 5：收口

1. 结论按契约逐字段回填 `result.json`；把 `source_registry.json`、`audit_report.json/md`、证据台账复制到 `/app/output` 作为可复核附件。
2. 终检：result.json 中任何文献相关陈述都能说出它来自哪条 PASS 记录；说不出来就删除该陈述或降级 `partial`。

## 异常处理

| 情形 | 处置 |
|-|-|
| 台账记录 FAIL 且修不好 | 该证据标记 `unusable` 并登记原因，综述中删除对应陈述；不允许"大概是这样"放行 |
| 来源文件不可解析（乱码/扫描件） | 换工具重试一次；仍失败则该来源登记 `unreadable`，相关结论降级并在不确定性中说明 |
| 文献集为空或全部排除 | `status:"partial"`；交付问题结构化、空台账、空核验报告与明确说明，协议可复跑 |
| 证据互相冲突 | 双方锚点均入台账；综合段写明冲突点与取舍理由，不允许只留支持性证据 |
| 预算将尽 | 立即把当前最好结果回填 result.json（`partial`），先保契约字段齐全 |

## 红线

- 不许引用未通过 `anchor_audit.py` 核验的证据；不许凭记忆"重建"引文；不许把转述写成引文；不许只登记支持性证据；不许把"输入文献集内未见"写成"国内外尚无研究"。

## 最小示例

`examples/` 内有**合成示例**（3 个虚构来源文本 + 5 条台账记录，其中故意埋了 2 条问题记录），运行方式与预期输出见 `examples/minimal_example.md`。
