---
name: conflict-tribunal
description: 冲突证据对抗裁决取向的科研选题评估技能。当任务是在 /input 给定 case.json（含 case_id 与 output_contract）、task.md 与科研材料，要求围绕固定研究问题完成文献综述、证据综合、选题或创新性评估并在 /app/output 交付结构化 result.json，且材料中可能存在互相矛盾的证据时使用。核心立场：只报告支持性证据的综述是宣传不是评估——每个关键断言组必须强制做一次对抗检索（找反证），支持/反证连同质量评级登记进卷宗，scripts/docket.py 机检"无对抗检索记录即违例"，并按显式准则优先级（直接性 > 证据类型 > 方法严谨度 > 时效）机械裁决；裁不动的冲突双方并列保留并标注未决。不适用：单一来源的转述任务、材料内部无结论性断言的场景。
---

# conflict-tribunal：没找过反证的结论，不许定稿

## 核心主张

基础 Agent 的综述有个系统性偏向：**顺着提案写**——检索为结论服务，冲突证据被静默丢弃，"已有研究均表明"成为口头禅。本技能把冲突处理变成对抗程序：每个关键断言必须配一份"我认真找过反证"的登记，找到的反证与支持证据同卷评级，裁决由显式准则机械作出而非由文笔作出。裁决可以输，程序不能缺。

## 运行时契约（必须先读）

1. 输入在 `/input`：`task.md`、`case.json`（含 `case_id`、`output_contract`）、材料文件（PDF/TXT/JSON/CSV）。逐文件读真实内容，不依据文件名或标签猜测；PDF 用运行环境实际可用的解析工具从原始 PDF 提取，不假设有预提取文本层。
2. 若存在 `/input/environment/resources.yaml`，先读它确认可用工具。
3. 中间产物写入 `/app/work`，最终交付写入 `/app/output`。
4. `/app/output/result.json` 必须含 `case_id`（与 case.json 逐字一致）与 `output_contract` 声明的**全部原始字段**，字段名逐字照抄。
5. 预算：约 64 次模型请求、900 秒、单次响应 16384 token。第一时间写 result.json 骨架（契约字段置 null、status=in_progress），逐阶段回填。
6. 诚实状态：`status` 只能是 `success` / `partial` / `failed`；partial 写明缺什么、为什么。
7. 禁止伪造：检索不到反证就登记"未找到"（附检索范围）；不许删掉找到的反证。

## 工作流程

### 阶段 1：常规打底

清点输入 → 研究问题结构化（对象/变量/基线/预期方向/可证伪条件）→ 纳排留痕 → 覆盖边界声明 → 证据表（每条带 文件+定位）。这一阶段与常规综述一致，产物在 `/app/work`。

### 阶段 2：断言分组与卷宗登记（本技能核心）

1. 从证据表挑出 **3–6 个承载结论的关键断言**，每个建一个断言组（G1、G2…）。
2. 对每个组登记支持证据（evidence 记录，含 quality 四元评级：directness / evidence_kind / method_rigor / year——评级标准见 `references/adjudication_rules.md`）。
3. **对每个组做一次专门的对抗检索**：回头翻整个输入材料集，专门寻找与该断言相反、限制其适用范围或与其数字冲突的证据。无论找没找到，都必须登记一条 counter_search 记录（scope 写清找了哪里；found=false 时 note ≥8 字符说明检索方式）。找到的反证登记为 counter 证据，同样评级。
4. 写入 `/app/work/docket.jsonl`，机检：

   ```
   python3 /skills/weekly-skill/scripts/docket.py lint --docket /app/work/docket.jsonl
   ```

   违例（缺对抗检索、字段不全、found=true 却无反证登记）必须修复后重跑。

### 阶段 3：机械裁决

```
python3 /skills/weekly-skill/scripts/docket.py adjudicate \
    --docket /app/work/docket.jsonl --out /app/work/tribunal
```

读 `tribunal_report.md` 与 `contradiction_register.md`：每组的裁决（support/counter/unresolved/unchallenged）、决定准则与取舍理由。裁决规则的细节与置信度口径见 `references/adjudication_rules.md`。

### 阶段 4：带裁决状态的综合

四项交付起草时的强制规则：

1. 引用任何断言组的结论，**必须同句标注其裁决状态**："（对抗裁决：support，决定准则=直接性）"、"（未决冲突，双方并列）"、"（未经对抗检验）"。
2. unresolved 组：双方结论并列写，不许二选一；在不确定性中显式登记。
3. 创新点与可行性判断若依赖某个被 counter 裁决推翻的断言，必须重新评估并说明。
4. 回填 result.json；把 docket.jsonl、tribunal_report.json/md、contradiction_register.md 复制到 `/app/output` 作可复核附件。

## 异常处理

| 情形 | 处置 |
|-|-|
| 材料中确实无反证 | counter_search found=false + 检索方式说明；组判 unchallenged，综述标注"未经对抗检验"，不许写成"已被证实" |
| 全部组都 unresolved | 合法结果；结论按未决冲突双方并列交付，不确定性充分展开 |
| lint 违例 | 逐条修复（补对抗检索记录/补字段）；不许绕过 lint 直接裁决 |
| 证据质量无法评级 | 按最低档评级并在 note 说明"评级信息不足，从低档" |
| 预算危急 | 优先保承载结论的 3 个组完成全流程，其余组在不确定性中登记"未做对抗检索" |

## 红线

- 不许只登记支持性证据；不许先定结论再补评级；不许把 unchallenged 写成 confirmed；不许在 unresolved 组上单边陈述；评级信息不足时从低档，不得从高档。

## 最小示例

`examples/` 内有**合成示例**：3 篇虚构文献构成一个真实冲突（两篇直接实验结论相反、一篇间接支持）+ 一个无反证断言；`docket_good.jsonl` 通过 lint 并被裁决（G1 按方法严谨度判 support、G2 unchallenged）；`docket_bad.jsonl` 故意缺对抗检索记录，被 lint 拒绝。命令与预期输出见 `examples/minimal_example.md`，实跑产物在 `examples/output/`。
