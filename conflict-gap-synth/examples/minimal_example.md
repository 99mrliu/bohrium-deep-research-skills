# 最小调用示例（示意，非正式案例结果）

输入（示意）：`/input/case.json`、`/input/task.md`（比较运动干预与药物对 T2DM 患者 HbA1c 的影响）。

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
  --case /input/case.json --input-dir /input --work /app/work --out /app/output
# {"ok": true, "scaffold": [...], "studies": 0, "task_chars": 123}  ← 示例值

python3 /skills/weekly-skill/scripts/matrix.py add \
  --matrix /app/output/study_matrix.json --study "Zhang et al. 2023" \
  --design rct --n 128 --population "T2DM成人" --topic 比较与效果 \
  --outcome HbA1c --direction positive --magnitude "-0.6%" \
  --limits "随访12周" --source "DOI:10.xxxx/yyyy"
# {"ok": true, "row": 1}   ← 示例值；缺 source 或 direction 非法会被拒绝

python3 /skills/weekly-skill/scripts/conflicts.py \
  --matrix /app/output/study_matrix.json --out /app/output
# {"ok": true, "conflict_pairs": 1, "topics": 2}   ← 示例值

# 冲突对须补裁定依据（编辑 conflict_register.json 的 adjudication 字段）：
# {"pair_id": "CF-001", "adjudication": "supports:B",
#  "adjudication_basis": "B 为 rct(n=128) vs A 为队列(n=60)，设计层级更高"}

python3 /skills/weekly-skill/scripts/finalize.py \
  --case /input/case.json --work /app/work --out /app/output
# {"ok": true, "status": "success", "conflict_pairs": 1,
#  "gaps": {"searched_but_absent": 0, "partially_covered": 1, "not_searched": 0}}
#   ← 示例值；存在未裁定冲突对时 status 只能为 partial
```

以上输出均为接口示意；正式运行以平台 3 个固定案例的实际矩阵为准。
