# 六道质控门（QC Gates）定义

本文件是 `scripts/selfcheck.py` 的判据来源。任何一门为 **FAIL** 时，selfcheck 退出码为 1，
交付物不得对外发出；必须先修复，或将 result.json 降级为 `status=partial` 并按
`references/partial_policy.md` 写清缺口。

| 门 | 名称 | 检查内容（机器实现） | 严重度 | 未通过时的修复建议 |
| --- | --- | --- | --- | --- |
| G1 | 契约字段齐全 | `validate_result.py`：output_contract 每个字段存在且 JSON 类型匹配；case_id 一致；status 词表合法；complete 不允许 null 字段 | FAIL | 对照 `contract_checklist.json` 补齐/修正字段；改不动就降级 partial 并在 uncertainty 说明 |
| G2 | 状态诚实 | status 与内容一致：partial/failed ⇒ uncertainty 非空；change_record 非空（状态演化可复核） | FAIL | 有多少写多少：status 必须反映真实完成度；补上每次 merge 的 change_record 条目 |
| G3 | 结论-条件一致 | `lint_review.py` 硬违规（R2：有条件可行无编号条件；R5：同一 plan_id 两个结论） | FAIL | 给每个「有条件可行」补编号条件清单；统一每个方案的结论措辞，消除前后矛盾 |
| G4 | 证据锚定密度 | review_report.md 中定位锚点（`[L12]`、`（第X节）`）总数 ≥3 | WARN | 给关键结论补行号/节号定位；锚点不足的结论不得写成确定事实 |
| G5 | 产物可复算校验 | `manifest.json` 中每个文件的 SHA-256 重新计算后仍匹配；且覆盖 result.json 与 review_report.md | FAIL | 产物在 manifest 生成后又被改动：重新运行 make_manifest.py；若输入本身变了，回查 change_record 并说明 |
| G6 | 交付物齐全 | out_dir 内存在 review_report.md、result.json、渲染预览（review_report.html 或 PDF/PNG） | FAIL | 补齐缺失产物；渲染预览缺失时先跑 render_report.py，再按平台能力补 PDF/PNG |

## 总门规则

- 任一 FAIL ⇒ 总体 **FAIL**（exit 1），禁止交付。
- 无 FAIL 但有 WARN ⇒ 总体 **WARN**（exit 0），可交付但必须在报告与 result.json 的
  uncertainty 中显式声明警告项。
- 全部 PASS ⇒ 总体 **PASS**（exit 0）。

## 设计理由（治什么病）

- G1/G6 治「缺字段导致契约不合规、审查意见无法进入真实流程」。
- G2 治「状态粉饰」：partial 不是失败，隐瞒缺口才是。
- G3 治「结论与内容不一致」：结论词、条件清单、方案编号三者必须对齐。
- G4 治「事后无法复核」：没有定位锚点的结论无法回溯到原材料。
- G5 治「事后无法复算」：字节级哈希 + 命令行记录 = 第三方可重现核验。
