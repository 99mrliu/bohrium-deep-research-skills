---
name: exp-contract-deliverer
description: 当任务要求向 /app/output 交付 result.json（含 case.json output_contract.required_fields 列出的全部字段）时使用。契约先行：先 scaffold 出合法 partial 保底，再逐字段 fill 充实六要素方案，validate 机械验收（FAIL 自动降级为诚实 partial），render 渲染人读 plan.md 并如实记录 PDF 降级。适用于 900 秒/有限请求预算下"任何时刻被截断都有合法交付"的场景。
---

# exp-contract-deliverer：下游交付契约与可验收渲染工程

## 1. 用途与新增价值

方案内容再好，缺 `output_contract` 要求的字段、result.json 非法、没有人读渲染件，
评审一样判失败。本 skill 把交付质量从"靠自觉"变成"由脚本机械保证"：

- **契约先行**：从 case.json 的 `output_contract.required_fields` 反推交付骨架，
  scaffold 后立即存在一个**合法的诚实 partial**（status=partial、case_id 已填、
  每字段占位 + TODO、`fields_status` 追踪 empty/draft/final）。
- **增量充实**：fill 子命令逐字段写入草稿，`--finalize-field` 标记 final。
- **机械验收**：validate 检查字段非占位、case_id 一致、status 自洽、
  plan.json 成本算术可重算、参数落在 parameter_domains 内；FAIL 时**自动**把
  status 降为 partial 并把缺口写进 `validation_gaps`——诚实降级不靠自觉。
- **人读渲染**：render 生成 plan.md（六要素 + 校验摘要表 + 确认项清单），
  探测 pandoc/libreoffice 导出 PDF，不可用则在 uncertainty 如实记录原因，绝不谎报。

## 2. 适用条件与不适用情况

适用：Harbor 类评测环境，`/input/case.json` 带 `output_contract`，需向 `/app/output`
交付 result.json 的科研方案任务（合成、表征、工艺优化等）。

不适用：纯问答无交付物任务；result.json 结构由评审方另行硬编码且与
required_fields 无关的任务（此时仍可用 validate 的成本/参数检查，但骨架以评审方为准）。

## 3. 运行时契约与路径

- 输入：`/input/case.json`（+ 可能的 task.md / 论文 PDF）。
- 工作区：`/app/work`（草稿、字段内容 JSON）。
- 交付：`/app/output`（result.json、plan.json、validation_report.json、plan.md 等）。
- 本 skill 安装于 `/skills/weekly-skill`，脚本为
  `/skills/weekly-skill/scripts/contract_deliver.py`，仅 Python3 标准库，
  缺键不崩（exit 0），单次运行 <5 秒（PDF 导出除外），`--help` 可用。

## 4. 工作流（编号步骤，命令可直接复制）

```bash
SKILL=/skills/weekly-skill/scripts/contract_deliver.py
```

1. **读 case**：读 `/input/case.json`，定位 `output_contract.required_fields`、
   `parameter_domains`、`resource_contract`、`candidate_plans`、`equipment_domain_note`。
2. **scaffold（保底，最先做）**：
   ```bash
   python3 $SKILL --case /input/case.json --out /app/output scaffold
   ```
   此刻起任何时刻被截断，都有一个 status 诚实的合法交付。
3. **正常完成六要素方案内容**：在 /app/work 起草假设与变量、对照组、设备与材料、
   时间与成本（cost_items 用 case 的 unit_price 真实算术）、参数范围
   （逐项对 parameter_domains）、风险与异常；同时评估 3 个候选方案
   （算术复算、预约吞吐、参数域、内嵌设备对账——靠脚本核对不靠肉眼）。
4. **写 plan.json** 到 /app/output（结构见第 5 节）。
5. **逐字段 fill**（内容文件放 /app/work）：
   ```bash
   python3 $SKILL --out /app/output fill --field revised_plan --file /app/work/revised_plan.json --finalize-field
   python3 $SKILL --out /app/output fill --field candidate_assessment --file /app/work/cand.json --finalize-field
   # …validation / uncertainty / sources / change_log / confirmation_items 同理
   ```
   未确认的字段先不加 `--finalize-field`，保持 draft。
