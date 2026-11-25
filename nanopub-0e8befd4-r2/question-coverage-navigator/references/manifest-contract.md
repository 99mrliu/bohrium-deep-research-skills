# Manifest 与未知 output contract 适配

工具只依赖 Python 3.9+ 标准库。`references/coverage-manifest.json` 是本合成样例的适配器，不是对官方字段的猜测。遇到未见 schema，先复制 manifest 到 `/app/work/coverage-manifest.json` 再修改。

## 契约来源优先级

1. `/input/task.md` 的 JSON 代码块中，由 `task_output_contract_pointer` 指向的契约；缺省指针是 `/output_contract`。
2. 若任务没有契约，才读 `/input/case.json` 的 `case_output_contract_pointer`。
3. 两者都没有即为运行/覆盖错误；不得用本 Skill 示例字段冒充官方契约。

任务文件可以有多个 JSON 代码块，工具选取第一个含目标指针的块。契约可为：

```json
{
  "output_contract": {
    "mode": "EXACT",
    "fields": {
      "answers": {"type": "array"},
      "sources": {"type": "array"},
      "uncertainty": {"type": "array"},
      "change_records": {"type": "array"}
    }
  }
}
```

也支持字段数组，或 JSON Schema 风格的 `properties` + `required` + `additionalProperties:false`。 properties 中出现的字段都视为声明字段；required 中额外字段也会纳入。字段默认值用于生成 skeleton，不用于伪造科学答案。

## 指针与键

- `*_pointer` 使用 RFC 6901 JSON Pointer，例如 `/questions`、`/result_payload/answers`；数组下标也可寻址。
- `*_key` 是当前单元内的键名，例如未见 schema 可将 `answer_key` 改成 `response`。
- `subquestions_pointer` 相对每个 question 对象；`unreported_pointer` 和 `searched_scope_pointer` 相对当前问题/子问题。
- `required_question_keys` 与 `required_subquestion_keys` 控制不同层级的必需键。
- `output_map` 将每个实际契约字段映射到 coverage JSON 的指针，因此 result 字段名无需与 coverage 字段同名。
- `case_id_pointer` 定位原 case ID，`case_id_output_key` 指定输出中的键；缺省均为 `case_id`。
- `result_nonempty_fields` 是额外语义防线，按实际任务设置；空数组 change_records 可被允许，但重大修改应诚实记录。

## 可定制规则

`answer_modes`、`unreported_modes`、`status_ceiling_percent`、`evidence_support_values` 和 `mode_required_support` 都可针对任务调整。不要为通过校验而放宽规则；只有任务语义确实不同才修改，并在 change_records 中说明。

`skeleton` 命令不读取 coverage，生成的只是可填写结构。`build-result` 必须先通过 coverage 校验，再依 output_map 复制数据；`audit` 会比较 result 与映射源的值，防止“coverage 完整但 result 陈旧”。

## 限制

Manifest 只适配JSON结构及上述验证语义，不自动理解任意新领域的科学规则。若任务需要完全不同的问题层级或证据逻辑，应扩展工具并补正负测试，而不是静默跳过校验。
