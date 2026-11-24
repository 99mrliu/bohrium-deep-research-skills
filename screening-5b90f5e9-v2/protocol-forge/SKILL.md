---
name: search-protocol-forge
description: 系统性文献检索案例的检索协议铸造与语法门禁。当案例给出研究问题与数据库范围、要求检索范围可声明可复核（检索式写在哪个库、限定哪些字段、覆盖到哪一天）时使用。重心在上游检索工程：概念块分解、逐库检索式确定性组装、L1–L9 静态语法门禁、标准—概念块映射核验。只在给定快照内工作，不联网检索、不声称全局召回、不预置命中结果。
---

# search-protocol-forge — 检索协议铸造与语法门禁

把研究问题编译成"在哪个库、用什么字段、覆盖到哪一天、每个词为什么在里面"
都能回答的检索协议，并用确定性门禁挡住会在目标库静默失败或答非所问的检索式。

## 1 适用场景与红线

**适用**：案例要求把固定研究问题落成可执行、可复核的检索协议；材料中已有
历史检索式需要评审；需要说明检索范围与纳入标准的对应关系。

**红线**：
- 不联网检索：协议产物是"应该怎么查"的声明，执行只在 `/input` 快照材料上
  对照，禁止声称实时检索或全局召回；
- 不预置命中数：命中数来自案例材料实际统计，不臆造；
- 不过门禁不定稿：FAIL 检索式禁止进入交付；
- 不口头改式：任何检索式修改落新版本并写 change_records。

## 2 运行环境

- Python 3 标准库，无第三方依赖；脚本在 `$SKILL/scripts/`；
- 退出码：0=正常（WARN 不阻断）；2=输入缺失；3=门禁 ERROR（阻断）；
- 全部脚本确定性：同输入同输出，可断点续跑。

## 3 端到端运行契约（平台案例）

1. 读 `/input/case.json` 与 `/input/task.md`：确认 case_id、研究问题原文、
   数据库/字段/时间/语种约束、output_contract 字段。
2. **尽早**落 `/app/output/result.json` 骨架（status=in_progress），逐步填充。
3. 案例材料若已含检索式或查询输入：先过 lint 门禁评审，再决定是否沿用；
   材料若只给研究问题：按第 4 节铸造协议。
4. 后续题录筛选、去重、纳排按案例要求完成；result.json 填齐全部合同字段，
   缺数据字段置 null 并在 uncertainty 说明。status ∈ completed/partial/failed，
   partial 写明完成与未完成边界。

## 4 协议铸造管线（[脚本]=确定性环节，[模型]=判断环节）

0. **[模型] 概念块分解**：把研究问题拆成概念块（人群/干预/对照/结局/研究设计），
   每块收集同义自由词；写成 research_question.json（模式见
   `references/protocol_schema.md`）。案例已给定查询输入时以材料为准，
   分解仅用于映射核验。
1. **[脚本] 协议组装**：`build_protocol.py --question rq.json --out /app/work/protocol`
   → `search_protocol.json`（逐库检索式 + block_trace）。
2. **[脚本] 语法门禁**：`lint_query.py --protocol .../search_protocol.json --out ...`
   → `lint_report.json`。exit 3 时按 issues 修复检索式（改 research_question
   或 notes 说明的手工调整），重跑到 PASS/WARN。
3. **[模型] 历史检索式评审（条件触发）**：材料中的既有检索式逐条
   `lint_query.py --database <方言> --query "<式子>"`，FAIL 项写入
   change_records 并给出修复版。
4. **[脚本] 标准映射**：把案例纳入/排除标准整理成 criteria.json →
   `map_criteria.py --question ... --criteria ... --protocol ...` →
   criteria_map.json/md。M1/M4 ERROR 必须消除；M2/M3 WARN 评估后在
   uncertainty 说明取舍（如"RCT"类标准本就靠筛选兜底）。
5. **[模型] 范围声明**：汇总 数据库×字段×日期×语种×search_date 为一段
   可引用的检索范围声明，写入 result.json 相应合同字段。

## 5 输出合同映射（常见字段）

| 合同字段 | 来源产物 |
|---|---|
| case_id | case.json |
| status | 协议 PASS 且范围声明完成 → completed；材料缺研究问题/约束 → partial |
| product | search_protocol.json（逐库检索式与覆盖声明） |
| evidence_matrix | block_trace + criteria_map（标准↔块↔子句对应） |
| sources | 案例材料清单；协议不引用快照外来源 |
| uncertainty | M2/M3 WARN 项、执行侧限定差异、历史检索式 FAIL 项 |
| change_records | 协议版本变更与原因、历史检索式修复记录 |
| counts | 概念块数、检索式数、lint issue 分级计数 |
| checks | lint overall、map overall |

## 6 异常处理表

| 异常 | 处理 |
|---|---|
| 案例未给研究问题 | status=partial，uncertainty 说明"无法铸造协议，仅评审材料检索式" |
| 研究问题含糊无法分块 | 给出最宽概念块假设并在 uncertainty 标注，禁止编造精确词表充数 |
| 材料检索式 FAIL | 记录 FAIL 详情，给出修复版；执行以修复版为准并留两版 |
| 方言不支持（材料来自其他库） | 在 uncertainty 声明未覆盖该库方言，不硬套白名单放行 |
| 日期/语种约束缺失 | 协议字段置 null 并在 uncertainty 说明，不虚构约束 |
| 门禁反复 FAIL（≥3 轮） | 保留最近 lint_report，status=partial，列出未解决 issue |

## 7 最小调用示例（合成数据）

`examples/minimal/` 含**合成**研究问题（GLP-1 受体激动剂与心血管结局，
虚构示例不对应真实检索任务）与标准表：

```bash
cd <bundle 根目录>
python3 scripts/run_example.py
```

流程：生成三库协议 → 门禁 PASS → 对一条故意写坏的历史查询跑门禁
（预期 FAIL、exit 3，演示 L5/L7/L9 命中）→ 标准映射（预期 WARN：I4/E1/E2
无概念块对应）。最终打印 `EXAMPLE PASS`。产物在 `examples/minimal/output/`，
运行记录见 `examples/minimal/RUNLOG.md`，均为合成示例输出。

## 8 自查方法

- 重跑 run_example.py 两次，search_protocol.json 逐字节一致；
- 手工核对任一数据库检索式：块内 OR、块间 AND、日期限定在登记范围内；
- 把某概念块从 criteria.json 的 blocks 里删掉，M2 WARN 应出现；
  改成不存在的块，M1 ERROR 应使 exit 3；
- 确认 result.json 的检索范围声明与 search_protocol.json 完全一致。