6. **validate 迭代修复**：
   ```bash
   python3 $SKILL --case /input/case.json --out /app/output validate
   ```
   读 validation_report.json，按每项 `fix` 修复，回到 4-5 步直到 overall=PASS
   （PASS 时脚本自动把 status 置 complete）。
7. **render**：
   ```bash
   python3 $SKILL --case /input/case.json --out /app/output render
   ```
   产出 plan.md；有 pandoc/libreoffice 则导出 plan.pdf，无则原因自动记入 uncertainty。
8. **最终目检**：result.json 合法、status 与 fields_status 自洽、plan.md 与最终数据同步。

## 5. 输出契约

**result.json**（/app/output）：
- `case_id`：与 case.json 逐字符一致（工具维护）。
- required_fields 全部存在且非占位；本 skill 附加 `fields_status`
  （每字段 empty/draft/final）与 FAIL 时的 `validation_gaps`。
- `status`：complete（仅当全部 final 且 validate PASS）/ partial / blocked。
- `uncertainty`、`sources`、`change_log`、`confirmation_items`：语义与验收标准见
  `references/result_contract.md`；写作要点与反例见 `references/field_writing_guide.md`。

**plan.json**（/app/output，Agent 自写，validate 会重算）：
```json
{"assumptions_variables": ["…"], "controls": ["…"],
 "equipment_materials": [{"id":"EQ-GB","name":"…","source":"resource_contract.equipment[0]"}],
 "schedule": {"est_days": 24, "basis": "…"},
 "parameters": {"anneal_temperature_C": [100,110,120], "spin_coating_rpm": 4000},
 "cost_items": [{"item":"手套箱","unit_price":80,"quantity":40,"subtotal":3200}],
 "total_cost": 7330, "risks": ["…"]}
```

**plan.md**（render 产物）：标题/状态 → 1 假设与变量 → 2 对照组 → 3 设备与材料 →
4 时间与成本（成本表）→ 5 参数范围 → 6 风险与异常 → 校验摘要表 → 确认项清单。

## 6. 失败模式与止损表

| 失败模式 | 信号 | 止损 |
| --- | --- | --- |
| 忘记 scaffold 直接写 result.json | 缺字段、JSON 手误 | 工作流第 2 步永远最先做 |
| 字段 draft 就声称完成 | validate fields_final FAIL | 按 fix 提示 `--finalize-field`，不要手改 status |
| 成本照抄候选方案 | cost_arithmetic FAIL | 用 case 的 unit_price×quantity 重算 |
| 参数越域 | parameter_domains FAIL | 改回域内；想越域就写进 confirmation_items |
| PDF 工具不存在 | render 提示降级 | 正常：plan.md 即人读件，原因已入 uncertainty |
| 时间耗尽 | 预算告警 | 立即跑一次 validate+render，交付当前诚实 partial |

## 7. 输入缺失/约束冲突的降级（honest partial）

- case.json 缺失或缺 `output_contract`：scaffold 回退到默认 9 字段集，照常产出骨架。
- plan.json 暂缺：validate 的 cost_arithmetic 记 FAIL 并给修复指引，render 渲染带
  TODO 的 plan.md——都不崩。
- 某字段内容来不及确认：保持 draft，validate 自动维持 partial 并在
  validation_gaps 写明缺口。**诚实 partial 优于虚假 complete。**
- 前瞻合同信息（价格/排期）一律进 confirmation_items，不写成已确认事实。

## 8. 预算意识（先存 partial 再迭代）

- scaffold 是第一个动作：秒级成本换来"永远有可提交的合法结果"。
- 机械工作全交脚本：算术、参数域、状态一致性由 validate 检查，不用模型肉眼核对，
  把 64 次请求省给方案内容本身。
- 每 fill 完一批字段就 validate（<5 秒），报告即修复清单；收尾前 ≥60 秒做最终
  validate + render，保证渲染件与 result.json 同步。
