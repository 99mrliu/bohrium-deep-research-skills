# 合成示例（synthetic，非正式案例结果）

本目录是**完全合成**的最小演示：`input/case.json` 含 6 条虚构候选（C002/C003 为
按归一化标题判重的重复对，C003 与 C005 缺 DOI），`input/decisions.jsonl` 含 5 条
有效决定 + 1 条**故意无效**的决定（第 6 行的 evidence_quote 系编造，不在 C001 的
标题/摘要中），用于演示机器核验拒绝。所有文献均为虚构，不代表任何真实出版物。

## 运行命令（在临时目录中实测通过）

```bash
B=<bundle 根目录>          # 本 bundle 的绝对路径
TMP=$(mktemp -d); W=$TMP/work; O=$TMP/output
python3 $B/scripts/init_ledger.py     --case $B/examples/input/case.json --workdir $W --output-dir $O
python3 $B/scripts/apply_decisions.py --workdir $W --decisions $B/examples/input/decisions.jsonl
python3 $B/scripts/flow_check.py      --workdir $W
python3 $B/scripts/build_result.py    --workdir $W --output-dir $O --case $B/examples/input/case.json
```

## 真实运行输出摘录（exit code 均为实际值）

```
$ init_ledger.py        → identified=6 unique=5 duplicates_removed=1 lists=1   (exit 0)
$ apply_decisions.py    → REJECT line 6 (C001): evidence_quote 未通过机器核验：归一化后不是 C001 标题/摘要的子串
                          applied=5 rejected=1 total=6                          (exit 0)
$ flow_check.py         → identified=6 duplicates=1 unique=5 screened=5 include=1 exclude=3
                          uncertain=1 unscreened=0 invariants=PASS              (exit 0)
$ build_result.py       → status=partial included=1 excluded=3 uncertain=1 unscreened=0  (exit 0)
```

**去重合并记录**（`work/duplicates.jsonl`，C003 无 DOI，靠归一化标题并入 C002）：

```json
{"survivor": "C002", "merged_ids": ["C003"], "key": "title:theamyloidcascadehypothesisthreedecadesofdebate",
 "reason": "与 C002 重复（归一化标题相同；来源 $/snapshots/records 并入 $/snapshots/records）"}
```

**被拒决定行**（`work/rejected_decisions.jsonl`，第 6 行引句系编造，机器核验拒绝）：

```json
{"line": 6, "row": {"cand_id": "C001", ..., "evidence_quote": "double-blind multicenter phase III registration trial with positive cognitive endpoint"},
 "reasons": ["evidence_quote 未通过机器核验：归一化后不是 C001 标题/摘要的子串"]}
```

**流程报告**（`work/flow_report.md`）：

```
| identified（去重前） | 6 |
| duplicates removed | 1 |
| records screened（唯一记录） | 5 |
| 已有有效决定 | 5 |
| records excluded（均附理由） | 3 |
| uncertain（待定） | 1 |
| 未筛选 | 0 |
| included | 1 |
- [PASS] I1_identified_minus_duplicates_equals_unique — identified(6) - duplicates_removed(1) = 5 vs unique_screened(5)
- [PASS] I2_stage_title_abstract_arithmetic — screened=5 include=1 exclude=3 uncertain=1; <=unique: True; 未知cand_id: 无
- [PASS] I3_stage_title_abstract_excludes_have_criteria — 无 criterion 的排除: 无
遗漏声明：待定声明：以下 1 条候选因元数据不足判为 uncertain，待补充信息后复筛：C006。
```

**result.json 要点**：`status="partial"`（诚实：C006 判 uncertain 待定，按规则不得
宣称 success）；`limits=["1 条候选待定（uncertain），需补充元数据/全文后复筛"]`；
C001 为 include + C-DESIGN + 已核验引句 + rank_rationale；C002 带
`"merged_from": ["C003"]`；`evidence_records` 共 5 条且全部 `verified: true`；
`output_contract` 声明的 8 个 required_fields 全部在 result.json 顶层镜像。

## 负例自检（空候选集，实测）

对 `{"case_id":"SYNTH-EMPTY","records":[]}` 运行同一流水线：不崩溃，
`init` 提示“空候选集”，`flow_check` 不变量 PASS，`build_result` 输出
`status="partial"` + `limits=["空候选集：identified=0，已按诚实零结果流程处理，未发明任何候选"]`
+ 零结果声明 omission。（apply_decisions.py 对空决定文件按约定返回 exit 1，此场景应跳过。）
