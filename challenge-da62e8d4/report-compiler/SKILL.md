---
name: report-compiler
description: 台账驱动的可核验报告编译。当论文复现/方法验证流程收尾、需要交付可核验报告与对比图表时触发：所有数字只能来自六个机器可读台账 JSON（inventory/targets/runs/comparison/attributions/result），由编译器机械注入生成 report.md、自包含 report.html 与带容差带的对比图，再由独立审计器把报告里的每个关键数字与台账逐一对账（孤儿数字、覆盖率、图存在性、result 契约全字段），审计不 PASS 不交付。适用于"论文复现与方法验证"中参数/代码/指标验算与差异归因子场景的"最后一公里"防失信。
---

# report-compiler：台账驱动的可核验报告编译

## 用途与适用条件

本 Skill 只做一件事、并把它做硬：**复现报告是编译产物，不是手写文档。**
复现报告的失信往往发生在"最后一公里"：人手抄数进报告抄错、结论与表格不一致、
图与数据不符。本 Skill 让报告里的每个关键数字都有机器可读的出处，并能被脚本对账。

适用条件：
- 上游已完成材料盘点、指标抽取、候选代码运行与逐项比较（或有其中一部分，允许 partial）；
- 需要交付带图表、可被独立脚本核验的复现报告；
- 需要防"台账改了报告没改 / 报告改了台账没改 / 结论塞了台账里没有的数字"。

不适用（不是本 Skill 重心，请配合其他工具或人工完成）：PDF 指标抽取、候选代码的
实际运行与统计判定、容差的制定。这些由 agent 按 schema 填进台账；编译器只做 schema
校验与代数复核（按 targets 容差重算 within），不做科学判断。

## 核心思想

1. **报告 = 编译产物。** 人只写台账（六个 JSON），不写报告里的数字。编译器把数字
   从台账注入 report.md / report.html / 对比图，并在 report_map.json 里给每个关键
   数字登记台账指针（`comparison.json#/entries/0/reproduced_value` 这种形式）。
2. **审计不过不交付。** 独立审计器不信任编译产物：重读台账逐项对账——登记值与台账
   当前值相等、比较表行数 == comparison 条目数且逐格一致、结论段无台账之外的
   "孤儿数字"、图文件存在且非空、result.json 含 case_id 与 output_contract 全字段。
   FAIL 就退回台账修正后重新编译，绝不手改报告。
3. **缺失不中断、但要留痕。** 台账缺文件 → 编译降级为 PARTIAL 报告并列出缺口清单；
   缺失材料/不确定性/变更记录必须成段出现，不许省略。

## 铁律

1. **台账外无数字。** 报告（尤其结论段）出现的任何数字必须能追溯到台账或
   report_map 登记/白名单；想加一个数字，先加进台账，再重新编译。
2. **结论分级只能由 comparison 判定机械汇总。** 规则（详见
   references/report_contract.md）：无有效比较 → `unable`；全部在容差内 →
   `reproducible`；有超差但每条超差均有证据归因 → `partially_reproducible`；
   有超差且无归因 → `not_reproducible`。agent 不得"凭感觉"写结论。
3. **缺失材料、不确定性、变更记录必须成段。** 原始数据/作者仓库缺失是**预期情况**，
   在 inventory 登记 `status: missing` 并在报告"缺失材料"节显式呈现，不得掩盖。
4. **result.json 全字段诚实。** 含 case_id 与 output_contract 全部字段；status ∈
   success / partial / unable / refused；审计会机检字段齐备与值非空。
5. **组织方合成代码 ≠ 作者原代码。** 合成数据上的"在容差内"只能表述为"候选实现与
   合成目标在容差内一致"，**不能写成论文数值复现**；禁止编造任何数据。
6. **预算纪律。** 总预算约 64 次模型请求 / 900 秒：编译与审计是廉价脚本，一次跑通
   后只修台账重编译，不要反复手润报告文本烧请求。

## 逐条命令流程（$SKILL 指代技能目录，评测时为 /skills/weekly-skill）

```bash
# 0. 读 /input/case.json 与 /input/task.md，提取 case_id 与 output_contract 字段清单
# 1. 在 /app/work/ledgers/ 下按 schema 填六个台账（字段级定义见下表与
#    $SKILL/references/report_contract.md；可直接以 $SKILL/examples/ledgers/ 为模板）：
#    inventory.json    材料清单：locator 与 present/missing（缺失显式登记）
#    targets.json      指标目标：论文值、单位、容差（abs/rel）、论文内来源定位
#    runs.json         运行记录：方法×指标×逐种子观测值、环境、命令、状态
#    comparison.json   比较：指标×方法的论文值/复现值/差值/within 判定
#    attributions.json 差异归因：每条超差给 cause + evidence（证据指针）
#    result.json       最终契约底账：case_id、status、output_contract 全字段、
#                      sources、uncertainties、changelog

# 2. 编译（台账 -> 报告）
python3 $SKILL/scripts/compile_report.py \
    --ledgers /app/work/ledgers --out /app/output/report
#    退出码 0 = 编译完成（含 PARTIAL 降级）；2 = 台账 schema 严重错误，先修台账
#    --svg 可强制纯标准库 SVG 渲染（无 matplotlib 时自动降级，无需干预）

# 3. 审计（不过不交付）
python3 $SKILL/scripts/audit_report.py \
    --ledgers /app/work/ledgers --report /app/output/report
#    终端打印 PASS/FAIL 与逐条明细，产物 audit.json；退出码 0=PASS，1=FAIL

# 4. 若 FAIL：按审计报错定位到具体数字 -> 改台账（不是改报告！）-> 回到第 2 步
# 5. PASS 后：把 /app/output/report 下的 report.md / report.html /
#    figures/ / report_map.json / audit.json 作为可编辑产物的渲染预览提交目检，
#    result.json 按台账 result.json 内容落到 /app/output/result.json
```

