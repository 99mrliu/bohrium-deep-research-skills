---
name: facet-gap-atlas
description: 结构化比较数据建模取向的科研选题评估技能。当任务是在 /input 给定 case.json（含 case_id 与 output_contract）、task.md 与一批文献材料，要求围绕固定研究问题完成已有工作比较、研究空白识别、选题或创新性评估并在 /app/output 交付结构化 result.json 时使用。核心立场：比较不是写作文而是建数据——把每篇纳入文献规范化成带类型的记录（task/method_family/data_domain/metrics/…），scripts/atlas.py 先机检记录完整性，再确定性计算切面覆盖矩阵（哪些 任务×方法 格子是输入文献集内空白）、指标覆盖缺口（谁缺报同类常用指标）和不可比对记录对（指标集不相交、附原因）；研究空白由查询算出而非由文笔断言，"未见"永远携带文献集边界。不适用：文献量 <3 篇或材料为单一记录型数据的场景。
---

# facet-gap-atlas：研究空白是算出来的，不是宣布出来的

## 核心主张

基础 Agent 做"已有工作比较"时写的是印象派散文：维度随手换、对象随手挑、"研究较少"随口说。本技能把比较变成数据建模：每篇文献一行类型化记录，维度事先定义、枚举受控、缺字段过不了机检；空白、缺口、不可比对关系全部从记录表**查询计算**得出——换个边界重跑一遍，结论如实跟着变。评审看到的不是"作者认为"，而是一张可以逐格复核的图谱。

## 运行时契约（必须先读）

1. 输入在 `/input`：`task.md`、`case.json`（含 `case_id`、`output_contract`）、材料文件（PDF/TXT/JSON/CSV）。逐文件读真实内容，不依据文件名或标签猜测；PDF 用运行环境实际可用的解析工具从原始 PDF 提取，不假设有预提取文本层。
2. 若存在 `/input/environment/resources.yaml`，先读它确认可用工具。
3. 中间产物写入 `/app/work`，最终交付写入 `/app/output`。
4. `/app/output/result.json` 必须含 `case_id`（与 case.json 逐字一致）与 `output_contract` 声明的**全部原始字段**，字段名逐字照抄。
5. 预算：约 64 次模型请求、900 秒、单次响应 16384 token。第一时间写 result.json 骨架（契约字段置 null、status=in_progress），逐阶段回填。
6. 诚实状态：`status` 只能是 `success` / `partial` / `failed`；partial 写明缺什么、为什么。
7. 禁止伪造：记录字段只能从材料中提取，填不出就标 `unreported`；不依据错误的领域标签补造数据。

## 工作流程

### 阶段 1：打底

清点输入 → 研究问题结构化（对象/变量/基线/预期方向/可证伪条件）→ 纳排留痕 → 覆盖边界声明落盘。

### 阶段 2：类型化记录提取（本技能核心）

1. 按 `references/schema.md` 为每篇纳入文献写一行记录：`task`（它解决什么任务）、`method_family`（方法族，用受控词表）、`data_domain`（数据/体系）、`metrics`（报告了哪些指标）、`headline_result`（一句话主结果）、`limitations`、`comparability_class`（和谁可比）。词表先根据材料起草本写入 `/app/work/vocabulary.md`，同一概念只许用一个词。
2. 提取不出的字段填 `unreported`——**`unreported` 本身是重要信号**（该文献不可按此维度比较）。
3. 写入 `/app/work/records.jsonl`，机检：

   ```
   python3 /skills/weekly-skill/scripts/atlas.py validate --records /app/work/records.jsonl
   ```

   违例（缺字段、枚举越界、年份非法）逐条修复；重复键警告人工核对。

### 阶段 3：可计算空白分析

```
python3 /skills/weekly-skill/scripts/atlas.py gap \
    --records /app/work/records.jsonl \
    --facets task,method_family --out /app/work/atlas
```

读 `atlas_report.md`：**空白格**（候选研究空白，标注"输入文献集内未见"）、**指标覆盖缺口**（谁缺报同类常用指标）、**不可比对记录对**（附原因）。方法学口径见 `references/gap_method.md`。切面可按研究问题换（如 `task,data_domain`），换切面重跑即可。

### 阶段 4：综合与交付

1. 已有工作比较：按 comparability_class 分组叙述，直接引用覆盖矩阵；不可比对记录对按报告中的原因说明。
2. 研究空白/创新点：只许引用 atlas 算出的空白格与缺口，每条携带边界声明（"在输入文献集 N 篇内，任务×方法 的 X×Y 格为空"）；提案的创新点对号入座到格子，判定其是否落在已填充格。
3. 可行性前提逐条标 `[来源:记录ID]` 或 `[假设]`；不确定性与冲突证据照常登记。
4. 回填 result.json；把 records.jsonl、atlas_report.json/md、vocabulary.md 复制到 `/app/output` 作可复核附件。

## 异常处理

| 情形 | 处置 |
|-|-|
| 文献 <3 篇 | 图谱价值有限：照常出矩阵，在不确定性中声明"样本过少，空白结论仅供参考" |
| 某维度大面积 unreported | 换用信息量更高的切面重跑 gap；并在不确定性中登记该维度不可比较 |
| validate 违例修不好 | 该记录标 `excluded` 并写明原因，不进入矩阵；综述中说明排除 |
| 词表摇摆（同义不同词） | 回 vocabulary.md 统一后批量改正重跑；不许让同义词制造假空白格 |
| 预算危急 | 矩阵与 gap 报告是确定性脚本、秒级完成；优先保证记录表填完，综合可从简（partial） |

## 红线

- 不许写"该方向研究较少"却不指向具体空白格；不许用同义词制造或消灭空白；不许让 unreported 字段静默消失；空白结论离开边界声明不许出现。

## 最小示例

`examples/` 内有**合成示例**：6 篇虚构文献记录覆盖 2 任务 × 3 方法族（故意留 2 个空格、1 处指标缺口、1 对不可比对记录），另附一份埋了 3 处违例的坏记录文件。命令与预期输出见 `examples/minimal_example.md`，实跑产物在 `examples/output/`。
