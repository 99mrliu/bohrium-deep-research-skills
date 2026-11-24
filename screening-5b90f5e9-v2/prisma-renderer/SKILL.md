---
name: prisma-flow-renderer
description: 系统性文献筛选的下游交付渲染。当案例要求把筛选流程计数与判定结果交付为可审阅的图形与报告（PRISMA 2020 流程图、方法学附录草稿）时使用。重心在渲染工程：计数闭合门（不闭合不出图）、确定性 SVG 布局、Mermaid 双轨、报告只复述上游产物数字并显式标注缺失。不产生任何新数字、不美化掩盖未决记录、计数对不上时宁可无图。
---

# prisma-flow-renderer — PRISMA 流程图与可复核报告渲染

筛选做对了，交付层还可能毁掉可信度：流程图数字对不上台账、报告把
待人工记录静默并入纳入侧、缺数据的章节写得像有数据。本技能把交付渲染
做成同源、确定、带闭合门的工程环节。

## 1 适用场景与红线

**适用**：案例要求交付 PRISMA 风格流程图、流程计数表、筛选报告；
需要把台账/判定产物转成评审者可读的最终形态。

**红线**：
- 不闭合不出图：R1–R3 任一 FAIL 即 exit 3，只留 render_check.json；
- 不生成新数字：报告只复述上游产物；缺失章节标"数据缺失"，不编造；
- 不掩盖 pending：needs_human 在图与报告中单列，禁止并入任一侧；
- 不搞双源：图、Mermaid、报告全部从同一份 counts 生成，禁止手改其一。

## 2 运行环境

- Python 3 标准库（含 xml.dom.minidom 自检），无第三方依赖；
- 脚本在 `$SKILL/scripts/`；退出码：0=正常；2=输入缺失；3=闭合门 FAIL；
- 渲染确定性：同输入 counts 的 flow.svg 逐字节一致。

## 3 端到端运行契约（平台案例）

1. 读 `/input/case.json` 与 `/input/task.md`，确认 case_id、材料、
   output_contract 字段。
2. **尽早**落 `/app/output/result.json` 骨架（status=in_progress）。
3. 完成筛选流程（检索/去重/纳排/冲突按案例要求，可用通用方法），
   把各环节计数汇成 counts.json（键见 render_flow.py 头部注释）；
   计数必须来自真实台账产物，禁止凭印象填写。
4. 执行第 4 节渲染管线；产物放 /app/output。
5. result.json 填齐全部合同字段；status ∈ completed/partial/failed；
   渲染层发现上游计数不闭合时，status=partial 并把差额写进 uncertainty
   （渲染层不修上游数字）。

## 4 渲染管线（编号步骤）

0. **[模型] 汇总 counts.json**：从台账/判定产物取数；含
   identified/duplicates_removed/screened/excluded/included/needs_human，
   可选 exclusion_reasons、databases、search_date。
1. **[脚本] 流程图**：`render_flow.py --counts counts.json --out /app/output`
   → flow.svg + flow.md + render_check.json。exit 3 时把闭合差额回交
   上游环节排查，修好后重渲染。
2. **[脚本] 报告**：`build_report.py --counts ... --protocol ...(可选)
   --decisions ...(可选) --flow-md /app/output/flow.md --out /app/output`
   → screening_report.md。缺的可选输入自动降级为"数据缺失"标注。
3. **[模型] 目检**：打开 flow.svg 确认布局可读（盒不重叠、箭头连贯）、
   数字与 counts 一致；读 screening_report.md 确认缺失清单与事实相符。
4. **[模型] 回填合同**：render_check 的门状态、产物路径、缺失清单
   填入 result.json 相应字段。

## 5 输出合同映射（常见字段）

| 合同字段 | 来源产物 |
|---|---|
| case_id | case.json |
| status | 闭合门全过且报告无缺失 → completed；有缺失标注 → completed 但 uncertainty 点名；门 FAIL → partial |
| product | flow.svg / flow.md / screening_report.md 及说明 |
| evidence_matrix | render_check.json 各门算式与差额 |
| sources | counts/protocol/decisions 等上游产物路径 |
| uncertainty | 报告缺失清单、needs_human 待确认声明 |
| change_records | 渲染参数与重渲染记录（若上游计数修正） |
| counts | 流程计数表（与图、报告同源） |
| checks | R1–R4 门状态、svg well-formed、svg_bytes |

## 6 异常处理表

| 异常 | 处理 |
|---|---|
| counts 缺整数键 | render_flow exit 2；回上游补台账，不猜数 |
| R1–R3 不闭合 | exit 3；差额写入 render_check 与 result.json uncertainty；禁止强渲 |
| 计数全零（合法空结果） | 照常渲染 0 值；报告保留 0 而非缺失标注 |
| 理由分解与 excluded 不等 | R3 FAIL；回查判定产物的理由码统计口径 |
| 输入文本含 XML 特殊字符 | escape 处理 + R4 well-formed 门兜底 |
| 全部报告输入缺失 | build_report exit 2；status=partial，说明渲染无米下锅 |

## 7 最小调用示例（合成数据）

```bash
cd <bundle 根目录>
python3 scripts/run_example.py
```

合成计数（200→23→177→160+12+5，理由分解 80+50+30）渲染出 flow.svg
（已目检：四盒三箭头、数字正确、well-formed）；篡改 excluded 为 159
立即被 R2/R3 拦截 exit 3；全量输入生成 screening_report.md（无缺失）；
仅 counts 输入生成降级报告（缺失清单 3 项）。**随包保留文本产物**
（flow.md、screening_report*.md、render_check.json）；flow.svg 为运行时
图形产物，由 `python3 scripts/run_example.py` 一条命令重新生成，
未随包附带（保持包内全部为平台允许的文本资源）。详见
`examples/minimal/RUNLOG.md`。

## 8 自查方法

- 重跑 run_example.py 两次，flow.md 与 render_check.json 逐字节一致；
- 对照 counts.json 逐盒核对 SVG/报告中的每个数字；
- 把 exclusion_reasons 改一个值，R3 应 FAIL 且无图产出；
- 确认报告缺失清单与实际提供输入一致，无"无声缺节"。
