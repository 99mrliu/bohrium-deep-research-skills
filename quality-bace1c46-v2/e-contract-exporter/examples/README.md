# 合成示例（synthetic，非正式案例结果）

本目录是一个**完全合成、仅用于演示流程**的小例子：两条虚构文献记录、
虚构命题、合成数据。以下所有命令与输出均为在本包脚本上的**真实运行摘录**
（运行环境：Python 3 标准库，离线，macOS）。

## 输入

- `input/case.json` — 案例，`output_contract.fields` 声明 4 个字段：
  `summary / items / evidence / conclusion`；
- `input/result_draft.json` — 故意做了 3 处违规的草稿：
  缺契约字段 `conclusion`、`summary` 内含 `TBD` 占位符、
  `status=partial` 但没有 `partial_limits`；
- `input/overrides.jsonl` — 2 行人工复核：
  第 1 行修复占位符（带正确 `old_value_expected`，应被应用）；
  第 2 行带**错误的** `old_value_expected`（应被拒绝）。

## 运行流程与真实输出

准备（任选临时目录）：

```bash
W=$(mktemp -d)
cp examples/input/result_draft.json "$W/result.json"
```

### 1. 契约检查 —— 按设计失败（exit 1）

```
$ python3 scripts/contract_check.py --result $W/result.json --case examples/input/case.json --report $W/check1.json
[FAIL] 契约检查未通过，共 3 项违规：
   1. 契约($.output_contract)声明的字段在 result.json 中缺失: conclusion
   2. status=partial 要求 partial_limits 存在且非空（说明覆盖范围的边界）
   3. 发现占位符 TBD @ $.summary: '两条虚构记录结论相互冲突，总体支持强度：TBD'

修复提示：先补齐缺失字段与占位符，再确认 partial 语义（uncertainties 非空 + partial_limits 非空）。
exit=1
```

### 2. 受理人工复核 —— 1 应用 1 拒绝（exit 0）

```
$ python3 scripts/apply_overrides.py --result $W/result.json --overrides examples/input/overrides.jsonl --workdir $W
[OK] overrides 处理完成: 应用 1 行，拒绝 1 行
  [REJECTED] 第 2 行 items.1.conclusion: old_value_expected 与现值不符: 期望 '弱反向证据'，实际 '反向证据'
  changelog: $W/changelog.jsonl
  沉淀报告: $W/sedimentation_report.md
  结果写回: $W/result.json
exit=0
```

应用的 override 已写入 result.json 的 `change_records`（before/after 留痕）：

```json
[
  {
    "target_path": "summary",
    "old_value": "两条虚构记录结论相互冲突，总体支持强度：TBD",
    "new_value": "两条虚构记录结论相互冲突，总体支持强度：不足（反向证据权重更高）",
    "reviewer": "李复核",
    "rationale": "草稿遗留 TBD 占位符；依据 evidence[1] 的重复失败记录，结论应判为支持不足",
    "date": "2026-11-25",
    "applied_at": "2026-11-25T15:34:40",
    "kind": "human_override"
  }
]
```

同时生成 `$W/changelog.jsonl`（逐行决策记录）与
`$W/sedimentation_report.md`（按字段族聚类的改进建议）。

### 3. 手工修补剩余违规（契约修复，文档化的一步）

占位符已由 override 修复，但 `conclusion` 缺失与 `partial_limits` 缺失
属于**契约补齐**而非内容裁决，按检查器报告手工补上（等价于上游重新
生成该字段；生产环境中这类机械补齐也应在 change_records 里说明）：

```bash
python3 - <<'EOF'
import json
import os
p = os.path.join(os.environ["W"], "result.json")
r = json.load(open(p, encoding="utf-8"))
r["conclusion"] = "综合两条虚构记录：命题支持不足；若后续纳入更多独立重复实验，结论可重估。"
r["partial_limits"] = "仅覆盖 case.json 列出的 2 条虚构记录；未检索外部数据库；证据均为合成数据。"
json.dump(r, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
EOF
```

### 4. 契约检查 —— 通过（exit 0）

```
$ python3 scripts/contract_check.py --result $W/result.json --case examples/input/case.json --report $W/check2.json
[PASS] 契约检查通过: $W/result.json
  case_id 一致性 ✓；output_contract 字段镜像 ✓
  status='partial'；占位符扫描 ✓；evidence 定位 ✓
exit=0
```

### 5. 渲染审计报告（exit 0）

```
$ python3 scripts/render_report.py --result $W/result.json --output-dir $W/report
[OK] HTML 审计报告: $W/report/audit_report.html
[OK] 纯文本预览:   $W/report/audit_report_preview.txt
exit=0
```

纯文本预览开头摘录：

```
================================================================
文献评估交付审计报告（纯文本预览）
case_id: SYNTH-DEMO-001    status: partial
生成时间: 2026-11-25T15:34:49
================================================================
```

HTML 为单文件自包含（内联 CSS、无外部资源/JS），含页头（case_id +
status 徽章）、主结果、证据表（quote 引用块 + source/locator）、
不确定性、change_records 表、partial_limits 六个区块；所有内容经
`html.escape` 转义（实测 `<script>alert("xss")</script>` 被转义为
`&lt;script&gt;`，无原始标签注入）。

### 6. 负向检查 —— 损坏的 JSON（exit 1，干净报错，无 traceback）

```
$ printf '{ "case_id": ' > $W/broken.json
$ python3 scripts/contract_check.py --result $W/broken.json --case examples/input/case.json
[FAIL] JSON 解析失败: $W/broken.json (第 1 行第 14 列: Expecting value)
exit=1
```