### 六个台账 schema 速查表

| 台账 | 顶层键 | 每条记录必填字段 |
| --- | --- | --- |
| inventory.json | materials[] | id, kind, status(present\|missing) |
| targets.json | metrics[] | id, name, paper_value, unit, tolerance{type:abs\|rel, value}, source_locator |
| runs.json | runs[] | run_id, method, metric_id, values[数字…], status |
| comparison.json | entries[] | metric_id, method, paper_value, reproduced_value, abs_diff, rel_diff, within |
| attributions.json | attributions[] | metric_id, method, cause, evidence |
| result.json | （顶层） | case_id, status, output_contract{字段:值…}, sources[], uncertainties[], changelog[] |

## 输入输出

输入：
- `--ledgers`：含上述六个 JSON 的目录（可缺，缺则 PARTIAL 降级）。

输出（`--out` 目录）：
- `report.md`：固定九章——材料定位 / 环境与参数 / 运行记录 / 指标比较 /
  差异归因 / 复现结论 / 不确定性 / 缺失材料 / 变更记录；每章数字从台账注入；
- `report.html`：自包含（内联 CSS、表格、base64 PNG 或内联 SVG 图），供目检；
- `figures/comparison_<指标id>.png|.svg`：每指标一图，画论文值点、各方法复现
  聚合点、逐种子散点与容差带；
- `report_map.json`：报告数字 → 台账 JSON 指针数组 + 计数/分级派生登记 +
  图清单 + partial/gaps 标记 + 孤儿数字显式白名单；
- `audit.json`（审计器产出）：overall PASS/FAIL 与逐条明细。

## 异常处理表

| 异常 | 行为 |
| --- | --- |
| 无 matplotlib | 自动降级为纯标准库 SVG 渲染，报告头部与 report_map.renderer 注明"已降级"；也可用 `--svg` 强制 |
| 台账缺文件 | 编译不中断：生成 PARTIAL 报告，头部与 report_map.gaps 列出缺口，退出码仍为 0；result.json 缺失时审计 result_contract 会 FAIL（如实反映） |
| 台账 schema 严重错误（解析失败/必填字段缺失/类型错/comparison 引用未知指标） | 编译拒绝执行，退出码 2，stderr 给出具体字段位置；修好台账再编译 |
| comparison 的 within 与按 targets 容差重算不一致 | 编译采用重算值并在 report_map.warnings 留痕（机械复核，不做科学判断） |
| 审计 FAIL | 逐条列出具体数字与位置（如"比较表第 0 行第 4 列：报告中为 0.935，台账应为 0.933"）；一律退回改台账后重新编译，禁止手改报告文本 |

## 运行契约（评测环境）

- 输入在 `/input/case.json` 与 `/input/task.md`：case.json 含 case_id 与
  output_contract 字段清单，材料按题目提供（真实 PDF、两份候选数值方法代码）；
- 工作在 `/app/work`（台账建议放 `/app/work/ledgers/`），最终产物在 `/app/output`；
- `/app/output/result.json` 必须含 case_id 与 output_contract 全部字段、诚实的
  status（success/partial/unable/refused）、来源定位、不确定性、变更记录——
  本 Skill 的 result 台账即其底账，审计器会机检；
- 诚实 partial：材料缺失/无法完成的项登记为 partial 并说明，绝不编造；
- report.html 与 figures/*.png|.svg 即为可编辑产物的真实渲染预览，交付前按
  references/report_contract.md 第 5 节目检清单过目。

## 最小合成示例

`examples/` 下是**合成示例（synthetic），非正式案例结果**：两个候选方法 × 3 项指标
共 6 条比较（含 1 条超差且已归因）、一条缺失材料登记、一条变更记录、result.json 带
case_id 与 output_contract 字段。

```bash
bash $SKILL/examples/run_example.sh /app/work/example_out        # 默认渲染（有 matplotlib 出 PNG）
bash $SKILL/examples/run_example.sh /app/work/example_out --svg  # 强制 SVG 降级链
# 预期：编译 -> 审计 PASS -> 打印结论分级 partially_reproducible
# 预期产物副本（SVG 链）见 examples/expected/
```

## 限制与自查

限制：
- 审计的孤儿数字检查只覆盖"复现结论"段（其余章节的数字全部经 report_map 登记与
  比较表逐格对账覆盖）；把数字篡改成另一个已登记数字无法被发现——交付前仍需目检；
- 编译器不验证台账内容的科学性（复现值算得对不对是上游运行流程的责任）；
- 纯标准库 SVG 是降级渲染，样式朴素；matplotlib 路径无中文字体时图标签降级为 ASCII。

交付前自查：
- [ ] audit.json overall = PASS；若是 PARTIAL 报告，gaps 与预期一致且已如实说明；
- [ ] report.html 浏览器打开自包含渲染正常，图的容差带/单位/轴正确；
- [ ] 结论分级与 comparison 机械汇总一致，未把合成数据达标写成论文数值复现；
- [ ] result.json 的 output_contract 覆盖 case.json 要求的全部字段；
- [ ] 缺失材料 / 不确定性 / 变更记录三节均非空且诚实。
