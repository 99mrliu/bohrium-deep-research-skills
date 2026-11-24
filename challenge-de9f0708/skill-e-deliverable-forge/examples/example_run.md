# 示例运行说明（合成示例，非正式测评结果）

本目录是 skill-e-deliverable-forge 的端到端演示。**所有材料与输出均为合成示意**，不对应任何
真实论文或真实测评。

## 输入

- `mock_case.json`：合成案例，`output_contract.required_fields` 声明 8 个必备字段
  （case_id / status / findings / summary / sources / uncertainty / change_log / not_reviewed）。
- `synthetic_paper.txt`：合成论文文本，埋入 6 个已知问题：摘要与表格数字矛盾（critical）、
  疑似编造文献（major，待复核）、缺伦理声明（major）、疑似 PII（minor）、无依据首创性论断
  （minor）、缺局限性讨论（info）。
- `findings_final.json`：针对上述 6 个问题的合成 findings，全部 quote 经脚本验证为
  `synthetic_paper.txt` 的逐字摘录；F02 为待复核条目。

## 如何复跑

```bash
bash examples/run_example.sh
```

脚本（`set -euo pipefail`）分五步，全部输出写入 `examples/output/`：

1. 组装 `result_missing.json`——**故意缺 sources、not_reviewed 两个 contract 字段**，
   status 自称 complete；
2. 第一次 `contract_validate.py` → `validation_missing.json`；
3. 补齐缺失字段、status 恢复 complete，组装 `result_full.json`（change_log 保留降级痕迹）；
4. 第二次 `contract_validate.py` → `validation_full.json`；
5. `report_render.py` 渲染 `audit_report.md` / `audit_report.html`，
   `summary_dashboard.py` 生成 `dashboard.json`。

## 输出如何解读

| 文件 | 看点 |
|---|---|
| `validation_missing.json` | `verdict=FAIL`，`missing_or_empty_fields=[sources, not_reviewed]`，`auto_fix_applied` 记录了三处机械改写。 |
| `result_missing.json` | 已被自动降级：`status: complete→partial`，`change_log` 追加「机械验收未过，状态自动降级」，`uncertainty` 追加两条缺失字段说明。 |
| `validation_full.json` | `verdict=PASS`，10 项检查全过——补齐字段后的 complete 才被验收器承认。 |
| `result_full.json` | 8 个 contract 字段齐全的完整交付物。 |
| `audit_report.md` / `.html` | 人读报告：概要（status、severity×type 交叉表、待复核数、未检查面）、6 张问题卡片（定位/逐字 quote/依据/严重度/建议/verdict_status 六要素齐全）、修改优先级清单（critical→info 排序）、尾部 uncertainty 与 change_log。HTML 为自包含 CSS 单文件，无外部依赖。 |
| `dashboard.json` | 结构化摘要：severity 计数 1/2/2/1、by_type、severity×type 矩阵、facet 覆盖记账、待复核清单（F02）、top 3 优先行动。可直接被 Agent 引用或用于复跑 diff。 |

## 已验证的性质

- 埋入的 6 个问题全部出现在报告与看板中，计数与 findings_final.json 一致（critical 1 /
  major 2 / minor 2 / info 1，待复核 1）；
- 缺字段时验收 FAIL 且 exit 0（不炸管道），降级改写落盘可审计；
- 同一输入重跑两次，`dashboard.json` 与 `audit_report.md` 逐字节一致（确定性输出）。
