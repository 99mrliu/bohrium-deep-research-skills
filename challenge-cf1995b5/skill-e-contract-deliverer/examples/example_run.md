# 示例运行说明（合成示例，非正式测评）

本示例使用**合成的**钙钛矿退火案例 `mock_case.json`（其 `note` 字段已标明"合成示意案例"），
演示 `scripts/contract_deliver.py` 的完整契约先行工作流。`examples/output/` 下所有产物
均为脚本真实生成，文件头部已注明"合成示例输出，非正式测评结果"。

## 如何复跑

```bash
bash examples/run_example.sh
```

脚本会清空并重建 `examples/output/` 与 `examples/work/`，全程仅 Python3 标准库，秒级完成。

## 演示流程与实际观察到的行为

1. **scaffold**：解析 `mock_case.json` 的 `output_contract.required_fields`（9 字段），
   生成 `result.json` 骨架（status=partial、case_id 已填、7 个内容字段 `<TODO:...>` 占位、
   `fields_status` 追踪 empty/draft/final）与 `plan_skeleton.md`。
   —— 此刻已有一个合法的诚实 partial，任何时刻截断都可提交。
2. **写 plan.json**：成本按 case 单价真实重算（80×24 + 40×12 + 250×5 + 180×5 = 4550），
   同时纠正了候选 v1 的算术错误（其 total_cost=7330，实际 subtotal 之和为 5350）。
3. **fill 三轮**：revised_plan/candidate_assessment → validation/sources/uncertainty →
   change_log；每轮 `--finalize-field` 标记 final。
4. **故意留 confirmation_items 为 draft**（不加 `--finalize-field`）。
5. **validate 第 1 次 → FAIL**：`fields_final` 检查FAIL
   （"以下字段未 final: confirmation_items(draft)"），脚本**自动**把
   `result.status` 降为 `partial` 并把缺口写入 `result.validation_gaps`；
   报告存档为 `validation_report_fail.json`。降级由脚本保证，不靠自觉。
6. **补全**：confirmation_items 重新 fill 并 `--finalize-field`。
7. **validate 第 2 次 → PASS**：六项检查全过，脚本自动把 status 置为 `complete`；
   报告存档为 `validation_report_pass.json`。
8. **render**：生成 `plan.md`（六要素章节 + 成本可重算表 + 校验摘要表 + 确认项清单）。
   本机未安装 pandoc/libreoffice，脚本**未生成 PDF**，并把原因如实追加进
   `result.json` 的 `uncertainty`（"未生成 PDF 预览：运行环境未检测到 pandoc 或
   libreoffice/soffice……"），不谎报。

## 输出解读

| 文件 | 解读 |
| --- | --- |
| result.json | 最终交付：9 字段齐全、status=complete、fields_status 全 final；uncertainty 含 PDF 降级原因 |
| validation_report_fail.json | 第 1 次验收：overall=FAIL，gaps 指明 confirmation_items(draft)，status_after_validate=partial |
| validation_report_pass.json | 第 2 次验收：overall=PASS，status_after_validate=complete。两份对比即"FAIL→修复→PASS"的机械闭环 |
| validation_report.json | 与 pass 版相同（validate 的原始输出名） |
| plan.md | 人读渲染件：六要素、成本表（合计 4550 可复算）、校验摘要表、确认项清单 |
| plan.json | 方案机读件，validate 的成本算术/参数域检查以其为依据 |
| plan_skeleton.md | scaffold 产物，过程痕迹 |

mock_case.json 内置的三个候选方案陷阱（v1 total_cost 算术错误、v2 est_days=45 超
30 天预约吞吐、v3 退火温度 165°C 越域上限 150，以及 equipment_domain_note 内嵌的
EQ-HP 加热台不在 equipment 列表）在 `candidate_assessment` 字段中被逐一定位。
