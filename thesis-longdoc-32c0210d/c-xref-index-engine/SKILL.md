---
name: xref-index-engine
description: 跨章节一致性索引引擎。为分章节长文档（学位论文/长报告的分章 Markdown 工作稿）构建图表题注、图表引用、[n] 引文与参考文献条目、缩略语定义、术语写法的机器可查注册表（index.json），确定性检测悬空引用、重复编号、标题跳号、引文断裂、术语漂移，并在任何编辑前做级联影响分析（改一处，找全所有受影响段落）。当任务涉及多章节稿件的交叉引用检查、图表重编号、术语统一或"这处改动还影响哪里"时触发。
---

# xref-index-engine — 跨章节一致性索引

机械可判定的检查全部由脚本完成；模型只做：读工单、定术语组、执行编辑、判断残留 warn 是否可接受。

## 1. 用途与触发条件

- 分章节 Markdown 工作稿的一致性体检：悬空图表引用、重复题注编号、标题编号断裂、
  引文无条目/条目无引用、缩略语重复定义、术语多写法。
- 编辑前级联定位：改动某图编号/某术语/某小节前，先列出全部受影响 file:line。
- 不适用：单文件无编号结构的散文、需要判断科学正误的内容（见 §7 已知边界）。

## 2. 输入契约

```
/input/case.json                      # case_id, task, output_contract.fields（运行时读取，不得硬编码）
/input/organizer-edit-workorder.json  # 编辑工单 items[]（可能缺省）
/input/ ...章节 Markdown（目录或散文件；若给 PDF 需先 pdftotext）
/app/work                             # 工作目录（索引、报告、编辑副本）
/app/output                           # 最终产物 + result.json
```

## 3. 工作流（按序执行；标注 [脚本]/[模型]）

设 `SKILL_DIR=/skills/weekly-skill/xref-index-engine`（若平台直接装在
`/skills/weekly-skill` 下则 `SKILL_DIR=/skills/weekly-skill`）。

```bash
# [脚本] 0. 准备工作区，把章节复制为可编辑副本（原件不动）
mkdir -p /app/work/chapters_edit /app/output
cp -R /input/chapters/. /app/work/chapters_edit/ 2>/dev/null || cp /input/*.md /app/work/chapters_edit/
```

1. **[模型]** 读 `case.json` 的 `output_contract.fields` 与工单 items。从工单"术语统一"
   类条目提炼术语组，写成 `规范|变体1;术语B|变体B1` 形式（无则省略 --terms）。

```bash
# [脚本] 2. 构建跨章节注册表
python3 $SKILL_DIR/scripts/build_index.py --chapters /app/work/chapters_edit \
    --terms "规范写法|变体1" --out /app/work/index.json

# [脚本] 3. 首检，出 consistency_report.json（有 error 退出码为 1，属预期）
python3 $SKILL_DIR/scripts/check_consistency.py --index /app/work/index.json \
    --out /app/work/consistency_report.json

# [脚本] 4. 先存诚实 partial（预算保护：此后随时超时也已有可交付物）
cp /app/work/consistency_report.json /app/output/
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
    --out /app/output/result.json --status partial \
    --report /app/work/consistency_report.json \
    --uncertainty "首轮检查完成，修复进行中"

# [脚本] 5. 每次编辑前做级联影响分析（三选一锚点；--renumber 可模拟编号变更）
python3 $SKILL_DIR/scripts/impact.py --index /app/work/index.json \
    --anchor figure:2-2 --out /app/work/impact_report.json
python3 $SKILL_DIR/scripts/impact.py --index /app/work/index.json \
    --term "规范写法" --out /app/work/impact_report.json
python3 $SKILL_DIR/scripts/impact.py --index /app/work/index.json \
    --anchor figure:2-2 --renumber figure:2-2=2-5 --out /app/work/impact_report.json
```

6. **[模型]** 按工单 + 报告逐条修复 `/app/work/chapters_edit` 中的章节
   （改编号前先看 impact 的 affected 清单，逐点同步改；术语统一跳过 `[n]` 开头的
   参考文献条目行）。每处修改记录到 `/app/work/changes.json`
   （list：`{"workorder_id","file","before","after","reason"}`）。

