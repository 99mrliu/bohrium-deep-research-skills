---
name: novelty-boundary-matrix
description: 创新边界判定取向的科研选题评估技能。当任务是在 /input 给定 case.json（含 case_id 与 output_contract）、task.md 与文献材料及待评提案，要求判断创新点是否成立、与已有工作划清边界，并在 /app/output 交付结构化 result.json 时使用。核心立场：创新性不是修辞而是对账——每条创新陈述先分类（方法/数据/场景迁移/结论修正），再与已有工作逐一做 covers/partial/none 对账，novelty_matrix.py 强制判定规则：covers 必须附证据锚点，uncovered 必须以已声明的检索边界为前提，缺边界则只能判 indeterminate；产出覆盖矩阵与划界备忘录。不适用：无明确创新陈述或无可对账文献的场景。
---

# novelty-boundary-matrix：创新性是对账，不是修辞

## 核心主张

选题评估里"创新"二字最容易被滥用：把场景迁移说成方法创新，把旧方法新用途说成理论突破，把"我没检索到"说成"国际首创"。本技能把创新判定变成可机检的对账：**每条创新陈述必须逐一对已有工作表态（covers/partial/none），判定由规则生成而非由文笔生成**。"未见覆盖"永远是带边界的判断，边界一换就要重新对账。

## 运行时契约

1. 输入在 `/input`：`task.md`、`case.json`（`case_id`、`output_contract`）、文献材料与待评提案。逐文件读真实内容；PDF 用实际可用工具从原始文件解析。
2. 若存在 `/input/environment/resources.yaml`，先读确认可用工具。
3. 中间产物入 `/app/work`，最终交付入 `/app/output`；`result.json` 含 `case_id`（逐字一致）与 `output_contract` 全部原始字段。
4. 预算：约 64 次模型请求、900 秒、16384 token/响应。第一阶段写 result.json 骨架（契约字段=null、status=in_progress），逐阶段回填。
5. 诚实状态：`status` ∈ {success, partial, failed}；材料不足判 indeterminate 是正常产出，不是失败。
6. 禁止伪造：不臆造对账结论，"检索不到"与"尚无人研究"严格区分。

## 工作流程

### 阶段 0：契约骨架与材料登记

登记 `/input` 文件到 `/app/work/inventory.md`；摘 case_id 与 output_contract；写 result.json 骨架。

### 阶段 1：创新陈述抽取与分类

从提案中逐条抽出创新陈述写入 `/app/work/claims.json`（格式见 `references/claim_format.md`），每条分类：

| 类型 | 含义 | 典型误判 |
|---|---|---|
| method | 方法/机制层面新 | 把已有方法的小调参说成方法创新 |
| data | 新数据/新标注/新基准 | 把别人数据的重用说成数据创新 |
| scenario | 已有方法迁移到新场景 | 把迁移说成方法创新（最常见） |
| conclusion | 修正/否定已有结论 | 把复述说成修正 |

`search_boundary` 字段必填：本判断覆盖哪些来源（输入文献集/检索式）、什么时间窗。

### 阶段 2：已有工作归一化

从文献材料归纳可比较工作清单 `/app/work/works.md`：每个工作给 ID（W1, W2…）、任务/方法/数据/指标一句话。不可比的工作也列出并写不可比原因——它们是"对账过但关系为 none 且有据"还是"无法对账"的分界线。

### 阶段 3：逐格对账

对每对（claim × work）在 `/app/work/judgments.jsonl` 写一条 judgment：`covers`（该工作已实现该陈述的实质）/ `partial`（覆盖一部分）/ `none`（无关或未覆盖）。`covers` 与 `partial` **必须**附 `evidence_anchor`（来源文件#页码或小节）；`none` 尽量写 note。规则细节见 `references/boundary_rules.md`。

### 阶段 4：机检判定与备忘录（本技能核心）

```
python3 /skills/weekly-skill/scripts/novelty_matrix.py \
    --claims /app/work/claims.json \
    --judgments /app/work/judgments.jsonl \
    --out /app/work/novelty
```

产出 `novelty_matrix.md`（覆盖矩阵）、`verdicts.json`（逐条判定）、`boundary_memo.md`（划界备忘录）。有违例（缺锚点、引用不存在的 ID、类型非法）必须修复重跑，不允许带违例交付。

### 阶段 5：回填与收口

判定按契约字段回填 result.json；矩阵、备忘录、judgments.jsonl 复制到 `/app/output`。每条 uncovered 在 result.json 中都带边界声明；每条 covered/partial 都能报出锚点。

## 异常处理

| 情形 | 处置 |
|-|-|
| 提案没有显式创新陈述 | 从任务文本归纳候选陈述并标注"由评估方归纳，非提案原文"；不替提案发明创新点 |
| 可对账文献为 0 | 全部判 indeterminate，status=partial，写明无法对账的原因 |
| 关键文献不可解析 | 相关对账格标"无法对账"并在备忘录登记，不猜关系 |
| 提案陈述互相重叠 | 保留原样逐条对账，在备忘录指出重叠，不擅自合并 |
| 预算将尽 | 立即回填已判定条目，未判条目记 indeterminate，status=partial |

## 红线

- 不许无锚点判 covered/partial；不许无边界声明判 uncovered；不许把 scenario 包装成 method；不许只报"未见覆盖"不报"已被覆盖"的部分（反之亦然）；不许把边界内判断说成全局首创。

## 最小示例

`examples/` 内有**合成示例**：虚构提案（4 条创新陈述）×3 篇虚构已有工作，含一处故意缺锚点的违例，演示机检拦下与修复，见 `examples/minimal_example.md`。
