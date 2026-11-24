# 合成示例说明（example run）

**这是合成示例，非正式测评结果。** `mock_case.json` 的 `note` 字段已标明"合成示意案例"：
全部价格、预约信息与候选方案均为演示构造的前瞻约定，不对应真实供应商报价或已确认排期。
`output/` 下每个由脚本生成的文件头部均含"合成示例输出，非正式测评结果"标注
（throughput.json/schedule.json/repair.json 为结构化数据，标注在对应 .md 文件头部）。

## 如何复跑
```bash
bash run_example.sh          # 默认使用 ../scripts/schedule_forge.py
SCHEDULE_FORGE=/skills/weekly-skill/scripts/schedule_forge.py bash run_example.sh
```
四步：① throughput 体检候选 v1/v2/v3 + 用户修订方案 rev1；② schedule 排 rev1
（预期超期被抓出）；③ repair 出修复选项表；④ 采纳修复后的 rev2 重排（预期 28 天可行）。

## 输出如何解读
- `throughput.md/.json`：设备吞吐表 + 逐候选体检。关键看点：
  - **v1**：est_days=28 与瓶颈算式一致（手套箱 40h ÷ 12h/周 = 4 周 = 28 天），但被抓出
    两处算术错误（XRD subtotal 120×15=1800≠1500；Σsubtotal=8000≠声明 total_cost=7330）；
  - **v2**：96h 手套箱机时在 3 slots/周 × 4h = 12h/周下需 8 周 = 56 天，超 30 天 deadline
    26 天，est_days=21 被判定"不可信"——典型拍脑袋；
  - **v3**：est_days=35 本身超 deadline，且引用了合同表外的 EQ-UV（无法核算）；
  - EQ-HP 加热台由脚本从 `equipment_domain_note` 文本内嵌 JSON 解析合并进设备表。
- `schedule_rev1.json` + `gantt_rev1.md` + `cashflow_rev1.md`：rev1（对手套箱堆了 56h）
  排程总工期 49 天，超期 19 天；检测到 EQ-GB 被排至第 7 周、超出其 30 天预约窗口；
  现金流按周累计（含试剂前置 1 周采购），W7 因 S6 结算出现 2880 元峰值。
- `repair.md/.json`：5 个修复选项按节省天数排序——S6 改用 EQ-HP（21 设备天，但有口径
  差异代价）、S2 批处理（7 天）、S6 削减重复 3→2（7 天）、S3 批处理（6 天）、
  XRD 合并批次（1 天），每项带算式与代价。
- `schedule.json` + `gantt.md` + `cashflow.md`（rev2）：采纳"S2 批处理 + XRD 合并 +
  S6 重复 3→2"后总工期 28 天 ≤ 30，无溢出无双订——验证 repair 后必须重排才算数。

## 注意
- rev1→rev2 的修复是人工按 repair.md 选择的（体现 SKILL.md 的"≤3 轮迭代"），
  脚本只负责算数与检测，不自动改方案。
