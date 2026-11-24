# 最小调用示例（合成示例，非正式案例结果）

全部输入为演示接口而构造的**合成数据**：单细胞转录组解析结直肠癌肿瘤
微环境，给定约束为 24 个月周期、2 名研究生、总经费 30 万元，样本采集
窗口第 5–10 月、测序机时窗口第 9–13 月。

- `input/case.json`、`input/task.md`、`input/materials_note.md`：合成契约
  （output_contract 五字段）、合成任务与合成材料摘记。
- `plan_overrun.json`：**故意不可行**的预制计划（10 个任务，结构合法）——
  关键路径 26 个月 > 24 个月（超期 2 个月），且第 21–22 月 T07/T08/T10
  三线并行需 3 名研究生 > 编制 2 人（人力超载）。演示 cpm_check 的超期/
  超载裁定与压缩建议（T06/T07 可裁剪、T07 可并行）。
- `plan_fixed.json`：**修复后**计划片段——T06 注释范围裁剪至核心亚群
  （105→84 人日）、T07 聚焦主效配受体对（84→63 人日）、T10 公共队列
  验证后置于 T07（消除三线并行）；修复后总工期 24 个月、各月人力 ≤2、
  经费 28.5 万 ≤ 30 万，两级门控全过。
- `plan_broken.json`：故意坏结构计划——依赖成环（TA→TB→TC→TA）、悬空
  依赖 T99、无编制角色「博士后」、里程碑空交付物，演示 plan_compile
  编译门拦截。
- `run_example.sh`：端到端演示；`expected/` 为真实执行输出，
  **以未修复版 `plan_overrun.json` 的拦截报告为主展示**（`compile_overrun.json`、
  `feasibility_report.json`），修复版通过报告（`compile_fixed.json`、
  `feasibility_fixed.json`、`schedule_summary.md`）演示「迭代至全过」；
  `result.json` 为诚实 partial（本 bundle 只产出排期类字段，其余契约字段
  缺项被 final 逐一点名）。

运行：`bash examples/run_example.sh`（依赖仅 python3，标准库）。
