# 交付前检查清单（delivery checklist）

交付 /app/output 之前逐项核对；任何一项不通过都必须修复或如实降级 status。

## 机器校验

- [ ] `contract_validate.py --result /app/output/result.json --schema contract_schema.json --case /input/case.json`
      退出码为 0；`validation_report.json` 已留档。
- [ ] result.json 中无任何 `PENDING::` 残留（除非 status=partial/failed 且
      每个残留都在 `pending_reasons` 中有具体人工理由）。
- [ ] status=complete ⇒ 零 pending、`pending_reasons` 为空。
- [ ] case_id 与 case.json 完全一致。

## 同源渲染（防漂移）

- [ ] `audit_sheet.md` / `audit_sheet.html` / `audit_findings.json` 由**同一份**
      findings JSONL 经 `render_audit_sheet.py` 一次渲染产出。
- [ ] result.json 中 findings 数组（若契约要求）与 `audit_findings.json` 内容一致，
      条数相同、id 对应；渲染之后没有再手工改过任何一边。
- [ ] HTML 用浏览器（或文本检查）确认：UTF-8 无乱码、包含全部 finding 文本、
      无外部资源引用。

## 内容诚实性

- [ ] `sources` 只列**实际读取过**的真实文件/来源；未读的不列，读到一半的注明。
- [ ] `uncertainty` 明确写出方法局限：例如哪些统计量无法从原文重算、哪些判断
      依赖摘录而非全文、待复核条目清单。
- [ ] 每条 finding 有原文位置 + 逐字引用；无法核实的标注 `待复核` 而非删去或
      改写为确定结论。
- [ ] 缺陷分类正确：事实错误 / 证据不足 / 规范问题 / 建议 四分，不混用。

## 第三方复现说明

- [ ] 输出目录含：`result.json`、`audit_sheet.md`、`audit_sheet.html`、
      `contract_schema.json`、`validation_report.json`（及 findings 数据）。
- [ ] 附一行复现说明：第三方可用
      `python3 scripts/contract_validate.py --result result.json --schema contract_schema.json`
      重放校验，用 `render_audit_sheet.py` 从 findings 数据重新渲染审查单，
      结果应与交付物一致。
