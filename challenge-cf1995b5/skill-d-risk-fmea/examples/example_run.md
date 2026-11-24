# 示例运行说明（example_run.md）

> 本目录是**合成示例**：`mock_case.json` 为合成示意案例（见 note 字段），
> `output/` 内全部文件头部标注"合成示例输出，非正式测评结果"。

## 复跑方法

```bash
bash examples/run_example.sh        # 或 PYTHON=/path/to/python3 bash examples/run_example.sh
```

脚本依次执行（全部输出写入 `examples/output/`，单次脚本运行 <1 秒）：

1. `risk_fmea.py map`：`mock_case.json` + `plan_steps.json`（7 步：手套箱溶液配制 /
   旋涂 / 加热台退火 / XRD 表征 / UV-Vis 测量 / 三批次重复性验证 / 数据归档）
   → `risk_map.json`；
2. `risk_fmea.py audit`：risk_map + `confirmation_items.json` → `audit_report.json`；
3. `risk_fmea.py decision_tree`：高 RPN（≥24）或 severity=5 → `anomaly_tree.md`；
4. `risk_fmea.py render`：risk_map → `risk_section.md`（方案风险章节，机械生成）；
5. `make_example_plan.py`（仅示例用装配器，演示 SKILL.md 第 9–10 步）：
   → `plan.json` / `plan.md` / `result.json`，并机械对账候选方案 v1。

## 输出解读（本次实跑结果）

- **risk_map.json**：7 步全部被失效模式覆盖，0 个 ORPHAN-WARN；共 26 条失效模式，
  14 条高优先级。**最高 RPN 项：FM-DRIFT 参数漂移 @ ST-03（退火），RPN=48（S3×O4×D4）**——
  发生度由基准 3 上调至 4，理由定位到 `case:equipment_domain_note`（EQ-HP 加热台允差 ±2°C
  且漂移史未知），见该条目 `score_notes`。
- **audit_report.json**：`verdict=PASS`；步骤覆盖率 1.0、失效模式四要素齐全率 1.0、
  confirmation_items 四类（安全/伦理/设备可用性/专家确认）覆盖率 1.0，gaps 为空。
- **anomaly_tree.md**：5 个高优先级失效模式（FM-DRIFT 48、FM-CONTAM 36、FM-REPRO 36、
  FM-NOSIGNAL 24、FM-SAFETY 10 但 severity=5 强制入选），每项按
  异常发生 → 判据确认 → 止损动作 → 替代路径 → 升级人工/专家确认 展开。
- **risk_section.md / plan.md**：plan.md 的"风险与异常处置"章节即 risk_section.md 原文，
  演示"风险章节由 risk_map.json 机械生成、禁止手写一句带过"。
- **result.json**：`status=complete`，`required_fields_check.missing=[]`；
  `candidate_assessment` 机械发现候选 v1 的 4 个问题（SPEC 陷阱全部检出）：
  1. `COST-ARITHMETIC`：total_cost=7330 ≠ 明细合计 5200；
  2. `PARAM-OUT-OF-DOMAIN`：退火温度 160°C 越出有限域 [80,150]；
  3. `SCHEDULE-INFEASIBLE`：est_days=40 > deadline_days=30；
  4. `EQUIPMENT-EMBEDDED-NOT-LISTED`：EQ-HP 加热台仅出现在 equipment_domain_note 文本中。

## 如何演示 ORPHAN-WARN

把 `plan_steps.json` 某步的 name/tags 改成不含任何库关键词（如 "步骤 X：待定"），
重跑 `run_example.sh`：risk_map 中该步会出现 `flags:["ORPHAN-WARN"]`，
audit 的 verdict 变为 `GAP` 并在 gaps 列出 `ORPHAN-STEP`——这就是 SKILL.md
第 5/6 步迭代修复（补关键词或 `prototype_hint`）要消解的对象。
