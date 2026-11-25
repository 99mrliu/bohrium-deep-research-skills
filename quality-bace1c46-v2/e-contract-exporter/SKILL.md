---
name: contract-review-exporter
description: >-
  文献研究质量评估的“最后一公里”交付契约与人工复核技能。当需要：校验 result.json
  是否满足交付契约（case_id 一致、output_contract 字段全镜像、status 枚举、
  诚实 partial 语义、禁用 TODO/TBD 等占位符）；受理人工复核 overrides.jsonl 并把
  before/after 写回 change_records、生成沉淀报告；或渲染自包含 HTML 审计报告供第二人
  检视时，使用本技能。触发词：交付契约检查、result.json 校验、诚实部分交付、
  人工复核 override、审计报告、audit report、contract check、sedimentation。
---

# contract-review-exporter：交付契约 & 人工复核导出器

## 解决什么问题

文献评估跑完之后的“最后一公里”经常烂尾：结果文件缺字段、写一半留 TODO、
status 随手填、人工改完没有痕迹、同样的错误下次照犯。本技能保证交付物：

1. **契约有效** —— `scripts/contract_check.py` 检查 result.json 是否满足
   交付契约（详见 `references/result_contract.md`）；
2. **诚实部分交付** —— 做不完就是 `partial`，必须同时给出非空
   `uncertainties` 与 `partial_limits`，绝不允许用占位符冒充完成；
3. **可被第二人复核** —— `scripts/apply_overrides.py` 受理人工 override，
   全部留痕（changelog + change_records），`scripts/render_report.py` 渲染
   自包含 HTML 审计报告；
4. **修正沉淀进流程** —— 同一字段被反复人工修改时，沉淀报告把它翻译成
   流程/规模改进建议，而不是沉默的一次性补丁。

本技能**不评判文献本身**，可与任何上游评估方法组合。

## 适用条件

- 安装于 `/skills/weekly-skill`；输入 `/input/case.json` 与 `/input/task.md`；
- **完全离线**：禁止任何 live 网络访问；
- 草稿区 `/app/work`；交付物写入 `/app/output`（含 result.json）；
- 预算：**≤64 次模型请求、≤900 秒**；
- Python 3 标准库即可运行全部脚本，无第三方依赖。

## 输入契约

- `/input/case.json`：案例文件。须含 `case_id`；交付字段清单以下列任一键
  防御式递归发现：`output_contract` / `contract` / `output_fields` /
  `required_fields`，支持“字段名列表”与“对象”两种形态
  （对象取 `fields` 子列表或键名）。
- `/input/task.md`：任务说明（人读）。
- 可选：`overrides.jsonl`（人工复核行，格式见
  `references/review_protocol.md`）。

## 运行方式

```bash
S=/skills/weekly-skill
# 1) 契约检查（exit 0 通过 / 1 违规 / 2 用法错误）
python3 $S/scripts/contract_check.py --result /app/output/result.json \
    --case /input/case.json --report /app/work/check_report.json
# 2) 受理人工复核 override（恒 exit 0，拒绝行不中断）
python3 $S/scripts/apply_overrides.py --result /app/output/result.json \
    --overrides /app/work/overrides.jsonl --workdir /app/work
# 3) 渲染审计报告（HTML + 纯文本预览）
python3 $S/scripts/render_report.py --result /app/output/result.json \
    --output-dir /app/output/audit
```

## 工作流

1. **先写骨架**：评估刚开始就把一份“骨架但契约合法”的 result.json 写到
   `/app/output/result.json`（case_id、契约字段占位空值、status=partial、
   uncertainties/partial_limits 先写“待评估”之类的真实说明、
   change_records=[]），立刻跑一次 contract_check 确认骨架合法。
2. **迭代填充**：用上游评估方法填充各字段，每完成一块就重跑检查器。
3. **到期兜底**：截止时检查器仍失败 → 保持 `status: partial`，把检查器
   报告（`--report` 输出的 JSON）一并放入 `/app/output`，诚实交付。
4. **人工复核**：把复核意见整理成 overrides.jsonl 交给 apply_overrides；
   被拒绝的行看 changelog 原因，修正后重提。
5. **出审计报告**：render_report 生成 HTML + 预览，连同
   sedimentation_report.md 一起交给第二人。
6. **沉淀改进**：按沉淀报告把高频人工修正固化为模板/校验/预算调整。

## 预算分配（≤64 请求 / 900 秒）

- 骨架 + 首次契约检查：0 次请求（纯脚本），控制在 60 秒内；
- 上游评估填充：≤52 次请求、≤700 秒（主体）；
- 缺口修补与占位符清理：≤8 次请求、≤100 秒；
- 最终检查 + override 受理 + 报告渲染：0 次请求，≤40 秒；
- 余量：≥4 次请求应对检查器报告的意外违规。

## 异常处理

| 异常 | 处理 |
|---|---|
| 契约缺字段（result 少字段） | 检查器逐项列出缺失字段；补齐或改 `partial` 并在 partial_limits 中声明边界 |
| 发现占位符（TODO/TBD/FIXME/lorem/xxx） | 检查器按 JSON 路径定位；必须替换为真实内容或诚实降级为 partial（change_records 审计历史中的旧值引用除外，不参与扫描） |
| override 目标路径不存在 | apply_overrides 拒绝该行并记 changelog；**只为 change_records 追加允许创建中间层，绝不创建任意新分支** |
| override 与 old_value_expected 不符 | 拒绝该行，changelog 记录期望值与实际值；复核人确认现值后重提 |
| result.json 损坏（非法 JSON） | contract_check 干净退出 1 并给出可读消息，无 traceback |
| 截止时检查仍失败 | 诚实 partial：保留违规清单 JSON 报告随交付物一起输出 |

## result.json 契约（摘要）

顶层必填：`case_id`（与案例一致）、契约声明的全部字段、`status`
（success|partial|failed）、`uncertainties`（列表）、`change_records`
（列表）。`status=partial` ⇒ `uncertainties` 非空 **且** `partial_limits`
存在且非空。字符串值禁止占位符。`evidence` 若存在，每行须有非空
`source` 或 `locator`。完整规范见 `references/result_contract.md`；
人工复核协议见 `references/review_protocol.md`；可运行示例见
`examples/README.md`。
