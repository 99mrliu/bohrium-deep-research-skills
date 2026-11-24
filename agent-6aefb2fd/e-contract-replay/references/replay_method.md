# 复算方法论与异常分类法

## 1. 第三方复核立场（replay_check.py）

复核器刻意"无知"：不读 SKILL 文档、不信任任何自报日志，只认 /input 原始数据
与自己的重算。三项硬判定：

- **R1 契约完整**：result.json 与 case.json 的 case_id 一致；status=success 时
  契约字段非空；引用的 /app/output 路径真实存在。这是"交付物存在性"底线。
- **R2 行数口径**：cleaned 表行数不得超过列匹配（Jaccard≥0.8）的原始表行数——
  行数变多几乎必然是拼接/复制事故；行数变少则必须有清洗证据（本复核器认可
  含 initial_rows/final_rows 的交付 JSON 作为口径说明，但以实测为准）。
- **R3 数字复算池**：报告中的数字有两个合法来源：交付的统计/证据 JSON（自报），
  或复核器从原始数据与 cleaned 表独立重算的描述统计池（行数、count/mean/std/
  min/median/max、分组计数、两两 Spearman 相关）。命中复算池而未命中自报 JSON
  视为通过——复核承认独立重算也是合法来源；两者都不命中即无源数字，阻断。

### 容差与豁免

与渲染契约同一规则：报告数字 x（d 位有效数字）与源值 y 满足
|x−y| ≤ 0.5×10^(⌊log10|x|⌋−d+1)；1–2 位有效数字与行首编号豁免。

### 已知边界

- 复算池是描述统计级：p 值、效应量等推断量必须由交付统计 JSON 承载（自报），
  复核器不重新选择检验方法（避免方法学分歧冒充数据问题）。
- 列匹配 Jaccard<0.8 时 R2 降级为"未找到原始表"的通过（记录 detail），
  因为 cleaned 表可能经过合法的列裁剪/重命名。

## 2. 异常分类法（contract_seal.py raise）

| kind | 何时使用 | 例子 |
|-|-|-|
| missing_material | case.json 声明的材料缺失或不可读 | 声明的 xlsx 不存在 |
| query_failure | 数据库/文件查询失败且无法恢复 | SQLite 打不开、表不存在 |
| unexplainable_result | 结果与任务预期冲突且无法解释 | 任务断言有差异但 p 不显著 |
| human_confirmation_needed | 需要领域判断才能定夺 | 近重复是否同一样本 |
| capability_limit | 超出 Skill/环境能力 | 无 scipy、多因素设计超范围 |

规则：异常必须分类登记，禁止笼统的"有些问题"；每条条目含 detail 与时间；
exceptions 字段为空本身即是 seal 的阻断项——没有异常时必须显式写
"无未解释异常"。

## 3. 交付顺序纪律

1. begin（第一件事，先保 partial）；
2. 产物落盘一个、fill 一个（fill 会拒绝悬空路径）；
3. 每遇异常立即 raise，不留到收尾凭记忆补写；
4. seal 之前跑 replay_check；复核失败先修复再 seal；
5. seal success 被拒时不许绕：修复、raise、或 partial。
