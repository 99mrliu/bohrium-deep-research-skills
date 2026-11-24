# 任务：实验方案可行性评估（合成示例，非正式案例数据）

case_id: `SYNTH-CELL-ELISA-001`

你在 `/input/case.json` 中有一个"细胞培养 + ELISA 检测"课题的完整材料：
主办方价格合同、预算上限、参数有限域、设备预约时限，以及 **3 个版本化候选方案**
（PLAN-V1 / V2 / V3）。

## 要求

1. 先运行 `inspect_case.py` 探明 case.json 的真实结构（字段名不固定，禁止猜）。
2. 对每个方案版本做结构化抽取（每版一个 extraction 文件，schema 见
   `references/extraction_schema.md`，数字逐字抄写、locator 必填）。
3. 用 `validate_extraction.py` 校验后，对每个版本分别运行：
   - `recalc_budget.py`（复算每行单价×数量、核对申报小计、对上限判 超支/结余）
   - `recalc_schedule.py`（DAG + 关键路径 + 时限判定）
   - `check_domains.py`（参数域成员判定 + 单位归一化）
4. 结论分级：超支 / 超期 / 越域 = gating fail；其余异常如实列 unverified。
5. 用 `assemble_result.py` 装配 `/app/output/result.json`：必须含 `case_id`、
   output_contract 声明的全部字段、`status`、`sources`、`uncertainty`、`change_record`。
6. 所有数值结论以脚本实算输出为准；模型不得直接断言任何未复算的数字。
