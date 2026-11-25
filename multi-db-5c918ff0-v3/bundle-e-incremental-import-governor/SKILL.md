---
name: incremental-import-governor
description: 多数据库联合检索的"增量导入治理与变更追踪"技能,专攻检索的时间维度。将组织者本地的上一轮 import_state(三种方言:records+watermarks / 扁平映射 / JSONL;逐库水印游标 + 逐记录内容哈希)与当前离线响应材料对账,把每个标识符六路分类:new / unchanged / changed(状态方言存字段时给出 field 级 before→after,否则诚实声明 changed_fields_unavailable)/ withdrawn(区分 source_present_but_record_gone 与源亦缺席的 unverifiable_withdrawal)/ inconsistent_state(状态行自相矛盾或标识符形态与声称来源库冲突)。随后产出水印推进提案 proposed_next_state.json(requires_approval=true,绝不静默写回、数值水印防回退)、delta_report.md 差异报告,并把模型对 changed/withdrawn/inconsistent 条目的单次批量处置(change_dispositions.json)折叠为 final_governed_state.json。import_state 缺失→首次导入基线模式;方言嗅探失败→诚实 partial 不猜结构;同一输入重跑字节级一致(内置确定性自查)。Python 3 标准库、离线、幂等。
---

# incremental-import-governor:增量导入治理与变更追踪

## 适用场景与边界

当多数据库联合检索任务提供了**上一轮组织者本地导入状态**(import_state:
逐库 watermarks/cursors + 逐记录 content hash)与**本轮离线响应材料**,
要求回答"自上一轮以来发生了什么变化"时启用本技能。典型问题:哪些记录
是新增的?哪些元数据变了、变了哪些字段?哪些记录从响应中消失了?水印
应该推进到哪里?

**边界(严格遵守):**

- **不联网**:只处理本地材料;材料即响应,不做任何超出材料证据的推断。
- **水印只出提案,绝不写回**:组织者本地状态是权威数据,本技能治理而不
  擅自变更。`proposed_next_state.json` 恒含 `requires_approval: true`,
  输入的 import_state 文件一个字节也不会被修改。
- **状态文件格式未知时不猜结构**:方言嗅探失败即写 sniff_report 并走
  exit 2 诚实 partial 路径,绝不按猜测的结构解析。
- **不做撤回语义判定**:本技能只登记"记录已不在响应中"的导入治理事实;
  是否撤稿/删除(retraction analysis)属于另一个专门流程,报告中仅给出
  移交指针。同理,本技能不做去重合并、不做查询规划、不做覆盖统计。

## 运行环境

- Python 3(仅标准库),离线,确定性:同一输入重跑,产物字节级一致
  (`selfcheck` 内置重跑比对)。无墙钟、无随机数、无绝对路径写入产物。
- 平台将本技能安装于 `/skills/weekly-skill`。若路径不确定,回退定位:
  `find / -maxdepth 6 -name "import_governor.py" 2>/dev/null`;
  若环境提供了 `$SKILL` 变量,则脚本位于 `$SKILL/scripts/import_governor.py`。
- 退出码:`0` = success;`2` = 诚实降级 partial(方言嗅探失败、待处置
  条目缺 dispositions、自查 FAIL);`3` = input_error(case.json 缺失/
  不可解析/缺 case_id)。

## 运行契约

- 输入只读:`/input`(case.json + task.md + materials/);
  中间产物:`/app/work`(previous_state.json、current_state.json、
  import_diff.json、sniff_report.json、proposed_next_state.json、
  selfcheck.json,以及模型产物 change_dispositions.json);
  交付物:`/app/output`(result.json、delta_report.md、
  final_governed_state.json)。
- `result.json` 恒含:`case_id`、`skill_name`、`status`
  (`success|partial|input_error`)、`products`、`sources`(逐输入文件
  sha256)、`counts`(previous_records/current_records/new/changed/
  unchanged/withdrawn/unverifiable_withdrawal/inconsistent)、
  `uncertainty`、`change_records`、`checks`、`baseline_established`、
  `watermark_requires_approval`、`unresolved_contract_fields`,
  以及 `case.json.output_contract` 声明的**每一个字段**——有确定性映射
  则填充,无法填充一律置 `null` 并列入 `unresolved_contract_fields`,
  **绝不捏造**;任何降级都是诚实 partial。

## 工作流程

0. **(脚本)读取 case**:校验 case.json(缺失→exit 3 并落 input_error
   骨架);**尽早**写出 result.json partial 骨架,保证任何中断都留下
   诚实中间态。
1. **(脚本)parse**:结构嗅探全部材料(crossref 信封 / EuropePMC
   resultList / 出版方 JSON/JSONL/CSV / reference_graph / import_state),
   对 import_state 做方言推断(a/b/c,见
   `references/import-state-dialects.md`)并规范化为
   `work/previous_state.json`;未知方言 → sniff_report + exit 2,
   不猜结构。材料中无 import_state → 首次导入基线模式。
