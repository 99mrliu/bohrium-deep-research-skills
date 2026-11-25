# 正式运行合同

正式入口为 `scripts/run_case.py --input /input --work /app/work --output /app/output`。case_id 原样保留，output_contract 可为字段数组；所有原字段必须出现在 `/app/output/result.json`。标准字段为 case_id、status、editable_source、export_artifact、content_map、compliance_checks、exceptions，另附 sources、uncertainty、change_records。

status 仅 success、partial、failed。启动和未目检状态为 partial；事务/输入失败为 failed；实际操作与检查完成且原生视觉复核后才可为 success。任何 pending/failed 检查不得写成 pass。

本目录旧验证器可能使用更复杂的合成合同以测试内部引擎，不是正式平台合同。正式案例始终以原始 `/input/case.json` 为权威。
