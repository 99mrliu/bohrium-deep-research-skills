# 交付终验报告

| 检查项 | 结果 | 说明 |
|---|---|---|
| result.json 存在 | PASS | /tmp/cc-out/result.json |
| result.json 可解析 | PASS | JSON 合法 |
| case_id 一致 | PASS | case.json='SYNTH-DEMO-0002' result.json='SYNTH-DEMO-0002' |
| 契约键存在: deliverable | PASS | 存在 |
| 契约键非空: deliverable | PASS | 非空 |
| 契约键存在: evidence_map | PASS | 存在 |
| 契约键非空: evidence_map | PASS | 空值且 status!=complete，合规 |
| partial 有 limits 说明 | PASS | status=partial 时 limits 必须非空 |
| 引用文件存在 | PASS | 全部存在 |
| 存在可编辑交付物 | PASS | deliverable.md, validation_report.md |

结论：全部通过。