2. **(脚本)骨架确认**:result.json 骨架已在第 0 步落盘。
3. **(脚本)快照当前响应**:抽取各源记录并规范化(标识符优先级
   doi → pmid → 源内 id),按精确定义(见方言文档)计算内容指纹
   content_fingerprint,写 `work/current_state.json`(含逐源游标信号:
   next-cursor / nextCursorMark / 条目数)。
4. **(脚本)diff**:对状态∪当前的标识符并集做六路分类,写
   `work/import_diff.json`,每条带证据定位(state_record_index /
   material + locator)。不变量:六类互不重叠、完备,计数和 = 并集大小
   (脚本内 assert)。
5. **(模型,唯一判断点,至多 1 次批量请求)**:代理通读 import_diff 中
   全部 changed / withdrawn / unverifiable_withdrawal /
   inconsistent_state 条目,**单次批量**给出处置
   (accept_change / keep_previous / exclude_withdrawn / escalate)
   与理由,写 `work/change_dispositions.json`;随后
   `apply-dispositions` 校验(标识符必须已知、处置必须合法)并折叠为
   `output/final_governed_state.json`(水印仍保持原值,待批准)。
6. **(脚本)watermark + report**:按 `references/watermark-policy.md`
   生成 `work/proposed_next_state.json`(在场库按规则推进、缺席库
   HELD 并注明 hold_reason、数值回归守卫)与
   `output/delta_report.md`(计数、before→after 表、撤回双子类表、
   不一致表、水印提案表、批准清单)。
7. **(脚本)finalize**:填充 result.json 全部契约字段;uncertainty
   必须列出 unverifiable_withdrawal、changed_fields_unavailable、
   未批准水印、escalate 待人工项。
8. **(脚本)selfcheck**:契约键齐全;分类分区算术;**同输入重跑
   parse+diff,import_diff.json 必须字节一致**;水印数值不回退;输入
   import_state 哈希未被改动。FAIL → status 保持 partial,exit 2。

## 输出合同映射表

| output_contract 字段名(含同义词) | 确定性来源 |
| --- | --- |
| `import_classification_counts` / `classification_counts` / `diff_counts` | import_diff.json 的 counts(六类 + 两轮记录数) |
| `changed_field_diffs` / `changed_records` / `changed_entries` | changed 条目的 field 级 before→after 列表 |
| `watermark_proposal` / `proposed_watermarks` | proposed_next_state.json 的 watermarks 节(含 requires_approval) |
| `delta_report_path` / `delta_report` | 常量 `"delta_report.md"` |
| `governance_summary` / `import_summary` / `delta_summary` | 由 counts 确定性拼装的摘要句 |
| `final_governed_state_path` | dispositions 已应用时为 `"final_governed_state.json"`,否则 null |
| 其他任何字段名 | `null` + 列入 `unresolved_contract_fields`(不编造) |

## 异常处理表

| 异常 | 行为 | 退出码 |
| --- | --- | --- |
| case.json 缺失/不可解析/缺 case_id | result.json 落 `input_error` 骨架 | 3 |
| 材料中无 import_state | **首次导入基线模式**:previous 为空,全部当前记录分类 new,声明 `baseline_established`,水印动作记 initialize | 0 |
| import_state 方言嗅探失败 | 写 sniff_report(含失败原因),诚实 partial,**不猜结构** | 2 |
| changed 但状态方言不存字段 | 仅报指纹变化,声明 `changed_fields_unavailable` | 0(列入 uncertainty) |
| 记录消失且其来源库响应缺席 | `unverifiable_withdrawal`(不可核验),不结论为撤回 | 0(列入 uncertainty) |
| 有待处置条目但未给 --dispositions | diff/提案/报告照常,final_governed_state.json 不生成,partial | 2 |
| dispositions 校验失败(未知标识符/非法处置/重复) | 拒绝折叠,partial 并列出全部错误 | 2 |
| selfcheck 任一项 FAIL | status 保持 partial,checks 给出精确原因 | 2 |

## 合成最小示例

`examples/synthetic-input/`(`case_id: "synthetic-import-gov-001"`):
11 条状态记录 × 10 条当前记录,精确工程化为 7 unchanged / 1 changed
(期刊更名 + 年份更新,field 级可见)/ 2 new / 1 withdrawn(europepmc
在场而记录消失)/ 1 unverifiable_withdrawal(publisher 响应缺席)/
1 inconsistent_state(状态行 identifier 与 fields.doi 冲突)。publisher
材料**有意缺席**,同时演练水印 HELD 与不可核验撤回两条路径。
`examples/synthetic-output/` 为**真实运行**产物(含手工编写的
change_dispositions.json 作为模型步),复现命令与退出码见
`examples/synthetic-output/run-record.md`。

## 诚实声明

- 所有"判定"均为确定性规则或模型显式处置;脚本不猜测、不捏造。
- 水印提案永不自动生效;`result.json` 中 `watermark_requires_approval`
  恒为 true,未批准前组织者状态视为不变。
- withdrawn 仅是导入治理事实,不构成撤稿结论。
- 不可核验项(unverifiable_withdrawal / changed_fields_unavailable /
  escalate 待人工)一律写入 `uncertainty`,绝不静默吞掉。
