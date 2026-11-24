# result.json 交付契约：9 字段语义、验收标准与常见退回原因

评审的硬门槛：`/app/output/result.json` 必须含 `case_id` 以及 case.json
`output_contract.required_fields` 列出的全部字段，并诚实标注
`status`（complete/partial/blocked）、`sources`、`uncertainty`、`change_log`。
方案内容再好，缺字段、占位未填、JSON 非法，评审一样判失败。契约先行：
先 scaffold 出合法 partial，再逐字段充实。

## 字段语义与验收标准

| 字段 | 语义 | 验收标准（validate 机械检查 + 评审人工检查） | 常见退回原因 |
| --- | --- | --- | --- |
| case_id | 案例标识 | 与 case.json 的 case_id 逐字符一致（机械） | 手抄错、scaffold 后被手改 |
| revised_plan | 修订后的完整方案 | 覆盖六要素（假设与变量、对照组、设备材料、时间成本、参数范围、风险异常）；`parameters` 中每个值落在 `parameter_domains` 内（机械） | 只写局部环节缺六要素；参数越域；把前瞻合同写成已确认报价 |
| candidate_assessment | 对 case 候选方案的评估 | 逐一评估每个 candidate_plans 版本：成本算术复算、est_days 对预约吞吐、参数域合规；每个问题可定位到 case.json 路径 | 只选优不指错；漏掉 total_cost 算术错、est_days 超吞吐、参数越域、equipment_domain_note 内嵌设备未对账 |
| validation | 自校验记录 | 列出做了哪些机械校验（成本算术、参数域、时间可行性）及结论，数字可复算 | 只写"已校验"无证据；数字与 plan.json 对不上 |
| status | 交付状态 | 全字段 final 才允许 complete；否则必须 partial/blocked（机械自洽） | 字段还是 draft 就写 complete——validate 会自动降级，别手改回去 |
| uncertainty | 不确定项 | 如实列出：假设、未验证信息、降级原因（如未生成 PDF 预览的具体原因） | 空列表冒充无疑虑；谎报"已生成 PDF" |
| sources | 来源 | 每个数字可定位到 case.json 路径（如 `resource_contract.reagents[0].unit_price`）或明确标注"假设" | 数字无出处；把组织方前瞻合同写成实际供应商报价 |
| change_log | 修改记录 | 列表，记录 scaffold/fill/修复过程 | 交付后补一条假的"一次成型" |
| confirmation_items | 待确认事项 | 前瞻合同价格/排期、未确认报价、超出域的参数意图都进这里，不写成可执行事实 | 把需要确认的事写进 revised_plan 当作既定事实 |

## 机械验收（validate 子命令）检查项一览

1. `required_fields`：全部存在且非占位（非空、非 `<TODO:` 前缀）。
2. `case_id_match`：与 case.json 一致。
3. `fields_final`：全部 required 字段 `fields_status=final`。
4. `status_consistency`：status 合法且 complete 时无 draft/empty 字段。
5. `cost_arithmetic`：plan.json 每个 cost_item 满足 `unit_price*quantity==subtotal`，
   且 `sum(subtotal)==total_cost`。
6. `parameter_domains`：revised_plan.parameters 与 plan.parameters 中命中域的参数
   全部在 range/enum/step 约束内（case 未提供域则 SKIP）。

overall=FAIL 时脚本自动把 status 降为 partial 并把缺口写进
`result.validation_gaps`——诚实 partial 由脚本保证，不靠自觉。
