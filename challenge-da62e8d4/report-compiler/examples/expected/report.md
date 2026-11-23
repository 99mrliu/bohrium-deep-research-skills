# 复现报告：synthetic-demo-001

> 本报告由 report-compiler v1.0 从机器可读台账自动编译生成，禁止手工修改；
> 报告中每个关键数字均可在 report_map.json 中追溯到台账 JSON 指针。
> 渲染器：纯标准库 SVG（无 matplotlib，已降级）。

## 材料定位

| 材料ID | 类型 | 状态 | 定位 | 备注 |
| --- | --- | --- | --- | --- |
| paper-pdf | paper_pdf | present | /input/paper.pdf | 题目提供的真实论文 PDF（合成示例中为示意路径） |
| code-method-a | candidate_code | present | /input/candidate_a/ | 候选数值方法 A（组织方合成代码，非作者原代码） |
| code-method-b | candidate_code | present | /input/candidate_b/ | 候选数值方法 B（组织方合成代码，非作者原代码） |
| author-repo | author_repository | missing | （无） | 作者官方仓库未随题提供且无法访问（预期情况），已显式登记，不得假装拥有 |
| raw-data | dataset | missing | （无） | 论文原始评测数据未随题提供（预期情况）；运行使用的是组织方合成数据，结论不得写成论文数值复现 |

## 环境与参数

运行环境：
- Python 3.12.14 / macOS arm64（合成示例环境）

| 指标ID | 指标名 | 论文值 | 单位 | 容差 | 来源定位 |
| --- | --- | --- | --- | --- | --- |
| m_acc | 准确率 accuracy | 0.934 | 比例 | abs 0.01 | 论文 Table 2, p.5 |
| m_f1 | F1 分数 | 0.881 | 比例 | abs 0.015 | 论文 Table 2, p.5 |
| m_rt | 推理耗时 runtime | 120 | s | rel 0.2 | 论文 Table 3, p.7 |

## 运行记录

| 运行ID | 方法 | 指标 | 种子 | 观测值 | 命令 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| r_a_acc | method_a | m_acc | 42,43,44 | 0.931 0.936 0.932 | `python3 candidate_a/run.py --metric accuracy --seeds 42,43,44` | ok |
| r_b_acc | method_b | m_acc | 42,43,44 | 0.899 0.903 0.901 | `python3 candidate_b/run.py --metric accuracy --seeds 42,43,44` | ok |
| r_a_f1 | method_a | m_f1 | 42,43,44 | 0.878 0.885 0.88 | `python3 candidate_a/run.py --metric f1 --seeds 42,43,44` | ok |
| r_b_f1 | method_b | m_f1 | 42,43,44 | 0.871 0.869 0.876 | `python3 candidate_b/run.py --metric f1 --seeds 42,43,44` | ok |
| r_a_rt | method_a | m_rt | 42,43,44 | 116 122 119 | `python3 candidate_a/run.py --metric runtime --seeds 42,43,44` | ok |
| r_b_rt | method_b | m_rt | 42,43,44 | 126 135 129 | `python3 candidate_b/run.py --metric runtime --seeds 42,43,44` | ok |

## 指标比较

| 指标 | 方法 | 论文值 | 复现值 | 绝对差 | 相对差 | 容差 | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| m_acc | method_a | 0.934 | 0.933 | 0.001 | 0.00107066 | abs 0.01 | ✓ 在容差内 |
| m_acc | method_b | 0.934 | 0.901 | 0.033 | 0.0353328 | abs 0.01 | ✗ 超差 |
| m_f1 | method_a | 0.881 | 0.881 | 0 | 0 | abs 0.015 | ✓ 在容差内 |
| m_f1 | method_b | 0.881 | 0.872 | 0.009 | 0.0102157 | abs 0.015 | ✓ 在容差内 |
| m_rt | method_a | 120 | 119 | 1 | 0.00833333 | rel 0.2 | ✓ 在容差内 |
| m_rt | method_b | 120 | 130 | 10 | 0.0833333 | rel 0.2 | ✓ 在容差内 |

对比图：
- m_acc：figures/comparison_m_acc.svg
- m_f1：figures/comparison_m_f1.svg
- m_rt：figures/comparison_m_rt.svg

## 差异归因

- **m_acc / method_b**（置信度 medium）：候选实现 B 的输入预处理与论文描述不一致：序列截断长度取 128，而论文方法节描述为 256，长样本信息丢失导致 accuracy 系统性偏低
  - 证据：runs.json#/runs/1（r_b_acc 三种子 0.899/0.903/0.901 均低于论文值，方向一致，属系统偏差而非随机波动）；工作日志 /app/work/runs/method_b_acc.log 中截断统计

## 复现结论

按 comparison.json 机械汇总：共 6 条比较，5 条在容差内，1 条超差（其中 1 条已有证据归因）。结论分级：**partially_reproducible（部分可复现：存在超差项，但均有证据归因）**。

注意：组织方合成代码 ≠ 作者原代码，合成数据上的达标不能表述为论文数值复现。

## 不确定性

- 论文未报告逐种子方差，容差判定基于 3 种子均值，n=3 的波动估计较弱
- 运行使用组织方合成数据，其分布与论文真实评测数据可能不同，结论不能外推为论文数值复现
- method_b accuracy 超差的归因（截断长度）置信度为 medium，未做受控消融确认

## 缺失材料

- **author-repo**（author_repository）：作者官方仓库未随题提供且无法访问（预期情况），已显式登记，不得假装拥有
- **raw-data**（dataset）：论文原始评测数据未随题提供（预期情况）；运行使用的是组织方合成数据，结论不得写成论文数值复现

## 变更记录

- 2026-11-23T10:00:00Z：初版六台账建立，两方法三指标完成运行核对
- 2026-11-23T11:30:00Z：修正 m_f1 复现值聚合方式：由单种子值改为 3 种子均值，comparison.json 与 runs.json 同步更新
