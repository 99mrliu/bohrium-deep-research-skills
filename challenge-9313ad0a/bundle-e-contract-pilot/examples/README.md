# 合成示例说明（synthetic demo，全部内容为合成）

本目录展示 contract-pilot 三个脚本的一次**真实脚本化运行**。synthetic-input/ 为合成输入（玩具 case、玩具任务、玩具材料），synthetic-output/ 为该次运行结束时的最终落盘状态。所有内容均为合成示例，仅用于验证脚本行为，不构成任何科研内容参照。

## 运行方式

在某一空目录（记为运行根目录）下，将 synthetic-input/ 的 case.json、task.md、material_demo.txt 复制为 input/，并建立 output/ 与 work/，然后依次执行（相对路径相对于运行根目录）：

```bash
# 1. 引导：清点材料，写出首个 partial result.json（exit 0）
python3 scripts/contract_boot.py --case input/case.json --task input/task.md --out output --work work

# 2. 检查点一（守卫演示）：在占位字段未填时请求 success，被强制回退 partial（exit 0）
python3 scripts/checkpoint.py --out output --status success --note "过早请求 success（守卫测试）"

# 3. 构建产物（示例：复制 toy_mindmap.md、写出 evidence_map.json 至 output/），随后登记
python3 scripts/checkpoint.py --out output \
  --artifact mindmap_file=output/toy_mindmap.md \
  --artifact evidence_map=output/evidence_map.json \
  --source material_demo.txt \
  --uncertainty "玩具材料未说明光反应与碳反应的能量计量关系，导图未展开（合成示例）" \
  --set bogus_field=should_be_skipped \
  --note "build 完成：登记导图与证据映射"

# 4. 检查点三：消解该不确定性并请求 success，获准（exit 0）
python3 scripts/checkpoint.py --out output \
  --resolve-uncertainty 1 \
  --status success \
  --note "不确定性经复核为可接受的合成示例限制，予以消解；全部契约字段已填"

# 5. 最终对账：verdict=pass（exit 0）
python3 scripts/final_audit.py --case input/case.json --out output --report output/contract_audit.json
```

## synthetic-output/ 文件对照

| 文件 | 来源 |
| --- | --- |
| result.json | 运行结束时的最终状态（status=success，契约 4/4 填写） |
| change_record.md | 三次 checkpoint 的 seq 1–3 记录；seq 1 展示了 success 请求被强制回退 partial 的守卫行为 |
| contract_audit.json | final_audit 报告，verdict=pass，七项检查全部通过 |
| intake_manifest.json | boot 材料清点（1 项，sha256 已记录，无缺失） |
| work_plan.md | boot 生成的六步勾选清单 |
| toy_mindmap.md / evidence_map.json | 运行中登记的合成产物文件 |

## 已验证的异常行为（不属于本目录落盘内容）

- case.json 缺失：contract_boot.py 仍写出 result.json（case_id="unknown"、status="unable_to_determine"），exit 2；
- 材料缺失：boot 播种 uncertainty 并发出 intake 警告，exit 0，不崩溃；
- 占位字段未填即请求 success：checkpoint 拒绝，强制 partial 并追加说明；
- boot 之后立即 final_audit：verdict=fail（契约字段占位、change_record 缺失），exit 1；
- --set 写入契约外字段：警告并跳过，不写入 result.json。
