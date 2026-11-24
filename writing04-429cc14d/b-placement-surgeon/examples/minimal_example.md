# 最小调用示例（合成示例，全部数据虚构）

本示例演示 placement-surgeon 的端到端流程。示例稿件
`examples/input/manuscript.txt` 是一篇**全部虚构**的中文小综述（3 节 +
1 图注 + 7 条虚构文献），其中**恰好植入 4 个位置缺陷**，另有 1 个对照段：

| 植入缺陷 | 位置 | 内容 |
|----------|------|------|
| P1 段末漂移 | 引言第 2 段 | 2019 年十二国调查（S005）与 2023 年荟萃分析（S006）是两个不同论断，唯一标记 `[2]` 挂在段末 |
| P5 超距覆盖 | 第 2 节 | `[4]` 之后连续 4 句无新标记，S012/S013 出现新数据（860 名受试者、12 周 15%） |
| P3 图表注误挂 | 图 1 注 | 支撑正文 S013 的 `[6]` 被写进了图注（S016） |
| P4 未覆盖论断 | 第 3 节 | S018（1500 份分离株、4 个基因家族）全段无标记，文献表中条目 `[7]` 未被引用 |
| **对照（不应报警）** | 引言第 3 段 | "该试验的随访结果显示……"回指前句，整段单一来源连续论述，段末 `[3]` 合理 |

## 命令步骤（本地相对路径；评测环境用 /skills/weekly-skill/scripts/）

```bash
cd skill/

# 1) 论断切分与标记清点（退出码 0）
python3 scripts/claim_scan.py \
    --manuscript examples/input/manuscript.txt --out examples/output

# 2) 位置审计（预期：4 条 violation，退出码 1）
python3 scripts/placement_audit.py \
    --sentences examples/output/sentences.jsonl \
    --markers examples/output/markers.jsonl \
    --out examples/output
echo $?   # -> 1

# 3) 校验并原子施加修复计划（预期退出码 0）
python3 scripts/placement_plan.py \
    --manuscript examples/input/manuscript.txt \
    --plan examples/input/plan.json \
    --out examples/output

# 4) 复审：对改后稿重跑 1+2（预期：0 violation，退出码 0）
python3 scripts/claim_scan.py \
    --manuscript examples/output/edited_manuscript.txt --out /tmp/ps_after
python3 scripts/placement_audit.py \
    --sentences /tmp/ps_after/sentences.jsonl \
    --markers /tmp/ps_after/markers.jsonl \
    --out /tmp/ps_after
echo $?   # -> 0
```

## 实际运行结果（已目检，产物在 examples/output/）

- 审计报告 **恰好 4 条 violation**：P1（P002，S005–S006）、P5（P004，
  S010–S014）、P3（P005，S016 的 `[6]`）、P4（P006，S018）；退出码 1。
- **对照段 P003 未报警**：P1 的"锚点集非空且不相交"条件对"该试验……"
  回指句不成立（后句锚点集为空），故不判"不同论断"。这正是把 P1 阈值
  设为"锚点不相交"而非"两个事实句即报警"的依据——否则会误伤所有单源
  连续论述段。
- P2 因未提供 intent.jsonl 而跳过，已在报告 `skipped_rules` 注明。
- 施加 plan 的 4 个操作（insert `[1]`→S005、insert `[5]`→S012、move
  `[6]` S016→S013、insert `[7]`→S018）后，复审 **0 violation**、退出
  码 0。
- `change_map.json` 的 diff 目检确认：除 4 处标记的插入/移动外，正文
  零改动。
- 另验证原子性：含错误锚点的 plan 被拒绝（退出码 2），输出目录未创建。

产物清单：`sentences.jsonl`、`markers.jsonl`（原稿扫描）、
`placement_report.json/md`（首审）、`edited_manuscript.txt`、
`change_map.json`、`sentences_edited.jsonl`、`markers_edited.jsonl`
（改后稿重扫）、`placement_report_after.json/md`（复审清零）。
