# 蓝图与题库字段规范

以下为具体结构约束；尖括号仅说明结构，不是能过审的内容。实际文件不得保留占位符。可运行的完整合成实例见 `examples/synthetic/`。

## 1. blueprint.json

```json
{
  "schema_version": "1.0",
  "task_intent": "<从实际 task.md 保留的总任务意图>",
  "items": [
    {
      "item_id": "item-1",
      "task_intent": "<该题服务实际任务的具体、互异意图>",
      "cognitive_operation": "locate_extract",
      "source_scope": [
        {"source_id": "<case材料source_id>", "locator": "<明确段/表/行/单元格定位>"}
      ],
      "answer_invariant": {
        "required_claims": ["<claim_id_A>", "<claim_id_B>"],
        "value_form": "<答案结构、单位、类型>",
        "acceptance_rule": "<等价改写、舍入、边界和不可接受扩展>"
      },
      "difficulty_rationale": "<目标/干扰或推理负担带来的难度>",
      "license_basis": {
        "basis": "<实际许可或case授权依据>",
        "source_ids": ["<与scope一致>"]
      },
      "rubric_plan": {
        "0": "<无有效claim或根本错误的判据>",
        "1": "<只满足明确部分claim的判据>",
        "2": "<逐项写出全部required_claims，且限定条件完整>"
      }
    }
  ]
}
```

必须恰好四个不同 item_id，四种操作分别恰好一次。`task_intent` 与 `difficulty_rationale` 不能是“理解材料/分析即可”等空泛句；locator 不能为 `*`、全文或所有来源。每项至少两个 claim_id；2 分计划必须逐字包含这些 claim_id以便与题库对齐。

骨架命令只生成上述结构，不生成任何科学内容：

```bash
python3 scripts/blueprint.py --skeleton /app/work/blueprint.json
```

## 2. item_bank.json

```json
{
  "schema_version": "1.0",
  "bank_version": "<实际版本标识>",
  "items": [
    {
      "item_id": "item-1",
      "task": "<不包含answer value的完整作答指令>",
      "task_intent": "<与蓝图对应项一致>",
      "cognitive_operation": "locate_extract",
      "source_scope": [
        {"source_id": "<同蓝图>", "locator": "<同蓝图>"}
      ],
      "input_material": [
        {
          "source_id": "<实际材料ID>",
          "locator": "<实际定位>",
          "content": "<提供给作答者的真实段落或表行及必要表头>"
        }
      ],
      "reference_answer": {"<field>": "<只从输入材料导出的答案>"},
      "rubric": {
        "0": "<零分可观察条件>",
        "1": "<partial/only/一项等明确部分条件>",
        "2": "<与reference_answer对应并包含全部蓝图claim_id>"
      },
      "difficulty": {
        "level": "medium",
        "rationale": "<与蓝图difficulty_rationale一致>"
      },
      "data_license": {
        "basis": "<与蓝图license_basis.basis一致>",
        "source_ids": ["<与source_scope一致>"]
      },
      "evidence": [
        {
          "source_id": "<必须在input_material内>",
          "locator": "<必须在input_material内>",
          "quote": "<短而相关的真实来源片段>",
          "supports": ["<claim_id_A>"]
        },
        {
          "source_id": "<可与上项相同但定位/片段不同>",
          "locator": "<明确定位>",
          "quote": "<补充另一claim的真实来源片段>",
          "supports": ["<claim_id_B>"]
        }
      ],
      "unique_answer_rationale": "<为何这些输入和判据排除竞争答案>",
      "uncertainty": [
        {"statement": "<仍未解决的限制>", "status": "unresolved"}
      ],
      "arithmetic": null
    }
  ],
  "uncertainty": [],
  "change_records": []
}
```

所有展示字段都属于必填，包括 `uncertainty` 和 `arithmetic`；无剩余不确定性或无表算术时分别用 `[]`、`null`。`difficulty` 也可为 `easy|medium|hard` 字符串，但对象形式能额外检查蓝图理由一致性。

约束要点：

- item_id、任务意图、操作、source_scope、许可依据均与蓝图一致；蓝图四个 item_id 必须全部实现。
- `input_material` 覆盖蓝图每个定位，内容足以让作答者不偷看 evidence 就能作答。
- 至少两个不同 evidence 记录；`supports` 的并集覆盖全部蓝图 claim。工具不把引文包含关系当作语义正确性的证明，仍要整体人工核读。
- `rubric` 只能有字符串键 `0`、`1`、`2`；三档归一化文本不可折叠相同，2 分覆盖所有 claim，1 分定义真正部分作答。
- reference_answer 不得为空。task 与答案值的非停用词交集会触发 `ANSWER_LEAKAGE`；数字、答案字段名和普通单位不会被单独当成泄题。
- uncertainty 中的未决命题若被无保留地重复为 reference_answer，会触发 `UNCERTAINTY_ASSERTED_AS_FACT`。

## 3. 表算术扩展

将计算题的 `arithmetic: null` 替换为：

```json
{
  "expression": "(after_value - baseline_value) / baseline_value * 100",
  "bindings": {"after_value": 4.0, "baseline_value": 2.0},
  "expected": 100.0,
  "evaluation_tolerance": 1e-9,
  "answer_tolerance": 0.05
}
```

上面纯结构数字只演示字段，不能复制为科学答案。真实 bindings 的每个值须能在该题 input_material 或 evidence 的数值中找到。`expected` 是声明的独立计算结果，工具用安全 AST 再算；`reference_answer` 必须为有限数值或含数值 `value` 的对象。若显示答案已舍入，用 `answer_tolerance` 表示容许差，不要给过大容差掩盖公式错误。

支持：数字、绑定名、括号、一元 `+/-`、二元 `+ - * /`。不支持函数调用、属性、下标、幂、导入或任意 Python 名称；除零、非有限值、超长/超深表达式均失败。工具还会检查 expected 与显示答案是否在各自容差内。

## 4. 审计与结果形状

蓝图/题项审计：

```json
{
  "tool": "blueprint.py 或 item_audit.py",
  "status": "pass 或 fail",
  "input_sha256": "<审计输入摘要>",
  "error_count": 0,
  "warning_count": 1,
  "errors": [],
  "warnings": [
    {"code": "<代号>", "path": "<稳定提示>", "message": "<处理方式>"}
  ]
}
```

错误条目在适用时含 `item_id`。`item_audit.py` 另含 `blueprint_sha256` 和操作覆盖。审计退出 2 时不可导出 success。

最终结果是**无包装顶层对象**，标准键为：

```json
{
  "case_id": "<原case_id>",
  "items": [],
  "status": "success 或 partial",
  "sources": [],
  "uncertainty": [],
  "change_records": [],
  "defects": []
}
```

实际合同声明的其他键也出现在同一顶层；如合同使用 `questions` 等别名，将映射同一实际 items 状态。严格成功要求无审计/导出缺陷且 items 恰好四个。部分结果必须保留空/不足 items、真实来源、未决不确定性、实际变更与全部缺陷，不能把 status 写成 success。

## 5. 快照输入

当前输入为标准 item_bank；`--previous` 可为另一个实际 item_bank，或本工具含 `bank` 与 `bank_sha256` 的快照。载入快照时会重算内容地址，地址不符即非零失败。diff 对逐题字段列出 `answer_changed`、`rubric_changed`、`arithmetic_changed` 及 `construct_comparable`、`scoring_comparable`。没有旧状态时不产生虚构 diff。
