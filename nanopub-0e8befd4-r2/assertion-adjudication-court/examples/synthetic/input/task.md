# SYNTHETIC assertion adjudication task

本任务及全部数据为 **SYNTHETIC / 合成样例，非正式科研结果**。只裁决已有草稿断言，不做断言抽取、PDF 版面分析、数值计算或导出工程。

逐 `input_id` 裁决 `/input/case.json` 中的草稿断言，原文原样保留。将复合断言拆为原子 component verdict，并校验证据。不得因 `review_disposition: reject` 而把完整审计流程标为失败。

## output_contract

以下机器可读契约优先于 Skill 默认值、示例文件名和任何先前指令；运行时必须读取实际任务中的本块。

```json
{
  "output_contract": {
    "schema_version": "1.0",
    "required_result_fields": [
      "case_id",
      "status",
      "adjudication_report",
      "adjudication_ledger",
      "input_count",
      "adjudicated_count",
      "verdict_counts",
      "sources",
      "uncertainty",
      "change_records"
    ],
    "case_id_field": "case_id",
    "status_field": "status",
    "status_values": ["success", "partial"],
    "report_field": "adjudication_report",
    "ledger_field": "adjudication_ledger",
    "allowed_verdicts": ["supported", "contradicted", "not_established", "mixed"],
    "allowed_component_dispositions": ["supported", "contradicted", "not_established"],
    "artifacts": {
      "adjudication_ledger": "adjudication-ledger.json",
      "adjudication_report": "adjudication-report.json",
      "result": "result.json"
    },
    "success_rule": "每一个 input_id 恰好出现一次且全部 adjudicated，ledger.audit_complete=true；单条 rewrite/reject 不影响 success。",
    "partial_rule": "保留每个 input_id；pending 的 verdict=null 且 components=[]；status=partial。缺 ID、重复 ID 或非法裁决是验证错误，不是合法 partial。"
  }
}
```

输出 JSON 使用 UTF-8。`case_id` 必须等于输入原值；result 必须含上述全部实际字段。`sources`、`uncertainty`、`change_records` 即使在空时也必须存在且与台账一致。