```bash
# [脚本] 7. 重建索引并复检，直到 errors=0（残留 warn 写入 uncertainty）
python3 $SKILL_DIR/scripts/build_index.py --chapters /app/work/chapters_edit \
    --terms "规范写法|变体1" --out /app/work/index.json
python3 $SKILL_DIR/scripts/check_consistency.py --index /app/work/index.json \
    --out /app/work/consistency_report.json

# [脚本] 8. 交付：编辑后章节 + 报告入 output，最终 result.json 覆写 partial
mkdir -p /app/output/edited_chapters && cp /app/work/chapters_edit/*.md /app/output/edited_chapters/
cp /app/work/consistency_report.json /app/work/impact_report.json /app/output/
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
    --out /app/output/result.json --status success \
    --report /app/work/consistency_report.json --impact /app/work/impact_report.json \
    --changes /app/work/changes.json --chapters /app/output/edited_chapters \
    --source "/input/chapters" --source "/input/organizer-edit-workorder.json" \
    --uncertainty "残留 warn：……（为何未处理）"
```

脚本替模型省了什么：注册表扫描/编号归一化（build_index）、9+1 条一致性判定与分级
（check_consistency）、受影响点穷举与重编号模拟（impact）、契约字段装配与原子写
（make_result）——模型不用全文 grep 计数，只做编辑与判断。

## 4. 输出契约

- `result.json` 必含 `case_id`、`status`（success/partial/failed）、`sources`、
  `uncertainty`、`change_records`，以及 `output_contract.fields` 声明的**每个字段**；
  无法填充的字段填 `null` 并列入 `unfilled_fields`（诚实 partial）。
- `consistency_report` 字段填 `{"file","errors","warnings"}`；
  `impact_report` 字段填 `{"file","affected_count"}`；`edited_chapters` 填文件名列表。
- 先存 partial 再改进：步骤 4 已保底；每完成一轮修复就重跑步骤 7-8 覆写。
- 编辑后的章节复制到 `/app/output`；报告为 JSON，无绝对路径与时间戳。

## 5. 异常矩阵

| 异常 | 降级路径 |
|---|---|
| 章节不是论文结构（无编号标题/题注/引文） | build_index 计数为 0 → check 报 `non-thesis-structure` warn；仅 float/citation 计数可用，result.json status=partial 并在 uncertainty 说明 |
| 参考文献小节缺失 | citation 规则整体降级为 warn（不 error）；报告 `bibliography_found=false`；在 uncertainty 说明引文未能核对 |
| 引文/图表目标找不到 | dangling-float-reference / citation-without-entry 会给出全部引用点 file:line；按建议改引用或补题注/条目，禁止臆造内容 |
| 工单 items 缺失或目标缺失 | 跳过对应修复，changes.json 记录 `{"workorder_id":N,"skipped":true,"reason":...}`，result.json status=partial |
| 材料为 PDF | 若 `pdftotext` 可用先转文本再按章拆分；不可用则 status=partial 并如实记录 |
| 渲染器不可用 | 本 Skill 不产出渲染件；若上层要求预览而不可用，在 uncertainty 如实记录 |
| 时间/预算不足 | 立即停止新修复，重跑 check_consistency + make_result --status partial，把未完成工单写入 uncertainty |

## 6. 依赖与文件清单

- 依赖：python3 标准库（无第三方包；PDF 场景唯一可选外部工具 `pdftotext`）。
- `scripts/build_index.py`（索引）、`scripts/check_consistency.py`（检查）、
  `scripts/impact.py`（级联影响）、`scripts/make_result.py`（交付装配）。
- `references/consistency_rules.md`（规则触发条件/级别/修复建议）、
  `references/index_schema.md`（index.json 结构与扫描口径）。
- `examples/synthetic/`：合成示例（自造 3 章"钙钛矿太阳能电池封装"，
  **非真实案例**），`run_example.sh` 一键端到端，`expected/` 为真实运行固化的产物。

## 7. 已知边界

- 只做结构性/机械性检查，不判断科学内容正误；不验证引文条目本身的真实性。
- 作者-年份引用（"(Zhang, 2021)"）不做条目匹配，仅 `[n]` 数字引文参与核对。
- 题注识别基于"行首浮动体 token"约定；把引用句写成行首"图 x-y …"会被记为题注。
- 缩略语全称带句首前缀时按互相包含聚类，极端同前缀异义全称可能漏报
  abbrev-redefined-differently。
- 术语匹配为字面子串匹配，不做分词与语义归一。
