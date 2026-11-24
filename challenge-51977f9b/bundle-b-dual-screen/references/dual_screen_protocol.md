# 双人独立筛选协议（slr-dual-screen）

> 目标：让"换一个人拿着同样的输入和记录，能复跑出基本一致的纳入集"。
> 本协议规定两轮双人筛选的流程、隔离纪律与排除条款代码表设计。

## 1. 两轮筛选流程

| 轮次 | 级别 | 输入 | 判定依据 | 产出 |
|------|------|------|----------|------|
| round 1 | 题录级 | records.json（题录+摘要） | 标题/摘要 vs 纳排条款 | decisions_round1.jsonl |
| round 2 | 全文级 | round 1 存活记录的全文 | 全文细节 vs 纳排条款（重点核实全文可得性、结局数据、设计真实性） | decisions_round2.jsonl |

每轮固定顺序：**条款先行 → A/B 独立判定 → screen_check → kappa → 仲裁本轮分歧 →
存活者进入下一轮**。round 2 完成后统一冻结。

判定取值：`include` / `exclude` / `uncertain`。
- `exclude` 必须给出条款代码（reason_code）与 ≥8 字符的文字理由（S3）；
- `uncertain` 是"本轮信息不足以判定"，**永不直接计入纳入**（S4），只允许经仲裁转判；
- 两名筛选者都判 `include` 才算共识纳入；一方 `uncertain` 即构成分歧。

## 2. pass 隔离纪律（签名能力的关键）

Agent 扮演两名互相独立的筛选者：**pass 1 以筛选者 A 身份判定，pass 2 以筛选者 B
身份判定**。pass 2 若参考 pass 1 的结论，kappa 就失去意义（虚假一致）。

给 Agent 的可执行隔离指令（SKILL.md 工作流程中原文引用）：

1. 开始 pass 2 之前，**不得读取、引用、复述** decisions_round1.jsonl 中任何
   A 的判定与理由；只允许读取 records 原文与 criteria 条款。
2. pass 2 的每条 reason_text 必须**仅引用该记录自身的内容与条款编号**，
   出现"同上""与 A 一致""如前所述"等措辞即视为隔离失败，须重写该条。
3. pass 2 独立完成后才允许运行 screen_check / kappa 查看双方结论；
   此后禁止回头修改 pass 1 / pass 2 的任何原始判定（改判只能走仲裁）。
4. 上下文工程建议：pass 2 尽量在"干净上下文"中执行——先让模型忘掉 pass 1
   的中间推理，只给 records + criteria + schema；若平台无法清空上下文，
   则在提示词中显式声明"以下判定不得参考此前任何筛选结论"。

## 3. 排除条款代码表设计

原则：代码稳定、互斥优先、单一事实来源（criteria.json），并**版本化**。

推荐基础代码表（可按案例扩展，但代码一经使用不得改义，只能新增）：

| 代码 | 含义 | 典型触发 |
|------|------|----------|
| EX-POP | 人群不符 | 非目标人群/年龄段/疾病分期 |
| EX-DESIGN | 研究设计不符 | 综述、病例报告、无对照单臂（当条款要求 RCT 时） |
| EX-OUTCOME | 结局指标不符 | 未报告条款要求的结局 |
| EX-TIME | 时间范围不符 | 早于/晚于时间窗 |
| EX-LANG | 语言不符 | 超出语言清单 |
| EX-FULLTEXT | 全文不可得 | 仅摘要、付费墙后无获取渠道 |

配套纳入条款（IN-*）与之一一对应，排除时引用 EX- 代码，理由文字复述该条款的
具体违犯点（"人群为儿童脑瘫，违反 IN-POP 的成年脑卒中要求"），而不是只写代码。

### 版本纪律（治理"纳排标准被悄悄放宽"）

- criteria.json 从 **v1.0** 起版本化，筛选启动即锁定；
- 筛选途中确需修改条款（如发现条款歧义）：升版本（v1.0→v1.1）→ 在
  result.json.change_records 写一条 {time, field:"criteria", from, to, reason,
  affected_records} → **重筛全部受影响记录**（双方重判该子集，新一轮 kappa）；
- 禁止"只改标准不回筛"；禁止口头放宽而不改 criteria.json。

## 4. 单人筛选降级模式

材料或预算不足无法完成双 pass 时允许 single-screener 模式：
result.json 的 status 必须为 partial，counts 记 `single_screener: true`，
uncertainty 声明"无双人对照，纳入集可复现性未验证"，kappa 环节记为不适用。
